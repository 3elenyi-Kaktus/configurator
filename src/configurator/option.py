from dataclasses import dataclass, field
import inspect
from inspect import Parameter, Signature, signature
import logging
from typing import Any, Callable, Optional

from configurator.commons import OptionName
from configurator.rules import Depends


class _NotSet:
    @staticmethod
    def __json__() -> str:
        return "_NOTSET"


_NOTSET: _NotSet = _NotSet()


class _Missing:
    @staticmethod
    def __json__() -> str:
        return "_MISSING"


_MISSING: _Missing = _Missing()


@dataclass
class Option:
    name: OptionName
    in_type: type = field(default=_NOTSET, kw_only=True)
    type: type = field(default=_NOTSET, kw_only=True)
    validator: Callable[[Any], Any] = field(default=lambda x: x, kw_only=True)
    required: bool = field(default=True, kw_only=True)
    dependencies: Optional[Depends] = field(default=None, kw_only=True)
    default: Any = field(default=_MISSING, kw_only=True)

    raw_value: Any = field(default=_MISSING, init=False)
    value: Any = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.default is not _MISSING:
            self.raw_value = self.default

        # If option is a simple one (pass-through without validator), copy the value type into the input type if needed.
        # Otherwise, check if it's needed to infer types from validator.
        if self.validator is Option.validator:
            if self.type is _NOTSET:
                raise RuntimeError(f"Option type parameter is not set (either set it, or provide a validator)")
            if self.in_type != self.type and self.in_type is not _NOTSET:
                raise RuntimeError(
                    f"Input and option types mismatch ({self.in_type} != {self.type}) (pass-through implementation can't have different types)"
                )
            self.in_type = self.type
        else:
            if self.in_type is not _NOTSET and self.type is not _NOTSET:
                return

            sign: Signature = signature(self.validator)
            logging.info(f"Option: Retrieved validator function return type: {sign.return_annotation}")
            if self.in_type is _NOTSET:
                parameters: list[Parameter] = list(sign.parameters.values())
                if len(parameters) == 0:
                    raise RuntimeError(f"Validator callable must have at least one parameter")
                parameter: Parameter = parameters[0]
                if parameter.annotation is Parameter.empty:
                    raise RuntimeError(f"Can't infer type for input value, validator callable parameter isn't typed")
                self.in_type = parameter.annotation
            if self.type is _NOTSET:
                if sign.return_annotation is not Signature.empty:
                    self.type = sign.return_annotation
                elif inspect.isclass(self.validator):
                    self.type = self.validator
                else:
                    raise RuntimeError(
                        f"Can't infer type for option value, validator callable return value isn't typed"
                    )

    def __json__(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "in_type": str(self.in_type),
            "required": self.required,
            "raw_value": self.raw_value,
            "value": self.value,
        }
