import logging
from pathlib import Path
import re
from re import Pattern
from typing import Any

from kaktus.json_helpers.helpers import toReadableJSON


log: logging.Logger = logging.getLogger(__name__)

_env_file_pattern: Pattern[str] = re.compile(r"(?:|#.*?|(?P<name>\w+?)=(?P<value>'.*?'|\".*?\"|\d+?)(?: *?#.*?)?)\n")


class EnvParser:
    @staticmethod
    def _readFile(path: Path) -> list[str] | None:
        log.info(f"EnvParser: Loading .env file from '{path}'")
        if not path.is_file():
            log.warning("EnvParser: Path doesn't exist or isn't a file")
            return None
        if path.name != ".env" and path.suffix != ".env":
            log.warning("EnvParser: File is possibly not a .env file")
        try:
            with open(path) as env_file:
                lines: list[str] = env_file.readlines()
        except OSError as exc:
            log.exception(exc)
            log.error("EnvParser: Failed to read the file")
            return None
        return lines

    @staticmethod
    def parseFile(path: Path) -> dict[str, Any] | None:
        lines: list[str] | None = EnvParser._readFile(path)
        if lines is None:
            log.error("EnvParser: Skipping parsing .env file")
            return None

        variables: dict[str, int | str] = {}
        for line in lines:
            if (match := _env_file_pattern.fullmatch(line)) is None:
                log.error(f"EnvParser: Line '{line}' seems to be malformed")
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
        log.info(f"EnvParser: Loaded env variables successfully: {toReadableJSON(variables)}")
        return variables
