"""Small typed fictional cohorts for task-utility metric tests."""

from __future__ import annotations

import dataclasses

from synthetic.cohort import CalibrationSamplingProfile, CohortMember, NativeCohort
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
    EncounterType,
    MeasurementAvailability,
    MeasurementChannel,
    MeasurementObservation,
    ObservationFrame,
    ObservationTruth,
    ObservationWindow,
    ObservedVisit,
    RecordedEventKind,
)
from synthetic.native.resources import (
    BASE_RESOURCE_NAMES,
    ClinicalDescendant,
    ObservedResourceBundle,
    ResourceRow,
    ResourceShape,
    ResourceSpec,
    SyntheticDemographics,
)
from synthetic.task_utility import TaskPrediction, TaskUtilityPolicy
from tests.synthetic.cohort_fixtures import aggregate_calibration_artifact


def task_policy(**changes: object) -> TaskUtilityPolicy:
    values: dict[str, object] = {
        "policy_id": "task-utility-v1",
        "policy_version": "1",
        "minimum_cohort_size": 4,
        "minimum_evaluable_members": 3,
        "minimum_class_support": 1,
        "maximum_unevaluable_members": 0,
        "require_probability_scores": True,
        "minimum_sensitivity": 0.5,
        "minimum_specificity": 0.5,
        "minimum_auroc": 0.8,
        "maximum_brier_score": 0.2,
        "subgroup_dimensions": (),
    }
    values.update(changes)
    return TaskUtilityPolicy(**values)  # type: ignore[arg-type]


def task_member(
    member_number: int,
    kind: DisorderKind,
    *,
    sex: str = "U",
) -> CohortMember:
    patient_id = f"syn-task-utility-{member_number}"
    point = AgeRegimePoint(
        patient_id,
        100,
        GrowthRegime.INFANCY,
        61.0 + member_number / 10,
        None,
        6.0 + member_number / 10,
        None,
    )
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
    disorder = LatentDisorderState(
        kind,
        None if kind is DisorderKind.HEALTHY else 50,
        0.0 if kind is DisorderKind.HEALTHY else 0.5,
    )
    trajectory = AgeRegimeDisorderTrajectory(
        AgeRegimeTrajectory((point,), state),
        disorder,
        (
            ()
            if kind is DisorderKind.HEALTHY
            else (ClinicalEvent(patient_id, 50, "latent_onset", None, True),)
        ),
    )
    window = ObservationWindow(0, 200, 200, CensoringMode.NONE)
    visit = ObservedVisit(
        patient_id,
        f"syn-task-utility-{member_number}-visit-1",
        100,
        EncounterType.ROUTINE,
        (
            MeasurementObservation(
                MeasurementChannel.WEIGHT,
                MeasurementAvailability.OBSERVED,
                6.0 + member_number / 10,
            ),
        ),
    )
    truth = ObservationTruth(patient_id, window, (), (), (), ())
    frame = ObservationFrame(
        patient_id,
        "observation-v1",
        window,
        (visit,),
        (),
        truth,
    )
    return CohortMember(
        SyntheticDemographics(patient_id, sex=sex),
        trajectory,
        frame,
        None,
    )


def balanced_task_cohort() -> NativeCohort:
    members = (
        task_member(1, DisorderKind.GROWTH_HORMONE_DEFICIENCY, sex="F"),
        task_member(2, DisorderKind.CONSTITUTIONAL_DELAY, sex="M"),
        task_member(3, DisorderKind.HEALTHY, sex="F"),
        task_member(4, DisorderKind.HEALTHY, sex="M"),
    )
    return task_cohort(*members)


def task_cohort(*members: CohortMember) -> NativeCohort:
    calibration = CalibrationSamplingProfile.from_artifact(
        aggregate_calibration_artifact()
    )
    return NativeCohort("development-v1", 7, tuple(members), calibration)


def task_member_with_bundle(member_number: int, kind: DisorderKind) -> CohortMember:
    member = task_member(member_number, kind)
    shape = ResourceShape(
        tuple(ResourceSpec(name, ("patient_id",)) for name in BASE_RESOURCE_NAMES)
    )
    rows = {
        name: (ResourceRow(name, (("patient_id", member.demographics.patient_id),)),)
        for name in BASE_RESOURCE_NAMES
    }
    source_frame = dataclasses.replace(member.frame)
    descendant = ClinicalDescendant(
        patient_id=member.demographics.patient_id,
        visit_id=member.frame.visits[0].visit_id,
        age_days=member.frame.visits[0].age_days,
        event_kind=RecordedEventKind.RECOGNITION,
        code="SYN-GROWTH-RECOGNITION",
    )
    bundle = ObservedResourceBundle(
        patient_id=member.demographics.patient_id,
        shape=shape,
        rows=rows,
        clinical_descendants=(descendant,),
        source_frame=source_frame,
    )
    return CohortMember(
        demographics=member.demographics,
        trajectory=member.trajectory,
        frame=member.frame,
        bundle=bundle,
    )


def scored_task_predictions() -> tuple[TaskPrediction, ...]:
    return (
        TaskPrediction(True, 0.75),
        TaskPrediction(False, 0.5),
        TaskPrediction(True, 0.5),
        TaskPrediction(False, 0.25),
    )
