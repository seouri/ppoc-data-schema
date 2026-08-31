from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from pathlib import Path

from synthetic.package_export import (
    export_exact_schema_package,
    export_observed_resource_package,
)

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "synthetic-generator.md"
README = ROOT / "README.md"
PACKAGE_EXPORT = ROOT / "src" / "synthetic" / "package_export.py"
FORBIDDEN_MODULES = {
    "synthetic.calibrate",
    "synthetic.calibration",
    "synthetic.calibration_input",
    "synthetic.heldout_validate",
    "synthetic.privacy_audit",
    "synthetic.synthea",
}
FORBIDDEN_ARGUMENTS = {
    "real_root",
    "data_root",
    "partition_key",
    "heldout_report",
    "privacy_policy",
}
PACKAGE_EXPORT_IMPORTS = {
    "__future__",
    "collections.abc",
    "dataclasses",
    "hashlib",
    "json",
    "math",
    "pathlib",
    "re",
    "shutil",
    "stat",
    "tempfile",
    "typing",
    "synthetic.base_resources",
    "synthetic.csv_package",
    "synthetic.derivation",
    "synthetic.manifest",
    "synthetic.native.resources",
    "synthetic.run_directory",
    "synthetic.schema_contract",
    "synthetic.validate",
}
PACKAGE_PATH_READERS = {
    "load_descriptor",
    "read_csv",
    "read_table",
    "read_parquet",
    "read_excel",
}
RANDOMNESS_IMPORTERS = {
    ROOT / "src" / "synthetic" / "generate.py",
    ROOT / "src" / "synthetic" / "manifest.py",
    ROOT / "src" / "synthetic" / "native" / "age_regime_disorder.py",
    ROOT / "src" / "synthetic" / "native" / "age_regimes.py",
    ROOT / "src" / "synthetic" / "native" / "clinical_modules.py",
    ROOT / "src" / "synthetic" / "native" / "counterfactual.py",
    ROOT / "src" / "synthetic" / "native" / "healthy.py",
    ROOT / "src" / "synthetic" / "native" / "observations.py",
    ROOT / "src" / "synthetic" / "native" / "trajectories.py",
}
OUTPUT_FILES = (
    "patients.csv",
    "patients_augmented.csv",
    "visits.csv",
    "visits_augmented-20251209150512.csv",
    "labs.csv",
    "medications.csv",
    "problem_list.csv",
    "referrals.csv",
    "datapackage.json",
    "validation-report.json",
    "manifest.json",
)


def _module_name(path: Path) -> str:
    return ".".join(path.relative_to(ROOT / "src").with_suffix("").parts)


def _import_base(node: ast.ImportFrom, module_name: str) -> str | None:
    if node.level == 0:
        return node.module
    package = module_name.split(".")[:-1]
    climb = node.level - 1
    if climb > len(package):
        return None
    parts = package[: len(package) - climb]
    if node.module is not None:
        parts.extend(node.module.split("."))
    return ".".join(parts)


def _imports_and_calls(path: Path) -> tuple[set[str], set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _import_base(node, _module_name(path))
            if base:
                imports.add(base)
                if base == "synthetic":
                    imports.update(f"{base}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    return imports, calls


def _visible_paths() -> tuple[Path, ...]:
    return (
        PACKAGE_EXPORT,
        ROOT / "src" / "synthetic" / "generate.py",
        ROOT / "src" / "synthetic" / "manifest.py",
        ROOT / "src" / "synthetic" / "derivation.py",
        *sorted((ROOT / "src" / "synthetic" / "native").rglob("*.py")),
    )


def _matches_forbidden(imports: set[str]) -> set[str]:
    return {
        imported
        for imported in imports
        if any(imported == module or imported.startswith(f"{module}.") for module in FORBIDDEN_MODULES)
    }


def test_visible_package_paths_reject_governed_synthea_and_package_reader_boundaries() -> None:
    """Catches an export path gaining governed inputs or descriptor/package readers."""
    for path in _visible_paths():
        imports, calls = _imports_and_calls(path)
        assert _matches_forbidden(imports) == set(), path
        if path != ROOT / "src" / "synthetic" / "generate.py":
            assert not calls & PACKAGE_PATH_READERS, path


def test_package_export_imports_only_lifecycle_and_schema_contract_dependencies() -> None:
    """Catches package export importing random, real-data, or governed modules directly."""
    imports, _calls = _imports_and_calls(PACKAGE_EXPORT)

    assert imports <= PACKAGE_EXPORT_IMPORTS


def test_randomness_dependencies_remain_limited_to_existing_synthetic_contracts() -> None:
    """Catches random generation being introduced into export-only boundary modules."""
    for path in _visible_paths():
        imports, _calls = _imports_and_calls(path)
        if "synthetic.randomness" in imports:
            assert path in RANDOMNESS_IMPORTERS


def test_exporter_apis_have_no_real_or_governed_input_arguments() -> None:
    for exporter in (export_exact_schema_package, export_observed_resource_package):
        assert not (set(inspect.signature(exporter).parameters) & FORBIDDEN_ARGUMENTS)


def test_production_cli_remains_fail_closed(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "synthetic.generate",
            "--output",
            str(tmp_path / "unavailable-package"),
            "--patients",
            "1",
            "--seed",
            "20260831",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "No production growth reference or authoritative derivation oracle is configured" in result.stderr
    assert not (tmp_path / "unavailable-package").exists()


def test_package_export_documentation_states_the_exact_api_and_boundaries() -> None:
    guide = GUIDE.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")

    assert "## Exact-schema observed-resource package export" in guide
    for required in (
        "PackageExportMetadata",
        "export_observed_resource_package",
        "IdentityPreservingTestDerivationOracle",
        "already-loaded mapping",
        "test-only oracle",
        "redacted",
        "deterministic",
        *OUTPUT_FILES,
    ):
        assert required in guide
    for deferred_gate in (
        "prevalence",
        "demographic calibration",
        "ancillary clinical pathways",
        "held-out validation",
        "privacy/non-matchability",
        "task utility",
        "clinical validity",
        "release",
        "Synthea conformance",
    ):
        assert deferred_gate in guide
    assert "structural success is not privacy/non-matchability or prevalence evidence" in guide
    assert "exact-schema observed-resource package export" in readme
    assert "does not enable package or file export" not in readme
