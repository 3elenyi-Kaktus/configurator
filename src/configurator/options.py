from dataclasses import dataclass
from datetime import datetime as dt
from pathlib import Path
from typing import Any, Callable, Optional, Type

from configurator.option_name import IOptionName
from configurator.rules import Depends


class Missing:
    pass


MISSING = Missing()


@dataclass
class Option:
    name: IOptionName
    config_inner_type: Type[Any]
    validator: Callable[[Any], Any] = lambda x: x
    required: bool = True
    dependencies: Depends = None

    # TODO: Maybe provide a default value interface for options
    #       For now, set them as special value MISSING
    raw_value: Any = MISSING
    value: Any = None

    def __post_init__(self):
        if not self.required:
            self.config_inner_type = Optional[self.config_inner_type]

    def __json__(self):
        value = self.value
        if isinstance(value, Path):
            value = str(value)
        elif isinstance(value, dt):
            value = str(value)
        return {
            "name": self.name.name,
            "config_inner_type": str(self.config_inner_type),
            "required": self.required,
            "value": value,
        }
