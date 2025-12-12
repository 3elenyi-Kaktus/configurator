import json
import logging
from pathlib import Path
import re
from threading import Lock, Thread
from typing import Any, Callable, Optional, TypeAlias

from typing_extensions import Unpack

from lib.configurator.arg_parser import IArgParser
from lib.configurator.change_poller import ChangePoller
from lib.configurator.options import IOptionName, Option
from lib.configurator.sys_options import SysOptionName, sys_options as SysOptions
from lib.json.helpers import toReadableJSON


__version__ = "0.3.1"

# it's a users responsibility to adapt (or ignore) online config reloading feature
# All classes that will support online config reloading (hot reload) must provide a corresponding interface:
#
# def callback(self, ...) -> None: ...
#
# Then the callback must be registered via subscribing to needed Config options
# Specified options will be passed to provided method on config reload


ReloadCallback: TypeAlias = Callable[[Unpack[tuple[Any, ...]]], None]
Properties: TypeAlias = list[property]


class IConfig:
    def __init__(self, arg_parser: IArgParser, registered_options: list[Option]):
        self.reload_lock: Lock = Lock()
        self.properties: list[property] = self._getProps()
        self.old_values: dict[property, Any] = {}
        self.arg_parser: IArgParser = arg_parser
        option_mapping: dict[IOptionName, Option] = {x.name: x for x in registered_options}
        sys_option_mapping: dict[IOptionName, Option] = {x.name: x for x in SysOptions}
        if len(option_mapping.keys() & sys_option_mapping.keys()) > 0:
            raise RuntimeError("Provided list of registered options overlaps with system ones, consider renaming")
        # this is a list of all available options, which can be used by this config
        self.registered_options: dict[IOptionName, Option] = option_mapping | sys_option_mapping
        self.on_reload_triggers: dict[ReloadCallback, Properties] = {}
        self.options: dict[IOptionName, Option] = None
        self.change_poller: ChangePoller = None
        self.path_to_config: Path = self.arg_parser.getConfigFilepath()
        if not self.path_to_config.is_file():
            raise RuntimeError(f"Config file {self.path_to_config} does not exist")

    def _getProps(self) -> list[property]:
        properties: list[property] = []
        for attr_name in dir(type(self)):
            attr: Any = getattr(type(self), attr_name)
            if isinstance(attr, property):
                properties.append(attr)
        return properties

    def _recreate(self):
        try:
            file_args: dict[str, Any] = json.load(open(self.path_to_config, "rt"))
            if not isinstance(file_args, dict):
                raise RuntimeError(f"Config file must contain a JSON dictionary")
        except BaseException as exc:
            raise RuntimeError(f"Failed to load config file to JSON at: {self.path_to_config}") from exc

        # reading all passed args from command line
        cmd_args: dict[str, Any] = self.arg_parser.getArgs()

        # try loading env variables from file
        # resolving file path in following order until first success: path from cmd args, path from file args, then lookup in this directory
        env_vars: dict[str, Any] = {}
        for source, env_file_path in [
            ("file args", file_args.get(SysOptionName.ENV_FILEPATH, None)),
            ("cmd args", cmd_args[SysOptionName.ENV_FILEPATH]),
            ("config directory", Path(__file__).parent / ".env"),
        ]:
            logging.info(f"Acquired env file path {env_file_path} from {source}")
            if env_file_path is None:
                continue
            variables: dict[str, Any] = self._loadEnvVars(Path(env_file_path))
            if variables is not None:
                env_vars = variables
                break

        # arguments precedence is resolved in following order: cmd args > file args > env vars
        args: dict[str, Any] = self._overrideWithArgs(env_vars, file_args)
        args = self._overrideWithArgs(args, cmd_args)

        # we collected all available options up to this point
        # now we need to inject those marked as non-required and omitted in all sources
        omitted_options: dict[str, Any] = {}
        for option_name, option in self.registered_options.items():
            if not option.required and option_name not in args:
                omitted_options[option_name] = option
        logging.info(f"Inject omitted options: {omitted_options}")
        # todo: maybe provide a default value interface for options
        #   for now, set them as None
        for option_name, _ in omitted_options.items():
            args[option_name] = None

        try:
            self.options = self._validateData(args)
        except BaseException as exc:
            raise RuntimeError(f"Failed to validate config options") from exc

        # At this point all the necessary amount of work of reading and validating arguments is done.
        # Logger can't be used earlier, because all args must be validated first, including logger config path etc.
        # That's why config file must be loaded as early, as possible
        logging.info(f"Collected arguments: {toReadableJSON(args)}")
        logging.info(f"Converted to options: {toReadableJSON(self.options)}")

    def _onReload(self):
        logging.info(f"Config reloading requested")
        with self.reload_lock:
            logging.info(f"Reload lock acquired, starting reload")
            # load all current values of properties
            for prop in self.properties:
                self.old_values[prop] = prop.fget(self)
            try:
                # reread arguments
                self._recreate()
            except BaseException as exc:
                logging.exception(exc)
                logging.error(f"Config reloading failed, keep old configuration")
                return

            # reload necessary classes based on changed props and registered reload callbacks
            for prop in self.properties:
                if self.old_values[prop] != prop.fget(self):
                    logging.info(
                        f"Property {prop.fget.__name__} was changed: {self.old_values[prop]} -> {prop.fget(self)}"
                    )
            logging.info(f"Reloaded config successfully, propagating changes to dependants")
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
                except BaseException as error:
                    logging.exception(error)
                    logging.error(f"Reloading trigger {callback} failed")
            logging.info(f"Config reloading completed")

    @staticmethod
    def _loadEnvVars(env_file_path: Path) -> Optional[dict[str, Any]]:
        if not env_file_path.is_file():
            logging.info(f"Provided path '{env_file_path}' seems to be invalid, skipping .env file loading")
            return None
        logging.info(f"Loading .env file from: {env_file_path}")
        env_vars: dict[str, Any] = {}
        with open(env_file_path, "rt") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                line: str = line.rstrip("\n")
                splitted: list[str] = line.split("=", maxsplit=1)
                if len(splitted) != 2:
                    continue
                key, value = splitted
                if re.fullmatch(r"\'.*?\'|\".*?\"", value):
                    value = value[1:-1]
                else:
                    if not all([x.isdigit() for x in value]):
                        raise RuntimeError(f"Config: Failed to interpret value {value} as integer")
                    value = int(value)
                if value == "":
                    value = None
                env_vars[key.lower()] = value
        logging.info(f"Loaded env variables successfully: {toReadableJSON(env_vars)}")
        return env_vars

    def _validateData(self, data: dict[str, Any]) -> dict[IOptionName, Any]:
        parsed_option_names: set[str] = set(data.keys())
        # all options must be from registered ones
        allowed_options: set[str] = set(self.registered_options.keys())
        if diff := parsed_option_names.difference(allowed_options):
            raise RuntimeError(f"Config: Invalid option names in config: {diff}")
        # all required options must be set
        required_options: set[str] = set()
        for option_name, option in self.registered_options.items():
            if option.required:
                required_options.add(option_name)
        if diff := required_options.difference(parsed_option_names):
            raise RuntimeError(f"Config: Missing options in config: {diff}")

        option_name: str
        value: Any
        options: dict[IOptionName, Option] = {}
        for option_name, value in data.items():
            option: Option = self.registered_options[option_name]
            if not isinstance(value, option.config_inner_type):
                raise RuntimeError(
                    f"Config: Invalid option {option_name} type: {value}, expected {option.config_inner_type}"
                )
            try:
                option.value = option.validator(value)
            except BaseException as exc:
                raise RuntimeError(f"Config: Exception occurred while validating option {option_name}") from exc
            options[option.name] = option
        return options

    @staticmethod
    def _overrideWithArgs(base_args: dict[str, Any], new_args: dict[str, Any]) -> dict[str, Any]:
        overridden_keys = {}
        for key, value in new_args.items():
            if value is not None or value is None and key not in base_args.keys():
                overridden_keys[key] = value
                base_args[key] = value
        logging.info(f"Overridden config keys: {toReadableJSON(overridden_keys)}")
        return base_args

    def _getOptionValue(self, option_name: IOptionName) -> Any:
        return self.options[option_name].value

    def setupConfigChangePoller(self):
        # setting poller to watch config file changes in online mode
        self.change_poller = ChangePoller(self.config_filepath, self._onReload)
        Thread(target=self.change_poller.poll).start()

    def addReloadCallback(self, callback: ReloadCallback, triggered_on: Properties):
        self.on_reload_triggers[callback] = triggered_on

    def atExit(self):
        self.change_poller.stopPolling()

    @property
    def config_filepath(self) -> Path:
        return self._getOptionValue(SysOptionName.CONFIG_FILEPATH)

    @property
    def env_filepath(self) -> Optional[Path]:
        return self._getOptionValue(SysOptionName.ENV_FILEPATH)
