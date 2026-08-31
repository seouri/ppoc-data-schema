from __future__ import annotations

import dataclasses
import json
import math
from dataclasses import FrozenInstanceError

import pytest

from synthetic.temporal_drift import (
    TEMPORAL_DRIFT_REPORT_VERSION,
    TEMPORAL_METRICS,
    TEMPORAL_REASON_CODES,
    TemporalCheck,
    TemporalComparison,
    TemporalDriftPolicy,
    TemporalDriftReport,
    TemporalDriftStatus,
    TemporalWindowPolicy,
)


def _window(window_id: str = "early", **changes: object) -> TemporalWindowPolicy:
    values: dict[str, object] = {
        "window_id": window_id,
        "lower_age_days": 0,
        "upper_age_days": 730,
        "minimum_member_support": 2,
        "minimum_growth_points": 1,
        "minimum_visible_visits": 1,
        "minimum_growth_coverage": 0.5,
        "minimum_visible_visit_coverage": 0.5,
        "maximum_mean_inter_visit_days": 400.0,
        "maximum_visit_count_step": 2.0,
        "maximum_recorded_event_rate_step": 0.5,
    }
    values.update(changes)
    return TemporalWindowPolicy(**values)  # type: ignore[arg-type]


def _policy(**changes: object) -> TemporalDriftPolicy:
    values: dict[str, object] = {
        "policy_id": "temporal-v1",
        "policy_version": "1",
        "minimum_cohort_size": 2,
        "maximum_unevaluable_checks": 1,
        "windows": (
            _window(),
            _window(
                "late",
                lower_age_days=730,
                upper_age_days=1_460,
                maximum_mean_inter_visit_days=365.0,
            ),
        ),
    }
    values.update(changes)
    return TemporalDriftPolicy(**values)  # type: ignore[arg-type]


def _coverage_comparison(**changes: object) -> TemporalComparison:
    values: dict[str, object] = {
        "metric": "growth_window_coverage",
        "window_id": "early",
        "status": TemporalDriftStatus.PASS,
        "reason_code": "WITHIN_BOUND",
        "observed": 0.75,
        "target": 0.5,
        "difference": 0.0,
        "support_count": 3,
    }
    values.update(changes)
    return TemporalComparison(**values)  # type: ignore[arg-type]


def _causal_comparison(**changes: object) -> TemporalComparison:
    values: dict[str, object] = {
        "metric": "causal_event_order",
        "window_id": None,
        "status": TemporalDriftStatus.PASS,
        "reason_code": "OK",
        "observed": None,
        "target": None,
        "difference": None,
        "support_count": None,
    }
    values.update(changes)
    return TemporalComparison(**values)  # type: ignore[arg-type]


def _checks() -> tuple[TemporalCheck, ...]:
    return (
        TemporalCheck("causal_event_timing", TemporalDriftStatus.PASS, "OK"),
        TemporalCheck("causal_event_order", TemporalDriftStatus.PASS, "OK"),
        TemporalCheck("sequence_metrics", TemporalDriftStatus.PASS, "WITHIN_BOUND"),
        TemporalCheck("window_coverage", TemporalDriftStatus.PASS, "WITHIN_BOUND"),
        TemporalCheck("cohort_size", TemporalDriftStatus.PASS, "OK"),
    )


def _metric_counts(**changes: int) -> dict[str, int]:
    counts = {
        "growth_window_coverage": 1,
        "visible_visit_coverage": 0,
        "visible_event_rate": 0,
        "mean_inter_visit_days": 0,
        "mean_visit_count_step": 0,
        "recorded_event_rate_step": 0,
        "causal_event_order": 1,
        "causal_event_timing": 0,
    }
    counts.update(changes)
    return counts


def _report(**changes: object) -> TemporalDriftReport:
    values: dict[str, object] = {
        "report_version": TEMPORAL_DRIFT_REPORT_VERSION,
        "policy_id": "temporal-v1",
        "policy_version": "1",
        "cohort_profile": "development-v1",
        "cohort_seed": 7,
        "cohort_size": 4,
        "status": TemporalDriftStatus.PASS,
        "status_counts": {"PASS": 2, "FAIL": 0, "UNEVALUABLE": 0},
        "metric_counts": _metric_counts(),
        "checks": _checks(),
        "comparisons": (_causal_comparison(), _coverage_comparison()),
        "_window_order": ("early", "late"),
    }
    values.update(changes)
    return TemporalDriftReport(**values)  # type: ignore[arg-type]


