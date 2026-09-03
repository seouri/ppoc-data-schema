from __future__ import annotations

import dataclasses
import json
from types import MappingProxyType

import pytest

from synthetic.models import DisorderKind
from synthetic.native.observations import (
    ObservationValidationStatus,
    validate_observation_frame,
)
from synthetic.native.resources import ResourceRow
from synthetic.native.turner_ancillary import (
    TURNER_ANCILLARY_CHECK_NAMES,
    TURNER_ANCILLARY_REASON_CODES,
    TURNER_DIAGNOSIS_CODE,
    TurnerAncillaryCheck,
    TurnerAncillaryProjection,
    TurnerAncillaryProjectionUnavailable,
    TurnerAncillaryValidationReport,
    TurnerAncillaryValidationStatus,
    project_turner_ancillary_resources,
    validate_turner_ancillary_resources,
)
from tests.synthetic.test_turner_ancillary_projection import (
    _member,
    _policy_ancillary,
    _shape,
)

PATIENT_ID = "syn-observation-patient"


def _target(**member_kwargs: object) -> tuple[object, TurnerAncillaryProjection]:
    member = _member(**member_kwargs)
    projection = project_turner_ancillary_resources(
        member, _shape(), _policy_ancillary()
    )
    return member, projection


def _check(
    report: TurnerAncillaryValidationReport,
    name: str,
) -> TurnerAncillaryCheck:
    return next(check for check in report.checks if check.name == name)


def _replace_rows(
    projection: TurnerAncillaryProjection,
    resource_name: str,
    rows: tuple[ResourceRow, ...],
) -> None:
    replacement = dict(projection.rows)
    replacement[resource_name] = rows
    object.__setattr__(projection, "rows", MappingProxyType(replacement))


def _unsafe_change_field(
    row: ResourceRow,
    field_name: str,
    value: object,
) -> ResourceRow:
    object.__setattr__(
        row,
        "values",
        tuple(
            (name, value if name == field_name else current)
            for name, current in row.values
        ),
    )
    return row


def _change_field(
    projection: TurnerAncillaryProjection,
    resource_name: str,
    index: int,
    field_name: str,
    value: object,
) -> None:
    rows = list(projection.rows[resource_name])
    rows[index] = _unsafe_change_field(rows[index], field_name, value)
    _replace_rows(projection, resource_name, tuple(rows))


def _without_truth(member: object) -> object:
    frame = dataclasses.replace(member.frame)  # type: ignore[union-attr]
    object.__setattr__(frame, "truth", None)
    return dataclasses.replace(member, frame=frame)  # type: ignore[arg-type]


def _malformed_truth(member: object) -> object:
    frame = dataclasses.replace(member.frame)  # type: ignore[union-attr]
    object.__setattr__(frame, "truth", object())
    return dataclasses.replace(member, frame=frame)  # type: ignore[arg-type]


def _invalid_frame_binding(member: object) -> object:
    snapshot = dataclasses.replace(member)  # type: ignore[arg-type]
    object.__setattr__(snapshot.frame, "patient_id", "syn-invalid-frame-patient")
    return snapshot


def _invalid_source_events(member: object) -> object:
    snapshot = dataclasses.replace(member)  # type: ignore[arg-type]
    truth = snapshot.frame.truth
    source_events = list(truth.source_events)
    source_events[0] = dataclasses.replace(source_events[0], age_days=1)
    object.__setattr__(truth, "source_events", tuple(source_events))
    return snapshot


def test_validator_passes_target_and_non_target_with_fixed_checks() -> None:
    member, projection = _target()
    report = validate_turner_ancillary_resources(
        member, projection, _policy_ancillary()
    )

    assert report.status is TurnerAncillaryValidationStatus.PASS
    assert tuple(check.name for check in report.checks) == (
        "pathway_scope",
        "row_schema",
        "causal_timing",
        "cross_resource_links",
        "source_evidence",
    )
    assert tuple(check.name for check in report.checks) == (
        TURNER_ANCILLARY_CHECK_NAMES
    )
    assert all(
        check.status is TurnerAncillaryValidationStatus.PASS
        and check.reason_code == "OK"
        for check in report.checks
    )
    assert report.check_counts == {"PASS": 5, "FAIL": 0, "UNEVALUABLE": 0}

    non_target = _member(kind=DisorderKind.GROWTH_HORMONE_DEFICIENCY)
    empty = project_turner_ancillary_resources(
        non_target, _shape(), _policy_ancillary()
    )
    non_target_report = validate_turner_ancillary_resources(
        non_target, empty, _policy_ancillary()
    )
    assert non_target_report.status is TurnerAncillaryValidationStatus.PASS
    assert all(not empty.rows[resource_name] for resource_name in empty.rows)


