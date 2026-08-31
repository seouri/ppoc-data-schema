"""Evaluator-only value contracts for the fictional GHD ancillary pathway.

The models in this module are deliberately independent of package export,
governed data, and filesystem state.  Later pathway tasks fill in the pure
projection and validator functions; the value objects are useful on their own
for keeping exact descriptor-shaped rows and aggregate reports immutable.
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
from synthetic.models import AgeRegimeDisorderTrajectory, ClinicalEvent, DisorderKind
from synthetic.native.observations import (
    ObservationValidationStatus,
    RecordedEvent,
    RecordedEventKind,
    validate_observation_frame,
)
from synthetic.native.resources import ResourceRow, ResourceShape

GHD_ANCILLARY_RESOURCE_NAMES = (
    "labs",
    "medications",
    "problem_list",
    "referrals",
)

GHD_DIAGNOSIS_CODE = "SYN-GHD"
GHD_IGF1_COMPONENT = "SYN-GHD-IGF1"
GHD_STIM_COMPONENT = "SYN-GHD-STIM"
GHD_LAB_COMPONENT_NAMES = (GHD_IGF1_COMPONENT, GHD_STIM_COMPONENT)
GHD_LAB_RESULT_FLAG = "Synthetic"
GHD_REFERRAL_SPECIALTY = "Synthetic Pediatric Endocrinology"
GHD_MEDICATION_RECORD_TYPE = "Internal"
GHD_MEDICATION_NAME = "Synthetic growth hormone"

# Descriptive aliases keep the fictional vocabulary easy to discover without
# introducing additional terminology or a clinical code-system claim.
SYNTHETIC_GHD_DIAGNOSIS_CODE = GHD_DIAGNOSIS_CODE
SYNTHETIC_GHD_IGF1_COMPONENT = GHD_IGF1_COMPONENT
SYNTHETIC_GHD_STIM_COMPONENT = GHD_STIM_COMPONENT

ANCILLARY_CHECK_NAMES = (
    "pathway_scope",
    "row_schema",
    "causal_timing",
    "cross_resource_links",
    "source_evidence",
)


class AncillaryValidationStatus(str, Enum):
    """Aggregate status for one fictional ancillary validation report."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNEVALUABLE = "UNEVALUABLE"


ValidationStatus = AncillaryValidationStatus


