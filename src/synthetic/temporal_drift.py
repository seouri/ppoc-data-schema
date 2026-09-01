"""Immutable aggregate-only contracts for evaluator temporal drift reports."""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import InitVar, dataclass
from enum import Enum
from itertools import pairwise
from types import MappingProxyType

from synthetic.calibration import require_aggregate_safe_token
from synthetic.cohort import CohortMember, NativeCohort
from synthetic.models import (
    AgeRegimeDisorderTrajectory,
    AgeRegimePoint,
    AgeRegimeState,
    AgeRegimeTrajectory,
    ClinicalEvent,
    LatentDisorderState,
)
from synthetic.native.observations import (
    CensoringMode,
    ObservationFrame,
    ObservationTruth,
    ObservationWindow,
    ObservedVisit,
    RecordedEvent,
)
from synthetic.native.resources import SyntheticDemographics

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
_CAUSAL_PHASE_ORDER = MappingProxyType(
    {
        "latent_onset": 0,
        "observable_phenotype": 1,
        "recognition_opportunity": 2,
        "workup": 3,
        "recorded_diagnosis": 4,
        "treatment_start": 5,
        "treatment_response": 6,
        "treatment_nonresponse": 6,
    }
)
_TREATMENT_OUTCOMES = frozenset(
    {"treatment_response", "treatment_nonresponse"}
)
_STRUCTURAL_FALLBACK_PROFILE = "unavailable"
_STRUCTURAL_FALLBACK_SEED = 0
_STRUCTURAL_FALLBACK_SIZE = 0


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
        if difference != expected_difference:
            raise ValueError("difference must match the temporal metric bound")
        expected_status = (
            TemporalDriftStatus.PASS
            if expected_difference == 0
            else TemporalDriftStatus.FAIL
        )
        if status is not expected_status:
            raise ValueError("status must match the temporal metric bound")
        object.__setattr__(self, "difference", expected_difference)
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


def _window_order_index(value: object) -> Mapping[str, int]:
    if not isinstance(value, tuple):
        raise TypeError("_window_order must be an immutable tuple")
    if not value:
        raise ValueError("_window_order must be a nonempty immutable tuple")
    for window_id in value:
        require_aggregate_safe_token(window_id, "_window_order")
    if len(set(value)) != len(value):
        raise ValueError("_window_order values must be unique")
    return MappingProxyType(
        {window_id: index for index, window_id in enumerate(value)}
    )


