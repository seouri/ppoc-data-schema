"""In-memory paired fictional EHR worlds for counterfactual evaluation.

This orchestration seam composes only already-typed native contracts.  It
does not read or write files, export packages, or expose latent truth in its
ordinary representations.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import ClassVar

from synthetic.cohort import CohortMember
from synthetic.native.ancillary import GhdAncillaryPolicy, project_ghd_ancillary_resources
from synthetic.native.ancillary_bundle import (
    AncillaryBundleValidationStatus,
    merge_ghd_ancillary_resources,
    validate_ghd_ancillary_bundle,
)
from synthetic.native.counterfactual import (
    CounterfactualChangeMatrix,
    CounterfactualPair,
    CounterfactualValidationStatus,
    InterventionKind,
    validate_counterfactual_pair,
)
from synthetic.native.observations import (
    OBSERVATION_STREAM_NAMES,
    ObservationPolicy,
    ObservationValidationStatus,
    generate_observation_frame,
    observation_stream_identity,
    validate_observation_frame,
)
from synthetic.native.resources import (
    ResourceShape,
    SyntheticDemographics,
    project_observed_resources,
)
from synthetic.randomness import NamedRandomStreams

COUNTERFACTUAL_WORLD_CHECK_NAMES = (
    "pair_binding",
    "shared_demographics",
    "shared_observation",
    "observation_invariants",
    "resource_invariants",
    "permitted_changes",
    "truth_boundary",
)


class CounterfactualWorldValidationStatus(str, Enum):
    """Closed aggregate status for paired EHR-world evaluation."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNEVALUABLE = "UNEVALUABLE"


COUNTERFACTUAL_WORLD_REASON_CODES_BY_STATUS: Mapping[
    CounterfactualWorldValidationStatus, frozenset[str]
] = MappingProxyType(
    {
        CounterfactualWorldValidationStatus.PASS: frozenset({"OK"}),
        CounterfactualWorldValidationStatus.FAIL: frozenset({"MALFORMED_WORLDS"}),
        CounterfactualWorldValidationStatus.UNEVALUABLE: frozenset({"INSUFFICIENT_EVIDENCE"}),
    }
)
COUNTERFACTUAL_WORLD_REASON_CODES = frozenset(
    reason
    for reasons in COUNTERFACTUAL_WORLD_REASON_CODES_BY_STATUS.values()
    for reason in reasons
)
_SUPPORTED_INTERVENTIONS = frozenset(
    {
        InterventionKind.PHYSIOLOGY_SEVERITY,
        InterventionKind.EARLIER_RECOGNITION,
        InterventionKind.TREATMENT_ADHERENCE,
    }
)


class CounterfactualWorldUnavailable(ValueError):
    """Fixed redacted error for an unavailable counterfactual EHR world."""


def _status_for_checks(
    checks: tuple[CounterfactualWorldCheck, ...],
) -> CounterfactualWorldValidationStatus:
    if any(check.status is CounterfactualWorldValidationStatus.FAIL for check in checks):
        return CounterfactualWorldValidationStatus.FAIL
    if any(check.status is CounterfactualWorldValidationStatus.UNEVALUABLE for check in checks):
        return CounterfactualWorldValidationStatus.UNEVALUABLE
    return CounterfactualWorldValidationStatus.PASS


@dataclass(frozen=True, repr=False)
class CounterfactualWorldCheck:
    """One fixed aggregate-only paired-world validation check."""

    name: str
    status: CounterfactualWorldValidationStatus
    reason_code: str

    CHECK_NAMES: ClassVar[tuple[str, ...]] = COUNTERFACTUAL_WORLD_CHECK_NAMES

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or self.name not in self.CHECK_NAMES:
            raise ValueError("unknown counterfactual world check")
        if not isinstance(self.status, CounterfactualWorldValidationStatus):
            raise TypeError("status must be a CounterfactualWorldValidationStatus")
        if self.reason_code not in COUNTERFACTUAL_WORLD_REASON_CODES_BY_STATUS[self.status]:
            raise ValueError("reason_code must be compatible with status")

    def to_mapping(self) -> dict[str, str]:
        return {
            "name": self.name,
            "status": self.status.value,
            "reason_code": self.reason_code,
        }

    def __repr__(self) -> str:
        return f"CounterfactualWorldCheck(name={self.name!r}, status={self.status.value!r})"


