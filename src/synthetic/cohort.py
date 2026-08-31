"""In-memory cohort models for fictional pediatric growth trajectories.

This module's ordinary mappings expose only synthetic demographics and the
existing visible observation/resource contracts. Latent trajectory and
observation truth remain reachable only through evaluator-held typed objects.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from numbers import Real

from synthetic.calibration import require_aggregate_safe_token
from synthetic.models import AgeRegimeDisorderTrajectory, DisorderKind
from synthetic.native.age_regimes import AgeRegimeConfig
from synthetic.native.clinical_modules import GrowthDisorderModule
from synthetic.native.observations import ObservationFrame, ObservationPolicy
from synthetic.native.resources import ObservedResourceBundle, SyntheticDemographics
from synthetic.references import GrowthReference

_REFERENCE_SEX_VALUES = frozenset({"F", "M", "U"})
_MAX_PATIENT_COUNT = 100_000


class CohortGenerationUnavailable(ValueError):
    """Raised when the native cohort cannot be assembled safely."""


def _require_probability(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be a real probability")
    probability = float(value)
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError(f"{field_name} must be finite and in [0, 1]")
    return probability


def _require_nonnegative_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a nonnegative integer")
    return value


def _require_weight_pairs(
    value: object,
    field_name: str,
) -> tuple[tuple[str, float], ...]:
    if not isinstance(value, tuple) or not value:
        raise TypeError(f"{field_name} must be a nonempty tuple")
    weights: list[tuple[str, float]] = []
    for pair in value:
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise TypeError(f"{field_name} must contain category/probability pairs")
        category, probability = pair
        if not isinstance(category, str):
            raise TypeError(f"{field_name} categories must be strings")
        weights.append((category, _require_probability(probability, field_name)))
    categories = tuple(category for category, _ in weights)
    if len(categories) != len(set(categories)):
        raise ValueError(f"{field_name} must not contain duplicate categories")
    return tuple(weights)


@dataclass(frozen=True)
class CohortModuleWeight:
    """One explicit latent-module prior weight."""

    kind: DisorderKind
    probability: float

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DisorderKind):
            raise TypeError("kind must be a DisorderKind")
        object.__setattr__(
            self,
            "probability",
            _require_probability(self.probability, "probability"),
        )


@dataclass(frozen=True)
class CohortConfig:
    """Strict, immutable inputs for one deterministic native cohort."""

    profile: str
    patient_count: int
    seed: int
    ages_days: tuple[int, ...]
    observation_policy: ObservationPolicy
    module_weights: tuple[CohortModuleWeight, ...]
    reference_sex_mapping: tuple[tuple[str, str], ...]
    age_regime_config: AgeRegimeConfig = field(default_factory=AgeRegimeConfig)

    def __post_init__(self) -> None:
        require_aggregate_safe_token(self.profile, "profile")
        patient_count = _require_nonnegative_integer(self.patient_count, "patient_count")
        if not 1 <= patient_count <= _MAX_PATIENT_COUNT:
            raise ValueError("patient_count must be in [1, 100000]")
        _require_nonnegative_integer(self.seed, "seed")

        if not isinstance(self.age_regime_config, AgeRegimeConfig):
            raise TypeError("age_regime_config must be an AgeRegimeConfig")
        if not isinstance(self.ages_days, tuple) or not self.ages_days:
            raise TypeError("ages_days must be a nonempty tuple")
        for age_days in self.ages_days:
            _require_nonnegative_integer(age_days, "ages_days")
            if age_days > self.age_regime_config.maximum_age_days:
                raise ValueError("ages_days must not exceed the configured maximum age")
        if any(left >= right for left, right in zip(self.ages_days, self.ages_days[1:])):
            raise ValueError("ages_days must be strictly increasing")

        if not isinstance(self.observation_policy, ObservationPolicy):
            raise TypeError("observation_policy must be an ObservationPolicy")
        self._validate_module_weights()
        self._validate_reference_sex_mapping()

    def _validate_module_weights(self) -> None:
        if not isinstance(self.module_weights, tuple) or not self.module_weights:
            raise TypeError("module_weights must be a nonempty tuple")
        if not all(isinstance(weight, CohortModuleWeight) for weight in self.module_weights):
            raise TypeError("module_weights must contain CohortModuleWeight values")
        kinds = tuple(weight.kind for weight in self.module_weights)
        if len(kinds) != len(set(kinds)):
            raise ValueError("module_weights must not contain duplicate module kinds")
        if sum(weight.probability for weight in self.module_weights) <= 0:
            raise ValueError("module_weights must have positive total probability")
        if not any(
            weight.kind is DisorderKind.HEALTHY and weight.probability > 0
            for weight in self.module_weights
        ):
            raise ValueError("module_weights must include a positive healthy module")
        if not any(
            weight.kind is not DisorderKind.HEALTHY and weight.probability > 0
            for weight in self.module_weights
        ):
            raise ValueError("module_weights must include a positive nonhealthy module")

    def _validate_reference_sex_mapping(self) -> None:
        value = self.reference_sex_mapping
        if not isinstance(value, tuple):
            raise TypeError("reference_sex_mapping must be a tuple")
        pairs: list[tuple[str, str]] = []
        for pair in value:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise TypeError("reference_sex_mapping must contain source/reference pairs")
            source, reference = pair
            if not isinstance(source, str) or not isinstance(reference, str):
                raise TypeError("reference_sex_mapping values must be strings")
            pairs.append((source, reference))
        sources = tuple(source for source, _ in pairs)
        references = tuple(reference for _, reference in pairs)
        if (
            len(pairs) != len(_REFERENCE_SEX_VALUES)
            or set(sources) != _REFERENCE_SEX_VALUES
            or set(references) != _REFERENCE_SEX_VALUES
            or len(sources) != len(set(sources))
            or len(references) != len(set(references))
        ):
            raise ValueError(
                "reference_sex_mapping must map F, M, and U one-to-one"
            )


@dataclass(frozen=True, repr=False)
class CalibrationSamplingProfile:
    """Aggregate-only cohort weights; artifact extraction is added separately."""

    artifact_id: str
    target_registry_version: str
    sex_weights: tuple[tuple[str, float], ...]
    ethnicity_weights: tuple[tuple[str, float], ...]
    race_weights: tuple[tuple[str, float], ...]
    race_multiselect_probability: float
    recorded_healthy_probability: float
    recorded_growth_dx_probability: float

    def __post_init__(self) -> None:
        require_aggregate_safe_token(self.artifact_id, "artifact_id")
        require_aggregate_safe_token(
            self.target_registry_version,
            "target_registry_version",
        )
        object.__setattr__(
            self,
            "sex_weights",
            _require_weight_pairs(self.sex_weights, "sex_weights"),
        )
        object.__setattr__(
            self,
            "ethnicity_weights",
            _require_weight_pairs(self.ethnicity_weights, "ethnicity_weights"),
        )
        object.__setattr__(
            self,
            "race_weights",
            _require_weight_pairs(self.race_weights, "race_weights"),
        )
        for field_name in (
            "race_multiselect_probability",
            "recorded_healthy_probability",
            "recorded_growth_dx_probability",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_probability(getattr(self, field_name), field_name),
            )

    def __repr__(self) -> str:
        return "CalibrationSamplingProfile(<aggregate-only>)"


def _member_visible_mapping(member: CohortMember) -> dict[str, object]:
    mapping: dict[str, object] = {
        "demographics": member.demographics.to_mapping(),
        "frame": member.frame.to_mapping(),
    }
    if member.bundle is not None:
        mapping["bundle"] = member.bundle.to_mapping()
    return mapping


@dataclass(frozen=True, repr=False)
class CohortMember:
    """One visible fictional patient plus evaluator-held latent objects."""

    demographics: SyntheticDemographics
    trajectory: AgeRegimeDisorderTrajectory
    frame: ObservationFrame
    bundle: ObservedResourceBundle | None

    def __post_init__(self) -> None:
        if not isinstance(self.demographics, SyntheticDemographics):
            raise TypeError("demographics must be SyntheticDemographics")
        if not isinstance(self.trajectory, AgeRegimeDisorderTrajectory):
            raise TypeError("trajectory must be an AgeRegimeDisorderTrajectory")
        if not isinstance(self.frame, ObservationFrame):
            raise TypeError("frame must be an ObservationFrame")
        if self.bundle is not None and not isinstance(self.bundle, ObservedResourceBundle):
            raise TypeError("bundle must be an ObservedResourceBundle or None")
        patient_ids = {
            self.demographics.patient_id,
            self.trajectory.physiology.points[0].patient_id,
            self.frame.patient_id,
        }
        if self.bundle is not None:
            patient_ids.add(self.bundle.patient_id)
        if len(patient_ids) != 1:
            raise ValueError("cohort member objects must identify the same patient")

    def to_mapping(self) -> dict[str, object]:
        """Return only visible demographics, observations, and resources."""

        return _member_visible_mapping(self)

    def __repr__(self) -> str:
        return "CohortMember(<evaluator-only>)"


@dataclass(frozen=True, repr=False)
class NativeCohort:
    """Stable cohort order plus aggregate-only visible counts."""

    profile: str
    seed: int
    members: tuple[CohortMember, ...]
    calibration: CalibrationSamplingProfile

    def __post_init__(self) -> None:
        require_aggregate_safe_token(self.profile, "profile")
        _require_nonnegative_integer(self.seed, "seed")
        if not isinstance(self.members, tuple) or not all(
            isinstance(member, CohortMember) for member in self.members
        ):
            raise TypeError("members must be a tuple of CohortMember values")
        if not isinstance(self.calibration, CalibrationSamplingProfile):
            raise TypeError("calibration must be a CalibrationSamplingProfile")

    def to_mapping(self) -> dict[str, str | int]:
        """Return fixed cohort metadata and visible aggregate counts only."""

        return {
            "profile": self.profile,
            "seed": self.seed,
            "member_count": len(self.members),
            "bundle_count": sum(member.bundle is not None for member in self.members),
            "visible_visit_count": sum(len(member.frame.visits) for member in self.members),
            "visible_event_count": sum(len(member.frame.events) for member in self.members),
        }

    def __repr__(self) -> str:
        return "NativeCohort(<evaluator-only>)"


def generate_native_cohort(
    config: CohortConfig,
    reference: GrowthReference,
    calibration: CalibrationSamplingProfile,
    *,
    modules: Mapping[DisorderKind, GrowthDisorderModule],
    descriptor: Mapping[str, object] | None = None,
) -> NativeCohort:
    """Reserve the reviewed API until trajectory assembly is implemented."""

    del config, reference, calibration, modules, descriptor
    raise CohortGenerationUnavailable("native cohort assembly is not available")


__all__ = [
    "CalibrationSamplingProfile",
    "CohortConfig",
    "CohortGenerationUnavailable",
    "CohortMember",
    "CohortModuleWeight",
    "NativeCohort",
    "generate_native_cohort",
]
