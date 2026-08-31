"""Evaluator-only contracts for paired fictional growth trajectories.

This module intentionally has no visible-resource or package serialization API.
Counterfactual trajectories, patient identity, seeds, and stream identities are
hidden evaluator state.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from itertools import pairwise
from numbers import Real
from types import MappingProxyType
from typing import Any

import numpy as np

from synthetic.models import (
    AgeRegimeDisorderTrajectory,
    ClinicalEvent,
    DisorderKind,
    LatentDisorderState,
    PatientState,
)
from synthetic.native.age_regime_disorder import AgeRegimeDisorderKernel
from synthetic.native.trajectories import validate_disorder_events
from synthetic.randomness import (
    PRNG_FAMILY,
    SEED_DERIVATION_VERSION,
    NamedRandomStreams,
)

_VERSION_TOKEN = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_SYNTHETIC_PATIENT_TOKEN = re.compile(r"^syn-[A-Za-z0-9][A-Za-z0-9._-]*$")
_WORLDS = frozenset({"baseline", "intervention"})
_STREAM_IDENTITY_VERSION = "counterfactual-stream-identity-v1"


class InterventionKind(str, Enum):
    """Reviewed interventions, including deferred observation-layer kinds."""

    PHYSIOLOGY_SEVERITY = "physiology_severity"
    EARLIER_RECOGNITION = "earlier_recognition"
    TREATMENT_ADHERENCE = "treatment_adherence"
    UTILIZATION_INTENSITY = "utilization_intensity"
    MEASUREMENT_ERROR_REMOVAL = "measurement_error_removal"


class CausalLayer(str, Enum):
    """Closed causal vocabulary for the trajectory replay contract."""

    AGE_REGIME = "age_regime"
    LATENT_DISORDER = "latent_disorder"
    GROWTH_PHYSIOLOGY = "growth_physiology"
    RECOGNITION = "recognition"
    TREATMENT = "treatment"
    EVENT_TRACE = "event_trace"


_SUPPORTED_INTERVENTIONS = frozenset(
    {
        InterventionKind.PHYSIOLOGY_SEVERITY,
        InterventionKind.EARLIER_RECOGNITION,
        InterventionKind.TREATMENT_ADHERENCE,
    }
)

# These are the names currently consumed by AgeRegimeDisorderKernel and its
# native age-regime/disorder collaborators. The matrix fails closed on any
# name outside this set.
_NATIVE_STREAM_NAMES = frozenset(
    {
        "regime.birth",
        "regime.childhood",
        "regime.puberty",
        "regime.residual",
        "regime.head",
        "disorder.familial_short_stature",
        "disorder.constitutional_delay",
        "disorder.growth_hormone_deficiency",
    }
)

_TRAJECTORY_ASSERTIONS = frozenset(
    {
        "growth_z_differs",
        "pre_onset_growth_invariant",
        "growth_z_invariant",
        "recognition_timing_earlier",
        "pre_treatment_growth_invariant",
        "post_treatment_growth_may_change",
    }
)

# These sets are the reviewed, intervention-specific semantics.  They are
# kept separate from DEFAULT_CHANGE_MATRICES so construction can validate a
# caller-supplied matrix while the default objects are being created.
_FIXED_MATRIX_SEMANTICS: dict[
    InterventionKind, tuple[frozenset[CausalLayer], frozenset[CausalLayer], frozenset[CausalLayer], frozenset[str]]
] = {
    InterventionKind.PHYSIOLOGY_SEVERITY: (
        frozenset({CausalLayer.GROWTH_PHYSIOLOGY}),
        frozenset(),
        frozenset(
            {
                CausalLayer.AGE_REGIME,
                CausalLayer.LATENT_DISORDER,
                CausalLayer.RECOGNITION,
                CausalLayer.TREATMENT,
            }
        ),
        frozenset({"growth_z_differs", "pre_onset_growth_invariant"}),
    ),
    InterventionKind.EARLIER_RECOGNITION: (
        frozenset({CausalLayer.RECOGNITION}),
        frozenset({CausalLayer.EVENT_TRACE}),
        frozenset(
            {
                CausalLayer.AGE_REGIME,
                CausalLayer.LATENT_DISORDER,
                CausalLayer.GROWTH_PHYSIOLOGY,
                CausalLayer.TREATMENT,
            }
        ),
        frozenset({"growth_z_invariant", "recognition_timing_earlier"}),
    ),
    InterventionKind.TREATMENT_ADHERENCE: (
        frozenset({CausalLayer.TREATMENT}),
        frozenset({CausalLayer.GROWTH_PHYSIOLOGY}),
        frozenset(
            {
                CausalLayer.AGE_REGIME,
                CausalLayer.LATENT_DISORDER,
                CausalLayer.RECOGNITION,
            }
        ),
        frozenset({"pre_treatment_growth_invariant", "post_treatment_growth_may_change"}),
    ),
}

_ALLOWED_ASSERTIONS_BY_INTERVENTION = {
    InterventionKind.PHYSIOLOGY_SEVERITY: frozenset(
        {"growth_z_differs", "pre_onset_growth_invariant"}
    ),
    InterventionKind.EARLIER_RECOGNITION: frozenset(
        {"growth_z_invariant", "recognition_timing_earlier"}
    ),
    InterventionKind.TREATMENT_ADHERENCE: frozenset(
        {"pre_treatment_growth_invariant", "post_treatment_growth_may_change"}
    ),
}

_MATRIX_KEYS = frozenset(
    {
        "version",
        "intervention",
        "manipulated_nodes",
        "permitted_descendants",
        "required_invariants",
        "reused_streams",
        "resampled_streams",
        "trajectory_assertions",
    }
)


def _require_frozenset(name: str, value: object) -> frozenset[Any]:
    if not isinstance(value, frozenset):
        raise TypeError(f"{name} must be a frozenset")
    return value


def _require_causal_layers(name: str, value: object) -> frozenset[CausalLayer]:
    values = _require_frozenset(name, value)
    if not all(isinstance(item, CausalLayer) for item in values):
        raise ValueError(f"{name} must contain only CausalLayer values")
    return values


def _require_streams(name: str, value: object) -> frozenset[str]:
    values = _require_frozenset(name, value)
    if not all(isinstance(item, str) and item in _NATIVE_STREAM_NAMES for item in values):
        raise ValueError(f"{name} must contain only a declared native stream")
    return values


def _require_assertions(value: object) -> frozenset[str]:
    values = _require_frozenset("trajectory_assertions", value)
    if not all(isinstance(item, str) and item in _TRAJECTORY_ASSERTIONS for item in values):
        raise ValueError("trajectory_assertions must contain only declared assertion tokens")
    return values


def _sequence_from_mapping(mapping: Mapping[str, object], key: str) -> list[object]:
    value = mapping[key]
    if not isinstance(value, list):
        raise TypeError(f"{key} must be a list")
    if len(value) != len(set(value)):
        raise ValueError(f"{key} must not contain duplicate values")
    return value


def _layer_set_from_mapping(mapping: Mapping[str, object], key: str) -> frozenset[CausalLayer]:
    values = _sequence_from_mapping(mapping, key)
    try:
        return frozenset(CausalLayer(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must contain only CausalLayer values") from exc


def _string_set_from_mapping(mapping: Mapping[str, object], key: str) -> frozenset[str]:
    values = _sequence_from_mapping(mapping, key)
    if not all(isinstance(value, str) for value in values):
        raise ValueError(f"{key} must contain only string tokens")
    return frozenset(values)


@dataclass(frozen=True)
class CounterfactualChangeMatrix:
    """Strict causal permissions for one supported trajectory intervention."""

    version: str
    intervention: InterventionKind
    manipulated_nodes: frozenset[CausalLayer]
    permitted_descendants: frozenset[CausalLayer]
    required_invariants: frozenset[CausalLayer]
    reused_streams: frozenset[str]
    resampled_streams: frozenset[str]
    trajectory_assertions: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not _VERSION_TOKEN.fullmatch(self.version):
            raise ValueError("version must be a nonempty version token")
        if not isinstance(self.intervention, InterventionKind):
            raise ValueError("intervention must be an InterventionKind")  # noqa: TRY004
        if self.intervention not in _SUPPORTED_INTERVENTIONS:
            raise ValueError("intervention is not supported by trajectory replay")

        manipulated = _require_causal_layers("manipulated_nodes", self.manipulated_nodes)
        permitted = _require_causal_layers("permitted_descendants", self.permitted_descendants)
        invariants = _require_causal_layers("required_invariants", self.required_invariants)
        if not manipulated:
            raise ValueError("manipulated_nodes must be nonempty")
        if manipulated & permitted or manipulated & invariants or permitted & invariants:
            raise ValueError("causal node sets must be pairwise disjoint")

        reused = _require_streams("reused_streams", self.reused_streams)
        resampled = _require_streams("resampled_streams", self.resampled_streams)
        if reused & resampled:
            raise ValueError("reused_streams and resampled_streams must be disjoint")
        if resampled:
            raise ValueError("stream resampling is not supported by trajectory replay")
        if not reused:
            raise ValueError("reused_streams must be nonempty")
        assertions = _require_assertions(self.trajectory_assertions)
        if not assertions:
            raise ValueError("trajectory_assertions must be nonempty")

        fixed = _FIXED_MATRIX_SEMANTICS[self.intervention]
        fixed_manipulated, fixed_permitted, fixed_invariants, fixed_assertions = fixed
        if manipulated != fixed_manipulated:
            raise ValueError("manipulated_nodes are incompatible with the intervention")
        if not permitted.issubset(fixed_permitted):
            raise ValueError("permitted_descendants weaken the fixed intervention semantics")
        if not invariants.issuperset(fixed_invariants):
            raise ValueError("required_invariants weaken the fixed intervention semantics")
        allowed_assertions = _ALLOWED_ASSERTIONS_BY_INTERVENTION[self.intervention]
        if not assertions.issuperset(fixed_assertions) or not assertions.issubset(
            allowed_assertions
        ):
            raise ValueError("trajectory assertions are incompatible with the intervention")
        if "recognition_timing_earlier" in assertions and CausalLayer.EVENT_TRACE not in permitted:
            raise ValueError(
                "permitted_descendants must include the event trace for recognition timing"
            )
        if (
            "post_treatment_growth_may_change" in assertions
            and CausalLayer.GROWTH_PHYSIOLOGY not in permitted
        ):
            raise ValueError(
                "permitted_descendants must include growth physiology for post-treatment growth"
            )
        if not reused.issuperset(_NATIVE_STREAM_NAMES):
            raise ValueError("reused_streams weaken the fixed intervention semantics")

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> CounterfactualChangeMatrix:
        """Parse the complete evaluator matrix mapping without coercive defaults."""

        if not isinstance(mapping, Mapping) or set(mapping) != _MATRIX_KEYS:
            raise ValueError("matrix mapping must contain exactly the declared keys")
        try:
            intervention = InterventionKind(mapping["intervention"])
        except (TypeError, ValueError) as exc:
            raise ValueError("intervention must be an InterventionKind token") from exc
        return cls(
            version=mapping["version"],  # type: ignore[arg-type]
            intervention=intervention,
            manipulated_nodes=_layer_set_from_mapping(mapping, "manipulated_nodes"),
            permitted_descendants=_layer_set_from_mapping(mapping, "permitted_descendants"),
            required_invariants=_layer_set_from_mapping(mapping, "required_invariants"),
            reused_streams=_string_set_from_mapping(mapping, "reused_streams"),
            resampled_streams=_string_set_from_mapping(mapping, "resampled_streams"),
            trajectory_assertions=_string_set_from_mapping(mapping, "trajectory_assertions"),
        )

    def to_mapping(self) -> dict[str, object]:
        """Return the canonical evaluator representation of this matrix."""

        return {
            "version": self.version,
            "intervention": self.intervention.value,
            "manipulated_nodes": sorted(node.value for node in self.manipulated_nodes),
            "permitted_descendants": sorted(node.value for node in self.permitted_descendants),
            "required_invariants": sorted(node.value for node in self.required_invariants),
            "reused_streams": sorted(self.reused_streams),
            "resampled_streams": sorted(self.resampled_streams),
            "trajectory_assertions": sorted(self.trajectory_assertions),
        }


def _matrix(
    intervention: InterventionKind,
    manipulated_nodes: frozenset[CausalLayer],
    permitted_descendants: frozenset[CausalLayer],
    required_invariants: frozenset[CausalLayer],
    trajectory_assertions: frozenset[str],
) -> CounterfactualChangeMatrix:
    return CounterfactualChangeMatrix(
        version="counterfactual-trajectory-v1",
        intervention=intervention,
        manipulated_nodes=manipulated_nodes,
        permitted_descendants=permitted_descendants,
        required_invariants=required_invariants,
        reused_streams=_NATIVE_STREAM_NAMES,
        resampled_streams=frozenset(),
        trajectory_assertions=trajectory_assertions,
    )


DEFAULT_CHANGE_MATRICES: Mapping[InterventionKind, CounterfactualChangeMatrix] = MappingProxyType(
    {
        InterventionKind.PHYSIOLOGY_SEVERITY: _matrix(
            InterventionKind.PHYSIOLOGY_SEVERITY,
            frozenset({CausalLayer.GROWTH_PHYSIOLOGY}),
            frozenset(),
            frozenset(
                {
                    CausalLayer.AGE_REGIME,
                    CausalLayer.LATENT_DISORDER,
                    CausalLayer.RECOGNITION,
                    CausalLayer.TREATMENT,
                }
            ),
            frozenset({"growth_z_differs", "pre_onset_growth_invariant"}),
        ),
        InterventionKind.EARLIER_RECOGNITION: _matrix(
            InterventionKind.EARLIER_RECOGNITION,
            frozenset({CausalLayer.RECOGNITION}),
            frozenset({CausalLayer.EVENT_TRACE}),
            frozenset(
                {
                    CausalLayer.AGE_REGIME,
                    CausalLayer.LATENT_DISORDER,
                    CausalLayer.GROWTH_PHYSIOLOGY,
                    CausalLayer.TREATMENT,
                }
            ),
            frozenset({"growth_z_invariant", "recognition_timing_earlier"}),
        ),
        InterventionKind.TREATMENT_ADHERENCE: _matrix(
            InterventionKind.TREATMENT_ADHERENCE,
            frozenset({CausalLayer.TREATMENT}),
            frozenset({CausalLayer.GROWTH_PHYSIOLOGY}),
            frozenset(
                {
                    CausalLayer.AGE_REGIME,
                    CausalLayer.LATENT_DISORDER,
                    CausalLayer.RECOGNITION,
                }
            ),
            frozenset(
                {
                    "pre_treatment_growth_invariant",
                    "post_treatment_growth_may_change",
                }
            ),
        ),
    }
)


def default_change_matrix(intervention: InterventionKind) -> CounterfactualChangeMatrix:
    """Return the fixed matrix for a supported trajectory intervention."""

    if not isinstance(intervention, InterventionKind):
        raise ValueError("intervention must be an InterventionKind")  # noqa: TRY004
    try:
        return DEFAULT_CHANGE_MATRICES[intervention]
    except KeyError as exc:
        raise ValueError("intervention is not supported by trajectory replay") from exc


def _validate_not_weaker(matrix: CounterfactualChangeMatrix) -> None:
    fixed = default_change_matrix(matrix.intervention)
    if (
        matrix.manipulated_nodes != fixed.manipulated_nodes
        or not matrix.required_invariants.issuperset(fixed.required_invariants)
        or not matrix.permitted_descendants.issubset(fixed.permitted_descendants)
        or not matrix.reused_streams.issuperset(fixed.reused_streams)
        or not matrix.resampled_streams.issubset(fixed.resampled_streams)
        or not matrix.trajectory_assertions.issuperset(fixed.trajectory_assertions)
    ):
        raise ValueError("matrix must not weaken the fixed intervention semantics")


@dataclass(frozen=True, repr=False)
class CounterfactualContext:
    """Hidden deterministic context for one fictional trajectory world."""

    patient: PatientState = field(repr=False)
    run_seed: int = field(repr=False)
    patient_index: int = field(repr=False)
    world: str
    matrix: CounterfactualChangeMatrix = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.patient, PatientState):
            raise TypeError("patient must be a PatientState")
        if not _SYNTHETIC_PATIENT_TOKEN.fullmatch(self.patient.patient_id):
            raise ValueError("patient must identify a fictional synthetic patient")
        if (
            isinstance(self.run_seed, bool)
            or not isinstance(self.run_seed, int)
            or self.run_seed < 0
        ):
            raise ValueError("run_seed must be a nonnegative integer")
        if (
            isinstance(self.patient_index, bool)
            or not isinstance(self.patient_index, int)
            or self.patient_index < 0
        ):
            raise ValueError("patient_index must be a nonnegative integer")
        if not isinstance(self.world, str) or self.world not in _WORLDS:
            raise ValueError("world must be baseline or intervention")
        if not isinstance(self.matrix, CounterfactualChangeMatrix):
            raise TypeError("matrix must be a CounterfactualChangeMatrix")
        _validate_not_weaker(self.matrix)

    @property
    def intervention(self) -> InterventionKind:
        return self.matrix.intervention

    def generator(self, name: str) -> np.random.Generator:
        """Return a fresh deterministic generator for a matrix-declared stream."""

        self._require_declared_stream(name)
        return NamedRandomStreams(self.run_seed, self.patient_index).generator(name)

    def stream_identity(self, name: str) -> str:
        """Return a deterministic opaque identity, independent of world label."""

        self._require_declared_stream(name)
        material = "\x1f".join(
            (
                _STREAM_IDENTITY_VERSION,
                SEED_DERIVATION_VERSION,
                PRNG_FAMILY,
                str(self.run_seed),
                str(self.patient_index),
                name,
            )
        ).encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    def _require_declared_stream(self, name: object) -> None:
        declared = self.matrix.reused_streams | self.matrix.resampled_streams
        if not isinstance(name, str) or name not in declared:
            raise ValueError("stream must be declared by the matrix")

    def to_mapping(self) -> dict[str, object]:
        """Return metadata with patient, seed, index, and identities removed."""

        return {
            "world": self.world,
            "intervention": self.intervention.value,
            "matrix_version": self.matrix.version,
            "reused_stream_names": sorted(self.matrix.reused_streams),
            "resampled_stream_names": sorted(self.matrix.resampled_streams),
        }

    def __repr__(self) -> str:
        return "CounterfactualContext(<evaluator-only>)"


def _trajectory_patient_id(trajectory: AgeRegimeDisorderTrajectory) -> str:
    return trajectory.physiology.points[0].patient_id


@dataclass(frozen=True, repr=False)
class CounterfactualPair:
    """Hidden paired trajectory worlds and the matrix that governs them."""

    baseline: AgeRegimeDisorderTrajectory = field(repr=False)
    intervention: AgeRegimeDisorderTrajectory = field(repr=False)
    baseline_context: CounterfactualContext = field(repr=False)
    intervention_context: CounterfactualContext = field(repr=False)
    matrix: CounterfactualChangeMatrix = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.baseline, AgeRegimeDisorderTrajectory) or not isinstance(
            self.intervention, AgeRegimeDisorderTrajectory
        ):
            raise TypeError("worlds must be AgeRegimeDisorderTrajectory values")
        if not isinstance(self.baseline_context, CounterfactualContext) or not isinstance(
            self.intervention_context, CounterfactualContext
        ):
            raise TypeError("contexts must be CounterfactualContext values")
        if not isinstance(self.matrix, CounterfactualChangeMatrix):
            raise TypeError("matrix must be a CounterfactualChangeMatrix")
        if (
            self.baseline_context.world != "baseline"
            or self.intervention_context.world != "intervention"
        ):
            raise ValueError("contexts must identify baseline and intervention worlds")
        if (
            self.baseline_context.matrix != self.matrix
            or self.intervention_context.matrix != self.matrix
        ):
            raise ValueError("contexts and pair must use one change matrix")
        if (
            self.baseline_context.run_seed != self.intervention_context.run_seed
            or self.baseline_context.patient_index
            != self.intervention_context.patient_index
        ):
            raise ValueError("paired worlds must share one deterministic stream identity")
        baseline_patient = _trajectory_patient_id(self.baseline)
        intervention_patient = _trajectory_patient_id(self.intervention)
        if (
            baseline_patient != intervention_patient
            or self.baseline_context.patient != self.intervention_context.patient
            or baseline_patient != self.baseline_context.patient.patient_id
        ):
            raise ValueError("paired worlds must contain one synthetic patient")
        if self.baseline.physiology.state != self.intervention.physiology.state:
            raise ValueError("paired worlds must share one age-regime state")
        if self.matrix.intervention is InterventionKind.TREATMENT_ADHERENCE:
            if _disorder_without_treatment_response(
                self.baseline.disorder
            ) != _disorder_without_treatment_response(self.intervention.disorder):
                raise ValueError("paired worlds must share one latent disorder state")
        elif self.baseline.disorder != self.intervention.disorder:
            raise ValueError("paired worlds must share one latent disorder state")
        for name in self.matrix.reused_streams:
            if self.baseline_context.stream_identity(
                name
            ) != self.intervention_context.stream_identity(name):
                raise ValueError("reused stream identities must match across worlds")

    def to_mapping(self) -> dict[str, object]:
        """Return evaluator metadata without either world or its hidden context."""

        return {
            "contract": "counterfactual-trajectory-pair-v1",
            "matrix_version": self.matrix.version,
            "intervention": self.matrix.intervention.value,
        }

    def __repr__(self) -> str:
        return "CounterfactualPair(<evaluator-only>)"


def _canonical_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _canonical_value(getattr(value, item.name))
            for item in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("canonical mappings must have string keys")
        return {key: _canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_canonical_value(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True))
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError("value cannot be canonically hashed")


def canonical_hidden_hash(value: object) -> str:
    """Hash hidden evaluator state using canonical JSON bytes."""

    try:
        encoded = json.dumps(
            _canonical_value(value),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError("hidden evaluator value is not canonical") from exc
    return hashlib.sha256(encoded).hexdigest()


class CounterfactualValidationStatus(str, Enum):
    """Aggregate status for one counterfactual validation report."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNEVALUABLE = "UNEVALUABLE"


