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
from types import MappingProxyType

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
from synthetic.models import AgeRegimeDisorderTrajectory, DisorderKind, PatientState
from synthetic.native.age_regime_disorder import AgeRegimeDisorderKernel
from synthetic.native.age_regimes import AgeRegimeConfig, AgeRegimeTrajectoryKernel
from synthetic.native.ancillary_contract import (
    GHD_ANCILLARY_RESOURCE_NAMES,
    ghd_ancillary_rows_are_valid,
)
from synthetic.native.clinical_modules import GrowthDisorderModule
from synthetic.native.observations import (
    CensoringMode,
    EncounterType,
    MeasurementAvailability,
    MeasurementChannel,
    MeasurementObservation,
    ObservationFrame,
    ObservationPolicy,
    ObservationTruth,
    ObservationValidationStatus,
    ObservationWindow,
    ObservedVisit,
    RecordedEvent,
    RecordedEventKind,
    generate_observation_frame,
    validate_observation_frame,
)
from synthetic.native.resources import (
    BASE_RESOURCE_NAMES,
    ClinicalDescendant,
    ObservedResourceBundle,
    ResourceRow,
    ResourceShape,
    ResourceSpec,
    ResourceValidationStatus,
    SyntheticDemographics,
    project_observed_resources,
    validate_observed_resources,
)
from synthetic.native.trajectories import validate_growth_disorder_module
from synthetic.randomness import NamedRandomStreams, synthetic_id
from synthetic.references import GrowthReference
from synthetic.schema_contract import EXPECTED_SCHEMA_FINGERPRINT

_REFERENCE_SEX_VALUES = frozenset({"F", "M", "U"})
_MAX_PATIENT_COUNT = 100_000
_WEIGHT_SUM_MINIMUM = 0.99
_WEIGHT_SUM_MAXIMUM = 1.01
_OBSERVED_STRATUM_ID = "outcome_layer=observed"
_SEX_CATEGORIES = tuple(SEX_CATEGORY_SLUGS)
_ETHNICITY_CATEGORIES = tuple(ETHNICITY_CATEGORY_SLUGS)
_RACE_CATEGORIES = tuple(RACE_CATEGORY_SLUGS)
_REQUIRED_PATIENT_RESOURCE_FIELDS = frozenset(
    {
        "patient_id",
        "sex",
        "ethnicity",
        *(f"race_{index}" for index in range(1, 9)),
    }
)
_REQUIRED_VISIT_RESOURCE_FIELDS = frozenset(
    {
        "patient_id",
        "visit_id",
        "age_in_days",
        "encounter_type",
        "orig_enc_source_Epic_yn",
        "weight_oz",
        "height_in",
        "head_circ_cm",
        "BMI",
    }
)


class CohortGenerationUnavailable(ValueError):
    """Raised when the native cohort cannot be assembled safely."""


def _resource_projection_contract(
    descriptor: Mapping[str, object],
) -> tuple[ResourceShape, dict[str, object]]:
    """Extract one exact-order shape and a plain in-memory projection mapping."""

    if not isinstance(descriptor, Mapping):
        raise TypeError("descriptor must be a mapping")
    resources = descriptor.get("resources")
    if not isinstance(resources, list):
        raise TypeError("descriptor resources must be a list")
    base_order: list[str] = []
    for resource in resources:
        if not isinstance(resource, Mapping):
            raise TypeError("descriptor resources must contain mappings")
        name = resource.get("name")
        if name in BASE_RESOURCE_NAMES:
            base_order.append(name)
    if tuple(base_order) != BASE_RESOURCE_NAMES:
        raise ValueError("base descriptor resources must use the fixed order")

    shape = ResourceShape.from_descriptor(descriptor)
    required_fields = (
        ("patients", _REQUIRED_PATIENT_RESOURCE_FIELDS),
        ("visits", _REQUIRED_VISIT_RESOURCE_FIELDS),
    )
    for resource_name, required in required_fields:
        if required.difference(shape.field_names(resource_name)):
            raise ValueError(
                f"{resource_name} descriptor lacks required projection fields"
            )
    projection_descriptor: dict[str, object] = {
        "resources": [
            {
                "name": resource.name,
                "schema": {
                    "fields": [
                        {"name": field_name} for field_name in resource.field_names
                    ]
                },
            }
            for resource in shape.resources
        ]
    }
    return shape, projection_descriptor


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


