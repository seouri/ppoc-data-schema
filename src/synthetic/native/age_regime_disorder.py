"""Evaluator-only composition of age-regime physiology and disorder effects."""

from __future__ import annotations

import dataclasses
import math
from itertools import pairwise
from numbers import Real

from synthetic.models import (
    AgeRegimeDisorderTrajectory,
    AgeRegimePoint,
    AgeRegimeState,
    AgeRegimeTrajectory,
    DisorderKind,
    GrowthRegime,
    LatentDisorderState,
    PatientState,
)
from synthetic.native.age_regimes import AgeRegimeTrajectoryKernel
from synthetic.native.clinical_modules import GrowthDisorderModule
from synthetic.native.trajectories import (
    validate_disorder_events,
    validate_growth_disorder_module,
)
from synthetic.randomness import NamedRandomStreams


def _finite_real(value: object, message: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(message)  # noqa: TRY004
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(message) from exc
    if not math.isfinite(result):
        raise ValueError(message)
    return result


def _positive_real(value: object, message: str) -> float:
    result = _finite_real(value, message)
    if result <= 0:
        raise ValueError(message)
    return result


def _derived_bmi(weight_kg: float, height_cm: float) -> float:
    message = "derived BMI must be finite and positive"
    try:
        height_m = height_cm / 100.0
        value = weight_kg / (height_m * height_m)
    except ArithmeticError as exc:
        raise ValueError(message) from exc
    return _positive_real(value, message)


def _derived_weight(bmi: float, height_cm: float) -> float:
    message = "derived weight must be finite and positive"
    try:
        height_m = height_cm / 100.0
        value = bmi * height_m * height_m
    except ArithmeticError as exc:
        raise ValueError(message) from exc
    return _positive_real(value, message)


class AgeRegimeDisorderKernel:
    """Compose deterministic disorder effects with age-regime physiology."""

    def __init__(
        self,
        physiology: AgeRegimeTrajectoryKernel,
        module: GrowthDisorderModule,
    ) -> None:
        if not isinstance(physiology, AgeRegimeTrajectoryKernel):
            raise TypeError("physiology must be an AgeRegimeTrajectoryKernel")
        validate_growth_disorder_module(module)
        self.physiology = physiology
        self.module = module

    def generate(
        self,
        patient: PatientState,
        ages_days: tuple[int, ...],
        streams: NamedRandomStreams,
    ) -> AgeRegimeDisorderTrajectory:
        validate_growth_disorder_module(self.module)
        physiology_state = self.physiology.sample_state(streams)
        disorder_state = self.module.sample_state(patient, streams)
        if not isinstance(disorder_state, LatentDisorderState):
            raise TypeError("module must return a LatentDisorderState")
        if disorder_state.kind is not self.module.kind:
            raise ValueError("module state kind must match module kind")

        adjusted_state = self._adjusted_state(physiology_state, disorder_state)
        baseline = self.physiology.generate(
            patient,
            ages_days,
            streams,
            state=adjusted_state,
        )
        if disorder_state.kind is DisorderKind.CONSTITUTIONAL_DELAY:
            physiology = baseline
        else:
            points = self._adjust_points(patient, baseline, disorder_state)
            self._validate_adjusted_transition_continuity(
                points,
                patient,
                adjusted_state,
                disorder_state,
            )
            physiology = AgeRegimeTrajectory(tuple(points), adjusted_state)

        events = tuple(self.module.events(patient, disorder_state))
        validate_disorder_events(patient, disorder_state, events)
        return AgeRegimeDisorderTrajectory(physiology, disorder_state, events)

    def _adjusted_state(
        self,
        state: AgeRegimeState,
        disorder_state: LatentDisorderState,
    ) -> AgeRegimeState:
        if disorder_state.kind is not DisorderKind.CONSTITUTIONAL_DELAY:
            return state
        try:
            adjusted_onset = state.puberty_onset_age_days + disorder_state.puberty_delay_days
        except ArithmeticError as exc:
            raise ValueError("adjusted puberty onset must be a nonnegative integer") from exc
        return dataclasses.replace(
            state,
            puberty_onset_age_days=adjusted_onset,
        )

    def _module_delta(
        self,
        state: LatentDisorderState,
        age_days: int,
        *,
        metric: str,
    ) -> float:
        message = f"module {metric} z-score delta must be finite"
        try:
            if metric == "height":
                value = self.module.height_z_delta(state, age_days)
            else:
                value = self.module.bmi_z_delta(state, age_days)
        except ArithmeticError as exc:
            raise ValueError(message) from exc
        return _finite_real(value, message)

    def _adjusted_z(
        self,
        baseline_z: object,
        state: LatentDisorderState,
        age_days: int,
        *,
        metric: str,
    ) -> float:
        baseline = _finite_real(
            baseline_z,
            f"baseline {metric} z-score must be finite",
        )
        delta = self._module_delta(state, age_days, metric=metric)
        message = f"adjusted {metric} z-score must be finite"
        try:
            value = baseline + delta
        except ArithmeticError as exc:
            raise ValueError(message) from exc
        return _finite_real(value, message)

    def _reference_value(
        self,
        metric: str,
        age_days: int,
        patient: PatientState,
        z: float,
        *,
        label: str,
    ) -> float:
        message = f"reference {label} must be finite and positive"
        try:
            value = self.physiology.reference.value(
                metric,
                age_days,
                patient.reference_sex,
                z,
            )
        except ArithmeticError as exc:
            raise ValueError(message) from exc
        return _positive_real(value, message)

    def _adjust_points(
        self,
        patient: PatientState,
        baseline: AgeRegimeTrajectory,
        disorder_state: LatentDisorderState,
    ) -> list[AgeRegimePoint]:
        values = [self._adjust_point(patient, point, disorder_state) for point in baseline.points]
        return self._with_recomputed_velocities(values)

    def _adjust_point(
        self,
        patient: PatientState,
        point: AgeRegimePoint,
        disorder_state: LatentDisorderState,
    ) -> AgeRegimePoint:
        if point.regime in (GrowthRegime.INFANCY, GrowthRegime.TRANSITION):
            return self._adjust_pre_transition_point(patient, point, disorder_state)
        return self._adjust_post_transition_point(patient, point, disorder_state)

    def _adjust_pre_transition_point(
        self,
        patient: PatientState,
        point: AgeRegimePoint,
        disorder_state: LatentDisorderState,
    ) -> AgeRegimePoint:
        length_z = self._adjusted_z(
            point.length_z,
            disorder_state,
            point.age_days,
            metric="height",
        )
        weight_z = self._adjusted_z(
            point.weight_z,
            disorder_state,
            point.age_days,
            metric="BMI",
        )
        length_cm = self._reference_value(
            "length_cm",
            point.age_days,
            patient,
            length_z,
            label="length",
        )
        weight_kg = self._reference_value(
            "weight_kg",
            point.age_days,
            patient,
            weight_z,
            label="weight",
        )

        height_cm: float | None = None
        bmi: float | None = None
        height_z: float | None = None
        if point.regime is GrowthRegime.TRANSITION:
            message = "converted standing height must be finite and positive"
            try:
                converted_height = length_cm - self.physiology.config.length_to_height_offset_cm
            except ArithmeticError as exc:
                raise ValueError(message) from exc
            height_cm = _positive_real(converted_height, message)
            bmi = _derived_bmi(weight_kg, height_cm)
            height_z = length_z

        return AgeRegimePoint(
            patient_id=point.patient_id,
            age_days=point.age_days,
            regime=point.regime,
            length_cm=length_cm,
            height_cm=height_cm,
            weight_kg=weight_kg,
            bmi=bmi,
            head_circumference_cm=point.head_circumference_cm,
            length_z=length_z,
            height_z=height_z,
            weight_z=weight_z,
            bmi_z=None,
        )

    def _adjust_post_transition_point(
        self,
        patient: PatientState,
        point: AgeRegimePoint,
        disorder_state: LatentDisorderState,
    ) -> AgeRegimePoint:
        height_z = self._adjusted_z(
            point.height_z,
            disorder_state,
            point.age_days,
            metric="height",
        )
        bmi_z = self._adjusted_z(
            point.bmi_z,
            disorder_state,
            point.age_days,
            metric="BMI",
        )
        height_cm = self._reference_value(
            "height_cm",
            point.age_days,
            patient,
            height_z,
            label="height",
        )
        bmi = self._reference_value(
            "bmi",
            point.age_days,
            patient,
            bmi_z,
            label="BMI",
        )
        weight_kg = _derived_weight(bmi, height_cm)
        return AgeRegimePoint(
            patient_id=point.patient_id,
            age_days=point.age_days,
            regime=point.regime,
            length_cm=None,
            height_cm=height_cm,
            weight_kg=weight_kg,
            bmi=bmi,
            head_circumference_cm=point.head_circumference_cm,
            length_z=None,
            height_z=height_z,
            weight_z=None,
            bmi_z=bmi_z,
        )

    def _with_recomputed_velocities(
        self,
        points: list[AgeRegimePoint],
    ) -> list[AgeRegimePoint]:
        adjusted: list[AgeRegimePoint] = []
        previous_age: int | None = None
        previous_size: float | None = None
        previous_weight: float | None = None
        for point in points:
            comparable_size = point.height_cm
            if comparable_size is None:
                message = "derived comparable body size must be finite and positive"
                try:
                    converted_size = (
                        point.length_cm - self.physiology.config.length_to_height_offset_cm
                    )
                except (ArithmeticError, TypeError) as exc:
                    raise ValueError(message) from exc
                comparable_size = _positive_real(converted_size, message)
            else:
                comparable_size = _positive_real(
                    comparable_size,
                    "derived comparable body size must be finite and positive",
                )
            weight_kg = _positive_real(
                point.weight_kg,
                "derived weight must be finite and positive",
            )

            height_velocity: float | None = None
            weight_velocity: float | None = None
            if previous_age is not None:
                try:
                    scale = 365.25 / (point.age_days - previous_age)
                    height_velocity = (comparable_size - previous_size) * scale
                    weight_velocity = (weight_kg - previous_weight) * scale
                except (ArithmeticError, TypeError) as exc:
                    raise ValueError("derived velocities must be finite") from exc
                height_velocity = _finite_real(
                    height_velocity,
                    "derived velocities must be finite",
                )
                weight_velocity = _finite_real(
                    weight_velocity,
                    "derived velocities must be finite",
                )

            adjusted.append(
                dataclasses.replace(
                    point,
                    height_velocity_cm_per_year=height_velocity,
                    weight_velocity_kg_per_year=weight_velocity,
                )
            )
            previous_age = point.age_days
            previous_size = comparable_size
            previous_weight = weight_kg
        return adjusted

    def _validate_adjusted_transition_continuity(
        self,
        points: list[AgeRegimePoint],
        patient: PatientState,
        state: AgeRegimeState,
        disorder_state: LatentDisorderState,
    ) -> None:
        transition_end = (
            self.physiology.config.transition_age_days
            + self.physiology.config.transition_window_days
        )
        for previous, current in pairwise(points):
            if previous.age_days <= transition_end < current.age_days:
                comparison_age = transition_end + 1
                adjusted_z = self._adjusted_z(
                    state.childhood_height_z,
                    disorder_state,
                    comparison_age,
                    metric="height",
                )
                length_cm = self._reference_value(
                    "length_cm",
                    comparison_age,
                    patient,
                    adjusted_z,
                    label="length",
                )
                message = "converted standing height must be finite and positive"
                try:
                    converted_value = length_cm - self.physiology.config.length_to_height_offset_cm
                except ArithmeticError as exc:
                    raise ValueError(message) from exc
                converted_height = _positive_real(converted_value, message)
                standing_height = self._reference_value(
                    "height_cm",
                    comparison_age,
                    patient,
                    adjusted_z,
                    label="height",
                )
                try:
                    discontinuity = abs(standing_height - converted_height)
                except ArithmeticError as exc:
                    raise ValueError("transition discontinuity must be finite") from exc
                discontinuity = _finite_real(
                    discontinuity,
                    "transition discontinuity must be finite",
                )
                if discontinuity > self.physiology.config.max_transition_discontinuity_cm:
                    raise ValueError("transition discontinuity exceeds configured tolerance")
