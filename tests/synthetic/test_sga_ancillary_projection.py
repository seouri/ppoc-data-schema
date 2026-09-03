from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from synthetic.cohort import CohortMember
from synthetic.models import DisorderKind, LatentDisorderState
from synthetic.native.observations import (
    ObservationValidationStatus,
    RecordedEventKind,
    generate_observation_frame,
    validate_observation_frame,
)
from synthetic.native.resources import ResourceShape, SyntheticDemographics
from synthetic.native.sga_ancillary import (
    SGA_ANCILLARY_RESOURCE_NAMES,
    SGA_DIAGNOSIS_CODE,
    SGA_LAB_COMPONENT_NAMES,
    SGA_REFERRAL_SPECIALTY,
    SgaAncillaryPolicy,
    SgaAncillaryProjectionUnavailable,
    project_sga_ancillary_resources,
)
from synthetic.randomness import NamedRandomStreams
from tests.synthetic.test_observation_generation import _event_trajectory, _policy

ROOT = Path(__file__).resolve().parents[2]
PATIENT_ID = "syn-observation-patient"


def _shape() -> ResourceShape:
    return ResourceShape.from_descriptor(json.loads((ROOT / "datapackage.json").read_text()))


def _policy_ancillary(**changes: object) -> SgaAncillaryPolicy:
    values: dict[str, object] = {
        "policy_id": "sga-ancillary-policy-v1",
        "policy_version": "1",
        "result_delay_days": 7,
    }
    values.update(changes)
    return SgaAncillaryPolicy(**values)  # type: ignore[arg-type]


def _member(
    *,
    recognized: bool = True,
    diagnosed: bool = True,
    workup: bool = True,
    severity: float = 0.7,
    same_age: bool = False,
    kind: DisorderKind = DisorderKind.SMALL_FOR_GESTATIONAL_AGE,
) -> CohortMember:
    source = _event_trajectory()
    if kind is not DisorderKind.SMALL_FOR_GESTATIONAL_AGE:
        frame = generate_observation_frame(
            source,
            _policy(),
            NamedRandomStreams(6, 0),
        )
        return CohortMember(SyntheticDemographics(PATIENT_ID), source, frame, None)
    events = source.events
    onset_age = source.disorder.onset_age_days
    if kind is DisorderKind.SMALL_FOR_GESTATIONAL_AGE:
        onset_age = 0
        events = tuple(
            dataclasses.replace(event, age_days=0) if event.event_type == "latent_onset" else event
            for event in events
            if event.event_type not in {"treatment_start", "treatment_response"}
        )
    if not workup:
        events = tuple(event for event in events if event.event_type != "workup")
    if same_age:
        events = tuple(
            dataclasses.replace(event, age_days=700)
            if event.event_type in {"recognition_opportunity", "workup", "recorded_diagnosis"}
            else event
            for event in events
        )
    trajectory = dataclasses.replace(
        source, disorder=LatentDisorderState(kind, onset_age, severity), events=events
    )
    frame = generate_observation_frame(
        trajectory,
        _policy(
            recognition_probability=1.0 if recognized else 0.0,
            diagnosis_probability=1.0 if diagnosed else 0.0,
        ),
        NamedRandomStreams(6, 0),
    )
    assert validate_observation_frame(frame).status is ObservationValidationStatus.PASS
    return CohortMember(SyntheticDemographics(PATIENT_ID), trajectory, frame, None)


def _resources(member: CohortMember, **changes: object) -> dict[str, object]:
    return project_sga_ancillary_resources(
        member, _shape(), _policy_ancillary(**changes)
    ).to_mapping()["resources"]  # type: ignore[no-any-return]


