import pytest

from synthetic.models import (
    ClinicalEvent,
    DisorderKind,
    LatentDisorderState,
    PatientState,
)
from synthetic.native.clinical_modules import (
    ConstitutionalDelayModule,
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
        LatentDisorderState(DisorderKind.HEALTHY, None, 0.0),
        (
            ClinicalEvent(PATIENT.patient_id, 800, "latent_onset", None, True),
            ClinicalEvent(PATIENT.patient_id, 799, "observable_phenotype", None, False),
        ),
    )

    with pytest.raises(ValueError, match="nondecreasing"):
        DisorderTrajectoryKernel(HealthyKernel(LinearTestReference()), module).generate(
            PATIENT, (730,), NamedRandomStreams(20260830, 0)
        )


def test_kernel_rejects_response_event_without_treatment_schedule() -> None:
    module = EventModule(
        LatentDisorderState(DisorderKind.HEALTHY, None, 0.0),
        (ClinicalEvent(PATIENT.patient_id, 800, "treatment_response", None, False),),
    )

    with pytest.raises(ValueError, match="treatment"):
        DisorderTrajectoryKernel(HealthyKernel(LinearTestReference()), module).generate(
            PATIENT, (730,), NamedRandomStreams(20260830, 0)
        )


def test_kernel_accepts_matching_treatment_response_terminal_event() -> None:
    module = _treatment_module(
        (
            ClinicalEvent(PATIENT.patient_id, 300, "treatment_start", None, False),
            ClinicalEvent(PATIENT.patient_id, 400, "treatment_response", None, False),
        )
    )

    result = DisorderTrajectoryKernel(
        HealthyKernel(LinearTestReference()), module
    ).generate(PATIENT, (730,), NamedRandomStreams(20260830, 0))

    assert [event.event_type for event in result.events] == [
        "treatment_start",
        "treatment_response",
    ]


def test_kernel_accepts_matching_treatment_nonresponse_terminal_event() -> None:
    module = _treatment_module(
        (
            ClinicalEvent(PATIENT.patient_id, 300, "treatment_start", None, False),
            ClinicalEvent(PATIENT.patient_id, 400, "treatment_nonresponse", None, False),
        ),
        treatment_response=0.0,
    )

    result = DisorderTrajectoryKernel(
        HealthyKernel(LinearTestReference()), module
    ).generate(PATIENT, (730,), NamedRandomStreams(20260830, 0))

    assert [event.event_type for event in result.events] == [
        "treatment_start",
        "treatment_nonresponse",
    ]


@pytest.mark.parametrize(
    ("events", "response", "message"),
    [
        (
            (ClinicalEvent(PATIENT.patient_id, 400, "treatment_response", None, False),),
            0.6,
            "prior treatment_start",
        ),
        (
            (ClinicalEvent(PATIENT.patient_id, 400, "treatment_nonresponse", None, False),),
            0.0,
            "prior treatment_start",
        ),
        (
            (
                ClinicalEvent(PATIENT.patient_id, 300, "treatment_start", None, False),
                ClinicalEvent(PATIENT.patient_id, 300, "treatment_response", None, False),
            ),
            0.6,
            "after treatment",
        ),
        (
            (
                ClinicalEvent(PATIENT.patient_id, 300, "treatment_start", None, False),
                ClinicalEvent(PATIENT.patient_id, 400, "treatment_response", None, False),
                ClinicalEvent(PATIENT.patient_id, 500, "treatment_nonresponse", None, False),
            ),
            0.6,
            "terminal",
        ),
        (
            (
                ClinicalEvent(PATIENT.patient_id, 300, "treatment_start", None, False),
                ClinicalEvent(PATIENT.patient_id, 400, "treatment_response", None, False),
                ClinicalEvent(PATIENT.patient_id, 500, "treatment_response", None, False),
            ),
            0.6,
            "terminal",
        ),
        (
            (
                ClinicalEvent(PATIENT.patient_id, 300, "treatment_start", None, False),
                ClinicalEvent(PATIENT.patient_id, 400, "treatment_nonresponse", None, False),
                ClinicalEvent(PATIENT.patient_id, 500, "treatment_response", None, False),
            ),
            0.0,
            "terminal",
        ),
        (
            (
                ClinicalEvent(PATIENT.patient_id, 300, "treatment_start", None, False),
                ClinicalEvent(PATIENT.patient_id, 400, "treatment_nonresponse", None, False),
                ClinicalEvent(PATIENT.patient_id, 500, "treatment_nonresponse", None, False),
            ),
            0.0,
            "terminal",
        ),
        (
            (
                ClinicalEvent(PATIENT.patient_id, 300, "treatment_start", None, False),
                ClinicalEvent(PATIENT.patient_id, 400, "treatment_response", None, False),
            ),
            0.0,
            "state.treatment_response",
        ),
        (
            (
                ClinicalEvent(PATIENT.patient_id, 300, "treatment_start", None, False),
                ClinicalEvent(PATIENT.patient_id, 400, "treatment_nonresponse", None, False),
            ),
            0.6,
            "state.treatment_response",
        ),
        (
            (
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
