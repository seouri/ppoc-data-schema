"""Closure checks for the source-matched growth augmenter."""

import csv
import hashlib
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CDC_REFERENCE_NAMES = {
    "statage_combined.csv",
    "wtage_combined.csv",
    "bmiagerev.csv",
    "hcageinf.csv",
    "wtstat.csv",
    "wtleninf.csv",
    "hvage_no_pub.csv",
    "hvage_earlier_pub.csv",
    "hvage_average_pub.csv",
    "hvage_later_pub.csv",
}
EXPECTED_RUNTIME_PATHS = {
    "scripts/__init__.py",
    "scripts/augment.py",
    "scripts/harrall_outliers.py",
    *(f"data/{name}" for name in CDC_REFERENCE_NAMES),
    "data/icd10cm-tabular-2026.csv",
}
EXPECTED_CDC_KEYS = {
    "height_for_age",
    "weight_for_age",
    "bmi_for_age",
    "head_circ_for_age",
    "weight_for_stature",
    "weight_for_length",
    "hvage_no_pub",
    "hvage_earlier_pub",
    "hvage_average_pub",
    "hvage_later_pub",
}


def _descriptor_fields(name: str) -> list[str]:
    descriptor = json.loads((ROOT / "datapackage.json").read_text())
    resource = next(resource for resource in descriptor["resources"] if resource["name"] == name)
    return [field["name"] for field in resource["schema"]["fields"]]


def _write_csv(path: Path, fields: list[str], row: dict[str, object]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in fields})


def test_runtime_manifest_covers_exact_source_matched_closure() -> None:
    """Detect a missing, altered, or accidentally broadened runtime import."""
    manifest = json.loads((DATA_DIR / "augment-runtime-manifest.json").read_text())
    entries = manifest["files"]

    assert {entry["path"] for entry in entries} == EXPECTED_RUNTIME_PATHS
    for entry in entries:
        relative_path = Path(entry["path"])
        assert not relative_path.is_absolute()
        path = ROOT / relative_path
        assert path.is_file()
        assert path.stat().st_size == entry["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
        assert entry["sha256"] == entry["sha256"].lower()


def test_reference_headers_and_imported_cdc_data_match_runtime_contract(monkeypatch) -> None:
    """Detect reference tables or import setup that cannot support augmentation."""
    for name in CDC_REFERENCE_NAMES:
        with (DATA_DIR / name).open(encoding="utf-8-sig", newline="") as stream:
            header = next(csv.reader(stream))
        assert {"Sex", "L", "M", "S"}.issubset(header)

    with (DATA_DIR / "icd10cm-tabular-2026.csv").open(newline="") as stream:
        icd10_header = next(csv.reader(stream))
    assert {"diag_name", "chronic"}.issubset(icd10_header)

    monkeypatch.chdir(ROOT)
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    sys.modules.pop("scripts.augment", None)
    augmenter = importlib.import_module("scripts.augment")
    assert set(augmenter.cdc_data) == EXPECTED_CDC_KEYS


def test_augmentation_preserves_descriptor_output_headers_for_synthetic_input(tmp_path, monkeypatch) -> None:
    """Detect an augmenter output that no longer satisfies the package schemas."""
    visits_fields = _descriptor_fields("visits")
    patients_fields = _descriptor_fields("patients")
    problem_list_fields = _descriptor_fields("problem_list")

    _write_csv(
        tmp_path / "visits.csv",
        visits_fields,
        {
            "patient_id": "synthetic-patient-001",
            "visit_id": "synthetic-visit-001",
            "age_in_days": 365,
            "encounter_type": "synthetic",
            "orig_enc_source_Epic_yn": "N",
            "weight_oz": 352.74,
            "height_in": 29.5,
            "head_circ_cm": 46.0,
            "BMI": 16.0,
            "bmi_percentile": 50.0,
        },
    )
    _write_csv(
        tmp_path / "patients.csv",
        patients_fields,
        {
            "patient_id": "synthetic-patient-001",
            "sex": "F",
            "ethnicity": "Synthetic",
            "race_1": "Synthetic",
        },
    )
    _write_csv(
        tmp_path / "problem_list.csv",
        problem_list_fields,
        {"patient_id": "synthetic-patient-001", "problem_list_id": "synthetic-problem-001"},
    )

    monkeypatch.chdir(ROOT)
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    sys.modules.pop("scripts.augment", None)
    augmenter = importlib.import_module("scripts.augment")
    visits = augmenter.augment_visits(str(tmp_path))
    patients = augmenter.augment_patients(str(tmp_path), visits)

    assert visits.columns.tolist() == _descriptor_fields("visits_augmented")
    assert patients.columns.tolist() == _descriptor_fields("patients_augmented")
