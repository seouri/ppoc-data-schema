"""Pure in-memory adapter over the reviewed fictional ancillary pathways.

The adapter selects one concrete pathway from evaluator-held trajectory state,
but its own mappings and reports expose only fixed aggregate counts and status
codes.  Merged observed-resource bundles remain caller-owned sidecars.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from copy import copy
from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from types import MappingProxyType
from typing import ClassVar

from synthetic.cohort import CohortMember
from synthetic.models import AgeRegimeDisorderTrajectory, DisorderKind
from synthetic.native.ancillary import (
    AncillaryResourceProjection,
    AncillaryValidationStatus,
    GhdAncillaryPolicy,
    project_ghd_ancillary_resources,
    validate_ghd_ancillary_resources,
)
from synthetic.native.celiac_ancillary import (
    CeliacAncillaryPolicy,
    CeliacAncillaryProjection,
    CeliacAncillaryValidationStatus,
    project_celiac_ancillary_resources,
    validate_celiac_ancillary_resources,
)
from synthetic.native.excess_weight_ancillary import (
    ExcessWeightAncillaryPolicy,
    ExcessWeightAncillaryProjection,
    ExcessWeightAncillaryValidationStatus,
    project_excess_weight_ancillary_resources,
    validate_excess_weight_ancillary_resources,
)
from synthetic.native.observations import (
    ObservationFrame,
    ObservationValidationStatus,
    validate_observation_frame,
)
from synthetic.native.pediatric_hypothyroidism_ancillary import (
    PediatricHypothyroidismAncillaryPolicy,
    PediatricHypothyroidismAncillaryProjection,
    PediatricHypothyroidismAncillaryValidationStatus,
    project_pediatric_hypothyroidism_ancillary_resources,
    validate_pediatric_hypothyroidism_ancillary_resources,
)
from synthetic.native.resources import (
    BASE_RESOURCE_NAMES,
    ObservedResourceBundle,
    ResourceRow,
    ResourceShape,
    ResourceValidationStatus,
    validate_observed_resources,
)
from synthetic.native.sga_ancillary import (
    SgaAncillaryPolicy,
    SgaAncillaryProjection,
    SgaAncillaryValidationStatus,
    project_sga_ancillary_resources,
    validate_sga_ancillary_resources,
)
from synthetic.native.turner_ancillary import (
    TurnerAncillaryPolicy,
    TurnerAncillaryProjection,
    TurnerAncillaryValidationStatus,
    project_turner_ancillary_resources,
    validate_turner_ancillary_resources,
)
from synthetic.native.undernutrition_ancillary import (
    UndernutritionAncillaryPolicy,
    UndernutritionAncillaryProjection,
    UndernutritionAncillaryValidationStatus,
    project_undernutrition_ancillary_resources,
    validate_undernutrition_ancillary_resources,
)

MULTIDISORDER_ANCILLARY_RESOURCE_NAMES = (
    "labs",
    "medications",
    "problem_list",
    "referrals",
)
MULTIDISORDER_ANCILLARY_CHECK_NAMES = (
    "pathway_scope",
    "row_schema",
    "causal_timing",
    "cross_resource_links",
    "source_evidence",
)
MULTIDISORDER_ANCILLARY_BUNDLE_CHECK_NAMES = (
    "bundle_identity",
    "base_resources",
    "ancillary_resources",
    "truth_boundary",
)


class MultidisorderAncillaryValidationStatus(str, Enum):
    """Closed status shared by projection and bundle adapter reports."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNEVALUABLE = "UNEVALUABLE"


MULTIDISORDER_ANCILLARY_REASON_CODES_BY_STATUS: Mapping[
    MultidisorderAncillaryValidationStatus, frozenset[str]
] = MappingProxyType(
    {
        MultidisorderAncillaryValidationStatus.PASS: frozenset({"OK"}),
        MultidisorderAncillaryValidationStatus.FAIL: frozenset(
            {
                "ANCILLARY_VALIDATION_FAILED",
                "BUNDLE_IDENTITY_INVALID",
                "BASE_RESOURCES_INVALID",
                "ANCILLARY_RESOURCES_INVALID",
                "TRUTH_BOUNDARY_INVALID",
            }
        ),
        MultidisorderAncillaryValidationStatus.UNEVALUABLE: frozenset(
            {"MALFORMED_ANCILLARY", "INSUFFICIENT_EVIDENCE"}
        ),
    }
)
MULTIDISORDER_ANCILLARY_REASON_CODES = frozenset(
    reason
    for reasons in MULTIDISORDER_ANCILLARY_REASON_CODES_BY_STATUS.values()
    for reason in reasons
)

