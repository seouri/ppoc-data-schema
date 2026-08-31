import dataclasses
import re

import pytest

from synthetic.models import (
    AgeRegimeDisorderTrajectory,
    AgeRegimePoint,
    AgeRegimeState,
    AgeRegimeTrajectory,
    DisorderKind,
    GrowthRegime,
    LatentDisorderState,
    PatientState,
)
from synthetic.native.counterfactual import (
    DEFAULT_CHANGE_MATRICES,
    CausalLayer,
    CounterfactualChangeMatrix,
    CounterfactualContext,
    CounterfactualPair,
    InterventionKind,
    canonical_hidden_hash,
    default_change_matrix,
)

PATIENT = PatientState("syn-patient-a", "F", "F")


def _trajectory(patient_id: str = PATIENT.patient_id) -> AgeRegimeDisorderTrajectory:
    point = AgeRegimePoint(
        patient_id=patient_id,
        age_days=365,
        regime=GrowthRegime.INFANCY,
        length_cm=75.0,
        height_cm=None,
        weight_kg=9.0,
        bmi=None,
        length_z=0.1,
        weight_z=0.2,
    )
    state = AgeRegimeState(
        module_version="age-regimes-v1",
        birth_length_z=0.1,
        birth_weight_z=0.2,
        head_circumference_z=0.0,
        childhood_height_z=0.1,
        childhood_bmi_z=0.2,
        puberty_onset_age_days=4380,
        puberty_tempo_days=900,
        puberty_height_spurt_z=0.0,
        puberty_bmi_shift_z=0.0,
    )
    return AgeRegimeDisorderTrajectory(
        physiology=AgeRegimeTrajectory((point,), state),
        disorder=LatentDisorderState(DisorderKind.HEALTHY, None, 0.0),
        events=(),
    )


def test_fixed_interventions_distinguish_supported_trajectory_scope() -> None:
    assert {kind.value for kind in InterventionKind} == {
        "physiology_severity",
        "earlier_recognition",
        "treatment_adherence",
        "utilization_intensity",
        "measurement_error_removal",
    }
    assert set(DEFAULT_CHANGE_MATRICES) == {
        InterventionKind.PHYSIOLOGY_SEVERITY,
        InterventionKind.EARLIER_RECOGNITION,
        InterventionKind.TREATMENT_ADHERENCE,
    }


@pytest.mark.parametrize(
    "intervention",
    [
        InterventionKind.UTILIZATION_INTENSITY,
        InterventionKind.MEASUREMENT_ERROR_REMOVAL,
    ],
)
def test_default_matrix_rejects_interventions_that_require_visible_resources(
    intervention: InterventionKind,
) -> None:
    with pytest.raises(ValueError, match="not supported by trajectory replay"):
        default_change_matrix(intervention)


def test_default_matrices_encode_the_reviewed_causal_layer_contract() -> None:
    severity = default_change_matrix(InterventionKind.PHYSIOLOGY_SEVERITY)
    assert severity.manipulated_nodes == frozenset({CausalLayer.GROWTH_PHYSIOLOGY})
    assert severity.permitted_descendants == frozenset()
    assert severity.required_invariants == frozenset(
        {
            CausalLayer.AGE_REGIME,
            CausalLayer.LATENT_DISORDER,
            CausalLayer.RECOGNITION,
            CausalLayer.TREATMENT,
        }
    )

    recognition = default_change_matrix(InterventionKind.EARLIER_RECOGNITION)
    assert recognition.manipulated_nodes == frozenset({CausalLayer.RECOGNITION})
    assert recognition.permitted_descendants == frozenset({CausalLayer.EVENT_TRACE})
    assert recognition.required_invariants == frozenset(
        {
            CausalLayer.AGE_REGIME,
            CausalLayer.LATENT_DISORDER,
            CausalLayer.GROWTH_PHYSIOLOGY,
            CausalLayer.TREATMENT,
        }
    )

    adherence = default_change_matrix(InterventionKind.TREATMENT_ADHERENCE)
    assert adherence.manipulated_nodes == frozenset({CausalLayer.TREATMENT})
    assert adherence.permitted_descendants == frozenset({CausalLayer.GROWTH_PHYSIOLOGY})
    assert adherence.required_invariants == frozenset(
        {
            CausalLayer.AGE_REGIME,
            CausalLayer.LATENT_DISORDER,
            CausalLayer.RECOGNITION,
        }
    )


def test_matrix_construction_rejects_intervention_incompatible_descendants() -> None:
    severity = default_change_matrix(InterventionKind.PHYSIOLOGY_SEVERITY)
    with pytest.raises(ValueError, match="permitted_descendants"):
        dataclasses.replace(severity, permitted_descendants=frozenset({CausalLayer.EVENT_TRACE}))

    recognition = default_change_matrix(InterventionKind.EARLIER_RECOGNITION)
    with pytest.raises(ValueError, match="assertion"):
        dataclasses.replace(
            recognition,
            trajectory_assertions=frozenset({"post_treatment_growth_may_change"}),
        )

    adherence = default_change_matrix(InterventionKind.TREATMENT_ADHERENCE)
    with pytest.raises(ValueError, match="permitted_descendants"):
        dataclasses.replace(adherence, permitted_descendants=frozenset())


