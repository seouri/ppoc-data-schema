"""Evaluator-only ancillary projection for a fictional SGA pathway."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
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


SGA_ANCILLARY_CHECK_NAMES = (
    "pathway_scope",
    "row_schema",
    "causal_timing",
    "cross_resource_links",
    "source_evidence",
)


class SgaAncillaryValidationStatus(str, Enum):
    """Aggregate status for one fictional pathway validation report."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNEVALUABLE = "UNEVALUABLE"


SGA_ANCILLARY_REASON_CODES_BY_STATUS: Mapping[
    SgaAncillaryValidationStatus, frozenset[str]
] = MappingProxyType(
    {
        SgaAncillaryValidationStatus.PASS: frozenset({"OK"}),
        SgaAncillaryValidationStatus.FAIL: frozenset(
            {
                "PATIENT_MISMATCH", "SCHEMA_SHAPE_INVALID", "ROW_SCHEMA_INVALID",
                "PATHWAY_SCOPE_INVALID", "CAUSAL_TIMING_INVALID",
                "CROSS_RESOURCE_LINK_INVALID", "SOURCE_EVIDENCE_INVALID",
                "MALFORMED_PROJECTION", "INVALID_ID", "INVALID_CODE", "INVALID_VALUE",
                "DUPLICATE_ROW", "EVENT_ORDER_INVALID", "TIMING_INVALID",
                "VISIT_REFERENCE_INVALID", "PATHWAY_OUT_OF_SCOPE",
            }
        ),
        SgaAncillaryValidationStatus.UNEVALUABLE: frozenset(
            {"MALFORMED_ANCILLARY", "MALFORMED_MEMBER", "INSUFFICIENT_EVIDENCE", "SOURCE_EVIDENCE_UNAVAILABLE"}
        ),
    }
)
SGA_ANCILLARY_REASON_CODES = frozenset(
    reason
    for reasons in SGA_ANCILLARY_REASON_CODES_BY_STATUS.values()
    for reason in reasons
)

_SGA_INTEGER_FIELDS = frozenset(
    {
        "result_line_num", "lab_order_date_age_in_days", "lab_result_date_age_in_days",
        "med_order_date_age_in_days", "med_start_date_age_in_days", "med_end_date_age_in_days",
        "noted_date_age_in_days", "resolved_date_age_in_days", "referral_date_age_in_days",
        "referral_number_of_visits",
    }
)
_SGA_OPTIONAL_INTEGER_FIELDS = frozenset({"med_end_date_age_in_days", "resolved_date_age_in_days"})
_SGA_AGE_FIELDS = frozenset(
    name for name in _SGA_INTEGER_FIELDS if name not in {"result_line_num", "referral_number_of_visits"}
)


def _validation_status_for_checks(
    checks: tuple[SgaAncillaryCheck, ...],
) -> SgaAncillaryValidationStatus:
    if any(check.status is SgaAncillaryValidationStatus.FAIL for check in checks):
        return SgaAncillaryValidationStatus.FAIL
    if any(check.status is SgaAncillaryValidationStatus.UNEVALUABLE for check in checks):
        return SgaAncillaryValidationStatus.UNEVALUABLE
    return SgaAncillaryValidationStatus.PASS


@dataclass(frozen=True, repr=False)
class SgaAncillaryCheck:
    """One fixed aggregate-only validation check."""

    name: str
    status: SgaAncillaryValidationStatus
    reason_code: str

    CHECK_NAMES: ClassVar[tuple[str, ...]] = SGA_ANCILLARY_CHECK_NAMES
    REASON_CODES: ClassVar[frozenset[str]] = SGA_ANCILLARY_REASON_CODES

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or self.name not in self.CHECK_NAMES:
            raise ValueError("unknown sga ancillary check name")
        if not isinstance(self.status, SgaAncillaryValidationStatus):
            raise TypeError("status must be a SgaAncillaryValidationStatus")
        if not isinstance(self.reason_code, str) or self.reason_code not in SGA_ANCILLARY_REASON_CODES_BY_STATUS[self.status]:
            raise ValueError("reason_code must be compatible with status")

    @property
    def check_id(self) -> str:
        return self.name

    def to_mapping(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status.value, "reason_code": self.reason_code}

    def __repr__(self) -> str:
        return f"SgaAncillaryCheck(name={self.name!r}, status={self.status.value!r})"


