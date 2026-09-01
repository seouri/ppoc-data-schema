from __future__ import annotations

import dataclasses
import json
import math
from dataclasses import FrozenInstanceError
from types import MappingProxyType

import pytest

from synthetic.task_utility import (
    TASK_METRICS,
    TASK_REASON_CODES,
    TASK_UTILITY_REPORT_VERSION,
    TaskPrediction,
    TaskUtilityCell,
    TaskUtilityMetric,
    TaskUtilityPolicy,
    TaskUtilityReport,
    TaskUtilityStatus,
)


def _policy(**changes: object) -> TaskUtilityPolicy:
    values: dict[str, object] = {
        "policy_id": "task-utility-v1",
        "policy_version": "1",
        "minimum_cohort_size": 4,
        "minimum_evaluable_members": 2,
        "minimum_class_support": 1,
        "maximum_unevaluable_members": 1,
        "require_probability_scores": True,
        "minimum_sensitivity": 0.5,
        "minimum_specificity": 0.8,
        "minimum_auroc": 0.7,
        "maximum_brier_score": 0.25,
        "subgroup_dimensions": ("sex",),
    }
    values.update(changes)
    return TaskUtilityPolicy(**values)  # type: ignore[arg-type]


_METRIC_VALUES: dict[str, tuple[object, object, int, str]] = {
    "sensitivity": (0.5, 0.5, 2, "WITHIN_BOUND"),
    "specificity": (1.0, 0.8, 2, "WITHIN_BOUND"),
    "precision": (1.0, None, 1, "OK"),
    "balanced_accuracy": (0.75, None, 4, "OK"),
    "auroc": (0.75, 0.7, 4, "WITHIN_BOUND"),
    "brier_score": (0.2, 0.25, 4, "WITHIN_BOUND"),
    "false_positive_count": (0, None, 4, "OK"),
    "false_negative_count": (1, None, 4, "OK"),
}


def _metric(name: str, **changes: object) -> TaskUtilityMetric:
    observed, target, support_count, reason_code = _METRIC_VALUES[name]
    values: dict[str, object] = {
        "name": name,
        "status": TaskUtilityStatus.PASS,
        "reason_code": reason_code,
        "observed": observed,
        "target": target,
        "support_count": support_count,
    }
    values.update(changes)
    return TaskUtilityMetric(**values)  # type: ignore[arg-type]


def _unevaluable_metric(name: str, reason_code: str) -> TaskUtilityMetric:
    return TaskUtilityMetric(
        name=name,
        status=TaskUtilityStatus.UNEVALUABLE,
        reason_code=reason_code,
        observed=None,
        target=None,
        support_count=None,
    )


def _structural_metric(name: str) -> TaskUtilityMetric:
    return TaskUtilityMetric(
        name=name,
        status=TaskUtilityStatus.FAIL,
        reason_code="STRUCTURAL_INVALID",
        observed=None,
        target=None,
        support_count=None,
    )


def _metrics(**replacements: TaskUtilityMetric) -> tuple[TaskUtilityMetric, ...]:
    return tuple(replacements.get(name, _metric(name)) for name in TASK_METRICS)


def _cell(**changes: object) -> TaskUtilityCell:
    values: dict[str, object] = {
        "scope": "overall",
        "status": TaskUtilityStatus.PASS,
        "reason_code": "WITHIN_BOUND",
        "member_count": 4,
        "evaluable_count": 4,
        "unevaluable_count": 0,
        "missing_score_count": 0,
        "positive_count": 2,
        "negative_count": 2,
        "true_positive": 1,
        "true_negative": 2,
        "false_positive": 0,
        "false_negative": 1,
        "metrics": _metrics(),
    }
    values.update(changes)
    return TaskUtilityCell(**values)  # type: ignore[arg-type]


def _structural_cell() -> TaskUtilityCell:
    return TaskUtilityCell(
        scope="overall",
        status=TaskUtilityStatus.FAIL,
        reason_code="STRUCTURAL_INVALID",
        member_count=0,
        evaluable_count=0,
        unevaluable_count=0,
        missing_score_count=0,
        positive_count=None,
        negative_count=None,
        true_positive=None,
        true_negative=None,
        false_positive=None,
        false_negative=None,
        metrics=tuple(_structural_metric(name) for name in TASK_METRICS),
    )


