from __future__ import annotations

import dataclasses
import math

import pytest

from synthetic.cohort import NativeCohort
from synthetic.cohort_validation import (
    CohortValidationStatus,
    validate_native_cohort,
)
from synthetic.models import ClinicalEvent
from synthetic.native.observations import RecordedEvent, RecordedEventKind
from tests.synthetic.test_cohort_validation_layers import _cohort, _comparison, _policy


def _growth_metrics() -> tuple[str, ...]:
    return (
        "height_z_score",
        "bmi_z_score",
        "height_velocity_cm_per_year",
        "weight_velocity_kg_per_year",
    )


def test_growth_comparisons_report_windowed_means_and_point_support() -> None:
    cohort = _cohort(patient_count=2)
    policy = _policy(
        minimum_cell_support=1,
        required_age_windows=(("childhood", 730, 4380),),
        growth_tolerances={
            "height_z_score": 10.0,
            "bmi_z_score": 10.0,
            "height_velocity_cm_per_year": 20.0,
            "weight_velocity_kg_per_year": 20.0,
        },
    )

    report = validate_native_cohort(cohort, policy)

    for metric in _growth_metrics():
        # Keep the expected-value calculation explicit because z-score names
        # and velocity names do not share a model field suffix.
        fields = {
            "height_z_score": "height_z",
            "bmi_z_score": "bmi_z",
            "height_velocity_cm_per_year": "height_velocity_cm_per_year",
            "weight_velocity_kg_per_year": "weight_velocity_kg_per_year",
        }
        values = [
            getattr(point, fields[metric])
            for member in cohort.members
            for point in member.trajectory.physiology.points
            if 730 <= point.age_days < 4380
            and getattr(point, fields[metric]) is not None
        ]
        comparison = _comparison(report, f"growth.childhood.{metric}_mean")
        assert comparison.support == len(values)
        assert comparison.denominator == sum(
            1
            for member in cohort.members
            for point in member.trajectory.physiology.points
            if 730 <= point.age_days < 4380
        )
        assert comparison.observed_value == pytest.approx(sum(values) / len(values))
        assert comparison.target_value == 0.0
        assert comparison.difference == pytest.approx(abs(sum(values) / len(values)))
        assert comparison.status is CohortValidationStatus.PASS


def test_first_none_velocity_is_omitted_from_the_growth_mean() -> None:
    cohort = _cohort(patient_count=1)
    policy = _policy(
        minimum_cell_support=1,
        required_age_windows=(("infant", 0, 730),),
        growth_tolerances={
            "height_z_score": 10.0,
            "bmi_z_score": 10.0,
            "height_velocity_cm_per_year": 20.0,
            "weight_velocity_kg_per_year": 20.0,
        },
    )

    report = validate_native_cohort(cohort, policy)

    height_velocity = _comparison(
        report, "growth.infant.height_velocity_cm_per_year_mean"
    )
    point_velocity = cohort.members[0].trajectory.physiology.points[1].height_velocity_cm_per_year
    assert point_velocity is not None
    assert height_velocity.support == 1
    assert height_velocity.denominator == 2
    assert height_velocity.observed_value == pytest.approx(point_velocity)


def test_window_tokens_with_dots_remain_parseable_in_growth_names() -> None:
    cohort = _cohort(patient_count=1)
    report = validate_native_cohort(
        cohort,
        _policy(
            minimum_cell_support=1,
            required_age_windows=(("childhood.v1", 730, 4380),),
            growth_tolerances={
                "height_z_score": 10.0,
                "bmi_z_score": 10.0,
                "height_velocity_cm_per_year": 20.0,
                "weight_velocity_kg_per_year": 20.0,
            },
        ),
    )

    growth = [
        item
        for item in report.comparisons
        if item.name.startswith("growth.childhood.v1.")
    ]
    assert [item.name for item in growth] == [
        f"growth.childhood.v1.{metric}_mean" for metric in _growth_metrics()
    ]
    assert all(item.layer == "growth" for item in growth)


