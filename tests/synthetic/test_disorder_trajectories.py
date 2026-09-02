import pytest

from synthetic.models import (
    ClinicalEvent,
    DisorderKind,
    LatentDisorderState,
    PatientState,
)
from synthetic.native.clinical_modules import (
    ConstitutionalDelayModule,
    FamilialShortStatureConfig,
    FamilialShortStatureModule,
    HealthyGrowthModule,
)
from synthetic.native.healthy import HealthyKernel
from synthetic.native.trajectories import (
    DisorderTrajectoryKernel,
    validate_disorder_events,
)
from synthetic.randomness import NamedRandomStreams
from tests.synthetic.fakes import LinearTestReference

PATIENT = PatientState("syn-patient-a", "F", "F")
AGES = (730, 1095, 1460, 4000, 5000)


class ZeroGenerationZReference(LinearTestReference):
    def generation_z_score(
        self, metric: str, age_days: int, reference_sex: str, z: float
    ) -> float:
        del metric, age_days, reference_sex, z
        return 0.0


class HalfGenerationZReference(LinearTestReference):
    def generation_z_score(
        self, metric: str, age_days: int, reference_sex: str, z: float
    ) -> float:
        del metric, age_days, reference_sex
        return z / 2.0


class EventModule:
    kind = DisorderKind.HEALTHY

    def __init__(
        self,
        state: LatentDisorderState,
        events: tuple[ClinicalEvent, ...],
        *,
        kind: DisorderKind = DisorderKind.HEALTHY,
        module_version: object = "event-test-v1",
    ) -> None:
        self.kind = kind
        self.module_version = module_version
        self.state = state
        self._events = events

    def sample_state(
        self, patient: PatientState, streams: NamedRandomStreams
    ) -> LatentDisorderState:
        del patient, streams
        return self.state

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
        return self._events


def _treatment_module(
    events: tuple[ClinicalEvent, ...], *, treatment_response: float = 0.6
) -> EventModule:
    return EventModule(
        LatentDisorderState(
            DisorderKind.GROWTH_HORMONE_DEFICIENCY,
            100,
            0.8,
            treatment_start_age_days=300,
            treatment_response=treatment_response,
        ),
        events,
        kind=DisorderKind.GROWTH_HORMONE_DEFICIENCY,
    )


def test_healthy_module_matches_existing_healthy_kernel() -> None:
    reference = LinearTestReference()
    baseline = HealthyKernel(reference).generate(
        PATIENT, AGES, NamedRandomStreams(20260830, 0)
    )
    result = DisorderTrajectoryKernel(
        HealthyKernel(reference), HealthyGrowthModule()
    ).generate(PATIENT, AGES, NamedRandomStreams(20260830, 0))

    assert result.disorder.kind is DisorderKind.HEALTHY
    assert result.points == baseline
    assert result.events == ()


def test_generation_hook_records_effective_z_scores_after_legacy_disorder_composition() -> None:
    result = DisorderTrajectoryKernel(
        HealthyKernel(ZeroGenerationZReference()), HealthyGrowthModule()
    ).generate(PATIENT, AGES, NamedRandomStreams(20260830, 0))

    for point in result.points:
        assert point.height_z == 0.0
        assert point.bmi_z == 0.0


def test_healthy_disorder_kernel_applies_generation_hook_once() -> None:
    reference = HalfGenerationZReference()
    baseline = HealthyKernel(reference).generate(
        PATIENT, AGES, NamedRandomStreams(20260830, 0)
    )
    result = DisorderTrajectoryKernel(
        HealthyKernel(reference), HealthyGrowthModule()
    ).generate(PATIENT, AGES, NamedRandomStreams(20260830, 0))

    assert result.points == baseline


def test_familial_short_stature_is_constant_height_shift_and_keeps_weight_identity() -> None:
    reference = LinearTestReference()
    baseline = HealthyKernel(reference).generate(
        PATIENT, AGES, NamedRandomStreams(20260830, 0)
    )
    result = DisorderTrajectoryKernel(
        HealthyKernel(reference), FamilialShortStatureModule()
    ).generate(PATIENT, AGES, NamedRandomStreams(20260830, 0))

    shifts = [point.height_z - base.height_z for point, base in zip(result.points, baseline)]
    assert shifts == pytest.approx([shifts[0]] * len(shifts))
    for point in result.points:
        assert point.weight_kg == pytest.approx(point.bmi * (point.height_cm / 100) ** 2)


