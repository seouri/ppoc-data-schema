from __future__ import annotations

import math
from numbers import Real

from synthetic.models import (
    ClinicalEvent,
    DisorderKind,
    LatentDisorderState,
    LatentPoint,
    LatentTrajectory,
    PatientState,
)
from synthetic.native.clinical_modules import GrowthDisorderModule
from synthetic.native.healthy import HealthyKernel
from synthetic.randomness import NamedRandomStreams


def _finite_real(value: object, message: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(message)
    return float(value)


def _positive_reference_value(value: object, message: str) -> float:
    result = _finite_real(value, message)
    if result <= 0:
        raise ValueError(message)
    return result


def _validate_events(
    patient: PatientState,
    state: LatentDisorderState,
    events: tuple[ClinicalEvent, ...],
) -> None:
    previous_age = -1
    treatment_start_seen = False
    treatment_response_seen = False
    for event in events:
        if not isinstance(event, ClinicalEvent):
            raise TypeError("module events must be ClinicalEvent instances")
        if event.patient_id != patient.patient_id:
            raise ValueError("module event patient ID must match the requested patient")
        if isinstance(event.age_days, bool) or not isinstance(event.age_days, int) or event.age_days < 0:
            raise ValueError("module event age must be nonnegative")
        if event.age_days < previous_age:
            raise ValueError("module event ages must be nondecreasing")
        if treatment_response_seen:
            raise ValueError("no event may follow a treatment response")

        if event.event_type == "treatment_start":
            if (
                state.treatment_start_age_days is None
                or event.age_days != state.treatment_start_age_days
                or treatment_start_seen
            ):
                raise ValueError("treatment start event does not match the treatment schedule")
            treatment_start_seen = True
        elif event.event_type == "treatment_response":
            if (
                state.treatment_start_age_days is None
                or not treatment_start_seen
                or event.age_days <= state.treatment_start_age_days
                or treatment_response_seen
            ):
                raise ValueError("treatment response event does not match the treatment schedule")
            treatment_response_seen = True

        previous_age = event.age_days


class DisorderTrajectoryKernel:
    def __init__(self, healthy: HealthyKernel, module: GrowthDisorderModule) -> None:
        if not isinstance(healthy, HealthyKernel):
            raise TypeError("healthy must be a HealthyKernel")
        if module is None:
            raise ValueError("module must be provided")
        if not isinstance(getattr(module, "kind", None), DisorderKind):
            raise TypeError("module must declare a DisorderKind")
        for method_name in (
            "sample_state",
            "height_z_delta",
            "bmi_z_delta",
            "events",
        ):
            if not callable(getattr(module, method_name, None)):
                raise TypeError(f"module must provide {method_name}")
        self.healthy = healthy
        self.module = module

    def generate(
        self,
        patient: PatientState,
        ages_days: tuple[int, ...],
        streams: NamedRandomStreams,
    ) -> LatentTrajectory:
        baseline = self.healthy.generate(patient, ages_days, streams)
        state = self.module.sample_state(patient, streams)
        if not isinstance(state, LatentDisorderState):
            raise TypeError("module must return a LatentDisorderState")
        if state.kind is not self.module.kind:
            raise ValueError("module state kind must match module kind")

        points: list[LatentPoint] = []
        for point in baseline:
            height_z = _finite_real(
                point.height_z + _finite_real(
                    self.module.height_z_delta(state, point.age_days),
                    "module height z-score delta must be finite",
                ),
                "adjusted height z-score must be finite",
            )
            bmi_z = _finite_real(
                point.bmi_z + _finite_real(
                    self.module.bmi_z_delta(state, point.age_days),
                    "module BMI z-score delta must be finite",
                ),
                "adjusted BMI z-score must be finite",
            )
            height_cm = _positive_reference_value(
                self.healthy.reference.value(
                    "height_cm", point.age_days, patient.reference_sex, height_z
                ),
                "reference height must be finite and positive",
            )
            bmi = _positive_reference_value(
                self.healthy.reference.value(
                    "bmi", point.age_days, patient.reference_sex, bmi_z
                ),
                "reference BMI must be finite and positive",
            )
            points.append(
                LatentPoint(
                    patient_id=patient.patient_id,
                    age_days=point.age_days,
                    height_cm=height_cm,
                    bmi=bmi,
                    weight_kg=bmi * (height_cm / 100.0) ** 2,
                    height_z=height_z,
                    bmi_z=bmi_z,
                )
            )

        events = tuple(self.module.events(patient, state))
        _validate_events(patient, state, events)
        return LatentTrajectory(tuple(points), state, events)
