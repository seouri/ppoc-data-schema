"""Evaluator-only observation-frame contracts for fictional trajectories.

The types in this module describe the boundary between a native latent growth
trajectory and the observations an evaluator may expose to a development
experiment.  They deliberately do not read files, serialize visible package
resources, or accept real-patient identifiers.  ``ObservationTruth`` and the
opportunity/measurement decision types are private evaluator state; only
``ObservationFrame.to_mapping`` and the aggregate validation report are safe
for ordinary logging.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass, replace
from enum import Enum
from numbers import Real
from types import MappingProxyType
from typing import Any, ClassVar

from synthetic.models import AgeRegimeDisorderTrajectory, ClinicalEvent, GrowthRegime
from synthetic.randomness import NamedRandomStreams

_VERSION_TOKEN = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_SYNTHETIC_PATIENT_TOKEN = re.compile(r"^syn-[A-Za-z0-9][A-Za-z0-9._-]*$")
_SYNTHETIC_VISIT_TOKEN = re.compile(r"^syn-[A-Za-z0-9][A-Za-z0-9._:-]*$")
_HASH_TOKEN = re.compile(r"^[0-9a-f]{64}$")
_OBSERVATION_STREAM_IDENTITY_VERSION = "observation-stream-identity-v1"

OBSERVATION_STREAM_NAMES = (
    "observation.window",
    "observation.censoring",
    "observation.visit.routine",
    "observation.measurement-availability",
    "observation.measurement-error",
    "observation.recognition",
    "observation.recorded-event",
)
_OBSERVATION_STREAM_NAME_SET = frozenset(OBSERVATION_STREAM_NAMES)

_SOURCE_EVENT_PHASES = {
    "latent_onset": 0,
    "observable_phenotype": 1,
    "recognition_opportunity": 2,
    "workup": 3,
    "recorded_diagnosis": 4,
    "treatment_start": 5,
    "treatment_response": 6,
    "treatment_nonresponse": 6,
}
_DEFERRED_SOURCE_EVENT_TYPES = frozenset(
    {"latent_onset", "observable_phenotype", "treatment_start", "treatment_response", "treatment_nonresponse"}
)

# Native trajectory modules currently emit only these event types.  Their
# events retain ``code=None`` until a reviewed terminology/resource contract
# exists; the observation truth boundary must not admit arbitrary codes.
_SOURCE_EVENT_TYPES = frozenset(
    {
        "latent_onset",
        "observable_phenotype",
        "recognition_opportunity",
        "workup",
        "recorded_diagnosis",
        "treatment_start",
        "treatment_response",
        "treatment_nonresponse",
    }
)


class CensoringMode(str, Enum):
    """Closed vocabulary for how a policy ends its observation window."""

    NONE = "none"
    ADMINISTRATIVE_END = "administrative_end"
    LOST_TO_FOLLOW_UP = "lost_to_follow_up"


class EncounterType(str, Enum):
    """Closed fictional encounter vocabulary for this first observation layer."""

    ROUTINE = "routine"


class MeasurementChannel(str, Enum):
    """Anthropometric channels supported by the evaluator observation frame."""

    LENGTH = "length"
    HEIGHT = "height"
    WEIGHT = "weight"
    HEAD_CIRCUMFERENCE = "head_circumference"
    BMI = "bmi"


class MeasurementAvailability(str, Enum):
    """Whether a channel is structurally applicable and recorded."""

    NOT_APPLICABLE = "not_applicable"
    MISSING = "missing"
    OBSERVED = "observed"


class RecordedEventKind(str, Enum):
    """Closed recorded descendants of observable native event evidence."""

    RECOGNITION = "recognition"
    WORKUP = "workup"
    DIAGNOSIS = "diagnosis"


_PHYSICAL_CHANNELS = (
    MeasurementChannel.LENGTH,
    MeasurementChannel.HEIGHT,
    MeasurementChannel.WEIGHT,
    MeasurementChannel.HEAD_CIRCUMFERENCE,
)


# These codes are intentionally fictional.  A later package/resource contract
# may choose a different registry, but this evaluator layer must not accept a
# caller-provided code that could be mistaken for a real clinical terminology.
RECORDED_EVENT_CODES: Mapping[RecordedEventKind, str] = MappingProxyType(
    {
        RecordedEventKind.RECOGNITION: "SYN-GROWTH-RECOGNITION",
        RecordedEventKind.WORKUP: "SYN-GROWTH-WORKUP",
        RecordedEventKind.DIAGNOSIS: "SYN-GROWTH-DIAGNOSIS",
    }
)


def _require_token(value: object, name: str) -> str:
    if not isinstance(value, str) or not _VERSION_TOKEN.fullmatch(value):
        raise ValueError(f"{name} must be a nonempty token")
    return value


def _require_synthetic_patient_id(value: object, name: str = "patient_id") -> str:
    if not isinstance(value, str) or not _SYNTHETIC_PATIENT_TOKEN.fullmatch(value):
        raise ValueError(f"{name} must identify a fictional synthetic patient")
    return value


def _require_synthetic_visit_id(value: object) -> str:
    if not isinstance(value, str) or not _SYNTHETIC_VISIT_TOKEN.fullmatch(value):
        raise ValueError("visit_id must be a safe synthetic token")
    return value


def _require_nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _require_positive_int(value: object, name: str) -> int:
    result = _require_nonnegative_int(value, name)
    if result <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return result


def _require_finite_real(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return float(value)


def _require_probability(value: object, name: str) -> float:
    result = _require_finite_real(value, name)
    if not 0 <= result <= 1:
        raise ValueError(f"{name} must be a probability in [0, 1]")
    return result


def _require_nonnegative_real(value: object, name: str) -> float:
    result = _require_finite_real(value, name)
    if result < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return result


def _require_positive_real(value: object, name: str) -> float:
    result = _require_finite_real(value, name)
    if result <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return result


def _require_optional_nonnegative_int(value: object, name: str) -> int | None:
    if value is None:
        return None
    return _require_nonnegative_int(value, name)


def _require_enum(value: object, enum_type: type[Enum], name: str) -> Enum:
    if not isinstance(value, enum_type):
        raise TypeError(f"{name} must be a {enum_type.__name__}")
    return value


def _require_tuple(value: object, name: str) -> tuple[Any, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple")
    return value


def _require_hash(value: object, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _HASH_TOKEN.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 hash or None")
    return value


def observation_stream_identity(name: str) -> str:
    """Return the stable opaque identity for one declared observation stream."""

    if not isinstance(name, str) or name not in _OBSERVATION_STREAM_NAME_SET:
        raise ValueError("stream must be one of the declared observation streams")
    material = f"{_OBSERVATION_STREAM_IDENTITY_VERSION}\x1f{name}".encode()
    return hashlib.sha256(material).hexdigest()


# A readable compatibility alias for callers that used the adjective form in
# early evaluator notebooks.  Both names are the same strict function.
observed_stream_identity = observation_stream_identity


@dataclass(frozen=True)
class ObservationPolicy:
    """Immutable, closed policy for one evaluator observation frame."""

    policy_version: str
    window_start_age_days: int
    window_end_age_days: int
    censoring_mode: CensoringMode = CensoringMode.NONE
    censor_age_days: int | None = None
    visit_probability: float = 1.0
    length_availability_probability: float = 1.0
    height_availability_probability: float = 1.0
    weight_availability_probability: float = 1.0
    head_circumference_availability_probability: float = 1.0
    length_error_sd_cm: float = 0.0
    height_error_sd_cm: float = 0.0
    weight_error_sd_kg: float = 0.0
    head_circumference_error_sd_cm: float = 0.0
    rounding_digits: int | None = None
    recognition_probability: float = 0.0
    diagnosis_probability: float = 0.0
    recognition_delay_days: int = 0

    _MAPPING_KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "policy_version",
            "window_start_age_days",
            "window_end_age_days",
            "censoring_mode",
            "censor_age_days",
            "visit_probability",
            "length_availability_probability",
            "height_availability_probability",
            "weight_availability_probability",
            "head_circumference_availability_probability",
            "length_error_sd_cm",
            "height_error_sd_cm",
            "weight_error_sd_kg",
            "head_circumference_error_sd_cm",
            "rounding_digits",
            "recognition_probability",
            "diagnosis_probability",
            "recognition_delay_days",
        }
    )

    def __post_init__(self) -> None:
        _require_token(self.policy_version, "policy_version")
        start = _require_nonnegative_int(self.window_start_age_days, "window_start_age_days")
        end = _require_positive_int(self.window_end_age_days, "window_end_age_days")
        if start >= end:
            raise ValueError("observation window start must precede window end")
        _require_enum(self.censoring_mode, CensoringMode, "censoring_mode")
        censor = _require_optional_nonnegative_int(self.censor_age_days, "censor_age_days")
        if self.censoring_mode is CensoringMode.NONE and censor is not None:
            raise ValueError("censor_age_days requires an explicit censoring mode")
        if self.censoring_mode is CensoringMode.ADMINISTRATIVE_END and censor not in (None, end):
            raise ValueError("administrative censoring must end at the administrative window bound")
        if self.censoring_mode is CensoringMode.LOST_TO_FOLLOW_UP and (
            censor is None or not start < censor < end
        ):
            raise ValueError("lost-to-follow-up censor age must lie inside the window")

        object.__setattr__(self, "window_start_age_days", start)
        object.__setattr__(self, "window_end_age_days", end)
        object.__setattr__(self, "censor_age_days", censor)
        for name in (
            "visit_probability",
            "length_availability_probability",
            "height_availability_probability",
            "weight_availability_probability",
            "head_circumference_availability_probability",
            "recognition_probability",
            "diagnosis_probability",
        ):
            object.__setattr__(self, name, _require_probability(getattr(self, name), name))
        for name in (
            "length_error_sd_cm",
            "height_error_sd_cm",
            "weight_error_sd_kg",
            "head_circumference_error_sd_cm",
        ):
            object.__setattr__(self, name, _require_nonnegative_real(getattr(self, name), name))
        if self.rounding_digits is not None:
            rounding_digits = _require_nonnegative_int(self.rounding_digits, "rounding_digits")
            if rounding_digits > 6:
                raise ValueError("rounding_digits must be at most six")
            object.__setattr__(self, "rounding_digits", rounding_digits)
        delay = _require_nonnegative_int(self.recognition_delay_days, "recognition_delay_days")
        object.__setattr__(self, "recognition_delay_days", delay)

    @property
    def effective_end_age_days(self) -> int:
        """Return the deterministic end of the policy's effective window."""

        if self.censoring_mode is CensoringMode.LOST_TO_FOLLOW_UP:
            assert self.censor_age_days is not None
            return self.censor_age_days
        return self.window_end_age_days

    def to_mapping(self) -> dict[str, object]:
        """Return the complete safe policy mapping with no hidden run state."""

        return {
            "policy_version": self.policy_version,
            "window_start_age_days": self.window_start_age_days,
            "window_end_age_days": self.window_end_age_days,
            "censoring_mode": self.censoring_mode.value,
            "censor_age_days": self.censor_age_days,
            "visit_probability": self.visit_probability,
            "length_availability_probability": self.length_availability_probability,
            "height_availability_probability": self.height_availability_probability,
            "weight_availability_probability": self.weight_availability_probability,
            "head_circumference_availability_probability": self.head_circumference_availability_probability,
            "length_error_sd_cm": self.length_error_sd_cm,
            "height_error_sd_cm": self.height_error_sd_cm,
            "weight_error_sd_kg": self.weight_error_sd_kg,
            "head_circumference_error_sd_cm": self.head_circumference_error_sd_cm,
            "rounding_digits": self.rounding_digits,
            "recognition_probability": self.recognition_probability,
            "diagnosis_probability": self.diagnosis_probability,
            "recognition_delay_days": self.recognition_delay_days,
        }

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> ObservationPolicy:
        """Parse a complete policy without coercive defaults or unknown keys."""

        if not isinstance(mapping, Mapping) or set(mapping) != cls._MAPPING_KEYS:
            raise ValueError("observation policy mapping must contain exactly the declared keys")
        values = dict(mapping)
        try:
            values["censoring_mode"] = CensoringMode(values["censoring_mode"])
        except (TypeError, ValueError) as exc:
            raise ValueError("censoring_mode must be a declared mode") from exc
        return cls(**values)  # type: ignore[arg-type]


