from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from synthetic.cohort import CohortMember
from synthetic.models import DisorderKind, LatentDisorderState
from synthetic.native.ancillary import (
    GHD_ANCILLARY_RESOURCE_NAMES,
    GHD_DIAGNOSIS_CODE,
    GHD_IGF1_COMPONENT,
    GHD_LAB_RESULT_FLAG,
    GHD_MEDICATION_NAME,
    GHD_MEDICATION_RECORD_TYPE,
    GHD_REFERRAL_SPECIALTY,
    AncillaryProjectionUnavailable,
    GhdAncillaryPolicy,
    project_ghd_ancillary_resources,
)
from synthetic.native.observations import (
    ObservationValidationStatus,
    RecordedEventKind,
    generate_observation_frame,
    validate_observation_frame,
)
from synthetic.native.resources import ResourceShape, SyntheticDemographics
from synthetic.randomness import NamedRandomStreams
from tests.synthetic.test_observation_generation import _event_trajectory, _policy, _trajectory

ROOT = Path(__file__).resolve().parents[2]
PATIENT_ID = "syn-observation-patient"


def _descriptor() -> dict[str, object]:
    return json.loads((ROOT / "datapackage.json").read_text(encoding="utf-8"))


def _shape() -> ResourceShape:
    return ResourceShape.from_descriptor(_descriptor())


def _policy_ancillary(**changes: object) -> GhdAncillaryPolicy:
    values: dict[str, object] = {
        "policy_id": "ghd-ancillary-policy-v1",
        "policy_version": "1",
        "result_delay_days": 7,
    }
    values.update(changes)
    return GhdAncillaryPolicy(**values)  # type: ignore[arg-type]


def _member(*, treatment: bool = True, recognized: bool = True) -> CohortMember:
    source = _event_trajectory()
    events = source.events
    if not treatment:
        events = tuple(
            event
            for event in events
            if event.event_type not in {"treatment_start", "treatment_response"}
        )
    trajectory = dataclasses.replace(
        source,
        disorder=LatentDisorderState(
            DisorderKind.GROWTH_HORMONE_DEFICIENCY,
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
            recognition_probability=1.0 if recognized else 0.0,
            diagnosis_probability=1.0,
        ),
        # The projection must consume an already-realized frame; its random
        # streams are intentionally not part of the projection API.
        NamedRandomStreams(6, 0),
    )
    assert validate_observation_frame(frame).status is ObservationValidationStatus.PASS
    return CohortMember(SyntheticDemographics(PATIENT_ID), trajectory, frame, None)


def _values(row: object) -> dict[str, object]:
    return row.to_mapping()  # type: ignore[union-attr]


def test_diagnosed_ghd_projects_all_visible_rows_in_descriptor_order() -> None:
    member = _member(treatment=True)
    shape = _shape()
    policy = _policy_ancillary(result_delay_days=7)

    projection = project_ghd_ancillary_resources(member, shape, policy)
    resources = projection.to_mapping()["resources"]

    assert tuple(resources) == GHD_ANCILLARY_RESOURCE_NAMES  # type: ignore[arg-type]
    assert len(resources["referrals"]) == 1  # type: ignore[index]
    assert len(resources["labs"]) == 2  # type: ignore[index]
    assert len(resources["problem_list"]) == 1  # type: ignore[index]
    assert len(resources["medications"]) == 1  # type: ignore[index]

    visible_by_kind = {
        event.event_kind: event for event in member.frame.events
    }
    recognition = visible_by_kind[RecordedEventKind.RECOGNITION]
    workup = visible_by_kind[RecordedEventKind.WORKUP]
    diagnosis = visible_by_kind[RecordedEventKind.DIAGNOSIS]
    visible_visit_by_source = {
        opportunity.source_point_index: visit
        for opportunity, visit in zip(
            (item for item in member.frame.truth.opportunities if item.realized),
            member.frame.visits,
            strict=True,
        )
    }
    recognition_visit = visible_visit_by_source[recognition.opportunity_index]
    workup_visit = visible_visit_by_source[workup.opportunity_index]
    diagnosis_visit = visible_visit_by_source[diagnosis.opportunity_index]

    referral = resources["referrals"][0]  # type: ignore[index]
    assert tuple(referral) == shape.field_names("referrals")
    assert referral["patient_id"] == PATIENT_ID
    assert referral["visit_id"] == recognition_visit.visit_id
    assert referral["referral_date_age_in_days"] == recognition.age_days
    assert referral["requested_specialty"] == GHD_REFERRAL_SPECIALTY
    assert referral["referral_number_of_visits"] == 1
    referral_id = referral["referral_id"]
    assert isinstance(referral_id, str)
    assert referral_id.startswith("syn-")
    assert referral_id == project_ghd_ancillary_resources(
        member, shape, policy
    ).to_mapping()["resources"]["referrals"][0]["referral_id"]  # type: ignore[index]
    expected_referral = {
        "patient_id": PATIENT_ID,
        "visit_id": recognition_visit.visit_id,
        "referral_id": referral_id,
        "referral_date_age_in_days": recognition.age_days,
        "requested_specialty": GHD_REFERRAL_SPECIALTY,
        "referral_number_of_visits": 1,
    }
    assert referral == expected_referral

    labs = resources["labs"]  # type: ignore[index]
    assert tuple(labs[0]) == shape.field_names("labs")
    assert labs[0]["patient_id"] == PATIENT_ID
    assert labs[0]["visit_id"] == workup_visit.visit_id
    assert labs[0]["lab_order_id"] == labs[1]["lab_order_id"]
    assert labs[0]["result_line_num"] == 1
    assert labs[1]["result_line_num"] == 2
    assert [row["lab_order_date_age_in_days"] for row in labs] == [workup.age_days] * 2
    assert [row["lab_result_date_age_in_days"] for row in labs] == [workup.age_days + 7] * 2
    assert [row["result_component_name"] for row in labs] == [
        GHD_IGF1_COMPONENT,
        "SYN-GHD-STIM",
    ]
    assert all(row["result_loinc_code"] == "" for row in labs)
    assert all(row["result_value"] == "" for row in labs)
    assert all(row["result_flag"] == GHD_LAB_RESULT_FLAG for row in labs)
    assert all(row["lab_procedure_name"] == "" for row in labs)
    assert all(row["lab_procedure_description"] == "" for row in labs)

    problem = resources["problem_list"][0]  # type: ignore[index]
    assert tuple(problem) == shape.field_names("problem_list")
    assert problem["patient_id"] == PATIENT_ID
    assert problem["noted_date_age_in_days"] == diagnosis.age_days
    assert problem["resolved_date_age_in_days"] == ""
    assert problem["pl_diag"] == GHD_DIAGNOSIS_CODE

    medication = resources["medications"][0]  # type: ignore[index]
    assert tuple(medication) == shape.field_names("medications")
    assert medication["patient_id"] == PATIENT_ID
    assert medication["visit_id"] == diagnosis_visit.visit_id
    assert medication["med_order_date_age_in_days"] == diagnosis.age_days
    assert medication["med_start_date_age_in_days"] == 1800
    assert medication["med_end_date_age_in_days"] == ""
    assert medication["med_record_type"] == GHD_MEDICATION_RECORD_TYPE
    assert medication["med_simple_generic_name"] == GHD_MEDICATION_NAME
    assert medication["med_record_id"].startswith("syn-")