ANCILLARY_REASON_CODES_BY_STATUS: Mapping[
    AncillaryValidationStatus, frozenset[str]
] = MappingProxyType(
    {
        AncillaryValidationStatus.PASS: frozenset({"OK"}),
        AncillaryValidationStatus.FAIL: frozenset(
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
        AncillaryValidationStatus.UNEVALUABLE: frozenset(
            {
                "MALFORMED_ANCILLARY",
                "MALFORMED_MEMBER",
                "INSUFFICIENT_EVIDENCE",
                "SOURCE_EVIDENCE_UNAVAILABLE",
            }
        ),
    }
)
ANCILLARY_REASON_CODES = frozenset(
    reason
    for reasons in ANCILLARY_REASON_CODES_BY_STATUS.values()
    for reason in reasons
)

_GHD_RESOURCE_NAME_SET = frozenset(GHD_ANCILLARY_RESOURCE_NAMES)
_SYNTHETIC_PATIENT_TOKEN = re.compile(r"^syn-[A-Za-z0-9][A-Za-z0-9._-]*$")
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


class AncillaryProjectionUnavailable(ValueError):
    """Raised while the later GHD projection assembly is not available."""


def _require_aggregate_safe_token(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if _AGGREGATE_TOKEN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be an ASCII token without whitespace or path separators")
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


def _require_synthetic_patient_id(value: object, field_name: str = "patient_id") -> str:
    if not isinstance(value, str) or _SYNTHETIC_PATIENT_TOKEN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must identify a fictional synthetic patient")
    return value


@dataclass(frozen=True, repr=False)
class GhdAncillaryPolicy:
    """Versioned, aggregate-safe policy metadata for the fictional pathway."""

    policy_id: str
    policy_version: str
    result_delay_days: int

    def __post_init__(self) -> None:
        _require_aggregate_safe_token(self.policy_id, "policy_id")
        _require_aggregate_safe_token(self.policy_version, "policy_version")
        _require_nonnegative_integer(self.result_delay_days, "result_delay_days")

    def __repr__(self) -> str:
        return "GhdAncillaryPolicy(<aggregate-only>)"


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
class AncillaryResourceProjection:
    """Immutable exact-schema rows for one synthetic member."""

    patient_id: str = field(repr=False)
    shape: ResourceShape = field(repr=False)
    rows: Mapping[str, tuple[ResourceRow, ...]] = field(repr=False)

    PROJECTION_VERSION: ClassVar[str] = "ghd-ancillary-projection-v1"

    def __post_init__(self) -> None:
        _require_synthetic_patient_id(self.patient_id)
        if not isinstance(self.shape, ResourceShape):
            raise TypeError("shape must be a ResourceShape")
        if not isinstance(self.rows, Mapping):
            raise TypeError("rows must be a mapping")
        if tuple(self.rows) != GHD_ANCILLARY_RESOURCE_NAMES:
            raise ValueError("rows must contain the four ancillary resources in fixed order")

        normalized: dict[str, tuple[ResourceRow, ...]] = {}
        for resource_name in GHD_ANCILLARY_RESOURCE_NAMES:
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
                    raise ValueError("resource rows must match the extracted descriptor field order")
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
                resource_name: [row.to_mapping() for row in self.rows[resource_name]]
                for resource_name in GHD_ANCILLARY_RESOURCE_NAMES
            },
        }

    def __repr__(self) -> str:
        return "AncillaryResourceProjection(<evaluator-only>)"


def _status_for_checks(
    checks: tuple[AncillaryCheck, ...],
) -> AncillaryValidationStatus:
    if any(check.status is AncillaryValidationStatus.FAIL for check in checks):
        return AncillaryValidationStatus.FAIL
    if any(check.status is AncillaryValidationStatus.UNEVALUABLE for check in checks):
        return AncillaryValidationStatus.UNEVALUABLE
    return AncillaryValidationStatus.PASS


@dataclass(frozen=True, repr=False)
class AncillaryCheck:
    """One fixed aggregate-only pathway check."""

    name: str
    status: AncillaryValidationStatus
    reason_code: str

    CHECK_NAMES: ClassVar[tuple[str, ...]] = ANCILLARY_CHECK_NAMES
    REASON_CODES: ClassVar[frozenset[str]] = ANCILLARY_REASON_CODES

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or self.name not in ANCILLARY_CHECK_NAMES:
            raise ValueError("unknown ancillary check name")
        if not isinstance(self.status, AncillaryValidationStatus):
            raise TypeError("status must be an AncillaryValidationStatus")
        if self.reason_code not in ANCILLARY_REASON_CODES_BY_STATUS[self.status]:
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
        return f"AncillaryCheck(name={self.name!r}, status={self.status.value!r})"


@dataclass(frozen=True, repr=False)
class AncillaryValidationReport:
    """Immutable aggregate report with no row or source evidence."""

    status: AncillaryValidationStatus
    checks: tuple[AncillaryCheck, ...]

    CHECK_NAMES: ClassVar[tuple[str, ...]] = ANCILLARY_CHECK_NAMES

    def __post_init__(self) -> None:
        if not isinstance(self.status, AncillaryValidationStatus):
            raise TypeError("status must be an AncillaryValidationStatus")
        if not isinstance(self.checks, tuple) or not self.checks:
            raise ValueError("checks must be a nonempty tuple")
        if not all(isinstance(check, AncillaryCheck) for check in self.checks):
            raise TypeError("checks must contain AncillaryCheck values")
        names = tuple(check.name for check in self.checks)
        if len(names) != len(set(names)) or set(names) != set(self.CHECK_NAMES):
            raise ValueError("checks must contain every fixed ancillary check exactly once")
        ordered = tuple(sorted(self.checks, key=lambda check: self.CHECK_NAMES.index(check.name)))
        if self.status is not _status_for_checks(ordered):
            raise ValueError("status must match ancillary check statuses")
        object.__setattr__(self, "checks", ordered)

    @property
    def check_counts(self) -> Mapping[str, int]:
        return MappingProxyType(
            {
                status.value: sum(check.status is status for check in self.checks)
                for status in AncillaryValidationStatus
            }
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "check_counts": dict(self.check_counts),
            "checks": [check.to_mapping() for check in self.checks],
        }

    def __repr__(self) -> str:
        return f"AncillaryValidationReport(status={self.status.value!r}, checks={len(self.checks)})"


