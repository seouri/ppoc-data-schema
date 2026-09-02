import pytest

from synthetic.models import (
    AgeRegimeDisorderTrajectory,
    AgeRegimePoint,
    AgeRegimeState,
    AgeRegimeTrajectory,
    ClinicalEvent,
    DisorderKind,
    GrowthRegime,
    LatentDisorderState,
    PatientState,
)
from synthetic.native.trajectories import (
    validate_disorder_events,
    validate_growth_disorder_module,
)


def _physiology() -> AgeRegimeTrajectory:
    state = AgeRegimeState(
        "age-regimes-v1", 0.0, 0.0, 0.0, 0.0, 0.0, 4380, 900, 0.0, 0.0
    )
    point = AgeRegimePoint(
        "syn-patient-a", 365, GrowthRegime.INFANCY, 75.0, None, 9.0, None
    )
    return AgeRegimeTrajectory((point,), state)


def test_composition_container_accepts_healthy_empty_events() -> None:
    result = AgeRegimeDisorderTrajectory(
        _physiology(), LatentDisorderState(DisorderKind.HEALTHY, None, 0.0), ()
    )
    assert result.physiology.points[0].patient_id == "syn-patient-a"
    assert result.disorder.kind is DisorderKind.HEALTHY
    assert result.events == ()


def test_container_rejects_patient_mismatch_and_non_tuple_events() -> None:
    with pytest.raises(ValueError, match="patient"):
        AgeRegimeDisorderTrajectory(
            _physiology(), LatentDisorderState(DisorderKind.HEALTHY, None, 0.0),
            (ClinicalEvent("other", 0, "latent_onset", None, True),),
        )
    with pytest.raises(ValueError, match="tuple"):
        AgeRegimeDisorderTrajectory(
            _physiology(), LatentDisorderState(DisorderKind.HEALTHY, None, 0.0), []
        )


def test_shared_event_validator_keeps_terminal_treatment_rules() -> None:
    state = LatentDisorderState(
        DisorderKind.GROWTH_HORMONE_DEFICIENCY, 100, 0.8,
        treatment_start_age_days=300, treatment_response=0.6,
    )
    events = (
        ClinicalEvent("syn-patient-a", 100, "latent_onset", None, True),
        ClinicalEvent("syn-patient-a", 300, "treatment_start", None, False),
        ClinicalEvent("syn-patient-a", 400, "treatment_response", None, False),
    )
    validate_disorder_events(PatientState("syn-patient-a", "F", "F"), state, events)


@pytest.mark.parametrize(
    "missing", ["module_version", "sample_state", "height_z_delta", "bmi_z_delta", "events"]
)
def test_shared_module_validator_rejects_missing_contract_member(missing: str) -> None:
    class Module:
        kind = DisorderKind.HEALTHY
        module_version = "test-v1"

        def sample_state(self, patient: PatientState, streams: object) -> LatentDisorderState:
            del patient, streams
            return LatentDisorderState(DisorderKind.HEALTHY, None, 0.0)

        def height_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
            del state, age_days
            return 0.0

        def bmi_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
            del state, age_days
            return 0.0

        def events(self, patient: PatientState, state: LatentDisorderState) -> tuple[ClinicalEvent, ...]:
            del patient, state
            return ()

    delattr(Module, missing)
    module = Module()
    with pytest.raises((TypeError, ValueError), match=missing):
        validate_growth_disorder_module(module)
