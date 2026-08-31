"""Aggregate-only models for native synthetic-cohort fidelity profiling.

This module intentionally contains only the immutable policy/report contract.
The evaluator is assembled in a later layer and must consume an in-memory
``NativeCohort`` without crossing into governed inputs or output lifecycles.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from numbers import Real
from types import MappingProxyType

from synthetic.calibration import require_aggregate_safe_token
from synthetic.cohort import NativeCohort
from synthetic.models import DisorderKind

COHORT_VALIDATION_REPORT_VERSION = "cohort-validation-report-v1"

GROWTH_TOLERANCE_KEYS = (
    "height_z_score",
    "bmi_z_score",
    "height_velocity_cm_per_year",
    "weight_velocity_kg_per_year",
)

# These names are deliberately closed.  Dynamic names below are permitted only
# when their variable component comes from one of the same fixed vocabularies.
COHORT_COMPARISON_LAYERS = (
    "cohort",
    "demographics",
    "latent",
    "observable",
    "recorded",
    "growth",
    "coverage",
)
COMPARISON_LAYERS = frozenset(COHORT_COMPARISON_LAYERS)

_LAYER_ORDER = MappingProxyType(
    {name: index for index, name in enumerate(COHORT_COMPARISON_LAYERS)}
)
_DEMOGRAPHIC_DIMENSIONS = frozenset({"sex", "ethnicity", "race"})
_FIXED_COMPARISON_NAMES = frozenset(
    {
        "cohort_size",
        "observable_phenotype",
        "recorded_recognition",
        "recorded_workup",
        "recorded_diagnosis",
        "coverage.cohort_size",
        "coverage.members_with_visit",
        "coverage.members_with_event",
        "coverage.members_with_recorded_event",
    }
)

# Reasons use the same upper-case style as the existing native validation
# reports.  The registry is exposed as immutable values so evaluator code can
# share it without creating an open-ended public vocabulary.
COHORT_COMPARISON_REASON_CODES = MappingProxyType(
    {
        "PASS": frozenset(
            {
                "OK",
                "WITHIN_TOLERANCE",
                "OBSERVED",
                "NO_EVIDENCE",
                "ABOVE_MINIMUM_SUPPORT",
            }
        ),
        "FAIL": frozenset(
            {
                "OUTSIDE_TOLERANCE",
                "INVALID_VALUE",
                "MALFORMED_COHORT",
                "STRUCTURAL_INVALID",
            }
        ),
        "UNEVALUABLE": frozenset(
            {
                "INSUFFICIENT_SUPPORT",
                "COHORT_TOO_SMALL",
                "MISSING_EVIDENCE",
                "MALFORMED_COHORT",
            }
        ),
    }
)
COMPARISON_REASON_CODES = frozenset(
    reason
    for reasons in COHORT_COMPARISON_REASON_CODES.values()
    for reason in reasons
)

_STATUS_VALUES = frozenset(COHORT_COMPARISON_REASON_CODES)
_DISORDER_ORDER = {kind.value: index for index, kind in enumerate(DisorderKind)}


class CohortValidationStatus(str, Enum):
    """Aggregate status for one profile comparison or complete report."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNEVALUABLE = "UNEVALUABLE"


def _require_positive_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _require_nonnegative_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a nonnegative integer")
    return value


def _require_finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be a finite number")
    try:
        number = float(value)
    except OverflowError:
        raise ValueError(f"{field_name} must be a finite number") from None
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be a finite number")
    return number


def _require_nonnegative_finite_number(value: object, field_name: str) -> float:
    number = _require_finite_number(value, field_name)
    if number < 0:
        raise ValueError(f"{field_name} must be finite and nonnegative")
    return number


