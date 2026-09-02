import dataclasses
import math

import pytest

from synthetic.models import (
    AgeRegimeState,
    ClinicalEvent,
    DisorderKind,
    LatentDisorderState,
    PatientState,
)
from synthetic.native.age_regime_disorder import AgeRegimeDisorderKernel
from synthetic.native.age_regimes import AgeRegimeConfig, AgeRegimeTrajectoryKernel
from synthetic.native.clinical_modules import (
    ConstitutionalDelayConfig,
    ConstitutionalDelayModule,
    FamilialShortStatureConfig,
    FamilialShortStatureModule,
    GrowthHormoneDeficiencyConfig,
    GrowthHormoneDeficiencyModule,
    HealthyGrowthModule,
)
from synthetic.randomness import NamedRandomStreams
from tests.synthetic.fakes import RegimeLinearTestReference

PATIENT = PatientState("syn-patient-a", "F", "F")
AGES = (0, 365, 699, 730, 760, 761, 3000, 4380, 5281, 7000)


class ZeroGenerationZReference(RegimeLinearTestReference):
    def generation_z_score(
        self, metric: str, age_days: int, reference_sex: str, z: float
    ) -> float:
        del metric, age_days, reference_sex, z
        return 0.0


class HalfGenerationZReference(RegimeLinearTestReference):
    def generation_z_score(
        self, metric: str, age_days: int, reference_sex: str, z: float
    ) -> float:
        del metric, age_days, reference_sex
        return z / 2.0


class FixedModule:
    module_version = "fixed-test-v1"

    def __init__(
        self,
        state: object,
        *,
        kind: DisorderKind = DisorderKind.HEALTHY,
        height_delta: object = 0.0,
        bmi_delta: object = 0.0,
        events: tuple[ClinicalEvent, ...] = (),
    ) -> None:
        self.kind = kind
        self.state = state
        self.height_delta = height_delta
        self.bmi_delta = bmi_delta
        self._events = events

    def sample_state(self, patient: PatientState, streams: NamedRandomStreams) -> object:
        del patient, streams
        return self.state

    def height_z_delta(self, state: LatentDisorderState, age_days: int) -> object:
        del state, age_days
        return self.height_delta

    def bmi_z_delta(self, state: LatentDisorderState, age_days: int) -> object:
        del state, age_days
        return self.bmi_delta

    def events(
        self, patient: PatientState, state: LatentDisorderState
    ) -> tuple[ClinicalEvent, ...]:
        del patient, state
        return self._events


def test_healthy_composition_matches_age_regime_physiology() -> None:
    physiology = AgeRegimeTrajectoryKernel(RegimeLinearTestReference())
    baseline = physiology.generate(PATIENT, AGES, NamedRandomStreams(7, 0))
    result = AgeRegimeDisorderKernel(physiology, HealthyGrowthModule()).generate(
        PATIENT, AGES, NamedRandomStreams(7, 0)
    )

    assert result.physiology == baseline
    assert result.disorder.kind is DisorderKind.HEALTHY
    assert result.events == ()


def test_generation_hook_records_effective_z_scores_after_disorder_composition() -> None:
    result = AgeRegimeDisorderKernel(
        AgeRegimeTrajectoryKernel(ZeroGenerationZReference()), HealthyGrowthModule()
    ).generate(PATIENT, AGES, NamedRandomStreams(7, 0))

    for point in result.physiology.points:
        for score in (point.length_z, point.height_z, point.weight_z, point.bmi_z):
            if score is not None:
                assert score == 0.0


def test_healthy_age_regime_composition_applies_generation_hook_once() -> None:
    physiology = AgeRegimeTrajectoryKernel(HalfGenerationZReference())
    baseline = physiology.generate(PATIENT, AGES, NamedRandomStreams(7, 0))
    result = AgeRegimeDisorderKernel(physiology, HealthyGrowthModule()).generate(
        PATIENT, AGES, NamedRandomStreams(7, 0)
    )

    assert result.physiology == baseline


