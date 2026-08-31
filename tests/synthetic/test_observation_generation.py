from __future__ import annotations

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
)
from synthetic.native.observations import (
    CensoringMode,
    MeasurementAvailability,
    MeasurementChannel,
    ObservationPolicy,
    RecordedEventKind,
    generate_observation_frame,
)
from synthetic.randomness import NamedRandomStreams

PATIENT_ID = "syn-observation-patient"


def _trajectory(*, events: tuple[ClinicalEvent, ...] = ()) -> AgeRegimeDisorderTrajectory:
    state = AgeRegimeState(
        "age-regimes-v1",
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        4380,
        900,
        0.0,
        0.0,
    )
    points = (
        AgeRegimePoint(
            PATIENT_ID,
            100,
            GrowthRegime.INFANCY,
            60.0,
            None,
            6.0,
            None,
            40.0,
        ),
        AgeRegimePoint(
            PATIENT_ID,
            730,
            GrowthRegime.TRANSITION,
            80.7,
            80.0,
            10.24,
            16.0,
            44.0,
        ),
        AgeRegimePoint(
            PATIENT_ID,
            1000,
            GrowthRegime.CHILDHOOD,
            None,
            90.0,
            11.34,
            14.0,
            None,
        ),
        AgeRegimePoint(
            PATIENT_ID,
            1500,
            GrowthRegime.CHILDHOOD,
            None,
            100.0,
            12.5,
            12.5,
            None,
        ),
        AgeRegimePoint(
            PATIENT_ID,
            2000,
            GrowthRegime.PUBERTY,
            None,
            110.0,
            14.52,
            12.0,
            None,
        ),
    )
    physiology = AgeRegimeTrajectory(points, state)
    disorder = LatentDisorderState(DisorderKind.HEALTHY, None, 0.0)
    return AgeRegimeDisorderTrajectory(physiology, disorder, events)


def _policy(**changes: object) -> ObservationPolicy:
    values: dict[str, object] = {
        "policy_version": "observation-v1",
        "window_start_age_days": 0,
        "window_end_age_days": 2200,
        "censoring_mode": CensoringMode.NONE,
        "censor_age_days": None,
        "visit_probability": 1.0,
        "length_availability_probability": 1.0,
        "height_availability_probability": 1.0,
        "weight_availability_probability": 1.0,
        "head_circumference_availability_probability": 1.0,
        "length_error_sd_cm": 0.0,
        "height_error_sd_cm": 0.0,
        "weight_error_sd_kg": 0.0,
        "head_circumference_error_sd_cm": 0.0,
        "rounding_digits": None,
        "recognition_probability": 0.0,
        "diagnosis_probability": 0.0,
        "recognition_delay_days": 0,
    }
    values.update(changes)
    return ObservationPolicy(**values)  # type: ignore[arg-type]


def _event_trajectory() -> AgeRegimeDisorderTrajectory:
    trajectory = _trajectory(
        events=(
            ClinicalEvent(PATIENT_ID, 500, "latent_onset", None, True),
            ClinicalEvent(PATIENT_ID, 600, "observable_phenotype", None, False),
            ClinicalEvent(PATIENT_ID, 700, "recognition_opportunity", None, False),
            ClinicalEvent(PATIENT_ID, 1200, "workup", None, False),
            ClinicalEvent(PATIENT_ID, 1500, "recorded_diagnosis", None, False),
            ClinicalEvent(PATIENT_ID, 1800, "treatment_start", None, False),
            ClinicalEvent(PATIENT_ID, 1900, "treatment_response", None, False),
        )
    )
    return dataclasses.replace(
        trajectory,
        disorder=LatentDisorderState(DisorderKind.FAMILIAL_SHORT_STATURE, 500, 0.8),
    )


