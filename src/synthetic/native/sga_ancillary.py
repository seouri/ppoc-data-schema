"""Evaluator-only ancillary projection for a fictional SGA pathway."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import ClassVar

from synthetic.cohort import CohortMember
from synthetic.models import MAX_AGE_DAYS, AgeRegimeDisorderTrajectory, DisorderKind
from synthetic.native.observations import (
    ObservationValidationStatus,
    RecordedEvent,
    RecordedEventKind,
    validate_observation_frame,
)
from synthetic.native.resources import ResourceRow, ResourceShape

SGA_ANCILLARY_RESOURCE_NAMES = ("labs", "medications", "problem_list", "referrals")
SGA_DIAGNOSIS_CODE = "SYN-SGA"
SGA_GESTATIONAL_AGE_COMPONENT = "SYN-SGA-GESTATIONAL-AGE"
SGA_BIRTH_SIZE_COMPONENT = "SYN-SGA-BIRTH-SIZE"
SGA_LAB_COMPONENT_NAMES = (SGA_GESTATIONAL_AGE_COMPONENT, SGA_BIRTH_SIZE_COMPONENT)
SGA_LAB_RESULT_FLAG = "Synthetic"
SGA_REFERRAL_SPECIALTY = "Synthetic Neonatology Follow-up"

_SYNTHETIC_PATIENT_TOKEN = re.compile(r"^syn-[A-Za-z0-9][A-Za-z0-9._-]*$")
_SYNTHETIC_VISIT_TOKEN = re.compile(r"^syn-[A-Za-z0-9][A-Za-z0-9._:-]*$")
_AGGREGATE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_PATH_EXTENSION = re.compile(
    r"\b[A-Za-z0-9_-]+\.(?:csv|tsv|json|parquet|txt|zip|gz)\b", re.IGNORECASE
)
_UNSAFE_TOKEN_PARTS = frozenset(
    {
        "patient",
        "visit",
        "path",
        "key",
        "identifier",
        "uuid",
        "sequence",
        "truth",
        "candidate",
        "match",
        "row",
        "resource",
        "latent",
    }
)

SYNTHETIC_SGA_DIAGNOSIS_CODE = SGA_DIAGNOSIS_CODE
SYNTHETIC_SGA_GESTATIONAL_AGE_COMPONENT = SGA_GESTATIONAL_AGE_COMPONENT
SYNTHETIC_SGA_BIRTH_SIZE_COMPONENT = SGA_BIRTH_SIZE_COMPONENT
_REQUIRED_FIELDS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "labs": frozenset(
            {
                "patient_id",
                "visit_id",
                "lab_order_id",
                "result_line_num",
                "lab_order_date_age_in_days",
                "lab_result_date_age_in_days",
                "result_component_name",
                "result_loinc_code",
                "result_value",
                "result_flag",
            }
        ),
        "medications": frozenset(
            {
                "patient_id",
                "visit_id",
                "med_record_id",
                "med_order_date_age_in_days",
                "med_start_date_age_in_days",
                "med_end_date_age_in_days",
                "med_record_type",
                "med_simple_generic_name",
            }
        ),
        "problem_list": frozenset(
            {
                "patient_id",
                "problem_list_id",
                "noted_date_age_in_days",
                "resolved_date_age_in_days",
                "pl_diag",
            }
        ),
        "referrals": frozenset(
            {
                "patient_id",
                "visit_id",
                "referral_id",
                "referral_date_age_in_days",
                "requested_specialty",
                "referral_number_of_visits",
            }
        ),
    }
)


class SgaAncillaryProjectionUnavailable(ValueError):
    """Fixed redacted error for an unsafe evaluator projection boundary."""


def _require_safe_token(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if (
        _AGGREGATE_TOKEN.fullmatch(value) is None
        or "/" in value
        or "\\" in value
        or _PATH_EXTENSION.search(value)
    ):
        raise ValueError(f"{field_name} must be aggregate-safe")
    if _UNSAFE_TOKEN_PARTS.intersection(re.findall(r"[a-z0-9]+", value.lower())):
        raise ValueError(f"{field_name} must be aggregate-safe")
    return value


def _require_nonnegative_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a nonnegative integer")
    return value


def _require_age(value: object, field_name: str) -> int:
    result = _require_nonnegative_integer(value, field_name)
    if result > MAX_AGE_DAYS:
        raise ValueError(f"{field_name} must be within supported age range")
    return result


def _require_patient_id(value: object) -> str:
    if not isinstance(value, str) or _SYNTHETIC_PATIENT_TOKEN.fullmatch(value) is None:
        raise ValueError("patient_id must identify a fictional synthetic patient")
    return value


def _row_values(row: ResourceRow) -> dict[str, object]:
    return dict(row.values)


@dataclass(frozen=True, repr=False)
class SgaAncillaryPolicy:
    """Versioned, aggregate-safe policy metadata for the fictional pathway."""

    policy_id: str
    policy_version: str
    result_delay_days: int

    def __post_init__(self) -> None:
        _require_safe_token(self.policy_id, "policy_id")
        _require_safe_token(self.policy_version, "policy_version")
        _require_nonnegative_integer(self.result_delay_days, "result_delay_days")

    def __repr__(self) -> str:
        return "SgaAncillaryPolicy(<aggregate-only>)"


@dataclass(frozen=True, repr=False)
class SgaAncillaryProjection:
    """Immutable exact-schema rows for one synthetic member."""

    patient_id: str = field(repr=False)
    shape: ResourceShape = field(repr=False)
    rows: Mapping[str, tuple[ResourceRow, ...]] = field(repr=False)

    PROJECTION_VERSION: ClassVar[str] = "sga-ancillary-projection-v1"

    def __post_init__(self) -> None:
        _require_patient_id(self.patient_id)
        if not isinstance(self.shape, ResourceShape) or not isinstance(self.rows, Mapping):
            raise TypeError("shape and rows must use evaluator resource contracts")
        if tuple(self.rows) != SGA_ANCILLARY_RESOURCE_NAMES:
            raise ValueError("rows must contain the four ancillary resources in fixed order")
        normalized: dict[str, tuple[ResourceRow, ...]] = {}
        for name in SGA_ANCILLARY_RESOURCE_NAMES:
            resource_rows = self.rows[name]
            if not isinstance(resource_rows, tuple) or not all(
                isinstance(row, ResourceRow) for row in resource_rows
            ):
                raise TypeError("resource rows must be tuples of ResourceRow values")
            for row in resource_rows:
                if row.resource_name != name or tuple(
                    field for field, _ in row.values
                ) != self.shape.field_names(name):
                    raise ValueError("resource rows must match their descriptor field order")
                if _row_values(row).get("patient_id") != self.patient_id:
                    raise ValueError("resource rows must identify the projection patient")
            normalized[name] = resource_rows
        object.__setattr__(self, "rows", MappingProxyType(normalized))

    def to_mapping(self) -> dict[str, object]:
        return {
            "contract": self.PROJECTION_VERSION,
            "patient_id": self.patient_id,
            "resources": {
                name: [row.to_mapping() for row in self.rows[name]]
                for name in SGA_ANCILLARY_RESOURCE_NAMES
            },
        }

    def __repr__(self) -> str:
        return "SgaAncillaryProjection(<evaluator-only>)"


def _synthetic_ancillary_id(patient_id: str, role: str) -> str:
    material = f"sga-ancillary-id-v1\x1f{patient_id}\x1f{role}".encode()
    return f"syn-{hashlib.sha256(material).hexdigest()}"


def _resource_row(name: str, values: Mapping[str, object], shape: ResourceShape) -> ResourceRow:
    return ResourceRow(
        name,
        tuple((field_name, values.get(field_name, "")) for field_name in shape.field_names(name)),
    )


def project_sga_ancillary_resources(
    member: CohortMember, shape: ResourceShape, policy: SgaAncillaryPolicy
) -> SgaAncillaryProjection:
    """Project first visible SGA descendants into exact-schema resource rows."""
    if (
        not isinstance(member, CohortMember)
        or not isinstance(shape, ResourceShape)
        or not isinstance(policy, SgaAncillaryPolicy)
    ):
        raise SgaAncillaryProjectionUnavailable("sga ancillary projection unavailable")
    try:
        frame = member.frame
        if validate_observation_frame(frame).status is not ObservationValidationStatus.PASS:
            raise ValueError
        patient_id = _require_patient_id(member.demographics.patient_id)
        trajectory = member.trajectory
        if (
            not isinstance(trajectory, AgeRegimeDisorderTrajectory)
            or patient_id != frame.patient_id
            or trajectory != frame.truth.latent_trajectory
            or trajectory.events != frame.truth.source_events
            or not trajectory.physiology.points
            or trajectory.physiology.points[0].patient_id != patient_id
        ):
            raise ValueError
        rows: dict[str, tuple[ResourceRow, ...]] = {
            name: () for name in SGA_ANCILLARY_RESOURCE_NAMES
        }
        if trajectory.disorder.kind is not DisorderKind.SMALL_FOR_GESTATIONAL_AGE:
            return SgaAncillaryProjection(patient_id, shape, rows)
        if any(
            not _REQUIRED_FIELDS[name].issubset(shape.field_names(name))
            for name in SGA_ANCILLARY_RESOURCE_NAMES
        ):
            raise ValueError
        realized = tuple(item for item in frame.truth.opportunities if item.realized)
        if len(realized) != len(frame.visits):
            raise ValueError
        visits = {
            item.source_point_index: visit
            for item, visit in zip(realized, frame.visits, strict=True)
        }
        events: dict[RecordedEventKind, RecordedEvent] = {}
        for event in frame.events:
            if not isinstance(event, RecordedEvent):
                raise TypeError
            events.setdefault(event.event_kind, event)

        def linked(kind: RecordedEventKind) -> tuple[RecordedEvent, object] | None:
            event = events.get(kind)
            if event is None or event.opportunity_index is None:
                return None
            visit = visits.get(event.opportunity_index)
            if (
                visit is None
                or not isinstance(visit.visit_id, str)
                or _SYNTHETIC_VISIT_TOKEN.fullmatch(visit.visit_id) is None
            ):
                raise ValueError
            return event, visit

        recognition = linked(RecordedEventKind.RECOGNITION)
        if recognition:
            event, visit = recognition
            rows["referrals"] = (
                _resource_row(
                    "referrals",
                    {
                        "patient_id": patient_id,
                        "visit_id": visit.visit_id,
                        "referral_id": _synthetic_ancillary_id(patient_id, "referral"),
                        "referral_date_age_in_days": _require_age(
                            event.age_days, "recognition age_days"
                        ),
                        "requested_specialty": SGA_REFERRAL_SPECIALTY,
                        "referral_number_of_visits": 1,
                    },
                    shape,
                ),
            )
        workup = linked(RecordedEventKind.WORKUP)
        if workup:
            event, visit = workup
            order_age = _require_age(event.age_days, "workup age_days")
            result_age = _require_age(
                order_age + policy.result_delay_days, "lab_result_date_age_in_days"
            )
            order_id = _synthetic_ancillary_id(patient_id, "lab-order")
            rows["labs"] = tuple(
                _resource_row(
                    "labs",
                    {
                        "patient_id": patient_id,
                        "visit_id": visit.visit_id,
                        "lab_order_id": order_id,
                        "result_line_num": number,
                        "lab_order_date_age_in_days": order_age,
                        "lab_result_date_age_in_days": result_age,
                        "result_component_name": component,
                        "result_loinc_code": "",
                        "result_value": "",
                        "result_flag": SGA_LAB_RESULT_FLAG,
                    },
                    shape,
                )
                for number, component in enumerate(SGA_LAB_COMPONENT_NAMES, 1)
            )
        diagnosis = linked(RecordedEventKind.DIAGNOSIS)
        if diagnosis:
            event, _ = diagnosis
            rows["problem_list"] = (
                _resource_row(
                    "problem_list",
                    {
                        "patient_id": patient_id,
                        "problem_list_id": _synthetic_ancillary_id(patient_id, "problem-list"),
                        "noted_date_age_in_days": _require_age(
                            event.age_days, "diagnosis age_days"
                        ),
                        "resolved_date_age_in_days": "",
                        "pl_diag": SGA_DIAGNOSIS_CODE,
                    },
                    shape,
                ),
            )
        return SgaAncillaryProjection(patient_id, shape, rows)
    except Exception:  # noqa: BLE001 - evaluator boundary is intentionally redacted
        raise SgaAncillaryProjectionUnavailable("sga ancillary projection failed") from None
