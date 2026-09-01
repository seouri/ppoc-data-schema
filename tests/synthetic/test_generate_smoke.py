import hashlib
import json
import os
from pathlib import Path

import pytest

import synthetic.generate as generate_module
from synthetic.cdc_reference import CDC_GENERATION_DOMAIN_POLICY
from synthetic.derivation import DerivationUnavailable
from synthetic.generate import _scan_tree, generate_smoke
from synthetic.package_export import PackageExportMetadata
from synthetic.run_directory import RunDirectory
from tests.synthetic.fakes import (
    IdentityPreservingTestDerivationOracle,
    LinearTestReference,
    test_derivation_binding,
)

ROOT = Path(__file__).resolve().parents[2]


def _hashes(root: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.iterdir())
        if path.is_file() and path.name != "manifest.json"
    }


def test_smoke_generation_is_exact_schema_and_reproducible(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    arguments = {
        "descriptor_path": ROOT / "datapackage.json",
        "patient_count": 3,
        "seed": 20260830,
        "reference_time": "2026-08-30T00:00:00Z",
        "software_revision": "test-revision",
        "reference": LinearTestReference(),
        "derivation_oracle": IdentityPreservingTestDerivationOracle(),
        "derivation_binding": test_derivation_binding(),
    }
    generate_smoke(output=first, **arguments)
    generate_smoke(output=second, **arguments)
    assert _hashes(first) == _hashes(second)
    manifest = json.loads((first / "manifest.json").read_text())
    assert manifest["profile"] == "smoke"
    assert manifest["status"] == "STRUCTURE_VALIDATED_TEST_ORACLE"
    assert set(manifest["row_counts"]) == {
        "patients", "patients_augmented", "visits", "visits_augmented",
        "labs", "medications", "problem_list", "referrals",
    }
    assert manifest["row_counts"]["patients_augmented"] == 3
    assert manifest["row_counts"]["visits_augmented"] == 9
    assert manifest["reference_id"] == "linear-test-reference-v1"
    assert manifest["file_sha256"]
    assert "manifest.json" not in manifest["file_sha256"]
    assert "derivation_oracle" not in manifest
    assert len(list(first.glob("*.csv"))) == 8


def test_smoke_profile_override_changes_only_profile_metadata(tmp_path: Path) -> None:
    """Catches ignoring the caller-selected aggregate-safe smoke profile."""
    legacy = tmp_path / "legacy"
    development = tmp_path / "development"
    arguments = {
        "descriptor_path": ROOT / "datapackage.json",
        "patient_count": 1,
        "seed": 20260901,
        "reference_time": "2026-09-01T00:00:00Z",
        "software_revision": "test-revision",
        "reference": LinearTestReference(),
        "derivation_oracle": IdentityPreservingTestDerivationOracle(),
        "derivation_binding": test_derivation_binding(),
    }

    generate_smoke(output=legacy, **arguments)
    generate_smoke(output=development, profile="development-smoke", **arguments)

    legacy_manifest = json.loads((legacy / "manifest.json").read_text())
    development_manifest = json.loads((development / "manifest.json").read_text())
    assert legacy_manifest["profile"] == "smoke"
    assert development_manifest["profile"] == "development-smoke"
    assert development_manifest["configuration_sha256"] != legacy_manifest["configuration_sha256"]
    assert {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in legacy.glob("*.csv")
    } == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in development.glob("*.csv")
    }


def test_smoke_configuration_hash_commits_generation_domain_policy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    hashes: list[str | None] = []

    def capture_export(descriptor, base_rows, output, **kwargs):
        del descriptor, base_rows
        hashes.append(kwargs["metadata"].configuration_sha256)
        return output

    monkeypatch.setattr(generate_module, "export_exact_schema_package", capture_export)
    arguments = {
        "descriptor_path": ROOT / "datapackage.json",
        "patient_count": 1,
        "seed": 20260901,
        "reference_time": "2026-09-01T00:00:00Z",
        "software_revision": "test-revision",
        "reference": LinearTestReference(),
        "derivation_oracle": IdentityPreservingTestDerivationOracle(),
        "derivation_binding": test_derivation_binding(),
    }
    generate_smoke(output=tmp_path / "baseline", **arguments)
    monkeypatch.setattr(
        generate_module,
        "CDC_GENERATION_DOMAIN_POLICY",
        f"{CDC_GENERATION_DOMAIN_POLICY}-changed",
    )
    generate_smoke(output=tmp_path / "changed", **arguments)

    assert len(hashes) == 2
    assert hashes[0] != hashes[1]


@pytest.mark.parametrize("profile", ("patient-profile", "profile/path", "profile value"))
def test_smoke_profile_rejects_unsafe_aggregate_metadata(profile: str, tmp_path: Path) -> None:
    """Catches a smoke profile accepting record or path-like metadata tokens."""
    output = tmp_path / "run"

    with pytest.raises(ValueError):
        generate_smoke(
            descriptor_path=ROOT / "datapackage.json",
            output=output,
            patient_count=1,
            seed=20260901,
            reference_time="2026-09-01T00:00:00Z",
            software_revision="test-revision",
            reference=LinearTestReference(),
            derivation_oracle=IdentityPreservingTestDerivationOracle(),
            derivation_binding=test_derivation_binding(),
            profile=profile,
        )

    assert not output.exists()


