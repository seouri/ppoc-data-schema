from __future__ import annotations

import dataclasses
import json

import pytest

from synthetic.cohort import CohortMember, NativeCohort
from synthetic.models import ClinicalEvent
from synthetic.native.observations import EventRecordingDecision
from synthetic.temporal_drift import (
    TemporalComparison,
    TemporalDriftPolicy,
    TemporalDriftReport,
    TemporalDriftStatus,
    validate_temporal_drift,
)
from tests.synthetic.temporal_drift_fixtures import (
    temporal_cohort,
    temporal_member,
    temporal_policy,
    temporal_window,
)

_PHASES = (
    "latent_onset",
    "observable_phenotype",
    "recognition_opportunity",
    "workup",
    "recorded_diagnosis",
    "treatment_start",
    "treatment_response",
)


def _events(patient_id: str, phases: tuple[str, ...] = _PHASES) -> tuple[ClinicalEvent, ...]:
    return tuple(
        ClinicalEvent(
            patient_id,
            10 * (index + 1),
            phase,
            None,
            phase == "latent_onset",
        )
        for index, phase in enumerate(phases)
    )


def _with_events(
    member: CohortMember, events: tuple[ClinicalEvent, ...]
) -> CohortMember:
    trajectory = dataclasses.replace(member.trajectory)
    object.__setattr__(trajectory, "events", events)
    truth = dataclasses.replace(
        member.frame.truth,
        source_events=events,
        event_decisions=tuple(
            EventRecordingDecision(index, False, None)
            for index in range(len(events))
        ),
        latent_trajectory=trajectory,
    )
    frame = dataclasses.replace(member.frame, truth=truth)
    return dataclasses.replace(member, trajectory=trajectory, frame=frame)


def _valid_member(member_number: int) -> CohortMember:
    member = temporal_member(
        member_number,
        point_ages=(10, 110),
        visit_ages=(10, 20, 110, 120),
    )
    phases = (
        _PHASES
        if member_number % 2
        else (*_PHASES[:-1], "treatment_nonresponse")
    )
    events = _events(member.demographics.patient_id, phases)
    if member_number % 2 == 0:
        events = (
            events[0],
            dataclasses.replace(events[1], age_days=events[0].age_days),
            *events[2:],
        )
    return _with_events(member, events)


def _valid_cohort() -> NativeCohort:
    return temporal_cohort(_valid_member(1), _valid_member(2))


def _comparison(report: TemporalDriftReport, metric: str) -> TemporalComparison:
    matches = [item for item in report.comparisons if item.metric == metric]
    assert len(matches) == 1
    return matches[0]


def _check(report: TemporalDriftReport, name: str) -> tuple[TemporalDriftStatus, str]:
    matches = [item for item in report.checks if item.name == name]
    assert len(matches) == 1
    return matches[0].status, matches[0].reason_code


def test_valid_source_schedule_passes_causal_checks_and_global_report() -> None:
    cohort = _valid_cohort()
    before_frames = tuple(member.frame.to_mapping() for member in cohort.members)
    before_events = tuple(member.trajectory.events for member in cohort.members)

    report = validate_temporal_drift(cohort, temporal_policy())

    order = _comparison(report, "causal_event_order")
    timing = _comparison(report, "causal_event_timing")
    assert report.status is TemporalDriftStatus.PASS
    assert (order.status, order.reason_code) == (TemporalDriftStatus.PASS, "OK")
    assert (timing.status, timing.reason_code) == (TemporalDriftStatus.PASS, "OK")
    assert (
        order.observed,
        order.target,
        order.difference,
        order.support_count,
    ) == (None, None, None, None)
    assert (
        timing.observed,
        timing.target,
        timing.difference,
        timing.support_count,
    ) == (None, None, None, None)
    assert _check(report, "cohort_size") == (TemporalDriftStatus.PASS, "OK")
    assert _check(report, "causal_event_order") == (TemporalDriftStatus.PASS, "OK")
    assert _check(report, "causal_event_timing") == (TemporalDriftStatus.PASS, "OK")
    assert tuple(member.frame.to_mapping() for member in cohort.members) == before_frames
    assert tuple(member.trajectory.events for member in cohort.members) == before_events