# Short alias for callers that use the generic validation terminology.
ValidationStatus = CounterfactualValidationStatus

_CHECK_NAMES = (
    "shared_patient",
    "shared_age_state",
    "shared_latent_state",
    "stream_reuse",
    "event_order",
    "age_coverage",
    "invariant_layers",
    "permitted_changes",
    "trajectory_assertions",
)
_CHECK_NAME_SET = frozenset(_CHECK_NAMES)
_REASON_CODES = frozenset(
    {
        "OK",
        "PATIENT_MISMATCH",
        "SHARED_STATE_MISMATCH",
        "STREAM_REUSE_MISMATCH",
        "EVENT_ORDER_INVALID",
        "AGE_COVERAGE_INVALID",
        "INVARIANT_LAYER_CHANGED",
        "FORBIDDEN_LAYER_CHANGED",
        "MANIPULATED_LAYER_UNCHANGED",
        "ASSERTION_FAILED",
        "ASSERTION_UNEVALUABLE",
        "MALFORMED_PAIR",
    }
)
_EVENT_PHASE_ORDER = {
    "latent_onset": 0,
    "observable_phenotype": 1,
    "recognition_opportunity": 2,
    "workup": 3,
    "recorded_diagnosis": 4,
    "treatment_start": 5,
    "treatment_response": 6,
    "treatment_nonresponse": 6,
}
_TREATMENT_EVENT_TYPES = frozenset(
    {"treatment_start", "treatment_response", "treatment_nonresponse"}
)
_PHYSIOLOGY_SEVERITY_SCALE = 0.5
_EARLIER_RECOGNITION_SHIFT_DAYS = 90


