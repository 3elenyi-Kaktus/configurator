from copy import deepcopy
import logging

from configurator.option import Option


class OptionGroup:
    _prefix: str = None
    _real: bool = True
    _prefix_path: list[str] = []
    _real_prefix_path: list[str] = []

    @classmethod
    def getOptions(cls) -> list[Option]:
        options: list[Option] = []
        for key, value in cls.__dict__.items():
            if not isinstance(value, Option):
                continue
            options.append(value)
        return options


def _preprocessOptionGroup(cls: type[OptionGroup], prefix: str, real: bool):
    if not issubclass(cls, OptionGroup):
        raise RuntimeError(f"'{cls.__name__}' is not a subclass of OptionGroup")
    logging.info(f"Preprocessing option group: '{cls.__name__}'")
    logging.info(f"Attributes (in): {cls.__dict__}")

    cls._prefix = prefix
    cls._real = real
    current_prefix_path: list[str] = deepcopy(cls._prefix_path)
    current_real_prefix_path: list[str] = deepcopy(cls._real_prefix_path)
    if current_prefix_path is None or current_real_prefix_path is None:
        raise RuntimeError(f"'{cls.__name__}' seems to be misconfigured (did you mess with inheritance?)")

    logging.info(current_prefix_path)
    logging.info(current_real_prefix_path)

    if prefix is not None:
        current_prefix_path.append(prefix)
        if real:
            current_real_prefix_path.append(prefix)

    if current_real_prefix_path is not None:
        for option in cls.getOptions():
            option.name = "_".join([*current_real_prefix_path, option.name])

    cls._prefix_path = current_prefix_path
    cls._real_prefix_path = current_real_prefix_path
    logging.info("Attributes (out): ", cls.__dict__)
    return cls


def optionGroup(cls: type[OptionGroup] = None, /, *, prefix: str = None, real: bool = True):
    def wrapper(cls_):
        return _preprocessOptionGroup(cls_, prefix, real)

    if cls is None:
        # Called with parentheses
        return wrapper

    # Called without parentheses
    return wrapper(cls)
