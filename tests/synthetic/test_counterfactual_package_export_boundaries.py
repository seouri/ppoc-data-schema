from __future__ import annotations

import ast
import inspect
from pathlib import Path

from synthetic.package_export import (
    CounterfactualPackageExportUnavailable,
    export_counterfactual_ehr_world_pair,
)

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "synthetic-generator.md"
README = ROOT / "README.md"
PACKAGE_EXPORT = ROOT / "src" / "synthetic" / "package_export.py"

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
    "calibration",
    "calibration_artifact",
    "model",
    "network",
    "synthea",
}
HIDDEN_IDENTIFIERS = {
    "event_trace",
    "latent_state",
    "latent_states",
    "source_frame",
    "source_object",
    "trajectory",
    "truth",
    "truth_hash",
    "patient_index",
    "stream_identity",
}
ALLOWED_PACKAGE_IMPORTS = {
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


def _imports(tree: ast.AST) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def _call_leaves(tree: ast.AST) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            function = node.func
            while isinstance(function, ast.Attribute):
                function = function.value
            if isinstance(node.func, ast.Attribute):
                result.add(node.func.attr)
            elif isinstance(function, ast.Name):
                result.add(function.id)
    return result


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    return next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)


def test_pair_export_documentation_states_the_exact_envelope_and_child_contract() -> None:
    guide = GUIDE.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    required = (
        "export_counterfactual_ehr_world_pair",
        "CounterfactualPackageExportUnavailable",
        "caller-loaded descriptor mapping",
        "explicit metadata",
        "test-only oracle",
        "baseline/",
        "intervention/",
        "exact eleven-file",
        "pair-manifest.json",
        "contract",
        "schema_fingerprint",
        "matrix_version",
        "serialization_projection",
        "validation_status",
        "validation_check_counts",
        "metadata",
        "children",
        "manifest_sha256",
        "aggregate-only",
        "not a PPOC package",
        "not a truth manifest",
        "hidden truth",
        "no real-data",
        "governed",
    )
    assert all(term in guide for term in required)
    assert "export_counterfactual_ehr_world_pair" in readme
    assert "pair-manifest.json" in readme
    assert "baseline/" in readme and "intervention/" in readme
    assert "not a PPOC package" in readme


def test_pair_export_documentation_retains_all_separate_evidence_deferrals() -> None:
    guide = GUIDE.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    combined = f"{guide}\n{readme}"
    for deferred in (
        "prevalence",
        "demographic calibration",
        "held-out",
        "temporal drift",
        "task utility",
        "clinical validity",
        "privacy",
        "non-matchability",
        "release approval",
        "Synthea",
    ):
        assert deferred in combined


def test_pair_export_public_signature_has_only_typed_in_memory_inputs_and_output() -> None:
    signature = inspect.signature(export_counterfactual_ehr_world_pair)
    assert tuple(signature.parameters) == (
        "worlds",
        "descriptor",
        "output",
        "metadata",
        "derivation_oracle",
        "trusted_derivation_fingerprint",
        "trusted_derivation_test_only",
    )
    assert not set(signature.parameters) & FORBIDDEN_ARGUMENTS
    assert signature.parameters["output"].annotation == "Path"
    for parameter in signature.parameters.values():
        if parameter.name != "output":
            assert "path" not in parameter.name.lower()
            assert "root" not in parameter.name.lower()

    assert issubclass(CounterfactualPackageExportUnavailable, Exception)


def test_pair_export_module_uses_only_allowed_dependencies() -> None:
    tree = ast.parse(PACKAGE_EXPORT.read_text(encoding="utf-8"))
    assert _imports(tree) <= ALLOWED_PACKAGE_IMPORTS
    assert not _imports(tree) & FORBIDDEN_MODULES


def test_pair_export_has_no_generic_observed_export_or_new_reader_boundary() -> None:
    tree = ast.parse(PACKAGE_EXPORT.read_text(encoding="utf-8"))
    pair = _function(tree, "export_counterfactual_ehr_world_pair")
    calls = _call_leaves(pair)
    assert "export_observed_resource_package" not in calls
    assert not calls & {
        "open",
        "read_csv",
        "read_json",
        "read_parquet",
        "read_text",
        "read_bytes",
        "write_text",
        "write_bytes",
    }


def test_pair_export_public_mappings_do_not_name_hidden_truth_objects() -> None:
    tree = ast.parse(PACKAGE_EXPORT.read_text(encoding="utf-8"))
    public_helpers = [
        _function(tree, "_pair_run_id"),
        _function(tree, "_pair_base_rows"),
        _function(tree, "_pair_manifest"),
        _function(tree, "export_counterfactual_ehr_world_pair"),
    ]
    identifiers = {
        node.id
        for helper in public_helpers
        for node in ast.walk(helper)
        if isinstance(node, ast.Name)
    }
    assert not identifiers & HIDDEN_IDENTIFIERS

    manifest = _function(tree, "_pair_manifest")
    keys = {
        node.value
        for node in ast.walk(manifest)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert not keys & HIDDEN_IDENTIFIERS
