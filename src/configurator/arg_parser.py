import argparse
from argparse import ArgumentParser
import logging
from pathlib import Path
from typing import Any

from json_helpers.helpers import toReadableJSON

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
            required=False,
            help="Path to .env file",
            dest=SystemOption.ENV_FILEPATH.name,
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
        return Path(self.getArg(SystemOption.CONFIG_FILEPATH.name))

    @staticmethod
    def __json__() -> dict[str, str]:
        return {"obj": "IArgParser"}
