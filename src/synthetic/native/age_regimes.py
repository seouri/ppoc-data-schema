"""Versioned, development-only age-regime configuration and classification."""

import math
from dataclasses import dataclass
from typing import ClassVar

from synthetic.models import GrowthRegime


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
