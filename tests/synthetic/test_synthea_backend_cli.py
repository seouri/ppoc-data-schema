from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.synthea_backend as backend


def _result(tmp_path: Path) -> backend.SyntheaBackendResult:
    report = backend.SyntheaBackendReport(
        report_version=backend.REPORT_VERSION,
        engine_revision=backend.SYNTHEA_REVISION,
        module_sha256="a" * 64,
        overlay_sha256="b" * 64,
        configuration_sha256="c" * 64,
        requested_patient_count=1,
        generated_patient_count=1,
        healthy_count=1,
        ghd_count=0,
        visit_count=1,
        height_observation_count=1,
        weight_observation_count=1,
        bmi_observation_count=1,
        head_observation_count=0,
        min_age_days=730,
        max_age_days=730,
        mean_age_days=730.0,
        status="GENERATED_TEST_ONLY",
    )
    return backend.SyntheaBackendResult(tmp_path / "package", report)


def test_cli_prints_only_package_path_and_aggregate_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = _result(tmp_path)
    monkeypatch.setattr(backend, "generate_synthea_package", lambda _: result)

    backend.main(
        [
            "--synthea-root",
            str(tmp_path / "checkout"),
            "--output",
            str(tmp_path / "package"),
            "--patients",
            "1",
            "--seed",
            "17",
        ]
    )

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == str(result.package)
    assert json.loads(lines[1])["status"] == "GENERATED_TEST_ONLY"
    assert "patient_id" not in lines[1]
    assert "package" not in lines[1]


def test_cli_redacts_backend_failures(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fail(_: backend.SyntheaBackendConfig) -> backend.SyntheaBackendResult:
        raise RuntimeError("patient-name-and-command-secret")

    monkeypatch.setattr(backend, "generate_synthea_package", fail)
    with pytest.raises(SystemExit, match=f"^{backend.BACKEND_ERROR}$"):
        backend.main(
            [
                "--synthea-root",
                str(tmp_path / "checkout"),
                "--output",
                str(tmp_path / "package"),
                "--patients",
                "1",
                "--seed",
                "17",
            ]
        )
