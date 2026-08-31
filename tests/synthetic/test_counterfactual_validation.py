from __future__ import annotations

import dataclasses

import pytest

from synthetic.models import (
    ClinicalEvent,
    DisorderKind,
    GrowthRegime,
    PatientState,
)
from synthetic.native.age_regime_disorder import AgeRegimeDisorderKernel
from synthetic.native.age_regimes import AgeRegimeTrajectoryKernel
from synthetic.native.clinical_modules import (
    FamilialShortStatureConfig,
    FamilialShortStatureModule,
    GrowthHormoneDeficiencyConfig,
    GrowthHormoneDeficiencyModule,
)
from synthetic.native.counterfactual import (
    CounterfactualValidationStatus,
    InterventionKind,
    generate_counterfactual_pair,
    validate_counterfactual_pair,
)
from synthetic.randomness import NamedRandomStreams
from tests.synthetic.fakes import RegimeLinearTestReference

PATIENT = PatientState("syn-counterfactual-validation", "F", "F")
SEED = 20260831
INDEX = 3


def _kernel(module: object) -> AgeRegimeDisorderKernel:
    return AgeRegimeDisorderKernel(
        AgeRegimeTrajectoryKernel(RegimeLinearTestReference()), module  # type: ignore[arg-type]
    )


def _familial_kernel() -> AgeRegimeDisorderKernel:
    return _kernel(
        FamilialShortStatureModule(
            FamilialShortStatureConfig(
                severity_min=1.0,
                severity_max=1.0,
                phenotype_age_days=730,
                recognition_age_days=1460,
                workup_age_days=1825,
                diagnosis_age_days=2190,
            )
        )
    )


def _treated_ghd_kernel() -> AgeRegimeDisorderKernel:
    return _kernel(
        GrowthHormoneDeficiencyModule(
            GrowthHormoneDeficiencyConfig(
                onset_min_age_days=730,
                onset_max_age_days=730,
                severity_min=1.0,
                severity_max=1.0,
                progression_days=730,
                phenotype_delay_days=90,
                recognition_delay_days=90,
                workup_delay_days=30,
                diagnosis_delay_days=30,
                treatment_probability=1.0,
                treatment_delay_days=30,
                response_days=365,
                treatment_response_min=0.8,
                treatment_response_max=0.8,
            )
        )
    )


def test_kernel_samples_and_replays_both_hidden_states() -> None:
    kernel = _treated_ghd_kernel()
    streams = NamedRandomStreams(SEED, INDEX)
    age_state, disorder_state = kernel.sample_state(PATIENT, streams)

    replayed = kernel.generate(
        PATIENT,
        (0, 365, 730, 1000, 1500, 4000),
        streams,
        state=(age_state, disorder_state),
    )
    ordinary = kernel.generate(
        PATIENT,
        (0, 365, 730, 1000, 1500, 4000),
        streams,
    )

    assert replayed == ordinary


def test_physiology_severity_replays_shared_states_and_changes_only_growth() -> None:
    pair = generate_counterfactual_pair(
        _treated_ghd_kernel(),
        PATIENT,
        (0, 365, 730, 900, 1000, 1500, 2500, 4000),
        SEED,
        INDEX,
        InterventionKind.PHYSIOLOGY_SEVERITY,
    )

    assert pair.baseline.physiology.state == pair.intervention.physiology.state
    assert pair.baseline.disorder == pair.intervention.disorder
    assert pair.baseline_context.stream_identity("regime.birth") == (
        pair.intervention_context.stream_identity("regime.birth")
    )
    assert any(
        left.height_z != right.height_z or left.bmi_z != right.bmi_z
        for left, right in zip(
            pair.baseline.physiology.points,
            pair.intervention.physiology.points,
            strict=True,
        )
    )

    report = validate_counterfactual_pair(pair)
    assert report.status is CounterfactualValidationStatus.PASS
    assert report.to_mapping()["status"] == "PASS"


def test_earlier_recognition_changes_event_timing_but_not_growth() -> None:
    pair = generate_counterfactual_pair(
        _familial_kernel(),
        PATIENT,
        (0, 365, 730, 1460, 1825, 2190, 4000),
        SEED,
        INDEX,
        InterventionKind.EARLIER_RECOGNITION,
    )

    baseline_recognition = [
        event.age_days
        for event in pair.baseline.events
        if event.event_type == "recognition_opportunity"
    ]
    intervention_recognition = [
        event.age_days
        for event in pair.intervention.events
        if event.event_type == "recognition_opportunity"
    ]
    assert intervention_recognition[0] < baseline_recognition[0]
    assert pair.baseline.physiology == pair.intervention.physiology
    assert validate_counterfactual_pair(pair).status is CounterfactualValidationStatus.PASS


