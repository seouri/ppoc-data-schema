from __future__ import annotations

import dataclasses
import json
from types import MappingProxyType

import pytest

from synthetic.models import DisorderKind
from synthetic.native.excess_weight_ancillary import (
    EXCESS_WEIGHT_ANCILLARY_CHECK_NAMES,
    EXCESS_WEIGHT_ANCILLARY_REASON_CODES,
    ExcessWeightAncillaryCheck,
    ExcessWeightAncillaryProjection,
    ExcessWeightAncillaryProjectionUnavailable,
    ExcessWeightAncillaryValidationReport,
    ExcessWeightAncillaryValidationStatus,
    project_excess_weight_ancillary_resources,
    validate_excess_weight_ancillary_resources,
)
from synthetic.native.observations import RecordedEventKind
from synthetic.native.resources import ResourceRow
from tests.synthetic.test_excess_weight_ancillary_projection import (
    _member,
    _policy_ancillary,
    _shape,
)

PATIENT_ID = "syn-observation-patient"


def _target() -> tuple[object, ExcessWeightAncillaryProjection]:
    member = _member()
    projection = project_excess_weight_ancillary_resources(
        member, _shape(), _policy_ancillary()
    )
    return member, projection


def _check(report: object, name: str) -> tuple[ExcessWeightAncillaryValidationStatus, str]:
    item = next(check for check in report.checks if check.name == name)  # type: ignore[union-attr]
    return item.status, item.reason_code


def _replace_row(
    projection: ExcessWeightAncillaryProjection,
    resource_name: str,
    index: int,
    transform: object,
) -> None:
    rows = dict(projection.rows)
    current = rows[resource_name][index]
    replacement = transform(current)  # type: ignore[operator]
    rows[resource_name] = (
        *rows[resource_name][:index],
        replacement,
        *rows[resource_name][index + 1 :],
    )
    object.__setattr__(projection, "rows", MappingProxyType(rows))


def _change_field(row: ResourceRow, field_name: str, value: object) -> ResourceRow:
    return ResourceRow(
        row.resource_name,
        tuple(
            (name, value if name == field_name else current)
            for name, current in row.values
        ),
    )


def _without_truth(member: object) -> object:
    frame = dataclasses.replace(member.frame)  # type: ignore[union-attr]
    object.__setattr__(frame, "truth", None)
    return dataclasses.replace(member, frame=frame)  # type: ignore[arg-type]


def test_validator_passes_target_and_non_target_with_fixed_checks() -> None:
    member, projection = _target()
    report = validate_excess_weight_ancillary_resources(
        member, projection, _policy_ancillary()
    )

    assert report.status is ExcessWeightAncillaryValidationStatus.PASS
    assert tuple(check.name for check in report.checks) == EXCESS_WEIGHT_ANCILLARY_CHECK_NAMES
    assert all(
        check.status is ExcessWeightAncillaryValidationStatus.PASS
        and check.reason_code == "OK"
        for check in report.checks
    )

    non_target = _member(kind=DisorderKind.FAMILIAL_SHORT_STATURE)
    empty = project_excess_weight_ancillary_resources(
        non_target, _shape(), _policy_ancillary()
    )
    non_target_report = validate_excess_weight_ancillary_resources(
        non_target, empty, _policy_ancillary()
    )
    assert non_target_report.status is ExcessWeightAncillaryValidationStatus.PASS
    assert all(
        not empty.rows[resource_name]
        for resource_name in empty.rows
    )