def test_nonhealthy_disorder_composition_applies_generation_hook_after_effect() -> None:
    reference = HalfGenerationZReference()
    baseline = HealthyKernel(reference).generate(
        PATIENT, AGES, NamedRandomStreams(20260830, 0)
    )
    module = FamilialShortStatureModule(
        config=FamilialShortStatureConfig(severity_min=0.8, severity_max=0.8)
    )
    result = DisorderTrajectoryKernel(
        HealthyKernel(reference), module
    ).generate(PATIENT, AGES, NamedRandomStreams(20260830, 0))

    assert result.points[0].height_z == pytest.approx(
        (baseline[0].height_z - 0.8) / 2.0
    )


def test_constitutional_delay_has_no_effect_before_puberty_and_returns_after_recovery() -> None:
    reference = LinearTestReference()
    result = DisorderTrajectoryKernel(
        HealthyKernel(reference), ConstitutionalDelayModule()
    ).generate(PATIENT, AGES, NamedRandomStreams(20260830, 0))
    puberty_age = ConstitutionalDelayModule().config.expected_puberty_age_days

    assert result.points[0].height_z == pytest.approx(
        HealthyKernel(reference).generate(PATIENT, (730,), NamedRandomStreams(20260830, 0))[0].height_z
    )
    assert result.disorder.kind is DisorderKind.CONSTITUTIONAL_DELAY
    assert next(event.event_type for event in result.events) == "latent_onset"
    assert puberty_age >= 3650


def test_kernel_accepts_nonempty_string_module_version() -> None:
    module = EventModule(
        LatentDisorderState(DisorderKind.HEALTHY, None, 0.0), ()
    )

    result = DisorderTrajectoryKernel(
        HealthyKernel(LinearTestReference()), module
    ).generate(PATIENT, (730,), NamedRandomStreams(20260830, 0))

    assert result.events == ()


@pytest.mark.parametrize("module_version", ["", "   ", None, 1])
def test_kernel_rejects_missing_empty_or_non_string_module_version(
    module_version: object,
) -> None:
    module = EventModule(
        LatentDisorderState(DisorderKind.HEALTHY, None, 0.0), (),
        module_version=module_version,
    )
    if module_version is None:
        del module.module_version

    with pytest.raises((TypeError, ValueError), match="module_version"):
        DisorderTrajectoryKernel(HealthyKernel(LinearTestReference()), module)


def test_kernel_rejects_module_events_for_a_different_patient() -> None:
    module = EventModule(
        LatentDisorderState(DisorderKind.HEALTHY, None, 0.0),
        (ClinicalEvent("other-patient", 730, "latent_onset", None, True),),
    )

    with pytest.raises(ValueError, match="patient"):
        DisorderTrajectoryKernel(HealthyKernel(LinearTestReference()), module).generate(
            PATIENT, (730,), NamedRandomStreams(20260830, 0)
        )


def test_shared_event_validator_preserves_patient_error_message() -> None:
    with pytest.raises(
        ValueError, match="module event patient ID must match the requested patient"
    ):
        validate_disorder_events(
            PATIENT,
            LatentDisorderState(DisorderKind.HEALTHY, None, 0.0),
            (ClinicalEvent("other-patient", 730, "latent_onset", None, True),),
        )


def test_kernel_rejects_module_events_with_decreasing_ages() -> None:
    module = EventModule(
        LatentDisorderState(DisorderKind.FAMILIAL_SHORT_STATURE, 800, 0.8),
        (
            ClinicalEvent(PATIENT.patient_id, 800, "latent_onset", None, True),
            ClinicalEvent(PATIENT.patient_id, 799, "observable_phenotype", None, False),
        ),
        kind=DisorderKind.FAMILIAL_SHORT_STATURE,
    )

    with pytest.raises(ValueError, match="nondecreasing"):
        DisorderTrajectoryKernel(HealthyKernel(LinearTestReference()), module).generate(
            PATIENT, (730,), NamedRandomStreams(20260830, 0)
        )


def test_kernel_rejects_response_event_without_treatment_schedule() -> None:
    module = EventModule(
        LatentDisorderState(DisorderKind.FAMILIAL_SHORT_STATURE, 800, 0.8),
        (
            ClinicalEvent(PATIENT.patient_id, 800, "latent_onset", None, True),
            ClinicalEvent(PATIENT.patient_id, 900, "treatment_response", None, False),
        ),
        kind=DisorderKind.FAMILIAL_SHORT_STATURE,
    )

    with pytest.raises(ValueError, match="treatment"):
        DisorderTrajectoryKernel(HealthyKernel(LinearTestReference()), module).generate(
            PATIENT, (730,), NamedRandomStreams(20260830, 0)
        )


