"""Development-only latent growth-disorder scenarios.

The default values describe uncalibrated scenarios. They are deliberately not
prevalence estimates or clinically validated parameterizations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import ClassVar, Protocol

from synthetic.models import (
    MAX_AGE_DAYS,
    ClinicalEvent,
    DisorderKind,
    LatentDisorderState,
    PatientState,
)
from synthetic.randomness import NamedRandomStreams

_PHASE_ORDER = {
    "latent_onset": 0,
    "observable_phenotype": 1,
    "recognition_opportunity": 2,
    "workup": 3,
    "recorded_diagnosis": 4,
    "treatment_start": 5,
    "treatment_response": 6,
    "treatment_nonresponse": 6,
}

class GrowthDisorderModule(Protocol):
    kind: DisorderKind
    module_version: str

    def sample_state(
        self, patient: PatientState, streams: NamedRandomStreams
    ) -> LatentDisorderState: ...

    def height_z_delta(self, state: LatentDisorderState, age_days: int) -> float: ...

    def bmi_z_delta(self, state: LatentDisorderState, age_days: int) -> float: ...

    def events(
        self, patient: PatientState, state: LatentDisorderState
    ) -> tuple[ClinicalEvent, ...]: ...


def _require_age(name: str, value: object, *, positive: bool = False) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > MAX_AGE_DAYS
    ):
        raise ValueError(f"{name} must be a nonnegative integer")
    if positive and value == 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _require_magnitude(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(  # noqa: TRY004
            f"{name} must be finite and nonnegative"
        )
    try:
        magnitude = float(value)
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite and nonnegative") from exc
    if not math.isfinite(magnitude) or magnitude < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return magnitude


def _require_finite_real(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite")  # noqa: TRY004
    try:
        result = float(value)
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _require_probability(name: str, value: object) -> float:
    probability = _require_magnitude(name, value)
    if probability > 1:
        raise ValueError(f"{name} must be in [0, 1]")
    return probability


def _require_ordered_bounds(
    lower_name: str, lower: object, upper_name: str, upper: object, *, ages: bool = False
) -> tuple[float, float] | tuple[int, int]:
    if ages:
        lower_value = _require_age(lower_name, lower)
        upper_value = _require_age(upper_name, upper)
    else:
        lower_value = _require_magnitude(lower_name, lower)
        upper_value = _require_magnitude(upper_name, upper)
    if lower_value > upper_value:
        raise ValueError(f"{lower_name} must not exceed {upper_name}")
    return lower_value, upper_value


def _validated_builtin_config(
    config: object | None,
    expected_type: type[object],
    expected_version: str,
    *,
    validate_type: bool = True,
    validate_version: bool = True,
) -> object:
    if config is None:
        config = expected_type()
    if validate_type and type(config) is not expected_type:
        raise TypeError(f"config must be a {expected_type.__name__}")
    if validate_version and getattr(config, "module_version", None) != expected_version:
        raise ValueError("module/config version mismatch")
    return config


def _require_module_state(state: LatentDisorderState, kind: DisorderKind) -> None:
    if not isinstance(state, LatentDisorderState):
        raise TypeError("state must be a LatentDisorderState")
    if state.kind is not kind:
        raise ValueError(f"state kind must be {kind.value}")


def _checked_age_sum(name: str, *values: int) -> int:
    try:
        total = sum(values)
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a supported age") from exc
    return _require_age(name, total)


def _ordered_events(
    patient: PatientState, schedule: tuple[tuple[str, int], ...]
) -> tuple[ClinicalEvent, ...]:
    previous_phase = -1
    previous_age = -1
    for event_type, age_days in schedule:
        if not isinstance(event_type, str):
            raise ValueError("clinical event type must be a string")  # noqa: TRY004
        phase = _PHASE_ORDER.get(event_type)
        if phase is None:
            raise ValueError(f"unknown clinical event type: {event_type}")
        _require_age(f"{event_type} age_days", age_days)
        if phase <= previous_phase or age_days < previous_age:
            raise ValueError("clinical event schedule must follow causal phase order")
        previous_phase = phase
        previous_age = age_days
    return tuple(
        ClinicalEvent(
            patient_id=patient.patient_id,
            age_days=age_days,
            event_type=event_type,
            code=None,
            hidden=event_type == "latent_onset",
        )
        for event_type, age_days in sorted(
            schedule, key=lambda event: (event[1], _PHASE_ORDER[event[0]])
        )
    )


@dataclass(frozen=True)
class HealthyGrowthConfig:
    """Empty configuration retained for the versioned module interface."""

    module_version: ClassVar[str] = "healthy-growth-v1"


class HealthyGrowthModule:
    kind = DisorderKind.HEALTHY
    module_version: ClassVar[str] = HealthyGrowthConfig.module_version

    def __init__(self, config: HealthyGrowthConfig | None = None) -> None:
        self.config = _validated_builtin_config(
            config,
            HealthyGrowthConfig,
            HealthyGrowthModule.module_version,
            validate_type=type(self) is HealthyGrowthModule,
            validate_version=type(self) is HealthyGrowthModule,
        )

    def sample_state(
        self, patient: PatientState, streams: NamedRandomStreams
    ) -> LatentDisorderState:
        return LatentDisorderState(self.kind, None, 0.0)

    def height_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
        _require_module_state(state, self.kind)
        _require_age("age_days", age_days)
        return 0.0

    def bmi_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
        _require_module_state(state, self.kind)
        _require_age("age_days", age_days)
        return 0.0

    def events(
        self, patient: PatientState, state: LatentDisorderState
    ) -> tuple[ClinicalEvent, ...]:
        _require_module_state(state, self.kind)
        return ()


@dataclass(frozen=True)
class FamilialShortStatureConfig:
    """Uncalibrated development scenario parameters for familial short stature."""

    module_version: ClassVar[str] = "familial-short-stature-v1"

    severity_min: float = 0.7
    severity_max: float = 1.3
    onset_age_days: int = 0
    phenotype_age_days: int = 730
    recognition_age_days: int = 1460
    workup_age_days: int = 1825
    diagnosis_age_days: int = 2190

    def __post_init__(self) -> None:
        _require_ordered_bounds("severity_min", self.severity_min, "severity_max", self.severity_max)
        if _require_age("onset_age_days", self.onset_age_days) != 0:
            raise ValueError("onset_age_days must be zero for familial short stature")
        schedule = (
            self.onset_age_days,
            self.phenotype_age_days,
            self.recognition_age_days,
            self.workup_age_days,
            self.diagnosis_age_days,
        )
        if tuple(_require_age("event age_days", age) for age in schedule) != tuple(sorted(schedule)):
            raise ValueError("familial short stature event ages must be causally ordered")


class FamilialShortStatureModule:
    kind = DisorderKind.FAMILIAL_SHORT_STATURE
    module_version: ClassVar[str] = FamilialShortStatureConfig.module_version

    def __init__(self, config: FamilialShortStatureConfig | None = None) -> None:
        self.config = _validated_builtin_config(
            config,
            FamilialShortStatureConfig,
            FamilialShortStatureModule.module_version,
            validate_type=type(self) is FamilialShortStatureModule,
            validate_version=type(self) is FamilialShortStatureModule,
        )

    def sample_state(
        self, patient: PatientState, streams: NamedRandomStreams
    ) -> LatentDisorderState:
        disorder = streams.generator(f"disorder.{self.kind.value}")
        severity = float(disorder.uniform(self.config.severity_min, self.config.severity_max))
        return LatentDisorderState(self.kind, self.config.onset_age_days, severity)

    def height_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
        _require_module_state(state, self.kind)
        _require_age("age_days", age_days)
        return -state.severity

    def bmi_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
        _require_module_state(state, self.kind)
        _require_age("age_days", age_days)
        return 0.0

    def events(
        self, patient: PatientState, state: LatentDisorderState
    ) -> tuple[ClinicalEvent, ...]:
        _require_module_state(state, self.kind)
        if state.severity == 0:
            return _ordered_events(
                patient, (("latent_onset", self.config.onset_age_days),)
            )
        return _ordered_events(
            patient,
            (
                ("latent_onset", self.config.onset_age_days),
                ("observable_phenotype", self.config.phenotype_age_days),
                ("recognition_opportunity", self.config.recognition_age_days),
                ("workup", self.config.workup_age_days),
                ("recorded_diagnosis", self.config.diagnosis_age_days),
            ),
        )


@dataclass(frozen=True)
class ConstitutionalDelayConfig:
    """Uncalibrated development scenario parameters for constitutional delay."""

    module_version: ClassVar[str] = "constitutional-delay-v1"

    expected_puberty_age_days: int = 4380
    puberty_delay_min_days: int = 180
    puberty_delay_max_days: int = 720
    recovery_days: int = 730
    height_z_magnitude: float = 1.0
    recognition_delay_days: int = 90
    workup_delay_days: int = 30
    diagnosis_delay_days: int = 30

    def __post_init__(self) -> None:
        _require_age("expected_puberty_age_days", self.expected_puberty_age_days)
        _require_ordered_bounds(
            "puberty_delay_min_days",
            self.puberty_delay_min_days,
            "puberty_delay_max_days",
            self.puberty_delay_max_days,
            ages=True,
        )
        _require_age("recovery_days", self.recovery_days, positive=True)
        _require_magnitude("height_z_magnitude", self.height_z_magnitude)
        for name, value in (
            ("recognition_delay_days", self.recognition_delay_days),
            ("workup_delay_days", self.workup_delay_days),
            ("diagnosis_delay_days", self.diagnosis_delay_days),
        ):
            _require_age(name, value)
        _checked_age_sum(
            "constitutional delay diagnosis age_days",
            self.expected_puberty_age_days,
            self.puberty_delay_max_days,
            self.recognition_delay_days,
            self.workup_delay_days,
            self.diagnosis_delay_days,
        )


class ConstitutionalDelayModule:
    kind = DisorderKind.CONSTITUTIONAL_DELAY
    module_version: ClassVar[str] = ConstitutionalDelayConfig.module_version

    def __init__(self, config: ConstitutionalDelayConfig | None = None) -> None:
        self.config = _validated_builtin_config(
            config,
            ConstitutionalDelayConfig,
            ConstitutionalDelayModule.module_version,
            validate_type=type(self) is ConstitutionalDelayModule,
            validate_version=type(self) is ConstitutionalDelayModule,
        )

    def sample_state(
        self, patient: PatientState, streams: NamedRandomStreams
    ) -> LatentDisorderState:
        disorder = streams.generator(f"disorder.{self.kind.value}")
        delay = int(
            disorder.integers(
                self.config.puberty_delay_min_days, self.config.puberty_delay_max_days + 1
            )
        )
        return LatentDisorderState(
            self.kind,
            self.config.expected_puberty_age_days,
            self.config.height_z_magnitude,
            puberty_delay_days=delay,
        )

    def height_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
        _require_module_state(state, self.kind)
        age = _require_age("age_days", age_days)
        puberty_age = self.config.expected_puberty_age_days
        delayed_end = _checked_age_sum(
            "constitutional delay end age_days",
            puberty_age,
            state.puberty_delay_days,
        )
        if age < puberty_age or state.puberty_delay_days == 0:
            return 0.0
        try:
            if age <= delayed_end:
                delta = -state.severity * (age - puberty_age) / state.puberty_delay_days
            else:
                elapsed_recovery = age - delayed_end
                if elapsed_recovery >= self.config.recovery_days:
                    return 0.0
                delta = -state.severity * (
                    1 - elapsed_recovery / self.config.recovery_days
                )
        except (ArithmeticError, TypeError, ValueError) as exc:
            raise ValueError("age_days is too large for disorder arithmetic") from exc
        return _require_finite_real("constitutional delay height z-score delta", delta)

    def bmi_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
        _require_module_state(state, self.kind)
        _require_age("age_days", age_days)
        return 0.0

    def events(
        self, patient: PatientState, state: LatentDisorderState
    ) -> tuple[ClinicalEvent, ...]:
        _require_module_state(state, self.kind)
        puberty_age = self.config.expected_puberty_age_days
        if state.severity == 0 or state.puberty_delay_days == 0:
            return _ordered_events(patient, (("latent_onset", puberty_age),))
        delayed_end = _checked_age_sum(
            "constitutional delay end age_days",
            puberty_age,
            state.puberty_delay_days,
        )
        phenotype_age = _checked_age_sum(
            "constitutional delay phenotype age_days",
            puberty_age,
            state.puberty_delay_days // 2,
        )
        recognition_age = _checked_age_sum(
            "constitutional delay recognition age_days",
            delayed_end,
            self.config.recognition_delay_days,
        )
        workup_age = _checked_age_sum(
            "constitutional delay workup age_days",
            recognition_age,
            self.config.workup_delay_days,
        )
        diagnosis_age = _checked_age_sum(
            "constitutional delay diagnosis age_days",
            workup_age,
            self.config.diagnosis_delay_days,
        )
        return _ordered_events(
            patient,
            (
                ("latent_onset", puberty_age),
                ("observable_phenotype", phenotype_age),
                ("recognition_opportunity", recognition_age),
                ("workup", workup_age),
                ("recorded_diagnosis", diagnosis_age),
            ),
        )


@dataclass(frozen=True)
class GrowthHormoneDeficiencyConfig:
    """Uncalibrated development scenario parameters for growth-hormone deficiency."""

    module_version: ClassVar[str] = "growth-hormone-deficiency-v1"

    onset_min_age_days: int = 730
    onset_max_age_days: int = 3652
    severity_min: float = 0.7
    severity_max: float = 1.3
    progression_days: int = 730
    phenotype_delay_days: int = 180
    recognition_delay_days: int = 180
    workup_delay_days: int = 30
    diagnosis_delay_days: int = 30
    treatment_probability: float = 0.7
    treatment_delay_days: int = 90
    response_days: int = 365
    treatment_response_min: float = 0.4
    treatment_response_max: float = 0.9
    bmi_z_max_delta: float = 0.8

    def __post_init__(self) -> None:
        _require_ordered_bounds(
            "onset_min_age_days",
            self.onset_min_age_days,
            "onset_max_age_days",
            self.onset_max_age_days,
            ages=True,
        )
        _require_ordered_bounds("severity_min", self.severity_min, "severity_max", self.severity_max)
        _require_age("progression_days", self.progression_days, positive=True)
        for name, value in (
            ("phenotype_delay_days", self.phenotype_delay_days),
            ("recognition_delay_days", self.recognition_delay_days),
            ("workup_delay_days", self.workup_delay_days),
            ("diagnosis_delay_days", self.diagnosis_delay_days),
            ("treatment_delay_days", self.treatment_delay_days),
        ):
            _require_age(name, value)
        _require_probability("treatment_probability", self.treatment_probability)
        _require_age("response_days", self.response_days, positive=True)
        _, response_max = _require_ordered_bounds(
            "treatment_response_min",
            self.treatment_response_min,
            "treatment_response_max",
            self.treatment_response_max,
        )
        if response_max > 1:
            raise ValueError("treatment response bounds must be in [0, 1]")
        _require_magnitude("bmi_z_max_delta", self.bmi_z_max_delta)
        _checked_age_sum(
            "growth hormone deficiency treatment outcome age_days",
            self.onset_max_age_days,
            self.phenotype_delay_days,
            self.recognition_delay_days,
            self.workup_delay_days,
            self.diagnosis_delay_days,
            self.treatment_delay_days,
            self.response_days,
        )


class GrowthHormoneDeficiencyModule:
    kind = DisorderKind.GROWTH_HORMONE_DEFICIENCY
    module_version: ClassVar[str] = GrowthHormoneDeficiencyConfig.module_version

    def __init__(self, config: GrowthHormoneDeficiencyConfig | None = None) -> None:
        self.config = _validated_builtin_config(
            config,
            GrowthHormoneDeficiencyConfig,
            GrowthHormoneDeficiencyModule.module_version,
            validate_type=type(self) is GrowthHormoneDeficiencyModule,
            validate_version=type(self) is GrowthHormoneDeficiencyModule,
        )

    def sample_state(
        self, patient: PatientState, streams: NamedRandomStreams
    ) -> LatentDisorderState:
        disorder = streams.generator(f"disorder.{self.kind.value}")
        try:
            onset = int(
                disorder.integers(
                    self.config.onset_min_age_days,
                    self.config.onset_max_age_days + 1,
                )
            )
            severity = float(
                disorder.uniform(self.config.severity_min, self.config.severity_max)
            )
            if severity == 0 or float(disorder.random()) >= self.config.treatment_probability:
                return LatentDisorderState(self.kind, onset, severity)
            response = float(
                disorder.uniform(
                    self.config.treatment_response_min, self.config.treatment_response_max
                )
            )
            treatment_start = _checked_age_sum(
                "growth hormone deficiency treatment start age_days",
                onset,
                self._treatment_start_offset(),
            )
        except (ArithmeticError, TypeError, ValueError) as exc:
            raise ValueError("growth hormone deficiency state cannot be sampled") from exc
        return LatentDisorderState(
            self.kind,
            onset,
            severity,
            treatment_start_age_days=treatment_start,
            treatment_response=response,
        )

    def _treatment_start_offset(self) -> int:
        return _checked_age_sum(
            "growth hormone deficiency treatment start offset",
            self.config.phenotype_delay_days
            + self.config.recognition_delay_days
            + self.config.workup_delay_days
            + self.config.diagnosis_delay_days
            + self.config.treatment_delay_days
        )

    def _untreated_height_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
        assert state.onset_age_days is not None
        if age_days < state.onset_age_days:
            return 0.0
        try:
            fraction = min(
                (age_days - state.onset_age_days) / self.config.progression_days,
                1.0,
            )
            delta = -state.severity * fraction
        except (ArithmeticError, TypeError, ValueError) as exc:
            raise ValueError("age_days is too large for disorder arithmetic") from exc
        return _require_finite_real("growth hormone deficiency height z-score delta", delta)

    def height_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
        _require_module_state(state, self.kind)
        age = _require_age("age_days", age_days)
        if state.onset_age_days is None:
            raise ValueError("growth hormone deficiency requires an onset age")
        untreated = self._untreated_height_z_delta(state, age)
        treatment_start = state.treatment_start_age_days
        if treatment_start is None or age <= treatment_start:
            return untreated
        try:
            at_treatment = self._untreated_height_z_delta(state, treatment_start)
            recovery_fraction = min(
                (age - treatment_start) / self.config.response_days,
                1.0,
            )
            recovered = at_treatment * (1 - state.treatment_response)
            delta = at_treatment + (recovered - at_treatment) * recovery_fraction
        except (ArithmeticError, TypeError, ValueError) as exc:
            raise ValueError("age_days is too large for disorder arithmetic") from exc
        return _require_finite_real("growth hormone deficiency height z-score delta", delta)

    def bmi_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
        _require_module_state(state, self.kind)
        _require_age("age_days", age_days)
        if state.severity == 0:
            return 0.0
        try:
            untreated_fraction = min(
                max(-self.height_z_delta(state, age_days) / state.severity, 0.0), 1.0
            )
            delta = self.config.bmi_z_max_delta * untreated_fraction
        except (ArithmeticError, TypeError, ValueError) as exc:
            raise ValueError("age_days is too large for disorder arithmetic") from exc
        return _require_finite_real("growth hormone deficiency BMI z-score delta", delta)

    def events(
        self, patient: PatientState, state: LatentDisorderState
    ) -> tuple[ClinicalEvent, ...]:
        _require_module_state(state, self.kind)
        if state.onset_age_days is None:
            raise ValueError("growth hormone deficiency requires an onset age")
        onset = state.onset_age_days
        if state.severity == 0:
            return _ordered_events(patient, (("latent_onset", onset),))
        phenotype_age = _checked_age_sum(
            "growth hormone deficiency phenotype age_days",
            onset,
            self.config.phenotype_delay_days,
        )
        recognition_age = _checked_age_sum(
            "growth hormone deficiency recognition age_days",
            phenotype_age,
            self.config.recognition_delay_days,
        )
        workup_age = _checked_age_sum(
            "growth hormone deficiency workup age_days",
            recognition_age,
            self.config.workup_delay_days,
        )
        diagnosis_age = _checked_age_sum(
            "growth hormone deficiency diagnosis age_days",
            workup_age,
            self.config.diagnosis_delay_days,
        )
        schedule: tuple[tuple[str, int], ...] = (
            ("latent_onset", onset),
            ("observable_phenotype", phenotype_age),
            ("recognition_opportunity", recognition_age),
            ("workup", workup_age),
            ("recorded_diagnosis", diagnosis_age),
        )
        if state.treatment_start_age_days is None:
            return _ordered_events(patient, schedule)
        expected_treatment_start = _checked_age_sum(
            "growth hormone deficiency treatment start age_days",
            diagnosis_age,
            self.config.treatment_delay_days,
        )
        if state.treatment_start_age_days != expected_treatment_start:
            raise ValueError("treatment start does not match the configured causal schedule")
        response_age = _checked_age_sum(
            "growth hormone deficiency treatment response age_days",
            state.treatment_start_age_days,
            self.config.response_days,
        )
        return _ordered_events(
            patient,
            schedule
            + (
                ("treatment_start", state.treatment_start_age_days),
                (
                    "treatment_response"
                    if state.treatment_response > 0
                    else "treatment_nonresponse",
                    response_age,
                ),
            ),
        )
