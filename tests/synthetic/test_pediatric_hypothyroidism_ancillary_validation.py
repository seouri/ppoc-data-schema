from __future__ import annotations

import dataclasses
import json
from types import MappingProxyType

import pytest

from synthetic.models import DisorderKind
from synthetic.native.observations import (
    ObservationValidationStatus,
    RecordedEventKind,
    validate_observation_frame,
)
from synthetic.native.pediatric_hypothyroidism_ancillary import (
    PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_CHECK_NAMES,
    PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_REASON_CODES,
    PediatricHypothyroidismAncillaryCheck,
    PediatricHypothyroidismAncillaryProjection,
    PediatricHypothyroidismAncillaryProjectionUnavailable,
    PediatricHypothyroidismAncillaryValidationReport,
    PediatricHypothyroidismAncillaryValidationStatus,
    project_pediatric_hypothyroidism_ancillary_resources,
    validate_pediatric_hypothyroidism_ancillary_resources,
)
from synthetic.native.resources import ResourceRow
from tests.synthetic.test_pediatric_hypothyroidism_ancillary_projection import (
    _member,
    _policy_ancillary,
    _shape,
)

PATIENT_ID = "syn-observation-patient"


def _target() -> tuple[object, PediatricHypothyroidismAncillaryProjection]:
    member = _member()
    projection = project_pediatric_hypothyroidism_ancillary_resources(
        member, _shape(), _policy_ancillary()
    )
    return member, projection


def _check(
    report: object,
    name: str,
) -> tuple[PediatricHypothyroidismAncillaryValidationStatus, str]:
    item = next(check for check in report.checks if check.name == name)  # type: ignore[union-attr]
    return item.status, item.reason_code


