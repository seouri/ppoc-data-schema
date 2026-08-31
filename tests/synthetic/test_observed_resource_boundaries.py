from __future__ import annotations

import ast
import inspect
from pathlib import Path

from synthetic.native.resources import validate_observed_resources

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "src" / "synthetic" / "native"
FORBIDDEN_IMPORT_ROOTS = {
    "synthetic.calibrate",
    "synthetic.calibration",
    "synthetic.calibration_input",
    "synthetic.heldout_validate",
    "synthetic.privacy_audit",
    "synthetic.generate",
}
FORBIDDEN_CALLS = {"open", "Path", "read_csv"}


def _imports_and_calls(path: Path) -> tuple[set[str], set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            calls.add(node.func.id)
    return imports, calls


def test_native_resource_contract_recursively_has_no_governed_or_file_boundaries() -> None:
    imports: set[str] = set()
    for path in NATIVE.rglob("*.py"):
        source_imports, _source_calls = _imports_and_calls(path)
        imports.update(source_imports)

    assert not imports & FORBIDDEN_IMPORT_ROOTS
    _, resource_calls = _imports_and_calls(NATIVE / "resources.py")
    assert not resource_calls & FORBIDDEN_CALLS


def test_resource_validation_has_no_governed_or_export_api_arguments() -> None:
    forbidden_arguments = {
        "data_root",
        "descriptor_path",
        "calibration_artifact",
        "heldout_report",
        "privacy_report",
        "output_path",
    }

    assert not forbidden_arguments & set(inspect.signature(validate_observed_resources).parameters)


def test_documentation_defers_augmented_package_export_prevalence_privacy_and_synthea_gates() -> None:
    documentation = "\n".join(
        (
            (ROOT / "docs" / "synthetic-generator.md").read_text(encoding="utf-8"),
            (ROOT / "README.md").read_text(encoding="utf-8"),
        )
    ).lower()

    for deferred in (
        "augmented",
        "package",
        "export",
        "prevalence",
        "privacy",
        "synthea",
        "deferred",
    ):
        assert deferred in documentation
