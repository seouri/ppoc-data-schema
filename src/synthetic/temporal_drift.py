"""Immutable aggregate-only contracts for evaluator temporal drift reports."""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from synthetic.calibration import require_aggregate_safe_token

TEMPORAL_DRIFT_REPORT_VERSION = "temporal-drift-report-v1"

TEMPORAL_METRICS = (
    "growth_window_coverage",
    "visible_visit_coverage",
    "visible_event_rate",
    "mean_inter_visit_days",
    "mean_visit_count_step",
    "recorded_event_rate_step",
    "causal_event_order",
    "causal_event_timing",
)

TEMPORAL_REASON_CODES = (
    "OK",
    "WITHIN_BOUND",
    "INSUFFICIENT_SUPPORT",
    "COHORT_TOO_SMALL",
    "MISSING_EVIDENCE",
    "STRUCTURAL_INVALID",
    "OUTSIDE_BOUND",
)

_TEMPORAL_CHECK_NAMES = (
    "cohort_size",
    "window_coverage",
    "sequence_metrics",
    "causal_event_order",
    "causal_event_timing",
)
_CAUSAL_METRICS = frozenset({"causal_event_order", "causal_event_timing"})
_LOWER_BOUND_METRICS = frozenset(
    {"growth_window_coverage", "visible_visit_coverage"}
)
_UPPER_BOUND_METRICS = frozenset({"mean_inter_visit_days"})
_STEP_METRICS = frozenset({"mean_visit_count_step", "recorded_event_rate_step"})
_METRIC_ORDER = MappingProxyType(
    {metric: index for index, metric in enumerate(TEMPORAL_METRICS)}
)
_CHECK_ORDER = MappingProxyType(
    {name: index for index, name in enumerate(_TEMPORAL_CHECK_NAMES)}
)
_STATUS_ORDER = MappingProxyType({"PASS": 0, "FAIL": 1, "UNEVALUABLE": 2})


