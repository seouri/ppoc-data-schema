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
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from numbers import Real
from types import MappingProxyType
from typing import Any, ClassVar

from synthetic.models import ClinicalEvent

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
        if any(event.patient_id != self.patient_id for event in source_events):
            raise ValueError("source events must identify the same synthetic patient")
        if any(
            decision.source_event_index >= len(source_events) for decision in event_decisions
        ):
            raise ValueError("event decision must reference a source event")
        if len({(item.source_point_index, item.channel) for item in measurement_truth}) != len(
            measurement_truth
        ):
            raise ValueError("measurement truth must not duplicate a source channel")
        if len({item.source_point_index for item in opportunities}) != len(opportunities):
            raise ValueError("opportunities must not duplicate a source point")
        _require_hash(self.latent_trajectory_hash, "latent_trajectory_hash")
        _require_hash(self.truth_hash, "truth_hash")

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
    "observation_stream_identity",
    "observed_stream_identity",
]
