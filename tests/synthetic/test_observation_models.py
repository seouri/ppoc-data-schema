from __future__ import annotations

import dataclasses
import json
import re

import pytest

from synthetic.models import ClinicalEvent
from synthetic.native.observations import (
    OBSERVATION_STREAM_NAMES,
    RECORDED_EVENT_CODES,
    CensoringMode,
    EncounterType,
    EventRecordingDecision,
    MeasurementAvailability,
    MeasurementChannel,
    MeasurementObservation,
    MeasurementTruth,
    ObservationCheck,
    ObservationFrame,
    ObservationPolicy,
    ObservationTruth,
    ObservationValidationReport,
    ObservationValidationStatus,
    ObservationWindow,
    ObservedVisit,
    RecordedEvent,
    RecordedEventKind,
    VisitOpportunity,
    observed_stream_identity,
)


def _policy(**changes: object) -> ObservationPolicy:
    values: dict[str, object] = {
        "policy_version": "observation-v1",
        "window_start_age_days": 30,
        "window_end_age_days": 3650,
        "censoring_mode": CensoringMode.NONE,
        "censor_age_days": None,
        "visit_probability": 0.8,
        "length_availability_probability": 0.9,
        "height_availability_probability": 0.9,
        "weight_availability_probability": 0.95,
        "head_circumference_availability_probability": 0.7,
        "length_error_sd_cm": 0.1,
        "height_error_sd_cm": 0.1,
        "weight_error_sd_kg": 0.05,
        "head_circumference_error_sd_cm": 0.1,
        "rounding_digits": 1,
        "recognition_probability": 0.6,
        "diagnosis_probability": 0.5,
        "recognition_delay_days": 14,
    }
    values.update(changes)
    return ObservationPolicy(**values)  # type: ignore[arg-type]


def _window() -> ObservationWindow:
    return ObservationWindow(
        start_age_days=30,
        effective_end_age_days=3650,
        administrative_end_age_days=3650,
        censoring_mode=CensoringMode.NONE,
    )


def _measurements() -> tuple[MeasurementObservation, ...]:
    return (
        MeasurementObservation(
            MeasurementChannel.HEIGHT,
            MeasurementAvailability.OBSERVED,
            90.2,
        ),
        MeasurementObservation(
            MeasurementChannel.WEIGHT,
            MeasurementAvailability.OBSERVED,
            13.8,
        ),
        MeasurementObservation(
            MeasurementChannel.BMI,
            MeasurementAvailability.OBSERVED,
            16.96,
        ),
        MeasurementObservation(
            MeasurementChannel.LENGTH,
            MeasurementAvailability.NOT_APPLICABLE,
            None,
        ),
        MeasurementObservation(
            MeasurementChannel.HEAD_CIRCUMFERENCE,
            MeasurementAvailability.MISSING,
            None,
        ),
    )


