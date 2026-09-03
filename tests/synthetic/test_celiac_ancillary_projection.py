from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from synthetic.cohort import CohortMember
from synthetic.models import DisorderKind, LatentDisorderState
from synthetic.native.celiac_ancillary import (
    CELIAC_ANCILLARY_RESOURCE_NAMES,
    CELIAC_DIAGNOSIS_CODE,
    CELIAC_LAB_RESULT_FLAG,
    CELIAC_MEDICATION_NAME,
    CELIAC_MEDICATION_RECORD_TYPE,
    CELIAC_REFERRAL_SPECIALTY,
    CELIAC_TOTAL_IGA_COMPONENT,
    CELIAC_TTG_IGA_COMPONENT,
    CeliacAncillaryPolicy,
    CeliacAncillaryProjectionUnavailable,
    project_celiac_ancillary_resources,
)
from synthetic.native.observations import (
    ObservationValidationStatus,
    RecordedEventKind,
    generate_observation_frame,
    validate_observation_frame,
)
from synthetic.native.resources import ResourceShape, SyntheticDemographics
from synthetic.randomness import NamedRandomStreams
from tests.synthetic.test_observation_generation import (
    _event_trajectory,
    _policy,
    _trajectory,
)

ROOT = Path(__file__).resolve().parents[2]
PATIENT_ID = "syn-observation-patient"


def _shape() -> ResourceShape:
    descriptor = json.loads((ROOT / "datapackage.json").read_text(encoding="utf-8"))
    return ResourceShape.from_descriptor(descriptor)


def _policy_ancillary(**changes: object) -> CeliacAncillaryPolicy:
    values: dict[str, object] = {
        "policy_id": "celiac-ancillary-policy-v1",
        "policy_version": "1",
        "result_delay_days": 7,
    }
    values.update(changes)
    return CeliacAncillaryPolicy(**values)  # type: ignore[arg-type]


def _member(
    *,
    treatment: bool = True,
    recognized: bool = True,
    diagnosed: bool = True,
    kind: DisorderKind = DisorderKind.CELIAC_DISEASE,
    same_age_events: bool = False,
    visit_probability: float = 1.0,
    workup: bool = True,
    window_start_age_days: int = 0,
) -> CohortMember:
    source = _event_trajectory()
    events = source.events
    if same_age_events:
        events = tuple(
            dataclasses.replace(
                event,
                age_days=700,
            )
            if event.event_type
            in {"recognition_opportunity", "workup", "recorded_diagnosis"}
            else event
            for event in events
        )
    if not treatment:
        events = tuple(
            event
            for event in events
            if event.event_type not in {"treatment_start", "treatment_response"}
        )
    if not workup:
        events = tuple(event for event in events if event.event_type != "workup")
    trajectory = dataclasses.replace(
        source,
        disorder=LatentDisorderState(
            kind,
            500,
            0.8,
            treatment_start_age_days=1800 if treatment else None,
            treatment_response=0.5 if treatment else 0.0,
        ),
        events=events,
    )
    frame = generate_observation_frame(
        trajectory,
        _policy(
            window_start_age_days=window_start_age_days,
            visit_probability=visit_probability,
            recognition_probability=1.0 if recognized else 0.0,
            diagnosis_probability=1.0 if diagnosed else 0.0,
        ),
        NamedRandomStreams(6, 0),
    )
    assert validate_observation_frame(frame).status is ObservationValidationStatus.PASS
    return CohortMember(SyntheticDemographics(PATIENT_ID), trajectory, frame, None)


def _resources(member: CohortMember, **policy_changes: object) -> dict[str, object]:
    return project_celiac_ancillary_resources(
        member,
        _shape(),
        _policy_ancillary(**policy_changes),
    ).to_mapping()["resources"]  # type: ignore[no-any-return]


def _expected_ancillary_id(role: str) -> str:
    material = f"celiac-ancillary-id-v1\x1f{PATIENT_ID}\x1f{role}".encode()
    return f"syn-{hashlib.sha256(material).hexdigest()}"


