from pathlib import Path
from typing import Optional

from lib.configurator.options import IOptionName, Option


class SysOptionName(IOptionName):
    CONFIG_FILEPATH = "config_filepath"
    ENV_FILEPATH = "env_filepath"


def validatePath(path: str) -> Path:
    if not Path(path).exists():
        raise RuntimeError(f"Path {path} does not exist!")
    return Path(path)


def asOptionalPath(path: Optional[str]) -> Optional[Path]:
    if path is None:
        return None
    return Path(path)


sys_options: list[Option] = [
    Option(SysOptionName.CONFIG_FILEPATH, str, validatePath),
    Option(SysOptionName.ENV_FILEPATH, Optional[str], asOptionalPath),
]