def _disorder_without_treatment_response(
    state: LatentDisorderState,
) -> LatentDisorderState:
    """Return the pairing projection for the treatment-adherence intervention."""

    return dataclasses.replace(state, treatment_response=0.0)


@dataclass(frozen=True)
class CounterfactualCheck:
    """One aggregate-only causal validation check."""

    name: str
    status: CounterfactualValidationStatus
    reason_code: str

    def __post_init__(self) -> None:
        if self.name not in _CHECK_NAME_SET:
            raise ValueError("unknown counterfactual check name")
        if not isinstance(self.status, CounterfactualValidationStatus):
            raise TypeError("status must be a CounterfactualValidationStatus")
        if self.reason_code not in _REASON_CODES:
            raise ValueError("unknown counterfactual reason code")

    def to_mapping(self) -> dict[str, str]:
        """Return only the fixed aggregate fields for this check."""

        return {
            "name": self.name,
            "status": self.status.value,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True, repr=False)
class CounterfactualValidationReport:
    """Immutable aggregate report with no patient- or trajectory-level evidence."""

    status: CounterfactualValidationStatus
    checks: tuple[CounterfactualCheck, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.status, CounterfactualValidationStatus):
            raise TypeError("status must be a CounterfactualValidationStatus")
        if not isinstance(self.checks, tuple) or not self.checks:
            raise ValueError("checks must be a nonempty tuple")
        if not all(isinstance(check, CounterfactualCheck) for check in self.checks):
            raise TypeError("checks must contain CounterfactualCheck values")
        names = tuple(check.name for check in self.checks)
        if len(names) != len(set(names)):
            raise ValueError("checks must not contain duplicate names")
        if set(names) != _CHECK_NAME_SET:
            raise ValueError("checks must contain the fixed counterfactual checks")
        if self.status is not _status_for_checks(self.checks):
            raise ValueError("status must match counterfactual check statuses")
        object.__setattr__(self, "checks", tuple(sorted(self.checks, key=lambda check: check.name)))

    @property
    def check_counts(self) -> Mapping[str, int]:
        """Return aggregate counts by fixed status token."""

        return MappingProxyType(
            {
                status.value: sum(check.status is status for check in self.checks)
                for status in CounterfactualValidationStatus
            }
        )

    def to_mapping(self) -> dict[str, object]:
        """Return a report safe for ordinary aggregate logging."""

        return {
            "status": self.status.value,
            "check_counts": dict(self.check_counts),
            "checks": [check.to_mapping() for check in self.checks],
        }

    def __repr__(self) -> str:
        return (
            "CounterfactualValidationReport(" \
            f"status={self.status.value!r}, checks={len(self.checks)})"
        )


