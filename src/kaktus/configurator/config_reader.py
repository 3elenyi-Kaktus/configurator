"""Read config files through format-specific backends.

The file suffix selects the backend. JSON and TOML are registered by default.
Another backend can be added with ``ConfigReader.register``.
"""

from __future__ import annotations

import json
from json import JSONDecodeError
import logging
from pathlib import Path
import sys
from typing import Any, Protocol


if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


log: logging.Logger = logging.getLogger(__name__)


class ConfigDecodeError(Exception):
    """File bytes could not be parsed as the selected format."""


class UnsupportedConfigFormat(Exception):
    """No backend is registered for this file suffix."""


class ConfigFileBackend(Protocol):
    suffixes: tuple[str, ...]

    def readFile(self, path: Path) -> Any: ...


class JSONReader:
    suffixes: tuple[str, ...] = (".json",)

    def readFile(self, path: Path) -> Any:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ConfigDecodeError(f"Config file '{path}' is not valid UTF-8") from exc
        try:
            return json.loads(text)
        except JSONDecodeError as exc:
            raise ConfigDecodeError(f"Config file '{path}' is not valid JSON") from exc


class TOMLReader:
    suffixes: tuple[str, ...] = (".toml",)

    def readFile(self, path: Path) -> Any:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ConfigDecodeError(f"Config file '{path}' is not valid UTF-8") from exc
        try:
            return tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigDecodeError(f"Config file '{path}' is not valid TOML") from exc


class ConfigReader:
    def __init__(self) -> None:
        self._backends: dict[str, ConfigFileBackend] = {}

    def register(self, backend: ConfigFileBackend) -> None:
        for suffix in backend.suffixes:
            normalized = suffix.lower()
            if not normalized.startswith("."):
                normalized = f".{normalized}"
            if normalized in self._backends:
                raise RuntimeError(f"Config reader for '{normalized}' is already registered")
            self._backends[normalized] = backend
        log.info("ConfigReader: Registered suffixes %s", backend.suffixes)

    def suffixes(self) -> tuple[str, ...]:
        return tuple(sorted(self._backends))

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in self._backends

    def readFile(self, path: Path) -> Any:
        backend = self._backends.get(path.suffix.lower())
        if backend is None:
            supported = ", ".join(self.suffixes()) or "(none)"
            raise UnsupportedConfigFormat(
                f"Unsupported config file format '{path.suffix}' for '{path}' (supported: {supported})"
            )
        log.info("ConfigReader: Reading '%s'", path)
        return backend.readFile(path)


def defaultConfigReader() -> ConfigReader:
    reader = ConfigReader()
    reader.register(JSONReader())
    reader.register(TOMLReader())
    return reader


configReader: ConfigReader = defaultConfigReader()
