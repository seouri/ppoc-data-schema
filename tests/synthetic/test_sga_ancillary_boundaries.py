from __future__ import annotations

import ast
import inspect
from pathlib import Path

from synthetic.native import sga_ancillary

_ALLOWED = {
    "synthetic.cohort": frozenset({"CohortMember"}),
    "synthetic.models": frozenset({"MAX_AGE_DAYS", "AgeRegimeDisorderTrajectory", "DisorderKind"}),
    "synthetic.native.observations": frozenset({"ObservationValidationStatus", "RecordedEvent", "RecordedEventKind", "validate_observation_frame"}),
    "synthetic.native.resources": frozenset({"ResourceRow", "ResourceShape"}),
}
_ALLOWED_DIRECT_IMPORTS = frozenset({"hashlib", "re"})
_ALLOWED_FROM_IMPORTS = {
    "__future__": frozenset({"annotations"}),
    "collections.abc": frozenset({"Mapping"}),
    "dataclasses": frozenset({"dataclass", "field"}),
    "enum": frozenset({"Enum"}),
    "types": frozenset({"MappingProxyType"}),
    "typing": frozenset({"ClassVar"}),
    **_ALLOWED,
}
_FORBIDDEN_CALL_ROOTS = frozenset(
    {
        "argparse",
        "builtins",
        "click",
        "csv",
        "dotenv",
        "duckdb",
        "http",
        "httpx",
        "os",
        "pandas",
        "pathlib",
        "polars",
        "requests",
        "socket",
        "subprocess",
        "sys",
        "typer",
        "urllib",
    }
)
_FORBIDDEN_BARE_CALLS = frozenset(
    {"__import__", "compile", "eval", "exec", "exit", "input", "open", "print", "quit"}
)


def _dotted_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    if isinstance(node, ast.Call):
        return _dotted_name(node.func)
    return None


def _import_violations(tree: ast.AST) -> set[str]:
    violations: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in _ALLOWED_DIRECT_IMPORTS:
                    violations.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                violations.add(f"{'.' * node.level}{node.module or ''}")
                continue
            allowed_symbols = _ALLOWED_FROM_IMPORTS.get(node.module or "")
            for alias in node.names:
                if allowed_symbols is None or alias.name not in allowed_symbols:
                    violations.add(f"{node.module}.{alias.name}")
    return violations


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".")[0]] = alias.name
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return aliases


def _qualified_call_name(node: ast.expr, aliases: dict[str, str]) -> str | None:
    name = _dotted_name(node)
    if name is None:
        return None
    root, *suffix = name.split(".")
    return ".".join((aliases.get(root, root), *suffix))


def _forbidden_calls(tree: ast.AST) -> set[str]:
    aliases = _import_aliases(tree)
    forbidden: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _qualified_call_name(node.func, aliases)
        if name is None:
            continue
        root = name.split(".", maxsplit=1)[0]
        if name in _FORBIDDEN_BARE_CALLS or root in _FORBIDDEN_CALL_ROOTS:
            forbidden.add(name)
    return forbidden


def test_module_is_native_only_and_has_no_io_randomness_or_obesity_leakage() -> None:
    source = Path(sga_ancillary.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert _import_violations(tree) == set()
    assert _forbidden_calls(tree) == set()
    assert "obesity_flag" not in source
    assert "package_export" not in source


def test_dependency_scanner_allows_only_the_explicit_native_import_contract() -> None:
    source = """from __future__ import annotations
import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import ClassVar
from synthetic.cohort import CohortMember
from synthetic.models import MAX_AGE_DAYS, AgeRegimeDisorderTrajectory, DisorderKind
from synthetic.native.observations import ObservationValidationStatus, RecordedEvent, RecordedEventKind, validate_observation_frame
from synthetic.native.resources import ResourceRow, ResourceShape"""

    assert _import_violations(ast.parse(source)) == set()


def test_dependency_scanner_rejects_network_filesystem_environment_cli_and_third_party() -> None:
    cases = {
        "import socket as network\nnetwork.create_connection(('example.test', 443))": (
            {"socket"},
            {"socket.create_connection"},
        ),
        "from pathlib import Path\nPath('fixture').read_text()": (
            {"pathlib.Path"},
            {"pathlib.Path", "pathlib.Path.read_text"},
        ),
        "import os\nos.getenv('PPOC_DATA_ROOT')\nimport argparse\nargparse.ArgumentParser()": (
            {"argparse", "os"},
            {"argparse.ArgumentParser", "os.getenv"},
        ),
        "import pandas as pd\npd.read_csv('fixture.csv')": (
            {"pandas"},
            {"pandas.read_csv"},
        ),
        "from .resources import ResourceShape": ({".resources"}, set()),
    }

    for source, (expected_imports, expected_calls) in cases.items():
        tree = ast.parse(source)
        assert _import_violations(tree) == expected_imports
        assert _forbidden_calls(tree) == expected_calls


def test_dependency_scanner_rejects_alias_aware_forbidden_calls() -> None:
    tree = ast.parse("from builtins import open as reader\nreader('fixture')")

    assert _import_violations(tree) == {"builtins.open"}
    assert _forbidden_calls(tree) == {"builtins.open"}


def test_public_functions_have_only_typed_in_memory_parameters() -> None:
    for function, expected in ((sga_ancillary.project_sga_ancillary_resources, ("member", "shape", "policy")), (sga_ancillary.validate_sga_ancillary_resources, ("member", "projection", "policy"))):
        parameters = inspect.signature(function).parameters
        assert tuple(parameters) == expected
        assert not set(parameters).intersection({"path", "descriptor_path", "rows", "row", "output", "destination", "report", "key"})
