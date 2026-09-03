from __future__ import annotations

import ast
import inspect
from pathlib import Path

from synthetic.native import pediatric_hypothyroidism_ancillary

_ALLOWED_REPOSITORY_SYMBOLS = {
    "synthetic.cohort": frozenset({"CohortMember"}),
    "synthetic.models": frozenset(
        {
            "MAX_AGE_DAYS",
            "AgeRegimeDisorderTrajectory",
            "ClinicalEvent",
            "DisorderKind",
        }
    ),
    "synthetic.native.observations": frozenset(
        {
            "ObservationValidationStatus",
            "RecordedEvent",
            "RecordedEventKind",
            "validate_observation_frame",
        }
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


def _allowed_repository_name(name: str) -> bool:
    name = name.lower()
    return any(
        name == f"{module}.{symbol}".lower()
        for module, symbols in _ALLOWED_REPOSITORY_SYMBOLS.items()
        for symbol in symbols
    )


def _unsafe_dependency_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                origin = alias.name.lower()
                names.add(origin)
                aliases[alias.asname or alias.name.split(".")[0]] = origin
                if origin.startswith("synthetic"):
                    names.add(f"repository-module-import:{origin}")
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                names.add("relative-import")
            module = (node.module or "").lower()
            for alias in node.names:
                origin = f"{module}.{alias.name}".strip(".").lower()
                names.add(origin)
                aliases[alias.asname or alias.name] = origin
        elif isinstance(node, ast.Assign):
            origin = _dotted_name(node.value)
            if origin:
                root, *suffix = origin.split(".")
                resolved = ".".join((aliases.get(root, root), *suffix)).lower()
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        aliases[target.id] = resolved
        elif isinstance(node, ast.Call):
            name = _dotted_name(node.func)
            if name:
                root, *suffix = name.split(".")
                names.add(".".join((aliases.get(root, root), *suffix)).lower())
    forbidden = {
        "calibration",
        "csv",
        "duckdb",
        "export",
        "filesystem",
        "heldout",
        "manifest",
        "fileio",
        "glob",
        "multiprocessing",
        "open",
        "os",
        "package",
        "pathlib",
        "privacy",
        "random",
        "secrets",
        "shutil",
        "sqlalchemy",
        "sqlite3",
        "subprocess",
        "synthea",
        "sys",
        "tempfile",
        "uuid",
    }
    return {
        name
        for name in names
        if forbidden.intersection(name.replace("_", ".").split("."))
        or name == "relative-import"
        or name.startswith("repository-module-import:")
        or name.startswith("synthetic") and not _allowed_repository_name(name)
    }


def test_module_has_only_native_safe_imports_and_no_lifecycle_calls() -> None:
    source = Path(pediatric_hypothyroidism_ancillary.__file__).read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    calls = {
        node.func.id.lower()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not _unsafe_dependency_names(source)
    assert not calls.intersection({"open", "print", "exit", "quit", "seed", "randint", "write"})


def test_dependency_scanner_rejects_forbidden_and_lifecycle_dependencies() -> None:
    for source in (
        "import synthetic.package_export",
        "from synthetic import calibration",
        "import synthetic.derivation",
        "from synthetic.heldout import compare",
        "import synthetic.privacy",
        "from duckdb import connect",
        "from pathlib import Path",
        "import os",
        "import csv",
        "import random",
        "import synthea",
        "synthetic.package_export.write()",
        "from synthetic.native.resources import project_observed_resources as lifecycle; lifecycle(None, None)",
        "from builtins import open as reader; reader('x')",
        "import uuid; uuid.uuid4()",
    ):
        assert _unsafe_dependency_names(source)


def test_public_interfaces_have_narrow_typed_in_memory_signatures() -> None:
    assert tuple(
        inspect.signature(
            pediatric_hypothyroidism_ancillary.project_pediatric_hypothyroidism_ancillary_resources
        ).parameters
    ) == ("member", "shape", "policy")
    assert tuple(
        inspect.signature(
            pediatric_hypothyroidism_ancillary.validate_pediatric_hypothyroidism_ancillary_resources
        ).parameters
    ) == ("member", "projection", "policy")
    for function in (
        pediatric_hypothyroidism_ancillary.project_pediatric_hypothyroidism_ancillary_resources,
        pediatric_hypothyroidism_ancillary.validate_pediatric_hypothyroidism_ancillary_resources,
    ):
        assert not set(inspect.signature(function).parameters).intersection(
            {
                "path",
                "descriptor_path",
                "rows",
                "row",
                "output",
                "destination",
                "report",
                "key",
            }
        )


def test_module_has_no_visible_obesity_flag_contract_or_forbidden_exports() -> None:
    source = Path(pediatric_hypothyroidism_ancillary.__file__).read_text(
        encoding="utf-8"
    )
    assert "obesity_flag" not in source
    assert "synthetic.native.ancillary" not in source
    assert "development_runtime" not in source
    assert "package_export" not in source
    assert "random" not in source
