from __future__ import annotations

import ast
import dataclasses
import inspect
from collections.abc import Mapping, Sequence

import pytest

import synthetic.task_utility as task_utility_module
from synthetic.models import ClinicalEvent, DisorderKind
from synthetic.native.observations import (
    CensoringMode,
    EncounterType,
    EventRecordingDecision,
    MeasurementAvailability,
    MeasurementChannel,
    MeasurementTruth,
    ObservationPolicy,
    ObservationWindow,
    RecordedEvent,
    RecordedEventKind,
    VisitOpportunity,
)
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
    task_cohort,
    task_member,
    task_member_with_bundle,
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


def _assert_null_metric_evidence(report: object) -> None:
    cell = report.cells[0]  # type: ignore[attr-defined]
    assert all(metric.status is TaskUtilityStatus.UNEVALUABLE for metric in cell.metrics)
    assert all(
        (metric.observed, metric.target, metric.support_count) == (None, None, None)
        for metric in cell.metrics
    )


def _assert_static_fallback(report: object, hostile_value: object) -> None:
    mapping = report.to_mapping()  # type: ignore[attr-defined]
    assert mapping["status"] == "FAIL"
    assert mapping["reason_code"] == "STRUCTURAL_INVALID"
    assert mapping["policy_id"] == "unavailable"
    assert mapping["cohort_profile"] == "unavailable"
    assert mapping["cohort_seed"] == 0
    assert mapping["cohort_size"] == 0
    assert str(hostile_value) not in report.canonical_json()  # type: ignore[attr-defined]


def test_metric_extraction_does_not_collect_score_truth_pairs() -> None:
    tree = ast.parse(inspect.getsource(task_utility_module))
    pair_annotations = tuple(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign)
        and ast.unparse(node.annotation) == "list[tuple[float, bool]]"
    )
    pair_appends = tuple(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "append"
        and node.args
        and isinstance(node.args[0], ast.Tuple)
        and any(
            isinstance(item, ast.Attribute) and item.attr == "risk_score"
            for item in ast.walk(node.args[0])
        )
        and any(
            isinstance(item, ast.Name) and item.id == "truth"
            for item in ast.walk(node.args[0])
        )
    )

    assert pair_annotations == ()
    assert pair_appends == ()


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
    _assert_null_metric_evidence(report)


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
    _assert_null_metric_evidence(report)


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
    _assert_null_metric_evidence(report)


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
    _assert_null_metric_evidence(report)


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
    _assert_null_metric_evidence(report)


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
    assert set(metrics) == set(TASK_METRICS)
    _assert_null_metric_evidence(report)


@pytest.mark.parametrize(
    "kind",
    (DisorderKind.HEALTHY, DisorderKind.GROWTH_HORMONE_DEFICIENCY),
)
def test_singleton_floor_never_exposes_truth_derived_metric_evidence(
    kind: DisorderKind,
) -> None:
    cohort = task_cohort(task_member(8, kind))
    report = evaluate_task_utility(
        cohort,
        (TaskPrediction(False, 0.25),),
        task_policy(
            minimum_cohort_size=2,
            minimum_evaluable_members=1,
            minimum_sensitivity=0.0,
            minimum_specificity=0.0,
            minimum_auroc=0.0,
            maximum_brier_score=1.0,
        ),
    )

    assert report.status is TaskUtilityStatus.UNEVALUABLE
    assert report.reason_code == "COHORT_TOO_SMALL"
    assert report.cells[0].positive_count is None
    assert report.cells[0].negative_count is None
    _assert_null_metric_evidence(report)


def test_below_cohort_floor_nulls_even_otherwise_evaluable_metrics() -> None:
    report = evaluate_task_utility(
        balanced_task_cohort(),
        scored_task_predictions(),
        task_policy(minimum_cohort_size=5),
    )

    assert report.status is TaskUtilityStatus.UNEVALUABLE
    assert report.reason_code == "COHORT_TOO_SMALL"
    _assert_null_metric_evidence(report)


