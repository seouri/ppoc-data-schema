from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest

from synthetic import generate
from synthetic.generate import generate_smoke
from synthetic.package_export import (
    export_counterfactual_ehr_world_pair,
    export_exact_schema_package,
    export_observed_resource_package,
)

ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC = ROOT / "src" / "synthetic"
BOUND_SOURCES = (
    SYNTHETIC / "derivation_binding.py",
    SYNTHETIC / "generate.py",
    SYNTHETIC / "package_export.py",
)
FORBIDDEN_MODULES = {
    "synthetic.calibration",
    "synthetic.heldout_validate",
    "synthetic.privacy_audit",
    "synthetic.native.trajectory",
    "synthetic.temporal_drift",
    "synthetic.prevalence_evidence",
    "synthea",
}
FORBIDDEN_ROUTE_CALL_SUFFIXES = {
    "audit_privacy",
    "calibrate",
    "generate_native_cohort",
    "load_calibration_artifact",
    "load_heldout",
    "load_privacy_policy",
    "validate_heldout",
    "validate_temporal_drift",
    "write_prevalence_evidence",
}
FORBIDDEN_EXTERNAL_PROCESS_CALLS = {
    "asyncio.create_subprocess_exec",
    "asyncio.create_subprocess_shell",
    "os.popen",
    "os.system",
    "subprocess.Popen",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "subprocess.getoutput",
    "subprocess.getstatusoutput",
    "subprocess.run",
}


def _module_context(path: Path) -> tuple[str, bool]:
    parts = list(path.relative_to(ROOT / "src").with_suffix("").parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts.pop()
    return ".".join(parts), is_package


def _import_base(
    node: ast.ImportFrom, module_name: str, *, is_package: bool
) -> str | None:
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


def _bindings(
    tree: ast.AST, module_name: str, *, is_package: bool
) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bindings[alias.asname or alias.name.split(".", maxsplit=1)[0]] = alias.name
        elif isinstance(node, ast.ImportFrom):
            base = _import_base(node, module_name, is_package=is_package)
            if base is not None:
                for alias in node.names:
                    bindings[alias.asname or alias.name] = f"{base}.{alias.name}"
    return bindings


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _qualified_calls(
    tree: ast.AST, module_name: str, *, is_package: bool
) -> set[str]:
    bindings = _bindings(tree, module_name, is_package=is_package)
    calls: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or (name := _call_name(node.func)) is None:
            continue
        root, dot, suffix = name.partition(".")
        qualified_name = f"{bindings.get(root, root)}{dot}{suffix}"
        if qualified_name.startswith("asyncio.subprocess.create_subprocess_"):
            qualified_name = qualified_name.replace("asyncio.subprocess.", "asyncio.", 1)
        calls.add(qualified_name)
    return calls


def _dynamic_imports(
    tree: ast.AST, module_name: str, *, is_package: bool
) -> set[str]:
    bindings = _bindings(tree, module_name, is_package=is_package)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)
        if name is None:
            continue
        root, dot, suffix = name.partition(".")
        qualified_name = f"{bindings.get(root, root)}{dot}{suffix}"
        if qualified_name not in {"__import__", "importlib.import_module"}:
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


def _imports(
    tree: ast.AST, module_name: str, *, is_package: bool
) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _import_base(node, module_name, is_package=is_package)
            if base is not None:
                imports.add(base)
                imports.update(f"{base}.{alias.name}" for alias in node.names)
    return imports | _dynamic_imports(tree, module_name, is_package=is_package)


def _forbidden_imports(imports: set[str]) -> set[str]:
    return {
        imported
        for imported in imports
        if any(imported == module or imported.startswith(f"{module}.") for module in FORBIDDEN_MODULES)
    }


def _forbidden_route_calls(
    tree: ast.AST, module_name: str, *, is_package: bool
) -> set[str]:
    return {
        call
        for call in _qualified_calls(tree, module_name, is_package=is_package)
        if call.rsplit(".", maxsplit=1)[-1] in FORBIDDEN_ROUTE_CALL_SUFFIXES
    }


def _external_process_calls(
    tree: ast.AST, module_name: str, *, is_package: bool
) -> set[str]:
    return _qualified_calls(tree, module_name, is_package=is_package) & FORBIDDEN_EXTERNAL_PROCESS_CALLS