@dataclass(frozen=True)
class ObservationWindow:
    """The policy window after applying its censoring decision."""

    start_age_days: int
    effective_end_age_days: int
    administrative_end_age_days: int
    censoring_mode: CensoringMode

    def __post_init__(self) -> None:
        start = _require_nonnegative_int(self.start_age_days, "start_age_days")
        effective = _require_positive_int(self.effective_end_age_days, "effective_end_age_days")
        administrative = _require_positive_int(
            self.administrative_end_age_days, "administrative_end_age_days"
        )
        if not start < effective <= administrative:
            raise ValueError("observation window ages must be ordered")
        mode = _require_enum(self.censoring_mode, CensoringMode, "censoring_mode")
        if mode is CensoringMode.NONE and effective != administrative:
            raise ValueError("uncensored window must end at the administrative bound")
        if mode is CensoringMode.ADMINISTRATIVE_END and effective != administrative:
            raise ValueError("administrative censoring must use the administrative bound")
        if mode is CensoringMode.LOST_TO_FOLLOW_UP and effective >= administrative:
            raise ValueError("lost-to-follow-up must precede the administrative bound")
        object.__setattr__(self, "start_age_days", start)
        object.__setattr__(self, "effective_end_age_days", effective)
        object.__setattr__(self, "administrative_end_age_days", administrative)

    @property
    def entry_age_days(self) -> int:
        return self.start_age_days

    @property
    def exit_age_days(self) -> int:
        return self.effective_end_age_days

    def to_mapping(self) -> dict[str, object]:
        return {
            "start_age_days": self.start_age_days,
            "effective_end_age_days": self.effective_end_age_days,
            "administrative_end_age_days": self.administrative_end_age_days,
            "censoring_mode": self.censoring_mode.value,
        }


@dataclass(frozen=True, repr=False)
class VisitOpportunity:
    """Private realization decision for a stable latent-point visit opportunity."""

    source_point_index: int
    age_days: int
    encounter_type: EncounterType
    realized: bool

    def __post_init__(self) -> None:
        _require_nonnegative_int(self.source_point_index, "source_point_index")
        _require_nonnegative_int(self.age_days, "age_days")
        _require_enum(self.encounter_type, EncounterType, "encounter_type")
        if not isinstance(self.realized, bool):
            raise TypeError("realized must be a boolean")

    @property
    def trigger(self) -> EncounterType:
        return self.encounter_type

    def __repr__(self) -> str:
        return "VisitOpportunity(<evaluator-only>)"


@dataclass(frozen=True)
class MeasurementObservation:
    """One visible channel/status/value triple."""

    channel: MeasurementChannel
    availability: MeasurementAvailability
    recorded_value: float | None

    def __post_init__(self) -> None:
        _require_enum(self.channel, MeasurementChannel, "channel")
        availability = _require_enum(
            self.availability, MeasurementAvailability, "availability"
        )
        if availability is MeasurementAvailability.OBSERVED:
            value = _require_positive_real(self.recorded_value, "recorded_value")
            object.__setattr__(self, "recorded_value", value)
        elif self.recorded_value is not None:
            raise ValueError("recorded_value must be None when the measurement is unavailable")

    @property
    def value(self) -> float | None:
        return self.recorded_value

    def to_mapping(self) -> dict[str, object]:
        return {
            "channel": self.channel.value,
            "availability": self.availability.value,
            "recorded_value": self.recorded_value,
        }


@dataclass(frozen=True, repr=False)
class MeasurementTruth:
    """Private latent/error decision for one source-point measurement channel."""

    source_point_index: int
    channel: MeasurementChannel
    availability: MeasurementAvailability
    latent_value: float | None
    error_delta: float | None

    def __post_init__(self) -> None:
        _require_nonnegative_int(self.source_point_index, "source_point_index")
        _require_enum(self.channel, MeasurementChannel, "channel")
        availability = _require_enum(
            self.availability, MeasurementAvailability, "availability"
        )
        if availability is MeasurementAvailability.NOT_APPLICABLE:
            if self.latent_value is not None or self.error_delta is not None:
                raise ValueError("not-applicable measurements cannot retain latent values or errors")
        else:
            _require_positive_real(self.latent_value, "latent_value")
            if availability is MeasurementAvailability.MISSING:
                if self.error_delta is not None:
                    raise ValueError("missing measurements cannot retain an error draw")
            else:
                _require_finite_real(self.error_delta, "error_delta")

    def __repr__(self) -> str:
        return "MeasurementTruth(<evaluator-only>)"


@dataclass(frozen=True, repr=False)
class EventRecordingDecision:
    """Private source-event recording decision and its optional visit link."""

    source_event_index: int
    recorded: bool
    opportunity_index: int | None

    def __post_init__(self) -> None:
        _require_nonnegative_int(self.source_event_index, "source_event_index")
        if not isinstance(self.recorded, bool):
            raise TypeError("recorded must be a boolean")
        opportunity = _require_optional_nonnegative_int(
            self.opportunity_index, "opportunity_index"
        )
        if self.recorded and opportunity is None:
            raise ValueError("recorded event decisions require an opportunity link")
        if not self.recorded and opportunity is not None:
            raise ValueError("unrecorded event decisions must have a null opportunity link")
        object.__setattr__(self, "opportunity_index", opportunity)

    def __repr__(self) -> str:
        return "EventRecordingDecision(<evaluator-only>)"


@dataclass(frozen=True)
class RecordedEvent:
    """One visible fictional event descendant."""

    patient_id: str
    age_days: int
    event_kind: RecordedEventKind
    code: str
    opportunity_index: int | None = None

    def __post_init__(self) -> None:
        _require_synthetic_patient_id(self.patient_id)
        _require_nonnegative_int(self.age_days, "age_days")
        kind = _require_enum(self.event_kind, RecordedEventKind, "event_kind")
        expected_code = RECORDED_EVENT_CODES.get(kind)
        if self.code != expected_code:
            raise ValueError("code must be the registered fictional code for event_kind")
        if not isinstance(self.code, str):
            raise TypeError("code must be a string")
        opportunity = _require_optional_nonnegative_int(
            self.opportunity_index, "opportunity_index"
        )
        object.__setattr__(self, "opportunity_index", opportunity)

    def to_mapping(self) -> dict[str, object]:
        return {
            "patient_id": self.patient_id,
            "age_days": self.age_days,
            "event_kind": self.event_kind.value,
            "code": self.code,
            "opportunity_index": self.opportunity_index,
        }


