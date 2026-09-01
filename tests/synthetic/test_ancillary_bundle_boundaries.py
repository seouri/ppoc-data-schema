from __future__ import annotations

import ast
import inspect
from pathlib import Path

from synthetic.native import ancillary_bundle


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.lower() for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add((node.module or "").lower())
    return modules


def test_bundle_module_is_in_memory_only_and_has_no_forbidden_dependencies() -> None:
    source = Path(ancillary_bundle.__file__).read_text(encoding="utf-8")
    imported = _imported_modules(source)
    forbidden = {
        "calibration",
        "csv",
        "duckdb",
        "heldout",
        "manifest",
        "os",
        "package_export",
        "pathlib",
        "privacy",
        "random",
        "synthea",
    }

    assert not {
        module
        for module in imported
        if forbidden.intersection(module.replace("_", ".").split("."))
    }
    assert "synthetic.cohort" in imported
    assert "synthetic.native.ancillary" in imported
    assert "synthetic.native.resources" in imported


def test_bundle_public_functions_accept_only_typed_in_memory_contracts() -> None:
    assert tuple(inspect.signature(ancillary_bundle.merge_ghd_ancillary_resources).parameters) == (
        "bundle",
        "member",
        "projection",
        "policy",
    )
    assert tuple(inspect.signature(ancillary_bundle.validate_ghd_ancillary_bundle).parameters) == (
        "bundle",
        "member",
        "policy",
    )
    forbidden_names = {
        "path",
        "descriptor",
        "rows",
        "row",
        "output",
        "destination",
        "report",
        "key",
        "model",
        "callable",
    }
    for function in (
        ancillary_bundle.merge_ghd_ancillary_resources,
        ancillary_bundle.validate_ghd_ancillary_bundle,
    ):
        assert not forbidden_names.intersection(inspect.signature(function).parameters)
