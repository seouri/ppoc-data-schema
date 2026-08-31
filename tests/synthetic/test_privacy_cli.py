from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.synthetic.privacy_fixtures import (
    policy_mapping,
    write_policy,
    write_real_package,
)
from tests.synthetic.test_privacy_integration import _independent_generated

ROOT = Path(__file__).resolve().parents[2]


def _command(tmp_path: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "synthetic.privacy_audit",
        "--real-root",
        str(write_real_package(tmp_path / "real")),
        "--synthetic-root",
        str(_independent_generated(tmp_path / "generated")),
        "--policy",
        str(write_policy(tmp_path / "policy.json", thresholds={key: 1.0 for key in policy_mapping()["thresholds"]})),
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
    command.extend([
        "--heldout-root", str(heldout), "--prior-release-root", str(prior_one),
        "--prior-release-root", str(prior_two),
    ])

    completed = _run(command)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
    assert json.loads((tmp_path / "output" / "privacy-audit-report.json").read_text(encoding="ascii"))["status"] == "PASS"


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