@dataclass(frozen=True, repr=False)
class SgaAncillaryValidationReport:
    """Immutable aggregate report with no row or source evidence."""

    status: SgaAncillaryValidationStatus
    checks: tuple[SgaAncillaryCheck, ...]

    CHECK_NAMES: ClassVar[tuple[str, ...]] = SGA_ANCILLARY_CHECK_NAMES

    def __post_init__(self) -> None:
        if not isinstance(self.status, SgaAncillaryValidationStatus):
            raise TypeError("status must be a SgaAncillaryValidationStatus")
        if not isinstance(self.checks, tuple) or not self.checks:
            raise ValueError("checks must be a nonempty tuple")
        if not all(isinstance(check, SgaAncillaryCheck) for check in self.checks):
            raise TypeError("checks must contain SgaAncillaryCheck values")
        names = tuple(check.name for check in self.checks)
        if len(names) != len(set(names)) or set(names) != set(self.CHECK_NAMES):
            raise ValueError("checks must contain every fixed sga ancillary check exactly once")
        ordered = tuple(sorted(self.checks, key=lambda check: self.CHECK_NAMES.index(check.name)))
        if self.status is not _validation_status_for_checks(ordered):
            raise ValueError("status must match sga check statuses")
        object.__setattr__(self, "checks", ordered)

    @property
    def check_counts(self) -> Mapping[str, int]:
        return MappingProxyType({status.value: sum(check.status is status for check in self.checks) for status in SgaAncillaryValidationStatus})

    def to_mapping(self) -> dict[str, object]:
        return {"status": self.status.value, "check_counts": dict(self.check_counts), "checks": [check.to_mapping() for check in self.checks]}

    def __repr__(self) -> str:
        return f"SgaAncillaryValidationReport(status={self.status.value!r}, checks={len(self.checks)})"


def _is_synthetic_patient_id(value: object) -> bool:
    return isinstance(value, str) and _SYNTHETIC_PATIENT_TOKEN.fullmatch(value) is not None


def _is_synthetic_visit_id(value: object) -> bool:
    return isinstance(value, str) and _SYNTHETIC_VISIT_TOKEN.fullmatch(value) is not None


def _row_types_are_valid(values: Mapping[str, object]) -> bool:
    for field_name, value in values.items():
        if field_name in _SGA_INTEGER_FIELDS:
            if value == "":
                if field_name not in _SGA_OPTIONAL_INTEGER_FIELDS:
                    return False
            elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
                return False
        elif not isinstance(value, str):
            return False
    return True


def _source_independent_row_reason(name: str, values: Mapping[str, object], patient_id: object) -> str | None:
    if not isinstance(patient_id, str):
        return "PATIENT_MISMATCH"
    expected: dict[str, object] = {field: "" for field in values}
    expected["patient_id"] = patient_id
    identifiers = {"labs": "lab_order_id", "problem_list": "problem_list_id", "referrals": "referral_id"}
    if name == "labs":
        expected.update({"lab_order_id": _synthetic_ancillary_id(patient_id, "lab-order"), "result_loinc_code": "", "result_value": "", "result_flag": SGA_LAB_RESULT_FLAG})
        if values.get("result_component_name") not in SGA_LAB_COMPONENT_NAMES:
            return "INVALID_CODE"
    elif name == "problem_list":
        expected.update({"problem_list_id": _synthetic_ancillary_id(patient_id, "problem-list"), "resolved_date_age_in_days": "", "pl_diag": SGA_DIAGNOSIS_CODE})
        if values.get("pl_diag") != SGA_DIAGNOSIS_CODE:
            return "INVALID_CODE"
    elif name == "referrals":
        expected.update({"referral_id": _synthetic_ancillary_id(patient_id, "referral"), "requested_specialty": SGA_REFERRAL_SPECIALTY, "referral_number_of_visits": 1})
    else:
        return None
    if values.get(identifiers[name]) != expected[identifiers[name]]:
        return "INVALID_ID"
    for field_name, expected_value in expected.items():
        if field_name not in _SGA_INTEGER_FIELDS and field_name not in {"patient_id", "visit_id", "result_component_name"} and values.get(field_name) != expected_value:
            return "INVALID_VALUE"
    if any(values.get(field_name) != "" for field_name in _SGA_OPTIONAL_INTEGER_FIELDS if field_name in values):
        return "INVALID_VALUE"
    return None