class TemporalDriftStatus(str, Enum):
    """Closed aggregate status for comparisons, checks, and reports."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNEVALUABLE = "UNEVALUABLE"


_STATUS_REASON_CODES = MappingProxyType(
    {
        TemporalDriftStatus.PASS: frozenset({"OK", "WITHIN_BOUND"}),
        TemporalDriftStatus.FAIL: frozenset({"OUTSIDE_BOUND", "STRUCTURAL_INVALID"}),
        TemporalDriftStatus.UNEVALUABLE: frozenset(
            {"INSUFFICIENT_SUPPORT", "COHORT_TOO_SMALL", "MISSING_EVIDENCE"}
        ),
    }
)


def _require_integer(value: object, field: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")  # noqa: TRY004
    if value < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    return value


def _require_number(value: object, field: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")  # noqa: TRY004
    try:
        if not math.isfinite(value):
            raise ValueError(f"{field} must be a finite number")
    except OverflowError:
        raise ValueError(f"{field} must be a finite number") from None
    return value


def _require_nonnegative_number(value: object, field: str) -> float:
    number = float(_require_number(value, field))
    if number < 0:
        raise ValueError(f"{field} must be nonnegative")
    return number


def _require_fraction(value: object, field: str) -> float:
    number = float(_require_number(value, field))
    if not 0 <= number <= 1:
        raise ValueError(f"{field} must be in [0, 1]")
    return number


def _require_status(value: object) -> TemporalDriftStatus:
    if not isinstance(value, TemporalDriftStatus):
        raise TypeError("status must be a TemporalDriftStatus")
    return value


def _require_reason(status: TemporalDriftStatus, value: object) -> str:
    if not isinstance(value, str) or value not in TEMPORAL_REASON_CODES:
        raise ValueError("reason_code must be a fixed temporal reason code")
    if value not in _STATUS_REASON_CODES[status]:
        raise ValueError("reason_code must be compatible with status")
    return value


@dataclass(frozen=True)
class TemporalWindowPolicy:
    """Frozen visible-metric thresholds for one half-open age window."""

    window_id: str
    lower_age_days: int
    upper_age_days: int
    minimum_member_support: int
    minimum_growth_points: int
    minimum_visible_visits: int
    minimum_growth_coverage: float
    minimum_visible_visit_coverage: float
    maximum_mean_inter_visit_days: float
    maximum_visit_count_step: float
    maximum_recorded_event_rate_step: float

    def __post_init__(self) -> None:
        require_aggregate_safe_token(self.window_id, "window_id")
        lower = _require_integer(self.lower_age_days, "lower_age_days", minimum=0)
        upper = _require_integer(self.upper_age_days, "upper_age_days", minimum=1)
        if lower >= upper:
            raise ValueError("upper_age_days must be greater than lower_age_days")
        _require_integer(
            self.minimum_member_support, "minimum_member_support", minimum=1
        )
        _require_integer(
            self.minimum_growth_points, "minimum_growth_points", minimum=0
        )
        _require_integer(
            self.minimum_visible_visits, "minimum_visible_visits", minimum=0
        )
        object.__setattr__(
            self,
            "minimum_growth_coverage",
            _require_fraction(self.minimum_growth_coverage, "minimum_growth_coverage"),
        )
        object.__setattr__(
            self,
            "minimum_visible_visit_coverage",
            _require_fraction(
                self.minimum_visible_visit_coverage,
                "minimum_visible_visit_coverage",
            ),
        )
        for field in (
            "maximum_mean_inter_visit_days",
            "maximum_visit_count_step",
            "maximum_recorded_event_rate_step",
        ):
            object.__setattr__(
                self,
                field,
                _require_nonnegative_number(getattr(self, field), field),
            )


@dataclass(frozen=True)
class TemporalDriftPolicy:
    """Immutable policy declared before evaluating a fictional cohort."""

    policy_id: str
    policy_version: str
    minimum_cohort_size: int
    maximum_unevaluable_checks: int
    windows: tuple[TemporalWindowPolicy, ...]

    def __post_init__(self) -> None:
        require_aggregate_safe_token(self.policy_id, "policy_id")
        require_aggregate_safe_token(self.policy_version, "policy_version")
        _require_integer(self.minimum_cohort_size, "minimum_cohort_size", minimum=1)
        _require_integer(
            self.maximum_unevaluable_checks,
            "maximum_unevaluable_checks",
            minimum=0,
        )
        if not isinstance(self.windows, tuple):
            raise TypeError("windows must be an immutable tuple")
        if not self.windows:
            raise ValueError("windows must be a nonempty immutable tuple")
        if not all(isinstance(window, TemporalWindowPolicy) for window in self.windows):
            raise TypeError("windows must contain TemporalWindowPolicy values")
        if len({window.window_id for window in self.windows}) != len(self.windows):
            raise ValueError("windows window_id values must be unique")
        for previous, current in zip(self.windows, self.windows[1:], strict=False):
            if current.lower_age_days < previous.lower_age_days:
                raise ValueError("windows must be ordered by lower_age_days")
            if current.lower_age_days < previous.upper_age_days:
                raise ValueError("windows must be non-overlapping")


def _comparison_difference(
    metric: str, observed: float, target: float | None
) -> float:
    if metric in _LOWER_BOUND_METRICS:
        if target is None:
            raise ValueError("target is required for bounded temporal metrics")
        return max(0.0, float(target) - float(observed))
    if metric in _UPPER_BOUND_METRICS:
        if target is None:
            raise ValueError("target is required for bounded temporal metrics")
        return max(0.0, float(observed) - float(target))
    if metric in _STEP_METRICS:
        if target is None:
            raise ValueError("target is required for bounded temporal metrics")
        return max(0.0, abs(float(observed)) - float(target))
    if metric == "visible_event_rate":
        if target is not None:
            raise ValueError("target must be null for diagnostic temporal metrics")
        return 0.0
    raise ValueError("metric does not support numeric temporal comparison fields")


@dataclass(frozen=True, repr=False)
class TemporalComparison:
    """One fixed-vocabulary aggregate comparison without member-level evidence."""

    metric: str
    window_id: str | None
    status: TemporalDriftStatus
    reason_code: str
    observed: float | int | None
    target: float | int | None
    difference: float | None
    support_count: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.metric, str) or self.metric not in TEMPORAL_METRICS:
            raise ValueError("metric must belong to the fixed temporal metric registry")
        status = _require_status(self.status)
        _require_reason(status, self.reason_code)

        values = (self.observed, self.target, self.difference, self.support_count)
        if self.metric in _CAUSAL_METRICS:
            if self.window_id is not None:
                raise ValueError("window_id must be null for causal temporal metrics")
            if any(value is not None for value in values):
                raise ValueError("causal temporal comparisons require null numeric fields")
            return

        require_aggregate_safe_token(self.window_id, "window_id")
        if status is TemporalDriftStatus.UNEVALUABLE or self.reason_code == "STRUCTURAL_INVALID":
            if any(value is not None for value in values):
                raise ValueError(
                    "unevaluable and structural comparisons require null numeric fields"
                )
            return

        if self.observed is None:
            raise ValueError("observed must be present for evaluable temporal comparisons")
        if self.difference is None:
            raise ValueError("difference must be present for evaluable temporal comparisons")
        if self.support_count is None:
            raise ValueError("support_count must be present for evaluable temporal comparisons")
        observed = _require_number(self.observed, "observed")
        target = (
            None if self.target is None else _require_number(self.target, "target")
        )
        difference = _require_nonnegative_number(self.difference, "difference")
        support_count = _require_integer(
            self.support_count, "support_count", minimum=0
        )

        if self.metric in {
            "growth_window_coverage",
            "visible_visit_coverage",
            "visible_event_rate",
        }:
            if not 0 <= float(observed) <= 1:
                raise ValueError("observed must be in [0, 1] for rate metrics")
            if target is not None and not 0 <= float(target) <= 1:
                raise ValueError("target must be in [0, 1] for coverage metrics")
        elif self.metric == "mean_inter_visit_days" and float(observed) < 0:
            raise ValueError("observed must be nonnegative for mean_inter_visit_days")
        if target is not None and float(target) < 0:
            raise ValueError("target must be nonnegative")

        expected_difference = _comparison_difference(self.metric, observed, target)
        if not math.isclose(difference, expected_difference, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("difference must match the temporal metric bound")
        expected_status = (
            TemporalDriftStatus.PASS
            if expected_difference == 0
            else TemporalDriftStatus.FAIL
        )
        if status is not expected_status:
            raise ValueError("status must match the temporal metric bound")
        object.__setattr__(self, "difference", difference)
        object.__setattr__(self, "support_count", support_count)

    def to_mapping(self) -> dict[str, object]:
        return {
            "metric": self.metric,
            "window_id": self.window_id,
            "status": self.status.value,
            "reason_code": self.reason_code,
            "observed": self.observed,
            "target": self.target,
            "difference": self.difference,
            "support_count": self.support_count,
        }

    def __repr__(self) -> str:
        return "TemporalComparison(<aggregate-only>)"


@dataclass(frozen=True)
class TemporalCheck:
    """One fixed aggregate evaluator check."""

    name: str
    status: TemporalDriftStatus
    reason_code: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or self.name not in _TEMPORAL_CHECK_NAMES:
            raise ValueError("name must belong to the fixed temporal check registry")
        status = _require_status(self.status)
        _require_reason(status, self.reason_code)

    def to_mapping(self) -> dict[str, str]:
        return {
            "name": self.name,
            "status": self.status.value,
            "reason_code": self.reason_code,
        }


def _freeze_counts(
    value: object, keys: tuple[str, ...], field: str
) -> Mapping[str, int]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be a mapping")
    if set(value) != set(keys):
        raise ValueError(f"{field} must use the fixed registry keys")
    return MappingProxyType(
        {key: _require_integer(value[key], f"{field}.{key}", minimum=0) for key in keys}
    )


def _comparison_sort_key(comparison: TemporalComparison) -> tuple[object, ...]:
    return (
        _METRIC_ORDER[comparison.metric],
        "" if comparison.window_id is None else comparison.window_id,
        _STATUS_ORDER[comparison.status.value],
    )


@dataclass(frozen=True, repr=False)
class TemporalDriftReport:
    """Immutable deterministic aggregate-only temporal evaluator report."""

    report_version: str
    policy_id: str
    policy_version: str
    cohort_profile: str
    cohort_seed: int
    cohort_size: int
    status: TemporalDriftStatus
    status_counts: Mapping[str, int]
    metric_counts: Mapping[str, int]
    checks: tuple[TemporalCheck, ...]
    comparisons: tuple[TemporalComparison, ...]

    def __post_init__(self) -> None:
        if self.report_version != TEMPORAL_DRIFT_REPORT_VERSION:
            raise ValueError(
                f"report_version must be {TEMPORAL_DRIFT_REPORT_VERSION}"
            )
        require_aggregate_safe_token(self.policy_id, "policy_id")
        require_aggregate_safe_token(self.policy_version, "policy_version")
        require_aggregate_safe_token(self.cohort_profile, "cohort_profile")
        _require_integer(self.cohort_seed, "cohort_seed", minimum=0)
        _require_integer(self.cohort_size, "cohort_size", minimum=0)
        _require_status(self.status)

        status_keys = tuple(status.value for status in TemporalDriftStatus)
        status_counts = _freeze_counts(self.status_counts, status_keys, "status_counts")
        metric_counts = _freeze_counts(
            self.metric_counts, TEMPORAL_METRICS, "metric_counts"
        )
        if not isinstance(self.checks, tuple):
            raise TypeError("checks must be an immutable tuple")
        if not all(isinstance(check, TemporalCheck) for check in self.checks):
            raise TypeError("checks must contain TemporalCheck values")
        if (
            len(self.checks) != len(_TEMPORAL_CHECK_NAMES)
            or {check.name for check in self.checks} != set(_TEMPORAL_CHECK_NAMES)
        ):
            raise ValueError("checks must contain unique fixed names exactly once")
        if not isinstance(self.comparisons, tuple):
            raise TypeError("comparisons must be an immutable tuple")
        if not self.comparisons:
            raise ValueError("comparisons must be a nonempty immutable tuple")
        if not all(
            isinstance(comparison, TemporalComparison)
            for comparison in self.comparisons
        ):
            raise TypeError("comparisons must contain TemporalComparison values")

        comparisons = tuple(sorted(self.comparisons, key=_comparison_sort_key))
        counted_statuses = Counter(
            comparison.status.value for comparison in comparisons
        )
        expected_status_counts = {
            key: counted_statuses[key] for key in status_keys
        }
        if dict(status_counts) != expected_status_counts:
            raise ValueError("status_counts must match comparisons")
        counted_metrics = Counter(comparison.metric for comparison in comparisons)
        expected_metric_counts = {
            key: counted_metrics[key] for key in TEMPORAL_METRICS
        }
        if dict(metric_counts) != expected_metric_counts:
            raise ValueError("metric_counts must match comparisons")

        object.__setattr__(self, "status_counts", status_counts)
        object.__setattr__(self, "metric_counts", metric_counts)
        object.__setattr__(
            self,
            "checks",
            tuple(sorted(self.checks, key=lambda check: _CHECK_ORDER[check.name])),
        )
        object.__setattr__(self, "comparisons", comparisons)

    def to_mapping(self) -> dict[str, object]:
        return {
            "report_version": self.report_version,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "cohort_profile": self.cohort_profile,
            "cohort_seed": self.cohort_seed,
            "cohort_size": self.cohort_size,
            "status": self.status.value,
            "status_counts": dict(self.status_counts),
            "metric_counts": dict(self.metric_counts),
            "checks": [check.to_mapping() for check in self.checks],
            "comparisons": [comparison.to_mapping() for comparison in self.comparisons],
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
        return "TemporalDriftReport(<aggregate-only>)"


__all__ = [
    "TEMPORAL_DRIFT_REPORT_VERSION",
    "TEMPORAL_METRICS",
    "TEMPORAL_REASON_CODES",
    "TemporalCheck",
    "TemporalComparison",
    "TemporalDriftPolicy",
    "TemporalDriftReport",
    "TemporalDriftStatus",
    "TemporalWindowPolicy",
]