@dataclass(frozen=True, repr=False)
class CounterfactualWorldValidationReport:
    """Immutable, aggregate-only report with a canonical check order."""

    status: CounterfactualWorldValidationStatus
    checks: tuple[CounterfactualWorldCheck, ...]

    CHECK_NAMES: ClassVar[tuple[str, ...]] = COUNTERFACTUAL_WORLD_CHECK_NAMES

    def __post_init__(self) -> None:
        if not isinstance(self.status, CounterfactualWorldValidationStatus):
            raise TypeError("status must be a CounterfactualWorldValidationStatus")
        if not isinstance(self.checks, tuple) or not all(
            isinstance(check, CounterfactualWorldCheck) for check in self.checks
        ):
            raise ValueError("checks must contain every fixed counterfactual world check")
        names = tuple(check.name for check in self.checks)
        if len(names) != len(self.CHECK_NAMES) or set(names) != set(self.CHECK_NAMES):
            raise ValueError("checks must contain every fixed counterfactual world check")
        ordered = tuple(sorted(self.checks, key=lambda check: self.CHECK_NAMES.index(check.name)))
        if self.status is not _status_for_checks(ordered):
            raise ValueError("status must match counterfactual world check statuses")
        object.__setattr__(self, "checks", ordered)

    @property
    def check_counts(self) -> Mapping[str, int]:
        return MappingProxyType(
            {
                status.value: sum(check.status is status for check in self.checks)
                for status in CounterfactualWorldValidationStatus
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
            "CounterfactualWorldValidationReport("
            f"status={self.status.value!r}, checks={len(self.checks)})"
        )


def _shape_mapping(shape: ResourceShape) -> dict[str, object]:
    return {
        "resources": [
            {"name": spec.name, "field_names": list(spec.field_names)}
            for spec in shape.resources
        ]
    }


@dataclass(frozen=True, repr=False)
class CounterfactualEhrWorldPair:
    """Two immutable visible EHR worlds bound to one hidden trajectory pair."""

    baseline: CohortMember
    intervention: CohortMember
    matrix: CounterfactualChangeMatrix
    observation_policy: ObservationPolicy
    shape: ResourceShape
    _pair: CounterfactualPair = field(repr=False)
    _ancillary_policy: GhdAncillaryPolicy = field(repr=False)
    _observation_stream_identities: tuple[str, ...] = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.baseline, CohortMember) or not isinstance(self.intervention, CohortMember):
            raise TypeError("worlds must be CohortMember values")
        if not isinstance(self.matrix, CounterfactualChangeMatrix):
            raise TypeError("matrix must be a CounterfactualChangeMatrix")
        if not isinstance(self.observation_policy, ObservationPolicy):
            raise TypeError("observation_policy must be an ObservationPolicy")
        if not isinstance(self.shape, ResourceShape):
            raise TypeError("shape must be a ResourceShape")
        if not isinstance(self._pair, CounterfactualPair):
            raise TypeError("paired trajectory binding must be a CounterfactualPair")
        if not isinstance(self._ancillary_policy, GhdAncillaryPolicy):
            raise TypeError("ancillary policy must be a GhdAncillaryPolicy")
        if not isinstance(self._observation_stream_identities, tuple) or self._observation_stream_identities != tuple(
            observation_stream_identity(name) for name in OBSERVATION_STREAM_NAMES
        ):
            raise ValueError("worlds must retain the fixed observation stream identities")
        if (
            self.matrix != self._pair.matrix
            or self.baseline.trajectory is not self._pair.baseline
            or self.intervention.trajectory is not self._pair.intervention
            or self.baseline.demographics != self.intervention.demographics
            or self.baseline.demographics.patient_id != self._pair.baseline_context.patient.patient_id
        ):
            raise ValueError("worlds must retain one paired synthetic identity")
        for member in (self.baseline, self.intervention):
            if member.bundle is None or member.bundle.shape != self.shape or member.bundle.source_frame is not member.frame:
                raise ValueError("world members must bind one exact resource bundle to each frame")
            if member.frame.policy_version != self.observation_policy.policy_version:
                raise ValueError("world frames must use the shared observation policy")

    def to_mapping(self) -> dict[str, object]:
        return {
            "contract": "counterfactual-ehr-world-pair-v1",
            "matrix_version": self.matrix.version,
            "intervention": self.matrix.intervention.value,
            "observation_policy": self.observation_policy.to_mapping(),
            "shape": _shape_mapping(self.shape),
            "baseline": self.baseline.to_mapping(),
            "intervention_world": self.intervention.to_mapping(),
        }

    def __repr__(self) -> str:
        return "CounterfactualEhrWorldPair(<evaluator-only>)"


