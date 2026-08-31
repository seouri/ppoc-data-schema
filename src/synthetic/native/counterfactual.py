"""Evaluator-only contracts for paired fictional growth trajectories.

This module intentionally has no visible-resource or package serialization API.
Counterfactual trajectories, patient identity, seeds, and stream identities are
hidden evaluator state.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

import numpy as np

from synthetic.models import AgeRegimeDisorderTrajectory, PatientState
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
        if not _require_assertions(self.trajectory_assertions):
            raise ValueError("trajectory_assertions must be nonempty")

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
        baseline_patient = _trajectory_patient_id(self.baseline)
        intervention_patient = _trajectory_patient_id(self.intervention)
        if (
            baseline_patient != intervention_patient
            or self.baseline_context.patient != self.intervention_context.patient
            or baseline_patient != self.baseline_context.patient.patient_id
        ):
            raise ValueError("paired worlds must contain one synthetic patient")
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
