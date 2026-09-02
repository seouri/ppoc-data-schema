from __future__ import annotations

import math
from dataclasses import FrozenInstanceError

import pytest

from synthetic.models import DisorderKind, LatentDisorderState, PatientState
from synthetic.native.age_regime_disorder import AgeRegimeDisorderKernel
from synthetic.native.age_regimes import AgeRegimeConfig, AgeRegimeTrajectoryKernel
from synthetic.native.clinical_modules import (
    UndernutritionConfig,
    UndernutritionModule,
)
from synthetic.randomness import NamedRandomStreams
from tests.synthetic.fakes import RegimeLinearTestReference

PATIENT = PatientState("syn-patient-undernutrition", "F", "F")


def test_undernutrition_samples_reproducibly_from_its_scoped_stream() -> None:
    module = UndernutritionModule()
    first = module.sample_state(PATIENT, NamedRandomStreams(20260902, 8))
    second = module.sample_state(PATIENT, NamedRandomStreams(20260902, 8))

    assert first == second
    assert first.kind is DisorderKind.UNDERNUTRITION
    assert module.config.onset_min_age_days <= first.onset_age_days <= module.config.onset_max_age_days  # type: ignore[operator]


def test_undernutrition_weight_decline_precedes_height_decline_without_treatment() -> None:
    config = UndernutritionConfig(
        onset_min_age_days=1000,
        onset_max_age_days=1000,
        severity_min=1.0,
        severity_max=1.0,
        treatment_probability=0.0,
    )
    module = UndernutritionModule(config)
    state = module.sample_state(PATIENT, NamedRandomStreams(7, 0))
    onset = state.onset_age_days
    assert onset == 1000
    assert module.bmi_z_delta(state, onset) == 0.0  # type: ignore[operator]
    assert module.height_z_delta(state, onset + config.height_onset_delay_days - 1) == 0.0  # type: ignore[operator]
    assert module.bmi_z_delta(state, onset + 1) < 0  # type: ignore[operator]
    assert module.height_z_delta(state, onset + config.height_onset_delay_days) == 0.0  # type: ignore[operator]
    assert module.height_z_delta(state, onset + config.height_onset_delay_days + 1) < 0  # type: ignore[operator]
    assert module.bmi_z_delta(state, onset + config.weight_progression_days) == pytest.approx(
        -config.weight_z_max_delta
    )  # type: ignore[operator]
    assert [event.event_type for event in module.events(PATIENT, state)] == [
        "latent_onset",
        "observable_phenotype",
        "recognition_opportunity",
        "workup",
        "recorded_diagnosis",
    ]


def test_treated_undernutrition_preserves_pre_treatment_effects_and_partially_recovers() -> None:
    config = UndernutritionConfig(
        onset_min_age_days=1000,
        onset_max_age_days=1000,
        severity_min=1.0,
        severity_max=1.0,
        treatment_probability=1.0,
        treatment_response_min=0.6,
        treatment_response_max=0.6,
    )
    module = UndernutritionModule(config)
    treated = module.sample_state(PATIENT, NamedRandomStreams(8, 0))
    untreated = LatentDisorderState(
        DisorderKind.UNDERNUTRITION,
        treated.onset_age_days,
        treated.severity,
    )

    treatment_start = treated.treatment_start_age_days
    assert treatment_start == 1300
    assert treatment_start is not None
    before_treatment = treatment_start - 1
    assert module.height_z_delta(treated, before_treatment) == pytest.approx(
        module.height_z_delta(untreated, before_treatment)
    )
    assert module.bmi_z_delta(treated, before_treatment) == pytest.approx(
        module.bmi_z_delta(untreated, before_treatment)
    )
    response_age = treatment_start + config.response_days
    assert module.height_z_delta(treated, response_age) > module.height_z_delta(
        untreated, response_age
    )
    assert module.bmi_z_delta(treated, response_age) > module.bmi_z_delta(
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
    module = UndernutritionModule(
        UndernutritionConfig(
            onset_min_age_days=1000,
            onset_max_age_days=1000,
            treatment_probability=1.0,
            treatment_response_min=0.0,
            treatment_response_max=0.0,
        )
    )
    state = module.sample_state(PATIENT, NamedRandomStreams(9, 0))
    assert state.treatment_start_age_days is not None
    assert [event.event_type for event in module.events(PATIENT, state)][-1] == (
        "treatment_nonresponse"
    )


@pytest.mark.parametrize(
    "operation",
    [
        lambda module: module.height_z_delta(
            LatentDisorderState(DisorderKind.UNDERNUTRITION, 0, 0.8), 0
        ),
        lambda module: module.bmi_z_delta(
            LatentDisorderState(DisorderKind.UNDERNUTRITION, None, 0.8), 0
        ),
        lambda module: module.events(
            PATIENT,
            LatentDisorderState(
                DisorderKind.UNDERNUTRITION, 730, 0.8, puberty_delay_days=1
            ),
        ),
    ],
)
def test_undernutrition_rejects_incoherent_state(operation: object) -> None:
    with pytest.raises(ValueError, match="onset|puberty"):
        operation(UndernutritionModule())  # type: ignore[operator]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: UndernutritionConfig(onset_min_age_days=10**1000),
        lambda: UndernutritionConfig(weight_progression_days=0),
        lambda: UndernutritionConfig(height_progression_days=0),
        lambda: UndernutritionConfig(severity_min=math.nan),
        lambda: UndernutritionConfig(treatment_probability=1.1),
        lambda: UndernutritionConfig(
            treatment_response_min=0.9, treatment_response_max=0.8
        ),
        lambda: UndernutritionConfig(weight_z_max_delta=-0.1),
    ],
)
def test_undernutrition_config_rejects_invalid_values(factory: object) -> None:
    with pytest.raises(ValueError):
        factory()


