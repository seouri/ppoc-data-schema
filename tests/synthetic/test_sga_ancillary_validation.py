from __future__ import annotations

import dataclasses
import json
from types import MappingProxyType

import pytest

from synthetic.models import DisorderKind
from synthetic.native.observations import ObservationValidationStatus, validate_observation_frame
from synthetic.native.resources import ResourceRow
from synthetic.native.sga_ancillary import (
    SGA_ANCILLARY_CHECK_NAMES,
    SGA_ANCILLARY_REASON_CODES,
    SgaAncillaryCheck,
    SgaAncillaryProjection,
    SgaAncillaryProjectionUnavailable,
    SgaAncillaryValidationReport,
    SgaAncillaryValidationStatus,
    project_sga_ancillary_resources,
    validate_sga_ancillary_resources,
)
from tests.synthetic.test_sga_ancillary_projection import _member, _policy_ancillary, _shape

PATIENT_ID = "syn-observation-patient"


def _target() -> tuple[object, SgaAncillaryProjection]:
    member = _member()
    return member, project_sga_ancillary_resources(member, _shape(), _policy_ancillary())


def _check(report: object, name: str) -> tuple[SgaAncillaryValidationStatus, str]:
    item = next(check for check in report.checks if check.name == name)  # type: ignore[union-attr]
    return item.status, item.reason_code


def _replace_row(
    projection: SgaAncillaryProjection, resource_name: str, index: int, transform: object
) -> None:
    rows = dict(projection.rows)
    current = rows[resource_name][index]
    rows[resource_name] = (
        *rows[resource_name][:index],
        transform(current),  # type: ignore[operator]
        *rows[resource_name][index + 1 :],
    )
    object.__setattr__(projection, "rows", MappingProxyType(rows))


def _change_field(row: ResourceRow, field_name: str, value: object) -> ResourceRow:
    return ResourceRow(
        row.resource_name,
        tuple((name, value if name == field_name else current) for name, current in row.values),
    )


def _without_truth(member: object) -> object:
    frame = dataclasses.replace(member.frame)  # type: ignore[union-attr]
    object.__setattr__(frame, "truth", None)
    return dataclasses.replace(member, frame=frame)  # type: ignore[arg-type]


def _invalid_source(member: object) -> object:
    snapshot = dataclasses.replace(member)  # type: ignore[arg-type]
    object.__setattr__(snapshot.frame, "patient_id", "syn-invalid-frame-patient")
    return snapshot


def test_validator_passes_target_and_non_target_with_fixed_checks() -> None:
    member, projection = _target()
    report = validate_sga_ancillary_resources(member, projection, _policy_ancillary())
    assert report.status is SgaAncillaryValidationStatus.PASS
    assert tuple(check.name for check in report.checks) == SGA_ANCILLARY_CHECK_NAMES
    assert all(check.status is SgaAncillaryValidationStatus.PASS and check.reason_code == "OK" for check in report.checks)

    other = _member(kind=DisorderKind.CELIAC_DISEASE)
    empty = project_sga_ancillary_resources(other, _shape(), _policy_ancillary())
    assert validate_sga_ancillary_resources(other, empty, _policy_ancillary()).status is SgaAncillaryValidationStatus.PASS


def test_validation_models_are_fixed_order_immutable_and_redacted() -> None:
    assert tuple(status.value for status in SgaAncillaryValidationStatus) == ("PASS", "FAIL", "UNEVALUABLE")
    assert SGA_ANCILLARY_CHECK_NAMES == ("pathway_scope", "row_schema", "causal_timing", "cross_resource_links", "source_evidence")
    assert "OK" in SGA_ANCILLARY_REASON_CODES
    checks = tuple(
        SgaAncillaryCheck(
            name,
            SgaAncillaryValidationStatus.FAIL if name == "row_schema" else SgaAncillaryValidationStatus.UNEVALUABLE if name == "source_evidence" else SgaAncillaryValidationStatus.PASS,
            "ROW_SCHEMA_INVALID" if name == "row_schema" else "SOURCE_EVIDENCE_UNAVAILABLE" if name == "source_evidence" else "OK",
        )
        for name in reversed(SGA_ANCILLARY_CHECK_NAMES)
    )
    report = SgaAncillaryValidationReport(SgaAncillaryValidationStatus.FAIL, checks)
    assert tuple(check.name for check in report.checks) == SGA_ANCILLARY_CHECK_NAMES
    assert report.check_counts == {"PASS": 3, "FAIL": 1, "UNEVALUABLE": 1}
    assert isinstance(report.check_counts, MappingProxyType)
    encoded = repr(report) + json.dumps(report.to_mapping(), sort_keys=True)
    assert PATIENT_ID not in encoded and "SYN-SGA" not in encoded and "truth" not in encoded
    with pytest.raises(TypeError):
        report.check_counts["PASS"] = 0  # type: ignore[index]