def test_extreme_finite_values_fail_as_invalid_without_dropping_growth_checks() -> None:
    cohort = _cohort(patient_count=2)
    for member in cohort.members:
        for point in member.trajectory.physiology.points[2:4]:
            object.__setattr__(point, "height_z", 1e308)

    report = validate_native_cohort(
        cohort,
        _policy(
            minimum_cell_support=1,
            required_age_windows=(("childhood", 730, 4380),),
            growth_tolerances={
                "height_z_score": 10.0,
                "bmi_z_score": 10.0,
                "height_velocity_cm_per_year": 20.0,
                "weight_velocity_kg_per_year": 20.0,
            },
        ),
    )

    height = _comparison(report, "growth.childhood.height_z_score_mean")
    assert report.status is CohortValidationStatus.FAIL
    assert height.status is CohortValidationStatus.FAIL
    assert height.reason_code == "INVALID_VALUE"
    assert height.support == 8
    assert height.denominator == 8
    assert {
        item.name
        for item in report.comparisons
        if item.name.startswith("growth.childhood.")
    } == {f"growth.childhood.{metric}_mean" for metric in _growth_metrics()}


def test_growth_bound_failure_and_insufficient_support_are_distinct() -> None:
    cohort = _cohort(patient_count=2)
    failing = validate_native_cohort(
        cohort,
        _policy(
            minimum_cell_support=1,
            required_age_windows=(("childhood", 730, 4380),),
            growth_tolerances={
                "height_z_score": 0.0,
                "bmi_z_score": 10.0,
                "height_velocity_cm_per_year": 20.0,
                "weight_velocity_kg_per_year": 20.0,
            },
        ),
    )
    height = _comparison(failing, "growth.childhood.height_z_score_mean")
    assert height.status is CohortValidationStatus.FAIL
    assert height.reason_code == "OUTSIDE_TOLERANCE"
    assert height.target_value == 0.0

    insufficient = validate_native_cohort(
        cohort,
        _policy(
            minimum_cell_support=1,
            required_age_windows=(("birth", 0, 1),),
        ),
    )
    for metric in _growth_metrics():
        comparison = _comparison(insufficient, f"growth.birth.{metric}_mean")
        assert comparison.status is CohortValidationStatus.UNEVALUABLE
        assert comparison.reason_code == "INSUFFICIENT_SUPPORT"
        assert comparison.observed_value is None


def test_coverage_reports_counts_and_rates_for_missing_visits_and_events() -> None:
    cohort = _cohort(patient_count=2)
    members = tuple(
        dataclasses.replace(member, frame=dataclasses.replace(member.frame, visits=()))
        for member in cohort.members
    )
    cohort_without_observations = dataclasses.replace(cohort, members=members)

    report = validate_native_cohort(cohort_without_observations, _policy())

    cohort_size = _comparison(report, "coverage.cohort_size")
    with_observation = _comparison(report, "coverage.members_with_observation")
    with_event = _comparison(report, "coverage.members_with_event")
    assert cohort_size.observed_value == 2
    assert cohort_size.support == 2
    assert cohort_size.denominator == 2
    assert with_observation.observed_value == 0.0
    assert with_observation.support == 0
    assert with_observation.denominator == 2
    assert with_observation.status is CohortValidationStatus.PASS
    assert with_event.observed_value == 0.0
    assert with_event.support == 0
    assert with_event.denominator == 2
    assert with_event.status is CohortValidationStatus.PASS


def test_coverage_and_growth_malformed_values_fail_without_leaking_identifiers() -> None:
    cohort = _cohort(patient_count=1)
    point = cohort.members[0].trajectory.physiology.points[2]
    object.__setattr__(point, "height_z", math.nan)

    report = validate_native_cohort(
        cohort,
        _policy(required_age_windows=(("childhood", 730, 4380),)),
    )

    comparison = _comparison(report, "growth.childhood.height_z_score_mean")
    assert report.status is CohortValidationStatus.FAIL
    assert comparison.status is CohortValidationStatus.FAIL
    assert comparison.reason_code == "INVALID_VALUE"
    assert comparison.observed_value == 0.0
    assert "syn-" not in str(report.to_mapping())
    assert "truth" not in repr(report).lower()


