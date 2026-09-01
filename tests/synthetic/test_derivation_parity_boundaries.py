from __future__ import annotations

import ast
import inspect
from pathlib import Path

from synthetic.derivation_parity import (
    DERIVATION_PARITY_CHECK_NAMES,
    DERIVATION_PARITY_VERSION,
    DerivationParityUnavailable,
    validate_derivation_parity,
)

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "synthetic-generator.md"
README = ROOT / "README.md"
PARITY = ROOT / "src" / "synthetic" / "derivation_parity.py"

BASE_RESOURCES = (
    "patients",
    "visits",
    "labs",
    "medications",
    "problem_list",
    "referrals",
)
AUGMENTED_RESOURCES = ("patients_augmented", "visits_augmented")
REPORT_FIELDS = (
    "contract",
    "schema_fingerprint",
    "policy",
    "candidate",
    "reference",
    "patient_row_count",
    "visit_row_count",
    "status",
    "status_counts",
    "checks",
)
CHECK_FIELDS = (
    "name",
    "status",
    "reason_code",
    "compared_count",
    "mismatch_count",
    "maximum_absolute_difference",
)
FORBIDDEN_IMPORT_PREFIXES = (
    "pathlib",
    "csv",
    "duckdb",
    "requests",
    "urllib",
    "http",
    "socket",
    "synthetic.cohort",
    "synthetic.derivation",
    "synthetic.generate",
    "synthetic.native",
    "synthetic.package_export",
    "synthetic.manifest",
    "synthetic.calibrat",
    "synthetic.heldout",
    "synthetic.privacy",
    "synthetic.real",
    "synthetic.models",
    "synthetic.synthea",
)
FORBIDDEN_IO_CALLS = {
    "open",
    "read_bytes",
    "read_csv",
    "read_excel",
    "read_json",
    "read_parquet",
    "read_text",
    "read_table",
    "write_bytes",
    "write_text",
    "writerow",
    "writerows",
}
FORBIDDEN_BOUNDARY_CALLS = {
    "__import__",
    "audit_privacy",
    "calibrate",
    "compute_raw_targets",
    "export_exact_schema_package",
    "export_observed_resource_package",
    "generate_native_cohort",
    "load_calibration_artifact",
    "load_calibration_report",
    "load_privacy_policy",
    "prepare_input",
    "prepare_synthetic_input",
    "import_module",
    "validate_heldout",
}
HIDDEN_SERIALIZATION_NAMES = {
    "event_trace",
    "latent",
    "latent_state",
    "latent_states",
    "source",
    "source_frame",
    "source_object",
    "trajectory",
    "truth",
    "truth_hash",
}


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


def _imports(tree: ast.AST, module_name: str) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _import_base(node, module_name)
            if base:
                imports.add(base)
                imports.update(f"{base}.{alias.name}" for alias in node.names)
    return imports


def _call_leaf_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


def _public_serializers(tree: ast.Module) -> tuple[ast.FunctionDef, ...]:
    serializers: list[ast.FunctionDef] = []
    for parent in tree.body:
        if not isinstance(parent, ast.ClassDef):
            continue
        for method in parent.body:
            if isinstance(method, ast.FunctionDef) and method.name in {"to_mapping", "__repr__"}:
                serializers.append(method)
    return tuple(serializers)


