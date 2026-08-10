"""Callable forms — always import Callable from collections.abc."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Callable as TypingCallable

import pytest

from kaktus.configurator.gen import Generator
from tests.unit.type_simplification import samples
from tests.unit.type_simplification.conftest import SAMPLES_MOD, simplify


@pytest.mark.parametrize(
    ("tp", "expected", "expected_imports"),
    [
        (Callable[[], int], "Callable[[], int]", {("collections.abc", "Callable")}),
        (Callable[[int], str], "Callable[[int], str]", {("collections.abc", "Callable")}),
        (Callable[..., Path], "Callable[..., Path]", {("collections.abc", "Callable"), ("pathlib", "Path")}),
        (
            TypingCallable[[int], str],
            "Callable[[int], str]",
            {("collections.abc", "Callable")},
        ),
        (
            Callable[[list[Path], dict[str, int]], Path | None],
            "Callable[[list[Path], dict[str, int]], Path | None]",
            {("collections.abc", "Callable"), ("pathlib", "Path")},
        ),
        (
            Callable[[Mapping[str, Sequence[int]]], list[Path]],
            "Callable[[Mapping[str, Sequence[int]]], list[Path]]",
            {
                ("collections.abc", "Callable"),
                ("collections.abc", "Mapping"),
                ("collections.abc", "Sequence"),
                ("pathlib", "Path"),
            },
        ),
        (
            Callable[[Callable[[int], str]], bool],
            "Callable[[Callable[[int], str]], bool]",
            {("collections.abc", "Callable")},
        ),
        (
            Callable[[samples.Outer.Inner], samples.Outer.Inner.Deep | None],
            "Callable[[Outer.Inner], Outer.Inner.Deep | None]",
            {("collections.abc", "Callable"), (SAMPLES_MOD, "Outer")},
        ),
        (
            list[Callable[[Path], str]],
            "list[Callable[[Path], str]]",
            {("collections.abc", "Callable"), ("pathlib", "Path")},
        ),
        (
            dict[str, Callable[..., list[Path] | None]],
            "dict[str, Callable[..., list[Path] | None]]",
            {("collections.abc", "Callable"), ("pathlib", "Path")},
        ),
    ],
)
def test_callables(
    generator: Generator,
    tp: Any,
    expected: str,
    expected_imports: set[tuple[str, str]],
) -> None:
    rendered, imports = simplify(generator, tp)
    assert rendered == expected
    assert imports == expected_imports


def test_callable_never_imports_from_typing(generator: Generator) -> None:
    for tp in (
        Callable[[int], str],
        TypingCallable[[Path], Path | None],
        Callable[[Callable[[int], str]], bool],
    ):
        _, imports = simplify(generator, tp)
        assert ("typing", "Callable") not in imports
        assert ("collections.abc", "Callable") in imports
