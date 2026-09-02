from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from synthetic.cohort import CohortMember
from synthetic.models import DisorderKind, LatentDisorderState
from synthetic.native.excess_weight_ancillary import (
    EXCESS_WEIGHT_A1C_COMPONENT,
    EXCESS_WEIGHT_ANCILLARY_RESOURCE_NAMES,
    EXCESS_WEIGHT_DIAGNOSIS_CODE,
    EXCESS_WEIGHT_LAB_RESULT_FLAG,
    EXCESS_WEIGHT_LIPID_COMPONENT,
    EXCESS_WEIGHT_REFERRAL_SPECIALTY,
    ExcessWeightAncillaryPolicy,
    ExcessWeightAncillaryProjectionUnavailable,
    project_excess_weight_ancillary_resources,
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


def _policy_ancillary(**changes: object) -> ExcessWeightAncillaryPolicy:
    values: dict[str, object] = {
        "policy_id": "excess-weight-ancillary-policy-v1",
        "policy_version": "1",
        "result_delay_days": 7,
    }
    values.update(changes)
    return ExcessWeightAncillaryPolicy(**values)  # type: ignore[arg-type]


def _member(
    *,
    treatment: bool = True,
    recognized: bool = True,
    diagnosed: bool = True,
    kind: DisorderKind = DisorderKind.EXCESS_WEIGHT,
    same_age_events: bool = False,
    visit_probability: float = 1.0,
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
            visit_probability=visit_probability,
            recognition_probability=1.0 if recognized else 0.0,
            diagnosis_probability=1.0 if diagnosed else 0.0,
        ),
        NamedRandomStreams(6, 0),
    )
    assert validate_observation_frame(frame).status is ObservationValidationStatus.PASS
    return CohortMember(SyntheticDemographics(PATIENT_ID), trajectory, frame, None)


def test_diagnosed_excess_weight_projects_exact_four_resource_contract() -> None:
    member = _member()
    shape = _shape()
    projection = project_excess_weight_ancillary_resources(
        member,
        shape,
        _policy_ancillary(),
    )
    resources = projection.to_mapping()["resources"]

    assert tuple(resources) == EXCESS_WEIGHT_ANCILLARY_RESOURCE_NAMES  # type: ignore[arg-type]
    assert len(resources["referrals"]) == 1  # type: ignore[index]
    assert len(resources["labs"]) == 2  # type: ignore[index]
    assert len(resources["problem_list"]) == 1  # type: ignore[index]
    assert resources["medications"] == []  # type: ignore[index]

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

    referral = resources["referrals"][0]  # type: ignore[index]
    assert tuple(referral) == shape.field_names("referrals")
    assert referral["patient_id"] == PATIENT_ID
    assert referral["visit_id"] == recognition_visit.visit_id
    assert referral["referral_date_age_in_days"] == recognition.age_days
    assert referral["requested_specialty"] == EXCESS_WEIGHT_REFERRAL_SPECIALTY
    assert referral["referral_number_of_visits"] == 1

    labs = resources["labs"]  # type: ignore[index]
    assert all(tuple(row) == shape.field_names("labs") for row in labs)
    assert all(row["visit_id"] == workup_visit.visit_id for row in labs)
    assert labs[0]["lab_order_id"] == labs[1]["lab_order_id"]
    assert [row["result_line_num"] for row in labs] == [1, 2]
    assert [row["lab_order_date_age_in_days"] for row in labs] == [workup.age_days] * 2
    assert [row["lab_result_date_age_in_days"] for row in labs] == [workup.age_days + 7] * 2
    assert [row["result_component_name"] for row in labs] == [
        EXCESS_WEIGHT_LIPID_COMPONENT,
        EXCESS_WEIGHT_A1C_COMPONENT,
    ]
    assert all(row["result_loinc_code"] == "" for row in labs)
    assert all(row["result_value"] == "" for row in labs)
    assert all(row["result_flag"] == EXCESS_WEIGHT_LAB_RESULT_FLAG for row in labs)

    problem = resources["problem_list"][0]  # type: ignore[index]
    assert tuple(problem) == shape.field_names("problem_list")
    assert problem["patient_id"] == PATIENT_ID
    assert problem["noted_date_age_in_days"] == diagnosis.age_days
    assert problem["resolved_date_age_in_days"] == ""
    assert problem["pl_diag"] == EXCESS_WEIGHT_DIAGNOSIS_CODE
    assert "visit_id" not in problem