_ALL_CHECK_NAMES = frozenset(
    (*MULTIDISORDER_ANCILLARY_CHECK_NAMES, *MULTIDISORDER_ANCILLARY_BUNDLE_CHECK_NAMES)
)
_EMPTY_KINDS = frozenset(
    {
        DisorderKind.HEALTHY,
        DisorderKind.FAMILIAL_SHORT_STATURE,
        DisorderKind.CONSTITUTIONAL_DELAY,
    }
)
_SYNTHETIC_PATIENT_TOKEN = re.compile(r"^syn-[A-Za-z0-9][A-Za-z0-9._-]*$")
_NATIVE_VISIT_ID = re.compile(r"^syn-[0-9a-f]{32}$")
_AGGREGATE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_PATH_EXTENSION = re.compile(
    r"\b[A-Za-z0-9_-]+\.(?:csv|tsv|json|parquet|txt|zip|gz)\b", re.IGNORECASE
)
_AGGREGATE_UNSAFE_COMPONENTS = frozenset(
    {
        "candidate",
        "identifier",
        "key",
        "latent",
        "match",
        "path",
        "patient",
        "resource",
        "row",
        "sequence",
        "truth",
        "visit",
    }
)


class MultidisorderAncillaryProjectionUnavailable(ValueError):
    """Fixed redacted failure for projection and projection validation."""


class MultidisorderAncillaryBundleUnavailable(ValueError):
    """Fixed redacted failure for unsafe bundle composition."""