def test_undernutrition_config_is_frozen_and_versioned() -> None:
    config = UndernutritionConfig()
    assert config.module_version == "undernutrition-v1"
    with pytest.raises(FrozenInstanceError):
        config.weight_progression_days = 30  # type: ignore[misc]


def test_undernutrition_constructor_rejects_config_version_drift() -> None:
    config = UndernutritionConfig()
    object.__setattr__(config, "module_version", "undernutrition-v999")
    with pytest.raises(ValueError, match="version"):
        UndernutritionModule(config)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("severity", -1.0),
        ("onset_age_days", "not-an-age"),
        ("treatment_response", 2.0),
        ("treatment_start_age_days", 1400),
    ],
)
def test_undernutrition_revalidates_tampered_state(
    field: str, value: object
) -> None:
    module = UndernutritionModule()
    state = LatentDisorderState(
        DisorderKind.UNDERNUTRITION,
        1000,
        1.0,
        treatment_start_age_days=1300,
        treatment_response=0.6,
    )
    object.__setattr__(state, field, value)

    with pytest.raises(ValueError):
        module.height_z_delta(state, 1500)
    with pytest.raises(ValueError):
        module.bmi_z_delta(state, 1500)
    with pytest.raises(ValueError):
        module.events(PATIENT, state)


def test_undernutrition_rejects_treatment_fields_on_zero_severity_state() -> None:
    module = UndernutritionModule()
    state = LatentDisorderState(
        DisorderKind.UNDERNUTRITION,
        1000,
        0.0,
        treatment_start_age_days=1300,
    )

    with pytest.raises(ValueError, match="zero-severity"):
        module.height_z_delta(state, 1500)
    with pytest.raises(ValueError, match="zero-severity"):
        module.events(PATIENT, state)


def test_age_regime_composition_preserves_undernutrition_weight_identity() -> None:
    config = UndernutritionConfig(
        onset_min_age_days=1000,
        onset_max_age_days=1000,
        severity_min=1.0,
        severity_max=1.0,
        treatment_probability=1.0,
        treatment_response_min=0.6,
        treatment_response_max=0.6,
    )
    module = UndernutritionModule(config)
    physiology = AgeRegimeTrajectoryKernel(
        RegimeLinearTestReference(), AgeRegimeConfig(residual_sd=0.0)
    )
    state = module.sample_state(PATIENT, NamedRandomStreams(11, 0))
    ages = (0, 730, 1000, 1180, 1300, 1665, 3000, 7305)
    physiology_state = physiology.sample_state(NamedRandomStreams(11, 0))
    baseline = physiology.generate(
        PATIENT,
        ages,
        NamedRandomStreams(11, 0),
        state=physiology_state,
    )
    result = AgeRegimeDisorderKernel(physiology, module).generate(
        PATIENT,
        ages,
        NamedRandomStreams(11, 0),
        disorder_state=state,
        physiology_state=physiology_state,
    )

    assert result.disorder == state
    assert result.events[-1].event_type == "treatment_response"
    assert result.physiology.points[2].bmi_z == pytest.approx(
        baseline.points[2].bmi_z
    )
    assert result.physiology.points[3].bmi_z < result.physiology.points[2].bmi_z
    assert result.physiology.points[3].bmi_z < baseline.points[3].bmi_z
    assert result.physiology.points[3].height_z == pytest.approx(
        baseline.points[3].height_z
    )
    assert all(
        point.weight_kg == pytest.approx(point.bmi * (point.height_cm / 100) ** 2)
        for point in result.physiology.points[2:]
    )
