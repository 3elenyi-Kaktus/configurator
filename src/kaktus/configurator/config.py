from collections.abc import Callable
from copy import copy
import hashlib
import json
from json import JSONDecodeError
import logging
from pathlib import Path
import re
from threading import Lock
from typing import Any, TypeAlias

from kaktus.json_helpers.helpers import toReadableJSON, writeJSON

from kaktus.configurator.arg_parser import IArgParser
from kaktus.configurator.change_poller import ChangePoller
from kaktus.configurator.commons import AccessZone, OptionName, toNonGenericType
from kaktus.configurator.env_parser import EnvParser
from kaktus.configurator.errors import (
    DependencyViolation,
    ExclusiveGroupViolation,
    InvalidConfig,
    InvalidOptionName,
    InvalidOptionValue,
    MissingOption,
    OptionNameOverlap,
)
from kaktus.configurator.option import _MISSING, Option
from kaktus.configurator.option_group import OptionGroup
from kaktus.configurator.rules import DependenciesResolver, DependencyGroup, Depends, ExclusiveGroupRule
from kaktus.configurator.sys_options import AdminOption, SystemOption


log: logging.Logger = logging.getLogger(__name__)

ReloadCallback: TypeAlias = Callable[..., None]
Properties: TypeAlias = list[property]

_PRESET_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_DEV_SUBDIR = "dev"


def _readConfigFile(fpath: Path) -> dict[str, Any]:
    try:
        with open(fpath) as config_file:
            file_args: dict[str, Any] = json.load(config_file)
    except OSError as exc:
        raise RuntimeError("Failed to read config file") from exc
    except JSONDecodeError as exc:
        raise RuntimeError("File contents aren't a valid JSON") from exc
    return file_args