def test_treatment_adherence_changes_response_and_post_treatment_growth() -> None:
    pair = generate_counterfactual_pair(
        _treated_ghd_kernel(),
        PATIENT,
        (0, 365, 730, 900, 999, 1000, 1200, 1500, 2500, 4000),
        SEED,
        INDEX,
        InterventionKind.TREATMENT_ADHERENCE,
    )

    assert pair.baseline.disorder.kind is DisorderKind.GROWTH_HORMONE_DEFICIENCY
    assert pair.baseline.disorder.onset_age_days == pair.intervention.disorder.onset_age_days
    assert pair.baseline.disorder.severity == pair.intervention.disorder.severity
    assert pair.baseline.disorder.puberty_delay_days == pair.intervention.disorder.puberty_delay_days
    assert pair.baseline.disorder.treatment_start_age_days == (
        pair.intervention.disorder.treatment_start_age_days
    )
    assert pair.baseline.disorder.treatment_response != pair.intervention.disorder.treatment_response
    assert validate_counterfactual_pair(pair).status is CounterfactualValidationStatus.PASS


@pytest.mark.parametrize(
    "intervention",
    [InterventionKind.UTILIZATION_INTENSITY, InterventionKind.MEASUREMENT_ERROR_REMOVAL],
)
def test_unsupported_observation_interventions_fail_closed(intervention: InterventionKind) -> None:
    with pytest.raises(ValueError, match="not supported"):
        generate_counterfactual_pair(
            _familial_kernel(),
            PATIENT,
            (0, 365, 730, 1460, 2190),
            SEED,
            INDEX,
            intervention,
        )


def test_validation_fails_on_a_forbidden_recognition_change() -> None:
    pair = generate_counterfactual_pair(
        _familial_kernel(),
        PATIENT,
        (0, 365, 730, 1460, 1825, 2190, 4000),
        SEED,
        INDEX,
        InterventionKind.PHYSIOLOGY_SEVERITY,
    )
    events = list(pair.intervention.events)
    index = next(
        index for index, event in enumerate(events) if event.event_type == "recognition_opportunity"
    )
    events[index] = dataclasses.replace(events[index], age_days=events[index].age_days + 1)
    tampered = dataclasses.replace(
        pair,
        intervention=dataclasses.replace(pair.intervention, events=tuple(events)),
    )

    report = validate_counterfactual_pair(tampered)
    assert report.status is CounterfactualValidationStatus.FAIL
    assert any(check.reason_code == "INVARIANT_LAYER_CHANGED" for check in report.checks)


def test_validation_is_unevaluable_when_a_required_window_is_not_observed() -> None:
    pair = generate_counterfactual_pair(
        _treated_ghd_kernel(),
        PATIENT,
        (1500, 2500, 4000),
        SEED,
        INDEX,
        InterventionKind.TREATMENT_ADHERENCE,
    )

    report = validate_counterfactual_pair(pair)
    assert report.status is CounterfactualValidationStatus.UNEVALUABLE
    assert any(check.status is CounterfactualValidationStatus.UNEVALUABLE for check in report.checks)


def test_validation_report_is_aggregate_only() -> None:
    pair = generate_counterfactual_pair(
        _familial_kernel(),
        PATIENT,
        (0, 365, 730, 1460, 1825, 2190, 4000),
        SEED,
        INDEX,
        InterventionKind.EARLIER_RECOGNITION,
    )
    report = validate_counterfactual_pair(pair)
    mapping = report.to_mapping()
    serialized = str(mapping) + repr(report)

    assert PATIENT.patient_id not in serialized
    assert "patient_id" not in serialized
    assert "hash" not in serialized
    assert "stream_identity" not in serialized
    assert "age_days" not in serialized
    assert set(mapping) == {"status", "check_counts", "checks"}


def test_event_order_is_checked_as_causal_phase_order() -> None:
    pair = generate_counterfactual_pair(
        _familial_kernel(),
        PATIENT,
        (0, 365, 730, 1460, 1825, 2190, 4000),
        SEED,
        INDEX,
        InterventionKind.EARLIER_RECOGNITION,
    )
    malformed = dataclasses.replace(
        pair.intervention,
        events=(
            ClinicalEvent(PATIENT.patient_id, 1000, "recorded_diagnosis", None, False),
            ClinicalEvent(PATIENT.patient_id, 1100, "recognition_opportunity", None, False),
        ),
    )
    tampered = dataclasses.replace(pair, intervention=malformed)

    report = validate_counterfactual_pair(tampered)
    assert report.status is CounterfactualValidationStatus.FAIL
    assert any(check.reason_code == "EVENT_ORDER_INVALID" for check in report.checks)