def project_ghd_ancillary_resources(
    member: CohortMember,
    shape: ResourceShape,
    policy: GhdAncillaryPolicy,
) -> AncillaryResourceProjection:
    """Project visible fictional GHD descendants into exact-schema rows.

    The member contains evaluator-held trajectory and observation evidence,
    but only the recorded descendants and their visible visit links are used
    to assemble rows.  Any malformed or unevaluable input crosses the same
    fixed error boundary so callers never receive private source details.
    """

    # Preserve Task 1's fixed assembly behavior for callers that have not
    # entered the typed projection boundary at all.  Once typed arguments are
    # present, downstream failures use the Task 2 pathway error below.
    if not isinstance(member, CohortMember) or not isinstance(shape, ResourceShape) or not isinstance(
        policy, GhdAncillaryPolicy
    ):
        raise AncillaryProjectionUnavailable("GHD ancillary projection unavailable")

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
            or trajectory.physiology.points[0].patient_id != patient_id
            or trajectory != truth_trajectory
            or trajectory.events != frame.truth.source_events
        ):
            raise ValueError("member trajectory is not bound to frame truth")

        rows: dict[str, tuple[ResourceRow, ...]] = {
            resource_name: () for resource_name in GHD_ANCILLARY_RESOURCE_NAMES
        }

        if trajectory.disorder.kind is not DisorderKind.GROWTH_HORMONE_DEFICIENCY:
            return AncillaryResourceProjection(patient_id, shape, rows)

        # Check the complete descriptor columns before constructing any rows.
        # This preserves the existing resource projection's fail-closed shape
        # boundary while still allowing future descriptor columns to remain
        # empty-string missing values.
        required_fields = {
            "labs": {
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
            },
            "medications": {
                "patient_id",
                "visit_id",
                "med_record_id",
                "med_order_date_age_in_days",
                "med_start_date_age_in_days",
                "med_end_date_age_in_days",
                "med_record_type",
                "med_simple_generic_name",
            },
            "problem_list": {
                "patient_id",
                "problem_list_id",
                "noted_date_age_in_days",
                "resolved_date_age_in_days",
                "pl_diag",
            },
            "referrals": {
                "patient_id",
                "visit_id",
                "referral_id",
                "referral_date_age_in_days",
                "requested_specialty",
                "referral_number_of_visits",
            },
        }
        if any(
            not required_fields[name].issubset(shape.field_names(name))
            for name in GHD_ANCILLARY_RESOURCE_NAMES
        ):
            raise ValueError("descriptor shape lacks required ancillary fields")

        # A realized opportunity and its visible visit occupy the same stable
        # order as in project_observed_resources.  No age-based re-matching is
        # performed: source-point identity is the causal link.
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

        def visible_visit(event_kind: RecordedEventKind):
            event = visible_events.get(event_kind)
            if event is None or event.opportunity_index is None:
                return None
            visit = visit_by_source_point.get(event.opportunity_index)
            if visit is None:
                raise ValueError("recorded event has no linked visible visit")
            return event, visit

        recognition = visible_visit(RecordedEventKind.RECOGNITION)
        if recognition is not None:
            event, visit = recognition
            rows["referrals"] = (
                _resource_row(
                    "referrals",
                    {
                        "patient_id": patient_id,
                        "visit_id": visit.visit_id,
                        "referral_id": _synthetic_ancillary_id(
                            patient_id, "referral"
                        ),
                        "referral_date_age_in_days": event.age_days,
                        "requested_specialty": GHD_REFERRAL_SPECIALTY,
                        "referral_number_of_visits": 1,
                    },
                    shape,
                ),
            )

        workup = visible_visit(RecordedEventKind.WORKUP)
        if workup is not None:
            event, visit = workup
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
                        "lab_result_date_age_in_days": (
                            event.age_days + policy.result_delay_days
                        ),
                        "result_component_name": component,
                        "result_loinc_code": "",
                        "result_value": "",
                        "result_flag": GHD_LAB_RESULT_FLAG,
                    },
                    shape,
                )
                for line_number, component in enumerate(
                    GHD_LAB_COMPONENT_NAMES, start=1
                )
            )

        diagnosis = visible_visit(RecordedEventKind.DIAGNOSIS)
        if diagnosis is not None:
            diagnosis_event, diagnosis_visit = diagnosis
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
                        "pl_diag": GHD_DIAGNOSIS_CODE,
                    },
                    shape,
                ),
            )

            treatment = next(
                (
                    event
                    for event in trajectory.events
                    if isinstance(event, ClinicalEvent)
                    and event.event_type == "treatment_start"
                ),
                None,
            )
            if treatment is not None:
                if treatment.age_days < diagnosis_event.age_days:
                    raise ValueError("treatment must follow diagnosis")
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
                            "med_start_date_age_in_days": treatment.age_days,
                            "med_end_date_age_in_days": "",
                            "med_record_type": GHD_MEDICATION_RECORD_TYPE,
                            "med_simple_generic_name": GHD_MEDICATION_NAME,
                        },
                        shape,
                    ),
                )

        return AncillaryResourceProjection(patient_id, shape, rows)
    except Exception:  # noqa: BLE001 - evaluator boundary is intentionally redacted
        raise AncillaryProjectionUnavailable("GHD ancillary projection failed") from None