class ConfigLayer:
    def __init__(
        self,
        option_groups: list[type[OptionGroup]],
        options: dict[OptionName, Option],
        zone: AccessZone,
        *,
        allow_all: bool = False,
        strict_flatten: bool = True,
    ) -> None:
        self.option_groups: list[type[OptionGroup]] = option_groups
        self.registered_options: dict[OptionName, Option] = {}
        self.zone: AccessZone = zone
        self.allow_all: bool = allow_all
        self.strict_flatten: bool = strict_flatten

        for option_name, option in options.items():
            if self._layerMayContain(option):
                self.registered_options[option_name] = option

    def _layerMayContain(self, option: Option) -> bool:
        if self.allow_all:
            return True
        name = option.name
        if name == SystemOption.ENV_FILEPATH.name:
            return True
        if name in {
            SystemOption.CONFIG_FILEPATH.name,
            SystemOption.OPTION_GRAPHS_DIRPATH.name,
            AdminOption.DEV_PRESET.name,
        }:
            return self.zone is AccessZone.ADMIN
        return option.isAccessibleFrom(self.zone)

    @staticmethod
    def _checkExcessiveOptionNames(args: dict[str, Any], allowed_options: set[str]) -> None:
        log.debug("Config: Validating option names")
        # All options must be from registered ones
        log.debug(f"Config: Allowed options: '{allowed_options}'")

        parsed_arg_names: set[str] = set(args.keys())
        if diff := parsed_arg_names.difference(allowed_options):
            raise RuntimeError(f"Invalid option names in config: {diff}")

    def _flattenArguments(self, args: dict[str, Any]) -> dict[str, Any]:
        for group in sorted(self.option_groups, key=lambda x: len(x._prefix_path), reverse=True):
            log.info(f"Config: Flattening {group._prefix_path}")
            if not group._prefix_path:
                continue
            current_args: dict[str, Any] = args
            missing_parent = False
            for entry in group._prefix_path[:-1]:
                if entry not in current_args:
                    if self.strict_flatten:
                        raise RuntimeError(f"Config: Expected key {entry}, but none was found")
                    missing_parent = True
                    break
                nested = current_args[entry]
                if not isinstance(nested, dict):
                    if self.strict_flatten:
                        raise RuntimeError(f"Config: Expected key {entry}, but none was found")
                    missing_parent = True
                    break
                current_args = nested
            if missing_parent:
                continue
            log.info(f"Config: Start {toReadableJSON(current_args)}")
            option_prefix = ""
            if group._real:
                option_prefix = f"{group._prefix_path[-1]}_"
            nested_group = current_args.get(group._prefix_path[-1], {})
            if not isinstance(nested_group, dict):
                nested_group = {}
            for key, value in nested_group.items():
                current_args[option_prefix + key] = value
            current_args.pop(group._prefix_path[-1], None)
            log.info(f"Config: Got {toReadableJSON(current_args)}")
            log.info(f"Config: Flattened {toReadableJSON(args)}")
        return args

    @staticmethod
    def _overrideArgs(base_args: dict[str, Any], new_args: dict[str, Any]) -> dict[str, Any]:
        overridden_keys = {}
        for key, value in new_args.items():
            if value is not None or value is None and key not in base_args.keys():
                overridden_keys[key] = value
                base_args[key] = value
        log.info(f"Overridden config keys: {toReadableJSON(overridden_keys)}")
        return base_args

    def collectPresentArgs(self, config_fpath: Path, env_path_override: str | None = None) -> dict[str, Any]:
        # Load args from config file
        try:
            file_args: dict[str, Any] = _readConfigFile(config_fpath)
        except RuntimeError as exc:
            raise InvalidConfig(f"Failed to load config file from '{config_fpath}'") from exc

        if not isinstance(file_args, dict):
            raise InvalidConfig("Config file must contain a JSON dictionary")

        # Flatten config dictionary
        try:
            file_args = self._flattenArguments(file_args)
        except RuntimeError as exc:
            raise InvalidConfig("Couldn't flatten config file") from exc

        # Load env variables from file, if possible.
        env_vars: dict[str, Any] = {}
        env_fpath_raw: Any = (
            env_path_override if env_path_override is not None else file_args.get(SystemOption.ENV_FILEPATH.name)
        )
        if env_fpath_raw is not None:
            log.info(f"Config: Trying to load .env file from '{env_fpath_raw}'")
            variables: dict[str, Any] | None = EnvParser.parseFile(Path(str(env_fpath_raw)))
            if variables is not None:
                env_vars = variables

        # All available arguments are acquired.
        # Resolve their precedence in following order: env variables > file args.
        args: dict[str, Any] = self._overrideArgs(file_args, env_vars)

        # Check for any excessive options
        try:
            self._checkExcessiveOptionNames(args, set(self.registered_options.keys()))
        except Exception as exc:
            raise InvalidOptionName("Failed to validate option names") from exc

        # At this point we performed all possible checks on arguments as is.
        log.info(f"Config: Collected arguments: {toReadableJSON(args)}")
        return args


def _SystemOptionGroups() -> list[type[OptionGroup]]:
    return [SystemOption, AdminOption]


