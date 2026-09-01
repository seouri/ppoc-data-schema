"""In-memory composition of fictional GHD ancillary and observed-resource rows.

The generic observed-resource validator deliberately rejects nonempty ancillary
rows.  This module keeps that contract intact by validating a zeroed base view
and a typed GHD projection separately before returning a fresh combined bundle.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import ClassVar

from synthetic.cohort import CohortMember
from synthetic.native.ancillary import (
    GHD_ANCILLARY_RESOURCE_NAMES,
    AncillaryResourceProjection,
    AncillaryValidationStatus,
    GhdAncillaryPolicy,
    validate_ghd_ancillary_resources,
)
from synthetic.native.resources import (
    ObservedResourceBundle,
    ResourceRow,
    ResourceValidationStatus,
    validate_observed_resources,
)

ANCILLARY_BUNDLE_CHECK_NAMES = (
    "bundle_identity",
    "base_resources",
    "ancillary_resources",
    "truth_boundary",
)

class AncillaryBundleValidationStatus(str, Enum):
    """Closed aggregate status for the integrated evaluator contract."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNEVALUABLE = "UNEVALUABLE"


ANCILLARY_BUNDLE_REASON_CODES_BY_STATUS: Mapping[
    AncillaryBundleValidationStatus, frozenset[str]
] = MappingProxyType(
    {
        AncillaryBundleValidationStatus.PASS: frozenset({"OK"}),
        AncillaryBundleValidationStatus.FAIL: frozenset(
            {
                "BUNDLE_IDENTITY_INVALID",
                "BASE_RESOURCES_INVALID",
                "ANCILLARY_RESOURCES_INVALID",
                "TRUTH_BOUNDARY_INVALID",
            }
        ),
        AncillaryBundleValidationStatus.UNEVALUABLE: frozenset(
            {"MALFORMED_BUNDLE", "INSUFFICIENT_EVIDENCE"}
        ),
    }
)
ANCILLARY_BUNDLE_REASON_CODES = frozenset(
    reason
    for reasons in ANCILLARY_BUNDLE_REASON_CODES_BY_STATUS.values()
    for reason in reasons
)


class AncillaryBundleUnavailable(ValueError):
    """Fixed redacted error for an unsafe ancillary-bundle composition."""


def _status_for_checks(
    checks: tuple[AncillaryBundleCheck, ...],
) -> AncillaryBundleValidationStatus:
    if any(check.status is AncillaryBundleValidationStatus.FAIL for check in checks):
        return AncillaryBundleValidationStatus.FAIL
    if any(check.status is AncillaryBundleValidationStatus.UNEVALUABLE for check in checks):
        return AncillaryBundleValidationStatus.UNEVALUABLE
    return AncillaryBundleValidationStatus.PASS


@dataclass(frozen=True, repr=False)
class AncillaryBundleCheck:
    """One fixed aggregate-only ancillary-bundle validation check."""

    name: str
    status: AncillaryBundleValidationStatus
    reason_code: str

    CHECK_NAMES: ClassVar[tuple[str, ...]] = ANCILLARY_BUNDLE_CHECK_NAMES
    REASON_CODES: ClassVar[frozenset[str]] = ANCILLARY_BUNDLE_REASON_CODES

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or self.name not in self.CHECK_NAMES:
            raise ValueError("unknown ancillary bundle check name")
        if not isinstance(self.status, AncillaryBundleValidationStatus):
            raise TypeError("status must be an AncillaryBundleValidationStatus")
        if self.reason_code not in ANCILLARY_BUNDLE_REASON_CODES_BY_STATUS[self.status]:
            raise ValueError("reason_code must be compatible with status")

    def to_mapping(self) -> dict[str, str]:
        return {
            "name": self.name,
            "status": self.status.value,
            "reason_code": self.reason_code,
        }

    def __repr__(self) -> str:
        return f"AncillaryBundleCheck(name={self.name!r}, status={self.status.value!r})"


