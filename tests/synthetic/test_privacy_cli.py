from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.synthetic.privacy_fixtures import (
    policy_mapping,
    write_generated_package,
    write_policy,
    write_real_package,
    write_shadow_manifest,
)
from tests.synthetic.test_privacy_integration import _independent_generated

ROOT = Path(__file__).resolve().parents[2]


def _command(tmp_path: Path) -> list[str]:
    thresholds = {key: 1.0 for key in policy_mapping()["thresholds"]}
    thresholds["identifier_overlap_rate"] = 0
    thresholds["exact_reproduction_rate"] = 0
    return [
        sys.executable,
        "-m",
        "synthetic.privacy_audit",
        "--real-root",
        str(write_real_package(tmp_path / "real")),
        "--synthetic-root",
        str(_independent_generated(tmp_path / "generated")),
        "--policy",
        str(write_policy(tmp_path / "policy.json", thresholds=thresholds)),
        "--output",
        str(tmp_path / "output"),
    ]


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)


def test_cli_promotes_pass_and_accepts_explicit_optional_paths(tmp_path: Path) -> None:
    """Catches CLI omission of explicit optional audit inputs."""
    command = _command(tmp_path)
    heldout = write_real_package(tmp_path / "heldout", id_prefix="HLD")
    prior_one = _independent_generated(tmp_path / "prior-one", id_prefix="P1")
    prior_two = _independent_generated(tmp_path / "prior-two", id_prefix="P2")
    shadow = _independent_generated(tmp_path / "shadow", id_prefix="SHD")
    manifest = write_shadow_manifest(
        tmp_path / "shadows.json",
        [{"run_id": "shadow-one", "package_root": str(shadow), "members": ["REAL-P-001", "REAL-P-002", "REAL-P-003"]}],
    )
    command.extend([
        "--heldout-root", str(heldout), "--shadow-manifest", str(manifest),
        "--prior-release-root", str(prior_one), "--prior-release-root", str(prior_two),
        "--negative-control-root", str(_independent_generated(tmp_path / "negative", id_prefix="NEG")),
        "--positive-control-root", str(write_generated_package(tmp_path / "positive", id_prefix="POS")),
    ])

    completed = _run(command)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
    assert json.loads((tmp_path / "output" / "privacy-audit-report.json").read_text(encoding="ascii"))["status"] == "PASS"


@pytest.mark.parametrize(("mode", "expected_status"), [("fail", "FAIL"), ("unevaluable", "UNEVALUABLE")])
def test_cli_promotes_nonpassing_aggregate_reports_with_gate_exit(
    tmp_path: Path, mode: str, expected_status: str
) -> None:
    """Catches treating a promoted FAIL or UNEVALUABLE privacy report as CLI success."""
    command = _command(tmp_path)
    policy = Path(command[command.index("--policy") + 1])
    if mode == "fail":
        package = Path(command[command.index("--synthetic-root") + 1])
        original = write_real_package(tmp_path / "copy-source")
        filename = "visits_augmented.csv"
        (package / filename).write_bytes(
            (original / filename).read_bytes().replace(b"REAL-", b"GEN-")
        )
    else:
        payload = json.loads(policy.read_text(encoding="utf-8"))
        payload["minimum_evaluable_patients"] = 100
        policy.write_text(json.dumps(payload), encoding="utf-8")

    completed = _run(command)

    assert completed.returncode == 1
    assert completed.stderr == "privacy audit failed\n"
    assert json.loads((tmp_path / "output" / "privacy-audit-report.json").read_text(encoding="ascii"))["status"] == expected_status


@pytest.mark.parametrize("missing", ["--real-root", "--synthetic-root", "--policy", "--output"])
def test_cli_requires_each_governed_flag(tmp_path: Path, missing: str) -> None:
    """Catches an audit invocation proceeding with an implicit governed input."""
    command = _command(tmp_path)
    index = command.index(missing)
    del command[index : index + 2]

    completed = _run(command)

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == "privacy audit arguments invalid\n"


def test_cli_redacts_parser_and_hard_failures(tmp_path: Path) -> None:
    """Catches governed paths, identifiers, and raw exception content in CLI stderr."""
    command = _command(tmp_path)
    command.extend(["--unknown", "/governed/REAL-P-001.csv"])
    parser_error = _run(command)
    assert parser_error.returncode == 2
    assert parser_error.stderr == "privacy audit arguments invalid\n"
    assert "REAL-P-001" not in parser_error.stderr

    command = _command(tmp_path / "hard")
    descriptor = Path(command[command.index("--synthetic-root") + 1]) / "datapackage.json"
    payload = json.loads(descriptor.read_text(encoding="utf-8"))
    payload.pop("x-synthetic")
    descriptor.write_text(json.dumps(payload), encoding="utf-8")
    hard_failure = _run(command)
    assert hard_failure.returncode == 1
    assert hard_failure.stderr == "privacy audit failed\n"
    assert "REAL-P-001" not in hard_failure.stderr
