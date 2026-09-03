"""Evaluator-only ancillary projection for a fictional thyroid pathway.

The projection consumes typed in-memory observation state and returns immutable
rows in the repository's exact descriptor shape.  It owns its fictional
terminology and synthetic identifier namespace; latent state and observation
truth never enter the returned mapping.
"""

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

PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_RESOURCE_NAMES = (
    "labs",
    "medications",
    "problem_list",
    "referrals",
)
PEDIATRIC_HYPOTHYROIDISM_DIAGNOSIS_CODE = "SYN-PEDIATRIC-HYPOTHYROIDISM"
PEDIATRIC_HYPOTHYROIDISM_TSH_COMPONENT = "SYN-HYPOTHYROIDISM-TSH"
PEDIATRIC_HYPOTHYROIDISM_FREE_T4_COMPONENT = "SYN-HYPOTHYROIDISM-FREE-T4"
PEDIATRIC_HYPOTHYROIDISM_LAB_COMPONENT_NAMES = (
    PEDIATRIC_HYPOTHYROIDISM_TSH_COMPONENT,
    PEDIATRIC_HYPOTHYROIDISM_FREE_T4_COMPONENT,
)
PEDIATRIC_HYPOTHYROIDISM_LAB_RESULT_FLAG = "Synthetic"
PEDIATRIC_HYPOTHYROIDISM_REFERRAL_SPECIALTY = "Synthetic Pediatric Endocrinology"
PEDIATRIC_HYPOTHYROIDISM_MEDICATION_NAME = "Synthetic levothyroxine"
PEDIATRIC_HYPOTHYROIDISM_MEDICATION_RECORD_TYPE = "Internal"

# Readable aliases keep the closed fictional vocabulary discoverable without
# accepting caller-supplied terminology.
SYNTHETIC_PEDIATRIC_HYPOTHYROIDISM_DIAGNOSIS_CODE = (
    PEDIATRIC_HYPOTHYROIDISM_DIAGNOSIS_CODE
)
SYNTHETIC_HYPOTHYROIDISM_TSH_COMPONENT = PEDIATRIC_HYPOTHYROIDISM_TSH_COMPONENT
SYNTHETIC_HYPOTHYROIDISM_FREE_T4_COMPONENT = (
    PEDIATRIC_HYPOTHYROIDISM_FREE_T4_COMPONENT
)