def _status_for_checks(
    checks: tuple[CounterfactualCheck, ...],
) -> CounterfactualValidationStatus:
    if any(check.status is CounterfactualValidationStatus.FAIL for check in checks):
        return CounterfactualValidationStatus.FAIL
    if any(check.status is CounterfactualValidationStatus.UNEVALUABLE for check in checks):
        return CounterfactualValidationStatus.UNEVALUABLE
    return CounterfactualValidationStatus.PASS


def _check(
    name: str,
    evaluator: Any,
) -> CounterfactualCheck:
    try:
        status, reason_code = evaluator()
    except (ArithmeticError, AttributeError, IndexError, KeyError, TypeError, ValueError):
        status, reason_code = (
            CounterfactualValidationStatus.UNEVALUABLE,
            "MALFORMED_PAIR",
        )
    return CounterfactualCheck(name, status, reason_code)


def _normal_events(
    trajectory: AgeRegimeDisorderTrajectory,
    *,
    exclude_treatment: bool = False,
) -> tuple[tuple[str, int, str | None, bool], ...]:
    events = trajectory.events
    normalized = []
    for event in events:
        if exclude_treatment and event.event_type in _TREATMENT_EVENT_TYPES:
            continue
        normalized.append((event.event_type, event.age_days, event.code, event.hidden))
    return tuple(normalized)