def _missing_prediction_cell() -> TaskUtilityCell:
    return TaskUtilityCell(
        scope="overall",
        status=TaskUtilityStatus.UNEVALUABLE,
        reason_code="MISSING_PREDICTION",
        member_count=4,
        evaluable_count=3,
        unevaluable_count=1,
        missing_score_count=0,
        positive_count=None,
        negative_count=None,
        true_positive=None,
        true_negative=None,
        false_positive=None,
        false_negative=None,
        metrics=_metrics(),
    )


def _status_counts(**changes: int) -> dict[str, int]:
    values = {"PASS": 1, "FAIL": 0, "UNEVALUABLE": 0}
    values.update(changes)
    return values


def _metric_counts(**changes: int) -> dict[str, int]:
    values = {metric: 1 for metric in TASK_METRICS}
    values.update(changes)
    return values


def _report(**changes: object) -> TaskUtilityReport:
    values: dict[str, object] = {
        "report_version": TASK_UTILITY_REPORT_VERSION,
        "policy_id": "task-utility-v1",
        "policy_version": "1",
        "cohort_profile": "development-v1",
        "cohort_seed": 7,
        "cohort_size": 4,
        "status": TaskUtilityStatus.PASS,
        "reason_code": "WITHIN_BOUND",
        "status_counts": _status_counts(),
        "metric_counts": _metric_counts(),
        "evaluable_count": 4,
        "unevaluable_count": 0,
        "cells": (_cell(),),
    }
    values.update(changes)
    return TaskUtilityReport(**values)  # type: ignore[arg-type]


def test_fixed_registries_and_status_enum_are_exact() -> None:
    assert TASK_UTILITY_REPORT_VERSION == "task-utility-report-v1"
    assert TASK_METRICS == (
        "sensitivity",
        "specificity",
        "precision",
        "balanced_accuracy",
        "auroc",
        "brier_score",
        "false_positive_count",
        "false_negative_count",
    )
    assert TASK_REASON_CODES == (
        "OK",
        "WITHIN_BOUND",
        "OUTSIDE_BOUND",
        "COHORT_TOO_SMALL",
        "INSUFFICIENT_SUPPORT",
        "MISSING_PREDICTION",
        "MISSING_SCORE",
        "STRUCTURAL_INVALID",
    )
    assert tuple(status.value for status in TaskUtilityStatus) == (
        "PASS",
        "FAIL",
        "UNEVALUABLE",
    )


def test_policy_is_frozen_and_accepts_only_the_fixed_subgroup_contract() -> None:
    policy = _policy()
    overall_only = _policy(
        require_probability_scores=False,
        subgroup_dimensions=(),
    )

    assert policy.require_probability_scores is True
    assert policy.subgroup_dimensions == ("sex",)
    assert overall_only.require_probability_scores is False
    assert overall_only.subgroup_dimensions == ()
    with pytest.raises(FrozenInstanceError):
        policy.policy_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("minimum_cohort_size", 0),
        ("minimum_cohort_size", True),
        ("minimum_evaluable_members", 0),
        ("minimum_evaluable_members", 1.5),
        ("minimum_class_support", 0),
        ("minimum_class_support", False),
        ("maximum_unevaluable_members", -1),
        ("maximum_unevaluable_members", True),
    ),
)
def test_policy_enforces_positive_and_zero_integer_floor_semantics(
    field: str, value: object
) -> None:
    with pytest.raises(ValueError, match=field):
        _policy(**{field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("minimum_sensitivity", -0.01),
        ("minimum_specificity", 1.01),
        ("minimum_auroc", math.nan),
        ("maximum_brier_score", math.inf),
        ("minimum_sensitivity", True),
        ("minimum_specificity", "0.8"),
    ),
)
def test_policy_requires_finite_probability_thresholds(
    field: str, value: object
) -> None:
    with pytest.raises(ValueError, match=field):
        _policy(**{field: value})


@pytest.mark.parametrize("value", (1, None, "true"))
def test_policy_requires_a_real_probability_score_switch(value: object) -> None:
    with pytest.raises(TypeError, match="require_probability_scores"):
        _policy(require_probability_scores=value)


@pytest.mark.parametrize(
    "value",
    (["sex"], ("race",), ("sex", "sex"), ("sex", "race")),
)
def test_policy_rejects_mutable_duplicate_or_unsupported_subgroups(
    value: object,
) -> None:
    with pytest.raises((TypeError, ValueError), match="subgroup_dimensions"):
        _policy(subgroup_dimensions=value)