def _comparison_sort_key(
    comparison: TemporalComparison, window_order: Mapping[str, int]
) -> tuple[object, ...]:
    return (
        _METRIC_ORDER[comparison.metric],
        -1 if comparison.window_id is None else window_order[comparison.window_id],
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
    _window_order: InitVar[tuple[str, ...]]

    def __post_init__(self, _window_order: tuple[str, ...]) -> None:
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

        window_order = _window_order_index(_window_order)
        if any(
            comparison.window_id is not None
            and comparison.window_id not in window_order
            for comparison in self.comparisons
        ):
            raise ValueError("comparison window_id must belong to _window_order")
        comparisons = tuple(
            sorted(
                self.comparisons,
                key=lambda comparison: _comparison_sort_key(
                    comparison, window_order
                ),
            )
        )
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


@dataclass(frozen=True)
class _VisibleWindowMetrics:
    window: TemporalWindowPolicy
    member_support: int
    growth_coverage: float
    visit_coverage: float
    event_rate: float
    mean_visit_count: float
    interval_member_support: int
    mean_inter_visit_days: float | None


def _is_in_window(age_days: int, window: TemporalWindowPolicy) -> bool:
    return window.lower_age_days <= age_days < window.upper_age_days


def _extract_visible_window_metrics(
    members: tuple[CohortMember, ...], window: TemporalWindowPolicy
) -> _VisibleWindowMetrics:
    member_support = len(members)
    growth_member_count = 0
    visit_member_count = 0
    event_member_count = 0
    total_visit_count = 0
    interval_member_support = 0
    intervals: list[int] = []

    for member in members:
        growth_count = sum(
            _is_in_window(point.age_days, window)
            for point in member.trajectory.physiology.points
        )
        visit_ages = sorted(
            visit.age_days
            for visit in member.frame.visits
            if _is_in_window(visit.age_days, window)
        )
        has_event = any(
            _is_in_window(event.age_days, window) for event in member.frame.events
        )

        growth_member_count += growth_count >= window.minimum_growth_points
        visit_member_count += len(visit_ages) >= window.minimum_visible_visits
        event_member_count += has_event
        total_visit_count += len(visit_ages)
        if len(visit_ages) >= 2:
            interval_member_support += 1
            intervals.extend(
                current - previous
                for previous, current in pairwise(visit_ages)
            )

    denominator = member_support or 1
    mean_inter_visit_days = (
        math.fsum(intervals) / len(intervals) if intervals else None
    )
    values = (
        growth_member_count / denominator,
        visit_member_count / denominator,
        event_member_count / denominator,
        total_visit_count / denominator,
    )
    if not all(math.isfinite(value) for value in values) or (
        mean_inter_visit_days is not None
        and not math.isfinite(mean_inter_visit_days)
    ):
        raise ValueError("visible temporal aggregates must be finite")
    return _VisibleWindowMetrics(
        window=window,
        member_support=member_support,
        growth_coverage=values[0],
        visit_coverage=values[1],
        event_rate=values[2],
        mean_visit_count=values[3],
        interval_member_support=interval_member_support,
        mean_inter_visit_days=mean_inter_visit_days,
    )


def _unevaluable_comparison(
    metric: str, window_id: str
) -> TemporalComparison:
    return TemporalComparison(
        metric=metric,
        window_id=window_id,
        status=TemporalDriftStatus.UNEVALUABLE,
        reason_code="INSUFFICIENT_SUPPORT",
        observed=None,
        target=None,
        difference=None,
        support_count=None,
    )


def _visible_comparison(
    metric: str,
    window_id: str,
    observed: float,
    target: float | None,
    support_count: int,
) -> TemporalComparison:
    difference = _comparison_difference(metric, observed, target)
    status = (
        TemporalDriftStatus.PASS
        if difference == 0
        else TemporalDriftStatus.FAIL
    )
    return TemporalComparison(
        metric=metric,
        window_id=window_id,
        status=status,
        reason_code="WITHIN_BOUND" if status is TemporalDriftStatus.PASS else "OUTSIDE_BOUND",
        observed=observed,
        target=target,
        difference=difference,
        support_count=support_count,
    )


def _window_comparisons(metrics: _VisibleWindowMetrics) -> tuple[TemporalComparison, ...]:
    window = metrics.window
    if metrics.member_support < window.minimum_member_support:
        return tuple(
            _unevaluable_comparison(metric, window.window_id)
            for metric in (
                "growth_window_coverage",
                "visible_visit_coverage",
                "visible_event_rate",
                "mean_inter_visit_days",
            )
        )

    comparisons = [
        _visible_comparison(
            "growth_window_coverage",
            window.window_id,
            metrics.growth_coverage,
            window.minimum_growth_coverage,
            metrics.member_support,
        ),
        _visible_comparison(
            "visible_visit_coverage",
            window.window_id,
            metrics.visit_coverage,
            window.minimum_visible_visit_coverage,
            metrics.member_support,
        ),
        _visible_comparison(
            "visible_event_rate",
            window.window_id,
            metrics.event_rate,
            None,
            metrics.member_support,
        ),
    ]
    if (
        metrics.mean_inter_visit_days is None
        or metrics.interval_member_support < window.minimum_member_support
    ):
        comparisons.append(
            _unevaluable_comparison("mean_inter_visit_days", window.window_id)
        )
    else:
        comparisons.append(
            _visible_comparison(
                "mean_inter_visit_days",
                window.window_id,
                metrics.mean_inter_visit_days,
                window.maximum_mean_inter_visit_days,
                metrics.interval_member_support,
            )
        )
    return tuple(comparisons)


def _step_comparisons(
    previous: _VisibleWindowMetrics, current: _VisibleWindowMetrics
) -> tuple[TemporalComparison, TemporalComparison]:
    if (
        previous.member_support < previous.window.minimum_member_support
        or current.member_support < current.window.minimum_member_support
    ):
        return (
            _unevaluable_comparison(
                "mean_visit_count_step", current.window.window_id
            ),
            _unevaluable_comparison(
                "recorded_event_rate_step", current.window.window_id
            ),
        )
    return (
        _visible_comparison(
            "mean_visit_count_step",
            current.window.window_id,
            current.mean_visit_count - previous.mean_visit_count,
            current.window.maximum_visit_count_step,
            current.member_support,
        ),
        _visible_comparison(
            "recorded_event_rate_step",
            current.window.window_id,
            current.event_rate - previous.event_rate,
            current.window.maximum_recorded_event_rate_step,
            current.member_support,
        ),
    )


def _visible_check(
    name: str, comparisons: tuple[TemporalComparison, ...]
) -> TemporalCheck:
    if any(
        comparison.reason_code == "STRUCTURAL_INVALID"
        for comparison in comparisons
    ):
        return TemporalCheck(
            name, TemporalDriftStatus.FAIL, "STRUCTURAL_INVALID"
        )
    if any(
        comparison.status is TemporalDriftStatus.FAIL for comparison in comparisons
    ):
        return TemporalCheck(name, TemporalDriftStatus.FAIL, "OUTSIDE_BOUND")
    if any(
        comparison.status is TemporalDriftStatus.UNEVALUABLE
        for comparison in comparisons
    ):
        return TemporalCheck(
            name, TemporalDriftStatus.UNEVALUABLE, "INSUFFICIENT_SUPPORT"
        )
    return TemporalCheck(name, TemporalDriftStatus.PASS, "WITHIN_BOUND")


def _causal_comparison(
    metric: str, status: TemporalDriftStatus
) -> TemporalComparison:
    reason_code = {
        TemporalDriftStatus.PASS: "OK",
        TemporalDriftStatus.FAIL: "STRUCTURAL_INVALID",
        TemporalDriftStatus.UNEVALUABLE: "MISSING_EVIDENCE",
    }[status]
    return TemporalComparison(
        metric=metric,
        window_id=None,
        status=status,
        reason_code=reason_code,
        observed=None,
        target=None,
        difference=None,
        support_count=None,
    )


def _structural_comparison(
    metric: str, window_id: str | None
) -> TemporalComparison:
    return TemporalComparison(
        metric=metric,
        window_id=window_id,
        status=TemporalDriftStatus.FAIL,
        reason_code="STRUCTURAL_INVALID",
        observed=None,
        target=None,
        difference=None,
        support_count=None,
    )


def _source_event_order_is_valid(
    member: CohortMember, events: tuple[ClinicalEvent, ...]
) -> bool:
    trajectory = member.trajectory
    frame = member.frame
    points = trajectory.physiology.points
    if not points:
        return False
    patient_id = member.demographics.patient_id
    if frame.patient_id != patient_id or points[0].patient_id != patient_id:
        return False

    phases: list[int] = []
    ages: list[int] = []
    event_types: list[str] = []
    for event in events:
        if not isinstance(event, ClinicalEvent):
            return False
        phase = _CAUSAL_PHASE_ORDER.get(event.event_type)
        if phase is None:
            return False
        if event.patient_id != patient_id or event.code is not None:
            return False
        if not isinstance(event.hidden, bool):
            return False
        if event.event_type == "latent_onset" and not event.hidden:
            return False
        if isinstance(event.age_days, bool) or not isinstance(event.age_days, int):
            return False
        phases.append(phase)
        ages.append(event.age_days)
        event_types.append(event.event_type)

    if any(current <= previous for previous, current in pairwise(phases)):
        return False
    if any(current < previous for previous, current in pairwise(ages)):
        return False

    outcomes = [
        index
        for index, event_type in enumerate(event_types)
        if event_type in _TREATMENT_OUTCOMES
    ]
    treatment_starts = [
        index
        for index, event_type in enumerate(event_types)
        if event_type == "treatment_start"
    ]
    if outcomes and (
        len(outcomes) != 1
        or len(treatment_starts) != 1
        or outcomes[0] != len(event_types) - 1
        or outcomes[0] <= treatment_starts[0]
    ):
        return False
    return not treatment_starts or len(outcomes) == 1


def _source_event_timing_is_valid(
    member: CohortMember,
    truth: ObservationTruth,
    events: tuple[ClinicalEvent, ...],
) -> bool:
    frame = member.frame
    window = frame.window
    if not isinstance(window, ObservationWindow) or truth.window != window:
        return False
    bounds = (
        window.start_age_days,
        window.effective_end_age_days,
        window.administrative_end_age_days,
    )
    if any(isinstance(value, bool) or not isinstance(value, int) for value in bounds):
        return False
    if not 0 <= bounds[0] < bounds[1] <= bounds[2]:
        return False
    if any(
        isinstance(event.age_days, bool)
        or not isinstance(event.age_days, int)
        or event.age_days < 0
        for event in events
    ):
        return False
    if not isinstance(frame.visits, tuple) or not isinstance(frame.events, tuple):
        return False
    if not all(isinstance(item, ObservedVisit) for item in frame.visits):
        return False
    if not all(isinstance(item, RecordedEvent) for item in frame.events):
        return False
    visible_records = (*frame.visits, *frame.events)
    return all(
        item.patient_id == frame.patient_id
        and not isinstance(item.age_days, bool)
        and isinstance(item.age_days, int)
        and window.start_age_days
        <= item.age_days
        < window.effective_end_age_days
        for item in visible_records
    )


def _observation_window_is_valid(window: object) -> bool:
    if type(window) is not ObservationWindow:
        return False
    bounds = (
        window.start_age_days,
        window.effective_end_age_days,
        window.administrative_end_age_days,
    )
    if any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in bounds
    ):
        return False
    if not 0 <= bounds[0] < bounds[1] <= bounds[2]:
        return False
    mode = window.censoring_mode
    if not isinstance(mode, CensoringMode):
        return False
    if mode is CensoringMode.LOST_TO_FOLLOW_UP:
        return bounds[1] < bounds[2]
    return bounds[1] == bounds[2]


