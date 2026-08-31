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
    return names


def test_visible_generator_interfaces_do_not_import_governed_privacy_inputs() -> None:
    """Catches privacy-audit imports crossing into visible generation and package APIs."""
    visible_modules = (
        "generate.py", "csv_package.py", "manifest.py", "derivation.py", "native/trajectories.py",
    )
    forbidden = {"synthetic.privacy_audit", "synthetic.calibration_input"}

    imported = set().union(*(_imports(ROOT / "src" / "synthetic" / module) for module in visible_modules))

    assert not imported & forbidden
