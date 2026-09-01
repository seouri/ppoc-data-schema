from __future__ import annotations

import ast
import inspect
from pathlib import Path

from synthetic import derivation_parity
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
ALLOWED_IMPORT_BASES = {
    "__future__",
    "collections.abc",
    "dataclasses",
    "enum",
    "json",
    "math",
    "re",
    "statistics",
    "synthetic.schema_contract",
    "types",
}
FORBIDDEN_BOUNDARY_CALLS = {
    "__import__",
    "audit_privacy",
    "calibrate",
    "copyfile",
    "compute_raw_targets",
    "export_exact_schema_package",
    "export_observed_resource_package",
    "generate_native_cohort",
    "load_calibration_artifact",
    "load_calibration_report",
    "load_privacy_policy",
    "open",
    "prepare_input",
    "prepare_synthetic_input",
    "read",
    "run",
    "scandir",
    "import_module",
    "validate_heldout",
    "write",
}
FORBIDDEN_PUBLIC_ARGUMENT_TOKENS = {
    "path",
    "paths",
    "key",
    "keys",
    "report",
    "reports",
    "output",
    "outputs",
}
PROTECTED_OUTPUT_FRAGMENTS = {
    "eventtrace",
    "hiddentruth",
    "identifier",
    "latent",
    "patientid",
    "row",
    "source",
    "trajectory",
    "truth",
}
ALLOWED_OUTPUT_NAMES = frozenset(
    (
        *REPORT_FIELDS,
        *CHECK_FIELDS,
        "implementation_id",
        "fingerprint",
        "test_only",
        "policy_id",
        "policy_version",
        "minimum_patient_rows",
        "minimum_visit_rows",
        "deterministic_tolerance",
        "reference_tolerance",
    )
)
PUBLIC_CALLABLES = {
    "DerivationImplementation",
    "DerivationParityCheck",
    "DerivationParityPolicy",
    "DerivationParityReport",
    "DerivationParityStatus",
    "DerivationParityUnavailable",
    "validate_derivation_parity",
}


def _module_context(path: Path) -> tuple[str, bool]:
    parts = list(path.relative_to(ROOT / "src").with_suffix("").parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts.pop()
    return ".".join(parts), is_package


def _import_base(
    node: ast.ImportFrom, module_name: str, *, is_package: bool
) -> str | None:
    if node.level == 0:
        return node.module
    package = module_name.split(".") if is_package else module_name.split(".")[:-1]
    climb = node.level - 1
    if climb > len(package):
        return None
    parts = package[: len(package) - climb]
    if node.module is not None:
        parts.extend(node.module.split("."))
    return ".".join(parts)


def _imports(tree: ast.AST, module_name: str, *, is_package: bool) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _import_base(node, module_name, is_package=is_package)
            if base:
                imports.add(base)
                imports.update(f"{base}.{alias.name}" for alias in node.names)
    return imports


def _import_bases(tree: ast.AST, module_name: str, *, is_package: bool) -> set[str]:
    return {
        base
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        if (base := _import_base(node, module_name, is_package=is_package))
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }


def _bindings(tree: ast.AST, module_name: str, *, is_package: bool) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bindings[alias.asname or alias.name.split(".", maxsplit=1)[0]] = alias.name
        elif isinstance(node, ast.ImportFrom):
            base = _import_base(node, module_name, is_package=is_package)
            if base:
                for alias in node.names:
                    bindings[alias.asname or alias.name] = f"{base}.{alias.name}"
    return bindings


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _qualified_calls(
    tree: ast.AST, module_name: str, *, is_package: bool
) -> set[str]:
    bindings = _bindings(tree, module_name, is_package=is_package)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and (name := _call_name(node.func)):
            root, dot, suffix = name.partition(".")
            names.add(f"{bindings.get(root, root)}{dot}{suffix}")
    return names


def _forbidden_calls(calls: set[str]) -> set[str]:
    return {
        call
        for call in calls
        if call.rsplit(".", maxsplit=1)[-1] in FORBIDDEN_BOUNDARY_CALLS
        or call.rsplit(".", maxsplit=1)[-1].startswith(("read_", "write_"))
    }


def _public_callable_names(tree: ast.Module) -> set[str]:
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }


