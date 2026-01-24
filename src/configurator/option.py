from dataclasses import dataclass, field
from datetime import datetime as dt
from pathlib import Path
from typing import Any, Callable, Optional

from configurator.commons import OptionName
from configurator.rules import Depends


class Missing:
    def __json__(self) -> str:
        return "_MISSING"

    pass


MISSING = Missing()


@dataclass
class Option:
    name: OptionName
    config_inner_type: type[Any]
    validator: Callable[[Any], Any] = lambda x: x
    required: bool = True
    dependencies: Depends = None

    # TODO: Maybe provide a default value interface for options
    #       For now, set them as special value MISSING
    groups: list[type] = field(default_factory=list)  # list[type[OptionGroup]]
    raw_value: Any = field(default=MISSING, init=False)
    value: Any = field(default=None, init=False)

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
            "name": self.name,
            "config_inner_type": str(self.config_inner_type),
            "required": self.required,
            "groups": self.groups,
            "raw_value": self.raw_value,
            "value": value,
        }
