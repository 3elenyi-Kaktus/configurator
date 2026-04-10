from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from configurator.commons import OptionName
from configurator.rules import Depends


class Missing:
    def __json__(self) -> str:
        return "_MISSING"


MISSING = Missing()


@dataclass
class Option:
    name: OptionName
    config_inner_type: type[Any]
    validator: Callable[[Any], Any] = field(default=lambda x: x, kw_only=True)
    required: bool = field(default=True, kw_only=True)
    dependencies: Optional[Depends] = field(default=None, kw_only=True)

    # TODO: Maybe provide a default value interface for options
    #       For now, set them as special value MISSING
    raw_value: Any = field(default=MISSING, init=False)
    value: Any = field(default=None, init=False)

    def __json__(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "config_inner_type": str(self.config_inner_type),
            "required": self.required,
            "raw_value": self.raw_value,
            "value": self.value,
        }