@pytest.mark.parametrize(
    "events",
    [
        _events("syn-temporal-1", ("observable_phenotype", "latent_onset")),
        (
            ClinicalEvent("syn-temporal-1", 20, "latent_onset", None, True),
            ClinicalEvent(
                "syn-temporal-1", 10, "observable_phenotype", None, False
            ),
        ),
        _events("syn-temporal-1", ("treatment_response", "treatment_start")),
        _events(
            "syn-temporal-1",
            ("treatment_start", "treatment_response", "treatment_nonresponse"),
        ),
    ],
    ids=(
        "reversed-phases",
        "decreasing-ages",
        "outcome-before-start",
        "both-outcomes",
    ),
)
def test_invalid_causal_schedules_fail_with_fixed_aggregate_reason(
    events: tuple[ClinicalEvent, ...],
) -> None:
    member = temporal_member(1, point_ages=(10,), visit_ages=(10, 20))
    cohort = temporal_cohort(_with_events(member, events), _valid_member(2))

    report = validate_temporal_drift(cohort, temporal_policy())

    comparison = _comparison(report, "causal_event_order")
    assert report.status is TemporalDriftStatus.FAIL
    assert (comparison.status, comparison.reason_code) == (
        TemporalDriftStatus.FAIL,
        "STRUCTURAL_INVALID",
    )
    assert _check(report, "causal_event_order") == (
        TemporalDriftStatus.FAIL,
        "STRUCTURAL_INVALID",
    )


@pytest.mark.parametrize(
    ("field", "unsafe_value"),
    [
        ("hidden", False),
        ("patient_id", "syn-secret-source-patient"),
        ("code", "REAL-SECRET-EVENT-CODE"),
    ],
)
def test_malformed_source_event_fails_without_disclosing_injected_value(
    field: str, unsafe_value: object
) -> None:
    member = _valid_member(1)
    object.__setattr__(member.trajectory.events[0], field, unsafe_value)
    cohort = temporal_cohort(member, _valid_member(2))

    report = validate_temporal_drift(cohort, temporal_policy())
    encoded = json.dumps(report.to_mapping(), sort_keys=True)

    assert _comparison(report, "causal_event_order").reason_code == "STRUCTURAL_INVALID"
    assert report.status is TemporalDriftStatus.FAIL
    assert str(unsafe_value) not in encoded
    assert str(unsafe_value) not in repr(report)


def test_negative_source_age_fails_timing_without_disclosing_age() -> None:
    member = _valid_member(1)
    object.__setattr__(member.trajectory.events[0], "age_days", -987_654)
    cohort = temporal_cohort(member, _valid_member(2))

    report = validate_temporal_drift(cohort, temporal_policy())
    encoded = json.dumps(report.to_mapping(), sort_keys=True)

    timing = _comparison(report, "causal_event_timing")
    assert (timing.status, timing.reason_code) == (
        TemporalDriftStatus.FAIL,
        "STRUCTURAL_INVALID",
    )
    assert report.status is TemporalDriftStatus.FAIL
    assert "987654" not in encoded


@pytest.mark.parametrize("record_kind", ["visit", "event"])
def test_visible_record_outside_declared_window_fails_causal_timing(
    record_kind: str,
) -> None:
    member = _valid_member(1)
    record = (
        member.frame.visits[0]
        if record_kind == "visit"
        else temporal_member(
            9, point_ages=(10,), event_ages=(10,)
        ).frame.events[0]
    )
    if record_kind == "event":
        object.__setattr__(record, "patient_id", member.frame.patient_id)
        object.__setattr__(member.frame, "events", (record,))
    object.__setattr__(record, "age_days", 987_654)
    cohort = temporal_cohort(member, _valid_member(2))

    report = validate_temporal_drift(cohort, temporal_policy())
    encoded = json.dumps(report.to_mapping(), sort_keys=True)

    assert _comparison(report, "causal_event_timing").reason_code == "STRUCTURAL_INVALID"
    assert report.status is TemporalDriftStatus.FAIL
    assert "987654" not in encoded


