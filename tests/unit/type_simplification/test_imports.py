"""Import accumulation and negative import assertions."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from kaktus.configurator.gen import Generator
from tests.unit.type_simplification import samples
from tests.unit.type_simplification.conftest import SAMPLES_MOD, imports_as_tuples, simplify


def test_complex_imports_accumulate_across_calls(generator: Generator) -> None:
    generator.imports.clear()
    assert generator.simplifyType(list[Path]) == "list[Path]"
    assert imports_as_tuples(generator.imports) == {("pathlib", "Path")}

    assert generator.simplifyType(Sequence[int]) == "Sequence[int]"
    assert imports_as_tuples(generator.imports) == {
        ("pathlib", "Path"),
        ("collections.abc", "Sequence"),
    }

    assert generator.simplifyType(Any) == "Any"
    assert imports_as_tuples(generator.imports) == {
        ("pathlib", "Path"),
        ("collections.abc", "Sequence"),
        ("typing", "Any"),
    }


def test_duplicate_imports_are_deduplicated(generator: Generator) -> None:
    generator.imports.clear()
    generator.simplifyType(Path)
    generator.simplifyType(list[Path])
    generator.simplifyType(dict[str, Path])
    generator.simplifyType(Path | None)
    assert imports_as_tuples(generator.imports) == {("pathlib", "Path")}


def test_nested_and_bare_user_types_share_same_import(generator: Generator) -> None:
    generator.imports.clear()
    assert generator.simplifyType(samples.Outer) == "Outer"
    assert generator.simplifyType(samples.Outer.Inner) == "Outer.Inner"
    assert generator.simplifyType(list[samples.Outer.Inner]) == "list[Outer.Inner]"
    assert imports_as_tuples(generator.imports) == {(SAMPLES_MOD, "Outer")}


def test_nested_class_does_not_import_inner_or_deep_names(generator: Generator) -> None:
    _, imports = simplify(generator, samples.Outer.Inner.Deep)
    assert imports == {(SAMPLES_MOD, "Outer")}
    assert (SAMPLES_MOD, "Inner") not in imports
    assert (SAMPLES_MOD, "Deep") not in imports
    assert not any(module.endswith(".Outer") for module, _name in imports)
    assert not any(module.endswith(".Inner") for module, _name in imports)


def test_nested_class_in_generic_does_not_import_qualname_fragments(generator: Generator) -> None:
    _, imports = simplify(generator, list[dict[str, samples.Outer.Inner.Deep | Path]])
    assert imports == {(SAMPLES_MOD, "Outer"), ("pathlib", "Path")}
    assert (SAMPLES_MOD, "Inner") not in imports
    assert (SAMPLES_MOD, "Deep") not in imports
    assert ("tests.unit.type_simplification.samples.Outer", "Inner") not in imports
    assert ("tests.unit.type_simplification.samples.Outer.Inner", "Deep") not in imports


def test_builtins_inside_generics_never_appear_in_imports(generator: Generator) -> None:
    cases: list[Any] = [
        list[int],
        dict[str, list[int | None]],
        tuple[str, bytes, object],
        list[dict[str, set[bool]]],
    ]
    for tp in cases:
        _, imports = simplify(generator, tp)
        assert not any(module == "builtins" for module, _name in imports)


def test_path_imported_from_pathlib_only(generator: Generator) -> None:
    from datetime import datetime

    _, imports = simplify(generator, list[Path | datetime])
    assert ("pathlib", "Path") in imports
    assert ("datetime", "datetime") in imports
    assert ("builtins", "Path") not in imports
    assert ("builtins", "datetime") not in imports
