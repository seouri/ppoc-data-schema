from __future__ import annotations

import math
from dataclasses import FrozenInstanceError

import pytest

from synthetic.models import DisorderKind, LatentDisorderState, PatientState
from synthetic.native.age_regime_disorder import AgeRegimeDisorderKernel
from synthetic.native.age_regimes import AgeRegimeConfig, AgeRegimeTrajectoryKernel
from synthetic.native.clinical_modules import (
    HealthyGrowthModule,
    SmallForGestationalAgeConfig,
    SmallForGestationalAgeModule,
)
from synthetic.randomness import NamedRandomStreams
from tests.synthetic.fakes import RegimeLinearTestReference

PATIENT = PatientState("syn-patient-sga", "F", "F")


def test_sga_samples_reproducibly_from_its_scoped_stream() -> None:
    module = SmallForGestationalAgeModule()
    first = module.sample_state(PATIENT, NamedRandomStreams(20260902, 5))
    second = module.sample_state(PATIENT, NamedRandomStreams(20260902, 5))

    assert first == second
    assert first.kind is DisorderKind.SMALL_FOR_GESTATIONAL_AGE
    assert first.onset_age_days == 0
    assert module.config.severity_min <= first.severity <= module.config.severity_max


def test_sga_catch_up_starts_small_at_birth_and_recovers_weight_before_height() -> None:
    config = SmallForGestationalAgeConfig()
    module = SmallForGestationalAgeModule(config)
    state = LatentDisorderState(DisorderKind.SMALL_FOR_GESTATIONAL_AGE, 0, 0.7)

    assert module.height_z_delta(state, 0) < 0
    assert module.bmi_z_delta(state, 0) < 0
    assert module.bmi_z_delta(state, config.bmi_catch_up_days) == pytest.approx(0.0)
    assert module.height_z_delta(state, config.bmi_catch_up_days) < 0
    assert module.height_z_delta(state, config.height_catch_up_days) == pytest.approx(0.0)
    assert [event.event_type for event in module.events(PATIENT, state)] == [
        "latent_onset",
        "observable_phenotype",
        "recognition_opportunity",
        "workup",
        "recorded_diagnosis",
    ]


def test_sga_persistent_branch_retains_height_offset_after_bmi_catch_up() -> None:
    config = SmallForGestationalAgeConfig()
    module = SmallForGestationalAgeModule(config)
    state = LatentDisorderState(DisorderKind.SMALL_FOR_GESTATIONAL_AGE, 0, 1.2)

    assert module.height_z_delta(state, 0) < 0
    assert module.height_z_delta(state, config.height_catch_up_days) == pytest.approx(
        module.height_z_delta(state, 0)
    )
    assert module.bmi_z_delta(state, config.bmi_catch_up_days) == pytest.approx(0.0)


def test_sga_probability_branch_respects_catch_up_at_severity_boundary() -> None:
    config = SmallForGestationalAgeConfig(
        severity_min=0.9,
        severity_max=1.2,
        catch_up_severity_max=0.9,
        catch_up_probability=1.0,
    )
    module = SmallForGestationalAgeModule(config)
    state = module.sample_state(PATIENT, NamedRandomStreams(9, 0))

    assert state.severity == pytest.approx(config.catch_up_severity_max)
    assert module.height_z_delta(state, config.height_catch_up_days) == pytest.approx(0.0)


def test_sga_probability_branch_respects_persistent_branch_at_boundary() -> None:
    config = SmallForGestationalAgeConfig(
        severity_min=0.9,
        severity_max=1.2,
        catch_up_severity_max=0.9,
        catch_up_probability=0.0,
    )
    module = SmallForGestationalAgeModule(config)
    state = module.sample_state(PATIENT, NamedRandomStreams(10, 0))

    assert state.severity > config.catch_up_severity_max
    assert module.height_z_delta(state, config.height_catch_up_days) < 0


def test_sga_persistent_branch_excludes_catch_up_threshold_endpoint() -> None:
    class EndpointGenerator:
        def random(self) -> float:
            return 1.0

        def uniform(self, low: float, high: float) -> float:
            assert low == math.nextafter(config.catch_up_severity_max, config.severity_max)
            return low

    class EndpointStreams(NamedRandomStreams):
        def generator(self, name: str) -> EndpointGenerator:
            assert name == "disorder.small_for_gestational_age"
            return EndpointGenerator()

    config = SmallForGestationalAgeConfig(catch_up_probability=0.0)
    module = SmallForGestationalAgeModule(config)
    state = module.sample_state(PATIENT, EndpointStreams(11, 0))

    assert state.severity > config.catch_up_severity_max
    assert module.height_z_delta(state, config.height_catch_up_days) < 0


