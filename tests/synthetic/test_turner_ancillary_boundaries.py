from __future__ import annotations

import ast
import inspect
from pathlib import Path

from synthetic.native import turner_ancillary

_ALLOWED_DIRECT_IMPORTS = frozenset({"hashlib", "re"})
_ALLOWED_FROM_IMPORTS = {
    "__future__": frozenset({"annotations"}),
    "collections.abc": frozenset({"Mapping"}),
    "dataclasses": frozenset({"dataclass", "field"}),
    "enum": frozenset({"Enum"}),
    "types": frozenset({"MappingProxyType"}),
    "typing": frozenset({"ClassVar"}),
    "synthetic.cohort": frozenset({"CohortMember"}),
    "synthetic.models": frozenset(
        {"MAX_AGE_DAYS", "AgeRegimeDisorderTrajectory", "ClinicalEvent", "DisorderKind"}
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

# This is intentionally an allowlist: adding a new external call requires an
# explicit review of the native-only boundary rather than a denylist update.
_ALLOWED_QUALIFIED_CALLS = frozenset(
    {
        "dataclasses.dataclass",
        "dataclasses.field",
        "hashlib.sha256",
        "hashlib.sha256.hexdigest",
        "re.compile",
        "re.findall",
        "synthetic.native.observations.validate_observation_frame",
        "synthetic.native.resources.ResourceRow",
        "types.MappingProxyType",
    }
)
_ALLOWED_BARE_CALLS = frozenset(
    {
        "ArithmeticError",
        "ClassVar",
        "ClinicalEvent",
        "CohortMember",
        "Exception",
        "MappingProxyType",
        "ObservationValidationStatus",
        "RecordedEvent",
        "RecordedEventKind",
        "ResourceRow",
        "ResourceShape",
        "TypeError",
        "ValueError",
        "all",
        "any",
        "bool",
        "bytes",
        "dataclass",
        "dict",
        "enumerate",
        "frozenset",
        "hashlib",
        "int",
        "iter",
        "isinstance",
        "len",
        "list",
        "max",
        "min",
        "next",
        "object",
        "re",
        "set",
        "sorted",
        "str",
        "sum",
        "tuple",
        "type",
        "validate_observation_frame",
        "zip",
    }
)
def _dotted_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    if isinstance(node, ast.Call):
        return _dotted_name(node.func)
    if isinstance(node, ast.Subscript):
        return _dotted_name(node.value)
    if isinstance(node, ast.JoinedStr):
        return "str"
    return None


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
            allowed = _ALLOWED_FROM_IMPORTS.get(node.module or "")
            for alias in node.names:
                if allowed is None or alias.name not in allowed:
                    violations.add(f"{node.module}.{alias.name}")
    return violations


def _call_violations(tree: ast.AST) -> set[str]:
    aliases = _import_aliases(tree)
    local_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    violations: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted_name(node.func)
        if name is None:
            violations.add("<dynamic>")
            continue
        root, *suffix = name.split(".")
        qualified = ".".join((aliases.get(root, root), *suffix))
        if root in aliases:
            if qualified not in _ALLOWED_QUALIFIED_CALLS and qualified not in _ALLOWED_BARE_CALLS:
                violations.add(qualified)
        elif (
            name not in _ALLOWED_BARE_CALLS
            and name not in local_names
            and "." not in name
        ):
            violations.add(name)
    return violations


def test_module_uses_only_explicit_native_import_and_call_allowlists() -> None:
    source = Path(turner_ancillary.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert _import_violations(tree) == set()
    assert _call_violations(tree) == set()
    assert "obesity_flag" not in source
    assert "package_export" not in source


def test_allowlist_rejects_forbidden_imports_and_calls() -> None:
    cases = {
        "import socket\nsocket.create_connection(('example.test', 443))": (
            {"socket"},
            {"socket.create_connection"},
        ),
        "from pathlib import Path\nPath('fixture').read_text()": (
            {"pathlib.Path"},
            {"pathlib.Path", "pathlib.Path.read_text"},
        ),
        "import pandas as pd\npd.read_csv('fixture.csv')": (
            {"pandas"},
            {"pandas.read_csv"},
        ),
        "from .resources import ResourceShape": ({".resources"}, set()),
        "open('fixture')": (set(), {"open"}),
    }

    for source, (expected_imports, expected_calls) in cases.items():
        tree = ast.parse(source)
        assert _import_violations(tree) == expected_imports
        assert _call_violations(tree) == expected_calls


def test_public_functions_have_only_typed_in_memory_parameters() -> None:
    for function, expected in (
        (
            turner_ancillary.project_turner_ancillary_resources,
            ("member", "shape", "policy"),
        ),
        (
            turner_ancillary.validate_turner_ancillary_resources,
            ("member", "projection", "policy"),
        ),
    ):
        parameters = inspect.signature(function).parameters
        assert tuple(parameters) == expected
        assert not set(parameters).intersection(
            {
                "path",
                "descriptor_path",
                "rows",
                "row",
                "keys",
                "output",
                "destination",
                "report",
                "descriptor",
                "mapping",
            }
        )
