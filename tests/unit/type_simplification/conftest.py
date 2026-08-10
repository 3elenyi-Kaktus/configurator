"""Shared fixtures/helpers for Generator.simplifyType black-box tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from kaktus.configurator.gen import Generator, ImportData
from tests.unit.type_simplification import samples, stub_options


SAMPLES_MOD = samples.__name__
STUB_OPTIONS_MOD = stub_options.__name__
OPTIONS_OBJECT = "option_groups"


@pytest.fixture
def generator() -> Generator:
    """Generator against stub_options (loadable module with empty option_groups)."""
    return Generator(
        STUB_OPTIONS_MOD,
        OPTIONS_OBJECT,
        Path("out.py"),
        f"config-regen {STUB_OPTIONS_MOD}:{OPTIONS_OBJECT} out.py",
    )


def simplify(generator: Generator, tp: Any) -> tuple[str, set[tuple[str, str | None]]]:
    generator.imports.clear()
    rendered = generator.simplifyType(tp)
    return rendered, imports_as_tuples(generator.imports)


def imports_as_tuples(imports: set[ImportData]) -> set[tuple[str, str | None]]:
    return {(item.module_name, item.object_name) for item in imports}
