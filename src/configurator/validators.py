from datetime import datetime as dt
from enum import IntEnum
from pathlib import Path
from typing import Callable, Optional


class PathTarget(IntEnum):
    FILE = 0
    DIRECTORY = 1


def pathValidator(
    *, optional: bool = False, missing_ok: bool = False, target: Optional[PathTarget] = None
) -> Callable[[Optional[str]], Optional[Path]]:
    def validate(in_path: Optional[str]) -> Optional[Path]:
        # If path target is not None, then existence check is implied in the pathlib methods.
        # This might conflict with intentional existence check skip.
        if missing_ok and target is not None:
            raise RuntimeError(f"Using path target and skipping existence check are mutually exclusive options")
        if in_path is None:
            if optional:
                return None
            raise TypeError(f"Expected a path string, got {in_path}")
        path: Path = Path(in_path)
        if target is not None:
            match target:
                case PathTarget.FILE:
                    if not path.is_file():
                        raise ValueError(f"Path '{path}' is not a file")
                    return path
                case PathTarget.DIRECTORY:
                    if not path.is_dir():
                        raise ValueError(f"Path '{path}' is not a directory")
                    return path
                case _:
                    raise RuntimeError(f"Unexpected path type '{target}'")
        if not missing_ok and not path.exists():
            raise RuntimeError(f"Path '{path}' does not exist")
        return path

    return validate


def datetimeValidator(dt_format: str, *, optional: bool = False) -> Callable[[Optional[str]], Optional[dt]]:
    def validate(ts: Optional[str]) -> Optional[dt]:
        if ts is None:
            if optional:
                return None
            raise TypeError(f"Expected a datetime string, got {ts}")
        parsed_ts: dt = dt.strptime(ts, dt_format)
        return parsed_ts

    return validate