def test_ghd_without_treatment_has_no_medication_and_problem_has_nullable_visit_semantics() -> None:
    projection = project_ghd_ancillary_resources(
        _member(treatment=False), _shape(), _policy_ancillary()
    )
    resources = projection.to_mapping()["resources"]

    assert resources["medications"] == []  # type: ignore[index]
    assert len(resources["problem_list"]) == 1  # type: ignore[index]
    assert "visit_id" not in resources["problem_list"][0]  # type: ignore[index]


def test_healthy_non_ghd_and_unrecognized_ghd_project_four_empty_tuples() -> None:
    healthy = CohortMember(
        SyntheticDemographics(PATIENT_ID),
        _trajectory(),
        generate_observation_frame(
            _trajectory(),
            _policy(),
            NamedRandomStreams(6, 0),
        ),
        None,
    )
    for member in (healthy, _member(recognized=False)):
        projection = project_ghd_ancillary_resources(member, _shape(), _policy_ancillary())
        assert all(not projection.rows[name] for name in GHD_ANCILLARY_RESOURCE_NAMES)


def test_projection_is_deterministic_nonmutating_and_uses_same_age_workup_diagnosis() -> None:
    member = _member(treatment=True)
    before = member.to_mapping()
    first = project_ghd_ancillary_resources(member, _shape(), _policy_ancillary())
    replay = project_ghd_ancillary_resources(member, _shape(), _policy_ancillary())

    assert first.to_mapping() == replay.to_mapping()
    assert member.to_mapping() == before
    assert first.to_mapping()["resources"]["labs"][0]["lab_order_id"].startswith("syn-")  # type: ignore[index]
    assert first.to_mapping()["resources"]["problem_list"][0]["pl_diag"] == GHD_DIAGNOSIS_CODE  # type: ignore[index]


def test_projection_redacts_malformed_observation_evidence() -> None:
    member = _member()
    malformed_frame = dataclasses.replace(
        member.frame,
        truth=dataclasses.replace(member.frame.truth, policy=None),
    )
    malformed_member = dataclasses.replace(member, frame=malformed_frame)

    with pytest.raises(AncillaryProjectionUnavailable, match="^GHD ancillary projection failed$") as exc_info:
        project_ghd_ancillary_resources(malformed_member, _shape(), _policy_ancillary())
    assert "syn-" not in str(exc_info.value)
    assert "truth" not in str(exc_info.value).lower()


def test_projection_rejects_trajectory_not_bound_to_frame_truth() -> None:
    member = _member(treatment=True)
    tampered_events = tuple(
        dataclasses.replace(event, age_days=1801)
        if event.event_type == "treatment_start"
        else event
        for event in member.trajectory.events
    )
    tampered_trajectory = dataclasses.replace(member.trajectory, events=tampered_events)
    tampered_member = dataclasses.replace(member, trajectory=tampered_trajectory)

    with pytest.raises(
        AncillaryProjectionUnavailable,
        match="^GHD ancillary projection failed$",
    ) as exc_info:
        project_ghd_ancillary_resources(
            tampered_member,
            _shape(),
            _policy_ancillary(),
        )
    assert "1801" not in str(exc_info.value)
    assert "truth" not in str(exc_info.value).lower()
