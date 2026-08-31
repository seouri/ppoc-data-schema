from __future__ import annotations

import ast
import inspect
from pathlib import Path

from synthetic.native import ancillary


def test_ancillary_module_has_only_native_safe_imports_and_no_lifecycle_calls() -> None:
    tree = ast.parse(Path(ancillary.__file__).read_text(encoding="utf-8"))
    forbidden = {"pathlib", "csv", "os", "sys", "random", "duckdb", "synthea", "package", "export", "manifest", "calibration", "privacy", "heldout"}
    imported = set()
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0].lower() for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0].lower())
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            calls.add(node.func.id.lower())
    assert not imported.intersection(forbidden)
    assert not calls.intersection({"open", "print", "exit", "quit", "seed", "randint", "write"})


def test_public_ancillary_interfaces_do_not_accept_paths_rows_or_outputs() -> None:
    for function, expected in (
        (ancillary.project_ghd_ancillary_resources, ("member", "shape", "policy")),
        (ancillary.validate_ghd_ancillary_resources, ("member", "projection", "policy")),
    ):
        names = tuple(inspect.signature(function).parameters)
        assert names == expected
        assert not set(names).intersection({"path", "descriptor_path", "rows", "row", "output", "destination", "report", "key"})