def test_validation_models_have_fixed_order_and_status_precedence() -> None:
    assert tuple(status.value for status in ExcessWeightAncillaryValidationStatus) == (
        "PASS",
        "FAIL",
        "UNEVALUABLE",
    )
    assert EXCESS_WEIGHT_ANCILLARY_CHECK_NAMES == (
        "pathway_scope",
        "row_schema",
        "causal_timing",
        "cross_resource_links",
        "source_evidence",
    )
    assert "OK" in EXCESS_WEIGHT_ANCILLARY_REASON_CODES
    assert isinstance(EXCESS_WEIGHT_ANCILLARY_REASON_CODES, frozenset)

    checks = tuple(
        ExcessWeightAncillaryCheck(
            name,
            (
                ExcessWeightAncillaryValidationStatus.FAIL
                if name == "row_schema"
                else ExcessWeightAncillaryValidationStatus.UNEVALUABLE
                if name == "source_evidence"
                else ExcessWeightAncillaryValidationStatus.PASS
            ),
            (
                "ROW_SCHEMA_INVALID"
                if name == "row_schema"
                else "SOURCE_EVIDENCE_UNAVAILABLE"
                if name == "source_evidence"
                else "OK"
            ),
        )
        for name in reversed(EXCESS_WEIGHT_ANCILLARY_CHECK_NAMES)
    )
    report = ExcessWeightAncillaryValidationReport(
        ExcessWeightAncillaryValidationStatus.FAIL, checks
    )
    assert tuple(check.name for check in report.checks) == EXCESS_WEIGHT_ANCILLARY_CHECK_NAMES
    assert report.status is ExcessWeightAncillaryValidationStatus.FAIL
    assert report.check_counts == {"PASS": 3, "FAIL": 1, "UNEVALUABLE": 1}
    assert isinstance(report.check_counts, MappingProxyType)

    with pytest.raises(ValueError, match="status"):
        ExcessWeightAncillaryValidationReport(
            ExcessWeightAncillaryValidationStatus.PASS, checks
        )


def test_validator_rejects_wrong_fictional_constants_without_payload_leakage() -> None:
    member, projection = _target()
    _replace_row(
        projection,
        "labs",
        0,
        lambda row: _change_field(row, "result_flag", "REAL-LAB-FLAG"),
    )

    report = validate_excess_weight_ancillary_resources(
        member, projection, _policy_ancillary()
    )
    rendered = repr(report) + json.dumps(report.to_mapping(), sort_keys=True)
    assert report.status is ExcessWeightAncillaryValidationStatus.FAIL
    assert _check(report, "row_schema") == (
        ExcessWeightAncillaryValidationStatus.FAIL,
        "INVALID_VALUE",
    )
    assert "REAL-LAB-FLAG" not in rendered
    assert PATIENT_ID not in rendered
    assert "SYN-EXCESS-WEIGHT" not in rendered


@pytest.mark.parametrize(
    ("resource_name", "index", "field_name", "value", "check_name", "reason"),
    [
        (
            "labs",
            0,
            "lab_order_id",
            "syn-tampered-order",
            "row_schema",
            "INVALID_ID",
        ),
        (
            "labs",
            0,
            "result_component_name",
            "SYN-WRONG-COMPONENT",
            "row_schema",
            "INVALID_CODE",
        ),
        (
            "labs",
            0,
            "result_line_num",
            1.0,
            "row_schema",
            "INVALID_VALUE",
        ),
        (
            "labs",
            0,
            "lab_result_date_age_in_days",
            1201,
            "causal_timing",
            "TIMING_INVALID",
        ),
        (
            "labs",
            0,
            "visit_id",
            "syn-other-visit",
            "cross_resource_links",
            "VISIT_REFERENCE_INVALID",
        ),
        (
            "problem_list",
            0,
            "pl_diag",
            "SYN-WRONG-DIAGNOSIS",
            "row_schema",
            "INVALID_CODE",
        ),
        (
            "problem_list",
            0,
            "resolved_date_age_in_days",
            1,
            "row_schema",
            "INVALID_VALUE",
        ),
        (
            "referrals",
            0,
            "patient_id",
            "syn-other-patient",
            "cross_resource_links",
            "PATIENT_MISMATCH",
        ),
    ],
)
def test_validator_catches_visible_row_tampering(
    resource_name: str,
    index: int,
    field_name: str,
    value: object,
    check_name: str,
    reason: str,
) -> None:
    member, projection = _target()
    _replace_row(
        projection,
        resource_name,
        index,
        lambda row: _change_field(row, field_name, value),
    )

    report = validate_excess_weight_ancillary_resources(
        member, projection, _policy_ancillary()
    )
    assert report.status is ExcessWeightAncillaryValidationStatus.FAIL
    assert _check(report, check_name) == (
        ExcessWeightAncillaryValidationStatus.FAIL,
        reason,
    )


