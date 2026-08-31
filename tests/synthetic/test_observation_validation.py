from __future__ import annotations

import dataclasses
import json

import pytest

from synthetic.native import observations as observation_module
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


def test_measurement_value_must_follow_hidden_error_and_rounding_policy() -> None:
    frame = generate_observation_frame(
        _trajectory(),
        _policy(height_error_sd_cm=0.1, rounding_digits=1),
        NamedRandomStreams(20260831, 0),
    )
    visit = next(visit for visit in frame.visits if visit.age_days == 1000)
    measurements = list(visit.measurements)
    height_index = next(
        index
        for index, item in enumerate(measurements)
        if item.channel is MeasurementChannel.HEIGHT
    )
    height = measurements[height_index]
    assert height.recorded_value is not None
    measurements[height_index] = dataclasses.replace(
        height,
        recorded_value=round(height.recorded_value + 0.1, 1),
    )
    tampered = dataclasses.replace(
        frame,
        visits=frame.visits[:2]
        + (dataclasses.replace(visit, measurements=tuple(measurements)),)
        + frame.visits[3:],
    )

    report = validate_observation_frame(tampered)

    assert report.status is ObservationValidationStatus.FAIL
    check = next(check for check in report.checks if check.name == "measurements")
    assert check.reason_code == "MEASUREMENT_INVALID"


def test_coordinated_truth_hash_tampering_cannot_replace_latent_source_value() -> None:
    frame = _valid_frame()
    truth_item_index = next(
        index
        for index, item in enumerate(frame.truth.measurement_truth)
        if item.channel is MeasurementChannel.HEIGHT and item.latent_value is not None
    )
    truth_items = list(frame.truth.measurement_truth)
    truth_item = truth_items[truth_item_index]
    assert truth_item.latent_value is not None
    truth_items[truth_item_index] = dataclasses.replace(
        truth_item,
        latent_value=truth_item.latent_value + 1.0,
    )
    unsealed_truth = dataclasses.replace(
        frame.truth,
        measurement_truth=tuple(truth_items),
        truth_hash=None,
    )
    resealed_truth = dataclasses.replace(
        unsealed_truth,
        truth_hash=observation_module._canonical_hash(
            (unsealed_truth.policy.to_mapping(), unsealed_truth)  # type: ignore[union-attr]
        ),
    )
    tampered = dataclasses.replace(frame, truth=resealed_truth)

    report = validate_observation_frame(tampered)

    assert report.status is ObservationValidationStatus.FAIL
    check = next(check for check in report.checks if check.name == "measurements")
    assert check.reason_code == "TRUTH_INTEGRITY_INVALID"


def test_invalid_latent_trajectory_hash_is_fail() -> None:
    frame = _valid_frame()
    tampered = dataclasses.replace(
        frame,
        truth=dataclasses.replace(frame.truth, latent_trajectory_hash="0" * 64),
    )

    report = validate_observation_frame(tampered)

    assert report.status is ObservationValidationStatus.FAIL
    check = next(check for check in report.checks if check.name == "evidence")
    assert check.reason_code == "TRUTH_INTEGRITY_INVALID"


def test_missing_provenance_is_unevaluable_not_pass() -> None:
    frame = _valid_frame()
    tampered = dataclasses.replace(
        frame,
        truth=dataclasses.replace(
            frame.truth,
            policy=None,
            latent_trajectory=None,
        ),
    )

    report = validate_observation_frame(tampered)

    assert report.status is ObservationValidationStatus.UNEVALUABLE
    checks = {check.name: check for check in report.checks}
    assert checks["measurements"].status is ObservationValidationStatus.UNEVALUABLE
    assert checks["evidence"].status is ObservationValidationStatus.UNEVALUABLE
    assert checks["evidence"].reason_code == "INSUFFICIENT_EVIDENCE"


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


def test_recorded_event_must_retain_exact_decision_opportunity_link() -> None:
    frame = generate_observation_frame(
        _event_trajectory(),
        _policy(
            recognition_probability=1.0,
            diagnosis_probability=1.0,
            visit_probability=1.0,
            recognition_delay_days=50,
        ),
        NamedRandomStreams(20260831, 0),
    )
    recognition = frame.events[0]
    swapped = dataclasses.replace(
        recognition,
        age_days=1500,
        opportunity_index=3,
    )
    tampered = dataclasses.replace(frame, events=(swapped,) + frame.events[1:])

    report = validate_observation_frame(tampered)

    assert report.status is ObservationValidationStatus.FAIL
    check = next(check for check in report.checks if check.name == "hidden_events")
    assert check.reason_code == "FORBIDDEN_EVENT"


