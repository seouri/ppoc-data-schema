from __future__ import annotations

import ast
import inspect
from pathlib import Path

from synthetic.native import undernutrition_ancillary

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
_ALLOWED_RECEIVER_CALLS = frozenset(
    {
        "UNDERNUTRITION_ANCILLARY_REASON_CODES_BY_STATUS.values",
        "_AGGREGATE_TOKEN.fullmatch",
        "_AGGREGATE_UNSAFE_COMPONENTS.intersection",
        "_PATH_EXTENSION.search",
        "_REQUIRED_FIELDS.issubset",
        "_SYNTHETIC_PATIENT_TOKEN.fullmatch",
        "_SYNTHETIC_VISIT_TOKEN.fullmatch",
        "actual_values.get",
        "age_sets.add",
        "check.to_mapping",
        "classified.update",
        "differing.intersection",
        "expected.items",
        "expected.update",
        "expected_counts.items",
        "lab_ids.add",
        "lab_pairs.append",
        "lab_results.add",
        "lab_visits.add",
        "medication.get",
        "medication_orders.add",
        "medication_starts.add",
        "medication_visits.add",
        "name.endswith",
        "nonempty_resources.add",
        "object.__setattr__",
        "problem_values.get",
        "projection.rows.get",
        "referral_values.get",
        "row.to_mapping",
        "rows.get",
        "seen.add",
        "self.CHECK_NAMES.index",
        "self.shape.field_names",
        "shape.field_names",
        "shape_fields.get",
        "str.encode",
        "treatment_ages.append",
        "value.lower",
        "values.get",
        "values.items",
        "values_by_resource.append",
        "visible_events.get",
        "visible_events.setdefault",
        "visit_by_source_point.get",
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
            if (
                qualified not in _ALLOWED_QUALIFIED_CALLS
                and qualified not in _ALLOWED_BARE_CALLS
            ):
                violations.add(qualified)
        elif "." in name:
            if name not in _ALLOWED_RECEIVER_CALLS:
                violations.add(name)
        elif name not in _ALLOWED_BARE_CALLS and name not in local_names:
            violations.add(name)
    return violations


def test_module_uses_only_explicit_native_import_and_call_allowlists() -> None:
    source = Path(undernutrition_ancillary.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert _import_violations(tree) == set()
    assert _call_violations(tree) == set()
    for forbidden in (
        "obesity_flag",
        "package_export",
        "duckdb",
        "synthea",
        "subprocess",
        "socket",
        "urlopen",
        "getenv",
        "environ",
        "read_csv",
        "write_csv",
        "manifest",
        "calibration",
        "heldout",
        "privacy",
    ):
        assert forbidden not in source.lower()


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
        "import random\nrandom.random()": ({"random"}, {"random.random"}),
        "member.frame.write_text('unsafe')": (set(), {"member.frame.write_text"}),
        "projection.export('unsafe')": (set(), {"projection.export"}),
        "member.frame.connect()": (set(), {"member.frame.connect"}),
        "member.frame.values()": (set(), {"member.frame.values"}),
    }
    for source, (expected_imports, expected_calls) in cases.items():
        tree = ast.parse(source)
        assert _import_violations(tree) == expected_imports
        assert _call_violations(tree) == expected_calls


def test_public_functions_have_exact_typed_in_memory_signatures() -> None:
    for function, expected_names, expected_annotations in (
        (
            undernutrition_ancillary.project_undernutrition_ancillary_resources,
            ("member", "shape", "policy"),
            {
                "member": "CohortMember",
                "shape": "ResourceShape",
                "policy": "UndernutritionAncillaryPolicy",
                "return": "UndernutritionAncillaryProjection",
            },
        ),
        (
            undernutrition_ancillary.validate_undernutrition_ancillary_resources,
            ("member", "projection", "policy"),
            {
                "member": "CohortMember",
                "projection": "UndernutritionAncillaryProjection",
                "policy": "UndernutritionAncillaryPolicy",
                "return": "UndernutritionAncillaryValidationReport",
            },
        ),
    ):
        signature = inspect.signature(function)
        parameters = signature.parameters
        assert tuple(parameters) == expected_names
        assert {
            **{name: parameter.annotation for name, parameter in parameters.items()},
            "return": signature.return_annotation,
        } == expected_annotations
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
