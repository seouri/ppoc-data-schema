from __future__ import annotations

import ast
import inspect
from pathlib import Path

from synthetic.native.resources import project_observed_resources, validate_observed_resources

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "src" / "synthetic" / "native"
FORBIDDEN_IMPORT_ROOTS = {
    "synthetic.calibrate",
    "synthetic.calibration",
    "synthetic.calibration_input",
    "synthetic.heldout_validate",
    "synthetic.privacy_audit",
    "synthetic.generate",
    "synthetic.csv_package",
    "synthetic.export",
    "synthetic.exporters",
    "synthetic.manifest",
    "synthetic.schema_contract",
}
RESOURCE_IMPORT_ALLOWLIST = {
    "__future__",
    "math",
    "re",
    "collections.abc",
    "dataclasses",
    "enum",
    "numbers",
    "types",
    "typing",
    "synthetic.native.observations",
}
RESOURCE_FORBIDDEN_IMPORTS = FORBIDDEN_IMPORT_ROOTS | {"synthetic.randomness"}
FORBIDDEN_CALLS = {
    "open",
    "read_bytes",
    "read_csv",
    "read_text",
    "to_csv",
    "write_bytes",
    "write_text",
}


def _imports_and_calls(path: Path) -> tuple[set[str], set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    return imports, calls


def test_native_resource_contract_recursively_has_no_governed_or_file_boundaries() -> None:
    imports: set[str] = set()
    for path in NATIVE.rglob("*.py"):
        source_imports, _source_calls = _imports_and_calls(path)
        imports.update(source_imports)

    assert not imports & FORBIDDEN_IMPORT_ROOTS
    resource_imports, resource_calls = _imports_and_calls(NATIVE / "resources.py")
    assert resource_imports <= RESOURCE_IMPORT_ALLOWLIST
    assert not resource_imports & RESOURCE_FORBIDDEN_IMPORTS
    assert not resource_calls & FORBIDDEN_CALLS


def test_resource_projection_and_validation_have_no_governed_or_export_api_arguments() -> None:
    forbidden_arguments = {
        "data_root",
        "descriptor_path",
        "calibration_artifact",
        "heldout_report",
        "privacy_report",
        "output_path",
    }

    for function in (validate_observed_resources, project_observed_resources):
        assert not forbidden_arguments & set(inspect.signature(function).parameters)


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
