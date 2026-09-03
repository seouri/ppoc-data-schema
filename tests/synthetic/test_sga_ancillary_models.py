from __future__ import annotations

import dataclasses
from types import MappingProxyType

import pytest

from synthetic.native.resources import ResourceRow, ResourceShape, ResourceSpec
from synthetic.native.sga_ancillary import (
    SGA_ANCILLARY_RESOURCE_NAMES,
    SGA_DIAGNOSIS_CODE,
    SGA_LAB_COMPONENT_NAMES,
    SGA_LAB_RESULT_FLAG,
    SGA_REFERRAL_SPECIALTY,
    SgaAncillaryPolicy,
    SgaAncillaryProjection,
)

PATIENT_ID = "syn-sga-ancillary-patient"


def _shape() -> ResourceShape:
    return ResourceShape(
        tuple(
            ResourceSpec(name, fields)
            for name, fields in (
                ("patients", ("patient_id",)),
                ("visits", ("patient_id", "visit_id")),
                ("labs", ("patient_id", "visit_id", "labs_field")),
                ("medications", ("patient_id", "visit_id", "medications_field")),
                ("problem_list", ("patient_id", "problem_list_field")),
                ("referrals", ("patient_id", "visit_id", "referrals_field")),
            )
        )
    )


def _rows() -> dict[str, tuple[ResourceRow, ...]]:
    return {
        name: (
            ResourceRow(
                name,
                tuple(
                    (
                        field,
                        PATIENT_ID
                        if field == "patient_id"
                        else "syn-sga-ancillary-visit"
                        if field == "visit_id"
                        else "",
                    )
                    for field in _shape().field_names(name)
                ),
            ),
        )
        for name in SGA_ANCILLARY_RESOURCE_NAMES
    }


def test_models_are_frozen_and_keep_the_fixed_fictional_contract() -> None:
    policy = SgaAncillaryPolicy("sga-ancillary-policy-v1", "1", 7)
    projection = SgaAncillaryProjection(PATIENT_ID, _shape(), _rows())

    assert SGA_ANCILLARY_RESOURCE_NAMES == ("labs", "medications", "problem_list", "referrals")
    assert SGA_DIAGNOSIS_CODE == "SYN-SGA"
    assert SGA_LAB_COMPONENT_NAMES == (
        "SYN-SGA-GESTATIONAL-AGE",
        "SYN-SGA-BIRTH-SIZE",
    )
    assert SGA_LAB_RESULT_FLAG == "Synthetic"
    assert SGA_REFERRAL_SPECIALTY == "Synthetic Neonatology Follow-up"
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.policy_id = "changed"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        projection.patient_id = "changed"  # type: ignore[misc]


def test_models_reject_unsafe_policy_and_row_shapes_and_freeze_rows() -> None:
    with pytest.raises(ValueError, match="policy_id"):
        SgaAncillaryPolicy("../unsafe", "1", 7)
    with pytest.raises(ValueError, match="result_delay_days"):
        SgaAncillaryPolicy("sga-policy", "1", -1)

    projection = SgaAncillaryProjection(PATIENT_ID, _shape(), MappingProxyType(_rows()))
    assert isinstance(projection.rows, MappingProxyType)
    with pytest.raises(TypeError):
        projection.rows["labs"] = ()  # type: ignore[index]
    assert tuple(projection.to_mapping()["resources"]) == SGA_ANCILLARY_RESOURCE_NAMES  # type: ignore[arg-type]

    rows = _rows()
    rows["labs"] = (ResourceRow("labs", tuple(reversed(rows["labs"][0].values))),)
    with pytest.raises(ValueError, match="field"):
        SgaAncillaryProjection(PATIENT_ID, _shape(), rows)
