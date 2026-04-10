from configurator.option import Option
from configurator.option_group import OptionGroup
from configurator.validators import PathTarget, pathValidator


class SystemOption(OptionGroup):
    CONFIG_FILEPATH = Option(
        "config_filepath",
        str,
        validator=pathValidator(target=PathTarget.FILE),
    )
    ENV_FILEPATH = Option(
        "env_filepath",
        str,
        validator=pathValidator(target=PathTarget.FILE),
        required=False,
    )
    OPTION_GRAPHS_DIRPATH = Option(
        "graphs_dirpath",
        str,
        validator=pathValidator(),
        required=False,
    )