@dataclass(frozen=True, repr=False)
class ObservationTruth:
    """Private evaluator state for reconstructing one observation frame."""

    patient_id: str = field(repr=False)
    window: ObservationWindow = field(repr=False)
    opportunities: tuple[VisitOpportunity, ...] = field(repr=False)
    measurement_truth: tuple[MeasurementTruth, ...] = field(repr=False)
    event_decisions: tuple[EventRecordingDecision, ...] = field(repr=False)
    source_events: tuple[ClinicalEvent, ...] = field(repr=False)
    latent_trajectory_hash: str | None = field(default=None, repr=False)
    truth_hash: str | None = field(default=None, repr=False)
    # These evaluator-only references let validation recompute the hashes and
    # check that latent measurement values came from the exact source point.
    # They are intentionally optional so callers holding only a redacted truth
    # object receive UNEVALUABLE rather than an unsafe PASS.
    policy: ObservationPolicy | None = field(default=None, repr=False)
    latent_trajectory: AgeRegimeDisorderTrajectory | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        _require_synthetic_patient_id(self.patient_id)
        if not isinstance(self.window, ObservationWindow):
            raise TypeError("window must be an ObservationWindow")
        opportunities = _require_tuple(self.opportunities, "opportunities")
        if not all(isinstance(item, VisitOpportunity) for item in opportunities):
            raise TypeError("opportunities must contain VisitOpportunity values")
        measurement_truth = _require_tuple(self.measurement_truth, "measurement_truth")
        if not all(isinstance(item, MeasurementTruth) for item in measurement_truth):
            raise TypeError("measurement_truth must contain MeasurementTruth values")
        event_decisions = _require_tuple(self.event_decisions, "event_decisions")
        if not all(isinstance(item, EventRecordingDecision) for item in event_decisions):
            raise TypeError("event_decisions must contain EventRecordingDecision values")
        source_events = _require_tuple(self.source_events, "source_events")
        if not all(isinstance(item, ClinicalEvent) for item in source_events):
            raise TypeError("source_events must contain ClinicalEvent values")
        for event in source_events:
            _require_synthetic_patient_id(event.patient_id, "source event patient_id")
            if event.patient_id != self.patient_id:
                raise ValueError("source events must identify the same synthetic patient")
            _require_nonnegative_int(event.age_days, "source event age_days")
            if event.event_type not in _SOURCE_EVENT_TYPES:
                raise ValueError("source event type must be a native trajectory event")
            if event.code is not None:
                raise ValueError("source event code must be None until terminology is reviewed")
            if not isinstance(event.hidden, bool):
                raise TypeError("source event hidden must be a boolean")
            if event.event_type == "latent_onset" and not event.hidden:
                raise ValueError("latent_onset source events must remain hidden")

        decision_indices = tuple(item.source_event_index for item in event_decisions)
        if decision_indices != tuple(range(len(source_events))):
            raise ValueError("event decisions must contain exactly one decision per source event")
        opportunity_by_source_point = {
            item.source_point_index: item for item in opportunities
        }
        for event, decision in zip(source_events, event_decisions, strict=True):
            if not decision.recorded:
                continue
            opportunity = opportunity_by_source_point.get(decision.opportunity_index)
            if opportunity is None:
                raise ValueError("recorded event decision must reference an existing opportunity")
            if not opportunity.realized:
                raise ValueError("recorded event decision must reference a realized opportunity")
            if event.hidden:
                raise ValueError("hidden source events must not be recorded")
        if len({(item.source_point_index, item.channel) for item in measurement_truth}) != len(
            measurement_truth
        ):
            raise ValueError("measurement truth must not duplicate a source channel")
        if len({item.source_point_index for item in opportunities}) != len(opportunities):
            raise ValueError("opportunities must not duplicate a source point")
        _require_hash(self.latent_trajectory_hash, "latent_trajectory_hash")
        _require_hash(self.truth_hash, "truth_hash")
        if self.policy is not None and not isinstance(self.policy, ObservationPolicy):
            raise TypeError("policy must be an ObservationPolicy or None")
        if self.latent_trajectory is not None and not isinstance(
            self.latent_trajectory, AgeRegimeDisorderTrajectory
        ):
            raise TypeError(
                "latent_trajectory must be an AgeRegimeDisorderTrajectory or None"
            )
        if self.latent_trajectory is not None:
            points = self.latent_trajectory.physiology.points
            if points and points[0].patient_id != self.patient_id:
                raise ValueError("latent trajectory must identify the truth patient")

    def __repr__(self) -> str:
        return "ObservationTruth(<evaluator-only>)"


@dataclass(frozen=True, repr=False)
class ObservedVisit:
    """One visible selected visit and its closed measurement records."""

    patient_id: str
    visit_id: str
    age_days: int
    encounter_type: EncounterType
    measurements: tuple[MeasurementObservation, ...]

    def __post_init__(self) -> None:
        _require_synthetic_patient_id(self.patient_id)
        _require_synthetic_visit_id(self.visit_id)
        _require_nonnegative_int(self.age_days, "age_days")
        _require_enum(self.encounter_type, EncounterType, "encounter_type")
        measurements = _require_tuple(self.measurements, "measurements")
        if not measurements:
            raise ValueError("measurements must be nonempty")
        if not all(isinstance(item, MeasurementObservation) for item in measurements):
            raise TypeError("measurements must contain MeasurementObservation values")
        channels = tuple(item.channel for item in measurements)
        if len(channels) != len(set(channels)):
            raise ValueError("measurements must not duplicate a channel")

    @property
    def observations(self) -> tuple[MeasurementObservation, ...]:
        return self.measurements

    def to_mapping(self) -> dict[str, object]:
        return {
            "patient_id": self.patient_id,
            "visit_id": self.visit_id,
            "age_days": self.age_days,
            "encounter_type": self.encounter_type.value,
            "measurements": [item.to_mapping() for item in self.measurements],
        }

    def __repr__(self) -> str:
        return "ObservedVisit(<visible>)"


@dataclass(frozen=True, repr=False)
class ObservationFrame:
    """Visible observations plus a private truth object for one patient."""

    patient_id: str = field(repr=False)
    policy_version: str
    window: ObservationWindow
    visits: tuple[ObservedVisit, ...]
    events: tuple[RecordedEvent, ...]
    truth: ObservationTruth = field(repr=False)

    def __post_init__(self) -> None:
        _require_synthetic_patient_id(self.patient_id)
        _require_token(self.policy_version, "policy_version")
        if not isinstance(self.window, ObservationWindow):
            raise TypeError("window must be an ObservationWindow")
        visits = _require_tuple(self.visits, "visits")
        if not all(isinstance(item, ObservedVisit) for item in visits):
            raise TypeError("visits must contain ObservedVisit values")
        events = _require_tuple(self.events, "events")
        if not all(isinstance(item, RecordedEvent) for item in events):
            raise TypeError("events must contain RecordedEvent values")
        if not isinstance(self.truth, ObservationTruth):
            raise TypeError("truth must be an ObservationTruth")
        if self.truth.patient_id != self.patient_id or self.truth.window != self.window:
            raise ValueError("frame and truth must identify the same patient and window")
        if any(item.patient_id != self.patient_id for item in (*visits, *events)):
            raise ValueError("visible records must identify the same synthetic patient")
        if any(not self.window.start_age_days <= item.age_days < self.window.effective_end_age_days for item in visits):
            raise ValueError("visible visits must fall inside the effective observation window")
        if any(not self.window.start_age_days <= item.age_days < self.window.effective_end_age_days for item in events):
            raise ValueError("visible events must fall inside the effective observation window")
        visit_ids = tuple(item.visit_id for item in visits)
        if len(visit_ids) != len(set(visit_ids)):
            raise ValueError("visible visits must have unique visit IDs")

    @property
    def measurement_count(self) -> int:
        return sum(len(visit.measurements) for visit in self.visits)

    def to_mapping(self) -> dict[str, object]:
        """Return only visible records, fixed metadata, and aggregate counts."""

        return {
            "contract": "observation-frame-v1",
            "patient_id": self.patient_id,
            "policy_version": self.policy_version,
            "window": self.window.to_mapping(),
            "visits": [visit.to_mapping() for visit in self.visits],
            "events": [event.to_mapping() for event in self.events],
            "counts": {
                "visits": len(self.visits),
                "events": len(self.events),
                "measurements": self.measurement_count,
            },
        }

    def __repr__(self) -> str:
        return "ObservationFrame(<evaluator-only>)"


def _canonical(value: object) -> object:
    """Return a deterministic, non-serializing hash representation."""

    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            item.name: _canonical(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("hash input must contain only finite values")
        return value
    return value


def _canonical_hash(value: object) -> str:
    try:
        encoded = json.dumps(
            _canonical(value),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("observation hash input is not canonicalizable") from exc
    return hashlib.sha256(encoded).hexdigest()


def _validate_observation_trajectory(
    trajectory: object,
) -> AgeRegimeDisorderTrajectory:
    if not isinstance(trajectory, AgeRegimeDisorderTrajectory):
        raise TypeError("trajectory must be an AgeRegimeDisorderTrajectory")
    points = trajectory.physiology.points
    patient_id = points[0].patient_id
    _require_synthetic_patient_id(patient_id)
    if any(point.patient_id != patient_id for point in points):
        raise ValueError("trajectory points must identify one synthetic patient")

    previous_age = -1
    previous_phase = -1
    for event in trajectory.events:
        if not isinstance(event, ClinicalEvent):
            raise TypeError("trajectory events must be ClinicalEvent instances")
        _require_synthetic_patient_id(event.patient_id, "source event patient_id")
        if event.patient_id != patient_id:
            raise ValueError("source events must identify the trajectory patient")
        _require_nonnegative_int(event.age_days, "source event age_days")
        if event.event_type not in _SOURCE_EVENT_TYPES:
            raise ValueError("source event type must be a native trajectory event")
        if event.code is not None:
            raise ValueError("source event code must be None until terminology is reviewed")
        if not isinstance(event.hidden, bool):
            raise TypeError("source event hidden must be a boolean")
        phase = _SOURCE_EVENT_PHASES[event.event_type]
        if event.age_days < previous_age or phase <= previous_phase:
            raise ValueError("source event schedule must follow causal phase order")
        if event.event_type == "latent_onset" and not event.hidden:
            raise ValueError("latent_onset source events must remain hidden")
        previous_age = event.age_days
        previous_phase = phase

    if trajectory.disorder.kind.value == "healthy" and any(
        event.event_type == "recorded_diagnosis" for event in trajectory.events
    ):
        raise ValueError("healthy trajectories cannot contain a recorded diagnosis")
    return trajectory


def _stream_generators(
    streams: NamedRandomStreams,
) -> tuple[Any, ...]:
    if not isinstance(streams, NamedRandomStreams):
        raise TypeError("streams must be NamedRandomStreams")
    generators = tuple(streams.generator(name) for name in OBSERVATION_STREAM_NAMES)
    if not all(
        callable(getattr(generator, "random", None))
        for generator in generators
    ):
        raise TypeError("observation streams must provide random draws")
    if not callable(getattr(generators[4], "normal", None)):
        raise TypeError("observation.measurement-error must provide normal draws")
    return generators


def _probability_draw(generator: Any, name: str) -> float:
    try:
        value = generator.random()
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} stream returned an invalid probability draw") from exc
    result = _require_finite_real(value, f"{name} stream draw must be finite")
    if not 0 <= result <= 1:
        raise ValueError(f"{name} stream draw must be in [0, 1]")
    return result


def _normal_draw(generator: Any, name: str, standard_deviation: float) -> float:
    try:
        value = generator.normal(0.0, standard_deviation)
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} stream returned an invalid error draw") from exc
    return _require_finite_real(value, f"{name} stream draw must be finite")


