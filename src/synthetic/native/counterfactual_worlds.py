"""In-memory paired fictional EHR worlds for counterfactual evaluation.

This orchestration seam composes only already-typed native contracts.  It
does not read or write files, export packages, or expose latent truth in its
ordinary representations.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
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
    ObservationFrame,
    ObservationPolicy,
    ObservationTruth,
    ObservationValidationStatus,
    generate_observation_frame,
    observation_stream_identity,
    validate_observation_frame,
)
from synthetic.native.resources import (
    BASE_RESOURCE_NAMES,
    ObservedResourceBundle,
    ResourceShape,
    ResourceValidationStatus,
    SyntheticDemographics,
    project_observed_resources,
    validate_observed_resources,
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
        CounterfactualWorldValidationStatus.FAIL: frozenset(
            {
                "PAIR_BINDING_INVALID",
                "SHARED_DEMOGRAPHICS_INVALID",
                "SHARED_OBSERVATION_INVALID",
                "OBSERVATION_INVARIANTS_INVALID",
                "RESOURCE_INVARIANTS_INVALID",
                "PERMITTED_CHANGES_INVALID",
                "TRUTH_BOUNDARY_INVALID",
            }
        ),
        CounterfactualWorldValidationStatus.UNEVALUABLE: frozenset(
            {"INSUFFICIENT_EVIDENCE", "MALFORMED_WORLDS"}
        ),
    }
)
_FAILURE_REASON_BY_CHECK: Mapping[str, str] = MappingProxyType(
    {
        "pair_binding": "PAIR_BINDING_INVALID",
        "shared_demographics": "SHARED_DEMOGRAPHICS_INVALID",
        "shared_observation": "SHARED_OBSERVATION_INVALID",
        "observation_invariants": "OBSERVATION_INVARIANTS_INVALID",
        "resource_invariants": "RESOURCE_INVARIANTS_INVALID",
        "permitted_changes": "PERMITTED_CHANGES_INVALID",
        "truth_boundary": "TRUTH_BOUNDARY_INVALID",
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
        if (
            self.status is CounterfactualWorldValidationStatus.FAIL
            and self.reason_code != _FAILURE_REASON_BY_CHECK[self.name]
        ):
            raise ValueError("reason_code must identify the failed check")

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
    _observation_stream_seed: int = field(repr=False)
    _observation_stream_patient_index: int = field(repr=False)

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
        pair_report = validate_counterfactual_pair(self._pair)
        contexts = (self._pair.baseline_context, self._pair.intervention_context)
        if (
            pair_report.status is not CounterfactualValidationStatus.PASS
            or contexts[0].world != "baseline"
            or contexts[1].world != "intervention"
            or contexts[0].matrix != self.matrix
            or contexts[1].matrix != self.matrix
            or contexts[0].patient != contexts[1].patient
            or contexts[0].run_seed != contexts[1].run_seed
            or contexts[0].patient_index != contexts[1].patient_index
            or self._observation_stream_seed != contexts[0].run_seed
            or self._observation_stream_patient_index != contexts[0].patient_index
        ):
            raise ValueError("worlds must retain one valid paired stream configuration")
        for member in (self.baseline, self.intervention):
            if member.bundle is None or member.bundle.shape != self.shape or member.bundle.source_frame is not member.frame:
                raise ValueError("world members must bind one exact resource bundle to each frame")
            if (
                member.frame.policy_version != self.observation_policy.policy_version
                or member.frame.truth.policy != self.observation_policy
                or validate_observation_frame(member.frame).status is not ObservationValidationStatus.PASS
                or validate_ghd_ancillary_bundle(
                    member.bundle, member, self._ancillary_policy
                ).status is not AncillaryBundleValidationStatus.PASS
            ):
                raise ValueError("world frames must use the shared observation policy")
        replayed_frames = tuple(
            generate_observation_frame(
                trajectory,
                self.observation_policy,
                NamedRandomStreams(
                    self._observation_stream_seed,
                    self._observation_stream_patient_index,
                ),
            )
            for trajectory in (self._pair.baseline, self._pair.intervention)
        )
        if tuple(member.frame for member in (self.baseline, self.intervention)) != replayed_frames:
            raise ValueError("world frames must equal deterministic observation replay")

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
            run_seed,
            patient_index,
        )
    except Exception:  # noqa: BLE001 - fixed redacted evaluator boundary
        raise CounterfactualWorldUnavailable("counterfactual EHR worlds unavailable") from None


def _world_check(
    name: str,
    evaluator: object,
) -> CounterfactualWorldCheck:
    """Convert one closed evaluator outcome into a fixed aggregate check."""

    try:
        status = evaluator()  # type: ignore[operator]
        if not isinstance(status, CounterfactualWorldValidationStatus):
            raise TypeError("counterfactual world check returned an invalid status")
    except Exception:  # noqa: BLE001 - public validator always returns a redacted report
        status = CounterfactualWorldValidationStatus.UNEVALUABLE
    if status is CounterfactualWorldValidationStatus.FAIL:
        reason = _FAILURE_REASON_BY_CHECK[name]
    elif status is CounterfactualWorldValidationStatus.PASS:
        reason = "OK"
    else:
        reason = "INSUFFICIENT_EVIDENCE"
    return CounterfactualWorldCheck(name, status, reason)


def _members(worlds: CounterfactualEhrWorldPair) -> tuple[CohortMember, CohortMember]:
    if not isinstance(worlds.baseline, CohortMember) or not isinstance(
        worlds.intervention, CohortMember
    ):
        raise TypeError("world members must be typed")
    return worlds.baseline, worlds.intervention


def _bundles(worlds: CounterfactualEhrWorldPair) -> tuple[ObservedResourceBundle, ObservedResourceBundle]:
    baseline, intervention = _members(worlds)
    if not isinstance(baseline.bundle, ObservedResourceBundle) or not isinstance(
        intervention.bundle, ObservedResourceBundle
    ):
        raise TypeError("world members must retain typed resource bundles")
    return baseline.bundle, intervention.bundle


def _report_status(report: object, expected: type[Enum]) -> CounterfactualWorldValidationStatus:
    status = getattr(report, "status", None)
    if status is CounterfactualValidationStatus.PASS or status is ObservationValidationStatus.PASS or status is AncillaryBundleValidationStatus.PASS or status is ResourceValidationStatus.PASS:
        return CounterfactualWorldValidationStatus.PASS
    if status is CounterfactualValidationStatus.FAIL or status is ObservationValidationStatus.FAIL or status is AncillaryBundleValidationStatus.FAIL or status is ResourceValidationStatus.FAIL:
        return CounterfactualWorldValidationStatus.FAIL
    if isinstance(status, expected):
        return CounterfactualWorldValidationStatus.UNEVALUABLE
    return CounterfactualWorldValidationStatus.UNEVALUABLE


def _check_pair_binding(worlds: CounterfactualEhrWorldPair) -> CounterfactualWorldValidationStatus:
    if not isinstance(worlds, CounterfactualEhrWorldPair):
        return CounterfactualWorldValidationStatus.UNEVALUABLE
    baseline, intervention = _members(worlds)
    pair = worlds._pair
    if not isinstance(pair, CounterfactualPair) or not isinstance(
        worlds.matrix, CounterfactualChangeMatrix
    ):
        return CounterfactualWorldValidationStatus.UNEVALUABLE
    if (
        worlds.matrix != pair.matrix
        or baseline.trajectory is not pair.baseline
        or intervention.trajectory is not pair.intervention
        or pair.baseline_context.world != "baseline"
        or pair.intervention_context.world != "intervention"
    ):
        return CounterfactualWorldValidationStatus.FAIL
    for member in (baseline, intervention):
        if not isinstance(member.frame, ObservationFrame) or not isinstance(
            member.bundle, ObservedResourceBundle
        ):
            return CounterfactualWorldValidationStatus.UNEVALUABLE
        if member.bundle.source_frame is not member.frame:
            return CounterfactualWorldValidationStatus.FAIL
        truth = member.frame.truth
        if not isinstance(truth, ObservationTruth) or truth.latent_trajectory is None:
            return CounterfactualWorldValidationStatus.UNEVALUABLE
        if not isinstance(truth.latent_trajectory, type(member.trajectory)):
            return CounterfactualWorldValidationStatus.UNEVALUABLE
        if truth.latent_trajectory is not member.trajectory:
            return CounterfactualWorldValidationStatus.FAIL
    return _report_status(validate_counterfactual_pair(pair), CounterfactualValidationStatus)


def _check_shared_demographics(worlds: CounterfactualEhrWorldPair) -> CounterfactualWorldValidationStatus:
    baseline, intervention = _members(worlds)
    bundles = _bundles(worlds)
    if not isinstance(baseline.demographics, SyntheticDemographics) or not isinstance(
        intervention.demographics, SyntheticDemographics
    ):
        return CounterfactualWorldValidationStatus.UNEVALUABLE
    if baseline.demographics != intervention.demographics:
        return CounterfactualWorldValidationStatus.FAIL
    demographics = baseline.demographics.to_mapping()
    patient_rows: list[object] = []
    for bundle in bundles:
        rows = bundle.rows.get("patients")
        if not isinstance(rows, tuple) or len(rows) != 1:
            return CounterfactualWorldValidationStatus.FAIL
        patient_rows.append(rows[0].to_mapping())
    if patient_rows[0] != demographics or patient_rows[1] != demographics or patient_rows[0] != patient_rows[1]:
        return CounterfactualWorldValidationStatus.FAIL
    return CounterfactualWorldValidationStatus.PASS


def _check_shared_observation(worlds: CounterfactualEhrWorldPair) -> CounterfactualWorldValidationStatus:
    baseline, intervention = _members(worlds)
    pair = worlds._pair
    if not isinstance(worlds.observation_policy, ObservationPolicy) or not isinstance(
        pair, CounterfactualPair
    ):
        return CounterfactualWorldValidationStatus.UNEVALUABLE
    if not isinstance(baseline.frame, ObservationFrame) or not isinstance(
        intervention.frame, ObservationFrame
    ):
        return CounterfactualWorldValidationStatus.UNEVALUABLE
    expected_streams = tuple(observation_stream_identity(name) for name in OBSERVATION_STREAM_NAMES)
    if (
        worlds._observation_stream_identities != expected_streams
        or worlds._observation_stream_seed != pair.baseline_context.run_seed
        or worlds._observation_stream_patient_index != pair.baseline_context.patient_index
        or pair.baseline_context.run_seed != pair.intervention_context.run_seed
        or pair.baseline_context.patient_index != pair.intervention_context.patient_index
    ):
        return CounterfactualWorldValidationStatus.FAIL
    try:
        replayed_frames = tuple(
            generate_observation_frame(
                trajectory,
                worlds.observation_policy,
                NamedRandomStreams(
                    worlds._observation_stream_seed,
                    worlds._observation_stream_patient_index,
                ),
            )
            for trajectory in (pair.baseline, pair.intervention)
        )
    except (AttributeError, TypeError, ValueError):
        return CounterfactualWorldValidationStatus.UNEVALUABLE
    evidence_missing = False
    for frame, replayed in zip(
        (baseline.frame, intervention.frame), replayed_frames, strict=True
    ):
        try:
            visible_state = (
                frame.patient_id,
                frame.policy_version,
                frame.window,
                frame.visits,
                frame.events,
            )
            replayed_visible_state = (
                replayed.patient_id,
                replayed.policy_version,
                replayed.window,
                replayed.visits,
                replayed.events,
            )
            if visible_state != replayed_visible_state:
                return CounterfactualWorldValidationStatus.FAIL
            if not isinstance(frame.truth, ObservationTruth):
                evidence_missing = True
                continue
            if frame.truth.policy != worlds.observation_policy:
                return CounterfactualWorldValidationStatus.FAIL
            if frame != replayed:
                return CounterfactualWorldValidationStatus.FAIL
        except (AttributeError, TypeError, ValueError):
            evidence_missing = True
    return (
        CounterfactualWorldValidationStatus.UNEVALUABLE
        if evidence_missing
        else CounterfactualWorldValidationStatus.PASS
    )


def _visit_structure(member: CohortMember) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (visit.patient_id, visit.visit_id, visit.age_days, visit.encounter_type)
        for visit in member.frame.visits
    )


def _availability(member: CohortMember) -> tuple[tuple[object, ...], ...]:
    return tuple(
        tuple((measurement.channel, measurement.availability) for measurement in visit.measurements)
        for visit in member.frame.visits
    )


def _check_observation_invariants(worlds: CounterfactualEhrWorldPair) -> CounterfactualWorldValidationStatus:
    baseline, intervention = _members(worlds)
    baseline_status = _report_status(validate_observation_frame(baseline.frame), ObservationValidationStatus)
    intervention_status = _report_status(validate_observation_frame(intervention.frame), ObservationValidationStatus)
    if CounterfactualWorldValidationStatus.FAIL in (baseline_status, intervention_status):
        return CounterfactualWorldValidationStatus.FAIL
    try:
        if _visit_structure(baseline) != _visit_structure(intervention) or _availability(
            baseline
        ) != _availability(intervention):
            return CounterfactualWorldValidationStatus.FAIL
    except (AttributeError, TypeError, ValueError):
        return CounterfactualWorldValidationStatus.FAIL
    if CounterfactualWorldValidationStatus.UNEVALUABLE in (baseline_status, intervention_status):
        return CounterfactualWorldValidationStatus.UNEVALUABLE
    return CounterfactualWorldValidationStatus.PASS


def _isolated_base_status(bundle: ObservedResourceBundle) -> CounterfactualWorldValidationStatus:
    try:
        rows = dict(bundle.rows)
        for name in BASE_RESOURCE_NAMES[2:]:
            rows[name] = ()
        base = ObservedResourceBundle(
            bundle.patient_id,
            bundle.shape,
            rows,
            bundle.clinical_descendants,
            bundle.source_frame,
        )
        return _report_status(validate_observed_resources(base), ResourceValidationStatus)
    except (AttributeError, KeyError, TypeError, ValueError):
        return CounterfactualWorldValidationStatus.FAIL


def _check_resource_invariants(worlds: CounterfactualEhrWorldPair) -> CounterfactualWorldValidationStatus:
    baseline, intervention = _members(worlds)
    bundles = _bundles(worlds)
    if not isinstance(worlds.shape, ResourceShape) or not isinstance(
        worlds._ancillary_policy, GhdAncillaryPolicy
    ):
        return CounterfactualWorldValidationStatus.UNEVALUABLE
    statuses: list[CounterfactualWorldValidationStatus] = []
    for member, bundle in zip((baseline, intervention), bundles, strict=True):
        if bundle.source_frame is not member.frame or bundle.shape != worlds.shape:
            return CounterfactualWorldValidationStatus.FAIL
        statuses.append(
            _report_status(
                validate_ghd_ancillary_bundle(bundle, member, worlds._ancillary_policy),
                AncillaryBundleValidationStatus,
            )
        )
        statuses.append(_isolated_base_status(bundle))
    if CounterfactualWorldValidationStatus.FAIL in statuses:
        return CounterfactualWorldValidationStatus.FAIL
    if CounterfactualWorldValidationStatus.UNEVALUABLE in statuses:
        return CounterfactualWorldValidationStatus.UNEVALUABLE
    return CounterfactualWorldValidationStatus.PASS


def _measurement_values(member: CohortMember) -> tuple[tuple[object, ...], ...]:
    return tuple(
        tuple(
            (visit.age_days, measurement.channel, measurement.recorded_value)
            for measurement in visit.measurements
        )
        for visit in member.frame.visits
    )


def _projected_measurement_values(bundle: ObservedResourceBundle) -> tuple[tuple[object, ...], ...]:
    fields = ("weight_oz", "height_in", "head_circ_cm", "BMI")
    return tuple(
        (row.to_mapping()["age_in_days"], *(row.to_mapping()[field] for field in fields))
        for row in bundle.rows["visits"]
    )


def _events(member: CohortMember) -> tuple[tuple[tuple[str, object], ...], ...]:
    return tuple(tuple(event.to_mapping().items()) for event in member.frame.events)


def _descendants(bundle: ObservedResourceBundle) -> tuple[tuple[tuple[str, object], ...], ...]:
    return tuple(tuple(item.to_mapping().items()) for item in bundle.clinical_descendants)


def _ancillary_rows(bundle: ObservedResourceBundle) -> tuple[tuple[tuple[tuple[str, object], ...], ...], ...]:
    return tuple(
        tuple(tuple(row.to_mapping().items()) for row in bundle.rows[name])
        for name in BASE_RESOURCE_NAMES[2:]
    )


def _check_permitted_changes(worlds: CounterfactualEhrWorldPair) -> CounterfactualWorldValidationStatus:
    baseline, intervention = _members(worlds)
    baseline_bundle, intervention_bundle = _bundles(worlds)
    try:
        baseline_values = _measurement_values(baseline)
        intervention_values = _measurement_values(intervention)
        baseline_projected = _projected_measurement_values(baseline_bundle)
        intervention_projected = _projected_measurement_values(intervention_bundle)
        baseline_events = _events(baseline)
        intervention_events = _events(intervention)
        baseline_descendants = _descendants(baseline_bundle)
        intervention_descendants = _descendants(intervention_bundle)
        baseline_ancillary = _ancillary_rows(baseline_bundle)
        intervention_ancillary = _ancillary_rows(intervention_bundle)
    except (AttributeError, KeyError, TypeError, ValueError):
        return CounterfactualWorldValidationStatus.FAIL
    intervention_kind = worlds.matrix.intervention
    if intervention_kind is InterventionKind.PHYSIOLOGY_SEVERITY:
        if (
            baseline_events != intervention_events
            or baseline_descendants != intervention_descendants
            or baseline_ancillary != intervention_ancillary
        ):
            return CounterfactualWorldValidationStatus.FAIL
        return CounterfactualWorldValidationStatus.PASS
    if intervention_kind is InterventionKind.EARLIER_RECOGNITION:
        return (
            CounterfactualWorldValidationStatus.PASS
            if baseline_values == intervention_values and baseline_projected == intervention_projected
            else CounterfactualWorldValidationStatus.FAIL
        )
    if intervention_kind is InterventionKind.TREATMENT_ADHERENCE:
        if (
            baseline_events != intervention_events
            or baseline_descendants != intervention_descendants
            or baseline_ancillary != intervention_ancillary
        ):
            return CounterfactualWorldValidationStatus.FAIL
        try:
            treatment_start = worlds._pair.baseline.disorder.treatment_start_age_days
        except (AttributeError, TypeError):
            return CounterfactualWorldValidationStatus.UNEVALUABLE
        for baseline_visit, intervention_visit in zip(
            baseline_values, intervention_values, strict=True
        ):
            for left, right in zip(baseline_visit, intervention_visit, strict=True):
                if left[:2] != right[:2]:
                    return CounterfactualWorldValidationStatus.FAIL
                if (treatment_start is None or left[0] < treatment_start) and left[2] != right[2]:
                    return CounterfactualWorldValidationStatus.FAIL
        for left, right in zip(baseline_projected, intervention_projected, strict=True):
            if left[0] != right[0] or (
                treatment_start is None or left[0] < treatment_start
            ) and left[1:] != right[1:]:
                return CounterfactualWorldValidationStatus.FAIL
        return CounterfactualWorldValidationStatus.PASS
    return CounterfactualWorldValidationStatus.FAIL


def _is_visible_value(value: object, active_containers: set[int] | None = None) -> bool:
    if value is None or isinstance(value, str):
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return isfinite(value)
    if isinstance(value, (list, tuple, Mapping)):
        active = set() if active_containers is None else active_containers
        identity = id(value)
        if identity in active:
            return False
        active.add(identity)
        try:
            if isinstance(value, Mapping):
                return all(
                    isinstance(key, str) and _is_visible_value(item, active)
                    for key, item in value.items()
                )
            return all(_is_visible_value(item, active) for item in value)
        except Exception:  # noqa: BLE001 - adversarial containers fail the boundary
            return False
        finally:
            active.remove(identity)
    return False


def _check_truth_boundary(worlds: CounterfactualEhrWorldPair) -> CounterfactualWorldValidationStatus:
    if not isinstance(worlds, CounterfactualEhrWorldPair):
        return CounterfactualWorldValidationStatus.UNEVALUABLE
    try:
        visible = worlds.to_mapping()
        if not _is_visible_value(visible):
            return CounterfactualWorldValidationStatus.FAIL
        for bundle in _bundles(worlds):
            for resource_name in BASE_RESOURCE_NAMES:
                for row in bundle.rows[resource_name]:
                    if any(
                        isinstance(value, bool)
                        or not isinstance(value, (str, int, float))
                        or isinstance(value, float)
                        and not isfinite(value)
                        for _, value in row.values
                    ):
                        return CounterfactualWorldValidationStatus.FAIL
        rendered = repr(worlds)
        if rendered != "CounterfactualEhrWorldPair(<evaluator-only>)" or any(
            token in rendered for token in ("truth", "trajectory", "seed", "stream", "context")
        ):
            return CounterfactualWorldValidationStatus.FAIL
    except Exception:  # noqa: BLE001 - public validator always returns a redacted report
        return CounterfactualWorldValidationStatus.FAIL
    return CounterfactualWorldValidationStatus.PASS


def validate_counterfactual_ehr_worlds(
    worlds: CounterfactualEhrWorldPair,
) -> CounterfactualWorldValidationReport:
    """Revalidate paired fictional EHR worlds with fixed aggregate output."""

    evaluators = {
        "pair_binding": _check_pair_binding,
        "shared_demographics": _check_shared_demographics,
        "shared_observation": _check_shared_observation,
        "observation_invariants": _check_observation_invariants,
        "resource_invariants": _check_resource_invariants,
        "permitted_changes": _check_permitted_changes,
        "truth_boundary": _check_truth_boundary,
    }
    checks = tuple(
        _world_check(name, lambda evaluator=evaluators[name]: evaluator(worlds))
        for name in COUNTERFACTUAL_WORLD_CHECK_NAMES
    )
    return CounterfactualWorldValidationReport(_status_for_checks(checks), checks)


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
    "validate_counterfactual_ehr_worlds",
]