def test_validation_models_have_fixed_order_reason_codes_and_precedence() -> None:
    assert tuple(
        status.value for status in TurnerAncillaryValidationStatus
    ) == ("PASS", "FAIL", "UNEVALUABLE")
    assert TURNER_ANCILLARY_CHECK_NAMES == (
        "pathway_scope",
        "row_schema",
        "causal_timing",
        "cross_resource_links",
        "source_evidence",
    )
    assert isinstance(TURNER_ANCILLARY_REASON_CODES, frozenset)
    assert "OK" in TURNER_ANCILLARY_REASON_CODES

    checks = tuple(
        TurnerAncillaryCheck(
            name,
            (
                TurnerAncillaryValidationStatus.FAIL
                if name == "row_schema"
                else TurnerAncillaryValidationStatus.UNEVALUABLE
                if name == "source_evidence"
                else TurnerAncillaryValidationStatus.PASS
            ),
            (
                "ROW_SCHEMA_INVALID"
                if name == "row_schema"
                else "SOURCE_EVIDENCE_UNAVAILABLE"
                if name == "source_evidence"
                else "OK"
            ),
        )
        for name in reversed(TURNER_ANCILLARY_CHECK_NAMES)
    )
    report = TurnerAncillaryValidationReport(
        TurnerAncillaryValidationStatus.FAIL, checks
    )
    assert tuple(check.name for check in report.checks) == TURNER_ANCILLARY_CHECK_NAMES
    assert report.status is TurnerAncillaryValidationStatus.FAIL
    assert report.check_counts == {"PASS": 3, "FAIL": 1, "UNEVALUABLE": 1}
    with pytest.raises(TypeError):
        report.check_counts["PASS"] = 0  # type: ignore[index]

    unevaluable_checks = tuple(
        TurnerAncillaryCheck(
            name,
            TurnerAncillaryValidationStatus.UNEVALUABLE,
            "SOURCE_EVIDENCE_UNAVAILABLE",
        )
        for name in TURNER_ANCILLARY_CHECK_NAMES
    )
    unevaluable_report = TurnerAncillaryValidationReport(
        TurnerAncillaryValidationStatus.UNEVALUABLE, unevaluable_checks
    )
    assert unevaluable_report.status is TurnerAncillaryValidationStatus.UNEVALUABLE

    with pytest.raises(ValueError, match="status"):
        TurnerAncillaryValidationReport(
            TurnerAncillaryValidationStatus.PASS, checks
        )


