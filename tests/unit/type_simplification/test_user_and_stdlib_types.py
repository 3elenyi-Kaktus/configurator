"""Stdlib and user-defined concrete types."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from kaktus.configurator.gen import Generator
from tests.unit.type_simplification import samples
from tests.unit.type_simplification.conftest import SAMPLES_MOD, simplify
from tests.unit.type_simplification.fixtures_types import (
    MODULE as FIXTURES_MOD,
    Closable,
    Movie,
    Point,
    UserId,
)


@pytest.mark.parametrize(
    ("tp", "expected", "expected_imports"),
    [
        (Path, "Path", {("pathlib", "Path")}),
        (datetime, "datetime", {("datetime", "datetime")}),
        (samples.Standalone, "Standalone", {(SAMPLES_MOD, "Standalone")}),
        (samples.Outer, "Outer", {(SAMPLES_MOD, "Outer")}),
        (samples.Outer.Inner, "Outer.Inner", {(SAMPLES_MOD, "Outer")}),
        (samples.Outer.Inner.Deep, "Outer.Inner.Deep", {(SAMPLES_MOD, "Outer")}),
        (Point, "Point", {(FIXTURES_MOD, "Point")}),
        (Movie, "Movie", {(FIXTURES_MOD, "Movie")}),
        (Closable, "Closable", {(FIXTURES_MOD, "Closable")}),
        (Any, "Any", {("typing", "Any")}),
        (UserId, "UserId", {(FIXTURES_MOD, "UserId")}),
    ],
)
def test_stdlib_and_user_types_emit_correct_imports(
    generator: Generator,
    tp: Any,
    expected: str,
    expected_imports: set[tuple[str, str]],
) -> None:
    rendered, imports = simplify(generator, tp)
    assert rendered == expected
    assert imports == expected_imports
