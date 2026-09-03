from __future__ import annotations

import ast
import dataclasses
import math
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
    tree = ast.parse(source)
    forbidden = {
        "calibration",
        "csv",
        "duckdb",
        "export",
        "filesystem",
        "heldout",
        "manifest",
        "obesity_flag",
        "package",
        "pathlib",
        "privacy",
        "random",
        "subprocess",
        "synthea",
        "synthetic.native.ancillary",
        "synthetic.native.excess_weight_ancillary",
        "synthetic.native.pediatric_hypothyroidism_ancillary",
    }
    imports = {
        f"{node.module}.{alias.name}".lower()
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    imports.update(
        alias.name.lower()
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert not any(
        any(part in imported.split(".") for part in forbidden)
        for imported in imports
    )
    calls = {
        node.func.id.lower()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not calls.intersection({"open", "print", "write", "seed", "randint"})