def _synthetic_ancillary_id(patient_id: str, role: str) -> str:
    """Return an opaque deterministic token for one fixed ancillary role."""

    material = f"ghd-ancillary-id-v1\x1f{patient_id}\x1f{role}".encode()
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


def validate_ghd_ancillary_resources(
    member: CohortMember,
    projection: AncillaryResourceProjection,
    policy: GhdAncillaryPolicy,
) -> AncillaryValidationReport:
    """Reserve the aggregate validator seam for the later pathway task."""

    del member, projection, policy
    raise AncillaryProjectionUnavailable("GHD ancillary projection unavailable")


__all__ = [
    "ANCILLARY_CHECK_NAMES",
    "ANCILLARY_REASON_CODES",
    "ANCILLARY_REASON_CODES_BY_STATUS",
    "GHD_ANCILLARY_RESOURCE_NAMES",
    "GHD_DIAGNOSIS_CODE",
    "GHD_IGF1_COMPONENT",
    "GHD_LAB_COMPONENT_NAMES",
    "GHD_LAB_RESULT_FLAG",
    "GHD_MEDICATION_NAME",
    "GHD_MEDICATION_RECORD_TYPE",
    "GHD_REFERRAL_SPECIALTY",
    "GHD_STIM_COMPONENT",
    "SYNTHETIC_GHD_DIAGNOSIS_CODE",
    "SYNTHETIC_GHD_IGF1_COMPONENT",
    "SYNTHETIC_GHD_STIM_COMPONENT",
    "AncillaryCheck",
    "AncillaryProjectionUnavailable",
    "AncillaryResourceProjection",
    "AncillaryValidationReport",
    "AncillaryValidationStatus",
    "GhdAncillaryPolicy",
    "ValidationStatus",
    "project_ghd_ancillary_resources",
    "validate_ghd_ancillary_resources",
]
