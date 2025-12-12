from typing import Optional

from lib.configurator.options import IOptionName, Option
from lib.configurator.validators import asOptionalPath, validatePath


class SysOptionName(IOptionName):
    CONFIG_FILEPATH = "config_filepath"
    ENV_FILEPATH = "env_filepath"


sys_options: list[Option] = [
    Option(SysOptionName.CONFIG_FILEPATH, str, validatePath),
    Option(SysOptionName.ENV_FILEPATH, Optional[str], asOptionalPath, False),
]