def test_nonhealthy_age_regime_composition_applies_generation_hook_after_effect() -> None:
    reference = HalfGenerationZReference()
    physiology = AgeRegimeTrajectoryKernel(reference)
    baseline = physiology.generate(PATIENT, AGES, NamedRandomStreams(7, 0))
    module = FamilialShortStatureModule(
        FamilialShortStatureConfig(severity_min=0.8, severity_max=0.8)
    )
    result = AgeRegimeDisorderKernel(physiology, module).generate(
        PATIENT, AGES, NamedRandomStreams(7, 0)
    )

    assert result.physiology.points[-1].height_z == pytest.approx(
        (baseline.points[-1].height_z - 0.8) / 2.0
    )


@pytest.mark.parametrize(
    "module",
    [
        FamilialShortStatureModule(
            FamilialShortStatureConfig(severity_min=0.0, severity_max=0.0)
        ),
        GrowthHormoneDeficiencyModule(
            GrowthHormoneDeficiencyConfig(
                onset_min_age_days=730,
                onset_max_age_days=730,
                severity_min=0.0,
                severity_max=0.0,
            )
        ),
    ],
    ids=["familial-short-stature", "growth-hormone-deficiency"],
)
def test_zero_effect_nonhealthy_composition_preserves_exact_baseline(module: object) -> None:
    physiology = AgeRegimeTrajectoryKernel(HalfGenerationZReference())
    baseline = physiology.generate(PATIENT, AGES, NamedRandomStreams(7, 0))

    result = AgeRegimeDisorderKernel(physiology, module).generate(
        PATIENT, AGES, NamedRandomStreams(7, 0)
    )

    assert result.physiology == baseline


def test_familial_effect_preserves_identities_across_regimes() -> None:
    physiology = AgeRegimeTrajectoryKernel(RegimeLinearTestReference())
    healthy = AgeRegimeDisorderKernel(physiology, HealthyGrowthModule()).generate(
        PATIENT, AGES, NamedRandomStreams(8, 0)
    )
    familial = AgeRegimeDisorderKernel(
        physiology,
        FamilialShortStatureModule(FamilialShortStatureConfig(severity_min=0.8, severity_max=0.8)),
    ).generate(PATIENT, AGES, NamedRandomStreams(8, 0))

    for base, adjusted in zip(healthy.physiology.points, familial.physiology.points, strict=True):
        if base.length_z is not None:
            assert adjusted.length_z < base.length_z
        if base.height_z is not None:
            assert adjusted.height_z < base.height_z
        if adjusted.bmi is not None and adjusted.height_cm is not None:
            assert adjusted.weight_kg == pytest.approx(
                adjusted.bmi * (adjusted.height_cm / 100.0) ** 2
            )


def test_constitutional_delay_shifts_puberty_once() -> None:
    class FixedOnsetKernel(AgeRegimeTrajectoryKernel):
        def sample_state(self, streams: NamedRandomStreams) -> AgeRegimeState:
            return dataclasses.replace(super().sample_state(streams), puberty_onset_age_days=4380)

    physiology = FixedOnsetKernel(
        RegimeLinearTestReference(),
        AgeRegimeConfig(
            residual_sd=0.0,
            puberty_min_age_days=4380,
            puberty_max_age_days=4740,
        ),
    )
    module = ConstitutionalDelayModule(
        ConstitutionalDelayConfig(
            expected_puberty_age_days=4380,
            puberty_delay_min_days=360,
            puberty_delay_max_days=360,
        )
    )
    result = AgeRegimeDisorderKernel(physiology, module).generate(
        PATIENT, (4380, 4740, 4741, 5100), NamedRandomStreams(9, 0)
    )

    assert result.disorder.puberty_delay_days == 360
    assert result.physiology.state.puberty_onset_age_days == 4740
    assert result.physiology.points[0].height_z == pytest.approx(
        result.physiology.points[1].height_z
    )
    assert result.events[0].event_type == "latent_onset"


