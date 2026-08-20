from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
import logging
import sys
from typing import Any


log: logging.Logger = logging.getLogger(__name__)


class NotSet:
    pass


NOTSET = NotSet()


@dataclass
class Configurable:
    inner_config_type: type[Any]
    validator: Callable[[Any], Any] = lambda x: x
    default: Any = NOTSET


def internalField(field: str) -> str:
    return "_" + field


def processClass(cls: type) -> type:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)-5s:    %(message)s",
        stream=sys.stderr,
    )
    log.info(f"Apply 'configurable' decorator to {cls}")
    log.info(f"Annotations: {cls.__annotations__}")
    log.info(f"Dict: {cls.__dict__}")
    configurable_fields: list[tuple[str, type]] = []
    for name, type_ in cls.__annotations__.items():
        if isinstance(getattr(cls, name, None), Configurable):
            configurable_fields.append((name, type_))
    for name, type_ in configurable_fields:
        configurable_field: Configurable = getattr(cls, name)
        default: Any = configurable_field.default
        if default is not NOTSET and not isinstance(default, type_ | None):
            raise RuntimeError(
                f"{cls}: Configurable field '{name}' was provided with invalid default value: {default} of type: {type(default)} (expected: {type_})"
            )

        setattr(cls, internalField(name), default)

        def getAttr(field_name: str, self: object) -> Any:
            log.debug(f"Get attr '{field_name}' from {self.__class__}")
            return getattr(self, internalField(field_name))

        # annotated fields are considered to be immutable, no guarantees are given for resetting them in runtime
        # todo: this is a very shaky solution, these objects can't be created directly for now
        #   a better way is to add a validator for types which are already correct (or something else)
        #   for example, if class A: a: int = Configurable(int) is created, it's ambiguous if it's created from runtime or from configurator
        def setAttr(
            field_name: str,
            field_type: type,
            default_value: Any,
            inner_type: type,
            validator: Callable[[Any], Any],
            self: object,
            value: Any,
        ) -> None:
            log.debug(f"Set attr '{field_name}' to: {value} in {self}")
            if value == type(self).__dict__[field_name]:
                log.info("Class is initialised, skip setting property to itself")
                return
            # if passed value is of proper type, which is different from requested inner one, then consider value to be already correct
            current_value = getattr(self, internalField(field_name))
            if (
                isinstance(value, field_type)
                and field_type != inner_type
                and current_value is not NOTSET
                and current_value != default_value
            ):
                setattr(self, internalField(field_name), value)
                return
            if not isinstance(value, inner_type):
                raise RuntimeError(
                    f"{cls}: Value: {value} of invalid type {type(value)} provided for field '{field_name}' (expected: {inner_type})"
                )
            try:
                setattr(self, internalField(field_name), validator(value))
            except RuntimeError as exc:
                raise RuntimeError(f"{cls}: Validation failed for field '{field_name}'") from exc

        name_property = property(
            partial(getAttr, name),
            partial(setAttr, name, type_, default, configurable_field.inner_config_type, configurable_field.validator),
        )
        setattr(cls, name, name_property)

    log.info("After mangling class")
    log.info(f"Annotations: {cls.__annotations__}")
    log.info(f"Dict: {cls.__dict__}")
    return cls


def configurable(cls: type | None = None) -> Callable[..., Any] | type:
    def wrap(cls: type) -> type:
        return processClass(cls)

    if cls is None:
        # Called via @configurable()
        return wrap
    # Called via @configurable
    return wrap(cls)
