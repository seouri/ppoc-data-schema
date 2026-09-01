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
COHORT = ROOT / "src" / "synthetic" / "cohort.py"
FORBIDDEN_MODULES = {
    "synthetic.calibrate",
    "synthetic.calibration",
    "synthetic.calibration_disclosure",
    "synthetic.calibration_input",
    "synthetic.calibration_targets",
    "synthetic.heldout_validate",
    "synthetic.privacy_audit",
    "synthetic.real_data",
    "synthetic.realdata",
    "synthetic.synthea",
}
FORBIDDEN_ARGUMENTS = {
    "real_root",
    "data_root",
    "real_data_root",
    "realdata_root",
    "snapshot_root",
    "partition_key",
    "heldout_report",
    "privacy_policy",
}
FORBIDDEN_REAL_DATA_IDENTIFIERS = FORBIDDEN_ARGUMENTS | {
    "real_data",
    "realdata",
    "ppoc_root",
    "source_data_root",
}
FORBIDDEN_CALL_SYMBOLS = {
    "audit_privacy",
    "build_result",
    "calibrate",
    "compute_raw_targets",
    "disclose_targets",
    "load_calibration_artifact",
    "load_calibration_report",
    "load_privacy_policy",
    "prepare_input",
    "prepare_synthetic_input",
    "validate_heldout",
}
PACKAGE_EXPORT_IMPORTS = {
    "__future__",
    "collections.abc",
    "dataclasses",
    "hashlib",
    "json",
    "math",
    "os",
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
    "synthetic.native.ancillary",
    "synthetic.native.counterfactual_worlds",
    "synthetic.native.resources",
    "synthetic.run_directory",
    "synthetic.schema_contract",
    "synthetic.validate",
}
PACKAGE_PATH_READERS = {
    "load_descriptor",
    "open",
    "read_csv",
    "read_excel",
    "read_json",
    "read_parquet",
    "read_text",
    "read_table",
}
LEGACY_READER_CALLS = {
    ROOT / "src" / "synthetic" / "generate.py": ("load_descriptor",),
    PACKAGE_EXPORT: ("read_bytes",),
}
RANDOMNESS_IMPORTERS = {
    COHORT,
    ROOT / "src" / "synthetic" / "generate.py",
    ROOT / "src" / "synthetic" / "manifest.py",
    ROOT / "src" / "synthetic" / "native" / "age_regime_disorder.py",
    ROOT / "src" / "synthetic" / "native" / "age_regimes.py",
    ROOT / "src" / "synthetic" / "native" / "clinical_modules.py",
    ROOT / "src" / "synthetic" / "native" / "counterfactual.py",
    ROOT / "src" / "synthetic" / "native" / "counterfactual_worlds.py",
    ROOT / "src" / "synthetic" / "native" / "healthy.py",
    ROOT / "src" / "synthetic" / "native" / "observations.py",
    ROOT / "src" / "synthetic" / "native" / "trajectories.py",
}
COHORT_ALLOWED_CALLS = frozenset(
    {
        "synthetic.calibration.require_aggregate_safe_token",
        "synthetic.calibration_targets.ETHNICITY_CATEGORY_SLUGS.items",
        "synthetic.calibration_targets.ETHNICITY_CATEGORY_SLUGS.values",
        "synthetic.calibration_targets.RACE_CATEGORY_SLUGS.items",
        "synthetic.calibration_targets.RACE_CATEGORY_SLUGS.values",
        "synthetic.calibration_targets.SEX_CATEGORY_SLUGS.items",
        "synthetic.calibration_targets.SEX_CATEGORY_SLUGS.values",
        "synthetic.calibration_targets.is_registered_target_key",
    }
)
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


def test_boundary_deny_lists_cover_governed_real_data_and_path_reader_categories() -> None:
    """Catches a visible package path gaining an unguarded governed or reader boundary."""
    assert {
        "synthetic.calibration_disclosure",
        "synthetic.calibration_targets",
        "synthetic.real_data",
        "synthetic.realdata",
    } <= FORBIDDEN_MODULES
    assert {"open", "read_json", "read_text"} <= PACKAGE_PATH_READERS
    assert {"real_data_root", "realdata_root", "snapshot_root"} <= FORBIDDEN_ARGUMENTS


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


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None


def _qualified_call_name(name: str, bindings: dict[str, str]) -> str:
    root, dot, suffix = name.partition(".")
    return f"{bindings.get(root, root)}{dot}{suffix}"


