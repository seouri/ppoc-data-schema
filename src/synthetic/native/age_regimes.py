"""Versioned, development-only age-regime configuration and classification."""

import math
from dataclasses import dataclass
from itertools import pairwise
from numbers import Real
from typing import ClassVar

from synthetic.models import (
    AgeRegimePoint,
    AgeRegimeState,
    AgeRegimeTrajectory,
    GrowthRegime,
    PatientState,
)
from synthetic.randomness import NamedRandomStreams
from synthetic.references import GrowthReference


def _nonnegative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")


def _positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _finite_number(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


@dataclass(frozen=True)
class AgeRegimeConfig:
    """Development-only, uncalibrated parameters for age-regime simulation."""

    module_version: ClassVar[str] = "age-regimes-v1"

    transition_age_days: int = 730
    transition_window_days: int = 30
    maximum_age_days: int = 7305
    puberty_min_age_days: int = 3287
    puberty_max_age_days: int = 5114
    puberty_tempo_min_days: int = 730
    puberty_tempo_max_days: int = 1460
    catch_up_days: int = 730
    head_circumference_decay_days: int = 730
    residual_sd: float = 0.1
    length_to_height_offset_cm: float = 0.7
    max_transition_discontinuity_cm: float = 3.0
    puberty_height_spurt_min: float = 0.2
    puberty_height_spurt_max: float = 0.8
    puberty_bmi_shift_min: float = -0.2
    puberty_bmi_shift_max: float = 0.3

    def __post_init__(self) -> None:
        for name in (
            "transition_age_days",
            "maximum_age_days",
            "puberty_min_age_days",
            "puberty_max_age_days",
        ):
            _nonnegative_int(name, getattr(self, name))
        for name in (
            "transition_window_days",
            "puberty_tempo_min_days",
            "puberty_tempo_max_days",
            "catch_up_days",
            "head_circumference_decay_days",
        ):
            _positive_int(name, getattr(self, name))
        for name in (
            "residual_sd",
            "length_to_height_offset_cm",
            "max_transition_discontinuity_cm",
            "puberty_height_spurt_min",
            "puberty_height_spurt_max",
            "puberty_bmi_shift_min",
            "puberty_bmi_shift_max",
        ):
            _finite_number(name, getattr(self, name))

        if self.puberty_min_age_days > self.puberty_max_age_days:
            raise ValueError("puberty age bounds must be ordered")
        if self.puberty_tempo_min_days > self.puberty_tempo_max_days:
            raise ValueError("puberty tempo bounds must be ordered")
        if self.puberty_height_spurt_min > self.puberty_height_spurt_max:
            raise ValueError("puberty height-spurt bounds must be ordered")
        if self.puberty_bmi_shift_min > self.puberty_bmi_shift_max:
            raise ValueError("puberty BMI-shift bounds must be ordered")
        if self.transition_window_days > self.transition_age_days:
            raise ValueError("transition window must start at or after day 0")
        if self.puberty_min_age_days <= self.transition_age_days + self.transition_window_days:
            raise ValueError("puberty must begin after the transition window")
        if self.residual_sd < 0:
            raise ValueError("residual_sd must be nonnegative")
        if self.length_to_height_offset_cm < 0:
            raise ValueError("length_to_height_offset_cm must be nonnegative")
        if self.max_transition_discontinuity_cm <= 0:
            raise ValueError("max_transition_discontinuity_cm must be positive")
        if self.puberty_max_age_days + self.puberty_tempo_max_days > self.maximum_age_days:
            raise ValueError("puberty schedule must fit within maximum_age_days")
        if self.transition_age_days + self.transition_window_days >= self.maximum_age_days:
            raise ValueError("transition window must precede maximum_age_days")


def classify_age(
    age_days: int,
    puberty_onset_age_days: int,
    puberty_tempo_days: int,
    config: AgeRegimeConfig,
) -> GrowthRegime:
    """Classify an age using inclusive upper boundaries for transition and puberty."""

    _nonnegative_int("age_days", age_days)
    _nonnegative_int("puberty_onset_age_days", puberty_onset_age_days)
    _positive_int("puberty_tempo_days", puberty_tempo_days)
    if not isinstance(config, AgeRegimeConfig):
        raise ValueError("config must be an AgeRegimeConfig")  # noqa: TRY004
    if not config.puberty_min_age_days <= puberty_onset_age_days <= config.puberty_max_age_days:
        raise ValueError("puberty onset is outside configured puberty bounds")
    if not config.puberty_tempo_min_days <= puberty_tempo_days <= config.puberty_tempo_max_days:
        raise ValueError("puberty tempo is outside configured puberty bounds")

    transition_start = config.transition_age_days - config.transition_window_days
    if age_days < transition_start:
        return GrowthRegime.INFANCY
    if age_days <= config.transition_age_days + config.transition_window_days:
        return GrowthRegime.TRANSITION
    if age_days < puberty_onset_age_days:
        return GrowthRegime.CHILDHOOD
    if age_days <= puberty_onset_age_days + puberty_tempo_days:
        return GrowthRegime.PUBERTY
    return GrowthRegime.ADOLESCENCE


def _positive_value(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be finite and positive")  # noqa: TRY004
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite and positive") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return number


def _derived_bmi(weight_kg: float, height_cm: float) -> float:
    try:
        height_m = height_cm / 100.0
        value = weight_kg / (height_m * height_m)
    except ArithmeticError as exc:
        raise ValueError("derived BMI must be finite and positive") from exc
    return _positive_value("derived BMI", value)


def _derived_weight(bmi: float, height_cm: float) -> float:
    try:
        height_m = height_cm / 100.0
        value = bmi * height_m * height_m
    except ArithmeticError as exc:
        raise ValueError("derived weight must be finite and positive") from exc
    return _positive_value("derived weight", value)


def _smooth_step(age_days: int, onset_age_days: int, tempo_days: int) -> float:
    if age_days < onset_age_days:
        return 0.0
    progress = min(1.0, max(0.0, (age_days - onset_age_days) / tempo_days))
    return 3.0 * progress * progress - 2.0 * progress * progress * progress


class AgeRegimeTrajectoryKernel:
    """Generate evaluator-only, deterministic trajectories across pediatric regimes."""

    def __init__(
        self,
        reference: GrowthReference,
        config: AgeRegimeConfig | None = None,
    ) -> None:
        if config is not None and not isinstance(config, AgeRegimeConfig):
            raise ValueError("config must be an AgeRegimeConfig")
        self.reference = reference
        self.config = config or AgeRegimeConfig()

    def generate(
        self,
        patient: PatientState,
        ages_days: tuple[int, ...],
        streams: NamedRandomStreams,
        *,
        state: AgeRegimeState | None = None,
    ) -> AgeRegimeTrajectory:
        self._validate_ages(ages_days)
        if state is None:
            state = self.sample_state(streams)
        else:
            self._validate_state(state)
        residual = streams.generator("regime.residual")
        head = streams.generator("regime.head")

        points: list[AgeRegimePoint] = []
        previous_age: int | None = None
        previous_size: float | None = None
        previous_weight: float | None = None
        for age_days in ages_days:
            regime = classify_age(
                age_days,
                state.puberty_onset_age_days,
                state.puberty_tempo_days,
                self.config,
            )
            size_residual = float(residual.normal(0.0, self.config.residual_sd))
            mass_residual = float(residual.normal(0.0, self.config.residual_sd))

            if regime in (GrowthRegime.INFANCY, GrowthRegime.TRANSITION):
                point_values = self._pre_transition_values(
                    patient,
                    age_days,
                    regime,
                    state,
                    size_residual,
                    mass_residual,
                    head,
                )
            else:
                point_values = self._post_transition_values(
                    patient,
                    age_days,
                    state,
                    size_residual,
                    mass_residual,
                )

            comparable_size = point_values["height_cm"]
            if comparable_size is None:
                comparable_size = point_values["length_cm"] - self.config.length_to_height_offset_cm
            comparable_size = _positive_value("derived comparable body size", comparable_size)
            weight_kg = _positive_value("derived weight", point_values["weight_kg"])

            height_velocity: float | None = None
            weight_velocity: float | None = None
            if previous_age is not None:
                scale = 365.25 / (age_days - previous_age)
                height_velocity = (comparable_size - previous_size) * scale
                weight_velocity = (weight_kg - previous_weight) * scale
                if not math.isfinite(height_velocity) or not math.isfinite(weight_velocity):
                    raise ValueError("derived velocities must be finite")

            points.append(
                AgeRegimePoint(
                    patient_id=patient.patient_id,
                    age_days=age_days,
                    regime=regime,
                    length_cm=point_values["length_cm"],
                    height_cm=point_values["height_cm"],
                    weight_kg=weight_kg,
                    bmi=point_values["bmi"],
                    head_circumference_cm=point_values["head_circumference_cm"],
                    length_z=point_values["length_z"],
                    height_z=point_values["height_z"],
                    weight_z=point_values["weight_z"],
                    bmi_z=point_values["bmi_z"],
                    height_velocity_cm_per_year=height_velocity,
                    weight_velocity_kg_per_year=weight_velocity,
                )
            )
            previous_age = age_days
            previous_size = comparable_size
            previous_weight = weight_kg

        self._validate_transition_continuity(points, patient, state)
        return AgeRegimeTrajectory(tuple(points), state)

    def _validate_ages(self, ages_days: object) -> None:
        if not isinstance(ages_days, tuple) or not ages_days:
            raise ValueError("ages_days must be a nonempty tuple")
        if any(isinstance(age, bool) or not isinstance(age, int) or age < 0 for age in ages_days):
            raise ValueError("ages_days must contain nonnegative integers")
        if any(left >= right for left, right in pairwise(ages_days)):
            raise ValueError("ages_days must be unique and increasing")
        if any(age > self.config.maximum_age_days for age in ages_days):
            raise ValueError("ages_days are outside the configured domain")

        reference_min_age = getattr(self.reference, "min_age_days", None)
        reference_max_age = getattr(self.reference, "max_age_days", None)
        if (
            isinstance(reference_min_age, int)
            and not isinstance(reference_min_age, bool)
            and any(age < reference_min_age for age in ages_days)
        ):
            raise ValueError("requested ages are outside the reference domain")
        if (
            isinstance(reference_max_age, int)
            and not isinstance(reference_max_age, bool)
            and any(age > reference_max_age for age in ages_days)
        ):
            raise ValueError("requested ages are outside the reference domain")

    def sample_state(self, streams: NamedRandomStreams) -> AgeRegimeState:
        birth = streams.generator("regime.birth")
        childhood = streams.generator("regime.childhood")
        puberty = streams.generator("regime.puberty")
        head = streams.generator("regime.head")

        puberty_height_spurt_z = float(
            puberty.uniform(
                self.config.puberty_height_spurt_min,
                self.config.puberty_height_spurt_max,
            )
        )
        puberty_bmi_shift_z = float(
            puberty.uniform(
                self.config.puberty_bmi_shift_min,
                self.config.puberty_bmi_shift_max,
            )
        )
        state = AgeRegimeState(
            module_version=self.config.module_version,
            birth_length_z=float(birth.normal(0.0, 0.8)),
            birth_weight_z=float(birth.normal(0.0, 0.8)),
            head_circumference_z=float(head.normal(0.0, 0.8)),
            childhood_height_z=float(childhood.normal(0.0, 0.8)),
            childhood_bmi_z=float(childhood.normal(0.0, 0.8)),
            puberty_onset_age_days=round(
                float(
                    puberty.uniform(
                        self.config.puberty_min_age_days,
                        self.config.puberty_max_age_days,
                    )
                )
            ),
            puberty_tempo_days=round(
                float(
                    puberty.uniform(
                        self.config.puberty_tempo_min_days,
                        self.config.puberty_tempo_max_days,
                    )
                )
            ),
            puberty_height_spurt_z=puberty_height_spurt_z,
            puberty_bmi_shift_z=puberty_bmi_shift_z,
        )
        return state

    def _validate_state(self, state: AgeRegimeState) -> None:
        if not isinstance(state, AgeRegimeState):
            raise ValueError("state must be an AgeRegimeState")  # noqa: TRY004
        if state.module_version != self.config.module_version:
            raise ValueError("state module_version does not match current module")
        if not self.config.puberty_min_age_days <= state.puberty_onset_age_days <= self.config.puberty_max_age_days:
            raise ValueError("state puberty onset is outside configured puberty bounds")
        if not self.config.puberty_tempo_min_days <= state.puberty_tempo_days <= self.config.puberty_tempo_max_days:
            raise ValueError("state puberty tempo is outside configured puberty bounds")
        if state.puberty_onset_age_days + state.puberty_tempo_days > self.config.maximum_age_days:
            raise ValueError("state puberty schedule exceeds maximum_age_days")

    def _pre_transition_values(
        self,
        patient: PatientState,
        age_days: int,
        regime: GrowthRegime,
        state: AgeRegimeState,
        size_residual: float,
        mass_residual: float,
        head,
    ) -> dict[str, float | None]:
        catch_up_fraction = max(0.0, 1.0 - age_days / self.config.catch_up_days)
        length_z = (
            state.childhood_height_z
            + catch_up_fraction * (state.birth_length_z - state.childhood_height_z)
            + size_residual
        )
        weight_z = (
            state.childhood_bmi_z
            + catch_up_fraction * (state.birth_weight_z - state.childhood_bmi_z)
            + mass_residual
        )
        head_fraction = max(
            0.0,
            1.0 - age_days / self.config.head_circumference_decay_days,
        )
        head_z = state.head_circumference_z * head_fraction + float(
            head.normal(0.0, self.config.residual_sd)
        )

        length_cm = self._reference_value("length_cm", age_days, patient, length_z)
        weight_kg = self._reference_value("weight_kg", age_days, patient, weight_z)
        head_circumference_cm = self._reference_value(
            "head_circumference_cm", age_days, patient, head_z
        )

        height_cm: float | None = None
        bmi: float | None = None
        height_z: float | None = None
        if regime is GrowthRegime.TRANSITION:
            height_cm = _positive_value(
                "converted standing height",
                length_cm - self.config.length_to_height_offset_cm,
            )
            bmi = _derived_bmi(weight_kg, height_cm)
            height_z = length_z

        return {
            "length_cm": length_cm,
            "height_cm": height_cm,
            "weight_kg": weight_kg,
            "bmi": bmi,
            "head_circumference_cm": head_circumference_cm,
            "length_z": length_z,
            "height_z": height_z,
            "weight_z": weight_z,
            "bmi_z": None,
        }

    def _post_transition_values(
        self,
        patient: PatientState,
        age_days: int,
        state: AgeRegimeState,
        size_residual: float,
        mass_residual: float,
    ) -> dict[str, float | None]:
        puberty_progress = _smooth_step(
            age_days,
            state.puberty_onset_age_days,
            state.puberty_tempo_days,
        )
        height_z = (
            state.childhood_height_z
            + size_residual
            + puberty_progress * state.puberty_height_spurt_z
        )
        bmi_z = (
            state.childhood_bmi_z
            + mass_residual
            + puberty_progress * state.puberty_bmi_shift_z
        )
        height_cm = self._reference_value("height_cm", age_days, patient, height_z)
        bmi = self._reference_value("bmi", age_days, patient, bmi_z)
        weight_kg = _derived_weight(bmi, height_cm)
        return {
            "length_cm": None,
            "height_cm": height_cm,
            "weight_kg": weight_kg,
            "bmi": bmi,
            "head_circumference_cm": None,
            "length_z": None,
            "height_z": height_z,
            "weight_z": None,
            "bmi_z": bmi_z,
        }

    def _reference_value(
        self,
        metric: str,
        age_days: int,
        patient: PatientState,
        z: float,
    ) -> float:
        value = self.reference.value(metric, age_days, patient.reference_sex, z)
        return _positive_value(f"reference {metric}", value)

    def _validate_transition_continuity(
        self,
        points: list[AgeRegimePoint],
        patient: PatientState,
        state: AgeRegimeState,
    ) -> None:
        transition_end = self.config.transition_age_days + self.config.transition_window_days
        for previous, current in pairwise(points):
            if previous.age_days <= transition_end < current.age_days:
                comparison_age = transition_end + 1
                length_cm = self._reference_value(
                    "length_cm",
                    comparison_age,
                    patient,
                    state.childhood_height_z,
                )
                converted_height = _positive_value(
                    "converted standing height",
                    length_cm - self.config.length_to_height_offset_cm,
                )
                standing_height = self._reference_value(
                    "height_cm",
                    comparison_age,
                    patient,
                    state.childhood_height_z,
                )
                if (
                    abs(standing_height - converted_height)
                    > self.config.max_transition_discontinuity_cm
                ):
                    raise ValueError("transition discontinuity exceeds configured tolerance")
