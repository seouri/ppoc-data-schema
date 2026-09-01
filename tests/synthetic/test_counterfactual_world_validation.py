from __future__ import annotations

import dataclasses

import pytest

from synthetic.native.counterfactual import (
    CounterfactualPair,
    InterventionKind,
    generate_counterfactual_pair,
)
from synthetic.native.counterfactual_worlds import (
    CounterfactualEhrWorldPair,
    CounterfactualWorldValidationStatus,
    assemble_counterfactual_ehr_worlds,
    validate_counterfactual_ehr_worlds,
)
from synthetic.native.observations import MeasurementAvailability
from synthetic.native.resources import ResourceShape, ResourceSpec, SyntheticDemographics
from tests.synthetic.test_counterfactual_world_assembly import (
    AGES,
    PATIENT,
    _ancillary_policy,
    _descriptor,
    _familial_kernel,
    _kernel,
    _pair,
    _pair_from,
    _policy,
)


def _worlds(intervention: InterventionKind):
    return assemble_counterfactual_ehr_worlds(
        _pair(intervention),
        SyntheticDemographics(PATIENT.patient_id, "F"),
        _policy(),
        _descriptor(),
        _ancillary_policy(),
    )


@pytest.mark.parametrize(
    "intervention",
    (
        InterventionKind.PHYSIOLOGY_SEVERITY,
        InterventionKind.EARLIER_RECOGNITION,
        InterventionKind.TREATMENT_ADHERENCE,
    ),
)
def test_validator_passes_each_reviewed_resource_change_matrix(intervention: InterventionKind) -> None:
    worlds = _worlds(intervention)

    report = validate_counterfactual_ehr_worlds(worlds)

    assert report.status is CounterfactualWorldValidationStatus.PASS
    assert tuple(check.name for check in report.checks) == (
        "pair_binding",
        "shared_demographics",
        "shared_observation",
        "observation_invariants",
        "resource_invariants",
        "permitted_changes",
        "truth_boundary",
    )
    assert all(check.reason_code == "OK" for check in report.checks)


def test_validator_fails_visible_visit_tampering_even_when_private_truth_is_malformed() -> None:
    worlds = _worlds(InterventionKind.PHYSIOLOGY_SEVERITY)
    bundle = worlds.intervention.bundle
    assert bundle is not None
    visit = bundle.rows["visits"][0]
    object.__setattr__(
        visit,
        "values",
        tuple((name, "syn-unlinked" if name == "visit_id" else value) for name, value in visit.values),
    )
    object.__setattr__(worlds.intervention.frame, "truth", None)

    report = validate_counterfactual_ehr_worlds(worlds)

    assert report.status is CounterfactualWorldValidationStatus.FAIL
    assert next(check for check in report.checks if check.name == "resource_invariants").status is CounterfactualWorldValidationStatus.FAIL


def test_validator_marks_only_malformed_private_evidence_unevaluable() -> None:
    worlds = _worlds(InterventionKind.PHYSIOLOGY_SEVERITY)
    object.__setattr__(worlds.intervention.frame, "truth", None)

    report = validate_counterfactual_ehr_worlds(worlds)

    assert report.status is CounterfactualWorldValidationStatus.UNEVALUABLE
    assert any(check.status is CounterfactualWorldValidationStatus.UNEVALUABLE for check in report.checks)
    assert not any(check.status is CounterfactualWorldValidationStatus.FAIL for check in report.checks)


def test_shared_observation_marks_redacted_private_replay_evidence_unevaluable() -> None:
    worlds = _worlds(InterventionKind.PHYSIOLOGY_SEVERITY)
    object.__setattr__(worlds.intervention.frame.truth, "truth_hash", None)

    report = validate_counterfactual_ehr_worlds(worlds)

    check = next(item for item in report.checks if item.name == "shared_observation")
    assert report.status is CounterfactualWorldValidationStatus.UNEVALUABLE
    assert check.status is CounterfactualWorldValidationStatus.UNEVALUABLE
    assert check.reason_code == "INSUFFICIENT_EVIDENCE"
    assert not any(item.status is CounterfactualWorldValidationStatus.FAIL for item in report.checks)


