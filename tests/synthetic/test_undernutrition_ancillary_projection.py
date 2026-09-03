from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from synthetic.cohort import CohortMember
from synthetic.models import (
    AgeRegimeDisorderTrajectory,
    DisorderKind,
    PatientState,
)
from synthetic.native.age_regimes import AgeRegimeConfig, AgeRegimeTrajectoryKernel
from synthetic.native.clinical_modules import (
    UndernutritionConfig,
    UndernutritionModule,
)
from synthetic.native.observations import (
    CensoringMode,
    ObservationValidationStatus,
    RecordedEventKind,
    generate_observation_frame,
    validate_observation_frame,
)
from synthetic.native.resources import ResourceShape, SyntheticDemographics
from synthetic.native.undernutrition_ancillary import (
    UNDERNUTRITION_ANCILLARY_RESOURCE_NAMES,
    UNDERNUTRITION_DIAGNOSIS_CODE,
    UNDERNUTRITION_HEIGHT_COMPONENT,
    UNDERNUTRITION_LAB_RESULT_FLAG,
    UNDERNUTRITION_MEDICATION_NAME,
    UNDERNUTRITION_MEDICATION_RECORD_TYPE,
    UNDERNUTRITION_REFERRAL_SPECIALTY,
    UNDERNUTRITION_WEIGHT_COMPONENT,
    UndernutritionAncillaryPolicy,
    UndernutritionAncillaryProjectionUnavailable,
    project_undernutrition_ancillary_resources,
)
from synthetic.randomness import NamedRandomStreams
from tests.synthetic.fakes import RegimeLinearTestReference
from tests.synthetic.test_observation_generation import _policy, _trajectory

ROOT = Path(__file__).resolve().parents[2]
PATIENT_ID = "syn-observation-patient"
PATIENT = PatientState(PATIENT_ID, "F", "F")
DEFAULT_PHYSIOLOGY_AGES = (100, 500, 590, 710, 730, 740, 770, 800, 1165, 1500, 2000)


def _shape() -> ResourceShape:
    descriptor = json.loads((ROOT / "datapackage.json").read_text(encoding="utf-8"))
    return ResourceShape.from_descriptor(descriptor)


def _ancillary_policy(**changes: object) -> UndernutritionAncillaryPolicy:
    values: dict[str, object] = {
        "policy_id": "undernutrition-ancillary-policy-v1",
        "policy_version": "1",
        "result_delay_days": 7,
    }
    values.update(changes)
    return UndernutritionAncillaryPolicy(**values)  # type: ignore[arg-type]


def _physiology(ages: tuple[int, ...] = DEFAULT_PHYSIOLOGY_AGES):
    kernel = AgeRegimeTrajectoryKernel(
        RegimeLinearTestReference(),
        AgeRegimeConfig(residual_sd=0.0),
    )
    streams = NamedRandomStreams(20260902, 0)
    state = kernel.sample_state(streams)
    return kernel.generate(PATIENT, ages, streams, state=state)


def _undernutrition_trajectory(
    *,
    treatment: bool = True,
    severity: float = 0.8,
    visible_through: str = "recorded_diagnosis",
    same_age_events: bool = False,
    ages: tuple[int, ...] = DEFAULT_PHYSIOLOGY_AGES,
) -> AgeRegimeDisorderTrajectory:
    module = UndernutritionModule(
        UndernutritionConfig(
            onset_min_age_days=500,
            onset_max_age_days=500,
            severity_min=severity,
            severity_max=severity,
            treatment_probability=1.0 if treatment else 0.0,
            treatment_response_min=0.5,
            treatment_response_max=0.5,
        )
    )
    state = module.sample_state(PATIENT, NamedRandomStreams(20260902, 1))
    events = module.events(PATIENT, state)
    if not treatment:
        terminal_index = {
            "latent_onset": 0,
            "recognition_opportunity": 2,
            "workup": 3,
            "recorded_diagnosis": 4,
        }[visible_through]
        events = events[: terminal_index + 1]
    if same_age_events:
        events = tuple(
            dataclasses.replace(event, age_days=730)
            if event.event_type
            in {"recognition_opportunity", "workup", "recorded_diagnosis"}
            else event
            for event in events
        )
    return AgeRegimeDisorderTrajectory(_physiology(ages), state, events)