def _point_channel_value(point: Any, channel: MeasurementChannel) -> float | None:
    if channel is MeasurementChannel.LENGTH:
        applicable = point.regime in (GrowthRegime.INFANCY, GrowthRegime.TRANSITION)
        value = point.length_cm if applicable else None
    elif channel is MeasurementChannel.HEIGHT:
        applicable = point.regime in (
            GrowthRegime.TRANSITION,
            GrowthRegime.CHILDHOOD,
            GrowthRegime.PUBERTY,
            GrowthRegime.ADOLESCENCE,
        )
        value = point.height_cm if applicable else None
    elif channel is MeasurementChannel.WEIGHT:
        value = point.weight_kg
    elif channel is MeasurementChannel.HEAD_CIRCUMFERENCE:
        applicable = point.regime in (GrowthRegime.INFANCY, GrowthRegime.TRANSITION)
        value = point.head_circumference_cm if applicable else None
    else:
        raise ValueError("BMI is derived and has no latent channel draw")
    if value is None:
        return None
    return _require_positive_real(value, f"latent {channel.value} must be finite and positive")


def _availability_probability(policy: ObservationPolicy, channel: MeasurementChannel) -> float:
    return {
        MeasurementChannel.LENGTH: policy.length_availability_probability,
        MeasurementChannel.HEIGHT: policy.height_availability_probability,
        MeasurementChannel.WEIGHT: policy.weight_availability_probability,
        MeasurementChannel.HEAD_CIRCUMFERENCE: policy.head_circumference_availability_probability,
    }[channel]


def _error_standard_deviation(policy: ObservationPolicy, channel: MeasurementChannel) -> float:
    return {
        MeasurementChannel.LENGTH: policy.length_error_sd_cm,
        MeasurementChannel.HEIGHT: policy.height_error_sd_cm,
        MeasurementChannel.WEIGHT: policy.weight_error_sd_kg,
        MeasurementChannel.HEAD_CIRCUMFERENCE: policy.head_circumference_error_sd_cm,
    }[channel]


def _measurement_records(
    point_index: int,
    point: Any,
    policy: ObservationPolicy,
    availability_generator: Any,
    error_generator: Any,
) -> tuple[tuple[MeasurementObservation, ...], tuple[MeasurementTruth, ...]]:
    observations: list[MeasurementObservation] = []
    truth: list[MeasurementTruth] = []
    by_channel: dict[MeasurementChannel, MeasurementObservation] = {}

    for channel in _PHYSICAL_CHANNELS:
        latent_value = _point_channel_value(point, channel)
        if latent_value is None:
            observation = MeasurementObservation(
                channel,
                MeasurementAvailability.NOT_APPLICABLE,
                None,
            )
            truth_item = MeasurementTruth(
                point_index,
                channel,
                MeasurementAvailability.NOT_APPLICABLE,
                None,
                None,
            )
        elif (
            _probability_draw(availability_generator, "observation.measurement-availability")
            >= _availability_probability(policy, channel)
        ):
            observation = MeasurementObservation(channel, MeasurementAvailability.MISSING, None)
            truth_item = MeasurementTruth(
                point_index,
                channel,
                MeasurementAvailability.MISSING,
                latent_value,
                None,
            )
        else:
            standard_deviation = _error_standard_deviation(policy, channel)
            error_delta = _normal_draw(
                error_generator,
                "observation.measurement-error",
                standard_deviation,
            )
            try:
                post_error = latent_value + error_delta
            except ArithmeticError as exc:
                raise ValueError("post-error measurement must be finite and positive") from exc
            post_error = _require_finite_real(
                post_error,
                "post-error measurement must be finite and positive",
            )
            if post_error <= 0:
                raise ValueError("post-error measurement must be finite and positive")
            if policy.rounding_digits is not None:
                try:
                    recorded = round(post_error, policy.rounding_digits)
                except (ArithmeticError, TypeError, ValueError) as exc:
                    raise ValueError("rounded measurement must be finite and positive") from exc
            else:
                recorded = post_error
            recorded = _require_finite_real(
                recorded,
                "rounded measurement must be finite and positive",
            )
            if recorded <= 0:
                raise ValueError("rounded measurement must be finite and positive")
            observation = MeasurementObservation(
                channel,
                MeasurementAvailability.OBSERVED,
                recorded,
            )
            truth_item = MeasurementTruth(
                point_index,
                channel,
                MeasurementAvailability.OBSERVED,
                latent_value,
                error_delta,
            )
        observations.append(observation)
        truth.append(truth_item)
        by_channel[channel] = observation

    latent_bmi = point.bmi
    if point.height_cm is None or latent_bmi is None:
        bmi_observation = MeasurementObservation(
            MeasurementChannel.BMI,
            MeasurementAvailability.NOT_APPLICABLE,
            None,
        )
    elif (
        by_channel[MeasurementChannel.HEIGHT].availability is MeasurementAvailability.OBSERVED
        and by_channel[MeasurementChannel.WEIGHT].availability is MeasurementAvailability.OBSERVED
    ):
        height = by_channel[MeasurementChannel.HEIGHT].recorded_value
        weight = by_channel[MeasurementChannel.WEIGHT].recorded_value
        assert height is not None and weight is not None
        try:
            bmi = weight / (height / 100.0) ** 2
        except ArithmeticError as exc:
            raise ValueError("derived BMI must be finite and positive") from exc
        bmi = _require_positive_real(bmi, "derived BMI must be finite and positive")
        bmi_observation = MeasurementObservation(
            MeasurementChannel.BMI,
            MeasurementAvailability.OBSERVED,
            bmi,
        )
    else:
        bmi_observation = MeasurementObservation(
            MeasurementChannel.BMI,
            MeasurementAvailability.MISSING,
            None,
        )
    observations.append(bmi_observation)
    return tuple(observations), tuple(truth)


def _stable_visit_id(patient_id: str, policy_version: str, point_index: int) -> str:
    material = f"observation-visit-v1\x1f{patient_id}\x1f{policy_version}\x1f{point_index}".encode()
    return f"syn-{hashlib.sha256(material).hexdigest()[:32]}"


def _selected_opportunity(
    opportunities: tuple[VisitOpportunity, ...],
    minimum_age_days: int,
    observed_measurements_by_point: Mapping[int, tuple[MeasurementObservation, ...]],
) -> VisitOpportunity | None:
    for opportunity in opportunities:
        measurements = observed_measurements_by_point.get(opportunity.source_point_index, ())
        has_observed_measurement = any(
            item.availability is MeasurementAvailability.OBSERVED
            for item in measurements
        )
        if (
            opportunity.realized
            and opportunity.age_days >= minimum_age_days
            and has_observed_measurement
        ):
            return opportunity
    return None


def _event_projection(
    trajectory: AgeRegimeDisorderTrajectory,
    policy: ObservationPolicy,
    opportunities: tuple[VisitOpportunity, ...],
    observed_measurements_by_point: Mapping[int, tuple[MeasurementObservation, ...]],
    recognition_generator: Any,
    recorded_event_generator: Any,
) -> tuple[tuple[RecordedEvent, ...], tuple[EventRecordingDecision, ...]]:
    source_events = trajectory.events
    decisions: list[EventRecordingDecision] = []
    records: list[RecordedEvent] = []
    recognition_recorded = False
    workup_recorded = False
    last_recorded_age: int | None = None

    for source_index, event in enumerate(source_events):
        recorded = False
        opportunity_index: int | None = None
        if event.event_type == "recognition_opportunity":
            recognition_roll = _probability_draw(
                recognition_generator,
                "observation.recognition",
            )
            has_observable_phenotype = any(
                prior.event_type == "observable_phenotype"
                and not prior.hidden
                for prior in source_events[:source_index]
            )
            minimum_age = event.age_days + policy.recognition_delay_days
            if last_recorded_age is not None:
                minimum_age = max(minimum_age, last_recorded_age)
            opportunity = _selected_opportunity(
                opportunities,
                minimum_age,
                observed_measurements_by_point,
            )
            if (
                not event.hidden
                and has_observable_phenotype
                and recognition_roll < policy.recognition_probability
                and opportunity is not None
            ):
                recorded = True
                opportunity_index = opportunity.source_point_index
                recognition_recorded = True
                last_recorded_age = opportunity.age_days
                records.append(
                    RecordedEvent(
                        trajectory.physiology.points[0].patient_id,
                        opportunity.age_days,
                        RecordedEventKind.RECOGNITION,
                        RECORDED_EVENT_CODES[RecordedEventKind.RECOGNITION],
                        opportunity_index,
                    )
                )
        elif event.event_type == "workup":
            recording_roll = _probability_draw(
                recorded_event_generator,
                "observation.recorded-event",
            )
            minimum_age = event.age_days
            if last_recorded_age is not None:
                minimum_age = max(minimum_age, last_recorded_age)
            opportunity = _selected_opportunity(
                opportunities,
                minimum_age,
                observed_measurements_by_point,
            )
            if (
                not event.hidden
                and recognition_recorded
                and recording_roll < 1.0
                and opportunity is not None
            ):
                recorded = True
                opportunity_index = opportunity.source_point_index
                workup_recorded = True
                last_recorded_age = opportunity.age_days
                records.append(
                    RecordedEvent(
                        trajectory.physiology.points[0].patient_id,
                        opportunity.age_days,
                        RecordedEventKind.WORKUP,
                        RECORDED_EVENT_CODES[RecordedEventKind.WORKUP],
                        opportunity_index,
                    )
                )
        elif event.event_type == "recorded_diagnosis":
            recording_roll = _probability_draw(
                recorded_event_generator,
                "observation.recorded-event",
            )
            minimum_age = event.age_days
            if last_recorded_age is not None:
                minimum_age = max(minimum_age, last_recorded_age)
            opportunity = _selected_opportunity(
                opportunities,
                minimum_age,
                observed_measurements_by_point,
            )
            if (
                not event.hidden
                and workup_recorded
                and recording_roll < policy.diagnosis_probability
                and opportunity is not None
            ):
                recorded = True
                opportunity_index = opportunity.source_point_index
                last_recorded_age = opportunity.age_days
                records.append(
                    RecordedEvent(
                        trajectory.physiology.points[0].patient_id,
                        opportunity.age_days,
                        RecordedEventKind.DIAGNOSIS,
                        RECORDED_EVENT_CODES[RecordedEventKind.DIAGNOSIS],
                        opportunity_index,
                    )
                )
        decisions.append(EventRecordingDecision(source_index, recorded, opportunity_index))
    return tuple(records), tuple(decisions)


