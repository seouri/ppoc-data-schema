from __future__ import annotations

import math
from dataclasses import FrozenInstanceError

import pytest

from synthetic.models import DisorderKind, LatentDisorderState, PatientState
from synthetic.native.age_regime_disorder import AgeRegimeDisorderKernel
from synthetic.native.age_regimes import AgeRegimeConfig, AgeRegimeTrajectoryKernel
from synthetic.native.clinical_modules import ExcessWeightConfig, ExcessWeightModule
from synthetic.randomness import NamedRandomStreams
from tests.synthetic.fakes import RegimeLinearTestReference

PATIENT = PatientState("syn-patient-excess-weight", "F", "F")


def test_excess_weight_samples_reproducibly_from_its_scoped_stream() -> None:
    module = ExcessWeightModule()
    first = module.sample_state(PATIENT, NamedRandomStreams(20260902, 8))
    second = module.sample_state(PATIENT, NamedRandomStreams(20260902, 8))

    assert first == second
    assert first.kind is DisorderKind.EXCESS_WEIGHT
    assert module.config.onset_min_age_days <= first.onset_age_days <= module.config.onset_max_age_days  # type: ignore[operator]


def test_excess_weight_rises_in_bmi_without_linear_growth_failure() -> None:
    config = ExcessWeightConfig(
        onset_min_age_days=1000,
        onset_max_age_days=1000,
        severity_min=1.0,
        severity_max=1.0,
        treatment_probability=0.0,
    )
    module = ExcessWeightModule(config)
    state = module.sample_state(PATIENT, NamedRandomStreams(7, 0))
    onset = state.onset_age_days

    assert onset == 1000
    assert module.height_z_delta(state, onset - 1) == 0.0  # type: ignore[operator]
    assert module.height_z_delta(state, onset + config.bmi_progression_days) == 0.0  # type: ignore[operator]
    assert module.bmi_z_delta(state, onset) == 0.0  # type: ignore[operator]
    assert module.bmi_z_delta(state, onset + 1) > 0  # type: ignore[operator]
    assert module.bmi_z_delta(state, onset + config.bmi_progression_days) == pytest.approx(
        config.bmi_z_max_delta
    )
    assert [event.event_type for event in module.events(PATIENT, state)] == [
        "latent_onset",
        "observable_phenotype",
        "recognition_opportunity",
        "workup",
        "recorded_diagnosis",
    ]


def test_treated_excess_weight_preserves_pre_treatment_effect_and_partially_recovers() -> None:
    config = ExcessWeightConfig(
        onset_min_age_days=1000,
        onset_max_age_days=1000,
        severity_min=1.0,
        severity_max=1.0,
        treatment_probability=1.0,
        treatment_response_min=0.6,
        treatment_response_max=0.6,
    )
    module = ExcessWeightModule(config)
    treated = module.sample_state(PATIENT, NamedRandomStreams(8, 0))
    untreated = LatentDisorderState(
        DisorderKind.EXCESS_WEIGHT,
        treated.onset_age_days,
        treated.severity,
    )

    treatment_start = treated.treatment_start_age_days
    assert treatment_start == 1300
    assert treatment_start is not None
    before_treatment = treatment_start - 1
    assert module.bmi_z_delta(treated, before_treatment) == pytest.approx(
        module.bmi_z_delta(untreated, before_treatment)
    )
    response_age = treatment_start + config.response_days
    assert module.bmi_z_delta(treated, response_age) < module.bmi_z_delta(
        untreated, response_age
    )
    assert module.bmi_z_delta(treated, response_age) > 0
    assert module.height_z_delta(treated, response_age) == 0.0
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
    module = ExcessWeightModule(
        ExcessWeightConfig(
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
            LatentDisorderState(DisorderKind.EXCESS_WEIGHT, 729, 0.8), 1000
        ),
        lambda module: module.bmi_z_delta(
            LatentDisorderState(DisorderKind.EXCESS_WEIGHT, 5000, 0.8), 5000
        ),
        lambda module: module.bmi_z_delta(
            LatentDisorderState(DisorderKind.EXCESS_WEIGHT, None, 0.8), 1000
        ),
        lambda module: module.events(
            PATIENT,
            LatentDisorderState(
                DisorderKind.EXCESS_WEIGHT, 1000, 0.8, puberty_delay_days=1
            ),
        ),
    ],
)
def test_excess_weight_rejects_incoherent_state(operation: object) -> None:
    with pytest.raises(ValueError, match="onset|puberty"):
        operation(ExcessWeightModule())  # type: ignore[operator]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ExcessWeightConfig(onset_max_age_days=10**1000),
        lambda: ExcessWeightConfig(bmi_progression_days=0),
        lambda: ExcessWeightConfig(severity_min=math.nan),
        lambda: ExcessWeightConfig(treatment_probability=1.1),
        lambda: ExcessWeightConfig(
            treatment_response_min=0.9, treatment_response_max=0.8
        ),
        lambda: ExcessWeightConfig(bmi_z_max_delta=-0.1),
    ],
)
def test_excess_weight_config_rejects_invalid_values(factory: object) -> None:
    with pytest.raises(ValueError):
        factory()


def test_excess_weight_config_is_frozen_and_versioned() -> None:
    config = ExcessWeightConfig()
    assert config.module_version == "excess-weight-v1"
    with pytest.raises(FrozenInstanceError):
        config.bmi_progression_days = 30  # type: ignore[misc]


def test_excess_weight_constructor_rejects_config_version_drift() -> None:
    config = ExcessWeightConfig()
    object.__setattr__(config, "module_version", "excess-weight-v999")
    with pytest.raises(ValueError, match="version"):
        ExcessWeightModule(config)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("severity", -1.0),
        ("onset_age_days", "not-an-age"),
        ("treatment_response", 2.0),
        ("treatment_start_age_days", 1400),
    ],
)
def test_excess_weight_revalidates_tampered_state(field: str, value: object) -> None:
    module = ExcessWeightModule()
    state = LatentDisorderState(
        DisorderKind.EXCESS_WEIGHT,
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


def test_excess_weight_rejects_treatment_fields_on_zero_severity_state() -> None:
    module = ExcessWeightModule()
    state = LatentDisorderState(
        DisorderKind.EXCESS_WEIGHT,
        1000,
        0.0,
        treatment_start_age_days=1300,
    )

    with pytest.raises(ValueError, match="zero-severity"):
        module.height_z_delta(state, 1500)
    with pytest.raises(ValueError, match="zero-severity"):
        module.events(PATIENT, state)


def test_age_regime_composition_preserves_excess_weight_identity_and_height() -> None:
    config = ExcessWeightConfig(
        onset_min_age_days=1000,
        onset_max_age_days=1000,
        severity_min=1.0,
        severity_max=1.0,
        treatment_probability=1.0,
        treatment_response_min=0.6,
        treatment_response_max=0.6,
    )
    module = ExcessWeightModule(config)
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
    assert result.physiology.points[2].bmi_z == pytest.approx(
        baseline.points[2].bmi_z
    )
    assert result.physiology.points[3].bmi_z > result.physiology.points[2].bmi_z
    assert result.physiology.points[3].bmi_z > baseline.points[3].bmi_z
    assert all(
        result.physiology.points[index].height_z
        == pytest.approx(baseline.points[index].height_z)
        for index in range(len(ages))
    )
    assert all(
        point.weight_kg == pytest.approx(point.bmi * (point.height_cm / 100) ** 2)
        for point in result.physiology.points[2:]
    )
