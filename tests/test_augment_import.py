"""Closure checks for the source-matched growth augmenter."""

import csv
import hashlib
import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

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
def _descriptor_fields(name: str) -> list[str]:
    descriptor = json.loads((ROOT / "datapackage.json").read_text())
    resource = next(resource for resource in descriptor["resources"] if resource["name"] == name)
    return [field["name"] for field in resource["schema"]["fields"]]


def _write_csv(path: Path, fields: list[str], row: dict[str, object]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in fields})


def _assert_manifest_entries_are_regular_files(root: Path, entries: list[dict[str, object]]) -> None:
    for entry in entries:
        relative_path = Path(str(entry["path"]))
        assert not relative_path.is_absolute()
        path = root / relative_path
        assert not path.is_symlink()
        assert stat.S_ISREG(path.lstat().st_mode)
        assert path.stat().st_size == entry["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
        assert entry["sha256"] == entry["sha256"].lower()


def test_runtime_manifest_covers_exact_source_matched_closure() -> None:
    """Detect a missing, altered, or accidentally broadened runtime import."""
    manifest = json.loads((DATA_DIR / "augment-runtime-manifest.json").read_text())
    entries = manifest["files"]

    assert {entry["path"] for entry in entries} == EXPECTED_RUNTIME_PATHS
    _assert_manifest_entries_are_regular_files(ROOT, entries)


def test_manifest_closure_rejects_a_symlinked_target(tmp_path) -> None:
    """Detect a manifest entry that follows a symlink outside its declared closure."""
    target = tmp_path / "reference.csv"
    target.write_text("reference\n")
    linked = tmp_path / "linked.csv"
    linked.symlink_to(target)
    entries = [
        {
            "path": "linked.csv",
            "bytes": target.stat().st_size,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }
    ]

    with pytest.raises(AssertionError):
        _assert_manifest_entries_are_regular_files(tmp_path, entries)


def test_reference_headers_match_runtime_contract() -> None:
    """Detect reference tables that cannot support augmentation."""
    for name in CDC_REFERENCE_NAMES:
        with (DATA_DIR / name).open(encoding="utf-8-sig", newline="") as stream:
            header = next(csv.reader(stream))
        assert {"Sex", "L", "M", "S"}.issubset(header)

    with (DATA_DIR / "icd10cm-tabular-2026.csv").open(newline="") as stream:
        icd10_header = next(csv.reader(stream))
    assert {"diag_name", "chronic"}.issubset(icd10_header)


def test_documentation_describes_synthetic_only_import_boundary() -> None:
    """Keep the runnable guide and the non-authoritative boundary explicit."""
    guide = (ROOT / "docs" / "augment-import.md").read_text()
    readme = (ROOT / "README.md").read_text()
    synthetic_guide = (ROOT / "docs" / "synthetic-generator.md").read_text()
    design = (ROOT / "docs" / "superpowers" / "specs" / "2026-09-01-augment-import-design.md").read_text()
    plan = (ROOT / "docs" / "superpowers" / "plans" / "2026-09-01-augment-import.md").read_text()
    data_readme = (DATA_DIR / "README.md").read_text()

    for required_input in ("visits.csv", "patients.csv", "problem_list.csv"):
        assert required_input in guide
    assert "uv sync" in guide
    documented_command = "uv run python scripts/augment.py fixtures/augment-input --output_dir artifacts/augment-output --output_format csv"
    assert documented_command in guide
    assert "\npython scripts/augment.py fixtures/augment-input" not in guide
    assert "replace `csv` with `parquet`" in guide
    assert "visits_augmented-YYYYMMDDHHMMSS.csv" in guide
    assert "patients_augmented-YYYYMMDDHHMMSS.csv" in guide
    assert "augment-runtime-manifest.json" in guide
    assert "SHA-256" in guide
    assert "Do not point this script at governed data, real patient data" in guide
    assert "not bound as authoritative" in guide
    assert "does not change the native generator, package exporter, calibration, privacy, counterfactual, Synthea, or release gates" in guide

    assert "[synthetic generator guide](docs/synthetic-generator.md)" in readme
    for document in (synthetic_guide,):
        assert "source-matched growth augmenter" in document
        assert "not bound as authoritative" in document
        assert "no production growth reference or authoritative augmentation oracle is shipped" not in document

    for document in (design, plan):
        assert "CLI-only" in document
        assert "importable `scripts.augment`" not in document
        assert "import `scripts.augment`" not in document

    assert "git@github.com:hms-dbmi/growth-ai.git" in data_readme
    assert "cd6abdd313d8ebadcb5c66052857a3bb107419ad" in data_readme
    assert "upstream dataset provenance and redistribution terms were not independently verified" in data_readme.lower()


def test_documented_cli_preserves_descriptor_output_headers_for_synthetic_input(tmp_path) -> None:
    """Detect a documented CLI run that no longer satisfies the package schemas."""
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

    output_dir = tmp_path / "fixed-output"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/augment.py",
            str(tmp_path),
            "--output_dir",
            str(output_dir),
            "--output_format",
            "csv",
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert "Saving" in completed.stdout
    visits_output = next(output_dir.glob("visits_augmented-*.csv"))
    patients_output = next(output_dir.glob("patients_augmented-*.csv"))
    with visits_output.open(newline="") as stream:
        assert next(csv.reader(stream)) == _descriptor_fields("visits_augmented")
    with patients_output.open(newline="") as stream:
        assert next(csv.reader(stream)) == _descriptor_fields("patients_augmented")