def _member(
    *,
    treatment: bool = True,
    severity: float = 0.8,
    visible_through: str = "recorded_diagnosis",
    recognized: bool = True,
    diagnosed: bool = True,
    same_age_events: bool = False,
    ages: tuple[int, ...] = DEFAULT_PHYSIOLOGY_AGES,
    censor_age_days: int | None = None,
    kind: DisorderKind = DisorderKind.UNDERNUTRITION,
) -> CohortMember:
    trajectory = _undernutrition_trajectory(
        treatment=treatment,
        severity=severity,
        visible_through=visible_through,
        same_age_events=same_age_events,
        ages=ages,
    )
    if kind is not DisorderKind.UNDERNUTRITION:
        trajectory = dataclasses.replace(
            trajectory,
            disorder=dataclasses.replace(trajectory.disorder, kind=kind),
        )
    frame = generate_observation_frame(
        trajectory,
        _policy(
            window_end_age_days=2200,
            censoring_mode=(
                CensoringMode.LOST_TO_FOLLOW_UP
                if censor_age_days is not None
                else CensoringMode.NONE
            ),
            censor_age_days=censor_age_days,
            recognition_probability=1.0 if recognized else 0.0,
            diagnosis_probability=1.0 if diagnosed else 0.0,
        ),
        NamedRandomStreams(20260902, 2),
    )
    assert validate_observation_frame(frame).status is ObservationValidationStatus.PASS
    return CohortMember(SyntheticDemographics(PATIENT_ID), trajectory, frame, None)


def _resources(member: CohortMember, **policy_changes: object) -> dict[str, object]:
    return project_undernutrition_ancillary_resources(
        member,
        _shape(),
        _ancillary_policy(**policy_changes),
    ).to_mapping()["resources"]  # type: ignore[no-any-return]


def _expected_ancillary_id(role: str) -> str:
    material = f"undernutrition-ancillary-id-v1\x1f{PATIENT_ID}\x1f{role}".encode()
    return f"syn-{hashlib.sha256(material).hexdigest()}"


def test_all_visible_events_project_exact_descriptor_order_and_values() -> None:
    member = _member()
    shape = _shape()
    resources = _resources(member)

    assert tuple(resources) == UNDERNUTRITION_ANCILLARY_RESOURCE_NAMES  # type: ignore[arg-type]
    assert {name: len(resources[name]) for name in resources} == {  # type: ignore[arg-type]
        "labs": 2,
        "medications": 1,
        "problem_list": 1,
        "referrals": 1,
    }

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

    referral = resources["referrals"][0]  # type: ignore[index]
    assert tuple(referral) == shape.field_names("referrals")
    assert referral == {
        "patient_id": PATIENT_ID,
        "visit_id": visible_visit_by_source[recognition.opportunity_index].visit_id,
        "referral_id": _expected_ancillary_id("referral"),
        "referral_date_age_in_days": recognition.age_days,
        "requested_specialty": UNDERNUTRITION_REFERRAL_SPECIALTY,
        "referral_number_of_visits": 1,
    }

    labs = resources["labs"]  # type: ignore[assignment]
    assert all(tuple(row) == shape.field_names("labs") for row in labs)
    assert [row["result_line_num"] for row in labs] == [1, 2]
    assert [row["result_component_name"] for row in labs] == [
        UNDERNUTRITION_WEIGHT_COMPONENT,
        UNDERNUTRITION_HEIGHT_COMPONENT,
    ]
    assert {row["lab_order_id"] for row in labs} == {
        _expected_ancillary_id("lab-order")
    }
    for row in labs:
        assert row["patient_id"] == PATIENT_ID
        assert row["visit_id"] == visible_visit_by_source[workup.opportunity_index].visit_id
        assert row["lab_order_date_age_in_days"] == workup.age_days
        assert row["lab_result_date_age_in_days"] == workup.age_days + 7
        assert row["lab_procedure_name"] == ""
        assert row["lab_procedure_description"] == ""
        assert row["result_loinc_code"] == ""
        assert row["result_value"] == ""
        assert row["result_flag"] == UNDERNUTRITION_LAB_RESULT_FLAG

    problem = resources["problem_list"][0]  # type: ignore[index]
    assert tuple(problem) == shape.field_names("problem_list")
    assert problem == {
        "patient_id": PATIENT_ID,
        "problem_list_id": _expected_ancillary_id("problem-list"),
        "noted_date_age_in_days": diagnosis.age_days,
        "resolved_date_age_in_days": "",
        "pl_diag": UNDERNUTRITION_DIAGNOSIS_CODE,
    }
    assert "visit_id" not in problem

    medication = resources["medications"][0]  # type: ignore[index]
    assert tuple(medication) == shape.field_names("medications")
    assert medication == {
        "patient_id": PATIENT_ID,
        "visit_id": visible_visit_by_source[diagnosis.opportunity_index].visit_id,
        "med_record_id": _expected_ancillary_id("medication"),
        "med_order_date_age_in_days": diagnosis.age_days,
        "med_start_date_age_in_days": 800,
        "med_end_date_age_in_days": "",
        "med_record_type": UNDERNUTRITION_MEDICATION_RECORD_TYPE,
        "med_simple_generic_name": UNDERNUTRITION_MEDICATION_NAME,
    }
    assert all(
        isinstance(value, (str, int, float)) and not isinstance(value, bool)
        for rows in resources.values()  # type: ignore[union-attr]
        for row in rows
        for value in row.values()
    )


