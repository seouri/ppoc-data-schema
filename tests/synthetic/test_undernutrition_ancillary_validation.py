from __future__ import annotations

import copy
import dataclasses
import json
from types import MappingProxyType

import pytest

from synthetic.cohort import CohortMember
from synthetic.models import AgeRegimeDisorderTrajectory, DisorderKind
from synthetic.native.observations import (
    ObservationValidationStatus,
    validate_observation_frame,
)
from synthetic.native.resources import ResourceRow
from synthetic.native.undernutrition_ancillary import (
    UNDERNUTRITION_ANCILLARY_CHECK_NAMES,
    UNDERNUTRITION_ANCILLARY_REASON_CODES,
    UNDERNUTRITION_DIAGNOSIS_CODE,
    UNDERNUTRITION_HEIGHT_COMPONENT,
    UNDERNUTRITION_WEIGHT_COMPONENT,
    UndernutritionAncillaryCheck,
    UndernutritionAncillaryProjection,
    UndernutritionAncillaryProjectionUnavailable,
    UndernutritionAncillaryValidationReport,
    UndernutritionAncillaryValidationStatus,
    project_undernutrition_ancillary_resources,
    validate_undernutrition_ancillary_resources,
)
from tests.synthetic.test_undernutrition_ancillary_projection import (
    PATIENT_ID,
    _ancillary_policy,
    _member,
    _shape,
    _shape_without_lab_procedure_fields,
)


def _target(**member_kwargs: object) -> tuple[CohortMember, UndernutritionAncillaryProjection]:
    member = _member(**member_kwargs)
    projection = project_undernutrition_ancillary_resources(
        member,
        _shape(),
        _ancillary_policy(),
    )
    return member, projection


def _check(
    report: UndernutritionAncillaryValidationReport,
    name: str,
) -> UndernutritionAncillaryCheck:
    return next(check for check in report.checks if check.name == name)


def _replace_rows(
    projection: UndernutritionAncillaryProjection,
    resource_name: str,
    rows: tuple[ResourceRow, ...],
) -> None:
    replacement = dict(projection.rows)
    replacement[resource_name] = rows
    object.__setattr__(projection, "rows", MappingProxyType(replacement))


def _change_field(
    projection: UndernutritionAncillaryProjection,
    resource_name: str,
    index: int,
    field_name: str,
    value: object,
) -> None:
    rows = list(projection.rows[resource_name])
    row = rows[index]
    object.__setattr__(
        row,
        "values",
        tuple(
            (name, value if name == field_name else current)
            for name, current in row.values
        ),
    )
    rows[index] = row
    _replace_rows(projection, resource_name, tuple(rows))


def _without_truth(member: CohortMember) -> CohortMember:
    frame = dataclasses.replace(member.frame)
    object.__setattr__(frame, "truth", None)
    return dataclasses.replace(member, frame=frame)


def _malformed_truth(member: CohortMember) -> CohortMember:
    frame = dataclasses.replace(member.frame)
    object.__setattr__(frame, "truth", object())
    return dataclasses.replace(member, frame=frame)


def _invalid_source_events(member: CohortMember) -> CohortMember:
    snapshot = dataclasses.replace(member)
    source_events = list(snapshot.frame.truth.source_events)
    source_events[0] = dataclasses.replace(source_events[0], age_days=1)
    object.__setattr__(snapshot.frame.truth, "source_events", tuple(source_events))
    return snapshot


def test_validator_passes_target_and_non_target_with_fixed_checks() -> None:
    member, projection = _target()
    report = validate_undernutrition_ancillary_resources(
        member,
        projection,
        _ancillary_policy(),
    )

    assert report.status is UndernutritionAncillaryValidationStatus.PASS
    assert tuple(check.name for check in report.checks) == (
        "pathway_scope",
        "row_schema",
        "causal_timing",
        "cross_resource_links",
        "source_evidence",
    )
    assert tuple(check.name for check in report.checks) == (
        UNDERNUTRITION_ANCILLARY_CHECK_NAMES
    )
    assert all(
        check.status is UndernutritionAncillaryValidationStatus.PASS
        and check.reason_code == "OK"
        for check in report.checks
    )
    assert report.check_counts == {"PASS": 5, "FAIL": 0, "UNEVALUABLE": 0}

    non_target = _member(kind=DisorderKind.GROWTH_HORMONE_DEFICIENCY)
    empty = project_undernutrition_ancillary_resources(
        non_target,
        _shape(),
        _ancillary_policy(),
    )
    non_target_report = validate_undernutrition_ancillary_resources(
        non_target,
        empty,
        _ancillary_policy(),
    )
    assert non_target_report.status is UndernutritionAncillaryValidationStatus.PASS
    assert all(not empty.rows[name] for name in empty.rows)