def test_malformed_frame_is_reported_by_recorded_and_coverage_checks() -> None:
    cohort = _cohort(patient_count=1)
    object.__setattr__(cohort.members[0], "frame", object())

    report = validate_native_cohort(cohort, _policy())

    assert report.status is CohortValidationStatus.FAIL
    assert _comparison(report, "recorded_recognition").reason_code in {
        "STRUCTURAL_INVALID",
        "MALFORMED_COHORT",
    }
    assert _comparison(report, "coverage.members_with_observation").reason_code == "STRUCTURAL_INVALID"
    assert "syn-" not in str(report.to_mapping())


def test_malformed_nested_visit_and_record_are_not_counted_as_evidence() -> None:
    cohort = _cohort(patient_count=1)
    member = cohort.members[0]
    visit = member.frame.visits[0]
    object.__setattr__(visit, "visit_id", "real-patient-visit")
    report = validate_native_cohort(cohort, _policy())

    observation = _comparison(report, "coverage.members_with_observation")
    assert observation.status is CohortValidationStatus.FAIL
    assert observation.support == 0

    clean_cohort = _cohort(patient_count=1)
    clean_member = clean_cohort.members[0]
    patient_id = clean_member.frame.patient_id
    record = RecordedEvent(
        patient_id,
        0,
        RecordedEventKind.RECOGNITION,
        "SYN-GROWTH-RECOGNITION",
    )
    object.__setattr__(record, "code", "real-diagnosis-code")
    object.__setattr__(clean_member.frame, "events", (record,))
    report = validate_native_cohort(clean_cohort, _policy())

    recorded = _comparison(report, "recorded_recognition")
    event_coverage = _comparison(report, "coverage.members_with_event")
    assert recorded.status is CohortValidationStatus.FAIL
    assert recorded.support == 0
    assert event_coverage.status is CohortValidationStatus.FAIL
    assert event_coverage.support == 0
    assert "real-diagnosis-code" not in str(report.to_mapping())


@pytest.mark.parametrize(
    "events",
    [
        (
            RecordedEvent(
                "syn-frame-order",
                100,
                RecordedEventKind.WORKUP,
                "SYN-GROWTH-WORKUP",
            ),
            RecordedEvent(
                "syn-frame-order",
                100,
                RecordedEventKind.RECOGNITION,
                "SYN-GROWTH-RECOGNITION",
            ),
        ),
        (
            RecordedEvent(
                "syn-frame-order",
                100,
                RecordedEventKind.RECOGNITION,
                "SYN-GROWTH-RECOGNITION",
            ),
            RecordedEvent(
                "syn-frame-order",
                100,
                RecordedEventKind.RECOGNITION,
                "SYN-GROWTH-RECOGNITION",
            ),
        ),
    ],
)
def test_reversed_or_repeated_typed_frame_events_fail_without_leaking(
    events: tuple[RecordedEvent, ...],
) -> None:
    cohort = _cohort(patient_count=1)
    member = cohort.members[0]
    for event in events:
        object.__setattr__(event, "patient_id", member.frame.patient_id)
    object.__setattr__(member.frame, "events", events)

    report = validate_native_cohort(cohort, _policy())

    recorded = _comparison(report, "recorded_recognition")
    coverage = _comparison(report, "coverage.members_with_event")
    assert report.status is CohortValidationStatus.FAIL
    assert recorded.status is CohortValidationStatus.FAIL
    assert recorded.reason_code == "STRUCTURAL_INVALID"
    assert recorded.support == 0
    assert coverage.status is CohortValidationStatus.FAIL
    assert coverage.reason_code == "STRUCTURAL_INVALID"
    assert coverage.support == 0
    assert "syn-frame-order" not in str(report.to_mapping())
    assert "SYN-GROWTH" not in str(report.to_mapping())


def test_same_age_typed_frame_events_in_causal_order_are_accepted() -> None:
    cohort = _cohort(patient_count=1)
    member = cohort.members[0]
    patient_id = member.frame.patient_id
    events = (
        RecordedEvent(
            patient_id,
            100,
            RecordedEventKind.RECOGNITION,
            "SYN-GROWTH-RECOGNITION",
        ),
        RecordedEvent(
            patient_id,
            100,
            RecordedEventKind.WORKUP,
            "SYN-GROWTH-WORKUP",
        ),
    )
    object.__setattr__(member.frame, "events", events)

    report = validate_native_cohort(cohort, _policy())

    assert _comparison(report, "recorded_recognition").status is CohortValidationStatus.PASS
    assert _comparison(report, "recorded_workup").status is CohortValidationStatus.PASS
    assert _comparison(report, "coverage.members_with_event").status is CohortValidationStatus.PASS


