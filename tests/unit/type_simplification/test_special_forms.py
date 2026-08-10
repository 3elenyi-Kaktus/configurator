"""Literal, Annotated, Sequence, Mapping, and similar forms."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Any, Literal

import pytest

from kaktus.configurator.gen import Generator
from tests.unit.type_simplification.conftest import simplify


@pytest.mark.parametrize(
    ("tp", "expected", "expected_imports"),
    [
        (Literal["a"], "Literal['a']", {("typing", "Literal")}),
        (Literal[True], "Literal[True]", {("typing", "Literal")}),
        (Literal[1, "x", True], "Literal[1, 'x', True]", {("typing", "Literal")}),
        (Annotated[int, "meta"], "Annotated[int, 'meta']", {("typing", "Annotated")}),
        (
            Annotated[Path, "meta"],
            "Annotated[Path, 'meta']",
            {("pathlib", "Path"), ("typing", "Annotated")},
        ),
        (
            Annotated[list[Path], "a", "b"],
            "Annotated[list[Path], 'a', 'b']",
            {("pathlib", "Path"), ("typing", "Annotated")},
        ),
        (Sequence[int], "Sequence[int]", {("collections.abc", "Sequence")}),
        (
            Mapping[str, Any],
            "Mapping[str, Any]",
            {("collections.abc", "Mapping"), ("typing", "Any")},
        ),
    ],
)
def test_special_typing_forms(
    generator: Generator,
    tp: Any,
    expected: str,
    expected_imports: set[tuple[str, str]],
) -> None:
    rendered, imports = simplify(generator, tp)
    assert rendered == expected
    assert imports == expected_imports
