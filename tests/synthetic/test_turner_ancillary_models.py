from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path
from types import MappingProxyType

import pytest

from synthetic.native import turner_ancillary
from synthetic.native.resources import ResourceRow, ResourceShape
from synthetic.native.turner_ancillary import (
    TURNER_ANCILLARY_RESOURCE_NAMES,
    TURNER_DIAGNOSIS_CODE,
    TURNER_ENDOCRINE_EVIDENCE_COMPONENT,
    TURNER_KARYOTYPE_COMPONENT,
    TURNER_LAB_COMPONENT_NAMES,
    TURNER_LAB_RESULT_FLAG,
    TURNER_MEDICATION_NAME,
    TURNER_MEDICATION_RECORD_TYPE,
    TURNER_REFERRAL_SPECIALTY,
    TurnerAncillaryPolicy,
    TurnerAncillaryProjection,
)

ROOT = Path(__file__).resolve().parents[2]
PATIENT_ID = "syn-turner-ancillary-patient"
VISIT_ID = "syn-turner-ancillary-visit"


def _shape() -> ResourceShape:
    return ResourceShape.from_descriptor(
        json.loads((ROOT / "datapackage.json").read_text(encoding="utf-8"))
    )


def _policy(**changes: object) -> TurnerAncillaryPolicy:
    values: dict[str, object] = {
        "policy_id": "turner-ancillary-policy-v1",
        "policy_version": "1",
        "result_delay_days": 7,
    }
    values.update(changes)
    return TurnerAncillaryPolicy(**values)  # type: ignore[arg-type]


_INTEGER_FIELDS = frozenset(
    {
        "result_line_num",
        "lab_order_date_age_in_days",
        "lab_result_date_age_in_days",
        "med_order_date_age_in_days",
        "med_start_date_age_in_days",
        "med_end_date_age_in_days",
        "noted_date_age_in_days",
        "resolved_date_age_in_days",
        "referral_date_age_in_days",
        "referral_number_of_visits",
    }
)


def _row(resource_name: str, patient_id: str = PATIENT_ID) -> ResourceRow:
    values: dict[str, object] = {}
    for field_name in _shape().field_names(resource_name):
        if field_name == "patient_id":
            values[field_name] = patient_id
        elif field_name == "visit_id":
            values[field_name] = VISIT_ID
        elif field_name == "result_line_num" or field_name == "referral_number_of_visits":
            values[field_name] = 1
        elif field_name in _INTEGER_FIELDS:
            values[field_name] = ""
        else:
            values[field_name] = ""
    return ResourceRow(
        resource_name,
        tuple((field_name, values[field_name]) for field_name in _shape().field_names(resource_name)),
    )


def _rows(patient_id: str = PATIENT_ID) -> dict[str, tuple[ResourceRow, ...]]:
    return {
        resource_name: (_row(resource_name, patient_id),)
        for resource_name in TURNER_ANCILLARY_RESOURCE_NAMES
    }


def _projection(**changes: object) -> TurnerAncillaryProjection:
    values: dict[str, object] = {
        "patient_id": PATIENT_ID,
        "shape": _shape(),
        "rows": _rows(),
    }
    values.update(changes)
    return TurnerAncillaryProjection(**values)  # type: ignore[arg-type]


def test_models_are_frozen_and_keep_the_fixed_fictional_contract() -> None:
    policy = _policy()
    projection = _projection()

    assert TURNER_ANCILLARY_RESOURCE_NAMES == (
        "labs",
        "medications",
        "problem_list",
        "referrals",
    )
    assert TURNER_DIAGNOSIS_CODE == "SYN-TURNER-SYNDROME"
    assert TURNER_KARYOTYPE_COMPONENT == "SYN-TURNER-KARYOTYPE"
    assert TURNER_ENDOCRINE_EVIDENCE_COMPONENT == "SYN-TURNER-ENDOCRINE-EVIDENCE"
    assert TURNER_LAB_COMPONENT_NAMES == (
        TURNER_KARYOTYPE_COMPONENT,
        TURNER_ENDOCRINE_EVIDENCE_COMPONENT,
    )
    assert TURNER_REFERRAL_SPECIALTY == "Synthetic Pediatric Endocrinology"
    assert TURNER_MEDICATION_NAME == "Synthetic estrogen intervention"
    assert TURNER_MEDICATION_RECORD_TYPE == "Internal"
    assert TURNER_LAB_RESULT_FLAG == "Synthetic"
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


def test_projection_requires_fixed_order_and_freezes_row_mapping() -> None:
    projection = _projection(rows=MappingProxyType(_rows()))

    assert isinstance(projection.rows, MappingProxyType)
    assert tuple(projection.rows) == TURNER_ANCILLARY_RESOURCE_NAMES
    with pytest.raises(TypeError):
        projection.rows["labs"] = ()  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        projection.rows = {}  # type: ignore[misc]

    for omitted in TURNER_ANCILLARY_RESOURCE_NAMES:
        rows = _rows()
        del rows[omitted]
        with pytest.raises(ValueError, match="resource"):
            _projection(rows=rows)

    reordered = {
        name: _rows()[name] for name in reversed(TURNER_ANCILLARY_RESOURCE_NAMES)
    }
    with pytest.raises(ValueError, match="order"):
        _projection(rows=reordered)


def test_projection_keeps_descriptor_order_scalar_types_and_empty_conventions() -> None:
    projection = _projection()
    integer_fields = _INTEGER_FIELDS

    for resource_name in TURNER_ANCILLARY_RESOURCE_NAMES:
        for row in projection.rows[resource_name]:
            assert tuple(field_name for field_name, _ in row.values) == _shape().field_names(
                resource_name
            )
            for field_name, value in row.values:
                if field_name in integer_fields:
                    assert value == "" or type(value) is int
                else:
                    assert type(value) is str

    mapping = projection.to_mapping()
    assert mapping["contract"] == "turner-ancillary-projection-v1"
    assert mapping["patient_id"] == PATIENT_ID
    assert tuple(mapping["resources"]) == TURNER_ANCILLARY_RESOURCE_NAMES  # type: ignore[arg-type]
    assert mapping["resources"]["labs"][0]["lab_procedure_name"] == ""  # type: ignore[index]
    assert mapping["resources"]["labs"][0]["result_value"] == ""  # type: ignore[index]
    assert mapping["resources"]["medications"][0]["med_end_date_age_in_days"] == ""  # type: ignore[index]
    assert mapping["resources"]["problem_list"][0]["resolved_date_age_in_days"] == ""  # type: ignore[index]


def test_projection_rejects_wrong_row_identity_or_descriptor_order() -> None:
    rows = _rows()
    rows["labs"] = (ResourceRow("medications", rows["labs"][0].values),)
    with pytest.raises((TypeError, ValueError), match="resource"):
        _projection(rows=rows)

    rows = _rows()
    rows["labs"] = (ResourceRow("labs", tuple(reversed(rows["labs"][0].values))),)
    with pytest.raises((TypeError, ValueError), match="field"):
        _projection(rows=rows)


def test_module_has_no_obesity_or_io_boundary_dependency() -> None:
    source = Path(turner_ancillary.__file__).read_text(encoding="utf-8")
    assert "obesity_flag" not in source
    assert "pathlib" not in source
    assert "random" not in source
    assert "synthea" not in source.lower()
