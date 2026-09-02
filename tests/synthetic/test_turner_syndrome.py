from __future__ import annotations

import math
from dataclasses import FrozenInstanceError

import pytest

from synthetic.models import DisorderKind, LatentDisorderState, PatientState
from synthetic.native.age_regime_disorder import AgeRegimeDisorderKernel
from synthetic.native.age_regimes import AgeRegimeConfig, AgeRegimeTrajectoryKernel
from synthetic.native.clinical_modules import (
    TurnerSyndromeConfig,
    TurnerSyndromeModule,
)
from synthetic.randomness import NamedRandomStreams
from tests.synthetic.fakes import RegimeLinearTestReference

FEMALE = PatientState("syn-patient-turner", "F", "F")
UNKNOWN_RECORDED = PatientState("syn-patient-turner-u", "U", "F")
MALE_REFERENCE = PatientState("syn-patient-turner-m", "M", "M")


class HalfGenerationZReference(RegimeLinearTestReference):
    """Test reference with a deliberately non-idempotent z-score hook."""

    def generation_z_score(
        self, metric: str, age_days: int, reference_sex: str, z: float
    ) -> float:
        del metric, age_days, reference_sex
        return z / 2


def test_turner_samples_reproducibly_from_its_scoped_stream() -> None:
    module = TurnerSyndromeModule()
    first = module.sample_state(FEMALE, NamedRandomStreams(20260902, 3))
    second = module.sample_state(FEMALE, NamedRandomStreams(20260902, 3))

    assert first == second
    assert first.kind is DisorderKind.TURNER_SYNDROME
    assert module.config.onset_min_age_days <= first.onset_age_days <= module.config.onset_max_age_days  # type: ignore[operator]
    assert module.config.severity_min <= first.severity <= module.config.severity_max


@pytest.mark.parametrize("patient", [MALE_REFERENCE, PatientState("syn-patient-turner-x", "F", "U")])
def test_turner_requires_female_reference_sex(patient: PatientState) -> None:
    with pytest.raises(ValueError, match="reference_sex"):
        TurnerSyndromeModule().sample_state(patient, NamedRandomStreams(1, 0))


def test_turner_keeps_recorded_sex_separate_from_reference_sex() -> None:
    state = TurnerSyndromeModule().sample_state(
        UNKNOWN_RECORDED, NamedRandomStreams(2, 0)
    )

    assert state.kind is DisorderKind.TURNER_SYNDROME


def test_turner_eligibility_is_checked_before_reference_generation() -> None:
    class RecordingReference(RegimeLinearTestReference):
        def __init__(self) -> None:
            self.calls = 0

        def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
            self.calls += 1
            return super().value(metric, age_days, reference_sex, z)

    reference = RecordingReference()
    physiology = AgeRegimeTrajectoryKernel(reference, AgeRegimeConfig(residual_sd=0.0))
    module = TurnerSyndromeModule()
    state = LatentDisorderState(DisorderKind.TURNER_SYNDROME, 1460, 1.0)

    with pytest.raises(ValueError, match="reference_sex"):
        AgeRegimeDisorderKernel(physiology, module).generate(
            MALE_REFERENCE,
            (0, 730, 1460),
            NamedRandomStreams(3, 0),
            disorder_state=state,
            physiology_state=physiology.sample_state(NamedRandomStreams(3, 0)),
        )
    assert reference.calls == 0


@pytest.mark.parametrize(
    "state",
    [
        LatentDisorderState(DisorderKind.TURNER_SYNDROME, 0, 1.0),
        LatentDisorderState(DisorderKind.TURNER_SYNDROME, None, 1.0),
        LatentDisorderState(DisorderKind.TURNER_SYNDROME, 730, 1.0, puberty_delay_days=1),
    ],
)
def test_turner_rejects_nonpositive_onset_or_puberty_delay(state: LatentDisorderState) -> None:
    module = TurnerSyndromeModule()

    with pytest.raises(ValueError, match="onset|puberty"):
        module.height_z_delta(state, 730)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("severity", -1.0),
        ("onset_age_days", "not-an-age"),
        ("treatment_response", 2.0),
        ("treatment_start_age_days", 1900),
    ],
)
def test_turner_revalidates_tampered_state_before_effects_and_events(
    field: str, value: object
) -> None:
    module = TurnerSyndromeModule()
    state = LatentDisorderState(
        DisorderKind.TURNER_SYNDROME,
        1460,
        1.0,
        treatment_start_age_days=1850,
        treatment_response=0.6,
    )
    object.__setattr__(state, field, value)

    with pytest.raises(ValueError):
        module.height_z_delta(state, 2000)
    with pytest.raises(ValueError):
        module.bmi_z_delta(state, 2000)
    with pytest.raises(ValueError):
        module.events(FEMALE, state)


def test_turner_rejects_treatment_fields_on_zero_severity_state() -> None:
    module = TurnerSyndromeModule()
    state = LatentDisorderState(
        DisorderKind.TURNER_SYNDROME,
        1460,
        0.0,
        treatment_start_age_days=1850,
    )

    with pytest.raises(ValueError, match="zero-severity"):
        module.height_z_delta(state, 2000)
    with pytest.raises(ValueError, match="zero-severity"):
        module.events(FEMALE, state)


