from __future__ import annotations

import ast
import inspect
from pathlib import Path

from synthetic.native import ancillary


def _dotted_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None


def _unsafe_dependency_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.lower() for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = (node.module or "").lower()
            names.add(module)
            names.update(f"{module}.{alias.name}".strip(".") for alias in node.names)
        elif isinstance(node, ast.Call):
            name = _dotted_name(node.func)
            if name:
                names.add(name.lower())
    forbidden = {
        "calibration", "csv", "duckdb", "export", "filesystem", "heldout", "manifest",
        "os", "package", "pathlib", "privacy", "random", "synthea", "sys",
    }
    return {
        name for name in names
        if forbidden.intersection(name.replace("_", ".").split("."))
    }


def test_ancillary_module_has_only_native_safe_imports_and_no_lifecycle_calls() -> None:
    source = Path(ancillary.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            calls.add(node.func.id.lower())
    assert not _unsafe_dependency_names(source)
    assert not calls.intersection({"open", "print", "exit", "quit", "seed", "randint", "write"})


def test_dependency_scanner_rejects_qualified_and_imported_forbidden_dependencies() -> None:
    for source in (
        "import synthetic.package_export",
        "from synthetic import calibration",
        "from synthetic.heldout import compare",
        "import synthetic.privacy",
        "from duckdb import connect",
        "from pathlib import Path",
        "import os",
        "import csv",
        "import random",
        "import synthea",
        "synthetic.package_export.write()",
    ):
        assert _unsafe_dependency_names(source)


def test_public_ancillary_interfaces_do_not_accept_paths_rows_or_outputs() -> None:
    for function, expected in (
        (ancillary.project_ghd_ancillary_resources, ("member", "shape", "policy")),
        (ancillary.validate_ghd_ancillary_resources, ("member", "projection", "policy")),
    ):
        names = tuple(inspect.signature(function).parameters)
        assert names == expected
        assert not set(names).intersection({"path", "descriptor_path", "rows", "row", "output", "destination", "report", "key"})
