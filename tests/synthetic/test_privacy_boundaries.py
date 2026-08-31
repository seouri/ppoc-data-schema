from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_VISIBLE_GENERATOR_MODULES = (
    "__init__.py",
    "generate.py",
    "csv_package.py",
    "manifest.py",
    "derivation.py",
    "native/__init__.py",
    "native/trajectories.py",
)


def _module_context(path: Path) -> tuple[str, bool]:
    relative = path.relative_to(ROOT / "src").with_suffix("")
    parts = list(relative.parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts.pop()
    return ".".join(parts), is_package


def _import_from_base(
    node: ast.ImportFrom,
    module: str,
    *,
    is_package: bool,
) -> str | None:
    if node.level == 0:
        return node.module
    package = module.split(".") if is_package else module.split(".")[:-1]
    climb = node.level - 1
    if climb > len(package):
        return None
    parts = package[: len(package) - climb]
    if node.module is not None:
        parts.extend(node.module.split("."))
    return ".".join(parts)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    module, is_package = _module_context(path)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _import_from_base(node, module, is_package=is_package)
            if base:
                names.add(base)
                names.update(f"{base}.{alias.name}" for alias in node.names)
    return names


def _module_path(module: str) -> Path | None:
    if not module.startswith("synthetic."):
        return None
    candidate = ROOT / "src" / Path(*module.split("."))
    source = candidate.with_suffix(".py")
    if source.is_file():
        return source
    package = candidate / "__init__.py"
    return package if package.is_file() else None


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


def _visible_generator_imports() -> set[str]:
    return _transitive_imports(
        tuple(ROOT / "src" / "synthetic" / module for module in _VISIBLE_GENERATOR_MODULES)
    )


@pytest.mark.parametrize(
    ("relative_path", "source", "forbidden"),
    [
        (
            "src/synthetic/__init__.py",
            "from . import privacy_audit\n",
            "synthetic.privacy_audit",
        ),
        (
            "src/synthetic/generate.py",
            "from .calibration_input import prepare_synthetic_input\n",
            "synthetic.calibration_input",
        ),
    ],
)
def test_import_scanner_qualifies_relative_forbidden_imports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative_path: str,
    source: str,
    forbidden: str,
) -> None:
    """Catches relative imports bypassing the fully qualified forbidden set."""
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)

    assert forbidden in _imports(path)


def test_visible_generator_interfaces_do_not_import_governed_privacy_inputs() -> None:
    """Catches privacy-audit imports crossing into visible generation and package APIs."""
    forbidden = {"synthetic.privacy_audit", "synthetic.calibration_input"}

    imported = _visible_generator_imports()

    assert not imported & forbidden


@pytest.mark.parametrize(
    ("initializer", "source"),
    [
        ("src/synthetic/__init__.py", "from . import privacy_audit\n"),
        ("src/synthetic/native/__init__.py", "from .. import privacy_audit\n"),
    ],
)
def test_visible_generator_scan_includes_implicitly_executed_package_initializers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    initializer: str,
    source: str,
) -> None:
    """Catches the real boundary roots omitting an implicitly executed package initializer."""
    for module in _VISIBLE_GENERATOR_MODULES:
        path = tmp_path / "src" / "synthetic" / module
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    initializer_path = tmp_path / initializer
    initializer_path.parent.mkdir(parents=True, exist_ok=True)
    initializer_path.write_text(source, encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)

    assert "synthetic.privacy_audit" in _visible_generator_imports()
