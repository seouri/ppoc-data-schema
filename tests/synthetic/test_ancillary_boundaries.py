from __future__ import annotations

import ast
import inspect
from pathlib import Path

from synthetic.native import ancillary

_ALLOWED_REPOSITORY_SYMBOLS = {
    "synthetic.cohort": frozenset({"CohortMember"}),
    "synthetic.models": frozenset(
        {"AgeRegimeDisorderTrajectory", "ClinicalEvent", "DisorderKind"}
    ),
    "synthetic.native.observations": frozenset(
        {"ObservationValidationStatus", "RecordedEvent", "RecordedEventKind", "validate_observation_frame"}
    ),
    "synthetic.native.resources": frozenset({"ResourceRow", "ResourceShape"}),
}


def _dotted_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None


def _unsafe_dependency_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.lower())
                aliases[alias.asname or alias.name.split(".")[0]] = alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                names.add("relative-import")
            module = (node.module or "").lower()
            names.add(module)
            for alias in node.names:
                origin = f"{module}.{alias.name}".strip(".")
                names.add(origin)
                aliases[alias.asname or alias.name] = origin
        elif isinstance(node, ast.Call):
            name = _dotted_name(node.func)
            if name:
                root, *suffix = name.split(".")
                names.add(".".join((aliases.get(root, root), *suffix)).lower())
    forbidden = {
        "calibration", "csv", "duckdb", "export", "filesystem", "heldout", "manifest",
        "glob", "open", "os", "package", "pathlib", "privacy",
        "random", "shutil", "subprocess", "synthea", "sys", "tempfile",
    }
    return {
        name for name in names
        if forbidden.intersection(name.replace("_", ".").split("."))
        or name == "relative-import"
        or name.startswith("synthetic") and not _allowed_repository_name(name)
    }


def _allowed_repository_name(name: str) -> bool:
    name = name.lower()
    for module, symbols in _ALLOWED_REPOSITORY_SYMBOLS.items():
        if name == module:
            return True
        if name.startswith(f"{module}."):
            return (
                name.removeprefix(f"{module}.").split(".")[0]
                in {symbol.lower() for symbol in symbols}
            )
    return False


def _repository_imports(source: str) -> set[str]:
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names if alias.name.startswith("synthetic."))
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("synthetic"):
            imports.add(node.module)
    return imports


def test_ancillary_module_has_only_native_safe_imports_and_no_lifecycle_calls() -> None:
    source = Path(ancillary.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            calls.add(node.func.id.lower())
    assert not _unsafe_dependency_names(source)
    assert _repository_imports(source) <= set(_ALLOWED_REPOSITORY_SYMBOLS)
    assert not calls.intersection({"open", "print", "exit", "quit", "seed", "randint", "write"})


def test_dependency_scanner_rejects_qualified_and_imported_forbidden_dependencies() -> None:
    for source in (
        "import synthetic.package_export",
        "from synthetic import calibration",
        "from synthetic import calibrate",
        "import synthetic.derivation",
        "import synthetic.run_directory",
        "from synthetic.heldout import compare",
        "import synthetic.privacy",
        "from duckdb import connect",
        "from pathlib import Path",
        "import os",
        "from tempfile import NamedTemporaryFile",
        "import shutil",
        "import glob",
        "import io; io.open('x')",
        "import builtins; builtins.open('x')",
        "import csv",
        "import random",
        "import synthea",
        "synthetic.package_export.write()",
        "synthetic.derivation.run()",
        "from synthetic.derivation import run as lifecycle; lifecycle()",
        "import synthetic.derivation as lifecycle; lifecycle.run()",
        "from builtins import open as reader; reader('x')",
        "from . import calibrate",
        "from ..derivation import run as lifecycle; lifecycle()",
        "from synthetic.cohort import generate_native_cohort; generate_native_cohort(None)",
        "from synthetic.native.resources import project_observed_resources as lifecycle; lifecycle(None, None)",
        "import synthetic.native.resources as lifecycle; lifecycle.project_observed_resources(None, None)",
    ):
        assert _unsafe_dependency_names(source)


def test_dependency_scanner_allows_only_the_named_repository_symbols() -> None:
    safe = (
        "from synthetic.cohort import CohortMember",
        "from synthetic.models import AgeRegimeDisorderTrajectory, ClinicalEvent, DisorderKind",
        "from synthetic.native.observations import ObservationValidationStatus, RecordedEvent, RecordedEventKind, validate_observation_frame",
        "from synthetic.native.resources import ResourceRow, ResourceShape",
    )
    for source in safe:
        assert not _unsafe_dependency_names(source)


def test_public_ancillary_interfaces_do_not_accept_paths_rows_or_outputs() -> None:
    for function, expected in (
        (ancillary.project_ghd_ancillary_resources, ("member", "shape", "policy")),
        (ancillary.validate_ghd_ancillary_resources, ("member", "projection", "policy")),
    ):
        names = tuple(inspect.signature(function).parameters)
        assert names == expected
        assert not set(names).intersection({"path", "descriptor_path", "rows", "row", "output", "destination", "report", "key"})