@dataclass(frozen=True, repr=False)
class AncillaryBundleValidationReport:
    """Immutable report of fixed checks, statuses, and aggregate counts only."""

    status: AncillaryBundleValidationStatus
    checks: tuple[AncillaryBundleCheck, ...]

    CHECK_NAMES: ClassVar[tuple[str, ...]] = ANCILLARY_BUNDLE_CHECK_NAMES

    def __post_init__(self) -> None:
        if not isinstance(self.status, AncillaryBundleValidationStatus):
            raise TypeError("status must be an AncillaryBundleValidationStatus")
        if not isinstance(self.checks, tuple) or not all(
            isinstance(check, AncillaryBundleCheck) for check in self.checks
        ):
            raise ValueError("checks must contain every fixed ancillary bundle check")
        names = tuple(check.name for check in self.checks)
        if len(names) != len(self.CHECK_NAMES) or set(names) != set(self.CHECK_NAMES):
            raise ValueError("checks must contain every fixed ancillary bundle check")
        ordered = tuple(sorted(self.checks, key=lambda check: self.CHECK_NAMES.index(check.name)))
        if self.status is not _status_for_checks(ordered):
            raise ValueError("status must match ancillary bundle check statuses")
        object.__setattr__(self, "checks", ordered)

    @property
    def check_counts(self) -> Mapping[str, int]:
        return MappingProxyType(
            {
                status.value: sum(check.status is status for check in self.checks)
                for status in AncillaryBundleValidationStatus
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
            "AncillaryBundleValidationReport("
            f"status={self.status.value!r}, checks={len(self.checks)})"
        )


def _zeroed_base(bundle: ObservedResourceBundle) -> ObservedResourceBundle:
    rows = dict(bundle.rows)
    for resource_name in GHD_ANCILLARY_RESOURCE_NAMES:
        rows[resource_name] = ()
    return ObservedResourceBundle(
        bundle.patient_id,
        bundle.shape,
        rows,
        bundle.clinical_descendants,
        bundle.source_frame,
    )


def _patient_row_matches_member(bundle: ObservedResourceBundle, member: CohortMember) -> bool:
    patient_rows = bundle.rows["patients"]
    if len(patient_rows) != 1:
        return False
    patient_row = patient_rows[0]
    if not isinstance(patient_row, ResourceRow):
        return False
    visible = patient_row.to_mapping()
    expected = member.demographics.to_mapping()
    return all(visible.get(field_name) == expected.get(field_name, "") for field_name in visible)


def _projection_visits_resolve(
    bundle: ObservedResourceBundle,
    projection: AncillaryResourceProjection,
) -> bool:
    visit_ids = {
        row.to_mapping().get("visit_id")
        for row in bundle.rows["visits"]
        if isinstance(row, ResourceRow)
    }
    for resource_name in ("labs", "medications", "referrals"):
        for row in projection.rows[resource_name]:
            visit_id = row.to_mapping().get("visit_id")
            if visit_id not in visit_ids:
                return False
    return True


def _inputs_are_bound(
    bundle: ObservedResourceBundle,
    member: CohortMember,
    projection: AncillaryResourceProjection,
) -> bool:
    return (
        bundle.patient_id == member.demographics.patient_id == projection.patient_id
        and bundle.shape == projection.shape
        and bundle.source_frame is member.frame
        and _patient_row_matches_member(bundle, member)
    )


def _validated_components(
    bundle: ObservedResourceBundle,
    member: CohortMember,
    projection: AncillaryResourceProjection,
    policy: GhdAncillaryPolicy,
) -> bool:
    if not _inputs_are_bound(bundle, member, projection):
        return False
    base = _zeroed_base(bundle)
    if validate_observed_resources(base).status is not ResourceValidationStatus.PASS:
        return False
    if (
        validate_ghd_ancillary_resources(member, projection, policy).status
        is not AncillaryValidationStatus.PASS
    ):
        return False
    return _projection_visits_resolve(base, projection)


def merge_ghd_ancillary_resources(
    bundle: ObservedResourceBundle,
    member: CohortMember,
    projection: AncillaryResourceProjection,
    policy: GhdAncillaryPolicy,
) -> ObservedResourceBundle:
    """Return a fresh bundle after typed base and GHD projection validation.

    The operation is pure and deterministic.  It validates the current typed
    inputs, never trusts a caller-supplied prior report, and exposes no private
    source evidence through its fixed error boundary.
    """

    if not all(
        (
            isinstance(bundle, ObservedResourceBundle),
            isinstance(member, CohortMember),
            isinstance(projection, AncillaryResourceProjection),
            isinstance(policy, GhdAncillaryPolicy),
        )
    ):
        raise AncillaryBundleUnavailable("GHD ancillary bundle unavailable")
    try:
        if any(bundle.rows[name] for name in GHD_ANCILLARY_RESOURCE_NAMES):
            raise ValueError("base bundle already contains ancillary rows")
        if not _validated_components(bundle, member, projection, policy):
            raise ValueError("typed components did not validate")
        rows = dict(bundle.rows)
        for resource_name in GHD_ANCILLARY_RESOURCE_NAMES:
            rows[resource_name] = projection.rows[resource_name]
        merged = ObservedResourceBundle(
            bundle.patient_id,
            bundle.shape,
            rows,
            bundle.clinical_descendants,
            bundle.source_frame,
        )
        extracted = AncillaryResourceProjection(
            merged.patient_id,
            merged.shape,
            {name: merged.rows[name] for name in GHD_ANCILLARY_RESOURCE_NAMES},
        )
        if not _validated_components(merged, member, extracted, policy):
            raise ValueError("combined bundle did not validate")
        return merged
    except Exception:  # noqa: BLE001 - preserve the redacted public boundary
        raise AncillaryBundleUnavailable("GHD ancillary bundle unavailable") from None


__all__ = [
    "ANCILLARY_BUNDLE_CHECK_NAMES",
    "ANCILLARY_BUNDLE_REASON_CODES",
    "ANCILLARY_BUNDLE_REASON_CODES_BY_STATUS",
    "AncillaryBundleCheck",
    "AncillaryBundleUnavailable",
    "AncillaryBundleValidationReport",
    "AncillaryBundleValidationStatus",
    "merge_ghd_ancillary_resources",
]
