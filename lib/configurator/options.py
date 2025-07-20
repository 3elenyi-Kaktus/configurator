from dataclasses import dataclass
from enum import Enum
from datetime import datetime as dt
from pathlib import Path
from typing import Callable, Any, Type


# base class for any custom options
class IOptionName(str, Enum):
    pass


@dataclass
class Option:
    name: IOptionName
    config_inner_type: Type[Any]
    validator: Callable[[Any], Any] = lambda x: x
    value: Any = None

    def __json__(self):
        value = self.value
        if isinstance(value, Path):
            value = str(value)
        elif isinstance(value, dt):
            value = str(value)
        return {"name": self.name.name, "value": value}
