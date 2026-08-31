from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from synthetic.calibrate import (
    DEFAULT_AGE_WINDOWS,
    CalibrationRunConfig,
    PartitionPolicy,
    calibrate,
    write_calibration_result,
)
from synthetic.calibration import CalibrationDisclosurePolicy
from synthetic.calibration_targets import TARGET_REGISTRY_VERSION
from synthetic.schema_contract import load_descriptor, resource_spec
from tests.synthetic.calibration_fixtures import write_mock_snapshot
from tests.synthetic.heldout_fixtures import write_synthetic_package

ROOT = Path(__file__).resolve().parents[2]
PARTITION_KEY = b"0123456789abcdef"


def _write_inputs(tmp_path: Path, *, mode: str = "pass") -> dict[str, Path]:
    minimum = 1_000 if mode == "unevaluable" else 1
    real_root = write_mock_snapshot(tmp_path / "real", id_prefix="REAL")
    synthetic_root = write_synthetic_package(tmp_path / "synthetic", id_prefix="GEN")
    if mode == "fail":
        descriptor = load_descriptor(ROOT / "datapackage.json")
        resource = resource_spec(descriptor, "visits_augmented")
        path = synthetic_root / resource["path"]
        with path.open(encoding=resource["encoding"], newline="") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            if row["height_z_score"]:
                row["height_z_score"] = "100000"
        with path.open("w", encoding=resource["encoding"], newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    partition_policy_mapping = {
        "policy_id": "partition-v1",
        "policy_version": "1",
        "key_id": "key-2026",
        "calibration_basis_points": 5_000,
        "minimum_partition_patients": 2,
    }
    disclosure_policy_mapping = {
        "policy_id": "disclosure-v1",
        "policy_version": "1",
        "minimum_cell_count": minimum,
        "continuous_rounding_decimals": 3,
    }
    fidelity_policy_mapping = {
        "policy_id": "fidelity-v1",
        "policy_version": "1",
        "target_registry_version": TARGET_REGISTRY_VERSION,
        "minimum_evaluable_support": 1,
        "proportion_floor": 1.0,
        "proportion_z_score": 2.0,
        "continuous_tolerances": {
            "demographics": 100.0,
            "observation": 100.0,
            "physiology": 100.0,
            "utilization": 100.0,
            "recorded_outcome": 100.0,
        },
        "count_abs_tolerance": 10_000,
        "required_families": [
            "demographics",
            "observation",
            "physiology",
            "utilization",
            "recorded_outcome",
        ],
        "max_unevaluable_targets": 1_000,
    }
    partition_policy = tmp_path / "partition-policy.json"
    disclosure_policy = tmp_path / "disclosure-policy.json"
    fidelity_policy = tmp_path / "fidelity-policy.json"
    key_file = tmp_path / "partition.key"
    partition_policy.write_text(json.dumps(partition_policy_mapping), encoding="utf-8")
    disclosure_policy.write_text(json.dumps(disclosure_policy_mapping), encoding="utf-8")
    fidelity_policy.write_text(json.dumps(fidelity_policy_mapping), encoding="utf-8")
    key_file.write_bytes(PARTITION_KEY)

    disclosure = CalibrationDisclosurePolicy("disclosure-v1", "1", minimum, 3)
    calibration = calibrate(
        CalibrationRunConfig(
            data_root=real_root,
            source_descriptor=ROOT / "datapackage.json",
            source_snapshot="snapshot-v1",
            artifact_id="synthetic-v1",
            created_at="2026-08-31T12:00:00Z",
            partition_policy=PartitionPolicy("partition-v1", "1", "key-2026", 5_000, 2),
            disclosure_policy=disclosure,
            partition_key=PARTITION_KEY,
            age_windows=DEFAULT_AGE_WINDOWS,
        )
    )
    calibration_output = tmp_path / "calibration"
    write_calibration_result(calibration, calibration_output)
    return {
        "real_root": real_root,
        "synthetic_root": synthetic_root,
        "partition_policy": partition_policy,
        "disclosure_policy": disclosure_policy,
        "fidelity_policy": fidelity_policy,
        "key_file": key_file,
        "artifact": calibration_output / "calibration-artifact.json",
        "report": calibration_output / "calibration-report.json",
    }


def _command(tmp_path: Path, output: Path, *, mode: str = "pass") -> list[str]:
    inputs = _write_inputs(tmp_path, mode=mode)
    return [
        sys.executable,
        "-m",
        "synthetic.heldout_validate",
        "--real-root",
        str(inputs["real_root"]),
        "--descriptor",
        str(ROOT / "datapackage.json"),
        "--snapshot",
        "snapshot-v1",
        "--synthetic-root",
        str(inputs["synthetic_root"]),
        "--calibration-artifact",
        str(inputs["artifact"]),
        "--calibration-report",
        str(inputs["report"]),
        "--partition-policy",
        str(inputs["partition_policy"]),
        "--disclosure-policy",
        str(inputs["disclosure_policy"]),
        "--partition-key-file",
        str(inputs["key_file"]),
        "--frozen-policy",
        str(inputs["fidelity_policy"]),
        "--output",
        str(output),
    ]


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)


