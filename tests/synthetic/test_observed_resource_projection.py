from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from synthetic.native.observations import (
    MeasurementAvailability,
    MeasurementChannel,
    ObservationValidationStatus,
    generate_observation_frame,
    validate_observation_frame,
)
from synthetic.native.resources import (
    BASE_RESOURCE_NAMES,
    ResourceProjectionUnavailable,
    SyntheticDemographics,
    project_observed_resources,
)
from synthetic.randomness import NamedRandomStreams
from tests.synthetic.test_observation_generation import _event_trajectory, _policy, _trajectory

ROOT = Path(__file__).resolve().parents[2]


def _descriptor() -> dict[str, object]:
    return json.loads((ROOT / "datapackage.json").read_text(encoding="utf-8"))


def _resource_compatible_frame():
    frame = generate_observation_frame(
        _event_trajectory(),
        _policy(
            length_availability_probability=0.0,
            height_availability_probability=1.0,
            weight_availability_probability=1.0,
            head_circumference_availability_probability=1.0,
            recognition_probability=1.0,
            diagnosis_probability=1.0,
            recognition_delay_days=50,
        ),
        NamedRandomStreams(6, 0),
    )
    assert validate_observation_frame(frame).status is ObservationValidationStatus.PASS
    return frame


def _row_by_age(bundle: object, age_days: int) -> dict[str, object]:
    visits = bundle.to_mapping()["resources"]["visits"]  # type: ignore[index,union-attr]
    return next(row for row in visits if row["age_in_days"] == age_days)  # type: ignore[union-attr,return-value]


def test_projection_emits_descriptor_ordered_rows_with_default_demographics_and_visible_measurements() -> None:
    frame = _resource_compatible_frame()

    bundle = project_observed_resources(frame, _descriptor())

    mapping = bundle.to_mapping()
    patient = mapping["resources"]["patients"][0]  # type: ignore[index]
    visit_1000 = _row_by_age(bundle, 1000)
    expected_visit_fields = tuple(
        field["name"]
        for resource in _descriptor()["resources"]  # type: ignore[index]
        if resource["name"] == "visits"  # type: ignore[index]
        for field in resource["schema"]["fields"]  # type: ignore[index]
    )

    assert tuple(mapping["resources"]) == BASE_RESOURCE_NAMES  # type: ignore[arg-type,index]
    assert len(mapping["resources"]["patients"]) == 1  # type: ignore[index]
    assert len(mapping["resources"]["visits"]) == len(frame.visits)  # type: ignore[index]
    assert patient == {
        "patient_id": "syn-observation-patient",
        "sex": "U",
        "ethnicity": "Unknown",
        "race_1": "Unknown",
        **{f"race_{index}": "" for index in range(2, 9)},
    }
    assert tuple(visit_1000) == expected_visit_fields
    assert visit_1000["encounter_type"] == "Office Visit"
    assert visit_1000["orig_enc_source_Epic_yn"] == "N"
    assert visit_1000["weight_oz"] == pytest.approx(400.00716)
    assert visit_1000["height_in"] == pytest.approx(35.43307086614173)
    assert visit_1000["head_circ_cm"] == ""
    assert visit_1000["BMI"] == pytest.approx(14.0)
    assert all(
        visit["height_in"] == ""
        for visit in mapping["resources"]["visits"]  # type: ignore[index]
        if visit["age_in_days"] == 100
    )
    assert all(mapping["resources"][name] == [] for name in BASE_RESOURCE_NAMES[2:])  # type: ignore[index]