def test_validation_models_are_frozen_fixed_and_apply_status_precedence() -> None:
    assert tuple(status.value for status in UndernutritionAncillaryValidationStatus) == (
        "PASS",
        "FAIL",
        "UNEVALUABLE",
    )
    assert UNDERNUTRITION_ANCILLARY_CHECK_NAMES == (
        "pathway_scope",
        "row_schema",
        "causal_timing",
        "cross_resource_links",
        "source_evidence",
    )
    assert isinstance(UNDERNUTRITION_ANCILLARY_REASON_CODES, frozenset)
    checks = tuple(
        UndernutritionAncillaryCheck(
            name,
            (
                UndernutritionAncillaryValidationStatus.FAIL
                if name == "row_schema"
                else UndernutritionAncillaryValidationStatus.UNEVALUABLE
                if name == "source_evidence"
                else UndernutritionAncillaryValidationStatus.PASS
            ),
            (
                "ROW_SCHEMA_INVALID"
                if name == "row_schema"
                else "SOURCE_EVIDENCE_UNAVAILABLE"
                if name == "source_evidence"
                else "OK"
            ),
        )
        for name in reversed(UNDERNUTRITION_ANCILLARY_CHECK_NAMES)
    )
    report = UndernutritionAncillaryValidationReport(
        UndernutritionAncillaryValidationStatus.FAIL,
        checks,
    )
    assert tuple(check.name for check in report.checks) == (
        UNDERNUTRITION_ANCILLARY_CHECK_NAMES
    )
    assert report.check_counts == {"PASS": 3, "FAIL": 1, "UNEVALUABLE": 1}
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.status = UndernutritionAncillaryValidationStatus.PASS  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.checks[0].reason_code = "OK"  # type: ignore[misc]
    with pytest.raises(TypeError):
        report.check_counts["PASS"] = 0  # type: ignore[index]
    with pytest.raises(ValueError, match="status"):
        UndernutritionAncillaryValidationReport(
            UndernutritionAncillaryValidationStatus.PASS,
            checks,
        )


@pytest.mark.parametrize(
    ("resource_name", "index", "field_name", "value", "reason"),
    [
        ("problem_list", 0, "pl_diag", "SYN-WRONG-DIAGNOSIS", "INVALID_CODE"),
        ("labs", 0, "result_component_name", "SYN-WRONG", "INVALID_CODE"),
        ("labs", 1, "result_component_name", UNDERNUTRITION_WEIGHT_COMPONENT, "ROW_SCHEMA_INVALID"),
        ("labs", 0, "result_flag", "Observed", "INVALID_VALUE"),
        ("referrals", 0, "requested_specialty", "Wrong specialty", "INVALID_VALUE"),
        ("medications", 0, "med_simple_generic_name", "Wrong treatment", "INVALID_VALUE"),
        ("medications", 0, "med_record_type", "External", "INVALID_VALUE"),
        ("labs", 0, "lab_order_id", "syn-wrong-order", "INVALID_ID"),
        ("medications", 0, "med_record_id", "external-id", "INVALID_ID"),
        ("problem_list", 0, "problem_list_id", "syn-wrong-problem", "INVALID_ID"),
        ("referrals", 0, "referral_id", "syn-wrong-referral", "INVALID_ID"),
        ("labs", 0, "result_line_num", 1.0, "INVALID_VALUE"),
        ("referrals", 0, "referral_number_of_visits", True, "INVALID_VALUE"),
        ("problem_list", 0, "resolved_date_age_in_days", 0, "INVALID_VALUE"),
        ("labs", 0, "result_flag", "", "INVALID_VALUE"),
        ("referrals", 0, "requested_specialty", "", "INVALID_VALUE"),
    ],
)
def test_validator_rejects_fixed_value_id_scalar_and_empty_tampering(
    resource_name: str,
    index: int,
    field_name: str,
    value: object,
    reason: str,
) -> None:
    member, projection = _target()
    _change_field(projection, resource_name, index, field_name, value)

    report = validate_undernutrition_ancillary_resources(
        member,
        projection,
        _ancillary_policy(),
    )
    assert report.status is UndernutritionAncillaryValidationStatus.FAIL
    assert _check(report, "row_schema").reason_code == reason


