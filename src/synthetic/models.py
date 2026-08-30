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


class GrowthRegime(str, Enum):
    INFANCY = "infancy"
    TRANSITION = "transition"
    CHILDHOOD = "childhood"
    PUBERTY = "puberty"
    ADOLESCENCE = "adolescence"


@dataclass(frozen=True)
class AgeRegimeState:
    module_version: str
    birth_length_z: float
    birth_weight_z: float
    head_circumference_z: float
    childhood_height_z: float
    childhood_bmi_z: float
    puberty_onset_age_days: int
    puberty_tempo_days: int
    puberty_height_spurt_z: float
    puberty_bmi_shift_z: float

    def __post_init__(self) -> None:
        if not isinstance(self.module_version, str) or not self.module_version:
            raise ValueError("module_version must be a nonempty string")
        for name in ("birth_length_z", "birth_weight_z", "head_circumference_z",
                     "childhood_height_z", "childhood_bmi_z", "puberty_height_spurt_z",
                     "puberty_bmi_shift_z"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if (isinstance(self.puberty_onset_age_days, bool)
                or not isinstance(self.puberty_onset_age_days, int)
                or self.puberty_onset_age_days < 0):
            raise ValueError("puberty_onset_age_days must be a nonnegative integer")
        if (isinstance(self.puberty_tempo_days, bool)
                or not isinstance(self.puberty_tempo_days, int)
                or self.puberty_tempo_days <= 0):
            raise ValueError("puberty_tempo_days must be a positive integer")


@dataclass(frozen=True)
class AgeRegimePoint:
    patient_id: str
    age_days: int
    regime: GrowthRegime
    length_cm: float | None
    height_cm: float | None
    weight_kg: float
    bmi: float | None
    head_circumference_cm: float | None = None
    length_z: float | None = None
    height_z: float | None = None
    weight_z: float | None = None
    bmi_z: float | None = None
    height_velocity_cm_per_year: float | None = None
    weight_velocity_kg_per_year: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.patient_id, str) or not self.patient_id:
            raise ValueError("patient_id must be nonempty")
        if isinstance(self.age_days, bool) or not isinstance(self.age_days, int) or self.age_days < 0:
            raise ValueError("age_days must be a nonnegative integer")
        if not isinstance(self.regime, GrowthRegime):
            raise ValueError("regime must be a GrowthRegime")  # noqa: TRY004
        for name in ("weight_kg", "length_cm", "height_cm", "bmi", "head_circumference_cm"):
            value = getattr(self, name)
            if name == "weight_kg" and value is None:
                raise ValueError("weight_kg must be finite and positive")
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0):
                raise ValueError(f"{name} must be finite and positive")
        for name in ("length_z", "height_z", "weight_z", "bmi_z", "height_velocity_cm_per_year", "weight_velocity_kg_per_year"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
                raise ValueError(f"{name} must be finite")
        if self.regime is GrowthRegime.INFANCY and self.length_cm is None:
            raise ValueError("infancy requires length")
        if self.regime is GrowthRegime.TRANSITION and (self.length_cm is None or self.height_cm is None):
            raise ValueError("transition requires length and standing height")
        if self.regime in (GrowthRegime.CHILDHOOD, GrowthRegime.PUBERTY, GrowthRegime.ADOLESCENCE) and (self.height_cm is None or self.bmi is None):
            raise ValueError("this regime requires standing height and BMI")
        if self.regime is not GrowthRegime.INFANCY and self.length_cm is not None and self.regime is not GrowthRegime.TRANSITION:
            raise ValueError("length is not accepted after transition")
        if self.height_cm is not None and self.bmi is not None:
            try:
                expected = self.bmi * (self.height_cm / 100) ** 2
            except OverflowError as exc:
                raise ValueError("weight does not match height and BMI") from exc
            if not math.isfinite(expected):
                raise ValueError("weight does not match height and BMI")
            if not math.isclose(self.weight_kg, expected, rel_tol=1e-9, abs_tol=1e-9):
                raise ValueError("weight does not match height and BMI")


@dataclass(frozen=True)
class AgeRegimeTrajectory:
    points: tuple[AgeRegimePoint, ...]
    state: AgeRegimeState

    def __post_init__(self) -> None:
        if not isinstance(self.points, tuple) or not self.points or not all(isinstance(p, AgeRegimePoint) for p in self.points):
            raise ValueError("points must be a nonempty tuple of AgeRegimePoint")
        if not isinstance(self.state, AgeRegimeState):
            raise ValueError("state must be an AgeRegimeState")  # noqa: TRY004
        patient = self.points[0].patient_id
        if any(p.patient_id != patient for p in self.points):
            raise ValueError("points must have one patient")
        if any(a.age_days >= b.age_days for a, b in zip(self.points, self.points[1:])):
            raise ValueError("points must be strictly increasing by age")