def _eligible_module_weights(
    positive_weights: tuple[tuple[DisorderKind, float], ...],
    modules: dict[DisorderKind, GrowthDisorderModule],
    reference_sex: str,
) -> tuple[tuple[DisorderKind, float], ...]:
    """Retain module weights compatible with one sampled reference sex."""

    eligible: list[tuple[DisorderKind, float]] = []
    missing = object()
    for kind, probability in positive_weights:
        required_reference_sex = getattr(modules[kind], "required_reference_sex", missing)
        if required_reference_sex is missing:
            eligible.append((kind, probability))
            continue
        if not isinstance(required_reference_sex, str) or not required_reference_sex.strip():
            raise TypeError("module required_reference_sex must be a nonempty string")
        if required_reference_sex == reference_sex:
            eligible.append((kind, probability))
    return tuple(eligible)


def _project_visible_category(category: str) -> str:
    """Map the released blank aggregate cell into the visible vocabulary."""

    if not isinstance(category, str):
        raise TypeError("category must be a string")
    return "Unknown" if category == "" else category


def _project_race_slots(
    primary_race: str,
    secondary_race: str | None,
) -> tuple[str, ...]:
    """Project approved primary/optional secondary draws into eight race slots.

    Empty trailing slots are represented by the schema's empty-string missing
    sentinel.  ``Unknown`` remains reserved for a sampled or otherwise
    explicitly unavailable race value, rather than for a slot that was never
    selected.
    """

    races = [_project_visible_category(primary_race)]
    if secondary_race is not None:
        races.append(_project_visible_category(secondary_race))
    races.extend("" for _ in range(8 - len(races)))
    return tuple(races)