def test_validator_rejects_recognition_measurement_and_physiology_event_changes() -> None:
    recognition = _worlds(InterventionKind.EARLIER_RECOGNITION)
    recognition_bundle = recognition.intervention.bundle
    assert recognition_bundle is not None
    measurement = recognition_bundle.rows["visits"][0]
    object.__setattr__(
        measurement,
        "values",
        tuple((name, 999.0 if name == "height_in" else value) for name, value in measurement.values),
    )
    assert validate_counterfactual_ehr_worlds(recognition).status is CounterfactualWorldValidationStatus.FAIL

    physiology = _worlds(InterventionKind.PHYSIOLOGY_SEVERITY)
    event = physiology.intervention.frame.events[0]
    object.__setattr__(event, "age_days", event.age_days + 1)
    assert validate_counterfactual_ehr_worlds(physiology).status is CounterfactualWorldValidationStatus.FAIL


def test_validator_rejects_treatment_measurement_difference_before_treatment_start() -> None:
    worlds = _worlds(InterventionKind.TREATMENT_ADHERENCE)
    bundle = worlds.intervention.bundle
    assert bundle is not None
    visit = bundle.rows["visits"][0]
    object.__setattr__(
        visit,
        "values",
        tuple((name, 999.0 if name == "height_in" else value) for name, value in visit.values),
    )

    report = validate_counterfactual_ehr_worlds(worlds)

    assert report.status is CounterfactualWorldValidationStatus.FAIL
    assert next(check for check in report.checks if check.name == "permitted_changes").status is CounterfactualWorldValidationStatus.FAIL


def test_validator_requires_measurement_invariance_when_treatment_start_is_absent() -> None:
    worlds = _worlds(InterventionKind.TREATMENT_ADHERENCE)
    object.__setattr__(worlds._pair.baseline.disorder, "treatment_start_age_days", None)
    object.__setattr__(worlds._pair.intervention.disorder, "treatment_start_age_days", None)

    report = validate_counterfactual_ehr_worlds(worlds)

    assert report.status is CounterfactualWorldValidationStatus.FAIL
    assert next(check for check in report.checks if check.name == "permitted_changes").status is CounterfactualWorldValidationStatus.FAIL


def test_validator_detects_tampered_shared_policy_metadata() -> None:
    worlds = _worlds(InterventionKind.PHYSIOLOGY_SEVERITY)
    object.__setattr__(worlds.observation_policy, "policy_version", "tampered-policy")

    report = validate_counterfactual_ehr_worlds(worlds)

    assert report.status is CounterfactualWorldValidationStatus.FAIL
    assert next(check for check in report.checks if check.name == "shared_observation").status is CounterfactualWorldValidationStatus.FAIL


def test_validator_detects_ancillary_visit_link_tampering_without_disclosing_the_link() -> None:
    worlds = _worlds(InterventionKind.PHYSIOLOGY_SEVERITY)
    bundle = worlds.intervention.bundle
    assert bundle is not None
    row = bundle.rows["labs"][0]
    object.__setattr__(
        row,
        "values",
        tuple((name, "syn-unlinked" if name == "visit_id" else value) for name, value in row.values),
    )

    report = validate_counterfactual_ehr_worlds(worlds)

    assert report.status is CounterfactualWorldValidationStatus.FAIL
    assert next(check for check in report.checks if check.name == "resource_invariants").status is CounterfactualWorldValidationStatus.FAIL
    assert "syn-unlinked" not in repr(report)


def test_validator_passes_unrecognized_and_non_ghd_empty_ancillary_pathways() -> None:
    unrecognized = assemble_counterfactual_ehr_worlds(
        _pair(InterventionKind.PHYSIOLOGY_SEVERITY),
        SyntheticDemographics(PATIENT.patient_id, "F"),
        dataclasses.replace(_policy(), recognition_probability=0.0, diagnosis_probability=0.0),
        _descriptor(),
        _ancillary_policy(),
    )
    non_ghd = assemble_counterfactual_ehr_worlds(
        _pair_from(_familial_kernel(), InterventionKind.EARLIER_RECOGNITION),
        SyntheticDemographics(PATIENT.patient_id, "F"),
        _policy(),
        _descriptor(),
        _ancillary_policy(),
    )

    assert validate_counterfactual_ehr_worlds(unrecognized).status is CounterfactualWorldValidationStatus.PASS
    assert validate_counterfactual_ehr_worlds(non_ghd).status is CounterfactualWorldValidationStatus.PASS


