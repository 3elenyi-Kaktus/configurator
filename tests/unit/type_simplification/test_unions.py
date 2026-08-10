"""Unions, Optional, and Union aliases."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

import pytest

from kaktus.configurator.gen import Generator
from tests.unit.type_simplification import samples
from tests.unit.type_simplification.conftest import SAMPLES_MOD, simplify


@pytest.mark.parametrize(
    ("tp", "expected", "expected_imports"),
    [
        (int | str, "int | str", set()),
        (int | None, "int | None", set()),
        (list[str] | dict[str, int], "list[str] | dict[str, int]", set()),
        (Path | None, "Path | None", {("pathlib", "Path")}),
        (list[Path] | dict[str, Path], "list[Path] | dict[str, Path]", {("pathlib", "Path")}),
        (samples.Outer.Inner | None, "Outer.Inner | None", {(SAMPLES_MOD, "Outer")}),
        (Optional[int], "int | None", set()),
        (Union[int, str], "int | str", set()),
        (Optional[Path], "Path | None", {("pathlib", "Path")}),
    ],
)
def test_unions_and_optionals(
    generator: Generator,
    tp: Any,
    expected: str,
    expected_imports: set[tuple[str, str]],
) -> None:
    rendered, imports = simplify(generator, tp)
    assert rendered == expected
    assert imports == expected_imports
