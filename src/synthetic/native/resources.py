"""Evaluator-only descriptor-shaped resource contracts for fictional observations.

This module accepts only an already-loaded descriptor mapping and an
``ObservationFrame``.  It deliberately has no file, package, governed-data,
or calibration interface.  Projection and validation are added in later
steps; the records here establish their strict, immutable boundary.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from numbers import Real
from types import MappingProxyType
from typing import ClassVar

from synthetic.native.observations import (
    RECORDED_EVENT_CODES,
    ObservationFrame,
    RecordedEventKind,
)

BASE_RESOURCE_NAMES = (
    "patients",
    "visits",
    "labs",
    "medications",
    "problem_list",
    "referrals",
)
_BASE_RESOURCE_NAME_SET = frozenset(BASE_RESOURCE_NAMES)
_SYNTHETIC_PATIENT_TOKEN = re.compile(r"^syn-[A-Za-z0-9][A-Za-z0-9._-]*$")
_SYNTHETIC_VISIT_TOKEN = re.compile(r"^syn-[A-Za-z0-9][A-Za-z0-9._:-]*$")
_SEX_VALUES = frozenset({"F", "M", "U"})
_ETHNICITY_VALUES = frozenset(
    {
        "Not Hispanic or Latino",
        "Hispanic or Latino",
        "Choose not to Answer",
        "Unknown",
        "Unable to collect",
        "Patient does not know",
    }
)
_RACE_VALUES = frozenset(
    {
        "American Indian or Alaska Native",
        "Another Race",
        "Asian",
        "Black or African American",
        "Choose not to answer",
        "Middle Eastern or Northern African",
        "Native Hawaiian or Other Pacific Islander",
        "Patient does not know",
        "Unable to collect",
        "Unknown",
        "White",
    }
)
class ResourceProjectionUnavailable(ValueError):
    """Raised when a visible observation has no safe base-resource projection."""


def _require_synthetic_patient_id(value: object, name: str = "patient_id") -> str:
    if not isinstance(value, str) or not _SYNTHETIC_PATIENT_TOKEN.fullmatch(value):
        raise ValueError(f"{name} must identify a fictional synthetic patient")
    return value


def _require_synthetic_visit_id(value: object, name: str = "visit_id") -> str:
    if not isinstance(value, str) or not _SYNTHETIC_VISIT_TOKEN.fullmatch(value):
        raise ValueError(f"{name} must identify a fictional synthetic visit")
    return value


def _require_nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _require_resource_name(value: object) -> str:
    if not isinstance(value, str) or value not in _BASE_RESOURCE_NAME_SET:
        raise ValueError("resource_name must be one of the base resources")
    return value


def _require_field_names(value: object, name: str = "field_names") -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple")
    if not value:
        raise ValueError(f"{name} must be nonempty")
    if not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{name} must contain nonempty field name strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{name} must not contain duplicate field names")
    return value


def _require_row_value(value: object) -> str | int | float:
    if isinstance(value, bool) or not isinstance(value, (str, int, Real)):
        raise TypeError("row values must be string, integer, finite float, or None")
    if isinstance(value, Real) and not isinstance(value, int):
        if not math.isfinite(value):
            raise ValueError("row float values must be finite")
        return float(value)
    return value


@dataclass(frozen=True, repr=False)
class ResourceSpec:
    """One base resource and its exact descriptor field order."""

    name: str
    field_names: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_resource_name(self.name)
        _require_field_names(self.field_names)

    def __repr__(self) -> str:
        return f"ResourceSpec(name={self.name!r}, fields={len(self.field_names)})"


@dataclass(frozen=True, repr=False)
class ResourceShape:
    """The immutable six-resource field shape extracted from one descriptor."""

    resources: tuple[ResourceSpec, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.resources, tuple):
            raise TypeError("resources must be a tuple")
        if not all(isinstance(resource, ResourceSpec) for resource in self.resources):
            raise TypeError("resources must contain ResourceSpec values")
        names = tuple(resource.name for resource in self.resources)
        if names != BASE_RESOURCE_NAMES:
            raise ValueError("resources must contain every required base resource in fixed order")

    @classmethod
    def from_descriptor(cls, descriptor: Mapping[str, object]) -> ResourceShape:
        """Extract only the six base-resource field shapes from an in-memory mapping."""

        if not isinstance(descriptor, Mapping):
            raise TypeError("descriptor must be a mapping")
        resources = descriptor.get("resources")
        if not isinstance(resources, list):
            raise TypeError("descriptor resources must be a list")
        by_name: dict[str, Mapping[str, object]] = {}
        for resource in resources:
            if not isinstance(resource, Mapping):
                raise TypeError("descriptor resources must contain mappings")
            name = resource.get("name")
            if not isinstance(name, str) or not name:
                raise ValueError("descriptor resource names must be nonempty strings")
            if name in by_name:
                raise ValueError("descriptor must not contain duplicate resource names")
            by_name[name] = resource
        if not _BASE_RESOURCE_NAME_SET.issubset(by_name):
            raise ValueError("descriptor must contain every required base resources entry")

        extracted: list[ResourceSpec] = []
        for name in BASE_RESOURCE_NAMES:
            schema = by_name[name].get("schema")
            if not isinstance(schema, Mapping):
                raise TypeError("base resource schema must be a mapping")
            fields = schema.get("fields")
            if not isinstance(fields, list):
                raise TypeError("base resource schema fields must be a list")
            field_names: list[str] = []
            for field_mapping in fields:
                if not isinstance(field_mapping, Mapping):
                    raise TypeError("base resource fields must contain mappings")
                field_name = field_mapping.get("name")
                if not isinstance(field_name, str) or not field_name:
                    raise ValueError("base resource field names must be nonempty strings")
                field_names.append(field_name)
            extracted.append(ResourceSpec(name, tuple(field_names)))
        return cls(tuple(extracted))

    def field_names(self, resource_name: str) -> tuple[str, ...]:
        _require_resource_name(resource_name)
        return self.resources[BASE_RESOURCE_NAMES.index(resource_name)].field_names

    def __repr__(self) -> str:
        return f"ResourceShape(resources={len(self.resources)})"


@dataclass(frozen=True, repr=False)
class SyntheticDemographics:
    """Closed fictional demographic values for one synthetic patient row."""

    patient_id: str
    sex: str = "U"
    ethnicity: str = "Unknown"
    races: tuple[str, ...] = ("Unknown",) * 8

    def __post_init__(self) -> None:
        _require_synthetic_patient_id(self.patient_id)
        if not isinstance(self.sex, str) or self.sex not in _SEX_VALUES:
            raise ValueError("sex must be one of F, M, or U")
        if not isinstance(self.ethnicity, str) or self.ethnicity not in _ETHNICITY_VALUES:
            raise ValueError("ethnicity must be a descriptor-valid value")
        if not isinstance(self.races, tuple) or len(self.races) != 8:
            raise ValueError("races must be a tuple of eight descriptor-valid race values")
        if not all(isinstance(race, str) and race in _RACE_VALUES for race in self.races):
            raise ValueError("races must contain descriptor-valid race values")

    @property
    def race_slots(self) -> tuple[str, ...]:
        return self.races

    def to_mapping(self) -> dict[str, str]:
        return {
            "patient_id": self.patient_id,
            "sex": self.sex,
            "ethnicity": self.ethnicity,
            **{f"race_{index}": race for index, race in enumerate(self.races, start=1)},
        }

    def __repr__(self) -> str:
        return "SyntheticDemographics(<synthetic>)"


@dataclass(frozen=True, repr=False)
class ResourceRow:
    """One immutable descriptor-ordered row using empty strings for missing values."""

    resource_name: str
    values: tuple[tuple[str, object], ...]

    def __post_init__(self) -> None:
        _require_resource_name(self.resource_name)
        if not isinstance(self.values, tuple):
            raise TypeError("values must be a tuple")
        normalised: list[tuple[str, str | int | float]] = []
        for pair in self.values:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise TypeError("values must contain field/value pairs")
            field_name, value = pair
            if not isinstance(field_name, str) or not field_name:
                raise ValueError("row field names must be nonempty strings")
            if field_name == "patient_id":
                normalised.append((field_name, _require_synthetic_patient_id(value)))
            elif field_name == "visit_id":
                normalised.append((field_name, _require_synthetic_visit_id(value)))
            else:
                normalised.append((field_name, "" if value is None else _require_row_value(value)))
        names = tuple(pair[0] for pair in normalised)
        if len(names) != len(set(names)):
            raise ValueError("row values must not contain duplicate field names")
        object.__setattr__(self, "values", tuple(normalised))

    def to_mapping(self) -> dict[str, str | int | float]:
        return dict(self.values)

    def __repr__(self) -> str:
        return f"ResourceRow(resource_name={self.resource_name!r}, fields={len(self.values)})"


@dataclass(frozen=True, repr=False)
class ClinicalDescendant:
    """One visible fictional recognition, workup, or diagnosis event row view."""

    patient_id: str
    visit_id: str
    age_days: int
    event_kind: RecordedEventKind
    code: str

    def __post_init__(self) -> None:
        _require_synthetic_patient_id(self.patient_id)
        _require_synthetic_visit_id(self.visit_id)
        _require_nonnegative_int(self.age_days, "age_days")
        if not isinstance(self.event_kind, RecordedEventKind):
            raise TypeError("event_kind must be a RecordedEventKind")
        if not isinstance(self.code, str) or self.code != RECORDED_EVENT_CODES[self.event_kind]:
            raise ValueError("code must be the registered fictional code for event_kind")

    def to_mapping(self) -> dict[str, str | int]:
        return {
            "patient_id": self.patient_id,
            "visit_id": self.visit_id,
            "age_days": self.age_days,
            "event_kind": self.event_kind.value,
            "code": self.code,
        }

    def __repr__(self) -> str:
        return "ClinicalDescendant(<visible>)"


@dataclass(frozen=True, repr=False)
class ObservedResourceBundle:
    """Visible resource rows with a private evaluator-only source frame."""

    patient_id: str
    shape: ResourceShape = field(repr=False)
    rows: Mapping[str, tuple[ResourceRow, ...]] = field(repr=False)
    clinical_descendants: tuple[ClinicalDescendant, ...]
    source_frame: ObservationFrame = field(repr=False)

    def __post_init__(self) -> None:
        _require_synthetic_patient_id(self.patient_id)
        if not isinstance(self.shape, ResourceShape):
            raise TypeError("shape must be a ResourceShape")
        if not isinstance(self.rows, Mapping):
            raise TypeError("rows must be a mapping")
        row_names = tuple(self.rows.keys())
        if set(row_names) != _BASE_RESOURCE_NAME_SET or len(row_names) != len(BASE_RESOURCE_NAMES):
            raise ValueError("rows must contain every base resource exactly once")
        normalised_rows: dict[str, tuple[ResourceRow, ...]] = {}
        for resource_name in BASE_RESOURCE_NAMES:
            resource_rows = self.rows[resource_name]
            if not isinstance(resource_rows, tuple):
                raise TypeError("resource rows must be tuples")
            if not all(isinstance(row, ResourceRow) for row in resource_rows):
                raise TypeError("resource rows must contain ResourceRow values")
            expected_fields = self.shape.field_names(resource_name)
            for row in resource_rows:
                if row.resource_name != resource_name or tuple(name for name, _ in row.values) != expected_fields:
                    raise ValueError("resource rows must match the extracted descriptor field order")
            normalised_rows[resource_name] = resource_rows
        if not isinstance(self.clinical_descendants, tuple) or not all(
            isinstance(item, ClinicalDescendant) for item in self.clinical_descendants
        ):
            raise TypeError("clinical_descendants must be a tuple of ClinicalDescendant values")
        if any(item.patient_id != self.patient_id for item in self.clinical_descendants):
            raise ValueError("clinical descendants must identify the bundle patient")
        if not isinstance(self.source_frame, ObservationFrame):
            raise TypeError("source_frame must be an ObservationFrame")
        if self.source_frame.patient_id != self.patient_id:
            raise ValueError("source_frame must identify the bundle patient")
        object.__setattr__(self, "rows", MappingProxyType(normalised_rows))

    def to_mapping(self) -> dict[str, object]:
        return {
            "contract": "observed-resource-bundle-v1",
            "patient_id": self.patient_id,
            "resources": {
                name: [row.to_mapping() for row in self.rows[name]]
                for name in BASE_RESOURCE_NAMES
            },
            "clinical_descendants": [item.to_mapping() for item in self.clinical_descendants],
        }

    def __repr__(self) -> str:
        return "ObservedResourceBundle(<evaluator-only>)"


class ResourceValidationStatus(str, Enum):
    """Aggregate status for evaluator-only observed-resource validation."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNEVALUABLE = "UNEVALUABLE"


