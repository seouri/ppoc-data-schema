import copy
import csv
import json
from pathlib import Path

from synthetic.csv_package import write_synthetic_descriptor
from synthetic.schema_contract import load_descriptor
from synthetic.validate import validate_structure

ROOT = Path(__file__).resolve().parents[2]


def _empty_package(root: Path, descriptor: dict) -> None:
    for resource in descriptor["resources"]:
        path = root / resource["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding=resource["encoding"], newline="") as handle:
            csv.writer(handle).writerow(
                field["name"] for field in resource["schema"]["fields"]
            )


def test_empty_exact_schema_package_is_structurally_valid(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    _empty_package(tmp_path, descriptor)
    report = validate_structure(tmp_path, descriptor)
    assert report.errors == ()
    assert report.row_counts == {item["name"]: 0 for item in descriptor["resources"]}


def test_wrong_header_fails_with_resource_name(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    _empty_package(tmp_path, descriptor)
    (tmp_path / "patients.csv").write_text("wrong\n", encoding="utf-8")
    report = validate_structure(tmp_path, descriptor)
    assert "patients: header mismatch" in report.errors


def test_invalid_required_and_enum_values_fail(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    _empty_package(tmp_path, descriptor)
    patients = next(item for item in descriptor["resources"] if item["name"] == "patients")
    fields = [field["name"] for field in patients["schema"]["fields"]]
    row = {field: "" for field in fields}
    row.update({"patient_id": "syn-patient-a", "sex": "X"})
    with (tmp_path / "patients.csv").open("a", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=fields).writerow(row)
    report = validate_structure(tmp_path, descriptor)
    assert "patients row 2 sex: value is not in enum" in report.errors


def test_synthetic_descriptor_removes_real_statistics(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    _empty_package(tmp_path, descriptor)
    row_counts = {item["name"]: 0 for item in descriptor["resources"]}
    output = write_synthetic_descriptor(tmp_path, copy.deepcopy(descriptor), row_counts)
    generated = json.loads(output.read_text())
    assert generated["name"] == "ppoc-pediatric-ehr-synthetic"
    assert generated["x-synthetic"] is True
    assert all(resource["x-rowCount"] == 0 for resource in generated["resources"])
    serialized = output.read_text()
    assert '"x-topValues"' not in serialized
    assert "250588" not in serialized
    patient_id = generated["resources"][0]["schema"]["fields"][0]
    assert patient_id["x-missingCount"] == 0
    assert patient_id["x-uniqueValueCount"] == 0
    logical_links = [
        link
        for resource in generated["resources"]
        for link in resource.get("x-logicalForeignKeys", [])
    ]
    assert logical_links
    assert all(link["nullRows"] == 0 and link["orphanRows"] == 0 for link in logical_links)
