from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "synthetic-generator.md"
README = ROOT / "README.md"
TEMPORAL_DRIFT = ROOT / "src" / "synthetic" / "temporal_drift.py"

_VISIBLE_MODULES = (
    ROOT / "src" / "synthetic" / "generate.py",
    ROOT / "src" / "synthetic" / "manifest.py",
    ROOT / "src" / "synthetic" / "derivation.py",
    ROOT / "src" / "synthetic" / "package_export.py",
    ROOT / "src" / "synthetic" / "csv_package.py",
    *sorted((ROOT / "src" / "synthetic" / "native").rglob("*.py")),
)
_FORBIDDEN_EVALUATOR_MODULES = {
    "csv",
    "duckdb",
    "pathlib",
    "shutil",
    "tempfile",
    "synthetic.calibrate",
    "synthetic.calibration_disclosure",
    "synthetic.calibration_input",
    "synthetic.calibration_targets",
    "synthetic.csv_package",
    "synthetic.heldout_validate",
    "synthetic.manifest",
    "synthetic.package_export",
    "synthetic.privacy_audit",
    "synthetic.run_directory",
    "synthetic.synthea",
}
_ALLOWED_CALIBRATION_IMPORTS = {
    "synthetic.calibration",
    "synthetic.calibration.require_aggregate_safe_token",
}
_FORBIDDEN_CALL_LEAVES = {
    "NamedTemporaryFile",
    "Path",
    "RunDirectory",
    "TemporaryDirectory",
    "TemporaryFile",
    "chmod",
    "chown",
    "copy",
    "copy2",
    "copyfile",
    "copytree",
    "dump",
    "export_exact_schema_package",
    "export_observed_resource_package",
    "hardlink_to",
    "link",
    "makedirs",
    "mkdir",
    "mkdtemp",
    "mkstemp",
    "move",
    "open",
    "read_bytes",
    "read_csv",
    "read_text",
    "remove",
    "rename",
    "replace",
    "rmdir",
    "rmtree",
    "symlink",
    "symlink_to",
    "touch",
    "unlink",
    "write",
    "write_bytes",
    "write_csv",
    "write_resource",
    "write_synthetic_descriptor",
    "write_text",
}
_FORBIDDEN_PUBLIC_ARGUMENT_TOKENS = {
    "key",
    "keys",
    "output",
    "outputs",
    "path",
    "paths",
    "report",
    "reports",
}
_METRICS = (
    "growth_window_coverage",
    "visible_visit_coverage",
    "visible_event_rate",
    "mean_inter_visit_days",
    "mean_visit_count_step",
    "recorded_event_rate_step",
    "causal_event_order",
    "causal_event_timing",
)
_NON_CLAIMS = (
    "real-data temporal fidelity",
    "growth-disorder prevalence",
    "clinical validity",
    "privacy/non-matchability",
    "task utility",
    "release readiness",
    "Synthea conformance",
)