@pytest.mark.parametrize("field", ["visits", "events"])
def test_visible_record_in_wrong_frame_collection_is_structural(field: str) -> None:
    member = _valid_member(1)
    if field == "visits":
        wrong_record = temporal_member(
            9, point_ages=(10,), event_ages=(10,)
        ).frame.events[0]
    else:
        wrong_record = member.frame.visits[0]
    object.__setattr__(wrong_record, "patient_id", member.frame.patient_id)
    object.__setattr__(member.frame, field, (wrong_record,))

    report = validate_temporal_drift(
        temporal_cohort(member, _valid_member(2)), temporal_policy()
    )

    assert report.status is TemporalDriftStatus.FAIL
    assert _comparison(report, "causal_event_timing").reason_code == "STRUCTURAL_INVALID"


def test_absent_private_truth_is_missing_evidence_and_unevaluable() -> None:
    member = _valid_member(1)
    object.__setattr__(member.frame, "truth", None)
    policy = dataclasses.replace(temporal_policy(), maximum_unevaluable_checks=0)
    cohort = temporal_cohort(member, _valid_member(2))

    report = validate_temporal_drift(cohort, policy)

    assert report.status is TemporalDriftStatus.UNEVALUABLE
    for metric in ("causal_event_order", "causal_event_timing"):
        comparison = _comparison(report, metric)
        assert (comparison.status, comparison.reason_code) == (
            TemporalDriftStatus.UNEVALUABLE,
            "MISSING_EVIDENCE",
        )
        assert (
            comparison.observed,
            comparison.target,
            comparison.difference,
            comparison.support_count,
        ) == (None, None, None, None)


@pytest.mark.parametrize(
    "corruption",
    (
        "later-point-patient",
        "later-point-age",
        "frame-patient",
        "frame-window-order",
        "visits-list",
        "events-list",
        "wrong-visit-record-type",
        "wrong-event-record-type",
        "visible-visit-patient",
        "visible-event-patient",
        "duplicate-visit-id",
        "visit-outside-frame",
    ),
)
def test_missing_truth_does_not_mask_truth_independent_structural_corruption(
    corruption: str,
) -> None:
    member = _valid_member(1)
    frame = member.frame
    if corruption == "later-point-patient":
        object.__setattr__(
            member.trajectory.physiology.points[1],
            "patient_id",
            "syn-secret-later-point",
        )
    elif corruption == "later-point-age":
        points = member.trajectory.physiology.points
        object.__setattr__(points[1], "age_days", points[0].age_days)
    elif corruption == "frame-patient":
        object.__setattr__(frame, "patient_id", "syn-secret-frame-patient")
    elif corruption == "frame-window-order":
        object.__setattr__(frame.window, "effective_end_age_days", 0)
    elif corruption == "visits-list":
        object.__setattr__(frame, "visits", list(frame.visits))
    elif corruption == "events-list":
        object.__setattr__(frame, "events", list(frame.events))
    elif corruption == "wrong-visit-record-type":
        wrong_records = temporal_member(
            9,
            point_ages=(10,),
            event_ages=(10, 20, 110, 120),
        ).frame.events
        for record in wrong_records:
            object.__setattr__(record, "patient_id", member.demographics.patient_id)
        object.__setattr__(frame, "visits", wrong_records)
    elif corruption == "wrong-event-record-type":
        object.__setattr__(frame, "events", (frame.visits[0], frame.visits[2]))
    elif corruption == "visible-visit-patient":
        object.__setattr__(
            frame.visits[0], "patient_id", "syn-secret-visible-visit"
        )
    elif corruption == "visible-event-patient":
        wrong_events = temporal_member(
            9, point_ages=(10,), event_ages=(10, 110)
        ).frame.events
        object.__setattr__(frame, "events", wrong_events)
    elif corruption == "duplicate-visit-id":
        object.__setattr__(frame.visits[1], "visit_id", frame.visits[0].visit_id)
    elif corruption == "visit-outside-frame":
        object.__setattr__(frame.visits[0], "age_days", 987_654)
    else:  # pragma: no cover - the parametrization is closed above
        raise AssertionError("unknown fictional corruption")
    object.__setattr__(frame, "truth", None)
    policy = dataclasses.replace(
        temporal_policy(), maximum_unevaluable_checks=99
    )

    report = validate_temporal_drift(
        temporal_cohort(member, _valid_member(2)), policy
    )
    encoded = json.dumps(report.to_mapping(), sort_keys=True)

    assert report.status is TemporalDriftStatus.FAIL
    for metric in ("causal_event_order", "causal_event_timing"):
        comparison = _comparison(report, metric)
        assert (comparison.status, comparison.reason_code) == (
            TemporalDriftStatus.FAIL,
            "STRUCTURAL_INVALID",
        )
    assert "syn-secret" not in encoded
    assert "987654" not in encoded


