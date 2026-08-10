"""User-defined typing constructs used by simplifyType tests."""

from __future__ import annotations

from typing import NamedTuple, NewType, Protocol, TypedDict, TypeVar


UserId = NewType("UserId", int)
T = TypeVar("T")

MODULE = __name__


class Point(NamedTuple):
    x: int
    y: int


class Movie(TypedDict):
    title: str


class Closable(Protocol):
    def close(self) -> None: ...