def test_growth_hormone_deficiency_keeps_treatment_events_and_changes_growth() -> None:
    physiology = AgeRegimeTrajectoryKernel(
        RegimeLinearTestReference(), AgeRegimeConfig(residual_sd=0.0)
    )
    module = GrowthHormoneDeficiencyModule(
        GrowthHormoneDeficiencyConfig(
            onset_min_age_days=3000,
            onset_max_age_days=3000,
            treatment_probability=1.0,
            treatment_delay_days=0,
            response_days=365,
            treatment_response_min=0.6,
            treatment_response_max=0.6,
        )
    )
    result = AgeRegimeDisorderKernel(physiology, module).generate(
        PATIENT, (2999, 3000, 3365, 4000, 5000), NamedRandomStreams(10, 0)
    )

    assert result.physiology.points[2].height_z < result.physiology.points[1].height_z
    assert [event.event_type for event in result.events][-2:] == [
        "treatment_start",
        "treatment_response",
    ]


def test_adjusted_velocities_are_recomputed_from_adjusted_points() -> None:
    physiology = AgeRegimeTrajectoryKernel(
        RegimeLinearTestReference(), AgeRegimeConfig(residual_sd=0.0)
    )
    module = GrowthHormoneDeficiencyModule(
        GrowthHormoneDeficiencyConfig(
            onset_min_age_days=1000,
            onset_max_age_days=1000,
            severity_min=1.0,
            severity_max=1.0,
            treatment_probability=0.0,
        )
    )
    result = AgeRegimeDisorderKernel(physiology, module).generate(
        PATIENT, (1000, 1365, 1730), NamedRandomStreams(11, 0)
    )

    for previous, current in zip(result.physiology.points, result.physiology.points[1:]):
        expected_height_velocity = (
            (current.height_cm - previous.height_cm)
            * 365.25
            / (current.age_days - previous.age_days)
        )
        expected_weight_velocity = (
            (current.weight_kg - previous.weight_kg)
            * 365.25
            / (current.age_days - previous.age_days)
        )
        assert current.height_velocity_cm_per_year == pytest.approx(expected_height_velocity)
        assert current.weight_velocity_kg_per_year == pytest.approx(expected_weight_velocity)


def test_composition_uses_only_regime_and_selected_disorder_streams() -> None:
    class RecordingStreams(NamedRandomStreams):
        def __init__(self, run_seed: int, patient_index: int) -> None:
            super().__init__(run_seed, patient_index)
            self.names: list[str] = []

        def generator(self, name: str):
            self.names.append(name)
            return super().generator(name)

    streams = RecordingStreams(12, 0)
    module = FamilialShortStatureModule(
        FamilialShortStatureConfig(severity_min=0.8, severity_max=0.8)
    )
    AgeRegimeDisorderKernel(
        AgeRegimeTrajectoryKernel(RegimeLinearTestReference()), module
    ).generate(PATIENT, (0, 730, 3000), streams)

    assert streams.names == [
        "regime.birth",
        "regime.childhood",
        "regime.puberty",
        "regime.residual",
        "regime.head",
        "disorder.familial_short_stature",
        "regime.residual",
        "regime.head",
    ]


@pytest.mark.parametrize(
    ("height_delta", "bmi_delta", "message"),
    [
        (math.nan, 0.0, "height z-score delta"),
        (0.0, math.inf, "BMI z-score delta"),
        (True, 0.0, "height z-score delta"),
    ],
)
def test_composition_rejects_nonfinite_or_nonreal_module_deltas(
    height_delta: object, bmi_delta: object, message: str
) -> None:
    module = FixedModule(
        LatentDisorderState(DisorderKind.FAMILIAL_SHORT_STATURE, 0, 0.8),
        height_delta=height_delta,
        bmi_delta=bmi_delta,
        kind=DisorderKind.FAMILIAL_SHORT_STATURE,
        events=(ClinicalEvent(PATIENT.patient_id, 0, "latent_onset", None, True),),
    )

    with pytest.raises(ValueError, match=message):
        AgeRegimeDisorderKernel(
            AgeRegimeTrajectoryKernel(RegimeLinearTestReference()), module
        ).generate(PATIENT, (1000,), NamedRandomStreams(13, 0))