def test_temporal_registries_and_status_enum_are_exact_and_immutable() -> None:
    assert TEMPORAL_DRIFT_REPORT_VERSION == "temporal-drift-report-v1"
    assert TEMPORAL_METRICS == (
        "growth_window_coverage",
        "visible_visit_coverage",
        "visible_event_rate",
        "mean_inter_visit_days",
        "mean_visit_count_step",
        "recorded_event_rate_step",
        "causal_event_order",
        "causal_event_timing",
    )
    assert TEMPORAL_REASON_CODES == (
        "OK",
        "WITHIN_BOUND",
        "INSUFFICIENT_SUPPORT",
        "COHORT_TOO_SMALL",
        "MISSING_EVIDENCE",
        "STRUCTURAL_INVALID",
        "OUTSIDE_BOUND",
    )
    assert tuple(status.value for status in TemporalDriftStatus) == (
        "PASS",
        "FAIL",
        "UNEVALUABLE",
    )


def test_policy_and_windows_are_frozen_with_half_open_ordered_bounds() -> None:
    policy = _policy()

    assert policy.windows[0].lower_age_days == 0
    assert policy.windows[0].upper_age_days == policy.windows[1].lower_age_days
    assert policy.windows[1].upper_age_days == 1_460
    with pytest.raises(FrozenInstanceError):
        policy.policy_id = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        policy.windows[0].upper_age_days = 800  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("lower_age_days", -1),
        ("lower_age_days", True),
        ("upper_age_days", 0),
        ("upper_age_days", True),
        ("minimum_member_support", 0),
        ("minimum_member_support", False),
        ("minimum_growth_points", -1),
        ("minimum_growth_points", True),
        ("minimum_visible_visits", -1),
        ("minimum_visible_visits", False),
        ("minimum_growth_coverage", -0.01),
        ("minimum_growth_coverage", 1.01),
        ("minimum_growth_coverage", True),
        ("minimum_visible_visit_coverage", -0.01),
        ("minimum_visible_visit_coverage", 1.01),
        ("minimum_visible_visit_coverage", False),
        ("maximum_mean_inter_visit_days", -1.0),
        ("maximum_mean_inter_visit_days", math.inf),
        ("maximum_mean_inter_visit_days", True),
        ("maximum_visit_count_step", -1.0),
        ("maximum_visit_count_step", math.nan),
        ("maximum_recorded_event_rate_step", -1.0),
        ("maximum_recorded_event_rate_step", False),
    ],
)
def test_window_rejects_invalid_boolean_nonfinite_and_out_of_range_values(
    field: str, value: object
) -> None:
    with pytest.raises(ValueError, match=field):
        _window(**{field: value})


def test_window_rejects_reversed_bounds_and_unsafe_identifier() -> None:
    with pytest.raises(ValueError, match="upper_age_days"):
        _window(lower_age_days=730, upper_age_days=730)
    for unsafe in ("patient-window", "truth-window", "../../window", "window.json"):
        with pytest.raises(ValueError, match="window_id"):
            _window(unsafe)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("minimum_cohort_size", 0),
        ("minimum_cohort_size", True),
        ("maximum_unevaluable_checks", -1),
        ("maximum_unevaluable_checks", False),
    ],
)
def test_policy_rejects_invalid_integer_thresholds(field: str, value: object) -> None:
    with pytest.raises(ValueError, match=field):
        _policy(**{field: value})