def _truth_independent_member_invariants_are_valid(member: object) -> bool:
    if type(member) is not CohortMember:
        return False
    demographics = member.demographics
    if type(demographics) is not SyntheticDemographics:
        return False
    patient_id = member.demographics.patient_id
    if not isinstance(patient_id, str) or not patient_id:
        return False
    trajectory = member.trajectory
    if type(trajectory) is not AgeRegimeDisorderTrajectory:
        return False
    if type(trajectory.disorder) is not LatentDisorderState:
        return False
    physiology = trajectory.physiology
    if type(physiology) is not AgeRegimeTrajectory:
        return False
    if type(physiology.state) is not AgeRegimeState:
        return False
    points = physiology.points
    if (
        type(points) is not tuple
        or not points
        or not all(type(point) is AgeRegimePoint for point in points)
    ):
        return False
    if any(point.patient_id != patient_id for point in points):
        return False
    point_ages = tuple(point.age_days for point in points)
    if any(
        isinstance(age_days, bool)
        or not isinstance(age_days, int)
        or age_days < 0
        for age_days in point_ages
    ):
        return False
    if any(current <= previous for previous, current in pairwise(point_ages)):
        return False
    trajectory_events = trajectory.events
    if type(trajectory_events) is not tuple or not all(
        type(event) is ClinicalEvent for event in trajectory_events
    ):
        return False
    if any(
        event.patient_id != patient_id
        or isinstance(event.age_days, bool)
        or not isinstance(event.age_days, int)
        or event.age_days < 0
        for event in trajectory_events
    ):
        return False
    if not _source_event_order_is_valid(member, trajectory_events):
        return False
    frame = member.frame
    if type(frame) is not ObservationFrame or frame.patient_id != patient_id:
        return False
    window = frame.window
    if not _observation_window_is_valid(window):
        return False
    visits = frame.visits
    events = frame.events
    if type(visits) is not tuple or type(events) is not tuple:
        return False
    if not all(type(visit) is ObservedVisit for visit in visits):
        return False
    if not all(type(event) is RecordedEvent for event in events):
        return False
    visit_ids = tuple(visit.visit_id for visit in visits)
    if (
        any(not isinstance(visit_id, str) or not visit_id for visit_id in visit_ids)
        or len(visit_ids) != len(set(visit_ids))
    ):
        return False
    visible_records = (*visits, *events)
    return all(
        record.patient_id == patient_id
        and not isinstance(record.age_days, bool)
        and isinstance(record.age_days, int)
        and window.start_age_days
        <= record.age_days
        < window.effective_end_age_days
        for record in visible_records
    )


