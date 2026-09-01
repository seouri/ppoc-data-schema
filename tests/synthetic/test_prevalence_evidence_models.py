from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from synthetic.prevalence_evidence import (
    PACKAGE_MANIFEST_MAX_BYTES,
    PackageIdentity,
    PrevalenceEvidenceConfig,
    PrevalenceEvidenceUnavailable,
    PrevalenceRunSpec,
    verify_package_identity,
)
from tests.synthetic.prevalence_evidence_fixtures import write_prevalence_package


def _runs(tmp_path: Path) -> tuple[PrevalenceRunSpec, ...]:
    return tuple(
        PrevalenceRunSpec(write_prevalence_package(tmp_path / f"run-{seed}", seed=seed), seed)
        for seed in (101, 102, 103)
    )


def test_run_spec_requires_path_and_nonboolean_seed(tmp_path: Path) -> None:
    package = write_prevalence_package(tmp_path / "package")
    with pytest.raises(TypeError, match="package_root"):
        PrevalenceRunSpec(str(package), 101)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="expected_seed"):
        PrevalenceRunSpec(package, True)


def test_evidence_config_requires_three_distinct_roots_and_seeds(tmp_path: Path) -> None:
    runs = _runs(tmp_path)
    with pytest.raises(ValueError, match="at least three"):
        PrevalenceEvidenceConfig(runs[:2])
    with pytest.raises(ValueError, match="expected_seed"):
        PrevalenceEvidenceConfig((runs[0], runs[1], PrevalenceRunSpec(runs[2].package_root, 101)))
    with pytest.raises(ValueError, match="package_root"):
        PrevalenceEvidenceConfig((runs[0], runs[1], PrevalenceRunSpec(runs[0].package_root, 103)))
    with pytest.raises(TypeError, match="heldout_template"):
        PrevalenceEvidenceConfig(runs, heldout_template=object())  # type: ignore[arg-type]


def test_verify_package_identity_binds_non_test_generated_manifest_and_exact_tree(tmp_path: Path) -> None:
    package = write_prevalence_package(tmp_path / "package", seed=789)

    identity = verify_package_identity(PrevalenceRunSpec(package, 789))

    assert isinstance(identity, PackageIdentity)
    assert identity.seed == 789
    assert identity.profile == "prevalence-fixture"
    assert identity.package_sha256 != identity.manifest_sha256
    assert set(identity.to_mapping()) == {
        "profile", "engine", "seed", "schema_fingerprint", "reference_time", "reference_id",
        "reference_sha256", "configuration_sha256", "software_revision", "prng_family",
        "seed_derivation_version", "derivation_fingerprint", "package_sha256", "manifest_sha256",
    }
    assert str(package) not in json.dumps(identity.to_mapping())


@pytest.mark.parametrize(
    ("mutation", "needle"),
    [
        ("unknown-key", "unavailable"),
        ("missing-key", "unavailable"),
        ("duplicate-key", "unavailable"),
        ("bom", "unavailable"),
        ("nonfinite", "unavailable"),
        ("wrong-status", "unavailable"),
        ("metadata-only", "unavailable"),
        ("wrong-version", "unavailable"),
        ("bad-digest", "unavailable"),
        ("bad-row-count", "unavailable"),
        ("outside-file", "unavailable"),
    ],
)
def test_verify_package_identity_rejects_noncanonical_manifest_inputs(
    tmp_path: Path, mutation: str, needle: str
) -> None:
    package = write_prevalence_package(tmp_path / "package")
    manifest_path = package / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if mutation == "unknown-key":
        payload["unknown"] = "value"
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    elif mutation == "missing-key":
        del payload["profile"]
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    elif mutation == "duplicate-key":
        manifest_path.write_text('{"manifest_version":"1","manifest_version":"1"}', encoding="utf-8")
    elif mutation == "bom":
        manifest_path.write_bytes(b"\xef\xbb\xbf" + json.dumps(payload).encode())
    elif mutation == "nonfinite":
        payload["seed"] = float("nan")
        manifest_path.write_text(json.dumps(payload, allow_nan=True), encoding="utf-8")
    elif mutation == "wrong-status":
        payload["status"] = "GENERATED_UNVALIDATED"
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    elif mutation == "metadata-only":
        payload["metadata_only"] = True
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    elif mutation == "wrong-version":
        payload["manifest_version"] = "2"
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    elif mutation == "bad-digest":
        payload["configuration_sha256"] = "bad"
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    elif mutation == "bad-row-count":
        payload["row_counts"]["patients"] = -1
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    else:
        payload["file_sha256"]["outside.csv"] = "a" * 64
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PrevalenceEvidenceUnavailable, match=needle):
        verify_package_identity(PrevalenceRunSpec(package, 101))


def test_verify_package_identity_rejects_test_only_and_expected_seed_mismatch(tmp_path: Path) -> None:
    test_only = write_prevalence_package(tmp_path / "test-only", test_only=True)
    with pytest.raises(PrevalenceEvidenceUnavailable, match="unavailable"):
        verify_package_identity(PrevalenceRunSpec(test_only, 101))

    package = write_prevalence_package(tmp_path / "mismatch")
    with pytest.raises(PrevalenceEvidenceUnavailable, match="unavailable"):
        verify_package_identity(PrevalenceRunSpec(package, 999))


def test_verify_package_identity_rejects_tampered_resource_and_extra_tree_entry(tmp_path: Path) -> None:
    package = write_prevalence_package(tmp_path / "tampered")
    (package / "patients.csv").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(PrevalenceEvidenceUnavailable, match="unavailable"):
        verify_package_identity(PrevalenceRunSpec(package, 101))

    extra = write_prevalence_package(tmp_path / "extra")
    (extra / "extra.txt").write_text("not allowed", encoding="utf-8")
    with pytest.raises(PrevalenceEvidenceUnavailable, match="unavailable"):
        verify_package_identity(PrevalenceRunSpec(extra, 101))


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="platform lacks symlink support")
def test_verify_package_identity_rejects_links_and_descriptor_schema_changes(tmp_path: Path) -> None:
    linked = write_prevalence_package(tmp_path / "linked")
    (linked / "patients.csv").unlink()
    (linked / "patients.csv").symlink_to(linked / "visits.csv")
    with pytest.raises(PrevalenceEvidenceUnavailable, match="unavailable"):
        verify_package_identity(PrevalenceRunSpec(linked, 101))

    hard_linked = write_prevalence_package(tmp_path / "hard-linked")
    (hard_linked / "duplicate.csv").hardlink_to(hard_linked / "patients.csv")
    with pytest.raises(PrevalenceEvidenceUnavailable, match="unavailable"):
        verify_package_identity(PrevalenceRunSpec(hard_linked, 101))

    mismatched = write_prevalence_package(tmp_path / "mismatched")
    descriptor_path = mismatched / "datapackage.json"
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    descriptor["resources"][0]["schema"]["fields"][0]["name"] = "wrong_patient_id"
    descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")
    with pytest.raises(PrevalenceEvidenceUnavailable, match="unavailable"):
        verify_package_identity(PrevalenceRunSpec(mismatched, 101))


def test_verify_package_identity_rejects_oversized_manifest(tmp_path: Path) -> None:
    package = write_prevalence_package(tmp_path / "large")
    (package / "manifest.json").write_bytes(b"{" + b" " * PACKAGE_MANIFEST_MAX_BYTES + b"}")
    with pytest.raises(PrevalenceEvidenceUnavailable, match="unavailable"):
        verify_package_identity(PrevalenceRunSpec(package, 101))