def _validate_age_windows(value: object) -> tuple[tuple[str, int, int], ...]:
    if not isinstance(value, tuple) or not value:
        raise TypeError("required_age_windows must be a nonempty tuple")

    windows: list[tuple[str, int, int]] = []
    names: set[str] = set()
    previous_lower: int | None = None
    previous_upper: int | None = None
    for index, item in enumerate(value):
        if not isinstance(item, tuple) or len(item) != 3:
            raise TypeError("required_age_windows must contain name/lower/upper triples")
        name, lower, upper = item
        require_aggregate_safe_token(name, f"required_age_windows[{index}].name")
        lower = _require_nonnegative_integer(
            lower, f"required_age_windows[{index}].lower_age_days"
        )
        upper = _require_positive_integer(
            upper, f"required_age_windows[{index}].upper_age_days"
        )
        if lower >= upper:
            raise ValueError("required_age_windows bounds must be half-open and ordered")
        if name in names:
            raise ValueError("required_age_windows names must be unique")
        if previous_lower is not None and lower < previous_lower:
            raise ValueError("required_age_windows must be sorted by lower age")
        if previous_upper is not None and lower < previous_upper:
            raise ValueError("required_age_windows must be non-overlapping")
        names.add(name)
        windows.append((name, lower, upper))
        previous_lower = lower
        previous_upper = upper
    return tuple(windows)


def _validate_growth_tolerances(value: object) -> Mapping[str, float]:
    if not isinstance(value, Mapping):
        raise TypeError("growth_tolerances must be a mapping")
    if set(value) != set(GROWTH_TOLERANCE_KEYS):
        raise ValueError("growth_tolerances must use the canonical metric keys")
    frozen = {
        key: _require_nonnegative_finite_number(value[key], f"growth_tolerances.{key}")
        for key in GROWTH_TOLERANCE_KEYS
    }
    return MappingProxyType(frozen)


@dataclass(frozen=True)
class CohortValidationPolicy:
    """Immutable bounds used before evaluating one fictional cohort."""

    policy_id: str
    policy_version: str
    minimum_cohort_size: int
    minimum_cell_support: int
    minimum_event_support: int
    proportion_tolerance: float
    growth_tolerances: Mapping[str, float]
    required_age_windows: tuple[tuple[str, int, int], ...]

    def __post_init__(self) -> None:
        require_aggregate_safe_token(self.policy_id, "policy_id")
        require_aggregate_safe_token(self.policy_version, "policy_version")
        _require_positive_integer(self.minimum_cohort_size, "minimum_cohort_size")
        _require_positive_integer(self.minimum_cell_support, "minimum_cell_support")
        _require_positive_integer(self.minimum_event_support, "minimum_event_support")
        proportion_tolerance = _require_nonnegative_finite_number(
            self.proportion_tolerance, "proportion_tolerance"
        )
        object.__setattr__(self, "proportion_tolerance", proportion_tolerance)
        object.__setattr__(
            self, "growth_tolerances", _validate_growth_tolerances(self.growth_tolerances)
        )
        object.__setattr__(
            self, "required_age_windows", _validate_age_windows(self.required_age_windows)
        )

    def to_mapping(self) -> dict[str, object]:
        """Return a fresh, JSON-compatible copy of the public policy fields."""

        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "minimum_cohort_size": self.minimum_cohort_size,
            "minimum_cell_support": self.minimum_cell_support,
            "minimum_event_support": self.minimum_event_support,
            "proportion_tolerance": self.proportion_tolerance,
            "growth_tolerances": dict(self.growth_tolerances),
            "required_age_windows": [list(window) for window in self.required_age_windows],
        }


def _expected_layer(name: str) -> str | None:
    if name == "cohort_size":
        return "cohort"
    if name == "observable_phenotype":
        return "observable"
    if name.startswith("recorded_") and name in {
        "recorded_recognition",
        "recorded_workup",
        "recorded_diagnosis",
    }:
        return "recorded"
    if name.startswith("coverage."):
        return "coverage"
    parts = name.split(".", 2)
    if len(parts) == 3 and parts[0] == "demographics" and parts[1] in _DEMOGRAPHIC_DIMENSIONS:
        return "demographics"
    if len(parts) == 2 and parts[0] == "latent_module" and parts[1] in _DISORDER_ORDER:
        return "latent"
    if len(parts) == 3 and parts[0] == "growth" and parts[2].endswith("_mean"):
        metric = parts[2][:-5]
        if metric in GROWTH_TOLERANCE_KEYS:
            return "growth"
    return None


