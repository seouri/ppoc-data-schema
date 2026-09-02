import math

import pytest

from synthetic.models import (
    ClinicalEvent,
    DisorderKind,
    LatentDisorderState,
    LatentPoint,
    LatentTrajectory,
)


def test_disorder_state_accepts_valid_treatment_schedule() -> None:
    state = LatentDisorderState(
        kind=DisorderKind.GROWTH_HORMONE_DEFICIENCY,
        onset_age_days=900,
        severity=0.8,
        treatment_start_age_days=1200,
        treatment_response=0.6,
    )

    assert state.kind is DisorderKind.GROWTH_HORMONE_DEFICIENCY
    assert state.treatment_start_age_days == 1200


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": "", "onset_age_days": 0, "severity": 0.5},
        {"kind": DisorderKind.HEALTHY, "onset_age_days": -1, "severity": 0.5},
        {"kind": DisorderKind.HEALTHY, "onset_age_days": 0, "severity": True},
        {
            "kind": DisorderKind.HEALTHY,
            "onset_age_days": 0,
            "severity": 10**1000,
        },
        {
            "kind": DisorderKind.HEALTHY,
            "onset_age_days": 10**1000,
            "severity": 0.5,
        },
        {
            "kind": DisorderKind.HEALTHY,
            "onset_age_days": 0,
            "severity": 0.5,
            "treatment_start_age_days": 10**1000,
        },
        {
            "kind": DisorderKind.HEALTHY,
            "onset_age_days": 0,
            "severity": 0.5,
            "puberty_delay_days": 10**1000,
        },
        {"kind": DisorderKind.HEALTHY, "onset_age_days": 0, "severity": math.nan},
        {"kind": DisorderKind.HEALTHY, "onset_age_days": 0, "severity": -0.1},
        {
            "kind": DisorderKind.HEALTHY,
            "onset_age_days": 1000,
            "severity": 0.5,
            "treatment_start_age_days": 999,
        },
        {
            "kind": DisorderKind.HEALTHY,
            "onset_age_days": 0,
            "severity": 0.5,
            "treatment_response": 1.1,
        },
        {
            "kind": DisorderKind.HEALTHY,
            "onset_age_days": 0,
            "severity": 0.5,
            "treatment_start_age_days": 1,
            "treatment_response": True,
        },
        {
            "kind": DisorderKind.HEALTHY,
            "onset_age_days": 0,
            "severity": 0.5,
            "treatment_start_age_days": 1,
            "treatment_response": 10**1000,
        },
    ],
)
def test_disorder_state_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        LatentDisorderState(**kwargs)


def test_latent_trajectory_is_frozen_and_keeps_hidden_events_separate() -> None:
    point = LatentPoint("syn-patient-a", 730, 90.0, 16.0, 12.96, 0.0, 0.0)
    event = ClinicalEvent("syn-patient-a", 0, "latent_onset", None, True)
    trajectory = LatentTrajectory(
        points=(point,),
        disorder=LatentDisorderState(DisorderKind.HEALTHY, None, 0.0),
        events=(event,),
    )

    assert trajectory.points == (point,)
    assert trajectory.events[0].hidden is True
    with pytest.raises(AttributeError):
        trajectory.points = ()


@pytest.mark.parametrize(
    ("points", "disorder", "events"),
    [
        ([LatentPoint("syn-patient-a", 730, 90.0, 16.0, 12.96, 0.0, 0.0)],
         LatentDisorderState(DisorderKind.HEALTHY, None, 0.0), ()),
        ((), LatentDisorderState(DisorderKind.HEALTHY, None, 0.0), ()),
        ((object(),), LatentDisorderState(DisorderKind.HEALTHY, None, 0.0), ()),
        ((LatentPoint("syn-patient-a", 730, 90.0, 16.0, 12.96, 0.0, 0.0),),
         object(), ()),
        ((LatentPoint("syn-patient-a", 730, 90.0, 16.0, 12.96, 0.0, 0.0),),
         LatentDisorderState(DisorderKind.HEALTHY, None, 0.0), [object()]),
        ((LatentPoint("syn-patient-a", 730, 90.0, 16.0, 12.96, 0.0, 0.0),),
         LatentDisorderState(DisorderKind.HEALTHY, None, 0.0), (object(),)),
    ],
)
def test_latent_trajectory_rejects_malformed_containers_and_members(
    points: object, disorder: object, events: object
) -> None:
    with pytest.raises((TypeError, ValueError)):
        LatentTrajectory(points=points, disorder=disorder, events=events)  # type: ignore[arg-type]


def test_latent_trajectory_rejects_patient_mismatch() -> None:
    point = LatentPoint("syn-patient-a", 730, 90.0, 16.0, 12.96, 0.0, 0.0)
    event = ClinicalEvent("other-patient", 0, "latent_onset", None, True)

    with pytest.raises(ValueError, match="patient"):
        LatentTrajectory(
            points=(point,),
            disorder=LatentDisorderState(DisorderKind.HEALTHY, None, 0.0),
            events=(event,),
        )


@pytest.mark.parametrize(
    "event",
    [
        ClinicalEvent("syn-patient-a", 10**1000, "latent_onset", None, True),
        ClinicalEvent("syn-patient-a", 0, ["latent_onset"], None, True),  # type: ignore[arg-type]
        ClinicalEvent("syn-patient-a", 0, "wat", None, False),
        ClinicalEvent("syn-patient-a", 0, "latent_onset", "secret", True),
        ClinicalEvent("syn-patient-a", 0, "latent_onset", None, False),
    ],
)
def test_latent_trajectory_rejects_malformed_event_metadata(event: ClinicalEvent) -> None:
    point = LatentPoint("syn-patient-a", 730, 90.0, 16.0, 12.96, 0.0, 0.0)

    with pytest.raises((TypeError, ValueError)):
        LatentTrajectory(
            points=(point,),
            disorder=LatentDisorderState(DisorderKind.HEALTHY, None, 0.0),
            events=(event,),
        )


def test_latent_point_rejects_unsupported_age() -> None:
    with pytest.raises(ValueError, match="age_days"):
        LatentPoint("syn-patient-a", 10**1000, 90.0, 16.0, 12.96, 0.0, 0.0)