def _forbidden_public_arguments(signature: inspect.Signature) -> set[str]:
    return {
        parameter.name
        for parameter in signature.parameters.values()
        if set(parameter.name.lower().split("_")) & FORBIDDEN_PUBLIC_ARGUMENT_TOKENS
    }


def _public_instance_method_names(tree: ast.Module) -> set[tuple[str, str]]:
    return {
        (parent.name, method.name)
        for parent in tree.body
        if isinstance(parent, ast.ClassDef) and parent.name in PUBLIC_CALLABLES
        for method in parent.body
        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not method.name.startswith("_")
    }


def _forbidden_public_instance_method_arguments(tree: ast.Module) -> set[str]:
    return {
        argument.arg
        for parent in tree.body
        if isinstance(parent, ast.ClassDef) and parent.name in PUBLIC_CALLABLES
        for method in parent.body
        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not method.name.startswith("_")
        for argument in (
            *method.args.posonlyargs,
            *method.args.args,
            *method.args.kwonlyargs,
        )
        if argument.arg not in {"self", "cls"}
        and set(argument.arg.lower().split("_")) & FORBIDDEN_PUBLIC_ARGUMENT_TOKENS
    }


def _public_serializers(tree: ast.Module) -> tuple[ast.FunctionDef, ...]:
    serializers: list[ast.FunctionDef] = []
    for parent in tree.body:
        if not isinstance(parent, ast.ClassDef):
            continue
        for method in parent.body:
            if isinstance(method, ast.FunctionDef) and method.name in {"to_mapping", "__repr__"}:
                serializers.append(method)
    return tuple(serializers)


def _serializer_output_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for serializer in _public_serializers(tree):
        for node in ast.walk(serializer):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                names.add(node.value)
            elif isinstance(node, (ast.Attribute, ast.Name)):
                names.add(node.attr if isinstance(node, ast.Attribute) else node.id)
            elif isinstance(node, ast.keyword) and node.arg is not None:
                names.add(node.arg)
    return names


def _protected_output_names(names: set[str]) -> set[str]:
    return {
        name
        for name in names
        if name not in ALLOWED_OUTPUT_NAMES
        and any(
            fragment in "".join(character for character in name.lower() if character.isalnum())
            for fragment in PROTECTED_OUTPUT_FRAGMENTS
        )
    }


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
    assert (
        "Identifiers, strings, flags/enums, copied identity fields, and null state are exact."
    ) in guide
    assert (
        "Only eligible finite numeric reference-dependent fields use `reference_tolerance`."
    ) in guide
    assert "Deterministic formulas use `deterministic_tolerance`." in guide
    assert (
        "Formula semantics are bound by `DERIVATION_PARITY_VERSION` and the checked-in evaluator "
        "implementation, not caller-mutated derivation annotations."
    ) in guide
    assert "The report's policy controls are public policy identity, not secret inputs." in guide
    assert (
        "Task utility is a separate non-authority evidence boundary governed by its own approved policy."
    ) in guide
    for field in (*REPORT_FIELDS, *CHECK_FIELDS):
        assert field in guide
    assert "fixed redacted" in combined
    assert "already-loaded fictional" in guide
    assert "privately controlled" in guide
    assert "CI fixtures are wholly fictional" in combined
    assert "privately loads both candidate and reference inputs" in combined
    assert "required review controls" in combined
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
    assert "[synthetic generator guide](docs/synthetic-generator.md)" in readme


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
    tree = ast.parse(PARITY.read_text(encoding="utf-8"), filename=str(PARITY))
    assert _public_callable_names(tree) == PUBLIC_CALLABLES
    for name in PUBLIC_CALLABLES:
        assert _forbidden_public_arguments(inspect.signature(getattr(derivation_parity, name))) == set()
    assert _public_instance_method_names(tree) == {
        ("DerivationImplementation", "to_mapping"),
        ("DerivationParityCheck", "to_mapping"),
        ("DerivationParityPolicy", "to_mapping"),
        ("DerivationParityReport", "to_json_bytes"),
        ("DerivationParityReport", "to_mapping"),
    }
    assert _forbidden_public_instance_method_arguments(tree) == set()


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
    module_name, is_package = _module_context(PARITY)

    assert _import_bases(tree, module_name, is_package=is_package) == ALLOWED_IMPORT_BASES
    assert _forbidden_calls(_qualified_calls(tree, module_name, is_package=is_package)) == set()