def _is_read_open(node: ast.Call, name: str) -> bool:
    if name == "os.open":
        return False
    if node.keywords:
        mode = next((item.value for item in node.keywords if item.arg == "mode"), None)
    else:
        mode = None
    if mode is None:
        mode_index = 0 if "." in name else 1
        if len(node.args) > mode_index:
            mode = node.args[mode_index]
    if mode is None:
        return True
    return not (
        isinstance(mode, ast.Constant)
        and isinstance(mode.value, str)
        and any(marker in mode.value for marker in ("w", "x", "a", "+"))
    )


def _imports_calls_readers_and_identifiers(
    source: str, module_name: str
) -> tuple[set[str], set[str], tuple[str, ...], set[str]]:
    tree = ast.parse(source, filename=f"<{module_name}>")
    imports: set[str] = set()
    bindings: dict[str, str] = {}
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
                bindings[alias.asname or alias.name.split(".", maxsplit=1)[0]] = alias.name
        elif isinstance(node, ast.ImportFrom):
            base = _import_base(node, module_name)
            if base:
                imports.add(base)
                for alias in node.names:
                    bindings[alias.asname or alias.name] = f"{base}.{alias.name}"
                    if base == "synthetic":
                        imports.add(f"{base}.{alias.name}")

    readers: list[str] = []
    identifiers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.arg):
            identifiers.add(node.arg)
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name is None:
                continue
            qualified = _qualified_call_name(name, bindings)
            calls.add(qualified)
            leaf = name.rsplit(".", maxsplit=1)[-1]
            if leaf in PACKAGE_PATH_READERS and (
                leaf != "open" or _is_read_open(node, qualified)
            ) or leaf == "read_bytes":
                readers.append(leaf)
    return imports, calls, tuple(sorted(readers)), identifiers


def _imports_and_calls(path: Path) -> tuple[set[str], set[str]]:
    imports, calls, _readers, _identifiers = _imports_calls_readers_and_identifiers(
        path.read_text(encoding="utf-8"), _module_name(path)
    )
    return imports, calls


def _visible_paths() -> tuple[Path, ...]:
    return (
        COHORT,
        PACKAGE_EXPORT,
        ROOT / "src" / "synthetic" / "generate.py",
        ROOT / "src" / "synthetic" / "manifest.py",
        ROOT / "src" / "synthetic" / "derivation.py",
        *sorted((ROOT / "src" / "synthetic" / "native").rglob("*.py")),
    )


def _matches_forbidden(
    names: set[str],
    *,
    allowed_names: frozenset[str] = frozenset(),
) -> set[str]:
    return {
        name
        for name in names
        if name not in allowed_names
        and (
            any(
                name == module or name.startswith(f"{module}.")
                for module in FORBIDDEN_MODULES
            )
            or name.rsplit(".", maxsplit=1)[-1] in FORBIDDEN_CALL_SYMBOLS
        )
    }


def test_visible_package_paths_reject_governed_synthea_and_package_reader_boundaries() -> None:
    """Catches an export path gaining governed inputs or descriptor/package readers."""
    for path in _visible_paths():
        allowed_imports = (
            frozenset({"synthetic.calibration", "synthetic.calibration_targets"})
            if path == COHORT
            else frozenset()
        )
        imports, calls, readers, identifiers = _imports_calls_readers_and_identifiers(
            path.read_text(encoding="utf-8"), _module_name(path)
        )
        assert _matches_forbidden(imports, allowed_names=allowed_imports) == set(), path
        allowed_calls = COHORT_ALLOWED_CALLS if path == COHORT else frozenset()
        assert _matches_forbidden(calls, allowed_names=allowed_calls) == set(), path
        assert not identifiers & FORBIDDEN_REAL_DATA_IDENTIFIERS, path
        assert readers == LEGACY_READER_CALLS.get(path, ()), path


def test_scanner_qualifies_alias_calls_and_detects_new_package_readers() -> None:
    source = """from synthetic.calibration_targets import compute_raw_targets as compute
from synthetic import privacy_audit as privacy
compute()
privacy.audit_privacy()
Path('future-package').read_text()
"""

    imports, calls, readers, _identifiers = _imports_calls_readers_and_identifiers(
        source, "synthetic.generate"
    )

    assert _matches_forbidden(imports) == {
        "synthetic.calibration_targets",
        "synthetic.privacy_audit",
    }
    assert _matches_forbidden(calls) == {
        "synthetic.calibration_targets.compute_raw_targets",
        "synthetic.privacy_audit.audit_privacy",
    }
    assert readers == ("read_text",)


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

    opening = guide.split("\n\n", maxsplit=2)[1]
    assert "exact-schema synthetic smoke generator" in opening
    assert "development-only observed-resource package export" in opening
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
    assert "Labs, medications, referrals, exact-schema export," not in guide
    assert "exact-schema observed-resource package export" in readme
    assert "does not enable package or file export" not in readme
