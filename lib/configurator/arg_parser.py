import argparse
import logging
from argparse import ArgumentParser
from pathlib import Path
from typing import Any

from lib.json.manager import toReadableJSON
from lib.configurator.sys_options import SysOptionName


class IArgParser:
    def __init__(self, description: str) -> None:
        # we don't want to allow non-strict arguments parsing
        self.parser = ArgumentParser(description=description, allow_abbrev=False)
        self.parser.add_argument(
            "-p",
            "--config-filepath",
            required=True,
            help="Path to config file, required",
            dest=SysOptionName.CONFIG_FILEPATH,
        )
        self.parser.add_argument(
            "--env-filepath",
            required=False,
            help="Path to .env file",
            dest=SysOptionName.ENV_FILEPATH,
        )
        self.args: argparse.Namespace = None

    def parseArgs(self):
        self.args = self.parser.parse_args()
        logging.info(f"Parsed args: {toReadableJSON(vars(self.args))}")

    def getArgs(self) -> dict[str, Any]:
        if self.args is None:
            self.parseArgs()
        return vars(self.args)

    def getArg(self, name: str) -> Any:
        return self.getArgs()[name]

    def getConfigFilepath(self) -> Path:
        return Path(self.getArg(SysOptionName.CONFIG_FILEPATH))

    @staticmethod
    def __json__() -> dict[str, str]:
        return {"obj": "IArgParser"}
