from __future__ import annotations

from enum import IntEnum
from types import UnionType
from typing import Annotated, Any, TypeAlias, Union, get_args, get_origin

from typing_extensions import TypeAliasType


OptionName: TypeAlias = str


class AccessZone(IntEnum):
    NOTSET = -1
    ADMIN = 0
    DEV = 1


def toNonGenericType(tp: Any) -> Any:
    if tp is Any:
        return object

    if isinstance(tp, TypeAliasType):
        return toNonGenericType(tp.__value__)

    origin = get_origin(tp)

    if origin is Annotated:
        return toNonGenericType(get_args(tp)[0])

    if origin is Union or origin is UnionType or isinstance(tp, UnionType):
        args = get_args(tp)
        if not args:
            return object
        erased = toNonGenericType(args[0])
        for arg in args[1:]:
            erased |= toNonGenericType(arg)
        return erased

    if origin is not None:
        return origin

    return tp