@pytest.mark.parametrize(
    ("resource_name", "index", "field_name", "value"),
    [
        ("labs", 0, "result_line_num", type("FancyInt", (int,), {})(1)),
        ("labs", 0, "result_flag", type("FancyStr", (str,), {})("Synthetic")),
        ("problem_list", 0, "resolved_date_age_in_days", type("FancyStr", (str,), {})("")),
    ],
)
def test_validator_rejects_scalar_subclasses(
    resource_name: str,
    index: int,
    field_name: str,
    value: object,
) -> None:
    member, projection = _target()
    _change_field(projection, resource_name, index, field_name, value)
    report = validate_undernutrition_ancillary_resources(
        member, projection, _ancillary_policy()
    )
    assert _check(report, "row_schema") == UndernutritionAncillaryCheck(
        "row_schema",
        UndernutritionAncillaryValidationStatus.FAIL,
        "INVALID_VALUE",
    )


def test_validator_rejects_field_order_malformed_rows_and_duplicates() -> None:
    member, projection = _target()
    row = projection.rows["labs"][0]
    object.__setattr__(row, "values", tuple(reversed(row.values)))
    report = validate_undernutrition_ancillary_resources(
        member, projection, _ancillary_policy()
    )
    assert _check(report, "row_schema").reason_code == "SCHEMA_SHAPE_INVALID"

    member, projection = _target()
    object.__setattr__(projection.rows["labs"][0], "resource_name", "referrals")
    report = validate_undernutrition_ancillary_resources(
        member, projection, _ancillary_policy()
    )
    assert _check(report, "row_schema").reason_code == "ROW_SCHEMA_INVALID"

    member, projection = _target()
    _replace_rows(
        projection,
        "referrals",
        (projection.rows["referrals"][0], projection.rows["referrals"][0]),
    )
    report = validate_undernutrition_ancillary_resources(
        member, projection, _ancillary_policy()
    )
    assert _check(report, "row_schema").reason_code == "DUPLICATE_ROW"


def test_invalid_visible_shape_does_not_downgrade_valid_source_evidence() -> None:
    member, projection = _target()
    object.__setattr__(projection, "shape", _shape_without_lab_procedure_fields())
    report = validate_undernutrition_ancillary_resources(
        member, projection, _ancillary_policy()
    )
    assert _check(report, "row_schema") == UndernutritionAncillaryCheck(
        "row_schema",
        UndernutritionAncillaryValidationStatus.FAIL,
        "SCHEMA_SHAPE_INVALID",
    )
    assert _check(report, "source_evidence") == UndernutritionAncillaryCheck(
        "source_evidence",
        UndernutritionAncillaryValidationStatus.PASS,
        "OK",
    )


def test_validator_rejects_mismatched_row_and_projection_patient_ids() -> None:
    member, projection = _target()
    _change_field(projection, "referrals", 0, "patient_id", "syn-other-patient")
    report = validate_undernutrition_ancillary_resources(
        member, projection, _ancillary_policy()
    )
    assert _check(report, "cross_resource_links").reason_code == "PATIENT_MISMATCH"

    member, projection = _target()
    object.__setattr__(projection, "patient_id", "syn-other-patient")
    report = validate_undernutrition_ancillary_resources(
        member, projection, _ancillary_policy()
    )
    assert _check(report, "cross_resource_links").reason_code == "PATIENT_MISMATCH"


@pytest.mark.parametrize(
    "resource_name", ["labs", "medications", "problem_list", "referrals"]
)
def test_validator_rejects_wrong_visible_resource_counts(resource_name: str) -> None:
    member, projection = _target()
    _replace_rows(projection, resource_name, ())
    report = validate_undernutrition_ancillary_resources(
        member, projection, _ancillary_policy()
    )
    assert _check(report, "pathway_scope").reason_code == "PATHWAY_SCOPE_INVALID"