@pytest.mark.parametrize(
    "corruption",
    (
        "visible-latent-onset",
        "nonboolean-hidden",
        "non-null-code",
        "unknown-phase",
        "reversed-phase",
        "decreasing-age",
        "treatment-start-without-outcome",
        "orphan-treatment-outcome",
        "dual-treatment-outcomes",
    ),
)
def test_missing_truth_does_not_mask_source_event_semantic_corruption(
    corruption: str,
) -> None:
    member = _valid_member(1)
    trajectory = member.trajectory
    patient_id = member.demographics.patient_id
    if corruption == "visible-latent-onset":
        object.__setattr__(trajectory.events[0], "hidden", False)
    elif corruption == "nonboolean-hidden":
        object.__setattr__(trajectory.events[0], "hidden", 1)
    elif corruption == "non-null-code":
        object.__setattr__(
            trajectory.events[0], "code", "syn-secret-source-code"
        )
    elif corruption == "unknown-phase":
        object.__setattr__(
            trajectory.events[0], "event_type", "syn-secret-source-phase"
        )
    elif corruption == "reversed-phase":
        object.__setattr__(
            trajectory,
            "events",
            _events(patient_id, ("observable_phenotype", "latent_onset")),
        )
    elif corruption == "decreasing-age":
        object.__setattr__(trajectory.events[1], "age_days", 5)
    elif corruption == "treatment-start-without-outcome":
        object.__setattr__(
            trajectory,
            "events",
            _events(patient_id, ("latent_onset", "treatment_start")),
        )
    elif corruption == "orphan-treatment-outcome":
        object.__setattr__(
            trajectory,
            "events",
            _events(patient_id, ("latent_onset", "treatment_response")),
        )
    elif corruption == "dual-treatment-outcomes":
        object.__setattr__(
            trajectory,
            "events",
            _events(
                patient_id,
                (
                    "latent_onset",
                    "treatment_start",
                    "treatment_response",
                    "treatment_nonresponse",
                ),
            ),
        )
    else:  # pragma: no cover - the parametrization is closed above
        raise AssertionError("unknown fictional source-event corruption")
    object.__setattr__(member.frame, "truth", None)
    policy = dataclasses.replace(
        temporal_policy(), maximum_unevaluable_checks=99
    )

    report = validate_temporal_drift(
        temporal_cohort(member, _valid_member(2)), policy
    )
    encoded = json.dumps(report.to_mapping(), sort_keys=True)

    assert report.status is TemporalDriftStatus.FAIL
    for metric in ("causal_event_order", "causal_event_timing"):
        comparison = _comparison(report, metric)
        assert (comparison.status, comparison.reason_code) == (
            TemporalDriftStatus.FAIL,
            "STRUCTURAL_INVALID",
        )
    assert "syn-secret-source-code" not in encoded
    assert "syn-secret-source-phase" not in encoded


class _ExplodingFrame:
    @property
    def visits(self) -> object:
        raise RuntimeError("syn-secret-patient raw injected exception 987654")


@pytest.mark.parametrize("field", ["frame", "trajectory"])
def test_malformed_member_parts_fail_closed_without_exception_text(field: str) -> None:
    member = _valid_member(1)
    injected: object = _ExplodingFrame() if field == "frame" else object()
    object.__setattr__(member, field, injected)
    cohort = temporal_cohort(member, _valid_member(2))

    report = validate_temporal_drift(cohort, temporal_policy())
    encoded = json.dumps(report.to_mapping(), sort_keys=True)

    assert report.status is TemporalDriftStatus.FAIL
    assert any(
        item.status is TemporalDriftStatus.FAIL
        and item.reason_code == "STRUCTURAL_INVALID"
        for item in report.comparisons
    )
    assert "syn-secret-patient" not in encoded
    assert "987654" not in encoded
    assert "injected exception" not in encoded