def test_projection_handles_visible_event_combinations_and_hidden_treatment() -> None:
    diagnosed = project_excess_weight_ancillary_resources(
        _member(treatment=False), _shape(), _policy_ancillary()
    ).to_mapping()["resources"]
    assert len(diagnosed["referrals"]) == 1  # type: ignore[index]
    assert len(diagnosed["labs"]) == 2  # type: ignore[index]
    assert len(diagnosed["problem_list"]) == 1  # type: ignore[index]
    assert diagnosed["medications"] == []  # type: ignore[index]

    workup_only = project_excess_weight_ancillary_resources(
        _member(diagnosed=False), _shape(), _policy_ancillary()
    ).to_mapping()["resources"]
    assert len(workup_only["referrals"]) == 1  # type: ignore[index]
    assert len(workup_only["labs"]) == 2  # type: ignore[index]
    assert workup_only["problem_list"] == []  # type: ignore[index]
    assert workup_only["medications"] == []  # type: ignore[index]

    unrecognized = project_excess_weight_ancillary_resources(
        _member(recognized=False), _shape(), _policy_ancillary()
    ).to_mapping()["resources"]
    assert all(not unrecognized[name] for name in EXCESS_WEIGHT_ANCILLARY_RESOURCE_NAMES)


def test_projection_is_empty_for_healthy_and_non_target_members() -> None:
    healthy_trajectory = _trajectory()
    healthy_frame = generate_observation_frame(
        healthy_trajectory,
        _policy(),
        NamedRandomStreams(6, 0),
    )
    healthy = CohortMember(
        SyntheticDemographics(PATIENT_ID), healthy_trajectory, healthy_frame, None
    )
    non_target = _member(kind=DisorderKind.FAMILIAL_SHORT_STATURE)

    for member in (healthy, non_target):
        projection = project_excess_weight_ancillary_resources(
            member, _shape(), _policy_ancillary()
        )
        assert tuple(projection.rows) == EXCESS_WEIGHT_ANCILLARY_RESOURCE_NAMES
        assert all(not projection.rows[name] for name in EXCESS_WEIGHT_ANCILLARY_RESOURCE_NAMES)


def test_projection_preserves_same_age_source_point_links_and_delays_results() -> None:
    member = _member(same_age_events=True)
    resources = project_excess_weight_ancillary_resources(
        member, _shape(), _policy_ancillary(result_delay_days=9)
    ).to_mapping()["resources"]
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
    first = project_excess_weight_ancillary_resources(
        member, _shape(), _policy_ancillary()
    )
    second = project_excess_weight_ancillary_resources(
        member, _shape(), _policy_ancillary()
    )

    assert first.to_mapping() == second.to_mapping()
    assert member.frame.to_mapping() == before
    assert "truth" not in repr(first).lower()
    assert "trajectory" not in repr(first).lower()


def test_projection_uses_fixed_redacted_errors_for_wrong_types_and_tampered_truth() -> None:
    with pytest.raises(ExcessWeightAncillaryProjectionUnavailable, match="unavailable") as error:
        project_excess_weight_ancillary_resources(object(), _shape(), _policy_ancillary())  # type: ignore[arg-type]
    message = str(error.value).lower()
    assert PATIENT_ID not in message
    assert "truth" not in message

    member = _member()
    object.__setattr__(member.frame.truth, "latent_trajectory", None)
    with pytest.raises(ExcessWeightAncillaryProjectionUnavailable, match="failed") as error:
        project_excess_weight_ancillary_resources(member, _shape(), _policy_ancillary())
    message = str(error.value).lower()
    assert PATIENT_ID not in message
    assert "truth" not in message
