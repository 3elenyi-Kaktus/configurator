"""Forward refs, ellipsis, and invalid inputs."""

from __future__ import annotations

import types
from typing import Any, ForwardRef, TypeVar

import pytest

from kaktus.configurator.gen import Generator
from tests.unit.type_simplification.conftest import simplify
from tests.unit.type_simplification.fixtures_types import T


@pytest.mark.parametrize(
    ("tp", "expected", "expected_imports"),
    [
        (ForwardRef("Missing"), "Missing", set()),
        ("MyClass", "MyClass", set()),
        (..., "...", set()),
    ],
)
def test_forward_refs_and_ellipsis_are_handled(
    generator: Generator,
    tp: Any,
    expected: str,
    expected_imports: set[tuple[str, str]],
) -> None:
    rendered, imports = simplify(generator, tp)
    assert rendered == expected
    assert imports == expected_imports


@pytest.mark.parametrize(
    "tp",
    [
        123,
        object(),
        types.UnionType,
        types.GenericAlias,
    ],
)
def test_nonsensical_values_raise_type_error(generator: Generator, tp: Any) -> None:
    generator.imports.clear()
    with pytest.raises(TypeError):
        generator.simplifyType(tp)
    assert generator.imports == set()


@pytest.mark.parametrize(
    "tp",
    [
        T,
        TypeVar("U", bound=int),
        TypeVar("V", int, str),
    ],
    ids=["shared_T", "bound_TypeVar", "constrained_TypeVar"],
)
def test_typevars_are_rejected(generator: Generator, tp: Any) -> None:
    generator.imports.clear()
    with pytest.raises(TypeError):
        generator.simplifyType(tp)
    assert generator.imports == set()