def test_malformed_truth_object_is_structural_not_missing() -> None:
    member = _valid_member(1)
    object.__setattr__(member.frame, "truth", object())
    cohort = temporal_cohort(member, _valid_member(2))

    report = validate_temporal_drift(cohort, temporal_policy())

    assert report.status is TemporalDriftStatus.FAIL
    assert _comparison(report, "causal_event_order").reason_code == "STRUCTURAL_INVALID"
    assert _comparison(report, "causal_event_timing").reason_code == "STRUCTURAL_INVALID"


def test_nested_trajectory_and_truth_corruption_prevents_any_causal_pass() -> None:
    def later_point_patient(cohort: NativeCohort) -> None:
        object.__setattr__(
            cohort.members[0].trajectory.physiology.points[1],
            "patient_id",
            "syn-secret-later-point",
        )

    def later_point_age(cohort: NativeCohort) -> None:
        points = cohort.members[0].trajectory.physiology.points
        object.__setattr__(points[1], "age_days", points[0].age_days)

    def truth_patient(cohort: NativeCohort) -> None:
        object.__setattr__(
            cohort.members[0].frame.truth,
            "patient_id",
            "syn-secret-truth-patient",
        )

    def truth_window(cohort: NativeCohort) -> None:
        mismatched = dataclasses.replace(
            cohort.members[0].frame.window,
            effective_end_age_days=900,
            administrative_end_age_days=900,
        )
        object.__setattr__(cohort.members[0].frame.truth, "window", mismatched)

    for mutation in (
        later_point_patient,
        later_point_age,
        truth_patient,
        truth_window,
    ):
        cohort = _valid_cohort()
        mutation(cohort)

        report = validate_temporal_drift(cohort, temporal_policy())
        encoded = json.dumps(report.to_mapping(), sort_keys=True)

        assert report.status is TemporalDriftStatus.FAIL
        for metric in ("causal_event_order", "causal_event_timing"):
            comparison = _comparison(report, metric)
            assert (comparison.status, comparison.reason_code) == (
                TemporalDriftStatus.FAIL,
                "STRUCTURAL_INVALID",
            )
        assert "syn-secret" not in encoded


class _ExplodingMembers(tuple[CohortMember, ...]):
    def __len__(self) -> int:
        raise RuntimeError("syn-secret-members raw exception age 987654")


class _ExplodingProfileCohort(NativeCohort):
    def __getattribute__(self, name: str) -> object:
        if name == "profile":
            raise RuntimeError("syn-secret-profile raw exception age 987654")
        return super().__getattribute__(name)


class _ExplodingSeedCohort(NativeCohort):
    def __getattribute__(self, name: str) -> object:
        if name == "seed":
            raise RuntimeError("syn-secret-seed raw exception age 987654")
        return super().__getattribute__(name)


def _as_hostile_cohort(
    cohort_type: type[NativeCohort], cohort: NativeCohort
) -> NativeCohort:
    hostile = object.__new__(cohort_type)
    object.__setattr__(hostile, "profile", "development-v1")
    object.__setattr__(hostile, "seed", 7)
    object.__setattr__(hostile, "members", cohort.members)
    object.__setattr__(hostile, "calibration", cohort.calibration)
    return hostile


def _assert_sanitized_structural_fallback(report: TemporalDriftReport) -> None:
    encoded = json.dumps(report.to_mapping(), sort_keys=True)
    assert report.status is TemporalDriftStatus.FAIL
    assert report.cohort_profile == "unavailable"
    assert report.cohort_seed == 0
    assert report.cohort_size == 0
    assert all(
        comparison.status is TemporalDriftStatus.FAIL
        and comparison.reason_code == "STRUCTURAL_INVALID"
        for comparison in report.comparisons
    )
    assert "syn-secret" not in encoded
    assert "987654" not in encoded
    assert "raw exception" not in encoded


def test_hostile_profile_accessor_returns_sanitized_structural_report() -> None:
    cohort = _as_hostile_cohort(_ExplodingProfileCohort, _valid_cohort())

    report = validate_temporal_drift(cohort, temporal_policy())

    _assert_sanitized_structural_fallback(report)


def test_hostile_seed_accessor_returns_sanitized_structural_report() -> None:
    cohort = _as_hostile_cohort(_ExplodingSeedCohort, _valid_cohort())

    report = validate_temporal_drift(cohort, temporal_policy())

    _assert_sanitized_structural_fallback(report)