def _layer_value(
    trajectory: AgeRegimeDisorderTrajectory,
    layer: CausalLayer,
    *,
    matrix: CounterfactualChangeMatrix,
) -> object:
    if layer is CausalLayer.AGE_REGIME:
        return trajectory.physiology.state
    if layer is CausalLayer.LATENT_DISORDER:
        state = trajectory.disorder
        if matrix.intervention is InterventionKind.TREATMENT_ADHERENCE:
            state = _disorder_without_treatment_response(state)
        return state
    if layer is CausalLayer.GROWTH_PHYSIOLOGY:
        # Compare canonical z-score layers. Raw centimetre trajectories are
        # derived observations and are intentionally not used for causality.
        return tuple(
            (
                point.age_days,
                point.length_z,
                point.height_z,
                point.weight_z,
                point.bmi_z,
            )
            for point in trajectory.physiology.points
        )
    if layer is CausalLayer.RECOGNITION:
        return tuple(
            (event.event_type, event.age_days)
            for event in trajectory.events
            if event.event_type == "recognition_opportunity"
        )
    if layer is CausalLayer.TREATMENT:
        state = trajectory.disorder
        return {
            "treatment_start_age_days": state.treatment_start_age_days,
            "treatment_response": state.treatment_response,
            "events": tuple(
                (event.event_type, event.age_days)
                for event in trajectory.events
                if event.event_type in _TREATMENT_EVENT_TYPES
            ),
        }
    if layer is CausalLayer.EVENT_TRACE:
        return _normal_events(
            trajectory,
            exclude_treatment=matrix.intervention is InterventionKind.TREATMENT_ADHERENCE,
        )
    raise ValueError("unknown causal layer")


def _layer_hashes(
    pair: CounterfactualPair,
) -> dict[CausalLayer, tuple[str, str]]:
    return {
        layer: (
            canonical_hidden_hash(
                _layer_value(pair.baseline, layer, matrix=pair.matrix)
            ),
            canonical_hidden_hash(
                _layer_value(pair.intervention, layer, matrix=pair.matrix)
            ),
        )
        for layer in CausalLayer
    }


def _growth_values(
    trajectory: AgeRegimeDisorderTrajectory,
) -> tuple[tuple[int, float | None, float | None], ...]:
    values: list[tuple[int, float | None, float | None]] = []
    for point in trajectory.physiology.points:
        height_z = point.height_z if point.height_z is not None else point.length_z
        mass_z = point.bmi_z if point.bmi_z is not None else point.weight_z
        values.append((point.age_days, height_z, mass_z))
    return tuple(values)


def _aligned_growth_values(
    baseline: AgeRegimeDisorderTrajectory,
    intervention: AgeRegimeDisorderTrajectory,
    *,
    predicate: Any = None,
) -> tuple[tuple[float | None, float | None, float | None, float | None], ...]:
    left = _growth_values(baseline)
    right = _growth_values(intervention)
    if len(left) != len(right):
        raise ValueError("paired growth coverage differs")
    aligned = []
    for (left_age, left_height, left_bmi), (right_age, right_height, right_bmi) in zip(
        left, right, strict=True
    ):
        if left_age != right_age:
            raise ValueError("paired growth ages differ")
        if predicate is not None and not predicate(left_age):
            continue
        aligned.append((left_height, right_height, left_bmi, right_bmi))
    return tuple(aligned)