def test_projection_links_fictional_events_to_exact_visits_and_replays_deterministically() -> None:
    frame = _resource_compatible_frame()

    first = project_observed_resources(frame, _descriptor())
    replay = project_observed_resources(frame, _descriptor())

    assert first.to_mapping() == replay.to_mapping()
    descendants = first.to_mapping()["clinical_descendants"]  # type: ignore[index]
    assert [(item["age_days"], item["event_kind"], item["code"]) for item in descendants] == [
        (1000, "recognition", "SYN-GROWTH-RECOGNITION"),
        (1500, "workup", "SYN-GROWTH-WORKUP"),
        (1500, "diagnosis", "SYN-GROWTH-DIAGNOSIS"),
    ]
    assert descendants[0]["visit_id"] == _row_by_age(first, 1000)["visit_id"]
    assert descendants[1]["visit_id"] == _row_by_age(first, 1500)["visit_id"]
    assert descendants[2]["visit_id"] == _row_by_age(first, 1500)["visit_id"]
    realized_opportunities = tuple(
        opportunity for opportunity in frame.truth.opportunities if opportunity.realized
    )
    visible_visit_by_source_point = {
        opportunity.source_point_index: visit
        for opportunity, visit in zip(realized_opportunities, frame.visits, strict=True)
    }
    assert all(event.opportunity_index is not None for event in frame.events)
    assert [descendant["visit_id"] for descendant in descendants] == [
        visible_visit_by_source_point[event.opportunity_index].visit_id  # type: ignore[index]
        for event in frame.events
    ]
    visit_1500 = _row_by_age(first, 1500)
    assert visit_1500["enc_diag_1"] == "SYN-GROWTH-WORKUP"
    assert visit_1500["enc_diag_2"] == "SYN-GROWTH-DIAGNOSIS"


def test_projection_keeps_missing_measurements_empty_and_requires_a_passing_frame() -> None:
    frame = generate_observation_frame(
        _trajectory(),
        _policy(
            length_availability_probability=0.0,
            height_availability_probability=0.0,
            weight_availability_probability=1.0,
            head_circumference_availability_probability=1.0,
        ),
        NamedRandomStreams(12, 0),
    )
    assert validate_observation_frame(frame).status is ObservationValidationStatus.PASS

    visit_1000 = _row_by_age(project_observed_resources(frame, _descriptor()), 1000)

    assert visit_1000["height_in"] == ""
    assert visit_1000["BMI"] == ""

    tampered = dataclasses.replace(frame, truth=dataclasses.replace(frame.truth, policy=None))
    assert validate_observation_frame(tampered).status is ObservationValidationStatus.UNEVALUABLE
    with pytest.raises(ValueError, match="PASS"):
        project_observed_resources(tampered, _descriptor())


def test_projection_rejects_valid_observed_length_before_emitting_rows() -> None:
    frame = generate_observation_frame(
        _trajectory(),
        _policy(length_availability_probability=1.0),
        NamedRandomStreams(3, 0),
    )
    assert validate_observation_frame(frame).status is ObservationValidationStatus.PASS

    with pytest.raises(ResourceProjectionUnavailable, match="LENGTH"):
        project_observed_resources(
            frame,
            _descriptor(),
            SyntheticDemographics("syn-observation-patient", "F", "Hispanic or Latino", ("White",) * 8),
        )


def test_projection_rejects_descriptors_missing_required_patient_fields() -> None:
    descriptor = _descriptor()
    patient_resource = next(
        resource for resource in descriptor["resources"] if resource["name"] == "patients"  # type: ignore[index]
    )
    patient_resource["schema"]["fields"] = [  # type: ignore[index]
        field
        for field in patient_resource["schema"]["fields"]  # type: ignore[index]
        if field["name"] != "race_8"
    ]

    with pytest.raises(ResourceProjectionUnavailable, match="patients resource lacks"):
        project_observed_resources(_resource_compatible_frame(), descriptor)


def test_projection_rejects_tampered_visible_values_even_when_the_frame_type_is_valid() -> None:
    frame = _resource_compatible_frame()
    visit = frame.visits[2]
    measurements = list(visit.measurements)
    weight_index = next(
        index
        for index, measurement in enumerate(measurements)
        if measurement.channel is MeasurementChannel.WEIGHT
    )
    measurements[weight_index] = dataclasses.replace(
        measurements[weight_index],
        availability=MeasurementAvailability.OBSERVED,
        recorded_value=99.0,
    )
    tampered = dataclasses.replace(
        frame,
        visits=frame.visits[:2]
        + (dataclasses.replace(visit, measurements=tuple(measurements)),)
        + frame.visits[3:],
    )
    assert validate_observation_frame(tampered).status is ObservationValidationStatus.FAIL

    with pytest.raises(ValueError, match="PASS"):
        project_observed_resources(tampered, _descriptor())
