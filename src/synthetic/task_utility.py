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
from synthetic.cohort import CalibrationSamplingProfile, CohortMember, NativeCohort
from synthetic.models import (
    AgeRegimeDisorderTrajectory,
    AgeRegimePoint,
    AgeRegimeState,
    AgeRegimeTrajectory,
    ClinicalEvent,
    DisorderKind,
    LatentDisorderState,
)
from synthetic.native.observations import (
    EventRecordingDecision,
    MeasurementObservation,
    MeasurementTruth,
    ObservationFrame,
    ObservationPolicy,
    ObservationTruth,
    ObservationWindow,
    ObservedVisit,
    RecordedEvent,
    VisitOpportunity,
)
from synthetic.native.resources import (
    BASE_RESOURCE_NAMES,
    ClinicalDescendant,
    ObservedResourceBundle,
    ResourceRow,
    ResourceShape,
    ResourceSpec,
    SyntheticDemographics,
)

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
        if status is TaskUtilityStatus.UNEVALUABLE:
            if reason == "COHORT_TOO_SMALL":
                raise ValueError("COHORT_TOO_SMALL is a report-level reason_code")
            if reason == "MISSING_SCORE" and self.name not in {
                "auroc",
                "brier_score",
            }:
                raise ValueError(
                    "MISSING_SCORE reason_code applies only to score metrics"
                )
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
            metric_reasons = {
                metric.reason_code for metric in unevaluable_metrics
            }
            expected_reason = (
                "MISSING_PREDICTION"
                if structural_counts["unevaluable_count"]
                else "MISSING_SCORE"
                if (
                    structural_counts["missing_score_count"]
                    and "MISSING_SCORE" in metric_reasons
                )
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
                cell.scope != "overall"
                or cell.reason_code != "MISSING_PREDICTION"
                for cell in unevaluable_cells
            ):
                raise ValueError(
                    "PASS report may contain only allowed missing-output cells"
                )
        elif reason != "COHORT_TOO_SMALL":
            cell_reasons = frozenset(
                cell.reason_code for cell in unevaluable_cells
            )
            metric_reasons = frozenset(
                metric.reason_code
                for cell in unevaluable_cells
                for metric in cell.metrics
                if metric.status is TaskUtilityStatus.UNEVALUABLE
            )
            if any(
                cell.scope != "overall"
                and cell.reason_code == "MISSING_PREDICTION"
                for cell in unevaluable_cells
            ):
                evidenced_reason = "MISSING_PREDICTION"
            elif "MISSING_SCORE" in metric_reasons:
                evidenced_reason = "MISSING_SCORE"
            elif "INSUFFICIENT_SUPPORT" in metric_reasons:
                evidenced_reason = "INSUFFICIENT_SUPPORT"
            elif "MISSING_SCORE" in cell_reasons:
                evidenced_reason = "MISSING_SCORE"
            elif "INSUFFICIENT_SUPPORT" in cell_reasons:
                evidenced_reason = "INSUFFICIENT_SUPPORT"
            elif (
                "MISSING_PREDICTION" in cell_reasons
                or "MISSING_PREDICTION" in metric_reasons
            ):
                evidenced_reason = "MISSING_PREDICTION"
            else:
                evidenced_reason = None
            if (
                reason != evidenced_reason
                or (
                    reason == "MISSING_PREDICTION"
                    and not unevaluable_count
                )
            ):
                raise ValueError(
                    "UNEVALUABLE report reason_code must match blocking evidence"
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


def _unevaluable_metric(name: str, reason_code: str) -> TaskUtilityMetric:
    return TaskUtilityMetric(
        name=name,
        status=TaskUtilityStatus.UNEVALUABLE,
        reason_code=reason_code,
        observed=None,
        target=None,
        support_count=None,
    )


def _evaluated_metric(
    name: str,
    observed: float,
    target: float | None,
    support_count: int,
) -> TaskUtilityMetric:
    if target is None:
        status = TaskUtilityStatus.PASS
        reason_code = "OK"
    else:
        within_bound = _bound_is_satisfied(name, float(observed), target)
        status = TaskUtilityStatus.PASS if within_bound else TaskUtilityStatus.FAIL
        reason_code = "WITHIN_BOUND" if within_bound else "OUTSIDE_BOUND"
    return TaskUtilityMetric(
        name=name,
        status=status,
        reason_code=reason_code,
        observed=observed,
        target=target,
        support_count=support_count,
    )


def _score_metrics(
    score_groups: Mapping[float, tuple[int, int]],
    *,
    brier_total: float,
    scored_count: int,
    evaluable_count: int,
    positive_count: int,
    negative_count: int,
    missing_score_count: int,
    policy: TaskUtilityPolicy,
) -> tuple[TaskUtilityMetric, TaskUtilityMetric]:
    if missing_score_count:
        return (
            _unevaluable_metric("auroc", "MISSING_SCORE"),
            _unevaluable_metric("brier_score", "MISSING_SCORE"),
        )
    if not positive_count or not negative_count:
        return (
            _unevaluable_metric("auroc", "INSUFFICIENT_SUPPORT"),
            _unevaluable_metric("brier_score", "INSUFFICIENT_SUPPORT"),
        )

    positive_rank_sum = 0.0
    lower_rank = 1
    for score in sorted(score_groups):
        group_positive, group_negative = score_groups[score]
        group_count = group_positive + group_negative
        upper_rank = lower_rank + group_count - 1
        midrank = (lower_rank + upper_rank) / 2
        positive_rank_sum += midrank * group_positive
        lower_rank = upper_rank + 1
    auroc = (
        positive_rank_sum - positive_count * (positive_count + 1) / 2
    ) / (positive_count * negative_count)
    if scored_count != evaluable_count:
        raise ValueError("score aggregates must match evaluable count")
    brier_score = brier_total / scored_count
    return (
        _evaluated_metric(
            "auroc",
            auroc,
            policy.minimum_auroc,
            evaluable_count,
        ),
        _evaluated_metric(
            "brier_score",
            brier_score,
            policy.maximum_brier_score,
            evaluable_count,
        ),
    )


def _task_cell(
    scope: str,
    members: tuple[CohortMember, ...],
    predictions: tuple[TaskPrediction, ...],
    policy: TaskUtilityPolicy,
) -> TaskUtilityCell:
    evaluable_count = 0
    missing_score_count = 0
    positive_count = 0
    negative_count = 0
    true_positive = 0
    true_negative = 0
    false_positive = 0
    false_negative = 0
    score_groups: dict[float, tuple[int, int]] = {}
    brier_total = 0.0
    scored_count = 0

    for member, prediction in zip(members, predictions, strict=True):
        if type(member) is not CohortMember:
            raise TypeError("cohort contains malformed typed evidence")
        trajectory = member.trajectory
        if type(trajectory) is not AgeRegimeDisorderTrajectory:
            raise TypeError("cohort contains malformed typed evidence")
        disorder = trajectory.disorder
        if (
            type(disorder) is not LatentDisorderState
            or type(disorder.kind) is not DisorderKind
        ):
            raise TypeError("cohort contains malformed typed evidence")
        truth = disorder.kind is not DisorderKind.HEALTHY
        decision = prediction.predicted_disorder
        if decision is None:
            continue
        evaluable_count += 1
        if truth:
            positive_count += 1
            if decision:
                true_positive += 1
            else:
                false_negative += 1
        else:
            negative_count += 1
            if decision:
                false_positive += 1
            else:
                true_negative += 1
        if prediction.risk_score is None:
            missing_score_count += 1
        else:
            score = prediction.risk_score
            group_positive, group_negative = score_groups.get(score, (0, 0))
            score_groups[score] = (
                group_positive + int(truth),
                group_negative + int(not truth),
            )
            brier_total += (score - int(truth)) ** 2
            scored_count += 1

    unevaluable_count = len(members) - evaluable_count
    minimum_support = policy.minimum_class_support
    if positive_count < minimum_support or negative_count < minimum_support:
        if unevaluable_count:
            reason_code = "MISSING_PREDICTION"
        elif policy.require_probability_scores and missing_score_count:
            reason_code = "MISSING_SCORE"
        else:
            reason_code = "INSUFFICIENT_SUPPORT"

        def metric_reason(name: str) -> str:
            if reason_code == "MISSING_SCORE":
                return (
                    "MISSING_SCORE"
                    if name in {"auroc", "brier_score"}
                    else "INSUFFICIENT_SUPPORT"
                )
            return reason_code

        return TaskUtilityCell(
            scope=scope,
            status=TaskUtilityStatus.UNEVALUABLE,
            reason_code=reason_code,
            member_count=len(members),
            evaluable_count=evaluable_count,
            unevaluable_count=unevaluable_count,
            missing_score_count=missing_score_count,
            positive_count=None,
            negative_count=None,
            true_positive=None,
            true_negative=None,
            false_positive=None,
            false_negative=None,
            metrics=tuple(
                _unevaluable_metric(name, metric_reason(name))
                for name in TASK_METRICS
            ),
        )

    if positive_count >= minimum_support:
        sensitivity = _evaluated_metric(
            "sensitivity",
            true_positive / positive_count,
            policy.minimum_sensitivity,
            positive_count,
        )
    else:
        sensitivity = _unevaluable_metric(
            "sensitivity", "INSUFFICIENT_SUPPORT"
        )
    if negative_count >= minimum_support:
        specificity = _evaluated_metric(
            "specificity",
            true_negative / negative_count,
            policy.minimum_specificity,
            negative_count,
        )
    else:
        specificity = _unevaluable_metric(
            "specificity", "INSUFFICIENT_SUPPORT"
        )
    predicted_positive_count = true_positive + false_positive
    if predicted_positive_count:
        precision = _evaluated_metric(
            "precision",
            true_positive / predicted_positive_count,
            None,
            predicted_positive_count,
        )
    else:
        precision = _unevaluable_metric("precision", "INSUFFICIENT_SUPPORT")
    if positive_count >= minimum_support and negative_count >= minimum_support:
        balanced_accuracy = _evaluated_metric(
            "balanced_accuracy",
            (
                true_positive / positive_count
                + true_negative / negative_count
            )
            / 2,
            None,
            evaluable_count,
        )
    else:
        balanced_accuracy = _unevaluable_metric(
            "balanced_accuracy", "INSUFFICIENT_SUPPORT"
        )
    auroc, brier_score = _score_metrics(
        score_groups,
        brier_total=brier_total,
        scored_count=scored_count,
        evaluable_count=evaluable_count,
        positive_count=positive_count,
        negative_count=negative_count,
        missing_score_count=missing_score_count,
        policy=policy,
    )
    if evaluable_count:
        false_positive_metric = _evaluated_metric(
            "false_positive_count", false_positive, None, evaluable_count
        )
        false_negative_metric = _evaluated_metric(
            "false_negative_count", false_negative, None, evaluable_count
        )
    else:
        false_positive_metric = _unevaluable_metric(
            "false_positive_count", "INSUFFICIENT_SUPPORT"
        )
        false_negative_metric = _unevaluable_metric(
            "false_negative_count", "INSUFFICIENT_SUPPORT"
        )
    metrics = (
        sensitivity,
        specificity,
        precision,
        balanced_accuracy,
        auroc,
        brier_score,
        false_positive_metric,
        false_negative_metric,
    )

    failed_metrics = tuple(
        metric for metric in metrics if metric.status is TaskUtilityStatus.FAIL
    )
    blocking_unevaluable_metrics = tuple(
        metric
        for metric in metrics
        if metric.status is TaskUtilityStatus.UNEVALUABLE
        and not (
            not policy.require_probability_scores
            and metric.name in {"auroc", "brier_score"}
            and metric.reason_code == "MISSING_SCORE"
        )
    )
    if failed_metrics:
        status = TaskUtilityStatus.FAIL
        reason_code = "OUTSIDE_BOUND"
    elif unevaluable_count:
        status = TaskUtilityStatus.UNEVALUABLE
        reason_code = "MISSING_PREDICTION"
    elif policy.require_probability_scores and missing_score_count:
        status = TaskUtilityStatus.UNEVALUABLE
        reason_code = "MISSING_SCORE"
    elif blocking_unevaluable_metrics:
        status = TaskUtilityStatus.UNEVALUABLE
        reason_code = (
            "MISSING_SCORE"
            if any(
                metric.reason_code == "MISSING_SCORE"
                for metric in blocking_unevaluable_metrics
            )
            else "INSUFFICIENT_SUPPORT"
        )
    else:
        status = TaskUtilityStatus.PASS
        reason_code = "WITHIN_BOUND"

    suppress_truth_counts = status is TaskUtilityStatus.UNEVALUABLE
    return TaskUtilityCell(
        scope=scope,
        status=status,
        reason_code=reason_code,
        member_count=len(members),
        evaluable_count=evaluable_count,
        unevaluable_count=unevaluable_count,
        missing_score_count=missing_score_count,
        positive_count=None if suppress_truth_counts else positive_count,
        negative_count=None if suppress_truth_counts else negative_count,
        true_positive=None if suppress_truth_counts else true_positive,
        true_negative=None if suppress_truth_counts else true_negative,
        false_positive=None if suppress_truth_counts else false_positive,
        false_negative=None if suppress_truth_counts else false_negative,
        metrics=metrics,
    )


def _validated_disorder(value: object) -> LatentDisorderState:
    if type(value) is not LatentDisorderState:
        raise TypeError("cohort contains malformed typed evidence")
    return LatentDisorderState(
        kind=value.kind,
        onset_age_days=value.onset_age_days,
        severity=value.severity,
        puberty_delay_days=value.puberty_delay_days,
        treatment_start_age_days=value.treatment_start_age_days,
        treatment_response=value.treatment_response,
    )


def _validated_age_state(value: object) -> AgeRegimeState:
    if type(value) is not AgeRegimeState:
        raise TypeError("cohort contains malformed typed evidence")
    return AgeRegimeState(
        module_version=value.module_version,
        birth_length_z=value.birth_length_z,
        birth_weight_z=value.birth_weight_z,
        head_circumference_z=value.head_circumference_z,
        childhood_height_z=value.childhood_height_z,
        childhood_bmi_z=value.childhood_bmi_z,
        puberty_onset_age_days=value.puberty_onset_age_days,
        puberty_tempo_days=value.puberty_tempo_days,
        puberty_height_spurt_z=value.puberty_height_spurt_z,
        puberty_bmi_shift_z=value.puberty_bmi_shift_z,
    )


def _validated_age_point(value: object) -> AgeRegimePoint:
    if type(value) is not AgeRegimePoint:
        raise TypeError("cohort contains malformed typed evidence")
    return AgeRegimePoint(
        patient_id=value.patient_id,
        age_days=value.age_days,
        regime=value.regime,
        length_cm=value.length_cm,
        height_cm=value.height_cm,
        weight_kg=value.weight_kg,
        bmi=value.bmi,
        head_circumference_cm=value.head_circumference_cm,
        length_z=value.length_z,
        height_z=value.height_z,
        weight_z=value.weight_z,
        bmi_z=value.bmi_z,
        height_velocity_cm_per_year=value.height_velocity_cm_per_year,
        weight_velocity_kg_per_year=value.weight_velocity_kg_per_year,
    )


def _validated_event(value: object) -> ClinicalEvent:
    if type(value) is not ClinicalEvent:
        raise TypeError("cohort contains malformed typed evidence")
    if (
        not isinstance(value.patient_id, str)
        or not value.patient_id
        or isinstance(value.age_days, bool)
        or not isinstance(value.age_days, int)
        or value.age_days < 0
        or not isinstance(value.event_type, str)
        or not value.event_type
        or (value.code is not None and not isinstance(value.code, str))
        or type(value.hidden) is not bool
    ):
        raise ValueError("cohort contains malformed typed evidence")
    return ClinicalEvent(
        patient_id=value.patient_id,
        age_days=value.age_days,
        event_type=value.event_type,
        code=value.code,
        hidden=value.hidden,
    )


def _validated_trajectory(value: object) -> AgeRegimeDisorderTrajectory:
    if type(value) is not AgeRegimeDisorderTrajectory:
        raise TypeError("cohort contains malformed typed evidence")
    physiology = value.physiology
    if type(physiology) is not AgeRegimeTrajectory or type(physiology.points) is not tuple:
        raise TypeError("cohort contains malformed typed evidence")
    validated_physiology = AgeRegimeTrajectory(
        tuple(_validated_age_point(point) for point in physiology.points),
        _validated_age_state(physiology.state),
    )
    if type(value.events) is not tuple:
        raise TypeError("cohort contains malformed typed evidence")
    return AgeRegimeDisorderTrajectory(
        validated_physiology,
        _validated_disorder(value.disorder),
        tuple(_validated_event(event) for event in value.events),
    )


def _validated_observation_window(value: object) -> ObservationWindow:
    if type(value) is not ObservationWindow:
        raise TypeError("cohort contains malformed typed evidence")
    return ObservationWindow(
        start_age_days=value.start_age_days,
        effective_end_age_days=value.effective_end_age_days,
        administrative_end_age_days=value.administrative_end_age_days,
        censoring_mode=value.censoring_mode,
    )


def _validated_measurement(value: object) -> MeasurementObservation:
    if type(value) is not MeasurementObservation:
        raise TypeError("cohort contains malformed typed evidence")
    return MeasurementObservation(
        channel=value.channel,
        availability=value.availability,
        recorded_value=value.recorded_value,
    )


def _validated_visit(value: object) -> ObservedVisit:
    if type(value) is not ObservedVisit or type(value.measurements) is not tuple:
        raise TypeError("cohort contains malformed typed evidence")
    return ObservedVisit(
        patient_id=value.patient_id,
        visit_id=value.visit_id,
        age_days=value.age_days,
        encounter_type=value.encounter_type,
        measurements=tuple(
            _validated_measurement(measurement)
            for measurement in value.measurements
        ),
    )


def _validated_recorded_event(value: object) -> RecordedEvent:
    if type(value) is not RecordedEvent:
        raise TypeError("cohort contains malformed typed evidence")
    return RecordedEvent(
        patient_id=value.patient_id,
        age_days=value.age_days,
        event_kind=value.event_kind,
        code=value.code,
        opportunity_index=value.opportunity_index,
    )


def _validated_opportunity(value: object) -> VisitOpportunity:
    if type(value) is not VisitOpportunity:
        raise TypeError("cohort contains malformed typed evidence")
    return VisitOpportunity(
        source_point_index=value.source_point_index,
        age_days=value.age_days,
        encounter_type=value.encounter_type,
        realized=value.realized,
    )


def _validated_measurement_truth(value: object) -> MeasurementTruth:
    if type(value) is not MeasurementTruth:
        raise TypeError("cohort contains malformed typed evidence")
    return MeasurementTruth(
        source_point_index=value.source_point_index,
        channel=value.channel,
        availability=value.availability,
        latent_value=value.latent_value,
        error_delta=value.error_delta,
    )


def _validated_event_decision(value: object) -> EventRecordingDecision:
    if type(value) is not EventRecordingDecision:
        raise TypeError("cohort contains malformed typed evidence")
    return EventRecordingDecision(
        source_event_index=value.source_event_index,
        recorded=value.recorded,
        opportunity_index=value.opportunity_index,
    )


def _validated_observation_policy(value: object) -> ObservationPolicy:
    if type(value) is not ObservationPolicy:
        raise TypeError("cohort contains malformed typed evidence")
    return ObservationPolicy(
        policy_version=value.policy_version,
        window_start_age_days=value.window_start_age_days,
        window_end_age_days=value.window_end_age_days,
        censoring_mode=value.censoring_mode,
        censor_age_days=value.censor_age_days,
        visit_probability=value.visit_probability,
        length_availability_probability=value.length_availability_probability,
        height_availability_probability=value.height_availability_probability,
        weight_availability_probability=value.weight_availability_probability,
        head_circumference_availability_probability=(
            value.head_circumference_availability_probability
        ),
        length_error_sd_cm=value.length_error_sd_cm,
        height_error_sd_cm=value.height_error_sd_cm,
        weight_error_sd_kg=value.weight_error_sd_kg,
        head_circumference_error_sd_cm=value.head_circumference_error_sd_cm,
        rounding_digits=value.rounding_digits,
        recognition_probability=value.recognition_probability,
        diagnosis_probability=value.diagnosis_probability,
        recognition_delay_days=value.recognition_delay_days,
    )


def _validated_observation_truth(value: object) -> ObservationTruth:
    if type(value) is not ObservationTruth:
        raise TypeError("cohort contains malformed typed evidence")
    for nested_tuple in (
        value.opportunities,
        value.measurement_truth,
        value.event_decisions,
        value.source_events,
    ):
        if type(nested_tuple) is not tuple:
            raise TypeError("cohort contains malformed typed evidence")
    return ObservationTruth(
        patient_id=value.patient_id,
        window=_validated_observation_window(value.window),
        opportunities=tuple(
            _validated_opportunity(item) for item in value.opportunities
        ),
        measurement_truth=tuple(
            _validated_measurement_truth(item) for item in value.measurement_truth
        ),
        event_decisions=tuple(
            _validated_event_decision(item) for item in value.event_decisions
        ),
        source_events=tuple(
            _validated_event(item) for item in value.source_events
        ),
        latent_trajectory_hash=value.latent_trajectory_hash,
        truth_hash=value.truth_hash,
        policy=(
            None
            if value.policy is None
            else _validated_observation_policy(value.policy)
        ),
        latent_trajectory=(
            None
            if value.latent_trajectory is None
            else _validated_trajectory(value.latent_trajectory)
        ),
    )


def _validated_observation_frame(value: object) -> ObservationFrame:
    if (
        type(value) is not ObservationFrame
        or type(value.visits) is not tuple
        or type(value.events) is not tuple
    ):
        raise TypeError("cohort contains malformed typed evidence")
    return ObservationFrame(
        patient_id=value.patient_id,
        policy_version=value.policy_version,
        window=_validated_observation_window(value.window),
        visits=tuple(_validated_visit(visit) for visit in value.visits),
        events=tuple(
            _validated_recorded_event(event) for event in value.events
        ),
        truth=_validated_observation_truth(value.truth),
    )


def _validated_resource_spec(value: object) -> ResourceSpec:
    if type(value) is not ResourceSpec or type(value.field_names) is not tuple:
        raise TypeError("cohort contains malformed typed evidence")
    return ResourceSpec(name=value.name, field_names=value.field_names)


def _validated_resource_shape(value: object) -> ResourceShape:
    if type(value) is not ResourceShape or type(value.resources) is not tuple:
        raise TypeError("cohort contains malformed typed evidence")
    return ResourceShape(
        tuple(_validated_resource_spec(item) for item in value.resources)
    )


def _validated_resource_row(value: object) -> ResourceRow:
    if (
        type(value) is not ResourceRow
        or type(value.values) is not tuple
        or any(type(pair) is not tuple for pair in value.values)
    ):
        raise TypeError("cohort contains malformed typed evidence")
    return ResourceRow(resource_name=value.resource_name, values=value.values)


def _validated_clinical_descendant(value: object) -> ClinicalDescendant:
    if type(value) is not ClinicalDescendant:
        raise TypeError("cohort contains malformed typed evidence")
    return ClinicalDescendant(
        patient_id=value.patient_id,
        visit_id=value.visit_id,
        age_days=value.age_days,
        event_kind=value.event_kind,
        code=value.code,
    )


def _validated_resource_bundle(value: object) -> ObservedResourceBundle:
    if (
        type(value) is not ObservedResourceBundle
        or type(value.rows) is not MappingProxyType
        or set(value.rows) != set(BASE_RESOURCE_NAMES)
        or type(value.clinical_descendants) is not tuple
    ):
        raise TypeError("cohort contains malformed typed evidence")
    validated_rows = {
        resource_name: tuple(
            _validated_resource_row(row) for row in value.rows[resource_name]
        )
        for resource_name in BASE_RESOURCE_NAMES
        if type(value.rows[resource_name]) is tuple
    }
    if len(validated_rows) != len(BASE_RESOURCE_NAMES):
        raise TypeError("cohort contains malformed typed evidence")
    validated_bundle = ObservedResourceBundle(
        patient_id=value.patient_id,
        shape=_validated_resource_shape(value.shape),
        rows=validated_rows,
        clinical_descendants=tuple(
            _validated_clinical_descendant(item)
            for item in value.clinical_descendants
        ),
        source_frame=_validated_observation_frame(value.source_frame),
    )
    for rows in validated_bundle.rows.values():
        for row in rows:
            row_values = dict(row.values)
            if (
                "patient_id" in row_values
                and row_values["patient_id"] != validated_bundle.patient_id
            ):
                raise ValueError("cohort contains malformed typed evidence")
    return validated_bundle


def _validated_member(value: object) -> CohortMember:
    if type(value) is not CohortMember:
        raise TypeError("cohort contains malformed typed evidence")
    validated_trajectory = _validated_trajectory(value.trajectory)
    if type(value.demographics) is not SyntheticDemographics:
        raise TypeError("cohort contains malformed typed evidence")
    validated_demographics = SyntheticDemographics(
        patient_id=value.demographics.patient_id,
        sex=value.demographics.sex,
        ethnicity=value.demographics.ethnicity,
        races=value.demographics.races,
    )
    validated_frame = _validated_observation_frame(value.frame)
    validated_bundle = (
        None
        if value.bundle is None
        else _validated_resource_bundle(value.bundle)
    )
    if (
        validated_frame.truth.latent_trajectory is not None
        and validated_frame.truth.latent_trajectory != validated_trajectory
    ):
        raise ValueError("cohort contains malformed typed evidence")
    if (
        validated_bundle is not None
        and validated_bundle.source_frame != validated_frame
    ):
        raise ValueError("cohort contains malformed typed evidence")
    return CohortMember(
        demographics=validated_demographics,
        trajectory=validated_trajectory,
        frame=validated_frame,
        bundle=validated_bundle,
    )


def _validated_calibration(value: object) -> CalibrationSamplingProfile:
    if type(value) is not CalibrationSamplingProfile:
        raise TypeError("cohort contains malformed typed evidence")
    return CalibrationSamplingProfile(
        artifact_id=value.artifact_id,
        target_registry_version=value.target_registry_version,
        sex_weights=value.sex_weights,
        ethnicity_weights=value.ethnicity_weights,
        race_weights=value.race_weights,
        race_multiselect_probability=value.race_multiselect_probability,
        recorded_healthy_probability=value.recorded_healthy_probability,
        recorded_growth_dx_probability=value.recorded_growth_dx_probability,
    )


def _validated_cohort(
    value: object,
    members: tuple[CohortMember, ...],
) -> NativeCohort:
    if type(value) is not NativeCohort:
        raise TypeError("cohort contains malformed typed evidence")
    return NativeCohort(
        profile=value.profile,
        seed=value.seed,
        members=tuple(_validated_member(member) for member in members),
        calibration=_validated_calibration(value.calibration),
    )


def _redacted_unevaluable_cell(
    cell: TaskUtilityCell,
    *,
    report_reason: str,
) -> TaskUtilityCell:
    if cell.status is TaskUtilityStatus.UNEVALUABLE:
        cell_reason = cell.reason_code
    elif cell.missing_score_count:
        cell_reason = "MISSING_SCORE"
    else:
        cell_reason = "INSUFFICIENT_SUPPORT"

    def metric_reason(name: str) -> str:
        if report_reason == "MISSING_PREDICTION":
            return "MISSING_PREDICTION"
        if report_reason == "MISSING_SCORE":
            return (
                "MISSING_SCORE"
                if name in {"auroc", "brier_score"}
                else "INSUFFICIENT_SUPPORT"
            )
        if report_reason == "INSUFFICIENT_SUPPORT":
            return "INSUFFICIENT_SUPPORT"
        if cell_reason == "MISSING_PREDICTION":
            return "MISSING_PREDICTION"
        if cell_reason == "MISSING_SCORE" and name in {"auroc", "brier_score"}:
            return "MISSING_SCORE"
        return "INSUFFICIENT_SUPPORT"

    return TaskUtilityCell(
        scope=cell.scope,
        status=TaskUtilityStatus.UNEVALUABLE,
        reason_code=cell_reason,
        member_count=cell.member_count,
        evaluable_count=cell.evaluable_count,
        unevaluable_count=cell.unevaluable_count,
        missing_score_count=cell.missing_score_count,
        positive_count=None,
        negative_count=None,
        true_positive=None,
        true_negative=None,
        false_positive=None,
        false_negative=None,
        metrics=tuple(
            _unevaluable_metric(name, metric_reason(name)) for name in TASK_METRICS
        ),
    )


def _validated_policy(policy: TaskUtilityPolicy) -> TaskUtilityPolicy:
    return TaskUtilityPolicy(
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        minimum_cohort_size=policy.minimum_cohort_size,
        minimum_evaluable_members=policy.minimum_evaluable_members,
        minimum_class_support=policy.minimum_class_support,
        maximum_unevaluable_members=policy.maximum_unevaluable_members,
        require_probability_scores=policy.require_probability_scores,
        minimum_sensitivity=policy.minimum_sensitivity,
        minimum_specificity=policy.minimum_specificity,
        minimum_auroc=policy.minimum_auroc,
        maximum_brier_score=policy.maximum_brier_score,
        subgroup_dimensions=policy.subgroup_dimensions,
    )


def evaluate_task_utility(
    cohort: NativeCohort,
    predictions: tuple[TaskPrediction, ...],
    policy: TaskUtilityPolicy,
) -> TaskUtilityReport:
    """Evaluate ordered fictional predictions against private aggregate truth."""

    try:
        if (
            type(cohort) is not NativeCohort
            or type(policy) is not TaskUtilityPolicy
            or type(predictions) is not tuple
        ):
            return _structural_fallback_report()
        members = cohort.members
        if (
            type(members) is not tuple
            or len(predictions) != len(members)
            or not all(type(item) is TaskPrediction for item in predictions)
        ):
            return _structural_fallback_report()
        validated_predictions = tuple(
            TaskPrediction(item.predicted_disorder, item.risk_score)
            for item in predictions
        )
        validated_policy = _validated_policy(policy)
        validated_cohort = _validated_cohort(cohort, members)
        members = validated_cohort.members
        raw_cells = [
            _task_cell(
                "overall",
                members,
                validated_predictions,
                validated_policy,
            )
        ]
        if validated_policy.subgroup_dimensions == ("sex",):
            for sex in ("F", "M", "U"):
                selected_indices = tuple(
                    index
                    for index, member in enumerate(members)
                    if member.demographics.sex == sex
                )
                if selected_indices:
                    raw_cells.append(
                        _task_cell(
                            f"sex:{sex}",
                            tuple(members[index] for index in selected_indices),
                            tuple(
                                validated_predictions[index]
                                for index in selected_indices
                            ),
                            validated_policy,
                        )
                    )
        overall = raw_cells[0]

        if any(cell.status is TaskUtilityStatus.FAIL for cell in raw_cells):
            status = TaskUtilityStatus.FAIL
            reason_code = "OUTSIDE_BOUND"
        elif (
            len(members) < validated_policy.minimum_cohort_size
            or overall.evaluable_count
            < validated_policy.minimum_evaluable_members
        ):
            status = TaskUtilityStatus.UNEVALUABLE
            reason_code = "COHORT_TOO_SMALL"
        elif (
            overall.unevaluable_count
            > validated_policy.maximum_unevaluable_members
            or any(
                cell.scope != "overall"
                and cell.reason_code == "MISSING_PREDICTION"
                for cell in raw_cells
            )
        ):
            status = TaskUtilityStatus.UNEVALUABLE
            reason_code = "MISSING_PREDICTION"
        elif (
            validated_policy.require_probability_scores
            and any(cell.missing_score_count for cell in raw_cells)
        ):
            status = TaskUtilityStatus.UNEVALUABLE
            reason_code = "MISSING_SCORE"
        else:
            blocking_reasons = tuple(
                metric.reason_code
                for cell in raw_cells
                for metric in cell.metrics
                if (
                    metric.status is TaskUtilityStatus.UNEVALUABLE
                    and not (
                        not validated_policy.require_probability_scores
                        and metric.name in {"auroc", "brier_score"}
                        and metric.reason_code == "MISSING_SCORE"
                    )
                )
            )
            if blocking_reasons:
                status = TaskUtilityStatus.UNEVALUABLE
                reason_code = (
                    "MISSING_SCORE"
                    if "MISSING_SCORE" in blocking_reasons
                    else "INSUFFICIENT_SUPPORT"
                )
            else:
                status = TaskUtilityStatus.PASS
                reason_code = "WITHIN_BOUND"

        cells = tuple(
            _redacted_unevaluable_cell(
                cell,
                report_reason=reason_code,
            )
            if cell.status is TaskUtilityStatus.UNEVALUABLE
            or reason_code == "COHORT_TOO_SMALL"
            else cell
            for cell in raw_cells
        )
        counted_cells = Counter(cell.status.value for cell in cells)

        return TaskUtilityReport(
            report_version=TASK_UTILITY_REPORT_VERSION,
            policy_id=validated_policy.policy_id,
            policy_version=validated_policy.policy_version,
            cohort_profile=validated_cohort.profile,
            cohort_seed=validated_cohort.seed,
            cohort_size=len(members),
            status=status,
            reason_code=reason_code,
            status_counts={
                item.value: counted_cells[item.value]
                for item in TaskUtilityStatus
            },
            metric_counts={name: len(cells) for name in TASK_METRICS},
            evaluable_count=overall.evaluable_count,
            unevaluable_count=overall.unevaluable_count,
            cells=cells,
        )
    except Exception:  # noqa: BLE001 - malformed evidence must fail closed
        return _structural_fallback_report()


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
    "evaluate_task_utility",
]