@pytest.mark.parametrize("metric", ["height", "bmi"])
def test_composition_normalizes_module_delta_arithmetic_errors(metric: str) -> None:
    class ArithmeticDeltaModule(FixedModule):
        def height_z_delta(self, state: LatentDisorderState, age_days: int) -> object:
            if metric == "height":
                raise OverflowError("delta overflow")
            return super().height_z_delta(state, age_days)

        def bmi_z_delta(self, state: LatentDisorderState, age_days: int) -> object:
            if metric == "bmi":
                raise TypeError("delta type failure")
            return super().bmi_z_delta(state, age_days)

    module = ArithmeticDeltaModule(
        LatentDisorderState(DisorderKind.FAMILIAL_SHORT_STATURE, 0, 0.8),
        kind=DisorderKind.FAMILIAL_SHORT_STATURE,
        events=(ClinicalEvent(PATIENT.patient_id, 0, "latent_onset", None, True),),
    )

    with pytest.raises(ValueError, match=f"(?i)module {metric}"):
        AgeRegimeDisorderKernel(
            AgeRegimeTrajectoryKernel(RegimeLinearTestReference()), module
        ).generate(PATIENT, (1000,), NamedRandomStreams(13, 0))


@pytest.mark.parametrize("events", [[], "latent_onset"])
def test_composition_requires_module_events_to_be_a_tuple(events: object) -> None:
    module = FixedModule(
        LatentDisorderState(DisorderKind.HEALTHY, None, 0.0),
        events=events,  # type: ignore[arg-type]
    )

    with pytest.raises(TypeError, match="tuple"):
        AgeRegimeDisorderKernel(
            AgeRegimeTrajectoryKernel(RegimeLinearTestReference()), module
        ).generate(PATIENT, (1000,), NamedRandomStreams(13, 0))


def test_composition_rejects_active_nonhealthy_empty_event_trace() -> None:
    module = FixedModule(
        LatentDisorderState(DisorderKind.FAMILIAL_SHORT_STATURE, 0, 0.8),
        kind=DisorderKind.FAMILIAL_SHORT_STATURE,
        height_delta=-0.8,
    )

    with pytest.raises(ValueError, match="empty|latent_onset"):
        AgeRegimeDisorderKernel(
            AgeRegimeTrajectoryKernel(RegimeLinearTestReference()), module
        ).generate(PATIENT, (1000,), NamedRandomStreams(13, 0))


def test_composition_rejects_wrong_module_state_type_or_kind() -> None:
    physiology = AgeRegimeTrajectoryKernel(RegimeLinearTestReference())
    with pytest.raises(TypeError, match="LatentDisorderState"):
        AgeRegimeDisorderKernel(physiology, FixedModule(object())).generate(
            PATIENT, (1000,), NamedRandomStreams(14, 0)
        )

    mismatched = FixedModule(
        LatentDisorderState(DisorderKind.HEALTHY, None, 0.0),
        kind=DisorderKind.FAMILIAL_SHORT_STATURE,
    )
    with pytest.raises(ValueError, match="kind"):
        AgeRegimeDisorderKernel(physiology, mismatched).generate(
            PATIENT, (1000,), NamedRandomStreams(14, 0)
        )


def test_composition_rejects_module_events_for_another_patient() -> None:
    module = FixedModule(
        LatentDisorderState(DisorderKind.HEALTHY, None, 0.0),
        events=(ClinicalEvent("other-patient", 0, "latent_onset", None, True),),
    )

    with pytest.raises(ValueError, match="patient"):
        AgeRegimeDisorderKernel(
            AgeRegimeTrajectoryKernel(RegimeLinearTestReference()), module
        ).generate(PATIENT, (1000,), NamedRandomStreams(15, 0))


def test_constitutional_delay_replay_rejects_shift_outside_configured_domain() -> None:
    class LateOnsetKernel(AgeRegimeTrajectoryKernel):
        def sample_state(self, streams: NamedRandomStreams) -> AgeRegimeState:
            return dataclasses.replace(super().sample_state(streams), puberty_onset_age_days=5000)

    physiology = LateOnsetKernel(RegimeLinearTestReference())
    module = ConstitutionalDelayModule(
        ConstitutionalDelayConfig(
            puberty_delay_min_days=360,
            puberty_delay_max_days=360,
        )
    )

    with pytest.raises(ValueError, match="puberty onset"):
        AgeRegimeDisorderKernel(physiology, module).generate(
            PATIENT, (5000,), NamedRandomStreams(16, 0)
        )


