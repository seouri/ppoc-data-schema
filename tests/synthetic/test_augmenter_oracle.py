from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from synthetic import augmenter_oracle
from synthetic.augmenter_oracle import (
    AUGMENTER_ORACLE_ID,
    AUGMENTER_RUNTIME_MANIFEST_SHA256,
    SourceMatchedAugmenterOracle,
)
from synthetic.derivation import DerivationUnavailable
from synthetic.schema_contract import resource_spec

ROOT = Path(__file__).resolve().parents[2]
UNAVAILABLE_MESSAGE = "source-matched augmenter unavailable"
VISITS_OUTPUT = "visits_augmented-20260901123456.csv"
PATIENTS_OUTPUT = "patients_augmented-20260901123456.csv"


def _descriptor() -> dict[str, Any]:
    return json.loads((ROOT / "datapackage.json").read_text(encoding="utf-8"))


def _field_names(descriptor: dict[str, Any], name: str) -> list[str]:
    return [field["name"] for field in resource_spec(descriptor, name)["schema"]["fields"]]


def _write_csv(
    path: Path,
    fields: list[str],
    rows: list[dict[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _write_synthetic_package(
    package_root: Path,
    descriptor: dict[str, Any],
) -> dict[str, str]:
    patient_id = "fictional-growth-patient-001"
    visits = [
        {
            "patient_id": patient_id,
            "visit_id": "fictional-growth-visit-001",
            "age_in_days": 365,
            "encounter_type": "synthetic",
            "orig_enc_source_Epic_yn": "N",
            "weight_oz": 352.74,
            "height_in": 29.5,
            "head_circ_cm": 46.0,
            "BMI": 16.0,
            "bmi_percentile": 50.0,
        },
        {
            "patient_id": patient_id,
            "visit_id": "fictional-growth-visit-002",
            "age_in_days": 730,
            "encounter_type": "synthetic",
            "orig_enc_source_Epic_yn": "N",
            "weight_oz": 448.0,
            "height_in": 34.5,
            "head_circ_cm": 49.0,
            "BMI": 16.7,
            "bmi_percentile": 55.0,
        },
    ]
    patients = [
        {
            "patient_id": patient_id,
            "sex": "F",
            "ethnicity": "Synthetic",
            "race_1": "Synthetic",
        }
    ]
    problems = [
        {
            "patient_id": patient_id,
            "problem_list_id": "fictional-problem-001",
        }
    ]

    for name, rows in (
        ("visits", visits),
        ("patients", patients),
        ("problem_list", problems),
    ):
        path = package_root / resource_spec(descriptor, name)["path"]
        _write_csv(path, _field_names(descriptor, name), rows)

    return {
        name: hashlib.sha256(
            (package_root / resource_spec(descriptor, name)["path"]).read_bytes()
        ).hexdigest()
        for name in ("visits", "patients", "problem_list")
    }


def _write_fake_outputs(output_root: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / VISITS_OUTPUT).write_bytes(b"visit-output\n")
    (output_root / PATIENTS_OUTPUT).write_bytes(b"patient-output\n")


def _fake_success(
    command: list[str],
    **_: object,
) -> subprocess.CompletedProcess[bytes]:
    output_root = Path(command[command.index("--output_dir") + 1])
    _write_fake_outputs(output_root)
    return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")


def _assert_unavailable(
    package_root: Path,
    descriptor: dict[str, Any],
    *,
    oracle: SourceMatchedAugmenterOracle | None = None,
) -> None:
    with pytest.raises(DerivationUnavailable) as caught:
        (oracle or SourceMatchedAugmenterOracle()).derive(package_root, descriptor)

    assert str(caught.value) == UNAVAILABLE_MESSAGE
    assert "fictional-growth-patient-001" not in str(caught.value)
    assert "secret-subprocess-stderr" not in str(caught.value)
    assert str(package_root) not in str(caught.value)
    for name in ("visits_augmented", "patients_augmented"):
        path = package_root / resource_spec(descriptor, name)["path"]
        assert not path.exists()
        assert not path.is_symlink()


def test_real_cli_derives_descriptor_outputs_without_mutating_base_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catch executing the wrong runtime or copying outputs into the wrong paths."""
    descriptor = _descriptor()
    base_hashes = _write_synthetic_package(tmp_path, descriptor)
    real_run = subprocess.run
    private_outputs: list[Path] = []

    def recording_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        private_outputs.append(Path(command[command.index("--output_dir") + 1]))
        return real_run(command, **kwargs)

    monkeypatch.setattr(augmenter_oracle.subprocess, "run", recording_run)

    result = SourceMatchedAugmenterOracle().derive(tmp_path, descriptor)

    assert result.oracle_id == AUGMENTER_ORACLE_ID == "growth-augmenter-cli-v1"
    assert (
        result.implementation_fingerprint
        == AUGMENTER_RUNTIME_MANIFEST_SHA256
        == "b50afc36eca61684380154129cdacf484e62d56fa6da55914adab18c2d94d1d6"
    )
    assert result.test_only is True
    for name in ("visits_augmented", "patients_augmented"):
        output = tmp_path / resource_spec(descriptor, name)["path"]
        with output.open(encoding="utf-8", newline="") as stream:
            assert next(csv.reader(stream)) == _field_names(descriptor, name)
    assert base_hashes == {
        name: hashlib.sha256(
            (tmp_path / resource_spec(descriptor, name)["path"]).read_bytes()
        ).hexdigest()
        for name in ("visits", "patients", "problem_list")
    }
    assert len(private_outputs) == 1
    assert not private_outputs[0].exists()
    descriptor_outputs = {
        tmp_path / resource_spec(descriptor, name)["path"]
        for name in ("visits_augmented", "patients_augmented")
    }
    timestamped_outputs = set(tmp_path.glob("*_augmented-[0-9]*.csv"))
    assert timestamped_outputs <= descriptor_outputs


def test_subprocess_uses_isolated_snapshot_and_fixed_csv_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catch invoking the repository copy, a shell, or an environment-sensitive Python."""
    descriptor = _descriptor()
    _write_synthetic_package(tmp_path, descriptor)
    captured: dict[str, object] = {}

    def inspect_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        captured["command"] = command
        captured["kwargs"] = kwargs
        runtime_root = Path(str(kwargs["cwd"]))
        assert runtime_root != ROOT
        assert Path(command[3]) == runtime_root / "scripts" / "augment.py"
        assert Path(command[3]).read_bytes() == (ROOT / "scripts" / "augment.py").read_bytes()
        _write_fake_outputs(Path(command[command.index("--output_dir") + 1]))
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(augmenter_oracle.subprocess, "run", inspect_run)

    SourceMatchedAugmenterOracle().derive(tmp_path, descriptor)

    command = captured["command"]
    kwargs = captured["kwargs"]
    assert isinstance(command, list)
    assert command[1:3] == ["-E", "-s"]
    assert command[-2:] == ["--output_format", "csv"]
    assert command[4] == str(tmp_path)
    assert kwargs["shell"] is False
    assert kwargs["check"] is False
    assert kwargs["capture_output"] is True
    assert kwargs["timeout"] == 300.0
    assert not Path(str(kwargs["cwd"])).exists()


@pytest.mark.parametrize("mode", ["nonzero", "timeout"])
def test_subprocess_failures_are_redacted_and_leave_no_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    """Catch leaking subprocess diagnostics or accepting a failed invocation."""
    descriptor = _descriptor()
    _write_synthetic_package(tmp_path, descriptor)

    def fail(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        if mode == "timeout":
            raise subprocess.TimeoutExpired(
                command,
                0.01,
                output=b"fictional-growth-patient-001",
                stderr=b"secret-subprocess-stderr",
            )
        return subprocess.CompletedProcess(
            command,
            9,
            stdout=b"fictional-growth-patient-001",
            stderr=b"secret-subprocess-stderr",
        )

    monkeypatch.setattr(augmenter_oracle.subprocess, "run", fail)

    _assert_unavailable(tmp_path, descriptor)


@pytest.mark.parametrize("mode", ["missing", "changed"])
def test_runtime_manifest_integrity_failures_stop_before_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    """Catch trusting an absent or byte-modified runtime manifest."""
    package_root = tmp_path / "package-with-fictional-growth-patient-001"
    package_root.mkdir()
    descriptor = _descriptor()
    _write_synthetic_package(package_root, descriptor)
    repository_root = tmp_path / "runtime-with-secret-path"
    (repository_root / "data").mkdir(parents=True)
    if mode == "changed":
        manifest = (ROOT / "data" / "augment-runtime-manifest.json").read_bytes()
        (repository_root / "data" / "augment-runtime-manifest.json").write_bytes(
            manifest + b"\n"
        )

    invoked = False

    def unexpected_run(*_: object, **__: object) -> subprocess.CompletedProcess[bytes]:
        nonlocal invoked
        invoked = True
        raise AssertionError("subprocess must not run")

    monkeypatch.setattr(augmenter_oracle.subprocess, "run", unexpected_run)

    _assert_unavailable(
        package_root,
        descriptor,
        oracle=SourceMatchedAugmenterOracle(repository_root),
    )
    assert invoked is False


def _extra_file(output_root: Path) -> None:
    _write_fake_outputs(output_root)
    (output_root / "secret-subprocess-stderr.txt").write_text("not allowed")


def _unexpected_directory(output_root: Path) -> None:
    _write_fake_outputs(output_root)
    (output_root / "unexpected-directory").mkdir()


def _symlinked_expected_output(output_root: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root.parent / "fictional-growth-patient-001.csv"
    target.write_bytes(b"visit-output\n")
    (output_root / VISITS_OUTPUT).symlink_to(target)
    (output_root / PATIENTS_OUTPUT).write_bytes(b"patient-output\n")


def _duplicate_timestamped_output(output_root: Path) -> None:
    _write_fake_outputs(output_root)
    (output_root / "visits_augmented-20260901123457.csv").write_bytes(b"duplicate\n")


@pytest.mark.parametrize(
    "malform",
    [
        _extra_file,
        _unexpected_directory,
        _symlinked_expected_output,
        _duplicate_timestamped_output,
    ],
    ids=["extra-file", "directory", "symlink", "duplicate"],
)
def test_malformed_private_outputs_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    malform: Callable[[Path], None],
) -> None:
    """Catch accepting artifacts outside the exact two-file output contract."""
    descriptor = _descriptor()
    _write_synthetic_package(tmp_path, descriptor)

    def malformed_run(
        command: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[bytes]:
        malform(Path(command[command.index("--output_dir") + 1]))
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(augmenter_oracle.subprocess, "run", malformed_run)

    _assert_unavailable(tmp_path, descriptor)


def test_unsafe_descriptor_output_path_stops_before_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catch descriptor traversal that would write outside the package root."""
    descriptor = _descriptor()
    _write_synthetic_package(tmp_path, descriptor)
    resource_spec(descriptor, "visits_augmented")["path"] = "../fictional-growth-patient-001.csv"
    invoked = False

    def unexpected_run(*_: object, **__: object) -> subprocess.CompletedProcess[bytes]:
        nonlocal invoked
        invoked = True
        raise AssertionError("subprocess must not run")

    monkeypatch.setattr(augmenter_oracle.subprocess, "run", unexpected_run)

    _assert_unavailable(tmp_path, descriptor)
    assert invoked is False
    assert not (tmp_path.parent / "fictional-growth-patient-001.csv").exists()


def test_preexisting_augmented_destination_stops_before_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catch overwriting a caller-controlled augmented output."""
    descriptor = _descriptor()
    _write_synthetic_package(tmp_path, descriptor)
    visits_output = tmp_path / resource_spec(descriptor, "visits_augmented")["path"]
    visits_output.write_bytes(b"preserve-this-existing-file\n")
    invoked = False

    def unexpected_run(*_: object, **__: object) -> subprocess.CompletedProcess[bytes]:
        nonlocal invoked
        invoked = True
        raise AssertionError("subprocess must not run")

    monkeypatch.setattr(augmenter_oracle.subprocess, "run", unexpected_run)

    with pytest.raises(DerivationUnavailable) as caught:
        SourceMatchedAugmenterOracle().derive(tmp_path, descriptor)

    assert str(caught.value) == UNAVAILABLE_MESSAGE
    assert visits_output.read_bytes() == b"preserve-this-existing-file\n"
    patients_output = tmp_path / resource_spec(descriptor, "patients_augmented")["path"]
    assert not patients_output.exists()
    assert invoked is False