def test_recorded_event_must_respect_recognition_delay_provenance() -> None:
    trajectory = _event_trajectory()
    points = list(trajectory.physiology.points)
    points[1] = dataclasses.replace(points[1], age_days=800)
    trajectory = dataclasses.replace(
        trajectory,
        physiology=dataclasses.replace(trajectory.physiology, points=tuple(points)),
    )
    frame = generate_observation_frame(
        trajectory,
        _policy(
            recognition_probability=1.0,
            diagnosis_probability=1.0,
            visit_probability=1.0,
            recognition_delay_days=50,
        ),
        NamedRandomStreams(20260831, 0),
    )
    assert frame.events[0].age_days == 800
    assert frame.truth.policy is not None
    delayed_policy = dataclasses.replace(frame.truth.policy, recognition_delay_days=150)
    unsealed_truth = dataclasses.replace(
        frame.truth,
        policy=delayed_policy,
        truth_hash=None,
    )
    resealed_truth = dataclasses.replace(
        unsealed_truth,
        truth_hash=observation_module._canonical_hash(
            (delayed_policy.to_mapping(), unsealed_truth)
        ),
    )
    tampered = dataclasses.replace(frame, truth=resealed_truth)

    report = validate_observation_frame(tampered)

    assert report.status is ObservationValidationStatus.FAIL
    check = next(check for check in report.checks if check.name == "hidden_events")
    assert check.reason_code == "FORBIDDEN_EVENT"


def test_recorded_descendants_require_recorded_ancestor_chain() -> None:
    frame = generate_observation_frame(
        _event_trajectory(),
        _policy(
            recognition_probability=1.0,
            diagnosis_probability=1.0,
            visit_probability=1.0,
        ),
        NamedRandomStreams(20260831, 0),
    )
    decisions = list(frame.truth.event_decisions)
    recognition_source_index = next(
        index
        for index, event in enumerate(frame.truth.source_events)
        if event.event_type == "recognition_opportunity"
    )
    decisions[recognition_source_index] = dataclasses.replace(
        decisions[recognition_source_index],
        recorded=False,
        opportunity_index=None,
    )
    unsealed_truth = dataclasses.replace(
        frame.truth,
        event_decisions=tuple(decisions),
        truth_hash=None,
    )
    resealed_truth = dataclasses.replace(
        unsealed_truth,
        truth_hash=observation_module._canonical_hash(
            (unsealed_truth.policy.to_mapping(), unsealed_truth)  # type: ignore[union-attr]
        ),
    )
    tampered = dataclasses.replace(frame, events=frame.events[1:], truth=resealed_truth)

    report = validate_observation_frame(tampered)

    assert report.status is ObservationValidationStatus.FAIL
    check = next(check for check in report.checks if check.name == "hidden_events")
    assert check.reason_code == "FORBIDDEN_EVENT"


@pytest.mark.parametrize("probability_field", ("recognition_probability", "diagnosis_probability"))
def test_recorded_descendants_cannot_survive_zero_policy_probability(
    probability_field: str,
) -> None:
    frame = generate_observation_frame(
        _event_trajectory(),
        _policy(
            recognition_probability=1.0,
            diagnosis_probability=1.0,
            visit_probability=1.0,
        ),
        NamedRandomStreams(20260831, 0),
    )
    assert frame.truth.policy is not None
    zero_probability_policy = dataclasses.replace(
        frame.truth.policy,
        **{probability_field: 0.0},
    )
    unsealed_truth = dataclasses.replace(
        frame.truth,
        policy=zero_probability_policy,
        truth_hash=None,
    )
    resealed_truth = dataclasses.replace(
        unsealed_truth,
        truth_hash=observation_module._canonical_hash(
            (zero_probability_policy.to_mapping(), unsealed_truth)
        ),
    )
    tampered = dataclasses.replace(frame, truth=resealed_truth)

    report = validate_observation_frame(tampered)

    assert report.status is ObservationValidationStatus.FAIL
    check = next(check for check in report.checks if check.name == "hidden_events")
    assert check.reason_code == "FORBIDDEN_EVENT"


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