@pytest.mark.parametrize(
    ("field", "value"),
    (("policy_id", "patient-policy"), ("policy_version", "../version")),
)
def test_policy_rejects_nonaggregate_identity(field: str, value: str) -> None:
    with pytest.raises(ValueError, match=field):
        _policy(**{field: value})


def test_prediction_is_frozen_and_repr_redacts_task_output() -> None:
    prediction = TaskPrediction(predicted_disorder=True, risk_score=0.75)

    assert prediction.risk_score == 0.75
    assert TaskPrediction(False).risk_score is None
    assert TaskPrediction(None).risk_score is None
    assert repr(prediction) == "TaskPrediction(<evaluator-only>)"
    assert "True" not in repr(prediction)
    assert "0.75" not in repr(prediction)
    with pytest.raises(FrozenInstanceError):
        prediction.risk_score = 0.1  # type: ignore[misc]


@pytest.mark.parametrize(
    ("predicted_disorder", "risk_score"),
    (
        (1, None),
        ("yes", None),
        (None, 0.4),
        (True, True),
        (True, -0.01),
        (False, 1.01),
        (True, math.nan),
        (False, math.inf),
    ),
)
def test_prediction_rejects_malformed_or_partial_task_output(
    predicted_disorder: object, risk_score: object
) -> None:
    with pytest.raises((TypeError, ValueError)):
        TaskPrediction(  # type: ignore[arg-type]
            predicted_disorder=predicted_disorder,
            risk_score=risk_score,
        )


def test_metric_is_frozen_exactly_shaped_and_evaluator_safe() -> None:
    metric = _metric("sensitivity")

    assert metric.to_mapping() == {
        "name": "sensitivity",
        "status": "PASS",
        "reason_code": "WITHIN_BOUND",
        "observed": 0.5,
        "target": 0.5,
        "support_count": 2,
    }
    assert repr(metric) == "TaskUtilityMetric(<aggregate-only>)"
    with pytest.raises(FrozenInstanceError):
        metric.observed = 0.9  # type: ignore[misc]


@pytest.mark.parametrize(
    "metric",
    (
        _unevaluable_metric("sensitivity", "INSUFFICIENT_SUPPORT"),
        _unevaluable_metric("auroc", "MISSING_SCORE"),
        _structural_metric("false_positive_count"),
    ),
)
def test_unevaluable_and_structural_metrics_require_null_numeric_evidence(
    metric: TaskUtilityMetric,
) -> None:
    assert (metric.observed, metric.target, metric.support_count) == (
        None,
        None,
        None,
    )


@pytest.mark.parametrize(
    "changes",
    (
        {"status": TaskUtilityStatus.UNEVALUABLE, "reason_code": "MISSING_SCORE"},
        {"status": TaskUtilityStatus.FAIL, "reason_code": "STRUCTURAL_INVALID"},
    ),
)
def test_null_evidence_statuses_reject_numeric_metric_values(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="null numeric evidence"):
        _metric("auroc", **changes)


@pytest.mark.parametrize(
    ("name", "reason_code"),
    (
        ("false_positive_count", "COHORT_TOO_SMALL"),
        ("sensitivity", "MISSING_SCORE"),
        ("false_negative_count", "MISSING_SCORE"),
    ),
)
def test_unevaluable_metric_reason_must_apply_to_the_metric(
    name: str, reason_code: str
) -> None:
    with pytest.raises(ValueError, match="reason_code"):
        _unevaluable_metric(name, reason_code)


def test_missing_score_cell_rejects_all_metrics_as_missing_score() -> None:
    with pytest.raises(ValueError, match="reason_code"):
        _cell(
            status=TaskUtilityStatus.UNEVALUABLE,
            reason_code="MISSING_SCORE",
            missing_score_count=4,
            positive_count=None,
            negative_count=None,
            true_positive=None,
            true_negative=None,
            false_positive=None,
            false_negative=None,
            metrics=tuple(
                _unevaluable_metric(name, "MISSING_SCORE")
                for name in TASK_METRICS
            ),
        )


