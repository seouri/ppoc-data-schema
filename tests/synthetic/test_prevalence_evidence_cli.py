from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from synthetic.prevalence_evidence import (
    PrevalenceEvidenceResult,
    evaluate_prevalence_evidence,
    write_prevalence_evidence,
)
from tests.synthetic.test_prevalence_evidence_integration import _config, _controlled_heldout_result

ROOT = Path(__file__).resolve().parents[2]


def _result(tmp_path: Path) -> PrevalenceEvidenceResult:
    return PrevalenceEvidenceResult(evaluate_prevalence_evidence(_config(tmp_path)))


def _command(output: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "synthetic.prevalence_evidence",
        "--real-root", "/governed/real",
        "--descriptor", "/governed/datapackage.json",
        "--snapshot", "snapshot-v1",
        "--calibration-artifact", "/governed/calibration-artifact.json",
        "--calibration-report", "/governed/calibration-report.json",
        "--partition-policy", "/governed/partition-policy.json",
        "--disclosure-policy", "/governed/disclosure-policy.json",
        "--partition-key-file", "/governed/partition.key",
        "--frozen-policy", "/governed/fidelity-policy.json",
        "--package-root", "/governed/package-a",
        "--package-root", "/governed/package-b",
        "--package-root", "/governed/package-c",
        "--expected-seed", "101",
        "--expected-seed", "102",
        "--expected-seed", "103",
        "--output", str(output),
    ]


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)


def _operational_command(tmp_path: Path, output: Path) -> list[str]:
    config = _config(tmp_path)
    template = config.heldout_template
    assert template is not None
    partition = tmp_path / "partition-policy.json"
    disclosure = tmp_path / "disclosure-policy.json"
    fidelity = tmp_path / "fidelity-policy.json"
    key_file = tmp_path / "partition.key"
    partition.write_text(
        json.dumps(
            {
                "policy_id": template.partition_policy.policy_id,
                "policy_version": template.partition_policy.policy_version,
                "key_id": template.partition_policy.key_id,
                "calibration_basis_points": template.partition_policy.calibration_basis_points,
                "minimum_partition_patients": template.partition_policy.minimum_partition_patients,
            }
        ),
        encoding="utf-8",
    )
    disclosure.write_text(
        json.dumps(
            {
                "policy_id": template.disclosure_policy.policy_id,
                "policy_version": template.disclosure_policy.policy_version,
                "minimum_cell_count": template.disclosure_policy.minimum_cell_count,
                "continuous_rounding_decimals": template.disclosure_policy.continuous_rounding_decimals,
            }
        ),
        encoding="utf-8",
    )
    fidelity.write_text(
        json.dumps(
            {
                "policy_id": template.fidelity_policy.policy_id,
                "policy_version": template.fidelity_policy.policy_version,
                "target_registry_version": template.fidelity_policy.target_registry_version,
                "minimum_evaluable_support": template.fidelity_policy.minimum_evaluable_support,
                "proportion_floor": template.fidelity_policy.proportion_floor,
                "proportion_z_score": template.fidelity_policy.proportion_z_score,
                "continuous_tolerances": dict(template.fidelity_policy.continuous_tolerances),
                "count_abs_tolerance": template.fidelity_policy.count_abs_tolerance,
                "required_families": list(template.fidelity_policy.required_families),
                "max_unevaluable_targets": template.fidelity_policy.max_unevaluable_targets,
            }
        ),
        encoding="utf-8",
    )
    key_file.write_bytes(template.partition_key)
    command = [
        sys.executable,
        "-m",
        "synthetic.prevalence_evidence",
        "--real-root",
        str(template.real_root),
        "--descriptor",
        str(template.real_descriptor),
        "--snapshot",
        template.source_snapshot,
        "--calibration-artifact",
        str(template.calibration_artifact),
        "--calibration-report",
        str(template.calibration_report),
        "--partition-policy",
        str(partition),
        "--disclosure-policy",
        str(disclosure),
        "--partition-key-file",
        str(key_file),
        "--frozen-policy",
        str(fidelity),
    ]
    for run in config.runs:
        command.extend(("--package-root", str(run.package_root)))
    for run in config.runs:
        command.extend(("--expected-seed", str(run.expected_seed)))
    return [*command, "--output", str(output)]


def test_result_canonical_report_and_summary_round_trip_without_governed_details(tmp_path: Path) -> None:
    """Removing canonical serialization would make written governed reports non-reproducible."""
    result = _result(tmp_path)

    report_bytes = result.report.canonical_json_bytes()
    summary_bytes = result.report.human_summary().encode("ascii")

    assert report_bytes == result.report.canonical_json_bytes()
    assert summary_bytes == result.report.human_summary().encode("ascii")
    assert report_bytes.decode("ascii").endswith("\n")
    assert summary_bytes.decode("ascii").isascii()
    public = report_bytes.decode("ascii") + summary_bytes.decode("ascii")
    forbidden = (
        str(tmp_path),
        "heldout_aggregate_sha256",
        "synthetic_aggregate_sha256",
        "support",
        "denominator",
        "PREV101-P-001",
        "REAL-P-001",
        "outcome_layer=latent",
    )
    assert all(value not in public for value in forbidden)


def test_writer_promotes_only_reparsed_canonical_aggregate_output(tmp_path: Path) -> None:
    """Skipping output reparse could promote a corrupted report or summary."""
    result = _result(tmp_path)
    output = tmp_path / "output"

    write_prevalence_evidence(result, output)

    assert sorted(path.name for path in output.iterdir()) == [
        "prevalence-evidence-report.json",
        "prevalence-evidence-summary.txt",
    ]
    assert (output / "prevalence-evidence-report.json").read_bytes() == result.report.canonical_json_bytes()
    assert (output / "prevalence-evidence-summary.txt").read_bytes() == result.report.human_summary().encode("ascii")


