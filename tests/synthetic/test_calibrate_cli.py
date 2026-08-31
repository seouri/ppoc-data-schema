from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.synthetic.calibration_fixtures import write_mock_snapshot

ROOT = Path(__file__).resolve().parents[2]


def _write_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    partition_policy = tmp_path / "partition-policy.json"
    partition_policy.write_text(
        json.dumps(
            {
                "policy_id": "partition-v1",
                "policy_version": "1",
                "key_id": "key-2026",
                "calibration_basis_points": 5000,
                "minimum_partition_patients": 2,
            }
        ),
        encoding="utf-8",
    )
    disclosure_policy = tmp_path / "disclosure-policy.json"
    disclosure_policy.write_text(
        json.dumps(
            {
                "policy_id": "disclosure-v1",
                "policy_version": "1",
                "minimum_cell_count": 2,
                "continuous_rounding_decimals": 3,
            }
        ),
        encoding="utf-8",
    )
    key_file = tmp_path / "partition.key"
    key_file.write_bytes(b"0123456789abcdef")
    return partition_policy, disclosure_policy, key_file


def _command(tmp_path: Path, output: Path) -> list[str]:
    partition_policy, disclosure_policy, key_file = _write_inputs(tmp_path)
    return [
        sys.executable,
        "-m",
        "synthetic.calibrate",
        "--data-root",
        str(write_mock_snapshot(tmp_path / "snapshot")),
        "--descriptor",
        str(ROOT / "datapackage.json"),
        "--snapshot",
        "synthetic-v1",
        "--artifact-id",
        "calibration-v1",
        "--created-at",
        "2026-08-31T12:00:00Z",
        "--partition-policy",
        str(partition_policy),
        "--disclosure-policy",
        str(disclosure_policy),
        "--partition-key-file",
        str(key_file),
        "--output",
        str(output),
    ]


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)


def test_cli_requires_all_governed_inputs_and_writes_only_aggregate_outputs(tmp_path: Path) -> None:
    output = tmp_path / "output"

    completed = _run(_command(tmp_path, output))

    assert completed.returncode == 0, completed.stderr
    assert sorted(path.name for path in output.iterdir()) == [
        "calibration-artifact.json",
        "calibration-report.json",
    ]


def test_cli_refuses_existing_output_without_overwriting(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    sentinel = output / "calibration-artifact.json"
    sentinel.write_text("keep\n", encoding="utf-8")

    completed = _run(_command(tmp_path, output))

    assert completed.returncode != 0
    assert sentinel.read_text(encoding="utf-8") == "keep\n"


@pytest.mark.parametrize("missing", ["--snapshot", "--partition-key-file"])
def test_cli_rejects_missing_required_flag(tmp_path: Path, missing: str) -> None:
    command = _command(tmp_path, tmp_path / "output")
    index = command.index(missing)
    del command[index : index + 2]

    completed = _run(command)

    assert completed.returncode == 2
    assert not (tmp_path / "output").exists()


def test_cli_rejects_missing_or_symlink_partition_key(tmp_path: Path) -> None:
    command = _command(tmp_path, tmp_path / "output")
    key_index = command.index("--partition-key-file") + 1
    key_path = Path(command[key_index])
    key_path.unlink()
    key_path.symlink_to(tmp_path / "missing-key")

    completed = _run(command)

    assert completed.returncode != 0
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("policy_flag", ["--partition-policy", "--disclosure-policy"])
def test_cli_rejects_duplicate_policy_keys(tmp_path: Path, policy_flag: str) -> None:
    command = _command(tmp_path, tmp_path / "output")
    policy_path = Path(command[command.index(policy_flag) + 1])
    policy_path.write_text('{"policy_id":"one","policy_id":"two"}\n', encoding="utf-8")

    completed = _run(command)

    assert completed.returncode != 0
    assert not (tmp_path / "output").exists()


def test_cli_malformed_snapshot_leaves_no_promoted_output_and_reports_no_source_detail(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    command = _command(tmp_path, output)
    data_root = Path(command[command.index("--data-root") + 1])
    (data_root / "patients.csv").write_text("wrong,header\n", encoding="utf-8")

    completed = _run(command)

    assert completed.returncode != 0
    assert not output.exists()
    assert str(data_root) not in completed.stderr
    assert "SYN-P-" not in completed.stderr


def test_cli_rejects_undeclared_real_data_alias(tmp_path: Path) -> None:
    command = _command(tmp_path, tmp_path / "output")
    command.extend(["--real-data", str(tmp_path / "snapshot")])

    completed = _run(command)

    assert completed.returncode == 2
    assert not (tmp_path / "output").exists()