def test_projection_follows_each_visible_event_prefix_and_zero_severity() -> None:
    no_visible = _resources(_member(treatment=False, recognized=False, diagnosed=False))
    recognition = _resources(
        _member(treatment=False, visible_through="recognition_opportunity")
    )
    workup = _resources(_member(treatment=False, visible_through="workup"))
    all_visible_untreated = _resources(_member(treatment=False))
    zero_severity = _resources(_member(treatment=False, severity=0.0))

    assert all(not no_visible[name] for name in UNDERNUTRITION_ANCILLARY_RESOURCE_NAMES)
    assert {name: len(recognition[name]) for name in recognition} == {  # type: ignore[arg-type]
        "labs": 0,
        "medications": 0,
        "problem_list": 0,
        "referrals": 1,
    }
    assert {name: len(workup[name]) for name in workup} == {  # type: ignore[arg-type]
        "labs": 2,
        "medications": 0,
        "problem_list": 0,
        "referrals": 1,
    }
    assert {name: len(all_visible_untreated[name]) for name in all_visible_untreated} == {  # type: ignore[arg-type]
        "labs": 2,
        "medications": 0,
        "problem_list": 1,
        "referrals": 1,
    }
    assert all(not zero_severity[name] for name in UNDERNUTRITION_ANCILLARY_RESOURCE_NAMES)


def test_medication_requires_visible_diagnosis_and_nonpreceding_private_start() -> None:
    diagnosis_censored = _resources(_member(censor_age_days=760))
    delayed_diagnosis = _resources(
        _member(ages=(100, 500, 590, 710, 730, 740, 1165, 1500, 2000))
    )

    assert len(diagnosis_censored["referrals"]) == 1  # type: ignore[index]
    assert len(diagnosis_censored["labs"]) == 2  # type: ignore[index]
    assert diagnosis_censored["problem_list"] == []  # type: ignore[index]
    assert diagnosis_censored["medications"] == []  # type: ignore[index]
    assert len(delayed_diagnosis["problem_list"]) == 1  # type: ignore[index]
    assert delayed_diagnosis["problem_list"][0]["noted_date_age_in_days"] == 1165  # type: ignore[index]
    assert delayed_diagnosis["medications"] == []  # type: ignore[index]