class IConfig:
    def __init__(
        self,
        option_groups: list[type[OptionGroup]],
        config_fpath: Path | None = None,
        arg_parser: IArgParser | None = None,
        exclusive_group_rules: list[ExclusiveGroupRule] | None = None,
        root_dirpath: Path | None = None,
    ):
        if config_fpath is not None:
            resolved_fpath = config_fpath
        elif arg_parser is not None:
            resolved_fpath = arg_parser.getConfigFilepath()
        else:
            raise RuntimeError("Configurator needs either a path to config file or a CLI parser")
        self.config_fpath: Path = resolved_fpath
        self.root_dirpath: Path = root_dirpath if root_dirpath is not None else resolved_fpath.parent
        self.option_groups: list[type[OptionGroup]] = option_groups
        self.arg_parser: IArgParser | None = arg_parser
        self.exclusive_group_rules: list[ExclusiveGroupRule] = (
            exclusive_group_rules if exclusive_group_rules is not None else []
        )

        self.reload_lock: Lock = Lock()
        self.change_pollers: list[ChangePoller] = []
        self.layer_files: dict[AccessZone, Path] = {}
        self.properties: Properties = self._getProps()
        self.old_values: dict[property, Any] = {}
        self.on_reload_triggers: dict[ReloadCallback, Properties] = {}

        # Initial composition of all possible options to be used as a reference on config (re)load
        self.registered_options: dict[OptionName, Option] = {}
        # Actual loaded options, based on provided config
        self.options: dict[OptionName, Option] = {}

        option_graphs_dirpath: Path | None = None
        if self.arg_parser is not None:
            option_graphs_dirpath = self.arg_parser.getOptionGraphsDirpath()

        self.deps_resolver: DependenciesResolver = DependenciesResolver(option_graphs_dirpath)

        # User-provided options and other preferences might be malformed.
        # We can already check for some of the invariants without actually trying to load a real config.
        # If any of them fail, then there is no use to continue anyway.
        self._staticCheck(option_groups)

        if not self.config_fpath.is_file():
            raise InvalidConfig(f"Config file at '{self.config_fpath}' doesn't exist or isn't a file")
        if self.config_fpath.suffix != ".json":
            raise InvalidConfig(f"Specified file is not a JSON file: '{self.config_fpath}'")

    @staticmethod
    def getOptionGroupsHash(option_groups: list[type[OptionGroup]]) -> str:
        group_hashes: str = "".join(group.hash() for group in option_groups)
        combined_hash: str = hashlib.md5(group_hashes.encode()).hexdigest()
        return combined_hash

    def _allOptionGroups(self) -> list[type[OptionGroup]]:
        return [*self.option_groups, *_SystemOptionGroups()]

    def _staticCheck(self, option_groups: list[type[OptionGroup]]) -> None:
        # To simplify things, we don't enforce any checks on how user creates options.
        # However, this can lead to options with duplicate names, which might cause unexpected side effects.
        self._checkForDuplicates(option_groups)

        # Save all the options as a reference
        all_groups: list[type[OptionGroup]] = self._allOptionGroups()
        self.registered_options = {
            option.name: option for option_group in all_groups for option in option_group.getOptions()
        }

        # Check for validity of provided option relations: dependencies and exclusive group rules
        option_dependencies: dict[OptionName, Depends | None] = {
            option.name: option.dependencies for option in self.registered_options.values()
        }
        self.deps_resolver.resolve(option_dependencies, self.exclusive_group_rules)

    @staticmethod
    def _checkForDuplicates(option_groups: list[type[OptionGroup]]) -> None:
        existing_options: dict[OptionName, type[OptionGroup]] = {}
        for option_group in option_groups:
            options: list[Option] = option_group.getOptions()
            for option in options:
                if option.name in existing_options:
                    raise OptionNameOverlap(
                        f"Option '{option.name}' from '{option_group}' is already present in '{existing_options[option.name]}'"
                    )
                existing_options[option.name] = option_group

        for system_option_group in _SystemOptionGroups():
            for option in system_option_group.getOptions():
                if option.name in existing_options:
                    raise OptionNameOverlap(
                        f"Option '{option.name}' from '{existing_options[option.name]}' overlaps with the system option name"
                    )

    def _getProps(self) -> Properties:
        properties: Properties = []
        for attr_name in dir(type(self)):
            attr: Any = getattr(type(self), attr_name)
            if isinstance(attr, property):
                properties.append(attr)
        return properties

    def _resolveExclusiveGroups(self, options: dict[OptionName, Option]) -> None:
        for exclusive_group_rule in self.exclusive_group_rules:
            group_defined: list[bool] = []
            options_set: list[set[OptionName]] = []
            for option_group in exclusive_group_rule:
                options_set.append(
                    set(option_name for option_name in option_group if options[option_name].raw_value is not _MISSING)
                )
                group_defined.append(len(options_set[-1]) > 0)
            if group_defined.count(True) > 1:
                raise RuntimeError(f"Options {[x for x in options_set if len(x) > 0]} are exclusive")
            for option_group, group_enabled in zip(exclusive_group_rule, group_defined, strict=True):
                if group_enabled:
                    continue
                log.info(
                    f"Config: Group {option_group} was detected as non-defined, setting its options `required` flag to False"
                )
                for option_name in option_group:
                    options[option_name].required = False

    def _resolveOptionDependencies(self, options: dict[OptionName, Option]) -> None:
        for option_name, option in options.items():
            if option.dependencies is None:
                continue

            dependency_groups: list[DependencyGroup] = self.deps_resolver.collectDependencies(option_name)
            for dependency_group in dependency_groups:
                if all(options[dependency].raw_value is not _MISSING for dependency in dependency_group):
                    # Dependency group is fulfilled, we can skip further checking of this option
                    break
            else:
                # We iterated over all dependency groups, none were fulfilled
                if options[option_name].raw_value is not _MISSING:
                    raise RuntimeError(
                        f"Option {option_name} was set, but none of it's dependency group rules {dependency_groups} were fulfilled"
                    )
                options[option_name].required = False

    def _resolveCatalogFile(self, subdir: str, preset_id: str, kind: str) -> Path:
        if _PRESET_ID_PATTERN.fullmatch(preset_id) is None:
            raise InvalidConfig(f"Invalid {kind.capitalize()} preset id: {preset_id}")
        fpath: Path = self.root_dirpath / subdir / f"{preset_id}.json"
        if not fpath.is_file():
            raise InvalidConfig(f"{kind.capitalize()} preset '{preset_id}' was not found at '{fpath}'")
        return fpath

    def _makeLayer(self, zone: AccessZone, *, allow_all: bool, strict_flatten: bool) -> ConfigLayer:
        return ConfigLayer(
            self._allOptionGroups(),
            self.registered_options,
            zone,
            allow_all=allow_all,
            strict_flatten=strict_flatten,
        )

    def _applyPresentArgs(self, options: dict[OptionName, Option], present: dict[str, Any], zone: AccessZone) -> None:
        applied = dict(present)
        if zone is not AccessZone.ADMIN:
            applied.pop(SystemOption.ENV_FILEPATH.name, None)
        for arg_name, value in applied.items():
            option = options[arg_name]
            option.raw_value = value
            option.source_zone = zone

    def _cmdArg(self, cmd_args: dict[str, Any], name: str) -> Any:
        value = cmd_args.get(name, _MISSING)
        return None if value is _MISSING else value

    def _isSingleFile(self) -> bool:
        dev_preset_id: str | None = None
        if self.arg_parser is not None:
            dev_preset_id = self.arg_parser.dev_preset
        if dev_preset_id is not None:
            return False

        try:
            raw_admin: dict[str, Any] = _readConfigFile(self.config_fpath)
        except RuntimeError as exc:
            raise InvalidConfig(f"Failed to load config file from '{self.config_fpath}'") from exc
        if not isinstance(raw_admin, dict):
            raise InvalidConfig("Config file must contain a JSON dictionary")
        dev_preset_id = raw_admin.get(AdminOption.DEV_PRESET.name)
        if dev_preset_id is not None:
            return False

        env_fpath: Path | None = raw_admin.get(SystemOption.ENV_FILEPATH.name)
        if env_fpath is None:
            if self.arg_parser is None or self.arg_parser.env_filepath is None:
                return True
            env_fpath = self.arg_parser.env_filepath
        parsed_env = EnvParser.parseFile(Path(str(env_fpath)))
        if parsed_env is not None:
            dev_preset_id = parsed_env.get(AdminOption.DEV_PRESET.name)
        return dev_preset_id is None

    def loadOptions(self) -> dict[OptionName, Option]:
        cmd_args: dict[str, Any]
        if self.arg_parser is not None:
            # Read all args from CLI
            cmd_args = self.arg_parser.getArgs()
        else:
            cmd_args = {SystemOption.CONFIG_FILEPATH.name: str(self.config_fpath)}

        options: dict[OptionName, Option] = {key: copy(value) for key, value in self.registered_options.items()}

        self.layer_files = {AccessZone.ADMIN: self.config_fpath}
        layer_payloads: list[tuple[AccessZone, dict[str, Any]]] = []

        admin_env_override = self._cmdArg(cmd_args, SystemOption.ENV_FILEPATH.name)
        admin_env_override_str = str(admin_env_override) if admin_env_override is not None else None

        if self._isSingleFile():
            admin_layer = self._makeLayer(AccessZone.ADMIN, allow_all=True, strict_flatten=True)
            present = admin_layer.collectPresentArgs(self.config_fpath, env_path_override=admin_env_override_str)
            layer_payloads.append((AccessZone.ADMIN, present))
        else:
            admin_layer = self._makeLayer(AccessZone.ADMIN, allow_all=False, strict_flatten=False)
            admin_present = admin_layer.collectPresentArgs(self.config_fpath, env_path_override=admin_env_override_str)
            layer_payloads.append((AccessZone.ADMIN, admin_present))

            if self._cmdArg(cmd_args, AdminOption.DEV_PRESET.name) is not None:
                dev_preset_id = self._cmdArg(cmd_args, AdminOption.DEV_PRESET.name)
            else:
                dev_preset_id = admin_present.get(AdminOption.DEV_PRESET.name)
            dev_path = self._resolveCatalogFile(_DEV_SUBDIR, str(dev_preset_id), "dev")
            self.layer_files[AccessZone.DEV] = dev_path

            dev_layer = self._makeLayer(AccessZone.DEV, allow_all=False, strict_flatten=False)
            dev_present = dev_layer.collectPresentArgs(dev_path)
            layer_payloads.append((AccessZone.DEV, dev_present))

        # Overlay options: dev > admin > CMD
        for zone, present in reversed(layer_payloads):
            self._applyPresentArgs(options, present, zone)

        for arg_name, value in cmd_args.items():
            if value is _MISSING:
                continue
            options[arg_name].raw_value = value

        return options

    def _recreate(self) -> None:
        options: dict[OptionName, Option] = self.loadOptions()

        # Now we can check if set options violate any of exclusive option groups.
        # Since by design some of conflicting options could be set as required, this will clash with them being not defined.
        # This is resolved via resetting `required` flag manually while checking for errors.
        # We need to be careful to use only parsed options list instead of registered options from now on.
        # TODO: Exclusive groups are a dummy objects without any internal checks.
        #   It's necessary to add some graph resolving or checks for their validity.
        #   For now, make it a user's problem.
        try:
            self._resolveExclusiveGroups(options)
        except Exception as exc:
            raise ExclusiveGroupViolation("One of exclusive options rules was violated") from exc

        # We resolved which exclusive group rules had to be applied, now we must check the option dependencies.
        # If not all dependencies for option are satisfied, then we have to do 2 things:
        # 1) check if option was set, then it's a reason for an error.
        # 2) otherwise, manually reset `required` flag, if needed.
        try:
            self._resolveOptionDependencies(options)
        except Exception as exc:
            raise DependencyViolation("One of options was set, despite of not fulfilled dependencies for it") from exc

        # We can check for missing options now.
        # `required` flag could have been mangled by previous resolves and differ from registered options list.
        try:
            self._checkForMissing(options)
        except Exception as exc:
            raise MissingOption("Some of required options were not set") from exc

        # Nothing seems off about passed options (at least on config logic level).
        # We can safely run userspace argument checks.
        try:
            self._validateOptions(options)
        except Exception as exc:
            raise InvalidOptionValue("Failed to validate config options") from exc

        # We successfully validated all options without errors and can save them
        log.info(f"Config: Converted to options: {toReadableJSON(options)}")
        self.options = options

    def _readProp(self, prop: property) -> Any:
        getter = prop.fget
        if getter is None:
            raise RuntimeError(f"Property {prop} has no getter")
        return getter(self)

    def _onReload(self) -> None:
        log.info("Config: Reload requested")
        with self.reload_lock:
            log.info("Config: Reload lock acquired, starting reload")
            # Load all current values of properties
            for prop in self.properties:
                self.old_values[prop] = self._readProp(prop)
            previous_files = set(self.layer_files.values())
            try:
                # Reread arguments
                self._recreate()
            except Exception as exc:
                log.exception(exc)
                log.error("Config: Reload failed, keeping old configuration")
                return

            # Reload necessary classes based on changed props and registered reload callbacks
            for prop in self.properties:
                if self.old_values[prop] != self._readProp(prop):
                    prop_name: str = getattr(prop.fget, "__name__", "<property>")
                    log.info(
                        f"Config: Property {prop_name} was changed: {self.old_values[prop]} -> {self._readProp(prop)}"
                    )
            log.info("Config: Reloaded config successfully, propagating changes to dependants")
            for callback, triggered_on in self.on_reload_triggers.items():
                args: list[Any] = []
                needs_reloading: bool = False
                for prop in triggered_on:
                    prop_value: Any = self._readProp(prop)
                    args.append(prop_value)
                    if self.old_values[prop] != prop_value:
                        needs_reloading = True
                if not needs_reloading:
                    continue
                try:
                    callback(*args)
                except Exception as exc:
                    log.exception(exc)
                    log.error(f"Config: Reloading trigger {callback} failed")
            if self.change_pollers and set(self.layer_files.values()) != previous_files:
                self._restartHotReloadPollers()
            log.info("Config: Reload completed")

    @staticmethod
    def _checkForMissing(options: dict[OptionName, Option]) -> None:
        # All required options must be set
        set_options: set[str] = set(x for x in options.keys() if options[x].raw_value is not _MISSING)
        all_options: set[str] = set(options.keys())
        required_options: set[str] = set(name for name, option in options.items() if option.required)
        if diff := required_options.difference(set_options):
            raise RuntimeError(f"Missing options in config: {diff}")

        # Just a fair warning, that some optional args weren't set
        if diff := all_options.difference(set_options):
            log.warning(f"Config: Options '{diff}' are omitted")

    @staticmethod
    def _validateOptions(options: dict[OptionName, Option]) -> None:
        for option in options.values():
            if option.raw_value is _MISSING:
                continue
            if not isinstance(option.raw_value, toNonGenericType(option.in_type)):
                raise RuntimeError(
                    f"Invalid option {option.name} value: {option.raw_value} of type {type(option.raw_value)} (expected {option.in_type})"
                )
            try:
                option.value = option.validator(option.raw_value)
            except Exception as exc:
                raise RuntimeError(f"Exception occurred while validating option {option.name}") from exc

    def _getOptionValue(self, option: Option) -> Any:
        return self.options[option.name].value

    def _fileForOption(self, option: Option) -> Path:
        loaded = self.options.get(option.name, option)
        source = loaded.source_zone if loaded.source_zone is not None else loaded.zone
        if source is AccessZone.NOTSET:
            source = AccessZone.ADMIN
        return self.layer_files.get(source, self.config_fpath)

    def _setOptionValue(self, option_group: type[OptionGroup], option: Option, new_value: Any) -> None:
        log.info(f"Config: Changing option '{option.name}' (from group: {option_group}) to: {new_value}")
        target = self._fileForOption(option)
        path = option_group._prefix_path
        try:
            config_json: dict[str, Any] = _readConfigFile(target)
        except RuntimeError as exc:
            raise InvalidConfig(f"Failed to load config file from '{target}'") from exc

        current_config: dict[str, Any] = config_json
        for name in path:
            current_config = current_config[name]

        option_name_prefix: str = "_".join(option_group._real_prefix_path) + "_"
        log.info(f"Config: Option name prefix: '{option_name_prefix}'")
        current_config[option.name.removeprefix(option_name_prefix)] = new_value
        log.info(toReadableJSON(config_json))
        writeJSON(target, config_json)

    def _watchedFiles(self) -> list[Path]:
        files = list(self.layer_files.values())
        if not files:
            files = [self.config_fpath]
        return files

    def _restartHotReloadPollers(self) -> None:
        for poller in self.change_pollers:
            poller.stopPolling()
        self.change_pollers = []
        for fpath in self._watchedFiles():
            poller = ChangePoller(fpath, self._onReload)
            poller.startPolling()
            self.change_pollers.append(poller)

    def enableHotReload(self) -> None:
        if self.change_pollers:
            self._restartHotReloadPollers()
            return
        for fpath in self._watchedFiles():
            poller = ChangePoller(fpath, self._onReload)
            poller.startPolling()
            self.change_pollers.append(poller)

    def addReloadCallback(self, callback: ReloadCallback, triggered_on: Properties) -> None:
        with self.reload_lock:
            self.on_reload_triggers[callback] = triggered_on

    def atExit(self) -> None:
        for poller in self.change_pollers:
            poller.stopPolling()
        self.change_pollers = []

    @property
    def config_filepath(self) -> Path:
        return self._getOptionValue(SystemOption.CONFIG_FILEPATH)  # type: ignore[no-any-return]

    @property
    def env_filepath(self) -> Path | None:
        return self._getOptionValue(SystemOption.ENV_FILEPATH)  # type: ignore[no-any-return]

    @property
    def option_graphs_dirpath(self) -> Path | None:
        return self._getOptionValue(SystemOption.OPTION_GRAPHS_DIRPATH)  # type: ignore[no-any-return]
