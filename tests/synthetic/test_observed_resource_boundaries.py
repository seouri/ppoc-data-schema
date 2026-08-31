from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

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
    relative = path.relative_to(ROOT / "src").with_suffix("")
    module = ".".join(relative.parts)
    return _imports_and_calls_source(path.read_text(encoding="utf-8"), module)


def _imports_and_calls_source(
    source: str,
    module: str = "synthetic.native.resources",
) -> tuple[set[str], set[str]]:
    tree = ast.parse(source, filename=f"<{module}>")
    imports: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package = module.split(".")[:-1]
                package = package[: len(package) - node.level + 1]
                parts = (*package, *(node.module.split(".") if node.module else ()))
                imported_module = ".".join(parts)
            else:
                imported_module = node.module or ""
            if imported_module:
                imports.add(imported_module)
                imports.update(f"{imported_module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    return imports, calls


def _matches_forbidden(imports: set[str], roots: set[str]) -> set[str]:
    return {
        imported
        for imported in imports
        if any(imported == root or imported.startswith(f"{root}.") for root in roots)
    }


def _is_resource_allowlisted(imported: str) -> bool:
    return any(
        imported == allowed or imported.startswith(f"{allowed}.")
        for allowed in RESOURCE_IMPORT_ALLOWLIST
    )


def test_native_resource_contract_recursively_has_no_governed_or_file_boundaries() -> None:
    imports: set[str] = set()
    for path in NATIVE.rglob("*.py"):
        source_imports, _source_calls = _imports_and_calls(path)
        imports.update(source_imports)

    assert not _matches_forbidden(imports, FORBIDDEN_IMPORT_ROOTS)
    resource_imports, resource_calls = _imports_and_calls(NATIVE / "resources.py")
    assert all(_is_resource_allowlisted(imported) for imported in resource_imports)
    assert not _matches_forbidden(resource_imports, RESOURCE_FORBIDDEN_IMPORTS)
    assert not resource_calls & FORBIDDEN_CALLS


def test_resource_projection_and_validation_have_exact_public_signatures() -> None:
    assert tuple(inspect.signature(validate_observed_resources).parameters) == ("bundle",)
    assert tuple(inspect.signature(project_observed_resources).parameters) == (
        "frame",
        "descriptor",
        "demographics",
    )


@pytest.mark.parametrize(
    ("source", "forbidden"),
    [
        (f"import {root}", root)
        for root in sorted(RESOURCE_FORBIDDEN_IMPORTS)
    ]
    + [
        (f"from synthetic import {root.rsplit('.', maxsplit=1)[1]}", root)
        for root in sorted(RESOURCE_FORBIDDEN_IMPORTS)
    ]
    + [
        (f"from {root} import boundary", root)
        for root in sorted(RESOURCE_FORBIDDEN_IMPORTS)
    ],
)
def test_import_scanner_qualifies_every_forbidden_import_form(source: str, forbidden: str) -> None:
    imports, _ = _imports_and_calls_source(source)

    assert forbidden in _matches_forbidden(imports, RESOURCE_FORBIDDEN_IMPORTS)


@pytest.mark.parametrize(
    ("source", "module", "forbidden"),
    [
        (f"from . import {root.rsplit('.', maxsplit=1)[1]}", "synthetic.boundary", root)
        for root in sorted(RESOURCE_FORBIDDEN_IMPORTS)
    ]
    + [
        (f"from .. import {root.rsplit('.', maxsplit=1)[1]}", "synthetic.native.resources", root)
        for root in sorted(RESOURCE_FORBIDDEN_IMPORTS)
    ]
    + [
        (f"from .{root.rsplit('.', maxsplit=1)[1]} import boundary", "synthetic.boundary", root)
        for root in sorted(RESOURCE_FORBIDDEN_IMPORTS)
    ],
)
def test_import_scanner_qualifies_relative_forbidden_import_forms(
    source: str,
    module: str,
    forbidden: str,
) -> None:
    imports, _ = _imports_and_calls_source(source, module)

    assert forbidden in _matches_forbidden(imports, RESOURCE_FORBIDDEN_IMPORTS)


@pytest.mark.parametrize("source", ("path.open()", "path.read_text()", "frame.write_text()"))
def test_call_scanner_detects_attribute_style_forbidden_io(source: str) -> None:
    _, calls = _imports_and_calls_source(source)

    assert calls & FORBIDDEN_CALLS


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
