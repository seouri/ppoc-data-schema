from __future__ import annotations

import json
from pathlib import Path

from synthetic.native.observations import MeasurementChannel
from synthetic.native.resources import (
    BASE_RESOURCE_NAMES,
    ClinicalDescendant,
    ResourceRow,
    ResourceValidationStatus,
    project_observed_resources,
    validate_observed_resources,
)
from tests.synthetic.test_observed_resource_projection import _resource_compatible_frame

ROOT = Path(__file__).resolve().parents[2]


def _descriptor() -> dict[str, object]:
    return json.loads((ROOT / "datapackage.json").read_text(encoding="utf-8"))


def _bundle():
    return project_observed_resources(_resource_compatible_frame(), _descriptor())


def _check(report: object, name: str) -> tuple[str, str]:
    checks = report.to_mapping()["checks"]  # type: ignore[union-attr,index]
    check = next(item for item in checks if item["name"] == name)
    return check["status"], check["reason_code"]


def test_validate_observed_resources_accepts_an_exact_projection_without_leaking_private_data() -> None:
    bundle = _bundle()

    first = validate_observed_resources(bundle)
    replay = validate_observed_resources(bundle)

    assert first.status is ResourceValidationStatus.PASS
    assert first.to_mapping() == replay.to_mapping()
    assert tuple(item["name"] for item in first.to_mapping()["checks"]) == tuple(
        sorted(
            (
                "patient_identity",
                "schema_shape",
                "visit_references",
                "measurements",
                "clinical_descendants",
                "ancillary_resources",
                "evidence",
            )
        )
    )
    rendered = repr(first) + repr(first.to_mapping())
    for forbidden in (
        bundle.patient_id,
        str(bundle.source_frame.visits[0].age_days),
        str(bundle.source_frame.visits[0].measurements[0].recorded_value),
        "truth",
        "hash",
        "ResourceShape",
    ):
        assert forbidden not in rendered


def test_validate_observed_resources_marks_nonbundle_or_missing_private_evidence_unevaluable() -> None:
    assert validate_observed_resources(object()).status is ResourceValidationStatus.UNEVALUABLE

    bundle = _bundle()
    object.__setattr__(bundle, "source_frame", None)

    report = validate_observed_resources(bundle)

    assert report.status is ResourceValidationStatus.UNEVALUABLE
    assert _check(report, "evidence") == ("UNEVALUABLE", "INSUFFICIENT_EVIDENCE")


def test_validate_observed_resources_rejects_bad_visible_visit_without_source_evidence() -> None:
    bundle = _bundle()
    row = bundle.rows["visits"][0]
    values = row.to_mapping()
    values["visit_id"] = "real-visit"
    object.__setattr__(row, "values", tuple(values.items()))
    object.__setattr__(bundle, "source_frame", None)

    report = validate_observed_resources(bundle)

    assert report.status is ResourceValidationStatus.FAIL
    assert _check(report, "visit_references") == ("FAIL", "VISIT_REFERENCE_INVALID")


def test_validate_observed_resources_rejects_bad_visible_measurement_without_source_evidence() -> None:
    bundle = _bundle()
    row = next(row for row in bundle.rows["visits"] if row.to_mapping()["weight_oz"] != "")
    values = row.to_mapping()
    values["weight_oz"] = -1.0
    object.__setattr__(row, "values", tuple(values.items()))
    object.__setattr__(bundle, "source_frame", None)

    report = validate_observed_resources(bundle)

    assert report.status is ResourceValidationStatus.FAIL
    assert _check(report, "measurements") == ("FAIL", "MEASUREMENT_INVALID")


