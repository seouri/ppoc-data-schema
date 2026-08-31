from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            if node.module == "synthetic":
                names.update(f"synthetic.{alias.name}" for alias in node.names)
    return names


def _module_path(module: str) -> Path | None:
    if not module.startswith("synthetic."):
        return None
    candidate = ROOT / "src" / Path(*module.split("."))
    source = candidate.with_suffix(".py")
    return source if source.is_file() else None


def _transitive_imports(paths: tuple[Path, ...]) -> set[str]:
    pending = list(paths)
    visited: set[Path] = set()
    imported: set[str] = set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        direct = _imports(path)
        imported.update(direct)
        pending.extend(candidate for name in direct if (candidate := _module_path(name)) is not None)
    return imported


def test_visible_generator_interfaces_do_not_import_governed_privacy_inputs() -> None:
    """Catches privacy-audit imports crossing into visible generation and package APIs."""
    visible_modules = (
        "generate.py", "csv_package.py", "manifest.py", "derivation.py", "native/trajectories.py",
    )
    forbidden = {"synthetic.privacy_audit", "synthetic.calibration_input"}

    imported = _transitive_imports(
        tuple(ROOT / "src" / "synthetic" / module for module in visible_modules)
    )

    assert not imported & forbidden