def test_diagnosed_celiac_projects_exact_four_resource_contract() -> None:
    member = _member()
    resources = _resources(member)

    assert tuple(resources) == CELIAC_ANCILLARY_RESOURCE_NAMES  # type: ignore[arg-type]
    assert len(resources["referrals"]) == 1  # type: ignore[index]
    assert len(resources["labs"]) == 2  # type: ignore[index]
    assert len(resources["problem_list"]) == 1  # type: ignore[index]
    assert len(resources["medications"]) == 1  # type: ignore[index]

    visible_by_kind = {event.event_kind: event for event in member.frame.events}
    visible_visit_by_source = {
        opportunity.source_point_index: visit
        for opportunity, visit in zip(
            (item for item in member.frame.truth.opportunities if item.realized),
            member.frame.visits,
            strict=True,
        )
    }
    recognition = visible_by_kind[RecordedEventKind.RECOGNITION]
    workup = visible_by_kind[RecordedEventKind.WORKUP]
    diagnosis = visible_by_kind[RecordedEventKind.DIAGNOSIS]
    recognition_visit = visible_visit_by_source[recognition.opportunity_index]
    workup_visit = visible_visit_by_source[workup.opportunity_index]
    diagnosis_visit = visible_visit_by_source[diagnosis.opportunity_index]

    referral = resources["referrals"][0]  # type: ignore[index]
    assert tuple(referral) == _shape().field_names("referrals")
    assert referral["patient_id"] == PATIENT_ID
    assert referral["visit_id"] == recognition_visit.visit_id
    assert referral["referral_date_age_in_days"] == recognition.age_days
    assert referral["requested_specialty"] == CELIAC_REFERRAL_SPECIALTY
    assert referral["referral_number_of_visits"] == 1

    labs = resources["labs"]  # type: ignore[assignment]
    assert all(tuple(row) == _shape().field_names("labs") for row in labs)
    assert all(row["visit_id"] == workup_visit.visit_id for row in labs)
    assert labs[0]["lab_order_id"] == labs[1]["lab_order_id"]
    assert [row["result_line_num"] for row in labs] == [1, 2]
    assert [row["lab_order_date_age_in_days"] for row in labs] == [workup.age_days] * 2
    assert [row["lab_result_date_age_in_days"] for row in labs] == [workup.age_days + 7] * 2
    assert [row["result_component_name"] for row in labs] == [
        CELIAC_TTG_IGA_COMPONENT,
        CELIAC_TOTAL_IGA_COMPONENT,
    ]
    assert all(row["lab_procedure_name"] == "" for row in labs)
    assert all(row["lab_procedure_description"] == "" for row in labs)
    assert all(row["result_loinc_code"] == "" for row in labs)
    assert all(row["result_value"] == "" for row in labs)
    assert all(row["result_flag"] == CELIAC_LAB_RESULT_FLAG for row in labs)

    problem = resources["problem_list"][0]  # type: ignore[index]
    assert tuple(problem) == _shape().field_names("problem_list")
    assert problem["patient_id"] == PATIENT_ID
    assert problem["noted_date_age_in_days"] == diagnosis.age_days
    assert problem["resolved_date_age_in_days"] == ""
    assert problem["pl_diag"] == CELIAC_DIAGNOSIS_CODE
    assert "visit_id" not in problem

    medication = resources["medications"][0]  # type: ignore[index]
    assert tuple(medication) == _shape().field_names("medications")
    assert medication["patient_id"] == PATIENT_ID
    assert medication["visit_id"] == diagnosis_visit.visit_id
    assert medication["med_order_date_age_in_days"] == diagnosis.age_days
    assert medication["med_start_date_age_in_days"] == 1800
    assert medication["med_end_date_age_in_days"] == ""
    assert medication["med_record_type"] == CELIAC_MEDICATION_RECORD_TYPE
    assert medication["med_simple_generic_name"] == CELIAC_MEDICATION_NAME


def test_projection_handles_visible_event_combinations_and_optional_treatment() -> None:
    diagnosed = _resources(_member(treatment=False))
    assert len(diagnosed["referrals"]) == 1  # type: ignore[index]
    assert len(diagnosed["labs"]) == 2  # type: ignore[index]
    assert len(diagnosed["problem_list"]) == 1  # type: ignore[index]
    assert diagnosed["medications"] == []  # type: ignore[index]

    workup_only = _resources(_member(diagnosed=False))
    assert len(workup_only["referrals"]) == 1  # type: ignore[index]
    assert len(workup_only["labs"]) == 2  # type: ignore[index]
    assert workup_only["problem_list"] == []  # type: ignore[index]
    assert workup_only["medications"] == []  # type: ignore[index]

    recognition_only = _resources(_member(workup=False, diagnosed=False))
    assert len(recognition_only["referrals"]) == 1  # type: ignore[index]
    assert recognition_only["labs"] == []  # type: ignore[index]
    assert recognition_only["problem_list"] == []  # type: ignore[index]
    assert recognition_only["medications"] == []  # type: ignore[index]

    unrecognized = _resources(_member(recognized=False, diagnosed=False))
    assert all(not unrecognized[name] for name in CELIAC_ANCILLARY_RESOURCE_NAMES)


def test_hidden_treatment_without_visible_diagnosis_never_emits_medication() -> None:
    resources = _resources(_member(recognized=False, diagnosed=False))
    assert resources["medications"] == []  # type: ignore[index]


def test_treatment_before_censored_observed_diagnosis_is_suppressed() -> None:
    resources = _resources(_member(window_start_age_days=1600))

    assert len(resources["referrals"]) == 1  # type: ignore[index]
    assert len(resources["labs"]) == 2  # type: ignore[index]
    assert len(resources["problem_list"]) == 1  # type: ignore[index]
    assert resources["problem_list"][0]["noted_date_age_in_days"] == 2000  # type: ignore[index]
    assert resources["medications"] == []  # type: ignore[index]