def _require_assembly_inputs(
    pair: object,
    demographics: object,
    observation_policy: object,
    descriptor: object,
    ancillary_policy: object,
) -> tuple[CounterfactualPair, SyntheticDemographics, ObservationPolicy, Mapping[str, object], GhdAncillaryPolicy]:
    if not isinstance(pair, CounterfactualPair):
        raise TypeError("pair must be a CounterfactualPair")
    if not isinstance(demographics, SyntheticDemographics):
        raise TypeError("demographics must be a SyntheticDemographics")
    if not isinstance(observation_policy, ObservationPolicy):
        raise TypeError("observation_policy must be an ObservationPolicy")
    if not isinstance(descriptor, Mapping):
        raise TypeError("descriptor must be a mapping")
    if not isinstance(ancillary_policy, GhdAncillaryPolicy):
        raise TypeError("ancillary_policy must be a GhdAncillaryPolicy")
    return pair, demographics, observation_policy, descriptor, ancillary_policy


def _assemble_member(
    trajectory: object,
    demographics: SyntheticDemographics,
    observation_policy: ObservationPolicy,
    descriptor: Mapping[str, object],
    shape: ResourceShape,
    ancillary_policy: GhdAncillaryPolicy,
    run_seed: int,
    patient_index: int,
) -> CohortMember:
    frame = generate_observation_frame(
        trajectory,  # type: ignore[arg-type]
        observation_policy,
        NamedRandomStreams(run_seed, patient_index),
    )
    if validate_observation_frame(frame).status is not ObservationValidationStatus.PASS:
        raise ValueError("generated frame did not validate")
    provisional = CohortMember(demographics, trajectory, frame, None)  # type: ignore[arg-type]
    base = project_observed_resources(frame, descriptor, demographics)
    projection = project_ghd_ancillary_resources(provisional, shape, ancillary_policy)
    merged = merge_ghd_ancillary_resources(base, provisional, projection, ancillary_policy)
    member = CohortMember(demographics, trajectory, frame, merged)  # type: ignore[arg-type]
    if validate_ghd_ancillary_bundle(merged, member, ancillary_policy).status is not AncillaryBundleValidationStatus.PASS:
        raise ValueError("generated ancillary bundle did not validate")
    return member


def assemble_counterfactual_ehr_worlds(
    pair: CounterfactualPair,
    demographics: SyntheticDemographics,
    observation_policy: ObservationPolicy,
    descriptor: Mapping[str, object],
    ancillary_policy: GhdAncillaryPolicy,
) -> CounterfactualEhrWorldPair:
    """Compose one validated fictional trajectory pair into visible EHR worlds."""

    try:
        pair, demographics, observation_policy, descriptor, ancillary_policy = _require_assembly_inputs(
            pair, demographics, observation_policy, descriptor, ancillary_policy
        )
        if pair.matrix.intervention not in _SUPPORTED_INTERVENTIONS:
            raise ValueError("intervention is not supported")
        if validate_counterfactual_pair(pair).status is not CounterfactualValidationStatus.PASS:
            raise ValueError("paired trajectory did not validate")
        if demographics.patient_id != pair.baseline_context.patient.patient_id:
            raise ValueError("demographics do not identify the paired patient")
        shape = ResourceShape.from_descriptor(descriptor)
        run_seed = pair.baseline_context.run_seed
        patient_index = pair.baseline_context.patient_index
        baseline = _assemble_member(
            pair.baseline,
            demographics,
            observation_policy,
            descriptor,
            shape,
            ancillary_policy,
            run_seed,
            patient_index,
        )
        intervention = _assemble_member(
            pair.intervention,
            demographics,
            observation_policy,
            descriptor,
            shape,
            ancillary_policy,
            run_seed,
            patient_index,
        )
        return CounterfactualEhrWorldPair(
            baseline,
            intervention,
            pair.matrix,
            observation_policy,
            shape,
            pair,
            ancillary_policy,
            tuple(observation_stream_identity(name) for name in OBSERVATION_STREAM_NAMES),
        )
    except Exception:  # noqa: BLE001 - fixed redacted evaluator boundary
        raise CounterfactualWorldUnavailable("counterfactual EHR worlds unavailable") from None


__all__ = [
    "COUNTERFACTUAL_WORLD_CHECK_NAMES",
    "COUNTERFACTUAL_WORLD_REASON_CODES",
    "COUNTERFACTUAL_WORLD_REASON_CODES_BY_STATUS",
    "CounterfactualEhrWorldPair",
    "CounterfactualWorldCheck",
    "CounterfactualWorldUnavailable",
    "CounterfactualWorldValidationReport",
    "CounterfactualWorldValidationStatus",
    "assemble_counterfactual_ehr_worlds",
]