def test_validator_enforces_hidden_treatment_gate_and_non_target_scope() -> None:
    _treated_member, treated = _target()

    untreated_member, untreated = _target(treatment=False)
    _replace_rows(untreated, "medications", treated.rows["medications"])
    report = validate_undernutrition_ancillary_resources(
        untreated_member,
        untreated,
        _ancillary_policy(),
    )
    assert _check(report, "pathway_scope").reason_code == "PATHWAY_SCOPE_INVALID"

    no_diagnosis_member, no_diagnosis = _target(censor_age_days=760)
    _replace_rows(no_diagnosis, "medications", treated.rows["medications"])
    report = validate_undernutrition_ancillary_resources(
        no_diagnosis_member,
        no_diagnosis,
        _ancillary_policy(),
    )
    assert _check(report, "pathway_scope").reason_code == "PATHWAY_SCOPE_INVALID"

    non_target = _member(kind=DisorderKind.CELIAC_DISEASE)
    empty = project_undernutrition_ancillary_resources(
        non_target,
        _shape(),
        _ancillary_policy(),
    )
    _replace_rows(empty, "medications", treated.rows["medications"])
    report = validate_undernutrition_ancillary_resources(
        non_target,
        empty,
        _ancillary_policy(),
    )
    assert _check(report, "pathway_scope").reason_code == "PATHWAY_SCOPE_INVALID"


@pytest.mark.parametrize(
    ("resource_name", "index", "field_name", "value"),
    [
        ("referrals", 0, "referral_date_age_in_days", 100),
        ("labs", 0, "lab_order_date_age_in_days", 100),
        ("labs", 0, "lab_result_date_age_in_days", 730),
        ("labs", 1, "lab_result_date_age_in_days", 729),
        ("problem_list", 0, "noted_date_age_in_days", 100),
        ("medications", 0, "med_order_date_age_in_days", 100),
        ("medications", 0, "med_start_date_age_in_days", 700),
    ],
)
def test_validator_rejects_visible_age_delay_and_treatment_timing(
    resource_name: str,
    index: int,
    field_name: str,
    value: object,
) -> None:
    member, projection = _target()
    _change_field(projection, resource_name, index, field_name, value)
    report = validate_undernutrition_ancillary_resources(
        member,
        projection,
        _ancillary_policy(),
    )
    assert report.status is UndernutritionAncillaryValidationStatus.FAIL
    assert _check(report, "causal_timing").reason_code == "TIMING_INVALID"


def test_validator_rejects_undelayed_and_reversed_lab_results() -> None:
    member, projection = _target()
    order_age = projection.rows["labs"][0].to_mapping()[
        "lab_order_date_age_in_days"
    ]
    for index in range(2):
        _change_field(
            projection,
            "labs",
            index,
            "lab_result_date_age_in_days",
            order_age,
        )
    report = validate_undernutrition_ancillary_resources(
        member, projection, _ancillary_policy()
    )
    assert _check(report, "causal_timing").reason_code == "TIMING_INVALID"

    member, projection = _target()
    order_age = projection.rows["labs"][0].to_mapping()[
        "lab_order_date_age_in_days"
    ]
    for index in range(2):
        _change_field(
            projection,
            "labs",
            index,
            "lab_result_date_age_in_days",
            order_age - 1,
        )
    report = validate_undernutrition_ancillary_resources(
        member, projection, _ancillary_policy()
    )
    assert _check(report, "causal_timing").reason_code == "TIMING_INVALID"


def test_validator_rejects_reversed_phases_and_bad_lab_line_order() -> None:
    member, projection = _target()
    events = list(member.frame.events)
    events[0], events[1] = events[1], events[0]
    object.__setattr__(member.frame, "events", tuple(events))
    report = validate_undernutrition_ancillary_resources(
        member, projection, _ancillary_policy()
    )
    assert _check(report, "causal_timing").reason_code == "EVENT_ORDER_INVALID"

    member, projection = _target()
    _change_field(projection, "labs", 0, "result_line_num", 2)
    _change_field(projection, "labs", 1, "result_line_num", 1)
    report = validate_undernutrition_ancillary_resources(
        member, projection, _ancillary_policy()
    )
    assert _check(report, "row_schema").reason_code == "ROW_SCHEMA_INVALID"


@pytest.mark.parametrize("resource_name", ["referrals", "labs", "medications"])
def test_validator_rejects_visit_links_absent_from_actual_frame(
    resource_name: str,
) -> None:
    member, projection = _target()
    for index in range(len(projection.rows[resource_name])):
        _change_field(
            projection,
            resource_name,
            index,
            "visit_id",
            "syn-absent-visit",
        )
    report = validate_undernutrition_ancillary_resources(
        member, projection, _ancillary_policy()
    )
    assert _check(report, "cross_resource_links").reason_code == (
        "VISIT_REFERENCE_INVALID"
    )