def test_policy_is_frozen_strict_and_has_no_seed_or_truth_fields() -> None:
    policy = _policy()

    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.visit_probability = 1.0  # type: ignore[misc]
    assert "run_seed" not in dataclasses.asdict(policy)
    assert "truth" not in dataclasses.asdict(policy)
    assert policy.effective_end_age_days == 3650
    assert policy.to_mapping()["policy_version"] == "observation-v1"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"policy_version": "../policy"}, "policy_version"),
        ({"policy_version": ""}, "policy_version"),
        ({"window_start_age_days": -1}, "window"),
        ({"window_end_age_days": 30}, "window"),
        ({"window_start_age_days": 3650}, "window"),
        ({"window_end_age_days": True}, "integer"),
        ({"visit_probability": -0.01}, "probability"),
        ({"visit_probability": 1.01}, "probability"),
        ({"visit_probability": True}, "probability"),
        ({"height_error_sd_cm": float("nan")}, "finite"),
        ({"weight_error_sd_kg": -0.01}, "error"),
        ({"rounding_digits": 7}, "rounding"),
        ({"rounding_digits": True}, "integer"),
        ({"recognition_delay_days": -1}, "delay"),
        ({"censoring_mode": CensoringMode.LOST_TO_FOLLOW_UP}, "censor"),
        (
            {
                "censoring_mode": CensoringMode.LOST_TO_FOLLOW_UP,
                "censor_age_days": 3650,
            },
            "censor",
        ),
    ],
)
def test_policy_rejects_invalid_bounds_and_tokens(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        _policy(**changes)


def test_policy_from_mapping_rejects_unknown_or_missing_keys_without_coercion() -> None:
    mapping = _policy().to_mapping()
    mapping["unexpected"] = 1
    with pytest.raises(ValueError, match="keys"):
        ObservationPolicy.from_mapping(mapping)

    mapping = _policy().to_mapping()
    mapping.pop("recognition_probability")
    with pytest.raises(ValueError, match="keys"):
        ObservationPolicy.from_mapping(mapping)

    mapping = _policy().to_mapping()
    mapping["visit_probability"] = True
    with pytest.raises((TypeError, ValueError), match="probability"):
        ObservationPolicy.from_mapping(mapping)


def test_policy_censoring_modes_have_explicit_effective_window() -> None:
    administrative = _policy(censoring_mode=CensoringMode.ADMINISTRATIVE_END)
    assert administrative.effective_end_age_days == administrative.window_end_age_days

    lost = _policy(
        censoring_mode=CensoringMode.LOST_TO_FOLLOW_UP,
        censor_age_days=1200,
    )
    assert lost.effective_end_age_days == 1200

    with pytest.raises(ValueError, match="censor"):
        _policy(censoring_mode=CensoringMode.NONE, censor_age_days=100)


def test_stream_names_are_closed_and_identity_is_deterministic() -> None:
    assert OBSERVATION_STREAM_NAMES == (
        "observation.window",
        "observation.censoring",
        "observation.visit.routine",
        "observation.measurement-availability",
        "observation.measurement-error",
        "observation.recognition",
        "observation.recorded-event",
    )
    identities = [observed_stream_identity(name) for name in OBSERVATION_STREAM_NAMES]
    assert identities == [observed_stream_identity(name) for name in OBSERVATION_STREAM_NAMES]
    assert all(re.fullmatch(r"[0-9a-f]{64}", identity) for identity in identities)
    with pytest.raises(ValueError, match="stream"):
        observed_stream_identity("observation.window/../patient.csv")


def test_window_is_immutable_and_validates_order_and_censoring() -> None:
    window = _window()
    with pytest.raises(dataclasses.FrozenInstanceError):
        window.effective_end_age_days = 100  # type: ignore[misc]
    assert window.entry_age_days == 30
    assert window.exit_age_days == 3650

    with pytest.raises(ValueError, match="window"):
        ObservationWindow(30, 30, 3650, CensoringMode.NONE)
    with pytest.raises(ValueError, match="censor"):
        ObservationWindow(30, 100, 3650, CensoringMode.NONE)


def test_visit_opportunity_is_private_truth_and_strict() -> None:
    opportunity = VisitOpportunity(2, 730, EncounterType.ROUTINE, True)

    assert "730" not in repr(opportunity)
    assert "routine" not in repr(opportunity)
    with pytest.raises(dataclasses.FrozenInstanceError):
        opportunity.realized = False  # type: ignore[misc]
    with pytest.raises(ValueError, match="index"):
        VisitOpportunity(-1, 730, EncounterType.ROUTINE, True)
    with pytest.raises((TypeError, ValueError), match="realized"):
        VisitOpportunity(2, 730, EncounterType.ROUTINE, 1)  # type: ignore[arg-type]


def test_measurement_observation_is_closed_and_preserves_status() -> None:
    observed = MeasurementObservation(
        MeasurementChannel.WEIGHT,
        MeasurementAvailability.OBSERVED,
        12.4,
    )
    assert observed.to_mapping() == {
        "channel": "weight",
        "availability": "observed",
        "recorded_value": 12.4,
    }
    assert MeasurementObservation(
        MeasurementChannel.HEIGHT, MeasurementAvailability.MISSING, None
    ).recorded_value is None

    with pytest.raises(ValueError, match="recorded"):
        MeasurementObservation(
            MeasurementChannel.WEIGHT,
            MeasurementAvailability.MISSING,
            12.4,
        )
    with pytest.raises(ValueError, match="positive"):
        MeasurementObservation(
            MeasurementChannel.WEIGHT,
            MeasurementAvailability.OBSERVED,
            0,
        )
    with pytest.raises((TypeError, ValueError), match="channel"):
        MeasurementObservation("weight", MeasurementAvailability.OBSERVED, 12.4)  # type: ignore[arg-type]


def test_recorded_events_require_fictional_codes_and_safe_links() -> None:
    event = RecordedEvent(
        patient_id="syn-patient-a",
        age_days=800,
        event_kind=RecordedEventKind.DIAGNOSIS,
        code=RECORDED_EVENT_CODES[RecordedEventKind.DIAGNOSIS],
        opportunity_index=4,
    )
    assert event.to_mapping()["patient_id"] == "syn-patient-a"
    assert event.to_mapping()["opportunity_index"] == 4
    assert RecordedEvent(
        "syn-patient-a",
        800,
        RecordedEventKind.RECOGNITION,
        RECORDED_EVENT_CODES[RecordedEventKind.RECOGNITION],
        None,
    ).opportunity_index is None

    with pytest.raises(ValueError, match="synthetic"):
        RecordedEvent(
            "real-patient",
            800,
            RecordedEventKind.DIAGNOSIS,
            RECORDED_EVENT_CODES[RecordedEventKind.DIAGNOSIS],
            None,
        )
    with pytest.raises(ValueError, match="code"):
        RecordedEvent("syn-patient-a", 800, RecordedEventKind.DIAGNOSIS, "ICD-10", None)
    with pytest.raises(ValueError, match="index"):
        RecordedEvent(
            "syn-patient-a",
            800,
            RecordedEventKind.DIAGNOSIS,
            RECORDED_EVENT_CODES[RecordedEventKind.DIAGNOSIS],
            -1,
        )


def test_private_truth_retains_decisions_but_repr_has_no_hidden_values() -> None:
    source_event = ClinicalEvent("syn-patient-a", 600, "observable_phenotype", None, False)
    truth = ObservationTruth(
        patient_id="syn-patient-a",
        window=_window(),
        opportunities=(VisitOpportunity(0, 730, EncounterType.ROUTINE, True),),
        measurement_truth=(
            MeasurementTruth(
                source_point_index=0,
                channel=MeasurementChannel.HEIGHT,
                availability=MeasurementAvailability.OBSERVED,
                latent_value=90.0,
                error_delta=0.2,
            ),
        ),
        event_decisions=(EventRecordingDecision(0, True, 0),),
        source_events=(source_event,),
        latent_trajectory_hash="a" * 64,
        truth_hash="b" * 64,
    )

    assert "syn-patient-a" not in repr(truth)
    assert "90.0" not in repr(truth)
    assert truth.opportunities[0].realized is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        truth.measurement_truth = ()  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        truth.measurement_truth[0].error_delta = 1.0  # type: ignore[misc]


def test_truth_rejects_nonfictional_source_events_and_bad_hashes() -> None:
    with pytest.raises(ValueError, match="synthetic"):
        ObservationTruth(
            patient_id="/real/patient.csv",
            window=_window(),
            opportunities=(),
            measurement_truth=(),
            event_decisions=(),
            source_events=(),
        )

    with pytest.raises(ValueError, match="hash"):
        ObservationTruth(
            patient_id="syn-patient-a",
            window=_window(),
            opportunities=(),
            measurement_truth=(),
            event_decisions=(),
            source_events=(),
            truth_hash="not-a-hash",
        )


def test_truth_requires_one_decision_per_source_event_and_valid_opportunity_links() -> None:
    source_events = (
        ClinicalEvent("syn-patient-a", 600, "observable_phenotype", None, False),
        ClinicalEvent("syn-patient-a", 700, "recognition_opportunity", None, False),
    )
    opportunities = (VisitOpportunity(0, 730, EncounterType.ROUTINE, True),)

    def build(
        decisions: tuple[EventRecordingDecision, ...],
    ) -> ObservationTruth:
        return ObservationTruth(
            patient_id="syn-patient-a",
            window=_window(),
            opportunities=opportunities,
            measurement_truth=(),
            event_decisions=decisions,
            source_events=source_events,
        )

    with pytest.raises(ValueError, match="one decision"):
        build((EventRecordingDecision(0, True, 1), EventRecordingDecision(0, False, None)))
    with pytest.raises(ValueError, match="one decision"):
        build((EventRecordingDecision(0, True, 0),))
    with pytest.raises(ValueError, match="one decision"):
        build(
            (
                EventRecordingDecision(0, True, 0),
                EventRecordingDecision(1, False, None),
                EventRecordingDecision(1, False, None),
            )
        )
    with pytest.raises(ValueError, match="opportunity"):
        build((EventRecordingDecision(0, True, 1), EventRecordingDecision(1, False, None)))


def test_truth_rejects_recorded_decisions_linked_to_unrealized_opportunities() -> None:
    with pytest.raises(ValueError, match="realized"):
        ObservationTruth(
            patient_id="syn-patient-a",
            window=_window(),
            opportunities=(VisitOpportunity(0, 730, EncounterType.ROUTINE, False),),
            measurement_truth=(),
            event_decisions=(EventRecordingDecision(0, True, 0),),
            source_events=(
                ClinicalEvent("syn-patient-a", 600, "observable_phenotype", None, False),
            ),
        )


def test_truth_rejects_malformed_or_recorded_latent_onset_events() -> None:
    with pytest.raises(ValueError, match="latent_onset"):
        ObservationTruth(
            patient_id="syn-patient-a",
            window=_window(),
            opportunities=(),
            measurement_truth=(),
            event_decisions=(EventRecordingDecision(0, False, None),),
            source_events=(
                ClinicalEvent("syn-patient-a", 0, "latent_onset", None, False),
            ),
        )

    with pytest.raises(ValueError, match="hidden"):
        ObservationTruth(
            patient_id="syn-patient-a",
            window=_window(),
            opportunities=(VisitOpportunity(0, 730, EncounterType.ROUTINE, True),),
            measurement_truth=(),
            event_decisions=(EventRecordingDecision(0, True, 0),),
            source_events=(
                ClinicalEvent("syn-patient-a", 0, "latent_onset", None, True),
            ),
        )


@pytest.mark.parametrize(
    "event",
    [
        ClinicalEvent("syn-patient-a", -1, "observable_phenotype", None, False),
        ClinicalEvent("syn-patient-a", True, "observable_phenotype", None, False),  # type: ignore[arg-type]
        ClinicalEvent("syn-patient-a", 600, "not-a-native-event", None, False),
        ClinicalEvent("syn-patient-a", 600, "observable_phenotype", "SYN-CODE", False),
        ClinicalEvent("syn-patient-a", 600, "observable_phenotype", None, "no"),  # type: ignore[arg-type]
    ],
)
def test_truth_rejects_malformed_source_event_fields(event: ClinicalEvent) -> None:
    with pytest.raises((TypeError, ValueError)):
        ObservationTruth(
            patient_id="syn-patient-a",
            window=_window(),
            opportunities=(),
            measurement_truth=(),
            event_decisions=(EventRecordingDecision(0, False, None),),
            source_events=(event,),
        )


def test_frame_mapping_and_repr_exclude_private_truth() -> None:
    visit = ObservedVisit(
        patient_id="syn-patient-a",
        visit_id="syn-visit-a",
        age_days=730,
        encounter_type=EncounterType.ROUTINE,
        measurements=_measurements(),
    )
    frame = ObservationFrame(
        patient_id="syn-patient-a",
        policy_version="observation-v1",
        window=_window(),
        visits=(visit,),
        events=(),
        truth=ObservationTruth(
            patient_id="syn-patient-a",
            window=_window(),
            opportunities=(VisitOpportunity(0, 730, EncounterType.ROUTINE, True),),
            measurement_truth=(),
            event_decisions=(),
            source_events=(),
            latent_trajectory_hash="c" * 64,
            truth_hash="d" * 64,
        ),
    )
    mapping = frame.to_mapping()
    encoded = json.dumps(mapping, sort_keys=True)
    assert mapping["patient_id"] == "syn-patient-a"
    assert mapping["counts"] == {"visits": 1, "events": 0, "measurements": 5}
    assert "truth_hash" not in encoded
    assert "latent_trajectory_hash" not in encoded
    assert "syn-patient-a" not in repr(frame)
    assert "syn-visit-a" not in repr(frame)

    with pytest.raises(ValueError, match="patient"):
        ObservedVisit("real-patient", "syn-visit-a", 730, EncounterType.ROUTINE, _measurements())


def test_aggregate_observation_report_is_fixed_and_safe() -> None:
    checks = tuple(
        ObservationCheck(name, ObservationValidationStatus.PASS, "OK")
        for name in ObservationValidationReport.CHECK_NAMES
    )
    report = ObservationValidationReport(ObservationValidationStatus.PASS, checks)

    assert report.to_mapping()["status"] == "PASS"
    assert report.check_counts == {"PASS": len(checks), "FAIL": 0, "UNEVALUABLE": 0}
    assert "syn-patient" not in json.dumps(report.to_mapping())
    with pytest.raises(ValueError, match="duplicate"):
        ObservationValidationReport(
            ObservationValidationStatus.PASS,
            checks[:-1] + (checks[0],),
        )
    with pytest.raises(ValueError, match="reason"):
        ObservationCheck("window", ObservationValidationStatus.PASS, "patient_id")
