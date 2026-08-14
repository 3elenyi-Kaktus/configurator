from pathlib import Path

from kaktus.configurator.option import Option
from kaktus.configurator.option_group import OptionGroup
from kaktus.configurator.validators import PathTarget, pathValidator


class SystemOption(OptionGroup):
    CONFIG_FILEPATH = Option(
        "config_filepath",
        in_type=str,
        rtype=Path,
        validator=pathValidator(target=PathTarget.FILE),
    )
    ENV_FILEPATH = Option(
        "env_filepath",
        in_type=str,
        validator=pathValidator(target=PathTarget.FILE),
        required=False,
    )
    OPTION_GRAPHS_DIRPATH = Option(
        "option_graphs_dirpath",
        in_type=str,
        validator=pathValidator(),
        required=False,
    )
