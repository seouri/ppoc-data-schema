from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import pytest

from synthetic.augmenter_oracle import AUGMENTER_RUNTIME_MANIFEST_SHA256
from synthetic.cdc_reference import CdcGrowthReference
from synthetic.generate import CLI_UNAVAILABLE_MESSAGE
from synthetic.schema_contract import (
    EXPECTED_SCHEMA_FINGERPRINT,
    field_names,
    load_descriptor,
    schema_fingerprint,
)
from synthetic.validate import validate_structure

ROOT = Path(__file__).resolve().parents[2]
_REDACTED_FAILURE = "Synthetic development generation unavailable"
_SCALE_ENABLED = os.environ.get("SYNTHETIC_RUN_SCALE") == "1"
_SCALE_PATIENT_COUNT = 10_000
_SCALE_VISIT_COUNT = 110_000
_SCALE_AGES = (
    0,
    365,
    730,
    1460,
    2190,
    3650,
    4380,
    5114,
    5475,
    6200,
    7305,
)
_SCALE_ROW_COUNTS = {
    "patients": _SCALE_PATIENT_COUNT,
    "patients_augmented": _SCALE_PATIENT_COUNT,
    "visits": _SCALE_VISIT_COUNT,
    "visits_augmented": _SCALE_VISIT_COUNT,
    "labs": 0,
    "medications": 0,
    "problem_list": 0,
    "referrals": 0,
}
_REALISTIC_SCALE_MIN_GROWTH_DX = 1_000
_REALISTIC_SCALE_MAX_GROWTH_DX = 2_000


def _command(
    output: Path,
    *,
    profile: str | None = None,
    descriptor: Path | None = None,
    reference_time: str | None = None,
    software_revision: str | None = None,
    patient_count: int = 3,
    seed: int = 20260901,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "synthetic.generate",
        "--output",
        str(output),
        "--patients",
        str(patient_count),
        "--seed",
        str(seed),
    ]
    if profile is not None:
        command.extend(["--profile", profile])
    if descriptor is not None:
        command.extend(["--descriptor", str(descriptor)])
    if reference_time is not None:
        command.extend(["--reference-time", reference_time])
    if software_revision is not None:
        command.extend(["--software-revision", software_revision])
    return command


def _run(command: list[str], *, env: dict[str, str] | None = None, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False, env=env)


def _non_manifest_hashes(root: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.iterdir())
        if path.is_file() and path.name != "manifest.json"
    }


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _resource_path(descriptor: dict[str, object], name: str) -> str:
    for resource in descriptor["resources"]:
        assert isinstance(resource, dict)
        if resource["name"] == name:
            path = resource["path"]
            assert isinstance(path, str)
            return path
    raise AssertionError(f"descriptor is missing resource {name}")


def _assert_max_decimal_places(rows: list[dict[str, str]], field: str, places: int) -> None:
    for row in rows:
        value = row[field]
        if not value:
            continue
        fraction = value.partition(".")[2]
        assert fraction.isdigit(), (field, value)
        assert len(fraction) <= places, (field, value, places)