def _check_shared_patient(pair: CounterfactualPair):
    baseline_id = _trajectory_patient_id(pair.baseline)
    intervention_id = _trajectory_patient_id(pair.intervention)
    if (
        baseline_id != intervention_id
        or pair.baseline_context.patient.patient_id != baseline_id
        or pair.intervention_context.patient.patient_id != baseline_id
        or pair.baseline_context.patient != pair.intervention_context.patient
    ):
        return CounterfactualValidationStatus.FAIL, "PATIENT_MISMATCH"
    return CounterfactualValidationStatus.PASS, "OK"


def _check_shared_age_state(pair: CounterfactualPair):
    if pair.baseline.physiology.state != pair.intervention.physiology.state:
        return CounterfactualValidationStatus.FAIL, "SHARED_STATE_MISMATCH"
    return CounterfactualValidationStatus.PASS, "OK"


def _check_shared_latent_state(pair: CounterfactualPair):
    if pair.matrix.intervention is InterventionKind.TREATMENT_ADHERENCE:
        baseline = _disorder_without_treatment_response(pair.baseline.disorder)
        intervention = _disorder_without_treatment_response(pair.intervention.disorder)
    else:
        baseline = pair.baseline.disorder
        intervention = pair.intervention.disorder
    if baseline != intervention:
        return CounterfactualValidationStatus.FAIL, "SHARED_STATE_MISMATCH"
    return CounterfactualValidationStatus.PASS, "OK"


def _check_stream_reuse(pair: CounterfactualPair):
    if not pair.matrix.reused_streams:
        return CounterfactualValidationStatus.UNEVALUABLE, "MALFORMED_PAIR"
    if (
        pair.baseline_context.run_seed != pair.intervention_context.run_seed
        or pair.baseline_context.patient_index != pair.intervention_context.patient_index
    ):
        return CounterfactualValidationStatus.FAIL, "STREAM_REUSE_MISMATCH"
    for name in pair.matrix.reused_streams:
        if pair.baseline_context.stream_identity(name) != pair.intervention_context.stream_identity(
            name
        ):
            return CounterfactualValidationStatus.FAIL, "STREAM_REUSE_MISMATCH"
    return CounterfactualValidationStatus.PASS, "OK"


def _event_order_valid(
    trajectory: AgeRegimeDisorderTrajectory,
    patient: PatientState,
) -> bool:
    try:
        validate_disorder_events(patient, trajectory.disorder, trajectory.events)
    except (TypeError, ValueError):
        return False
    return True


def _check_event_order(pair: CounterfactualPair):
    if not _event_order_valid(
        pair.baseline, pair.baseline_context.patient
    ) or not _event_order_valid(pair.intervention, pair.intervention_context.patient):
        return CounterfactualValidationStatus.FAIL, "EVENT_ORDER_INVALID"
    return CounterfactualValidationStatus.PASS, "OK"


def _check_age_coverage(pair: CounterfactualPair):
    baseline_points = pair.baseline.physiology.points
    intervention_points = pair.intervention.physiology.points
    if not baseline_points or len(baseline_points) != len(intervention_points):
        return CounterfactualValidationStatus.UNEVALUABLE, "AGE_COVERAGE_INVALID"
    baseline_ages = tuple(point.age_days for point in baseline_points)
    intervention_ages = tuple(point.age_days for point in intervention_points)
    if baseline_ages != intervention_ages or any(
        left >= right for left, right in pairwise(baseline_ages)
    ):
        return CounterfactualValidationStatus.FAIL, "AGE_COVERAGE_INVALID"
    for point in (*baseline_points, *intervention_points):
        for value in (
            point.length_z,
            point.height_z,
            point.weight_z,
            point.bmi_z,
        ):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, Real)
                or not math.isfinite(float(value))
            ):
                return CounterfactualValidationStatus.FAIL, "AGE_COVERAGE_INVALID"
    return CounterfactualValidationStatus.PASS, "OK"


def _check_invariant_layers(pair: CounterfactualPair):
    hashes = _layer_hashes(pair)
    for layer in pair.matrix.required_invariants:
        baseline_hash, intervention_hash = hashes[layer]
        if baseline_hash != intervention_hash:
            return CounterfactualValidationStatus.FAIL, "INVARIANT_LAYER_CHANGED"
    return CounterfactualValidationStatus.PASS, "OK"


def _check_permitted_changes(pair: CounterfactualPair):
    hashes = _layer_hashes(pair)
    changed = {
        layer
        for layer, (baseline_hash, intervention_hash) in hashes.items()
        if baseline_hash != intervention_hash
    }
    allowed = pair.matrix.manipulated_nodes | pair.matrix.permitted_descendants
    if changed - allowed:
        return CounterfactualValidationStatus.FAIL, "FORBIDDEN_LAYER_CHANGED"
    if (
        pair.matrix.intervention is InterventionKind.EARLIER_RECOGNITION
        and not _changes_only_recognition_timing(pair)
    ):
        return CounterfactualValidationStatus.FAIL, "FORBIDDEN_LAYER_CHANGED"
    if not pair.matrix.manipulated_nodes.issubset(changed):
        return CounterfactualValidationStatus.UNEVALUABLE, "MANIPULATED_LAYER_UNCHANGED"
    return CounterfactualValidationStatus.PASS, "OK"


def _changes_only_recognition_timing(pair: CounterfactualPair) -> bool:
    def timing_scoped_event(event: ClinicalEvent) -> object:
        if event.event_type != "recognition_opportunity":
            return event
        return (event.patient_id, event.event_type, event.code, event.hidden)

    baseline = tuple(timing_scoped_event(event) for event in pair.baseline.events)
    intervention = tuple(timing_scoped_event(event) for event in pair.intervention.events)
    return baseline == intervention


def _recognition_ages(trajectory: AgeRegimeDisorderTrajectory) -> tuple[int, ...]:
    return tuple(
        event.age_days
        for event in trajectory.events
        if event.event_type == "recognition_opportunity"
    )


def _treatment_start(trajectory: AgeRegimeDisorderTrajectory) -> int | None:
    state_start = trajectory.disorder.treatment_start_age_days
    event_starts = tuple(
        event.age_days
        for event in trajectory.events
        if event.event_type == "treatment_start"
    )
    if state_start is None or event_starts != (state_start,):
        return None
    return state_start