def test_policy_rejects_mutable_empty_duplicate_unsorted_and_overlapping_windows() -> None:
    with pytest.raises(TypeError, match="windows"):
        _policy(windows=[_window()])
    with pytest.raises(ValueError, match="nonempty"):
        _policy(windows=())
    with pytest.raises(ValueError, match="unique"):
        _policy(windows=(_window(), _window()))
    with pytest.raises(ValueError, match="ordered"):
        _policy(
            windows=(
                _window("late", lower_age_days=730, upper_age_days=1_460),
                _window(),
            )
        )
    with pytest.raises(ValueError, match="non-overlapping"):
        _policy(
            windows=(
                _window(),
                _window("late", lower_age_days=700, upper_age_days=1_460),
            )
        )
    with pytest.raises(TypeError, match="TemporalWindowPolicy"):
        _policy(windows=(_window(), ("late", 730, 1_460)))


@pytest.mark.parametrize("field", ["policy_id", "policy_version"])
def test_policy_rejects_identifier_path_and_truth_metadata(field: str) -> None:
    for unsafe in ("patient-P-001", "../policy", "policy.json", "truth-policy"):
        with pytest.raises(ValueError, match=field):
            _policy(**{field: unsafe})


@pytest.mark.parametrize(
    "comparison",
    [
        _coverage_comparison(),
        _coverage_comparison(
            status=TemporalDriftStatus.FAIL,
            reason_code="OUTSIDE_BOUND",
            observed=0.25,
            target=0.5,
            difference=0.25,
            support_count=2,
        ),
        _coverage_comparison(
            metric="mean_inter_visit_days",
            status=TemporalDriftStatus.FAIL,
            reason_code="OUTSIDE_BOUND",
            observed=401.0,
            target=400.0,
            difference=1.0,
            support_count=2,
        ),
        _coverage_comparison(
            metric="mean_visit_count_step",
            status=TemporalDriftStatus.FAIL,
            reason_code="OUTSIDE_BOUND",
            observed=-3.0,
            target=2.0,
            difference=1.0,
            support_count=2,
        ),
        _coverage_comparison(
            metric="visible_event_rate",
            reason_code="OK",
            observed=0.5,
            target=None,
            difference=0.0,
            support_count=2,
        ),
    ],
)
def test_comparison_accepts_registered_metric_shapes(comparison: TemporalComparison) -> None:
    assert comparison.to_mapping()["metric"] in TEMPORAL_METRICS
    with pytest.raises(FrozenInstanceError):
        comparison.metric = "visible_event_rate"  # type: ignore[misc]


def test_unevaluable_and_structural_comparisons_require_null_numeric_fields() -> None:
    unevaluable = _coverage_comparison(
        status=TemporalDriftStatus.UNEVALUABLE,
        reason_code="INSUFFICIENT_SUPPORT",
        observed=None,
        target=None,
        difference=None,
        support_count=None,
    )
    structural = _coverage_comparison(
        status=TemporalDriftStatus.FAIL,
        reason_code="STRUCTURAL_INVALID",
        observed=None,
        target=None,
        difference=None,
        support_count=None,
    )

    assert unevaluable.to_mapping() == {
        "metric": "growth_window_coverage",
        "window_id": "early",
        "status": "UNEVALUABLE",
        "reason_code": "INSUFFICIENT_SUPPORT",
        "observed": None,
        "target": None,
        "difference": None,
        "support_count": None,
    }
    assert structural.status is TemporalDriftStatus.FAIL
    for field, value in (
        ("observed", 0.0),
        ("target", 0.0),
        ("difference", 0.0),
        ("support_count", 0),
    ):
        with pytest.raises(ValueError, match="null numeric"):
            dataclasses.replace(unevaluable, **{field: value})