_SYNTHETIC_PATIENT_TOKEN = re.compile(r"^syn-[A-Za-z0-9][A-Za-z0-9._-]*$")
_SYNTHETIC_VISIT_TOKEN = re.compile(r"^syn-[A-Za-z0-9][A-Za-z0-9._:-]*$")
_AGGREGATE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_AGGREGATE_UNSAFE_COMPONENTS = frozenset(
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
_PATH_EXTENSION = re.compile(
    r"\b[A-Za-z0-9_-]+\.(?:csv|tsv|json|parquet|txt|zip|gz)\b", re.IGNORECASE
)
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


class PediatricHypothyroidismAncillaryProjectionUnavailable(ValueError):
    """Fixed redacted error for an unsafe evaluator projection boundary."""


def _require_aggregate_safe_token(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if _AGGREGATE_TOKEN.fullmatch(value) is None:
        raise ValueError(
            f"{field_name} must be an ASCII token without whitespace or path separators"
        )
    if "/" in value or "\\" in value or _PATH_EXTENSION.search(value):
        raise ValueError(f"{field_name} must be aggregate-safe")
    components = tuple(re.findall(r"[a-z0-9]+", value.lower()))
    if _AGGREGATE_UNSAFE_COMPONENTS.intersection(components):
        raise ValueError(f"{field_name} must be aggregate-safe")
    return value


def _require_nonnegative_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be a nonnegative integer")
    if value < 0:
        raise ValueError(f"{field_name} must be a nonnegative integer")
    return value


def _require_supported_age(value: object, field_name: str) -> int:
    result = _require_nonnegative_integer(value, field_name)
    if result > MAX_AGE_DAYS:
        raise ValueError(f"{field_name} must be within supported age range")
    return result


def _require_synthetic_patient_id(value: object, field_name: str = "patient_id") -> str:
    if not isinstance(value, str) or _SYNTHETIC_PATIENT_TOKEN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must identify a fictional synthetic patient")
    return value


def _require_synthetic_visit_id(value: object, field_name: str = "visit_id") -> str:
    if not isinstance(value, str) or _SYNTHETIC_VISIT_TOKEN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must identify a fictional synthetic visit")
    return value


@dataclass(frozen=True, repr=False)
class PediatricHypothyroidismAncillaryPolicy:
    """Versioned, aggregate-safe policy metadata for the fictional pathway."""

    policy_id: str
    policy_version: str
    result_delay_days: int

    def __post_init__(self) -> None:
        _require_aggregate_safe_token(self.policy_id, "policy_id")
        _require_aggregate_safe_token(self.policy_version, "policy_version")
        _require_nonnegative_integer(self.result_delay_days, "result_delay_days")

    def __repr__(self) -> str:
        return "PediatricHypothyroidismAncillaryPolicy(<aggregate-only>)"


def _row_values(row: ResourceRow) -> dict[str, object]:
    values: dict[str, object] = {}
    for pair in row.values:
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise TypeError("row values must contain field/value pairs")
        field_name, value = pair
        if not isinstance(field_name, str) or field_name in values:
            raise ValueError("row values must contain unique field names")
        values[field_name] = value
    return values


@dataclass(frozen=True, repr=False)
class PediatricHypothyroidismAncillaryProjection:
    """Immutable exact-schema rows for one synthetic member."""

    patient_id: str = field(repr=False)
    shape: ResourceShape = field(repr=False)
    rows: Mapping[str, tuple[ResourceRow, ...]] = field(repr=False)

    PROJECTION_VERSION: ClassVar[str] = (
        "pediatric-hypothyroidism-ancillary-projection-v1"
    )

    def __post_init__(self) -> None:
        _require_synthetic_patient_id(self.patient_id)
        if not isinstance(self.shape, ResourceShape):
            raise TypeError("shape must be a ResourceShape")
        if not isinstance(self.rows, Mapping):
            raise TypeError("rows must be a mapping")
        if tuple(self.rows) != PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_RESOURCE_NAMES:
            raise ValueError(
                "rows must contain the four ancillary resources in fixed order"
            )

        normalized: dict[str, tuple[ResourceRow, ...]] = {}
        for resource_name in PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_RESOURCE_NAMES:
            resource_rows = self.rows[resource_name]
            if not isinstance(resource_rows, tuple):
                raise TypeError("resource rows must be tuples")
            if not all(isinstance(row, ResourceRow) for row in resource_rows):
                raise TypeError("resource rows must contain ResourceRow values")
            expected_fields = self.shape.field_names(resource_name)
            for row in resource_rows:
                if row.resource_name != resource_name:
                    raise ValueError("resource rows must use their fixed resource name")
                if tuple(field_name for field_name, _ in row.values) != expected_fields:
                    raise ValueError(
                        "resource rows must match the extracted descriptor field order"
                    )
                values = _row_values(row)
                if values.get("patient_id") != self.patient_id:
                    raise ValueError("resource rows must identify the projection patient")
            normalized[resource_name] = resource_rows
        object.__setattr__(self, "rows", MappingProxyType(normalized))

    def to_mapping(self) -> dict[str, object]:
        """Return visible rows only; evaluator-held source state is excluded."""

        return {
            "contract": self.PROJECTION_VERSION,
            "patient_id": self.patient_id,
            "resources": {
                resource_name: [
                    row.to_mapping() for row in self.rows[resource_name]
                ]
                for resource_name in PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_RESOURCE_NAMES
            },
        }

    def __repr__(self) -> str:
        return "PediatricHypothyroidismAncillaryProjection(<evaluator-only>)"


def _synthetic_ancillary_id(patient_id: str, role: str) -> str:
    material = (
        f"pediatric-hypothyroidism-ancillary-id-v1\x1f{patient_id}\x1f{role}"
    ).encode()
    return f"syn-{hashlib.sha256(material).hexdigest()}"


def _resource_row(
    resource_name: str,
    values: Mapping[str, object],
    shape: ResourceShape,
) -> ResourceRow:
    fields = shape.field_names(resource_name)
    return ResourceRow(
        resource_name,
        tuple((field_name, values.get(field_name, "")) for field_name in fields),
    )


def project_pediatric_hypothyroidism_ancillary_resources(
    member: CohortMember,
    shape: ResourceShape,
    policy: PediatricHypothyroidismAncillaryPolicy,
) -> PediatricHypothyroidismAncillaryProjection:
    """Project visible fictional descendants into exact-schema resource rows."""

    if (
        not isinstance(member, CohortMember)
        or not isinstance(shape, ResourceShape)
        or not isinstance(policy, PediatricHypothyroidismAncillaryPolicy)
    ):
        raise PediatricHypothyroidismAncillaryProjectionUnavailable(
            "pediatric hypothyroidism ancillary projection unavailable"
        )

    try:
        frame = member.frame
        observation_report = validate_observation_frame(frame)
        if observation_report.status is not ObservationValidationStatus.PASS:
            raise ValueError("observation frame did not pass validation")

        patient_id = member.demographics.patient_id
        trajectory = member.trajectory
        truth_trajectory = frame.truth.latent_trajectory
        if (
            patient_id != frame.patient_id
            or not isinstance(trajectory, AgeRegimeDisorderTrajectory)
            or not isinstance(truth_trajectory, AgeRegimeDisorderTrajectory)
            or not trajectory.physiology.points
            or trajectory.physiology.points[0].patient_id != patient_id
            or trajectory != truth_trajectory
            or trajectory.events != frame.truth.source_events
        ):
            raise ValueError("member trajectory is not bound to frame truth")

        rows: dict[str, tuple[ResourceRow, ...]] = {
            resource_name: ()
            for resource_name in PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_RESOURCE_NAMES
        }
        if trajectory.disorder.kind is not DisorderKind.PEDIATRIC_HYPOTHYROIDISM:
            return PediatricHypothyroidismAncillaryProjection(patient_id, shape, rows)

        if any(
            not _REQUIRED_FIELDS[name].issubset(shape.field_names(name))
            for name in PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_RESOURCE_NAMES
        ):
            raise ValueError("descriptor shape lacks required ancillary fields")

        realized_opportunities = tuple(
            opportunity
            for opportunity in frame.truth.opportunities
            if opportunity.realized
        )
        if len(realized_opportunities) != len(frame.visits):
            raise ValueError("realized opportunities do not match visible visits")
        visit_by_source_point = {
            opportunity.source_point_index: visit
            for opportunity, visit in zip(
                realized_opportunities,
                frame.visits,
                strict=True,
            )
        }

        visible_events: dict[RecordedEventKind, RecordedEvent] = {}
        for event in frame.events:
            if not isinstance(event, RecordedEvent):
                raise TypeError("visible events must be RecordedEvent values")
            visible_events.setdefault(event.event_kind, event)

        def visible_visit(
            event_kind: RecordedEventKind,
        ) -> tuple[RecordedEvent, object] | None:
            event = visible_events.get(event_kind)
            if event is None or event.opportunity_index is None:
                return None
            visit = visit_by_source_point.get(event.opportunity_index)
            if visit is None:
                raise ValueError("recorded event has no linked visible visit")
            _require_synthetic_visit_id(visit.visit_id)
            return event, visit

        recognition = visible_visit(RecordedEventKind.RECOGNITION)
        if recognition is not None:
            event, visit = recognition
            _require_supported_age(event.age_days, "recognition age_days")
            rows["referrals"] = (
                _resource_row(
                    "referrals",
                    {
                        "patient_id": patient_id,
                        "visit_id": visit.visit_id,
                        "referral_id": _synthetic_ancillary_id(patient_id, "referral"),
                        "referral_date_age_in_days": event.age_days,
                        "requested_specialty": PEDIATRIC_HYPOTHYROIDISM_REFERRAL_SPECIALTY,
                        "referral_number_of_visits": 1,
                    },
                    shape,
                ),
            )

        workup = visible_visit(RecordedEventKind.WORKUP)
        if workup is not None:
            event, visit = workup
            _require_supported_age(event.age_days, "workup age_days")
            result_age = _require_supported_age(
                event.age_days + policy.result_delay_days,
                "lab_result_date_age_in_days",
            )
            lab_order_id = _synthetic_ancillary_id(patient_id, "lab-order")
            rows["labs"] = tuple(
                _resource_row(
                    "labs",
                    {
                        "patient_id": patient_id,
                        "visit_id": visit.visit_id,
                        "lab_order_id": lab_order_id,
                        "result_line_num": line_number,
                        "lab_order_date_age_in_days": event.age_days,
                        "lab_result_date_age_in_days": result_age,
                        "result_component_name": component,
                        "result_loinc_code": "",
                        "result_value": "",
                        "result_flag": PEDIATRIC_HYPOTHYROIDISM_LAB_RESULT_FLAG,
                    },
                    shape,
                )
                for line_number, component in enumerate(
                    PEDIATRIC_HYPOTHYROIDISM_LAB_COMPONENT_NAMES,
                    start=1,
                )
            )

        diagnosis = visible_visit(RecordedEventKind.DIAGNOSIS)
        if diagnosis is not None:
            diagnosis_event, diagnosis_visit = diagnosis
            _require_supported_age(diagnosis_event.age_days, "diagnosis age_days")
            rows["problem_list"] = (
                _resource_row(
                    "problem_list",
                    {
                        "patient_id": patient_id,
                        "problem_list_id": _synthetic_ancillary_id(
                            patient_id, "problem-list"
                        ),
                        "noted_date_age_in_days": diagnosis_event.age_days,
                        "resolved_date_age_in_days": "",
                        "pl_diag": PEDIATRIC_HYPOTHYROIDISM_DIAGNOSIS_CODE,
                    },
                    shape,
                ),
            )

            treatment_age = next(
                (
                    event.age_days
                    for event in trajectory.events
                    if event.event_type == "treatment_start"
                ),
                None,
            )
            if treatment_age is not None and treatment_age >= diagnosis_event.age_days:
                _require_supported_age(treatment_age, "treatment_start age_days")
                rows["medications"] = (
                    _resource_row(
                        "medications",
                        {
                            "patient_id": patient_id,
                            "visit_id": diagnosis_visit.visit_id,
                            "med_record_id": _synthetic_ancillary_id(
                                patient_id, "medication"
                            ),
                            "med_order_date_age_in_days": diagnosis_event.age_days,
                            "med_start_date_age_in_days": treatment_age,
                            "med_end_date_age_in_days": "",
                            "med_record_type": PEDIATRIC_HYPOTHYROIDISM_MEDICATION_RECORD_TYPE,
                            "med_simple_generic_name": PEDIATRIC_HYPOTHYROIDISM_MEDICATION_NAME,
                        },
                        shape,
                    ),
                )

        return PediatricHypothyroidismAncillaryProjection(patient_id, shape, rows)
    except Exception:  # noqa: BLE001 - evaluator boundary is intentionally redacted
        raise PediatricHypothyroidismAncillaryProjectionUnavailable(
            "pediatric hypothyroidism ancillary projection failed"
        ) from None