def test_validator_marks_malformed_hidden_pair_binding_unevaluable_when_visible_worlds_remain_valid() -> None:
    worlds = _worlds(InterventionKind.PHYSIOLOGY_SEVERITY)
    object.__setattr__(worlds, "_pair", object())

    report = validate_counterfactual_ehr_worlds(worlds)

    assert report.status is CounterfactualWorldValidationStatus.UNEVALUABLE
    assert next(check for check in report.checks if check.name == "pair_binding").status is CounterfactualWorldValidationStatus.UNEVALUABLE


def test_validator_rejects_cross_pair_frame_and_bundle_splice_with_typed_but_wrong_provenance() -> None:
    worlds = _worlds(InterventionKind.EARLIER_RECOGNITION)
    other = assemble_counterfactual_ehr_worlds(
        generate_counterfactual_pair(
            _kernel(), PATIENT, AGES, 20260901, 12, InterventionKind.EARLIER_RECOGNITION
        ),
        SyntheticDemographics(PATIENT.patient_id, "F"),
        _policy(),
        _descriptor(),
        _ancillary_policy(),
    )
    assert worlds._pair.baseline_context.run_seed != other._pair.baseline_context.run_seed
    object.__setattr__(worlds.intervention, "frame", other.intervention.frame)
    object.__setattr__(worlds.intervention, "bundle", other.intervention.bundle)

    report = validate_counterfactual_ehr_worlds(worlds)

    assert report.status is CounterfactualWorldValidationStatus.FAIL
    assert next(check for check in report.checks if check.name == "pair_binding").status is CounterfactualWorldValidationStatus.FAIL


def test_constructor_and_validator_reject_same_trajectory_frame_replayed_with_a_different_seed() -> None:
    pair = _pair(InterventionKind.PHYSIOLOGY_SEVERITY)
    policy = dataclasses.replace(
        _policy(),
        height_error_sd_cm=0.7,
        weight_error_sd_kg=0.4,
        head_circumference_error_sd_cm=0.3,
    )
    demographics = SyntheticDemographics(PATIENT.patient_id, "F")
    worlds = assemble_counterfactual_ehr_worlds(
        pair, demographics, policy, _descriptor(), _ancillary_policy()
    )
    alternate_pair = CounterfactualPair(
        pair.baseline,
        pair.intervention,
        dataclasses.replace(pair.baseline_context, run_seed=20260999),
        dataclasses.replace(pair.intervention_context, run_seed=20260999),
        pair.matrix,
    )
    alternate = assemble_counterfactual_ehr_worlds(
        alternate_pair, demographics, policy, _descriptor(), _ancillary_policy()
    )

    assert tuple(
        (visit.age_days, tuple(item.availability for item in visit.measurements))
        for visit in worlds.intervention.frame.visits
    ) == tuple(
        (visit.age_days, tuple(item.availability for item in visit.measurements))
        for visit in alternate.intervention.frame.visits
    )
    assert worlds.intervention.frame.events == alternate.intervention.frame.events
    assert worlds.intervention.frame.visits != alternate.intervention.frame.visits
    with pytest.raises(ValueError, match="observation"):
        CounterfactualEhrWorldPair(
            worlds.baseline,
            alternate.intervention,
            worlds.matrix,
            worlds.observation_policy,
            worlds.shape,
            worlds._pair,
            worlds._ancillary_policy,
            worlds._observation_stream_identities,
            worlds._observation_stream_seed,
            worlds._observation_stream_patient_index,
        )

    object.__setattr__(worlds.intervention, "frame", alternate.intervention.frame)
    object.__setattr__(worlds.intervention, "bundle", alternate.intervention.bundle)

    report = validate_counterfactual_ehr_worlds(worlds)

    check = next(item for item in report.checks if item.name == "shared_observation")
    assert report.status is CounterfactualWorldValidationStatus.FAIL
    assert check.status is CounterfactualWorldValidationStatus.FAIL
    assert check.reason_code == "SHARED_OBSERVATION_INVALID"


