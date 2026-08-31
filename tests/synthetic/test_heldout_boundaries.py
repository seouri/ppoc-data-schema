from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "synthetic-generator.md"
README = ROOT / "README.md"
FORBIDDEN_MODULES = {
    "synthetic.heldout_validate",
    "synthetic.calibrate",
    "synthetic.calibration_input",
}
FORBIDDEN_ARGUMENTS = {"real_root", "data_root", "partition_key", "heldout_report"}


def _visible_modules() -> tuple[Path, ...]:
    return (
        ROOT / "src" / "synthetic" / "generate.py",
        ROOT / "src" / "synthetic" / "manifest.py",
        ROOT / "src" / "synthetic" / "derivation.py",
        *sorted((ROOT / "src" / "synthetic" / "native").glob("*.py")),
    )


def _forbidden_imports(tree: ast.AST) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
    return imports & FORBIDDEN_MODULES


def _forbidden_arguments(tree: ast.AST) -> set[str]:
    return {
        node.arg
        for node in ast.walk(tree)
        if isinstance(node, ast.arg) and node.arg in FORBIDDEN_ARGUMENTS
    }


def test_visible_generator_paths_do_not_consume_governed_validation_inputs() -> None:
    for path in _visible_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assert _forbidden_imports(tree) == set(), path
        assert _forbidden_arguments(tree) == set(), path


def test_heldout_documentation_declares_explicit_governed_gate() -> None:
    guide = GUIDE.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")

    assert "## Patient-disjoint held-out validation" in guide
    assert "uv run python -m synthetic.heldout_validate" in guide
    for flag in (
        "--real-root",
        "--descriptor",
        "--snapshot",
        "--synthetic-root",
        "--calibration-artifact",
        "--calibration-report",
        "--partition-policy",
        "--disclosure-policy",
        "--partition-key-file",
        "--frozen-policy",
        "--output",
    ):
        assert flag in guide
    assert "PASS" in guide
    assert "FAIL" in guide
    assert "UNEVALUABLE" in guide
    assert "synthetic-only" in guide
    assert "no real data in CI" in guide
    for deferred_gate in ("privacy", "temporal drift", "task utility", "prevalence", "Synthea"):
        assert deferred_gate in guide
    assert "Patient-disjoint held-out validation" in readme
