from pathlib import Path

from kaktus.configurator.commons import AccessZone
from kaktus.configurator.option import Option
from kaktus.configurator.option_group import OptionGroup, optionGroup
from kaktus.configurator.validators import PathTarget, pathValidator


@optionGroup(zone=AccessZone.ADMIN)
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
    ENABLE_HOT_RELOAD = Option(
        "enable_hot_reload",
        rtype=bool,
        required=False,
        default=False,
    )


@optionGroup(zone=AccessZone.ADMIN)
class AdminOption(OptionGroup):
    DEV_PRESET = Option(
        "dev_preset",
        rtype=str,
        required=False,
    )
