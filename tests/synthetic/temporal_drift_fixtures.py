"""Small typed fictional cohorts for temporal-drift metric tests."""

from __future__ import annotations

from synthetic.cohort import CalibrationSamplingProfile, CohortMember, NativeCohort
from synthetic.models import (
    AgeRegimeDisorderTrajectory,
    AgeRegimePoint,
    AgeRegimeState,
    AgeRegimeTrajectory,
    DisorderKind,
    GrowthRegime,
    LatentDisorderState,
)
from synthetic.native.observations import (
    RECORDED_EVENT_CODES,
    CensoringMode,
    EncounterType,
    MeasurementAvailability,
    MeasurementChannel,
    MeasurementObservation,
    ObservationFrame,
    ObservationTruth,
    ObservationWindow,
    ObservedVisit,
    RecordedEvent,
    RecordedEventKind,
)
from synthetic.native.resources import SyntheticDemographics
from synthetic.temporal_drift import TemporalDriftPolicy, TemporalWindowPolicy
from tests.synthetic.cohort_fixtures import aggregate_calibration_artifact


def temporal_window(
    window_id: str,
    lower_age_days: int,
    upper_age_days: int,
    **changes: object,
) -> TemporalWindowPolicy:
    values: dict[str, object] = {
        "window_id": window_id,
        "lower_age_days": lower_age_days,
        "upper_age_days": upper_age_days,
        "minimum_member_support": 2,
        "minimum_growth_points": 1,
        "minimum_visible_visits": 1,
        "minimum_growth_coverage": 0.5,
        "minimum_visible_visit_coverage": 0.5,
        "maximum_mean_inter_visit_days": 40.0,
        "maximum_visit_count_step": 0.5,
        "maximum_recorded_event_rate_step": 0.25,
    }
    values.update(changes)
    return TemporalWindowPolicy(**values)  # type: ignore[arg-type]


def temporal_policy(
    *windows: TemporalWindowPolicy,
    minimum_cohort_size: int = 2,
) -> TemporalDriftPolicy:
    configured_windows = windows or (
        temporal_window("z_early", 0, 100),
        temporal_window("a_late", 100, 200),
    )
    return TemporalDriftPolicy(
        policy_id="temporal-v1",
        policy_version="1",
        minimum_cohort_size=minimum_cohort_size,
        maximum_unevaluable_checks=2,
        windows=configured_windows,
    )


def temporal_member(
    member_number: int,
    *,
    point_ages: tuple[int, ...],
    visit_ages: tuple[int, ...] = (),
    event_ages: tuple[int, ...] = (),
) -> CohortMember:
    patient_id = f"syn-temporal-{member_number}"
    state = AgeRegimeState(
        "age-regimes-v1",
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        4_380,
        900,
        0.0,
        0.0,
    )
    points = tuple(
        AgeRegimePoint(
            patient_id,
            age_days,
            GrowthRegime.INFANCY,
            60.0,
            None,
            6.0,
            None,
        )
        for age_days in point_ages
    )
    trajectory = AgeRegimeDisorderTrajectory(
        AgeRegimeTrajectory(points, state),
        LatentDisorderState(DisorderKind.HEALTHY, None, 0.0),
        (),
    )
    measurements = (
        MeasurementObservation(
            MeasurementChannel.WEIGHT,
            MeasurementAvailability.OBSERVED,
            6.0,
        ),
    )
    visits = tuple(
        ObservedVisit(
            patient_id,
            f"syn-temporal-{member_number}-visit-{index}",
            age_days,
            EncounterType.ROUTINE,
            measurements,
        )
        for index, age_days in enumerate(visit_ages)
    )
    events = tuple(
        RecordedEvent(
            patient_id,
            age_days,
            RecordedEventKind.DIAGNOSIS,
            RECORDED_EVENT_CODES[RecordedEventKind.DIAGNOSIS],
        )
        for age_days in event_ages
    )
    window = ObservationWindow(0, 1_000, 1_000, CensoringMode.NONE)
    truth = ObservationTruth(patient_id, window, (), (), (), ())
    frame = ObservationFrame(
        patient_id,
        "observation-v1",
        window,
        visits,
        events,
        truth,
    )
    return CohortMember(
        SyntheticDemographics(patient_id),
        trajectory,
        frame,
        None,
    )


def temporal_cohort(*members: CohortMember) -> NativeCohort:
    calibration = CalibrationSamplingProfile.from_artifact(
        aggregate_calibration_artifact()
    )
    return NativeCohort("development-v1", 7, tuple(members), calibration)
