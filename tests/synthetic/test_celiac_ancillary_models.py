from __future__ import annotations

import ast
import dataclasses
import math
import re
from pathlib import Path
from types import MappingProxyType

import pytest

from synthetic.native import celiac_ancillary
from synthetic.native.celiac_ancillary import (
    CELIAC_ANCILLARY_RESOURCE_NAMES,
    CELIAC_DIAGNOSIS_CODE,
    CELIAC_LAB_COMPONENT_NAMES,
    CELIAC_LAB_RESULT_FLAG,
    CELIAC_MEDICATION_NAME,
    CELIAC_MEDICATION_RECORD_TYPE,
    CELIAC_REFERRAL_SPECIALTY,
    CELIAC_TOTAL_IGA_COMPONENT,
    CELIAC_TTG_IGA_COMPONENT,
    CeliacAncillaryPolicy,
    CeliacAncillaryProjection,
)
from synthetic.native.resources import ResourceRow, ResourceShape, ResourceSpec

PATIENT_ID = "syn-celiac-ancillary-patient"

_ALLOWED_REPOSITORY_SYMBOLS = {
    "synthetic.cohort": frozenset({"CohortMember"}),
    "synthetic.models": frozenset(
        {"MAX_AGE_DAYS", "AgeRegimeDisorderTrajectory", "DisorderKind"}
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

_FORBIDDEN_MODULES = frozenset(
    {
        "builtins",
        "csv",
        "duckdb",
        "glob",
        "http",
        "httpx",
        "io",
        "multiprocessing",
        "numpy.random",
        "os",
        "pathlib",
        "random",
        "requests",
        "secrets",
        "shutil",
        "socket",
        "sqlalchemy",
        "sqlite3",
        "subprocess",
        "sys",
        "tempfile",
        "urllib",
        "uuid",
    }
)

_FORBIDDEN_NAME_PARTS = frozenset(
    {
        "calibrate",
        "calibration",
        "derivation",
        "export",
        "fileio",
        "filesystem",
        "governed",
        "heldout",
        "manifest",
        "obesity",
        "package",
        "privacy",
        "synthea",
    }
)

_FORBIDDEN_CALL_NAMES = frozenset(
    {
        "check_call",
        "check_output",
        "connect",
        "create_connection",
        "environ",
        "execute",
        "exit",
        "getenv",
        "mkdir",
        "makedirs",
        "open",
        "popen",
        "print",
        "quit",
        "read",
        "read_bytes",
        "read_text",
        "remove",
        "rename",
        "replace",
        "rmdir",
        "run",
        "seed",
        "system",
        "token_hex",
        "unlink",
        "urlopen",
        "uuid4",
        "write",
        "write_bytes",
        "write_text",
    }
)


def _dotted_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None


def _resolve_dotted_name(name: str, aliases: dict[str, str]) -> str:
    root, *suffix = name.split(".")
    resolved_root = aliases.get(root, root)
    return ".".join((resolved_root, *suffix)).lower()


def _allowed_repository_name(name: str) -> bool:
    return any(
        name == f"{module}.{symbol}".lower()
        for module, symbols in _ALLOWED_REPOSITORY_SYMBOLS.items()
        for symbol in symbols
    )


def _is_forbidden_dependency(name: str) -> bool:
    normalized = name.lower()
    if normalized == "relative-import":
        return True
    if normalized.startswith("synthetic."):
        return not _allowed_repository_name(normalized)
    if any(
        normalized == module or normalized.startswith(f"{module}.")
        for module in _FORBIDDEN_MODULES
    ):
        return True
    parts = tuple(part for part in re.split(r"[._]+", normalized) if part)
    return bool(
        _FORBIDDEN_NAME_PARTS.intersection(parts)
        or parts
        and parts[-1] in _FORBIDDEN_CALL_NAMES
    )


class _DependencyScanner(ast.NodeVisitor):
    def __init__(self) -> None:
        self.names: set[str] = set()
        self.aliases: dict[str, str] = {}

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            origin = alias.name.lower()
            self.names.add(origin)
            local_name = alias.asname or alias.name.split(".", 1)[0]
            self.aliases[local_name] = origin if alias.asname else local_name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level:
            self.names.add("relative-import")
        module = (node.module or "").lower()
        for alias in node.names:
            origin = f"{module}.{alias.name}".strip(".").lower()
            self.names.add(origin)
            self.aliases[alias.asname or alias.name] = origin
        self.generic_visit(node)

    def _record_assignment(self, targets: list[ast.expr], value: ast.expr) -> None:
        origin = _dotted_name(value)
        if origin is None:
            return
        resolved = _resolve_dotted_name(origin, self.aliases)
        for target in targets:
            if isinstance(target, ast.Name):
                self.aliases[target.id] = resolved

    def visit_Assign(self, node: ast.Assign) -> None:
        self._record_assignment(node.targets, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._record_assignment([node.target], node.value)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _dotted_name(node.func)
        if name:
            self.names.add(_resolve_dotted_name(name, self.aliases))
        self.generic_visit(node)


def _unsafe_dependency_names(source: str) -> set[str]:
    scanner = _DependencyScanner()
    scanner.visit(ast.parse(source))
    return {name for name in scanner.names if _is_forbidden_dependency(name)}


def _shape() -> ResourceShape:
    fields_by_name = {
        "patients": ("patient_id", "patients_field"),
        "visits": ("patient_id", "visit_id", "visits_field"),
        "labs": ("patient_id", "visit_id", "labs_field"),
        "medications": ("patient_id", "visit_id", "medications_field"),
        "problem_list": ("patient_id", "problem_list_field"),
        "referrals": ("patient_id", "visit_id", "referrals_field"),
    }
    return ResourceShape(
        tuple(
            ResourceSpec(name, fields_by_name[name])
            for name in (
                "patients",
                "visits",
                "labs",
                "medications",
                "problem_list",
                "referrals",
            )
        )
    )


def _row(resource_name: str, patient_id: str = PATIENT_ID) -> ResourceRow:
    return ResourceRow(
        resource_name,
        tuple(
            (
                field_name,
                patient_id
                if field_name == "patient_id"
                else "syn-celiac-ancillary-visit"
                if field_name == "visit_id"
                else "",
            )
            for field_name in _shape().field_names(resource_name)
        ),
    )


def _rows(patient_id: str = PATIENT_ID) -> dict[str, tuple[ResourceRow, ...]]:
    return {
        resource_name: (_row(resource_name, patient_id),)
        for resource_name in CELIAC_ANCILLARY_RESOURCE_NAMES
    }


def _policy(**changes: object) -> CeliacAncillaryPolicy:
    values: dict[str, object] = {
        "policy_id": "celiac-ancillary-policy-v1",
        "policy_version": "1",
        "result_delay_days": 7,
    }
    values.update(changes)
    return CeliacAncillaryPolicy(**values)  # type: ignore[arg-type]


def _projection(**changes: object) -> CeliacAncillaryProjection:
    values: dict[str, object] = {
        "patient_id": PATIENT_ID,
        "shape": _shape(),
        "rows": _rows(),
    }
    values.update(changes)
    return CeliacAncillaryProjection(**values)  # type: ignore[arg-type]


def test_policy_and_projection_are_frozen_records() -> None:
    policy = _policy()
    projection = _projection()

    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.policy_id = "other"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        projection.patient_id = "other"  # type: ignore[misc]
    assert dataclasses.is_dataclass(policy)
    assert dataclasses.is_dataclass(projection)


def test_policy_rejects_unsafe_tokens_and_invalid_delays() -> None:
    for field_name, value in (
        ("policy_id", "patient-policy-v1"),
        ("policy_id", "../policy"),
        ("policy_id", "policy.json"),
        ("policy_version", "truth-v1"),
        ("policy_version", "policy with spaces"),
    ):
        with pytest.raises((TypeError, ValueError), match=field_name):
            _policy(**{field_name: value})

    for value in (True, -1, 1.5, math.inf, math.nan):
        with pytest.raises((TypeError, ValueError), match="result_delay_days"):
            _policy(result_delay_days=value)


def test_constants_and_resource_registry_are_fixed() -> None:
    assert CELIAC_ANCILLARY_RESOURCE_NAMES == (
        "labs",
        "medications",
        "problem_list",
        "referrals",
    )
    assert CELIAC_DIAGNOSIS_CODE == "SYN-CELIAC-DISEASE"
    assert CELIAC_TTG_IGA_COMPONENT == "SYN-CELIAC-TTG-IGA"
    assert CELIAC_TOTAL_IGA_COMPONENT == "SYN-CELIAC-TOTAL-IGA"
    assert CELIAC_LAB_COMPONENT_NAMES == (
        CELIAC_TTG_IGA_COMPONENT,
        CELIAC_TOTAL_IGA_COMPONENT,
    )
    assert CELIAC_LAB_RESULT_FLAG == "Synthetic"
    assert CELIAC_REFERRAL_SPECIALTY == "Synthetic Pediatric Gastroenterology"
    assert CELIAC_MEDICATION_NAME == "Synthetic gluten-free intervention"
    assert CELIAC_MEDICATION_RECORD_TYPE == "Internal"


def test_projection_requires_four_rows_in_fixed_order_and_freezes_mapping() -> None:
    projection = _projection(rows=MappingProxyType(_rows()))

    assert isinstance(projection.rows, MappingProxyType)
    assert tuple(projection.rows) == CELIAC_ANCILLARY_RESOURCE_NAMES
    with pytest.raises(TypeError):
        projection.rows["labs"] = ()  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        projection.rows = {}  # type: ignore[misc]

    for omitted in CELIAC_ANCILLARY_RESOURCE_NAMES:
        rows = _rows()
        del rows[omitted]
        with pytest.raises(ValueError, match="resource"):
            _projection(rows=rows)

    reordered = {
        name: _rows()[name]
        for name in reversed(CELIAC_ANCILLARY_RESOURCE_NAMES)
    }
    with pytest.raises(ValueError, match="order"):
        _projection(rows=reordered)


def test_projection_rejects_wrong_resource_identity_or_descriptor_field_order() -> None:
    rows = _rows()
    rows["labs"] = (ResourceRow("medications", rows["labs"][0].values),)
    with pytest.raises((TypeError, ValueError), match="resource"):
        _projection(rows=rows)

    rows = _rows()
    rows["labs"] = (
        ResourceRow("labs", tuple(reversed(rows["labs"][0].values))),
    )
    with pytest.raises((TypeError, ValueError), match="field"):
        _projection(rows=rows)


def test_projection_normalizes_mapping_and_requires_synthetic_patient_ids() -> None:
    projection = _projection(rows=MappingProxyType(_rows()))
    mapping = projection.to_mapping()

    assert mapping["contract"] == "celiac-ancillary-projection-v1"
    assert mapping["patient_id"] == PATIENT_ID
    assert tuple(mapping["resources"]) == CELIAC_ANCILLARY_RESOURCE_NAMES  # type: ignore[arg-type]
    assert mapping["resources"]["labs"][0]["labs_field"] == ""  # type: ignore[index]
    assert "truth" not in repr(projection).lower()
    assert "trajectory" not in repr(projection).lower()

    with pytest.raises(ValueError, match="synthetic"):
        _projection(patient_id="real-patient")
    with pytest.raises(ValueError, match="synthetic"):
        _projection(rows=_rows("real-patient"))


def test_module_has_no_io_or_ancillary_runtime_coupling() -> None:
    source = Path(celiac_ancillary.__file__).read_text(encoding="utf-8")
    assert not _unsafe_dependency_names(source)
    assert "obesity_flag" not in source


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        ("import synthetic.native.ancillary", "synthetic.native.ancillary"),
        (
            "from synthetic.native import excess_weight_ancillary",
            "synthetic.native.excess_weight_ancillary",
        ),
        (
            "import synthetic.native.ancillary_bundle",
            "synthetic.native.ancillary_bundle",
        ),
        (
            "from synthetic.native import ancillary_contract",
            "synthetic.native.ancillary_contract",
        ),
        (
            "import synthetic.native.pediatric_hypothyroidism_ancillary as thyroid",
            "synthetic.native.pediatric_hypothyroidism_ancillary",
        ),
        ("import synthetic.package_export", "synthetic.package_export"),
        ("import synthetic.csv_package as package", "synthetic.csv_package"),
        ("from pathlib import Path; Path('x').read_text()", "pathlib"),
        (
            "import pathlib as filesystem; filesystem.Path('x').write_text('x')",
            "pathlib",
        ),
        (
            "import os as environment; read = environment.getenv; read('TOKEN')",
            "os.getenv",
        ),
        (
            "import socket as network; connect = network.create_connection; connect(('x', 80))",
            "socket.create_connection",
        ),
        ("import urllib.request as network; network.urlopen('https://x')", "urllib"),
        ("from random import randint as choose; choose(0, 1)", "random.randint"),
        ("import secrets as randomizer; randomizer.token_hex()", "secrets"),
        ("import subprocess as process; process.run(['command'])", "subprocess.run"),
        ("import synthetic.derivation", "synthetic.derivation"),
        (
            "import synthetic.development_runtime",
            "synthetic.development_runtime",
        ),
        (
            "from synthetic.calibration_input import load as governed; governed()",
            "synthetic.calibration_input",
        ),
        ("from synthetic.heldout import compare", "synthetic.heldout"),
        ("import synthetic.privacy", "synthetic.privacy"),
        ("from synthetic import calibration", "synthetic.calibration"),
        ("import synthetic.cdc_reference", "synthetic.cdc_reference"),
        ("import synthetic.privacy_audit", "synthetic.privacy_audit"),
        ("import synthetic.synthea_conformance", "synthetic.synthea_conformance"),
        ("import synthea", "synthea"),
        (
            "import builtins as platform; read = platform.open; read('x')",
            "builtins.open",
        ),
        ("import io as stream; stream.open('x')", "io.open"),
        ("import uuid as identifiers; identifiers.uuid4()", "uuid"),
        ("from .resources import ResourceRow", "relative-import"),
    ),
    ids=(
        "ghd-ancillary",
        "excess-weight-ancillary",
        "ancillary-bundle",
        "ancillary-contract",
        "hypothyroidism-ancillary",
        "package-export",
        "csv-package-export",
        "filesystem",
        "pathlib-alias-io",
        "environment-alias",
        "network-alias",
        "urllib-network",
        "random-alias",
        "secrets-alias",
        "subprocess-alias",
        "governed-derivation",
        "development-runtime",
        "governed-calibration",
        "held-out",
        "privacy",
        "calibration",
        "governed-reference",
        "privacy-audit",
        "synthea-conformance",
        "synthea",
        "attribute-io-alias",
        "attribute-io-module",
        "uuid-alias",
        "relative-import",
    ),
)
def test_dependency_scanner_rejects_forbidden_dependencies(
    source: str, expected: str
) -> None:
    findings = _unsafe_dependency_names(source)
    assert findings
    assert any(expected in finding for finding in findings)
