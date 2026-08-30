"""Development-only latent growth-disorder scenarios.

The default values describe uncalibrated scenarios. They are deliberately not
prevalence estimates or clinically validated parameterizations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from synthetic.models import ClinicalEvent, DisorderKind, LatentDisorderState, PatientState
from synthetic.randomness import NamedRandomStreams

_PHASE_ORDER = {
    "latent_onset": 0,
    "observable_phenotype": 1,
    "recognition_opportunity": 2,
    "workup": 3,
    "recorded_diagnosis": 4,
    "treatment_start": 5,
    "treatment_response": 6,
}


class GrowthDisorderModule(Protocol):
    kind: DisorderKind

    def sample_state(
        self, patient: PatientState, streams: NamedRandomStreams
    ) -> LatentDisorderState: ...

    def height_z_delta(self, state: LatentDisorderState, age_days: int) -> float: ...

    def bmi_z_delta(self, state: LatentDisorderState, age_days: int) -> float: ...

    def events(
        self, patient: PatientState, state: LatentDisorderState
    ) -> tuple[ClinicalEvent, ...]: ...


def _require_age(name: str, value: object, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    if positive and value == 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _require_magnitude(name: str, value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(f"{name} must be finite and nonnegative")
    return float(value)


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


def _require_module_state(state: LatentDisorderState, kind: DisorderKind) -> None:
    if state.kind is not kind:
        raise ValueError(f"state kind must be {kind.value}")


def _ordered_events(
    patient: PatientState, schedule: tuple[tuple[str, int], ...]
) -> tuple[ClinicalEvent, ...]:
    previous_phase = -1
    previous_age = -1
    for event_type, age_days in schedule:
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
    """Empty configuration retained for a uniform versioned module interface."""


class HealthyGrowthModule:
    kind = DisorderKind.HEALTHY

    def __init__(self, config: HealthyGrowthConfig | None = None) -> None:
        self.config = config or HealthyGrowthConfig()

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

    severity_min: float = 0.7
    severity_max: float = 1.3
    onset_age_days: int = 0
    phenotype_age_days: int = 730
    recognition_age_days: int = 1460
    workup_age_days: int = 1825
    diagnosis_age_days: int = 2190

    def __post_init__(self) -> None:
        _require_ordered_bounds("severity_min", self.severity_min, "severity_max", self.severity_max)
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

    def __init__(self, config: FamilialShortStatureConfig | None = None) -> None:
        self.config = config or FamilialShortStatureConfig()

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


class ConstitutionalDelayModule:
    kind = DisorderKind.CONSTITUTIONAL_DELAY

    def __init__(self, config: ConstitutionalDelayConfig | None = None) -> None:
        self.config = config or ConstitutionalDelayConfig()

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
        delayed_end = puberty_age + state.puberty_delay_days
        if age < puberty_age or state.puberty_delay_days == 0:
            return 0.0
        if age <= delayed_end:
            return -state.severity * (age - puberty_age) / state.puberty_delay_days
        elapsed_recovery = age - delayed_end
        if elapsed_recovery >= self.config.recovery_days:
            return 0.0
        return -state.severity * (1 - elapsed_recovery / self.config.recovery_days)

    def bmi_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
        _require_module_state(state, self.kind)
        _require_age("age_days", age_days)
        return 0.0

    def events(
        self, patient: PatientState, state: LatentDisorderState
    ) -> tuple[ClinicalEvent, ...]:
        _require_module_state(state, self.kind)
        puberty_age = self.config.expected_puberty_age_days
        delayed_end = puberty_age + state.puberty_delay_days
        phenotype_age = puberty_age + state.puberty_delay_days // 2
        recognition_age = delayed_end + self.config.recognition_delay_days
        workup_age = recognition_age + self.config.workup_delay_days
        diagnosis_age = workup_age + self.config.diagnosis_delay_days
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


class GrowthHormoneDeficiencyModule:
    kind = DisorderKind.GROWTH_HORMONE_DEFICIENCY

    def __init__(self, config: GrowthHormoneDeficiencyConfig | None = None) -> None:
        self.config = config or GrowthHormoneDeficiencyConfig()

    def sample_state(
        self, patient: PatientState, streams: NamedRandomStreams
    ) -> LatentDisorderState:
        disorder = streams.generator(f"disorder.{self.kind.value}")
        onset = int(
            disorder.integers(self.config.onset_min_age_days, self.config.onset_max_age_days + 1)
        )
        severity = float(disorder.uniform(self.config.severity_min, self.config.severity_max))
        if float(disorder.random()) >= self.config.treatment_probability:
            return LatentDisorderState(self.kind, onset, severity)
        response = float(
            disorder.uniform(
                self.config.treatment_response_min, self.config.treatment_response_max
            )
        )
        treatment_start = onset + self._treatment_start_offset()
        return LatentDisorderState(
            self.kind,
            onset,
            severity,
            treatment_start_age_days=treatment_start,
            treatment_response=response,
        )

    def _treatment_start_offset(self) -> int:
        return (
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
        fraction = min((age_days - state.onset_age_days) / self.config.progression_days, 1.0)
        return -state.severity * fraction

    def height_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
        _require_module_state(state, self.kind)
        age = _require_age("age_days", age_days)
        if state.onset_age_days is None:
            raise ValueError("growth hormone deficiency requires an onset age")
        untreated = self._untreated_height_z_delta(state, age)
        treatment_start = state.treatment_start_age_days
        if treatment_start is None or age <= treatment_start:
            return untreated
        at_treatment = self._untreated_height_z_delta(state, treatment_start)
        recovery_fraction = min((age - treatment_start) / self.config.response_days, 1.0)
        recovered = at_treatment * (1 - state.treatment_response)
        return at_treatment + (recovered - at_treatment) * recovery_fraction

    def bmi_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
        _require_module_state(state, self.kind)
        _require_age("age_days", age_days)
        if state.severity == 0:
            return 0.0
        untreated_fraction = min(
            max(-self.height_z_delta(state, age_days) / state.severity, 0.0), 1.0
        )
        return self.config.bmi_z_max_delta * untreated_fraction

    def events(
        self, patient: PatientState, state: LatentDisorderState
    ) -> tuple[ClinicalEvent, ...]:
        _require_module_state(state, self.kind)
        if state.onset_age_days is None:
            raise ValueError("growth hormone deficiency requires an onset age")
        onset = state.onset_age_days
        phenotype_age = onset + self.config.phenotype_delay_days
        recognition_age = phenotype_age + self.config.recognition_delay_days
        workup_age = recognition_age + self.config.workup_delay_days
        diagnosis_age = workup_age + self.config.diagnosis_delay_days
        schedule: tuple[tuple[str, int], ...] = (
            ("latent_onset", onset),
            ("observable_phenotype", phenotype_age),
            ("recognition_opportunity", recognition_age),
            ("workup", workup_age),
            ("recorded_diagnosis", diagnosis_age),
        )
        if state.treatment_start_age_days is None:
            return _ordered_events(patient, schedule)
        expected_treatment_start = diagnosis_age + self.config.treatment_delay_days
        if state.treatment_start_age_days != expected_treatment_start:
            raise ValueError("treatment start does not match the configured causal schedule")
        return _ordered_events(
            patient,
            schedule
            + (
                ("treatment_start", state.treatment_start_age_days),
                ("treatment_response", state.treatment_start_age_days + self.config.response_days),
            ),
        )