def test_public_parity_serializers_exclude_hidden_truth_names() -> None:
    tree = ast.parse(PARITY.read_text(encoding="utf-8"), filename=str(PARITY))
    assert _protected_output_names(_serializer_output_names(tree)) == set()


def test_visible_generation_export_and_governed_evaluators_do_not_auto_call_parity() -> None:
    paths = tuple(sorted((ROOT / "src" / "synthetic").rglob("*.py")))
    visible_paths = tuple(path for path in paths if path != PARITY)
    for path in visible_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        module_name, is_package = _module_context(path)
        imports = _imports(tree, module_name, is_package=is_package)
        assert "synthetic.derivation_parity" not in imports, path
        assert "validate_derivation_parity" not in _qualified_calls(
            tree, module_name, is_package=is_package
        ), path


def test_boundary_scanners_reject_forbidden_imports_and_qualified_calls() -> None:
    cases = (
        ("import synthetic.prevalence_evidence", {"synthetic.prevalence_evidence"}, set()),
        ("import synthea", {"synthea"}, set()),
        ("import os\nos.read(fd, 1)", {"os"}, {"os.read"}),
        ("import os\nos.write(fd, b'x')", {"os"}, {"os.write"}),
        ("import os\nos.scandir(root)", {"os"}, {"os.scandir"}),
        ("import shutil\nshutil.copyfile(source, target)", {"shutil"}, {"shutil.copyfile"}),
        ("import subprocess\nsubprocess.run(['command'])", {"subprocess"}, {"subprocess.run"}),
    )
    for source, unexpected_imports, forbidden_calls in cases:
        tree = ast.parse(source)
        assert _import_bases(tree, "synthetic.derivation_parity", is_package=False) - ALLOWED_IMPORT_BASES == unexpected_imports
        assert _forbidden_calls(
            _qualified_calls(tree, "synthetic.derivation_parity", is_package=False)
        ) == forbidden_calls


def test_redaction_scanner_rejects_hidden_compound_mapping_and_repr_names() -> None:
    cases = (
        ('return {"patient_id": "value"}', {"patient_id"}),
        ('return {"patient_rows": "value"}', {"patient_rows"}),
        ('return {"event_trace": "value"}', {"event_trace"}),
        ('return {"hidden_truth": "value"}', {"hidden_truth"}),
        ('return {"source_path": "value"}', {"source_path"}),
        ('return "row"', {"row"}),
    )
    for body, expected in cases:
        source = f"class Dangerous:\n    def to_mapping(self):\n        {body}\n"
        tree = ast.parse(source)
        assert _protected_output_names(_serializer_output_names(tree)) == expected


def test_redaction_scanner_rejects_keyword_mappings_and_attribute_references() -> None:
    cases = (
        ("to_mapping", "return dict(event_trace=value)", {"event_trace"}),
        ("to_mapping", "return {'safe': self.event_trace}", {"event_trace"}),
        ("__repr__", "return f'{self.event_trace!r}'", {"event_trace"}),
    )
    for method, body, expected in cases:
        source = f"class Dangerous:\n    def {method}(self):\n        {body}\n"
        tree = ast.parse(source)
        assert _protected_output_names(_serializer_output_names(tree)) == expected


def test_public_method_argument_guard_rejects_path_key_report_and_output_inputs() -> None:
    cases = (
        ("write_report", "output", {"output"}),
        ("from_path", "path", {"path"}),
        ("from_key", "key", {"key"}),
    )
    for method, argument, expected in cases:
        tree = ast.parse(
            f"class DerivationParityReport:\n    def {method}(self, {argument}):\n        ...\n"
        )
        assert _forbidden_public_instance_method_arguments(tree) == expected