def test_required_mixed_evidence_has_one_canonical_report_reason() -> None:
    predictions = (
        TaskPrediction(True),
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

    assert report.reason_code == "MISSING_SCORE"
    with pytest.raises(ValueError, match="reason_code"):
        dataclasses.replace(report, reason_code="INSUFFICIENT_SUPPORT")


def test_optional_score_does_not_override_support_as_canonical_reason() -> None:
    predictions = (
        TaskPrediction(True),
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
            require_probability_scores=False,
        ),
    )

    assert report.reason_code == "INSUFFICIENT_SUPPORT"
    with pytest.raises(ValueError, match="reason_code"):
        dataclasses.replace(report, reason_code="MISSING_SCORE")


def test_corrupted_latent_state_returns_static_fallback() -> None:
    cohort = balanced_task_cohort()
    hostile_age = -999
    object.__setattr__(
        cohort.members[0].trajectory.disorder,
        "onset_age_days",
        hostile_age,
    )

    report = evaluate_task_utility(cohort, scored_task_predictions(), task_policy())

    _assert_static_fallback(report, hostile_age)


@pytest.mark.parametrize(
    ("target", "field", "hostile_value"),
    (
        ("point", "age_days", -777),
        ("trajectory", "events", ["hostile-event-secret"]),
        ("member", "frame", "hostile-frame-secret"),
        ("cohort", "profile", "patient-hostile-profile"),
        ("cohort", "seed", -333),
        ("calibration", "recorded_healthy_probability", 2.0),
        ("cohort", "members", ["hostile-member-secret"]),
    ),
)
def test_corrupted_nested_cohort_returns_static_fallback(
    target: str,
    field: str,
    hostile_value: object,
) -> None:
    cohort = balanced_task_cohort()
    targets = {
        "point": cohort.members[0].trajectory.physiology.points[0],
        "trajectory": cohort.members[0].trajectory,
        "member": cohort.members[0],
        "cohort": cohort,
        "calibration": cohort.calibration,
    }
    object.__setattr__(targets[target], field, hostile_value)

    report = evaluate_task_utility(cohort, scored_task_predictions(), task_policy())

    _assert_static_fallback(report, hostile_value)


@pytest.mark.parametrize(
    ("target", "field", "hostile_value"),
    (
        ("measurement", "recorded_value", -123.45),
        ("measurement", "availability", MeasurementAvailability.MISSING),
        ("visit", "age_days", -101),
        ("window", "effective_end_age_days", -404),
        ("truth", "opportunities", ["hostile-opportunity"]),
        ("truth", "patient_id", "syn-hostile-other-patient"),
    ),
)
def test_corrupted_observation_child_returns_static_fallback(
    target: str,
    field: str,
    hostile_value: object,
) -> None:
    cohort = balanced_task_cohort()
    frame = cohort.members[0].frame
    targets = {
        "measurement": frame.visits[0].measurements[0],
        "visit": frame.visits[0],
        "window": frame.window,
        "truth": frame.truth,
    }
    object.__setattr__(targets[target], field, hostile_value)

    report = evaluate_task_utility(cohort, scored_task_predictions(), task_policy())

    _assert_static_fallback(report, hostile_value)


def test_corrupted_visible_recorded_event_returns_static_fallback() -> None:
    cohort = balanced_task_cohort()
    frame = cohort.members[0].frame
    event = RecordedEvent(
        patient_id=frame.patient_id,
        age_days=frame.visits[0].age_days,
        event_kind=RecordedEventKind.RECOGNITION,
        code="SYN-GROWTH-RECOGNITION",
    )
    hostile_code = "hostile-recorded-event-code"
    object.__setattr__(event, "code", hostile_code)
    object.__setattr__(frame, "events", (event,))

    report = evaluate_task_utility(cohort, scored_task_predictions(), task_policy())

    _assert_static_fallback(report, hostile_code)