def test_source_point_specific_linkage_rejects_a_different_real_visit() -> None:
    member, projection = _target(same_age_events=True)
    workup_visit = projection.rows["labs"][0].to_mapping()["visit_id"]
    different_real_visit = next(
        visit.visit_id
        for visit in member.frame.visits
        if visit.visit_id != workup_visit
    )
    for index in range(2):
        _change_field(projection, "labs", index, "visit_id", different_real_visit)

    report = validate_undernutrition_ancillary_resources(
        member, projection, _ancillary_policy()
    )
    assert _check(report, "cross_resource_links") == UndernutritionAncillaryCheck(
        "cross_resource_links",
        UndernutritionAncillaryValidationStatus.FAIL,
        "VISIT_REFERENCE_INVALID",
    )


def test_source_point_linkage_still_fails_with_another_visible_failure() -> None:
    member, projection = _target(same_age_events=True)
    workup_visit = projection.rows["labs"][0].to_mapping()["visit_id"]
    different_real_visit = next(
        visit.visit_id
        for visit in member.frame.visits
        if visit.visit_id != workup_visit
    )
    for index in range(2):
        _change_field(projection, "labs", index, "visit_id", different_real_visit)
    _change_field(projection, "labs", 0, "result_flag", "Wrong marker")

    report = validate_undernutrition_ancillary_resources(
        member, projection, _ancillary_policy()
    )
    assert _check(report, "row_schema").status is (
        UndernutritionAncillaryValidationStatus.FAIL
    )
    assert _check(report, "cross_resource_links") == UndernutritionAncillaryCheck(
        "cross_resource_links",
        UndernutritionAncillaryValidationStatus.FAIL,
        "VISIT_REFERENCE_INVALID",
    )
    rendered = repr(report) + json.dumps(report.to_mapping(), sort_keys=True)
    assert PATIENT_ID not in rendered
    assert str(different_real_visit) not in rendered
    assert "Wrong marker" not in rendered


def test_problem_row_retains_descriptor_no_visit_key_semantics() -> None:
    _member_value, projection = _target()
    assert "visit_id" not in projection.rows["problem_list"][0].to_mapping()


@pytest.mark.parametrize("source", [_without_truth, _malformed_truth])
def test_missing_or_malformed_private_truth_is_unevaluable(source: object) -> None:
    member, projection = _target()
    report = validate_undernutrition_ancillary_resources(
        source(member),  # type: ignore[operator]
        projection,
        _ancillary_policy(),
    )
    assert report.status is UndernutritionAncillaryValidationStatus.UNEVALUABLE
    assert _check(report, "source_evidence") == UndernutritionAncillaryCheck(
        "source_evidence",
        UndernutritionAncillaryValidationStatus.UNEVALUABLE,
        "SOURCE_EVIDENCE_UNAVAILABLE",
    )


@pytest.mark.parametrize("source", [_without_truth, _malformed_truth])
def test_visible_failure_precedes_unavailable_source(source: object) -> None:
    member, projection = _target()
    _replace_rows(projection, "labs", ())
    report = validate_undernutrition_ancillary_resources(
        source(member),  # type: ignore[operator]
        projection,
        _ancillary_policy(),
    )
    assert report.status is UndernutritionAncillaryValidationStatus.FAIL
    assert _check(report, "pathway_scope").reason_code == "PATHWAY_SCOPE_INVALID"
    assert _check(report, "source_evidence").status is (
        UndernutritionAncillaryValidationStatus.UNEVALUABLE
    )


def test_medication_without_visible_diagnosis_fails_with_unavailable_source() -> None:
    _treated_member, treated = _target()
    member, projection = _target(censor_age_days=760)
    _replace_rows(projection, "medications", treated.rows["medications"])
    report = validate_undernutrition_ancillary_resources(
        _without_truth(member),
        projection,
        _ancillary_policy(),
    )
    assert report.status is UndernutritionAncillaryValidationStatus.FAIL
    assert _check(report, "pathway_scope").reason_code == "PATHWAY_SCOPE_INVALID"
    assert _check(report, "source_evidence").status is (
        UndernutritionAncillaryValidationStatus.UNEVALUABLE
    )


