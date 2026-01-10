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
from configurator.options import MISSING, ExclusiveGroups, IOptionName, Option
from configurator.sys_options import SysOptionName, sys_options as SysOptions


ReloadCallback: TypeAlias = Callable[[Unpack[tuple[Any, ...]]], None]
Properties: TypeAlias = list[property]


class IConfig:
    def __init__(
        self,
        arg_parser: IArgParser,
        registered_options: list[Option],
        exclusive_groups_rules: list[ExclusiveGroups] = None,
    ):
        self.arg_parser: IArgParser = arg_parser
        self.exclusive_groups_rules: list[ExclusiveGroups] = (
            exclusive_groups_rules if exclusive_groups_rules is not None else []
        )

        option_mapping: dict[IOptionName, Option] = {x.name: x for x in registered_options}
        sys_option_mapping: dict[IOptionName, Option] = {x.name: x for x in SysOptions}
        if len(option_mapping.keys() & sys_option_mapping.keys()) > 0:
            raise RuntimeError("Provided list of registered options overlaps with system ones, consider renaming")
        # This is a composition of all possible options, which will be used by this config
        self.registered_options: dict[IOptionName, Option] = option_mapping | sys_option_mapping

        self.reload_lock: Lock = Lock()
        self.change_poller: ChangePoller = None
        self.properties: Properties = self._getProps()
        self.old_values: dict[property, Any] = {}
        self.on_reload_triggers: dict[ReloadCallback, Properties] = {}

        self.options: dict[IOptionName, Option] = {}
        self.path_to_config: Path = self.arg_parser.getConfigFilepath()
        if not self.path_to_config.is_file():
            raise RuntimeError(f"Config file at '{self.path_to_config}' doesn't exist or isn't a file")
        if self.path_to_config.suffix != ".json":
            raise RuntimeError(f"Specified file is not a JSON file: '{self.path_to_config}'")

        # TODO  Simplify pattern (comment and normal lines)
        self.env_file_pattern: Pattern = re.compile(
            r"^#.*?\n$|^\n$|^(?P<name>\w+?)=(?P<value>'.+?'|\".+?\"|\d+?)(?:\s*?#.*?)?\n$"
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

        variables: dict[str, Any] = {}
        for line in lines:
            if (match := self.env_file_pattern.fullmatch(line)) is None:
                logging.error(f"Config: .env file seems to be malformed. Line: '{line}'")
                return None
            name: str = match.group("name")
            if name is None:
                continue
            value: str = match.group("value")
            if value[0] in "\"'" and value[-1] in "\"'":
                value = value[1:-1]
            else:
                value = int(value)
            variables[name.lower()] = value
        logging.info(f"Config: Loaded env variables successfully: {toReadableJSON(variables)}")
        return variables

    def _validateOptionNames(self, args: dict[str, Any]) -> None:
        parsed_arg_names: set[str] = set(args.keys())
        # All options must be from registered ones
        allowed_options: set[str] = set(self.registered_options.keys())
        if diff := parsed_arg_names.difference(allowed_options):
            raise RuntimeError(f"Invalid option names in config: {diff}")

    def _resolveExclusiveGroups(self, options: dict[IOptionName, Option]) -> None:
        for exclusive_groups_rule in self.exclusive_groups_rules:
            group_defined: list[bool] = []
            options_set: list[set[IOptionName]] = []
            for option_group in exclusive_groups_rule:
                options_set.append(
                    set(option_name for option_name in option_group if options[option_name].raw_value is not MISSING)
                )
                group_defined.append(len(options_set[-1]) > 0)
            if group_defined.count(True) > 1:
                raise RuntimeError(f"Options {[x for x in options_set if len(x) > 0]} are exclusive")
            for option_group, group_enabled in zip(exclusive_groups_rule, group_defined):
                if group_enabled:
                    continue
                logging.info(
                    f"Config: Group {option_group} was detected as non-defined, setting its options `required` flag to False"
                )
                for option_name in option_group:
                    options[option_name].required = False

    def _recreate(self):
        # Load args from config file
        try:
            file_args: dict[str, Any] = self._readConfigFile()
        except RuntimeError as exc:
            raise RuntimeError(f"Failed to load config file from '{self.path_to_config}'") from exc

        if not isinstance(file_args, dict):
            raise RuntimeError(f"Config file must contain a JSON dictionary")

        # Read all args from command line
        cmd_args: dict[str, Any] = self.arg_parser.getArgs()

        # Load env variables from file, if possible.
        # Filepath resolve order (until first success): CMD args, file args, then lookup in this directory.
        env_vars: dict[str, Any] = {}
        for source, env_filepath in [
            ("File args", file_args.get(SysOptionName.ENV_FILEPATH, None)),
            ("CMD args", cmd_args[SysOptionName.ENV_FILEPATH]),
            ("Configurator lib directory", Path(__file__).parent / ".env"),
        ]:
            logging.info(f"Config: Trying to load .env file from '{env_filepath}' (acquired from: {source})")
            if env_filepath is None:
                continue
            variables: dict[str, Any] = self._readEnvFile(Path(env_filepath))
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
            raise RuntimeError(f"Failed to validate option names") from exc

        # At this point we performed all possible checks on arguments as is.
        # We can move their values to the corresponding options.
        logging.info(f"Config: Collected arguments: {toReadableJSON(args)}")
        options: dict[IOptionName, Option] = {key: copy(value) for key, value in self.registered_options.items()}
        # TODO: This type mismatch between str and IOptionName bugs me,
        #  but seems to be safe as we checked args for name mismatches beforehand.
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
            raise RuntimeError(f"One of exclusive options rules was violated") from exc

        # We can check for missing options now.
        # `required` flag could have been mangled by previous resolves and differ from registered options list.
        try:
            self._checkForMissing(options)
        except BaseException as exc:
            raise RuntimeError(f"Some of required options were not set") from exc

        # Nothing seems off about passed options (at least on config logic level).
        # We can safely run userspace argument checks.
        try:
            self._validateOptions(options)
        except BaseException as exc:
            raise RuntimeError(f"Failed to validate config options") from exc

        # We successfully validated all options without errors and can save them
        logging.info(f"Config: Converted to options: {toReadableJSON(options)}")
        self.options = options

    def _onReload(self):
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
    def _checkForMissing(options: dict[IOptionName, Option]) -> None:
        # All required options must be set
        set_options: set[str] = set(x for x in options.keys() if options[x].raw_value is not MISSING)
        all_options: set[str] = set(options.keys())
        required_options: set[str] = set(name for name, option in options.items() if option.required)
        if diff := required_options.difference(set_options):
            raise RuntimeError(f"Missing options in config: {diff}")

        # Just a fair warning, that some optional args weren't set
        if diff := all_options.difference(required_options).difference(set_options):
            logging.warning(f"Config: Options '{diff}' are omitted")

    @staticmethod
    def _validateOptions(options: dict[IOptionName, Option]) -> None:
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

    def _getOptionValue(self, option_name: IOptionName) -> Any:
        return self.options[option_name].value

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
        return self._getOptionValue(SysOptionName.CONFIG_FILEPATH)

    @property
    def env_filepath(self) -> Optional[Path]:
        return self._getOptionValue(SysOptionName.ENV_FILEPATH)
