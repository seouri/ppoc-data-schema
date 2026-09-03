from __future__ import annotations

import dataclasses
import math
from types import MappingProxyType

import pytest

from synthetic.models import DisorderKind
from synthetic.native.resources import ResourceRow, ResourceShape, ResourceSpec
from synthetic.native.undernutrition_ancillary import (
    UNDERNUTRITION_ANCILLARY_RESOURCE_NAMES,
    UNDERNUTRITION_DIAGNOSIS_CODE,
    UNDERNUTRITION_HEIGHT_COMPONENT,
    UNDERNUTRITION_LAB_COMPONENT_NAMES,
    UNDERNUTRITION_LAB_RESULT_FLAG,
    UNDERNUTRITION_MEDICATION_NAME,
    UNDERNUTRITION_MEDICATION_RECORD_TYPE,
    UNDERNUTRITION_REFERRAL_SPECIALTY,
    UNDERNUTRITION_WEIGHT_COMPONENT,
    UndernutritionAncillaryPolicy,
    UndernutritionAncillaryProjection,
)

PATIENT_ID = "syn-undernutrition-ancillary-patient"


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
                else "syn-undernutrition-ancillary-visit"
                if field_name == "visit_id"
                else "",
            )
            for field_name in _shape().field_names(resource_name)
        ),
    )


def _rows(patient_id: str = PATIENT_ID) -> dict[str, tuple[ResourceRow, ...]]:
    return {
        resource_name: (_row(resource_name, patient_id),)
        for resource_name in UNDERNUTRITION_ANCILLARY_RESOURCE_NAMES
    }


def _policy(**changes: object) -> UndernutritionAncillaryPolicy:
    values: dict[str, object] = {
        "policy_id": "undernutrition-ancillary-policy-v1",
        "policy_version": "1",
        "result_delay_days": 7,
    }
    values.update(changes)
    return UndernutritionAncillaryPolicy(**values)  # type: ignore[arg-type]


def _projection(**changes: object) -> UndernutritionAncillaryProjection:
    values: dict[str, object] = {
        "patient_id": PATIENT_ID,
        "shape": _shape(),
        "rows": _rows(),
    }
    values.update(changes)
    return UndernutritionAncillaryProjection(**values)  # type: ignore[arg-type]


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
        ("policy_version", "caf\u00e9"),
    ):
        with pytest.raises((TypeError, ValueError), match=field_name):
            _policy(**{field_name: value})

    for value in (True, -1, 1.5, math.inf, math.nan):
        with pytest.raises((TypeError, ValueError), match="result_delay_days"):
            _policy(result_delay_days=value)


def test_policy_rejects_behavior_bearing_integer_subclass() -> None:
    class MutableDelay(int):
        additions = 0

        def __radd__(self, other: object) -> object:
            type(self).additions += 1
            return int(self) + int(other) + type(self).additions

    with pytest.raises(TypeError, match="result_delay_days"):
        _policy(result_delay_days=MutableDelay(7))
    assert MutableDelay.additions == 0


def test_policy_rejects_behavior_bearing_string_subclasses() -> None:
    class MutableToken(str):
        lower_calls = 0

        def lower(self) -> str:
            type(self).lower_calls += 1
            return "safe" if type(self).lower_calls == 1 else "patient"

    for field_name in ("policy_id", "policy_version"):
        with pytest.raises(TypeError, match=field_name):
            _policy(**{field_name: MutableToken("stable-token")})
    assert MutableToken.lower_calls == 0


def test_constants_and_resource_registry_are_fixed() -> None:
    assert UNDERNUTRITION_ANCILLARY_RESOURCE_NAMES == (
        "labs",
        "medications",
        "problem_list",
        "referrals",
    )
    assert UNDERNUTRITION_DIAGNOSIS_CODE == "SYN-UNDERNUTRITION"
    assert UNDERNUTRITION_WEIGHT_COMPONENT == (
        "SYN-UNDERNUTRITION-WEIGHT-EVIDENCE"
    )
    assert UNDERNUTRITION_HEIGHT_COMPONENT == (
        "SYN-UNDERNUTRITION-HEIGHT-EVIDENCE"
    )
    assert UNDERNUTRITION_LAB_COMPONENT_NAMES == (
        UNDERNUTRITION_WEIGHT_COMPONENT,
        UNDERNUTRITION_HEIGHT_COMPONENT,
    )
    assert UNDERNUTRITION_LAB_RESULT_FLAG == "Synthetic"
    assert UNDERNUTRITION_REFERRAL_SPECIALTY == "Synthetic Pediatric Nutrition"
    assert UNDERNUTRITION_MEDICATION_NAME == (
        "Synthetic nutrition-supplement intervention"
    )
    assert UNDERNUTRITION_MEDICATION_RECORD_TYPE == "Internal"
    assert DisorderKind.UNDERNUTRITION.value == "undernutrition"


def test_projection_requires_four_row_tuples_in_fixed_order() -> None:
    projection = _projection(rows=MappingProxyType(_rows()))

    assert isinstance(projection.rows, MappingProxyType)
    assert tuple(projection.rows) == UNDERNUTRITION_ANCILLARY_RESOURCE_NAMES
    assert all(isinstance(rows, tuple) for rows in projection.rows.values())
    with pytest.raises(TypeError):
        projection.rows["labs"] = ()  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        projection.rows = {}  # type: ignore[misc]

    for omitted in UNDERNUTRITION_ANCILLARY_RESOURCE_NAMES:
        rows = _rows()
        del rows[omitted]
        with pytest.raises(ValueError, match="resource"):
            _projection(rows=rows)

    reordered = {
        name: _rows()[name]
        for name in reversed(UNDERNUTRITION_ANCILLARY_RESOURCE_NAMES)
    }
    with pytest.raises(ValueError, match="order"):
        _projection(rows=reordered)

    rows = _rows()
    rows["labs"] = list(rows["labs"])  # type: ignore[assignment]
    with pytest.raises(TypeError, match="tuple"):
        _projection(rows=rows)


def test_projection_rejects_wrong_resource_field_order_and_patient() -> None:
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

    with pytest.raises(ValueError, match="synthetic"):
        _projection(patient_id="real-patient")
    with pytest.raises(ValueError, match="projection patient"):
        _projection(rows=_rows("syn-other-patient"))


def test_projection_mapping_preserves_contract_order_and_redacts_private_state() -> None:
    projection = _projection()
    mapping = projection.to_mapping()

    assert mapping["contract"] == "undernutrition-ancillary-projection-v1"
    assert mapping["patient_id"] == PATIENT_ID
    assert tuple(mapping["resources"]) == UNDERNUTRITION_ANCILLARY_RESOURCE_NAMES  # type: ignore[arg-type]
    assert mapping["resources"]["labs"][0]["labs_field"] == ""  # type: ignore[index]
    assert "truth" not in repr(projection).lower()
    assert "trajectory" not in repr(projection).lower()
    assert "severity" not in repr(projection).lower()
