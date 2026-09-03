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


def _dotted_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None


def _unsafe_names(source: str) -> set[str]:
    tree, names, aliases = ast.parse(source), set[str](), {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.lower())
                aliases[alias.asname or alias.name.split(".")[0]] = alias.name.lower()
        elif isinstance(node, ast.ImportFrom):
            module = (node.module or "").lower()
            for alias in node.names:
                names.add(f"{module}.{alias.name}".strip(".").lower())
                aliases[alias.asname or alias.name] = f"{module}.{alias.name}".strip(".").lower()
        elif isinstance(node, ast.Call):
            name = _dotted_name(node.func)
            if name:
                root, *suffix = name.split(".")
                names.add(".".join((aliases.get(root, root), *suffix)).lower())
    forbidden = {"calibration", "csv", "duckdb", "export", "filesystem", "heldout", "manifest", "open", "os", "package", "pathlib", "privacy", "random", "subprocess", "synthea", "uuid"}
    allowed = {f"{module}.{symbol}".lower() for module, symbols in _ALLOWED.items() for symbol in symbols}
    return {name for name in names if forbidden.intersection(name.replace("_", ".").split(".")) or name.startswith("synthetic") and name not in allowed}


def test_module_is_native_only_and_has_no_io_randomness_or_obesity_leakage() -> None:
    source = Path(sga_ancillary.__file__).read_text(encoding="utf-8")
    calls = {node.func.id.lower() for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not _unsafe_names(source)
    assert not calls.intersection({"open", "print", "exit", "quit", "seed", "randint", "write"})
    assert "obesity_flag" not in source
    assert "package_export" not in source


def test_dependency_scanner_rejects_alias_aware_forbidden_coupling() -> None:
    for source in ("import random", "from pathlib import Path", "from builtins import open as reader; reader('x')", "import synthetic.package_export", "from synthetic.native.resources import project_observed_resources as lifecycle; lifecycle(None, None)"):
        assert _unsafe_names(source)


def test_public_functions_have_only_typed_in_memory_parameters() -> None:
    for function, expected in ((sga_ancillary.project_sga_ancillary_resources, ("member", "shape", "policy")), (sga_ancillary.validate_sga_ancillary_resources, ("member", "projection", "policy"))):
        parameters = inspect.signature(function).parameters
        assert tuple(parameters) == expected
        assert not set(parameters).intersection({"path", "descriptor_path", "rows", "row", "output", "destination", "report", "key"})