_REASON_CODES_BY_STATUS: Mapping[ResourceValidationStatus, frozenset[str]] = MappingProxyType(
    {
        ResourceValidationStatus.PASS: frozenset({"OK"}),
        ResourceValidationStatus.FAIL: frozenset(
            {
                "PATIENT_MISMATCH",
                "SCHEMA_SHAPE_INVALID",
                "VISIT_REFERENCE_INVALID",
                "MEASUREMENT_INVALID",
                "CLINICAL_DESCENDANT_INVALID",
                "ANCILLARY_ROWS_PRESENT",
            }
        ),
        ResourceValidationStatus.UNEVALUABLE: frozenset(
            {"MALFORMED_BUNDLE", "INSUFFICIENT_EVIDENCE"}
        ),
    }
)


def _status_for_checks(checks: tuple[ResourceCheck, ...]) -> ResourceValidationStatus:
    if any(check.status is ResourceValidationStatus.FAIL for check in checks):
        return ResourceValidationStatus.FAIL
    if any(check.status is ResourceValidationStatus.UNEVALUABLE for check in checks):
        return ResourceValidationStatus.UNEVALUABLE
    return ResourceValidationStatus.PASS


@dataclass(frozen=True)
class ResourceCheck:
    """One fixed aggregate-only observed-resource validation check."""

    name: str
    status: ResourceValidationStatus
    reason_code: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or self.name not in ResourceValidationReport.CHECK_NAMES:
            raise ValueError("unknown fixed resource check name")
        if not isinstance(self.status, ResourceValidationStatus):
            raise TypeError("status must be a ResourceValidationStatus")
        if (
            not isinstance(self.reason_code, str)
            or self.reason_code not in _REASON_CODES_BY_STATUS[self.status]
        ):
            raise ValueError("reason_code must be compatible with status")

    def to_mapping(self) -> dict[str, str]:
        return {
            "name": self.name,
            "status": self.status.value,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True, repr=False)
