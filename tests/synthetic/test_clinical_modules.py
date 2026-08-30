import pytest

from synthetic.models import DisorderKind, PatientState
from synthetic.native.clinical_modules import (
    ConstitutionalDelayModule,
    FamilialShortStatureModule,
    GrowthHormoneDeficiencyModule,
    HealthyGrowthModule,
)
from synthetic.randomness import NamedRandomStreams

PATIENT = PatientState("syn-patient-a", "F", "F")


def test_healthy_module_has_no_effects_or_events() -> None:
    module = HealthyGrowthModule()
    state = module.sample_state(PATIENT, NamedRandomStreams(5, 0))

    assert state.kind is DisorderKind.HEALTHY
    assert state.severity == 0.0
    assert module.height_z_delta(state, 1000) == 0.0
    assert module.bmi_z_delta(state, 1000) == 0.0
    assert module.events(PATIENT, state) == ()


def test_familial_short_stature_preserves_velocity_with_constant_height_offset() -> None:
    module = FamilialShortStatureModule()
    state = module.sample_state(PATIENT, NamedRandomStreams(5, 0))

    assert state.kind is DisorderKind.FAMILIAL_SHORT_STATURE
    assert module.height_z_delta(state, 730) < 0
    assert module.height_z_delta(state, 5000) == pytest.approx(
        module.height_z_delta(state, 730)
    )
    assert module.bmi_z_delta(state, 2000) == 0.0
    assert [event.event_type for event in module.events(PATIENT, state)] == [
        "latent_onset",
        "observable_phenotype",
        "recognition_opportunity",
        "workup",
        "recorded_diagnosis",
    ]


def test_constitutional_delay_has_temporary_puberty_effect_and_ordered_events() -> None:
    module = ConstitutionalDelayModule()
    state = module.sample_state(PATIENT, NamedRandomStreams(5, 0))
    puberty_age = module.config.expected_puberty_age_days
    delayed_end = puberty_age + state.puberty_delay_days

    assert module.height_z_delta(state, puberty_age - 1) == 0.0
    assert module.height_z_delta(state, puberty_age + state.puberty_delay_days // 2) < 0
    assert module.height_z_delta(state, delayed_end + module.config.recovery_days) == 0.0
    ages = [event.age_days for event in module.events(PATIENT, state)]
    assert ages == sorted(ages)
    assert ages[0] == puberty_age


def test_growth_hormone_deficiency_progresses_and_treatment_has_response() -> None:
    module = GrowthHormoneDeficiencyModule()
    state = module.sample_state(PATIENT, NamedRandomStreams(5, 0))
    assert state.kind is DisorderKind.GROWTH_HORMONE_DEFICIENCY
    assert state.onset_age_days is not None
    onset = state.onset_age_days
    assert module.height_z_delta(state, onset - 1) == 0.0
    untreated = module.height_z_delta(state, onset + module.config.progression_days)
    assert untreated < 0
    if state.treatment_start_age_days is not None:
        response_age = state.treatment_start_age_days + module.config.response_days
        assert module.height_z_delta(state, response_age) > untreated
        event_types = [event.event_type for event in module.events(PATIENT, state)]
        assert "treatment_start" in event_types
        assert "treatment_response" in event_types


def test_module_sampling_is_reproducible_and_uses_named_streams() -> None:
    modules = (
        FamilialShortStatureModule(),
        ConstitutionalDelayModule(),
        GrowthHormoneDeficiencyModule(),
    )
    for module in modules:
        left = module.sample_state(PATIENT, NamedRandomStreams(123, 7))
        right = module.sample_state(PATIENT, NamedRandomStreams(123, 7))
        assert left == right