def test_kernel_accepts_matching_treatment_response_terminal_event() -> None:
    module = _treatment_module(
        (
            ClinicalEvent(PATIENT.patient_id, 100, "latent_onset", None, True),
            ClinicalEvent(PATIENT.patient_id, 300, "treatment_start", None, False),
            ClinicalEvent(PATIENT.patient_id, 400, "treatment_response", None, False),
        )
    )

    result = DisorderTrajectoryKernel(
        HealthyKernel(LinearTestReference()), module
    ).generate(PATIENT, (730,), NamedRandomStreams(20260830, 0))

    assert [event.event_type for event in result.events] == [
        "latent_onset",
        "treatment_start",
        "treatment_response",
    ]


def test_kernel_accepts_matching_treatment_nonresponse_terminal_event() -> None:
    module = _treatment_module(
        (
            ClinicalEvent(PATIENT.patient_id, 100, "latent_onset", None, True),
            ClinicalEvent(PATIENT.patient_id, 300, "treatment_start", None, False),
            ClinicalEvent(PATIENT.patient_id, 400, "treatment_nonresponse", None, False),
        ),
        treatment_response=0.0,
    )

    result = DisorderTrajectoryKernel(
        HealthyKernel(LinearTestReference()), module
    ).generate(PATIENT, (730,), NamedRandomStreams(20260830, 0))

    assert [event.event_type for event in result.events] == [
        "latent_onset",
        "treatment_start",
        "treatment_nonresponse",
    ]


@pytest.mark.parametrize(
    ("events", "response", "message"),
    [
        (
            (
                ClinicalEvent(PATIENT.patient_id, 100, "latent_onset", None, True),
                ClinicalEvent(PATIENT.patient_id, 400, "treatment_response", None, False),
            ),
            0.6,
            "prior treatment_start",
        ),
        (
            (
                ClinicalEvent(PATIENT.patient_id, 100, "latent_onset", None, True),
                ClinicalEvent(PATIENT.patient_id, 400, "treatment_nonresponse", None, False),
            ),
            0.0,
            "prior treatment_start",
        ),
        (
            (
                ClinicalEvent(PATIENT.patient_id, 100, "latent_onset", None, True),
                ClinicalEvent(PATIENT.patient_id, 300, "treatment_start", None, False),
                ClinicalEvent(PATIENT.patient_id, 300, "treatment_response", None, False),
            ),
            0.6,
            "after treatment",
        ),
        (
            (
                ClinicalEvent(PATIENT.patient_id, 100, "latent_onset", None, True),
                ClinicalEvent(PATIENT.patient_id, 300, "treatment_start", None, False),
                ClinicalEvent(PATIENT.patient_id, 400, "treatment_response", None, False),
                ClinicalEvent(PATIENT.patient_id, 500, "treatment_nonresponse", None, False),
            ),
            0.6,
            "terminal",
        ),
        (
            (
                ClinicalEvent(PATIENT.patient_id, 100, "latent_onset", None, True),
                ClinicalEvent(PATIENT.patient_id, 300, "treatment_start", None, False),
                ClinicalEvent(PATIENT.patient_id, 400, "treatment_response", None, False),
                ClinicalEvent(PATIENT.patient_id, 500, "treatment_response", None, False),
            ),
            0.6,
            "terminal",
        ),
        (
            (
                ClinicalEvent(PATIENT.patient_id, 100, "latent_onset", None, True),
                ClinicalEvent(PATIENT.patient_id, 300, "treatment_start", None, False),
                ClinicalEvent(PATIENT.patient_id, 400, "treatment_nonresponse", None, False),
                ClinicalEvent(PATIENT.patient_id, 500, "treatment_response", None, False),
            ),
            0.0,
            "terminal",
        ),
        (
            (
                ClinicalEvent(PATIENT.patient_id, 100, "latent_onset", None, True),
                ClinicalEvent(PATIENT.patient_id, 300, "treatment_start", None, False),
                ClinicalEvent(PATIENT.patient_id, 400, "treatment_nonresponse", None, False),
                ClinicalEvent(PATIENT.patient_id, 500, "treatment_nonresponse", None, False),
            ),
            0.0,
            "terminal",
        ),
        (
            (
                ClinicalEvent(PATIENT.patient_id, 100, "latent_onset", None, True),
                ClinicalEvent(PATIENT.patient_id, 300, "treatment_start", None, False),
                ClinicalEvent(PATIENT.patient_id, 400, "treatment_response", None, False),
            ),
            0.0,
            "state.treatment_response",
        ),
        (
            (
                ClinicalEvent(PATIENT.patient_id, 100, "latent_onset", None, True),
                ClinicalEvent(PATIENT.patient_id, 300, "treatment_start", None, False),
                ClinicalEvent(PATIENT.patient_id, 400, "treatment_nonresponse", None, False),
            ),
            0.6,
            "state.treatment_response",
        ),
        (
            (
                ClinicalEvent(PATIENT.patient_id, 100, "latent_onset", None, True),
                ClinicalEvent(PATIENT.patient_id, 200, "treatment_response", None, False),
                ClinicalEvent(PATIENT.patient_id, 300, "treatment_start", None, False),
            ),
            0.6,
            "prior treatment_start",
        ),
    ],
)
def test_kernel_rejects_malformed_terminal_treatment_events(
    events: tuple[ClinicalEvent, ...], response: float, message: str
) -> None:
    module = _treatment_module(events, treatment_response=response)

    with pytest.raises(ValueError, match=message):
        DisorderTrajectoryKernel(HealthyKernel(LinearTestReference()), module).generate(
            PATIENT, (730,), NamedRandomStreams(20260830, 0)
        )


