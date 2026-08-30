import math
from dataclasses import FrozenInstanceError

import pytest

from synthetic.models import DisorderKind, LatentDisorderState, PatientState
from synthetic.native.clinical_modules import (
    ConstitutionalDelayConfig,
    ConstitutionalDelayModule,
    FamilialShortStatureConfig,
    FamilialShortStatureModule,
    GrowthHormoneDeficiencyConfig,
    GrowthHormoneDeficiencyModule,
    HealthyGrowthConfig,
    HealthyGrowthModule,
)
from synthetic.randomness import NamedRandomStreams

PATIENT = PatientState("syn-patient-a", "F", "F")


class RecordingStreams(NamedRandomStreams):
    def __init__(self, run_seed: int, patient_index: int) -> None:
        super().__init__(run_seed, patient_index)
        self.requested_names: list[str] = []

    def generator(self, name: str):
        self.requested_names.append(name)
        return super().generator(name)


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


def test_modules_request_only_their_scoped_disorder_streams() -> None:
    streams = RecordingStreams(123, 7)
    modules = (
        FamilialShortStatureModule(),
        ConstitutionalDelayModule(),
        GrowthHormoneDeficiencyModule(),
    )

    for module in modules:
        module.sample_state(PATIENT, streams)

    assert streams.requested_names == [f"disorder.{module.kind.value}" for module in modules]
    healthy_streams = RecordingStreams(123, 7)
    HealthyGrowthModule().sample_state(PATIENT, healthy_streams)
    assert healthy_streams.requested_names == []


@pytest.mark.parametrize(
    ("factory", "attribute", "value"),
    [
        (HealthyGrowthConfig, "unused", None),
        (FamilialShortStatureConfig, "severity_min", 0.0),
        (ConstitutionalDelayConfig, "height_z_magnitude", 0.0),
        (GrowthHormoneDeficiencyConfig, "treatment_probability", 0.0),
    ],
)
def test_module_configurations_are_frozen(
    factory: type[object], attribute: str, value: object
) -> None:
    config = factory()
    with pytest.raises(FrozenInstanceError):
        setattr(config, attribute, value)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: FamilialShortStatureConfig(severity_min=math.nan),
        lambda: FamilialShortStatureConfig(
            phenotype_age_days=1000, recognition_age_days=999
        ),
        lambda: ConstitutionalDelayConfig(height_z_magnitude=-0.1),
        lambda: GrowthHormoneDeficiencyConfig(treatment_probability=1.1),
    ],
)
def test_module_configurations_reject_invalid_magnitudes_probabilities_and_schedules(
    factory: object,
) -> None:
    with pytest.raises(ValueError):
        factory()


def test_familial_short_stature_requires_birth_onset() -> None:
    with pytest.raises(ValueError, match="onset_age_days"):
        FamilialShortStatureConfig(onset_age_days=1)


def test_disorder_events_keep_codes_empty_and_only_hide_latent_onset() -> None:
    for module in (
        FamilialShortStatureModule(),
        ConstitutionalDelayModule(),
        GrowthHormoneDeficiencyModule(GrowthHormoneDeficiencyConfig(treatment_probability=1.0)),
    ):
        state = module.sample_state(PATIENT, NamedRandomStreams(123, 7))
        events = module.events(PATIENT, state)

        assert events[0].event_type == "latent_onset"
        assert events[0].hidden is True
        assert all(event.code is None for event in events)
        assert all(event.hidden is False for event in events[1:])


def test_growth_hormone_deficiency_treatment_branches_and_bmi_boundaries() -> None:
    untreated_config = GrowthHormoneDeficiencyConfig(treatment_probability=0.0)
    untreated_module = GrowthHormoneDeficiencyModule(untreated_config)
    untreated_state = untreated_module.sample_state(PATIENT, NamedRandomStreams(123, 7))
    assert untreated_state.treatment_start_age_days is None
    assert untreated_state.onset_age_days is not None
    untreated_onset = untreated_state.onset_age_days
    untreated_at_onset = untreated_module.height_z_delta(untreated_state, untreated_onset)
    untreated_midpoint = untreated_module.height_z_delta(
        untreated_state, untreated_onset + untreated_config.progression_days // 2
    )
    untreated_height = untreated_module.height_z_delta(
        untreated_state, untreated_onset + untreated_config.progression_days
    )
    assert untreated_at_onset == 0.0
    assert untreated_midpoint < 0
    assert untreated_height < untreated_midpoint
    assert untreated_height < 0
    untreated_event_types = [
        event.event_type for event in untreated_module.events(PATIENT, untreated_state)
    ]
    assert "treatment_start" not in untreated_event_types
    assert "treatment_response" not in untreated_event_types
    assert 0 <= untreated_module.bmi_z_delta(
        untreated_state, untreated_onset + untreated_config.progression_days
    ) <= untreated_config.bmi_z_max_delta

    treated_config = GrowthHormoneDeficiencyConfig(treatment_probability=1.0)
    treated_module = GrowthHormoneDeficiencyModule(treated_config)
    treated_state = treated_module.sample_state(PATIENT, NamedRandomStreams(123, 7))
    assert treated_state.treatment_start_age_days is not None
    treated_onset = treated_state.onset_age_days
    assert treated_onset is not None
    matching_untreated = LatentDisorderState(
        DisorderKind.GROWTH_HORMONE_DEFICIENCY,
        treated_onset,
        treated_state.severity,
    )
    before_treatment = treated_state.treatment_start_age_days - 1
    assert treated_module.height_z_delta(
        treated_state, before_treatment
    ) == treated_module.height_z_delta(matching_untreated, before_treatment)
    response_age = treated_state.treatment_start_age_days + treated_config.response_days
    assert treated_module.height_z_delta(treated_state, response_age) > untreated_height
    assert 0 <= treated_module.bmi_z_delta(
        treated_state, response_age
    ) <= treated_config.bmi_z_max_delta