def _validate_category_weights(
    weights: tuple[tuple[str, float], ...],
    field_name: str,
) -> tuple[tuple[str, float], ...]:
    total = math.fsum(value for _, value in weights)
    below_minimum = total < _WEIGHT_SUM_MINIMUM and not math.isclose(
        total,
        _WEIGHT_SUM_MINIMUM,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    above_maximum = total > _WEIGHT_SUM_MAXIMUM and not math.isclose(
        total,
        _WEIGHT_SUM_MAXIMUM,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    if below_minimum or above_maximum:
        raise ValueError(f"{field_name} values must sum within [0.99, 1.01]")
    if total <= 0:
        raise ValueError(f"{field_name} values must have positive total")
    return weights


def _require_canonical_category_weights(
    value: object,
    field_name: str,
    expected_categories: tuple[str, ...],
) -> tuple[tuple[str, float], ...]:
    weights = _require_weight_pairs(value, field_name)
    if tuple(category for category, _ in weights) != expected_categories:
        raise ValueError(f"{field_name} must use the fixed registry category order")
    return _validate_category_weights(weights, field_name)


def _require_released_proportion(
    target: CalibrationTarget,
    minimum_cell_count: int,
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
        or not minimum_cell_count <= target.support_count <= target.denominator
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
    expected = round(target.support_count / target.denominator, target.rounding_decimals)
    if value != expected:
        raise ValueError(
            f"{name} value must match support_count / denominator at declared precision"
        )
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
    module_weights_by_reference_sex: tuple[
        tuple[str, tuple[CohortModuleWeight, ...]], ...
    ] = field(default_factory=tuple)

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
        self._validate_module_weights_by_reference_sex()

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

    def _validate_module_weights_by_reference_sex(self) -> None:
        rows = self.module_weights_by_reference_sex
        if not isinstance(rows, tuple):
            raise TypeError("module_weights_by_reference_sex must be a tuple")
        base_kinds = tuple(weight.kind for weight in self.module_weights)
        seen_reference_sexes: set[str] = set()
        for entry in rows:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise TypeError(
                    "module_weights_by_reference_sex must contain reference-sex rows"
                )
            reference_sex, weights = entry
            if not isinstance(reference_sex, str):
                raise TypeError("module weight reference sex must be a string")
            if reference_sex not in _REFERENCE_SEX_VALUES:
                raise ValueError("module weight reference sex must be F, M, or U")
            if reference_sex in seen_reference_sexes:
                raise ValueError("module weight reference sexes must be unique")
            seen_reference_sexes.add(reference_sex)
            if not isinstance(weights, tuple) or not weights:
                raise TypeError("conditional module weights must be a nonempty tuple")
            if not all(isinstance(weight, CohortModuleWeight) for weight in weights):
                raise TypeError(
                    "conditional module weights must contain CohortModuleWeight values"
                )
            kinds = tuple(weight.kind for weight in weights)
            if kinds != base_kinds:
                raise ValueError(
                    "conditional module weights must match the flat module registry"
                )
            if sum(weight.probability for weight in weights) <= 0:
                raise ValueError("conditional module weights must have positive total probability")
            if not any(
                weight.kind is DisorderKind.HEALTHY and weight.probability > 0
                for weight in weights
            ):
                raise ValueError(
                    "conditional module weights must include a positive healthy module"
                )
            if not any(
                weight.kind is not DisorderKind.HEALTHY and weight.probability > 0
                for weight in weights
            ):
                raise ValueError(
                    "conditional module weights must include a positive nonhealthy module"
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
        if self.target_registry_version != TARGET_REGISTRY_VERSION:
            raise ValueError(
                "target_registry_version must match the fixed target registry"
            )
        object.__setattr__(
            self,
            "sex_weights",
            _require_canonical_category_weights(
                self.sex_weights,
                "sex_weights",
                _SEX_CATEGORIES,
            ),
        )
        object.__setattr__(
            self,
            "ethnicity_weights",
            _require_canonical_category_weights(
                self.ethnicity_weights,
                "ethnicity_weights",
                _ETHNICITY_CATEGORIES,
            ),
        )
        object.__setattr__(
            self,
            "race_weights",
            _require_canonical_category_weights(
                self.race_weights,
                "race_weights",
                _RACE_CATEGORIES,
            ),
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

        if type(artifact) is not CalibrationArtifact:
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
                raise ValueError("artifact contains duplicate target names")
            for target in stratum.targets:
                if not is_registered_target_key(
                    stratum.stratum_id,
                    target.target_name,
                    target.family,
                    target.statistic,
                    target.unit,
                    target.quantile_level,
                ):
                    raise ValueError("artifact contains a target outside the fixed registry")

        targets = {target.target_name: target for target in observed[0].targets}

        def required_target(target_name: str) -> CalibrationTarget:
            target = targets.get(target_name)
            if target is None:
                raise ValueError(f"{target_name} is missing from the observed stratum")
            return target

        required_names = (
            *(f"sex_{slug}" for slug in SEX_CATEGORY_SLUGS.values()),
            *(f"ethnicity_{slug}" for slug in ETHNICITY_CATEGORY_SLUGS.values()),
            *(f"race_{slug}" for slug in RACE_CATEGORY_SLUGS.values()),
            "race_multiselect",
            "healthy_flag",
            "growth_dx_flag",
        )
        required = {name: required_target(name) for name in required_names}
        values = {
            name: _require_released_proportion(
                target,
                artifact.disclosure_policy.minimum_cell_count,
            )
            for name, target in required.items()
        }
        if len({target.denominator for target in required.values()}) != 1:
            raise ValueError("observed target denominators must match")

        sex_weights = tuple(
            (category, values[f"sex_{slug}"])
            for category, slug in SEX_CATEGORY_SLUGS.items()
        )
        ethnicity_weights = tuple(
            (category, values[f"ethnicity_{slug}"])
            for category, slug in ETHNICITY_CATEGORY_SLUGS.items()
        )
        race_weights = tuple(
            (category, values[f"race_{slug}"])
            for category, slug in RACE_CATEGORY_SLUGS.items()
        )

        return cls(
            artifact_id=artifact.artifact_id,
            target_registry_version=TARGET_REGISTRY_VERSION,
            sex_weights=sex_weights,
            ethnicity_weights=ethnicity_weights,
            race_weights=race_weights,
            race_multiselect_probability=values["race_multiselect"],
            recorded_healthy_probability=values["healthy_flag"],
            recorded_growth_dx_probability=values["growth_dx_flag"],
        )

    def to_mapping(self) -> dict[str, object]:
        """Return only released aggregate probabilities and safe identities."""

        profile = _snapshot_calibration_profile(self)
        return _calibration_profile_mapping(profile)

    def __repr__(self) -> str:
        return "CalibrationSamplingProfile(<aggregate-only>)"


def _snapshot_calibration_profile(
    profile: CalibrationSamplingProfile,
) -> CalibrationSamplingProfile:
    """Return a validated exact profile without trusting frozen stored values."""

    if type(profile) is not CalibrationSamplingProfile:
        raise TypeError("calibration must be exactly a CalibrationSamplingProfile")
    try:
        if (
            type(profile.artifact_id) is not str
            or type(profile.target_registry_version) is not str
        ):
            raise TypeError
        for weights in (
            profile.sex_weights,
            profile.ethnicity_weights,
            profile.race_weights,
        ):
            if type(weights) is not tuple:
                raise TypeError
            for pair in weights:
                if (
                    type(pair) is not tuple
                    or len(pair) != 2
                    or type(pair[0]) is not str
                    or type(pair[1]) is not float
                    or not math.isfinite(pair[1])
                ):
                    raise TypeError
        if not all(
            type(value) is float and math.isfinite(value)
            for value in (
                profile.race_multiselect_probability,
                profile.recorded_healthy_probability,
                profile.recorded_growth_dx_probability,
            )
        ):
            raise TypeError
        return CalibrationSamplingProfile(
            artifact_id=profile.artifact_id,
            target_registry_version=profile.target_registry_version,
            sex_weights=profile.sex_weights,
            ethnicity_weights=profile.ethnicity_weights,
            race_weights=profile.race_weights,
            race_multiselect_probability=profile.race_multiselect_probability,
            recorded_healthy_probability=profile.recorded_healthy_probability,
            recorded_growth_dx_probability=profile.recorded_growth_dx_probability,
        )
    except Exception:  # noqa: BLE001 - mutated fields must fail with fixed text
        raise ValueError("calibration contains invalid aggregate values") from None


def _calibration_profile_mapping(
    profile: CalibrationSamplingProfile,
) -> dict[str, object]:
    def weight_mapping(
        weights: tuple[tuple[str, float], ...],
    ) -> list[dict[str, str | float]]:
        return [
            {"category": category, "probability": probability}
            for category, probability in weights
        ]

    return {
        "artifact_id": profile.artifact_id,
        "target_registry_version": profile.target_registry_version,
        "sex_weights": weight_mapping(profile.sex_weights),
        "ethnicity_weights": weight_mapping(profile.ethnicity_weights),
        "race_weights": weight_mapping(profile.race_weights),
        "race_multiselect_probability": profile.race_multiselect_probability,
        "recorded_healthy_probability": profile.recorded_healthy_probability,
        "recorded_growth_dx_probability": profile.recorded_growth_dx_probability,
    }


def _require_exact_visible_frame(frame: ObservationFrame) -> None:
    """Reject subtype-expanded serializers in one visible frame graph."""

    if type(frame) is not ObservationFrame:
        raise TypeError("frame must be exactly an ObservationFrame")
    if type(frame.window) is not ObservationWindow:
        raise TypeError("frame.window must be exactly an ObservationWindow")
    if type(frame.visits) is not tuple:
        raise TypeError("frame.visits must be exactly a tuple")
    for visit in frame.visits:
        if type(visit) is not ObservedVisit:
            raise TypeError("frame.visits must contain exact ObservedVisit values")
        if type(visit.measurements) is not tuple:
            raise TypeError("frame.visits.measurements must be exactly tuples")
        if not all(type(item) is MeasurementObservation for item in visit.measurements):
            raise TypeError(
                "frame.visits.measurements must contain exact "
                "MeasurementObservation values"
            )
    if type(frame.events) is not tuple or not all(
        type(event) is RecordedEvent for event in frame.events
    ):
        raise TypeError("frame.events must contain exact RecordedEvent values")


def _require_exact_visible_scalar(value: object) -> None:
    """Reject scalar subclasses before equality or ordinary serialization."""

    if type(value) is str or type(value) is int:
        return
    if type(value) is float and math.isfinite(value):
        return
    raise TypeError("visible values must use exact finite primitive types")


def _require_exact_frame_primitives(frame: ObservationFrame) -> None:
    if type(frame.patient_id) is not str or type(frame.policy_version) is not str:
        raise TypeError("frame identifiers must be exact strings")
    if (
        type(frame.window.start_age_days) is not int
        or type(frame.window.effective_end_age_days) is not int
        or type(frame.window.administrative_end_age_days) is not int
        or type(frame.window.censoring_mode) is not CensoringMode
    ):
        raise TypeError("frame window must use exact primitive values")
    for visit in frame.visits:
        if (
            type(visit.patient_id) is not str
            or type(visit.visit_id) is not str
            or type(visit.age_days) is not int
            or type(visit.encounter_type) is not EncounterType
        ):
            raise TypeError("frame visits must use exact primitive values")
        for measurement in visit.measurements:
            if (
                type(measurement.channel) is not MeasurementChannel
                or type(measurement.availability) is not MeasurementAvailability
                or (
                    measurement.recorded_value is not None
                    and (
                        type(measurement.recorded_value) is not float
                        or not math.isfinite(measurement.recorded_value)
                    )
                )
            ):
                raise TypeError("frame measurements must use exact primitive values")
    for event in frame.events:
        if (
            type(event.patient_id) is not str
            or type(event.age_days) is not int
            or type(event.event_kind) is not RecordedEventKind
            or type(event.code) is not str
            or (
                event.opportunity_index is not None
                and type(event.opportunity_index) is not int
            )
        ):
            raise TypeError("frame events must use exact primitive values")


def _require_exact_visible_bundle(bundle: ObservedResourceBundle) -> None:
    """Reject subtype-expanded serializers in one visible resource graph."""

    if type(bundle) is not ObservedResourceBundle:
        raise TypeError("bundle must be exactly an ObservedResourceBundle")
    if type(bundle.shape) is not ResourceShape:
        raise TypeError("bundle.shape must be exactly a ResourceShape")
    if type(bundle.source_frame) is not ObservationFrame:
        raise TypeError("bundle.source_frame must be exactly an ObservationFrame")
    _require_exact_visible_frame(bundle.source_frame)
    if type(bundle.rows) is not MappingProxyType:
        raise TypeError("bundle.rows must be exactly an immutable mapping")
    try:
        row_names = tuple(bundle.rows)
        if not all(type(name) is str for name in row_names) or (
            row_names != BASE_RESOURCE_NAMES
        ):
            raise TypeError
        for resource_name in BASE_RESOURCE_NAMES:
            resource_rows = bundle.rows[resource_name]
            if type(resource_rows) is not tuple or not all(
                type(row) is ResourceRow for row in resource_rows
            ):
                raise TypeError("bundle.rows must contain exact ResourceRow values")
    except Exception:  # noqa: BLE001 - hostile mappings must not leak callbacks
        raise TypeError("bundle.rows must contain exact ResourceRow values") from None
    if type(bundle.clinical_descendants) is not tuple or not all(
        type(item) is ClinicalDescendant for item in bundle.clinical_descendants
    ):
        raise TypeError(
            "bundle.clinical_descendants must contain exact ClinicalDescendant values"
        )


def _snapshot_visible_frame(frame: ObservationFrame) -> ObservationFrame:
    """Rebuild a validated frame whose visible serializers cannot be mutated."""

    _require_exact_visible_frame(frame)
    try:
        _require_exact_frame_primitives(frame)
        window = ObservationWindow(
            frame.window.start_age_days,
            frame.window.effective_end_age_days,
            frame.window.administrative_end_age_days,
            frame.window.censoring_mode,
        )
        visits: list[ObservedVisit] = []
        for visit in frame.visits:
            measurements = tuple(
                MeasurementObservation(
                    measurement.channel,
                    measurement.availability,
                    measurement.recorded_value,
                )
                for measurement in visit.measurements
            )
            visits.append(
                ObservedVisit(
                    visit.patient_id,
                    visit.visit_id,
                    visit.age_days,
                    visit.encounter_type,
                    measurements,
                )
            )
        events = tuple(
            RecordedEvent(
                event.patient_id,
                event.age_days,
                event.event_kind,
                event.code,
                event.opportunity_index,
            )
            for event in frame.events
        )
        truth = ObservationTruth(
            frame.patient_id,
            window,
            (),
            (),
            (),
            (),
        )
        return ObservationFrame(
            frame.patient_id,
            frame.policy_version,
            window,
            tuple(visits),
            events,
            truth,
        )
    except Exception:  # noqa: BLE001 - mutated fields must fail with fixed text
        raise ValueError("frame contains invalid visible values") from None


def _snapshot_resource_shape(shape: ResourceShape) -> ResourceShape:
    if type(shape) is not ResourceShape or type(shape.resources) is not tuple:
        raise TypeError("bundle.shape must be exactly a ResourceShape")
    try:
        resources: list[ResourceSpec] = []
        for resource in shape.resources:
            if (
                type(resource) is not ResourceSpec
                or type(resource.name) is not str
                or type(resource.field_names) is not tuple
                or not all(type(field_name) is str for field_name in resource.field_names)
            ):
                raise TypeError
            resources.append(ResourceSpec(resource.name, tuple(resource.field_names)))
        return ResourceShape(tuple(resources))
    except Exception:  # noqa: BLE001 - mutated shape values must be redacted
        raise ValueError("bundle.shape contains invalid values") from None


def _snapshot_visible_bundle(
    bundle: ObservedResourceBundle,
    *,
    validate_semantics: bool,
) -> ObservedResourceBundle:
    """Rebuild a bundle and enforce row order before ordinary serialization."""

    _require_exact_visible_bundle(bundle)
    shape = _snapshot_resource_shape(bundle.shape)
    source_frame = _snapshot_visible_frame(bundle.source_frame)
    try:
        if type(bundle.patient_id) is not str:
            raise TypeError
        rows: dict[str, tuple[ResourceRow, ...]] = {}
        for resource_name in BASE_RESOURCE_NAMES:
            copied_rows: list[ResourceRow] = []
            for row in bundle.rows[resource_name]:
                if type(row.values) is not tuple or not all(
                    type(pair) is tuple and len(pair) == 2 for pair in row.values
                ):
                    raise TypeError
                if type(row.resource_name) is not str:
                    raise TypeError
                for field_name, value in row.values:
                    if type(field_name) is not str:
                        raise TypeError
                    _require_exact_visible_scalar(value)
                copied_rows.append(ResourceRow(row.resource_name, tuple(row.values)))
            rows[resource_name] = tuple(copied_rows)
        if not all(
            type(item.patient_id) is str
            and type(item.visit_id) is str
            and type(item.age_days) is int
            and type(item.event_kind) is RecordedEventKind
            and type(item.code) is str
            for item in bundle.clinical_descendants
        ):
            raise TypeError
        descendants = tuple(
            ClinicalDescendant(
                item.patient_id,
                item.visit_id,
                item.age_days,
                item.event_kind,
                item.code,
            )
            for item in bundle.clinical_descendants
        )
        snapshot = ObservedResourceBundle(
            bundle.patient_id,
            shape,
            rows,
            descendants,
            source_frame,
        )
    except Exception:  # noqa: BLE001 - mutated row values must fail with fixed text
        raise ValueError("bundle.rows contain invalid values") from None
    if validate_semantics:
        try:
            validation_rows = {
                resource_name: (
                    snapshot.rows[resource_name]
                    if resource_name in {"patients", "visits"}
                    else ()
                )
                for resource_name in BASE_RESOURCE_NAMES
            }
            validation_bundle = ObservedResourceBundle(
                snapshot.patient_id,
                snapshot.shape,
                validation_rows,
                snapshot.clinical_descendants,
                snapshot.source_frame,
            )
            report = validate_observed_resources(validation_bundle)
            if report.status is ResourceValidationStatus.FAIL:
                raise ValueError
            visit_ids = frozenset(
                dict(row.values)["visit_id"] for row in snapshot.rows["visits"]
            )
            ancillary_rows = {
                resource_name: snapshot.rows[resource_name]
                for resource_name in GHD_ANCILLARY_RESOURCE_NAMES
            }
            if not ghd_ancillary_rows_are_valid(
                snapshot.patient_id,
                snapshot.shape,
                ancillary_rows,
                visit_ids,
            ):
                raise ValueError
        except Exception:  # noqa: BLE001 - validation callbacks must be redacted
            raise ValueError("bundle.rows contain invalid visible values") from None
    return snapshot


def _snapshot_demographics(
    demographics: SyntheticDemographics,
) -> SyntheticDemographics:
    if type(demographics) is not SyntheticDemographics:
        raise TypeError("demographics must be exactly SyntheticDemographics")
    try:
        if (
            type(demographics.patient_id) is not str
            or type(demographics.sex) is not str
            or type(demographics.ethnicity) is not str
            or type(demographics.races) is not tuple
            or not all(type(race) is str for race in demographics.races)
        ):
            raise TypeError
        return SyntheticDemographics(
            demographics.patient_id,
            demographics.sex,
            demographics.ethnicity,
            tuple(demographics.races),
        )
    except Exception:  # noqa: BLE001 - mutated fields must fail with fixed text
        raise ValueError("demographics contain invalid visible values") from None


def _snapshot_member_contract(
    member: CohortMember,
    *,
    validate_visible_semantics: bool = False,
) -> tuple[SyntheticDemographics, ObservationFrame, ObservedResourceBundle | None]:
    """Snapshot and validate every object used by ordinary member mappings."""

    if type(member) is not CohortMember:
        raise TypeError("members must contain exact CohortMember values")
    demographics = _snapshot_demographics(member.demographics)
    if type(member.trajectory) is not AgeRegimeDisorderTrajectory:
        raise TypeError("trajectory must be exactly an AgeRegimeDisorderTrajectory")
    frame = _snapshot_visible_frame(member.frame)
    bundle = (
        _snapshot_visible_bundle(
            member.bundle,
            validate_semantics=validate_visible_semantics,
        )
        if member.bundle is not None
        else None
    )
    try:
        patient_ids = {
            demographics.patient_id,
            member.trajectory.physiology.points[0].patient_id,
            frame.patient_id,
        }
        if bundle is not None:
            patient_ids.add(bundle.patient_id)
    except Exception:  # noqa: BLE001 - evaluator mutation must be redacted
        raise ValueError("trajectory contains invalid patient values") from None
    if len(patient_ids) != 1:
        raise ValueError("cohort member objects must identify the same patient")
    return demographics, frame, bundle


def _member_visible_mapping(member: CohortMember) -> dict[str, object]:
    demographics, frame, bundle = _snapshot_member_contract(
        member,
        validate_visible_semantics=True,
    )
    mapping: dict[str, object] = {
        "demographics": SyntheticDemographics.to_mapping(demographics),
        "frame": ObservationFrame.to_mapping(frame),
    }
    if bundle is not None:
        mapping["bundle"] = ObservedResourceBundle.to_mapping(bundle)
    return mapping


@dataclass(frozen=True, repr=False)
class CohortMember:
    """One visible fictional patient plus evaluator-held latent objects."""

    demographics: SyntheticDemographics
    trajectory: AgeRegimeDisorderTrajectory
    frame: ObservationFrame
    bundle: ObservedResourceBundle | None

    def __post_init__(self) -> None:
        _snapshot_member_contract(self)

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
        if type(self.members) is not tuple or not all(
            type(member) is CohortMember for member in self.members
        ):
            raise TypeError("members must be a tuple of CohortMember values")
        if type(self.calibration) is not CalibrationSamplingProfile:
            raise TypeError("calibration must be a CalibrationSamplingProfile")

    def to_mapping(self) -> dict[str, str | int]:
        """Return fixed cohort metadata and visible aggregate counts only."""

        try:
            profile = require_aggregate_safe_token(self.profile, "profile")
            seed = _require_nonnegative_integer(self.seed, "seed")
            if type(self.members) is not tuple:
                raise TypeError
            snapshots = tuple(
                _snapshot_member_contract(member) for member in self.members
            )
            _snapshot_calibration_profile(self.calibration)
        except Exception:  # noqa: BLE001 - aggregate mapping must be fixed-redacted
            raise ValueError("members contain invalid cohort values") from None
        return {
            "profile": profile,
            "seed": seed,
            "member_count": len(snapshots),
            "bundle_count": sum(bundle is not None for _, _, bundle in snapshots),
            "visible_visit_count": sum(len(frame.visits) for _, frame, _ in snapshots),
            "visible_event_count": sum(len(frame.events) for _, frame, _ in snapshots),
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
    """Generate a deterministic evaluator-only cohort from aggregate weights."""

    if type(config) is not CohortConfig:
        raise TypeError("config must be a CohortConfig")
    if type(calibration) is not CalibrationSamplingProfile:
        raise TypeError("calibration must be a CalibrationSamplingProfile")
    try:
        reference_value = getattr(reference, "value", None)
    except Exception:  # noqa: BLE001 - injected access must be redacted
        raise CohortGenerationUnavailable("native cohort generation failed") from None
    if not callable(reference_value):
        raise TypeError("reference must provide a callable value method")
    if not isinstance(modules, Mapping):
        raise TypeError("modules must be a mapping")
    resource_shape: ResourceShape | None = None
    projection_descriptor: dict[str, object] | None = None
    if descriptor is not None:
        try:
            resource_shape, projection_descriptor = _resource_projection_contract(
                descriptor
            )
        except Exception:  # noqa: BLE001 - descriptor failures must be redacted
            raise CohortGenerationUnavailable("native cohort generation failed") from None

    positive_weights = tuple(
        sorted(
            (
                (weight.kind, weight.probability)
                for weight in config.module_weights
                if weight.probability > 0
            ),
            key=lambda item: item[0].value,
        )
    )
    weights_by_reference_sex = {
        reference_sex: tuple(
            sorted(
                (
                    (weight.kind, weight.probability)
                    for weight in weights
                    if weight.probability > 0
                ),
                key=lambda item: item[0].value,
            )
        )
        for reference_sex, weights in config.module_weights_by_reference_sex
    }
    required_kinds = tuple(kind for kind, _ in positive_weights)
    try:
        copied_modules = dict(modules)
    except Exception:  # noqa: BLE001 - injected mapping access must be redacted
        raise CohortGenerationUnavailable("native cohort generation failed") from None
    if not all(isinstance(kind, DisorderKind) for kind in copied_modules):
        raise TypeError("modules keys must be DisorderKind values")
    if set(copied_modules) != set(required_kinds):
        raise ValueError("modules must exactly match positive module-weight kinds")

    try:
        physiology = AgeRegimeTrajectoryKernel(reference, config.age_regime_config)
    except Exception:  # noqa: BLE001 - injected kernel construction must be redacted
        raise CohortGenerationUnavailable("native cohort generation failed") from None
    kernels: dict[DisorderKind, AgeRegimeDisorderKernel] = {}
    for kind in required_kinds:
        module = copied_modules[kind]
        try:
            module_kind = getattr(module, "kind", None)
            module_version = getattr(module, "module_version", None)
            module_version_is_nonempty = (
                bool(module_version.strip())
                if isinstance(module_version, str)
                else False
            )
            module_methods = tuple(
                getattr(module, method_name, None)
                for method_name in (
                    "sample_state",
                    "height_z_delta",
                    "bmi_z_delta",
                    "events",
                )
            )
        except Exception:  # noqa: BLE001 - injected module access must be redacted
            raise CohortGenerationUnavailable("native cohort generation failed") from None
        if not isinstance(module_kind, DisorderKind):
            raise TypeError("modules must declare DisorderKind values")
        if not isinstance(module_version, str) or not module_version_is_nonempty:
            raise TypeError("modules must declare nonempty module versions")
        if not all(callable(method) for method in module_methods):
            raise TypeError("modules must provide the growth-disorder methods")
        if module_kind is not kind:
            raise ValueError("modules keys must match module kinds")
        try:
            validate_growth_disorder_module(module)
            kernels[kind] = AgeRegimeDisorderKernel(physiology, module)
        except Exception:  # noqa: BLE001 - injected validation must be redacted
            raise CohortGenerationUnavailable("native cohort generation failed") from None

    reference_sex_by_recorded = dict(config.reference_sex_mapping)
    members: list[CohortMember] = []
    patient_ids: set[str] = set()
    frame_visit_ids: set[str] = set()
    seen_bundle_visit_ids: set[str] = set()
    for patient_index in range(config.patient_count):
        try:
            patient_id = synthetic_id(config.seed, "patient", patient_index)
            if patient_id in patient_ids:
                raise ValueError("duplicate synthetic patient identifier")
            patient_ids.add(patient_id)

            streams = NamedRandomStreams(config.seed, patient_index)
            demographics_stream = streams.generator("cohort.demographics")
            recorded_sex = _select_weighted_category(
                calibration.sex_weights,
                float(demographics_stream.random()),
            )
            ethnicity = _select_weighted_category(
                calibration.ethnicity_weights,
                float(demographics_stream.random()),
            )
            primary_race = _select_weighted_category(
                calibration.race_weights,
                float(demographics_stream.random()),
            )
            multiselect = (
                float(demographics_stream.random())
                < calibration.race_multiselect_probability
            )
            secondary_race = (
                _select_weighted_category(
                    calibration.race_weights,
                    float(demographics_stream.random()),
                )
                if multiselect
                else None
            )
            demographics = SyntheticDemographics(
                patient_id=patient_id,
                sex=recorded_sex,
                ethnicity=_project_visible_category(ethnicity),
                races=_project_race_slots(primary_race, secondary_race),
            )

            patient = PatientState(
                patient_id=patient_id,
                recorded_sex=recorded_sex,
                reference_sex=reference_sex_by_recorded[recorded_sex],
            )
            selection_weights = positive_weights
            if weights_by_reference_sex:
                selection_weights = weights_by_reference_sex[patient.reference_sex]
            eligible_weights = _eligible_module_weights(
                selection_weights,
                copied_modules,
                patient.reference_sex,
            )
            module_stream = streams.generator("cohort.module")
            module_kind = DisorderKind(
                _select_weighted_category(
                    tuple((kind.value, probability) for kind, probability in eligible_weights),
                    float(module_stream.random()),
                )
            )
            trajectory = kernels[module_kind].generate(
                patient,
                config.ages_days,
                streams,
            )
            frame = generate_observation_frame(
                trajectory,
                config.observation_policy,
                streams,
            )
            if (
                validate_observation_frame(frame).status
                is not ObservationValidationStatus.PASS
            ):
                raise ValueError("observation frame did not pass validation")
            member_frame_visit_ids = tuple(visit.visit_id for visit in frame.visits)
            if (
                len(member_frame_visit_ids) != len(set(member_frame_visit_ids))
                or not frame_visit_ids.isdisjoint(member_frame_visit_ids)
            ):
                raise ValueError("duplicate synthetic visit identifier")
            frame_visit_ids.update(member_frame_visit_ids)
            bundle = None
            if resource_shape is not None:
                assert projection_descriptor is not None
                bundle = project_observed_resources(
                    frame,
                    projection_descriptor,
                    demographics,
                )
                if bundle.shape != resource_shape:
                    raise ValueError("resource shape changed during generation")
                if (
                    validate_observed_resources(bundle).status
                    is not ResourceValidationStatus.PASS
                ):
                    raise ValueError("observed resources did not pass validation")
                member_bundle_visit_ids = tuple(
                    row.to_mapping()["visit_id"] for row in bundle.rows["visits"]
                )
                if (
                    not all(
                        isinstance(visit_id, str)
                        for visit_id in member_bundle_visit_ids
                    )
                    or len(member_bundle_visit_ids)
                    != len(set(member_bundle_visit_ids))
                    or not seen_bundle_visit_ids.isdisjoint(
                        member_bundle_visit_ids
                    )
                ):
                    raise ValueError("duplicate synthetic visit identifier")
                seen_bundle_visit_ids.update(member_bundle_visit_ids)
            members.append(CohortMember(demographics, trajectory, frame, bundle))
        except Exception:  # noqa: BLE001 - injected runtime errors must be redacted
            raise CohortGenerationUnavailable("native cohort generation failed") from None

    return NativeCohort(
        profile=config.profile,
        seed=config.seed,
        members=tuple(members),
        calibration=calibration,
    )


__all__ = [
    "CalibrationSamplingProfile",
    "CohortConfig",
    "CohortGenerationUnavailable",
    "CohortMember",
    "CohortModuleWeight",
    "NativeCohort",
    "generate_native_cohort",
]