@pytest.mark.parametrize(
    ("event", "message"),
    [
        (
            ClinicalEvent(PATIENT.patient_id, 100, "latent_onset", "secret", True),
            "code",
        ),
        (
            ClinicalEvent(PATIENT.patient_id, 100, "latent_onset", None, False),
            "hidden",
        ),
        (
            ClinicalEvent(PATIENT.patient_id, 100, "observable_phenotype", None, True),
            "hidden",
        ),
        (
            ClinicalEvent(PATIENT.patient_id, 100, ["latent_onset"], None, True),  # type: ignore[arg-type]
            "event_type",
        ),
    ],
)
def test_kernel_rejects_malformed_event_visibility_and_types(
    event: ClinicalEvent, message: str
) -> None:
    module = EventModule(
        LatentDisorderState(DisorderKind.FAMILIAL_SHORT_STATURE, 100, 0.8),
        (event,),
        kind=DisorderKind.FAMILIAL_SHORT_STATURE,
    )

    with pytest.raises(ValueError, match=message):
        DisorderTrajectoryKernel(HealthyKernel(LinearTestReference()), module).generate(
            PATIENT, (730,), NamedRandomStreams(20260830, 0)
        )


@pytest.mark.parametrize("events", [[], "latent_onset"])
def test_kernel_requires_module_events_to_be_a_tuple(events: object) -> None:
    module = EventModule(
        LatentDisorderState(DisorderKind.HEALTHY, None, 0.0),
        events,  # type: ignore[arg-type]
    )

    with pytest.raises(TypeError, match="tuple"):
        DisorderTrajectoryKernel(HealthyKernel(LinearTestReference()), module).generate(
            PATIENT, (730,), NamedRandomStreams(20260830, 0)
        )


def test_kernel_requires_latent_onset_before_descendant_events() -> None:
    module = EventModule(
        LatentDisorderState(DisorderKind.FAMILIAL_SHORT_STATURE, 100, 0.8),
        (ClinicalEvent(PATIENT.patient_id, 200, "observable_phenotype", None, False),),
        kind=DisorderKind.FAMILIAL_SHORT_STATURE,
    )

    with pytest.raises(ValueError, match="latent_onset"):
        DisorderTrajectoryKernel(HealthyKernel(LinearTestReference()), module).generate(
            PATIENT, (730,), NamedRandomStreams(20260830, 0)
        )


@pytest.mark.parametrize("metric", ["height", "bmi"])
def test_kernel_normalizes_module_delta_arithmetic_errors(metric: str) -> None:
    class ArithmeticDeltaModule(EventModule):
        def height_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
            if metric == "height":
                raise OverflowError("delta overflow")
            return super().height_z_delta(state, age_days)

        def bmi_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
            if metric == "bmi":
                raise TypeError("delta type failure")
            return super().bmi_z_delta(state, age_days)

    module = ArithmeticDeltaModule(
        LatentDisorderState(DisorderKind.FAMILIAL_SHORT_STATURE, 0, 0.8),
        (),
        kind=DisorderKind.FAMILIAL_SHORT_STATURE,
    )

    with pytest.raises(ValueError, match=f"(?i)module {metric}"):
        DisorderTrajectoryKernel(HealthyKernel(LinearTestReference()), module).generate(
            PATIENT, (730,), NamedRandomStreams(20260830, 0)
        )
