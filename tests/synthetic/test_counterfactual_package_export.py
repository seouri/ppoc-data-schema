from __future__ import annotations

import csv
import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from synthetic import package_export
from synthetic.native.counterfactual import InterventionKind
from synthetic.native.counterfactual_worlds import (
    CounterfactualWorldValidationStatus,
    validate_counterfactual_ehr_worlds,
)
from synthetic.package_export import (
    CounterfactualPackageExportUnavailable,
    PackageExportMetadata,
    PackageExportUnavailable,
    export_counterfactual_ehr_world_pair,
)
from synthetic.schema_contract import EXPECTED_SCHEMA_FINGERPRINT, load_descriptor
from synthetic.validate import validate_structure
from tests.synthetic.fakes import IdentityPreservingTestDerivationOracle
from tests.synthetic.test_counterfactual_world_validation import _worlds

ROOT = Path(__file__).resolve().parents[2]
TRUSTED_FINGERPRINT = "0123456789abcdef" * 4


def _descriptor() -> dict:
    return load_descriptor(ROOT / "datapackage.json")


def _metadata() -> PackageExportMetadata:
    return PackageExportMetadata(
        profile="counterfactual-development",
        seed=20260831,
        reference_time="2026-08-31T00:00:00Z",
        reference_id="fictional-counterfactual-reference-v1",
        software_revision="test-revision",
        configuration_sha256="a" * 64,
        reference_sha256="b" * 64,
    )


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _csv_rows(package: Path, resource_name: str, descriptor: dict) -> list[dict[str, str]]:
    path = next(resource["path"] for resource in descriptor["resources"] if resource["name"] == resource_name)
    with (package / path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_export_pair_creates_two_exact_schema_packages_and_a_deterministic_aggregate_manifest(
    tmp_path: Path,
) -> None:
    descriptor = _descriptor()
    metadata = _metadata()
    worlds = _worlds(InterventionKind.PHYSIOLOGY_SEVERITY)
    report = validate_counterfactual_ehr_worlds(worlds)
    source_labs = worlds.baseline.bundle.rows["labs"]  # type: ignore[union-attr]
    assert source_labs and all(row.to_mapping()["result_flag"] == "Synthetic" for row in source_labs)

    result = export_counterfactual_ehr_world_pair(
        worlds,
        descriptor,
        tmp_path / "pair",
        metadata=metadata,
        derivation_oracle=IdentityPreservingTestDerivationOracle(),
        trusted_derivation_fingerprint=TRUSTED_FINGERPRINT,
        trusted_derivation_test_only=True,
    )
    replay = export_counterfactual_ehr_world_pair(
        worlds,
        descriptor,
        tmp_path / "pair-replay",
        metadata=metadata,
        derivation_oracle=IdentityPreservingTestDerivationOracle(),
        trusted_derivation_fingerprint=TRUSTED_FINGERPRINT,
        trusted_derivation_test_only=True,
    )

    assert result == tmp_path / "pair"
    assert issubclass(CounterfactualPackageExportUnavailable, PackageExportUnavailable)
    assert {path.name for path in result.iterdir()} == {
        "baseline",
        "intervention",
        "pair-manifest.json",
    }
    expected_package_files = {
        *(resource["path"] for resource in descriptor["resources"]),
        "datapackage.json",
        "validation-report.json",
        "manifest.json",
    }
    for child_name in ("baseline", "intervention"):
        child = result / child_name
        assert _tree_bytes(child).keys() == expected_package_files
        assert not validate_structure(child, descriptor).errors
        assert all(row["result_flag"] == "" for row in _csv_rows(child, "labs", descriptor))

    assert all(row.to_mapping()["result_flag"] == "Synthetic" for row in source_labs)

    manifest = json.loads((result / "pair-manifest.json").read_text(encoding="utf-8"))
    assert manifest == {
        "children": {
            "baseline": {
                "manifest_sha256": hashlib.sha256(
                    (result / "baseline" / "manifest.json").read_bytes()
                ).hexdigest(),
                "path": "baseline",
            },
            "intervention": {
                "manifest_sha256": hashlib.sha256(
                    (result / "intervention" / "manifest.json").read_bytes()
                ).hexdigest(),
                "path": "intervention",
            },
        },
        "contract": "counterfactual-ehr-package-pair-v1",
        "intervention": worlds.matrix.intervention.value,
        "matrix_version": worlds.matrix.version,
        "metadata": dataclasses.asdict(metadata),
        "schema_fingerprint": EXPECTED_SCHEMA_FINGERPRINT,
        "serialization_projection": "ghd-result-flag-empty-v1",
        "validation_check_counts": {"FAIL": 0, "PASS": 7, "UNEVALUABLE": 0},
        "validation_status": CounterfactualWorldValidationStatus.PASS.value,
    }
    assert report.status is CounterfactualWorldValidationStatus.PASS
    assert _tree_bytes(result) == _tree_bytes(replay)


def test_export_pair_archives_only_fixed_failure_content_after_copy_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_copytree = package_export.shutil.copytree

    def copy_then_fail(source: Path, destination: Path, *args: object, **kwargs: object) -> Path:
        original_copytree(source, destination, *args, **kwargs)
        (destination / "arbitrary-token.txt").write_text("raw-copy-failure-token", encoding="utf-8")
        raise RuntimeError("raw-copy-failure-token")

    monkeypatch.setattr(package_export.shutil, "copytree", copy_then_fail)

    with pytest.raises(
        CounterfactualPackageExportUnavailable, match="counterfactual package export failed"
    ):
        export_counterfactual_ehr_world_pair(
            _worlds(InterventionKind.PHYSIOLOGY_SEVERITY),
            _descriptor(),
            tmp_path / "pair",
            metadata=_metadata(),
            derivation_oracle=IdentityPreservingTestDerivationOracle(),
            trusted_derivation_fingerprint=TRUSTED_FINGERPRINT,
            trusted_derivation_test_only=True,
        )

    assert not (tmp_path / "pair").exists()
    failed = list(tmp_path.glob(".pair.*.failed"))
    assert len(failed) == 1
    assert [path.relative_to(failed[0]).as_posix() for path in failed[0].rglob("*")] == [
        "failure.json"
    ]
    assert json.loads((failed[0] / "failure.json").read_text(encoding="utf-8")) == {
        "reason": "counterfactual package export failed",
        "status": "FAILED",
    }
    assert b"raw-copy-failure-token" not in _tree_bytes(failed[0]).get("failure.json", b"")


def test_export_pair_clears_a_restrictive_copied_child_before_archiving_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_copytree = package_export.shutil.copytree

    def copy_restrict_then_fail(
        source: Path, destination: Path, *args: object, **kwargs: object
    ) -> Path:
        original_copytree(source, destination, *args, **kwargs)
        destination.chmod(0o555)
        raise RuntimeError("raw-restrictive-copy-failure-token")

    monkeypatch.setattr(package_export.shutil, "copytree", copy_restrict_then_fail)

    with pytest.raises(
        CounterfactualPackageExportUnavailable, match="counterfactual package export failed"
    ):
        export_counterfactual_ehr_world_pair(
            _worlds(InterventionKind.PHYSIOLOGY_SEVERITY),
            _descriptor(),
            tmp_path / "pair",
            metadata=_metadata(),
            derivation_oracle=IdentityPreservingTestDerivationOracle(),
            trusted_derivation_fingerprint=TRUSTED_FINGERPRINT,
            trusted_derivation_test_only=True,
        )

    assert not (tmp_path / "pair").exists()
    assert not list(tmp_path.glob(".pair.*.partial"))
    failed = list(tmp_path.glob(".pair.*.failed"))
    assert len(failed) == 1
    assert [path.relative_to(failed[0]).as_posix() for path in failed[0].rglob("*")] == [
        "failure.json"
    ]
    assert b"raw-restrictive-copy-failure-token" not in _tree_bytes(failed[0]).get(
        "failure.json", b""
    )


def test_export_pair_removes_the_empty_partial_when_failure_archiving_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_copytree = package_export.shutil.copytree

    def copy_then_fail(source: Path, destination: Path, *args: object, **kwargs: object) -> Path:
        original_copytree(source, destination, *args, **kwargs)
        raise RuntimeError("raw-copy-failure-token")

    def fail_archiving(*args: object, **kwargs: object) -> Path:
        raise OSError("raw-failure-archive-token")

    monkeypatch.setattr(package_export.shutil, "copytree", copy_then_fail)
    monkeypatch.setattr(package_export.RunDirectory, "fail", fail_archiving)

    with pytest.raises(
        CounterfactualPackageExportUnavailable, match="counterfactual package export failed"
    ):
        export_counterfactual_ehr_world_pair(
            _worlds(InterventionKind.PHYSIOLOGY_SEVERITY),
            _descriptor(),
            tmp_path / "pair",
            metadata=_metadata(),
            derivation_oracle=IdentityPreservingTestDerivationOracle(),
            trusted_derivation_fingerprint=TRUSTED_FINGERPRINT,
            trusted_derivation_test_only=True,
        )

    assert not (tmp_path / "pair").exists()
    assert not list(tmp_path.glob(".pair.*.partial"))
    assert not list(tmp_path.glob(".pair.*.failed"))
