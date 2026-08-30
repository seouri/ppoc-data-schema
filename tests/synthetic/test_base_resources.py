import csv
from pathlib import Path

from synthetic.base_resources import build_base_rows
from synthetic.csv_package import write_resource
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