def test_turner_ignores_tampered_config_reference_attribute() -> None:
    config = TurnerSyndromeConfig()
    object.__setattr__(config, "reference_sex", "M")

    state = TurnerSyndromeModule(config).sample_state(
        FEMALE, NamedRandomStreams(4, 0)
    )

    assert state.kind is DisorderKind.TURNER_SYNDROME


def test_turner_has_no_birth_deficit_and_progresses_after_onset() -> None:
    module = TurnerSyndromeModule()
    state = LatentDisorderState(DisorderKind.TURNER_SYNDROME, 1460, 1.0)

    assert module.height_z_delta(state, 0) == pytest.approx(0.0)
    assert module.height_z_delta(state, 1460) == pytest.approx(0.0)
    assert module.height_z_delta(state, 1460 + module.config.progression_days) < 0
    assert module.height_z_delta(state, 1460 + module.config.progression_days) == pytest.approx(-1.0)
    assert module.bmi_z_delta(state, 1460) == pytest.approx(0.0)
    assert module.bmi_z_delta(state, 1460 + module.config.progression_days) > 0


def test_turner_treatment_improves_height_without_regression() -> None:
    config = TurnerSyndromeConfig()
    module = TurnerSyndromeModule(config)
    state = LatentDisorderState(
        DisorderKind.TURNER_SYNDROME,
        1460,
        1.0,
        treatment_start_age_days=1850,
        treatment_response=0.6,
    )

    at_start = module.height_z_delta(state, state.treatment_start_age_days)  # type: ignore[arg-type]
    during = module.height_z_delta(state, 2215)
    after = module.height_z_delta(state, 3000)
    assert at_start < 0
    assert at_start < during < 0
    assert after > during
    assert after == pytest.approx(module.height_z_delta(state, 4000))
    assert module.bmi_z_delta(state, 2215) > 0


def test_turner_events_require_reference_compatible_patient_and_causal_treatment() -> None:
    module = TurnerSyndromeModule()
    state = LatentDisorderState(
        DisorderKind.TURNER_SYNDROME,
        1460,
        1.0,
        treatment_start_age_days=1850,
        treatment_response=0.6,
    )

    assert [event.event_type for event in module.events(FEMALE, state)] == [
        "latent_onset",
        "observable_phenotype",
        "recognition_opportunity",
        "workup",
        "recorded_diagnosis",
        "treatment_start",
        "treatment_response",
    ]
    with pytest.raises(ValueError, match="reference_sex"):
        module.events(MALE_REFERENCE, state)


def test_turner_composes_with_age_regime_kernel_and_preserves_weight_identity() -> None:
    physiology = AgeRegimeTrajectoryKernel(
        RegimeLinearTestReference(), AgeRegimeConfig(residual_sd=0.0)
    )
    module = TurnerSyndromeModule()
    state = LatentDisorderState(DisorderKind.TURNER_SYNDROME, 1460, 1.0)
    result = AgeRegimeDisorderKernel(physiology, module).generate(
        FEMALE,
        (0, 730, 1460, 2190, 3000, 4380, 7305),
        NamedRandomStreams(7, 0),
        disorder_state=state,
        physiology_state=physiology.sample_state(NamedRandomStreams(7, 0)),
    )

    assert result.disorder == state
    assert result.physiology.points[0].length_cm is not None
    assert result.physiology.points[2].height_cm is not None
    assert all(point.height_cm is not None for point in result.physiology.points[2:])
    assert all(
        point.weight_kg == pytest.approx(point.bmi * (point.height_cm / 100) ** 2)
        for point in result.physiology.points[2:]
    )


def test_turner_preserves_zero_effect_baseline_with_nonidempotent_reference_hook() -> None:
    reference = HalfGenerationZReference()
    physiology = AgeRegimeTrajectoryKernel(
        reference, AgeRegimeConfig(residual_sd=0.0)
    )
    physiology_state = physiology.sample_state(NamedRandomStreams(8, 0))
    ages = (0, 730, 1460, 2190)
    baseline = physiology.generate(
        FEMALE,
        ages,
        NamedRandomStreams(8, 0),
        state=physiology_state,
    )
    result = AgeRegimeDisorderKernel(physiology, TurnerSyndromeModule()).generate(
        FEMALE,
        ages,
        NamedRandomStreams(8, 0),
        physiology_state=physiology_state,
        disorder_state=LatentDisorderState(
            DisorderKind.TURNER_SYNDROME, 1460, 1.0
        ),
    )

    assert result.physiology.points[:3] == baseline.points[:3]


def test_turner_config_rejects_invalid_values() -> None:
    factories = (
        lambda: TurnerSyndromeConfig(onset_min_age_days=3651, onset_max_age_days=3650),
        lambda: TurnerSyndromeConfig(severity_min=math.nan),
        lambda: TurnerSyndromeConfig(progression_days=0),
        lambda: TurnerSyndromeConfig(treatment_probability=1.1),
        lambda: TurnerSyndromeConfig(response_days=0),
        lambda: TurnerSyndromeConfig(treatment_response_max=1.1),
        lambda: TurnerSyndromeConfig(bmi_z_max_delta=-0.1),
    )
    for factory in factories:
        with pytest.raises(ValueError):
            factory()


def test_turner_config_is_frozen_and_versioned() -> None:
    config = TurnerSyndromeConfig()
    assert config.module_version == "turner-syndrome-v1"
    with pytest.raises(FrozenInstanceError):
        config.progression_days = 10  # type: ignore[misc]
