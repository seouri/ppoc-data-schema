import math
from dataclasses import dataclass, fields
from enum import Enum

# Shared evaluator age bound. The native clinical modules feed age ranges to
# NumPy's signed-int64 sampler, whose exclusive upper bound must also fit.
MAX_AGE_DAYS = (1 << 63) - 2


def _is_finite_numeric(value: object) -> bool:
    """Return whether a model numeric is finite without leaking conversion errors."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def _is_nonnegative_age(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, int)
        and 0 <= value <= MAX_AGE_DAYS
    )


_DISORDER_EVENT_PHASE_ORDER = {
    "latent_onset": 0,
    "observable_phenotype": 1,
    "recognition_opportunity": 2,
    "workup": 3,
    "recorded_diagnosis": 4,
    "treatment_start": 5,
    "treatment_response": 6,
    "treatment_nonresponse": 6,
}
_DISORDER_EVENT_TYPES = frozenset(_DISORDER_EVENT_PHASE_ORDER)


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

    def __post_init__(self) -> None:
        if not _is_nonnegative_age(self.age_days):
            raise ValueError("age_days must be a nonnegative integer within the supported age range")


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
    PEDIATRIC_HYPOTHYROIDISM = "pediatric_hypothyroidism"
    CELIAC_DISEASE = "celiac_disease"
    SMALL_FOR_GESTATIONAL_AGE = "small_for_gestational_age"
    TURNER_SYNDROME = "turner_syndrome"
    UNDERNUTRITION = "undernutrition"
    EXCESS_WEIGHT = "excess_weight"


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
            if age is not None and not _is_nonnegative_age(age):
                raise ValueError(f"{name} must be a nonnegative integer or None")
        if (
            not _is_nonnegative_age(self.puberty_delay_days)
        ):
            raise ValueError("puberty_delay_days must be a nonnegative integer")
        if (
            not _is_finite_numeric(self.severity)
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
            not _is_finite_numeric(self.treatment_response)
            or not 0 <= self.treatment_response <= 1
        ):
            raise ValueError("treatment_response must be finite and in [0, 1]")
        if self.treatment_start_age_days is None and self.treatment_response != 0:
            raise ValueError(
                "nonzero treatment_response requires treatment_start_age_days"
            )


def validate_disorder_event_trace(
    patient_id: str,
    state: LatentDisorderState,
    events: tuple[ClinicalEvent, ...],
) -> None:
    """Validate evaluator-only disorder events without importing native kernels."""

    zero_effect = (
        state.severity == 0
        and state.puberty_delay_days == 0
        and state.treatment_start_age_days is None
        and state.treatment_response == 0
    )
    if not events and state.kind is not DisorderKind.HEALTHY and not zero_effect:
        raise ValueError("active nonhealthy disorder state requires a latent_onset event")

    previous_age = -1
    previous_phase = -1
    latent_onset_seen = False
    treatment_start_seen = False
    treatment_outcome_seen: str | None = None
    for event in events:
        if event.patient_id != patient_id:
            raise ValueError("module event patient ID must match the requested patient")
        if not _is_nonnegative_age(event.age_days):
            raise ValueError("module event age must be within supported age range")
        if event.age_days < previous_age:
            raise ValueError("module event ages must be nondecreasing")
        if not isinstance(event.event_type, str):
            raise ValueError("module event_type must be a string")  # noqa: TRY004
        phase = _DISORDER_EVENT_PHASE_ORDER.get(event.event_type)
        if phase is None:
            raise ValueError(f"unknown clinical event type: {event.event_type}")
        if event.code is not None:
            raise ValueError("module events must have code=None")
        if type(event.hidden) is not bool:
            raise ValueError("module event hidden must be a boolean")
        expected_hidden = event.event_type == "latent_onset"
        if event.hidden is not expected_hidden:
            raise ValueError("module event hidden flag is invalid")
        if event.event_type == "latent_onset":
            if state.onset_age_days is None or event.age_days != state.onset_age_days:
                raise ValueError("latent_onset must match state onset age")
            latent_onset_seen = True
        elif not latent_onset_seen:
            raise ValueError("module event schedule must begin with latent_onset")
        if treatment_outcome_seen is not None:
            raise ValueError("treatment outcome events are terminal")
        if phase <= previous_phase:
            raise ValueError("module event schedule must follow causal phase order")

        if event.event_type == "treatment_start":
            if (
                state.treatment_start_age_days is None
                or event.age_days != state.treatment_start_age_days
                or treatment_start_seen
            ):
                raise ValueError(
                    "treatment start event does not match the treatment schedule"
                )
            treatment_start_seen = True
        elif event.event_type in {"treatment_response", "treatment_nonresponse"}:
            if state.treatment_start_age_days is None or not treatment_start_seen:
                raise ValueError(
                    f"{event.event_type} requires a prior treatment_start event"
                )
            if event.age_days <= state.treatment_start_age_days:
                raise ValueError(f"{event.event_type} must occur after treatment start")
            if event.event_type == "treatment_response" and state.treatment_response <= 0:
                raise ValueError(
                    "treatment_response event requires state.treatment_response > 0"
                )
            if (
                event.event_type == "treatment_nonresponse"
                and state.treatment_response != 0
            ):
                raise ValueError(
                    "treatment_nonresponse event requires state.treatment_response == 0"
                )
            treatment_outcome_seen = event.event_type

        previous_age = event.age_days
        previous_phase = phase

    if state.treatment_start_age_days is not None:
        if not treatment_start_seen:
            raise ValueError(
                "treatment-bearing state requires a matching treatment_start event"
            )
        expected_outcome = (
            "treatment_response"
            if state.treatment_response > 0
            else "treatment_nonresponse"
        )
        if treatment_outcome_seen != expected_outcome:
            raise ValueError(
                "treatment-bearing state requires exactly one matching terminal treatment outcome"
            )


@dataclass(frozen=True)
class LatentTrajectory:
    points: tuple[LatentPoint, ...]
    disorder: LatentDisorderState
    events: tuple[ClinicalEvent, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.points, tuple)
            or not self.points
            or not all(isinstance(point, LatentPoint) for point in self.points)
        ):
            raise ValueError("points must be a nonempty tuple of LatentPoint")
        if not isinstance(self.disorder, LatentDisorderState):
            raise TypeError("disorder must be a LatentDisorderState")
        if not isinstance(self.events, tuple):
            raise ValueError(  # noqa: TRY004
                "events must be a tuple of ClinicalEvent"
            )
        if not all(isinstance(event, ClinicalEvent) for event in self.events):
            raise ValueError("events must be a tuple of ClinicalEvent")

        for event in self.events:
            if not _is_nonnegative_age(event.age_days):
                raise ValueError(
                    "event age_days must be a nonnegative integer within the supported age range"
                )
            if not isinstance(event.event_type, str):
                raise ValueError("event_type must be a string")  # noqa: TRY004
            if event.event_type not in _DISORDER_EVENT_TYPES:
                raise ValueError(f"unknown event_type: {event.event_type}")
            if event.code is not None:
                raise ValueError("latent trajectory events must have code=None")
            if type(event.hidden) is not bool:
                raise ValueError("event hidden must be a boolean")
            if event.hidden is not (event.event_type == "latent_onset"):
                raise ValueError("event hidden flag is invalid")

        patient_id = self.points[0].patient_id
        if any(point.patient_id != patient_id for point in self.points):
            raise ValueError("points must have one patient")
        if any(event.patient_id != patient_id for event in self.events):
            raise ValueError("events must have one patient")
        if any(
            previous.age_days >= current.age_days
            for previous, current in zip(self.points, self.points[1:])
        ):
            raise ValueError("points must be strictly increasing by age")


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
            if not _is_finite_numeric(value):
                raise ValueError(f"{name} must be finite")
        if not _is_nonnegative_age(self.puberty_onset_age_days):
            raise ValueError("puberty_onset_age_days must be a nonnegative integer")
        if not _is_nonnegative_age(self.puberty_tempo_days) or self.puberty_tempo_days <= 0:
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
        if not _is_nonnegative_age(self.age_days):
            raise ValueError("age_days must be a nonnegative integer")
        if not isinstance(self.regime, GrowthRegime):
            raise ValueError("regime must be a GrowthRegime")  # noqa: TRY004
        for name in ("weight_kg", "length_cm", "height_cm", "bmi", "head_circumference_cm"):
            value = getattr(self, name)
            if name == "weight_kg" and value is None:
                raise ValueError("weight_kg must be finite and positive")
            if value is not None and (
                not _is_finite_numeric(value) or value <= 0
            ):
                raise ValueError(f"{name} must be finite and positive")
        for name in ("length_z", "height_z", "weight_z", "bmi_z", "height_velocity_cm_per_year", "weight_velocity_kg_per_year"):
            value = getattr(self, name)
            if value is not None and not _is_finite_numeric(value):
                raise ValueError(f"{name} must be finite")
        if self.regime is GrowthRegime.INFANCY and (
            self.height_cm is not None or self.bmi is not None
        ):
            raise ValueError("infancy does not accept standing height or BMI")
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


@dataclass(frozen=True)
class AgeRegimeDisorderTrajectory:
    physiology: AgeRegimeTrajectory
    disorder: LatentDisorderState
    events: tuple[ClinicalEvent, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.physiology, AgeRegimeTrajectory):
            raise TypeError("physiology must be an AgeRegimeTrajectory")
        if not isinstance(self.disorder, LatentDisorderState):
            raise TypeError("disorder must be a LatentDisorderState")
        if not isinstance(self.events, tuple):
            raise ValueError("events must be a tuple of ClinicalEvent")  # noqa: TRY004
        if not all(isinstance(event, ClinicalEvent) for event in self.events):
            raise ValueError("events must be a tuple of ClinicalEvent")

        points = tuple(
            AgeRegimePoint(
                **{field.name: getattr(point, field.name) for field in fields(AgeRegimePoint)}
            )
            for point in self.physiology.points
        )
        state = AgeRegimeState(
            **{
                field.name: getattr(self.physiology.state, field.name)
                for field in fields(AgeRegimeState)
            }
        )
        physiology = AgeRegimeTrajectory(points, state)
        disorder = LatentDisorderState(
            **{
                field.name: getattr(self.disorder, field.name)
                for field in fields(LatentDisorderState)
            }
        )
        events = tuple(
            ClinicalEvent(
                **{field.name: getattr(event, field.name) for field in fields(ClinicalEvent)}
            )
            for event in self.events
        )
        validate_disorder_event_trace(points[0].patient_id, disorder, events)
        object.__setattr__(self, "physiology", physiology)
        object.__setattr__(self, "disorder", disorder)
        object.__setattr__(self, "events", events)
