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
from synthetic.native.turner_ancillary import (
    TURNER_ANCILLARY_RESOURCE_NAMES,
    TURNER_DIAGNOSIS_CODE,
    TURNER_ENDOCRINE_EVIDENCE_COMPONENT,
    TURNER_KARYOTYPE_COMPONENT,
    TURNER_LAB_RESULT_FLAG,
    TURNER_MEDICATION_NAME,
    TURNER_MEDICATION_RECORD_TYPE,
    TURNER_REFERRAL_SPECIALTY,
    TurnerAncillaryPolicy,
    TurnerAncillaryProjectionUnavailable,
    project_turner_ancillary_resources,
)
from synthetic.randomness import NamedRandomStreams
from tests.synthetic.test_observation_generation import (
    _event_trajectory,
    _policy,
    _trajectory,
)

ROOT = Path(__file__).resolve().parents[2]
PATIENT_ID = "syn-observation-patient"


def _shape() -> ResourceShape:
    return ResourceShape.from_descriptor(
        json.loads((ROOT / "datapackage.json").read_text(encoding="utf-8"))
    )


def _policy_ancillary(**changes: object) -> TurnerAncillaryPolicy:
    values: dict[str, object] = {
        "policy_id": "turner-ancillary-policy-v1",
        "policy_version": "1",
        "result_delay_days": 7,
    }
    values.update(changes)
    return TurnerAncillaryPolicy(**values)  # type: ignore[arg-type]


def _member(
    *,
    recorded_sex: str = "F",
    treatment: bool = True,
    recognized: bool = True,
    diagnosed: bool = True,
    workup: bool = True,
    same_age_events: bool = False,
    window_start_age_days: int = 0,
    kind: DisorderKind = DisorderKind.TURNER_SYNDROME,
) -> CohortMember:
    if kind is DisorderKind.HEALTHY:
        trajectory = _trajectory()
    else:
        source = _event_trajectory()
        events = source.events
        if same_age_events:
            events = tuple(
                dataclasses.replace(event, age_days=700)
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
            recognition_probability=1.0 if recognized else 0.0,
            diagnosis_probability=1.0 if diagnosed else 0.0,
        ),
        NamedRandomStreams(6, 0),
    )
    assert validate_observation_frame(frame).status is ObservationValidationStatus.PASS
    return CohortMember(
        SyntheticDemographics(PATIENT_ID, sex=recorded_sex),
        trajectory,
        frame,
        None,
    )


def _resources(member: CohortMember, **policy_changes: object) -> dict[str, object]:
    return project_turner_ancillary_resources(
        member, _shape(), _policy_ancillary(**policy_changes)
    ).to_mapping()["resources"]  # type: ignore[no-any-return]


def _expected_id(role: str) -> str:
    material = f"turner-ancillary-id-v1\x1f{PATIENT_ID}\x1f{role}".encode()
    return f"syn-{hashlib.sha256(material).hexdigest()}"


def test_target_projects_exact_four_resources_and_source_point_links() -> None:
    member = _member()
    resources = _resources(member)
    visible_by_kind = {event.event_kind: event for event in member.frame.events}
    visible_visit_by_source = {
        opportunity.source_point_index: visit
        for opportunity, visit in zip(
            (item for item in member.frame.truth.opportunities if item.realized),
            member.frame.visits,
            strict=True,
        )
    }

    assert tuple(resources) == TURNER_ANCILLARY_RESOURCE_NAMES
    assert [len(resources[name]) for name in TURNER_ANCILLARY_RESOURCE_NAMES] == [
        2,
        1,
        1,
        1,
    ]  # type: ignore[index]

    recognition = visible_by_kind[RecordedEventKind.RECOGNITION]
    workup = visible_by_kind[RecordedEventKind.WORKUP]
    diagnosis = visible_by_kind[RecordedEventKind.DIAGNOSIS]
    referral = resources["referrals"][0]  # type: ignore[index]
    assert referral["patient_id"] == PATIENT_ID
    assert referral["visit_id"] == visible_visit_by_source[recognition.opportunity_index].visit_id
    assert referral["referral_date_age_in_days"] == recognition.age_days
    assert referral["requested_specialty"] == TURNER_REFERRAL_SPECIALTY
    assert referral["referral_number_of_visits"] == 1

    labs = resources["labs"]  # type: ignore[assignment]
    assert [row["result_line_num"] for row in labs] == [1, 2]
    assert labs[0]["lab_order_id"] == labs[1]["lab_order_id"]
    assert all(
        row["visit_id"] == visible_visit_by_source[workup.opportunity_index].visit_id
        and row["lab_order_date_age_in_days"] == workup.age_days
        and row["lab_result_date_age_in_days"] == workup.age_days + 7
        and row["result_loinc_code"] == ""
        and row["result_value"] == ""
        and row["result_flag"] == TURNER_LAB_RESULT_FLAG
        and row["lab_procedure_name"] == ""
        and row["lab_procedure_description"] == ""
        for row in labs
    )
    assert [row["result_component_name"] for row in labs] == [
        TURNER_KARYOTYPE_COMPONENT,
        TURNER_ENDOCRINE_EVIDENCE_COMPONENT,
    ]

    problem = resources["problem_list"][0]  # type: ignore[index]
    assert problem["patient_id"] == PATIENT_ID
    assert problem["noted_date_age_in_days"] == diagnosis.age_days
    assert problem["resolved_date_age_in_days"] == ""
    assert problem["pl_diag"] == TURNER_DIAGNOSIS_CODE
    assert "visit_id" not in problem

    medication = resources["medications"][0]  # type: ignore[index]
    assert medication["patient_id"] == PATIENT_ID
    assert medication["visit_id"] == visible_visit_by_source[diagnosis.opportunity_index].visit_id
    assert medication["med_order_date_age_in_days"] == diagnosis.age_days
    assert medication["med_start_date_age_in_days"] == 1800
    assert medication["med_end_date_age_in_days"] == ""
    assert medication["med_record_type"] == TURNER_MEDICATION_RECORD_TYPE
    assert medication["med_simple_generic_name"] == TURNER_MEDICATION_NAME


