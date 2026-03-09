import argparse
from argparse import ArgumentParser
import logging
from pathlib import Path
from typing import Any, Optional

from json_helpers.helpers import toReadableJSON

from configurator.option import MISSING, Missing
from configurator.sys_options import SystemOption


class IArgParser:
    def __init__(self, description: str) -> None:
        # we don't want to allow non-strict arguments parsing
        self.parser = ArgumentParser(description=description, allow_abbrev=False)
        self.parser.add_argument(
            "-p",
            "--config-filepath",
            required=True,
            help="Path to config file, required",
            dest=SystemOption.CONFIG_FILEPATH.name,
        )
        self.parser.add_argument(
            "--env-filepath",
            default=argparse.SUPPRESS,
            required=False,
            help="Path to .env file",
            dest=SystemOption.ENV_FILEPATH.name,
        )
        self.parser.add_argument(
            "--option-graphs-dirpath",
            default=argparse.SUPPRESS,
            required=False,
            help="Path to directory for outputting option graphs",
            dest=SystemOption.OPTION_GRAPHS_DIRPATH.name,
        )
        self.args: dict[str, Any] = {}

    def parseArgs(self) -> None:
        args_namespace: argparse.Namespace = self.parser.parse_args()
        self.args = vars(args_namespace)
        logging.info(f"Parsed args: {toReadableJSON(self.args)}")

    def getArgs(self) -> dict[str, Any]:
        if not self.args:
            self.parseArgs()
        return self.args

    def getArg(self, name: str) -> Any:
        if not self.args:
            self.parseArgs()
        return self.args.get(name, MISSING)

    def getConfigFilepath(self) -> Path:
        return Path(self.getArg(SystemOption.CONFIG_FILEPATH.name))

    def getOptionGraphsDirpath(self) -> Optional[Path]:
        arg: str | Missing = self.getArg(SystemOption.OPTION_GRAPHS_DIRPATH.name)
        return Path(arg) if arg is not MISSING else None

    @staticmethod
    def __json__() -> dict[str, str]:
        return {"obj": "IArgParser"}