def _module_context(path: Path) -> tuple[str, bool]:
    parts = list(path.relative_to(ROOT / "src").with_suffix("").parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts.pop()
    return ".".join(parts), is_package


def _import_from_base(
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
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _import_from_base(node, module_name, is_package=is_package)
            if base:
                imported.add(base)
                imported.update(f"{base}.{alias.name}" for alias in node.names)
    return imported


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _calls(tree: ast.AST) -> set[str]:
    return {
        name
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        if (name := _call_name(node.func)) is not None
    }


def _argument_names(node: ast.arguments) -> set[str]:
    arguments = {
        argument.arg
        for argument in (*node.posonlyargs, *node.args, *node.kwonlyargs)
    }
    if node.vararg is not None:
        arguments.add(node.vararg.arg)
    if node.kwarg is not None:
        arguments.add(node.kwarg.arg)
    return arguments


def _public_arguments(tree: ast.Module) -> set[str]:
    arguments: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith(
            "_"
        ):
            arguments.update(_argument_names(node.args))
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and not item.name.startswith(
                    "_"
                ):
                    arguments.update(_argument_names(item.args))
    return arguments - {"self", "cls"}


def _forbidden_modules(imports: set[str]) -> set[str]:
    return {
        imported
        for imported in imports
        if (
            imported.startswith("synthetic.calibration.")
            and imported not in _ALLOWED_CALIBRATION_IMPORTS
        )
        or any(
            imported == forbidden or imported.startswith(f"{forbidden}.")
            for forbidden in _FORBIDDEN_EVALUATOR_MODULES
        )
    }


def _forbidden_calls(calls: set[str]) -> set[str]:
    return {
        call
        for call in calls
        if (
            (leaf := call.rsplit(".", maxsplit=1)[-1]) in _FORBIDDEN_CALL_LEAVES
            or leaf.startswith(("export_", "read_", "write_"))
        )
    }


def _forbidden_public_arguments(arguments: set[str]) -> set[str]:
    return {
        argument
        for argument in arguments
        if set(argument.split("_")) & _FORBIDDEN_PUBLIC_ARGUMENT_TOKENS
    }


def test_visible_generation_export_and_native_paths_do_not_import_temporal_evaluator() -> None:
    for path in _VISIBLE_MODULES:
        module_name, is_package = _module_context(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = _imports(tree, module_name, is_package=is_package)
        assert not any(
            imported == "synthetic.temporal_drift"
            or imported.startswith("synthetic.temporal_drift.")
            for imported in imports
        ), path


def test_temporal_evaluator_has_no_filesystem_governed_or_output_lifecycle() -> None:
    tree = ast.parse(
        TEMPORAL_DRIFT.read_text(encoding="utf-8"), filename=str(TEMPORAL_DRIFT)
    )
    imports = _imports(tree, "synthetic.temporal_drift", is_package=False)

    assert _forbidden_modules(imports) == set()
    assert _forbidden_calls(_calls(tree)) == set()
    assert _forbidden_public_arguments(_public_arguments(tree)) == set()


@pytest.mark.parametrize(
    ("source", "module_name", "is_package"),
    [
        ("from synthetic import temporal_drift", "synthetic.generate", False),
        ("from . import temporal_drift", "synthetic.generate", False),
        ("from .. import temporal_drift", "synthetic.native.healthy", False),
        ("from .. import temporal_drift", "synthetic.native", True),
    ],
)
def test_visible_import_scan_detects_temporal_evaluator(
    source: str, module_name: str, is_package: bool
) -> None:
    imports = _imports(ast.parse(source), module_name, is_package=is_package)
    assert "synthetic.temporal_drift" in imports


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from pathlib import Path", {"pathlib", "pathlib.Path"}),
        ("import duckdb", {"duckdb"}),
        ("from synthetic import privacy_audit", {"synthetic.privacy_audit"}),
        (
            "import synthetic.calibration_targets",
            {"synthetic.calibration_targets"},
        ),
        (
            "from synthetic import calibration_targets",
            {"synthetic.calibration_targets"},
        ),
        (
            "from synthetic.calibration import load_calibration_artifact",
            {"synthetic.calibration.load_calibration_artifact"},
        ),
        (
            "from synthetic.package_export import export_observed_resource_package",
            {
                "synthetic.package_export",
                "synthetic.package_export.export_observed_resource_package",
            },
        ),
    ],
)
def test_evaluator_import_scan_detects_forbidden_dependencies(
    source: str, expected: set[str]
) -> None:
    imports = _imports(
        ast.parse(source), "synthetic.temporal_drift", is_package=False
    )
    assert _forbidden_modules(imports) == expected


def test_evaluator_import_scan_allows_only_the_aggregate_token_validator() -> None:
    imports = _imports(
        ast.parse(
            "from synthetic.calibration import require_aggregate_safe_token"
        ),
        "synthetic.temporal_drift",
        is_package=False,
    )
    assert _forbidden_modules(imports) == set()


@pytest.mark.parametrize(
    "source",
    [
        "Path('report.json')",
        "open('report.json')",
        "destination.write_text('payload')",
        "export_observed_resource_package(bundle)",
    ],
)
def test_evaluator_call_scan_detects_filesystem_and_export_lifecycles(
    source: str,
) -> None:
    assert _forbidden_calls(_calls(ast.parse(source)))


@pytest.mark.parametrize(
    "argument",
    ["path", "partition_key_file", "heldout_report", "output_path"],
)
def test_evaluator_public_argument_scan_detects_lifecycle_inputs(argument: str) -> None:
    tree = ast.parse(
        f"def validate_temporal_drift(cohort, policy, *, {argument}=None): ..."
    )
    assert _forbidden_public_arguments(_public_arguments(tree)) == {argument}


def test_temporal_drift_guide_documents_exact_evaluator_contract() -> None:
    guide = GUIDE.read_text(encoding="utf-8")
    temporal_section = guide.split(
        "## Evaluator-only temporal-drift validation\n", maxsplit=1
    )[1].split("\n## ", maxsplit=1)[0]

    assert "## Evaluator-only temporal-drift validation" in guide
    assert "report = validate_temporal_drift(cohort, policy)" in guide
    assert "[lower_age_days, upper_age_days)" in guide
    assert "hidden causal" in guide
    for name in ("TemporalDriftPolicy", "TemporalWindowPolicy", "validate_temporal_drift"):
        assert name in guide
    for metric in _METRICS:
        assert metric in guide
    for status in ("PASS", "FAIL", "UNEVALUABLE"):
        assert status in guide
    for boundary in _NON_CLAIMS:
        assert boundary in guide
    assert (
        "Individual comparisons with missing or insufficient evidence remain `UNEVALUABLE`"
        in temporal_section
    )
    assert "do not by themselves block an overall `PASS`" in temporal_section
    assert "smaller than `minimum_cohort_size`" in temporal_section
    assert "required window lacks minimum support" in temporal_section
    assert "strictly exceeds `maximum_unevaluable_checks`" in temporal_section


def test_readme_summarizes_temporal_drift_api_metrics_and_non_claims() -> None:
    readme = README.read_text(encoding="utf-8")
    paragraph_start = readme.index(
        "The evaluator-only [`validate_temporal_drift`]"
    )
    temporal_paragraph = readme[paragraph_start:].split("\n\n", maxsplit=1)[0]

    assert "docs/synthetic-generator.md#evaluator-only-temporal-drift-validation" in readme
    for name in ("TemporalDriftPolicy", "TemporalWindowPolicy", "validate_temporal_drift"):
        assert name in readme
    for metric in _METRICS:
        assert metric in readme
    for status in ("PASS", "FAIL", "UNEVALUABLE"):
        assert status in readme
    for boundary in _NON_CLAIMS:
        assert boundary in readme
    assert (
        "Individual `UNEVALUABLE` comparisons do not by themselves block an overall `PASS`"
        in temporal_paragraph
    )
    assert "smaller than `minimum_cohort_size`" in temporal_paragraph
    assert "required window lacks minimum support" in temporal_paragraph
    assert "strictly exceeds `maximum_unevaluable_checks`" in temporal_paragraph