def _sga_ancillary_report(states: Mapping[str, tuple[SgaAncillaryValidationStatus, str]]) -> SgaAncillaryValidationReport:
    checks = tuple(SgaAncillaryCheck(name, *states[name]) for name in SGA_ANCILLARY_CHECK_NAMES)
    return SgaAncillaryValidationReport(_validation_status_for_checks(checks), checks)


def validate_sga_ancillary_resources(
    member: CohortMember,
    projection: SgaAncillaryProjection,
    policy: SgaAncillaryPolicy,
) -> SgaAncillaryValidationReport:
    """Return fixed aggregate checks for one fictional SGA projection."""

    if (
        not isinstance(member, CohortMember)
        or not isinstance(projection, SgaAncillaryProjection)
        or not isinstance(policy, SgaAncillaryPolicy)
    ):
        raise SgaAncillaryProjectionUnavailable("sga ancillary projection unavailable")
    states: dict[str, tuple[SgaAncillaryValidationStatus, str]] = {
        name: (SgaAncillaryValidationStatus.PASS, "OK")
        for name in SGA_ANCILLARY_CHECK_NAMES
    }

    def mark(name: str, status: SgaAncillaryValidationStatus, reason: str) -> None:
        current = states[name][0]
        if current is SgaAncillaryValidationStatus.FAIL:
            return
        if status is SgaAncillaryValidationStatus.FAIL or current is SgaAncillaryValidationStatus.PASS:
            states[name] = (status, reason)

    target_kind: bool | None = None
    trajectory: AgeRegimeDisorderTrajectory | None = None
    member_id: object = None
    rows: Mapping[str, tuple[ResourceRow, ...]] | dict[str, tuple[ResourceRow, ...]] = {}
    shape_fields: dict[str, tuple[str, ...]] = {}
    values_by_resource: dict[str, list[dict[str, object]]] = {
        name: [] for name in SGA_ANCILLARY_RESOURCE_NAMES
    }
    visible_events: dict[RecordedEventKind, RecordedEvent] = {}
    visible_visit_ids: frozenset[object] = frozenset()
    ages: dict[str, set[object]] = {"labs": set(), "problem_list": set(), "referrals": set()}
    try:
        member_id = member.demographics.patient_id
        if projection.patient_id != member_id or not _is_synthetic_patient_id(projection.patient_id):
            mark("cross_resource_links", SgaAncillaryValidationStatus.FAIL, "PATIENT_MISMATCH")
        trajectory = member.trajectory
        if not isinstance(trajectory, AgeRegimeDisorderTrajectory):
            mark("pathway_scope", SgaAncillaryValidationStatus.UNEVALUABLE, "MALFORMED_MEMBER")
        else:
            target_kind = trajectory.disorder.kind is DisorderKind.SMALL_FOR_GESTATIONAL_AGE
        rows = projection.rows
        if not isinstance(rows, Mapping) or tuple(rows) != SGA_ANCILLARY_RESOURCE_NAMES:
            mark("row_schema", SgaAncillaryValidationStatus.FAIL, "SCHEMA_SHAPE_INVALID")
            rows = {}
        shape = projection.shape
        if not isinstance(shape, ResourceShape):
            mark("row_schema", SgaAncillaryValidationStatus.FAIL, "SCHEMA_SHAPE_INVALID")
        else:
            for name in SGA_ANCILLARY_RESOURCE_NAMES:
                try:
                    fields = shape.field_names(name)
                except Exception:  # noqa: BLE001 - malformed shapes are redacted
                    mark("row_schema", SgaAncillaryValidationStatus.FAIL, "SCHEMA_SHAPE_INVALID")
                    continue
                shape_fields[name] = fields
                if not _REQUIRED_FIELDS[name].issubset(fields):
                    mark("row_schema", SgaAncillaryValidationStatus.FAIL, "SCHEMA_SHAPE_INVALID")
        try:
            visible_visit_ids = frozenset(visit.visit_id for visit in member.frame.visits)
        except Exception:  # noqa: BLE001 - only visible links are read here
            visible_visit_ids = frozenset()
        for name in SGA_ANCILLARY_RESOURCE_NAMES:
            resource_rows = rows.get(name)
            if not isinstance(resource_rows, tuple):
                mark("row_schema", SgaAncillaryValidationStatus.FAIL, "SCHEMA_SHAPE_INVALID")
                continue
            if name == "medications" and resource_rows:
                mark("pathway_scope", SgaAncillaryValidationStatus.FAIL, "PATHWAY_SCOPE_INVALID")
            if len(resource_rows) > (2 if name == "labs" else 1):
                mark("row_schema", SgaAncillaryValidationStatus.FAIL, "DUPLICATE_ROW")
            fields = shape_fields.get(name)
            if fields is None:
                continue
            seen: set[tuple[tuple[str, object], ...]] = set()
            lab_pairs: set[tuple[object, object]] = set()
            lab_ids: set[object] = set()
            lab_visits: set[object] = set()
            lab_results: set[object] = set()
            for row in resource_rows:
                if not isinstance(row, ResourceRow) or row.resource_name != name:
                    mark("row_schema", SgaAncillaryValidationStatus.FAIL, "ROW_SCHEMA_INVALID")
                    continue
                if tuple(field for field, _ in row.values) != fields:
                    mark("row_schema", SgaAncillaryValidationStatus.FAIL, "SCHEMA_SHAPE_INVALID")
                try:
                    if row.values in seen:
                        mark("row_schema", SgaAncillaryValidationStatus.FAIL, "DUPLICATE_ROW")
                    seen.add(row.values)
                    values = _row_values(row)
                except (AttributeError, TypeError, ValueError):
                    mark("row_schema", SgaAncillaryValidationStatus.FAIL, "ROW_SCHEMA_INVALID")
                    continue
                values_by_resource[name].append(values)
                types_valid = _row_types_are_valid(values)
                if not types_valid:
                    mark("row_schema", SgaAncillaryValidationStatus.FAIL, "INVALID_VALUE")
                fixed_reason = _source_independent_row_reason(name, values, projection.patient_id)
                if fixed_reason is not None:
                    mark("row_schema", SgaAncillaryValidationStatus.FAIL, fixed_reason)
                if not _is_synthetic_patient_id(values.get("patient_id")) or values.get("patient_id") != projection.patient_id:
                    mark("cross_resource_links", SgaAncillaryValidationStatus.FAIL, "PATIENT_MISMATCH")
                if name in {"labs", "referrals"}:
                    visit_id = values.get("visit_id")
                    if not _is_synthetic_visit_id(visit_id) or visit_id not in visible_visit_ids:
                        mark("cross_resource_links", SgaAncillaryValidationStatus.FAIL, "VISIT_REFERENCE_INVALID")
                if types_valid:
                    for field_name in _SGA_AGE_FIELDS:
                        value = values.get(field_name)
                        if field_name in values and value != "" and (
                            isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_AGE_DAYS
                        ):
                            mark("causal_timing", SgaAncillaryValidationStatus.FAIL, "TIMING_INVALID")
                if name == "labs" and types_valid:
                    ages["labs"].add(values.get("lab_order_date_age_in_days"))
                    lab_pairs.add((values.get("result_line_num"), values.get("result_component_name")))
                    lab_ids.add(values.get("lab_order_id"))
                    lab_visits.add(values.get("visit_id"))
                    lab_results.add(values.get("lab_result_date_age_in_days"))
                elif name == "problem_list" and types_valid:
                    ages["problem_list"].add(values.get("noted_date_age_in_days"))
                elif name == "referrals" and types_valid:
                    ages["referrals"].add(values.get("referral_date_age_in_days"))
            if name == "labs" and resource_rows:
                if lab_pairs != {(1, SGA_GESTATIONAL_AGE_COMPONENT), (2, SGA_BIRTH_SIZE_COMPONENT)} or len(lab_ids) != 1:
                    mark("row_schema", SgaAncillaryValidationStatus.FAIL, "ROW_SCHEMA_INVALID")
                if len(lab_visits) != 1:
                    mark("cross_resource_links", SgaAncillaryValidationStatus.FAIL, "VISIT_REFERENCE_INVALID")
                if len(ages["labs"]) != 1 or len(lab_results) != 1:
                    mark("causal_timing", SgaAncillaryValidationStatus.FAIL, "TIMING_INVALID")
                else:
                    order_age = next(iter(ages["labs"]))
                    result_age = next(iter(lab_results))
                    if not isinstance(order_age, int) or isinstance(order_age, bool) or result_age != order_age + policy.result_delay_days:
                        mark("causal_timing", SgaAncillaryValidationStatus.FAIL, "TIMING_INVALID")
        if ages["referrals"] and ages["labs"] and max(ages["referrals"]) > min(ages["labs"]):
            mark("causal_timing", SgaAncillaryValidationStatus.FAIL, "TIMING_INVALID")
        if ages["labs"] and ages["problem_list"] and max(ages["labs"]) > min(ages["problem_list"]):
            mark("causal_timing", SgaAncillaryValidationStatus.FAIL, "TIMING_INVALID")
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
        if target_kind is False and any(rows.get(name, ()) for name in SGA_ANCILLARY_RESOURCE_NAMES):
            mark("pathway_scope", SgaAncillaryValidationStatus.FAIL, "PATHWAY_SCOPE_INVALID")
        if target_kind:
            expected_counts = {
                "labs": 2 if RecordedEventKind.WORKUP in visible_events else 0,
                "medications": 0,
                "problem_list": 1 if RecordedEventKind.DIAGNOSIS in visible_events else 0,
                "referrals": 1 if RecordedEventKind.RECOGNITION in visible_events else 0,
            }
            for name, expected_count in expected_counts.items():
                if len(rows.get(name, ())) != expected_count:
                    mark("pathway_scope", SgaAncillaryValidationStatus.FAIL, "PATHWAY_SCOPE_INVALID")
            recognition = visible_events.get(RecordedEventKind.RECOGNITION)
            workup = visible_events.get(RecordedEventKind.WORKUP)
            diagnosis = visible_events.get(RecordedEventKind.DIAGNOSIS)
            if (recognition and workup and recognition.age_days > workup.age_days) or (workup and diagnosis and workup.age_days > diagnosis.age_days):
                mark("causal_timing", SgaAncillaryValidationStatus.FAIL, "TIMING_INVALID")
            if recognition and len(values_by_resource["referrals"]) == 1 and values_by_resource["referrals"][0].get("referral_date_age_in_days") != recognition.age_days:
                mark("causal_timing", SgaAncillaryValidationStatus.FAIL, "TIMING_INVALID")
            if workup and len(values_by_resource["labs"]) == 2 and any(
                values.get("lab_order_date_age_in_days") != workup.age_days
                or values.get("lab_result_date_age_in_days") != workup.age_days + policy.result_delay_days
                for values in values_by_resource["labs"]
            ):
                mark("causal_timing", SgaAncillaryValidationStatus.FAIL, "TIMING_INVALID")
            if diagnosis and len(values_by_resource["problem_list"]) == 1 and values_by_resource["problem_list"][0].get("noted_date_age_in_days") != diagnosis.age_days:
                mark("causal_timing", SgaAncillaryValidationStatus.FAIL, "TIMING_INVALID")
    except Exception:  # noqa: BLE001 - malformed visible values stay redacted
        mark("row_schema", SgaAncillaryValidationStatus.FAIL, "MALFORMED_PROJECTION")

    # Private source validation deliberately follows every visible check.
    try:
        observation = validate_observation_frame(member.frame)
    except Exception:  # noqa: BLE001 - source details never leave this boundary
        mark("source_evidence", SgaAncillaryValidationStatus.UNEVALUABLE, "SOURCE_EVIDENCE_UNAVAILABLE")
        return _sga_ancillary_report(states)
    if observation.status is ObservationValidationStatus.FAIL:
        mark("source_evidence", SgaAncillaryValidationStatus.FAIL, "SOURCE_EVIDENCE_INVALID")
        if any(check.name == "event_order" and check.status.name == "FAIL" for check in observation.checks):
            mark("causal_timing", SgaAncillaryValidationStatus.FAIL, "EVENT_ORDER_INVALID")
        return _sga_ancillary_report(states)
    if observation.status is not ObservationValidationStatus.PASS:
        mark("source_evidence", SgaAncillaryValidationStatus.UNEVALUABLE, "SOURCE_EVIDENCE_UNAVAILABLE")
        return _sga_ancillary_report(states)
    try:
        truth = member.frame.truth
        binding_valid = (
            isinstance(trajectory, AgeRegimeDisorderTrajectory)
            and isinstance(truth.latent_trajectory, AgeRegimeDisorderTrajectory)
            and member.frame.patient_id == member_id
            and truth.patient_id == member_id
            and bool(trajectory.physiology.points)
            and trajectory.physiology.points[0].patient_id == member_id
            and trajectory == truth.latent_trajectory
            and trajectory.events == truth.source_events
        )
    except Exception:  # noqa: BLE001 - source details never leave this boundary
        binding_valid = False
    if not binding_valid:
        mark("source_evidence", SgaAncillaryValidationStatus.FAIL, "SOURCE_EVIDENCE_INVALID")
        return _sga_ancillary_report(states)
    if not any(states[name][0] is SgaAncillaryValidationStatus.FAIL for name in SGA_ANCILLARY_CHECK_NAMES[:-1]):
        try:
            expected = project_sga_ancillary_resources(member, projection.shape, policy)
            for name in SGA_ANCILLARY_RESOURCE_NAMES:
                actual_rows = projection.rows.get(name, ())
                wanted_rows = expected.rows[name]
                if len(actual_rows) != len(wanted_rows):
                    mark("pathway_scope", SgaAncillaryValidationStatus.FAIL, "PATHWAY_SCOPE_INVALID")
                    continue
                for actual, wanted in zip(actual_rows, wanted_rows, strict=True):
                    if not isinstance(actual, ResourceRow):
                        continue
                    actual_values = _row_values(actual)
                    wanted_values = _row_values(wanted)
                    differing = {
                        field_name
                        for field_name in wanted_values
                        if actual_values.get(field_name) != wanted_values[field_name]
                    }
                    if "patient_id" in differing:
                        mark("cross_resource_links", SgaAncillaryValidationStatus.FAIL, "PATIENT_MISMATCH")
                    if "visit_id" in differing:
                        mark("cross_resource_links", SgaAncillaryValidationStatus.FAIL, "VISIT_REFERENCE_INVALID")
                    if any("age_in_days" in field_name for field_name in differing):
                        mark("causal_timing", SgaAncillaryValidationStatus.FAIL, "TIMING_INVALID")
                    if any(field_name.endswith("_id") for field_name in differing):
                        mark("row_schema", SgaAncillaryValidationStatus.FAIL, "INVALID_ID")
                    if any(field_name in {"result_component_name", "pl_diag"} for field_name in differing):
                        mark("row_schema", SgaAncillaryValidationStatus.FAIL, "INVALID_CODE")
                    if differing and not differing.intersection({"patient_id", "visit_id"}) and not any("age_in_days" in field_name for field_name in differing) and not any(field_name.endswith("_id") for field_name in differing) and not any(field_name in {"result_component_name", "pl_diag"} for field_name in differing):
                        mark("row_schema", SgaAncillaryValidationStatus.FAIL, "INVALID_VALUE")
        except Exception:  # noqa: BLE001 - deterministic source comparison is redacted
            mark("source_evidence", SgaAncillaryValidationStatus.UNEVALUABLE, "SOURCE_EVIDENCE_UNAVAILABLE")
    return _sga_ancillary_report(states)