def test_projection_is_empty_for_healthy_and_all_other_disorder_kinds() -> None:
    healthy_trajectory = _trajectory()
    healthy_frame = generate_observation_frame(
        healthy_trajectory,
        _policy(),
        NamedRandomStreams(6, 0),
    )
    healthy = CohortMember(
        SyntheticDemographics(PATIENT_ID), healthy_trajectory, healthy_frame, None
    )
    non_target_kinds = (
        DisorderKind.GROWTH_HORMONE_DEFICIENCY,
        DisorderKind.PEDIATRIC_HYPOTHYROIDISM,
        DisorderKind.SMALL_FOR_GESTATIONAL_AGE,
        DisorderKind.TURNER_SYNDROME,
        DisorderKind.UNDERNUTRITION,
        DisorderKind.EXCESS_WEIGHT,
        DisorderKind.FAMILIAL_SHORT_STATURE,
        DisorderKind.CONSTITUTIONAL_DELAY,
    )

    members = [healthy, *(_member(kind=kind) for kind in non_target_kinds)]
    for member in members:
        projection = project_celiac_ancillary_resources(
            member, _shape(), _policy_ancillary()
        )
        assert tuple(projection.rows) == CELIAC_ANCILLARY_RESOURCE_NAMES
        assert all(not projection.rows[name] for name in CELIAC_ANCILLARY_RESOURCE_NAMES)


def test_projection_preserves_same_age_source_point_links_and_delays_results() -> None:
    member = _member(same_age_events=True)
    resources = _resources(member, result_delay_days=9)
    ages = {event.event_kind: event.age_days for event in member.frame.events}

    assert len(set(ages.values())) == 1
    assert len(resources["referrals"]) == 1  # type: ignore[index]
    assert len(resources["labs"]) == 2  # type: ignore[index]
    assert resources["referrals"][0]["referral_date_age_in_days"] == 730  # type: ignore[index]
    assert all(  # type: ignore[index]
        row["lab_order_date_age_in_days"] == 730
        and row["lab_result_date_age_in_days"] == 739
        for row in resources["labs"]
    )


def test_projection_replays_deterministically_without_mutating_member() -> None:
    member = _member()
    before = member.frame.to_mapping()
    first = project_celiac_ancillary_resources(
        member, _shape(), _policy_ancillary()
    )
    second = project_celiac_ancillary_resources(
        member, _shape(), _policy_ancillary()
    )

    first_resources = first.to_mapping()["resources"]
    second_resources = second.to_mapping()["resources"]
    assert first_resources == second_resources
    assert first_resources["labs"][0]["lab_order_id"] == first_resources["labs"][1]["lab_order_id"]  # type: ignore[index]
    role_ids = {
        first_resources["referrals"][0]["referral_id"],  # type: ignore[index]
        first_resources["labs"][0]["lab_order_id"],  # type: ignore[index]
        first_resources["problem_list"][0]["problem_list_id"],  # type: ignore[index]
        first_resources["medications"][0]["med_record_id"],  # type: ignore[index]
    }
    assert len(role_ids) == 4
    assert all(
        isinstance(identifier, str) and identifier.startswith("syn-")
        for identifier in role_ids
    )
    assert {
        "referral": first_resources["referrals"][0]["referral_id"],  # type: ignore[index]
        "lab-order": first_resources["labs"][0]["lab_order_id"],  # type: ignore[index]
        "problem-list": first_resources["problem_list"][0]["problem_list_id"],  # type: ignore[index]
        "medication": first_resources["medications"][0]["med_record_id"],  # type: ignore[index]
    } == {
        role: _expected_ancillary_id(role)
        for role in ("referral", "lab-order", "problem-list", "medication")
    }
    assert member.frame.to_mapping() == before
    assert "truth" not in repr(first).lower()
    assert "trajectory" not in repr(first).lower()
    assert "obesity_flag" not in json.dumps(first.to_mapping(), sort_keys=True)


def test_projection_uses_fixed_redacted_errors_for_wrong_types_and_tampered_truth() -> None:
    with pytest.raises(
        CeliacAncillaryProjectionUnavailable,
        match="unavailable",
    ) as error:
        project_celiac_ancillary_resources(  # type: ignore[arg-type]
            object(), _shape(), _policy_ancillary()
        )
    message = str(error.value).lower()
    assert PATIENT_ID not in message
    assert "truth" not in message

    member = _member()
    object.__setattr__(member.frame.truth, "latent_trajectory", None)
    with pytest.raises(
        CeliacAncillaryProjectionUnavailable,
        match="failed",
    ) as error:
        project_celiac_ancillary_resources(
            member, _shape(), _policy_ancillary()
        )
    message = str(error.value).lower()
    assert PATIENT_ID not in message
    assert "truth" not in message