class ResourceValidationReport:
    """Immutable report with fixed check names, statuses, reasons, and counts only."""

    status: ResourceValidationStatus
    checks: tuple[ResourceCheck, ...]

    CHECK_NAMES: ClassVar[tuple[str, ...]] = (
        "patient_identity",
        "schema_shape",
        "visit_references",
        "measurements",
        "clinical_descendants",
        "ancillary_resources",
        "evidence",
    )

    def __post_init__(self) -> None:
        if not isinstance(self.status, ResourceValidationStatus):
            raise TypeError("status must be a ResourceValidationStatus")
        if not isinstance(self.checks, tuple) or not all(
            isinstance(check, ResourceCheck) for check in self.checks
        ):
            raise ValueError("checks must contain every fixed resource check")
        names = tuple(check.name for check in self.checks)
        if len(names) != len(self.CHECK_NAMES) or set(names) != set(self.CHECK_NAMES):
            raise ValueError("checks must contain every fixed resource check")
        if self.status is not _status_for_checks(self.checks):
            raise ValueError("status must match resource check statuses")
        object.__setattr__(self, "checks", tuple(sorted(self.checks, key=lambda check: check.name)))

    @property
    def check_counts(self) -> Mapping[str, int]:
        return MappingProxyType(
            {
                status.value: sum(check.status is status for check in self.checks)
                for status in ResourceValidationStatus
            }
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "check_counts": dict(self.check_counts),
            "checks": [check.to_mapping() for check in self.checks],
        }

    def __repr__(self) -> str:
        return f"ResourceValidationReport(status={self.status.value!r}, checks={len(self.checks)})"
