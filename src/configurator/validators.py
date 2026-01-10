from pathlib import Path
from typing import Optional


def validatePath(path: str) -> Path:
    if not Path(path).exists():
        raise RuntimeError(f"Path {path} does not exist!")
    return Path(path)


def asPath(path: str) -> Path:
    return Path(path)


def asOptionalPath(path: Optional[str]) -> Optional[Path]:
    if path is None:
        return None
    return Path(path)
