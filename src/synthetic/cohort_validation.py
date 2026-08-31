"""Aggregate-only evaluator for native synthetic-cohort fidelity profiling.

The policy, report, and evaluator consume an in-memory ``NativeCohort``
without crossing into governed inputs or output lifecycles. Latent state is
used only for aggregate module diagnostics; visible observation events remain
a separate recorded layer.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from synthetic.calibration import require_aggregate_safe_token
from synthetic.calibration_targets import (
    ETHNICITY_CATEGORY_SLUGS,
    RACE_CATEGORY_SLUGS,
    SEX_CATEGORY_SLUGS,
)
from synthetic.cohort import CalibrationSamplingProfile, CohortMember, NativeCohort
from synthetic.models import (
    AgeRegimeDisorderTrajectory,
    AgeRegimePoint,
    AgeRegimeTrajectory,
    ClinicalEvent,
    DisorderKind,
    GrowthRegime,
)
from synthetic.native.observations import (
    RECORDED_EVENT_CODES,
    EncounterType,
    MeasurementAvailability,
    MeasurementChannel,
    MeasurementObservation,
    ObservationFrame,
    ObservedVisit,
    RecordedEvent,
    RecordedEventKind,
)

COHORT_VALIDATION_REPORT_VERSION = "cohort-validation-report-v1"

_SYNTHETIC_PATIENT_TOKEN = re.compile(r"^syn-[A-Za-z0-9][A-Za-z0-9._-]*$")
_SYNTHETIC_VISIT_TOKEN = re.compile(r"^syn-[A-Za-z0-9][A-Za-z0-9._:-]*$")
_SOURCE_EVENT_PHASES = MappingProxyType(
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
_SOURCE_EVENT_TYPES = frozenset(_SOURCE_EVENT_PHASES)

GROWTH_TOLERANCE_KEYS = (
    "height_z_score",
    "bmi_z_score",
    "height_velocity_cm_per_year",
    "weight_velocity_kg_per_year",
)
_GROWTH_FIELDS = MappingProxyType(
    {
        "height_z_score": "height_z",
        "bmi_z_score": "bmi_z",
        "height_velocity_cm_per_year": "height_velocity_cm_per_year",
        "weight_velocity_kg_per_year": "weight_velocity_kg_per_year",
    }
)
_GROWTH_METRIC_ORDER = MappingProxyType(
    {name: index for index, name in enumerate(GROWTH_TOLERANCE_KEYS)}
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
_DEMOGRAPHIC_REGISTRIES = MappingProxyType(
    {
        "sex": SEX_CATEGORY_SLUGS,
        "ethnicity": ETHNICITY_CATEGORY_SLUGS,
        "race": RACE_CATEGORY_SLUGS,
    }
)
_DEMOGRAPHIC_VALUES = MappingProxyType(
    {
        "sex": frozenset({*SEX_CATEGORY_SLUGS, *SEX_CATEGORY_SLUGS.values()}),
        "ethnicity": frozenset(
            {
                *ETHNICITY_CATEGORY_SLUGS,
                *ETHNICITY_CATEGORY_SLUGS.values(),
            }
        ),
        "race": frozenset({*RACE_CATEGORY_SLUGS, *RACE_CATEGORY_SLUGS.values()}),
    }
)
_FIXED_COMPARISON_NAMES = frozenset(
    {
        "cohort_size",
        "coverage.cohort_size",
        "observable_phenotype",
        "recorded_recognition",
        "recorded_workup",
        "recorded_diagnosis",
        "coverage.members_with_observation",
        "coverage.members_with_event",
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
_RECORDED_LAYER_NAMES = (
    (RecordedEventKind.RECOGNITION, "recorded_recognition"),
    (RecordedEventKind.WORKUP, "recorded_workup"),
    (RecordedEventKind.DIAGNOSIS, "recorded_diagnosis"),
)


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
    if type(value) not in (int, float):
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
    if name in _FIXED_COMPARISON_NAMES and name.startswith("coverage."):
        return "coverage"
    parts = name.split(".", 2)
    if (
        len(parts) == 3
        and parts[0] == "demographics"
        and parts[1] in _DEMOGRAPHIC_DIMENSIONS
        and parts[2] in _DEMOGRAPHIC_VALUES[parts[1]]
    ):
        return "demographics"
    if len(parts) == 2 and parts[0] == "latent_module" and parts[1] in _DISORDER_ORDER:
        return "latent"
    if _growth_name_parts(name) is not None:
        return "growth"
    return None


def _growth_name_parts(name: str) -> tuple[str, str] | None:
    """Parse a growth comparison from its fixed metric suffix.

    Window tokens are aggregate-safe and may contain dots, so splitting the
    full name on every dot cannot identify the window.  The metric registry is
    closed; matching its suffix from the right keeps the serialized window
    token unchanged and makes the grammar unambiguous.
    """

    if not name.startswith("growth."):
        return None
    body = name.removeprefix("growth.")
    for metric in GROWTH_TOLERANCE_KEYS:
        suffix = f".{metric}_mean"
        if body.endswith(suffix):
            window = body[: -len(suffix)]
            if window:
                return window, metric
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
    if expected is not None and value != expected:
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
        registry = _DEMOGRAPHIC_REGISTRIES[parts[1]]
        category_order: dict[str, int] = {}
        for index, (category, slug) in enumerate(registry.items()):
            category_order[category] = index
            category_order[slug] = index
        return (1, dimension_order[parts[1]], category_order[parts[2]])
    if name.startswith("latent_module."):
        module = name.split(".", 1)[1]
        return (2, _DISORDER_ORDER[module], module)
    if name == "observable_phenotype":
        return (3, 0, name)
    if name.startswith("recorded_"):
        return (4, ("recorded_recognition", "recorded_workup", "recorded_diagnosis").index(name), name)
    if name.startswith("growth."):
        parsed = _growth_name_parts(name)
        if parsed is None:
            raise ValueError("growth comparison name is not registered")
        window, metric = parsed
        return (5, window, _GROWTH_METRIC_ORDER[metric])
    if name.startswith("coverage."):
        coverage_order = {
            "coverage.cohort_size": 0,
            "coverage.members_with_observation": 1,
            "coverage.members_with_event": 2,
        }
        return (6, coverage_order[name])
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
        if not self.comparisons:
            raise ValueError("comparisons must be nonempty")
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
    """Evaluate demographic and event-layer aggregates for one cohort.

    The evaluator intentionally consumes only the already materialized native
    cohort.  It reads latent state only for aggregate module counts and reads
    visible frames only for recorded-event counts; neither layer is treated as
    a target for the other.
    """

    if not isinstance(cohort, NativeCohort):
        raise TypeError("cohort must be a NativeCohort")
    if not isinstance(policy, CohortValidationPolicy):
        raise TypeError("policy must be a CohortValidationPolicy")

    try:
        members = cohort.members
        if not isinstance(members, tuple) or not all(
            isinstance(member, CohortMember) for member in members
        ):
            raise TypeError("cohort members are malformed")
        denominator = len(members)
        calibration = cohort.calibration
        if not isinstance(calibration, CalibrationSamplingProfile):
            raise TypeError("cohort calibration is malformed")
        comparisons: list[CohortComparison] = []
        comparisons.append(
            _status_only_comparison(
                "cohort_size",
                "cohort",
                denominator,
                denominator,
                policy.minimum_cohort_size,
            )
        )
        comparisons.extend(_demographic_comparisons(members, calibration, policy))
        comparisons.extend(_latent_comparisons(members, policy))
        comparisons.append(_observable_comparison(members, policy))
        comparisons.extend(_recorded_comparisons(members, policy))
        comparisons.extend(_growth_comparisons(members, policy))
        comparisons.extend(_coverage_comparisons(members, policy))
        ordered = tuple(comparisons)
        return CohortValidationReport(
            report_version=COHORT_VALIDATION_REPORT_VERSION,
            policy_id=policy.policy_id,
            cohort_profile=cohort.profile,
            seed=cohort.seed,
            status=_report_status(ordered),
            comparisons=ordered,
        )
    except Exception:  # noqa: BLE001 - evaluator failures must be redacted
        return _malformed_cohort_report(cohort, policy)


def _malformed_cohort_report(
    cohort: NativeCohort,
    policy: CohortValidationPolicy,
) -> CohortValidationReport:
    """Return a fixed failure without exposing injected evaluator details."""

    policy_id = _safe_report_token(policy, "policy_id", "invalid-policy")
    profile = _safe_report_token(cohort, "profile", "invalid-cohort")
    seed = _safe_report_seed(cohort)
    comparison = CohortComparison(
        name="cohort_size",
        layer="cohort",
        status=CohortValidationStatus.FAIL,
        observed_value=0,
        target_value=None,
        difference=None,
        tolerance=None,
        support=0,
        denominator=1,
        reason_code="MALFORMED_COHORT",
    )
    coverage_comparison = CohortComparison(
        name="coverage.cohort_size",
        layer="coverage",
        status=CohortValidationStatus.FAIL,
        observed_value=0.0,
        target_value=None,
        difference=None,
        tolerance=None,
        support=0,
        denominator=1,
        reason_code="MALFORMED_COHORT",
    )
    return CohortValidationReport(
        report_version=COHORT_VALIDATION_REPORT_VERSION,
        policy_id=policy_id,
        cohort_profile=profile,
        seed=seed,
        status=CohortValidationStatus.FAIL,
        comparisons=(comparison, coverage_comparison),
    )


def _safe_report_token(value: object, attribute: str, fallback: str) -> str:
    try:
        candidate = getattr(value, attribute)
        require_aggregate_safe_token(candidate, attribute)
    except Exception:  # noqa: BLE001 - metadata failures must be redacted
        return fallback
    return candidate


def _safe_report_seed(cohort: NativeCohort) -> int:
    try:
        seed = cohort.seed
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            return 0
        return seed
    except Exception:  # noqa: BLE001 - metadata failures must be redacted
        return 0


def _status_only_comparison(
    name: str,
    layer: str,
    observed_value: float,
    support: int,
    minimum_cohort_size: int,
) -> CohortComparison:
    denominator = observed_value if name in {"cohort_size", "coverage.cohort_size"} else None
    if name not in {"cohort_size", "coverage.cohort_size"}:
        raise ValueError("status-only cohort comparison requires a proportion denominator")
    if not isinstance(denominator, int):
        raise TypeError("status-only cohort size must be an integer")
    if denominator < minimum_cohort_size:
        return CohortComparison(
            name=name,
            layer=layer,
            status=CohortValidationStatus.UNEVALUABLE,
            observed_value=None,
            target_value=None,
            difference=None,
            tolerance=None,
            support=support,
            denominator=denominator,
            reason_code="COHORT_TOO_SMALL",
        )
    return CohortComparison(
        name=name,
        layer=layer,
        status=CohortValidationStatus.PASS,
        observed_value=observed_value,
        target_value=None,
        difference=None,
        tolerance=None,
        support=support,
        denominator=denominator,
        reason_code="ABOVE_MINIMUM_SUPPORT",
    )


def _unevaluable_comparison(
    name: str,
    layer: str,
    support: int,
    denominator: int,
    reason_code: str,
) -> CohortComparison:
    return CohortComparison(
        name=name,
        layer=layer,
        status=CohortValidationStatus.UNEVALUABLE,
        observed_value=None,
        target_value=None,
        difference=None,
        tolerance=None,
        support=support,
        denominator=denominator,
        reason_code=reason_code,
    )


def _targeted_comparison(
    name: str,
    layer: str,
    support: int,
    denominator: int,
    target: float,
    policy: CohortValidationPolicy,
) -> CohortComparison:
    if denominator < policy.minimum_cohort_size:
        return _unevaluable_comparison(
            name, layer, support, denominator, "COHORT_TOO_SMALL"
        )
    if support < policy.minimum_cell_support:
        return _unevaluable_comparison(
            name, layer, support, denominator, "INSUFFICIENT_SUPPORT"
        )
    observed = support / denominator
    difference = abs(observed - target)
    status = (
        CohortValidationStatus.PASS
        if difference <= policy.proportion_tolerance
        else CohortValidationStatus.FAIL
    )
    reason = (
        "WITHIN_TOLERANCE"
        if status is CohortValidationStatus.PASS
        else "OUTSIDE_TOLERANCE"
    )
    return CohortComparison(
        name=name,
        layer=layer,
        status=status,
        observed_value=observed,
        target_value=target,
        difference=difference,
        tolerance=policy.proportion_tolerance,
        support=support,
        denominator=denominator,
        reason_code=reason,
    )


def _status_rate_comparison(
    name: str,
    layer: str,
    support: int,
    denominator: int,
    minimum_support: int,
    minimum_cohort_size: int,
) -> CohortComparison:
    if denominator < minimum_cohort_size:
        return _unevaluable_comparison(
            name, layer, support, denominator, "COHORT_TOO_SMALL"
        )
    if support == 0:
        status = CohortValidationStatus.PASS
        reason = "NO_EVIDENCE"
    elif support < minimum_support:
        return _unevaluable_comparison(
            name, layer, support, denominator, "INSUFFICIENT_SUPPORT"
        )
    else:
        status = CohortValidationStatus.PASS
        reason = "ABOVE_MINIMUM_SUPPORT"
    return CohortComparison(
        name=name,
        layer=layer,
        status=status,
        observed_value=support / denominator,
        target_value=None,
        difference=None,
        tolerance=None,
        support=support,
        denominator=denominator,
        reason_code=reason,
    )


def _failed_status_comparison(
    name: str,
    layer: str,
    support: int,
    denominator: int,
    reason_code: str,
) -> CohortComparison:
    """Return a redacted status-only failure with safe aggregate counts."""

    denominator = max(1, denominator)
    support = min(max(0, support), denominator)
    return CohortComparison(
        name=name,
        layer=layer,
        status=CohortValidationStatus.FAIL,
        observed_value=0.0,
        target_value=None,
        difference=None,
        tolerance=None,
        support=support,
        denominator=denominator,
        reason_code=reason_code,
    )


def _is_synthetic_patient_id(value: object) -> bool:
    return isinstance(value, str) and _SYNTHETIC_PATIENT_TOKEN.fullmatch(value) is not None


def _is_synthetic_visit_id(value: object) -> bool:
    return isinstance(value, str) and _SYNTHETIC_VISIT_TOKEN.fullmatch(value) is not None


def _member_patient_id(member: object) -> str | None:
    try:
        patient_id = member.demographics.patient_id
    except Exception:  # noqa: BLE001 - evaluator failures must be redacted
        return None
    if not _is_synthetic_patient_id(patient_id):
        return None
    return patient_id


def _trajectory_events(
    member: object,
    expected_patient_id: str,
) -> tuple[tuple[ClinicalEvent, ...], str | None]:
    """Validate private source events before they contribute to a layer rate."""

    try:
        trajectory = member.trajectory
        if not isinstance(trajectory, AgeRegimeDisorderTrajectory):
            return (), "STRUCTURAL_INVALID"
        events = trajectory.events
        if not isinstance(events, tuple) or not all(
            isinstance(event, ClinicalEvent) for event in events
        ):
            return (), "STRUCTURAL_INVALID"
        previous_age = -1
        previous_phase = -1
        for event in events:
            if (
                not _is_synthetic_patient_id(event.patient_id)
                or event.patient_id != expected_patient_id
                or isinstance(event.age_days, bool)
                or not isinstance(event.age_days, int)
                or event.age_days < 0
                or event.age_days < previous_age
                or not isinstance(event.event_type, str)
                or event.event_type not in _SOURCE_EVENT_TYPES
                or event.code is not None
                or not isinstance(event.hidden, bool)
                or (event.event_type == "latent_onset" and not event.hidden)
            ):
                return (), "STRUCTURAL_INVALID"
            phase = _SOURCE_EVENT_PHASES[event.event_type]
            if phase <= previous_phase:
                return (), "STRUCTURAL_INVALID"
            previous_age = event.age_days
            previous_phase = phase
        return events, None
    except Exception:  # noqa: BLE001 - evaluator failures must be redacted
        return (), "MALFORMED_COHORT"


def _measurements_are_valid(measurements: object) -> bool:
    try:
        if not isinstance(measurements, tuple) or not measurements:
            return False
        channels: set[MeasurementChannel] = set()
        for measurement in measurements:
            if not isinstance(measurement, MeasurementObservation):
                return False
            if not isinstance(measurement.channel, MeasurementChannel):
                return False
            if measurement.channel in channels:
                return False
            channels.add(measurement.channel)
            if not isinstance(measurement.availability, MeasurementAvailability):
                return False
            value = measurement.recorded_value
            if measurement.availability is MeasurementAvailability.OBSERVED:
                if (
                    type(value) not in (int, float)
                    or not math.isfinite(float(value))
                    or value <= 0
                ):
                    return False
            elif value is not None:
                return False
        return True
    except Exception:  # noqa: BLE001 - evaluator failures must be redacted
        return False


def _frame_records(
    member: object,
    expected_patient_id: str,
) -> tuple[tuple[ObservedVisit, ...], tuple[RecordedEvent, ...], str | None]:
    """Validate visible visits/events before counting observation coverage."""

    try:
        frame = member.frame
        if not isinstance(frame, ObservationFrame):
            return (), (), "STRUCTURAL_INVALID"
        if frame.patient_id != expected_patient_id or not _is_synthetic_patient_id(
            frame.patient_id
        ):
            return (), (), "STRUCTURAL_INVALID"
        if not isinstance(frame.policy_version, str):
            return (), (), "STRUCTURAL_INVALID"
        visits = frame.visits
        events = frame.events
        if not isinstance(visits, tuple) or not all(
            isinstance(visit, ObservedVisit) for visit in visits
        ):
            return (), (), "STRUCTURAL_INVALID"
        if not isinstance(events, tuple) or not all(
            isinstance(event, RecordedEvent) for event in events
        ):
            return (), (), "STRUCTURAL_INVALID"

        previous_age = -1
        visit_ids: set[str] = set()
        for visit in visits:
            if (
                not _is_synthetic_patient_id(visit.patient_id)
                or visit.patient_id != expected_patient_id
                or not _is_synthetic_visit_id(visit.visit_id)
                or visit.visit_id in visit_ids
                or isinstance(visit.age_days, bool)
                or not isinstance(visit.age_days, int)
                or visit.age_days < 0
                or visit.age_days <= previous_age
                or not isinstance(visit.encounter_type, EncounterType)
                or not _measurements_are_valid(visit.measurements)
            ):
                return (), (), "STRUCTURAL_INVALID"
            visit_ids.add(visit.visit_id)
            previous_age = visit.age_days

        previous_age = -1
        for event in events:
            if not isinstance(event.event_kind, RecordedEventKind):
                return (), (), "STRUCTURAL_INVALID"
            expected_code = RECORDED_EVENT_CODES[event.event_kind]
            if (
                not _is_synthetic_patient_id(event.patient_id)
                or event.patient_id != expected_patient_id
                or isinstance(event.age_days, bool)
                or not isinstance(event.age_days, int)
                or event.age_days < 0
                or event.age_days < previous_age
                or event.code != expected_code
                or (
                    event.opportunity_index is not None
                    and (
                        isinstance(event.opportunity_index, bool)
                        or not isinstance(event.opportunity_index, int)
                        or event.opportunity_index < 0
                    )
                )
            ):
                return (), (), "STRUCTURAL_INVALID"
            previous_age = event.age_days
        return visits, events, None
    except Exception:  # noqa: BLE001 - evaluator failures must be redacted
        return (), (), "MALFORMED_COHORT"


def _trajectory_points(
    member: object,
) -> tuple[tuple[AgeRegimePoint, ...], str | None]:
    """Return points plus a fixed reason when evaluator structure is invalid."""

    try:
        patient_id = member.demographics.patient_id
        trajectory = member.trajectory
        if not isinstance(trajectory, AgeRegimeDisorderTrajectory):
            return (), "STRUCTURAL_INVALID"
        physiology = trajectory.physiology
        if not isinstance(physiology, AgeRegimeTrajectory):
            return (), "STRUCTURAL_INVALID"
        points = physiology.points
        if not isinstance(points, tuple) or not points:
            return (), "STRUCTURAL_INVALID"
        if not _is_synthetic_patient_id(patient_id):
            return (), "STRUCTURAL_INVALID"
        previous_age = -1
        for point in points:
            if not isinstance(point, AgeRegimePoint):
                return (), "STRUCTURAL_INVALID"
            if point.patient_id != patient_id:
                return (), "STRUCTURAL_INVALID"
            if (
                isinstance(point.age_days, bool)
                or not isinstance(point.age_days, int)
                or point.age_days < 0
                or point.age_days <= previous_age
            ):
                return (), "STRUCTURAL_INVALID"
            if not isinstance(point.regime, GrowthRegime):
                return (), "STRUCTURAL_INVALID"
            previous_age = point.age_days
        return points, None
    except Exception:  # noqa: BLE001 - evaluator failures must be redacted
        return (), "MALFORMED_COHORT"


def _point_numeric_values_are_valid(point: AgeRegimePoint) -> bool:
    """Check typed finite/physical point values without exposing point data."""

    try:
        if point.regime is GrowthRegime.INFANCY and point.length_cm is None:
            return False
        if point.regime is GrowthRegime.TRANSITION and (
            point.length_cm is None or point.height_cm is None
        ):
            return False
        if point.regime in (
            GrowthRegime.CHILDHOOD,
            GrowthRegime.PUBERTY,
            GrowthRegime.ADOLESCENCE,
        ) and (point.height_cm is None or point.bmi is None):
            return False
        if (
            point.regime is not GrowthRegime.INFANCY
            and point.regime is not GrowthRegime.TRANSITION
            and point.length_cm is not None
        ):
            return False
        for field_name in (
            "length_cm",
            "height_cm",
            "weight_kg",
            "bmi",
            "head_circumference_cm",
        ):
            value = getattr(point, field_name)
            if value is not None and (
                type(value) not in (int, float)
                or not math.isfinite(float(value))
                or value <= 0
            ):
                return False
        if point.height_cm is not None and point.bmi is not None:
            try:
                expected_weight = point.bmi * (point.height_cm / 100.0) ** 2
            except OverflowError:
                return False
            if not math.isfinite(expected_weight) or not math.isclose(
                point.weight_kg, expected_weight, rel_tol=1e-9, abs_tol=1e-9
            ):
                return False
        for field_name in (
            "length_z",
            "height_z",
            "weight_z",
            "bmi_z",
            "height_velocity_cm_per_year",
            "weight_velocity_kg_per_year",
        ):
            value = getattr(point, field_name)
            if value is not None and (
                type(value) not in (int, float) or not math.isfinite(float(value))
            ):
                return False
    except Exception:  # noqa: BLE001 - malformed evaluator values are redacted
        return False
    return True


def _growth_comparison(
    name: str,
    metric: str,
    values: list[float],
    denominator: int,
    policy: CohortValidationPolicy,
    invalid_reason: str | None,
) -> CohortComparison:
    if invalid_reason is not None:
        return _failed_status_comparison(
            name,
            "growth",
            len(values),
            denominator,
            invalid_reason,
        )
    if len(values) < policy.minimum_cell_support:
        return _unevaluable_comparison(
            name,
            "growth",
            len(values),
            denominator,
            "INSUFFICIENT_SUPPORT",
        )
    try:
        mean = math.fsum(values) / len(values)
        difference = abs(mean)
    except (OverflowError, ValueError):
        return _failed_status_comparison(
            name,
            "growth",
            len(values),
            denominator,
            "INVALID_VALUE",
        )
    if not math.isfinite(mean) or not math.isfinite(difference):
        return _failed_status_comparison(
            name,
            "growth",
            len(values),
            denominator,
            "INVALID_VALUE",
        )
    tolerance = policy.growth_tolerances[metric]
    status = (
        CohortValidationStatus.PASS
        if difference <= tolerance
        else CohortValidationStatus.FAIL
    )
    return CohortComparison(
        name=name,
        layer="growth",
        status=status,
        observed_value=mean,
        target_value=0.0,
        difference=difference,
        tolerance=tolerance,
        support=len(values),
        denominator=denominator,
        reason_code="WITHIN_TOLERANCE" if status is CohortValidationStatus.PASS else "OUTSIDE_TOLERANCE",
    )


def _growth_comparisons(
    members: tuple[object, ...],
    policy: CohortValidationPolicy,
) -> tuple[CohortComparison, ...]:
    comparisons: list[CohortComparison] = []
    for window_name, lower_age, upper_age in policy.required_age_windows:
        for metric in GROWTH_TOLERANCE_KEYS:
            values: list[float] = []
            candidate_count = 0
            invalid_reason: str | None = None
            field_name = _GROWTH_FIELDS[metric]
            for member in members:
                points, structural_reason = _trajectory_points(member)
                if structural_reason is not None:
                    invalid_reason = structural_reason
                    continue
                for point in points:
                    if not lower_age <= point.age_days < upper_age:
                        continue
                    candidate_count += 1
                    if not _point_numeric_values_are_valid(point):
                        invalid_reason = "INVALID_VALUE"
                        continue
                    try:
                        value = getattr(point, field_name)
                    except Exception:  # noqa: BLE001 - malformed values are redacted
                        invalid_reason = "INVALID_VALUE"
                        continue
                    if value is None:
                        continue
                    if type(value) not in (int, float) or not math.isfinite(float(value)):
                        invalid_reason = "INVALID_VALUE"
                        continue
                    values.append(float(value))
            comparisons.append(
                _growth_comparison(
                    f"growth.{window_name}.{metric}_mean",
                    metric,
                    values,
                    candidate_count,
                    policy,
                    invalid_reason,
                )
            )
    return tuple(comparisons)


def _coverage_comparisons(
    members: tuple[object, ...],
    policy: CohortValidationPolicy,
) -> tuple[CohortComparison, ...]:
    denominator = len(members)
    members_with_observation = 0
    members_with_event = 0
    seen_patient_ids: set[str] = set()
    structural_reason: str | None = None
    for member in members:
        try:
            patient_id = _member_patient_id(member)
            if patient_id is None or patient_id in seen_patient_ids:
                structural_reason = "STRUCTURAL_INVALID"
                continue
            seen_patient_ids.add(patient_id)

            _points, point_reason = _trajectory_points(member)
            if point_reason is not None:
                structural_reason = point_reason
                continue

            _source_events, event_reason = _trajectory_events(member, patient_id)
            if event_reason is not None:
                structural_reason = event_reason
                continue

            visits, events, frame_reason = _frame_records(member, patient_id)
            if frame_reason is not None:
                structural_reason = frame_reason
                continue
            if visits:
                members_with_observation += 1
            if events:
                members_with_event += 1
        except Exception:  # noqa: BLE001 - malformed evaluator values are redacted
            structural_reason = "MALFORMED_COHORT"

    if structural_reason is not None:
        return tuple(
            _failed_status_comparison(
                name,
                "coverage",
                support,
                denominator,
                structural_reason,
            )
            for name, support in (
                ("coverage.cohort_size", denominator),
                ("coverage.members_with_observation", members_with_observation),
                ("coverage.members_with_event", members_with_event),
            )
        )

    return (
        _status_only_comparison(
            "coverage.cohort_size",
            "coverage",
            denominator,
            denominator,
            policy.minimum_cohort_size,
        ),
        _status_rate_comparison(
            "coverage.members_with_observation",
            "coverage",
            members_with_observation,
            denominator,
            policy.minimum_event_support,
            policy.minimum_cohort_size,
        ),
        _status_rate_comparison(
            "coverage.members_with_event",
            "coverage",
            members_with_event,
            denominator,
            policy.minimum_event_support,
            policy.minimum_cohort_size,
        ),
    )


def _demographic_comparisons(
    members: tuple[object, ...],
    calibration: object,
    policy: CohortValidationPolicy,
) -> tuple[CohortComparison, ...]:
    registries = (
        ("sex", SEX_CATEGORY_SLUGS, "sex_weights", "sex"),
        ("ethnicity", ETHNICITY_CATEGORY_SLUGS, "ethnicity_weights", "ethnicity"),
        ("race", RACE_CATEGORY_SLUGS, "race_weights", "race"),
    )
    comparisons: list[CohortComparison] = []
    for dimension, registry, weights_field, attribute in registries:
        weights = getattr(calibration, weights_field)
        projected_targets: dict[str, float] = {}
        for category, probability in weights:
            visible_category = "Unknown" if category == "" else category
            slug = registry[visible_category]
            projected_targets[slug] = projected_targets.get(slug, 0.0) + probability
        total = math.fsum(projected_targets.values())
        projected_targets = {
            slug: value / total for slug, value in projected_targets.items()
        }
        counts = Counter()
        invalid_reason: str | None = None
        for member in members:
            try:
                demographics = member.demographics
                value = (
                    demographics.races[0]
                    if attribute == "race"
                    else getattr(demographics, attribute)
                )
                visible_category = "Unknown" if value == "" else value
                counts[registry[visible_category]] += 1
            except Exception:  # noqa: BLE001 - evaluator failures must be redacted
                invalid_reason = "MALFORMED_COHORT"
        for category, slug in registry.items():
            if category == "":
                continue
            name = f"demographics.{dimension}.{slug}"
            if invalid_reason is not None:
                comparisons.append(
                    _failed_status_comparison(
                        name,
                        "demographics",
                        counts[slug],
                        len(members),
                        invalid_reason,
                    )
                )
            else:
                comparisons.append(
                    _targeted_comparison(
                        name,
                        "demographics",
                        counts[slug],
                        len(members),
                        projected_targets[slug],
                        policy,
                    )
                )
    return tuple(comparisons)


def _latent_comparisons(
    members: tuple[object, ...],
    policy: CohortValidationPolicy,
) -> tuple[CohortComparison, ...]:
    counts = Counter()
    invalid_reason: str | None = None
    for member in members:
        try:
            kind = member.trajectory.disorder.kind
            if not isinstance(kind, DisorderKind):
                invalid_reason = "STRUCTURAL_INVALID"
            else:
                counts[kind] += 1
        except Exception:  # noqa: BLE001 - evaluator failures must be redacted
            invalid_reason = "MALFORMED_COHORT"
    denominator = len(members)
    if invalid_reason is not None:
        return tuple(
            _failed_status_comparison(
                f"latent_module.{kind.value}",
                "latent",
                counts[kind],
                denominator,
                invalid_reason,
            )
            for kind in DisorderKind
        )
    return tuple(
        _status_rate_comparison(
            f"latent_module.{kind.value}",
            "latent",
            counts[kind],
            denominator,
            policy.minimum_event_support,
            policy.minimum_cohort_size,
        )
        for kind in DisorderKind
    )


def _observable_comparison(
    members: tuple[object, ...],
    policy: CohortValidationPolicy,
) -> CohortComparison:
    support = 0
    invalid_reason: str | None = None
    for member in members:
        try:
            patient_id = _member_patient_id(member)
            if patient_id is None:
                invalid_reason = "STRUCTURAL_INVALID"
                continue
            events, event_reason = _trajectory_events(member, patient_id)
            if event_reason is not None:
                invalid_reason = event_reason
                continue
            if any(event.event_type == "observable_phenotype" for event in events):
                support += 1
        except Exception:  # noqa: BLE001 - evaluator failures must be redacted
            invalid_reason = "MALFORMED_COHORT"
    if invalid_reason is not None:
        return _failed_status_comparison(
            "observable_phenotype",
            "observable",
            support,
            len(members),
            invalid_reason,
        )
    return _status_rate_comparison(
        "observable_phenotype",
        "observable",
        support,
        len(members),
        policy.minimum_event_support,
        policy.minimum_cohort_size,
    )


def _recorded_comparisons(
    members: tuple[object, ...],
    policy: CohortValidationPolicy,
) -> tuple[CohortComparison, ...]:
    denominator = len(members)
    comparisons: list[CohortComparison] = []
    for event_kind, name in _RECORDED_LAYER_NAMES:
        support = 0
        invalid_reason: str | None = None
        for member in members:
            try:
                patient_id = _member_patient_id(member)
                if patient_id is None:
                    invalid_reason = "STRUCTURAL_INVALID"
                    continue
                _visits, events, frame_reason = _frame_records(member, patient_id)
                if frame_reason is not None:
                    invalid_reason = frame_reason
                    continue
                if any(event.event_kind is event_kind for event in events):
                    support += 1
            except Exception:  # noqa: BLE001 - evaluator failures must be redacted
                invalid_reason = "MALFORMED_COHORT"
        if invalid_reason is not None:
            comparisons.append(
                _failed_status_comparison(
                    name,
                    "recorded",
                    support,
                    denominator,
                    invalid_reason,
                )
            )
        else:
            comparisons.append(
                _status_rate_comparison(
                    name,
                    "recorded",
                    support,
                    denominator,
                    policy.minimum_event_support,
                    policy.minimum_cohort_size,
                )
            )
    return tuple(comparisons)


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