def _require_aggregate_safe_token(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if (
        _AGGREGATE_TOKEN.fullmatch(value) is None
        or "/" in value
        or "\\" in value
        or _PATH_EXTENSION.search(value)
    ):
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


@dataclass(frozen=True, repr=False)
class MultidisorderAncillaryPolicy:
    """Versioned aggregate-safe policy shared by all concrete pathways."""

    policy_id: str
    policy_version: str
    result_delay_days: int

    def __post_init__(self) -> None:
        _require_aggregate_safe_token(self.policy_id, "policy_id")
        _require_aggregate_safe_token(self.policy_version, "policy_version")
        _require_nonnegative_integer(self.result_delay_days, "result_delay_days")

    def __repr__(self) -> str:
        return "MultidisorderAncillaryPolicy(<aggregate-only>)"


@dataclass(frozen=True, repr=False)
class MultidisorderAncillaryProjection:
    """Immutable exact-shape rows with aggregate-only public rendering."""

    patient_id: str = field(repr=False)
    shape: ResourceShape = field(repr=False)
    rows: Mapping[str, tuple[ResourceRow, ...]] = field(repr=False)

    PROJECTION_VERSION: ClassVar[str] = "multidisorder-ancillary-projection-v1"

    def __post_init__(self) -> None:
        if (
            not isinstance(self.patient_id, str)
            or _SYNTHETIC_PATIENT_TOKEN.fullmatch(self.patient_id) is None
        ):
            raise ValueError("patient_id must identify a fictional synthetic patient")
        if not isinstance(self.shape, ResourceShape):
            raise TypeError("shape must be a ResourceShape")
        if not isinstance(self.rows, Mapping):
            raise TypeError("rows must be a mapping")
        if tuple(self.rows) != MULTIDISORDER_ANCILLARY_RESOURCE_NAMES:
            raise ValueError("rows must contain four ancillary resources in fixed order")

        normalized: dict[str, tuple[ResourceRow, ...]] = {}
        for resource_name in MULTIDISORDER_ANCILLARY_RESOURCE_NAMES:
            resource_rows = self.rows[resource_name]
            if not isinstance(resource_rows, tuple):
                raise TypeError("resource rows must be tuples")
            if not all(isinstance(row, ResourceRow) for row in resource_rows):
                raise TypeError("resource rows must contain ResourceRow values")
            expected_fields = self.shape.field_names(resource_name)
            for row in resource_rows:
                if row.resource_name != resource_name:
                    raise ValueError("resource rows must use their fixed resource name")
                if tuple(name for name, _ in row.values) != expected_fields:
                    raise ValueError("resource rows must match descriptor field order")
                if row.to_mapping().get("patient_id") != self.patient_id:
                    raise ValueError("resource rows must identify the projection patient")
            normalized[resource_name] = resource_rows
        object.__setattr__(self, "rows", MappingProxyType(normalized))

    @property
    def resource_counts(self) -> Mapping[str, int]:
        return MappingProxyType(
            {name: len(self.rows[name]) for name in MULTIDISORDER_ANCILLARY_RESOURCE_NAMES}
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "contract": self.PROJECTION_VERSION,
            "resource_counts": dict(self.resource_counts),
        }

    def __repr__(self) -> str:
        return "MultidisorderAncillaryProjection(<aggregate-only>)"


def _status_for_checks(
    checks: tuple[MultidisorderAncillaryCheck, ...],
) -> MultidisorderAncillaryValidationStatus:
    if any(check.status is MultidisorderAncillaryValidationStatus.FAIL for check in checks):
        return MultidisorderAncillaryValidationStatus.FAIL
    if any(
        check.status is MultidisorderAncillaryValidationStatus.UNEVALUABLE
        for check in checks
    ):
        return MultidisorderAncillaryValidationStatus.UNEVALUABLE
    return MultidisorderAncillaryValidationStatus.PASS


@dataclass(frozen=True, repr=False)
class MultidisorderAncillaryCheck:
    """One fixed aggregate-only projection or bundle validation check."""

    name: str
    status: MultidisorderAncillaryValidationStatus
    reason_code: str

    CHECK_NAMES: ClassVar[frozenset[str]] = _ALL_CHECK_NAMES
    REASON_CODES: ClassVar[frozenset[str]] = MULTIDISORDER_ANCILLARY_REASON_CODES

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or self.name not in self.CHECK_NAMES:
            raise ValueError("unknown multidisorder ancillary check name")
        if not isinstance(self.status, MultidisorderAncillaryValidationStatus):
            raise TypeError("status must be a MultidisorderAncillaryValidationStatus")
        if self.reason_code not in MULTIDISORDER_ANCILLARY_REASON_CODES_BY_STATUS[self.status]:
            raise ValueError("reason_code must be compatible with status")

    def to_mapping(self) -> dict[str, str]:
        return {
            "name": self.name,
            "status": self.status.value,
            "reason_code": self.reason_code,
        }

    def __repr__(self) -> str:
        return (
            "MultidisorderAncillaryCheck("
            f"name={self.name!r}, status={self.status.value!r})"
        )


@dataclass(frozen=True, repr=False)
class MultidisorderAncillaryValidationReport:
    """Fixed, immutable, aggregate-only validation report."""

    status: MultidisorderAncillaryValidationStatus
    checks: tuple[MultidisorderAncillaryCheck, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.status, MultidisorderAncillaryValidationStatus):
            raise TypeError("status must be a MultidisorderAncillaryValidationStatus")
        if not isinstance(self.checks, tuple) or not all(
            isinstance(check, MultidisorderAncillaryCheck) for check in self.checks
        ):
            raise TypeError("checks must be a tuple of MultidisorderAncillaryCheck values")
        names = tuple(check.name for check in self.checks)
        if set(names) == set(MULTIDISORDER_ANCILLARY_CHECK_NAMES) and len(names) == len(
            MULTIDISORDER_ANCILLARY_CHECK_NAMES
        ):
            expected_names = MULTIDISORDER_ANCILLARY_CHECK_NAMES
        elif set(names) == set(MULTIDISORDER_ANCILLARY_BUNDLE_CHECK_NAMES) and len(
            names
        ) == len(MULTIDISORDER_ANCILLARY_BUNDLE_CHECK_NAMES):
            expected_names = MULTIDISORDER_ANCILLARY_BUNDLE_CHECK_NAMES
        else:
            raise ValueError("checks must contain one complete fixed check set")
        ordered = tuple(sorted(self.checks, key=lambda item: expected_names.index(item.name)))
        if self.status is not _status_for_checks(ordered):
            raise ValueError("status must match multidisorder ancillary check statuses")
        object.__setattr__(self, "checks", ordered)

    @property
    def check_counts(self) -> Mapping[str, int]:
        return MappingProxyType(
            {
                status.value: sum(check.status is status for check in self.checks)
                for status in MultidisorderAncillaryValidationStatus
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
            "MultidisorderAncillaryValidationReport("
            f"status={self.status.value!r}, checks={len(self.checks)})"
        )


@dataclass(frozen=True)
class _ConcreteAdapter:
    policy_class: type[object]
    projection_class: type[object]
    projector: Callable[[CohortMember, ResourceShape, object], object]
    validator: Callable[[CohortMember, object, object], object]
    status_class: type[Enum]


_CONCRETE_ADAPTERS: Mapping[DisorderKind, _ConcreteAdapter] = MappingProxyType(
    {
        DisorderKind.GROWTH_HORMONE_DEFICIENCY: _ConcreteAdapter(
            GhdAncillaryPolicy,
            AncillaryResourceProjection,
            project_ghd_ancillary_resources,
            validate_ghd_ancillary_resources,
            AncillaryValidationStatus,
        ),
        DisorderKind.PEDIATRIC_HYPOTHYROIDISM: _ConcreteAdapter(
            PediatricHypothyroidismAncillaryPolicy,
            PediatricHypothyroidismAncillaryProjection,
            project_pediatric_hypothyroidism_ancillary_resources,
            validate_pediatric_hypothyroidism_ancillary_resources,
            PediatricHypothyroidismAncillaryValidationStatus,
        ),
        DisorderKind.CELIAC_DISEASE: _ConcreteAdapter(
            CeliacAncillaryPolicy,
            CeliacAncillaryProjection,
            project_celiac_ancillary_resources,
            validate_celiac_ancillary_resources,
            CeliacAncillaryValidationStatus,
        ),
        DisorderKind.SMALL_FOR_GESTATIONAL_AGE: _ConcreteAdapter(
            SgaAncillaryPolicy,
            SgaAncillaryProjection,
            project_sga_ancillary_resources,
            validate_sga_ancillary_resources,
            SgaAncillaryValidationStatus,
        ),
        DisorderKind.TURNER_SYNDROME: _ConcreteAdapter(
            TurnerAncillaryPolicy,
            TurnerAncillaryProjection,
            project_turner_ancillary_resources,
            validate_turner_ancillary_resources,
            TurnerAncillaryValidationStatus,
        ),
        DisorderKind.UNDERNUTRITION: _ConcreteAdapter(
            UndernutritionAncillaryPolicy,
            UndernutritionAncillaryProjection,
            project_undernutrition_ancillary_resources,
            validate_undernutrition_ancillary_resources,
            UndernutritionAncillaryValidationStatus,
        ),
        DisorderKind.EXCESS_WEIGHT: _ConcreteAdapter(
            ExcessWeightAncillaryPolicy,
            ExcessWeightAncillaryProjection,
            project_excess_weight_ancillary_resources,
            validate_excess_weight_ancillary_resources,
            ExcessWeightAncillaryValidationStatus,
        ),
    }
)


def _member_kind(member: CohortMember) -> DisorderKind:
    trajectory = member.trajectory
    if not isinstance(trajectory, AgeRegimeDisorderTrajectory) or not isinstance(
        trajectory.disorder.kind, DisorderKind
    ):
        raise TypeError("member trajectory is malformed")
    return trajectory.disorder.kind


def _concrete_policy(
    policy: MultidisorderAncillaryPolicy,
    kind: DisorderKind,
    adapter: _ConcreteAdapter,
) -> object:
    return adapter.policy_class(
        f"{policy.policy_id}-{kind.value}",
        policy.policy_version,
        policy.result_delay_days,
    )


def _empty_member_is_valid(member: CohortMember) -> bool:
    frame = member.frame
    trajectory = member.trajectory
    if (
        not isinstance(frame, ObservationFrame)
        or not isinstance(trajectory, AgeRegimeDisorderTrajectory)
        or validate_observation_frame(frame).status is not ObservationValidationStatus.PASS
    ):
        return False
    try:
        return (
            member.demographics.patient_id == frame.patient_id
            and bool(trajectory.physiology.points)
            and trajectory.physiology.points[0].patient_id == frame.patient_id
            and trajectory == frame.truth.latent_trajectory
            and trajectory.events == frame.truth.source_events
        )
    except Exception:  # noqa: BLE001 - private evidence stays behind fixed boundary
        return False


def project_multidisorder_ancillary_resources(
    member: CohortMember,
    shape: ResourceShape,
    policy: MultidisorderAncillaryPolicy,
) -> MultidisorderAncillaryProjection:
    """Dispatch one typed member to its single reviewed ancillary pathway."""

    if (
        not isinstance(member, CohortMember)
        or not isinstance(shape, ResourceShape)
        or not isinstance(policy, MultidisorderAncillaryPolicy)
    ):
        raise MultidisorderAncillaryProjectionUnavailable(
            "multidisorder ancillary projection unavailable"
        )
    try:
        kind = _member_kind(member)
        adapter = _CONCRETE_ADAPTERS.get(kind)
        if adapter is None:
            if kind not in _EMPTY_KINDS or not _empty_member_is_valid(member):
                raise ValueError("empty pathway member is malformed")
            rows = {name: () for name in MULTIDISORDER_ANCILLARY_RESOURCE_NAMES}
        else:
            concrete = adapter.projector(
                member, shape, _concrete_policy(policy, kind, adapter)
            )
            if not isinstance(concrete, adapter.projection_class):
                raise TypeError("concrete projector returned an invalid projection")
            rows = concrete.rows
        return MultidisorderAncillaryProjection(
            member.demographics.patient_id, shape, rows
        )
    except Exception:  # noqa: BLE001 - fixed redacted adapter boundary
        raise MultidisorderAncillaryProjectionUnavailable(
            "multidisorder ancillary projection unavailable"
        ) from None


def _mapped_status(value: object) -> MultidisorderAncillaryValidationStatus:
    raw = getattr(value, "value", None)
    return MultidisorderAncillaryValidationStatus(raw)


def _reason_for_status(status: MultidisorderAncillaryValidationStatus) -> str:
    if status is MultidisorderAncillaryValidationStatus.PASS:
        return "OK"
    if status is MultidisorderAncillaryValidationStatus.FAIL:
        return "ANCILLARY_VALIDATION_FAILED"
    return "INSUFFICIENT_EVIDENCE"


def _projection_report(
    states: Mapping[str, MultidisorderAncillaryValidationStatus],
) -> MultidisorderAncillaryValidationReport:
    checks = tuple(
        MultidisorderAncillaryCheck(name, states[name], _reason_for_status(states[name]))
        for name in MULTIDISORDER_ANCILLARY_CHECK_NAMES
    )
    return MultidisorderAncillaryValidationReport(_status_for_checks(checks), checks)


def _concrete_projection_shell(
    adapter: _ConcreteAdapter, projection: MultidisorderAncillaryProjection
) -> object:
    concrete = object.__new__(adapter.projection_class)
    object.__setattr__(concrete, "patient_id", projection.patient_id)
    object.__setattr__(concrete, "shape", projection.shape)
    object.__setattr__(concrete, "rows", projection.rows)
    return concrete


def _validate_empty_projection(
    member: CohortMember, projection: MultidisorderAncillaryProjection
) -> MultidisorderAncillaryValidationReport:
    states = {
        name: MultidisorderAncillaryValidationStatus.PASS
        for name in MULTIDISORDER_ANCILLARY_CHECK_NAMES
    }
    try:
        if projection.patient_id != member.demographics.patient_id:
            states["cross_resource_links"] = MultidisorderAncillaryValidationStatus.FAIL
        if any(projection.rows[name] for name in MULTIDISORDER_ANCILLARY_RESOURCE_NAMES):
            states["pathway_scope"] = MultidisorderAncillaryValidationStatus.FAIL
        MultidisorderAncillaryProjection(
            projection.patient_id, projection.shape, projection.rows
        )
    except Exception:  # noqa: BLE001 - malformed visible rows become a fixed failure
        states["row_schema"] = MultidisorderAncillaryValidationStatus.FAIL
    if not _empty_member_is_valid(member):
        states["source_evidence"] = MultidisorderAncillaryValidationStatus.UNEVALUABLE
    return _projection_report(states)


def validate_multidisorder_ancillary_resources(
    member: CohortMember,
    projection: MultidisorderAncillaryProjection,
    policy: MultidisorderAncillaryPolicy,
) -> MultidisorderAncillaryValidationReport:
    """Validate one adapted projection without exposing concrete diagnostics."""

    if (
        not isinstance(member, CohortMember)
        or not isinstance(projection, MultidisorderAncillaryProjection)
        or not isinstance(policy, MultidisorderAncillaryPolicy)
    ):
        raise MultidisorderAncillaryProjectionUnavailable(
            "multidisorder ancillary projection unavailable"
        )
    try:
        kind = _member_kind(member)
        adapter = _CONCRETE_ADAPTERS.get(kind)
        if adapter is None:
            if kind not in _EMPTY_KINDS:
                raise ValueError("unsupported disorder kind")
            return _validate_empty_projection(member, projection)

        concrete = _concrete_projection_shell(adapter, projection)
        report = adapter.validator(
            member, concrete, _concrete_policy(policy, kind, adapter)
        )
        concrete_checks = {check.name: check for check in report.checks}
        states = {
            name: _mapped_status(concrete_checks[name].status)
            for name in MULTIDISORDER_ANCILLARY_CHECK_NAMES
        }
        return _projection_report(states)
    except MultidisorderAncillaryProjectionUnavailable:
        raise
    except Exception:  # noqa: BLE001 - fixed redacted adapter boundary
        raise MultidisorderAncillaryProjectionUnavailable(
            "multidisorder ancillary projection unavailable"
        ) from None


def _zeroed_base(bundle: ObservedResourceBundle) -> ObservedResourceBundle:
    rows = dict(bundle.rows)
    for resource_name in MULTIDISORDER_ANCILLARY_RESOURCE_NAMES:
        rows[resource_name] = ()
    return ObservedResourceBundle(
        bundle.patient_id,
        bundle.shape,
        rows,
        bundle.clinical_descendants,
        bundle.source_frame,
    )


def _zeroed_base_validation_view(
    bundle: ObservedResourceBundle,
) -> ObservedResourceBundle:
    if isinstance(bundle.source_frame, ObservationFrame):
        return _zeroed_base(bundle)
    rows = dict(bundle.rows)
    for resource_name in MULTIDISORDER_ANCILLARY_RESOURCE_NAMES:
        rows[resource_name] = ()
    view = copy(bundle)
    object.__setattr__(view, "rows", MappingProxyType(rows))
    return view


def _patient_row_matches_member(
    bundle: ObservedResourceBundle, member: CohortMember
) -> bool:
    patient_rows = bundle.rows["patients"]
    if len(patient_rows) != 1 or not isinstance(patient_rows[0], ResourceRow):
        return False
    visible = patient_rows[0].to_mapping()
    expected = member.demographics.to_mapping()
    return all(visible.get(name) == expected.get(name, "") for name in visible)


def _has_independent_visible_base_failure(bundle: ObservedResourceBundle) -> bool:
    view = _zeroed_base_validation_view(bundle)
    if validate_observed_resources(view).status is ResourceValidationStatus.FAIL:
        return True
    try:
        return any(
            not isinstance(row, ResourceRow)
            or _NATIVE_VISIT_ID.fullmatch(row.to_mapping().get("visit_id", "")) is None
            for row in view.rows["visits"]
        )
    except Exception:  # noqa: BLE001 - malformed visible rows are fixed failures
        return True


def _projection_visits_resolve(
    bundle: ObservedResourceBundle, projection: MultidisorderAncillaryProjection
) -> bool:
    visit_ids = {
        row.to_mapping().get("visit_id")
        for row in bundle.rows["visits"]
        if isinstance(row, ResourceRow)
    }
    for resource_name in ("labs", "medications", "referrals"):
        for row in projection.rows[resource_name]:
            if row.to_mapping().get("visit_id") not in visit_ids:
                return False
    return True


def _inputs_are_bound(
    bundle: ObservedResourceBundle,
    member: CohortMember,
    projection: MultidisorderAncillaryProjection,
) -> bool:
    return (
        bundle.patient_id == member.demographics.patient_id == projection.patient_id
        and bundle.shape == projection.shape
        and bundle.source_frame is member.frame
        and _patient_row_matches_member(bundle, member)
    )


def _bundle_identity_state(
    bundle: object, member: object
) -> tuple[MultidisorderAncillaryValidationStatus, str]:
    if not isinstance(bundle, ObservedResourceBundle) or not isinstance(
        member, CohortMember
    ):
        return MultidisorderAncillaryValidationStatus.UNEVALUABLE, "MALFORMED_ANCILLARY"
    try:
        if (
            bundle.patient_id != member.demographics.patient_id
            or not _patient_row_matches_member(bundle, member)
        ):
            return (
                MultidisorderAncillaryValidationStatus.FAIL,
                "BUNDLE_IDENTITY_INVALID",
            )
        if not isinstance(bundle.source_frame, ObservationFrame) or not isinstance(
            member.frame, ObservationFrame
        ):
            return (
                MultidisorderAncillaryValidationStatus.UNEVALUABLE,
                "INSUFFICIENT_EVIDENCE",
            )
        if bundle.source_frame is not member.frame:
            return (
                MultidisorderAncillaryValidationStatus.FAIL,
                "BUNDLE_IDENTITY_INVALID",
            )
    except Exception:  # noqa: BLE001 - malformed visible identity is a fixed failure
        return MultidisorderAncillaryValidationStatus.FAIL, "BUNDLE_IDENTITY_INVALID"
    return MultidisorderAncillaryValidationStatus.PASS, "OK"


def _base_resources_state(
    bundle: object,
) -> tuple[MultidisorderAncillaryValidationStatus, str]:
    if not isinstance(bundle, ObservedResourceBundle):
        return MultidisorderAncillaryValidationStatus.UNEVALUABLE, "MALFORMED_ANCILLARY"
    try:
        if _has_independent_visible_base_failure(bundle):
            return MultidisorderAncillaryValidationStatus.FAIL, "BASE_RESOURCES_INVALID"
        status = validate_observed_resources(_zeroed_base_validation_view(bundle)).status
    except Exception:  # noqa: BLE001 - malformed visible rows are fixed failures
        return MultidisorderAncillaryValidationStatus.FAIL, "BASE_RESOURCES_INVALID"
    if status is ResourceValidationStatus.PASS:
        return MultidisorderAncillaryValidationStatus.PASS, "OK"
    if status is ResourceValidationStatus.UNEVALUABLE:
        return (
            MultidisorderAncillaryValidationStatus.UNEVALUABLE,
            "INSUFFICIENT_EVIDENCE",
        )
    return MultidisorderAncillaryValidationStatus.FAIL, "BASE_RESOURCES_INVALID"


def _ancillary_resources_state(
    bundle: object,
    member: object,
    policy: object,
) -> tuple[MultidisorderAncillaryValidationStatus, str]:
    if (
        not isinstance(bundle, ObservedResourceBundle)
        or not isinstance(member, CohortMember)
        or not isinstance(policy, MultidisorderAncillaryPolicy)
    ):
        return MultidisorderAncillaryValidationStatus.UNEVALUABLE, "MALFORMED_ANCILLARY"
    try:
        projection = MultidisorderAncillaryProjection(
            bundle.patient_id,
            bundle.shape,
            {
                name: bundle.rows[name]
                for name in MULTIDISORDER_ANCILLARY_RESOURCE_NAMES
            },
        )
        if not _projection_visits_resolve(
            _zeroed_base_validation_view(bundle), projection
        ):
            return (
                MultidisorderAncillaryValidationStatus.FAIL,
                "ANCILLARY_RESOURCES_INVALID",
            )
        status = validate_multidisorder_ancillary_resources(
            member, projection, policy
        ).status
    except Exception:  # noqa: BLE001 - malformed rows stay behind fixed checks
        return (
            MultidisorderAncillaryValidationStatus.FAIL,
            "ANCILLARY_RESOURCES_INVALID",
        )
    if status is MultidisorderAncillaryValidationStatus.PASS:
        return MultidisorderAncillaryValidationStatus.PASS, "OK"
    if status is MultidisorderAncillaryValidationStatus.UNEVALUABLE:
        return (
            MultidisorderAncillaryValidationStatus.UNEVALUABLE,
            "INSUFFICIENT_EVIDENCE",
        )
    return (
        MultidisorderAncillaryValidationStatus.FAIL,
        "ANCILLARY_RESOURCES_INVALID",
    )


def _visible_scalar_is_safe(value: object) -> bool:
    return (
        isinstance(value, str)
        or (isinstance(value, int) and not isinstance(value, bool))
        or (isinstance(value, float) and isfinite(value))
    )


def _visible_mapping_is_safe(
    bundle: ObservedResourceBundle, mapping: Mapping[object, object]
) -> bool:
    if (
        mapping.get("contract") != "observed-resource-bundle-v1"
        or not _visible_scalar_is_safe(mapping.get("patient_id"))
    ):
        return False
    resources = mapping.get("resources")
    if not isinstance(resources, Mapping) or tuple(resources) != BASE_RESOURCE_NAMES:
        return False
    try:
        for resource_name in BASE_RESOURCE_NAMES:
            rows = resources[resource_name]
            fields = bundle.shape.field_names(resource_name)
            if not isinstance(rows, list):
                return False
            for row in rows:
                if (
                    not isinstance(row, Mapping)
                    or tuple(row) != fields
                    or not all(_visible_scalar_is_safe(value) for value in row.values())
                ):
                    return False
        descendants = mapping.get("clinical_descendants")
        descendant_fields = (
            "patient_id",
            "visit_id",
            "age_days",
            "event_kind",
            "code",
        )
        if not isinstance(descendants, list):
            return False
        return all(
            isinstance(descendant, Mapping)
            and tuple(descendant) == descendant_fields
            and all(_visible_scalar_is_safe(value) for value in descendant.values())
            for descendant in descendants
        )
    except Exception:  # noqa: BLE001 - malformed public values are not rendered
        return False


def _truth_boundary_state(
    bundle: object,
) -> tuple[MultidisorderAncillaryValidationStatus, str]:
    if not isinstance(bundle, ObservedResourceBundle):
        return MultidisorderAncillaryValidationStatus.UNEVALUABLE, "MALFORMED_ANCILLARY"
    try:
        mapping = bundle.to_mapping()
        expected_keys = {
            "contract",
            "patient_id",
            "resources",
            "clinical_descendants",
        }
        if (
            not isinstance(mapping, Mapping)
            or set(mapping) != expected_keys
            or not _visible_mapping_is_safe(bundle, mapping)
            or repr(bundle) != "ObservedResourceBundle(<evaluator-only>)"
        ):
            return (
                MultidisorderAncillaryValidationStatus.FAIL,
                "TRUTH_BOUNDARY_INVALID",
            )
    except Exception:  # noqa: BLE001 - malformed wrapper stays redacted
        return MultidisorderAncillaryValidationStatus.UNEVALUABLE, "MALFORMED_ANCILLARY"
    return MultidisorderAncillaryValidationStatus.PASS, "OK"


def validate_multidisorder_ancillary_bundle(
    bundle: ObservedResourceBundle,
    member: CohortMember,
    policy: MultidisorderAncillaryPolicy,
) -> MultidisorderAncillaryValidationReport:
    """Return fixed aggregate checks for one empty or merged sidecar bundle."""

    states = (
        ("bundle_identity", _bundle_identity_state(bundle, member)),
        ("base_resources", _base_resources_state(bundle)),
        (
            "ancillary_resources",
            _ancillary_resources_state(bundle, member, policy),
        ),
        ("truth_boundary", _truth_boundary_state(bundle)),
    )
    checks = tuple(
        MultidisorderAncillaryCheck(name, status, reason)
        for name, (status, reason) in states
    )
    return MultidisorderAncillaryValidationReport(_status_for_checks(checks), checks)


def _validated_components(
    bundle: ObservedResourceBundle,
    member: CohortMember,
    projection: MultidisorderAncillaryProjection,
    policy: MultidisorderAncillaryPolicy,
) -> bool:
    if not _inputs_are_bound(bundle, member, projection):
        return False
    if any(bundle.rows[name] for name in MULTIDISORDER_ANCILLARY_RESOURCE_NAMES):
        return False
    if validate_observed_resources(bundle).status is not ResourceValidationStatus.PASS:
        return False
    if (
        validate_multidisorder_ancillary_resources(member, projection, policy).status
        is not MultidisorderAncillaryValidationStatus.PASS
    ):
        return False
    return _projection_visits_resolve(bundle, projection)


def merge_multidisorder_ancillary_resources(
    bundle: ObservedResourceBundle,
    member: CohortMember,
    projection: MultidisorderAncillaryProjection,
    policy: MultidisorderAncillaryPolicy,
) -> ObservedResourceBundle:
    """Return a fresh merged sidecar after validating all typed components."""

    if not all(
        (
            isinstance(bundle, ObservedResourceBundle),
            isinstance(member, CohortMember),
            isinstance(projection, MultidisorderAncillaryProjection),
            isinstance(policy, MultidisorderAncillaryPolicy),
        )
    ):
        raise MultidisorderAncillaryBundleUnavailable(
            "multidisorder ancillary bundle unavailable"
        )
    try:
        if not _validated_components(bundle, member, projection, policy):
            raise ValueError("typed components did not validate")
        rows = dict(bundle.rows)
        for resource_name in MULTIDISORDER_ANCILLARY_RESOURCE_NAMES:
            rows[resource_name] = projection.rows[resource_name]
        merged = ObservedResourceBundle(
            bundle.patient_id,
            bundle.shape,
            rows,
            bundle.clinical_descendants,
            bundle.source_frame,
        )
        if (
            validate_multidisorder_ancillary_bundle(merged, member, policy).status
            is not MultidisorderAncillaryValidationStatus.PASS
        ):
            raise ValueError("merged bundle did not validate")
        return merged
    except Exception:  # noqa: BLE001 - preserve fixed redacted bundle boundary
        raise MultidisorderAncillaryBundleUnavailable(
            "multidisorder ancillary bundle unavailable"
        ) from None


__all__ = [
    "MULTIDISORDER_ANCILLARY_BUNDLE_CHECK_NAMES",
    "MULTIDISORDER_ANCILLARY_CHECK_NAMES",
    "MULTIDISORDER_ANCILLARY_REASON_CODES",
    "MULTIDISORDER_ANCILLARY_REASON_CODES_BY_STATUS",
    "MULTIDISORDER_ANCILLARY_RESOURCE_NAMES",
    "MultidisorderAncillaryBundleUnavailable",
    "MultidisorderAncillaryCheck",
    "MultidisorderAncillaryPolicy",
    "MultidisorderAncillaryProjection",
    "MultidisorderAncillaryProjectionUnavailable",
    "MultidisorderAncillaryValidationReport",
    "MultidisorderAncillaryValidationStatus",
    "merge_multidisorder_ancillary_resources",
    "project_multidisorder_ancillary_resources",
    "validate_multidisorder_ancillary_bundle",
    "validate_multidisorder_ancillary_resources",
]