def test_generation_applies_effective_censoring_and_stable_opportunity_indices() -> None:
    policy = _policy(
        window_start_age_days=600,
        window_end_age_days=1800,
        censoring_mode=CensoringMode.LOST_TO_FOLLOW_UP,
        censor_age_days=1600,
    )
    frame = generate_observation_frame(
        _trajectory(), policy, NamedRandomStreams(20260831, 0)
    )

    assert frame.window.start_age_days == 600
    assert frame.window.effective_end_age_days == 1600
    assert [visit.age_days for visit in frame.visits] == [730, 1000, 1500]
    assert [item.source_point_index for item in frame.truth.opportunities] == [1, 2, 3]
    assert [item.realized for item in frame.truth.opportunities] == [True, True, True]
    assert all(600 <= visit.age_days < 1600 for visit in frame.visits)


def test_generation_uses_independent_named_streams_and_replays_identically() -> None:
    class RecordingStreams(NamedRandomStreams):
        def __init__(self, run_seed: int, patient_index: int) -> None:
            super().__init__(run_seed, patient_index)
            self.names: list[str] = []

        def generator(self, name: str):
            self.names.append(name)
            return super().generator(name)

    streams = RecordingStreams(20260831, 1)
    policy = _policy(
        visit_probability=0.5,
        length_availability_probability=0.5,
        height_availability_probability=0.5,
        weight_availability_probability=0.5,
        head_circumference_availability_probability=0.5,
        length_error_sd_cm=0.1,
        height_error_sd_cm=0.1,
        weight_error_sd_kg=0.1,
        head_circumference_error_sd_cm=0.1,
        recognition_probability=0.5,
        diagnosis_probability=0.5,
    )
    first = generate_observation_frame(_event_trajectory(), policy, streams)
    replay = generate_observation_frame(
        _event_trajectory(), policy, NamedRandomStreams(20260831, 1)
    )

    assert first.to_mapping() == replay.to_mapping()
    assert first.truth.truth_hash == replay.truth.truth_hash
    assert first.truth.latent_trajectory_hash == replay.truth.latent_trajectory_hash
    assert set(streams.names) == {
        "observation.window",
        "observation.censoring",
        "observation.visit.routine",
        "observation.measurement-availability",
        "observation.measurement-error",
        "observation.recognition",
        "observation.recorded-event",
    }


def test_generation_keeps_regime_channel_applicability_and_derives_bmi() -> None:
    frame = generate_observation_frame(
        _trajectory(), _policy(rounding_digits=2), NamedRandomStreams(3, 0)
    )

    by_age = {visit.age_days: {item.channel: item for item in visit.measurements} for visit in frame.visits}
    assert by_age[100][MeasurementChannel.LENGTH].availability is MeasurementAvailability.OBSERVED
    assert by_age[100][MeasurementChannel.HEIGHT].availability is MeasurementAvailability.NOT_APPLICABLE
    assert by_age[100][MeasurementChannel.BMI].availability is MeasurementAvailability.NOT_APPLICABLE
    assert by_age[730][MeasurementChannel.LENGTH].availability is MeasurementAvailability.OBSERVED
    assert by_age[730][MeasurementChannel.HEIGHT].availability is MeasurementAvailability.OBSERVED
    assert by_age[730][MeasurementChannel.HEAD_CIRCUMFERENCE].availability is MeasurementAvailability.OBSERVED
    assert by_age[1000][MeasurementChannel.LENGTH].availability is MeasurementAvailability.NOT_APPLICABLE
    assert by_age[1000][MeasurementChannel.HEIGHT].availability is MeasurementAvailability.OBSERVED
    assert by_age[1000][MeasurementChannel.HEAD_CIRCUMFERENCE].availability is MeasurementAvailability.NOT_APPLICABLE

    height = by_age[1000][MeasurementChannel.HEIGHT].recorded_value
    weight = by_age[1000][MeasurementChannel.WEIGHT].recorded_value
    bmi = by_age[1000][MeasurementChannel.BMI].recorded_value
    assert height is not None and weight is not None and bmi is not None
    assert bmi == pytest.approx(weight / (height / 100.0) ** 2)
    assert frame.truth.measurement_truth
    assert all(item.channel is not MeasurementChannel.BMI for item in frame.truth.measurement_truth)


