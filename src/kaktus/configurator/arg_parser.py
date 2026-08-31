import argparse
from argparse import Action, ArgumentParser
import logging
from pathlib import Path
from typing import Any

from kaktus.json_helpers.helpers import toReadableJSON
from typing_extensions import override

from kaktus.configurator.option import _MISSING, _Missing
from kaktus.configurator.sys_options import AdminOption, SystemOption


log: logging.Logger = logging.getLogger(__name__)


class SuppressingParser(ArgumentParser):
    @override
    def add_argument(self, *name_or_flags: str, **kw: Any) -> Action:
        # TODO check what will happen if required is not set, since its optional
        if kw.get("required") is False and "default" not in kw:
            kw["default"] = argparse.SUPPRESS
        return super().add_argument(*name_or_flags, **kw)


class IArgParser:
    def __init__(self, description: str) -> None:
        # We don't want to allow non-strict arguments parsing
        self.parser: SuppressingParser = SuppressingParser(description=description, allow_abbrev=False)
        self.parser.add_argument(
            "-p",
            "--config-filepath",
            required=True,
            help="Path to config file, required",
            dest=SystemOption.CONFIG_FILEPATH.name,
        )
        self.parser.add_argument(
            "--env-filepath",
            required=False,
            help="Path to .env file",
            dest=SystemOption.ENV_FILEPATH.name,
        )
        self.parser.add_argument(
            "--option-graphs-dirpath",
            required=False,
            help="Path to directory for outputting option graphs",
            dest=SystemOption.OPTION_GRAPHS_DIRPATH.name,
        )
        self.parser.add_argument(
            "--dev-preset",
            required=False,
            help="Preset ID of developer settings",
            dest=AdminOption.DEV_PRESET.name,
        )
        self.parser.add_argument(
            "--enable-hot-reload",
            required=False,
            action="store_true",
            help="Enable hot reloading of config files at runtime",
            dest=SystemOption.ENABLE_HOT_RELOAD.name,
        )
        self.args: dict[str, Any] = {}

    def parseArgs(self) -> None:
        args_namespace: argparse.Namespace = self.parser.parse_args()
        self.args = vars(args_namespace)
        log.info(f"Parsed args: {toReadableJSON(self.args)}")

    def getArgs(self) -> dict[str, Any]:
        if not self.args:
            self.parseArgs()
        return self.args

    def getArg(self, name: str) -> Any:
        if not self.args:
            self.parseArgs()
        return self.args.get(name, _MISSING)

    def getConfigFilepath(self) -> Path:
        return Path(self.getArg(SystemOption.CONFIG_FILEPATH.name))

    def getOptionGraphsDirpath(self) -> Path | None:
        arg: str | _Missing = self.getArg(SystemOption.OPTION_GRAPHS_DIRPATH.name)
        return Path(arg) if not isinstance(arg, _Missing) else None

    @property
    def env_filepath(self) -> Path | None:
        arg: str | _Missing = self.getArg(SystemOption.ENV_FILEPATH.name)
        return Path(arg) if not isinstance(arg, _Missing) else None

    @property
    def dev_preset(self) -> str | None:
        arg: str | _Missing = self.getArg(AdminOption.DEV_PRESET.name)
        return arg if not isinstance(arg, _Missing) else None

    @staticmethod
    def __json__() -> dict[str, str]:
        return {"obj": "IArgParser"}