def test_smoke_manifest_records_injected_reference_digest(tmp_path: Path) -> None:
    class HashedLinearTestReference(LinearTestReference):
        source_sha256 = "a" * 64

    output = tmp_path / "run"
    generate_smoke(
        descriptor_path=ROOT / "datapackage.json",
        output=output,
        patient_count=1,
        seed=20260830,
        reference_time="2026-08-30T00:00:00Z",
        software_revision="test-revision",
        reference=HashedLinearTestReference(),
        derivation_oracle=IdentityPreservingTestDerivationOracle(),
        derivation_binding=test_derivation_binding(),
    )

    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["reference_sha256"] == "a" * 64


def test_smoke_generation_preserves_legacy_lifecycle_run_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    started: list[tuple[Path, str]] = []
    original_start = RunDirectory.start

    def start(cls: type[RunDirectory], target: Path, run_id: str) -> RunDirectory:
        started.append((target, run_id))
        return original_start(target, run_id)

    monkeypatch.setattr("synthetic.package_export.RunDirectory.start", classmethod(start))
    seed = 20260830
    patient_count = 2
    reference_time = "2026-08-30T00:00:00Z"
    output = tmp_path / "run"

    generate_smoke(
        descriptor_path=ROOT / "datapackage.json",
        output=output,
        patient_count=patient_count,
        seed=seed,
        reference_time=reference_time,
        software_revision="test-revision",
        reference=LinearTestReference(),
        derivation_oracle=IdentityPreservingTestDerivationOracle(),
        derivation_binding=test_derivation_binding(),
    )

    expected = hashlib.sha256(f"{seed}:{patient_count}:{reference_time}".encode()).hexdigest()[:12]
    assert started == [(output, expected)]


def test_smoke_generation_delegates_exact_rows_and_metadata_to_shared_package_lifecycle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}
    expected = tmp_path / "shared-result"

    def export(descriptor, base_rows, output, **kwargs):
        captured.update(
            descriptor=descriptor,
            base_rows=base_rows,
            output=output,
            metadata=kwargs["metadata"],
            oracle=kwargs["derivation_oracle"],
            binding=kwargs["derivation_binding"],
        )
        return expected

    monkeypatch.setattr("synthetic.generate.export_exact_schema_package", export)
    oracle = IdentityPreservingTestDerivationOracle()

    result = generate_smoke(
        descriptor_path=ROOT / "datapackage.json",
        output=tmp_path / "run",
        patient_count=2,
        seed=20260830,
        reference_time="2026-08-30T00:00:00Z",
        software_revision="test-revision",
        reference=LinearTestReference(),
        derivation_oracle=oracle,
        derivation_binding=test_derivation_binding(),
    )

    assert result == expected
    assert captured["output"] == tmp_path / "run"
    assert captured["oracle"] is oracle
    assert captured["binding"] == test_derivation_binding()
    assert isinstance(captured["metadata"], PackageExportMetadata)
    metadata = captured["metadata"]
    assert metadata.profile == "smoke"
    assert metadata.seed == 20260830
    assert metadata.reference_sha256 is None
    assert {name: len(rows) for name, rows in captured["base_rows"].items()} == {
        "patients": 2,
        "visits": 6,
        "labs": 0,
        "medications": 0,
        "problem_list": 0,
        "referrals": 0,
    }


def test_smoke_collision_is_detected_before_patient_row_generation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "run"
    output.mkdir()
    (output / "patients.csv").mkdir()
    generation_calls = 0

    def reject_generation(*args, **kwargs):
        nonlocal generation_calls
        generation_calls += 1
        raise AssertionError("smoke rows must not be generated for an existing target")

    monkeypatch.setattr("synthetic.generate.build_base_rows", reject_generation)

    with pytest.raises(FileExistsError):
        generate_smoke(
            descriptor_path=ROOT / "datapackage.json",
            output=output,
            patient_count=1,
            seed=20260830,
            reference_time="2026-08-30T00:00:00Z",
            software_revision="test-revision",
            reference=LinearTestReference(),
            derivation_oracle=IdentityPreservingTestDerivationOracle(),
            derivation_binding=test_derivation_binding(),
        )

    assert generation_calls == 0


def test_no_derivation_oracle_cannot_promote_output(tmp_path: Path) -> None:
    with pytest.raises(DerivationUnavailable):
        generate_smoke(
            descriptor_path=ROOT / "datapackage.json",
            output=tmp_path / "run",
            patient_count=1,
            seed=1,
            reference_time="2026-08-30T00:00:00Z",
            software_revision="test-revision",
            reference=LinearTestReference(),
            derivation_oracle=None,
            derivation_binding=test_derivation_binding(),
        )
    assert not (tmp_path / "run").exists()


