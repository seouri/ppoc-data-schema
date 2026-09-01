from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest

from synthetic import generate
from synthetic.generate import generate_smoke
from synthetic.package_export import (
    export_counterfactual_ehr_world_pair,
    export_exact_schema_package,
    export_observed_resource_package,
)

ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC = ROOT / "src" / "synthetic"
BOUND_SOURCES = (
    SYNTHETIC / "derivation_binding.py",
    SYNTHETIC / "generate.py",
    SYNTHETIC / "package_export.py",
)
FORBIDDEN_MODULE_PREFIXES = (
    "synthetic.calibration",
    "synthetic.heldout_validate",
    "synthetic.privacy_audit",
    "synthetic.native.trajectory",
    "synthetic.temporal_drift",
    "synthetic.prevalence_evidence",
    "synthea",
)
FORBIDDEN_CALLS = {
    "audit_privacy",
    "calibrate",
    "generate_native_cohort",
    "load_calibration_artifact",
    "load_heldout",
    "load_privacy_policy",
    "run",
    "validate_heldout",
    "validate_temporal_drift",
    "write_prevalence_evidence",
}


def _imports(tree: ast.AST) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
    return imports


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _call_suffixes(tree: ast.AST) -> set[str]:
    return {
        name.rsplit(".", maxsplit=1)[-1]
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        if (name := _call_name(node.func)) is not None
    }


def test_production_cli_remains_fail_closed_without_an_approved_oracle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Breaks if the production CLI gains an unreviewed route past oracle approval."""
    monkeypatch.setattr(sys, "argv", ["synthetic.generate", "--output", "fictional", "--patients", "1", "--seed", "1"])

    with pytest.raises(SystemExit) as error:
        generate.main()

    assert str(error.value) == (
        "No production growth reference or authoritative derivation oracle is configured"
    )


def test_public_export_and_generator_signatures_require_an_explicit_binding() -> None:
    """Breaks if a public export route can bypass a supplied derivation binding."""
    for callable_ in (
        generate_smoke,
        export_exact_schema_package,
        export_observed_resource_package,
        export_counterfactual_ehr_world_pair,
    ):
        assert "derivation_binding" in inspect.signature(callable_).parameters


def test_binding_handoff_sources_do_not_import_or_execute_governed_or_external_routes() -> None:
    """Breaks if automatic calibration, evaluator, Synthea, or harness execution is added."""
    for path in BOUND_SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = _imports(tree)
        calls = _call_suffixes(tree)
        assert not {
            imported
            for imported in imports
            if imported.startswith(FORBIDDEN_MODULE_PREFIXES)
        }, path
        assert not calls & FORBIDDEN_CALLS, path
