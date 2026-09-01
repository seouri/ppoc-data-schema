from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_ROOT = ROOT / "src" / "synthetic"
GOLDEN_MODULE = SYNTHETIC_ROOT / "golden_trajectories.py"

_ALLOWED_IMPORT_BASES = {
    "__future__",
    "collections.abc",
    "dataclasses",
    "enum",
    "itertools",
    "json",
    "math",
    "re",
    "synthetic.models",
    "synthetic.native.age_regime_disorder",
    "synthetic.native.age_regimes",
    "synthetic.native.clinical_modules",
    "synthetic.randomness",
    "synthetic.references",
}
_FORBIDDEN_PUBLIC_ARGUMENT_TOKENS = {
    "artifact",
    "calibration",
    "csv",
    "descriptor",
    "file",
    "heldout",
    "java",
    "key",
    "manifest",
    "model",
    "output",
    "package",
    "path",
    "privacy",
    "root",
    "synthea",
    "writer",
}
_REQUIRED_VISIBLE_MODULES = {
    "__init__.py",
    "calibrate.py",
    "calibration.py",
    "calibration_disclosure.py",
    "calibration_input.py",
    "calibration_targets.py",
    "csv_package.py",
    "generate.py",
    "heldout_validate.py",
    "package_export.py",
    "prevalence_evidence.py",
    "privacy_audit.py",
    "synthea_conformance.py",
    "task_utility.py",
}
_FORBIDDEN_IMPORT_ROOTS = {
    "csv",
    "java",
    "os",
    "pathlib",
    "requests",
    "shutil",
    "subprocess",
    "synthea",
    "tempfile",
    "urllib",
}
_FORBIDDEN_CALL_LEAVES = {
    "NamedTemporaryFile",
    "Path",
    "TemporaryDirectory",
    "TemporaryFile",
    "dump",
    "export_counterfactual_ehr_world_pair",
    "export_exact_schema_package",
    "export_observed_resource_package",
    "fdopen",
    "load",
    "makedirs",
    "mkdir",
    "mkdtemp",
    "mkstemp",
    "open",
    "read_bytes",
    "read_csv",
    "read_text",
    "remove",
    "rename",
    "replace",
    "rmdir",
    "rmtree",
    "scandir",
    "symlink",
    "touch",
    "unlink",
    "write",
    "write_bytes",
    "write_csv",
    "write_package",
    "write_resource",
    "write_synthetic_descriptor",
    "write_text",
}


def _module_context(path: Path) -> tuple[str, bool]:
    parts = list(path.relative_to(ROOT / "src").with_suffix("").parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts.pop()
    return ".".join(parts), is_package


def _import_from_base(node: ast.ImportFrom, module_name: str, *, is_package: bool) -> str | None:
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


def _import_bases(tree: ast.AST, module_name: str, *, is_package: bool) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _import_from_base(node, module_name, is_package=is_package)
            if base:
                imported.add(base)
    return imported


def _qualified_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _unexpected_import_bases(imports: set[str]) -> set[str]:
    return imports - _ALLOWED_IMPORT_BASES


def _argument_names(arguments: ast.arguments) -> set[str]:
    names = {
        argument.arg
        for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)
    }
    if arguments.vararg is not None:
        names.add(arguments.vararg.arg)
    if arguments.kwarg is not None:
        names.add(arguments.kwarg.arg)
    return names - {"self", "cls"}


def _public_argument_and_field_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith(
            "_"
        ):
            names.update(_argument_names(node.args))
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    if not item.target.id.startswith("_"):
                        names.add(item.target.id)
                elif isinstance(
                    item, (ast.FunctionDef, ast.AsyncFunctionDef)
                ) and not item.name.startswith("_"):
                    names.update(_argument_names(item.args))
    return names


def test_golden_module_imports_only_stdlib_and_named_evaluator_contracts() -> None:
    """Catches governed, output, engine, or visible-generator dependencies."""
    tree = _tree(GOLDEN_MODULE)
    bases = _import_bases(tree, "synthetic.golden_trajectories", is_package=False)

    assert _unexpected_import_bases(bases) == set()
    for imported in bases:
        root = imported.split(".", maxsplit=1)[0]
        assert root.lower() not in _FORBIDDEN_IMPORT_ROOTS


@pytest.mark.parametrize(
    "source",
    (
        "import socket\nsocket.socket()",
        "import http.client\nhttp.client.HTTPConnection('fictional.invalid')",
        "import sqlite3\nsqlite3.connect('fictional.sqlite')",
        "import zipfile\nzipfile.ZipFile('fictional.zip')",
    ),
)
def test_import_allowlist_rejects_representative_network_and_file_clients(source: str) -> None:
    """Catches the stdlib allowlist admitting network, database, or archive clients."""
    bases = _import_bases(
        ast.parse(source),
        "synthetic.golden_trajectories",
        is_package=False,
    )

    assert _unexpected_import_bases(bases) == bases


def test_every_other_synthetic_module_remains_independent_of_golden_runner() -> None:
    """Catches automatic consumption by generation, export, or evaluator paths."""
    scanned: set[str] = set()
    for path in sorted(SYNTHETIC_ROOT.rglob("*.py")):
        if path == GOLDEN_MODULE:
            continue
        module_name, is_package = _module_context(path)
        imports = _imports(_tree(path), module_name, is_package=is_package)
        assert not any(
            imported == "synthetic.golden_trajectories"
            or imported.startswith("synthetic.golden_trajectories.")
            for imported in imports
        ), path.relative_to(ROOT)
        if path.parent == SYNTHETIC_ROOT:
            scanned.add(path.name)

    assert _REQUIRED_VISIBLE_MODULES <= scanned


@pytest.mark.parametrize(
    ("source", "module_name", "is_package"),
    [
        ("import synthetic.golden_trajectories", "synthetic.generate", False),
        (
            "from .golden_trajectories import run_golden_trajectory_suite",
            "synthetic.generate",
            False,
        ),
        ("from . import golden_trajectories", "synthetic", True),
    ],
)
def test_import_scan_detects_absolute_and_relative_golden_imports(
    source: str, module_name: str, is_package: bool
) -> None:
    """Catches a blind spot in the automatic-consumption regression scan."""
    imports = _imports(ast.parse(source), module_name, is_package=is_package)

    assert any(
        imported == "synthetic.golden_trajectories"
        or imported.startswith("synthetic.golden_trajectories.")
        for imported in imports
    )


def test_golden_module_has_no_file_package_engine_or_output_lifecycle_calls() -> None:
    """Catches evaluator-only code gaining filesystem, engine, or writer behavior."""
    tree = _tree(GOLDEN_MODULE)
    calls = {
        name
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        if (name := _qualified_name(node.func)) is not None
    }
    identifiers = {node.id.lower() for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
        node.attr.lower() for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }

    assert not identifiers & _FORBIDDEN_IMPORT_ROOTS
    assert not any("synthea" in identifier or "java" in identifier for identifier in identifiers)
    public_names = _public_argument_and_field_names(tree)
    assert not {
        name
        for name in public_names
        if set(name.lower().split("_")) & _FORBIDDEN_PUBLIC_ARGUMENT_TOKENS
    }
    for name in calls:
        root = name.split(".", maxsplit=1)[0].lower()
        leaf = name.rsplit(".", maxsplit=1)[-1]
        assert root not in _FORBIDDEN_IMPORT_ROOTS, name
        assert leaf not in _FORBIDDEN_CALL_LEAVES, name
        assert not leaf.startswith(("export_", "read_", "write_")), name
        assert "synthea" not in leaf.lower(), name
