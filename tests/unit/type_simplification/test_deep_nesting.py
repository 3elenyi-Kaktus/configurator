"""Deeply nested type expressions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal, Optional, Union

import pytest

from kaktus.configurator.gen import Generator
from tests.unit.type_simplification import samples
from tests.unit.type_simplification.conftest import SAMPLES_MOD, simplify
from tests.unit.type_simplification.fixtures_types import MODULE as FIXTURES_MOD, UserId


@pytest.mark.parametrize(
    ("tp", "expected", "expected_imports"),
    [
        (list[list[int]], "list[list[int]]", set()),
        (list[dict[str, int]], "list[dict[str, int]]", set()),
        (dict[str, list[int]], "dict[str, list[int]]", set()),
        (dict[str, dict[str, int]], "dict[str, dict[str, int]]", set()),
        (list[tuple[int, str]], "list[tuple[int, str]]", set()),
        (tuple[list[int], dict[str, str]], "tuple[list[int], dict[str, str]]", set()),
        (set[frozenset[bytes]], "set[frozenset[bytes]]", set()),
        (list[list[Path]], "list[list[Path]]", {("pathlib", "Path")}),
        (dict[str, list[Path]], "dict[str, list[Path]]", {("pathlib", "Path")}),
        (
            list[dict[str, Path | None]],
            "list[dict[str, Path | None]]",
            {("pathlib", "Path")},
        ),
        (
            dict[str, list[datetime | None]],
            "dict[str, list[datetime | None]]",
            {("datetime", "datetime")},
        ),
        (
            Mapping[str, Sequence[Path]],
            "Mapping[str, Sequence[Path]]",
            {
                ("collections.abc", "Mapping"),
                ("collections.abc", "Sequence"),
                ("pathlib", "Path"),
            },
        ),
        (
            list[Path] | dict[str, list[Path]] | None,
            "list[Path] | dict[str, list[Path]] | None",
            {("pathlib", "Path")},
        ),
        (
            Optional[dict[str, list[Path]]],
            "dict[str, list[Path]] | None",
            {("pathlib", "Path")},
        ),
        (
            Union[list[dict[str, int]], tuple[Path, ...]],
            "list[dict[str, int]] | tuple[Path, ...]",
            {("pathlib", "Path")},
        ),
        (
            Annotated[list[dict[str, Path]], "json"],
            "Annotated[list[dict[str, Path]], 'json']",
            {("pathlib", "Path"), ("typing", "Annotated")},
        ),
        (
            Annotated[list[Path] | dict[str, Path] | None, "mixed"],
            "Annotated[list[Path] | dict[str, Path] | None, 'mixed']",
            {("pathlib", "Path"), ("typing", "Annotated")},
        ),
        (
            dict[str, list[Literal["a", "b"]]],
            "dict[str, list[Literal['a', 'b']]]",
            {("typing", "Literal")},
        ),
        (
            Mapping[str, list[Any]],
            "Mapping[str, list[Any]]",
            {("collections.abc", "Mapping"), ("typing", "Any")},
        ),
        (
            list[samples.Outer.Inner.Deep],
            "list[Outer.Inner.Deep]",
            {(SAMPLES_MOD, "Outer")},
        ),
        (
            dict[str, list[samples.Outer.Inner | None]],
            "dict[str, list[Outer.Inner | None]]",
            {(SAMPLES_MOD, "Outer")},
        ),
        (
            list[dict[str, samples.Outer.Inner.Deep | Path]],
            "list[dict[str, Outer.Inner.Deep | Path]]",
            {(SAMPLES_MOD, "Outer"), ("pathlib", "Path")},
        ),
        (
            list[UserId],
            "list[UserId]",
            {(FIXTURES_MOD, "UserId")},
        ),
        (
            dict[str, list[UserId | None]],
            "dict[str, list[UserId | None]]",
            {(FIXTURES_MOD, "UserId")},
        ),
        (
            list[dict[str, list[tuple[Path, int]]]],
            "list[dict[str, list[tuple[Path, int]]]]",
            {("pathlib", "Path")},
        ),
        (
            dict[str, Mapping[str, Sequence[list[Path | None]]]],
            "dict[str, Mapping[str, Sequence[list[Path | None]]]]",
            {
                ("collections.abc", "Mapping"),
                ("collections.abc", "Sequence"),
                ("pathlib", "Path"),
            },
        ),
    ],
)
def test_deeply_nested_types(
    generator: Generator,
    tp: Any,
    expected: str,
    expected_imports: set[tuple[str, str]],
) -> None:
    rendered, imports = simplify(generator, tp)
    assert rendered == expected
    assert imports == expected_imports
