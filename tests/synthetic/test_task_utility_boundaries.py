from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TASK_UTILITY = ROOT / "src" / "synthetic" / "task_utility.py"

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
    "lightgbm",
    "pathlib",
    "shutil",
    "sklearn",
    "tempfile",
    "tensorflow",
    "torch",
    "xgboost",
    "synthea",
    "synthetic.calibrate",
    "synthetic.calibration_disclosure",
    "synthetic.calibration_input",
    "synthetic.calibration_targets",
    "synthetic.csv_package",
    "synthetic.generate",
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
    "GridSearchCV",
    "NamedTemporaryFile",
    "Path",
    "RandomizedSearchCV",
    "RunDirectory",
    "TemporaryDirectory",
    "TemporaryFile",
    "dump",
    "export_exact_schema_package",
    "export_observed_resource_package",
    "fit",
    "fit_predict",
    "fit_transform",
    "load_calibration_artifact",
    "load_manifest",
    "load_package",
    "makedirs",
    "mkdir",
    "mkdtemp",
    "mkstemp",
    "open",
    "partial_fit",
    "predict",
    "predict_proba",
    "read_bytes",
    "read_csv",
    "read_text",
    "remove",
    "rename",
    "replace",
    "rmdir",
    "rmtree",
    "symlink",
    "touch",
    "train",
    "train_model",
    "tune",
    "unlink",
    "write",
    "write_bytes",
    "write_csv",
    "write_resource",
    "write_synthetic_descriptor",
    "write_text",
    "build_manifest",
    "build_package",
}
_FORBIDDEN_PUBLIC_ARGUMENT_TOKENS = {
    "callable",
    "key",
    "keys",
    "model",
    "models",
    "output",
    "outputs",
    "path",
    "paths",
    "report",
    "reports",
}


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
    forbidden = {
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
    if (
        "synthetic.calibration" in imports
        and "synthetic.calibration.require_aggregate_safe_token" not in imports
    ):
        forbidden.add("synthetic.calibration")
    return forbidden


def _forbidden_calls(calls: set[str]) -> set[str]:
    return {
        call
        for call in calls
        if (
            (leaf := call.rsplit(".", maxsplit=1)[-1])
            in _FORBIDDEN_CALL_LEAVES
            or leaf.startswith(("export_", "read_", "write_"))
            or "synthea" in leaf.lower()
        )
    }


def _forbidden_public_arguments(arguments: set[str]) -> set[str]:
    return {
        argument
        for argument in arguments
        if set(argument.split("_")) & _FORBIDDEN_PUBLIC_ARGUMENT_TOKENS
    }


def test_visible_generation_export_and_native_paths_do_not_import_task_evaluator() -> None:
    for path in _VISIBLE_MODULES:
        module_name, is_package = _module_context(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = _imports(tree, module_name, is_package=is_package)
        assert not any(
            imported == "synthetic.task_utility"
            or imported.startswith("synthetic.task_utility.")
            for imported in imports
        ), path


def test_task_evaluator_has_no_filesystem_governed_training_or_output_lifecycle() -> None:
    tree = ast.parse(
        TASK_UTILITY.read_text(encoding="utf-8"), filename=str(TASK_UTILITY)
    )
    imports = _imports(tree, "synthetic.task_utility", is_package=False)

    assert _forbidden_modules(imports) == set()
    assert _forbidden_calls(_calls(tree)) == set()
    assert _forbidden_public_arguments(_public_arguments(tree)) == set()


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from pathlib import Path", {"pathlib", "pathlib.Path"}),
        ("import duckdb", {"duckdb"}),
        (
            "from sklearn.linear_model import LogisticRegression",
            {"sklearn.linear_model", "sklearn.linear_model.LogisticRegression"},
        ),
        ("import synthetic.calibration", {"synthetic.calibration"}),
        ("from synthetic import privacy_audit", {"synthetic.privacy_audit"}),
        (
            "from synthetic import calibration_targets",
            {"synthetic.calibration_targets"},
        ),
        (
            "from synthetic.calibration import load_calibration_artifact",
            {
                "synthetic.calibration",
                "synthetic.calibration.load_calibration_artifact",
            },
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
def test_import_scan_detects_forbidden_dependencies(
    source: str, expected: set[str]
) -> None:
    imports = _imports(ast.parse(source), "synthetic.task_utility", is_package=False)
    assert _forbidden_modules(imports) == expected


def test_import_scan_allows_only_aggregate_token_validator_from_calibration() -> None:
    imports = _imports(
        ast.parse("from synthetic.calibration import require_aggregate_safe_token"),
        "synthetic.task_utility",
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
        "model.fit(features, labels)",
        "model.predict(features)",
        "build_manifest(rows)",
        "run_synthea(config)",
    ],
)
def test_call_scan_detects_filesystem_export_and_model_training(source: str) -> None:
    assert _forbidden_calls(_calls(ast.parse(source)))


@pytest.mark.parametrize(
    "argument",
    [
        "data_path",
        "partition_key_file",
        "heldout_report",
        "output_path",
        "screening_model",
        "predict_callable",
    ],
)
def test_public_argument_scan_detects_forbidden_inputs(argument: str) -> None:
    tree = ast.parse(
        f"def evaluate_task_utility(cohort, predictions, policy, *, {argument}=None): ..."
    )
    assert _forbidden_public_arguments(_public_arguments(tree)) == {argument}