@pytest.mark.parametrize(
    ("name", "changes", "message"),
    (
        ("invented", {}, "name"),
        ("sensitivity", {"target": None}, "target"),
        ("specificity", {"support_count": 0}, "support_count"),
        ("precision", {"target": 0.5}, "target"),
        ("false_positive_count", {"observed": 0.0}, "observed"),
        ("false_negative_count", {"observed": -1}, "observed"),
        ("auroc", {"observed": math.nan}, "observed"),
        ("brier_score", {"observed": True}, "observed"),
        (
            "sensitivity",
            {
                "status": TaskUtilityStatus.FAIL,
                "reason_code": "OUTSIDE_BOUND",
                "observed": 0.6,
                "target": 0.5,
            },
            "status",
        ),
        (
            "brier_score",
            {
                "status": TaskUtilityStatus.FAIL,
                "reason_code": "OUTSIDE_BOUND",
                "observed": 0.2,
                "target": 0.25,
            },
            "status",
        ),
    ),
)
def test_metric_rejects_unknown_malformed_or_bound_inconsistent_values(
    name: str, changes: dict[str, object], message: str
) -> None:
    if name == "invented":
        with pytest.raises(ValueError, match=message):
            TaskUtilityMetric(
                name=name,
                status=TaskUtilityStatus.PASS,
                reason_code="OK",
                observed=0.5,
                target=None,
                support_count=1,
            )
    else:
        with pytest.raises((TypeError, ValueError), match=message):
            _metric(name, **changes)


def test_cell_is_frozen_exactly_shaped_and_metrics_are_fixed_order() -> None:
    cell = _cell(metrics=tuple(reversed(_metrics())))
    expected = {
        "scope": "overall",
        "status": "PASS",
        "reason_code": "WITHIN_BOUND",
        "member_count": 4,
        "evaluable_count": 4,
        "unevaluable_count": 0,
        "missing_score_count": 0,
        "positive_count": 2,
        "negative_count": 2,
        "true_positive": 1,
        "true_negative": 2,
        "false_positive": 0,
        "false_negative": 1,
        "metrics": [_metric(name).to_mapping() for name in TASK_METRICS],
    }

    assert cell.to_mapping() == expected
    assert tuple(metric.name for metric in cell.metrics) == TASK_METRICS
    assert repr(cell) == "TaskUtilityCell(<aggregate-only>)"
    with pytest.raises(FrozenInstanceError):
        cell.scope = "sex:F"  # type: ignore[misc]


def test_unevaluable_cell_retains_aggregate_counts_and_null_metric_evidence() -> None:
    cell = _cell(
        status=TaskUtilityStatus.UNEVALUABLE,
        reason_code="MISSING_SCORE",
        missing_score_count=4,
        positive_count=None,
        negative_count=None,
        true_positive=None,
        true_negative=None,
        false_positive=None,
        false_negative=None,
        metrics=_metrics(
            auroc=_unevaluable_metric("auroc", "MISSING_SCORE"),
            brier_score=_unevaluable_metric("brier_score", "MISSING_SCORE"),
        ),
    )

    assert cell.member_count == 4
    assert cell.evaluable_count == 4
    assert cell.missing_score_count == 4
    assert cell.positive_count is None
    assert cell.false_negative is None
    assert cell.metrics[4].observed is None
    assert cell.metrics[5].support_count is None

    with pytest.raises(ValueError, match="truth-dependent"):
        dataclasses.replace(cell, positive_count=2)