def _truth_invariants_are_valid(
    member: CohortMember, truth: ObservationTruth
) -> bool:
    frame = member.frame
    return truth.patient_id == frame.patient_id and truth.window == frame.window


def _member_causal_statuses(
    member: CohortMember,
) -> tuple[TemporalDriftStatus, TemporalDriftStatus]:
    try:
        if not _truth_independent_member_invariants_are_valid(member):
            return TemporalDriftStatus.FAIL, TemporalDriftStatus.FAIL
        truth = member.frame.truth
        if truth is None:
            return (
                TemporalDriftStatus.UNEVALUABLE,
                TemporalDriftStatus.UNEVALUABLE,
            )
        if not isinstance(truth, ObservationTruth):
            return TemporalDriftStatus.FAIL, TemporalDriftStatus.FAIL
        if not _truth_invariants_are_valid(member, truth):
            return TemporalDriftStatus.FAIL, TemporalDriftStatus.FAIL
        source_events = truth.source_events
        trajectory_events = member.trajectory.events
        if not isinstance(source_events, tuple) or not isinstance(
            trajectory_events, tuple
        ):
            return TemporalDriftStatus.FAIL, TemporalDriftStatus.FAIL
        if not source_events or not trajectory_events:
            return (
                TemporalDriftStatus.UNEVALUABLE,
                TemporalDriftStatus.UNEVALUABLE,
            )
        if source_events != trajectory_events:
            return TemporalDriftStatus.FAIL, TemporalDriftStatus.FAIL
        order_status = (
            TemporalDriftStatus.PASS
            if _source_event_order_is_valid(member, source_events)
            else TemporalDriftStatus.FAIL
        )
        timing_status = (
            TemporalDriftStatus.PASS
            if _source_event_timing_is_valid(member, truth, source_events)
            else TemporalDriftStatus.FAIL
        )
        return order_status, timing_status
    except Exception:  # noqa: BLE001 - injected evidence must fail closed
        return TemporalDriftStatus.FAIL, TemporalDriftStatus.FAIL


