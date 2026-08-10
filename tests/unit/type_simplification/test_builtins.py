"""Builtin / None-like types: short names, no imports."""

from __future__ import annotations

from typing import Any

import pytest

from kaktus.configurator.gen import Generator
from tests.unit.type_simplification.conftest import simplify


@pytest.mark.parametrize(
    ("tp", "expected"),
    [
        (None, "None"),
        (type(None), "None"),
        (int, "int"),
        (str, "str"),
        (bool, "bool"),
        (float, "float"),
        (bytes, "bytes"),
        (list, "list"),
        (dict, "dict"),
        (tuple, "tuple"),
        (set, "set"),
        (type, "type"),
        (object, "object"),
    ],
)
def test_builtins_need_no_imports(generator: Generator, tp: Any, expected: str) -> None:
    rendered, imports = simplify(generator, tp)
    assert rendered == expected
    assert imports == set()
