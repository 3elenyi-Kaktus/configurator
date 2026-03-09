from copy import deepcopy
import logging
from typing import Optional

from configurator.option import Option


class OptionGroup:
    _prefix: Optional[str] = None
    _real: bool = True
    _prefix_path: list[str] = []
    _real_prefix_path: list[str] = []

    @classmethod
    def getOptions(cls) -> list[Option]:
        options: list[Option] = []
        for attr_name in dir(cls):
            value = getattr(cls, attr_name)
            if not isinstance(value, Option):
                continue
            options.append(value)
            logging.info(f"Attr: '{attr_name}'")
        logging.info(f"OptionGroup: Got options: {options}")
        return options

    def __init_subclass__(cls, **kwargs):
        logging.info(f"Mangling subclass of OptionGroup: '{cls.__name__}'")
        super().__init_subclass__()
        for attr_name in dir(cls):
            value = getattr(cls, attr_name)
            if not isinstance(value, Option):
                continue
            if attr_name in cls.__dict__:
                continue
            logging.info(f"Attr: '{attr_name}'")
            setattr(cls, attr_name, deepcopy(value))
        logging.info(f"Completed subclass mangling")


def _preprocessOptionGroup(cls: type[OptionGroup], parent: type[OptionGroup], prefix: str, real: bool):
    logging.info(f"Preprocessing option group: '{cls.__name__}'")
    if not issubclass(cls, OptionGroup):
        raise RuntimeError(f"'{cls.__name__}' is not a subclass of OptionGroup")
    logging.info(f"Attributes (in): {cls.__dict__}")

    logging.info(
        f"Adding prefix '{prefix}' to parent ('{parent.__name__}') paths as {'real' if real else 'virtual'} part"
    )
    cls._prefix = prefix
    cls._real = real

    current_prefix_path: list[str] = deepcopy(parent._prefix_path)
    current_real_prefix_path: list[str] = deepcopy(parent._real_prefix_path)
    logging.info(f"Parents path: {current_prefix_path} (real: {current_real_prefix_path})")
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
    logging.info(f"Attributes (out): {cls.__dict__}")
    return cls


def optionGroup(
    cls: Optional[type[OptionGroup]] = None,
    /,
    *,
    parent: type[OptionGroup] = OptionGroup,
    prefix: Optional[str] = None,
    real: bool = True,
):
    def wrapper(cls_):
        return _preprocessOptionGroup(cls_, parent, prefix, real)

    if cls is None:
        # Called with parentheses
        return wrapper

    # Called without parentheses
    return wrapper(cls)
