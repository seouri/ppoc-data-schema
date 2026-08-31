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

from synthetic.calibration import (
    CalibrationArtifact,
    CalibrationTarget,
    require_aggregate_safe_token,
)
from synthetic.calibration_targets import (
    ETHNICITY_CATEGORY_SLUGS,
    RACE_CATEGORY_SLUGS,
    SEX_CATEGORY_SLUGS,
    TARGET_REGISTRY_VERSION,
    is_registered_target_key,
)
from synthetic.models import AgeRegimeDisorderTrajectory, DisorderKind
from synthetic.native.age_regimes import AgeRegimeConfig
from synthetic.native.clinical_modules import GrowthDisorderModule
from synthetic.native.observations import ObservationFrame, ObservationPolicy
from synthetic.native.resources import ObservedResourceBundle, SyntheticDemographics
from synthetic.references import GrowthReference
from synthetic.schema_contract import EXPECTED_SCHEMA_FINGERPRINT

_REFERENCE_SEX_VALUES = frozenset({"F", "M", "U"})
_MAX_PATIENT_COUNT = 100_000
_WEIGHT_SUM_MINIMUM = 0.99
_WEIGHT_SUM_MAXIMUM = 1.01
_OBSERVED_STRATUM_ID = "outcome_layer=observed"


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


def _select_weighted_category(
    weights: tuple[tuple[str, float], ...],
    draw: float,
) -> str:
    """Select one category from validated weights with a unit-interval draw."""

    checked = _require_weight_pairs(weights, "weights")
    probability = _require_probability(draw, "draw")
    if probability >= 1:
        raise ValueError("draw must be in [0, 1)")
    total = sum(weight for _, weight in checked)
    if total <= 0:
        raise ValueError("weights must have positive total probability")
    threshold = probability * total
    cumulative = 0.0
    for category, weight in checked:
        cumulative += weight
        if threshold < cumulative:
            return category
    return checked[-1][0]


def _project_visible_category(category: str) -> str:
    """Map the released blank aggregate cell into the visible vocabulary."""

    if not isinstance(category, str):
        raise TypeError("category must be a string")
    return "Unknown" if category == "" else category


def _project_race_slots(
    primary_race: str,
    secondary_race: str | None,
) -> tuple[str, ...]:
    """Project approved primary/optional secondary draws into eight race slots."""

    races = [_project_visible_category(primary_race)]
    if secondary_race is not None:
        races.append(_project_visible_category(secondary_race))
    races.extend("Unknown" for _ in range(8 - len(races)))
    return tuple(races)


def _normalize_category_weights(
    weights: tuple[tuple[str, float], ...],
    field_name: str,
) -> tuple[tuple[str, float], ...]:
    total = sum(value for _, value in weights)
    if not _WEIGHT_SUM_MINIMUM <= total <= _WEIGHT_SUM_MAXIMUM:
        raise ValueError(f"{field_name} values must sum within [0.99, 1.01]")
    if total <= 0:
        raise ValueError(f"{field_name} values must have positive total")
    return tuple((category, value / total) for category, value in weights)