def _assert_valid_encounter_diagnoses(rows: list[dict[str, str]]) -> None:
    with (ROOT / "data" / "icd10cm-tabular-2026.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        valid_codes = {row["diag_name"] for row in csv.DictReader(stream)}
    diagnoses = [
        value
        for row in rows
        for field_name, value in row.items()
        if field_name.startswith("enc_diag_") and value
    ]
    assert set(diagnoses) <= valid_codes


def test_no_profile_remains_fail_closed(tmp_path: Path) -> None:
    """Catches a CLI fallback that enables a reference without explicit opt-in."""
    output = tmp_path / "no-profile"

    result = _run(_command(output))

    assert result.returncode != 0
    assert result.stderr.strip().endswith(CLI_UNAVAILABLE_MESSAGE)
    assert not output.exists()


def test_unknown_profile_remains_fail_closed(tmp_path: Path) -> None:
    """Catches an unrecognized profile reaching runtime or filesystem checks."""
    output = tmp_path / "unknown-profile"

    result = _run(_command(output, profile="unknown"))

    assert result.returncode != 0
    assert result.stderr.strip().endswith(CLI_UNAVAILABLE_MESSAGE)
    assert not output.exists()


def test_development_smoke_cli_exports_exact_visible_package(tmp_path: Path) -> None:
    """Catches CLI dispatch that bypasses the pinned runtime or exact exporter."""
    output = tmp_path / "development-smoke"

    result = _run(_command(output, profile="development-smoke"))

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    descriptor = load_descriptor(ROOT / "datapackage.json")
    expected_resources = {resource["path"] for resource in descriptor["resources"]}
    assert {path.name for path in output.glob("*.csv")} == expected_resources
    assert len(expected_resources) == 8
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["profile"] == "development-smoke"
    assert manifest["reference_id"] == "cdc-lms-reference-v1"
    assert manifest["reference_sha256"] == CdcGrowthReference.from_repository(ROOT).source_sha256
    assert manifest["derivation_fingerprint"] == AUGMENTER_RUNTIME_MANIFEST_SHA256
    assert manifest["status"] == "STRUCTURE_VALIDATED_TEST_ORACLE"
    assert not validate_structure(output, descriptor).errors
    generated_descriptor = load_descriptor(output / "datapackage.json")
    assert "x-projectGovernance" not in generated_descriptor
    assert "x-statisticsSource" not in generated_descriptor
    for resource_name in ("patients_augmented", "visits_augmented"):
        resource_path = next(
            resource["path"] for resource in descriptor["resources"] if resource["name"] == resource_name
        )
        with (output / resource_path).open(encoding="utf-8", newline="") as handle:
            assert next(csv.reader(handle)) == list(field_names(descriptor, resource_name))
    published = b"".join(path.read_bytes() for path in sorted(output.iterdir()) if path.is_file())
    assert b"latent" not in published.lower()
    assert b"truth" not in published.lower()


def test_development_smoke_cli_forwards_descriptor_and_metadata_options(tmp_path: Path) -> None:
    """Catches subprocess helper or CLI forwarding that drops optional generation metadata."""
    output = tmp_path / "forwarded-options"
    runtime_root = tmp_path / "fictional-runtime"
    shutil.copytree(ROOT / "src", runtime_root / "src")
    shutil.copytree(ROOT / "data", runtime_root / "data")
    shutil.copytree(ROOT / "scripts", runtime_root / "scripts")
    shutil.copy2(ROOT / "uv.lock", runtime_root / "uv.lock")
    descriptor = runtime_root / "fictional-descriptor.json"
    shutil.copy2(ROOT / "datapackage.json", descriptor)
    environment = os.environ | {"PYTHONPATH": str(runtime_root / "src")}

    result = _run(
        _command(
            output,
            profile="development-smoke",
            descriptor=descriptor,
            reference_time="2099-12-31T23:59:59Z",
            software_revision="fictional-forwarding-v1",
        ),
        env=environment,
        cwd=runtime_root,
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    expected_descriptor = load_descriptor(ROOT / "datapackage.json")
    expected_resources = {resource["path"] for resource in expected_descriptor["resources"]}
    assert {path.name for path in output.glob("*.csv")} == expected_resources
    assert len(expected_resources) == 8
    assert not validate_structure(output, expected_descriptor).errors
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["profile"] == "development-smoke"
    assert manifest["status"] == "STRUCTURE_VALIDATED_TEST_ORACLE"
    assert manifest["reference_time"] == "2099-12-31T23:59:59Z"
    assert manifest["software_revision"] == "fictional-forwarding-v1"


def test_development_cohort_cli_exports_exact_visible_package(tmp_path: Path) -> None:
    """Catches the cohort CLI route bypassing the fixed native profile or exact exporter."""
    output = tmp_path / "development-cohort"

    result = _run(_command(output, profile="development-cohort"))

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    descriptor = load_descriptor(ROOT / "datapackage.json")
    expected_resources = {resource["path"] for resource in descriptor["resources"]}
    assert {path.name for path in output.glob("*.csv")} == expected_resources
    assert len(expected_resources) == 8
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["profile"] == "development-cohort"
    assert manifest["reference_id"] == "cdc-lms-reference-v1"
    assert manifest["reference_sha256"] == CdcGrowthReference.from_repository(ROOT).source_sha256
    assert manifest["derivation_fingerprint"] == AUGMENTER_RUNTIME_MANIFEST_SHA256
    assert manifest["test_only_derivation"] is True
    assert manifest["status"] == "STRUCTURE_VALIDATED_TEST_ORACLE"
    assert not validate_structure(output, descriptor).errors
    published = b"".join(path.read_bytes() for path in sorted(output.iterdir()) if path.is_file())
    for forbidden in (b"latent", b"severity", b"truth", b"growth_hormone_deficiency"):
        assert forbidden not in published.lower()


def test_development_realistic_cli_exports_target_shaped_package(tmp_path: Path) -> None:
    """Catches the opt-in target-shaped profile bypassing exact-schema export."""
    output = tmp_path / "development-realistic"

    result = _run(_command(output, profile="development-realistic", patient_count=128))

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    descriptor = load_descriptor(ROOT / "datapackage.json")
    expected_resources = {resource["path"] for resource in descriptor["resources"]}
    assert {path.name for path in output.glob("*.csv")} == expected_resources
    assert len(expected_resources) == 8
    assert not validate_structure(output, descriptor).errors
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["profile"] == "development-realistic"
    assert manifest["reference_id"] == "cdc-lms-reference-v1"
    assert manifest["reference_sha256"] == CdcGrowthReference.from_repository(ROOT).source_sha256
    assert manifest["derivation_fingerprint"] == AUGMENTER_RUNTIME_MANIFEST_SHA256
    assert manifest["test_only_derivation"] is True
    assert manifest["status"] == "STRUCTURE_VALIDATED_TEST_ORACLE"
    visits_path = _resource_path(descriptor, "visits")
    for resource_name, bmi_field in (("visits", "BMI"), ("visits_augmented", "bmi")):
        visits = _csv_rows(output / _resource_path(descriptor, resource_name))
        _assert_valid_encounter_diagnoses(visits)
        _assert_max_decimal_places(visits, "weight_oz", 2)
        _assert_max_decimal_places(visits, "height_in", 2)
        _assert_max_decimal_places(visits, "head_circ_cm", 1)
        _assert_max_decimal_places(visits, bmi_field, 2)
    for resource_name in ("patients", "patients_augmented"):
        patients = _csv_rows(output / _resource_path(descriptor, resource_name))
        if resource_name == "patients":
            assert all(row["race_1"] for row in patients)
        assert all(
            row[f"race_{index}"] == ""
            for row in patients
            for index in range(3, 9)
        )
        assert sum(row["race_2"] == "" for row in patients) >= 0.85 * len(patients)
    diagnosis_codes = [
        value
        for row in _csv_rows(output / visits_path)
        for field_name, value in row.items()
        if field_name.startswith("enc_diag_") and value
    ]
    assert {code: diagnosis_codes.count(code) for code in set(diagnosis_codes)} == {
        "R62.52": 20,
        "R62.50": 20,
        "R62.59": 20,
        "E23.0": 20,
    }
    augmented_path = _resource_path(descriptor, "patients_augmented")
    augmented_patients = _csv_rows(output / augmented_path)
    assert sum(int(row["growth_dx_flag"]) for row in augmented_patients) == 20
    labs = _csv_rows(output / _resource_path(descriptor, "labs"))
    assert len(labs) == 40
    assert {row["result_flag"] for row in labs} == {""}
    assert len(_csv_rows(output / _resource_path(descriptor, "problem_list"))) == 20
    assert len(_csv_rows(output / _resource_path(descriptor, "referrals"))) == 20
    published = b"".join(path.read_bytes() for path in sorted(output.iterdir()) if path.is_file())
    for forbidden in (b"latent", b"severity", b"truth", b"growth_hormone_deficiency"):
        assert forbidden not in published.lower()


def test_development_all_disorders_cli_exports_every_visible_pathway(tmp_path: Path) -> None:
    """Catches the all-disorder route dropping a module, sidecar, or exact-schema boundary."""
    output = tmp_path / "development-all-disorders"

    result = _run(
        _command(
            output,
            profile="development-all-disorders",
            patient_count=512,
            seed=20260903,
        )
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    descriptor = load_descriptor(ROOT / "datapackage.json")
    generated_descriptor = load_descriptor(output / "datapackage.json")
    assert tuple(resource["name"] for resource in generated_descriptor["resources"]) == (
        "patients",
        "patients_augmented",
        "visits",
        "visits_augmented",
        "labs",
        "medications",
        "problem_list",
        "referrals",
    )
    assert schema_fingerprint(generated_descriptor) == EXPECTED_SCHEMA_FINGERPRINT
    assert {path.name for path in output.glob("*.csv")} == {
        resource["path"] for resource in descriptor["resources"]
    }
    assert not validate_structure(output, descriptor).errors

    patients = _csv_rows(output / _resource_path(descriptor, "patients"))
    visits = _csv_rows(output / _resource_path(descriptor, "visits"))
    _assert_valid_encounter_diagnoses(visits)
    patient_ids = [row["patient_id"] for row in patients]
    visit_ids = [row["visit_id"] for row in visits]
    assert len(patient_ids) == len(set(patient_ids)) == 512
    assert len(visit_ids) == len(set(visit_ids))
    assert all(value.startswith("syn-") for value in (*patient_ids, *visit_ids))

    diagnosis_codes = [
        value
        for row in visits
        for field_name, value in row.items()
        if field_name.startswith("enc_diag_") and value
    ]
    for code in ("R62.52", "R62.50", "R62.59"):
        assert code in diagnosis_codes

    labs = _csv_rows(output / _resource_path(descriptor, "labs"))
    medications = _csv_rows(output / _resource_path(descriptor, "medications"))
    problem_list = _csv_rows(output / _resource_path(descriptor, "problem_list"))
    referrals = _csv_rows(output / _resource_path(descriptor, "referrals"))
    assert labs and medications and problem_list and referrals
    assert {row["result_flag"] for row in labs} == {""}
    expected_pathways = {
        "SYN-GHD": (
            {"SYN-GHD-IGF1", "SYN-GHD-STIM"},
            "Synthetic Pediatric Endocrinology",
            {"Synthetic growth hormone"},
        ),
        "SYN-PEDIATRIC-HYPOTHYROIDISM": (
            {"SYN-HYPOTHYROIDISM-TSH", "SYN-HYPOTHYROIDISM-FREE-T4"},
            "Synthetic Pediatric Endocrinology",
            {"Synthetic levothyroxine"},
        ),
        "SYN-CELIAC-DISEASE": (
            {"SYN-CELIAC-TTG-IGA", "SYN-CELIAC-TOTAL-IGA"},
            "Synthetic Pediatric Gastroenterology",
            {"Synthetic gluten-free intervention"},
        ),
        "SYN-SGA": (
            {"SYN-SGA-GESTATIONAL-AGE", "SYN-SGA-BIRTH-SIZE"},
            "Synthetic Neonatology Follow-up",
            set(),
        ),
        "SYN-TURNER-SYNDROME": (
            {"SYN-TURNER-KARYOTYPE", "SYN-TURNER-ENDOCRINE-EVIDENCE"},
            "Synthetic Pediatric Endocrinology",
            set(),
        ),
        "SYN-UNDERNUTRITION": (
            {
                "SYN-UNDERNUTRITION-WEIGHT-EVIDENCE",
                "SYN-UNDERNUTRITION-HEIGHT-EVIDENCE",
            },
            "Synthetic Pediatric Nutrition",
            {"Synthetic nutrition-supplement intervention"},
        ),
        "SYN-EXCESS-WEIGHT": (
            {"SYN-EXCESS-WEIGHT-LIPID", "SYN-EXCESS-WEIGHT-A1C"},
            "Synthetic Pediatric Nutrition",
            set(),
        ),
    }
    assert {row["pl_diag"] for row in problem_list} == set(expected_pathways)

    diagnosis_by_patient = {row["patient_id"]: row["pl_diag"] for row in problem_list}
    assert len(diagnosis_by_patient) == len(problem_list)
    ancillary_rows = (*labs, *medications, *referrals)
    assert all(row["patient_id"] in diagnosis_by_patient for row in ancillary_rows)

    visit_patient_by_id = {row["visit_id"]: row["patient_id"] for row in visits}
    for row in ancillary_rows:
        if visit_id := row.get("visit_id"):
            assert visit_patient_by_id.get(visit_id) == row["patient_id"]

    for diagnosis_code, (components, specialty, medication_names) in expected_pathways.items():
        pathway_patient_ids = {
            patient_id
            for patient_id, patient_diagnosis in diagnosis_by_patient.items()
            if patient_diagnosis == diagnosis_code
        }
        pathway_labs = [row for row in labs if row["patient_id"] in pathway_patient_ids]
        pathway_referrals = [
            row for row in referrals if row["patient_id"] in pathway_patient_ids
        ]
        pathway_medications = [
            row for row in medications if row["patient_id"] in pathway_patient_ids
        ]

        labs_by_patient: defaultdict[str, set[str]] = defaultdict(set)
        for row in pathway_labs:
            labs_by_patient[row["patient_id"]].add(row["result_component_name"])
        assert set(labs_by_patient) == pathway_patient_ids
        assert all(
            patient_components == components
            for patient_components in labs_by_patient.values()
        )
        assert len(pathway_labs) == 2 * len(pathway_patient_ids)

        assert {row["patient_id"] for row in pathway_referrals} == pathway_patient_ids
        assert {row["requested_specialty"] for row in pathway_referrals} == {specialty}
        assert len(pathway_referrals) == len(pathway_patient_ids)

        assert {
            row["med_simple_generic_name"] for row in pathway_medications
        } == medication_names
        assert len(pathway_medications) == len(
            {row["patient_id"] for row in pathway_medications}
        )

    ghd_patient_ids = {
        row["patient_id"] for row in problem_list if row["pl_diag"] == "SYN-GHD"
    }
    e23_patient_ids = {
        row["patient_id"]
        for row in visits
        if "E23.0" in {
            value for field_name, value in row.items() if field_name.startswith("enc_diag_")
        }
    }
    augmented = _csv_rows(output / _resource_path(descriptor, "patients_augmented"))
    flagged_patient_ids = {
        row["patient_id"] for row in augmented if row["growth_dx_flag"] == "1"
    }
    assert e23_patient_ids == ghd_patient_ids == flagged_patient_ids

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["profile"] == "development-all-disorders"
    assert manifest["schema_fingerprint"] == EXPECTED_SCHEMA_FINGERPRINT
    assert manifest["reference_id"] == "cdc-lms-reference-v1"
    assert manifest["reference_sha256"] == CdcGrowthReference.from_repository(ROOT).source_sha256
    assert manifest["derivation_fingerprint"] == AUGMENTER_RUNTIME_MANIFEST_SHA256
    assert manifest["test_only_derivation"] is True
    assert manifest["status"] == "STRUCTURE_VALIDATED_TEST_ORACLE"
    for artifact in output.rglob("*"):
        if artifact.is_file():
            published = artifact.read_bytes().lower()
            for forbidden in (b"latent", b"severity", b"truth", b"turner_syndrome"):
                assert forbidden not in published


@pytest.mark.scale
@pytest.mark.skipif(
    not _SCALE_ENABLED,
    reason="set SYNTHETIC_RUN_SCALE=1 to run the development CLI composition scale profile",
)
def test_development_all_disorders_cli_scale_profile_exports_visible_exact_schema(
    tmp_path: Path,
) -> None:
    """Catches the explicit all-disorder CLI route failing at the scheduled scale."""
    output = tmp_path / "development-all-disorders-scale"

    result = _run(
        _command(
            output,
            profile="development-all-disorders",
            patient_count=_SCALE_PATIENT_COUNT,
            seed=20260903,
        )
    )

    assert result.returncode == 0, result.stderr
    descriptor = load_descriptor(ROOT / "datapackage.json")
    generated_descriptor = load_descriptor(output / "datapackage.json")
    assert schema_fingerprint(generated_descriptor) == EXPECTED_SCHEMA_FINGERPRINT
    assert not validate_structure(output, descriptor).errors
    assert len(_csv_rows(output / _resource_path(descriptor, "patients"))) == 10_000
    assert json.loads((output / "manifest.json").read_text(encoding="utf-8"))[
        "profile"
    ] == "development-all-disorders"


@pytest.mark.scale
@pytest.mark.skipif(
    not _SCALE_ENABLED,
    reason="set SYNTHETIC_RUN_SCALE=1 to run the development CLI composition scale profile",
)
def test_development_cohort_cli_scale_profile_exports_visible_exact_schema(
    tmp_path: Path,
) -> None:
    """Catches public CLI composition that cannot sustain the fixed 10,000-member profile."""
    output = tmp_path / "development-cohort-scale"

    result = _run(
        _command(
            output,
            profile="development-cohort",
            patient_count=_SCALE_PATIENT_COUNT,
        )
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    descriptor = load_descriptor(ROOT / "datapackage.json")
    generated_descriptor = load_descriptor(output / "datapackage.json")
    assert tuple(resource["name"] for resource in generated_descriptor["resources"]) == (
        "patients",
        "patients_augmented",
        "visits",
        "visits_augmented",
        "labs",
        "medications",
        "problem_list",
        "referrals",
    )
    assert tuple(resource["path"] for resource in generated_descriptor["resources"]) == tuple(
        resource["path"] for resource in descriptor["resources"]
    )
    assert schema_fingerprint(generated_descriptor) == EXPECTED_SCHEMA_FINGERPRINT
    assert {
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file()
    } == {
        *(
            resource["path"]
            for resource in descriptor["resources"]
            if isinstance(resource["path"], str)
        ),
        "datapackage.json",
        "manifest.json",
        "validation-report.json",
    }
    assert not validate_structure(output, descriptor).errors

    patients = _csv_rows(output / _resource_path(descriptor, "patients"))
    visits = _csv_rows(output / _resource_path(descriptor, "visits"))
    assert len(patients) == _SCALE_PATIENT_COUNT
    assert len(visits) == _SCALE_VISIT_COUNT
    patient_ids = [row["patient_id"] for row in patients]
    visit_ids = [row["visit_id"] for row in visits]
    assert len(patient_ids) == len(set(patient_ids)) == _SCALE_PATIENT_COUNT
    assert len(visit_ids) == len(set(visit_ids)) == _SCALE_VISIT_COUNT
    assert all(patient_id.startswith("syn-") for patient_id in patient_ids)
    assert all(visit_id.startswith("syn-") for visit_id in visit_ids)
    ages_by_patient: dict[str, set[int]] = defaultdict(set)
    for row in visits:
        ages_by_patient[row["patient_id"]].add(int(row["age_in_days"]))
    assert set(ages_by_patient) == set(patient_ids)
    assert all(ages == set(_SCALE_AGES) for ages in ages_by_patient.values())

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["profile"] == "development-cohort"
    assert manifest["schema_fingerprint"] == EXPECTED_SCHEMA_FINGERPRINT
    assert manifest["reference_id"] == "cdc-lms-reference-v1"
    assert (
        manifest["reference_sha256"]
        == CdcGrowthReference.from_repository(ROOT).source_sha256
    )
    assert manifest["derivation_fingerprint"] == AUGMENTER_RUNTIME_MANIFEST_SHA256
    assert manifest["test_only_derivation"] is True
    assert manifest["row_counts"] == _SCALE_ROW_COUNTS
    assert manifest["status"] == "STRUCTURE_VALIDATED_TEST_ORACLE"

    for artifact in output.rglob("*"):
        if artifact.is_file():
            published = artifact.read_bytes().lower()
            for forbidden in (
                b"latent",
                b"severity",
                b"truth",
                b"growth_hormone_deficiency",
            ):
                assert forbidden not in published


@pytest.mark.scale
@pytest.mark.skipif(
    not _SCALE_ENABLED,
    reason="set SYNTHETIC_RUN_SCALE=1 to run the development CLI composition scale profile",
)
def test_development_realistic_cli_scale_profile_preserves_target_shaped_descendants(
    tmp_path: Path,
) -> None:
    """Catches target-shaped scale runs that lose typed GHD descendants or schema sentinels."""
    output = tmp_path / "development-realistic-scale"

    result = _run(
        _command(
            output,
            profile="development-realistic",
            patient_count=_SCALE_PATIENT_COUNT,
        )
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    descriptor = load_descriptor(ROOT / "datapackage.json")
    generated_descriptor = load_descriptor(output / "datapackage.json")
    assert schema_fingerprint(generated_descriptor) == EXPECTED_SCHEMA_FINGERPRINT
    assert {
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file()
    } == {
        *(
            resource["path"]
            for resource in descriptor["resources"]
            if isinstance(resource["path"], str)
        ),
        "datapackage.json",
        "manifest.json",
        "validation-report.json",
    }
    assert not validate_structure(output, descriptor).errors

    patients = _csv_rows(output / _resource_path(descriptor, "patients"))
    visits = _csv_rows(output / _resource_path(descriptor, "visits"))
    augmented_patients = _csv_rows(
        output / _resource_path(descriptor, "patients_augmented")
    )
    labs = _csv_rows(output / _resource_path(descriptor, "labs"))
    medications = _csv_rows(output / _resource_path(descriptor, "medications"))
    problems = _csv_rows(output / _resource_path(descriptor, "problem_list"))
    referrals = _csv_rows(output / _resource_path(descriptor, "referrals"))

    assert len(patients) == _SCALE_PATIENT_COUNT
    assert len(visits) == _SCALE_VISIT_COUNT
    assert len(augmented_patients) == _SCALE_PATIENT_COUNT
    assert len(problems) == len(referrals)
    assert len(labs) == 2 * len(problems)
    assert 0 <= len(medications) <= len(problems)
    growth_dx_count = sum(int(row["growth_dx_flag"]) for row in augmented_patients)
    assert growth_dx_count == len(problems)
    assert _REALISTIC_SCALE_MIN_GROWTH_DX <= growth_dx_count <= _REALISTIC_SCALE_MAX_GROWTH_DX
    assert {row["result_flag"] for row in labs} <= {""}

    patient_ids = [row["patient_id"] for row in patients]
    visit_ids = [row["visit_id"] for row in visits]
    assert len(patient_ids) == len(set(patient_ids)) == _SCALE_PATIENT_COUNT
    assert len(visit_ids) == len(set(visit_ids)) == _SCALE_VISIT_COUNT

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["profile"] == "development-realistic"
    assert manifest["schema_fingerprint"] == EXPECTED_SCHEMA_FINGERPRINT
    assert manifest["reference_id"] == "cdc-lms-reference-v1"
    assert manifest["derivation_fingerprint"] == AUGMENTER_RUNTIME_MANIFEST_SHA256
    assert manifest["test_only_derivation"] is True
    assert manifest["row_counts"] == {
        "patients": len(patients),
        "patients_augmented": len(augmented_patients),
        "visits": len(visits),
        "visits_augmented": _SCALE_VISIT_COUNT,
        "labs": len(labs),
        "medications": len(medications),
        "problem_list": len(problems),
        "referrals": len(referrals),
    }

    published = b"".join(
        path.read_bytes() for path in sorted(output.rglob("*")) if path.is_file()
    )
    for forbidden in (
        b"latent",
        b"severity",
        b"truth",
        b"growth_hormone_deficiency",
    ):
        assert forbidden not in published.lower()


def test_development_smoke_cli_is_reproducible_across_distinct_outputs(tmp_path: Path) -> None:
    """Catches CLI generation that depends on the selected output path."""
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_result = _run(_command(first, profile="development-smoke"))
    second_result = _run(_command(second, profile="development-smoke"))

    assert first_result.returncode == 0, first_result.stderr
    assert second_result.returncode == 0, second_result.stderr
    assert _non_manifest_hashes(first) == _non_manifest_hashes(second)


def test_cli_redacts_collision_and_altered_runtime_failures(tmp_path: Path) -> None:
    """Catches CLI errors that disclose output paths or runtime implementation details."""
    collision = tmp_path / "collision"
    collision.mkdir()
    collision_result = _run(_command(collision, profile="development-smoke"))
    assert collision_result.returncode != 0
    assert collision_result.stderr.strip().endswith(_REDACTED_FAILURE)
    assert str(collision) not in collision_result.stderr
    assert "Traceback" not in collision_result.stderr

    altered_root = tmp_path / "altered-runtime"
    shutil.copytree(ROOT / "src", altered_root / "src")
    shutil.copytree(ROOT / "data", altered_root / "data")
    shutil.copy2(ROOT / "datapackage.json", altered_root / "datapackage.json")
    shutil.copy2(ROOT / "uv.lock", altered_root / "uv.lock")
    runtime_file = altered_root / "data" / "augment-runtime-manifest.json"
    runtime_file.write_bytes(runtime_file.read_bytes() + b"\n")
    runtime_output = altered_root / "runtime-output"
    environment = os.environ | {"PYTHONPATH": str(altered_root / "src")}
    runtime_result = _run(
        _command(runtime_output, profile="development-smoke"), env=environment, cwd=altered_root
    )
    assert runtime_result.returncode != 0
    assert runtime_result.stderr.strip().endswith(_REDACTED_FAILURE)
    assert str(altered_root) not in runtime_result.stderr
    assert "Traceback" not in runtime_result.stderr
    assert not runtime_output.exists()
