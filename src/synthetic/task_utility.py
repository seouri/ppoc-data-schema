"""Strict aggregate-only contracts for synthetic task-utility evaluation."""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from synthetic.calibration import require_aggregate_safe_token

TASK_UTILITY_REPORT_VERSION = "task-utility-report-v1"

TASK_METRICS = (
    "sensitivity",
    "specificity",
    "precision",
    "balanced_accuracy",
    "auroc",
    "brier_score",
    "false_positive_count",
    "false_negative_count",
)

TASK_REASON_CODES = (
    "OK",
    "WITHIN_BOUND",
    "OUTSIDE_BOUND",
    "COHORT_TOO_SMALL",
    "INSUFFICIENT_SUPPORT",
    "MISSING_PREDICTION",
    "MISSING_SCORE",
    "STRUCTURAL_INVALID",
)

_TASK_SCOPES = ("overall", "sex:F", "sex:M", "sex:U")
_SCOPE_ORDER = MappingProxyType(
    {scope: index for index, scope in enumerate(_TASK_SCOPES)}
)
_BOUNDED_METRICS = frozenset(
    {"sensitivity", "specificity", "auroc", "brier_score"}
)
_LOWER_BOUND_METRICS = frozenset({"sensitivity", "specificity", "auroc"})
_RATE_METRICS = frozenset(TASK_METRICS[:6])
_COUNT_METRICS = frozenset(TASK_METRICS[6:])


