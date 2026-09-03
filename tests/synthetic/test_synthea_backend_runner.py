from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import scripts.synthea_backend as backend


def _config(tmp_path: Path, **changes: object) -> backend.SyntheaBackendConfig:
    values: dict[str, object] = {
        "synthea_root": tmp_path / "checkout",
        "output": tmp_path / "package",
        "patient_count": 2,
        "seed": 99,
        "java_home": tmp_path / "jdk",
    }
    values.update(changes)
    return backend.SyntheaBackendConfig(**values)  # type: ignore[arg-type]


def test_command_is_fixed_pediatric_offline_and_shell_free(tmp_path: Path) -> None:
    config = _config(tmp_path)
    command = backend.build_synthea_command(
        config,
        work_root=tmp_path / "work",
        fhir_output=tmp_path / "fhir",
        overlay_dir=tmp_path / "overlay",
    )
    assert command[0] == str(tmp_path / "work" / "gradlew")
    assert "--offline" in command
    assert "-Dorg.gradle.vfs.watch=false" in command
    joined = " ".join(command)
    for argument in ("-s 99", "-p 2", "-a 0-18", "-r 20260901", "-d"):
        assert argument in joined
    assert "--exporter.fhir.export=true" in joined
    assert "--exporter.fhir.transaction_bundle=false" in joined
    assert "--exporter.baseDirectory=" in joined
    assert "--allow-gradle-network" not in joined

    online = _config(tmp_path, allow_gradle_network=True)
    assert "--offline" not in backend.build_synthea_command(
        online,
        work_root=tmp_path / "work",
        fhir_output=tmp_path / "fhir",
        overlay_dir=tmp_path / "overlay",
    )


def test_checkout_copy_rejects_symlinks_and_does_not_copy_build_output(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
    (source / "build.gradle").write_text("sourceCompatibility = '17'\n", encoding="utf-8")
    (source / "tracked.txt").write_text("source", encoding="utf-8")
    (source / "build").mkdir()
    (source / "build" / "ignored.txt").write_text("ignored", encoding="utf-8")
    destination = tmp_path / "destination"
    backend.copy_checkout_tree(source, destination)
    assert (destination / "tracked.txt").read_text(encoding="utf-8") == "source"
    assert not (destination / "build").exists()

    (source / "unsafe").symlink_to(source / "tracked.txt")
    with pytest.raises(ValueError, match=backend.BACKEND_ERROR):
        backend.copy_checkout_tree(source, tmp_path / "rejected")


def test_verify_java_home_requires_major_17(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    java_home = tmp_path / "jdk"
    (java_home / "bin").mkdir(parents=True)
    (java_home / "bin" / "java").write_text("", encoding="utf-8")

    def fake_run(command: object, **_: object) -> subprocess.CompletedProcess[str]:
        assert command == [str(java_home / "bin" / "java"), "-version"]
        return subprocess.CompletedProcess(command, 0, "", 'openjdk version "17.0.20"\n')

    monkeypatch.setattr(backend.subprocess, "run", fake_run)
    assert backend.verify_java_home(java_home) == java_home / "bin" / "java"

    def java_26(command: object, **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, "", 'openjdk version "26.0.2"\n')

    monkeypatch.setattr(backend.subprocess, "run", java_26)
    with pytest.raises(ValueError, match=backend.BACKEND_ERROR):
        backend.verify_java_home(java_home)


def test_checkout_verifier_requires_the_pinned_revision_and_wrapper(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    checkout = tmp_path / "checkout"
    (checkout / "gradle" / "wrapper").mkdir(parents=True)
    (checkout / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
    (checkout / "build.gradle").write_text("sourceCompatibility = '17'\n", encoding="utf-8")
    (checkout / "gradle" / "wrapper" / "gradle-wrapper.properties").write_text(
        "distributionUrl=gradle-9.2.1-bin.zip\n", encoding="utf-8"
    )
    monkeypatch.setattr(backend, "_git_output", lambda *_: backend.SYNTHEA_REVISION)
    monkeypatch.setattr(
        backend.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, b"", b""),
    )
    backend.verify_synthea_checkout(checkout)

    monkeypatch.setattr(backend, "_git_output", lambda *_: "wrong-revision")
    with pytest.raises(ValueError, match=backend.BACKEND_ERROR):
        backend.verify_synthea_checkout(checkout)


def test_backend_failure_is_fixed_and_discards_subprocess_details(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path)

    def fail(*_: object, **__: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 134, "patient-secret", "stack/path")

    monkeypatch.setattr(backend.subprocess, "run", fail)
    with pytest.raises(ValueError, match=f"^{backend.BACKEND_ERROR}$") as error:
        backend.invoke_synthea(config, work_root=tmp_path / "work", overlay_dir=tmp_path / "overlay")
    assert "patient-secret" not in str(error.value)
    assert "stack/path" not in str(error.value)
