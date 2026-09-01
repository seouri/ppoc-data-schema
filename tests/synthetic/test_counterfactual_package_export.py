from __future__ import annotations

import csv
import dataclasses
import hashlib
import json
import os
from pathlib import Path

import pytest

from synthetic import package_export
from synthetic.derivation import DerivationResult
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
from synthetic.schema_contract import (
    EXPECTED_SCHEMA_FINGERPRINT,
    load_descriptor,
    schema_fingerprint,
)
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


def _lifecycle_paths(root: Path, output: Path) -> list[Path]:
    return [
        path
        for path in root.iterdir()
        if path.name == output.name or path.name.startswith(f".{output.name}.")
    ]


def _assert_no_pair_output(root: Path, output: Path) -> None:
    assert _lifecycle_paths(root, output) == []


def _assert_failure_only(root: Path, output: Path, *secrets: str) -> None:
    assert not output.exists()
    assert not list(root.glob(f".{output.name}.*.partial"))
    failed = list(root.glob(f".{output.name}.*.failed"))
    assert len(failed) == 1
    assert [path.relative_to(failed[0]).as_posix() for path in failed[0].rglob("*")] == [
        "failure.json"
    ]
    public_text = (failed[0] / "failure.json").read_text(encoding="utf-8")
    assert json.loads(public_text) == {
        "reason": "counterfactual package export failed",
        "status": "FAILED",
    }
    assert all(secret not in public_text for secret in secrets)


class _RecordingOracle(IdentityPreservingTestDerivationOracle):
    def __init__(self) -> None:
        self.calls: list[tuple[Path, tuple[str, ...], dict]] = []

    def derive(self, package_root: Path, descriptor: dict) -> DerivationResult:
        visible_paths = tuple(
            path.relative_to(package_root).as_posix()
            for path in sorted(package_root.rglob("*"))
            if path.is_file()
        )
        self.calls.append((package_root, visible_paths, descriptor))
        return super().derive(package_root, descriptor)


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


def test_export_pair_clears_a_restrictive_partial_root_before_archiving_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_copytree = package_export.shutil.copytree

    def copy_restrict_root_then_fail(
        source: Path, destination: Path, *args: object, **kwargs: object
    ) -> Path:
        original_copytree(source, destination, *args, **kwargs)
        destination.parent.chmod(0o555)
        raise RuntimeError("raw-restrictive-root-copy-failure-token")

    monkeypatch.setattr(package_export.shutil, "copytree", copy_restrict_root_then_fail)

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
    assert b"raw-restrictive-root-copy-failure-token" not in _tree_bytes(failed[0]).get(
        "failure.json", b""
    )


@pytest.mark.parametrize(
    (
        "intervention",
        "changed_fields",
        "referral_changed",
    ),
    (
        (
            InterventionKind.PHYSIOLOGY_SEVERITY,
            {"weight_oz", "height_in", "BMI"},
            False,
        ),
        (
            InterventionKind.EARLIER_RECOGNITION,
            {"enc_diag_1", "enc_diag_2", "enc_diag_3"},
            True,
        ),
        (
            InterventionKind.TREATMENT_ADHERENCE,
            {"weight_oz", "height_in", "BMI"},
            False,
        ),
    ),
)
def test_export_pair_preserves_each_supported_visible_matrix_and_ghd_ancillary_rows(
    tmp_path: Path,
    intervention: InterventionKind,
    changed_fields: set[str],
    referral_changed: bool,
) -> None:
    """Catch dropped ancillary rows or a matrix-specific visible projection change."""
    worlds = _worlds(intervention)
    descriptor = _descriptor()
    result = export_counterfactual_ehr_world_pair(
        worlds,
        descriptor,
        tmp_path / intervention.value,
        metadata=_metadata(),
        derivation_oracle=IdentityPreservingTestDerivationOracle(),
        trusted_derivation_fingerprint=TRUSTED_FINGERPRINT,
        trusted_derivation_test_only=True,
    )

    assert len(_tree_bytes(result)) == 23
    for child_name, member in (("baseline", worlds.baseline), ("intervention", worlds.intervention)):
        assert member.bundle is not None
        child = result / child_name
        assert not validate_structure(child, descriptor).errors
        for resource_name in ("labs", "medications", "problem_list", "referrals"):
            source_rows = member.bundle.rows[resource_name]
            exported_rows = _csv_rows(child, resource_name, descriptor)
            assert source_rows
            assert len(exported_rows) == len(source_rows)
            source_mappings = [row.to_mapping() for row in source_rows]
            for identifier in ("patient_id", "visit_id"):
                if identifier in source_mappings[0]:
                    assert [row[identifier] for row in exported_rows] == [
                        str(row[identifier]) for row in source_mappings
                    ]
        assert all(row["result_flag"] == "" for row in _csv_rows(child, "labs", descriptor))

    baseline_visits = _csv_rows(result / "baseline", "visits", descriptor)
    intervention_visits = _csv_rows(result / "intervention", "visits", descriptor)
    observed_changed_fields = {
        field_name
        for baseline, intervention_row in zip(baseline_visits, intervention_visits, strict=True)
        for field_name in baseline
        if baseline[field_name] != intervention_row[field_name]
    }
    assert observed_changed_fields == changed_fields
    assert (
        _csv_rows(result / "baseline", "referrals", descriptor)
        != _csv_rows(result / "intervention", "referrals", descriptor)
    ) is referral_changed


