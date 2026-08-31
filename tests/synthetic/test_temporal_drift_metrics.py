from __future__ import annotations

import json
import math

import pytest

from synthetic.temporal_drift import (
    TemporalComparison,
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


def _comparison(
    report: TemporalDriftReport, metric: str, window_id: str
) -> TemporalComparison:
    matches = [
        comparison
        for comparison in report.comparisons
        if comparison.metric == metric and comparison.window_id == window_id
    ]
    assert len(matches) == 1
    return matches[0]


def test_half_open_windows_assign_bounds_once_and_follow_policy_order() -> None:
    policy = temporal_policy(
        temporal_window("z_early", 0, 100, minimum_member_support=1),
        temporal_window("a_late", 100, 200, minimum_member_support=1),
    )
    cohort = temporal_cohort(
        temporal_member(
            1,
            point_ages=(0, 99, 100, 199),
            visit_ages=(0, 99, 100, 199),
            event_ages=(99, 100),
        ),
        temporal_member(
            2,
            point_ages=(100, 199),
            visit_ages=(100, 199),
            event_ages=(100,),
        ),
    )

    report = validate_temporal_drift(cohort, policy)

    assert [
        (comparison.metric, comparison.window_id)
        for comparison in report.comparisons
    ] == [
        ("growth_window_coverage", "z_early"),
        ("growth_window_coverage", "a_late"),
        ("visible_visit_coverage", "z_early"),
        ("visible_visit_coverage", "a_late"),
        ("visible_event_rate", "z_early"),
        ("visible_event_rate", "a_late"),
        ("mean_inter_visit_days", "z_early"),
        ("mean_inter_visit_days", "a_late"),
        ("mean_visit_count_step", "a_late"),
        ("recorded_event_rate_step", "a_late"),
    ]
    assert _comparison(report, "growth_window_coverage", "z_early").observed == 0.5
    assert _comparison(report, "growth_window_coverage", "a_late").observed == 1.0
    assert _comparison(report, "visible_visit_coverage", "z_early").observed == 0.5
    assert _comparison(report, "visible_event_rate", "z_early").observed == 0.5
    assert _comparison(report, "visible_event_rate", "a_late").observed == 1.0
    assert _comparison(report, "mean_inter_visit_days", "z_early").observed == 99.0
    assert _comparison(report, "mean_inter_visit_days", "a_late").observed == 99.0
    assert _comparison(report, "mean_visit_count_step", "a_late").observed == 1.0
    assert _comparison(report, "recorded_event_rate_step", "a_late").observed == 0.5


def test_empty_window_emits_zero_rates_failures_and_no_interval_evidence() -> None:
    policy = temporal_policy()
    cohort = temporal_cohort(
        temporal_member(1, point_ages=(10,), visit_ages=(10,), event_ages=(10,)),
        temporal_member(2, point_ages=(20,), visit_ages=(20,)),
    )

    report = validate_temporal_drift(cohort, policy)

    growth = _comparison(report, "growth_window_coverage", "a_late")
    visits = _comparison(report, "visible_visit_coverage", "a_late")
    events = _comparison(report, "visible_event_rate", "a_late")
    intervals = _comparison(report, "mean_inter_visit_days", "a_late")
    assert (growth.status, growth.observed, growth.target, growth.difference) == (
        TemporalDriftStatus.FAIL,
        0.0,
        0.5,
        0.5,
    )
    assert (visits.status, visits.observed, visits.target, visits.difference) == (
        TemporalDriftStatus.FAIL,
        0.0,
        0.5,
        0.5,
    )
    assert (events.status, events.observed, events.target, events.difference) == (
        TemporalDriftStatus.PASS,
        0.0,
        None,
        0.0,
    )
    assert intervals.status is TemporalDriftStatus.UNEVALUABLE
    assert intervals.reason_code == "INSUFFICIENT_SUPPORT"
    assert (
        intervals.observed,
        intervals.target,
        intervals.difference,
        intervals.support_count,
    ) == (None, None, None, None)


def test_member_level_growth_and_visit_floors_control_coverage() -> None:
    policy = temporal_policy(
        temporal_window(
            "only",
            0,
            100,
            minimum_growth_points=2,
            minimum_visible_visits=2,
            minimum_growth_coverage=1.0,
            minimum_visible_visit_coverage=1.0,
        )
    )
    cohort = temporal_cohort(
        temporal_member(1, point_ages=(10, 20), visit_ages=(10, 20)),
        temporal_member(2, point_ages=(10,), visit_ages=(10,)),
    )

    report = validate_temporal_drift(cohort, policy)

    growth = _comparison(report, "growth_window_coverage", "only")
    visits = _comparison(report, "visible_visit_coverage", "only")
    assert (growth.observed, growth.target, growth.difference, growth.support_count) == (
        0.5,
        1.0,
        0.5,
        2,
    )
    assert (visits.observed, visits.target, visits.difference, visits.support_count) == (
        0.5,
        1.0,
        0.5,
        2,
    )
    assert growth.status is TemporalDriftStatus.FAIL
    assert visits.status is TemporalDriftStatus.FAIL


def test_interval_mean_uses_only_consecutive_visits_inside_the_window() -> None:
    policy = temporal_policy(
        temporal_window(
            "only",
            0,
            100,
            maximum_mean_inter_visit_days=10.0,
        )
    )
    cohort = temporal_cohort(
        temporal_member(1, point_ages=(10,), visit_ages=(0, 10, 30, 100)),
        temporal_member(2, point_ages=(10,), visit_ages=(5, 15)),
    )

    report = validate_temporal_drift(cohort, policy)

    comparison = _comparison(report, "mean_inter_visit_days", "only")
    assert (
        comparison.status,
        comparison.observed,
        comparison.target,
        comparison.difference,
        comparison.support_count,
    ) == (TemporalDriftStatus.FAIL, 40.0 / 3.0, 10.0, 3.333333333333334, 2)


def test_support_floor_and_absent_intervals_are_unevaluable() -> None:
    unsupported_policy = temporal_policy(
        temporal_window("only", 0, 100, minimum_member_support=2)
    )
    unsupported = validate_temporal_drift(
        temporal_cohort(temporal_member(1, point_ages=(10,), visit_ages=(10,))),
        unsupported_policy,
    )
    assert all(
        comparison.status is TemporalDriftStatus.UNEVALUABLE
        for comparison in unsupported.comparisons
    )
    assert all(
        (
            comparison.observed,
            comparison.target,
            comparison.difference,
            comparison.support_count,
        )
        == (None, None, None, None)
        for comparison in unsupported.comparisons
    )

    no_intervals = validate_temporal_drift(
        temporal_cohort(
            temporal_member(1, point_ages=(10,), visit_ages=(10,)),
            temporal_member(2, point_ages=(20,), visit_ages=(20,)),
        ),
        unsupported_policy,
    )
    interval = _comparison(no_intervals, "mean_inter_visit_days", "only")
    assert interval.status is TemporalDriftStatus.UNEVALUABLE
    assert interval.reason_code == "INSUFFICIENT_SUPPORT"


def test_adjacent_steps_use_signed_changes_and_exact_absolute_bounds() -> None:
    policy = temporal_policy()
    cohort = temporal_cohort(
        temporal_member(
            1,
            point_ages=(10, 110),
            visit_ages=(10, 20, 110, 120, 130),
            event_ages=(10,),
        ),
        temporal_member(
            2,
            point_ages=(20, 120),
            visit_ages=(120,),
        ),
    )

    report = validate_temporal_drift(cohort, policy)

    visit_step = _comparison(report, "mean_visit_count_step", "a_late")
    event_step = _comparison(report, "recorded_event_rate_step", "a_late")
    assert (
        visit_step.status,
        visit_step.observed,
        visit_step.target,
        visit_step.difference,
    ) == (TemporalDriftStatus.FAIL, 1.0, 0.5, 0.5)
    assert (
        event_step.status,
        event_step.observed,
        event_step.target,
        event_step.difference,
    ) == (TemporalDriftStatus.FAIL, -0.5, 0.25, 0.25)


def test_zero_steps_pass_and_first_window_has_no_step_comparison() -> None:
    cohort = temporal_cohort(
        temporal_member(
            1,
            point_ages=(10, 110),
            visit_ages=(10, 110),
            event_ages=(10, 110),
        ),
        temporal_member(2, point_ages=(20, 120), visit_ages=(20, 120)),
    )

    report = validate_temporal_drift(cohort, temporal_policy())

    visit_steps = [
        comparison
        for comparison in report.comparisons
        if comparison.metric == "mean_visit_count_step"
    ]
    event_steps = [
        comparison
        for comparison in report.comparisons
        if comparison.metric == "recorded_event_rate_step"
    ]
    assert len(visit_steps) == len(event_steps) == 1
    assert (visit_steps[0].status, visit_steps[0].observed, visit_steps[0].difference) == (
        TemporalDriftStatus.PASS,
        0.0,
        0.0,
    )
    assert (event_steps[0].status, event_steps[0].observed, event_steps[0].difference) == (
        TemporalDriftStatus.PASS,
        0.0,
        0.0,
    )


def test_visible_report_values_are_finite_aggregate_only() -> None:
    report = validate_temporal_drift(
        temporal_cohort(
            temporal_member(
                1,
                point_ages=(10, 110),
                visit_ages=(10, 20, 110, 120),
                event_ages=(10,),
            ),
            temporal_member(2, point_ages=(20, 120), visit_ages=(20, 120)),
        ),
        temporal_policy(),
    )

    encoded = json.dumps(report.to_mapping(), sort_keys=True)
    assert "syn-temporal" not in encoded
    assert "SYN-GROWTH-DIAGNOSIS" not in encoded
    assert "visit-" not in encoded
    assert all(
        math.isfinite(float(value))
        for comparison in report.comparisons
        for value in (
            comparison.observed,
            comparison.target,
            comparison.difference,
        )
        if value is not None
    )


@pytest.mark.parametrize("cohort", [None, object()])
def test_validator_rejects_non_native_cohort_before_reading_members(cohort: object) -> None:
    with pytest.raises(TypeError, match="NativeCohort"):
        validate_temporal_drift(cohort, temporal_policy())  # type: ignore[arg-type]


def test_validator_rejects_non_temporal_policy_before_reading_members() -> None:
    cohort = temporal_cohort(temporal_member(1, point_ages=(10,)))
    with pytest.raises(TypeError, match="TemporalDriftPolicy"):
        validate_temporal_drift(cohort, object())  # type: ignore[arg-type]