def test_malformed_clinical_event_is_not_counted_as_observable_phenotype() -> None:
    cohort = _cohort(patient_count=1)
    member = cohort.members[0]
    patient_id = member.demographics.patient_id
    event = ClinicalEvent(patient_id, 500, "real-clinical-event", None, False)
    object.__setattr__(member.trajectory, "events", (event,))

    report = validate_native_cohort(cohort, _policy())

    observable = _comparison(report, "observable_phenotype")
    assert report.status is CohortValidationStatus.FAIL
    assert observable.status is CohortValidationStatus.FAIL
    assert observable.support == 0
    assert "real-clinical-event" not in str(report.to_mapping())


def test_missing_required_weight_is_an_invalid_growth_value() -> None:
    cohort = _cohort(patient_count=1)
    point = cohort.members[0].trajectory.physiology.points[0]
    object.__setattr__(point, "weight_kg", None)

    report = validate_native_cohort(cohort, _policy())

    growth = _comparison(report, "growth.infant.height_velocity_cm_per_year_mean")
    assert report.status is CohortValidationStatus.FAIL
    assert growth.status is CohortValidationStatus.FAIL
    assert growth.reason_code == "INVALID_VALUE"
    assert "syn-" not in str(report.to_mapping())


def test_nonmonotone_trajectory_is_a_redacted_coverage_failure() -> None:
    cohort = _cohort(patient_count=1)
    points = cohort.members[0].trajectory.physiology.points
    object.__setattr__(points[1], "age_days", points[0].age_days)

    report = validate_native_cohort(cohort, _policy())

    assert report.status is CohortValidationStatus.FAIL
    assert any(
        item.layer == "coverage"
        and item.status is CohortValidationStatus.FAIL
        and item.reason_code in {"STRUCTURAL_INVALID", "MALFORMED_COHORT"}
        for item in report.comparisons
    )
    assert "syn-" not in str(report.to_mapping())


def test_fail_has_precedence_over_unevaluable_and_report_order_is_fixed() -> None:
    cohort = _cohort(patient_count=2)
    policy = _policy(
        required_age_windows=(("childhood", 730, 4380),),
        minimum_cell_support=1,
        growth_tolerances={
            "height_z_score": 0.0,
            "bmi_z_score": 0.0,
            "height_velocity_cm_per_year": 0.0,
            "weight_velocity_kg_per_year": 0.0,
        },
    )
    report = validate_native_cohort(cohort, policy)
    names = [item.name for item in report.comparisons]
    assert report.status is CohortValidationStatus.FAIL
    assert names[0] == "cohort_size"
    assert max(names.index(name) for name in names if name.startswith("demographics.")) < names.index("latent_module.healthy")
    assert names.index("recorded_diagnosis") < names.index("growth.childhood.height_z_score_mean")
    assert names.index("growth.childhood.height_z_score_mean") < names.index("coverage.cohort_size")
    assert any(item.status is CohortValidationStatus.UNEVALUABLE for item in report.comparisons)


def test_underpowered_cohort_has_unevaluable_coverage_without_exception_leakage() -> None:
    cohort = _cohort(patient_count=1)
    report = validate_native_cohort(
        cohort,
        _policy(
            minimum_cohort_size=2,
            growth_tolerances={
                "height_z_score": 10.0,
                "bmi_z_score": 10.0,
                "height_velocity_cm_per_year": 20.0,
                "weight_velocity_kg_per_year": 20.0,
            },
        ),
    )

    assert report.status is CohortValidationStatus.UNEVALUABLE
    assert _comparison(report, "coverage.cohort_size").status is CohortValidationStatus.UNEVALUABLE
    assert _comparison(report, "coverage.cohort_size").target_value is None


def test_growth_evaluator_does_not_mutate_cohort() -> None:
    cohort: NativeCohort = _cohort(patient_count=2)
    before = cohort.to_mapping()
    validate_native_cohort(
        cohort,
        _policy(required_age_windows=(("childhood", 730, 4380),)),
    )
    assert cohort.to_mapping() == before
