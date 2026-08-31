from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from synthetic.native.observations import (
    RECORDED_EVENT_CODES,
    CensoringMode,
    ObservationFrame,
    ObservationTruth,
    ObservationWindow,
    RecordedEventKind,
)
from synthetic.native.resources import (
    BASE_RESOURCE_NAMES,
    ClinicalDescendant,
    ObservedResourceBundle,
    ResourceCheck,
    ResourceRow,
    ResourceShape,
    ResourceSpec,
    ResourceValidationReport,
    ResourceValidationStatus,
    SyntheticDemographics,
)

ROOT = Path(__file__).resolve().parents[2]


def _descriptor() -> dict[str, object]:
    return json.loads((ROOT / "datapackage.json").read_text(encoding="utf-8"))


def _frame(patient_id: str = "syn-resource-patient") -> ObservationFrame:
    window = ObservationWindow(0, 3650, 3650, CensoringMode.NONE)
    truth = ObservationTruth(patient_id, window, (), (), (), ())
    return ObservationFrame(patient_id, "observation-v1", window, (), (), truth)


def _shape() -> ResourceShape:
    return ResourceShape.from_descriptor(_descriptor())


def _bundle() -> ObservedResourceBundle:
    shape = _shape()
    demographics = SyntheticDemographics("syn-resource-patient")
    patient_values = tuple(
        (field_name, demographics.to_mapping().get(field_name, ""))
        for field_name in shape.field_names("patients")
    )
    rows = {
        "patients": (ResourceRow("patients", patient_values),),
        "visits": (),
        "labs": (),
        "medications": (),
        "problem_list": (),
        "referrals": (),
    }
    return ObservedResourceBundle(
        "syn-resource-patient", shape, rows, (), _frame()
    )


def _checks(status: ResourceValidationStatus) -> tuple[ResourceCheck, ...]:
    return tuple(
        ResourceCheck(name, status, "OK") for name in ResourceValidationReport.CHECK_NAMES
    )


def test_shape_extracts_exact_six_base_resources_in_descriptor_field_order() -> None:
    shape = _shape()

    assert BASE_RESOURCE_NAMES == (
        "patients",
        "visits",
        "labs",
        "medications",
        "problem_list",
        "referrals",
    )
    assert tuple(spec.name for spec in shape.resources) == BASE_RESOURCE_NAMES
    assert shape.field_names("patients") == (
        "patient_id",
        "sex",
        "ethnicity",
        "race_1",
        "race_2",
        "race_3",
        "race_4",
        "race_5",
        "race_6",
        "race_7",
        "race_8",
    )
    assert shape.field_names("visits")[:5] == (
        "patient_id",
        "visit_id",
        "age_in_days",
        "encounter_type",
        "orig_enc_source_Epic_yn",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        shape.resources = ()  # type: ignore[misc]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda descriptor: descriptor["resources"].pop(),  # type: ignore[index,union-attr]
            "required base resources",
        ),
        (
            lambda descriptor: descriptor["resources"].append(  # type: ignore[index,union-attr]
                descriptor["resources"][0]  # type: ignore[index,union-attr]
            ),
            "duplicate resource",
        ),
        (
            lambda descriptor: descriptor["resources"][0]["schema"].update(  # type: ignore[index,union-attr]
                {"fields": [{"name": "patient_id"}, {"name": "patient_id"}]}
            ),
            "duplicate field",
        ),
        (
            lambda descriptor: descriptor["resources"][0]["schema"].update(  # type: ignore[index,union-attr]
                {"fields": [{"name": "patient_id"}, {"name": ""}]}
            ),
            "field name",
        ),
    ],
)
def test_shape_rejects_missing_or_duplicate_required_resource_fields(
    mutate: object, message: str
) -> None:
    descriptor = _descriptor()
    mutate(descriptor)  # type: ignore[operator]

    with pytest.raises((TypeError, ValueError), match=message):
        ResourceShape.from_descriptor(descriptor)


def test_demographics_are_synthetic_only_closed_and_immutable() -> None:
    demographics = SyntheticDemographics(
        "syn-resource-patient", "F", "Hispanic or Latino", ("White",) * 8
    )

    assert demographics.to_mapping() == {
        "patient_id": "syn-resource-patient",
        "sex": "F",
        "ethnicity": "Hispanic or Latino",
        **{f"race_{index}": "White" for index in range(1, 9)},
    }
    with pytest.raises(dataclasses.FrozenInstanceError):
        demographics.sex = "U"  # type: ignore[misc]
    with pytest.raises(ValueError, match="synthetic"):
        SyntheticDemographics("patient-1")
    with pytest.raises(ValueError, match="sex"):
        SyntheticDemographics("syn-resource-patient", "X")
    with pytest.raises(ValueError, match="ethnicity"):
        SyntheticDemographics("syn-resource-patient", ethnicity="Martian")
    with pytest.raises(ValueError, match="race"):
        SyntheticDemographics("syn-resource-patient", races=("Martian",) * 8)