def _require_released_proportion(
    target: CalibrationTarget,
) -> float:
    name = target.target_name
    if target.status != "released":
        raise ValueError(f"{name} must be released")
    if target.statistic != "proportion" or target.unit != "proportion":
        raise ValueError(f"{name} must be a registered proportion target")
    if (
        isinstance(target.denominator, bool)
        or not isinstance(target.denominator, int)
        or target.denominator <= 0
    ):
        raise ValueError(f"{name} must have a positive denominator")
    if (
        isinstance(target.support_count, bool)
        or not isinstance(target.support_count, int)
        or not 0 <= target.support_count <= target.denominator
    ):
        raise ValueError(f"{name} must have valid aggregate support")
    if isinstance(target.value, bool) or not isinstance(target.value, Real):
        raise TypeError(f"{name} must have a finite numeric value")
    try:
        value = float(target.value)
    except OverflowError:
        raise ValueError(f"{name} must have a finite numeric value") from None
    if not math.isfinite(value):
        raise ValueError(f"{name} must have a finite numeric value")
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must be in [0, 1]")
    return value


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

    @classmethod
    def from_artifact(
        cls,
        artifact: CalibrationArtifact,
    ) -> CalibrationSamplingProfile:
        """Extract a complete sampling profile from released aggregate cells."""

        if not isinstance(artifact, CalibrationArtifact):
            raise TypeError("artifact must be a CalibrationArtifact")
        if artifact.source_partition != "calibration":
            raise ValueError("source_partition must be calibration")
        if artifact.schema_fingerprint != EXPECTED_SCHEMA_FINGERPRINT:
            raise ValueError("schema_fingerprint does not match the repository contract")

        observed = tuple(
            stratum
            for stratum in artifact.strata
            if stratum.stratum_id == _OBSERVED_STRATUM_ID
            and stratum.dimensions == (("outcome_layer", "observed"),)
        )
        if len(observed) != 1:
            raise ValueError(
                "artifact must contain exactly one outcome_layer=observed stratum"
            )

        for stratum in artifact.strata:
            names = tuple(target.target_name for target in stratum.targets)
            if len(names) != len(set(names)):
                raise ValueError(f"duplicate target in {stratum.stratum_id}")
            for target in stratum.targets:
                if not is_registered_target_key(
                    stratum.stratum_id,
                    target.target_name,
                    target.family,
                    target.statistic,
                    target.unit,
                    target.quantile_level,
                ):
                    raise ValueError(
                        f"{target.target_name} does not belong to "
                        f"{TARGET_REGISTRY_VERSION} registry"
                    )

        targets = {target.target_name: target for target in observed[0].targets}

        def required_value(target_name: str) -> float:
            target = targets.get(target_name)
            if target is None:
                raise ValueError(f"{target_name} is missing from the observed stratum")
            return _require_released_proportion(target)

        sex_weights = tuple(
            (category, required_value(f"sex_{slug}"))
            for category, slug in SEX_CATEGORY_SLUGS.items()
        )
        ethnicity_weights = tuple(
            (category, required_value(f"ethnicity_{slug}"))
            for category, slug in ETHNICITY_CATEGORY_SLUGS.items()
        )
        race_weights = tuple(
            (category, required_value(f"race_{slug}"))
            for category, slug in RACE_CATEGORY_SLUGS.items()
        )

        return cls(
            artifact_id=artifact.artifact_id,
            target_registry_version=TARGET_REGISTRY_VERSION,
            sex_weights=_normalize_category_weights(sex_weights, "sex_weights"),
            ethnicity_weights=_normalize_category_weights(
                ethnicity_weights,
                "ethnicity_weights",
            ),
            race_weights=_normalize_category_weights(race_weights, "race_weights"),
            race_multiselect_probability=required_value("race_multiselect"),
            recorded_healthy_probability=required_value("healthy_flag"),
            recorded_growth_dx_probability=required_value("growth_dx_flag"),
        )

    def to_mapping(self) -> dict[str, object]:
        """Return only released aggregate probabilities and safe identities."""

        def weight_mapping(
            weights: tuple[tuple[str, float], ...],
        ) -> list[dict[str, str | float]]:
            return [
                {"category": category, "probability": probability}
                for category, probability in weights
            ]

        return {
            "artifact_id": self.artifact_id,
            "target_registry_version": self.target_registry_version,
            "sex_weights": weight_mapping(self.sex_weights),
            "ethnicity_weights": weight_mapping(self.ethnicity_weights),
            "race_weights": weight_mapping(self.race_weights),
            "race_multiselect_probability": self.race_multiselect_probability,
            "recorded_healthy_probability": self.recorded_healthy_probability,
            "recorded_growth_dx_probability": self.recorded_growth_dx_probability,
        }

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
