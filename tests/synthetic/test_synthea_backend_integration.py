from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.synthea_backend as backend
from tests.synthetic.test_synthea_backend_parser import _fixture_bundle


def _healthy_bundle() -> dict[str, object]:
    bundle = copy.deepcopy(_fixture_bundle())
    for entry in bundle["entry"]:
        resource = entry["resource"]
        if not isinstance(resource, dict):
            continue
        resource_id = resource.get("id")
        if isinstance(resource_id, str):
            resource["id"] = resource_id.replace("p-source", "p-healthy").replace(
                "condition-source", "condition-healthy"
            ).replace("e-", "healthy-e-")
        for key in ("subject", "encounter"):
            reference = resource.get(key)
            if isinstance(reference, dict) and isinstance(reference.get("reference"), str):
                reference["reference"] = reference["reference"].replace(
                    "p-source", "p-healthy"
                ).replace("Encounter/e-", "Encounter/healthy-e-")
    bundle["entry"] = [
        entry
        for entry in bundle["entry"]
        if not (
            isinstance(entry.get("resource"), dict)
            and entry["resource"].get("resourceType") == "Condition"
        )
    ]
    return bundle


def _config(tmp_path: Path, *, patients: int = 2, seed: int = 17) -> backend.SyntheaBackendConfig:
    checkout = tmp_path / "checkout"
    checkout.mkdir(parents=True)
    return backend.SyntheaBackendConfig(
        synthea_root=checkout,
        output=tmp_path / "package",
        patient_count=patients,
        seed=seed,
        java_home=tmp_path / "jdk",
    )


def _fake_runtime() -> SimpleNamespace:
    return SimpleNamespace(
        reference=SimpleNamespace(reference_id="fake-reference-v1", source_sha256="a" * 64),
        derivation_oracle=object(),
        derivation_binding=object(),
    )


def test_generate_projects_external_fhir_and_publishes_aggregate_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    captured: dict[str, object] = {}

    monkeypatch.setattr(backend, "verify_synthea_checkout", lambda _: None)
    monkeypatch.setattr(backend, "build_development_runtime", lambda _: _fake_runtime())

    def fake_invoke(
        _: backend.SyntheaBackendConfig, *, work_root: Path, overlay_dir: Path
    ) -> Path:
        del overlay_dir
        fhir = work_root / "synthea-output" / "fhir"
        fhir.mkdir(parents=True)
        for name, bundle in (("ghd.json", _fixture_bundle()), ("healthy.json", _healthy_bundle())):
            (fhir / name).write_text(json.dumps(bundle), encoding="utf-8")
        return fhir

    def fake_export(
        _: dict[str, object],
        rows: dict[str, list[dict[str, object]]],
        output: Path,
        *,
        metadata: backend.PackageExportMetadata,
        derivation_oracle: object,
        derivation_binding: object,
    ) -> Path:
        del derivation_oracle, derivation_binding
        captured["rows"] = rows
        captured["metadata"] = metadata
        output.mkdir()
        return output

    monkeypatch.setattr(backend, "invoke_synthea", fake_invoke)
    monkeypatch.setattr(backend, "export_exact_schema_package", fake_export)

    result = backend.generate_synthea_package(config)

    assert result.package == config.output
    assert result.package.is_dir()
    assert result.report.generated_patient_count == 2
    assert result.report.healthy_count == 1
    assert result.report.ghd_count == 1
    assert result.report.visit_count == 4
    metadata = captured["metadata"]
    assert isinstance(metadata, backend.PackageExportMetadata)
    assert metadata.engine == "synthea"
    assert metadata.profile == backend.SYNTHEA_PROFILE
    rows = captured["rows"]
    assert isinstance(rows, dict)
    patient_ids = tuple(row["patient_id"] for row in rows["patients"])
    assert len(patient_ids) == len(set(patient_ids)) == 2
    assert all(patient_id not in {"p-source", "p-healthy"} for patient_id in patient_ids)
    report_text = result.report.to_json_bytes().decode("ascii")
    assert "p-source" not in report_text
    assert "healthy.json" not in report_text