def test_validator_catches_duplicate_and_forbidden_medication_rows() -> None:
    member, projection = _target()
    rows = dict(projection.rows)
    rows["referrals"] = (rows["referrals"][0], rows["referrals"][0])
    object.__setattr__(projection, "rows", MappingProxyType(rows))
    report = validate_excess_weight_ancillary_resources(
        member, projection, _policy_ancillary()
    )
    assert _check(report, "row_schema") == (
        ExcessWeightAncillaryValidationStatus.FAIL,
        "DUPLICATE_ROW",
    )

    member, projection = _target()
    medication_shape = projection.shape.field_names("medications")
    medication = ResourceRow(
        "medications",
        tuple(
            (
                name,
                member.demographics.patient_id
                if name == "patient_id"
                else "syn-excess-weight-medication-visit"
                if name == "visit_id"
                else ""
            )
            for name in medication_shape
        ),
    )
    rows = dict(projection.rows)
    rows["medications"] = (medication,)
    object.__setattr__(projection, "rows", MappingProxyType(rows))
    report = validate_excess_weight_ancillary_resources(
        member, projection, _policy_ancillary()
    )
    assert report.status is ExcessWeightAncillaryValidationStatus.FAIL
    assert _check(report, "pathway_scope") == (
        ExcessWeightAncillaryValidationStatus.FAIL,
        "PATHWAY_SCOPE_INVALID",
    )


def test_validator_rejects_reversed_visible_event_ages_without_private_truth() -> None:
    member, projection = _target()
    _without = _without_truth(member)
    _replace_row(
        projection,
        "problem_list",
        0,
        lambda row: _change_field(row, "noted_date_age_in_days", 1000),
    )
    report = validate_excess_weight_ancillary_resources(
        _without, projection, _policy_ancillary()  # type: ignore[arg-type]
    )
    assert report.status is ExcessWeightAncillaryValidationStatus.FAIL
    assert _check(report, "causal_timing") == (
        ExcessWeightAncillaryValidationStatus.FAIL,
        "TIMING_INVALID",
    )


def test_validator_marks_missing_private_truth_unevaluable_unless_visible_rows_fail() -> None:
    member, projection = _target()
    report = validate_excess_weight_ancillary_resources(
        _without_truth(member), projection, _policy_ancillary()  # type: ignore[arg-type]
    )
    assert report.status is ExcessWeightAncillaryValidationStatus.UNEVALUABLE
    assert _check(report, "source_evidence") == (
        ExcessWeightAncillaryValidationStatus.UNEVALUABLE,
        "SOURCE_EVIDENCE_UNAVAILABLE",
    )

    member, projection = _target()
    _replace_row(
        projection,
        "labs",
        0,
        lambda row: _change_field(row, "result_flag", "tampered"),
    )
    report = validate_excess_weight_ancillary_resources(
        _without_truth(member), projection, _policy_ancillary()  # type: ignore[arg-type]
    )
    assert report.status is ExcessWeightAncillaryValidationStatus.FAIL
    assert _check(report, "row_schema")[0] is ExcessWeightAncillaryValidationStatus.FAIL
    assert _check(report, "source_evidence")[0] is ExcessWeightAncillaryValidationStatus.UNEVALUABLE