def _compare_growth_window(
    pair: CounterfactualPair,
    predicate: Any,
) -> tuple[CounterfactualValidationStatus, str]:
    values = _aligned_growth_values(
        pair.baseline,
        pair.intervention,
        predicate=predicate,
    )
    if not values:
        return CounterfactualValidationStatus.UNEVALUABLE, "ASSERTION_UNEVALUABLE"
    if any(
        left_height != right_height or left_bmi != right_bmi
        for left_height, right_height, left_bmi, right_bmi in values
    ):
        return CounterfactualValidationStatus.FAIL, "ASSERTION_FAILED"
    return CounterfactualValidationStatus.PASS, "OK"


def _evaluate_assertion(pair: CounterfactualPair, assertion: str):
    if assertion == "growth_z_differs":
        values = _aligned_growth_values(pair.baseline, pair.intervention)
        if not values:
            return CounterfactualValidationStatus.UNEVALUABLE, "ASSERTION_UNEVALUABLE"
        if not any(
            left_height != right_height or left_bmi != right_bmi
            for left_height, right_height, left_bmi, right_bmi in values
        ):
            return CounterfactualValidationStatus.UNEVALUABLE, "MANIPULATED_LAYER_UNCHANGED"
        if pair.matrix.intervention is InterventionKind.PHYSIOLOGY_SEVERITY:
            for left_height, right_height, left_bmi, right_bmi in values:
                if (
                    left_height is not None
                    and right_height is not None
                    and right_height < left_height
                ):
                    return CounterfactualValidationStatus.FAIL, "ASSERTION_FAILED"
                if (
                    pair.baseline.disorder.kind is DisorderKind.GROWTH_HORMONE_DEFICIENCY
                    and left_bmi is not None
                    and right_bmi is not None
                    and right_bmi > left_bmi
                ):
                    return CounterfactualValidationStatus.FAIL, "ASSERTION_FAILED"
        elif pair.matrix.intervention is InterventionKind.TREATMENT_ADHERENCE:
            baseline_response = pair.baseline.disorder.treatment_response
            intervention_response = pair.intervention.disorder.treatment_response
            response_increased = intervention_response > baseline_response
            response_decreased = intervention_response < baseline_response
            for left_height, right_height, left_bmi, right_bmi in values:
                if response_decreased:
                    if (
                        left_height is not None
                        and right_height is not None
                        and right_height > left_height
                    ):
                        return CounterfactualValidationStatus.FAIL, "ASSERTION_FAILED"
                    if (
                        left_bmi is not None
                        and right_bmi is not None
                        and right_bmi < left_bmi
                    ):
                        return CounterfactualValidationStatus.FAIL, "ASSERTION_FAILED"
                elif response_increased:
                    if (
                        left_height is not None
                        and right_height is not None
                        and right_height < left_height
                    ):
                        return CounterfactualValidationStatus.FAIL, "ASSERTION_FAILED"
                    if (
                        left_bmi is not None
                        and right_bmi is not None
                        and right_bmi > left_bmi
                    ):
                        return CounterfactualValidationStatus.FAIL, "ASSERTION_FAILED"
        return CounterfactualValidationStatus.PASS, "OK"

    if assertion == "pre_onset_growth_invariant":
        onset = pair.baseline.disorder.onset_age_days
        if onset is None:
            return CounterfactualValidationStatus.UNEVALUABLE, "ASSERTION_UNEVALUABLE"
        return _compare_growth_window(pair, lambda age: age < onset)

    if assertion == "growth_z_invariant":
        return _compare_growth_window(pair, lambda age: True)

    if assertion == "recognition_timing_earlier":
        baseline = _recognition_ages(pair.baseline)
        intervention = _recognition_ages(pair.intervention)
        if not baseline or len(baseline) != len(intervention):
            return CounterfactualValidationStatus.UNEVALUABLE, "ASSERTION_UNEVALUABLE"
        if not all(left > right for left, right in zip(baseline, intervention, strict=True)):
            return CounterfactualValidationStatus.FAIL, "ASSERTION_FAILED"
        return CounterfactualValidationStatus.PASS, "OK"

    if assertion == "pre_treatment_growth_invariant":
        baseline_start = _treatment_start(pair.baseline)
        intervention_start = _treatment_start(pair.intervention)
        if baseline_start is None or baseline_start != intervention_start:
            return CounterfactualValidationStatus.UNEVALUABLE, "ASSERTION_UNEVALUABLE"
        return _compare_growth_window(pair, lambda age: age < baseline_start)

    if assertion == "post_treatment_growth_may_change":
        start = _treatment_start(pair.baseline)
        intervention_start = _treatment_start(pair.intervention)
        if start is None or start != intervention_start:
            return CounterfactualValidationStatus.UNEVALUABLE, "ASSERTION_UNEVALUABLE"
        values = _aligned_growth_values(
            pair.baseline,
            pair.intervention,
            predicate=lambda age: age > start,
        )
        if not values:
            return CounterfactualValidationStatus.UNEVALUABLE, "ASSERTION_UNEVALUABLE"
        return CounterfactualValidationStatus.PASS, "OK"

    raise ValueError("unknown trajectory assertion")


def _check_trajectory_assertions(pair: CounterfactualPair):
    unevaluable = False
    for assertion in sorted(pair.matrix.trajectory_assertions):
        status, reason_code = _evaluate_assertion(pair, assertion)
        if status is CounterfactualValidationStatus.FAIL:
            return status, reason_code
        if status is CounterfactualValidationStatus.UNEVALUABLE:
            unevaluable = True
    if unevaluable:
        return CounterfactualValidationStatus.UNEVALUABLE, "ASSERTION_UNEVALUABLE"
    return CounterfactualValidationStatus.PASS, "OK"


def validate_counterfactual_pair(
    pair: CounterfactualPair,
) -> CounterfactualValidationReport:
    """Validate a hidden pair and return aggregate-only causal evidence."""

    if not isinstance(pair, CounterfactualPair):
        raise TypeError("pair must be a CounterfactualPair")
    checks = tuple(
        _check(name, evaluator)
        for name, evaluator in (
            ("shared_patient", lambda: _check_shared_patient(pair)),
            ("shared_age_state", lambda: _check_shared_age_state(pair)),
            ("shared_latent_state", lambda: _check_shared_latent_state(pair)),
            ("stream_reuse", lambda: _check_stream_reuse(pair)),
            ("event_order", lambda: _check_event_order(pair)),
            ("age_coverage", lambda: _check_age_coverage(pair)),
            ("invariant_layers", lambda: _check_invariant_layers(pair)),
            ("permitted_changes", lambda: _check_permitted_changes(pair)),
            ("trajectory_assertions", lambda: _check_trajectory_assertions(pair)),
        )
    )
    return CounterfactualValidationReport(_status_for_checks(checks), checks)


