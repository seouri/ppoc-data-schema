from __future__ import annotations

import json
from pathlib import Path

import pytest

from synthetic import calibrate as calibrate_module
from synthetic.calibrate import (
    DEFAULT_AGE_WINDOWS,
    CalibrationRunConfig,
    PartitionPolicy,
    calibrate,
    write_calibration_result,
)
from synthetic.calibration import CalibrationArtifact, CalibrationDisclosurePolicy
from tests.synthetic.calibration_fixtures import write_mock_snapshot

ROOT = Path(__file__).resolve().parents[2]


def _test_config(root: Path) -> CalibrationRunConfig:
    return CalibrationRunConfig(
        data_root=root,
        source_descriptor=ROOT / "datapackage.json",
        source_snapshot="synthetic-v1",
        artifact_id="calibration-v1",
        created_at="2026-08-31T12:00:00Z",
        partition_policy=PartitionPolicy("partition-v1", "1", "key-2026", 5_000, 2),
        disclosure_policy=CalibrationDisclosurePolicy("disclosure-v1", "1", 2, 3),
        partition_key=b"0123456789abcdef",
        age_windows=DEFAULT_AGE_WINDOWS,
    )


def test_calibrate_is_deterministic_valid_and_aggregate_only(tmp_path: Path) -> None:
    root = write_mock_snapshot(tmp_path / "snapshot")

    first = calibrate(_test_config(root))
    second = calibrate(_test_config(root))

    assert min(first.report.partition_counts.values()) >= 2
    assert CalibrationArtifact.from_mapping(first.artifact.to_mapping()) == first.artifact
    assert first.report.status == "AGGREGATES_ONLY"
    assert first.artifact.source_aggregate_sha256 == first.report.source_aggregate_sha256
    assert first.artifact.canonical_json() == second.artifact.canonical_json()
    assert first.report.to_json_bytes() == second.report.to_json_bytes()
    serialized = first.artifact.canonical_json() + first.report.canonical_json()
    assert "SYN-P-" not in serialized
    assert str(root) not in serialized
    assert _test_config(root).partition_key.hex() not in serialized


def test_write_calibration_result_promotes_only_two_reparsed_files(tmp_path: Path) -> None:
    result = calibrate(_test_config(write_mock_snapshot(tmp_path / "snapshot")))
    output = tmp_path / "calibration"

    write_calibration_result(result, output)

    assert sorted(path.name for path in output.iterdir()) == [
        "calibration-artifact.json",
        "calibration-report.json",
    ]
    artifact_mapping = json.loads((output / "calibration-artifact.json").read_bytes())
    assert CalibrationArtifact.from_mapping(artifact_mapping) == result.artifact
    assert json.loads((output / "calibration-report.json").read_bytes()) == result.report.to_mapping()


@pytest.mark.parametrize("kind", ["directory", "file", "symlink"])
def test_write_calibration_result_refuses_every_existing_output_kind(
    tmp_path: Path, kind: str
) -> None:
    result = calibrate(_test_config(write_mock_snapshot(tmp_path / "snapshot")))
    output = tmp_path / "calibration"
    if kind == "directory":
        output.mkdir()
        (output / "calibration-artifact.json").write_text("keep\n", encoding="utf-8")
    elif kind == "file":
        output.write_text("keep\n", encoding="utf-8")
    else:
        output.symlink_to(tmp_path / "missing-target")

    with pytest.raises(FileExistsError):
        write_calibration_result(result, output)

    if kind == "directory":
        assert (output / "calibration-artifact.json").read_text(encoding="utf-8") == "keep\n"
    elif kind == "file":
        assert output.read_text(encoding="utf-8") == "keep\n"
    else:
        assert output.is_symlink()


def test_write_failure_archives_only_aggregate_reason_without_promoting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = calibrate(_test_config(write_mock_snapshot(tmp_path / "snapshot")))
    output = tmp_path / "calibration"
    monkeypatch.setattr(calibrate_module.os, "fsync", lambda _descriptor: (_ for _ in ()).throw(OSError("raw detail")))

    with pytest.raises(ValueError, match="could not be promoted"):
        write_calibration_result(result, output)

    assert not output.exists()
    failed = tmp_path / ".calibration.calibration-v1.failed"
    failure = json.loads((failed / "failure.json").read_text(encoding="utf-8"))
    assert failure == {"status": "FAILED", "reason": "calibration output validation failed"}
    assert "raw detail" not in (failed / "failure.json").read_text(encoding="utf-8")