def test_export_pair_calls_the_oracle_only_for_two_distinct_visible_child_staging_roots(
    tmp_path: Path,
) -> None:
    """Catch pair/frame/truth leakage or a changed child-export invocation count."""
    descriptor = _descriptor()
    oracle = _RecordingOracle()
    result = export_counterfactual_ehr_world_pair(
        _worlds(InterventionKind.PHYSIOLOGY_SEVERITY),
        descriptor,
        tmp_path / "pair",
        metadata=_metadata(),
        derivation_oracle=oracle,
        trusted_derivation_fingerprint=TRUSTED_FINGERPRINT,
        trusted_derivation_test_only=True,
    )

    expected_paths = tuple(
        sorted(resource["path"] for resource in descriptor["resources"] if not resource["name"].endswith("_augmented"))
    )
    assert not validate_structure(result / "baseline", descriptor).errors
    assert not validate_structure(result / "intervention", descriptor).errors
    assert len(oracle.calls) == 2
    assert oracle.calls[0][0] != oracle.calls[1][0]
    assert [visible_paths for _, visible_paths, _ in oracle.calls] == [expected_paths, expected_paths]
    assert all(received_descriptor is not descriptor for _, _, received_descriptor in oracle.calls)
    assert all(
        schema_fingerprint(received_descriptor) == EXPECTED_SCHEMA_FINGERPRINT
        for _, _, received_descriptor in oracle.calls
    )


@pytest.mark.parametrize(
    "case",
    (
        "unevaluable_world",
        "failed_world",
        "malformed_bundle",
        "missing_bundle",
        "descriptor",
        "oracle",
        "fingerprint",
        "classification",
    ),
)
def test_export_pair_rejects_invalid_precreation_inputs_without_public_lifecycle_artifacts(
    tmp_path: Path, case: str
) -> None:
    """Catch any invalid input that reaches the public pair lifecycle."""
    worlds = _worlds(InterventionKind.PHYSIOLOGY_SEVERITY)
    descriptor = _descriptor()
    kwargs: dict[str, object] = {
        "metadata": _metadata(),
        "derivation_oracle": IdentityPreservingTestDerivationOracle(),
        "trusted_derivation_fingerprint": TRUSTED_FINGERPRINT,
        "trusted_derivation_test_only": True,
    }
    if case == "unevaluable_world":
        object.__setattr__(worlds.intervention.frame, "truth", None)
    elif case == "failed_world":
        row = worlds.intervention.bundle.rows["visits"][0]  # type: ignore[union-attr]
        object.__setattr__(
            row,
            "values",
            tuple((name, "syn-unlinked" if name == "visit_id" else value) for name, value in row.values),
        )
    elif case == "malformed_bundle":
        object.__setattr__(worlds.baseline, "bundle", object())
    elif case == "missing_bundle":
        object.__setattr__(worlds.baseline, "bundle", None)
    elif case == "descriptor":
        descriptor["resources"].pop()
    elif case == "oracle":
        kwargs["derivation_oracle"] = None
    elif case == "fingerprint":
        kwargs["trusted_derivation_fingerprint"] = "invalid-fingerprint"
    else:
        kwargs["trusted_derivation_test_only"] = 1

    output = tmp_path / f"invalid-{case}"
    with pytest.raises(
        CounterfactualPackageExportUnavailable, match="counterfactual package export failed"
    ):
        export_counterfactual_ehr_world_pair(worlds, descriptor, output, **kwargs)  # type: ignore[arg-type]
    _assert_no_pair_output(tmp_path, output)