def test_generate_does_not_publish_when_synthea_count_is_short(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path, patients=2)
    monkeypatch.setattr(backend, "verify_synthea_checkout", lambda _: None)
    monkeypatch.setattr(backend, "build_development_runtime", lambda _: _fake_runtime())

    def fake_invoke(
        _: backend.SyntheaBackendConfig, *, work_root: Path, overlay_dir: Path
    ) -> Path:
        del overlay_dir
        fhir = work_root / "synthea-output" / "fhir"
        fhir.mkdir(parents=True)
        (fhir / "one.json").write_text(json.dumps(_fixture_bundle()), encoding="utf-8")
        return fhir

    monkeypatch.setattr(backend, "invoke_synthea", fake_invoke)
    with pytest.raises(ValueError, match=f"^{backend.BACKEND_ERROR}$"):
        backend.generate_synthea_package(config)
    assert not config.output.exists()


def test_generate_rejects_an_existing_output_before_running_synthea(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    config.output.mkdir()
    called = False

    def should_not_run(*_: object, **__: object) -> Path:
        nonlocal called
        called = True
        raise AssertionError("Synthea should not run for an existing output")

    monkeypatch.setattr(backend, "invoke_synthea", should_not_run)
    with pytest.raises(FileExistsError, match="output path already exists"):
        backend.generate_synthea_package(config)
    assert called is False


def test_generate_is_reproducible_for_same_seed_and_changes_for_new_seed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: list[dict[str, list[dict[str, object]]]] = []
    monkeypatch.setattr(backend, "verify_synthea_checkout", lambda _: None)
    monkeypatch.setattr(backend, "build_development_runtime", lambda _: _fake_runtime())

    def fake_invoke(
        _: backend.SyntheaBackendConfig, *, work_root: Path, overlay_dir: Path
    ) -> Path:
        del overlay_dir
        fhir = work_root / "synthea-output" / "fhir"
        fhir.mkdir(parents=True)
        for name, bundle in (("ghd.json", _fixture_bundle()), ("healthy.json", _healthy_bundle())):
            (fhir / name).write_text(json.dumps(bundle), encoding="utf-8")
        return fhir

    def fake_export(
        _: dict[str, object],
        rows: dict[str, list[dict[str, object]]],
        output: Path,
        *,
        metadata: backend.PackageExportMetadata,
        derivation_oracle: object,
        derivation_binding: object,
    ) -> Path:
        del metadata, derivation_oracle, derivation_binding
        captured.append(copy.deepcopy(rows))
        output.mkdir()
        return output

    monkeypatch.setattr(backend, "invoke_synthea", fake_invoke)
    monkeypatch.setattr(backend, "export_exact_schema_package", fake_export)

    first = backend.generate_synthea_package(_config(tmp_path / "first"))
    second_config = _config(tmp_path / "second")
    second = backend.generate_synthea_package(second_config)
    changed_config = _config(tmp_path / "changed", seed=18)
    changed = backend.generate_synthea_package(changed_config)

    assert captured[0] == captured[1]
    assert captured[0] != captured[2]
    assert first.report.to_mapping() == second.report.to_mapping()
    assert first.report.configuration_sha256 == second.report.configuration_sha256
    assert first.report.configuration_sha256 != changed.report.configuration_sha256


@pytest.mark.skipif(
    not os.environ.get("SYNTHEA_CHECKOUT"),
    reason="set SYNTHEA_CHECKOUT to run the opt-in external Synthea smoke",
)
def test_opt_in_pinned_checkout_smoke(tmp_path: Path) -> None:
    java_home = os.environ.get("SYNTHEA_JAVA_HOME") or os.environ.get("JAVA_HOME")
    config = backend.SyntheaBackendConfig(
        synthea_root=Path(os.environ["SYNTHEA_CHECKOUT"]),
        output=tmp_path / "package",
        patient_count=2,
        seed=17,
        java_home=None if java_home is None else Path(java_home),
        timeout_seconds=900.0,
    )
    result = backend.generate_synthea_package(config)
    assert result.package.is_dir()
    assert result.report.generated_patient_count == 2
    assert result.report.status == "GENERATED_TEST_ONLY"