def test_generation_applies_additive_error_before_rounding_and_never_clips() -> None:
    policy = _policy(
        height_error_sd_cm=0.0,
        weight_error_sd_kg=0.0,
        rounding_digits=1,
    )
    frame = generate_observation_frame(
        _trajectory(), policy, NamedRandomStreams(4, 0)
    )
    visit = next(item for item in frame.visits if item.age_days == 1000)
    height = next(item for item in visit.measurements if item.channel is MeasurementChannel.HEIGHT)
    weight = next(item for item in visit.measurements if item.channel is MeasurementChannel.WEIGHT)
    assert height.recorded_value == 90.0
    assert weight.recorded_value == 11.3

    class ZeroErrorStreams(NamedRandomStreams):
        def generator(self, name: str):
            if name == "observation.measurement-error":
                class FixedErrorGenerator:
                    def random(self) -> float:
                        return 0.0

                    def normal(self, *args: object, **kwargs: object) -> float:
                        del args, kwargs
                        return -100.0

                return FixedErrorGenerator()
            return super().generator(name)

    with pytest.raises(ValueError, match="positive"):
        generate_observation_frame(
            _trajectory(), _policy(height_error_sd_cm=1.0), ZeroErrorStreams(5, 0)
        )


def test_generation_projects_recognition_workup_and_diagnosis_with_delay() -> None:
    policy = _policy(
        recognition_probability=1.0,
        diagnosis_probability=1.0,
        recognition_delay_days=50,
    )
    frame = generate_observation_frame(
        _event_trajectory(), policy, NamedRandomStreams(6, 0)
    )

    assert [event.event_kind for event in frame.events] == [
        RecordedEventKind.RECOGNITION,
        RecordedEventKind.WORKUP,
        RecordedEventKind.DIAGNOSIS,
    ]
    assert [event.age_days for event in frame.events] == [1000, 1500, 1500]
    assert all(event.opportunity_index is not None for event in frame.events)
    assert all(event.age_days >= 700 + 50 for event in frame.events)
    assert all(event.age_days >= frame.visits[event.opportunity_index].age_days for event in frame.events)


def test_generation_suppresses_hidden_and_deferred_events() -> None:
    policy = _policy(recognition_probability=1.0, diagnosis_probability=1.0)
    frame = generate_observation_frame(
        _event_trajectory(), policy, NamedRandomStreams(7, 0)
    )

    assert all(event.event_kind not in {RecordedEventKind.RECOGNITION} or event.age_days > 500 for event in frame.events)
    assert any(event.event_kind is RecordedEventKind.DIAGNOSIS for event in frame.events)
    assert any(event.event_kind is RecordedEventKind.WORKUP for event in frame.events)
    assert all(source.event_type not in {"latent_onset", "treatment_start", "treatment_response"}
               for source in frame.truth.source_events if frame.truth.event_decisions[frame.truth.source_events.index(source)].recorded)


@pytest.mark.parametrize("bad_value", [-100.0, math.nan, math.inf])
def test_generation_rejects_nonpositive_or_nonfinite_post_error_measurements(
    bad_value: float,
) -> None:
    class BadErrorStreams(NamedRandomStreams):
        def generator(self, name: str):
            if name == "observation.measurement-error":
                class FixedErrorGenerator:
                    def random(self) -> float:
                        return 0.0

                    def normal(self, *args: object, **kwargs: object) -> float:
                        del args, kwargs
                        return bad_value

                return FixedErrorGenerator()
            return super().generator(name)

    with pytest.raises(ValueError, match="finite|positive"):
        generate_observation_frame(
            _trajectory(),
            _policy(height_error_sd_cm=1.0, rounding_digits=None),
            BadErrorStreams(8, 0),
        )


def test_generation_rejects_nontrajectory_and_unknown_source_events() -> None:
    with pytest.raises(TypeError, match="trajectory"):
        generate_observation_frame(object(), _policy(), NamedRandomStreams(9, 0))  # type: ignore[arg-type]

    malformed = dataclasses.replace(
        _trajectory(),
        events=(ClinicalEvent(PATIENT_ID, 500, "not-native", None, False),),
    )
    with pytest.raises(ValueError, match="event type"):
        generate_observation_frame(malformed, _policy(), NamedRandomStreams(9, 0))