@pytest.mark.parametrize(
    ("resource_name", "index", "field_name", "value", "check_name", "reason"),
    [
        ("labs", 0, "lab_order_id", "syn-tampered-order", "row_schema", "INVALID_ID"),
        ("labs", 0, "result_component_name", "SYN-WRONG", "row_schema", "INVALID_CODE"),
        ("labs", 0, "result_line_num", 1.0, "row_schema", "INVALID_VALUE"),
        ("labs", 0, "lab_result_date_age_in_days", 1201, "causal_timing", "TIMING_INVALID"),
        ("labs", 0, "visit_id", "syn-missing-visit", "cross_resource_links", "VISIT_REFERENCE_INVALID"),
        ("problem_list", 0, "pl_diag", "SYN-WRONG", "row_schema", "INVALID_CODE"),
        ("problem_list", 0, "resolved_date_age_in_days", 1, "row_schema", "INVALID_VALUE"),
        ("referrals", 0, "patient_id", "syn-other-patient", "cross_resource_links", "PATIENT_MISMATCH"),
    ],
)
def test_validator_catches_visible_tampering(
    resource_name: str, index: int, field_name: str, value: object, check_name: str, reason: str
) -> None:
    member, projection = _target()
    _replace_row(projection, resource_name, index, lambda row: _change_field(row, field_name, value))
    report = validate_sga_ancillary_resources(member, projection, _policy_ancillary())
    assert report.status is SgaAncillaryValidationStatus.FAIL
    assert _check(report, check_name) == (SgaAncillaryValidationStatus.FAIL, reason)


def test_validator_rejects_counts_duplicates_and_any_medication() -> None:
    member, projection = _target()
    rows = dict(projection.rows)
    rows["referrals"] = (rows["referrals"][0], rows["referrals"][0])
    object.__setattr__(projection, "rows", MappingProxyType(rows))
    assert _check(validate_sga_ancillary_resources(member, projection, _policy_ancillary()), "row_schema") == (SgaAncillaryValidationStatus.FAIL, "DUPLICATE_ROW")

    member, projection = _target()
    rows = dict(projection.rows)
    rows["medications"] = (projection.rows["referrals"][0],)
    object.__setattr__(projection, "rows", MappingProxyType(rows))
    assert _check(validate_sga_ancillary_resources(member, projection, _policy_ancillary()), "pathway_scope") == (SgaAncillaryValidationStatus.FAIL, "PATHWAY_SCOPE_INVALID")


@pytest.mark.parametrize("source", [_without_truth, _invalid_source])
def test_visible_failures_precede_missing_or_invalid_private_source(source: object) -> None:
    member, projection = _target()
    rows = dict(projection.rows)
    rows["labs"] = ()
    object.__setattr__(projection, "rows", MappingProxyType(rows))
    report = validate_sga_ancillary_resources(source(member), projection, _policy_ancillary())  # type: ignore[arg-type, operator]
    assert report.status is SgaAncillaryValidationStatus.FAIL
    assert _check(report, "pathway_scope") == (SgaAncillaryValidationStatus.FAIL, "PATHWAY_SCOPE_INVALID")


def test_missing_source_is_unevaluable_only_without_visible_failure() -> None:
    member, projection = _target()
    report = validate_sga_ancillary_resources(_without_truth(member), projection, _policy_ancillary())  # type: ignore[arg-type]
    assert report.status is SgaAncillaryValidationStatus.UNEVALUABLE
    assert _check(report, "source_evidence") == (SgaAncillaryValidationStatus.UNEVALUABLE, "SOURCE_EVIDENCE_UNAVAILABLE")


def test_valid_frame_member_trajectory_mismatch_is_invalid_source() -> None:
    member, projection = _target()
    changed = dataclasses.replace(member.trajectory, disorder=dataclasses.replace(member.trajectory.disorder, severity=0.8))
    object.__setattr__(member, "trajectory", changed)
    assert validate_observation_frame(member.frame).status is ObservationValidationStatus.PASS
    report = validate_sga_ancillary_resources(member, projection, _policy_ancillary())
    assert _check(report, "source_evidence") == (SgaAncillaryValidationStatus.FAIL, "SOURCE_EVIDENCE_INVALID")


def test_validator_requires_the_workup_source_visit_after_truth_binds() -> None:
    member, projection = _target()
    workup_visit = projection.rows["labs"][0].to_mapping()["visit_id"]
    other_visit = next(visit.visit_id for visit in member.frame.visits if visit.visit_id != workup_visit)
    for index in range(2):
        _replace_row(projection, "labs", index, lambda row: _change_field(row, "visit_id", other_visit))
    report = validate_sga_ancillary_resources(member, projection, _policy_ancillary())
    assert _check(report, "cross_resource_links") == (
        SgaAncillaryValidationStatus.FAIL,
        "VISIT_REFERENCE_INVALID",
    )


def test_validator_has_one_redacted_typed_input_boundary() -> None:
    _member_value, projection = _target()
    with pytest.raises(SgaAncillaryProjectionUnavailable, match="^sga ancillary projection unavailable$"):
        validate_sga_ancillary_resources(object(), projection, _policy_ancillary())  # type: ignore[arg-type]
