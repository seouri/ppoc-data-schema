from __future__ import annotations

import dataclasses

import pytest

from synthetic.native.counterfactual import InterventionKind
from synthetic.native.counterfactual_worlds import (
    CounterfactualWorldValidationStatus,
    assemble_counterfactual_ehr_worlds,
    validate_counterfactual_ehr_worlds,
)
from synthetic.native.resources import SyntheticDemographics
from tests.synthetic.test_counterfactual_world_assembly import (
    PATIENT,
    _ancillary_policy,
    _descriptor,
    _familial_kernel,
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
