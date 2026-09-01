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


def _command(
    output: Path,
    *,
    profile: str | None = None,
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
    for resource_name in ("patients_augmented", "visits_augmented"):
        resource_path = next(
            resource["path"] for resource in descriptor["resources"] if resource["name"] == resource_name
        )
        with (output / resource_path).open(encoding="utf-8", newline="") as handle:
            assert next(csv.reader(handle)) == list(field_names(descriptor, resource_name))
    published = b"".join(path.read_bytes() for path in sorted(output.iterdir()) if path.is_file())
    assert b"latent" not in published.lower()
    assert b"truth" not in published.lower()


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