@pytest.mark.parametrize("resource_name", ["labs", "referrals"])
@pytest.mark.parametrize("source_state", ["missing_truth", "invalid"])
def test_validator_rejects_nonexistent_visible_visit_without_source_evidence(
    resource_name: str,
    source_state: str,
) -> None:
    member, projection = _target()
    nonexistent_visit_id = "syn-not-visible-visit"
    rows = dict(projection.rows)
    rows[resource_name] = tuple(
        _change_field(row, "visit_id", nonexistent_visit_id)
        for row in rows[resource_name]
    )
    object.__setattr__(projection, "rows", MappingProxyType(rows))

    if source_state == "missing_truth":
        member = _without_truth(member)  # type: ignore[assignment]
    else:
        frame = dataclasses.replace(member.frame)
        events = list(frame.events)
        diagnosis = next(
            index
            for index, event in enumerate(events)
            if event.event_kind is RecordedEventKind.DIAGNOSIS
        )
        events[diagnosis] = dataclasses.replace(events[diagnosis], age_days=1)
        object.__setattr__(frame, "events", tuple(events))
        member = dataclasses.replace(member, frame=frame)

    report = validate_excess_weight_ancillary_resources(
        member, projection, _policy_ancillary()  # type: ignore[arg-type]
    )
    assert report.status is ExcessWeightAncillaryValidationStatus.FAIL
    assert _check(report, "cross_resource_links") == (
        ExcessWeightAncillaryValidationStatus.FAIL,
        "VISIT_REFERENCE_INVALID",
    )
    expected_source_status = (
        ExcessWeightAncillaryValidationStatus.UNEVALUABLE
        if source_state == "missing_truth"
        else ExcessWeightAncillaryValidationStatus.FAIL
    )
    expected_source_reason = (
        "SOURCE_EVIDENCE_UNAVAILABLE"
        if source_state == "missing_truth"
        else "SOURCE_EVIDENCE_INVALID"
    )
    assert _check(report, "source_evidence") == (
        expected_source_status,
        expected_source_reason,
    )


def test_validator_rejects_wrong_typed_inputs_at_one_fixed_error_boundary() -> None:
    _member_value, projection = _target()
    with pytest.raises(
        ExcessWeightAncillaryProjectionUnavailable,
        match="^excess-weight ancillary projection unavailable$",
    ):
        validate_excess_weight_ancillary_resources(  # type: ignore[arg-type]
            object(), projection, _policy_ancillary()
        )


def test_validator_marks_invalid_source_evidence_as_failed() -> None:
    member, projection = _target()
    frame = dataclasses.replace(member.frame)
    events = list(frame.events)
    diagnosis = next(
        index
        for index, event in enumerate(events)
        if event.event_kind is RecordedEventKind.DIAGNOSIS
    )
    events[diagnosis] = dataclasses.replace(events[diagnosis], age_days=1)
    object.__setattr__(frame, "events", tuple(events))
    invalid_member = dataclasses.replace(member, frame=frame)

    report = validate_excess_weight_ancillary_resources(
        invalid_member, projection, _policy_ancillary()
    )
    assert report.status is ExcessWeightAncillaryValidationStatus.FAIL
    assert _check(report, "source_evidence") == (
        ExcessWeightAncillaryValidationStatus.FAIL,
        "SOURCE_EVIDENCE_INVALID",
    )


def test_validation_report_and_mapping_are_aggregate_only_and_immutable() -> None:
    member, projection = _target()
    report = validate_excess_weight_ancillary_resources(
        member, projection, _policy_ancillary()
    )
    encoded = json.dumps(report.to_mapping(), sort_keys=True)
    assert tuple(report.to_mapping()) == ("status", "check_counts", "checks")
    assert "patient" not in encoded
    assert "row_id" not in encoded
    assert "truth" not in encoded
    assert "SYN-EXCESS-WEIGHT" not in encoded
    assert "patient" not in repr(report).lower()
    assert "truth" not in repr(report).lower()
    assert isinstance(report.check_counts, MappingProxyType)
    with pytest.raises(TypeError):
        report.check_counts["PASS"] = 0  # type: ignore[index]