def test_validate_observed_resources_rejects_bad_descendant_or_diagnosis_slot_without_source_evidence() -> None:
    descendant_bundle = _bundle()
    descendant = descendant_bundle.clinical_descendants[0]
    object.__setattr__(descendant, "code", "not-a-fictional-code")
    object.__setattr__(descendant_bundle, "source_frame", None)

    descendant_report = validate_observed_resources(descendant_bundle)

    assert descendant_report.status is ResourceValidationStatus.FAIL
    assert _check(descendant_report, "clinical_descendants") == (
        "FAIL",
        "CLINICAL_DESCENDANT_INVALID",
    )

    slot_bundle = _bundle()
    row = next(row for row in slot_bundle.rows["visits"] if row.to_mapping()["enc_diag_1"] != "")
    values = row.to_mapping()
    values["enc_diag_1"] = "not-a-fictional-code"
    object.__setattr__(row, "values", tuple(values.items()))
    object.__setattr__(slot_bundle, "source_frame", None)

    slot_report = validate_observed_resources(slot_bundle)

    assert slot_report.status is ResourceValidationStatus.FAIL
    assert _check(slot_report, "clinical_descendants") == (
        "FAIL",
        "CLINICAL_DESCENDANT_INVALID",
    )


def test_validate_observed_resources_rejects_patient_field_order_and_visit_key_violations() -> None:
    patient_bundle = _bundle()
    patient_row = patient_bundle.rows["patients"][0]
    object.__setattr__(
        patient_row,
        "values",
        (("patient_id", "syn-other-patient"), *patient_row.values[1:]),
    )
    patient_report = validate_observed_resources(patient_bundle)
    assert _check(patient_report, "patient_identity") == ("FAIL", "PATIENT_MISMATCH")

    shape_bundle = _bundle()
    visit_row = shape_bundle.rows["visits"][0]
    object.__setattr__(shape_bundle.rows["visits"][0], "values", tuple(reversed(visit_row.values)))
    shape_report = validate_observed_resources(shape_bundle)
    assert _check(shape_report, "schema_shape") == ("FAIL", "SCHEMA_SHAPE_INVALID")

    visit_bundle = _bundle()
    tampered_visit = visit_bundle.rows["visits"][0]
    object.__setattr__(
        tampered_visit,
        "values",
        (("patient_id", visit_bundle.patient_id), ("visit_id", "syn-wrong-visit"), *tampered_visit.values[2:]),
    )
    visit_report = validate_observed_resources(visit_bundle)
    assert _check(visit_report, "visit_references") == ("FAIL", "VISIT_REFERENCE_INVALID")


def test_validate_observed_resources_requires_exactly_one_patient_row() -> None:
    missing_patient = _bundle()
    missing_rows = dict(missing_patient.rows)
    missing_rows["patients"] = ()
    object.__setattr__(missing_patient, "rows", missing_rows)

    missing_report = validate_observed_resources(missing_patient)

    assert _check(missing_report, "schema_shape") == ("FAIL", "SCHEMA_SHAPE_INVALID")

    duplicate_patient = _bundle()
    duplicate_rows = dict(duplicate_patient.rows)
    duplicate_rows["patients"] = duplicate_rows["patients"] * 2
    object.__setattr__(duplicate_patient, "rows", duplicate_rows)

    duplicate_report = validate_observed_resources(duplicate_patient)

    assert _check(duplicate_report, "schema_shape") == ("FAIL", "SCHEMA_SHAPE_INVALID")


def test_validate_observed_resources_rejects_invalid_patient_demographic_tokens() -> None:
    bundle = _bundle()
    patient = bundle.rows["patients"][0]
    values = patient.to_mapping()
    values["sex"] = "X"
    object.__setattr__(patient, "values", tuple(values.items()))

    report = validate_observed_resources(bundle)

    assert _check(report, "patient_identity") == ("FAIL", "PATIENT_MISMATCH")


def test_validate_observed_resources_treats_malformed_visible_rows_as_failures() -> None:
    bundle = _bundle()
    row = bundle.rows["visits"][0]
    object.__setattr__(row, "values", (("patient_id", bundle.patient_id), "malformed-pair"))

    report = validate_observed_resources(bundle)

    assert report.status is ResourceValidationStatus.FAIL
    assert _check(report, "schema_shape") == ("FAIL", "SCHEMA_SHAPE_INVALID")


def test_validate_observed_resources_keeps_private_truth_corruption_unevaluable() -> None:
    bundle = _bundle()
    object.__setattr__(bundle.source_frame.truth, "opportunities", None)

    report = validate_observed_resources(bundle)

    assert report.status is ResourceValidationStatus.UNEVALUABLE
    assert _check(report, "evidence") == ("UNEVALUABLE", "INSUFFICIENT_EVIDENCE")