@pytest.mark.parametrize("suffix", ["partial", "failed"])
def test_writer_refuses_existing_lifecycle_collision_without_overwrite(tmp_path: Path, suffix: str) -> None:
    """Allowing lifecycle reuse would replace a prior governed evidence result."""
    result = _result(tmp_path)
    output = tmp_path / "output"
    lifecycle = result.report.lifecycle_identity()
    collision = output.parent / f".{output.name}.{lifecycle}.{suffix}"
    collision.mkdir()

    with pytest.raises(FileExistsError, match="lifecycle"):
        write_prevalence_evidence(result, output)
    assert not output.exists()


def test_writer_refuses_existing_output_without_replacing_it(tmp_path: Path) -> None:
    """Writing over an earlier report would make the audit lifecycle non-reproducible."""
    result = _result(tmp_path)
    output = tmp_path / "output"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("keep\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="lifecycle"):
        write_prevalence_evidence(result, output)
    assert sentinel.read_text(encoding="utf-8") == "keep\n"


def test_writer_archives_only_fixed_failure_after_noncanonical_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Leaking writer errors or retaining report bytes would disclose governed material."""
    result = _result(tmp_path)
    output = tmp_path / "output"
    module = __import__("synthetic.prevalence_evidence", fromlist=["_write_exclusive_fsynced"])
    real_write = module._write_exclusive_fsynced

    def corrupt_report(path: Path, payload: bytes) -> None:
        if path.name == "prevalence-evidence-report.json":
            payload = b" " + payload
        real_write(path, payload)

    monkeypatch.setattr(module, "_write_exclusive_fsynced", corrupt_report)

    with pytest.raises(ValueError, match="could not be promoted") as error:
        write_prevalence_evidence(result, output)

    assert "canonical" not in str(error.value)
    assert not output.exists()
    lifecycle = result.report.lifecycle_identity()
    failed = output.parent / f".{output.name}.{lifecycle}.failed"
    assert sorted(path.name for path in failed.iterdir()) == ["failure.json"]
    assert json.loads((failed / "failure.json").read_text(encoding="utf-8")) == {
        "status": "FAILED",
        "reason": "prevalence evidence output validation failed",
    }


@pytest.mark.parametrize(
    "missing",
    [
        "--real-root",
        "--descriptor",
        "--snapshot",
        "--calibration-artifact",
        "--calibration-report",
        "--partition-policy",
        "--disclosure-policy",
        "--partition-key-file",
        "--frozen-policy",
        "--package-root",
        "--expected-seed",
        "--output",
    ],
)
def test_cli_requires_every_governed_argument_without_echoing_values(tmp_path: Path, missing: str) -> None:
    """Making any governed input optional would silently select unapproved evidence."""
    command = _command(tmp_path / "output")
    index = command.index(missing)
    del command[index : index + 2]

    completed = _run(command)

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == "prevalence evidence arguments invalid\n"
    assert "/governed" not in completed.stderr


def test_cli_redacts_unknown_flags_and_hard_runtime_failures(tmp_path: Path) -> None:
    """Parser and runtime failures must not reveal a path, key, or validation detail."""
    command = _command(tmp_path / "output")
    secret = "/governed/secret/REAL-P-001.csv"
    unknown = _run([*command, "--unexpected", secret])
    failed = _run(command)

    assert unknown.returncode == 2
    assert unknown.stdout == ""
    assert unknown.stderr == "prevalence evidence arguments invalid\n"
    assert failed.returncode == 1
    assert failed.stdout == ""
    assert failed.stderr == "prevalence evidence failed\n"
    assert secret not in unknown.stderr + failed.stderr
    assert "/governed" not in unknown.stderr + failed.stderr


def test_cli_treats_invalid_seed_cardinality_as_a_redacted_parser_error(tmp_path: Path) -> None:
    """Allowing fewer than three seed/package pairs reaches governed evaluation incorrectly."""
    command = _command(tmp_path / "output")
    third_root = [index for index, value in enumerate(command) if value == "--package-root"][2]
    del command[third_root : third_root + 2]
    third_seed = [index for index, value in enumerate(command) if value == "--expected-seed"][2]
    del command[third_seed : third_seed + 2]

    completed = _run(command)

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == "prevalence evidence arguments invalid\n"


def test_cli_promotes_unevaluable_evidence_but_returns_a_nonzero_gate_status(tmp_path: Path) -> None:
    """Returning zero for unevaluable evidence would permit unsupported prevalence claims."""
    output = tmp_path / "output"

    completed = _run(_operational_command(tmp_path, output))

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr == "prevalence evidence failed\n"
    assert json.loads((output / "prevalence-evidence-report.json").read_text(encoding="ascii"))["status"] == "UNEVALUABLE"


def test_cli_returns_zero_only_after_a_pass_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Changing the PASS gate must make this command return a failure exit code."""
    command = _operational_command(tmp_path, tmp_path / "output")
    module = __import__("synthetic.prevalence_evidence", fromlist=["main"])
    template = _config(tmp_path / "second-config").heldout_template
    assert template is not None
    monkeypatch.setattr(sys, "argv", command[2:])
    monkeypatch.setattr(module, "validate_heldout", lambda _config: _controlled_heldout_result(template))

    module.main()

    assert json.loads((tmp_path / "output" / "prevalence-evidence-report.json").read_text(encoding="ascii"))["status"] == "PASS"


def test_writer_rejects_invalid_result_type(tmp_path: Path) -> None:
    """Accepting a report-shaped object would bypass report/run binding validation."""
    with pytest.raises(TypeError):
        write_prevalence_evidence(object(), tmp_path / "output")  # type: ignore[arg-type]