def test_matrix_construction_rejects_missing_fixed_assertions() -> None:
    base = default_change_matrix(InterventionKind.PHYSIOLOGY_SEVERITY)
    with pytest.raises(ValueError, match="assertions"):
        dataclasses.replace(base, trajectory_assertions=frozenset({"growth_z_differs"}))


@pytest.mark.parametrize(
    ("intervention", "incompatible"),
    [
        (InterventionKind.PHYSIOLOGY_SEVERITY, "growth_z_invariant"),
        (InterventionKind.EARLIER_RECOGNITION, "growth_z_differs"),
        (InterventionKind.TREATMENT_ADHERENCE, "growth_z_differs"),
    ],
)
def test_matrix_rejects_intervention_incompatible_extra_assertions(
    intervention: InterventionKind, incompatible: str
) -> None:
    base = default_change_matrix(intervention)
    with pytest.raises(ValueError, match="assertion"):
        dataclasses.replace(
            base,
            trajectory_assertions=base.trajectory_assertions | {incompatible},
        )


def test_matrix_requires_enum_nodes_frozensets_and_disjoint_causal_sets() -> None:
    base = default_change_matrix(InterventionKind.PHYSIOLOGY_SEVERITY)

    with pytest.raises(TypeError, match="frozenset"):
        dataclasses.replace(base, manipulated_nodes=(CausalLayer.GROWTH_PHYSIOLOGY,))
    with pytest.raises(ValueError, match="CausalLayer"):
        dataclasses.replace(base, manipulated_nodes=frozenset({"growth_physiology"}))
    with pytest.raises(ValueError, match="disjoint"):
        dataclasses.replace(
            base,
            required_invariants=base.required_invariants
            | frozenset({CausalLayer.GROWTH_PHYSIOLOGY}),
        )
    with pytest.raises(ValueError, match="token"):
        dataclasses.replace(base, version="../../matrix.json")


def test_matrix_mapping_rejects_duplicate_values_and_unknown_keys() -> None:
    mapping = default_change_matrix(InterventionKind.EARLIER_RECOGNITION).to_mapping()
    mapping["manipulated_nodes"] = ["recognition", "recognition"]
    with pytest.raises(ValueError, match="duplicate"):
        CounterfactualChangeMatrix.from_mapping(mapping)

    mapping = default_change_matrix(InterventionKind.EARLIER_RECOGNITION).to_mapping()
    mapping["unexpected"] = []
    with pytest.raises(ValueError, match="keys"):
        CounterfactualChangeMatrix.from_mapping(mapping)

    mapping = default_change_matrix(InterventionKind.EARLIER_RECOGNITION).to_mapping()
    mapping["required_invariants"] = ["age_regime", "unknown_layer"]
    with pytest.raises(ValueError, match="CausalLayer"):
        CounterfactualChangeMatrix.from_mapping(mapping)


def test_matrix_rejects_unknown_or_resampled_streams() -> None:
    base = default_change_matrix(InterventionKind.PHYSIOLOGY_SEVERITY)
    with pytest.raises(ValueError, match="declared native stream"):
        dataclasses.replace(base, reused_streams=frozenset({"../../patient.csv"}))
    with pytest.raises(ValueError, match="resampling"):
        dataclasses.replace(
            base,
            reused_streams=base.reused_streams - {"regime.birth"},
            resampled_streams=frozenset({"regime.birth"}),
        )


def test_context_is_immutable_and_requires_a_fictional_patient() -> None:
    matrix = default_change_matrix(InterventionKind.PHYSIOLOGY_SEVERITY)
    context = CounterfactualContext(PATIENT, 20260831, 7, "baseline", matrix)

    with pytest.raises(dataclasses.FrozenInstanceError):
        context.run_seed = 1  # type: ignore[misc]
    with pytest.raises(ValueError, match="fictional synthetic patient"):
        CounterfactualContext(
            PatientState("/real/patient.csv", "F", "F"),
            20260831,
            7,
            "baseline",
            matrix,
        )
    with pytest.raises(ValueError, match="world"):
        CounterfactualContext(PATIENT, 20260831, 7, "../baseline", matrix)


def test_matrix_rejects_a_matrix_that_weakens_fixed_semantics() -> None:
    base = default_change_matrix(InterventionKind.PHYSIOLOGY_SEVERITY)
    with pytest.raises(ValueError, match="required_invariants"):
        dataclasses.replace(
            base,
            required_invariants=base.required_invariants - {CausalLayer.TREATMENT},
        )


