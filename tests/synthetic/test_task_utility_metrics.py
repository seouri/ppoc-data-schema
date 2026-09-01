from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest

from synthetic.task_utility import (
    TASK_METRICS,
    TaskPrediction,
    TaskUtilityMetric,
    TaskUtilityStatus,
    evaluate_task_utility,
)
from tests.synthetic.task_utility_fixtures import (
    balanced_task_cohort,
    scored_task_predictions,
    task_policy,
)


def _metrics(report: object) -> dict[str, TaskUtilityMetric]:
    cell = report.cells[0]  # type: ignore[attr-defined]
    return {metric.name: metric for metric in cell.metrics}


def _scalar_values(value: object) -> tuple[object, ...]:
    if isinstance(value, Mapping):
        return tuple(
            item
            for nested in value.values()
            for item in _scalar_values(nested)
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(item for nested in value for item in _scalar_values(nested))
    return (value,)


def test_evaluator_computes_exact_overall_confusion_and_rates() -> None:
    report = evaluate_task_utility(
        balanced_task_cohort(),
        scored_task_predictions(),
        task_policy(),
    )
    cell = report.cells[0]
    metrics = _metrics(report)

    assert report.status is TaskUtilityStatus.PASS
    assert report.reason_code == "WITHIN_BOUND"
    assert (cell.member_count, cell.evaluable_count, cell.unevaluable_count) == (
        4,
        4,
        0,
    )
    assert (
        cell.positive_count,
        cell.negative_count,
        cell.true_positive,
        cell.true_negative,
        cell.false_positive,
        cell.false_negative,
    ) == (2, 2, 1, 1, 1, 1)
    assert metrics["sensitivity"].observed == 0.5
    assert metrics["specificity"].observed == 0.5
    assert metrics["precision"].observed == 0.5
    assert metrics["balanced_accuracy"].observed == 0.5
    assert metrics["false_positive_count"].observed == 1
    assert metrics["false_negative_count"].observed == 1


def test_evaluator_uses_tied_midranks_and_exact_brier_mean() -> None:
    metrics = _metrics(
        evaluate_task_utility(
            balanced_task_cohort(),
            scored_task_predictions(),
            task_policy(),
        )
    )

    assert metrics["auroc"].observed == 0.875
    assert metrics["auroc"].support_count == 4
    assert metrics["brier_score"].observed == 0.15625
    assert metrics["brier_score"].support_count == 4


def test_optional_scores_leave_binary_diagnostics_passing() -> None:
    predictions = tuple(
        TaskPrediction(item.predicted_disorder) for item in scored_task_predictions()
    )
    report = evaluate_task_utility(
        balanced_task_cohort(),
        predictions,
        task_policy(require_probability_scores=False),
    )
    metrics = _metrics(report)

    assert report.status is TaskUtilityStatus.PASS
    assert report.cells[0].status is TaskUtilityStatus.PASS
    assert report.cells[0].missing_score_count == 4
    assert tuple(metrics[name].status for name in TASK_METRICS[:4]) == (
        TaskUtilityStatus.PASS,
        TaskUtilityStatus.PASS,
        TaskUtilityStatus.PASS,
        TaskUtilityStatus.PASS,
    )
    assert metrics["auroc"].to_mapping() == {
        "name": "auroc",
        "status": "UNEVALUABLE",
        "reason_code": "MISSING_SCORE",
        "observed": None,
        "target": None,
        "support_count": None,
    }
    assert metrics["brier_score"].reason_code == "MISSING_SCORE"
    assert metrics["false_positive_count"].observed == 1
    assert metrics["false_negative_count"].observed == 1


def test_required_missing_scores_make_report_unevaluable() -> None:
    predictions = tuple(
        TaskPrediction(item.predicted_disorder) for item in scored_task_predictions()
    )
    report = evaluate_task_utility(
        balanced_task_cohort(),
        predictions,
        task_policy(require_probability_scores=True),
    )

    assert report.status is TaskUtilityStatus.UNEVALUABLE
    assert report.reason_code == "MISSING_SCORE"
    assert report.cells[0].status is TaskUtilityStatus.UNEVALUABLE
    assert report.cells[0].reason_code == "MISSING_SCORE"
    assert report.cells[0].positive_count is None
    assert report.cells[0].true_positive is None


def test_allowed_missing_decision_does_not_hide_required_missing_score() -> None:
    predictions = (
        TaskPrediction(True),
        TaskPrediction(None),
        TaskPrediction(False, 0.5),
        TaskPrediction(False, 0.25),
    )
    report = evaluate_task_utility(
        balanced_task_cohort(),
        predictions,
        task_policy(maximum_unevaluable_members=1),
    )

    assert report.status is TaskUtilityStatus.UNEVALUABLE
    assert report.reason_code == "MISSING_SCORE"
    assert report.cells[0].reason_code == "MISSING_PREDICTION"


def test_allowed_missing_decision_does_not_hide_insufficient_support() -> None:
    predictions = (
        TaskPrediction(True, 0.75),
        TaskPrediction(None),
        TaskPrediction(False, 0.5),
        TaskPrediction(False, 0.25),
    )
    report = evaluate_task_utility(
        balanced_task_cohort(),
        predictions,
        task_policy(
            maximum_unevaluable_members=1,
            minimum_class_support=2,
        ),
    )

    assert report.status is TaskUtilityStatus.UNEVALUABLE
    assert report.reason_code == "INSUFFICIENT_SUPPORT"
    assert report.cells[0].reason_code == "MISSING_PREDICTION"


def test_allowed_missing_decision_preserves_explicit_report_pass() -> None:
    predictions = (
        TaskPrediction(True, 0.75),
        TaskPrediction(None),
        TaskPrediction(False, 0.5),
        TaskPrediction(False, 0.25),
    )
    report = evaluate_task_utility(
        balanced_task_cohort(),
        predictions,
        task_policy(maximum_unevaluable_members=1),
    )

    assert report.status is TaskUtilityStatus.PASS
    assert report.reason_code == "WITHIN_BOUND"
    assert report.evaluable_count == 3
    assert report.unevaluable_count == 1
    assert report.cells[0].status is TaskUtilityStatus.UNEVALUABLE
    assert report.cells[0].reason_code == "MISSING_PREDICTION"
    assert report.cells[0].positive_count is None


def test_excess_missing_decisions_make_report_unevaluable() -> None:
    predictions = (
        TaskPrediction(True, 0.75),
        TaskPrediction(None),
        TaskPrediction(False, 0.5),
        TaskPrediction(False, 0.25),
    )
    report = evaluate_task_utility(
        balanced_task_cohort(),
        predictions,
        task_policy(maximum_unevaluable_members=0),
    )

    assert report.status is TaskUtilityStatus.UNEVALUABLE
    assert report.reason_code == "MISSING_PREDICTION"


@pytest.mark.parametrize(
    "policy_changes",
    (
        {"minimum_cohort_size": 5},
        {"minimum_evaluable_members": 4, "maximum_unevaluable_members": 1},
    ),
)
def test_cohort_and_evaluable_floors_use_report_level_reason(
    policy_changes: dict[str, object],
) -> None:
    predictions = scored_task_predictions()
    if "minimum_evaluable_members" in policy_changes:
        predictions = (
            predictions[0],
            TaskPrediction(None),
            predictions[2],
            predictions[3],
        )
    report = evaluate_task_utility(
        balanced_task_cohort(),
        predictions,
        task_policy(**policy_changes),
    )

    assert report.status is TaskUtilityStatus.UNEVALUABLE
    assert report.reason_code == "COHORT_TOO_SMALL"


def test_minimum_class_support_nulls_only_unsupported_metrics() -> None:
    report = evaluate_task_utility(
        balanced_task_cohort(),
        scored_task_predictions(),
        task_policy(minimum_class_support=3),
    )
    metrics = _metrics(report)

    assert report.status is TaskUtilityStatus.UNEVALUABLE
    assert report.reason_code == "INSUFFICIENT_SUPPORT"
    assert report.cells[0].status is TaskUtilityStatus.UNEVALUABLE
    assert metrics["sensitivity"].observed is None
    assert metrics["specificity"].observed is None
    assert metrics["balanced_accuracy"].observed is None
    assert metrics["precision"].observed == 0.5
    assert metrics["auroc"].observed == 0.875
    assert metrics["brier_score"].observed == 0.15625


@pytest.mark.parametrize(
    ("policy_changes", "metric_name"),
    (
        ({"minimum_sensitivity": 0.6}, "sensitivity"),
        ({"minimum_specificity": 0.6}, "specificity"),
        ({"minimum_auroc": 0.9}, "auroc"),
        ({"maximum_brier_score": 0.1}, "brier_score"),
    ),
)
def test_evaluated_threshold_failure_has_global_precedence(
    policy_changes: dict[str, object], metric_name: str
) -> None:
    report = evaluate_task_utility(
        balanced_task_cohort(),
        scored_task_predictions(),
        task_policy(**policy_changes),
    )

    assert report.status is TaskUtilityStatus.FAIL
    assert report.reason_code == "OUTSIDE_BOUND"
    assert _metrics(report)[metric_name].status is TaskUtilityStatus.FAIL


@pytest.mark.parametrize(
    "invalid_predictions",
    (
        list(scored_task_predictions()),
        scored_task_predictions()[:-1],
        (*scored_task_predictions()[:-1], object()),
    ),
)
def test_invalid_prediction_container_returns_static_structural_fallback(
    invalid_predictions: object,
) -> None:
    report = evaluate_task_utility(
        balanced_task_cohort(),
        invalid_predictions,  # type: ignore[arg-type]
        task_policy(),
    )

    assert report.status is TaskUtilityStatus.FAIL
    assert report.reason_code == "STRUCTURAL_INVALID"
    assert report.policy_id == "unavailable"
    assert report.cohort_profile == "unavailable"
    assert report.cohort_size == 0
    assert report.cells[0].member_count == 0


def test_report_is_deterministic_and_contains_no_member_level_material() -> None:
    cohort = balanced_task_cohort()
    predictions = (
        TaskPrediction(True, 0.91),
        TaskPrediction(False, 0.81),
        TaskPrediction(True, 0.61),
        TaskPrediction(False, 0.11),
    )
    policy = task_policy(minimum_auroc=0.5, maximum_brier_score=0.5)

    first = evaluate_task_utility(cohort, predictions, policy)
    second = evaluate_task_utility(cohort, predictions, policy)
    mapping = first.to_mapping()
    scalar_values = _scalar_values(mapping)

    assert first.to_json_bytes() == second.to_json_bytes()
    assert repr(first) == "TaskUtilityReport(<aggregate-only>)"
    for member in cohort.members:
        assert member.demographics.patient_id not in first.canonical_json()
        assert member.frame.visits[0].visit_id not in first.canonical_json()
        assert member.frame.visits[0].measurements[0].recorded_value not in scalar_values
    for prediction in predictions:
        assert prediction.risk_score not in scalar_values
    assert not {"patient_id", "visit_id", "truth", "risk_score"} & set(mapping)