def _aggregate_causal_status(
    statuses: tuple[TemporalDriftStatus, ...]
) -> TemporalDriftStatus:
    if not statuses:
        return TemporalDriftStatus.UNEVALUABLE
    if any(status is TemporalDriftStatus.FAIL for status in statuses):
        return TemporalDriftStatus.FAIL
    if any(status is TemporalDriftStatus.UNEVALUABLE for status in statuses):
        return TemporalDriftStatus.UNEVALUABLE
    return TemporalDriftStatus.PASS


def _causal_comparisons(
    members: tuple[CohortMember, ...],
) -> tuple[TemporalComparison, TemporalComparison]:
    member_statuses = tuple(_member_causal_statuses(member) for member in members)
    order_status = _aggregate_causal_status(
        tuple(statuses[0] for statuses in member_statuses)
    )
    timing_status = _aggregate_causal_status(
        tuple(statuses[1] for statuses in member_statuses)
    )
    return (
        _causal_comparison("causal_event_order", order_status),
        _causal_comparison("causal_event_timing", timing_status),
    )


def _structural_comparisons(
    policy: TemporalDriftPolicy,
) -> tuple[TemporalComparison, ...]:
    comparisons = [
        _structural_comparison(metric, window.window_id)
        for window in policy.windows
        for metric in (
            "growth_window_coverage",
            "visible_visit_coverage",
            "visible_event_rate",
            "mean_inter_visit_days",
        )
    ]
    comparisons.extend(
        _structural_comparison(metric, current.window_id)
        for _previous, current in pairwise(policy.windows)
        for metric in ("mean_visit_count_step", "recorded_event_rate_step")
    )
    comparisons.extend(
        (
            _structural_comparison("causal_event_order", None),
            _structural_comparison("causal_event_timing", None),
        )
    )
    return tuple(comparisons)


def _causal_check(comparison: TemporalComparison) -> TemporalCheck:
    return TemporalCheck(
        comparison.metric,
        comparison.status,
        comparison.reason_code,
    )


