from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_ROOT = ROOT / "src" / "synthetic"
ADAPTER = SYNTHETIC_ROOT / "augmenter_oracle.py"
EXPLICIT_DEVELOPMENT_COMPOSITION = SYNTHETIC_ROOT / "development_runtime.py"
ALLOWED_ADAPTER_IMPORTERS = frozenset({
    SYNTHETIC_ROOT / "cdc_reference.py",
    EXPLICIT_DEVELOPMENT_COMPOSITION,
})
PRODUCTION_CLI = SYNTHETIC_ROOT / "generate.py"
ADAPTER_ALLOWED_PROJECT_IMPORTS = {
    "synthetic.derivation",
    "synthetic.schema_contract",
}
PRODUCTION_FAILURE = (
    "No production growth reference or authoritative derivation oracle is configured"
)
_DEVELOPMENT_RUNTIME_FORBIDDEN_IMPORT_PREFIXES = (
    "synthetic.calibrate",
    "synthetic.calibration",
    "synthetic.calibration_disclosure",
    "synthetic.calibration_input",
    "synthetic.heldout_validate",
    "synthetic.privacy_audit",
    "synthetic.real_data",
    "synthetic.realdata",
    "synthetic.synthea",
)
_NETWORK_OR_PROCESS_IMPORTS = {
    "asyncio.subprocess",
    "http",
    "http.client",
    "requests",
    "socket",
    "subprocess",
    "urllib",
    "webbrowser",
}
_DEVELOPMENT_RUNTIME_FORBIDDEN_ARGUMENTS = {
    "calibration_path",
    "data_root",
    "heldout_report",
    "privacy_policy",
    "privacy_report",
    "real_data_root",
    "real_root",
    "synthea_input",
}
_DEVELOPMENT_RUNTIME_ALLOWED_READS = {
    "synthetic.augmenter_oracle.verify_source_matched_runtime",
    "synthetic.cdc_reference.CdcGrowthReference.from_repository",
    "synthetic.schema_contract.load_descriptor",
}
_DEVELOPMENT_RUNTIME_ALLOWED_PACKAGE_CALLS = {
    "synthetic.package_export._require_output_available",
    "synthetic.package_export.export_exact_schema_package",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = "." * node.level + (node.module or "")
            elif node.module:
                base = node.module
            else:
                continue
            imports.add(base)
            separator = "" if base.endswith(".") else "."
            imports.update(f"{base}{separator}{alias.name}" for alias in node.names)
    return imports


def _absolute_module(imported: str) -> str:
    if imported.startswith("."):
        suffix = imported.lstrip(".")
        return f"synthetic.{suffix}" if suffix else "synthetic"
    return imported


def test_adapter_imports_only_stdlib_and_narrow_synthetic_contracts() -> None:
    """Catches the candidate reaching visible generation or evaluator dependencies."""
    imports = _imports(ADAPTER)

    for imported in imports:
        absolute = _absolute_module(imported)
        root = absolute.split(".", maxsplit=1)[0]
        assert (
            any(
                absolute == allowed or absolute.startswith(f"{allowed}.")
                for allowed in ADAPTER_ALLOWED_PROJECT_IMPORTS
            )
            or root in sys.stdlib_module_names
            or absolute == "__future__"
        ), absolute


def test_visible_and_evaluator_modules_do_not_import_candidate_adapter() -> None:
    """Catches accidental production, native, governed, privacy, or Synthea wiring."""
    for path in sorted(SYNTHETIC_ROOT.rglob("*.py")):
        if path == ADAPTER or path in ALLOWED_ADAPTER_IMPORTERS:
            continue
        imports = {_absolute_module(imported) for imported in _imports(path)}
        assert not any(
            imported == "synthetic.augmenter_oracle"
            or imported.startswith("synthetic.augmenter_oracle.")
            for imported in imports
        ), path.relative_to(ROOT)


def test_only_declared_explicit_composition_modules_import_candidate_adapter() -> None:
    """Catches a new route composing the candidate without an explicit review boundary."""
    assert ALLOWED_ADAPTER_IMPORTERS == frozenset(
        {
            SYNTHETIC_ROOT / "cdc_reference.py",
            EXPLICIT_DEVELOPMENT_COMPOSITION,
        }
    )
    for path in ALLOWED_ADAPTER_IMPORTERS:
        imports = {_absolute_module(imported) for imported in _imports(path)}
        assert any(
            imported == "synthetic.augmenter_oracle"
            or imported.startswith("synthetic.augmenter_oracle.")
            for imported in imports
        ), path.relative_to(ROOT)


def test_explicit_runtime_has_only_development_safe_input_and_lifecycle_seams() -> None:
    """Catches the development route gaining governed inputs or its own process escape."""
    tree = ast.parse(
        EXPLICIT_DEVELOPMENT_COMPOSITION.read_text(encoding="utf-8"),
        filename=str(EXPLICIT_DEVELOPMENT_COMPOSITION),
    )
    imports = {
        _absolute_module(imported)
        for imported in _imports(EXPLICIT_DEVELOPMENT_COMPOSITION)
    }
    arguments = {node.arg for node in ast.walk(tree) if isinstance(node, ast.arg)}
    calls = _qualified_calls(tree)

    assert not any(
        imported == forbidden or imported.startswith(f"{forbidden}.")
        for imported in imports
        for forbidden in _DEVELOPMENT_RUNTIME_FORBIDDEN_IMPORT_PREFIXES
    )
    assert imports.isdisjoint(_NETWORK_OR_PROCESS_IMPORTS)
    assert arguments.isdisjoint(_DEVELOPMENT_RUNTIME_FORBIDDEN_ARGUMENTS)
    assert _DEVELOPMENT_RUNTIME_ALLOWED_READS <= calls
    assert _DEVELOPMENT_RUNTIME_ALLOWED_PACKAGE_CALLS <= calls
    assert not {
        "open",
        "read_bytes",
        "read_text",
        "subprocess.run",
        "subprocess.Popen",
        "os.system",
    } & calls


def test_cli_exposes_no_governed_or_model_options() -> None:
    """Catches the explicit profiles accepting real, governed, or model inputs."""
    source = PRODUCTION_CLI.read_text(encoding="utf-8")

    for forbidden in (
        "--real-root",
        "--calibration",
        "--heldout",
        "--privacy",
        "--synthea",
        "--model",
    ):
        assert forbidden not in source


@pytest.mark.parametrize(
    "source",
    (
        "import synthetic.augmenter_oracle",
        "import synthetic.augmenter_oracle as candidate",
        "from synthetic import augmenter_oracle",
        "from synthetic import augmenter_oracle as candidate",
        "from . import augmenter_oracle",
        "from . import augmenter_oracle as candidate",
    ),
)
def test_import_scanner_records_alias_qualified_candidate_imports(
    tmp_path: Path,
    source: str,
) -> None:
    """Catches import-from aliases disappearing from the visible-module scan."""
    module = tmp_path / "visible.py"
    module.write_text(source, encoding="utf-8")

    imports = {_absolute_module(imported) for imported in _imports(module)}

    assert "synthetic.augmenter_oracle" in imports


def test_production_cli_failure_text_remains_fixed() -> None:
    """Catches the development candidate weakening the fail-closed CLI contract."""
    tree = ast.parse(PRODUCTION_CLI.read_text(encoding="utf-8"), filename=str(PRODUCTION_CLI))
    strings = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert PRODUCTION_FAILURE in strings


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    return None


def _qualified_calls(tree: ast.AST) -> set[str]:
    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bindings[alias.asname or alias.name.split(".", maxsplit=1)[0]] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            base = _absolute_module("." * node.level + node.module)
            for alias in node.names:
                bindings[alias.asname or alias.name] = f"{base}.{alias.name}"

    calls: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)
        if name is None:
            continue
        root, dot, suffix = name.partition(".")
        calls.add(f"{bindings.get(root, root)}{dot}{suffix}")
    return calls
