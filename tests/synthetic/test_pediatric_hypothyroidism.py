from __future__ import annotations

import math
from dataclasses import FrozenInstanceError

import pytest

from synthetic.models import DisorderKind, LatentDisorderState, PatientState
from synthetic.native.age_regime_disorder import AgeRegimeDisorderKernel
from synthetic.native.age_regimes import AgeRegimeConfig, AgeRegimeTrajectoryKernel
from synthetic.native.clinical_modules import (
    PediatricHypothyroidismConfig,
    PediatricHypothyroidismModule,
)
from synthetic.randomness import NamedRandomStreams
from tests.synthetic.fakes import RegimeLinearTestReference

PATIENT = PatientState("syn-patient-hypothyroidism", "F", "F")


def test_pediatric_hypothyroidism_samples_onset_and_uses_scoped_stream() -> None:
    module = PediatricHypothyroidismModule()
    first = module.sample_state(PATIENT, NamedRandomStreams(20260902, 3))
    second = module.sample_state(PATIENT, NamedRandomStreams(20260902, 3))

    assert first == second
    assert first.kind is DisorderKind.PEDIATRIC_HYPOTHYROIDISM
    assert module.config.onset_min_age_days <= first.onset_age_days <= module.config.onset_max_age_days  # type: ignore[operator]
    assert module.config.severity_min <= first.severity <= module.config.severity_max


def test_untreated_hypothyroidism_decelerates_height_and_raises_relative_bmi() -> None:
    config = PediatricHypothyroidismConfig(
        onset_min_age_days=1000,
        onset_max_age_days=1000,
        severity_min=1.0,
        severity_max=1.0,
        treatment_probability=0.0,
    )
    module = PediatricHypothyroidismModule(config)
    state = module.sample_state(PATIENT, NamedRandomStreams(7, 0))
    onset = state.onset_age_days
    assert onset == 1000

    assert module.height_z_delta(state, onset - 1) == 0.0  # type: ignore[operator]
    midpoint = module.height_z_delta(state, onset + config.progression_days // 2)  # type: ignore[operator]
    endpoint = module.height_z_delta(state, onset + config.progression_days)  # type: ignore[operator]
    assert endpoint < midpoint < 0
    assert 0 < module.bmi_z_delta(state, onset + config.progression_days) <= config.bmi_z_max_delta
    assert [event.event_type for event in module.events(PATIENT, state)] == [
        "latent_onset",
        "observable_phenotype",
        "recognition_opportunity",
        "workup",
        "recorded_diagnosis",
    ]


def test_treated_hypothyroidism_preserves_pre_treatment_growth_and_recovers_partially() -> None:
    config = PediatricHypothyroidismConfig(
        onset_min_age_days=1000,
        onset_max_age_days=1000,
        severity_min=1.0,
        severity_max=1.0,
        treatment_probability=1.0,
        treatment_response_min=0.6,
        treatment_response_max=0.6,
    )
    module = PediatricHypothyroidismModule(config)
    treated = module.sample_state(PATIENT, NamedRandomStreams(8, 0))
    untreated = LatentDisorderState(
        DisorderKind.PEDIATRIC_HYPOTHYROIDISM,
        treated.onset_age_days,
        treated.severity,
    )

    treatment_start = treated.treatment_start_age_days
    assert treatment_start is not None
    assert treatment_start == 1390
    before_treatment = treatment_start - 1
    assert module.height_z_delta(treated, before_treatment) == pytest.approx(
        module.height_z_delta(untreated, before_treatment)
    )
    response_age = treatment_start + config.response_days
    assert module.height_z_delta(treated, response_age) > module.height_z_delta(
        untreated, response_age
    )
    assert 0 <= module.bmi_z_delta(treated, response_age) < module.bmi_z_delta(
        untreated, response_age
    )
    assert [event.event_type for event in module.events(PATIENT, treated)] == [
        "latent_onset",
        "observable_phenotype",
        "recognition_opportunity",
        "workup",
        "recorded_diagnosis",
        "treatment_start",
        "treatment_response",
    ]


def test_zero_response_is_recorded_as_treatment_nonresponse() -> None:
    module = PediatricHypothyroidismModule(
        PediatricHypothyroidismConfig(
            onset_min_age_days=1000,
            onset_max_age_days=1000,
            treatment_probability=1.0,
            treatment_response_min=0.0,
            treatment_response_max=0.0,
        )
    )
    state = module.sample_state(PATIENT, NamedRandomStreams(9, 0))
    assert state.treatment_start_age_days is not None
    assert state.treatment_response == 0.0
    assert [event.event_type for event in module.events(PATIENT, state)][-1] == (
        "treatment_nonresponse"
    )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: PediatricHypothyroidismConfig(onset_min_age_days=10**1000),
        lambda: PediatricHypothyroidismConfig(progression_days=10**1000),
        lambda: PediatricHypothyroidismConfig(severity_min=math.nan),
        lambda: PediatricHypothyroidismConfig(treatment_probability=1.1),
        lambda: PediatricHypothyroidismConfig(
            treatment_response_min=0.9, treatment_response_max=0.8
        ),
        lambda: PediatricHypothyroidismConfig(
            onset_min_age_days=4000,
            onset_max_age_days=3000,
        ),
    ],
)
def test_pediatric_hypothyroidism_config_rejects_invalid_values(factory: object) -> None:
    with pytest.raises(ValueError):
        factory()