def test_member_trajectory_and_source_event_binding_fail_source_evidence() -> None:
    member, projection = _target()
    changed = dataclasses.replace(
        member.trajectory,
        disorder=dataclasses.replace(member.trajectory.disorder, severity=0.7),
    )
    object.__setattr__(member, "trajectory", changed)
    assert validate_observation_frame(member.frame).status is ObservationValidationStatus.PASS
    report = validate_undernutrition_ancillary_resources(
        member, projection, _ancillary_policy()
    )
    assert _check(report, "source_evidence").reason_code == "SOURCE_EVIDENCE_INVALID"

    member, projection = _target()
    report = validate_undernutrition_ancillary_resources(
        _invalid_source_events(member),
        projection,
        _ancillary_policy(),
    )
    assert _check(report, "source_evidence").reason_code == "SOURCE_EVIDENCE_INVALID"


def test_frame_member_identity_mismatch_fails_visible_and_source_checks() -> None:
    member, projection = _target()
    object.__setattr__(member.frame, "patient_id", "syn-other-frame-patient")
    report = validate_undernutrition_ancillary_resources(
        member, projection, _ancillary_policy()
    )
    assert report.status is UndernutritionAncillaryValidationStatus.FAIL
    assert _check(report, "source_evidence").reason_code == "SOURCE_EVIDENCE_INVALID"


def test_reports_are_aggregate_only_and_redact_all_payloads() -> None:
    member, projection = _target()
    _change_field(projection, "labs", 0, "result_flag", "PRIVATE-SOURCE-TEXT")
    report = validate_undernutrition_ancillary_resources(
        member, projection, _ancillary_policy()
    )
    rendered = repr(report) + json.dumps(report.to_mapping(), sort_keys=True)

    assert set(report.to_mapping()) == {"status", "check_counts", "checks"}
    for forbidden in (
        PATIENT_ID,
        member.frame.visits[0].visit_id,
        "PRIVATE-SOURCE-TEXT",
        UNDERNUTRITION_DIAGNOSIS_CODE,
        UNDERNUTRITION_WEIGHT_COMPONENT,
        UNDERNUTRITION_HEIGHT_COMPONENT,
        "treatment_start",
        "latent_onset",
        "age_days",
        "patient_id",
        "visit_id",
    ):
        assert forbidden not in rendered


def test_validator_has_one_strict_redacted_typed_boundary() -> None:
    member, projection = _target()
    with pytest.raises(
        UndernutritionAncillaryProjectionUnavailable,
        match="^undernutrition ancillary projection unavailable$",
    ):
        validate_undernutrition_ancillary_resources(  # type: ignore[arg-type]
            object(), projection, _ancillary_policy()
        )

    class MutableMember(CohortMember):
        pass

    class MutableProjection(UndernutritionAncillaryProjection):
        pass

    mutable_member = object.__new__(MutableMember)
    for name in ("demographics", "trajectory", "frame", "bundle"):
        object.__setattr__(mutable_member, name, getattr(member, name))
    mutable_projection = object.__new__(MutableProjection)
    for name in ("patient_id", "shape", "rows"):
        object.__setattr__(mutable_projection, name, getattr(projection, name))

    for candidate_member, candidate_projection in (
        (mutable_member, projection),
        (member, mutable_projection),
    ):
        with pytest.raises(
            UndernutritionAncillaryProjectionUnavailable,
            match="^undernutrition ancillary projection unavailable$",
        ):
            validate_undernutrition_ancillary_resources(
                candidate_member,
                candidate_projection,
                _ancillary_policy(),
            )