def test_documentation_states_the_complete_parity_contract_and_safe_usage() -> None:
    guide = GUIDE.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    combined = f"{guide}\n{readme}"

    assert "## Evaluator-only augmented-derivation parity gate" in guide
    assert DERIVATION_PARITY_VERSION == "derivation-parity-v1"
    assert "DERIVATION_PARITY_VERSION = \"derivation-parity-v1\"" in guide
    assert "validate_derivation_parity" in guide
    assert "DerivationParityUnavailable" in guide
    assert "candidate" in guide and "reference" in guide
    assert "independently reviewed reference implementation" in combined
    assert (
        "`base_rows` contains exactly `patients`, `visits`, `labs`, "
        "`medications`, `problem_list`, and `referrals`"
    ) in guide
    assert (
        "`candidate_rows` and `reference_rows` each contain exactly "
        "`patients_augmented` and `visits_augmented`"
    ) in guide
    for check in (
        "deterministic_age_conversion",
        "deterministic_unit_conversion",
        "deterministic_bmi",
        "deterministic_patient_summaries",
        "clinical_flag_relationships",
        "reference_field_parity",
    ):
        assert check in guide
    assert "deterministic_tolerance" in guide
    assert "reference_tolerance" in guide
    assert "FAIL > UNEVALUABLE > PASS" in guide
    for field in (*REPORT_FIELDS, *CHECK_FIELDS):
        assert field in guide
    assert "fixed redacted" in combined
    assert "already-loaded fictional" in guide
    assert "privately controlled" in guide
    assert "report.status" in guide
    assert "report.to_mapping()" in guide
    for boundary in (
        "clinical validity",
        "real-population prevalence",
        "privacy/non-matchability",
        "release approval",
        "Synthea conformance",
    ):
        assert boundary in combined
    assert "Evaluator-only augmented-derivation parity gate" in readme
    assert "validate_derivation_parity" in readme


def test_parity_api_has_only_in_memory_inputs_and_no_path_key_or_output_arguments() -> None:
    signature = inspect.signature(validate_derivation_parity)
    assert tuple(signature.parameters) == (
        "base_rows",
        "candidate_rows",
        "reference_rows",
        "descriptor",
        "candidate",
        "reference",
        "policy",
    )
    for parameter in signature.parameters:
        lowered = parameter.lower()
        assert "path" not in lowered
        assert "key" not in lowered
        assert "output" not in lowered


def test_parity_contract_uses_the_fixed_check_universe_and_redaction() -> None:
    assert DERIVATION_PARITY_CHECK_NAMES == (
        "schema_contract",
        "base_shape",
        "candidate_shape",
        "reference_shape",
        "patient_key_alignment",
        "visit_key_alignment",
        "patient_identity_projection",
        "visit_identity_projection",
        "deterministic_age_conversion",
        "deterministic_unit_conversion",
        "deterministic_bmi",
        "deterministic_patient_summaries",
        "clinical_flag_relationships",
        "reference_field_parity",
        "support",
    )
    assert str(DerivationParityUnavailable("private detail")) == (
        "derivation parity evaluation is unavailable"
    )


def test_parity_module_remains_an_in_memory_evaluator_boundary() -> None:
    tree = ast.parse(PARITY.read_text(encoding="utf-8"), filename=str(PARITY))
    imports = _imports(tree, _module_name(PARITY))
    calls = _call_leaf_names(tree)

    assert not {
        name
        for name in imports
        if any(name == prefix or name.startswith(f"{prefix}.") for prefix in FORBIDDEN_IMPORT_PREFIXES)
    }
    assert not calls & FORBIDDEN_IO_CALLS
    assert not calls & FORBIDDEN_BOUNDARY_CALLS
    assert "validate_derivation_parity" not in calls


def test_public_parity_serializers_exclude_hidden_truth_names() -> None:
    tree = ast.parse(PARITY.read_text(encoding="utf-8"), filename=str(PARITY))
    names: set[str] = set()
    for serializer in _public_serializers(tree):
        for node in ast.walk(serializer):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                names.add(node.value)
    assert not names & HIDDEN_SERIALIZATION_NAMES


def test_visible_generation_export_and_governed_evaluators_do_not_auto_call_parity() -> None:
    paths = tuple(sorted((ROOT / "src" / "synthetic").rglob("*.py")))
    visible_paths = tuple(path for path in paths if path != PARITY)
    for path in visible_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = _imports(tree, _module_name(path))
        assert "synthetic.derivation_parity" not in imports, path
        assert "validate_derivation_parity" not in _call_leaf_names(tree), path