class TaskUtilityStatus(str, Enum):
    """Closed status for task-utility metrics, cells, and reports."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNEVALUABLE = "UNEVALUABLE"


_STATUS_REASON_CODES = MappingProxyType(
    {
        TaskUtilityStatus.PASS: frozenset({"OK", "WITHIN_BOUND"}),
        TaskUtilityStatus.FAIL: frozenset({"OUTSIDE_BOUND", "STRUCTURAL_INVALID"}),
        TaskUtilityStatus.UNEVALUABLE: frozenset(
            {
                "COHORT_TOO_SMALL",
                "INSUFFICIENT_SUPPORT",
                "MISSING_PREDICTION",
                "MISSING_SCORE",
            }
        ),
    }
)


def _require_integer(value: object, field: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")  # noqa: TRY004
    if value < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    return value


def _require_probability(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite probability")  # noqa: TRY004
    try:
        number = float(value)
    except OverflowError:
        raise ValueError(f"{field} must be a finite probability") from None
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise ValueError(f"{field} must be a finite probability in [0, 1]")
    return number


def _require_status(value: object) -> TaskUtilityStatus:
    if not isinstance(value, TaskUtilityStatus):
        raise TypeError("status must be a TaskUtilityStatus")
    return value


def _require_reason(status: TaskUtilityStatus, value: object) -> str:
    if not isinstance(value, str) or value not in TASK_REASON_CODES:
        raise ValueError("reason_code must be a fixed task reason code")
    if value not in _STATUS_REASON_CODES[status]:
        raise ValueError("reason_code must be compatible with status")
    return value


@dataclass(frozen=True)
class TaskUtilityPolicy:
    """Frozen thresholds declared before task-utility evaluation."""

    policy_id: str
    policy_version: str
    minimum_cohort_size: int
    minimum_evaluable_members: int
    minimum_class_support: int
    maximum_unevaluable_members: int
    require_probability_scores: bool
    minimum_sensitivity: float
    minimum_specificity: float
    minimum_auroc: float
    maximum_brier_score: float
    subgroup_dimensions: tuple[str, ...]

    def __post_init__(self) -> None:
        require_aggregate_safe_token(self.policy_id, "policy_id")
        require_aggregate_safe_token(self.policy_version, "policy_version")
        for field in (
            "minimum_cohort_size",
            "minimum_evaluable_members",
            "minimum_class_support",
        ):
            _require_integer(getattr(self, field), field, minimum=1)
        _require_integer(
            self.maximum_unevaluable_members,
            "maximum_unevaluable_members",
            minimum=0,
        )
        if type(self.require_probability_scores) is not bool:
            raise TypeError("require_probability_scores must be a boolean")
        for field in (
            "minimum_sensitivity",
            "minimum_specificity",
            "minimum_auroc",
            "maximum_brier_score",
        ):
            object.__setattr__(
                self,
                field,
                _require_probability(getattr(self, field), field),
            )
        if not isinstance(self.subgroup_dimensions, tuple):
            raise TypeError("subgroup_dimensions must be an immutable tuple")
        if self.subgroup_dimensions not in ((), ("sex",)):
            raise ValueError(
                "subgroup_dimensions must be empty or the exact ('sex',) tuple"
            )


@dataclass(frozen=True, repr=False)
class TaskPrediction:
    """One process-local ordered task output without a member identifier."""

    predicted_disorder: bool | None
    risk_score: float | None = None

    def __post_init__(self) -> None:
        if self.predicted_disorder is not None and type(self.predicted_disorder) is not bool:
            raise TypeError("predicted_disorder must be a boolean or None")
        if self.risk_score is not None:
            object.__setattr__(
                self,
                "risk_score",
                _require_probability(self.risk_score, "risk_score"),
            )
        if self.predicted_disorder is None and self.risk_score is not None:
            raise ValueError("a missing decision must not carry a risk_score")

    def __repr__(self) -> str:
        return "TaskPrediction(<evaluator-only>)"


def _bound_is_satisfied(name: str, observed: float, target: float) -> bool:
    if name in _LOWER_BOUND_METRICS:
        return observed >= target
    if name == "brier_score":
        return observed <= target
    raise ValueError("metric does not have a policy bound")


@dataclass(frozen=True, repr=False)
class TaskUtilityMetric:
    """One fixed aggregate metric with explicit evidence availability."""

    name: str
    status: TaskUtilityStatus
    reason_code: str
    observed: float | int | None
    target: float | None
    support_count: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or self.name not in TASK_METRICS:
            raise ValueError("name must belong to the fixed task metric registry")
        status = _require_status(self.status)
        reason = _require_reason(status, self.reason_code)
        if status is TaskUtilityStatus.UNEVALUABLE or reason == "STRUCTURAL_INVALID":
            if any(
                value is not None
                for value in (self.observed, self.target, self.support_count)
            ):
                raise ValueError(
                    "unevaluable and structural metrics require null numeric evidence"
                )
            return

        if self.name in _COUNT_METRICS:
            observed: float | int = _require_integer(
                self.observed, "observed", minimum=0
            )
        else:
            observed = _require_probability(self.observed, "observed")
            object.__setattr__(self, "observed", observed)
        support_count = _require_integer(
            self.support_count, "support_count", minimum=1
        )
        object.__setattr__(self, "support_count", support_count)

        if self.name in _BOUNDED_METRICS:
            if self.target is None:
                raise ValueError("target is required for bounded task metrics")
            target = _require_probability(self.target, "target")
            object.__setattr__(self, "target", target)
            within_bound = _bound_is_satisfied(self.name, float(observed), target)
            expected_status = (
                TaskUtilityStatus.PASS if within_bound else TaskUtilityStatus.FAIL
            )
            expected_reason = "WITHIN_BOUND" if within_bound else "OUTSIDE_BOUND"
            if status is not expected_status or reason != expected_reason:
                raise ValueError("status and reason_code must match the metric bound")
        else:
            if self.target is not None:
                raise ValueError("target must be null for diagnostic task metrics")
            if status is not TaskUtilityStatus.PASS or reason != "OK":
                raise ValueError("diagnostic task metrics must PASS with reason OK")

    def to_mapping(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status.value,
            "reason_code": self.reason_code,
            "observed": self.observed,
            "target": self.target,
            "support_count": self.support_count,
        }

    def __repr__(self) -> str:
        return "TaskUtilityMetric(<aggregate-only>)"


def _ordered_metrics(value: object) -> tuple[TaskUtilityMetric, ...]:
    if not isinstance(value, tuple):
        raise TypeError("metrics must be an immutable tuple")
    if not all(type(metric) is TaskUtilityMetric for metric in value):
        raise TypeError("metrics must contain TaskUtilityMetric values")
    names = tuple(metric.name for metric in value)
    if len(names) != len(set(names)) or set(names) != set(TASK_METRICS):
        raise ValueError("metrics must contain each fixed task metric exactly once")
    by_name = {metric.name: metric for metric in value}
    return tuple(by_name[name] for name in TASK_METRICS)


def _validate_metric_against_cell(
    metric: TaskUtilityMetric,
    *,
    evaluable_count: int,
    missing_score_count: int,
    positive_count: int,
    negative_count: int,
    true_positive: int,
    true_negative: int,
    false_positive: int,
    false_negative: int,
) -> None:
    if metric.status is TaskUtilityStatus.UNEVALUABLE or (
        metric.reason_code == "STRUCTURAL_INVALID"
    ):
        return
    expected_observed: float | int | None = None
    expected_support: int | None = None
    if metric.name == "sensitivity" and positive_count:
        expected_observed = true_positive / positive_count
        expected_support = positive_count
    elif metric.name == "specificity" and negative_count:
        expected_observed = true_negative / negative_count
        expected_support = negative_count
    elif metric.name == "precision" and true_positive + false_positive:
        expected_observed = true_positive / (true_positive + false_positive)
        expected_support = true_positive + false_positive
    elif metric.name == "balanced_accuracy" and positive_count and negative_count:
        expected_observed = (
            true_positive / positive_count + true_negative / negative_count
        ) / 2
        expected_support = evaluable_count
    elif metric.name in {"auroc", "brier_score"} and not missing_score_count:
        expected_support = evaluable_count
    elif metric.name == "false_positive_count":
        expected_observed = false_positive
        expected_support = evaluable_count
    elif metric.name == "false_negative_count":
        expected_observed = false_negative
        expected_support = evaluable_count

    if expected_support is None:
        raise ValueError(f"metrics.{metric.name} lacks consistent cell support")
    if metric.support_count != expected_support:
        raise ValueError(f"metrics.{metric.name} support_count must match cell counts")
    if expected_observed is not None and metric.observed != expected_observed:
        raise ValueError(f"metrics.{metric.name} observed must match cell counts")


@dataclass(frozen=True, repr=False)
class TaskUtilityCell:
    """One fixed-scope aggregate task-utility summary."""

    scope: str
    status: TaskUtilityStatus
    reason_code: str
    member_count: int
    evaluable_count: int
    unevaluable_count: int
    missing_score_count: int
    positive_count: int | None
    negative_count: int | None
    true_positive: int | None
    true_negative: int | None
    false_positive: int | None
    false_negative: int | None
    metrics: tuple[TaskUtilityMetric, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.scope, str) or self.scope not in _SCOPE_ORDER:
            raise ValueError("scope must be a fixed task-utility scope")
        require_aggregate_safe_token(self.scope, "scope")
        status = _require_status(self.status)
        reason = _require_reason(status, self.reason_code)
        structural_count_fields = (
            "member_count",
            "evaluable_count",
            "unevaluable_count",
            "missing_score_count",
        )
        structural_counts = {
            field: _require_integer(getattr(self, field), field, minimum=0)
            for field in structural_count_fields
        }
        truth_count_fields = (
            "positive_count",
            "negative_count",
            "true_positive",
            "true_negative",
            "false_positive",
            "false_negative",
        )
        metrics = _ordered_metrics(self.metrics)
        object.__setattr__(self, "metrics", metrics)

        structural = reason == "STRUCTURAL_INVALID"
        if structural:
            if any(structural_counts.values()) or any(
                getattr(self, field) is not None for field in truth_count_fields
            ) or any(
                metric.status is not TaskUtilityStatus.FAIL
                or metric.reason_code != "STRUCTURAL_INVALID"
                or any(
                    value is not None
                    for value in (
                        metric.observed,
                        metric.target,
                        metric.support_count,
                    )
                )
                for metric in metrics
            ):
                raise ValueError(
                    "structural cells require zero structural counts, null truth-dependent counts, and null metric evidence"
                )
            return
        if any(metric.reason_code == "STRUCTURAL_INVALID" for metric in metrics):
            raise ValueError("nonstructural cells must not contain structural metrics")

        if structural_counts["member_count"] != (
            structural_counts["evaluable_count"]
            + structural_counts["unevaluable_count"]
        ):
            raise ValueError("member_count must match evaluable and unevaluable counts")
        if (
            structural_counts["missing_score_count"]
            > structural_counts["evaluable_count"]
        ):
            raise ValueError("missing_score_count cannot exceed evaluable_count")
        failed_metrics = tuple(
            metric for metric in metrics if metric.status is TaskUtilityStatus.FAIL
        )
        unevaluable_metrics = tuple(
            metric
            for metric in metrics
            if metric.status is TaskUtilityStatus.UNEVALUABLE
        )
        if status is TaskUtilityStatus.UNEVALUABLE:
            if any(getattr(self, field) is not None for field in truth_count_fields):
                raise ValueError(
                    "unevaluable cells must suppress truth-dependent counts"
                )
            if failed_metrics:
                raise ValueError("failed metrics must take precedence over unevaluable cell status")
            expected_reason = (
                "MISSING_PREDICTION"
                if structural_counts["unevaluable_count"]
                else "MISSING_SCORE"
                if structural_counts["missing_score_count"]
                else "INSUFFICIENT_SUPPORT"
            )
            if reason != expected_reason:
                raise ValueError(
                    "unevaluable cell reason_code must match missing-evidence precedence"
                )
            if not unevaluable_metrics and reason != "MISSING_PREDICTION":
                raise ValueError("UNEVALUABLE cell status requires unevaluable metrics")
            return

        truth_counts = {
            field: _require_integer(getattr(self, field), field, minimum=0)
            for field in truth_count_fields
        }
        if structural_counts["evaluable_count"] != (
            truth_counts["positive_count"] + truth_counts["negative_count"]
        ):
            raise ValueError("positive and negative counts must match evaluable_count")
        if truth_counts["positive_count"] != (
            truth_counts["true_positive"] + truth_counts["false_negative"]
        ):
            raise ValueError("positive confusion counts must be consistent")
        if truth_counts["negative_count"] != (
            truth_counts["true_negative"] + truth_counts["false_positive"]
        ):
            raise ValueError("negative confusion counts must be consistent")

        for metric in metrics:
            _validate_metric_against_cell(
                metric,
                evaluable_count=structural_counts["evaluable_count"],
                missing_score_count=structural_counts["missing_score_count"],
                **truth_counts,
            )

        if failed_metrics:
            if status is not TaskUtilityStatus.FAIL or reason != "OUTSIDE_BOUND":
                raise ValueError("cell status must match failed metric precedence")
        elif status is TaskUtilityStatus.FAIL:
            raise ValueError("FAIL cell status requires a failed metric")
        elif structural_counts["unevaluable_count"]:
            raise ValueError("missing predictions require UNEVALUABLE cell status")
        elif reason != "WITHIN_BOUND":
            raise ValueError("PASS cell reason_code must be WITHIN_BOUND")
        elif unevaluable_metrics and any(
            metric.name not in {"auroc", "brier_score"}
            or metric.reason_code != "MISSING_SCORE"
            for metric in unevaluable_metrics
        ):
            raise ValueError(
                "PASS cells may omit only optional score metric evidence"
            )

    def to_mapping(self) -> dict[str, object]:
        return {
            "scope": self.scope,
            "status": self.status.value,
            "reason_code": self.reason_code,
            "member_count": self.member_count,
            "evaluable_count": self.evaluable_count,
            "unevaluable_count": self.unevaluable_count,
            "missing_score_count": self.missing_score_count,
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "true_positive": self.true_positive,
            "true_negative": self.true_negative,
            "false_positive": self.false_positive,
            "false_negative": self.false_negative,
            "metrics": [metric.to_mapping() for metric in self.metrics],
        }

    def __repr__(self) -> str:
        return "TaskUtilityCell(<aggregate-only>)"


def _freeze_counts(
    value: object, keys: tuple[str, ...], field: str
) -> Mapping[str, int]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field} must be a mapping")
    if not all(isinstance(key, str) for key in value) or set(value) != set(keys):
        raise ValueError(f"{field} must use the fixed status registry")
    return MappingProxyType(
        {
            key: _require_integer(value[key], f"{field}.{key}", minimum=0)
            for key in keys
        }
    )


@dataclass(frozen=True, repr=False)
class TaskUtilityReport:
    """Immutable deterministic aggregate-only task-utility report."""

    report_version: str
    policy_id: str
    policy_version: str
    cohort_profile: str
    cohort_seed: int
    cohort_size: int
    status: TaskUtilityStatus
    reason_code: str
    status_counts: Mapping[str, int]
    metric_counts: Mapping[str, int]
    evaluable_count: int
    unevaluable_count: int
    cells: tuple[TaskUtilityCell, ...]

    def __post_init__(self) -> None:
        if self.report_version != TASK_UTILITY_REPORT_VERSION:
            raise ValueError(
                f"report_version must be {TASK_UTILITY_REPORT_VERSION}"
            )
        require_aggregate_safe_token(self.policy_id, "policy_id")
        require_aggregate_safe_token(self.policy_version, "policy_version")
        require_aggregate_safe_token(self.cohort_profile, "cohort_profile")
        _require_integer(self.cohort_seed, "cohort_seed", minimum=0)
        cohort_size = _require_integer(self.cohort_size, "cohort_size", minimum=0)
        evaluable_count = _require_integer(
            self.evaluable_count, "evaluable_count", minimum=0
        )
        unevaluable_count = _require_integer(
            self.unevaluable_count, "unevaluable_count", minimum=0
        )
        if evaluable_count + unevaluable_count != cohort_size:
            raise ValueError(
                "evaluable_count and unevaluable_count must match cohort_size"
            )
        status = _require_status(self.status)
        reason = _require_reason(status, self.reason_code)
        status_keys = tuple(item.value for item in TaskUtilityStatus)
        status_counts = _freeze_counts(
            self.status_counts, status_keys, "status_counts"
        )
        metric_counts = _freeze_counts(
            self.metric_counts, TASK_METRICS, "metric_counts"
        )

        if not isinstance(self.cells, tuple):
            raise TypeError("cells must be an immutable tuple")
        if not self.cells or not all(type(cell) is TaskUtilityCell for cell in self.cells):
            raise TypeError("cells must be a nonempty tuple of TaskUtilityCell values")
        scopes = tuple(cell.scope for cell in self.cells)
        if len(set(scopes)) != len(scopes):
            raise ValueError("cells must have unique fixed scopes")
        if "overall" not in scopes:
            raise ValueError("cells must contain the overall scope")
        cells = tuple(sorted(self.cells, key=lambda cell: _SCOPE_ORDER[cell.scope]))

        counted_cells = Counter(cell.status.value for cell in cells)
        expected_status_counts = {key: counted_cells[key] for key in status_keys}
        if dict(status_counts) != expected_status_counts:
            raise ValueError("status_counts must match cell statuses")
        expected_metric_counts = {
            metric: sum(
                any(item.name == metric for item in cell.metrics) for cell in cells
            )
            for metric in TASK_METRICS
        }
        if dict(metric_counts) != expected_metric_counts:
            raise ValueError("metric_counts must match metrics carried by cells")

        overall = cells[0]
        if (
            overall.member_count != cohort_size
            or overall.evaluable_count != evaluable_count
            or overall.unevaluable_count != unevaluable_count
        ):
            raise ValueError("overall cell counts must match report counts")
        failed_cells = tuple(
            cell for cell in cells if cell.status is TaskUtilityStatus.FAIL
        )
        unevaluable_cells = tuple(
            cell for cell in cells if cell.status is TaskUtilityStatus.UNEVALUABLE
        )
        if failed_cells:
            expected_reason = (
                "STRUCTURAL_INVALID"
                if any(cell.reason_code == "STRUCTURAL_INVALID" for cell in failed_cells)
                else "OUTSIDE_BOUND"
            )
            if status is not TaskUtilityStatus.FAIL or reason != expected_reason:
                raise ValueError("report status and reason_code must match failed cells")
        elif status is TaskUtilityStatus.FAIL:
            raise ValueError("FAIL report status requires a failed cell")
        elif status is TaskUtilityStatus.PASS:
            if reason not in {"OK", "WITHIN_BOUND"}:
                raise ValueError("PASS report reason_code must be nonblocking")
            if any(
                cell.reason_code != "MISSING_PREDICTION"
                for cell in unevaluable_cells
            ):
                raise ValueError(
                    "PASS report may contain only allowed missing-output cells"
                )
        elif not unevaluable_cells and reason not in {
            "COHORT_TOO_SMALL",
            "MISSING_PREDICTION",
        }:
            raise ValueError(
                "UNEVALUABLE report requires a blocking cell or aggregate floor"
            )

        object.__setattr__(self, "status_counts", status_counts)
        object.__setattr__(self, "metric_counts", metric_counts)
        object.__setattr__(self, "cells", cells)

    def to_mapping(self) -> dict[str, object]:
        return {
            "report_version": self.report_version,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "cohort_profile": self.cohort_profile,
            "cohort_seed": self.cohort_seed,
            "cohort_size": self.cohort_size,
            "status": self.status.value,
            "reason_code": self.reason_code,
            "status_counts": dict(self.status_counts),
            "metric_counts": dict(self.metric_counts),
            "evaluable_count": self.evaluable_count,
            "unevaluable_count": self.unevaluable_count,
            "cells": [cell.to_mapping() for cell in self.cells],
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.to_mapping(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )

    def to_json_bytes(self) -> bytes:
        return (self.canonical_json() + "\n").encode("ascii")

    def __repr__(self) -> str:
        return "TaskUtilityReport(<aggregate-only>)"


def _structural_fallback_report() -> TaskUtilityReport:
    metrics = tuple(
        TaskUtilityMetric(
            name=name,
            status=TaskUtilityStatus.FAIL,
            reason_code="STRUCTURAL_INVALID",
            observed=None,
            target=None,
            support_count=None,
        )
        for name in TASK_METRICS
    )
    cell = TaskUtilityCell(
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
        metrics=metrics,
    )
    return TaskUtilityReport(
        report_version=TASK_UTILITY_REPORT_VERSION,
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
        cells=(cell,),
    )


__all__ = [
    "TASK_METRICS",
    "TASK_REASON_CODES",
    "TASK_UTILITY_REPORT_VERSION",
    "TaskPrediction",
    "TaskUtilityCell",
    "TaskUtilityMetric",
    "TaskUtilityPolicy",
    "TaskUtilityReport",
    "TaskUtilityStatus",
]
