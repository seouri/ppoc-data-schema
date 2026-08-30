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
