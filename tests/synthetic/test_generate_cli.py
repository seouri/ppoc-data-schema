from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from synthetic.augmenter_oracle import AUGMENTER_RUNTIME_MANIFEST_SHA256
from synthetic.cdc_reference import CdcGrowthReference
from synthetic.generate import CLI_UNAVAILABLE_MESSAGE
from synthetic.schema_contract import field_names, load_descriptor
from synthetic.validate import validate_structure

ROOT = Path(__file__).resolve().parents[2]
_REDACTED_FAILURE = "Synthetic development generation unavailable"


def _command(output: Path, *, profile: str | None = None) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "synthetic.generate",
        "--output",
        str(output),
        "--patients",
        "3",
        "--seed",
        "20260901",
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