def test_production_cli_remains_fail_closed_without_an_approved_oracle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Breaks if the production CLI gains an unreviewed route past oracle approval."""
    monkeypatch.setattr(sys, "argv", ["synthetic.generate", "--output", "fictional", "--patients", "1", "--seed", "1"])

    with pytest.raises(SystemExit) as error:
        generate.main()

    assert str(error.value) == (
        "No production growth reference or authoritative derivation oracle is configured"
    )


def test_public_export_and_generator_signatures_require_an_explicit_binding() -> None:
    """Breaks if a public export route can bypass a supplied derivation binding."""
    for callable_ in (
        generate_smoke,
        export_exact_schema_package,
        export_observed_resource_package,
        export_counterfactual_ehr_world_pair,
    ):
        parameter = inspect.signature(callable_).parameters["derivation_binding"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is inspect.Parameter.empty


def test_binding_handoff_sources_do_not_import_or_execute_governed_or_external_routes() -> None:
    """Breaks if automatic calibration, evaluator, Synthea, or harness execution is added."""
    for path in BOUND_SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        module_name, is_package = _module_context(path)
        assert not _forbidden_imports(
            _imports(tree, module_name, is_package=is_package)
        ), path
        assert not _forbidden_route_calls(tree, module_name, is_package=is_package), path
        assert not _external_process_calls(tree, module_name, is_package=is_package), path


def test_boundary_scanner_rejects_relative_dynamic_and_external_route_evasions() -> None:
    """Breaks if an import alias or process helper can evade the source boundary scan."""
    cases = (
        (
            "from . import calibration",
            "synthetic.generate",
            False,
            "synthetic.calibration",
        ),
        (
            "from . import trajectory",
            "synthetic.native.resources",
            False,
            "synthetic.native.trajectory",
        ),
        (
            "import importlib as loader\nloader.import_module('synthetic.privacy_audit')",
            "synthetic.generate",
            False,
            "synthetic.privacy_audit",
        ),
        (
            "from importlib import import_module as load\nload('synthetic.prevalence_evidence')",
            "synthetic.generate",
            False,
            "synthetic.prevalence_evidence",
        ),
        (
            "import importlib as loader\nloader.import_module(name='synthetic.calibration')",
            "synthetic.generate",
            False,
            "synthetic.calibration",
        ),
        ("__import__('synthea')", "synthetic.generate", False, "synthea"),
        ("__import__(name='synthea')", "synthetic.generate", False, "synthea"),
    )
    for source, module_name, is_package, forbidden_module in cases:
        tree = ast.parse(source)
        assert _forbidden_imports(
            _imports(tree, module_name, is_package=is_package)
        ) == {forbidden_module}

    external_cases = (
        (
            "from asyncio import subprocess as a\na.create_subprocess_exec('fictional')",
            "asyncio.create_subprocess_exec",
        ),
        (
            "import asyncio\nasyncio.create_subprocess_shell('fictional')",
            "asyncio.create_subprocess_shell",
        ),
        ("import os\nos.popen('fictional')", "os.popen"),
        ("import os\nos.system('fictional')", "os.system"),
        ("import subprocess\nsubprocess.Popen(['fictional'])", "subprocess.Popen"),
        ("import subprocess\nsubprocess.run(['fictional'])", "subprocess.run"),
        ("import subprocess\nsubprocess.call(['fictional'])", "subprocess.call"),
        (
            "import subprocess\nsubprocess.check_call(['fictional'])",
            "subprocess.check_call",
        ),
        (
            "import subprocess as process\nprocess.check_output(['fictional'])",
            "subprocess.check_output",
        ),
        ("import subprocess\nsubprocess.getoutput('fictional')", "subprocess.getoutput"),
        (
            "import subprocess\nsubprocess.getstatusoutput('fictional')",
            "subprocess.getstatusoutput",
        ),
        (
            "from subprocess import Popen as launch\nlaunch(['fictional'])",
            "subprocess.Popen",
        ),
    )
    detected_calls: set[str] = set()
    for source, expected_call in external_cases:
        tree = ast.parse(source)
        calls = _external_process_calls(
            tree,
            "synthetic.generate",
            is_package=False,
        )
        assert expected_call in calls
        detected_calls.update(calls)
    assert detected_calls == FORBIDDEN_EXTERNAL_PROCESS_CALLS