def _validate_comparison_name(value: object) -> str:
    name = require_aggregate_safe_token(value, "name")
    if name not in _FIXED_COMPARISON_NAMES and _expected_layer(name) is None:
        raise ValueError("name must be a registered cohort comparison")
    return name


def _validate_comparison_layer(name: str, value: object) -> str:
    if not isinstance(value, str) or value not in COMPARISON_LAYERS:
        raise ValueError("layer must be a registered cohort comparison layer")
    expected = _expected_layer(name)
    if expected is not None and value != expected and not (
        name == "cohort_size" and value == "coverage"
    ):
        raise ValueError("layer does not match the registered comparison name")
    return value


def _validate_reason(status: CohortValidationStatus, value: object) -> str:
    if not isinstance(value, str) or value not in COHORT_COMPARISON_REASON_CODES[status.value]:
        raise ValueError("reason_code must be compatible with status")
    return value


def _comparison_sort_key(comparison: CohortComparison) -> tuple[object, ...]:
    name = comparison.name
    if name == "cohort_size":
        return (0, 0, name)
    if name.startswith("demographics."):
        parts = name.split(".", 2)
        dimension_order = {"sex": 0, "ethnicity": 1, "race": 2}
        return (1, dimension_order[parts[1]], parts[2])
    if name.startswith("latent_module."):
        module = name.split(".", 1)[1]
        return (2, _DISORDER_ORDER[module], module)
    if name == "observable_phenotype":
        return (3, 0, name)
    if name.startswith("recorded_"):
        return (4, ("recorded_recognition", "recorded_workup", "recorded_diagnosis").index(name), name)
    if name.startswith("growth."):
        return (5, name)
    if name.startswith("coverage."):
        return (6, name)
    return (99, _LAYER_ORDER[comparison.layer], name)


@dataclass(frozen=True)
class CohortComparison:
    """One aggregate comparison with no row-level or evaluator truth fields."""

    name: str
    layer: str
    status: CohortValidationStatus
    observed_value: float | int | None
    target_value: float | int | None
    difference: float | None
    tolerance: float | None
    support: int
    denominator: int
    reason_code: str

    def __post_init__(self) -> None:
        name = _validate_comparison_name(self.name)
        object.__setattr__(self, "name", name)
        layer = _validate_comparison_layer(name, self.layer)
        object.__setattr__(self, "layer", layer)
        if not isinstance(self.status, CohortValidationStatus):
            raise TypeError("status must be a CohortValidationStatus")
        _validate_reason(self.status, self.reason_code)

        support = _require_nonnegative_integer(self.support, "support")
        denominator = _require_nonnegative_integer(self.denominator, "denominator")
        if support > denominator:
            raise ValueError("support must not exceed denominator")
        object.__setattr__(self, "support", support)
        object.__setattr__(self, "denominator", denominator)

        values = (self.observed_value, self.target_value, self.difference, self.tolerance)
        if self.status is CohortValidationStatus.UNEVALUABLE:
            if any(value is not None for value in values):
                raise ValueError("UNEVALUABLE comparisons require null numeric values")
            return

        if denominator <= 0:
            raise ValueError("evaluable comparisons require a positive denominator")
        observed = self.observed_value
        target = self.target_value
        if target is None:
            if self.difference is not None or self.tolerance is not None:
                raise ValueError("status-only aggregate comparisons require null target fields")
            _require_finite_number(observed, "observed_value")
            return

        if observed is None or self.difference is None or self.tolerance is None:
            raise ValueError("targeted comparisons require all numeric values")
        observed_number = _require_finite_number(observed, "observed_value")
        target_number = _require_finite_number(target, "target_value")
        difference = _require_nonnegative_finite_number(self.difference, "difference")
        tolerance = _require_nonnegative_finite_number(self.tolerance, "tolerance")
        expected_difference = abs(observed_number - target_number)
        if difference != expected_difference:
            raise ValueError("difference must equal the absolute numeric difference")
        expected_status = (
            CohortValidationStatus.PASS
            if difference <= tolerance
            else CohortValidationStatus.FAIL
        )
        if self.status is not expected_status:
            raise ValueError("status must match difference and tolerance")

    def to_mapping(self) -> dict[str, object]:
        """Return only aggregate values and fixed vocabulary fields."""

        return {
            "name": self.name,
            "layer": self.layer,
            "status": self.status.value,
            "observed_value": self.observed_value,
            "target_value": self.target_value,
            "difference": self.difference,
            "tolerance": self.tolerance,
            "support": self.support,
            "denominator": self.denominator,
            "reason_code": self.reason_code,
        }