def test_malformed_typed_treatment_leaves_count_unknown_before_source_result() -> None:
    member, projection = _target()
    trajectory = dataclasses.replace(member.trajectory)
    events = list(trajectory.events)
    treatment = next(event for event in events if event.event_type == "treatment_start")
    object.__setattr__(treatment, "age_days", "malformed")
    object.__setattr__(trajectory, "events", tuple(events))
    object.__setattr__(member, "trajectory", trajectory)

    report = validate_undernutrition_ancillary_resources(
        member, projection, _ancillary_policy()
    )
    assert _check(report, "pathway_scope").status is (
        UndernutritionAncillaryValidationStatus.PASS
    )
    assert report.status in {
        UndernutritionAncillaryValidationStatus.FAIL,
        UndernutritionAncillaryValidationStatus.UNEVALUABLE,
    }


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("age_days", type("FancyInt", (int,), {})(800)),
        ("event_type", type("FancyStr", (str,), {})("treatment_start")),
    ],
)
def test_private_treatment_scalar_subclasses_are_source_unavailable(
    field_name: str,
    replacement: object,
) -> None:
    member, projection = _target()
    trajectory = copy.deepcopy(member.trajectory)
    treatment = next(
        event for event in trajectory.events if event.event_type == "treatment_start"
    )
    object.__setattr__(treatment, field_name, replacement)
    object.__setattr__(member, "trajectory", trajectory)

    report = validate_undernutrition_ancillary_resources(
        member, projection, _ancillary_policy()
    )
    assert _check(report, "pathway_scope").status is (
        UndernutritionAncillaryValidationStatus.PASS
    )
    assert _check(report, "row_schema").status is (
        UndernutritionAncillaryValidationStatus.PASS
    )
    assert _check(report, "source_evidence") == UndernutritionAncillaryCheck(
        "source_evidence",
        UndernutritionAncillaryValidationStatus.UNEVALUABLE,
        "SOURCE_EVIDENCE_UNAVAILABLE",
    )
    assert report.status is UndernutritionAncillaryValidationStatus.UNEVALUABLE


@pytest.mark.parametrize(
    ("kind", "malform_kind"),
    [
        (DisorderKind.UNDERNUTRITION, False),
        (DisorderKind.CELIAC_DISEASE, True),
    ],
)
def test_malformed_disorder_is_private_unavailable_not_projection_failure(
    kind: DisorderKind,
    malform_kind: bool,
) -> None:
    member = _member(kind=kind)
    projection = project_undernutrition_ancillary_resources(
        member, _shape(), _ancillary_policy()
    )
    trajectory = dataclasses.replace(member.trajectory)
    if malform_kind:
        disorder = dataclasses.replace(trajectory.disorder)
        object.__setattr__(disorder, "kind", object())
        object.__setattr__(trajectory, "disorder", disorder)
    else:
        object.__setattr__(trajectory, "disorder", object())
    object.__setattr__(member, "trajectory", trajectory)

    report = validate_undernutrition_ancillary_resources(
        member, projection, _ancillary_policy()
    )
    assert _check(report, "pathway_scope") == UndernutritionAncillaryCheck(
        "pathway_scope",
        UndernutritionAncillaryValidationStatus.UNEVALUABLE,
        "MALFORMED_MEMBER",
    )
    assert _check(report, "row_schema").status is (
        UndernutritionAncillaryValidationStatus.PASS
    )
    assert _check(report, "source_evidence") == UndernutritionAncillaryCheck(
        "source_evidence",
        UndernutritionAncillaryValidationStatus.UNEVALUABLE,
        "SOURCE_EVIDENCE_UNAVAILABLE",
    )
    assert report.status is UndernutritionAncillaryValidationStatus.UNEVALUABLE


def test_invalid_observation_precedes_malformed_private_member() -> None:
    member, projection = _target()
    trajectory = dataclasses.replace(member.trajectory)
    object.__setattr__(trajectory, "disorder", object())
    object.__setattr__(member, "trajectory", trajectory)
    object.__setattr__(member.frame.truth, "truth_hash", "0" * 64)

    report = validate_undernutrition_ancillary_resources(
        member, projection, _ancillary_policy()
    )
    assert _check(report, "pathway_scope").status is (
        UndernutritionAncillaryValidationStatus.UNEVALUABLE
    )
    assert _check(report, "row_schema").status is (
        UndernutritionAncillaryValidationStatus.PASS
    )
    assert _check(report, "source_evidence") == UndernutritionAncillaryCheck(
        "source_evidence",
        UndernutritionAncillaryValidationStatus.FAIL,
        "SOURCE_EVIDENCE_INVALID",
    )
    assert report.status is UndernutritionAncillaryValidationStatus.FAIL


def test_validator_rejects_mutable_trajectory_subclasses_as_invalid_source() -> None:
    class MutableTrajectory(AgeRegimeDisorderTrajectory):
        pass

    member, projection = _target()
    mutable = MutableTrajectory(
        member.trajectory.physiology,
        member.trajectory.disorder,
        member.trajectory.events,
    )
    object.__setattr__(member, "trajectory", mutable)
    report = validate_undernutrition_ancillary_resources(
        member, projection, _ancillary_policy()
    )
    assert _check(report, "source_evidence").reason_code == "SOURCE_EVIDENCE_INVALID"
