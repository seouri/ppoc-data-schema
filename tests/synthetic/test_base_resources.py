import csv
from io import StringIO
from pathlib import Path

import pytest

from synthetic.base_resources import build_base_rows
from synthetic.csv_package import format_resource_csv_bytes, write_resource
from synthetic.models import LatentPoint, PatientState
from synthetic.schema_contract import field_names, load_descriptor, resource_spec

ROOT = Path(__file__).resolve().parents[2]


def test_base_rows_cover_six_nonderived_resources() -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    patient = PatientState("syn-patient-a", "F", "F")
    point = LatentPoint("syn-patient-a", 730, 90.0, 16.0, 12.96, 0.0, 0.0)
    rows = build_base_rows(descriptor, patient, (point,), seed=9)
    assert set(rows) == {
        "patients", "visits", "labs", "medications", "problem_list", "referrals"
    }
    assert tuple(rows["patients"][0]) == field_names(descriptor, "patients")
    assert tuple(rows["visits"][0]) == field_names(descriptor, "visits")
    assert rows["visits"][0]["weight_oz"] == 12.96 * 35.274
    assert rows["visits"][0]["height_in"] == 90.0 / 2.54


def test_writer_uses_descriptor_header_and_encoding(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    resource = resource_spec(descriptor, "labs")
    output = tmp_path / resource["path"]
    write_resource(output, resource, [])
    with output.open(encoding="iso-8859-1", newline="") as handle:
        assert next(csv.reader(handle)) == list(field_names(descriptor, "labs"))


def test_writer_formats_raw_visit_measurements_to_fixture_precision(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    resource = resource_spec(descriptor, "visits")
    row = {name: "" for name in field_names(descriptor, "visits")}
    row.update(
        {
            "patient_id": "syn-patient-a",
            "visit_id": "syn-visit-a",
            "age_in_days": 365,
            "weight_oz": 12.345,
            "height_in": 35.678,
            "head_circ_cm": 48.76,
            "BMI": 17.123456,
            "enc_diag_1": "SYN-GROWTH-RECOGNITION",
            "enc_diag_2": "SYN-GROWTH-WORKUP",
            "enc_diag_3": "SYN-GROWTH-DIAGNOSIS",
        }
    )
    output = tmp_path / resource["path"]

    write_resource(output, resource, [row])

    with output.open(encoding="utf-8", newline="") as handle:
        written = next(csv.DictReader(handle))
    assert written["weight_oz"] == "12.35"
    assert written["height_in"] == "35.68"
    assert written["head_circ_cm"] == "48.8"
    assert written["BMI"] == "17.12"
    assert written["enc_diag_1"] == "R62.52"
    assert written["enc_diag_2"] == "R62.50"
    assert written["enc_diag_3"] == "R62.59"


def test_formatter_formats_augmented_bmi_without_changing_other_values() -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    resource = resource_spec(descriptor, "visits_augmented")
    fields = list(field_names(descriptor, "visits_augmented"))
    row = {name: "" for name in fields}
    row.update(
        {
            "patient_id": "syn-patient-a",
            "visit_id": "syn-visit-a",
            "age_in_days": "730",
            "bmi": "17.123456",
            "weight_kg": "12.345",
        }
    )
    source = StringIO(newline="")
    writer = csv.DictWriter(source, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerow(row)

    formatted = format_resource_csv_bytes(resource, source.getvalue().encode("utf-8"))

    written = next(csv.DictReader(StringIO(formatted.decode("utf-8"))))
    assert written["bmi"] == "17.12"
    assert written["weight_kg"] == "12.345"


def test_writer_rejects_non_icd10_encounter_diagnosis(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    resource = resource_spec(descriptor, "visits")
    row = {name: "" for name in field_names(descriptor, "visits")}
    row.update(
        {
            "patient_id": "syn-patient-a",
            "visit_id": "syn-visit-a",
            "age_in_days": 365,
            "enc_diag_1": "SYN-NOT-ICD10",
        }
    )

    with pytest.raises(ValueError, match="enc_diag_1 must contain an ICD-10 code"):
        write_resource(tmp_path / resource["path"], resource, [row])