def test_validator_detects_changed_demographics_and_patient_row_at_the_shared_demographics_check() -> None:
    worlds = _worlds(InterventionKind.PHYSIOLOGY_SEVERITY)
    object.__setattr__(worlds.intervention, "demographics", SyntheticDemographics(PATIENT.patient_id, "M"))

    demographics_report = validate_counterfactual_ehr_worlds(worlds)

    assert demographics_report.status is CounterfactualWorldValidationStatus.FAIL
    assert next(check for check in demographics_report.checks if check.name == "shared_demographics").status is CounterfactualWorldValidationStatus.FAIL
    assert PATIENT.patient_id not in repr(demographics_report)

    worlds = _worlds(InterventionKind.PHYSIOLOGY_SEVERITY)
    patient = worlds.intervention.bundle.rows["patients"][0]  # type: ignore[union-attr]
    object.__setattr__(
        patient,
        "values",
        tuple((name, "M" if name == "sex" else value) for name, value in patient.values),
    )

    patient_row_report = validate_counterfactual_ehr_worlds(worlds)

    assert patient_row_report.status is CounterfactualWorldValidationStatus.FAIL
    assert next(check for check in patient_row_report.checks if check.name == "shared_demographics").status is CounterfactualWorldValidationStatus.FAIL


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    (("age_in_days", 1), ("visit_id", "syn-unlinked")),
)
def test_validator_detects_visit_age_and_identifier_tampering_independently(
    field_name: str, replacement: object
) -> None:
    worlds = _worlds(InterventionKind.PHYSIOLOGY_SEVERITY)
    visit = worlds.intervention.bundle.rows["visits"][0]  # type: ignore[union-attr]
    object.__setattr__(
        visit,
        "values",
        tuple((name, replacement if name == field_name else value) for name, value in visit.values),
    )

    report = validate_counterfactual_ehr_worlds(worlds)

    assert report.status is CounterfactualWorldValidationStatus.FAIL
    assert next(check for check in report.checks if check.name == "resource_invariants").status is CounterfactualWorldValidationStatus.FAIL
    assert str(replacement) not in repr(report)


def test_validator_detects_measurement_availability_and_clinical_descendant_tampering() -> None:
    worlds = _worlds(InterventionKind.PHYSIOLOGY_SEVERITY)
    measurement = next(
        item
        for item in worlds.intervention.frame.visits[0].measurements
        if item.recorded_value is not None
    )
    object.__setattr__(measurement, "availability", MeasurementAvailability.MISSING)

    availability_report = validate_counterfactual_ehr_worlds(worlds)

    assert availability_report.status is CounterfactualWorldValidationStatus.FAIL
    assert next(check for check in availability_report.checks if check.name == "observation_invariants").status is CounterfactualWorldValidationStatus.FAIL

    worlds = _worlds(InterventionKind.PHYSIOLOGY_SEVERITY)
    descendant = worlds.intervention.bundle.clinical_descendants[0]  # type: ignore[union-attr]
    object.__setattr__(descendant, "code", "SYN-TAMPERED")

    descendant_report = validate_counterfactual_ehr_worlds(worlds)

    assert descendant_report.status is CounterfactualWorldValidationStatus.FAIL
    assert next(check for check in descendant_report.checks if check.name == "resource_invariants").status is CounterfactualWorldValidationStatus.FAIL
    assert "SYN-TAMPERED" not in repr(descendant_report)


