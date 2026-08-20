import logging

from kaktus.configurator._version import __version__
from kaktus.configurator.arg_parser import IArgParser
from kaktus.configurator.config import IConfig
from kaktus.configurator.option import Option
from kaktus.configurator.option_group import OptionGroup, optionGroup
from kaktus.configurator.rules import Depends


logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "__version__",
    "Option",
    "OptionGroup",
    "optionGroup",
    "IConfig",
    "IArgParser",
    "Depends",
]