def test_treatment_validation_is_unevaluable_when_the_manipulated_layer_is_unchanged() -> None:
    pair = generate_counterfactual_pair(
        _treated_ghd_kernel(),
        PATIENT,
        (0, 365, 730, 900, 999, 1000, 1200, 1500, 2500, 4000),
        SEED,
        INDEX,
        InterventionKind.TREATMENT_ADHERENCE,
    )
    unchanged = dataclasses.replace(pair, intervention=pair.baseline)

    report = validate_counterfactual_pair(unchanged)
    permitted_changes = next(check for check in report.checks if check.name == "permitted_changes")

    assert report.status is CounterfactualValidationStatus.UNEVALUABLE
    assert permitted_changes.status is CounterfactualValidationStatus.UNEVALUABLE
    assert permitted_changes.reason_code == "MANIPULATED_LAYER_UNCHANGED"


@pytest.mark.parametrize(
    ("field", "value"),
    [("code", "tampered-treatment"), ("hidden", True)],
)
def test_treatment_adherence_rejects_treatment_event_payload_tampering(
    field: str, value: object
) -> None:
    pair = generate_counterfactual_pair(
        _treated_ghd_kernel(),
        PATIENT,
        (0, 365, 730, 900, 999, 1000, 1200, 1500, 2500, 4000),
        SEED,
        INDEX,
        InterventionKind.TREATMENT_ADHERENCE,
    )
    events = list(pair.intervention.events)
    index = next(
        index for index, event in enumerate(events) if event.event_type == "treatment_start"
    )
    events[index] = dataclasses.replace(events[index], **{field: value})
    tampered = dataclasses.replace(
        pair,
        intervention=dataclasses.replace(pair.intervention, events=tuple(events)),
    )

    report = validate_counterfactual_pair(tampered)

    assert report.status is CounterfactualValidationStatus.FAIL
    assert any(check.reason_code == "TREATMENT_PAYLOAD_MISMATCH" for check in report.checks)


def _strip_growth_z_scores(trajectory: object, *, stature: bool, mass: bool):
    points = []
    for point in trajectory.physiology.points:  # type: ignore[attr-defined]
        points.append(
            dataclasses.replace(
                point,
                length_z=None if stature else point.length_z,
                height_z=None if stature else point.height_z,
                weight_z=None if mass else point.weight_z,
                bmi_z=None if mass else point.bmi_z,
            )
        )
    return dataclasses.replace(trajectory, physiology=dataclasses.replace(  # type: ignore[attr-defined]
        trajectory.physiology, points=tuple(points)  # type: ignore[attr-defined]
    ))


@pytest.mark.parametrize(
    ("stature", "mass"),
    [(True, True), (True, False), (False, True)],
)
def test_missing_or_partial_growth_z_score_evidence_is_unevaluable(
    stature: bool, mass: bool
) -> None:
    pair = generate_counterfactual_pair(
        _familial_kernel(),
        PATIENT,
        (0, 365, 730, 1460, 1825, 2190, 4000),
        SEED,
        INDEX,
        InterventionKind.EARLIER_RECOGNITION,
    )
    malformed = dataclasses.replace(
        pair,
        baseline=_strip_growth_z_scores(pair.baseline, stature=stature, mass=mass),
        intervention=_strip_growth_z_scores(pair.intervention, stature=stature, mass=mass),
    )

    report = validate_counterfactual_pair(malformed)
    age_coverage = next(check for check in report.checks if check.name == "age_coverage")

    assert report.status is CounterfactualValidationStatus.UNEVALUABLE
    assert age_coverage.status is CounterfactualValidationStatus.UNEVALUABLE
    assert age_coverage.reason_code == "GROWTH_EVIDENCE_MISSING"


def test_missing_growth_evidence_in_one_world_is_not_a_forbidden_change() -> None:
    pair = generate_counterfactual_pair(
        _familial_kernel(),
        PATIENT,
        (0, 365, 730, 1460, 1825, 2190, 4000),
        SEED,
        INDEX,
        InterventionKind.EARLIER_RECOGNITION,
    )
    malformed = dataclasses.replace(
        pair,
        baseline=_strip_growth_z_scores(pair.baseline, stature=True, mass=True),
    )

    report = validate_counterfactual_pair(malformed)
    age_coverage = next(check for check in report.checks if check.name == "age_coverage")

    assert report.status is CounterfactualValidationStatus.UNEVALUABLE
    assert age_coverage.status is CounterfactualValidationStatus.UNEVALUABLE


def test_point_level_growth_regime_label_tampering_fails_validation() -> None:
    pair = generate_counterfactual_pair(
        _familial_kernel(),
        PATIENT,
        (0, 365, 730, 1460, 1825, 2190, 4000),
        SEED,
        INDEX,
        InterventionKind.EARLIER_RECOGNITION,
    )
    points = list(pair.intervention.physiology.points)
    points[3] = dataclasses.replace(points[3], regime=GrowthRegime.PUBERTY)
    tampered = dataclasses.replace(
        pair,
        intervention=dataclasses.replace(
            pair.intervention,
            physiology=dataclasses.replace(pair.intervention.physiology, points=tuple(points)),
        ),
    )

    report = validate_counterfactual_pair(tampered)

    assert report.status is CounterfactualValidationStatus.FAIL
    assert any(check.reason_code == "INVARIANT_LAYER_CHANGED" for check in report.checks)


