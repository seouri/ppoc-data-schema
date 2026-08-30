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


def test_synthetic_descriptor_has_no_real_provenance(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    _empty_package(tmp_path, descriptor)
    output = write_synthetic_descriptor(tmp_path, copy.deepcopy(descriptor), {
        item["name"]: 0 for item in descriptor["resources"]
    })
    generated = json.loads(output.read_text())
    assert generated["sources"] == []
    assert generated["licenses"] == []
    assert generated["contributors"] == []
    assert generated["homepage"] is None
    assert all("x-generatedBy" not in resource and "x-derivedFrom" not in resource
               for resource in generated["resources"])


def test_synthetic_descriptor_strips_all_source_snapshot_metadata(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    descriptor["x-created"] = "real-snapshot"
    descriptor["resources"][0]["x-keyDescription"] = "real"
    descriptor["resources"][0]["schema"]["fields"][0]["x-unit"] = "cm"
    descriptor["resources"][0]["schema"]["fields"][0]["x-encodingNote"] = "real"
    _empty_package(tmp_path, descriptor)
    generated = json.loads(write_synthetic_descriptor(tmp_path, descriptor, {
        item["name"]: 0 for item in descriptor["resources"]
    }).read_text())
    serialized = json.dumps(generated)
    assert "real-snapshot" not in serialized
    assert "x-keyDescription" not in serialized
    assert "x-encodingNote" not in serialized
    assert generated["resources"][0]["schema"]["fields"][0]["x-unit"] == "cm"


def test_validation_uses_declared_semicolon_dialect(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    patients = next(item for item in descriptor["resources"] if item["name"] == "patients")
    patients["dialect"]["delimiter"] = ";"
    _empty_package(tmp_path, descriptor)
    fields = [field["name"] for field in patients["schema"]["fields"]]
    row = {field: "" for field in fields}
    row["patient_id"] = "syn-a"
    row["sex"] = "U"
    with (tmp_path / "patients.csv").open("w", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=fields, delimiter=";").writeheader()
        csv.DictWriter(handle, fieldnames=fields, delimiter=";").writerow(row)
    report = validate_structure(tmp_path, descriptor)
    assert not any(error.startswith("patients:") for error in report.errors)


def test_descriptor_statistics_use_declared_dialect(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    patients = next(item for item in descriptor["resources"] if item["name"] == "patients")
    patients["dialect"].update({"delimiter": ";", "quoteChar": "|"})
    sex = next(field for field in patients["schema"]["fields"] if field["name"] == "sex")
    sex["constraints"]["enum"].append("syn;|sex")
    links = next(item for item in descriptor["resources"] if item["name"] == "visits_augmented")
    links["dialect"].update({"delimiter": ";", "quoteChar": "|"})
    _empty_package(tmp_path, descriptor)
    patient_fields = [field["name"] for field in patients["schema"]["fields"]]
    patient_row = {field: "" for field in patient_fields}
    patient_row.update({"patient_id": "syn;|a", "sex": "syn;|sex"})
    with (tmp_path / patients["path"]).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=patient_fields, delimiter=";", quotechar="|")
        writer.writeheader()
        writer.writerow(patient_row)
    link_fields = [field["name"] for field in links["schema"]["fields"]]
    link_row = {field: "" for field in link_fields}
    link_row["visit_id"] = "orphan;|visit"
    with (tmp_path / links["path"]).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=link_fields, delimiter=";", quotechar="|")
        writer.writeheader()
        writer.writerow(link_row)
    output = write_synthetic_descriptor(tmp_path, descriptor, {
        item["name"]: 1 if item["name"] in {"patients", "visits_augmented"} else 0
        for item in descriptor["resources"]
    })
    generated = json.loads(output.read_text())
    patient_field = generated["resources"][0]["schema"]["fields"][0]
    assert patient_field["x-uniqueValueCount"] == 1
    assert patient_field["x-missingCount"] == 0
    generated_patients = generated["resources"][0]
    generated_sex = next(field for field in generated_patients["schema"]["fields"] if field["name"] == "sex")
    assert generated_sex["x-categories"] == [{"value": "syn;|sex", "count": 1}]
    generated_links = next(item for item in generated["resources"] if item["name"] == "visits_augmented")
    assert generated_links["x-logicalForeignKeys"][0]["orphanRows"] == 1
    visit_field = next(field for field in generated_links["schema"]["fields"] if field["name"] == "visit_id")
    assert visit_field["x-uniqueValueCount"] == 1


def test_truncated_and_overwide_rows_fail_validation(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    _empty_package(tmp_path, descriptor)
    patients = next(item for item in descriptor["resources"] if item["name"] == "patients")
    fields = [field["name"] for field in patients["schema"]["fields"]]
    (tmp_path / "patients.csv").write_text(
        ",".join(fields) + "\n" + "syn-a,U\n" + ",".join(["syn-b", "U"] + [""] * len(fields)) + "\n",
        encoding="utf-8",
    )
    report = validate_structure(tmp_path, descriptor)
    assert any("patients row 2: column count mismatch" in error for error in report.errors)
    assert any("patients row 3: column count mismatch" in error for error in report.errors)