def test_malformed_member_container_returns_redacted_structural_report() -> None:
    cohort = _valid_cohort()
    object.__setattr__(cohort, "members", _ExplodingMembers(cohort.members))

    report = validate_temporal_drift(cohort, temporal_policy())
    encoded = json.dumps(report.to_mapping(), sort_keys=True)

    assert report.status is TemporalDriftStatus.FAIL
    assert all(
        comparison.status is TemporalDriftStatus.FAIL
        and comparison.reason_code == "STRUCTURAL_INVALID"
        for comparison in report.comparisons
    )
    assert "syn-secret-members" not in encoded
    assert "987654" not in encoded
    assert "raw exception" not in encoded


def test_cohort_below_minimum_is_unevaluable_even_when_comparisons_pass() -> None:
    policy = temporal_policy(minimum_cohort_size=3)

    report = validate_temporal_drift(_valid_cohort(), policy)

    assert report.status is TemporalDriftStatus.UNEVALUABLE
    assert _check(report, "cohort_size") == (
        TemporalDriftStatus.UNEVALUABLE,
        "COHORT_TOO_SMALL",
    )
    assert not any(
        item.status is TemporalDriftStatus.FAIL for item in report.comparisons
    )


def test_empty_cohort_has_no_vacuous_causal_pass() -> None:
    report = validate_temporal_drift(temporal_cohort(), temporal_policy())

    assert report.status is TemporalDriftStatus.UNEVALUABLE
    for metric in ("causal_event_order", "causal_event_timing"):
        comparison = _comparison(report, metric)
        assert (comparison.status, comparison.reason_code) == (
            TemporalDriftStatus.UNEVALUABLE,
            "MISSING_EVIDENCE",
        )


def test_fail_precedes_missing_causal_evidence() -> None:
    first = temporal_member(1, point_ages=(10,), visit_ages=(10,))
    second = temporal_member(2, point_ages=(20,), visit_ages=(20,))
    object.__setattr__(first.frame, "truth", None)
    object.__setattr__(second.frame, "truth", None)

    report = validate_temporal_drift(
        temporal_cohort(first, second), temporal_policy()
    )

    assert report.status is TemporalDriftStatus.FAIL
    assert any(
        item.metric == "growth_window_coverage"
        and item.status is TemporalDriftStatus.FAIL
        for item in report.comparisons
    )
    assert _comparison(report, "causal_event_order").status is TemporalDriftStatus.UNEVALUABLE


def test_unevaluable_count_must_exceed_policy_maximum() -> None:
    cohort = temporal_cohort(
        _with_events(
            temporal_member(1, point_ages=(10,), visit_ages=(10,)),
            _events("syn-temporal-1"),
        ),
        _with_events(
            temporal_member(2, point_ages=(20,), visit_ages=(20,)),
            _events("syn-temporal-2"),
        ),
    )
    base = temporal_policy(temporal_window("only", 0, 100))

    allowed = validate_temporal_drift(
        cohort, dataclasses.replace(base, maximum_unevaluable_checks=1)
    )
    exceeded = validate_temporal_drift(
        cohort, dataclasses.replace(base, maximum_unevaluable_checks=0)
    )

    assert allowed.status is TemporalDriftStatus.PASS
    assert exceeded.status is TemporalDriftStatus.UNEVALUABLE
    assert sum(
        item.status is TemporalDriftStatus.UNEVALUABLE
        for item in allowed.comparisons
    ) == 1


def test_required_window_support_is_mandatory_even_with_high_unevaluable_limit() -> None:
    member = _with_events(
        temporal_member(1, point_ages=(10,), visit_ages=(10, 20)),
        _events("syn-temporal-1"),
    )
    policy = TemporalDriftPolicy(
        policy_id="temporal-v1",
        policy_version="1",
        minimum_cohort_size=1,
        maximum_unevaluable_checks=99,
        windows=(temporal_window("only", 0, 100, minimum_member_support=2),),
    )

    report = validate_temporal_drift(temporal_cohort(member), policy)

    assert report.status is TemporalDriftStatus.UNEVALUABLE
    assert all(
        item.status is TemporalDriftStatus.UNEVALUABLE
        for item in report.comparisons
        if item.window_id == "only"
    )