def test_validate_observed_resources_treats_private_truth_hash_failure_as_unevaluable() -> None:
    bundle = _bundle()
    object.__setattr__(bundle.source_frame.truth, "truth_hash", "0" * 64)

    report = validate_observed_resources(bundle)

    assert report.status is ResourceValidationStatus.UNEVALUABLE
    assert _check(report, "evidence") == ("UNEVALUABLE", "INSUFFICIENT_EVIDENCE")


def test_validate_observed_resources_rejects_measurement_unit_and_bmi_changes() -> None:
    bundle = _bundle()
    weight_row = next(row for row in bundle.rows["visits"] if row.to_mapping()["weight_oz"] != "")
    weight_values = weight_row.to_mapping()
    weight_values["weight_oz"] = float(weight_values["weight_oz"]) + 1.0
    object.__setattr__(weight_row, "values", tuple(weight_values.items()))

    unit_report = validate_observed_resources(bundle)

    assert _check(unit_report, "measurements") == ("FAIL", "MEASUREMENT_INVALID")

    bundle = _bundle()
    visit = next(
        visit for visit in bundle.source_frame.visits if any(
            measurement.channel is MeasurementChannel.BMI
            and measurement.recorded_value is not None
            for measurement in visit.measurements
        )
    )
    row = next(row for row in bundle.rows["visits"] if row.to_mapping()["visit_id"] == visit.visit_id)
    values = row.to_mapping()
    values["BMI"] = float(values["BMI"]) + 1.0
    object.__setattr__(row, "values", tuple(values.items()))

    report = validate_observed_resources(bundle)

    assert _check(report, "measurements") == ("FAIL", "MEASUREMENT_INVALID")


def test_validate_observed_resources_rejects_unprojected_visit_field_values() -> None:
    bundle = _bundle()
    row = bundle.rows["visits"][0]
    values = row.to_mapping()
    values["bmi_percentile"] = 50.0
    object.__setattr__(row, "values", tuple(values.items()))

    report = validate_observed_resources(bundle)

    assert _check(report, "schema_shape") == ("FAIL", "SCHEMA_SHAPE_INVALID")


def test_validate_observed_resources_requires_exact_event_correspondence_and_empty_ancillary_resources() -> None:
    bundle = _bundle()
    descendant = bundle.clinical_descendants[0]
    object.__setattr__(
        bundle,
        "clinical_descendants",
        (
            ClinicalDescendant(
                bundle.patient_id,
                "syn-wrong-visit",
                descendant.age_days,
                descendant.event_kind,
                descendant.code,
            ),
            *bundle.clinical_descendants[1:],
        ),
    )
    descendant_report = validate_observed_resources(bundle)
    assert _check(descendant_report, "clinical_descendants") == (
        "FAIL",
        "CLINICAL_DESCENDANT_INVALID",
    )

    ancillary_bundle = _bundle()
    lab_values = tuple(
        (
            name,
            ancillary_bundle.patient_id
            if name == "patient_id"
            else "syn-ancillary-visit"
            if name == "visit_id"
            else "",
        )
        for name in ancillary_bundle.shape.field_names("labs")
    )
    rows = dict(ancillary_bundle.rows)
    rows["labs"] = (ResourceRow("labs", lab_values),)
    object.__setattr__(ancillary_bundle, "rows", rows)
    ancillary_report = validate_observed_resources(ancillary_bundle)
    assert _check(ancillary_report, "ancillary_resources") == ("FAIL", "ANCILLARY_ROWS_PRESENT")


def test_validate_observed_resources_uses_the_current_descriptor_shape_without_changing_it() -> None:
    bundle = _bundle()
    descriptor = _descriptor()

    report = validate_observed_resources(bundle)

    assert report.status is ResourceValidationStatus.PASS
    assert tuple(bundle.rows) == BASE_RESOURCE_NAMES
    assert tuple(
        resource["name"] for resource in descriptor["resources"]  # type: ignore[index]
    ) == (
        "patients",
        "patients_augmented",
        "visits",
        "visits_augmented",
        "labs",
        "medications",
        "problem_list",
        "referrals",
    )
