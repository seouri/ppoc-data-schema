from __future__ import annotations

import dataclasses
import math
from types import MappingProxyType

import pytest

from synthetic.models import DisorderKind
from synthetic.native.pediatric_hypothyroidism_ancillary import (
    PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_RESOURCE_NAMES,
    PEDIATRIC_HYPOTHYROIDISM_DIAGNOSIS_CODE,
    PEDIATRIC_HYPOTHYROIDISM_FREE_T4_COMPONENT,
    PEDIATRIC_HYPOTHYROIDISM_LAB_COMPONENT_NAMES,
    PEDIATRIC_HYPOTHYROIDISM_LAB_RESULT_FLAG,
    PEDIATRIC_HYPOTHYROIDISM_MEDICATION_NAME,
    PEDIATRIC_HYPOTHYROIDISM_MEDICATION_RECORD_TYPE,
    PEDIATRIC_HYPOTHYROIDISM_REFERRAL_SPECIALTY,
    PEDIATRIC_HYPOTHYROIDISM_TSH_COMPONENT,
    PediatricHypothyroidismAncillaryPolicy,
    PediatricHypothyroidismAncillaryProjection,
)
from synthetic.native.resources import ResourceRow, ResourceShape, ResourceSpec

PATIENT_ID = "syn-pediatric-hypothyroidism-ancillary-patient"


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
                else "syn-pediatric-hypothyroidism-visit"
                if field_name == "visit_id"
                else "",
            )
            for field_name in _shape().field_names(resource_name)
        ),
    )


def _rows(patient_id: str = PATIENT_ID) -> dict[str, tuple[ResourceRow, ...]]:
    return {
        resource_name: (_row(resource_name, patient_id),)
        for resource_name in PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_RESOURCE_NAMES
    }


def _policy(**changes: object) -> PediatricHypothyroidismAncillaryPolicy:
    values: dict[str, object] = {
        "policy_id": "pediatric-hypothyroidism-ancillary-policy-v1",
        "policy_version": "1",
        "result_delay_days": 7,
    }
    values.update(changes)
    return PediatricHypothyroidismAncillaryPolicy(**values)  # type: ignore[arg-type]


def _projection(**changes: object) -> PediatricHypothyroidismAncillaryProjection:
    values: dict[str, object] = {
        "patient_id": PATIENT_ID,
        "shape": _shape(),
        "rows": _rows(),
    }
    values.update(changes)
    return PediatricHypothyroidismAncillaryProjection(**values)  # type: ignore[arg-type]


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
    assert PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_RESOURCE_NAMES == (
        "labs",
        "medications",
        "problem_list",
        "referrals",
    )
    assert PEDIATRIC_HYPOTHYROIDISM_DIAGNOSIS_CODE == "SYN-PEDIATRIC-HYPOTHYROIDISM"
    assert PEDIATRIC_HYPOTHYROIDISM_TSH_COMPONENT == "SYN-HYPOTHYROIDISM-TSH"
    assert PEDIATRIC_HYPOTHYROIDISM_FREE_T4_COMPONENT == "SYN-HYPOTHYROIDISM-FREE-T4"
    assert PEDIATRIC_HYPOTHYROIDISM_LAB_COMPONENT_NAMES == (
        PEDIATRIC_HYPOTHYROIDISM_TSH_COMPONENT,
        PEDIATRIC_HYPOTHYROIDISM_FREE_T4_COMPONENT,
    )
    assert PEDIATRIC_HYPOTHYROIDISM_LAB_RESULT_FLAG == "Synthetic"
    assert PEDIATRIC_HYPOTHYROIDISM_REFERRAL_SPECIALTY == (
        "Synthetic Pediatric Endocrinology"
    )
    assert PEDIATRIC_HYPOTHYROIDISM_MEDICATION_NAME == "Synthetic levothyroxine"
    assert PEDIATRIC_HYPOTHYROIDISM_MEDICATION_RECORD_TYPE == "Internal"
    assert DisorderKind.PEDIATRIC_HYPOTHYROIDISM.value == "pediatric_hypothyroidism"


def test_projection_requires_four_rows_in_fixed_order_and_freezes_mapping() -> None:
    projection = _projection(rows=MappingProxyType(_rows()))

    assert isinstance(projection.rows, MappingProxyType)
    assert tuple(projection.rows) == PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_RESOURCE_NAMES
    with pytest.raises(TypeError):
        projection.rows["labs"] = ()  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        projection.rows = {}  # type: ignore[misc]

    for omitted in PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_RESOURCE_NAMES:
        rows = _rows()
        del rows[omitted]
        with pytest.raises(ValueError, match="resource"):
            _projection(rows=rows)

    reordered = {
        name: _rows()[name]
        for name in reversed(PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_RESOURCE_NAMES)
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
    projection = _projection()
    mapping = projection.to_mapping()

    assert mapping["contract"] == "pediatric-hypothyroidism-ancillary-projection-v1"
    assert mapping["patient_id"] == PATIENT_ID
    assert tuple(mapping["resources"]) == (  # type: ignore[arg-type]
        "labs",
        "medications",
        "problem_list",
        "referrals",
    )
    assert mapping["resources"]["labs"][0]["labs_field"] == ""  # type: ignore[index]
    assert "truth" not in repr(projection).lower()
    assert "trajectory" not in repr(projection).lower()

    with pytest.raises(ValueError, match="synthetic"):
        _projection(patient_id="real-patient")
    with pytest.raises(ValueError, match="synthetic"):
        _projection(rows=_rows("real-patient"))