@pytest.mark.parametrize("invalid_age", [False, 0.5, -1])
def test_validation_marks_non_integer_or_negative_event_ages_unevaluable(
    invalid_age: object,
) -> None:
    pair = generate_counterfactual_pair(
        _treated_ghd_kernel(),
        PATIENT,
        (0, 365, 730, 900, 999, 1000, 1200, 1500, 2500, 4000),
        SEED,
        INDEX,
        InterventionKind.TREATMENT_ADHERENCE,
    )

    def with_invalid_first_event_age(trajectory: object):
        events = list(trajectory.events)  # type: ignore[attr-defined]
        events[0] = dataclasses.replace(events[0], age_days=invalid_age)
        return dataclasses.replace(trajectory, events=tuple(events))

    malformed = dataclasses.replace(
        pair,
        baseline=with_invalid_first_event_age(pair.baseline),
        intervention=with_invalid_first_event_age(pair.intervention),
    )

    report = validate_counterfactual_pair(malformed)
    event_order = next(check for check in report.checks if check.name == "event_order")

    assert report.status is CounterfactualValidationStatus.UNEVALUABLE
    assert event_order.status is CounterfactualValidationStatus.UNEVALUABLE
    assert event_order.reason_code == "MALFORMED_PAIR"


@pytest.mark.parametrize(
    ("field", "value"),
    [("code", "tampered-recognition"), ("hidden", True)],
)
def test_earlier_recognition_rejects_recognition_payload_tampering(
    field: str, value: object
) -> None:
    pair = generate_counterfactual_pair(
        _familial_kernel(),
        PATIENT,
        (0, 365, 730, 1460, 1825, 2190, 4000),
        SEED,
        INDEX,
        InterventionKind.EARLIER_RECOGNITION,
    )
    events = list(pair.intervention.events)
    index = next(
        index for index, event in enumerate(events) if event.event_type == "recognition_opportunity"
    )
    events[index] = dataclasses.replace(events[index], **{field: value})
    tampered = dataclasses.replace(
        pair,
        intervention=dataclasses.replace(pair.intervention, events=tuple(events)),
    )

    report = validate_counterfactual_pair(tampered)

    assert report.status is CounterfactualValidationStatus.FAIL
    assert any(check.reason_code == "FORBIDDEN_LAYER_CHANGED" for check in report.checks)


@pytest.mark.parametrize(
    ("field", "value"),
    [("age_days", 2191), ("code", "tampered-diagnosis"), ("hidden", True)],
)
def test_earlier_recognition_rejects_downstream_event_tampering(
    field: str, value: object
) -> None:
    pair = generate_counterfactual_pair(
        _familial_kernel(),
        PATIENT,
        (0, 365, 730, 1460, 1825, 2190, 4000),
        SEED,
        INDEX,
        InterventionKind.EARLIER_RECOGNITION,
    )
    events = list(pair.intervention.events)
    index = next(
        index for index, event in enumerate(events) if event.event_type == "recorded_diagnosis"
    )
    events[index] = dataclasses.replace(events[index], **{field: value})
    tampered = dataclasses.replace(
        pair,
        intervention=dataclasses.replace(pair.intervention, events=tuple(events)),
    )

    report = validate_counterfactual_pair(tampered)

    assert report.status is CounterfactualValidationStatus.FAIL
    assert any(check.reason_code == "FORBIDDEN_LAYER_CHANGED" for check in report.checks)


def test_validation_marks_treatment_outcome_state_mismatch_unevaluable() -> None:
    pair = generate_counterfactual_pair(
        _treated_ghd_kernel(),
        PATIENT,
        (0, 365, 730, 900, 999, 1000, 1200, 1500, 2500, 4000),
        SEED,
        INDEX,
        InterventionKind.TREATMENT_ADHERENCE,
    )
    events = list(pair.intervention.events)
    index = next(
        index for index, event in enumerate(events) if event.event_type == "treatment_nonresponse"
    )
    events[index] = dataclasses.replace(events[index], event_type="treatment_response")
    malformed = dataclasses.replace(
        pair,
        intervention=dataclasses.replace(pair.intervention, events=tuple(events)),
    )

    report = validate_counterfactual_pair(malformed)
    event_order = next(check for check in report.checks if check.name == "event_order")

    assert report.status is CounterfactualValidationStatus.UNEVALUABLE
    assert event_order.status is CounterfactualValidationStatus.UNEVALUABLE
    assert event_order.reason_code == "MALFORMED_PAIR"
