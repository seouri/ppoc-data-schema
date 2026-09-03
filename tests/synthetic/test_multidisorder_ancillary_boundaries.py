from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

from synthetic.native import multidisorder_ancillary


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.lower() for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add((node.module or "").lower())
    return modules


def test_adapter_is_in_memory_only_and_has_no_forbidden_dependencies() -> None:
    source = Path(multidisorder_ancillary.__file__).read_text(encoding="utf-8")
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
    assert "synthetic.native.resources" in imported


def test_public_functions_accept_only_typed_in_memory_contracts() -> None:
    expected = {
        multidisorder_ancillary.project_multidisorder_ancillary_resources: (
            "member",
            "shape",
            "policy",
        ),
        multidisorder_ancillary.validate_multidisorder_ancillary_resources: (
            "member",
            "projection",
            "policy",
        ),
        multidisorder_ancillary.merge_multidisorder_ancillary_resources: (
            "bundle",
            "member",
            "projection",
            "policy",
        ),
        multidisorder_ancillary.validate_multidisorder_ancillary_bundle: (
            "bundle",
            "member",
            "policy",
        ),
    }
    for function, parameters in expected.items():
        assert tuple(inspect.signature(function).parameters) == parameters

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
        "terminology",
    }
    for function in expected:
        assert not forbidden_names.intersection(inspect.signature(function).parameters)


def test_projection_has_no_public_kind_or_latent_field() -> None:
    fields = tuple(
        field.name
        for field in dataclasses.fields(
            multidisorder_ancillary.MultidisorderAncillaryProjection
        )
    )

    assert fields == ("patient_id", "shape", "rows")
    assert "kind" not in inspect.signature(
        multidisorder_ancillary.MultidisorderAncillaryProjection
    ).parameters
