from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from synthetic.models import PatientState
from synthetic.native.age_regime_disorder import AgeRegimeDisorderKernel
from synthetic.native.age_regimes import AgeRegimeTrajectoryKernel
from synthetic.native.ancillary import GHD_ANCILLARY_RESOURCE_NAMES, GhdAncillaryPolicy
from synthetic.native.clinical_modules import (
    FamilialShortStatureConfig,
    FamilialShortStatureModule,
    GrowthHormoneDeficiencyConfig,
    GrowthHormoneDeficiencyModule,
)
from synthetic.native.counterfactual import (
    CounterfactualValidationStatus,
    InterventionKind,
    generate_counterfactual_pair,
    validate_counterfactual_pair,
)
from synthetic.native.counterfactual_worlds import (
    CounterfactualEhrWorldPair,
    CounterfactualWorldUnavailable,
    assemble_counterfactual_ehr_worlds,
)
from synthetic.native.observations import ObservationPolicy
from synthetic.native.resources import BASE_RESOURCE_NAMES, SyntheticDemographics
from tests.synthetic.fakes import RegimeLinearTestReference

ROOT = Path(__file__).resolve().parents[2]
PATIENT = PatientState("syn-counterfactual-world", "F", "F")
AGES = (0, 365, 730, 900, 1000, 1500, 2500, 4000)


def _descriptor() -> dict[str, object]:
    return json.loads((ROOT / "datapackage.json").read_text(encoding="utf-8"))


def _kernel() -> AgeRegimeDisorderKernel:
    return AgeRegimeDisorderKernel(
        AgeRegimeTrajectoryKernel(RegimeLinearTestReference()),
        GrowthHormoneDeficiencyModule(
            GrowthHormoneDeficiencyConfig(
                onset_min_age_days=730,
                onset_max_age_days=730,
                severity_min=1.0,
                severity_max=1.0,
                progression_days=730,
                phenotype_delay_days=90,
                recognition_delay_days=90,
                workup_delay_days=30,
                diagnosis_delay_days=30,
                treatment_probability=1.0,
                treatment_delay_days=30,
                response_days=365,
                treatment_response_min=0.8,
                treatment_response_max=0.8,
            )
        ),
    )


def _pair(intervention: InterventionKind):
    return _pair_from(_kernel(), intervention)


def _pair_from(kernel: AgeRegimeDisorderKernel, intervention: InterventionKind):
    pair = generate_counterfactual_pair(kernel, PATIENT, AGES, 20260831, 11, intervention)
    assert validate_counterfactual_pair(pair).status is CounterfactualValidationStatus.PASS
    return pair


def _familial_kernel() -> AgeRegimeDisorderKernel:
    return AgeRegimeDisorderKernel(
        AgeRegimeTrajectoryKernel(RegimeLinearTestReference()),
        FamilialShortStatureModule(
            FamilialShortStatureConfig(
                severity_min=1.0,
                severity_max=1.0,
                phenotype_age_days=730,
                recognition_age_days=1460,
                workup_age_days=1825,
                diagnosis_age_days=2190,
            )
        ),
    )


def _policy() -> ObservationPolicy:
    return ObservationPolicy(
        "counterfactual-world-observation-v1",
        0,
        5000,
        visit_probability=1.0,
        length_availability_probability=0.0,
        height_availability_probability=1.0,
        weight_availability_probability=1.0,
        head_circumference_availability_probability=1.0,
        recognition_probability=1.0,
        diagnosis_probability=1.0,
    )


def _ancillary_policy() -> GhdAncillaryPolicy:
    return GhdAncillaryPolicy("counterfactual-world-ghd-v1", "1", 7)


@pytest.mark.parametrize(
    "intervention",
    (
        InterventionKind.PHYSIOLOGY_SEVERITY,
        InterventionKind.EARLIER_RECOGNITION,
        InterventionKind.TREATMENT_ADHERENCE,
    ),
)
def test_assemble_replays_one_shared_observation_process_into_fresh_six_resource_worlds(
    intervention: InterventionKind,
) -> None:
    pair = _pair(intervention)
    demographics = SyntheticDemographics(PATIENT.patient_id, "F")
    descriptor = _descriptor()
    before = (pair, demographics, _policy(), json.loads(json.dumps(descriptor)))

    worlds = assemble_counterfactual_ehr_worlds(
        pair, demographics, _policy(), descriptor, _ancillary_policy()
    )
    replay = assemble_counterfactual_ehr_worlds(
        pair, demographics, _policy(), descriptor, _ancillary_policy()
    )

    assert isinstance(worlds, CounterfactualEhrWorldPair)
    assert worlds is not replay
    assert worlds.to_mapping() == replay.to_mapping()
    assert worlds.baseline is not replay.baseline
    assert worlds.baseline.bundle is not replay.baseline.bundle
    assert worlds.baseline.demographics == worlds.intervention.demographics == demographics
    assert tuple(worlds.baseline.bundle.rows) == BASE_RESOURCE_NAMES  # type: ignore[union-attr]
    assert worlds.baseline.bundle.source_frame is worlds.baseline.frame  # type: ignore[union-attr]
    assert worlds.intervention.bundle.source_frame is worlds.intervention.frame  # type: ignore[union-attr]
    assert worlds.baseline.bundle.shape == worlds.shape  # type: ignore[union-attr]
    assert worlds.intervention.bundle.shape == worlds.shape  # type: ignore[union-attr]
    assert pair == before[0]
    assert demographics == before[1]
    assert descriptor == before[3]
    assert repr(worlds) == "CounterfactualEhrWorldPair(<evaluator-only>)"
    rendered = repr(worlds) + json.dumps(worlds.to_mapping(), sort_keys=True)
    assert "truth" not in rendered
    assert "run_seed" not in rendered


