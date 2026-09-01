from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_ROOT = ROOT / "src" / "synthetic"
ADAPTER = SYNTHETIC_ROOT / "augmenter_oracle.py"
PRODUCTION_CLI = SYNTHETIC_ROOT / "generate.py"
ADAPTER_ALLOWED_PROJECT_IMPORTS = {
    "synthetic.derivation",
    "synthetic.schema_contract",
}
PRODUCTION_FAILURE = (
    "No production growth reference or authoritative derivation oracle is configured"
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                imports.add("." * node.level + (node.module or ""))
            elif node.module:
                imports.add(node.module)
    return imports


def _absolute_module(imported: str) -> str:
    if imported.startswith("."):
        return f"synthetic.{imported.lstrip('.')}"
    return imported


def test_adapter_imports_only_stdlib_and_narrow_synthetic_contracts() -> None:
    """Catches the candidate reaching visible generation or evaluator dependencies."""
    imports = _imports(ADAPTER)

    for imported in imports:
        absolute = _absolute_module(imported)
        root = absolute.split(".", maxsplit=1)[0]
        assert (
            absolute in ADAPTER_ALLOWED_PROJECT_IMPORTS
            or root in sys.stdlib_module_names
            or absolute == "__future__"
        ), absolute


def test_visible_and_evaluator_modules_do_not_import_candidate_adapter() -> None:
    """Catches accidental production, native, governed, privacy, or Synthea wiring."""
    for path in sorted(SYNTHETIC_ROOT.rglob("*.py")):
        if path == ADAPTER:
            continue
        imports = {_absolute_module(imported) for imported in _imports(path)}
        assert not any(
            imported == "synthetic.augmenter_oracle"
            or imported.startswith("synthetic.augmenter_oracle.")
            for imported in imports
        ), path.relative_to(ROOT)


def test_production_cli_failure_text_remains_fixed() -> None:
    """Catches the development candidate weakening the fail-closed CLI contract."""
    tree = ast.parse(PRODUCTION_CLI.read_text(encoding="utf-8"), filename=str(PRODUCTION_CLI))
    strings = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert PRODUCTION_FAILURE in strings