@pytest.mark.parametrize(
    "target",
    (
        "opportunity",
        "measurement_truth",
        "event_decision",
        "source_event",
        "policy",
        "latent_trajectory",
    ),
)
def test_corrupted_truth_child_returns_static_fallback(target: str) -> None:
    cohort = balanced_task_cohort()
    member = cohort.members[0]
    truth = member.frame.truth
    hostile_value: object
    if target == "opportunity":
        child = VisitOpportunity(0, 100, EncounterType.ROUTINE, True)
        hostile_value = -301
        object.__setattr__(child, "age_days", hostile_value)
        object.__setattr__(truth, "opportunities", (child,))
    elif target == "measurement_truth":
        child = MeasurementTruth(
            0,
            MeasurementChannel.WEIGHT,
            MeasurementAvailability.OBSERVED,
            6.1,
            0.0,
        )
        hostile_value = -302.5
        object.__setattr__(child, "latent_value", hostile_value)
        object.__setattr__(truth, "measurement_truth", (child,))
    elif target in {"event_decision", "source_event"}:
        source_event = ClinicalEvent(
            member.demographics.patient_id,
            100,
            "recognition_opportunity",
            None,
            False,
        )
        decision = EventRecordingDecision(0, False, None)
        object.__setattr__(truth, "source_events", (source_event,))
        object.__setattr__(truth, "event_decisions", (decision,))
        if target == "event_decision":
            hostile_value = -303
            object.__setattr__(decision, "source_event_index", hostile_value)
        else:
            hostile_value = "hostile-source-event-code"
            object.__setattr__(source_event, "code", hostile_value)
    elif target == "policy":
        policy = ObservationPolicy("observation-v1", 0, 200)
        hostile_value = -0.25
        object.__setattr__(policy, "visit_probability", hostile_value)
        object.__setattr__(truth, "policy", policy)
    else:
        physiology = member.trajectory.physiology
        point = dataclasses.replace(physiology.points[0])
        copied_physiology = dataclasses.replace(physiology, points=(point,))
        copied_trajectory = dataclasses.replace(
            member.trajectory,
            physiology=copied_physiology,
        )
        hostile_value = -304
        object.__setattr__(point, "age_days", hostile_value)
        object.__setattr__(truth, "latent_trajectory", copied_trajectory)

    report = evaluate_task_utility(cohort, scored_task_predictions(), task_policy())

    _assert_static_fallback(report, hostile_value)


def test_frame_and_truth_window_mismatch_returns_static_fallback() -> None:
    cohort = balanced_task_cohort()
    mismatched_window = ObservationWindow(0, 199, 199, CensoringMode.NONE)
    object.__setattr__(cohort.members[0].frame.truth, "window", mismatched_window)

    report = evaluate_task_utility(cohort, scored_task_predictions(), task_policy())

    _assert_static_fallback(report, 199)


@pytest.mark.parametrize(
    ("target", "field", "hostile_value"),
    (
        ("shape", "resources", ["hostile-resource-spec"]),
        ("row", "values", [("patient_id", "hostile-row-patient")]),
        ("descendant", "age_days", -202),
        ("source_frame", "patient_id", "syn-hostile-source-patient"),
    ),
)
def test_corrupted_resource_bundle_child_returns_static_fallback(
    target: str,
    field: str,
    hostile_value: object,
) -> None:
    member = task_member_with_bundle(10, DisorderKind.HEALTHY)
    assert member.bundle is not None
    targets = {
        "shape": member.bundle.shape,
        "row": next(iter(member.bundle.rows.values()))[0],
        "descendant": member.bundle.clinical_descendants[0],
        "source_frame": member.bundle.source_frame,
    }
    object.__setattr__(targets[target], field, hostile_value)
    cohort = task_cohort(member)

    report = evaluate_task_utility(
        cohort,
        (TaskPrediction(False, 0.25),),
        task_policy(
            minimum_cohort_size=1,
            minimum_evaluable_members=1,
            minimum_sensitivity=0.0,
            minimum_specificity=0.0,
            minimum_auroc=0.0,
            maximum_brier_score=1.0,
        ),
    )

    _assert_static_fallback(report, hostile_value)


def test_wrong_prediction_length_stops_before_deep_member_read() -> None:
    class AccessTrackingFloat(float):
        accessed = False

        def __lt__(self, other: object) -> bool:
            type(self).accessed = True
            raise RuntimeError("hostile nested value must remain unread")

    cohort = balanced_task_cohort()
    hostile_value = AccessTrackingFloat(-123.45)
    object.__setattr__(
        cohort.members[0].trajectory.disorder,
        "severity",
        hostile_value,
    )

    report = evaluate_task_utility(
        cohort,
        scored_task_predictions()[:-1],
        task_policy(),
    )

    _assert_static_fallback(report, hostile_value)
    assert AccessTrackingFloat.accessed is False


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