def test_pediatric_hypothyroidism_config_is_frozen_and_versioned() -> None:
    config = PediatricHypothyroidismConfig()
    assert config.module_version == "pediatric-hypothyroidism-v1"
    with pytest.raises(FrozenInstanceError):
        config.progression_days = 30  # type: ignore[misc]


def test_pediatric_hypothyroidism_constructor_rejects_config_version_drift() -> None:
    config = PediatricHypothyroidismConfig()
    object.__setattr__(config, "module_version", "pediatric-hypothyroidism-v999")
    with pytest.raises(ValueError, match="version"):
        PediatricHypothyroidismModule(config)


def test_pediatric_hypothyroidism_rejects_wrong_state_kind() -> None:
    module = PediatricHypothyroidismModule()
    state = LatentDisorderState(DisorderKind.GROWTH_HORMONE_DEFICIENCY, 1000, 0.8)
    with pytest.raises(ValueError, match="state kind"):
        module.height_z_delta(state, 1000)


def test_pediatric_hypothyroidism_rejects_treatment_schedule_drift() -> None:
    module = PediatricHypothyroidismModule(
        PediatricHypothyroidismConfig(
            onset_min_age_days=1000,
            onset_max_age_days=1000,
            treatment_probability=1.0,
        )
    )
    state = LatentDisorderState(
        DisorderKind.PEDIATRIC_HYPOTHYROIDISM,
        1000,
        0.8,
        treatment_start_age_days=1391,
        treatment_response=0.6,
    )
    with pytest.raises(ValueError, match="treatment start"):
        module.events(PATIENT, state)


def test_age_regime_composition_applies_hypothyroidism_once_and_preserves_weight_identity() -> None:
    config = PediatricHypothyroidismConfig(
        onset_min_age_days=1000,
        onset_max_age_days=1000,
        severity_min=1.0,
        severity_max=1.0,
        treatment_probability=1.0,
        treatment_response_min=0.6,
        treatment_response_max=0.6,
    )
    module = PediatricHypothyroidismModule(config)
    physiology = AgeRegimeTrajectoryKernel(
        RegimeLinearTestReference(), AgeRegimeConfig(residual_sd=0.0)
    )
    state = module.sample_state(PATIENT, NamedRandomStreams(11, 0))
    result = AgeRegimeDisorderKernel(physiology, module).generate(
        PATIENT,
        (0, 730, 1000, 1390, 1755, 3000, 7305),
        NamedRandomStreams(11, 0),
        disorder_state=state,
        physiology_state=physiology.sample_state(NamedRandomStreams(11, 0)),
    )

    assert result.disorder == state
    assert result.events[-1].event_type == "treatment_response"
    affected = [point for point in result.physiology.points if point.age_days >= 1000]
    assert affected
    assert all(
        point.weight_kg == pytest.approx(point.bmi * (point.height_cm / 100) ** 2)
        for point in affected
    )
    assert result.physiology.points[3].height_z < result.physiology.points[1].height_z
    assert result.physiology.points[4].height_z > result.physiology.points[3].height_z
