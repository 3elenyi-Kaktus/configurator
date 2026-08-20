from __future__ import annotations

from collections.abc import Callable
import inspect
from inspect import Parameter, Signature, signature
import logging
from types import GenericAlias, UnionType
from typing import Any, TypeAlias

from kaktus.configurator.commons import OptionName
from kaktus.configurator.rules import Depends


log: logging.Logger = logging.getLogger(__name__)


class _NotSet:
    def __json__(self) -> str:
        return "_NOTSET"


_NOTSET: _NotSet = _NotSet()


class _Missing:
    def __json__(self) -> str:
        return "_MISSING"


_MISSING: _Missing = _Missing()

OptionType: TypeAlias = type | UnionType | GenericAlias
Validator: TypeAlias = Callable[[Any], Any]


class Option:
    def __init__(
        self,
        name: OptionName,
        *,
        in_type: OptionType | None = None,
        rtype: OptionType | None = None,
        validator: Validator | None = None,
        required: bool = True,
        dependencies: Depends | None = None,
        default: Any = _NOTSET,
    ):
        self.name: OptionName = name
        self.validator: Validator = (lambda x: x) if validator is None else validator
        self.required: bool = required
        self.dependencies: Depends | None = dependencies
        self.default: Any = default

        self.raw_value: Any = _MISSING
        self.value: Any = None

        if self.default is not _NOTSET:
            self.raw_value = self.default

        resolved_types: tuple[OptionType, OptionType] = self.__resolveOptionTypes(in_type, rtype, validator)
        self.in_type: OptionType = resolved_types[0]
        self.rtype: OptionType = resolved_types[1]

    def __resolveOptionTypes(
        self, in_type: OptionType | None, rtype: OptionType | None, validator: Validator | None
    ) -> tuple[OptionType, OptionType]:
        # We need to infer option input/option types for later typechecking.
        # If option has no custom validator (a default pass-through one), we can infer types only from the ones provided by user.
        if validator is None:
            if rtype is None:
                raise RuntimeError("Option 'rtype' parameter is unset (set it or provide a typed validator)")
            if in_type is not None and in_type != rtype:
                raise RuntimeError(
                    f"Input and option types in option {self.name} mismatch (input -> '{in_type}' != '{rtype}' <- option) (change input/option types or provide a custom validator)"
                )
            return rtype, rtype

        sign: Signature = signature(self.validator)
        input_parameters: list[Parameter] = list(sign.parameters.values())
        if len(input_parameters) == 0:
            raise RuntimeError(f"Validator callable must have at least one parameter in option '{self.name}'")
        input_annotation: Any = input_parameters[0].annotation
        log.info(f"Option: Retrieved validator callable input argument type: {input_annotation}")

        return_annotation: Any
        if inspect.isclass(self.validator):
            return_annotation = self.validator
        else:
            return_annotation = sign.return_annotation
        log.info(f"Option: Retrieved validator callable return type: {sign.return_annotation}")

        # Check if it's needed to infer types from existing option validator.
        if in_type is not None and rtype is not None:
            # We don't check if the input/option types are not subtypes of the validator in/out types.
            # We guarantee only that the argument of an asked type will be provided into user's validator function.
            # Make a simple equality check and warn user (even though it's not our problem).
            if in_type != input_annotation:
                log.warning(
                    f"Input type of option '{self.name}' is mismatched with the validator: {in_type} != {input_annotation}"
                )
            if rtype != return_annotation:
                log.warning(
                    f"Option type of option '{self.name}' is mismatched with the validator: {rtype} != {return_annotation}"
                )
            return in_type, rtype

        if in_type is None:
            if input_annotation is Parameter.empty:
                raise RuntimeError(
                    f"Can't infer type for option '{self.name}' input value, 'validator' callable input argument isn't typed"
                )
            in_type = input_annotation
        if rtype is None:
            if return_annotation is Signature.empty:
                raise RuntimeError(
                    f"Can't infer type for option '{self.name}', validator callable return value isn't typed"
                )
            rtype = return_annotation
        return in_type, rtype

    def __json__(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "in_type": str(self.in_type),
            "type": str(self.rtype),
            "required": self.required,
            "default": str(self.default),
            "raw_value": self.raw_value,
            "value": self.value,
        }
