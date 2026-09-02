import dataclasses
import math

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
from synthetic.native.clinical_modules import FamilialShortStatureModule
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


@pytest.mark.parametrize(
    ("state", "events", "message"),
    [
        (
            LatentDisorderState(DisorderKind.FAMILIAL_SHORT_STATURE, 100, 0.8),
            (ClinicalEvent("syn-patient-a", 100, "unknown", None, True),),
            "unknown clinical event type",
        ),
        (
            LatentDisorderState(DisorderKind.FAMILIAL_SHORT_STATURE, 100, 0.8),
            (ClinicalEvent("syn-patient-a", 100, "latent_onset", "code", True),),
            "code=None",
        ),
        (
            LatentDisorderState(DisorderKind.FAMILIAL_SHORT_STATURE, 100, 0.8),
            (ClinicalEvent("syn-patient-a", 100, "observable_phenotype", None, True),),
            "hidden flag",
        ),
        (
            LatentDisorderState(DisorderKind.FAMILIAL_SHORT_STATURE, 100, 0.8),
            (ClinicalEvent("syn-patient-a", 101, "latent_onset", None, True),),
            "onset age",
        ),
        (
            LatentDisorderState(DisorderKind.FAMILIAL_SHORT_STATURE, 100, 0.8),
            (ClinicalEvent("syn-patient-a", 100, "workup", None, False),),
            "begin with latent_onset",
        ),
        (
            LatentDisorderState(DisorderKind.FAMILIAL_SHORT_STATURE, 100, 0.8),
            (
                ClinicalEvent("syn-patient-a", 100, "latent_onset", None, True),
                ClinicalEvent("syn-patient-a", 99, "observable_phenotype", None, False),
            ),
            "nondecreasing",
        ),
        (
            LatentDisorderState(DisorderKind.FAMILIAL_SHORT_STATURE, 100, 0.8),
            (
                ClinicalEvent("syn-patient-a", 100, "latent_onset", None, True),
                ClinicalEvent(
                    "syn-patient-a", 10**1000, "observable_phenotype", None, False
                ),
            ),
            "supported age",
        ),
        (
            LatentDisorderState(
                DisorderKind.GROWTH_HORMONE_DEFICIENCY,
                100,
                0.8,
                treatment_start_age_days=300,
                treatment_response=0.6,
            ),
            (
                ClinicalEvent("syn-patient-a", 100, "latent_onset", None, True),
                ClinicalEvent("syn-patient-a", 300, "treatment_start", None, False),
            ),
            "terminal treatment outcome",
        ),
    ],
)
def test_composition_container_rejects_malformed_causal_events(
    state: LatentDisorderState,
    events: tuple[ClinicalEvent, ...],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        AgeRegimeDisorderTrajectory(_physiology(), state, events)


def test_composition_container_rejects_active_nonhealthy_empty_event_trace() -> None:
    with pytest.raises(ValueError, match="empty|latent_onset"):
        AgeRegimeDisorderTrajectory(
            _physiology(),
            LatentDisorderState(DisorderKind.FAMILIAL_SHORT_STATURE, 100, 0.8),
            (),
        )


def test_composition_container_accepts_nonhealthy_zero_effect_empty_event_trace() -> None:
    result = AgeRegimeDisorderTrajectory(
        _physiology(),
        LatentDisorderState(DisorderKind.FAMILIAL_SHORT_STATURE, 100, 0.0),
        (),
    )

    assert result.events == ()


@pytest.mark.parametrize("target", ["point", "physiology_state", "disorder_state"])
def test_composition_container_revalidates_nested_models(target: str) -> None:
    physiology = _physiology()
    disorder = LatentDisorderState(DisorderKind.HEALTHY, None, 0.0)
    message = ""
    if target == "point":
        object.__setattr__(physiology.points[0], "patient_id", "")
        message = "patient_id"
    elif target == "physiology_state":
        object.__setattr__(physiology.state, "module_version", "")
        message = "module_version"
    else:
        object.__setattr__(disorder, "severity", math.nan)
        message = "severity"

    with pytest.raises(ValueError, match=message):
        AgeRegimeDisorderTrajectory(physiology, disorder, ())


def test_composition_container_rejects_tampered_nested_patient_identity() -> None:
    first = _physiology().points[0]
    second = dataclasses.replace(first, age_days=366)
    physiology = AgeRegimeTrajectory((first, second), _physiology().state)
    object.__setattr__(second, "patient_id", "other-patient")

    with pytest.raises(ValueError, match="one patient"):
        AgeRegimeDisorderTrajectory(
            physiology,
            LatentDisorderState(DisorderKind.HEALTHY, None, 0.0),
            (),
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


def test_shared_module_validator_rejects_built_in_module_config_version_drift() -> None:
    module = FamilialShortStatureModule()
    module.module_version = "familial-short-stature-v999"

    with pytest.raises(ValueError, match="version"):
        validate_growth_disorder_module(module)