@pytest.mark.parametrize(
    (
        "resource_name",
        "index",
        "field_name",
        "value",
        "check_name",
        "reason",
    ),
    [
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
            "result_flag",
            "Wrong marker",
            "row_schema",
            "INVALID_VALUE",
        ),
        (
            "referrals",
            0,
            "requested_specialty",
            "Wrong specialty",
            "row_schema",
            "INVALID_VALUE",
        ),
        (
            "medications",
            0,
            "med_simple_generic_name",
            "Wrong intervention",
            "row_schema",
            "INVALID_VALUE",
        ),
        (
            "medications",
            0,
            "med_record_type",
            "External",
            "row_schema",
            "INVALID_VALUE",
        ),
        (
            "labs",
            0,
            "lab_order_id",
            "syn-tampered-order",
            "row_schema",
            "INVALID_ID",
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
            "labs",
            0,
            "result_line_num",
            1.0,
            "row_schema",
            "INVALID_VALUE",
        ),
        (
            "problem_list",
            0,
            "resolved_date_age_in_days",
            0,
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
    _change_field(projection, resource_name, index, field_name, value)

    report = validate_turner_ancillary_resources(
        member, projection, _policy_ancillary()
    )
    assert report.status is TurnerAncillaryValidationStatus.FAIL
    check = _check(report, check_name)
    assert (check.status, check.reason_code) == (
        TurnerAncillaryValidationStatus.FAIL,
        reason,
    )


def test_validator_rejects_wrong_constants_and_never_leaks_payload() -> None:
    member, projection = _target()
    _change_field(projection, "labs", 0, "result_flag", "REAL-LAB-FLAG")
    report = validate_turner_ancillary_resources(
        member, projection, _policy_ancillary()
    )
    rendered = repr(report) + json.dumps(report.to_mapping(), sort_keys=True)
    assert report.status is TurnerAncillaryValidationStatus.FAIL
    assert _check(report, "row_schema").reason_code == "INVALID_VALUE"
    assert "REAL-LAB-FLAG" not in rendered
    assert PATIENT_ID not in rendered
    assert TURNER_DIAGNOSIS_CODE not in rendered
    assert "SYN-TURNER-KARYOTYPE" not in rendered
    assert "latent_onset" not in rendered


def test_validator_rejects_duplicates_counts_and_treatment_gate() -> None:
    member, projection = _target()
    _replace_rows(
        projection,
        "referrals",
        (projection.rows["referrals"][0], projection.rows["referrals"][0]),
    )
    report = validate_turner_ancillary_resources(
        member, projection, _policy_ancillary()
    )
    assert _check(report, "row_schema").reason_code == "DUPLICATE_ROW"

    member, projection = _target()
    _replace_rows(projection, "labs", ())
    report = validate_turner_ancillary_resources(
        member, projection, _policy_ancillary()
    )
    assert _check(report, "pathway_scope").reason_code == "PATHWAY_SCOPE_INVALID"

    untreated_member, untreated_projection = _target(treatment=False)
    _replace_rows(
        untreated_projection,
        "medications",
        projection.rows["medications"],
    )
    report = validate_turner_ancillary_resources(
        untreated_member, untreated_projection, _policy_ancillary()
    )
    assert _check(report, "pathway_scope").reason_code == "PATHWAY_SCOPE_INVALID"

    non_target = _member(kind=DisorderKind.CELIAC_DISEASE)
    non_target_projection = project_turner_ancillary_resources(
        non_target, _shape(), _policy_ancillary()
    )
    _replace_rows(
        non_target_projection,
        "referrals",
        projection.rows["referrals"],
    )
    report = validate_turner_ancillary_resources(
        non_target, non_target_projection, _policy_ancillary()
    )
    assert _check(report, "pathway_scope").reason_code == "PATHWAY_SCOPE_INVALID"


@pytest.mark.parametrize(
    ("resource_name", "index", "field_name", "value"),
    [
        ("referrals", 0, "referral_date_age_in_days", 100),
        ("labs", 0, "lab_order_date_age_in_days", 701),
        ("labs", 0, "lab_result_date_age_in_days", 1001),
        ("labs", 1, "lab_result_date_age_in_days", 1000),
        ("problem_list", 0, "noted_date_age_in_days", 2001),
        ("medications", 0, "med_start_date_age_in_days", 1900),
    ],
)
def test_validator_rejects_event_age_result_delay_and_treatment_timing(
    resource_name: str,
    index: int,
    field_name: str,
    value: object,
) -> None:
    member, projection = _target()
    _change_field(projection, resource_name, index, field_name, value)
    report = validate_turner_ancillary_resources(
        member, projection, _policy_ancillary()
    )
    assert report.status is TurnerAncillaryValidationStatus.FAIL
    assert _check(report, "causal_timing").reason_code == "TIMING_INVALID"


def test_validator_rejects_reversed_visible_phases_and_line_numbers() -> None:
    member, projection = _target()
    events = list(member.frame.events)
    events[0], events[1] = events[1], events[0]
    object.__setattr__(member.frame, "events", tuple(events))
    report = validate_turner_ancillary_resources(
        member, projection, _policy_ancillary()
    )
    assert report.status is TurnerAncillaryValidationStatus.FAIL
    assert _check(report, "causal_timing").reason_code == "EVENT_ORDER_INVALID"

    member, projection = _target()
    _change_field(projection, "labs", 0, "result_line_num", 2)
    report = validate_turner_ancillary_resources(
        member, projection, _policy_ancillary()
    )
    assert _check(report, "row_schema").reason_code == "ROW_SCHEMA_INVALID"


def test_validator_rejects_wrong_field_order_and_non_synthetic_ids() -> None:
    member, projection = _target()
    row = projection.rows["labs"][0]
    object.__setattr__(row, "values", tuple(reversed(row.values)))
    report = validate_turner_ancillary_resources(
        member, projection, _policy_ancillary()
    )
    assert _check(report, "row_schema").reason_code == "SCHEMA_SHAPE_INVALID"

    member, projection = _target()
    _change_field(projection, "labs", 0, "visit_id", "not-a-synthetic-visit")
    report = validate_turner_ancillary_resources(
        member, projection, _policy_ancillary()
    )
    assert _check(report, "cross_resource_links").reason_code == (
        "VISIT_REFERENCE_INVALID"
    )


def test_source_point_specific_linkage_rejects_a_different_actual_visit() -> None:
    member, projection = _target(same_age_events=True)
    workup_visit = projection.rows["labs"][0].to_mapping()["visit_id"]
    other_visit = next(
        visit.visit_id
        for visit in member.frame.visits
        if visit.visit_id != workup_visit
    )
    for index in range(2):
        _change_field(projection, "labs", index, "visit_id", other_visit)
    report = validate_turner_ancillary_resources(
        member, projection, _policy_ancillary()
    )
    assert _check(report, "cross_resource_links") == TurnerAncillaryCheck(
        "cross_resource_links",
        TurnerAncillaryValidationStatus.FAIL,
        "VISIT_REFERENCE_INVALID",
    )


def test_problem_row_keeps_descriptor_no_visit_key_semantics() -> None:
    _member_value, projection = _target()
    problem = projection.rows["problem_list"][0]
    assert "visit_id" not in problem.to_mapping()


@pytest.mark.parametrize("source", [_without_truth, _malformed_truth])
def test_source_only_absence_is_unevaluable(source: object) -> None:
    member, projection = _target()
    report = validate_turner_ancillary_resources(
        source(member), projection, _policy_ancillary()  # type: ignore[operator]
    )
    assert report.status is TurnerAncillaryValidationStatus.UNEVALUABLE
    assert _check(report, "source_evidence") == TurnerAncillaryCheck(
        "source_evidence",
        TurnerAncillaryValidationStatus.UNEVALUABLE,
        "SOURCE_EVIDENCE_UNAVAILABLE",
    )


@pytest.mark.parametrize("source", [_without_truth, _malformed_truth])
def test_visible_failure_precedes_unavailable_source(source: object) -> None:
    member, projection = _target()
    _replace_rows(projection, "labs", ())
    report = validate_turner_ancillary_resources(
        source(member), projection, _policy_ancillary()  # type: ignore[operator]
    )
    assert report.status is TurnerAncillaryValidationStatus.FAIL
    assert _check(report, "pathway_scope").reason_code == "PATHWAY_SCOPE_INVALID"
    assert _check(report, "source_evidence").status is (
        TurnerAncillaryValidationStatus.UNEVALUABLE
    )


def test_valid_frame_member_trajectory_mismatch_is_invalid_source() -> None:
    member, projection = _target()
    changed = dataclasses.replace(
        member.trajectory,
        disorder=dataclasses.replace(member.trajectory.disorder, severity=0.7),
    )
    object.__setattr__(member, "trajectory", changed)
    assert validate_observation_frame(member.frame).status is ObservationValidationStatus.PASS
    report = validate_turner_ancillary_resources(
        member, projection, _policy_ancillary()
    )
    assert _check(report, "source_evidence") == TurnerAncillaryCheck(
        "source_evidence",
        TurnerAncillaryValidationStatus.FAIL,
        "SOURCE_EVIDENCE_INVALID",
    )


def test_invalid_source_event_binding_is_invalid_source() -> None:
    member, projection = _target()
    invalid = _invalid_source_events(member)
    report = validate_turner_ancillary_resources(
        invalid, projection, _policy_ancillary()  # type: ignore[arg-type]
    )
    assert _check(report, "source_evidence").status is (
        TurnerAncillaryValidationStatus.FAIL
    )
    assert _check(report, "source_evidence").reason_code == "SOURCE_EVIDENCE_INVALID"


def test_invalid_frame_binding_is_invalid_source() -> None:
    member, projection = _target()
    report = validate_turner_ancillary_resources(
        _invalid_frame_binding(member),  # type: ignore[arg-type]
        projection,
        _policy_ancillary(),
    )
    assert _check(report, "source_evidence").reason_code == "SOURCE_EVIDENCE_INVALID"


def test_validator_has_one_redacted_typed_input_boundary() -> None:
    _member_value, projection = _target()
    with pytest.raises(
        TurnerAncillaryProjectionUnavailable,
        match="^turner ancillary projection unavailable$",
    ):
        validate_turner_ancillary_resources(  # type: ignore[arg-type]
            object(), projection, _policy_ancillary()
        )
