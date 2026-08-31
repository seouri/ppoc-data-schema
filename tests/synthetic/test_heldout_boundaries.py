from __future__ import annotations

import ast
from pathlib import Path

import pytest

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
        *sorted((ROOT / "src" / "synthetic" / "native").rglob("*.py")),
    )


def _module_name(path: Path) -> str:
    return ".".join(path.relative_to(ROOT / "src").with_suffix("").parts)


def _import_from_base(node: ast.ImportFrom, module_name: str) -> str | None:
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


def _forbidden_imports(tree: ast.AST, module_name: str) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _import_from_base(node, module_name)
            if base is not None:
                imports.add(base)
                if base == "synthetic":
                    imports.update(f"{base}.{alias.name}" for alias in node.names)
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
        assert _forbidden_imports(tree, _module_name(path)) == set(), path
        assert _forbidden_arguments(tree) == set(), path


@pytest.mark.parametrize(
    ("source", "module_name", "expected"),
    [
        (
            "from synthetic import calibration_input",
            "synthetic.generate",
            {"synthetic.calibration_input"},
        ),
        ("from . import heldout_validate", "synthetic.generate", {"synthetic.heldout_validate"}),
        ("from .. import calibrate", "synthetic.native.healthy", {"synthetic.calibrate"}),
        (
            "from ..calibration_input import prepare_input",
            "synthetic.native.healthy",
            {"synthetic.calibration_input"},
        ),
    ],
)
def test_forbidden_imports_detect_package_exports_and_relative_forms(
    source: str, module_name: str, expected: set[str]
) -> None:
    assert _forbidden_imports(ast.parse(source), module_name) == expected


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
    assert "synthetic.heldout_validate" in readme
    assert "no default data root" in readme
    assert "fictional synthetic packages" in readme
    assert "PASS" in readme
    assert "FAIL" in readme
    assert "UNEVALUABLE" in readme
    for deferred_gate in ("privacy", "temporal drift", "task utility", "prevalence", "Synthea"):
        assert deferred_gate in readme