def generate_observation_frame(
    trajectory: AgeRegimeDisorderTrajectory,
    policy: ObservationPolicy,
    streams: NamedRandomStreams,
) -> ObservationFrame:
    """Generate one deterministic evaluator-only observation frame.

    The policy determines the effective window.  All stochastic choices are
    isolated to the declared observation streams; latent trajectory values are
    never resampled or altered by this function.
    """

    trajectory = _validate_observation_trajectory(trajectory)
    if not isinstance(policy, ObservationPolicy):
        raise TypeError("policy must be an ObservationPolicy")
    (
        _window_generator,
        _censoring_generator,
        visit_generator,
        availability_generator,
        error_generator,
        recognition_generator,
        recorded_event_generator,
    ) = _stream_generators(streams)
    del _window_generator, _censoring_generator

    points = trajectory.physiology.points
    patient_id = points[0].patient_id
    window = ObservationWindow(
        policy.window_start_age_days,
        policy.effective_end_age_days,
        policy.window_end_age_days,
        policy.censoring_mode,
    )

    opportunities: list[VisitOpportunity] = []
    for point_index, point in enumerate(points):
        if not window.start_age_days <= point.age_days < window.administrative_end_age_days:
            continue
        visit_roll = _probability_draw(visit_generator, "observation.visit.routine")
        realized = (
            point.age_days < window.effective_end_age_days
            and visit_roll < policy.visit_probability
        )
        opportunities.append(
            VisitOpportunity(point_index, point.age_days, EncounterType.ROUTINE, realized)
        )

    visits: list[ObservedVisit] = []
    measurement_truth: list[MeasurementTruth] = []
    observed_measurements_by_point: dict[int, tuple[MeasurementObservation, ...]] = {}
    for opportunity in opportunities:
        if not opportunity.realized:
            continue
        point = points[opportunity.source_point_index]
        measurements, truth_items = _measurement_records(
            opportunity.source_point_index,
            point,
            policy,
            availability_generator,
            error_generator,
        )
        measurement_truth.extend(truth_items)
        observed_measurements_by_point[opportunity.source_point_index] = measurements
        visits.append(
            ObservedVisit(
                patient_id,
                _stable_visit_id(patient_id, policy.policy_version, opportunity.source_point_index),
                point.age_days,
                EncounterType.ROUTINE,
                measurements,
            )
        )

    events, event_decisions = _event_projection(
        trajectory,
        policy,
        tuple(opportunities),
        observed_measurements_by_point,
        recognition_generator,
        recorded_event_generator,
    )
    latent_trajectory_hash = _canonical_hash(trajectory)
    base_truth = ObservationTruth(
        patient_id=patient_id,
        window=window,
        opportunities=tuple(opportunities),
        measurement_truth=tuple(measurement_truth),
        event_decisions=event_decisions,
        source_events=trajectory.events,
        latent_trajectory_hash=latent_trajectory_hash,
        truth_hash=None,
        policy=policy,
        latent_trajectory=trajectory,
    )
    truth_hash = _canonical_hash((policy.to_mapping(), base_truth))
    truth = replace(base_truth, truth_hash=truth_hash)
    return ObservationFrame(
        patient_id=patient_id,
        policy_version=policy.policy_version,
        window=window,
        visits=tuple(visits),
        events=events,
        truth=truth,
    )


