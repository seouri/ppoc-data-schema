from __future__ import annotations

import dataclasses
import json

from synthetic.native.observations import (
    MeasurementChannel,
    ObservationValidationStatus,
    RecordedEvent,
    RecordedEventKind,
    generate_observation_frame,
    validate_observation_frame,
)
from synthetic.randomness import NamedRandomStreams
from tests.synthetic.test_observation_generation import (
    _event_trajectory,
    _policy,
    _trajectory,
)


def _valid_frame():
    return generate_observation_frame(
        _trajectory(),
        _policy(
            visit_probability=1.0,
            length_availability_probability=1.0,
            height_availability_probability=1.0,
            weight_availability_probability=1.0,
            head_circumference_availability_probability=1.0,
        ),
        NamedRandomStreams(20260831, 0),
    )


def test_valid_frame_has_fixed_aggregate_pass_report() -> None:
    report = validate_observation_frame(_valid_frame())

    assert report.status is ObservationValidationStatus.PASS
    assert tuple(check.name for check in report.checks) == (
        "event_order",
        "evidence",
        "hidden_events",
        "measurements",
        "patient_identity",
        "visit_references",
        "window",
    )
    assert report.check_counts == {"PASS": 7, "FAIL": 0, "UNEVALUABLE": 0}
    assert all(check.reason_code == "OK" for check in report.checks)


def test_missing_hidden_measurement_evidence_is_unevaluable() -> None:
    frame = _valid_frame()
    truth = dataclasses.replace(frame.truth, measurement_truth=())
    malformed = dataclasses.replace(frame, truth=truth)

    report = validate_observation_frame(malformed)

    assert report.status is ObservationValidationStatus.UNEVALUABLE
    checks = {check.name: check for check in report.checks}
    assert checks["measurements"].status is ObservationValidationStatus.UNEVALUABLE
    assert checks["measurements"].reason_code == "INSUFFICIENT_EVIDENCE"


def test_true_measurement_identity_violation_is_fail() -> None:
    frame = _valid_frame()
    visit = frame.visits[1]
    measurements = list(visit.measurements)
    height_index = next(
        index
        for index, item in enumerate(measurements)
        if item.channel is MeasurementChannel.HEIGHT
    )
    measurements[height_index] = dataclasses.replace(
        measurements[height_index],
        recorded_value=measurements[height_index].recorded_value + 1.0,  # type: ignore[operator]
    )
    tampered = dataclasses.replace(
        frame,
        visits=frame.visits[:1]
        + (dataclasses.replace(visit, measurements=tuple(measurements)),)
        + frame.visits[2:],
    )

    report = validate_observation_frame(tampered)

    assert report.status is ObservationValidationStatus.FAIL
    check = next(check for check in report.checks if check.name == "measurements")
    assert check.status is ObservationValidationStatus.FAIL
    assert check.reason_code == "MEASUREMENT_INVALID"


def test_unmatched_visible_visit_is_fail() -> None:
    frame = _valid_frame()
    tampered = dataclasses.replace(
        frame,
        visits=(dataclasses.replace(frame.visits[0], visit_id="syn-unmatched"),)
        + frame.visits[1:],
    )

    report = validate_observation_frame(tampered)

    assert report.status is ObservationValidationStatus.FAIL
    check = next(check for check in report.checks if check.name == "visit_references")
    assert check.reason_code == "VISIT_REFERENCE_INVALID"


def test_visible_recorded_event_for_hidden_source_event_is_fail() -> None:
    frame = generate_observation_frame(
        _event_trajectory(),
        _policy(
            recognition_probability=0.0,
            diagnosis_probability=0.0,
            visit_probability=1.0,
        ),
        NamedRandomStreams(20260831, 0),
    )
    visible = RecordedEvent(
        frame.patient_id,
        730,
        RecordedEventKind.RECOGNITION,
        "SYN-GROWTH-RECOGNITION",
        1,
    )
    tampered = dataclasses.replace(frame, events=(visible,))

    report = validate_observation_frame(tampered)

    assert report.status is ObservationValidationStatus.FAIL
    check = next(check for check in report.checks if check.name == "hidden_events")
    assert check.reason_code in {"HIDDEN_EVENT_VISIBLE", "FORBIDDEN_EVENT"}


def test_causal_event_order_violation_is_fail() -> None:
    frame = generate_observation_frame(
        _event_trajectory(),
        _policy(
            recognition_probability=1.0,
            diagnosis_probability=1.0,
            visit_probability=1.0,
        ),
        NamedRandomStreams(20260831, 0),
    )
    assert len(frame.events) >= 2
    tampered_events = list(frame.events)
    tampered_events[1] = dataclasses.replace(tampered_events[1], age_days=701)
    tampered = dataclasses.replace(frame, events=tuple(tampered_events))

    report = validate_observation_frame(tampered)

    assert report.status is ObservationValidationStatus.FAIL
    check = next(check for check in report.checks if check.name == "event_order")
    assert check.reason_code == "EVENT_ORDER_INVALID"


def test_malformed_frame_is_unevaluable_without_detail_leakage() -> None:
    report = validate_observation_frame(object())

    assert report.status is ObservationValidationStatus.UNEVALUABLE
    assert all(check.status is ObservationValidationStatus.UNEVALUABLE for check in report.checks)
    assert all(check.reason_code == "MALFORMED_FRAME" for check in report.checks)
    encoded = json.dumps(report.to_mapping(), sort_keys=True) + repr(report)
    assert "syn-" not in encoded
    assert "20260831" not in encoded
    assert "source_events" not in encoded


def test_report_never_contains_private_frame_truth() -> None:
    frame = _valid_frame()
    report = validate_observation_frame(frame)
    encoded = json.dumps(report.to_mapping(), sort_keys=True) + repr(report)

    assert frame.patient_id not in encoded
    assert frame.truth.truth_hash not in encoded
    assert frame.truth.latent_trajectory_hash not in encoded
    assert "source_events" not in encoded
    assert "measurement_truth" not in encoded
    assert "error_delta" not in encoded