def test_target_projects_only_visible_fictional_referral_labs_and_problem() -> None:
    member = _member()
    resources = _resources(member)
    events = {event.event_kind: event for event in member.frame.events}
    visits = {
        opportunity.source_point_index: visit
        for opportunity, visit in zip(
            (item for item in member.frame.truth.opportunities if item.realized),
            member.frame.visits,
            strict=True,
        )
    }

    assert tuple(resources) == SGA_ANCILLARY_RESOURCE_NAMES
    assert [len(resources[name]) for name in SGA_ANCILLARY_RESOURCE_NAMES] == [2, 0, 1, 1]  # type: ignore[index]
    referral = resources["referrals"][0]  # type: ignore[index]
    assert referral["requested_specialty"] == SGA_REFERRAL_SPECIALTY
    assert (
        referral["visit_id"]
        == visits[events[RecordedEventKind.RECOGNITION].opportunity_index].visit_id
    )
    labs = resources["labs"]  # type: ignore[assignment]
    assert [row["result_component_name"] for row in labs] == list(SGA_LAB_COMPONENT_NAMES)
    assert all(
        row["result_loinc_code"] == row["result_value"] == "" and row["result_flag"] == "Synthetic"
        for row in labs
    )
    assert all(
        row["visit_id"] == visits[events[RecordedEventKind.WORKUP].opportunity_index].visit_id
        for row in labs
    )
    assert all(
        row["lab_result_date_age_in_days"] == events[RecordedEventKind.WORKUP].age_days + 7
        for row in labs
    )
    problem = resources["problem_list"][0]  # type: ignore[index]
    assert problem["pl_diag"] == SGA_DIAGNOSIS_CODE
    assert problem["resolved_date_age_in_days"] == ""
    assert "visit_id" not in problem


def test_emitted_rows_keep_actual_descriptor_order_and_scalar_conventions() -> None:
    member = _member()
    shape = _shape()
    projection = project_sga_ancillary_resources(member, shape, _policy_ancillary())
    integer_fields = frozenset(
        {
            "result_line_num",
            "lab_order_date_age_in_days",
            "lab_result_date_age_in_days",
            "noted_date_age_in_days",
            "referral_date_age_in_days",
            "referral_number_of_visits",
        }
    )

    assert projection.rows["medications"] == ()
    for resource_name in ("labs", "problem_list", "referrals"):
        for row in projection.rows[resource_name]:
            assert tuple(field_name for field_name, _ in row.values) == shape.field_names(
                resource_name
            )
            for field_name, value in row.values:
                assert isinstance(value, int) if field_name in integer_fields else isinstance(value, str)

    labs = projection.rows["labs"]
    assert all(dict(row.values)["lab_procedure_name"] == "" for row in labs)
    assert all(dict(row.values)["lab_procedure_description"] == "" for row in labs)
    assert all(dict(row.values)["result_loinc_code"] == "" for row in labs)
    assert all(dict(row.values)["result_value"] == "" for row in labs)
    assert dict(projection.rows["problem_list"][0].values)["resolved_date_age_in_days"] == ""


def test_each_visible_event_and_hidden_birth_branch_controls_only_its_descendant() -> None:
    for member, expected in (
        (_member(diagnosed=False), (2, 0, 0, 1)),
        (_member(workup=False, diagnosed=False), (0, 0, 0, 1)),
        (_member(recognized=False, diagnosed=False), (0, 0, 0, 0)),
        (_member(severity=0.7), (2, 0, 1, 1)),
        (_member(severity=1.2), (2, 0, 1, 1)),
    ):
        resources = _resources(member)
        assert tuple(len(resources[name]) for name in SGA_ANCILLARY_RESOURCE_NAMES) == expected  # type: ignore[index]


def test_same_age_is_deterministic_namespaced_and_nonmutating() -> None:
    member = _member(same_age=True)
    before = member.frame.to_mapping()
    first = _resources(member, result_delay_days=9)
    second = _resources(member, result_delay_days=9)
    expected = lambda role: (
        f"syn-{hashlib.sha256(f'sga-ancillary-id-v1{chr(31)}{PATIENT_ID}{chr(31)}{role}'.encode()).hexdigest()}"
    )

    assert first == second
    assert first["referrals"][0]["referral_id"] == expected("referral")  # type: ignore[index]
    assert first["labs"][0]["lab_order_id"] == expected("lab-order")  # type: ignore[index]
    assert first["problem_list"][0]["problem_list_id"] == expected("problem-list")  # type: ignore[index]
    assert all(
        row["lab_order_date_age_in_days"] == 730 and row["lab_result_date_age_in_days"] == 739
        for row in first["labs"]
    )  # type: ignore[index]
    assert member.frame.to_mapping() == before


def test_non_target_and_unsafe_inputs_do_not_project_or_disclose_state() -> None:
    projection = project_sga_ancillary_resources(
        _member(kind=DisorderKind.CELIAC_DISEASE), _shape(), _policy_ancillary()
    )
    assert all(not projection.rows[name] for name in SGA_ANCILLARY_RESOURCE_NAMES)
    with pytest.raises(SgaAncillaryProjectionUnavailable, match="unavailable") as error:
        project_sga_ancillary_resources(object(), _shape(), _policy_ancillary())  # type: ignore[arg-type]
    assert PATIENT_ID not in str(error.value)