def test_each_visible_event_controls_only_its_descendant_and_treatment_is_gated() -> None:
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
    assert all(not unrecognized[name] for name in TURNER_ANCILLARY_RESOURCE_NAMES)


def test_hidden_treatment_without_diagnosis_and_early_treatment_are_suppressed() -> None:
    hidden_treatment = _resources(_member(recognized=False, diagnosed=False))
    assert hidden_treatment["medications"] == []  # type: ignore[index]

    censored_diagnosis = _resources(_member(window_start_age_days=1600))
    assert len(censored_diagnosis["problem_list"]) == 1  # type: ignore[index]
    assert censored_diagnosis["problem_list"][0]["noted_date_age_in_days"] == 2000  # type: ignore[index]
    assert censored_diagnosis["medications"] == []  # type: ignore[index]


def test_same_age_events_are_source_point_linked_and_projection_replays() -> None:
    member = _member(same_age_events=True)
    before = member.frame.to_mapping()
    first = _resources(member, result_delay_days=9)
    second = _resources(member, result_delay_days=9)

    assert first == second
    assert first["referrals"][0]["referral_date_age_in_days"] == 730  # type: ignore[index]
    assert all(  # type: ignore[index]
        row["lab_order_date_age_in_days"] == 730
        and row["lab_result_date_age_in_days"] == 739
        for row in first["labs"]
    )
    assert first["referrals"][0]["referral_id"] == _expected_id("referral")  # type: ignore[index]
    assert first["labs"][0]["lab_order_id"] == _expected_id("lab-order")  # type: ignore[index]
    assert first["problem_list"][0]["problem_list_id"] == _expected_id("problem-list")  # type: ignore[index]
    assert first["medications"][0]["med_record_id"] == _expected_id("medication")  # type: ignore[index]
    assert member.frame.to_mapping() == before

    row_ids = {
        first["referrals"][0]["referral_id"],  # type: ignore[index]
        first["labs"][0]["lab_order_id"],  # type: ignore[index]
        first["problem_list"][0]["problem_list_id"],  # type: ignore[index]
        first["medications"][0]["med_record_id"],  # type: ignore[index]
    }
    assert all(PATIENT_ID not in row_id for row_id in row_ids)
    assert all(
        visit.visit_id not in row_id
        for visit in member.frame.visits
        for row_id in row_ids
    )
    serialized = json.dumps(first, sort_keys=True)
    assert "obesity_flag" not in serialized
    assert "latent_onset" not in serialized
    assert "treatment_response" not in serialized


@pytest.mark.parametrize("recorded_sex", ["F", "U"])
def test_recorded_sex_does_not_replace_upstream_reference_sex(recorded_sex: str) -> None:
    resources = _resources(_member(recorded_sex=recorded_sex))
    assert len(resources["problem_list"]) == 1  # type: ignore[index]
    assert resources["problem_list"][0]["pl_diag"] == TURNER_DIAGNOSIS_CODE  # type: ignore[index]


@pytest.mark.parametrize(
    "kind",
    [
        DisorderKind.HEALTHY,
        DisorderKind.GROWTH_HORMONE_DEFICIENCY,
        DisorderKind.PEDIATRIC_HYPOTHYROIDISM,
        DisorderKind.CELIAC_DISEASE,
        DisorderKind.SMALL_FOR_GESTATIONAL_AGE,
        DisorderKind.UNDERNUTRITION,
        DisorderKind.EXCESS_WEIGHT,
        DisorderKind.FAMILIAL_SHORT_STATURE,
        DisorderKind.CONSTITUTIONAL_DELAY,
    ],
)
def test_healthy_and_every_non_target_member_are_four_empty_tuples(
    kind: DisorderKind,
) -> None:
    projection = project_turner_ancillary_resources(
        _member(kind=kind), _shape(), _policy_ancillary()
    )
    assert tuple(projection.rows) == TURNER_ANCILLARY_RESOURCE_NAMES
    assert all(projection.rows[name] == () for name in TURNER_ANCILLARY_RESOURCE_NAMES)


def test_projection_uses_fixed_redacted_errors_for_wrong_types_and_tampered_truth() -> None:
    with pytest.raises(TurnerAncillaryProjectionUnavailable, match="unavailable") as error:
        project_turner_ancillary_resources(  # type: ignore[arg-type]
            object(), _shape(), _policy_ancillary()
        )
    message = str(error.value).lower()
    assert PATIENT_ID not in message
    assert "truth" not in message
    assert "trajectory" not in message

    member = _member()
    object.__setattr__(member.frame.truth, "latent_trajectory", None)
    with pytest.raises(TurnerAncillaryProjectionUnavailable, match="failed") as error:
        project_turner_ancillary_resources(member, _shape(), _policy_ancillary())
    message = str(error.value).lower()
    assert PATIENT_ID not in message
    assert "truth" not in message