def test_validator_detects_non_link_ancillary_values_and_descriptor_shape_order_tampering() -> None:
    worlds = _worlds(InterventionKind.PHYSIOLOGY_SEVERITY)
    lab = worlds.intervention.bundle.rows["labs"][0]  # type: ignore[union-attr]
    object.__setattr__(
        lab,
        "values",
        tuple((name, "SYN-ALTERED" if name == "result_component_name" else value) for name, value in lab.values),
    )

    ancillary_report = validate_counterfactual_ehr_worlds(worlds)

    assert ancillary_report.status is CounterfactualWorldValidationStatus.FAIL
    assert next(check for check in ancillary_report.checks if check.name == "resource_invariants").status is CounterfactualWorldValidationStatus.FAIL
    assert "SYN-ALTERED" not in repr(ancillary_report)

    worlds = _worlds(InterventionKind.PHYSIOLOGY_SEVERITY)
    tampered_shape = ResourceShape(
        tuple(
            ResourceSpec(spec.name, tuple(reversed(spec.field_names)))
            if spec.name == "labs"
            else spec
            for spec in worlds.shape.resources
        )
    )
    object.__setattr__(worlds, "shape", tampered_shape)

    shape_report = validate_counterfactual_ehr_worlds(worlds)

    assert shape_report.status is CounterfactualWorldValidationStatus.FAIL
    assert next(check for check in shape_report.checks if check.name == "resource_invariants").status is CounterfactualWorldValidationStatus.FAIL


def test_validator_detects_bundle_source_frame_binding_tampering() -> None:
    worlds = _worlds(InterventionKind.PHYSIOLOGY_SEVERITY)
    object.__setattr__(worlds.intervention.bundle, "source_frame", worlds.baseline.frame)  # type: ignore[arg-type]

    report = validate_counterfactual_ehr_worlds(worlds)

    assert report.status is CounterfactualWorldValidationStatus.FAIL
    assert next(check for check in report.checks if check.name == "pair_binding").status is CounterfactualWorldValidationStatus.FAIL


def test_validator_returns_only_unevaluable_checks_for_an_untyped_world_container() -> None:
    report = validate_counterfactual_ehr_worlds(object())  # type: ignore[arg-type]

    assert report.status is CounterfactualWorldValidationStatus.UNEVALUABLE
    assert all(check.status is CounterfactualWorldValidationStatus.UNEVALUABLE for check in report.checks)


def test_validator_rejects_private_object_in_a_visible_row_value() -> None:
    worlds = _worlds(InterventionKind.PHYSIOLOGY_SEVERITY)
    bundle = worlds.intervention.bundle
    assert bundle is not None
    row = bundle.rows["labs"][0]
    object.__setattr__(
        row,
        "values",
        tuple((name, worlds.intervention.frame if name == "result_value" else value) for name, value in row.values),
    )

    report = validate_counterfactual_ehr_worlds(worlds)

    assert report.status is CounterfactualWorldValidationStatus.FAIL
    assert next(check for check in report.checks if check.name == "truth_boundary").status is CounterfactualWorldValidationStatus.FAIL


def test_validator_returns_a_redacted_truth_boundary_failure_for_a_cyclic_visible_mapping() -> None:
    worlds = _worlds(InterventionKind.PHYSIOLOGY_SEVERITY)
    bundle = worlds.intervention.bundle
    assert bundle is not None
    row = bundle.rows["labs"][0]
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    object.__setattr__(
        row,
        "values",
        tuple((name, cyclic if name == "result_value" else value) for name, value in row.values),
    )

    report = validate_counterfactual_ehr_worlds(worlds)

    check = next(item for item in report.checks if item.name == "truth_boundary")
    assert report.status is CounterfactualWorldValidationStatus.FAIL
    assert check.status is CounterfactualWorldValidationStatus.FAIL
    assert check.reason_code == "TRUTH_BOUNDARY_INVALID"
    assert set(report.to_mapping()) == {"status", "check_counts", "checks"}
    assert "self" not in repr(report)


def test_validator_passes_an_earlier_recognition_world_with_partial_recorded_events() -> None:
    worlds = assemble_counterfactual_ehr_worlds(
        _pair(InterventionKind.EARLIER_RECOGNITION),
        SyntheticDemographics(PATIENT.patient_id, "F"),
        dataclasses.replace(_policy(), diagnosis_probability=0.0),
        _descriptor(),
        _ancillary_policy(),
    )

    assert all(member.frame.events for member in (worlds.baseline, worlds.intervention))
    assert all(
        event.event_kind.value != "diagnosis"
        for member in (worlds.baseline, worlds.intervention)
        for event in member.frame.events
    )
    assert validate_counterfactual_ehr_worlds(worlds).status is CounterfactualWorldValidationStatus.PASS
