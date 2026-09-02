from __future__ import annotations

import dataclasses
import math
from types import MappingProxyType

import pytest

from synthetic.models import DisorderKind
from synthetic.native.excess_weight_ancillary import (
    EXCESS_WEIGHT_A1C_COMPONENT,
    EXCESS_WEIGHT_ANCILLARY_RESOURCE_NAMES,
    EXCESS_WEIGHT_DIAGNOSIS_CODE,
    EXCESS_WEIGHT_LAB_COMPONENT_NAMES,
    EXCESS_WEIGHT_LAB_RESULT_FLAG,
    EXCESS_WEIGHT_LIPID_COMPONENT,
    EXCESS_WEIGHT_REFERRAL_SPECIALTY,
    ExcessWeightAncillaryPolicy,
    ExcessWeightAncillaryProjection,
)
from synthetic.native.resources import ResourceRow, ResourceShape, ResourceSpec

PATIENT_ID = "syn-excess-weight-ancillary-patient"


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
            ResourceSpec(
                name,
                fields_by_name[name],
            )
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
                else "syn-excess-weight-visit"
                if field_name == "visit_id"
                else "",
            )
            for field_name in _shape().field_names(resource_name)
        ),
    )


def _rows(patient_id: str = PATIENT_ID) -> dict[str, tuple[ResourceRow, ...]]:
    return {
        resource_name: (_row(resource_name, patient_id),)
        for resource_name in EXCESS_WEIGHT_ANCILLARY_RESOURCE_NAMES
    }


def _policy(**changes: object) -> ExcessWeightAncillaryPolicy:
    values: dict[str, object] = {
        "policy_id": "excess-weight-ancillary-policy-v1",
        "policy_version": "1",
        "result_delay_days": 7,
    }
    values.update(changes)
    return ExcessWeightAncillaryPolicy(**values)  # type: ignore[arg-type]


def _projection(**changes: object) -> ExcessWeightAncillaryProjection:
    values: dict[str, object] = {
        "patient_id": PATIENT_ID,
        "shape": _shape(),
        "rows": _rows(),
    }
    values.update(changes)
    return ExcessWeightAncillaryProjection(**values)  # type: ignore[arg-type]


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
    assert EXCESS_WEIGHT_ANCILLARY_RESOURCE_NAMES == (
        "labs",
        "medications",
        "problem_list",
        "referrals",
    )
    assert EXCESS_WEIGHT_DIAGNOSIS_CODE == "SYN-EXCESS-WEIGHT"
    assert EXCESS_WEIGHT_LIPID_COMPONENT == "SYN-EXCESS-WEIGHT-LIPID"
    assert EXCESS_WEIGHT_A1C_COMPONENT == "SYN-EXCESS-WEIGHT-A1C"
    assert EXCESS_WEIGHT_LAB_COMPONENT_NAMES == (
        EXCESS_WEIGHT_LIPID_COMPONENT,
        EXCESS_WEIGHT_A1C_COMPONENT,
    )
    assert EXCESS_WEIGHT_LAB_RESULT_FLAG == "Synthetic"
    assert EXCESS_WEIGHT_REFERRAL_SPECIALTY == "Synthetic Pediatric Nutrition"


def test_projection_requires_four_rows_in_fixed_order_and_freezes_mapping() -> None:
    projection = _projection(rows=MappingProxyType(_rows()))

    assert isinstance(projection.rows, MappingProxyType)
    assert tuple(projection.rows) == EXCESS_WEIGHT_ANCILLARY_RESOURCE_NAMES
    with pytest.raises(TypeError):
        projection.rows["labs"] = ()  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        projection.rows = {}  # type: ignore[misc]

    for omitted in EXCESS_WEIGHT_ANCILLARY_RESOURCE_NAMES:
        rows = _rows()
        del rows[omitted]
        with pytest.raises(ValueError, match="resource"):
            _projection(rows=rows)

    reordered = {name: _rows()[name] for name in reversed(EXCESS_WEIGHT_ANCILLARY_RESOURCE_NAMES)}
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

    assert mapping["contract"] == "excess-weight-ancillary-projection-v1"
    assert mapping["patient_id"] == PATIENT_ID
    assert tuple(mapping["resources"]) == EXCESS_WEIGHT_ANCILLARY_RESOURCE_NAMES  # type: ignore[arg-type]
    assert mapping["resources"]["labs"][0]["labs_field"] == ""  # type: ignore[index]
    assert "truth" not in repr(projection).lower()
    assert "trajectory" not in repr(projection).lower()

    with pytest.raises(ValueError, match="synthetic"):
        _projection(patient_id="real-patient")
    with pytest.raises(ValueError, match="synthetic"):
        _projection(rows=_rows("real-patient"))


def test_disorder_kind_is_excess_weight() -> None:
    assert DisorderKind.EXCESS_WEIGHT.value == "excess_weight"