def test_sga_rejects_wrong_state_kind_and_unrepresentable_age() -> None:
    module = SmallForGestationalAgeModule()
    wrong_state = LatentDisorderState(DisorderKind.CELIAC_DISEASE, 0, 0.8)

    with pytest.raises(ValueError, match="state kind"):
        module.height_z_delta(wrong_state, 0)
    with pytest.raises(ValueError, match="age_days"):
        module.height_z_delta(
            LatentDisorderState(DisorderKind.SMALL_FOR_GESTATIONAL_AGE, 0, 0.8),
            10**1000,
        )


def test_sga_rejects_nonbirth_onset_states() -> None:
    module = SmallForGestationalAgeModule()
    state = LatentDisorderState(DisorderKind.SMALL_FOR_GESTATIONAL_AGE, 1, 0.8)

    for operation in (
        lambda: module.height_z_delta(state, 0),
        lambda: module.bmi_z_delta(state, 0),
        lambda: module.events(PATIENT, state),
    ):
        with pytest.raises(ValueError, match="birth onset"):
            operation()


@pytest.mark.parametrize(
    "factory",
    [
        lambda: SmallForGestationalAgeConfig(severity_min=math.nan),
        lambda: SmallForGestationalAgeConfig(catch_up_severity_max=-0.1),
        lambda: SmallForGestationalAgeConfig(catch_up_severity_max=0.5),
        lambda: SmallForGestationalAgeConfig(catch_up_severity_max=1.5),
        lambda: SmallForGestationalAgeConfig(catch_up_probability=1.1),
        lambda: SmallForGestationalAgeConfig(bmi_catch_up_days=0),
        lambda: SmallForGestationalAgeConfig(height_catch_up_days=10**1000),
        lambda: SmallForGestationalAgeConfig(recognition_delay_days=10**1000),
        lambda: SmallForGestationalAgeConfig(
            severity_min=1.0, severity_max=0.5
        ),
    ],
)
def test_sga_config_rejects_invalid_values(factory: object) -> None:
    with pytest.raises(ValueError):
        factory()


def test_sga_config_is_frozen_and_versioned() -> None:
    config = SmallForGestationalAgeConfig()
    assert config.module_version == "small-for-gestational-age-v1"
    with pytest.raises(FrozenInstanceError):
        config.bmi_catch_up_days = 30  # type: ignore[misc]


def test_sga_constructor_rejects_config_version_drift() -> None:
    config = SmallForGestationalAgeConfig()
    object.__setattr__(config, "module_version", "small-for-gestational-age-v999")
    with pytest.raises(ValueError, match="version"):
        SmallForGestationalAgeModule(config)


def test_age_regime_composition_preserves_sga_weight_identity_and_birth_effect() -> None:
    config = SmallForGestationalAgeConfig()
    module = SmallForGestationalAgeModule(config)
    physiology = AgeRegimeTrajectoryKernel(
        RegimeLinearTestReference(), AgeRegimeConfig(residual_sd=0.0)
    )
    state = LatentDisorderState(DisorderKind.SMALL_FOR_GESTATIONAL_AGE, 0, 0.7)
    result = AgeRegimeDisorderKernel(physiology, module).generate(
        PATIENT,
        (0, 365, 730, 1095, 1825, 3000, 7305),
        NamedRandomStreams(11, 0),
        disorder_state=state,
        physiology_state=physiology.sample_state(NamedRandomStreams(11, 0)),
    )
    baseline = AgeRegimeDisorderKernel(physiology, HealthyGrowthModule()).generate(
        PATIENT,
        (0, 365, 730, 1095, 1825, 3000, 7305),
        NamedRandomStreams(11, 0),
        physiology_state=physiology.sample_state(NamedRandomStreams(11, 0)),
        disorder_state=LatentDisorderState(DisorderKind.HEALTHY, None, 0.0),
    )

    assert result.disorder == state
    birth = result.physiology.points[0]
    baseline_birth = baseline.physiology.points[0]
    assert birth.length_cm is not None
    assert baseline_birth.length_cm is not None
    assert birth.length_cm < baseline_birth.length_cm
    assert birth.weight_kg < baseline_birth.weight_kg
    assert all(
        point.weight_kg == pytest.approx(point.bmi * (point.height_cm / 100) ** 2)
        for point in result.physiology.points[2:]
    )