def test_causal_comparisons_are_status_only_and_have_fixed_safe_repr() -> None:
    comparison = _causal_comparison()

    assert comparison.to_mapping() == {
        "metric": "causal_event_order",
        "window_id": None,
        "status": "PASS",
        "reason_code": "OK",
        "observed": None,
        "target": None,
        "difference": None,
        "support_count": None,
    }
    assert repr(comparison) == "TemporalComparison(<aggregate-only>)"
    for field, value in (
        ("observed", 1.0),
        ("target", 1.0),
        ("difference", 0.0),
        ("support_count", 1),
    ):
        with pytest.raises(ValueError, match="causal"):
            dataclasses.replace(comparison, **{field: value})


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"metric": "invented_metric"}, "metric"),
        ({"window_id": "patient-window"}, "window_id"),
        ({"window_id": None}, "window_id"),
        ({"status": "PASS"}, "TemporalDriftStatus"),
        ({"reason_code": "INVENTED"}, "reason_code"),
        ({"reason_code": "OUTSIDE_BOUND"}, "compatible"),
        ({"observed": True}, "observed"),
        ({"observed": math.inf}, "observed"),
        ({"target": False}, "target"),
        ({"difference": -0.1}, "difference"),
        ({"support_count": True}, "support_count"),
        ({"support_count": -1}, "support_count"),
    ],
)
def test_comparison_rejects_unknown_unsafe_and_invalid_values(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        _coverage_comparison(**changes)


def test_comparison_rejects_difference_or_status_inconsistent_with_bound() -> None:
    with pytest.raises(ValueError, match="difference"):
        _coverage_comparison(observed=0.25, target=0.5, difference=0.0)
    with pytest.raises(ValueError, match="status"):
        _coverage_comparison(
            status=TemporalDriftStatus.FAIL,
            reason_code="OUTSIDE_BOUND",
            observed=0.75,
            target=0.5,
            difference=0.0,
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"difference": 5e-13},
        {
            "status": TemporalDriftStatus.FAIL,
            "reason_code": "OUTSIDE_BOUND",
            "observed": 0.25,
            "target": 0.5,
            "difference": 0.2500000000005,
        },
        {
            "metric": "mean_inter_visit_days",
            "status": TemporalDriftStatus.FAIL,
            "reason_code": "OUTSIDE_BOUND",
            "observed": 401.0,
            "target": 400.0,
            "difference": 1.0000000000005,
        },
        {
            "metric": "mean_visit_count_step",
            "status": TemporalDriftStatus.FAIL,
            "reason_code": "OUTSIDE_BOUND",
            "observed": -3.0,
            "target": 2.0,
            "difference": 1.0000000000005,
        },
    ],
)
def test_comparison_requires_exact_frozen_difference(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="difference"):
        _coverage_comparison(**changes)


def test_check_uses_only_fixed_name_status_and_reason_vocabularies() -> None:
    check = TemporalCheck("cohort_size", TemporalDriftStatus.PASS, "OK")

    assert check.to_mapping() == {
        "name": "cohort_size",
        "status": "PASS",
        "reason_code": "OK",
    }
    with pytest.raises(FrozenInstanceError):
        check.name = "window_coverage"  # type: ignore[misc]
    with pytest.raises(ValueError, match="name"):
        TemporalCheck("invented_check", TemporalDriftStatus.PASS, "OK")
    with pytest.raises(TypeError, match="TemporalDriftStatus"):
        TemporalCheck("cohort_size", "PASS", "OK")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="compatible"):
        TemporalCheck("cohort_size", TemporalDriftStatus.FAIL, "OK")
    with pytest.raises(ValueError, match="reason_code"):
        TemporalCheck("cohort_size", TemporalDriftStatus.PASS, "INVENTED")