def test_same_age_events_keep_their_source_point_visit_and_result_delay() -> None:
    member = _member(same_age_events=True)
    resources = _resources(member, result_delay_days=9)
    visible = {event.event_kind: event for event in member.frame.events}

    assert {event.age_days for event in visible.values()} == {730}
    visit_ids = {
        resources["referrals"][0]["visit_id"],  # type: ignore[index]
        resources["labs"][0]["visit_id"],  # type: ignore[index]
        resources["labs"][1]["visit_id"],  # type: ignore[index]
        resources["medications"][0]["visit_id"],  # type: ignore[index]
    }
    assert len(visit_ids) == 1
    assert all(
        row["lab_order_date_age_in_days"] == 730
        and row["lab_result_date_age_in_days"] == 739
        for row in resources["labs"]  # type: ignore[union-attr]
    )


def test_every_non_target_kind_has_the_fixed_empty_projection() -> None:
    healthy_trajectory = _trajectory()
    healthy_frame = generate_observation_frame(
        healthy_trajectory,
        _policy(),
        NamedRandomStreams(20260902, 3),
    )
    healthy = CohortMember(
        SyntheticDemographics(PATIENT_ID),
        healthy_trajectory,
        healthy_frame,
        None,
    )
    members = [
        healthy,
        *(
            _member(kind=kind)
            for kind in DisorderKind
            if kind not in {DisorderKind.HEALTHY, DisorderKind.UNDERNUTRITION}
        ),
    ]

    for member in members:
        projection = project_undernutrition_ancillary_resources(
            member,
            _shape(),
            _ancillary_policy(),
        )
        assert tuple(projection.rows) == UNDERNUTRITION_ANCILLARY_RESOURCE_NAMES
        assert all(
            not projection.rows[name]
            for name in UNDERNUTRITION_ANCILLARY_RESOURCE_NAMES
        )


def test_projection_is_deterministic_nonmutating_and_never_derives_ids_from_visits() -> None:
    member = _member()
    shape = _shape()
    policy = _ancillary_policy()
    before_member = copy.deepcopy(member)
    before_frame = copy.deepcopy(member.frame)
    before_shape = copy.deepcopy(shape)
    before_policy = copy.deepcopy(policy)

    first = project_undernutrition_ancillary_resources(member, shape, policy)
    second = project_undernutrition_ancillary_resources(member, shape, policy)

    assert first.to_mapping() == second.to_mapping()
    assert member == before_member
    assert member.frame == before_frame
    assert shape == before_shape
    assert policy == before_policy

    resources = first.to_mapping()["resources"]
    generated_ids = {
        resources["referrals"][0]["referral_id"],  # type: ignore[index]
        resources["labs"][0]["lab_order_id"],  # type: ignore[index]
        resources["problem_list"][0]["problem_list_id"],  # type: ignore[index]
        resources["medications"][0]["med_record_id"],  # type: ignore[index]
    }
    input_visit_ids = {visit.visit_id for visit in member.frame.visits}
    assert generated_ids == {
        _expected_ancillary_id(role)
        for role in ("referral", "lab-order", "problem-list", "medication")
    }
    assert all(
        generated_id != visit_id and visit_id not in generated_id
        for generated_id in generated_ids
        for visit_id in input_visit_ids
    )

    visible = json.dumps(first.to_mapping(), sort_keys=True)
    for private_name in (
        "latent_onset",
        "severity",
        "treatment_response",
        "treatment_nonresponse",
        "obesity_flag",
    ):
        assert private_name not in visible


def test_projection_uses_fixed_redacted_errors_for_malformed_typed_inputs() -> None:
    with pytest.raises(
        UndernutritionAncillaryProjectionUnavailable,
        match="^undernutrition ancillary projection unavailable$",
    ) as error:
        project_undernutrition_ancillary_resources(  # type: ignore[arg-type]
            object(),
            _shape(),
            _ancillary_policy(),
        )
    assert PATIENT_ID not in str(error.value)

    member = _member()
    object.__setattr__(member.frame.truth, "latent_trajectory", None)
    with pytest.raises(
        UndernutritionAncillaryProjectionUnavailable,
        match="^undernutrition ancillary projection failed$",
    ) as error:
        project_undernutrition_ancillary_resources(
            member,
            _shape(),
            _ancillary_policy(),
        )
    message = str(error.value).lower()
    assert PATIENT_ID not in message
    assert "truth" not in message
    assert "path" not in message
    assert "key" not in message