def _assemble_report(
    policy: TemporalDriftPolicy,
    comparisons: tuple[TemporalComparison, ...],
    *,
    cohort_profile: str,
    cohort_seed: int,
    cohort_size: int,
    required_window_lacks_support: bool,
) -> TemporalDriftReport:
    coverage_comparisons = tuple(
        comparison
        for comparison in comparisons
        if comparison.metric in _LOWER_BOUND_METRICS
    )
    sequence_comparisons = tuple(
        comparison
        for comparison in comparisons
        if comparison.metric not in _LOWER_BOUND_METRICS | _CAUSAL_METRICS
    )
    causal_by_metric = {
        comparison.metric: comparison
        for comparison in comparisons
        if comparison.metric in _CAUSAL_METRICS
    }
    cohort_is_too_small = cohort_size < policy.minimum_cohort_size
    cohort_check = (
        TemporalCheck("cohort_size", TemporalDriftStatus.PASS, "OK")
        if not cohort_is_too_small
        else TemporalCheck(
            "cohort_size", TemporalDriftStatus.UNEVALUABLE, "COHORT_TOO_SMALL"
        )
    )
    checks = (
        cohort_check,
        _visible_check("window_coverage", coverage_comparisons),
        _visible_check("sequence_metrics", sequence_comparisons),
        _causal_check(causal_by_metric["causal_event_order"]),
        _causal_check(causal_by_metric["causal_event_timing"]),
    )
    unevaluable_count = sum(
        comparison.status is TemporalDriftStatus.UNEVALUABLE
        for comparison in comparisons
    )
    if any(
        comparison.status is TemporalDriftStatus.FAIL for comparison in comparisons
    ):
        report_status = TemporalDriftStatus.FAIL
    elif (
        cohort_is_too_small
        or unevaluable_count > policy.maximum_unevaluable_checks
        or required_window_lacks_support
    ):
        report_status = TemporalDriftStatus.UNEVALUABLE
    else:
        report_status = TemporalDriftStatus.PASS

    counted_statuses = Counter(
        comparison.status.value for comparison in comparisons
    )
    counted_metrics = Counter(comparison.metric for comparison in comparisons)
    return TemporalDriftReport(
        report_version=TEMPORAL_DRIFT_REPORT_VERSION,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        cohort_profile=cohort_profile,
        cohort_seed=cohort_seed,
        cohort_size=cohort_size,
        status=report_status,
        status_counts={
            status.value: counted_statuses[status.value]
            for status in TemporalDriftStatus
        },
        metric_counts={metric: counted_metrics[metric] for metric in TEMPORAL_METRICS},
        checks=checks,
        comparisons=comparisons,
        _window_order=tuple(window.window_id for window in policy.windows),
    )


def _structural_fallback_report(
    policy: TemporalDriftPolicy,
) -> TemporalDriftReport:
    return _assemble_report(
        policy,
        _structural_comparisons(policy),
        cohort_profile=_STRUCTURAL_FALLBACK_PROFILE,
        cohort_seed=_STRUCTURAL_FALLBACK_SEED,
        cohort_size=_STRUCTURAL_FALLBACK_SIZE,
        required_window_lacks_support=False,
    )


def validate_temporal_drift(
    cohort: NativeCohort, policy: TemporalDriftPolicy
) -> TemporalDriftReport:
    """Evaluate visible and causal temporal drift for a fictional native cohort."""

    if not isinstance(cohort, NativeCohort):
        raise TypeError("cohort must be a NativeCohort")
    if not isinstance(policy, TemporalDriftPolicy):
        raise TypeError("policy must be a TemporalDriftPolicy")

    try:
        cohort_profile = require_aggregate_safe_token(
            cohort.profile, "cohort_profile"
        )
        cohort_seed = _require_integer(
            cohort.seed, "cohort_seed", minimum=0
        )
        members = cohort.members
        if type(members) is not tuple or not all(
            isinstance(member, CohortMember) for member in members
        ):
            raise TypeError("members must contain CohortMember values")
        cohort_size = len(members)
        window_metrics = tuple(
            _extract_visible_window_metrics(members, window)
            for window in policy.windows
        )
    except Exception:  # noqa: BLE001 - injected evidence must fail closed
        return _structural_fallback_report(policy)

    window_comparisons = tuple(
        comparison
        for metrics in window_metrics
        for comparison in _window_comparisons(metrics)
    )
    step_comparisons = tuple(
        comparison
        for previous, current in pairwise(window_metrics)
        for comparison in _step_comparisons(previous, current)
    )
    comparisons = (
        window_comparisons
        + step_comparisons
        + _causal_comparisons(members)
    )
    return _assemble_report(
        policy,
        comparisons,
        cohort_profile=cohort_profile,
        cohort_seed=cohort_seed,
        cohort_size=cohort_size,
        required_window_lacks_support=any(
            metrics.member_support < metrics.window.minimum_member_support
            for metrics in window_metrics
        ),
    )


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
    "validate_temporal_drift",
]