def test_assemble_composes_empty_or_partial_ancillary_resources_only_from_visible_events() -> None:
    pair = _pair(InterventionKind.EARLIER_RECOGNITION)
    worlds = assemble_counterfactual_ehr_worlds(
        pair,
        SyntheticDemographics(PATIENT.patient_id, "F"),
        _policy(),
        _descriptor(),
        _ancillary_policy(),
    )
    baseline_rows = worlds.baseline.bundle.rows  # type: ignore[union-attr]
    intervention_rows = worlds.intervention.bundle.rows  # type: ignore[union-attr]
    assert any(baseline_rows[name] for name in GHD_ANCILLARY_RESOURCE_NAMES)
    assert any(intervention_rows[name] for name in GHD_ANCILLARY_RESOURCE_NAMES)
    assert all(
        row.to_mapping().get("visit_id", "") in {
            visit.to_mapping()["visit_id"] for visit in worlds.baseline.bundle.rows["visits"]  # type: ignore[union-attr]
        }
        for name in GHD_ANCILLARY_RESOURCE_NAMES
        for row in baseline_rows[name]
        if row.to_mapping().get("visit_id", "")
    )


def test_assemble_preserves_empty_ancillary_resources_for_unrecognized_and_non_ghd_worlds() -> None:
    unrecognized = assemble_counterfactual_ehr_worlds(
        _pair(InterventionKind.PHYSIOLOGY_SEVERITY),
        SyntheticDemographics(PATIENT.patient_id, "F"),
        dataclasses.replace(_policy(), recognition_probability=0.0, diagnosis_probability=0.0),
        _descriptor(),
        _ancillary_policy(),
    )
    non_ghd = assemble_counterfactual_ehr_worlds(
        _pair_from(_familial_kernel(), InterventionKind.EARLIER_RECOGNITION),
        SyntheticDemographics(PATIENT.patient_id, "F"),
        _policy(),
        _descriptor(),
        _ancillary_policy(),
    )

    for worlds in (unrecognized, non_ghd):
        for member in (worlds.baseline, worlds.intervention):
            assert all(not member.bundle.rows[name] for name in GHD_ANCILLARY_RESOURCE_NAMES)  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "intervention",
    (InterventionKind.UTILIZATION_INTENSITY, InterventionKind.MEASUREMENT_ERROR_REMOVAL),
)
def test_assemble_rejects_deferred_interventions_at_a_fixed_redacted_boundary(
    intervention: InterventionKind,
) -> None:
    # The trajectory constructor rejects deferred kinds, so a valid supported
    # pair is deliberately relabelled to exercise the world-assembly guard.
    pair = _pair(InterventionKind.PHYSIOLOGY_SEVERITY)
    original = pair.matrix.intervention
    object.__setattr__(pair.matrix, "intervention", intervention)
    try:
        with pytest.raises(
            CounterfactualWorldUnavailable, match=r"^counterfactual EHR worlds unavailable$"
        ) as error:
            assemble_counterfactual_ehr_worlds(
                pair,
                SyntheticDemographics(PATIENT.patient_id, "F"),
                _policy(),
                _descriptor(),
                _ancillary_policy(),
            )
    finally:
        object.__setattr__(pair.matrix, "intervention", original)
    assert PATIENT.patient_id not in str(error.value)


def test_assemble_rejects_observed_length_and_mismatched_demographics_without_leaking_inputs() -> None:
    pair = _pair(InterventionKind.PHYSIOLOGY_SEVERITY)
    length_policy = dataclasses.replace(_policy(), length_availability_probability=1.0)

    for demographics, policy in (
        (SyntheticDemographics("syn-other-world", "F"), _policy()),
        (SyntheticDemographics(PATIENT.patient_id, "F"), length_policy),
    ):
        with pytest.raises(
            CounterfactualWorldUnavailable, match=r"^counterfactual EHR worlds unavailable$"
        ) as error:
            assemble_counterfactual_ehr_worlds(
                pair, demographics, policy, _descriptor(), _ancillary_policy()
            )
        assert "syn-other-world" not in str(error.value)
