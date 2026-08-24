from collections.abc import Callable
from copy import deepcopy
import hashlib
from inspect import signature
import logging
from typing import Any

from kaktus.configurator.commons import AccessZone
from kaktus.configurator.option import Option


log: logging.Logger = logging.getLogger(__name__)


class OptionGroup:
    _prefix: str | None = None
    _real: bool = True
    _prefix_path: list[str] = []
    _real_prefix_path: list[str] = []

    @classmethod
    def hash(cls) -> str:
        options: list[Option] = cls.getOptions()
        qualifiers: str = ""
        for option in options:
            qualifiers += option.name + str(option.in_type) + str(option.rtype) + str(signature(option.validator))
        return hashlib.md5(qualifiers.encode()).hexdigest()

    @classmethod
    def getOptionAttrs(cls) -> list[str]:
        attrs: list[str] = []
        for attr_name in dir(cls):
            value = getattr(cls, attr_name)
            if not isinstance(value, Option):
                continue
            attrs.append(attr_name)
            log.info(f"Attr: '{attr_name}'")
        log.info(f"OptionGroup: Got attrs: {attrs}")
        return attrs

    @classmethod
    def getOptions(cls) -> list[Option]:
        options: list[Option] = []
        for attr_name in dir(cls):
            value = getattr(cls, attr_name)
            if not isinstance(value, Option):
                continue
            options.append(value)
            log.info(f"Attr: '{attr_name}'")
        log.info(f"OptionGroup: Got options: {options}")
        return options

    def __init_subclass__(cls, **kwargs: Any) -> None:
        log.info(f"Mangling subclass of OptionGroup: '{cls.__name__}'")
        super().__init_subclass__()
        for attr_name in dir(cls):
            value = getattr(cls, attr_name)
            # We want to only copy options which are inherited from the parent class
            if not isinstance(value, Option) or attr_name in cls.__dict__:
                continue
            log.info(f"Attr: '{attr_name}'")
            setattr(cls, attr_name, deepcopy(value))
        log.info("Completed subclass mangling")


def _addPrefix(cls: type[OptionGroup], parent: type[OptionGroup], prefix: str, real: bool) -> type[OptionGroup]:
    log.info(f"Adding prefix '{prefix}' to parent ('{parent.__name__}') paths as {'real' if real else 'virtual'} part")
    cls._prefix = prefix
    cls._real = real

    current_prefix_path: list[str] = deepcopy(parent._prefix_path)
    current_real_prefix_path: list[str] = deepcopy(parent._real_prefix_path)
    log.info(f"Parents path: {current_prefix_path} (real: {current_real_prefix_path})")
    if current_prefix_path is None or current_real_prefix_path is None:
        raise RuntimeError(f"'{cls.__name__}' seems to be misconfigured (did you mess with inheritance?)")

    if prefix is not None:
        current_prefix_path.append(prefix)
        if real:
            current_real_prefix_path.append(prefix)

    if current_real_prefix_path is not None:
        for option in cls.getOptions():
            option.name = "_".join([*current_real_prefix_path, option.name])

    cls._prefix_path = current_prefix_path
    cls._real_prefix_path = current_real_prefix_path
    log.info(f"Attributes (out): {cls.__dict__}")
    return cls


def _preprocessOptionGroup(
    cls: type[OptionGroup], parent: type[OptionGroup], prefix: str | None, real: bool, zone: AccessZone
) -> type[OptionGroup]:
    log.info(f"Preprocessing option group: '{cls.__name__}'")
    if not issubclass(cls, OptionGroup):
        raise TypeError(f"'{cls.__name__}' is not a subclass of OptionGroup")
    log.info(f"Attributes (in): {cls.__dict__}")

    if prefix is not None:
        cls = _addPrefix(cls, parent, prefix, real)

    for option in cls.getOptions():
        option.zone = zone
        if option.accessible_from is AccessZone.NOTSET:
            option.accessible_from = zone
        elif option.zone < option.accessible_from:
            raise RuntimeError(
                f"Option '{option.name}' is misplaced: accessible to zone '{option.accessible_from.name}', but placed in group with access zone '{zone.name}'"
            )

    log.info(f"Attributes (out): {cls.__dict__}")
    return cls


# Inheriting OptionGroup (or its subclass) should be used only to get the same options
# inside new group without copy-pasting them across option groups. However, this leads
# to option name overlapping, which is prohibited. The optionGroup decorator prefixes
# the option names so that this collision is resolved. So by design calling the decorator
# without prefix is useless, therefore this form is not supported.


def optionGroup(
    _: None = None,
    /,
    *,
    parent: type[OptionGroup] = OptionGroup,
    prefix: str | None = None,
    real: bool = True,
    zone: AccessZone = AccessZone.DEV,
) -> Callable[[type[OptionGroup]], type[OptionGroup]]:
    def wrapper(cls: type[OptionGroup]) -> type[OptionGroup]:
        return _preprocessOptionGroup(cls, parent, prefix, real, zone)

    return wrapper