class _TransformedModule:
    """Evaluator-only module wrapper with no sampling side effects."""

    def __init__(self, module: Any) -> None:
        self._module = module
        self.kind = module.kind
        self.module_version = module.module_version

    def sample_state(self, patient: PatientState, streams: Any) -> LatentDisorderState:
        return self._module.sample_state(patient, streams)

    def height_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
        return self._module.height_z_delta(state, age_days)

    def bmi_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
        return self._module.bmi_z_delta(state, age_days)

    def events(
        self,
        patient: PatientState,
        state: LatentDisorderState,
    ) -> tuple[ClinicalEvent, ...]:
        return tuple(self._module.events(patient, state))


class _SeverityModule(_TransformedModule):
    def height_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
        return self._module.height_z_delta(state, age_days) * _PHYSIOLOGY_SEVERITY_SCALE

    def bmi_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
        return self._module.bmi_z_delta(state, age_days) * _PHYSIOLOGY_SEVERITY_SCALE


class _EarlierRecognitionModule(_TransformedModule):
    def events(
        self,
        patient: PatientState,
        state: LatentDisorderState,
    ) -> tuple[ClinicalEvent, ...]:
        events = list(super().events(patient, state))
        recognition_index = next(
            (
                index
                for index, event in enumerate(events)
                if event.event_type == "recognition_opportunity"
            ),
            None,
        )
        if recognition_index is None:
            return tuple(events)
        original = events[recognition_index]
        previous_ages = [
            event.age_days
            for event in events[:recognition_index]
            if _EVENT_PHASE_ORDER.get(event.event_type, -1)
            < _EVENT_PHASE_ORDER["recognition_opportunity"]
        ]
        lower_bound = max(previous_ages, default=0)
        earlier_age = max(lower_bound, original.age_days - _EARLIER_RECOGNITION_SHIFT_DAYS)
        events[recognition_index] = dataclasses.replace(original, age_days=earlier_age)
        return tuple(
            sorted(
                events,
                key=lambda event: (
                    event.age_days,
                    _EVENT_PHASE_ORDER.get(event.event_type, len(_EVENT_PHASE_ORDER)),
                ),
            )
        )


def _intervention_module(module: Any, intervention: InterventionKind) -> Any:
    if intervention is InterventionKind.PHYSIOLOGY_SEVERITY:
        return _SeverityModule(module)
    if intervention is InterventionKind.EARLIER_RECOGNITION:
        return _EarlierRecognitionModule(module)
    if intervention is InterventionKind.TREATMENT_ADHERENCE:
        return module
    raise ValueError("intervention is not supported by trajectory replay")


def _coerce_intervention(value: object) -> InterventionKind:
    if isinstance(value, InterventionKind):
        return value
    try:
        return InterventionKind(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("intervention must be a declared intervention token") from exc


def _resolve_matrix(
    intervention: object,
    matrix: CounterfactualChangeMatrix | None,
) -> CounterfactualChangeMatrix:
    if isinstance(intervention, CounterfactualChangeMatrix):
        if matrix is not None:
            raise ValueError("intervention matrix was supplied twice")
        matrix = intervention
        intervention = matrix.intervention
    if matrix is None:
        if intervention is None:
            raise ValueError("intervention must be supplied")
        return default_change_matrix(_coerce_intervention(intervention))
    if not isinstance(matrix, CounterfactualChangeMatrix):
        raise TypeError("matrix must be a CounterfactualChangeMatrix")
    if intervention is not None and _coerce_intervention(intervention) is not matrix.intervention:
        raise ValueError("intervention does not match the change matrix")
    _validate_not_weaker(matrix)
    return matrix


def generate_counterfactual_pair(
    kernel: AgeRegimeDisorderKernel,
    patient: PatientState,
    ages_days: tuple[int, ...],
    run_seed: int,
    patient_index: int,
    intervention: InterventionKind | CounterfactualChangeMatrix | str | None = None,
    *,
    matrix: CounterfactualChangeMatrix | None = None,
) -> CounterfactualPair:
    """Build one paired fictional trajectory using one shared hidden state."""

    if not isinstance(kernel, AgeRegimeDisorderKernel):
        raise TypeError("kernel must be an AgeRegimeDisorderKernel")
    if not isinstance(ages_days, tuple):
        raise TypeError("ages_days must be a tuple")
    resolved_matrix = _resolve_matrix(intervention, matrix)
    baseline_context = CounterfactualContext(
        patient, run_seed, patient_index, "baseline", resolved_matrix
    )
    intervention_context = CounterfactualContext(
        patient, run_seed, patient_index, "intervention", resolved_matrix
    )

    age_state, disorder_state = kernel.sample_state(patient, baseline_context)
    shared_state = (age_state, disorder_state)
    baseline = kernel.generate(
        patient,
        ages_days,
        baseline_context,
        state=shared_state,
    )

    intervention_disorder_state = disorder_state
    if (
        resolved_matrix.intervention is InterventionKind.TREATMENT_ADHERENCE
        and disorder_state.treatment_start_age_days is not None
    ):
        treatment_response = 0.0 if disorder_state.treatment_response > 0 else 1.0
        intervention_disorder_state = dataclasses.replace(
            disorder_state,
            treatment_response=treatment_response,
        )

    intervention_kernel = AgeRegimeDisorderKernel(
        kernel.physiology,
        _intervention_module(kernel.module, resolved_matrix.intervention),
    )
    intervention = intervention_kernel.generate(
        patient,
        ages_days,
        intervention_context,
        state=(age_state, intervention_disorder_state),
    )
    pair = CounterfactualPair(
        baseline=baseline,
        intervention=intervention,
        baseline_context=baseline_context,
        intervention_context=intervention_context,
        matrix=resolved_matrix,
    )
    report = validate_counterfactual_pair(pair)
    if report.status is CounterfactualValidationStatus.FAIL:
        raise ValueError("generated counterfactual pair failed causal validation")
    return pair
