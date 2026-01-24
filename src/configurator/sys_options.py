from typing import Optional

from configurator.option import Option
from configurator.option_group import OptionGroup
from configurator.validators import asOptionalPath, validatePath


class SystemOption(OptionGroup):
    CONFIG_FILEPATH = Option("config_filepath", str, validatePath)
    ENV_FILEPATH = Option("env_filepath", Optional[str], asOptionalPath, False)