def test_row_pairs_are_ordered_immutable_and_map_missing_values_to_empty_strings() -> None:
    row = ResourceRow("patients", (("patient_id", "syn-resource-patient"), ("sex", None)))

    assert row.values == (("patient_id", "syn-resource-patient"), ("sex", ""))
    assert row.to_mapping() == {"patient_id": "syn-resource-patient", "sex": ""}
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.values = ()  # type: ignore[misc]
    with pytest.raises(TypeError, match="tuple"):
        ResourceRow("patients", {"patient_id": "syn-resource-patient"})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="duplicate field"):
        ResourceRow("patients", (("patient_id", "syn-a"), ("patient_id", "syn-a")))


def test_descendants_only_accept_registered_fictional_codes_and_synthetic_links() -> None:
    descendant = ClinicalDescendant(
        "syn-resource-patient",
        "syn-resource-visit",
        730,
        RecordedEventKind.DIAGNOSIS,
        RECORDED_EVENT_CODES[RecordedEventKind.DIAGNOSIS],
    )

    assert descendant.to_mapping()["code"] == "SYN-GROWTH-DIAGNOSIS"
    with pytest.raises(ValueError, match="code"):
        ClinicalDescendant(
            "syn-resource-patient",
            "syn-resource-visit",
            730,
            RecordedEventKind.DIAGNOSIS,
            "ICD-10",
        )
    with pytest.raises(ValueError, match="synthetic"):
        ClinicalDescendant(
            "real-patient",
            "syn-resource-visit",
            730,
            RecordedEventKind.DIAGNOSIS,
            RECORDED_EVENT_CODES[RecordedEventKind.DIAGNOSIS],
        )


def test_bundle_keeps_source_frame_private_and_visible_mapping_uses_all_resources() -> None:
    bundle = _bundle()

    mapping = bundle.to_mapping()
    serialized = json.dumps(mapping, sort_keys=True)
    assert tuple(mapping["resources"]) == BASE_RESOURCE_NAMES
    assert mapping["resources"]["labs"] == []
    assert "truth" not in serialized
    assert "source_frame" not in serialized
    assert "syn-resource-patient" not in repr(bundle)
    assert "ObservationFrame" not in repr(bundle)
    with pytest.raises(dataclasses.FrozenInstanceError):
        bundle.source_frame = _frame()  # type: ignore[misc]
    with pytest.raises(TypeError, match="ObservationFrame"):
        ObservedResourceBundle(
            bundle.patient_id,
            bundle.shape,
            bundle.rows,
            bundle.clinical_descendants,
            object(),
        )


def test_report_requires_fixed_checks_and_aggregates_statuses() -> None:
    report = ResourceValidationReport(ResourceValidationStatus.PASS, _checks(ResourceValidationStatus.PASS))

    assert report.check_counts == {"PASS": 7, "FAIL": 0, "UNEVALUABLE": 0}
    assert report.to_mapping()["status"] == "PASS"
    checks = list(_checks(ResourceValidationStatus.PASS))
    checks[-1] = ResourceCheck("evidence", ResourceValidationStatus.UNEVALUABLE, "INSUFFICIENT_EVIDENCE")
    unevaluable = ResourceValidationReport(ResourceValidationStatus.UNEVALUABLE, tuple(checks))
    assert unevaluable.status is ResourceValidationStatus.UNEVALUABLE
    checks[-2] = ResourceCheck("ancillary_resources", ResourceValidationStatus.FAIL, "ANCILLARY_ROWS_PRESENT")
    failed = ResourceValidationReport(ResourceValidationStatus.FAIL, tuple(checks))
    assert failed.status is ResourceValidationStatus.FAIL
    with pytest.raises(ValueError, match="fixed resource check"):
        ResourceCheck("unknown", ResourceValidationStatus.PASS, "OK")
    with pytest.raises(ValueError, match="every fixed"):
        ResourceValidationReport(ResourceValidationStatus.PASS, _checks(ResourceValidationStatus.PASS)[:-1])


def test_resource_spec_rejects_unknown_resource_and_unordered_fields() -> None:
    with pytest.raises(ValueError, match="base resource"):
        ResourceSpec("unknown", ("field",))
    with pytest.raises(TypeError, match="tuple"):
        ResourceSpec("patients", ["patient_id"])  # type: ignore[arg-type]
