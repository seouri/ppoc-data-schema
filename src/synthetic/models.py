import math
from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class PatientState:
    patient_id: str
    recorded_sex: str
    reference_sex: str


@dataclass(frozen=True)
class LatentPoint:
    patient_id: str
    age_days: int
    height_cm: float
    bmi: float
    weight_kg: float
    height_z: float
    bmi_z: float


@dataclass(frozen=True)
class ObservedVisit:
    patient_id: str
    visit_id: str
    age_days: int
    encounter_type: str
    height_in: float | None
    weight_oz: float | None
    epic_bmi: float | None


@dataclass(frozen=True)
class ClinicalEvent:
    patient_id: str
    age_days: int
    event_type: str
    code: str | None
    hidden: bool


class DisorderKind(str, Enum):
    HEALTHY = "healthy"
    FAMILIAL_SHORT_STATURE = "familial_short_stature"
    CONSTITUTIONAL_DELAY = "constitutional_delay"
    GROWTH_HORMONE_DEFICIENCY = "growth_hormone_deficiency"


@dataclass(frozen=True)
class LatentDisorderState:
    kind: DisorderKind
    onset_age_days: int | None
    severity: float
    puberty_delay_days: int = 0
    treatment_start_age_days: int | None = None
    treatment_response: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DisorderKind):
            raise ValueError("kind must be a DisorderKind")  # noqa: TRY004
        for name, age in (
            ("onset_age_days", self.onset_age_days),
            ("treatment_start_age_days", self.treatment_start_age_days),
        ):
            if age is not None and (isinstance(age, bool) or not isinstance(age, int) or age < 0):
                raise ValueError(f"{name} must be a nonnegative integer or None")
        if (
            isinstance(self.puberty_delay_days, bool)
            or not isinstance(self.puberty_delay_days, int)
            or self.puberty_delay_days < 0
        ):
            raise ValueError("puberty_delay_days must be a nonnegative integer")
        if (
            not isinstance(self.severity, (int, float))
            or not math.isfinite(self.severity)
            or self.severity < 0
        ):
            raise ValueError("severity must be finite and nonnegative")
        if (
            self.onset_age_days is not None
            and self.treatment_start_age_days is not None
            and self.treatment_start_age_days < self.onset_age_days
        ):
            raise ValueError("treatment must not precede onset")
        if (
            not isinstance(self.treatment_response, (int, float))
            or not math.isfinite(self.treatment_response)
            or not 0 <= self.treatment_response <= 1
        ):
            raise ValueError("treatment_response must be finite and in [0, 1]")
        if self.treatment_start_age_days is None and self.treatment_response != 0:
            raise ValueError(
                "nonzero treatment_response requires treatment_start_age_days"
            )


@dataclass(frozen=True)
class LatentTrajectory:
    points: tuple[LatentPoint, ...]
    disorder: LatentDisorderState
    events: tuple[ClinicalEvent, ...]
