import logging

from kaktus.configurator._version import __version__
from kaktus.configurator.arg_parser import IArgParser
from kaktus.configurator.commons import AccessZone
from kaktus.configurator.config import IConfig
from kaktus.configurator.option import Option
from kaktus.configurator.option_group import OptionGroup, optionGroup
from kaktus.configurator.rules import Depends


_log = logging.getLogger(__name__)
_log.addHandler(logging.NullHandler())
_log.setLevel(logging.WARNING)


def setLogLevel(level: int | str) -> None:
    if isinstance(level, str):
        resolved = logging.getLevelName(level.upper())
        if not isinstance(resolved, int):
            raise ValueError(f"Unknown log level: {level}")
        level = resolved
    _log.setLevel(level)


__all__ = [
    "__version__",
    "AccessZone",
    "Option",
    "OptionGroup",
    "optionGroup",
    "IConfig",
    "IArgParser",
    "Depends",
    "setLogLevel",
]