def test_untrusted_derivation_identity_cannot_promote(tmp_path: Path) -> None:
    binding_mapping = test_derivation_binding().to_mapping()
    binding_mapping["oracle"]["implementation_fingerprint"] = "f" * 64
    mismatched_binding = type(test_derivation_binding()).from_mapping(binding_mapping)
    with pytest.raises(DerivationUnavailable):
        generate_smoke(
            descriptor_path=ROOT / "datapackage.json", output=tmp_path / "run",
            patient_count=1, seed=1, reference_time="2026-08-30T00:00:00Z",
            software_revision="test", reference=LinearTestReference(),
            derivation_oracle=IdentityPreservingTestDerivationOracle(),
            derivation_binding=mismatched_binding,
        )


def test_oracle_cannot_mutate_actual_partial(tmp_path: Path) -> None:
    output = tmp_path / "run"

    class Hostile(IdentityPreservingTestDerivationOracle):
        def derive(self, package_root: Path, descriptor: dict):
            result = super().derive(package_root, descriptor)
            partial = next(tmp_path.glob(".run.*.partial"))
            with (partial / "patients.csv").open("a") as handle:
                handle.write("tampered\n")
            return result

    with pytest.raises(DerivationUnavailable):
        generate_smoke(
            descriptor_path=ROOT / "datapackage.json", output=output,
            patient_count=1, seed=1, reference_time="2026-08-30T00:00:00Z",
            software_revision="test", reference=LinearTestReference(),
            derivation_oracle=Hostile(), derivation_binding=test_derivation_binding(),
        )
    assert not output.exists()


def test_oracle_test_only_classification_must_match_trusted_config(tmp_path: Path) -> None:
    class Mismatch(IdentityPreservingTestDerivationOracle):
        def derive(self, package_root: Path, descriptor: dict):
            result = super().derive(package_root, descriptor)
            return result.__class__(result.oracle_id, result.implementation_fingerprint, False)

    with pytest.raises(DerivationUnavailable):
        generate_smoke(
            descriptor_path=ROOT / "datapackage.json", output=tmp_path / "run",
            patient_count=1, seed=1, reference_time="2026-08-30T00:00:00Z",
            software_revision="test", reference=LinearTestReference(),
            derivation_oracle=Mismatch(), derivation_binding=test_derivation_binding(),
        )


def test_tree_scan_rejects_fifo(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "pipe")
    with pytest.raises(DerivationUnavailable):
        _scan_tree(tmp_path, {"data.csv"}, set())


def test_non_boolean_oracle_classification_fails_closed(tmp_path: Path) -> None:
    class Duck(IdentityPreservingTestDerivationOracle):
        def derive(self, package_root: Path, descriptor: dict):
            result = super().derive(package_root, descriptor)
            return type("Result", (), {"oracle_id": result.oracle_id,
                "implementation_fingerprint": result.implementation_fingerprint,
                "test_only": 1})()

    with pytest.raises(DerivationUnavailable):
        generate_smoke(
            descriptor_path=ROOT / "datapackage.json", output=tmp_path / "run",
            patient_count=1, seed=1, reference_time="2026-08-30T00:00:00Z",
            software_revision="test", reference=LinearTestReference(), derivation_oracle=Duck(),
            derivation_binding=test_derivation_binding(),
        )


def test_oracle_fifo_replacement_fails_before_hashing(tmp_path: Path) -> None:
    class Hostile(IdentityPreservingTestDerivationOracle):
        def derive(self, package_root: Path, descriptor: dict):
            result = super().derive(package_root, descriptor)
            path = package_root / "patients.csv"
            path.unlink()
            os.mkfifo(path)
            return result

    with pytest.raises(DerivationUnavailable):
        generate_smoke(
            descriptor_path=ROOT / "datapackage.json", output=tmp_path / "run",
            patient_count=1, seed=1, reference_time="2026-08-30T00:00:00Z",
            software_revision="test", reference=LinearTestReference(), derivation_oracle=Hostile(),
            derivation_binding=test_derivation_binding(),
        )


@pytest.mark.parametrize("mode", ["extra", "mutate"])
def test_derivation_cannot_write_extra_artifacts_or_mutate_base(tmp_path: Path, mode: str) -> None:
    class Hostile(IdentityPreservingTestDerivationOracle):
        def derive(self, package_root: Path, descriptor: dict):
            result = super().derive(package_root, descriptor)
            if mode == "extra":
                (package_root / "hidden.txt").write_text("secret")
            else:
                with (package_root / "patients.csv").open("a") as handle:
                    handle.write("tampered\n")
            return result

    with pytest.raises(DerivationUnavailable):
        generate_smoke(
            descriptor_path=ROOT / "datapackage.json", output=tmp_path / "run",
            patient_count=1, seed=1, reference_time="2026-08-30T00:00:00Z",
            software_revision="test", reference=LinearTestReference(),
            derivation_oracle=Hostile(),
            derivation_binding=test_derivation_binding(),
        )
    assert not (tmp_path / "run").exists()