@pytest.mark.parametrize(
    ("mode", "expected_status", "expected_exit"),
    [("pass", "PASS", 0), ("fail", "FAIL", 1), ("unevaluable", "UNEVALUABLE", 1)],
)
def test_cli_promotes_every_comparison_status_with_gate_exit(
    tmp_path: Path, mode: str, expected_status: str, expected_exit: int
) -> None:
    output = tmp_path / "output"

    completed = _run(_command(tmp_path, output, mode=mode))

    assert completed.returncode == expected_exit, completed.stderr
    assert json.loads((output / "heldout-validation-report.json").read_text(encoding="ascii"))["status"] == expected_status
    assert sorted(path.name for path in output.iterdir()) == [
        "heldout-validation-report.json",
        "heldout-validation-summary.txt",
    ]


@pytest.mark.parametrize(
    "missing",
    [
        "--real-root",
        "--descriptor",
        "--snapshot",
        "--synthetic-root",
        "--calibration-artifact",
        "--calibration-report",
        "--partition-policy",
        "--disclosure-policy",
        "--partition-key-file",
        "--frozen-policy",
        "--output",
    ],
)
def test_cli_requires_every_explicit_flag(tmp_path: Path, missing: str) -> None:
    output = tmp_path / "output"
    command = _command(tmp_path, output)
    index = command.index(missing)
    del command[index : index + 2]

    completed = _run(command)

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == "held-out arguments invalid\n"
    assert not output.exists()


def test_cli_hard_failure_has_no_output_or_sensitive_stderr(tmp_path: Path) -> None:
    output = tmp_path / "output"
    command = _command(tmp_path, output)
    synthetic_root = Path(command[command.index("--synthetic-root") + 1])
    descriptor = synthetic_root / "datapackage.json"
    mapping = json.loads(descriptor.read_text(encoding="utf-8"))
    mapping.pop("x-synthetic")
    descriptor.write_text(json.dumps(mapping), encoding="utf-8")

    completed = _run(command)

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr == "held-out validation failed\n"
    assert not output.exists()
    forbidden = (
        str(synthetic_root),
        str(ROOT),
        PARTITION_KEY.hex(),
        "REAL-P-001",
        "GEN-P-001",
        "synthetic descriptor marker is required",
    )
    assert all(value not in completed.stderr for value in forbidden)


def test_cli_parser_error_redacts_unknown_argument_value(tmp_path: Path) -> None:
    output = tmp_path / "output"
    command = _command(tmp_path, output)
    governed_value = "/governed/secret/REAL-P-001.csv"
    command.extend(["--real-data", governed_value])

    completed = _run(command)

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == "held-out arguments invalid\n"
    assert governed_value not in completed.stderr
    assert "REAL-P-001" not in completed.stderr
    assert not output.exists()
