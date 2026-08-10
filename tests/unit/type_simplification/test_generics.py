"""Builtin generics and shallow nesting."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from kaktus.configurator.gen import Generator
from tests.unit.type_simplification import samples
from tests.unit.type_simplification.conftest import SAMPLES_MOD, simplify


@pytest.mark.parametrize(
    ("tp", "expected", "expected_imports"),
    [
        (list[int], "list[int]", set()),
        (list[str], "list[str]", set()),
        (dict[str, int], "dict[str, int]", set()),
        (tuple[int, str], "tuple[int, str]", set()),
        (tuple[int, ...], "tuple[int, ...]", set()),
        (set[bytes], "set[bytes]", set()),
        (frozenset[str], "frozenset[str]", set()),
        (type[int], "type[int]", set()),
        (list[Path], "list[Path]", {("pathlib", "Path")}),
        (dict[str, Path], "dict[str, Path]", {("pathlib", "Path")}),
        (list[datetime], "list[datetime]", {("datetime", "datetime")}),
        (list[Any], "list[Any]", {("typing", "Any")}),
        (list[samples.Outer.Inner], "list[Outer.Inner]", {(SAMPLES_MOD, "Outer")}),
        (dict[str, samples.Outer.Inner], "dict[str, Outer.Inner]", {(SAMPLES_MOD, "Outer")}),
    ],
)
def test_generics_render_and_collect_nested_imports(
    generator: Generator,
    tp: Any,
    expected: str,
    expected_imports: set[tuple[str, str]],
) -> None:
    rendered, imports = simplify(generator, tp)
    assert rendered == expected
    assert imports == expected_imports