def _replace_row(
    projection: PediatricHypothyroidismAncillaryProjection,
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


def _with_invalid_source(member: object) -> object:
    snapshot = dataclasses.replace(member)  # type: ignore[arg-type]
    object.__setattr__(snapshot.frame, "patient_id", "syn-invalid-frame-patient")
    return snapshot


def _source_variant(member: object, source_state: str) -> object:
    if source_state == "missing_truth":
        return _without_truth(member)
    return _with_invalid_source(member)


def test_validator_passes_target_and_non_target_with_fixed_checks() -> None:
    member, projection = _target()
    report = validate_pediatric_hypothyroidism_ancillary_resources(
        member, projection, _policy_ancillary()
    )

    assert report.status is PediatricHypothyroidismAncillaryValidationStatus.PASS
    assert tuple(check.name for check in report.checks) == (
        "pathway_scope",
        "row_schema",
        "causal_timing",
        "cross_resource_links",
        "source_evidence",
    )
    assert tuple(check.name for check in report.checks) == (
        PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_CHECK_NAMES
    )
    assert all(
        check.status is PediatricHypothyroidismAncillaryValidationStatus.PASS
        and check.reason_code == "OK"
        for check in report.checks
    )

    non_target = _member(kind=DisorderKind.GROWTH_HORMONE_DEFICIENCY)
    empty = project_pediatric_hypothyroidism_ancillary_resources(
        non_target, _shape(), _policy_ancillary()
    )
    non_target_report = validate_pediatric_hypothyroidism_ancillary_resources(
        non_target, empty, _policy_ancillary()
    )
    assert non_target_report.status is PediatricHypothyroidismAncillaryValidationStatus.PASS
    assert all(not empty.rows[resource_name] for resource_name in empty.rows)


def test_validation_models_have_fixed_order_and_status_precedence() -> None:
    assert tuple(
        status.value for status in PediatricHypothyroidismAncillaryValidationStatus
    ) == ("PASS", "FAIL", "UNEVALUABLE")
    assert PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_CHECK_NAMES == (
        "pathway_scope",
        "row_schema",
        "causal_timing",
        "cross_resource_links",
        "source_evidence",
    )
    assert "OK" in PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_REASON_CODES
    assert isinstance(PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_REASON_CODES, frozenset)

    checks = tuple(
        PediatricHypothyroidismAncillaryCheck(
            name,
            (
                PediatricHypothyroidismAncillaryValidationStatus.FAIL
                if name == "row_schema"
                else PediatricHypothyroidismAncillaryValidationStatus.UNEVALUABLE
                if name == "source_evidence"
                else PediatricHypothyroidismAncillaryValidationStatus.PASS
            ),
            (
                "ROW_SCHEMA_INVALID"
                if name == "row_schema"
                else "SOURCE_EVIDENCE_UNAVAILABLE"
                if name == "source_evidence"
                else "OK"
            ),
        )
        for name in reversed(PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_CHECK_NAMES)
    )
    report = PediatricHypothyroidismAncillaryValidationReport(
        PediatricHypothyroidismAncillaryValidationStatus.FAIL, checks
    )
    assert tuple(check.name for check in report.checks) == (
        PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_CHECK_NAMES
    )
    assert report.status is PediatricHypothyroidismAncillaryValidationStatus.FAIL
    assert report.check_counts == {"PASS": 3, "FAIL": 1, "UNEVALUABLE": 1}
    assert isinstance(report.check_counts, MappingProxyType)

    with pytest.raises(ValueError, match="status"):
        PediatricHypothyroidismAncillaryValidationReport(
            PediatricHypothyroidismAncillaryValidationStatus.PASS, checks
        )


def test_validator_rejects_wrong_fictional_constants_without_payload_leakage() -> None:
    member, projection = _target()
    _replace_row(
        projection,
        "labs",
        0,
        lambda row: _change_field(row, "result_flag", "REAL-LAB-FLAG"),
    )

    report = validate_pediatric_hypothyroidism_ancillary_resources(
        member, projection, _policy_ancillary()
    )
    rendered = repr(report) + json.dumps(report.to_mapping(), sort_keys=True)
    assert report.status is PediatricHypothyroidismAncillaryValidationStatus.FAIL
    assert _check(report, "row_schema") == (
        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
        "INVALID_VALUE",
    )
    assert "REAL-LAB-FLAG" not in rendered
    assert PATIENT_ID not in rendered
    assert "SYN-PEDIATRIC-HYPOTHYROIDISM" not in rendered


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
            "medications",
            0,
            "med_simple_generic_name",
            "Real medicine",
            "row_schema",
            "INVALID_VALUE",
        ),
        (
            "medications",
            0,
            "med_start_date_age_in_days",
            1400,
            "causal_timing",
            "TIMING_INVALID",
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

    report = validate_pediatric_hypothyroidism_ancillary_resources(
        member, projection, _policy_ancillary()
    )
    assert report.status is PediatricHypothyroidismAncillaryValidationStatus.FAIL
    assert _check(report, check_name) == (
        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
        reason,
    )


def test_validator_catches_duplicate_and_unexpected_medication_rows() -> None:
    member, projection = _target()
    rows = dict(projection.rows)
    rows["referrals"] = (rows["referrals"][0], rows["referrals"][0])
    object.__setattr__(projection, "rows", MappingProxyType(rows))
    report = validate_pediatric_hypothyroidism_ancillary_resources(
        member, projection, _policy_ancillary()
    )
    assert _check(report, "row_schema") == (
        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
        "DUPLICATE_ROW",
    )

    member, projection = _target()
    no_diagnosis = _member(diagnosed=False)
    projection = project_pediatric_hypothyroidism_ancillary_resources(
        no_diagnosis, _shape(), _policy_ancillary()
    )
    target_projection = _target()[1]
    rows = dict(projection.rows)
    rows["medications"] = target_projection.rows["medications"]
    object.__setattr__(projection, "rows", MappingProxyType(rows))
    report = validate_pediatric_hypothyroidism_ancillary_resources(
        no_diagnosis, projection, _policy_ancillary()
    )
    assert _check(report, "pathway_scope") == (
        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
        "PATHWAY_SCOPE_INVALID",
    )


def test_validator_rejects_malformed_rows_and_count_violations() -> None:
    member, projection = _target()
    rows = dict(projection.rows)
    rows["labs"] = ()
    object.__setattr__(projection, "rows", MappingProxyType(rows))
    report = validate_pediatric_hypothyroidism_ancillary_resources(
        member, projection, _policy_ancillary()
    )
    assert _check(report, "pathway_scope") == (
        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
        "PATHWAY_SCOPE_INVALID",
    )

    member, projection = _target()
    rows = dict(projection.rows)
    rows["labs"] = ("not-a-resource-row",)  # type: ignore[assignment]
    object.__setattr__(projection, "rows", MappingProxyType(rows))
    report = validate_pediatric_hypothyroidism_ancillary_resources(
        member, projection, _policy_ancillary()
    )
    assert _check(report, "row_schema") == (
        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
        "ROW_SCHEMA_INVALID",
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
    report = validate_pediatric_hypothyroidism_ancillary_resources(
        _without, projection, _policy_ancillary()  # type: ignore[arg-type]
    )
    assert report.status is PediatricHypothyroidismAncillaryValidationStatus.FAIL
    assert _check(report, "causal_timing") == (
        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
        "TIMING_INVALID",
    )


def test_validator_marks_missing_private_truth_unevaluable_unless_visible_rows_fail() -> None:
    member, projection = _target()
    report = validate_pediatric_hypothyroidism_ancillary_resources(
        _without_truth(member), projection, _policy_ancillary()  # type: ignore[arg-type]
    )
    assert report.status is PediatricHypothyroidismAncillaryValidationStatus.UNEVALUABLE
    assert _check(report, "source_evidence") == (
        PediatricHypothyroidismAncillaryValidationStatus.UNEVALUABLE,
        "SOURCE_EVIDENCE_UNAVAILABLE",
    )

    member, projection = _target()
    _replace_row(
        projection,
        "labs",
        0,
        lambda row: _change_field(row, "result_flag", "tampered"),
    )
    report = validate_pediatric_hypothyroidism_ancillary_resources(
        _without_truth(member), projection, _policy_ancillary()  # type: ignore[arg-type]
    )
    assert report.status is PediatricHypothyroidismAncillaryValidationStatus.FAIL
    assert _check(report, "row_schema")[0] is PediatricHypothyroidismAncillaryValidationStatus.FAIL
    assert _check(report, "source_evidence")[0] is PediatricHypothyroidismAncillaryValidationStatus.UNEVALUABLE


@pytest.mark.parametrize("source_state", ["missing_truth", "invalid_source"])
def test_visible_workup_count_failure_precedes_private_truth(
    source_state: str,
) -> None:
    member, projection = _target()
    rows = dict(projection.rows)
    rows["labs"] = ()
    object.__setattr__(projection, "rows", MappingProxyType(rows))

    member = _source_variant(member, source_state)
    report = validate_pediatric_hypothyroidism_ancillary_resources(
        member, projection, _policy_ancillary()  # type: ignore[arg-type]
    )
    assert report.status is PediatricHypothyroidismAncillaryValidationStatus.FAIL
    assert _check(report, "pathway_scope") == (
        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
        "PATHWAY_SCOPE_INVALID",
    )


@pytest.mark.parametrize("source_state", ["missing_truth", "invalid_source"])
def test_injected_referral_without_visible_events_fails_before_private_truth(
    source_state: str,
) -> None:
    member = _member(recognized=False, diagnosed=False)
    assert member.frame.events == ()
    projection = project_pediatric_hypothyroidism_ancillary_resources(
        member, _shape(), _policy_ancillary()
    )
    _target_member, target_projection = _target()
    rows = dict(projection.rows)
    rows["referrals"] = target_projection.rows["referrals"]
    object.__setattr__(projection, "rows", MappingProxyType(rows))

    member = _source_variant(member, source_state)
    report = validate_pediatric_hypothyroidism_ancillary_resources(
        member, projection, _policy_ancillary()  # type: ignore[arg-type]
    )
    assert report.status is PediatricHypothyroidismAncillaryValidationStatus.FAIL
    assert _check(report, "pathway_scope") == (
        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
        "PATHWAY_SCOPE_INVALID",
    )


@pytest.mark.parametrize("source_state", ["missing_truth", "invalid_source"])
def test_deleted_eligible_medication_fails_before_private_truth(
    source_state: str,
) -> None:
    member, projection = _target()
    rows = dict(projection.rows)
    rows["medications"] = ()
    object.__setattr__(projection, "rows", MappingProxyType(rows))

    member = _source_variant(member, source_state)
    report = validate_pediatric_hypothyroidism_ancillary_resources(
        member, projection, _policy_ancillary()  # type: ignore[arg-type]
    )
    assert report.status is PediatricHypothyroidismAncillaryValidationStatus.FAIL
    assert _check(report, "pathway_scope") == (
        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
        "PATHWAY_SCOPE_INVALID",
    )


@pytest.mark.parametrize("source_state", ["missing_truth", "invalid_source"])
def test_injected_medication_without_hidden_treatment_fails_before_private_truth(
    source_state: str,
) -> None:
    member = _member(treatment=False)
    projection = project_pediatric_hypothyroidism_ancillary_resources(
        member, _shape(), _policy_ancillary()
    )
    target_projection = _target()[1]
    rows = dict(projection.rows)
    rows["medications"] = target_projection.rows["medications"]
    object.__setattr__(projection, "rows", MappingProxyType(rows))

    member = _source_variant(member, source_state)
    report = validate_pediatric_hypothyroidism_ancillary_resources(
        member, projection, _policy_ancillary()  # type: ignore[arg-type]
    )
    assert report.status is PediatricHypothyroidismAncillaryValidationStatus.FAIL
    assert _check(report, "pathway_scope") == (
        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
        "PATHWAY_SCOPE_INVALID",
    )


def test_valid_frame_with_member_truth_binding_mismatch_is_invalid_source() -> None:
    member, projection = _target()
    changed_disorder = dataclasses.replace(
        member.trajectory.disorder,
        severity=0.7,
    )
    changed_trajectory = dataclasses.replace(
        member.trajectory,
        disorder=changed_disorder,
    )
    object.__setattr__(member, "trajectory", changed_trajectory)
    assert validate_observation_frame(member.frame).status is ObservationValidationStatus.PASS

    report = validate_pediatric_hypothyroidism_ancillary_resources(
        member, projection, _policy_ancillary()
    )
    assert report.status is PediatricHypothyroidismAncillaryValidationStatus.FAIL
    assert _check(report, "source_evidence") == (
        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
        "SOURCE_EVIDENCE_INVALID",
    )


@pytest.mark.parametrize("source_state", ["missing_truth", "invalid_source"])
def test_visible_event_age_failure_precedes_private_truth(source_state: str) -> None:
    member, projection = _target()
    visible_events = tuple(
        dataclasses.replace(
            event,
            age_days=730
            if event.event_kind is RecordedEventKind.RECOGNITION
            else 1500,
        )
        for event in member.frame.events
    )
    frame = dataclasses.replace(member.frame, events=visible_events)
    member = dataclasses.replace(member, frame=frame)
    _replace_row(
        projection,
        "referrals",
        0,
        lambda row: _change_field(row, "referral_date_age_in_days", 700),
    )
    for index in range(2):
        _replace_row(
            projection,
            "labs",
            index,
            lambda row: _change_field(row, "lab_order_date_age_in_days", 1400),
        )
        _replace_row(
            projection,
            "labs",
            index,
            lambda row: _change_field(row, "lab_result_date_age_in_days", 1407),
        )
    _replace_row(
        projection,
        "problem_list",
        0,
        lambda row: _change_field(row, "noted_date_age_in_days", 1400),
    )

    member = _source_variant(member, source_state)
    report = validate_pediatric_hypothyroidism_ancillary_resources(
        member, projection, _policy_ancillary()  # type: ignore[arg-type]
    )
    assert report.status is PediatricHypothyroidismAncillaryValidationStatus.FAIL
    assert _check(report, "causal_timing") == (
        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
        "TIMING_INVALID",
    )


@pytest.mark.parametrize("resource_name", ["labs", "medications", "referrals"])
@pytest.mark.parametrize("source_state", ["missing_truth", "invalid_source"])
def test_validator_checks_actual_visible_visit_ids_before_private_truth(
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

    member = _source_variant(member, source_state)
    report = validate_pediatric_hypothyroidism_ancillary_resources(
        member, projection, _policy_ancillary()  # type: ignore[arg-type]
    )
    assert report.status is PediatricHypothyroidismAncillaryValidationStatus.FAIL
    assert _check(report, "cross_resource_links") == (
        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
        "VISIT_REFERENCE_INVALID",
    )


def test_validator_rejects_treatment_before_visible_diagnosis() -> None:
    member, projection = _target()
    _replace_row(
        projection,
        "medications",
        0,
        lambda row: _change_field(row, "med_start_date_age_in_days", 1400),
    )
    report = validate_pediatric_hypothyroidism_ancillary_resources(
        member, projection, _policy_ancillary()
    )
    assert _check(report, "causal_timing") == (
        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
        "TIMING_INVALID",
    )


def test_validator_reports_invalid_source_and_redacts_details() -> None:
    member, projection = _target()
    report = validate_pediatric_hypothyroidism_ancillary_resources(
        _with_invalid_source(member), projection, _policy_ancillary()  # type: ignore[arg-type]
    )
    assert report.status is PediatricHypothyroidismAncillaryValidationStatus.FAIL
    assert _check(report, "source_evidence") == (
        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
        "SOURCE_EVIDENCE_INVALID",
    )


def test_validator_rejects_wrong_typed_inputs_at_one_fixed_error_boundary() -> None:
    _member_value, projection = _target()
    with pytest.raises(
        PediatricHypothyroidismAncillaryProjectionUnavailable,
        match="^pediatric hypothyroidism ancillary projection unavailable$",
    ):
        validate_pediatric_hypothyroidism_ancillary_resources(  # type: ignore[arg-type]
            object(), projection, _policy_ancillary()
        )


def test_validation_report_and_mapping_are_aggregate_only_and_immutable() -> None:
    member, projection = _target()
    report = validate_pediatric_hypothyroidism_ancillary_resources(
        member, projection, _policy_ancillary()
    )
    encoded = json.dumps(report.to_mapping(), sort_keys=True)
    assert tuple(report.to_mapping()) == ("status", "check_counts", "checks")
    assert "patient" not in encoded
    assert "row_id" not in encoded
    assert "truth" not in encoded
    assert "SYN-PEDIATRIC-HYPOTHYROIDISM" not in encoded
    assert "patient" not in repr(report).lower()
    assert "truth" not in repr(report).lower()
    assert isinstance(report.check_counts, MappingProxyType)
    with pytest.raises(TypeError):
        report.check_counts["PASS"] = 0  # type: ignore[index]
