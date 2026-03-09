from copy import copy
import json
from json import JSONDecodeError
import logging
from pathlib import Path
import re
from re import Pattern
from threading import Lock
from typing import Any, Callable, Optional, TypeAlias

from json_helpers.helpers import toReadableJSON
from typing_extensions import Unpack

from configurator.arg_parser import IArgParser
from configurator.change_poller import ChangePoller
from configurator.errors import (
    ExclusiveGroupViolation,
    InvalidConfig,
    InvalidOptionName,
    InvalidOptionValue,
    MissingOption,
    OptionNameOverlap,
    UnfulfilledDependency,
)
from configurator.option import MISSING, Option, OptionName
from configurator.option_group import OptionGroup
from configurator.rules import DependenciesResolver, DependencyGroup, Depends, ExclusiveGroupRule
from configurator.sys_options import SystemOption


ReloadCallback: TypeAlias = Callable[[Unpack[tuple[Any, ...]]], None]
Properties: TypeAlias = list[property]


class IConfig:
    def __init__(
        self,
        arg_parser: IArgParser,
        option_groups: list[type[OptionGroup]],
        exclusive_group_rules: Optional[list[ExclusiveGroupRule]] = None,
    ):
        self.option_groups: list[type[OptionGroup]] = option_groups
        self.arg_parser: IArgParser = arg_parser
        self.exclusive_group_rules: list[ExclusiveGroupRule] = (
            exclusive_group_rules if exclusive_group_rules is not None else []
        )

        # TODO Maybe there is a way to check for prefixes validity
        # We think of option group prefixes as of syntactic sugar, so we don't enforce any checks on how user organized his options.
        # However, this can lead to multiple options have similar names, which is a problem for us.
        # User could've created several options with exact same name by mistake too.
        option_parents: dict[OptionName, type[OptionGroup]] = {}
        registered_options: list[Option] = []
        for option_group in option_groups:
            options: list[Option] = option_group.getOptions()
            for option in options:
                if option.name in option_parents:
                    raise OptionNameOverlap(
                        f"Option '{option.name}' from '{option_group}' is already registered in '{option_parents[option.name]}'"
                    )
            option_parents.update({option.name: option_group for option in options})
            registered_options.extend(options)
        logging.info(f"Registered options: {registered_options}")

        option_mapping: dict[OptionName, Option] = {x.name: x for x in registered_options}
        sys_option_mapping: dict[OptionName, Option] = {x.name: x for x in SystemOption.getOptions()}
        if len(option_mapping.keys() & sys_option_mapping.keys()) > 0:
            raise OptionNameOverlap("Provided list of registered options overlaps with system ones, consider renaming")

        # This is a composition of all possible options, which will be used by this config
        self.registered_options: dict[OptionName, Option] = option_mapping | sys_option_mapping

        self.reload_lock: Lock = Lock()
        self.change_poller: Optional[ChangePoller] = None
        self.properties: Properties = self._getProps()
        self.old_values: dict[property, Any] = {}
        self.on_reload_triggers: dict[ReloadCallback, Properties] = {}

        self.options: dict[OptionName, Option] = {}
        self.path_to_config: Path = self.arg_parser.getConfigFilepath()
        if not self.path_to_config.is_file():
            raise InvalidConfig(f"Config file at '{self.path_to_config}' doesn't exist or isn't a file")
        if self.path_to_config.suffix != ".json":
            raise InvalidConfig(f"Specified file is not a JSON file: '{self.path_to_config}'")

        # TODO  Simplify pattern (comment and normal lines)
        self.env_file_pattern: Pattern = re.compile(
            r"^#.*?\n$|^\n$|^(?P<name>\w+?)=(?P<value>'.+?'|\".+?\"|\d+?)(?:\s*?#.*?)?\n$"
        )

        option_dependencies: dict[OptionName, Depends] = {
            option.name: option.dependencies for option in self.registered_options.values()
        }
        option_graphs_dirpath: Optional[Path] = self.arg_parser.getOptionGraphsDirpath()
        self.dependencies_resolver: DependenciesResolver = DependenciesResolver(
            option_graphs_dirpath, option_dependencies, self.exclusive_group_rules
        )

    def _getProps(self) -> Properties:
        properties: Properties = []
        for attr_name in dir(type(self)):
            attr: Any = getattr(type(self), attr_name)
            if isinstance(attr, property):
                properties.append(attr)
        return properties

    def _readConfigFile(self) -> dict[str, Any]:
        try:
            with open(self.path_to_config, "rt") as config_file:
                file_args: dict[str, Any] = json.load(config_file)
        except OSError as exc:
            raise RuntimeError(f"Failed to read config file") from exc
        except JSONDecodeError as exc:
            raise RuntimeError(f"File contents aren't a valid JSON") from exc
        return file_args

    def _readEnvFile(self, path: Path) -> Optional[dict[str, Any]]:
        logging.info(f"Config: Loading .env file from '{path}'")
        if not path.is_file():
            logging.warning(f"Config: Path '{path}' doesn't exist or isn't a file, skipping .env file loading")
            return None
        if path.suffix != ".env":
            logging.warning(f"Config: File '{path.name}' is possibly not a .env file")
        try:
            with open(path, "rt") as env_file:
                lines: list[str] = env_file.readlines()
        except OSError as exc:
            logging.exception(exc)
            logging.error(f"Config: Failed to read .env file from '{path}'")
            return None

        variables: dict[str, int | str] = {}
        for line in lines:
            if (match := self.env_file_pattern.fullmatch(line)) is None:
                logging.error(f"Config: .env file seems to be malformed. Line: '{line}'")
                return None
            name: str = match.group("name")
            if name is None:
                continue
            raw_value: str = match.group("value")
            value: int | str
            if raw_value[0] in "\"'" and raw_value[-1] in "\"'":
                value = raw_value[1:-1]
            else:
                value = int(raw_value)
            variables[name.lower()] = value
        logging.info(f"Config: Loaded env variables successfully: {toReadableJSON(variables)}")
        return variables

    def _validateOptionNames(self, args: dict[str, Any]) -> None:
        logging.debug(f"Config: Validating option names")
        # All options must be from registered ones
        allowed_options: set[str] = set(self.registered_options.keys())
        logging.debug(f"Config: Allowed options: '{allowed_options}'")

        parsed_arg_names: set[str] = set(args.keys())
        if diff := parsed_arg_names.difference(allowed_options):
            raise RuntimeError(f"Invalid option names in config: {diff}")

    def _resolveExclusiveGroups(self, options: dict[OptionName, Option]) -> None:
        for exclusive_group_rule in self.exclusive_group_rules:
            group_defined: list[bool] = []
            options_set: list[set[OptionName]] = []
            for option_group in exclusive_group_rule:
                options_set.append(
                    set(option_name for option_name in option_group if options[option_name].raw_value is not MISSING)
                )
                group_defined.append(len(options_set[-1]) > 0)
            if group_defined.count(True) > 1:
                raise RuntimeError(f"Options {[x for x in options_set if len(x) > 0]} are exclusive")
            for option_group, group_enabled in zip(exclusive_group_rule, group_defined):
                if group_enabled:
                    continue
                logging.info(
                    f"Config: Group {option_group} was detected as non-defined, setting its options `required` flag to False"
                )
                for option_name in option_group:
                    options[option_name].required = False

    def _resolveOptionDependencies(self, options: dict[OptionName, Option]) -> None:
        for option_name, option in options.items():
            if option.dependencies is None:
                continue

            dependency_groups: list[DependencyGroup] = self.dependencies_resolver.collectDependencies(option_name)
            for dependency_group in dependency_groups:
                if all(options[dependency].raw_value is not MISSING for dependency in dependency_group):
                    # Dependency group is fulfilled, we can skip further checking of this option
                    break
            else:
                # We iterated over all dependency groups, none were fulfilled
                if options[option_name].raw_value is not MISSING:
                    raise RuntimeError(
                        f"Option {option_name} was set, but none of it's dependency group rules {dependency_groups} were fulfilled"
                    )
                options[option_name].required = False

    def _flattenArguments(self, args: dict[str, Any]) -> dict[str, Any]:
        for group in sorted(self.option_groups, key=lambda x: len(x._prefix_path), reverse=True):
            logging.info(f"Config: Flattening {group._prefix_path}")
            if not group._prefix_path:
                continue
            current_args: dict[str, Any] = args
            for entry in group._prefix_path[:-1]:
                if entry not in current_args:
                    raise RuntimeError(f"Config: Expected key {entry}, but none was found")
                current_args = current_args[entry]
            logging.info(f"Config: Start {toReadableJSON(current_args)}")
            option_prefix = ""
            if group._real:
                option_prefix = f"{group._prefix_path[-1]}_"
            for key, value in current_args[group._prefix_path[-1]].items():
                current_args[option_prefix + key] = value
            current_args.pop(group._prefix_path[-1])
            logging.info(f"Config: Got {toReadableJSON(current_args)}")
            logging.info(f"Config: Flattened {toReadableJSON(args)}")
        return args

    def _recreate(self) -> None:
        # Load args from config file
        try:
            file_args: dict[str, Any] = self._readConfigFile()
        except RuntimeError as exc:
            raise InvalidConfig(f"Failed to load config file from '{self.path_to_config}'") from exc

        if not isinstance(file_args, dict):
            raise InvalidConfig(f"Config file must contain a JSON dictionary")

        # Flatten config dictionary
        try:
            file_args = self._flattenArguments(file_args)
        except RuntimeError as exc:
            raise InvalidConfig(f"Couldn't flatten config file") from exc

        # Read all args from command line
        cmd_args: dict[str, Any] = self.arg_parser.getArgs()

        # Load env variables from file, if possible.
        # Filepath resolve order (until first success): CMD args, file args, then lookup in this directory.
        env_vars: dict[str, Any] = {}
        for source, env_filepath in [
            ("File args", file_args.get(SystemOption.ENV_FILEPATH.name, None)),
            ("CMD args", cmd_args.get(SystemOption.ENV_FILEPATH.name)),
            ("Configurator lib directory", Path(__file__).parent / ".env"),
        ]:
            logging.info(f"Config: Trying to load .env file from '{env_filepath}' (acquired from: {source})")
            if env_filepath is None:
                continue
            variables: Optional[dict[str, Any]] = self._readEnvFile(Path(env_filepath))
            if variables is not None:
                env_vars = variables
                break

        # All available arguments are acquired.
        # Resolve their precedence in following order: CMD args > file args > env variables.
        args: dict[str, Any] = env_vars
        args = self._overrideArgs(args, file_args)
        args = self._overrideArgs(args, cmd_args)

        # Check for any excessive options
        try:
            self._validateOptionNames(args)
        except BaseException as exc:
            raise InvalidOptionName(f"Failed to validate option names") from exc

        # At this point we performed all possible checks on arguments as is.
        # We can move their values to the corresponding options.
        logging.info(f"Config: Collected arguments: {toReadableJSON(args)}")
        options: dict[OptionName, Option] = {key: copy(value) for key, value in self.registered_options.items()}
        for arg_name, value in args.items():
            options[arg_name].raw_value = value

        # Now we can check if set options violate any of exclusive option groups.
        # Since by design some of conflicting options could be set as required, this will clash with them being not defined.
        # This is resolved via resetting `required` flag manually while checking for errors.
        # We need to be careful to use only parsed options list instead of registered options from now on.
        # TODO: Exclusive groups are a dummy objects without any internal checks.
        #   It's necessary to add some graph resolving or checks for their validity.
        #   For now, make it a user's problem.
        try:
            self._resolveExclusiveGroups(options)
        except BaseException as exc:
            raise ExclusiveGroupViolation(f"One of exclusive options rules was violated") from exc

        # We resolved which exclusive group rules had to be applied, now we must check the option dependencies.
        # If not all dependencies for option are satisfied, then we have to do 2 things:
        # 1) check if option was set, then it's a reason for an error.
        # 2) otherwise, manually reset `required` flag, if needed.
        try:
            self._resolveOptionDependencies(options)
        except BaseException as exc:
            raise UnfulfilledDependency(
                f"One of options was set, despite of not fulfilled dependencies for it"
            ) from exc

        # We can check for missing options now.
        # `required` flag could have been mangled by previous resolves and differ from registered options list.
        try:
            self._checkForMissing(options)
        except BaseException as exc:
            raise MissingOption(f"Some of required options were not set") from exc

        # Nothing seems off about passed options (at least on config logic level).
        # We can safely run userspace argument checks.
        try:
            self._validateOptions(options)
        except BaseException as exc:
            raise InvalidOptionValue(f"Failed to validate config options") from exc

        # We successfully validated all options without errors and can save them
        logging.info(f"Config: Converted to options: {toReadableJSON(options)}")
        self.options = options

    def _onReload(self) -> None:
        logging.info(f"Config: Reload requested")
        with self.reload_lock:
            logging.info(f"Config: Reload lock acquired, starting reload")
            # Load all current values of properties
            for prop in self.properties:
                self.old_values[prop] = prop.fget(self)
            try:
                # Reread arguments
                self._recreate()
            except BaseException as exc:
                logging.exception(exc)
                logging.error(f"Config: Reload failed, keeping old configuration")
                return

            # Reload necessary classes based on changed props and registered reload callbacks
            for prop in self.properties:
                if self.old_values[prop] != prop.fget(self):
                    logging.info(
                        f"Config: Property {prop.fget.__name__} was changed: {self.old_values[prop]} -> {prop.fget(self)}"
                    )
            logging.info(f"Config: Reloaded config successfully, propagating changes to dependants")
            for callback, triggered_on in self.on_reload_triggers.items():
                args: list[Any] = []
                needs_reloading: bool = False
                for prop in triggered_on:
                    prop_value: Any = prop.fget(self)
                    args.append(prop_value)
                    if self.old_values[prop] != prop_value:
                        needs_reloading = True
                if not needs_reloading:
                    continue
                try:
                    callback(*args)
                except BaseException as exc:
                    logging.exception(exc)
                    logging.error(f"Config: Reloading trigger {callback} failed")
            logging.info(f"Config: Reload completed")

    @staticmethod
    def _checkForMissing(options: dict[OptionName, Option]) -> None:
        # All required options must be set
        set_options: set[str] = set(x for x in options.keys() if options[x].raw_value is not MISSING)
        all_options: set[str] = set(options.keys())
        required_options: set[str] = set(name for name, option in options.items() if option.required)
        if diff := required_options.difference(set_options):
            raise RuntimeError(f"Missing options in config: {diff}")

        # Just a fair warning, that some optional args weren't set
        if diff := all_options.difference(set_options):
            logging.warning(f"Config: Options '{diff}' are omitted")

    @staticmethod
    def _validateOptions(options: dict[OptionName, Option]) -> None:
        for option in options.values():
            if option.raw_value is MISSING:
                continue
            if not isinstance(option.raw_value, option.config_inner_type):
                raise RuntimeError(
                    f"Invalid option {option.name} value: {option.raw_value} of type {type(option.raw_value)} (expected {option.config_inner_type})"
                )
            try:
                option.value = option.validator(option.raw_value)
            except BaseException as exc:
                raise RuntimeError(f"Exception occurred while validating option {option.name}") from exc

    @staticmethod
    def _overrideArgs(base_args: dict[str, Any], new_args: dict[str, Any]) -> dict[str, Any]:
        overridden_keys = {}
        for key, value in new_args.items():
            if value is not None or value is None and key not in base_args.keys():
                overridden_keys[key] = value
                base_args[key] = value
        logging.info(f"Overridden config keys: {toReadableJSON(overridden_keys)}")
        return base_args

    def _getOptionValue(self, option: Option) -> Any:
        return self.options[option.name].value

    def enableHotReload(self):
        self.change_poller = ChangePoller(self.config_filepath, self._onReload)
        self.change_poller.startPolling()

    def addReloadCallback(self, callback: ReloadCallback, triggered_on: Properties):
        with self.reload_lock:
            self.on_reload_triggers[callback] = triggered_on

    def atExit(self):
        self.change_poller.stopPolling()

    @property
    def config_filepath(self) -> Path:
        return self._getOptionValue(SystemOption.CONFIG_FILEPATH)

    @property
    def env_filepath(self) -> Optional[Path]:
        return self._getOptionValue(SystemOption.ENV_FILEPATH)

    @property
    def option_graphs_dirpath(self) -> Optional[Path]:
        return self._getOptionValue(SystemOption.OPTION_GRAPHS_DIRPATH)