def test_context_replays_declared_streams_with_world_independent_identities() -> None:
    matrix = default_change_matrix(InterventionKind.TREATMENT_ADHERENCE)
    baseline = CounterfactualContext(PATIENT, 20260831, 7, "baseline", matrix)
    intervention = CounterfactualContext(PATIENT, 20260831, 7, "intervention", matrix)

    baseline_values = baseline.generator("regime.birth").normal(size=4)
    intervention_values = intervention.generator("regime.birth").normal(size=4)
    assert baseline_values.tolist() == intervention_values.tolist()
    assert baseline.stream_identity("regime.birth") == intervention.stream_identity("regime.birth")
    assert re.fullmatch(r"[0-9a-f]{64}", baseline.stream_identity("regime.birth"))
    with pytest.raises(ValueError, match="declared by the matrix"):
        baseline.generator("patient.csv")


def test_context_repr_and_mapping_exclude_patient_seed_and_stream_identities() -> None:
    matrix = default_change_matrix(InterventionKind.PHYSIOLOGY_SEVERITY)
    context = CounterfactualContext(PATIENT, 20260831, 7, "baseline", matrix)

    representation = repr(context)
    mapping = context.to_mapping()
    assert PATIENT.patient_id not in representation
    assert "20260831" not in representation
    assert PATIENT.patient_id not in str(mapping)
    assert "run_seed" not in mapping
    assert "patient_index" not in mapping
    assert "stream_identities" not in mapping


def test_pair_is_immutable_and_excludes_hidden_trajectories_from_repr_and_mapping() -> None:
    matrix = default_change_matrix(InterventionKind.PHYSIOLOGY_SEVERITY)
    baseline_context = CounterfactualContext(PATIENT, 20260831, 7, "baseline", matrix)
    intervention_context = CounterfactualContext(PATIENT, 20260831, 7, "intervention", matrix)
    trajectory = _trajectory()
    pair = CounterfactualPair(
        baseline=trajectory,
        intervention=trajectory,
        baseline_context=baseline_context,
        intervention_context=intervention_context,
        matrix=matrix,
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        pair.baseline = _trajectory()  # type: ignore[misc]
    assert PATIENT.patient_id not in repr(pair)
    assert PATIENT.patient_id not in str(pair.to_mapping())
    assert "baseline" not in pair.to_mapping()
    assert "intervention_trajectory" not in pair.to_mapping()


def test_pair_rejects_patient_or_context_mismatch_without_echoing_identifiers() -> None:
    matrix = default_change_matrix(InterventionKind.PHYSIOLOGY_SEVERITY)
    baseline_context = CounterfactualContext(PATIENT, 20260831, 7, "baseline", matrix)
    intervention_context = CounterfactualContext(PATIENT, 20260831, 7, "intervention", matrix)

    with pytest.raises(ValueError, match="one synthetic patient") as error:
        CounterfactualPair(
            baseline=_trajectory(),
            intervention=_trajectory("syn-patient-b"),
            baseline_context=baseline_context,
            intervention_context=intervention_context,
            matrix=matrix,
        )
    assert PATIENT.patient_id not in str(error.value)


def test_pair_requires_shared_age_regime_and_latent_disorder_states() -> None:
    matrix = default_change_matrix(InterventionKind.PHYSIOLOGY_SEVERITY)
    baseline_context = CounterfactualContext(PATIENT, 20260831, 7, "baseline", matrix)
    intervention_context = CounterfactualContext(PATIENT, 20260831, 7, "intervention", matrix)
    baseline = _trajectory()
    different_state = dataclasses.replace(
        baseline.physiology,
        state=dataclasses.replace(baseline.physiology.state, childhood_height_z=0.9),
    )
    with pytest.raises(ValueError, match="age-regime state"):
        CounterfactualPair(
            baseline=baseline,
            intervention=dataclasses.replace(baseline, physiology=different_state),
            baseline_context=baseline_context,
            intervention_context=intervention_context,
            matrix=matrix,
        )

    different_disorder = dataclasses.replace(
        baseline,
        disorder=LatentDisorderState(DisorderKind.FAMILIAL_SHORT_STATURE, 100, 0.5),
    )
    with pytest.raises(ValueError, match="latent disorder state"):
        CounterfactualPair(
            baseline=baseline,
            intervention=different_disorder,
            baseline_context=baseline_context,
            intervention_context=intervention_context,
            matrix=matrix,
        )


def test_hidden_hash_is_canonical_and_does_not_embed_patient_data() -> None:
    left = {"z": (0.1, 0.2), "layer": CausalLayer.GROWTH_PHYSIOLOGY}
    right = {"layer": CausalLayer.GROWTH_PHYSIOLOGY, "z": (0.1, 0.2)}

    digest = canonical_hidden_hash(left)
    assert digest == canonical_hidden_hash(right)
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert "growth_physiology" not in digest
