from __future__ import annotations

from synthetic.models import (
    ClinicalEvent,
    DisorderKind,
    LatentDisorderState,
    LatentPoint,
    LatentTrajectory,
    PatientState,
    validate_disorder_event_trace,
)
from synthetic.native.anthropometry import (
    derive_weight_kg,
    require_finite_positive,
    require_finite_real,
)
from synthetic.native.clinical_modules import (
    ConstitutionalDelayConfig,
    ConstitutionalDelayModule,
    FamilialShortStatureConfig,
    FamilialShortStatureModule,
    GrowthDisorderModule,
    GrowthHormoneDeficiencyConfig,
    GrowthHormoneDeficiencyModule,
    HealthyGrowthConfig,
    HealthyGrowthModule,
)
from synthetic.native.healthy import HealthyKernel
from synthetic.randomness import NamedRandomStreams
from synthetic.references import generation_z_score

_BUILTIN_MODULE_CONTRACTS = (
    (HealthyGrowthModule, HealthyGrowthConfig, "healthy-growth-v1"),
    (
        FamilialShortStatureModule,
        FamilialShortStatureConfig,
        "familial-short-stature-v1",
    ),
    (ConstitutionalDelayModule, ConstitutionalDelayConfig, "constitutional-delay-v1"),
    (
        GrowthHormoneDeficiencyModule,
        GrowthHormoneDeficiencyConfig,
        "growth-hormone-deficiency-v1",
    ),
)


def validate_growth_disorder_module(module: object) -> None:
    if module is None:
        raise ValueError("module must be provided")
    if not isinstance(getattr(module, "kind", None), DisorderKind):
        raise TypeError("module must declare a DisorderKind")
    module_version = getattr(module, "module_version", None)
    if not isinstance(module_version, str) or not module_version.strip():
        raise TypeError("module must declare a nonempty string module_version")
    for method_name in (
        "sample_state",
        "height_z_delta",
        "bmi_z_delta",
        "events",
    ):
        if not callable(getattr(module, method_name, None)):
            raise TypeError(f"module must provide {method_name}")
    for module_type, config_type, expected_version in _BUILTIN_MODULE_CONTRACTS:
        if type(module) is module_type:
            config = getattr(module, "config", None)
            if type(config) is not config_type:
                raise TypeError(
                    f"built-in module config must be a {config_type.__name__}"
                )
            if (
                getattr(module, "module_version", None) != expected_version
                or getattr(config, "module_version", None) != expected_version
            ):
                raise ValueError("built-in module/config version mismatch")
            break


def validate_disorder_events(
    patient: PatientState,
    state: LatentDisorderState,
    events: tuple[ClinicalEvent, ...],
) -> None:
    if not isinstance(patient, PatientState):
        raise TypeError("patient must be a PatientState")
    if not isinstance(state, LatentDisorderState):
        raise TypeError("state must be a LatentDisorderState")
    if not isinstance(events, tuple):
        raise TypeError("module events must be a tuple of ClinicalEvent")
    for event in events:
        if not isinstance(event, ClinicalEvent):
            raise TypeError("module events must be ClinicalEvent instances")
    validate_disorder_event_trace(patient.patient_id, state, events)


class DisorderTrajectoryKernel:
    def __init__(self, healthy: HealthyKernel, module: GrowthDisorderModule) -> None:
        if not isinstance(healthy, HealthyKernel):
            raise TypeError("healthy must be a HealthyKernel")
        validate_growth_disorder_module(module)
        self.healthy = healthy
        self.module = module

    def generate(
        self,
        patient: PatientState,
        ages_days: tuple[int, ...],
        streams: NamedRandomStreams,
    ) -> LatentTrajectory:
        validate_growth_disorder_module(self.module)
        baseline = self.healthy.generate(patient, ages_days, streams)
        state = self.module.sample_state(patient, streams)
        if not isinstance(state, LatentDisorderState):
            raise TypeError("module must return a LatentDisorderState")
        if state.kind is not self.module.kind:
            raise ValueError("module state kind must match module kind")
        events = self.module.events(patient, state)
        if not isinstance(events, tuple):
            raise TypeError("module events must be a tuple of ClinicalEvent")
        validate_disorder_events(patient, state, events)
        if state.kind is DisorderKind.HEALTHY:
            return LatentTrajectory(baseline, state, events)

        points: list[LatentPoint] = []
        for point in baseline:
            height_z = require_finite_real(
                point.height_z + self._module_delta(state, point.age_days, metric="height"),
                "adjusted height z-score must be finite",
            )
            height_z = generation_z_score(
                self.healthy.reference,
                "height_cm",
                point.age_days,
                patient.reference_sex,
                height_z,
            )
            bmi_z = require_finite_real(
                point.bmi_z + self._module_delta(state, point.age_days, metric="BMI"),
                "adjusted BMI z-score must be finite",
            )
            bmi_z = generation_z_score(
                self.healthy.reference,
                "bmi",
                point.age_days,
                patient.reference_sex,
                bmi_z,
            )
            height_cm = require_finite_positive(
                self._reference_value(
                    "height_cm", point.age_days, patient.reference_sex, height_z
                ),
                "reference height must be finite and positive",
            )
            bmi = require_finite_positive(
                self._reference_value("bmi", point.age_days, patient.reference_sex, bmi_z),
                "reference BMI must be finite and positive",
            )
            points.append(
                LatentPoint(
                    patient_id=patient.patient_id,
                    age_days=point.age_days,
                    height_cm=height_cm,
                    bmi=bmi,
                    weight_kg=derive_weight_kg(bmi, height_cm),
                    height_z=height_z,
                    bmi_z=bmi_z,
                )
            )

        return LatentTrajectory(tuple(points), state, events)

    def _module_delta(
        self,
        state: LatentDisorderState,
        age_days: int,
        *,
        metric: str,
    ) -> float:
        message = f"module {metric} z-score delta must be finite"
        try:
            value = (
                self.module.height_z_delta(state, age_days)
                if metric == "height"
                else self.module.bmi_z_delta(state, age_days)
            )
        except (ArithmeticError, TypeError) as exc:
            raise ValueError(message) from exc
        return require_finite_real(value, message)

    def _reference_value(
        self,
        metric: str,
        age_days: int,
        reference_sex: str,
        z: float,
    ) -> float:
        try:
            return self.healthy.reference.value(metric, age_days, reference_sex, z)
        except (ArithmeticError, TypeError) as exc:
            raise ValueError(f"reference {metric} failed during evaluation") from exc
