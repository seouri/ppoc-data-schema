from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_ROOT = ROOT / "src" / "synthetic"
MANIFEST_MODULE = SYNTHETIC_ROOT / "synthea_conformance.py"
AUGMENTER_MODULE = ROOT / "scripts" / "augment.py"
FORBIDDEN_CALL_ROOTS = {
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
FORBIDDEN_PACKAGE_CALLS = {
    "export_counterfactual_ehr_world_pair",
    "export_exact_schema_package",
    "export_observed_resource_package",
    "open",
    "Path",
    "write_package",
}
FORBIDDEN_WRITE_METHODS = {
    "mkdir",
    "rename",
    "replace",
    "unlink",
    "write_bytes",
    "write_text",
}
_DYNAMIC_IMPORT_CALLS = {"__import__", "importlib.import_module"}


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imports(path: Path) -> set[str]:
    tree = _tree(path)
    imports: set[str] = set()
    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
                bindings[alias.asname or alias.name.split(".", maxsplit=1)[0]] = alias.name
        elif isinstance(node, ast.ImportFrom):
            base = "." * node.level + (node.module or "")
            imports.add(base)
            separator = "" if base.endswith(".") else "."
            for alias in node.names:
                imported = f"{base}{separator}{alias.name}"
                imports.add(imported)
                bindings[alias.asname or alias.name] = imported
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        qualified = _qualified_name(node.func)
        if qualified is not None:
            head, *tail = qualified.split(".")
            qualified = ".".join([bindings.get(head, head), *tail])
            if qualified == "builtins.__import__":
                qualified = "__import__"
        if qualified not in _DYNAMIC_IMPORT_CALLS:
            continue
        argument = (
            node.args[0]
            if node.args
            else next(
                (keyword.value for keyword in node.keywords if keyword.arg == "name"),
                None,
            )
        )
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            imports.add(argument.value)
    return imports


def _absolute_module(imported: str) -> str:
    if imported.startswith("."):
        suffix = imported.lstrip(".")
        return f"synthetic.{suffix}" if suffix else "synthetic"
    return imported


def _assert_not_manifest_consumer(path: Path) -> None:
    imports = {_absolute_module(imported) for imported in _imports(path)}
    assert not any(
        imported == "synthetic.synthea_conformance"
        or imported.startswith("synthetic.synthea_conformance.")
        for imported in imports
    ), path.relative_to(ROOT) if path.is_relative_to(ROOT) else path


def _qualified_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def test_manifest_module_imports_only_the_standard_library() -> None:
    """Catches the declaration gaining project, engine, or external dependencies."""
    for imported in _imports(MANIFEST_MODULE):
        absolute = _absolute_module(imported)
        root = absolute.split(".", maxsplit=1)[0]
        assert root in sys.stdlib_module_names or absolute == "__future__", absolute
        assert root.lower() not in FORBIDDEN_CALL_ROOTS, absolute


def test_other_synthetic_modules_do_not_import_the_manifest_contract() -> None:
    """Catches automatic consumption by generation, export, or evaluator code."""
    for path in [*sorted(SYNTHETIC_ROOT.rglob("*.py")), AUGMENTER_MODULE]:
        if path == MANIFEST_MODULE:
            continue
        _assert_not_manifest_consumer(path)


def test_tracked_augmenter_is_in_the_non_consumer_scan() -> None:
    """Catches the tracked augmenter being omitted from the boundary guard."""
    assert AUGMENTER_MODULE.exists()
    _assert_not_manifest_consumer(AUGMENTER_MODULE)


def test_non_consumer_guard_rejects_manifest_import_in_augmenter_fixture(
    tmp_path: Path,
) -> None:
    """A manifest import in the augmenter-shaped path must fail the guard."""
    fixture = tmp_path / "scripts" / "augment.py"
    fixture.parent.mkdir()
    fixture.write_text("from synthetic import synthea_conformance\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="augment.py"):
        _assert_not_manifest_consumer(fixture)


@pytest.mark.parametrize(
    "source",
    (
        "import synthetic.synthea_conformance",
        "import synthetic.synthea_conformance as declaration",
        "from synthetic import synthea_conformance",
        "from synthetic import synthea_conformance as declaration",
        "from . import synthea_conformance",
        "from . import synthea_conformance as declaration",
        "from .synthea_conformance import SyntheaEngineManifest",
        'import importlib\nimportlib.import_module("synthetic.synthea_conformance")',
        '__import__("synthetic.synthea_conformance")',
        'import importlib as il\nil.import_module("synthetic.synthea_conformance")',
        'from importlib import import_module as load\nload("synthetic.synthea_conformance")',
        'import builtins as bi\nbi.__import__("synthetic.synthea_conformance")',
        'from builtins import __import__ as load\nload("synthetic.synthea_conformance")',
    ),
)
def test_import_scanner_records_alias_qualified_manifest_imports(
    tmp_path: Path,
    source: str,
) -> None:
    """Catches an import form disappearing from the non-consumption scan."""
    module = tmp_path / "visible.py"
    module.write_text(source, encoding="utf-8")

    imports = {_absolute_module(imported) for imported in _imports(module)}

    assert "synthetic.synthea_conformance" in imports


def test_import_scanner_records_literal_forbidden_runtime_import(tmp_path: Path) -> None:
    """Catches a forbidden runtime import hidden behind __import__()."""
    module = tmp_path / "visible.py"
    module.write_text('__import__("subprocess")', encoding="utf-8")

    imports = {_absolute_module(imported) for imported in _imports(module)}

    assert "subprocess" in imports


def test_manifest_module_has_no_engine_runtime_data_or_package_writer_calls() -> None:
    """Catches the declaration growing execution, I/O, or export behavior."""
    calls = {
        name
        for node in ast.walk(_tree(MANIFEST_MODULE))
        if isinstance(node, ast.Call)
        if (name := _qualified_name(node.func)) is not None
    }

    for name in calls:
        root = name.split(".", maxsplit=1)[0].lower()
        leaf = name.rsplit(".", maxsplit=1)[-1]
        assert root not in FORBIDDEN_CALL_ROOTS, name
        assert leaf not in FORBIDDEN_PACKAGE_CALLS, name
        assert leaf not in FORBIDDEN_WRITE_METHODS, name