def _report_status(comparisons: tuple[CohortComparison, ...]) -> CohortValidationStatus:
    if any(item.status is CohortValidationStatus.FAIL for item in comparisons):
        return CohortValidationStatus.FAIL
    if any(item.status is CohortValidationStatus.UNEVALUABLE for item in comparisons):
        return CohortValidationStatus.UNEVALUABLE
    return CohortValidationStatus.PASS


@dataclass(frozen=True, repr=False)
class CohortValidationReport:
    """Immutable aggregate-only profile report."""

    report_version: str
    policy_id: str
    cohort_profile: str
    seed: int
    status: CohortValidationStatus
    comparisons: tuple[CohortComparison, ...]

    def __post_init__(self) -> None:
        if self.report_version != COHORT_VALIDATION_REPORT_VERSION:
            raise ValueError(f"report_version must be {COHORT_VALIDATION_REPORT_VERSION}")
        require_aggregate_safe_token(self.policy_id, "policy_id")
        require_aggregate_safe_token(self.cohort_profile, "cohort_profile")
        _require_nonnegative_integer(self.seed, "seed")
        if not isinstance(self.status, CohortValidationStatus):
            raise TypeError("status must be a CohortValidationStatus")
        if not isinstance(self.comparisons, tuple):
            raise TypeError("comparisons must be a tuple")
        if not all(isinstance(item, CohortComparison) for item in self.comparisons):
            raise TypeError("comparisons must contain CohortComparison values")
        if len({item.name for item in self.comparisons}) != len(self.comparisons):
            raise ValueError("comparisons must have unique registered names")
        canonical = tuple(sorted(self.comparisons, key=_comparison_sort_key))
        if self.status is not _report_status(canonical):
            raise ValueError("status must match comparison statuses")
        object.__setattr__(self, "comparisons", canonical)

    def to_mapping(self) -> dict[str, object]:
        """Return a fresh JSON-compatible mapping with no hidden cohort state."""

        return {
            "report_version": self.report_version,
            "policy_id": self.policy_id,
            "cohort_profile": self.cohort_profile,
            "seed": self.seed,
            "status": self.status.value,
            "comparisons": [item.to_mapping() for item in self.comparisons],
        }

    def __repr__(self) -> str:
        return (
            f"CohortValidationReport(status={self.status.value!r}, "
            f"comparisons={len(self.comparisons)})"
        )


def validate_native_cohort(
    cohort: NativeCohort,
    policy: CohortValidationPolicy,
) -> CohortValidationReport:
    """Placeholder for the aggregate evaluator assembled in Task 2."""

    del cohort, policy
    raise NotImplementedError("native cohort validation assembly is not available")


__all__ = [
    "COHORT_COMPARISON_LAYERS",
    "COHORT_COMPARISON_REASON_CODES",
    "COHORT_VALIDATION_REPORT_VERSION",
    "COMPARISON_LAYERS",
    "COMPARISON_REASON_CODES",
    "GROWTH_TOLERANCE_KEYS",
    "CohortComparison",
    "CohortValidationPolicy",
    "CohortValidationReport",
    "CohortValidationStatus",
    "validate_native_cohort",
]