class ObservationValidationStatus(str, Enum):
    """Aggregate validation result for one observation frame."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNEVALUABLE = "UNEVALUABLE"


ValidationStatus = ObservationValidationStatus


_OBSERVATION_REASON_CODES = frozenset(
    {
        "OK",
        "MALFORMED_FRAME",
        "PATIENT_MISMATCH",
        "WINDOW_INVALID",
        "VISIT_REFERENCE_INVALID",
        "MEASUREMENT_INVALID",
        "HIDDEN_EVENT_VISIBLE",
        "EVENT_ORDER_INVALID",
        "FORBIDDEN_EVENT",
        "INSUFFICIENT_EVIDENCE",
        "TRUTH_INTEGRITY_INVALID",
    }
)


@dataclass(frozen=True)
class ObservationCheck:
    """One fixed aggregate-only observation validation check."""

    name: str
    status: ObservationValidationStatus
    reason_code: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or self.name not in ObservationValidationReport.CHECK_NAMES:
            raise ValueError("unknown observation check name")
        _require_enum(self.status, ObservationValidationStatus, "status")
        if self.reason_code not in _OBSERVATION_REASON_CODES:
            raise ValueError("unknown observation reason code")

    @property
    def check_id(self) -> str:
        return self.name

    def to_mapping(self) -> dict[str, str]:
        return {
            "name": self.name,
            "status": self.status.value,
            "reason_code": self.reason_code,
        }


def _status_for_checks(
    checks: tuple[ObservationCheck, ...],
) -> ObservationValidationStatus:
    if any(check.status is ObservationValidationStatus.FAIL for check in checks):
        return ObservationValidationStatus.FAIL
    if any(check.status is ObservationValidationStatus.UNEVALUABLE for check in checks):
        return ObservationValidationStatus.UNEVALUABLE
    return ObservationValidationStatus.PASS


@dataclass(frozen=True, repr=False)
class ObservationValidationReport:
    """Immutable report containing only fixed aggregate metrics and reason codes."""

    status: ObservationValidationStatus
    checks: tuple[ObservationCheck, ...]

    CHECK_NAMES: ClassVar[tuple[str, ...]] = (
        "patient_identity",
        "window",
        "visit_references",
        "measurements",
        "hidden_events",
        "event_order",
        "evidence",
    )

    def __post_init__(self) -> None:
        _require_enum(self.status, ObservationValidationStatus, "status")
        checks = _require_tuple(self.checks, "checks")
        if len(checks) != len(self.CHECK_NAMES) or not all(
            isinstance(check, ObservationCheck) for check in checks
        ):
            raise ValueError("checks must contain every fixed observation check")
        names = tuple(check.name for check in checks)
        if len(names) != len(set(names)):
            raise ValueError("checks must not contain duplicate names")
        if set(names) != set(self.CHECK_NAMES):
            raise ValueError("checks must contain every fixed observation check")
        if self.status is not _status_for_checks(checks):
            raise ValueError("status must match observation check statuses")
        object.__setattr__(self, "checks", tuple(sorted(checks, key=lambda check: check.name)))

    @property
    def check_counts(self) -> Mapping[str, int]:
        return MappingProxyType(
            {
                status.value: sum(check.status is status for check in self.checks)
                for status in ObservationValidationStatus
            }
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "check_counts": dict(self.check_counts),
            "checks": [check.to_mapping() for check in self.checks],
        }

    def __repr__(self) -> str:
        return f"ObservationValidationReport(status={self.status.value!r}, checks={len(self.checks)})"


_RECORDED_TO_SOURCE_EVENT = {
    RecordedEventKind.RECOGNITION: "recognition_opportunity",
    RecordedEventKind.WORKUP: "workup",
    RecordedEventKind.DIAGNOSIS: "recorded_diagnosis",
}
_RECORDED_EVENT_ORDER = {
    RecordedEventKind.RECOGNITION: 0,
    RecordedEventKind.WORKUP: 1,
    RecordedEventKind.DIAGNOSIS: 2,
}


def _observation_frame_parts(frame: object) -> ObservationFrame:
    if not isinstance(frame, ObservationFrame):
        raise TypeError("frame must be an ObservationFrame")
    if not isinstance(frame.truth, ObservationTruth):
        raise TypeError("frame truth must be an ObservationTruth")
    if not isinstance(frame.visits, tuple) or not isinstance(frame.events, tuple):
        raise TypeError("frame records must be tuples")
    return frame


def _opportunity_map(
    truth: ObservationTruth,
) -> dict[int, VisitOpportunity]:
    if not isinstance(truth.opportunities, tuple):
        raise TypeError("opportunities must be a tuple")
    by_index: dict[int, VisitOpportunity] = {}
    previous_index = -1
    previous_age = -1
    for opportunity in truth.opportunities:
        if not isinstance(opportunity, VisitOpportunity):
            raise TypeError("opportunities must contain VisitOpportunity values")
        _require_nonnegative_int(opportunity.source_point_index, "source_point_index")
        _require_nonnegative_int(opportunity.age_days, "opportunity age_days")
        _require_enum(opportunity.encounter_type, EncounterType, "encounter_type")
        if not isinstance(opportunity.realized, bool):
            raise TypeError("opportunity realized must be a boolean")
        if opportunity.source_point_index <= previous_index or opportunity.age_days <= previous_age:
            raise ValueError("opportunity order is invalid")
        if opportunity.source_point_index in by_index:
            raise ValueError("opportunities must not duplicate a source point")
        by_index[opportunity.source_point_index] = opportunity
        previous_index = opportunity.source_point_index
        previous_age = opportunity.age_days
    return by_index


def _source_event_data(
    truth: ObservationTruth,
) -> tuple[tuple[ClinicalEvent, ...], tuple[EventRecordingDecision, ...]]:
    if not isinstance(truth.source_events, tuple) or not isinstance(truth.event_decisions, tuple):
        raise TypeError("source events and decisions must be tuples")
    events = truth.source_events
    decisions = truth.event_decisions
    if len(events) != len(decisions):
        raise ValueError("source events and decisions must have equal length")
    for index, (event, decision) in enumerate(zip(events, decisions, strict=True)):
        if not isinstance(event, ClinicalEvent):
            raise TypeError("source events must contain ClinicalEvent values")
        if not isinstance(decision, EventRecordingDecision):
            raise TypeError("event decisions must contain EventRecordingDecision values")
        if decision.source_event_index != index:
            raise ValueError("event decisions must be indexed by source event")
        if not isinstance(decision.recorded, bool):
            raise TypeError("event decision recorded must be a boolean")
        _require_optional_nonnegative_int(decision.opportunity_index, "opportunity_index")
        if decision.recorded and decision.opportunity_index is None:
            raise ValueError("recorded event decisions require an opportunity link")
        if not decision.recorded and decision.opportunity_index is not None:
            raise ValueError("unrecorded event decisions must not have an opportunity link")
        _require_synthetic_patient_id(event.patient_id, "source event patient_id")
        _require_nonnegative_int(event.age_days, "source event age_days")
        if event.event_type not in _SOURCE_EVENT_TYPES:
            raise ValueError("source event type must be a native trajectory event")
        if event.code is not None:
            raise ValueError("source event code must be None until terminology is reviewed")
        if not isinstance(event.hidden, bool):
            raise TypeError("source event hidden must be a boolean")
    return events, decisions


def _truth_provenance(
    frame: ObservationFrame,
) -> tuple[
    ObservationValidationStatus,
    str,
    ObservationPolicy | None,
    AgeRegimeDisorderTrajectory | None,
]:
    """Return validated hidden provenance without exposing any of its detail.

    A frame assembled from a redacted ``ObservationTruth`` cannot establish
    that its hidden values are authentic.  Such a frame is deliberately
    unevaluable.  When provenance is present, the hashes and source-point
    identities are checked before downstream validators use the hidden values.
    """

    truth = frame.truth
    policy = truth.policy
    trajectory = truth.latent_trajectory
    if not isinstance(policy, ObservationPolicy) or not isinstance(
        trajectory, AgeRegimeDisorderTrajectory
    ):
        return (
            ObservationValidationStatus.UNEVALUABLE,
            "INSUFFICIENT_EVIDENCE",
            None,
            None,
        )
    if truth.latent_trajectory_hash is None or truth.truth_hash is None:
        return (
            ObservationValidationStatus.UNEVALUABLE,
            "INSUFFICIENT_EVIDENCE",
            None,
            None,
        )
    try:
        # A redacted/incomplete measurement truth payload cannot support a
        # meaningful hash-integrity verdict.  Preserve the public contract that
        # missing evidence is UNEVALUABLE rather than turning it into FAIL just
        # because its old hash no longer matches.
        opportunities = _opportunity_map(truth)
        _truth_measurements_by_point(
            truth,
            {index for index, item in opportunities.items() if item.realized},
        )
        trajectory = _validate_observation_trajectory(trajectory)
        if policy.policy_version != frame.policy_version:
            return (
                ObservationValidationStatus.FAIL,
                "TRUTH_INTEGRITY_INVALID",
                policy,
                trajectory,
            )
        expected_window = ObservationWindow(
            policy.window_start_age_days,
            policy.effective_end_age_days,
            policy.window_end_age_days,
            policy.censoring_mode,
        )
        if truth.window != expected_window:
            return (
                ObservationValidationStatus.FAIL,
                "TRUTH_INTEGRITY_INVALID",
                policy,
                trajectory,
            )
        if truth.source_events != trajectory.events:
            return (
                ObservationValidationStatus.FAIL,
                "TRUTH_INTEGRITY_INVALID",
                policy,
                trajectory,
            )
        points = trajectory.physiology.points
        opportunities = _opportunity_map(truth)
        for opportunity in opportunities.values():
            if opportunity.source_point_index >= len(points):
                return (
                    ObservationValidationStatus.FAIL,
                    "TRUTH_INTEGRITY_INVALID",
                    policy,
                    trajectory,
                )
            if opportunity.age_days != points[opportunity.source_point_index].age_days:
                return (
                    ObservationValidationStatus.FAIL,
                    "TRUTH_INTEGRITY_INVALID",
                    policy,
                    trajectory,
                )
        expected_latent_hash = _canonical_hash(trajectory)
        if truth.latent_trajectory_hash != expected_latent_hash:
            return (
                ObservationValidationStatus.FAIL,
                "TRUTH_INTEGRITY_INVALID",
                policy,
                trajectory,
            )
        expected_truth_hash = _canonical_hash(
            (policy.to_mapping(), replace(truth, truth_hash=None))
        )
        if truth.truth_hash != expected_truth_hash:
            return (
                ObservationValidationStatus.FAIL,
                "TRUTH_INTEGRITY_INVALID",
                policy,
                trajectory,
            )
    except (ArithmeticError, AttributeError, IndexError, KeyError, TypeError, ValueError):
        return (
            ObservationValidationStatus.UNEVALUABLE,
            "INSUFFICIENT_EVIDENCE",
            None,
            None,
        )
    return ObservationValidationStatus.PASS, "OK", policy, trajectory


def _validation_check(
    name: str,
    evaluator: Any,
) -> ObservationCheck:
    try:
        status, reason_code = evaluator()
    except (ArithmeticError, AttributeError, IndexError, KeyError, TypeError, ValueError):
        status, reason_code = ObservationValidationStatus.UNEVALUABLE, "MALFORMED_FRAME"
    return ObservationCheck(name, status, reason_code)


def _check_patient_identity(frame: object) -> tuple[ObservationValidationStatus, str]:
    frame = _observation_frame_parts(frame)
    _require_synthetic_patient_id(frame.patient_id)
    truth = frame.truth
    if truth.patient_id != frame.patient_id:
        return ObservationValidationStatus.FAIL, "PATIENT_MISMATCH"
    for visit in frame.visits:
        if not isinstance(visit, ObservedVisit):
            raise TypeError("visits must contain ObservedVisit values")
        _require_synthetic_patient_id(visit.patient_id)
        _require_synthetic_visit_id(visit.visit_id)
        _require_nonnegative_int(visit.age_days, "visit age_days")
        _require_enum(visit.encounter_type, EncounterType, "encounter_type")
        if visit.patient_id != frame.patient_id:
            return ObservationValidationStatus.FAIL, "PATIENT_MISMATCH"
    for event in frame.events:
        if not isinstance(event, RecordedEvent):
            raise TypeError("events must contain RecordedEvent values")
        _require_synthetic_patient_id(event.patient_id)
        _require_nonnegative_int(event.age_days, "recorded event age_days")
        _require_enum(event.event_kind, RecordedEventKind, "event_kind")
        if event.patient_id != frame.patient_id:
            return ObservationValidationStatus.FAIL, "PATIENT_MISMATCH"
    for event in truth.source_events:
        if not isinstance(event, ClinicalEvent):
            raise TypeError("source events must contain ClinicalEvent values")
        _require_synthetic_patient_id(event.patient_id, "source event patient_id")
        if event.patient_id != frame.patient_id:
            return ObservationValidationStatus.FAIL, "PATIENT_MISMATCH"
    return ObservationValidationStatus.PASS, "OK"


def _check_window(frame: object) -> tuple[ObservationValidationStatus, str]:
    frame = _observation_frame_parts(frame)
    _require_token(frame.policy_version, "policy_version")
    window = frame.window
    if not isinstance(window, ObservationWindow):
        raise TypeError("window must be an ObservationWindow")
    try:
        ObservationWindow(
            window.start_age_days,
            window.effective_end_age_days,
            window.administrative_end_age_days,
            window.censoring_mode,
        )
    except (TypeError, ValueError):
        return ObservationValidationStatus.FAIL, "WINDOW_INVALID"
    if frame.truth.window != window:
        return ObservationValidationStatus.FAIL, "WINDOW_INVALID"
    opportunities = _opportunity_map(frame.truth)
    for opportunity in opportunities.values():
        if not window.start_age_days <= opportunity.age_days < window.administrative_end_age_days:
            return ObservationValidationStatus.FAIL, "WINDOW_INVALID"
        if opportunity.realized and opportunity.age_days >= window.effective_end_age_days:
            return ObservationValidationStatus.FAIL, "WINDOW_INVALID"
    for visit in frame.visits:
        if not isinstance(visit, ObservedVisit):
            raise TypeError("visits must contain ObservedVisit values")
        if not window.start_age_days <= visit.age_days < window.effective_end_age_days:
            return ObservationValidationStatus.FAIL, "WINDOW_INVALID"
    for event in frame.events:
        if not isinstance(event, RecordedEvent):
            raise TypeError("events must contain RecordedEvent values")
        if not window.start_age_days <= event.age_days < window.effective_end_age_days:
            return ObservationValidationStatus.FAIL, "WINDOW_INVALID"
    return ObservationValidationStatus.PASS, "OK"


def _expected_visit_ids(frame: ObservationFrame) -> dict[str, VisitOpportunity]:
    return {
        _stable_visit_id(frame.patient_id, frame.policy_version, index): opportunity
        for index, opportunity in _opportunity_map(frame.truth).items()
        if opportunity.realized
    }


def _check_visit_references(frame: object) -> tuple[ObservationValidationStatus, str]:
    frame = _observation_frame_parts(frame)
    expected = _expected_visit_ids(frame)
    seen: set[str] = set()
    previous_age = -1
    for visit in frame.visits:
        if not isinstance(visit, ObservedVisit):
            raise TypeError("visits must contain ObservedVisit values")
        if visit.age_days <= previous_age:
            return ObservationValidationStatus.FAIL, "VISIT_REFERENCE_INVALID"
        previous_age = visit.age_days
        if visit.visit_id not in expected or visit.visit_id in seen:
            return ObservationValidationStatus.FAIL, "VISIT_REFERENCE_INVALID"
        opportunity = expected[visit.visit_id]
        if visit.age_days != opportunity.age_days or visit.encounter_type is not opportunity.encounter_type:
            return ObservationValidationStatus.FAIL, "VISIT_REFERENCE_INVALID"
        seen.add(visit.visit_id)
    if seen != set(expected):
        return ObservationValidationStatus.FAIL, "VISIT_REFERENCE_INVALID"
    return ObservationValidationStatus.PASS, "OK"


def _truth_measurements_by_point(
    truth: ObservationTruth,
    realized_indices: set[int],
) -> dict[tuple[int, MeasurementChannel], MeasurementTruth]:
    if not isinstance(truth.measurement_truth, tuple):
        raise TypeError("measurement truth must be a tuple")
    by_key: dict[tuple[int, MeasurementChannel], MeasurementTruth] = {}
    for item in truth.measurement_truth:
        if not isinstance(item, MeasurementTruth):
            raise TypeError("measurement truth must contain MeasurementTruth values")
        _require_nonnegative_int(item.source_point_index, "measurement source_point_index")
        if item.channel is MeasurementChannel.BMI or item.channel not in _PHYSICAL_CHANNELS:
            raise ValueError("measurement truth contains an unsupported channel")
        if item.source_point_index not in realized_indices:
            raise ValueError("measurement truth references an unselected point")
        key = (item.source_point_index, item.channel)
        if key in by_key:
            raise ValueError("measurement truth must not duplicate a source channel")
        by_key[key] = item
    expected = {
        (index, channel)
        for index in realized_indices
        for channel in _PHYSICAL_CHANNELS
    }
    if set(by_key) != expected:
        raise ValueError("measurement truth is incomplete")
    return by_key


def _valid_truth_measurement(item: MeasurementTruth) -> bool:
    if item.availability is MeasurementAvailability.NOT_APPLICABLE:
        return item.latent_value is None and item.error_delta is None
    try:
        _require_positive_real(item.latent_value, "latent measurement")
    except (TypeError, ValueError):
        return False
    if item.availability is MeasurementAvailability.MISSING:
        return item.error_delta is None
    if item.availability is MeasurementAvailability.OBSERVED:
        try:
            _require_finite_real(item.error_delta, "measurement error")
        except (TypeError, ValueError):
            return False
        return True
    return False


def _reconstructed_measurement_value(
    item: MeasurementTruth,
    policy: ObservationPolicy,
) -> float | None:
    """Reconstruct the visible value prescribed by one hidden measurement."""

    if item.availability is not MeasurementAvailability.OBSERVED:
        return None
    assert item.latent_value is not None and item.error_delta is not None
    if _error_standard_deviation(policy, item.channel) == 0 and item.error_delta != 0:
        raise ValueError("zero-error policy requires a zero error delta")
    post_error = _require_finite_real(
        item.latent_value + item.error_delta,
        "post-error measurement",
    )
    if post_error <= 0:
        raise ValueError("post-error measurement must be finite and positive")
    if policy.rounding_digits is None:
        recorded = post_error
    else:
        recorded = round(post_error, policy.rounding_digits)
    recorded = _require_finite_real(recorded, "rounded measurement")
    if recorded <= 0:
        raise ValueError("rounded measurement must be finite and positive")
    return recorded


def _check_measurements(frame: object) -> tuple[ObservationValidationStatus, str]:
    frame = _observation_frame_parts(frame)
    opportunities = _opportunity_map(frame.truth)
    realized = {index for index, opportunity in opportunities.items() if opportunity.realized}
    try:
        truth_by_key = _truth_measurements_by_point(frame.truth, realized)
    except (TypeError, ValueError):
        return ObservationValidationStatus.UNEVALUABLE, "INSUFFICIENT_EVIDENCE"
    provenance_status, provenance_reason, policy, trajectory = _truth_provenance(frame)
    if provenance_status is not ObservationValidationStatus.PASS:
        return provenance_status, provenance_reason
    assert policy is not None and trajectory is not None
    expected_ids = _expected_visit_ids(frame)
    for visit in frame.visits:
        if not isinstance(visit, ObservedVisit):
            raise TypeError("visits must contain ObservedVisit values")
        opportunity = expected_ids.get(visit.visit_id)
        if opportunity is None:
            return ObservationValidationStatus.FAIL, "MEASUREMENT_INVALID"
        by_channel: dict[MeasurementChannel, MeasurementObservation] = {}
        for observation in visit.measurements:
            if not isinstance(observation, MeasurementObservation):
                raise TypeError("measurements must contain MeasurementObservation values")
            if observation.channel in by_channel:
                return ObservationValidationStatus.FAIL, "MEASUREMENT_INVALID"
            if not isinstance(observation.channel, MeasurementChannel):
                raise TypeError("measurement channel must be a MeasurementChannel")
            if not isinstance(observation.availability, MeasurementAvailability):
                raise TypeError("measurement availability must be a MeasurementAvailability")
            by_channel[observation.channel] = observation
        if set(by_channel) != set(MeasurementChannel):
            return ObservationValidationStatus.FAIL, "MEASUREMENT_INVALID"
        for channel in _PHYSICAL_CHANNELS:
            observation = by_channel[channel]
            truth_item = truth_by_key.get((opportunity.source_point_index, channel))
            if truth_item is None or not _valid_truth_measurement(truth_item):
                return ObservationValidationStatus.UNEVALUABLE, "INSUFFICIENT_EVIDENCE"
            try:
                point = trajectory.physiology.points[opportunity.source_point_index]
                expected_latent = _point_channel_value(point, channel)
            except (ArithmeticError, AttributeError, IndexError, TypeError, ValueError):
                return ObservationValidationStatus.UNEVALUABLE, "INSUFFICIENT_EVIDENCE"
            if truth_item.availability is MeasurementAvailability.NOT_APPLICABLE:
                if expected_latent is not None:
                    return ObservationValidationStatus.FAIL, "TRUTH_INTEGRITY_INVALID"
            elif expected_latent is None or truth_item.latent_value != expected_latent:
                return ObservationValidationStatus.FAIL, "TRUTH_INTEGRITY_INVALID"
            availability_probability = _availability_probability(policy, channel)
            if expected_latent is not None:
                if availability_probability == 0 and truth_item.availability is not MeasurementAvailability.MISSING:
                    return ObservationValidationStatus.FAIL, "TRUTH_INTEGRITY_INVALID"
                if availability_probability == 1 and truth_item.availability is not MeasurementAvailability.OBSERVED:
                    return ObservationValidationStatus.FAIL, "TRUTH_INTEGRITY_INVALID"
            if observation.availability is not truth_item.availability:
                return ObservationValidationStatus.FAIL, "MEASUREMENT_INVALID"
            if observation.availability is MeasurementAvailability.OBSERVED:
                try:
                    _require_positive_real(observation.recorded_value, "recorded measurement")
                    expected_recorded = _reconstructed_measurement_value(truth_item, policy)
                except (ArithmeticError, TypeError, ValueError):
                    return ObservationValidationStatus.FAIL, "TRUTH_INTEGRITY_INVALID"
                if observation.recorded_value != expected_recorded:
                    return ObservationValidationStatus.FAIL, "MEASUREMENT_INVALID"
            elif observation.recorded_value is not None:
                return ObservationValidationStatus.FAIL, "MEASUREMENT_INVALID"

        height = by_channel[MeasurementChannel.HEIGHT]
        weight = by_channel[MeasurementChannel.WEIGHT]
        bmi = by_channel[MeasurementChannel.BMI]
        if height.availability is MeasurementAvailability.NOT_APPLICABLE:
            expected_bmi_status = MeasurementAvailability.NOT_APPLICABLE
        elif (
            height.availability is MeasurementAvailability.OBSERVED
            and weight.availability is MeasurementAvailability.OBSERVED
        ):
            expected_bmi_status = MeasurementAvailability.OBSERVED
        else:
            expected_bmi_status = MeasurementAvailability.MISSING
        if bmi.availability is not expected_bmi_status:
            return ObservationValidationStatus.FAIL, "MEASUREMENT_INVALID"
        if expected_bmi_status is MeasurementAvailability.OBSERVED:
            try:
                height_value = _require_positive_real(height.recorded_value, "recorded height")
                weight_value = _require_positive_real(weight.recorded_value, "recorded weight")
                bmi_value = _require_positive_real(bmi.recorded_value, "recorded BMI")
                expected_bmi = weight_value / (height_value / 100.0) ** 2
            except (ArithmeticError, TypeError, ValueError):
                return ObservationValidationStatus.FAIL, "MEASUREMENT_INVALID"
            if not math.isclose(bmi_value, expected_bmi, rel_tol=1e-9, abs_tol=1e-9):
                return ObservationValidationStatus.FAIL, "MEASUREMENT_INVALID"
        elif bmi.recorded_value is not None:
            return ObservationValidationStatus.FAIL, "MEASUREMENT_INVALID"
    return ObservationValidationStatus.PASS, "OK"


def _check_hidden_events(frame: object) -> tuple[ObservationValidationStatus, str]:
    frame = _observation_frame_parts(frame)
    provenance_status, provenance_reason, policy, _trajectory = _truth_provenance(frame)
    if provenance_status is not ObservationValidationStatus.PASS:
        return provenance_status, provenance_reason
    assert policy is not None
    try:
        source_events, decisions = _source_event_data(frame.truth)
        opportunities = _opportunity_map(frame.truth)
    except (TypeError, ValueError):
        return ObservationValidationStatus.UNEVALUABLE, "INSUFFICIENT_EVIDENCE"
    if any(event.patient_id != frame.patient_id for event in source_events):
        return ObservationValidationStatus.FAIL, "PATIENT_MISMATCH"
    expected_visit_ids = _expected_visit_ids(frame)
    observed_physical_points: set[int] = set()
    for visit in frame.visits:
        if not isinstance(visit, ObservedVisit):
            raise TypeError("visits must contain ObservedVisit values")
        opportunity = expected_visit_ids.get(visit.visit_id)
        if opportunity is None:
            continue
        if any(
            isinstance(measurement, MeasurementObservation)
            and measurement.channel in _PHYSICAL_CHANNELS
            and measurement.availability is MeasurementAvailability.OBSERVED
            for measurement in visit.measurements
        ):
            observed_physical_points.add(opportunity.source_point_index)
    source_by_type = {
        event.event_type: (index, event) for index, event in enumerate(source_events)
    }
    recorded_source_indices: set[int] = set()
    recorded_source_types: set[str] = set()
    for index, (event, decision) in enumerate(zip(source_events, decisions, strict=True)):
        if decision.recorded and event.hidden:
            return ObservationValidationStatus.FAIL, "HIDDEN_EVENT_VISIBLE"
        if decision.recorded and event.event_type in _DEFERRED_SOURCE_EVENT_TYPES:
            return ObservationValidationStatus.FAIL, "FORBIDDEN_EVENT"
        if decision.recorded:
            if (
                event.event_type == "recognition_opportunity"
                and policy.recognition_probability == 0.0
            ):
                return ObservationValidationStatus.FAIL, "FORBIDDEN_EVENT"
            if event.event_type == "recognition_opportunity" and not any(
                prior.event_type == "observable_phenotype" and not prior.hidden
                for prior in source_events[:index]
            ):
                return ObservationValidationStatus.FAIL, "FORBIDDEN_EVENT"
            if event.event_type == "recorded_diagnosis" and policy.diagnosis_probability == 0.0:
                return ObservationValidationStatus.FAIL, "FORBIDDEN_EVENT"
            if event.event_type == "workup" and "recognition_opportunity" not in recorded_source_types:
                return ObservationValidationStatus.FAIL, "FORBIDDEN_EVENT"
            if event.event_type == "recorded_diagnosis" and "workup" not in recorded_source_types:
                return ObservationValidationStatus.FAIL, "FORBIDDEN_EVENT"
            opportunity = opportunities.get(decision.opportunity_index)
            if opportunity is None or not opportunity.realized:
                return ObservationValidationStatus.FAIL, "FORBIDDEN_EVENT"
            if opportunity.source_point_index not in observed_physical_points:
                return ObservationValidationStatus.FAIL, "FORBIDDEN_EVENT"
            recorded_source_indices.add(index)
            recorded_source_types.add(event.event_type)

    visible_for_source: dict[int, RecordedEvent] = {}
    for record in frame.events:
        if not isinstance(record, RecordedEvent):
            raise TypeError("events must contain RecordedEvent values")
        if not isinstance(record.event_kind, RecordedEventKind):
            return ObservationValidationStatus.FAIL, "FORBIDDEN_EVENT"
        expected_code = RECORDED_EVENT_CODES[record.event_kind]
        if record.code != expected_code:
            return ObservationValidationStatus.FAIL, "FORBIDDEN_EVENT"
        source_type = _RECORDED_TO_SOURCE_EVENT[record.event_kind]
        source_entry = source_by_type.get(source_type)
        if source_entry is None:
            return ObservationValidationStatus.FAIL, "HIDDEN_EVENT_VISIBLE"
        source_index, source_event = source_entry
        if source_event.hidden:
            return ObservationValidationStatus.FAIL, "HIDDEN_EVENT_VISIBLE"
        decision = decisions[source_index]
        if not decision.recorded:
            return ObservationValidationStatus.FAIL, "HIDDEN_EVENT_VISIBLE"
        if source_index in visible_for_source:
            return ObservationValidationStatus.FAIL, "FORBIDDEN_EVENT"
        # The visible record must preserve the exact source decision link.  A
        # different realized opportunity is not an equivalent observation.
        if record.opportunity_index != decision.opportunity_index:
            return ObservationValidationStatus.FAIL, "FORBIDDEN_EVENT"
        opportunity = opportunities.get(decision.opportunity_index)
        if opportunity is None or not opportunity.realized:
            return ObservationValidationStatus.FAIL, "FORBIDDEN_EVENT"
        minimum_age = source_event.age_days
        if record.event_kind is RecordedEventKind.RECOGNITION:
            minimum_age += policy.recognition_delay_days
        if record.age_days != opportunity.age_days or record.age_days < minimum_age:
            return ObservationValidationStatus.FAIL, "FORBIDDEN_EVENT"
        visible_for_source[source_index] = record
    if set(visible_for_source) != recorded_source_indices:
        return ObservationValidationStatus.FAIL, "HIDDEN_EVENT_VISIBLE"
    return ObservationValidationStatus.PASS, "OK"


def _check_event_order(frame: object) -> tuple[ObservationValidationStatus, str]:
    frame = _observation_frame_parts(frame)
    provenance_status, provenance_reason, policy, _trajectory = _truth_provenance(frame)
    if provenance_status is not ObservationValidationStatus.PASS:
        return provenance_status, provenance_reason
    assert policy is not None
    try:
        source_events, decisions = _source_event_data(frame.truth)
        opportunities = _opportunity_map(frame.truth)
    except (TypeError, ValueError):
        return ObservationValidationStatus.UNEVALUABLE, "INSUFFICIENT_EVIDENCE"
    previous_age = -1
    previous_phase = -1
    source_by_type: dict[str, tuple[int, ClinicalEvent]] = {}
    for source_index, event in enumerate(source_events):
        phase = _SOURCE_EVENT_PHASES[event.event_type]
        if event.age_days < previous_age or phase <= previous_phase:
            return ObservationValidationStatus.FAIL, "EVENT_ORDER_INVALID"
        previous_age = event.age_days
        previous_phase = phase
        source_by_type[event.event_type] = (source_index, event)
    previous_record_age = -1
    previous_record_order = -1
    seen_source_types: set[str] = set()
    for record in frame.events:
        if not isinstance(record, RecordedEvent):
            raise TypeError("events must contain RecordedEvent values")
        if not isinstance(record.event_kind, RecordedEventKind):
            return ObservationValidationStatus.FAIL, "EVENT_ORDER_INVALID"
        source_type = _RECORDED_TO_SOURCE_EVENT[record.event_kind]
        source_entry = source_by_type.get(source_type)
        if source_entry is None:
            return ObservationValidationStatus.FAIL, "EVENT_ORDER_INVALID"
        source_index, source = source_entry
        decision = decisions[source_index]
        if record.opportunity_index != decision.opportunity_index:
            return ObservationValidationStatus.FAIL, "EVENT_ORDER_INVALID"
        opportunity = opportunities.get(decision.opportunity_index)
        if opportunity is None or not opportunity.realized or record.age_days != opportunity.age_days:
            return ObservationValidationStatus.FAIL, "EVENT_ORDER_INVALID"
        minimum_age = source.age_days
        if record.event_kind is RecordedEventKind.RECOGNITION:
            minimum_age += policy.recognition_delay_days
        if record.age_days < minimum_age or record.age_days < previous_record_age:
            return ObservationValidationStatus.FAIL, "EVENT_ORDER_INVALID"
        if source_type in seen_source_types:
            return ObservationValidationStatus.FAIL, "EVENT_ORDER_INVALID"
        if _RECORDED_EVENT_ORDER[record.event_kind] <= previous_record_order:
            return ObservationValidationStatus.FAIL, "EVENT_ORDER_INVALID"
        if not decision.recorded:
            return ObservationValidationStatus.FAIL, "EVENT_ORDER_INVALID"
        seen_source_types.add(source_type)
        previous_record_age = record.age_days
        previous_record_order = _RECORDED_EVENT_ORDER[record.event_kind]
    return ObservationValidationStatus.PASS, "OK"


def _check_evidence(frame: object) -> tuple[ObservationValidationStatus, str]:
    frame = _observation_frame_parts(frame)
    provenance_status, provenance_reason, _policy, _trajectory = _truth_provenance(frame)
    if provenance_status is not ObservationValidationStatus.PASS:
        return provenance_status, provenance_reason
    opportunities = _opportunity_map(frame.truth)
    if not opportunities or not any(item.realized for item in opportunities.values()):
        return ObservationValidationStatus.UNEVALUABLE, "INSUFFICIENT_EVIDENCE"
    if not frame.visits:
        return ObservationValidationStatus.UNEVALUABLE, "INSUFFICIENT_EVIDENCE"
    observed_physical = 0
    for visit in frame.visits:
        if not isinstance(visit, ObservedVisit):
            raise TypeError("visits must contain ObservedVisit values")
        observed_physical += sum(
            observation.availability is MeasurementAvailability.OBSERVED
            and observation.channel in _PHYSICAL_CHANNELS
            for observation in visit.measurements
            if isinstance(observation, MeasurementObservation)
        )
    if observed_physical == 0:
        return ObservationValidationStatus.UNEVALUABLE, "INSUFFICIENT_EVIDENCE"
    try:
        _truth_measurements_by_point(
            frame.truth,
            {index for index, item in opportunities.items() if item.realized},
        )
        _source_event_data(frame.truth)
    except (TypeError, ValueError):
        return ObservationValidationStatus.UNEVALUABLE, "INSUFFICIENT_EVIDENCE"
    return ObservationValidationStatus.PASS, "OK"


def validate_observation_frame(frame: object) -> ObservationValidationReport:
    """Validate one evaluator-only frame without returning patient-level evidence.

    Malformed frame or private truth evidence is reported as ``UNEVALUABLE``.
    Violations observed in otherwise typed visible records are ``FAIL``.  The
    report contains only the fixed check names, statuses, and reason codes.
    """

    if not isinstance(frame, ObservationFrame):
        checks = tuple(
            ObservationCheck(name, ObservationValidationStatus.UNEVALUABLE, "MALFORMED_FRAME")
            for name in ObservationValidationReport.CHECK_NAMES
        )
        return ObservationValidationReport(ObservationValidationStatus.UNEVALUABLE, checks)
    evaluators = {
        "patient_identity": _check_patient_identity,
        "window": _check_window,
        "visit_references": _check_visit_references,
        "measurements": _check_measurements,
        "hidden_events": _check_hidden_events,
        "event_order": _check_event_order,
        "evidence": _check_evidence,
    }
    checks = tuple(
        _validation_check(name, lambda evaluator=evaluators[name]: evaluator(frame))
        for name in ObservationValidationReport.CHECK_NAMES
    )
    return ObservationValidationReport(_status_for_checks(checks), checks)


__all__ = [
    "OBSERVATION_STREAM_NAMES",
    "RECORDED_EVENT_CODES",
    "CensoringMode",
    "EncounterType",
    "EventRecordingDecision",
    "MeasurementAvailability",
    "MeasurementChannel",
    "MeasurementObservation",
    "MeasurementTruth",
    "ObservationCheck",
    "ObservationFrame",
    "ObservationPolicy",
    "ObservationTruth",
    "ObservationValidationReport",
    "ObservationValidationStatus",
    "ObservationWindow",
    "ObservedVisit",
    "RecordedEvent",
    "RecordedEventKind",
    "ValidationStatus",
    "VisitOpportunity",
    "generate_observation_frame",
    "observation_stream_identity",
    "observed_stream_identity",
    "validate_observation_frame",
]