def test_optional_score_metrics_can_be_unevaluable_in_a_passing_cell() -> None:
    cell = _cell(
        missing_score_count=4,
        metrics=_metrics(
            auroc=_unevaluable_metric("auroc", "MISSING_SCORE"),
            brier_score=_unevaluable_metric("brier_score", "MISSING_SCORE"),
        ),
    )

    assert cell.status is TaskUtilityStatus.PASS
    assert tuple(metric.status for metric in cell.metrics[4:6]) == (
        TaskUtilityStatus.UNEVALUABLE,
        TaskUtilityStatus.UNEVALUABLE,
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"scope": "patient:001"}, "scope"),
        ({"status": "PASS"}, "TaskUtilityStatus"),
        ({"reason_code": "OUTSIDE_BOUND"}, "compatible"),
        ({"reason_code": "OK"}, "WITHIN_BOUND"),
        ({"member_count": True}, "member_count"),
        ({"evaluable_count": 3}, "member_count"),
        ({"unevaluable_count": -1}, "unevaluable_count"),
        ({"missing_score_count": 5}, "missing_score_count"),
        ({"positive_count": 3}, "evaluable_count"),
        ({"true_positive": 2}, "positive"),
        ({"true_negative": 1}, "negative"),
        ({"metrics": list(_metrics())}, "metrics"),
        ({"metrics": _metrics()[:-1]}, "metrics"),
        ({"metrics": _metrics(sensitivity=_metric("specificity"))}, "metrics"),
        (
            {
                "metrics": _metrics(
                    false_positive_count=_metric(
                        "false_positive_count", observed=1
                    )
                )
            },
            "false_positive_count",
        ),
    ),
)
def test_cell_rejects_unsafe_mutable_or_inconsistent_inputs(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        _cell(**changes)


def test_structural_cell_has_static_zero_counts_and_null_metric_evidence() -> None:
    cell = _structural_cell()

    numeric_counts = (
        cell.member_count,
        cell.evaluable_count,
        cell.unevaluable_count,
        cell.missing_score_count,
        cell.positive_count,
        cell.negative_count,
        cell.true_positive,
        cell.true_negative,
        cell.false_positive,
        cell.false_negative,
    )
    assert numeric_counts == (0, 0, 0, 0, None, None, None, None, None, None)
    assert all(metric.observed is None for metric in cell.metrics)
    with pytest.raises(ValueError, match="structural"):
        dataclasses.replace(cell, member_count=1)


def test_report_is_frozen_canonical_aggregate_only_and_exactly_shaped() -> None:
    source_status_counts = _status_counts()
    source_metric_counts = _metric_counts()
    report = _report(
        status_counts=source_status_counts,
        metric_counts=source_metric_counts,
    )
    expected = {
        "report_version": "task-utility-report-v1",
        "policy_id": "task-utility-v1",
        "policy_version": "1",
        "cohort_profile": "development-v1",
        "cohort_seed": 7,
        "cohort_size": 4,
        "status": "PASS",
        "reason_code": "WITHIN_BOUND",
        "status_counts": {"PASS": 1, "FAIL": 0, "UNEVALUABLE": 0},
        "metric_counts": {metric: 1 for metric in TASK_METRICS},
        "evaluable_count": 4,
        "unevaluable_count": 0,
        "cells": [_cell().to_mapping()],
    }

    assert set(report.to_mapping()) == {
        "report_version",
        "policy_id",
        "policy_version",
        "cohort_profile",
        "cohort_seed",
        "cohort_size",
        "status",
        "reason_code",
        "status_counts",
        "metric_counts",
        "evaluable_count",
        "unevaluable_count",
        "cells",
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
    assert repr(report) == "TaskUtilityReport(<aggregate-only>)"

    source_status_counts["PASS"] = 99
    source_metric_counts["sensitivity"] = 99
    assert report.status_counts["PASS"] == 1
    assert report.metric_counts["sensitivity"] == 1
    assert isinstance(report.status_counts, MappingProxyType)
    assert isinstance(report.metric_counts, MappingProxyType)
    with pytest.raises(FrozenInstanceError):
        report.cohort_seed = 9  # type: ignore[misc]


def test_report_sorts_unique_cells_by_fixed_observed_scope_order() -> None:
    overall = _cell()
    female = _cell(scope="sex:F")
    male = _cell(scope="sex:M")

    report = _report(
        cells=(male, overall, female),
        status_counts={"PASS": 3, "FAIL": 0, "UNEVALUABLE": 0},
        metric_counts={metric: 3 for metric in TASK_METRICS},
    )

    assert tuple(cell.scope for cell in report.cells) == (
        "overall",
        "sex:F",
        "sex:M",
    )


def test_static_structural_fallback_report_has_no_caller_evidence() -> None:
    report = _report(
        policy_id="unavailable",
        policy_version="unavailable",
        cohort_profile="unavailable",
        cohort_seed=0,
        cohort_size=0,
        status=TaskUtilityStatus.FAIL,
        reason_code="STRUCTURAL_INVALID",
        status_counts={"PASS": 0, "FAIL": 1, "UNEVALUABLE": 0},
        metric_counts={metric: 1 for metric in TASK_METRICS},
        evaluable_count=0,
        unevaluable_count=0,
        cells=(_structural_cell(),),
    )

    assert report.to_mapping()["cells"] == [_structural_cell().to_mapping()]
    assert "task-utility-v1" not in report.canonical_json()


def test_report_permits_the_explicit_bounded_missing_output_pass() -> None:
    report = _report(
        status=TaskUtilityStatus.PASS,
        reason_code="WITHIN_BOUND",
        status_counts={"PASS": 0, "FAIL": 0, "UNEVALUABLE": 1},
        evaluable_count=3,
        unevaluable_count=1,
        cells=(_missing_prediction_cell(),),
    )

    assert report.status is TaskUtilityStatus.PASS
    assert report.reason_code == "WITHIN_BOUND"
    assert report.cells[0].status is TaskUtilityStatus.UNEVALUABLE
    assert report.cells[0].reason_code == "MISSING_PREDICTION"


def test_unevaluable_report_rejects_reason_below_cell_precedence() -> None:
    with pytest.raises(ValueError, match="reason_code"):
        _report(
            status=TaskUtilityStatus.UNEVALUABLE,
            reason_code="MISSING_SCORE",
            status_counts={"PASS": 0, "FAIL": 0, "UNEVALUABLE": 1},
            evaluable_count=3,
            unevaluable_count=1,
            cells=(_missing_prediction_cell(),),
        )


def test_unevaluable_report_requires_evidence_for_missing_prediction() -> None:
    with pytest.raises(ValueError, match="reason_code"):
        _report(
            status=TaskUtilityStatus.UNEVALUABLE,
            reason_code="MISSING_PREDICTION",
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"report_version": "task-utility-report-v2"}, "report_version"),
        ({"policy_id": "patient-policy"}, "policy_id"),
        ({"policy_version": "../version"}, "policy_version"),
        ({"cohort_profile": "truth-profile"}, "cohort_profile"),
        ({"cohort_seed": True}, "cohort_seed"),
        ({"cohort_size": -1}, "cohort_size"),
        ({"status": "PASS"}, "TaskUtilityStatus"),
        ({"reason_code": "OUTSIDE_BOUND"}, "compatible"),
        ({"reason_code": "INVENTED"}, "reason_code"),
        ({"status_counts": {"PASS": 1}}, "status_counts"),
        (
            {"status_counts": {"PASS": 0, "FAIL": 1, "UNEVALUABLE": 0}},
            "status_counts",
        ),
        ({"metric_counts": {"sensitivity": 1}}, "metric_counts"),
        (
            {"metric_counts": _metric_counts(sensitivity=0)},
            "metric_counts",
        ),
        ({"evaluable_count": True}, "evaluable_count"),
        ({"unevaluable_count": -1}, "unevaluable_count"),
        ({"evaluable_count": 3}, "cohort_size"),
        ({"cells": [_cell()]}, "cells"),
        ({"cells": (_cell(), _cell())}, "scope"),
        ({"cells": (_cell(scope="sex:F"),)}, "overall"),
        ({"cells": (_structural_cell(),)}, "status"),
    ),
)
def test_report_rejects_unsafe_mutable_or_inconsistent_inputs(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        _report(**changes)


def test_dataclass_field_contracts_are_exact() -> None:
    assert tuple(field.name for field in dataclasses.fields(TaskUtilityPolicy)) == (
        "policy_id",
        "policy_version",
        "minimum_cohort_size",
        "minimum_evaluable_members",
        "minimum_class_support",
        "maximum_unevaluable_members",
        "require_probability_scores",
        "minimum_sensitivity",
        "minimum_specificity",
        "minimum_auroc",
        "maximum_brier_score",
        "subgroup_dimensions",
    )
    assert tuple(field.name for field in dataclasses.fields(TaskPrediction)) == (
        "predicted_disorder",
        "risk_score",
    )
    assert tuple(field.name for field in dataclasses.fields(TaskUtilityMetric)) == (
        "name",
        "status",
        "reason_code",
        "observed",
        "target",
        "support_count",
    )
    assert tuple(field.name for field in dataclasses.fields(TaskUtilityCell)) == (
        "scope",
        "status",
        "reason_code",
        "member_count",
        "evaluable_count",
        "unevaluable_count",
        "missing_score_count",
        "positive_count",
        "negative_count",
        "true_positive",
        "true_negative",
        "false_positive",
        "false_negative",
        "metrics",
    )
    assert tuple(field.name for field in dataclasses.fields(TaskUtilityReport)) == (
        "report_version",
        "policy_id",
        "policy_version",
        "cohort_profile",
        "cohort_seed",
        "cohort_size",
        "status",
        "reason_code",
        "status_counts",
        "metric_counts",
        "evaluable_count",
        "unevaluable_count",
        "cells",
    )
