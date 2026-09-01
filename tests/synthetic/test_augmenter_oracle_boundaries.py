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
_NETWORK_OR_PROCESS_IMPORT_PREFIXES = {
    "asyncio",
    "ftplib",
    "http",
    "http.client",
    "importlib",
    "multiprocessing",
    "requests",
    "smtplib",
    "socket",
    "subprocess",
    "telnetlib",
    "urllib",
    "webbrowser",
    "xmlrpc",
}
_PROCESS_CALL_PREFIXES = (
    "asyncio.create_subprocess",
    "os.exec",
    "os.popen",
    "os.spawn",
    "os.system",
    "subprocess",
)
_DYNAMIC_IMPORT_CALLS = {"__import__", "importlib.import_module"}
_DIRECT_FILE_CALL_LEAVES = {
    "mkdir",
    "open",
    "read_bytes",
    "read_text",
    "rename",
    "replace",
    "rmdir",
    "unlink",
    "write_bytes",
    "write_text",
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
_GOVERNED_CLI_OPTION_PREFIXES = (
    "--real-root",
    "--calibration",
    "--heldout",
    "--privacy",
    "--synthea",
)
_MODEL_OR_DIAGNOSIS_OPTION_COMPONENTS = {
    "diagnosis",
    "dx",
    "llm",
    "model",
    "payload",
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
    assert not _prefixed_matches(imports, _NETWORK_OR_PROCESS_IMPORT_PREFIXES)
    assert arguments.isdisjoint(_DEVELOPMENT_RUNTIME_FORBIDDEN_ARGUMENTS)
    assert _DEVELOPMENT_RUNTIME_ALLOWED_READS <= calls
    assert _DEVELOPMENT_RUNTIME_ALLOWED_PACKAGE_CALLS <= calls
    assert not _direct_file_calls(calls)
    assert not _forbidden_process_calls(calls)
    assert not _DYNAMIC_IMPORT_CALLS & calls


def test_cli_exposes_no_governed_or_model_options() -> None:
    """Catches the explicit profiles accepting real, governed, or model inputs."""
    options = _cli_options(PRODUCTION_CLI.read_text(encoding="utf-8"))

    assert not _forbidden_cli_options(options)


def test_runtime_boundary_scanner_detects_network_submodule_import() -> None:
    """Catches a network import hidden below a forbidden module root."""
    imports = _imports_from_tree(ast.parse("import urllib.request"))

    assert _prefixed_matches(imports, _NETWORK_OR_PROCESS_IMPORT_PREFIXES) == {
        "urllib.request"
    }


def test_runtime_boundary_scanner_detects_os_process_escape() -> None:
    """Catches process creation through a standard-library module alias."""
    calls = _qualified_calls(ast.parse("import os\nos.popen('ignored')"))

    assert _forbidden_process_calls(calls) == {"os.popen"}


def test_runtime_boundary_scanner_detects_direct_file_read() -> None:
    """Catches a composition-layer path read outside the declared adapters."""
    calls = _qualified_calls(ast.parse("from pathlib import Path\nPath('ignored').read_text()"))

    assert _direct_file_calls(calls) == {"pathlib.Path.read_text"}


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        ("parser.add_argument('--diagnosis-model')", {"--diagnosis-model"}),
        ("parser.add_argument('--llm')", {"--llm"}),
    ),
)
def test_cli_option_scanner_detects_model_and_diagnosis_payload_options(
    source: str,
    expected: set[str],
) -> None:
    """Catches model or diagnosis payload options that evade exact-string checks."""
    assert _forbidden_cli_options(_cli_options(source)) == expected


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


def _imports_from_tree(tree: ast.AST) -> set[str]:
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


def _prefixed_matches(names: set[str], prefixes: set[str] | tuple[str, ...]) -> set[str]:
    return {
        name
        for name in names
        if any(name == prefix or name.startswith(f"{prefix}.") for prefix in prefixes)
    }


def _forbidden_process_calls(calls: set[str]) -> set[str]:
    return _prefixed_matches(calls, _PROCESS_CALL_PREFIXES)


def _direct_file_calls(calls: set[str]) -> set[str]:
    return {
        name
        for name in calls
        if name.rsplit(".", maxsplit=1)[-1] in _DIRECT_FILE_CALL_LEAVES
    }


def _cli_options(source: str) -> set[str]:
    tree = ast.parse(source)
    return {
        argument.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_argument"
        for argument in node.args
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
    }


def _forbidden_cli_options(options: set[str]) -> set[str]:
    return {
        option
        for option in options
        if any(
            option == prefix or option.startswith(f"{prefix}-")
            for prefix in _GOVERNED_CLI_OPTION_PREFIXES
        )
        or bool(
            _MODEL_OR_DIAGNOSIS_OPTION_COMPONENTS
            & set(option.removeprefix("--").lower().replace("_", "-").split("-"))
        )
    }


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