def test_report_is_frozen_canonical_aggregate_only_and_exactly_shaped() -> None:
    source_status_counts = {"PASS": 2, "FAIL": 0, "UNEVALUABLE": 0}
    source_metric_counts = _metric_counts()
    report = _report(
        status_counts=source_status_counts,
        metric_counts=source_metric_counts,
    )
    expected = {
        "report_version": "temporal-drift-report-v1",
        "policy_id": "temporal-v1",
        "policy_version": "1",
        "cohort_profile": "development-v1",
        "cohort_seed": 7,
        "cohort_size": 4,
        "status": "PASS",
        "status_counts": {"PASS": 2, "FAIL": 0, "UNEVALUABLE": 0},
        "metric_counts": {
            "growth_window_coverage": 1,
            "visible_visit_coverage": 0,
            "visible_event_rate": 0,
            "mean_inter_visit_days": 0,
            "mean_visit_count_step": 0,
            "recorded_event_rate_step": 0,
            "causal_event_order": 1,
            "causal_event_timing": 0,
        },
        "checks": [
            {"name": "cohort_size", "status": "PASS", "reason_code": "OK"},
            {
                "name": "window_coverage",
                "status": "PASS",
                "reason_code": "WITHIN_BOUND",
            },
            {
                "name": "sequence_metrics",
                "status": "PASS",
                "reason_code": "WITHIN_BOUND",
            },
            {
                "name": "causal_event_order",
                "status": "PASS",
                "reason_code": "OK",
            },
            {
                "name": "causal_event_timing",
                "status": "PASS",
                "reason_code": "OK",
            },
        ],
        "comparisons": [
            {
                "metric": "growth_window_coverage",
                "window_id": "early",
                "status": "PASS",
                "reason_code": "WITHIN_BOUND",
                "observed": 0.75,
                "target": 0.5,
                "difference": 0.0,
                "support_count": 3,
            },
            {
                "metric": "causal_event_order",
                "window_id": None,
                "status": "PASS",
                "reason_code": "OK",
                "observed": None,
                "target": None,
                "difference": None,
                "support_count": None,
            },
        ],
    }

    assert set(report.to_mapping()) == {
        "report_version",
        "policy_id",
        "policy_version",
        "cohort_profile",
        "cohort_seed",
        "cohort_size",
        "status",
        "status_counts",
        "metric_counts",
        "checks",
        "comparisons",
    }
    assert report.to_mapping() == expected
    expected_json = json.dumps(
        expected,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    assert report.canonical_json() == expected_json
    assert "\n" not in report.canonical_json()
    assert report.to_json_bytes() == (expected_json + "\n").encode("ascii")
    assert repr(report) == "TemporalDriftReport(<aggregate-only>)"

    source_status_counts["PASS"] = 99
    source_metric_counts["growth_window_coverage"] = 99
    assert report.status_counts["PASS"] == 2
    assert report.metric_counts["growth_window_coverage"] == 1
    with pytest.raises(FrozenInstanceError):
        report.cohort_seed = 9  # type: ignore[misc]
    with pytest.raises(TypeError):
        report.status_counts["PASS"] = 9  # type: ignore[index]


def test_report_uses_nonserialized_policy_window_order_not_lexical_ids() -> None:
    early = _coverage_comparison(window_id="z_early")
    late = _coverage_comparison(window_id="a_late")

    report = _report(
        comparisons=(late, early),
        status_counts={"PASS": 2, "FAIL": 0, "UNEVALUABLE": 0},
        metric_counts=_metric_counts(growth_window_coverage=2, causal_event_order=0),
        _window_order=("z_early", "a_late"),
    )

    assert [comparison.window_id for comparison in report.comparisons] == [
        "z_early",
        "a_late",
    ]
    assert "_window_order" not in report.to_mapping()
    assert "_window_order" not in {
        field.name for field in dataclasses.fields(TemporalDriftReport)
    }


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"report_version": "temporal-drift-report-v2"}, "report_version"),
        ({"policy_id": "patient-policy"}, "policy_id"),
        ({"policy_version": "../version"}, "policy_version"),
        ({"cohort_profile": "truth-profile"}, "cohort_profile"),
        ({"cohort_seed": True}, "cohort_seed"),
        ({"cohort_seed": -1}, "cohort_seed"),
        ({"cohort_size": False}, "cohort_size"),
        ({"cohort_size": -1}, "cohort_size"),
        ({"status": "PASS"}, "TemporalDriftStatus"),
        ({"status_counts": {"PASS": 2}}, "status_counts"),
        (
            {"status_counts": {"PASS": 1, "FAIL": 1, "UNEVALUABLE": 0}},
            "status_counts",
        ),
        ({"metric_counts": {"growth_window_coverage": 2}}, "metric_counts"),
        ({"metric_counts": _metric_counts(growth_window_coverage=2)}, "metric_counts"),
        ({"checks": list(_checks())}, "checks"),
        ({"checks": _checks()[:-1] + (_checks()[0],)}, "unique"),
        ({"comparisons": [_coverage_comparison()]}, "comparisons"),
    ],
)
def test_report_rejects_unsafe_inconsistent_and_mutable_inputs(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        _report(**changes)