@pytest.mark.parametrize("bad_value", [math.nan, 0.0, 10**1000])
def test_composition_rejects_nonphysical_adjusted_reference_values(
    bad_value: object,
) -> None:
    class BadAdjustedReference(RegimeLinearTestReference):
        def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
            if metric == "height_cm" and z < -5.0:
                return bad_value  # type: ignore[return-value]
            return super().value(metric, age_days, reference_sex, z)

    module = FamilialShortStatureModule(
        FamilialShortStatureConfig(severity_min=10.0, severity_max=10.0)
    )

    with pytest.raises(ValueError, match="reference height.*finite and positive"):
        AgeRegimeDisorderKernel(AgeRegimeTrajectoryKernel(BadAdjustedReference()), module).generate(
            PATIENT, (1000,), NamedRandomStreams(17, 0)
        )


def test_composition_converts_adjusted_weight_overflow_to_value_error() -> None:
    class ExtremeAdjustedReference(RegimeLinearTestReference):
        def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
            if metric == "height_cm" and z < -5.0:
                return 1e308
            return super().value(metric, age_days, reference_sex, z)

    module = FamilialShortStatureModule(
        FamilialShortStatureConfig(severity_min=10.0, severity_max=10.0)
    )

    with pytest.raises(ValueError, match="derived weight.*finite and positive"):
        AgeRegimeDisorderKernel(
            AgeRegimeTrajectoryKernel(ExtremeAdjustedReference()), module
        ).generate(PATIENT, (1000,), NamedRandomStreams(18, 0))


def test_composition_rechecks_sparse_adjusted_transition_continuity() -> None:
    class AdjustedJumpReference(RegimeLinearTestReference):
        def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
            value = super().value(metric, age_days, reference_sex, z)
            if metric == "height_cm" and age_days > 760 and z < -5.0:
                return value + 10.0
            return value

    module = FamilialShortStatureModule(
        FamilialShortStatureConfig(severity_min=10.0, severity_max=10.0)
    )

    with pytest.raises(ValueError, match="transition"):
        AgeRegimeDisorderKernel(
            AgeRegimeTrajectoryKernel(AdjustedJumpReference()), module
        ).generate(PATIENT, (699, 3000), NamedRandomStreams(19, 0))


def test_composition_checks_adjusted_continuity_at_actual_sparse_crossing_age() -> None:
    class LateEffectModule(FixedModule):
        def height_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
            del state
            return 0.0 if age_days <= 761 else -10.0

    module = LateEffectModule(
        LatentDisorderState(DisorderKind.FAMILIAL_SHORT_STATURE, 0, 0.8),
        kind=DisorderKind.FAMILIAL_SHORT_STATURE,
        events=(ClinicalEvent(PATIENT.patient_id, 0, "latent_onset", None, True),),
    )

    with pytest.raises(ValueError, match="transition"):
        AgeRegimeDisorderKernel(
            AgeRegimeTrajectoryKernel(RegimeLinearTestReference()), module
        ).generate(PATIENT, (730, 762), NamedRandomStreams(19, 0))


def test_constructor_rejects_wrong_physiology_type() -> None:
    with pytest.raises(TypeError, match="AgeRegimeTrajectoryKernel"):
        AgeRegimeDisorderKernel(object(), HealthyGrowthModule())  # type: ignore[arg-type]


@pytest.mark.parametrize("missing", ["sample_state", "height_z_delta", "bmi_z_delta", "events"])
def test_constructor_rejects_missing_required_module_methods(missing: str) -> None:
    class Module:
        kind = DisorderKind.HEALTHY
        module_version = "incomplete-test-v1"

        def sample_state(
            self, patient: PatientState, streams: NamedRandomStreams
        ) -> LatentDisorderState:
            del patient, streams
            return LatentDisorderState(DisorderKind.HEALTHY, None, 0.0)

        def height_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
            del state, age_days
            return 0.0

        def bmi_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
            del state, age_days
            return 0.0

        def events(
            self, patient: PatientState, state: LatentDisorderState
        ) -> tuple[ClinicalEvent, ...]:
            del patient, state
            return ()

    delattr(Module, missing)
    with pytest.raises(TypeError, match=missing):
        AgeRegimeDisorderKernel(AgeRegimeTrajectoryKernel(RegimeLinearTestReference()), Module())
