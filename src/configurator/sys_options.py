from typing import Optional

from configurator.option import Option
from configurator.option_group import OptionGroup
from configurator.validators import asOptionalPath, asPath, validatePath


class SystemOption(OptionGroup):
    CONFIG_FILEPATH = Option("config_filepath", str, validatePath)
    ENV_FILEPATH = Option("env_filepath", Optional[str], asOptionalPath, False)
    OPTION_GRAPHS_DIRPATH = Option("graphs_dirpath", str, asPath, False)