def test_export_pair_rejects_existing_output_without_overwriting(tmp_path: Path) -> None:
    output = tmp_path / "pair"
    output.mkdir()
    (output / "keep.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        export_counterfactual_ehr_world_pair(
            _worlds(InterventionKind.PHYSIOLOGY_SEVERITY),
            _descriptor(),
            output,
            metadata=_metadata(),
            derivation_oracle=IdentityPreservingTestDerivationOracle(),
            trusted_derivation_fingerprint=TRUSTED_FINGERPRINT,
            trusted_derivation_test_only=True,
        )

    assert (output / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_export_pair_rejects_deterministic_lifecycle_collision_before_oracle_calls(
    tmp_path: Path,
) -> None:
    """Catch a lifecycle collision that needlessly derives private child packages."""
    worlds = _worlds(InterventionKind.PHYSIOLOGY_SEVERITY)
    output = tmp_path / "pair"
    run_id = package_export._pair_run_id(_metadata(), worlds)
    collision = tmp_path / f".{output.name}.{run_id}.partial"
    collision.mkdir()
    oracle = _RecordingOracle()

    with pytest.raises(FileExistsError):
        export_counterfactual_ehr_world_pair(
            worlds,
            _descriptor(),
            output,
            metadata=_metadata(),
            derivation_oracle=oracle,
            trusted_derivation_fingerprint=TRUSTED_FINGERPRINT,
            trusted_derivation_test_only=True,
        )

    assert oracle.calls == []
    assert collision.is_dir()


@pytest.mark.parametrize("tree_change", ("extra", "symlink", "special", "missing"))
def test_export_pair_archives_only_fixed_failure_content_after_copied_tree_rejection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tree_change: str
) -> None:
    """Catch a copied tree that is not the exact regular-file pair inventory."""
    original_copytree = package_export.shutil.copytree
    copy_count = 0

    def copy_then_poison(source: Path, destination: Path, *args: object, **kwargs: object) -> Path:
        nonlocal copy_count
        copied = original_copytree(source, destination, *args, **kwargs)
        copy_count += 1
        if copy_count == 2:
            if tree_change == "extra":
                (destination.parent / "unapproved-token.txt").write_text("hidden-tree-token", encoding="utf-8")
            elif tree_change == "symlink":
                (destination.parent / "unapproved-link").symlink_to(destination / "patients.csv")
            elif tree_change == "special":
                os.mkfifo(destination.parent / "unapproved-fifo")
            else:
                (destination / "patients.csv").unlink()
        return copied

    monkeypatch.setattr(package_export.shutil, "copytree", copy_then_poison)
    output = tmp_path / "pair"
    with pytest.raises(
        CounterfactualPackageExportUnavailable, match="counterfactual package export failed"
    ):
        export_counterfactual_ehr_world_pair(
            _worlds(InterventionKind.PHYSIOLOGY_SEVERITY),
            _descriptor(),
            output,
            metadata=_metadata(),
            derivation_oracle=IdentityPreservingTestDerivationOracle(),
            trusted_derivation_fingerprint=TRUSTED_FINGERPRINT,
            trusted_derivation_test_only=True,
        )

    _assert_failure_only(tmp_path, output, "hidden-tree-token")


def test_export_pair_redacts_post_creation_pair_manifest_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Catch a post-creation exception that leaks hidden content through a failed archive."""
    raw_token = "patient-visit-truth-frame-source-temporary-token"

    def manifest_failure(*args: object, **kwargs: object) -> dict[str, object]:
        del args, kwargs
        raise RuntimeError(raw_token)

    monkeypatch.setattr(package_export, "_pair_manifest", manifest_failure)
    output = tmp_path / "pair"
    with pytest.raises(
        CounterfactualPackageExportUnavailable, match="counterfactual package export failed"
    ) as error:
        export_counterfactual_ehr_world_pair(
            _worlds(InterventionKind.PHYSIOLOGY_SEVERITY),
            _descriptor(),
            output,
            metadata=_metadata(),
            derivation_oracle=IdentityPreservingTestDerivationOracle(),
            trusted_derivation_fingerprint=TRUSTED_FINGERPRINT,
            trusted_derivation_test_only=True,
        )

    assert raw_token not in str(error.value)
    _assert_failure_only(tmp_path, output, raw_token)
