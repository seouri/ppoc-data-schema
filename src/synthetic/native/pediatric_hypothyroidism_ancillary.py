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
from enum import Enum
from types import MappingProxyType
from typing import ClassVar

from synthetic.cohort import CohortMember
from synthetic.models import (
    MAX_AGE_DAYS,
    AgeRegimeDisorderTrajectory,
    ClinicalEvent,
    DisorderKind,
)
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


PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_CHECK_NAMES = (
    "pathway_scope",
    "row_schema",
    "causal_timing",
    "cross_resource_links",
    "source_evidence",
)


class PediatricHypothyroidismAncillaryValidationStatus(str, Enum):
    """Aggregate status for one fictional pathway validation report."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNEVALUABLE = "UNEVALUABLE"


PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_REASON_CODES_BY_STATUS: Mapping[
    PediatricHypothyroidismAncillaryValidationStatus, frozenset[str]
] = MappingProxyType(
    {
        PediatricHypothyroidismAncillaryValidationStatus.PASS: frozenset({"OK"}),
        PediatricHypothyroidismAncillaryValidationStatus.FAIL: frozenset(
            {
                "PATIENT_MISMATCH",
                "SCHEMA_SHAPE_INVALID",
                "ROW_SCHEMA_INVALID",
                "PATHWAY_SCOPE_INVALID",
                "CAUSAL_TIMING_INVALID",
                "CROSS_RESOURCE_LINK_INVALID",
                "SOURCE_EVIDENCE_INVALID",
                "MALFORMED_PROJECTION",
                "INVALID_ID",
                "INVALID_CODE",
                "INVALID_VALUE",
                "DUPLICATE_ROW",
                "EVENT_ORDER_INVALID",
                "TIMING_INVALID",
                "VISIT_REFERENCE_INVALID",
                "PATHWAY_OUT_OF_SCOPE",
            }
        ),
        PediatricHypothyroidismAncillaryValidationStatus.UNEVALUABLE: frozenset(
            {
                "MALFORMED_ANCILLARY",
                "MALFORMED_MEMBER",
                "INSUFFICIENT_EVIDENCE",
                "SOURCE_EVIDENCE_UNAVAILABLE",
            }
        ),
    }
)
PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_REASON_CODES = frozenset(
    reason
    for reasons in PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_REASON_CODES_BY_STATUS.values()
    for reason in reasons
)

_PEDIATRIC_HYPOTHYROIDISM_INTEGER_FIELDS = frozenset(
    {
        "result_line_num",
        "lab_order_date_age_in_days",
        "lab_result_date_age_in_days",
        "med_order_date_age_in_days",
        "med_start_date_age_in_days",
        "med_end_date_age_in_days",
        "noted_date_age_in_days",
        "resolved_date_age_in_days",
        "referral_date_age_in_days",
        "referral_number_of_visits",
    }
)
_PEDIATRIC_HYPOTHYROIDISM_OPTIONAL_INTEGER_FIELDS = frozenset(
    {"med_end_date_age_in_days", "resolved_date_age_in_days"}
)
_PEDIATRIC_HYPOTHYROIDISM_AGE_FIELDS = frozenset(
    field_name
    for field_name in _PEDIATRIC_HYPOTHYROIDISM_INTEGER_FIELDS
    if field_name not in {"result_line_num", "referral_number_of_visits"}
)


def _validation_status_for_checks(
    checks: tuple[PediatricHypothyroidismAncillaryCheck, ...],
) -> PediatricHypothyroidismAncillaryValidationStatus:
    if any(
        check.status is PediatricHypothyroidismAncillaryValidationStatus.FAIL
        for check in checks
    ):
        return PediatricHypothyroidismAncillaryValidationStatus.FAIL
    if any(
        check.status is PediatricHypothyroidismAncillaryValidationStatus.UNEVALUABLE
        for check in checks
    ):
        return PediatricHypothyroidismAncillaryValidationStatus.UNEVALUABLE
    return PediatricHypothyroidismAncillaryValidationStatus.PASS


@dataclass(frozen=True, repr=False)
class PediatricHypothyroidismAncillaryCheck:
    """One fixed aggregate-only validation check."""

    name: str
    status: PediatricHypothyroidismAncillaryValidationStatus
    reason_code: str

    CHECK_NAMES: ClassVar[tuple[str, ...]] = (
        PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_CHECK_NAMES
    )
    REASON_CODES: ClassVar[frozenset[str]] = (
        PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_REASON_CODES
    )

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or self.name not in self.CHECK_NAMES:
            raise ValueError("unknown pediatric hypothyroidism ancillary check name")
        if not isinstance(
            self.status, PediatricHypothyroidismAncillaryValidationStatus
        ):
            raise TypeError(
                "status must be a PediatricHypothyroidismAncillaryValidationStatus"
            )
        if (
            not isinstance(self.reason_code, str)
            or self.reason_code
            not in PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_REASON_CODES_BY_STATUS[
                self.status
            ]
        ):
            raise ValueError("reason_code must be compatible with status")

    @property
    def check_id(self) -> str:
        return self.name

    def to_mapping(self) -> dict[str, str]:
        return {
            "name": self.name,
            "status": self.status.value,
            "reason_code": self.reason_code,
        }

    def __repr__(self) -> str:
        return (
            "PediatricHypothyroidismAncillaryCheck("
            f"name={self.name!r}, status={self.status.value!r})"
        )


@dataclass(frozen=True, repr=False)
class PediatricHypothyroidismAncillaryValidationReport:
    """Immutable aggregate report with no row or source evidence."""

    status: PediatricHypothyroidismAncillaryValidationStatus
    checks: tuple[PediatricHypothyroidismAncillaryCheck, ...]

    CHECK_NAMES: ClassVar[tuple[str, ...]] = (
        PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_CHECK_NAMES
    )

    def __post_init__(self) -> None:
        if not isinstance(
            self.status, PediatricHypothyroidismAncillaryValidationStatus
        ):
            raise TypeError(
                "status must be a PediatricHypothyroidismAncillaryValidationStatus"
            )
        if not isinstance(self.checks, tuple) or not self.checks:
            raise ValueError("checks must be a nonempty tuple")
        if not all(
            isinstance(check, PediatricHypothyroidismAncillaryCheck)
            for check in self.checks
        ):
            raise TypeError(
                "checks must contain PediatricHypothyroidismAncillaryCheck values"
            )
        names = tuple(check.name for check in self.checks)
        if len(names) != len(set(names)) or set(names) != set(self.CHECK_NAMES):
            raise ValueError(
                "checks must contain every fixed pediatric hypothyroidism ancillary "
                "check exactly once"
            )
        ordered = tuple(
            sorted(self.checks, key=lambda check: self.CHECK_NAMES.index(check.name))
        )
        if self.status is not _validation_status_for_checks(ordered):
            raise ValueError("status must match pediatric hypothyroidism check statuses")
        object.__setattr__(self, "checks", ordered)

    @property
    def check_counts(self) -> Mapping[str, int]:
        return MappingProxyType(
            {
                status.value: sum(check.status is status for check in self.checks)
                for status in PediatricHypothyroidismAncillaryValidationStatus
            }
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "check_counts": dict(self.check_counts),
            "checks": [check.to_mapping() for check in self.checks],
        }

    def __repr__(self) -> str:
        return (
            "PediatricHypothyroidismAncillaryValidationReport("
            f"status={self.status.value!r}, checks={len(self.checks)})"
        )


def _is_synthetic_patient_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and _SYNTHETIC_PATIENT_TOKEN.fullmatch(value) is not None
    )


def _is_synthetic_visit_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and _SYNTHETIC_VISIT_TOKEN.fullmatch(value) is not None
    )


def _ancillary_row_types_are_valid(values: Mapping[str, object]) -> bool:
    """Check scalar kinds before comparisons can coerce equal values."""

    for field_name, value in values.items():
        if field_name in _PEDIATRIC_HYPOTHYROIDISM_INTEGER_FIELDS:
            if value == "":
                if field_name not in _PEDIATRIC_HYPOTHYROIDISM_OPTIONAL_INTEGER_FIELDS:
                    return False
            elif (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                return False
        elif not isinstance(value, str):
            return False
    return True


def _source_independent_row_reason(
    resource_name: str,
    values: Mapping[str, object],
    patient_id: object,
) -> str | None:
    """Validate fixed fictional values without consulting private evidence."""

    if not isinstance(patient_id, str):
        return "PATIENT_MISMATCH"
    expected: dict[str, object] = {name: "" for name in values}
    expected["patient_id"] = patient_id
    if resource_name == "labs":
        expected.update(
            {
                "lab_order_id": _synthetic_ancillary_id(patient_id, "lab-order"),
                "result_loinc_code": "",
                "result_value": "",
                "result_flag": PEDIATRIC_HYPOTHYROIDISM_LAB_RESULT_FLAG,
            }
        )
    elif resource_name == "medications":
        expected.update(
            {
                "med_record_id": _synthetic_ancillary_id(
                    patient_id, "medication"
                ),
                "med_end_date_age_in_days": "",
                "med_record_type": PEDIATRIC_HYPOTHYROIDISM_MEDICATION_RECORD_TYPE,
                "med_simple_generic_name": PEDIATRIC_HYPOTHYROIDISM_MEDICATION_NAME,
            }
        )
    elif resource_name == "problem_list":
        expected.update(
            {
                "problem_list_id": _synthetic_ancillary_id(
                    patient_id, "problem-list"
                ),
                "resolved_date_age_in_days": "",
                "pl_diag": PEDIATRIC_HYPOTHYROIDISM_DIAGNOSIS_CODE,
            }
        )
    elif resource_name == "referrals":
        expected.update(
            {
                "referral_id": _synthetic_ancillary_id(patient_id, "referral"),
                "requested_specialty": PEDIATRIC_HYPOTHYROIDISM_REFERRAL_SPECIALTY,
                "referral_number_of_visits": 1,
            }
        )
    else:
        return None

    identifier_fields = {
        "labs": {"lab_order_id"},
        "medications": {"med_record_id"},
        "problem_list": {"problem_list_id"},
        "referrals": {"referral_id"},
    }[resource_name]
    for field_name in identifier_fields:
        if values.get(field_name) != expected[field_name]:
            return "INVALID_ID"
    if resource_name == "labs" and values.get("result_component_name") not in (
        PEDIATRIC_HYPOTHYROIDISM_TSH_COMPONENT,
        PEDIATRIC_HYPOTHYROIDISM_FREE_T4_COMPONENT,
    ):
        return "INVALID_CODE"
    if resource_name == "problem_list" and values.get("pl_diag") != (
        PEDIATRIC_HYPOTHYROIDISM_DIAGNOSIS_CODE
    ):
        return "INVALID_CODE"
    for field_name, expected_value in expected.items():
        if field_name in _PEDIATRIC_HYPOTHYROIDISM_INTEGER_FIELDS or field_name in {
            "visit_id",
            "result_component_name",
            "patient_id",
        }:
            continue
        if values.get(field_name) != expected_value:
            return "INVALID_VALUE"
    for field_name in _PEDIATRIC_HYPOTHYROIDISM_OPTIONAL_INTEGER_FIELDS:
        if field_name in values and values[field_name] != "":
            return "INVALID_VALUE"
    if (
        resource_name == "referrals"
        and values.get("referral_number_of_visits") != 1
    ):
        return "INVALID_VALUE"
    return None


def _typed_treatment_start_age(
    trajectory: AgeRegimeDisorderTrajectory,
) -> tuple[bool, int | None]:
    """Return typed treatment timing, or unknown when the object is malformed."""

    try:
        events = trajectory.events
        if not isinstance(events, tuple):
            return False, None
        points = trajectory.physiology.points
        if not points:
            return False, None
        patient_id = points[0].patient_id
        treatment_ages: list[int] = []
        for event in events:
            if not isinstance(event, ClinicalEvent):
                return False, None
            if (
                not isinstance(event.event_type, str)
                or event.event_type
                not in {
                    "latent_onset",
                    "observable_phenotype",
                    "recognition_opportunity",
                    "workup",
                    "recorded_diagnosis",
                    "treatment_start",
                    "treatment_response",
                    "treatment_nonresponse",
                }
                or event.patient_id != patient_id
                or isinstance(event.age_days, bool)
                or not isinstance(event.age_days, int)
                or not 0 <= event.age_days <= MAX_AGE_DAYS
                or event.code is not None
                or type(event.hidden) is not bool
                or event.hidden is not (event.event_type == "latent_onset")
            ):
                return False, None
            if event.event_type == "treatment_start":
                treatment_ages.append(event.age_days)
        if len(treatment_ages) > 1:
            return False, None
        return True, treatment_ages[0] if treatment_ages else None
    except (AttributeError, TypeError, ValueError):
        return False, None


def _pediatric_hypothyroidism_ancillary_report(
    states: Mapping[
        str,
        tuple[PediatricHypothyroidismAncillaryValidationStatus, str],
    ],
) -> PediatricHypothyroidismAncillaryValidationReport:
    checks = tuple(
        PediatricHypothyroidismAncillaryCheck(
            name,
            states[name][0],
            states[name][1],
        )
        for name in PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_CHECK_NAMES
    )
    return PediatricHypothyroidismAncillaryValidationReport(
        _validation_status_for_checks(checks), checks
    )


def validate_pediatric_hypothyroidism_ancillary_resources(
    member: CohortMember,
    projection: PediatricHypothyroidismAncillaryProjection,
    policy: PediatricHypothyroidismAncillaryPolicy,
) -> PediatricHypothyroidismAncillaryValidationReport:
    """Return fixed aggregate checks for one fictional ancillary projection."""

    if (
        not isinstance(member, CohortMember)
        or not isinstance(projection, PediatricHypothyroidismAncillaryProjection)
        or not isinstance(policy, PediatricHypothyroidismAncillaryPolicy)
    ):
        raise PediatricHypothyroidismAncillaryProjectionUnavailable(
            "pediatric hypothyroidism ancillary projection unavailable"
        )

    states: dict[
        str, tuple[PediatricHypothyroidismAncillaryValidationStatus, str]
    ] = {
        name: (PediatricHypothyroidismAncillaryValidationStatus.PASS, "OK")
        for name in PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_CHECK_NAMES
    }

    def mark(
        name: str,
        status: PediatricHypothyroidismAncillaryValidationStatus,
        reason_code: str,
    ) -> None:
        current = states[name][0]
        if current is PediatricHypothyroidismAncillaryValidationStatus.FAIL:
            return
        if (
            status is PediatricHypothyroidismAncillaryValidationStatus.FAIL
            or current is PediatricHypothyroidismAncillaryValidationStatus.PASS
        ):
            states[name] = (status, reason_code)

    # All checks in this block use visible rows and visible events only.  The
    # private observation evidence is deliberately consulted afterwards.
    target_kind: bool | None = None
    typed_treatment_known = False
    typed_treatment_age: int | None = None
    trajectory: AgeRegimeDisorderTrajectory | None = None
    member_id: object = None
    visible_row_values: dict[str, list[dict[str, object]]] = {
        resource_name: []
        for resource_name in PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_RESOURCE_NAMES
    }
    visible_events: dict[RecordedEventKind, RecordedEvent] = {}
    shape_fields: dict[str, tuple[str, ...]] = {}
    rows: Mapping[str, tuple[ResourceRow, ...]] | dict[str, tuple[ResourceRow, ...]] = {}
    visible_visit_ids: frozenset[object] = frozenset()
    visible_lab_order_ages: set[int] = set()
    visible_referral_ages: set[int] = set()
    visible_problem_ages: set[int] = set()

    try:
        member_id = member.demographics.patient_id
        projection_id = projection.patient_id
        if (
            projection_id != member_id
            or not _is_synthetic_patient_id(projection_id)
        ):
            mark(
                "cross_resource_links",
                PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                "PATIENT_MISMATCH",
            )

        trajectory = member.trajectory
        if not isinstance(trajectory, AgeRegimeDisorderTrajectory):
            mark(
                "pathway_scope",
                PediatricHypothyroidismAncillaryValidationStatus.UNEVALUABLE,
                "MALFORMED_MEMBER",
            )
        else:
            target_kind = (
                trajectory.disorder.kind
                is DisorderKind.PEDIATRIC_HYPOTHYROIDISM
            )
            if target_kind:
                typed_treatment_known, typed_treatment_age = (
                    _typed_treatment_start_age(trajectory)
                )

        rows = projection.rows
        if not isinstance(rows, Mapping):
            mark(
                "row_schema",
                PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                "SCHEMA_SHAPE_INVALID",
            )
            rows = {}
        elif tuple(rows) != PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_RESOURCE_NAMES:
            mark(
                "row_schema",
                PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                "SCHEMA_SHAPE_INVALID",
            )

        shape = projection.shape
        if not isinstance(shape, ResourceShape):
            mark(
                "row_schema",
                PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                "SCHEMA_SHAPE_INVALID",
            )
        else:
            for resource_name in PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_RESOURCE_NAMES:
                try:
                    fields = shape.field_names(resource_name)
                except Exception:  # noqa: BLE001 - malformed shapes are redacted
                    mark(
                        "row_schema",
                        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                        "SCHEMA_SHAPE_INVALID",
                    )
                    continue
                shape_fields[resource_name] = fields
                if not _REQUIRED_FIELDS[resource_name].issubset(fields):
                    mark(
                        "row_schema",
                        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                        "SCHEMA_SHAPE_INVALID",
                    )

        try:
            visible_visit_ids = frozenset(
                visit.visit_id for visit in member.frame.visits
            )
        except Exception:  # noqa: BLE001 - visible records are aggregate-only
            visible_visit_ids = frozenset()

        nonempty_resources: set[str] = set()
        for resource_name in PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_RESOURCE_NAMES:
            resource_rows = rows.get(resource_name)
            if not isinstance(resource_rows, tuple):
                mark(
                    "row_schema",
                    PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                    "SCHEMA_SHAPE_INVALID",
                )
                continue
            if resource_rows:
                nonempty_resources.add(resource_name)
            if len(resource_rows) > (2 if resource_name == "labs" else 1):
                mark(
                    "row_schema",
                    PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                    "DUPLICATE_ROW",
                )
            fields = shape_fields.get(resource_name)
            if fields is None:
                continue

            seen: set[tuple[tuple[str, object], ...]] = set()
            lab_pairs: set[tuple[object, object]] = set()
            lab_order_ids: set[object] = set()
            lab_visits: set[object] = set()
            lab_order_ages: set[object] = set()
            lab_result_ages: set[object] = set()
            medication_order_ages: set[object] = set()
            medication_start_ages: set[object] = set()
            medication_visits: set[object] = set()

            for row in resource_rows:
                if not isinstance(row, ResourceRow) or row.resource_name != resource_name:
                    mark(
                        "row_schema",
                        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                        "ROW_SCHEMA_INVALID",
                    )
                    continue
                if tuple(field_name for field_name, _ in row.values) != fields:
                    mark(
                        "row_schema",
                        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                        "SCHEMA_SHAPE_INVALID",
                    )
                try:
                    if row.values in seen:
                        mark(
                            "row_schema",
                            PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                            "DUPLICATE_ROW",
                        )
                    seen.add(row.values)
                    values = _row_values(row)
                except (AttributeError, TypeError, ValueError):
                    mark(
                        "row_schema",
                        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                        "ROW_SCHEMA_INVALID",
                    )
                    continue

                visible_row_values[resource_name].append(values)
                types_valid = _ancillary_row_types_are_valid(values)
                if not types_valid:
                    mark(
                        "row_schema",
                        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                        "INVALID_VALUE",
                    )
                fixed_reason = _source_independent_row_reason(
                    resource_name, values, projection.patient_id
                )
                if fixed_reason is not None:
                    mark(
                        "row_schema",
                        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                        fixed_reason,
                    )

                row_patient_id = values.get("patient_id")
                if (
                    not _is_synthetic_patient_id(row_patient_id)
                    or row_patient_id != projection.patient_id
                ):
                    mark(
                        "cross_resource_links",
                        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                        "PATIENT_MISMATCH",
                    )
                if resource_name in {"labs", "medications", "referrals"}:
                    visit_id = values.get("visit_id")
                    if (
                        not _is_synthetic_visit_id(visit_id)
                        or visit_id not in visible_visit_ids
                    ):
                        mark(
                            "cross_resource_links",
                            PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                            "VISIT_REFERENCE_INVALID",
                        )
                elif "visit_id" in values and values["visit_id"] != "":
                    visit_id = values["visit_id"]
                    if (
                        not _is_synthetic_visit_id(visit_id)
                        or visit_id not in visible_visit_ids
                    ):
                        mark(
                            "cross_resource_links",
                            PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                            "VISIT_REFERENCE_INVALID",
                        )

                if types_valid:
                    for field_name in _PEDIATRIC_HYPOTHYROIDISM_AGE_FIELDS:
                        value = values.get(field_name)
                        if field_name in values and value != "" and (
                            isinstance(value, bool)
                            or not isinstance(value, int)
                            or value < 0
                            or value > MAX_AGE_DAYS
                        ):
                            mark(
                                "causal_timing",
                                PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                                "TIMING_INVALID",
                            )

                if resource_name == "labs" and types_valid:
                    visible_lab_order_ages.add(values["lab_order_date_age_in_days"])
                    lab_pairs.add(
                        (
                            values.get("result_line_num"),
                            values.get("result_component_name"),
                        )
                    )
                    lab_order_ids.add(values.get("lab_order_id"))
                    lab_visits.add(values.get("visit_id"))
                    lab_order_ages.add(values.get("lab_order_date_age_in_days"))
                    lab_result_ages.add(values.get("lab_result_date_age_in_days"))
                elif resource_name == "medications" and types_valid:
                    medication_order_ages.add(values.get("med_order_date_age_in_days"))
                    medication_start_ages.add(values.get("med_start_date_age_in_days"))
                    medication_visits.add(values.get("visit_id"))
                elif resource_name == "referrals" and types_valid:
                    visible_referral_ages.add(values["referral_date_age_in_days"])
                elif resource_name == "problem_list" and types_valid:
                    visible_problem_ages.add(values["noted_date_age_in_days"])

            if resource_name == "labs" and resource_rows:
                if lab_pairs != {
                    (1, PEDIATRIC_HYPOTHYROIDISM_TSH_COMPONENT),
                    (2, PEDIATRIC_HYPOTHYROIDISM_FREE_T4_COMPONENT),
                } or len(lab_order_ids) != 1:
                    mark(
                        "row_schema",
                        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                        "ROW_SCHEMA_INVALID",
                    )
                if len(lab_visits) != 1:
                    mark(
                        "cross_resource_links",
                        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                        "VISIT_REFERENCE_INVALID",
                    )
                if len(lab_order_ages) != 1 or len(lab_result_ages) != 1:
                    mark(
                        "causal_timing",
                        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                        "TIMING_INVALID",
                    )
                else:
                    order_age = next(iter(lab_order_ages))
                    result_age = next(iter(lab_result_ages))
                    try:
                        expected_result_age = order_age + policy.result_delay_days
                    except (ArithmeticError, TypeError, ValueError):
                        expected_result_age = None
                    if result_age != expected_result_age:
                        mark(
                            "causal_timing",
                            PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                            "TIMING_INVALID",
                        )

            if resource_name == "medications" and resource_rows:
                if len(medication_visits) != 1:
                    mark(
                        "cross_resource_links",
                        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                        "VISIT_REFERENCE_INVALID",
                    )
                if len(medication_order_ages) != 1 or len(medication_start_ages) != 1:
                    mark(
                        "causal_timing",
                        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                        "TIMING_INVALID",
                    )

        if visible_referral_ages and visible_lab_order_ages and (
            max(visible_referral_ages) > min(visible_lab_order_ages)
        ):
            mark(
                "causal_timing",
                PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                "TIMING_INVALID",
            )
        if visible_lab_order_ages and visible_problem_ages and (
            max(visible_lab_order_ages) > min(visible_problem_ages)
        ):
            mark(
                "causal_timing",
                PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                "TIMING_INVALID",
            )
        if visible_referral_ages and visible_problem_ages and (
            max(visible_referral_ages) > min(visible_problem_ages)
        ):
            mark(
                "causal_timing",
                PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                "TIMING_INVALID",
            )

        frame_events = member.frame.events
        if isinstance(frame_events, tuple):
            for event in frame_events:
                if (
                    isinstance(event, RecordedEvent)
                    and isinstance(event.event_kind, RecordedEventKind)
                    and event.patient_id == member_id
                    and not isinstance(event.age_days, bool)
                    and isinstance(event.age_days, int)
                    and 0 <= event.age_days <= MAX_AGE_DAYS
                ):
                    visible_events.setdefault(event.event_kind, event)

        if target_kind is not None and not target_kind and nonempty_resources:
            mark(
                "pathway_scope",
                PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                "PATHWAY_SCOPE_INVALID",
            )

        if target_kind:
            diagnosis = visible_events.get(RecordedEventKind.DIAGNOSIS)
            medication_expected_count: int | None = None
            if diagnosis is None:
                medication_expected_count = 0
            elif typed_treatment_known:
                medication_expected_count = int(
                    typed_treatment_age is not None
                    and typed_treatment_age >= diagnosis.age_days
                )
            expected_counts = {
                "labs": 2 if RecordedEventKind.WORKUP in visible_events else 0,
                "problem_list": 1
                if RecordedEventKind.DIAGNOSIS in visible_events
                else 0,
                "referrals": 1
                if RecordedEventKind.RECOGNITION in visible_events
                else 0,
            }
            if medication_expected_count is not None:
                expected_counts["medications"] = medication_expected_count
            for resource_name, expected_count in expected_counts.items():
                resource_rows = rows.get(resource_name)
                actual_count = (
                    len(resource_rows) if isinstance(resource_rows, tuple) else 0
                )
                if actual_count != expected_count:
                    mark(
                        "pathway_scope",
                        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                        "PATHWAY_SCOPE_INVALID",
                    )

            medication_values = visible_row_values["medications"]
            if len(medication_values) > 1:
                mark(
                    "pathway_scope",
                    PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                    "PATHWAY_SCOPE_INVALID",
                )

            recognition = visible_events.get(RecordedEventKind.RECOGNITION)
            workup = visible_events.get(RecordedEventKind.WORKUP)
            if (
                recognition is not None
                and workup is not None
                and recognition.age_days > workup.age_days
            ):
                mark(
                    "causal_timing",
                    PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                    "TIMING_INVALID",
                )
            if (
                workup is not None
                and diagnosis is not None
                and workup.age_days > diagnosis.age_days
            ):
                mark(
                    "causal_timing",
                    PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                    "TIMING_INVALID",
                )

            referral_values = visible_row_values["referrals"]
            if (
                recognition is not None
                and len(referral_values) == 1
                and referral_values[0].get("referral_date_age_in_days")
                != recognition.age_days
            ):
                mark(
                    "causal_timing",
                    PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                    "TIMING_INVALID",
                )

            lab_values = visible_row_values["labs"]
            if workup is not None and len(lab_values) == 2:
                expected_result_age = workup.age_days + policy.result_delay_days
                if any(
                    values.get("lab_order_date_age_in_days") != workup.age_days
                    or values.get("lab_result_date_age_in_days")
                    != expected_result_age
                    for values in lab_values
                ):
                    mark(
                        "causal_timing",
                        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                        "TIMING_INVALID",
                    )

            problem_values = visible_row_values["problem_list"]
            if (
                diagnosis is not None
                and len(problem_values) == 1
                and problem_values[0].get("noted_date_age_in_days")
                != diagnosis.age_days
            ):
                mark(
                    "causal_timing",
                    PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                    "TIMING_INVALID",
                )

            if diagnosis is not None and len(medication_values) == 1:
                medication = medication_values[0]
                order_age = medication.get("med_order_date_age_in_days")
                start_age = medication.get("med_start_date_age_in_days")
                if (
                    order_age != diagnosis.age_days
                    or not isinstance(start_age, int)
                    or isinstance(start_age, bool)
                    or start_age < diagnosis.age_days
                    or start_age > MAX_AGE_DAYS
                ):
                    mark(
                        "causal_timing",
                        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                        "TIMING_INVALID",
                    )
    except Exception:  # noqa: BLE001 - malformed visible values are redacted
        mark(
            "row_schema",
            PediatricHypothyroidismAncillaryValidationStatus.FAIL,
            "MALFORMED_PROJECTION",
        )

    # Private evidence is consulted only after all visible checks above have
    # been completed, preserving visible FAIL results when evidence is absent.
    try:
        observation = validate_observation_frame(member.frame)
    except Exception:  # noqa: BLE001 - source evidence cannot escape this boundary
        mark(
            "source_evidence",
            PediatricHypothyroidismAncillaryValidationStatus.UNEVALUABLE,
            "SOURCE_EVIDENCE_UNAVAILABLE",
        )
        return _pediatric_hypothyroidism_ancillary_report(states)

    if observation.status is ObservationValidationStatus.FAIL:
        mark(
            "source_evidence",
            PediatricHypothyroidismAncillaryValidationStatus.FAIL,
            "SOURCE_EVIDENCE_INVALID",
        )
        if any(
            check.name == "event_order" and check.status.name == "FAIL"
            for check in observation.checks
        ):
            mark(
                "causal_timing",
                PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                "EVENT_ORDER_INVALID",
            )
        return _pediatric_hypothyroidism_ancillary_report(states)
    if observation.status is not ObservationValidationStatus.PASS:
        mark(
            "source_evidence",
            PediatricHypothyroidismAncillaryValidationStatus.UNEVALUABLE,
            "SOURCE_EVIDENCE_UNAVAILABLE",
        )
        return _pediatric_hypothyroidism_ancillary_report(states)

    # Observation validation authenticates the frame against its own private
    # truth.  The ancillary boundary also requires that truth to be the same
    # typed trajectory supplied by the member before any row comparison.
    binding_valid = False
    try:
        truth = member.frame.truth
        truth_trajectory = truth.latent_trajectory
        binding_valid = (
            isinstance(trajectory, AgeRegimeDisorderTrajectory)
            and isinstance(truth_trajectory, AgeRegimeDisorderTrajectory)
            and member.frame.patient_id == member_id
            and truth.patient_id == member_id
            and bool(trajectory.physiology.points)
            and trajectory.physiology.points[0].patient_id == member_id
            and trajectory == truth_trajectory
            and trajectory.events == truth.source_events
        )
    except Exception:  # noqa: BLE001 - source details stay redacted
        binding_valid = False
    if not binding_valid:
        mark(
            "source_evidence",
            PediatricHypothyroidismAncillaryValidationStatus.FAIL,
            "SOURCE_EVIDENCE_INVALID",
        )
        return _pediatric_hypothyroidism_ancillary_report(states)

    # A valid frame permits deterministic comparison against the typed
    # projection.  Do not compare if a visible check already failed.
    expected: PediatricHypothyroidismAncillaryProjection | None = None
    if isinstance(projection.shape, ResourceShape):
        try:
            expected = project_pediatric_hypothyroidism_ancillary_resources(
                member, projection.shape, policy
            )
        except Exception:  # noqa: BLE001 - source details stay redacted
            mark(
                "source_evidence",
                PediatricHypothyroidismAncillaryValidationStatus.UNEVALUABLE,
                "SOURCE_EVIDENCE_UNAVAILABLE",
            )
    if expected is not None and not any(
        states[name][0] is PediatricHypothyroidismAncillaryValidationStatus.FAIL
        for name in (
            "pathway_scope",
            "row_schema",
            "causal_timing",
            "cross_resource_links",
        )
    ):
        try:
            for resource_name in PEDIATRIC_HYPOTHYROIDISM_ANCILLARY_RESOURCE_NAMES:
                actual_rows = projection.rows.get(resource_name, ())
                expected_rows = expected.rows[resource_name]
                if len(actual_rows) != len(expected_rows):
                    mark(
                        "pathway_scope",
                        PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                        "PATHWAY_SCOPE_INVALID",
                    )
                    continue
                for actual, wanted in zip(actual_rows, expected_rows, strict=True):
                    if not isinstance(actual, ResourceRow):
                        continue
                    actual_values = _row_values(actual)
                    wanted_values = _row_values(wanted)
                    if actual_values == wanted_values:
                        continue
                    differing = {
                        name
                        for name in wanted_values
                        if actual_values.get(name) != wanted_values[name]
                    }
                    if "patient_id" in differing:
                        mark(
                            "cross_resource_links",
                            PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                            "PATIENT_MISMATCH",
                        )
                    if "visit_id" in differing:
                        mark(
                            "cross_resource_links",
                            PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                            "VISIT_REFERENCE_INVALID",
                        )
                    if any("age_in_days" in name for name in differing):
                        mark(
                            "causal_timing",
                            PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                            "TIMING_INVALID",
                        )
                    if any(name.endswith("_id") for name in differing):
                        mark(
                            "row_schema",
                            PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                            "INVALID_ID",
                        )
                    if any(
                        name in {"result_component_name", "pl_diag"}
                        for name in differing
                    ):
                        mark(
                            "row_schema",
                            PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                            "INVALID_CODE",
                        )
                    if not differing.intersection({"patient_id", "visit_id"}) and not any(
                        "age_in_days" in name for name in differing
                    ) and not any(name.endswith("_id") for name in differing) and not any(
                        name in {"result_component_name", "pl_diag"}
                        for name in differing
                    ):
                        mark(
                            "row_schema",
                            PediatricHypothyroidismAncillaryValidationStatus.FAIL,
                            "INVALID_VALUE",
                        )
        except Exception:  # noqa: BLE001 - source details stay redacted
            mark(
                "source_evidence",
                PediatricHypothyroidismAncillaryValidationStatus.UNEVALUABLE,
                "SOURCE_EVIDENCE_UNAVAILABLE",
            )
    return _pediatric_hypothyroidism_ancillary_report(states)
