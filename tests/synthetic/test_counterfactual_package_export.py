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
from tests.synthetic.fakes import (
    IdentityPreservingTestDerivationOracle,
    test_derivation_binding,
)
from tests.synthetic.test_counterfactual_world_validation import _worlds

ROOT = Path(__file__).resolve().parents[2]


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
        derivation_binding=test_derivation_binding(),
    )
    replay = export_counterfactual_ehr_world_pair(
        worlds,
        descriptor,
        tmp_path / "pair-replay",
        metadata=metadata,
        derivation_oracle=IdentityPreservingTestDerivationOracle(),
        derivation_binding=test_derivation_binding(),
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
    original_copy = package_export._copy_pair_child_at

    def copy_then_fail(
        source: Path,
        directory_descriptor: int,
        child_name: str,
        files: set[str],
        dirs: set[str],
    ) -> None:
        original_copy(source, directory_descriptor, child_name, files, dirs)
        package_export._write_regular_at(
            directory_descriptor,
            f"{child_name}/arbitrary-token.txt",
            b"raw-copy-failure-token",
        )
        raise RuntimeError("raw-copy-failure-token")

    monkeypatch.setattr(package_export, "_copy_pair_child_at", copy_then_fail)

    with pytest.raises(
        CounterfactualPackageExportUnavailable, match="counterfactual package export failed"
    ):
        export_counterfactual_ehr_world_pair(
            _worlds(InterventionKind.PHYSIOLOGY_SEVERITY),
            _descriptor(),
            tmp_path / "pair",
            metadata=_metadata(),
            derivation_oracle=IdentityPreservingTestDerivationOracle(),
            derivation_binding=test_derivation_binding(),
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
    original_copy = package_export._copy_pair_child_at

    def copy_restrict_then_fail(
        source: Path,
        directory_descriptor: int,
        child_name: str,
        files: set[str],
        dirs: set[str],
    ) -> None:
        original_copy(source, directory_descriptor, child_name, files, dirs)
        child_descriptor = package_export._open_relative_directory_at(
            directory_descriptor, child_name
        )
        try:
            os.fchmod(child_descriptor, 0o555)
        finally:
            os.close(child_descriptor)
        raise RuntimeError("raw-restrictive-copy-failure-token")

    monkeypatch.setattr(package_export, "_copy_pair_child_at", copy_restrict_then_fail)

    with pytest.raises(
        CounterfactualPackageExportUnavailable, match="counterfactual package export failed"
    ):
        export_counterfactual_ehr_world_pair(
            _worlds(InterventionKind.PHYSIOLOGY_SEVERITY),
            _descriptor(),
            tmp_path / "pair",
            metadata=_metadata(),
            derivation_oracle=IdentityPreservingTestDerivationOracle(),
            derivation_binding=test_derivation_binding(),
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
    original_copy = package_export._copy_pair_child_at
    original_rename = package_export._rename_pair_directory_at

    def copy_then_fail(
        source: Path,
        directory_descriptor: int,
        child_name: str,
        files: set[str],
        dirs: set[str],
    ) -> None:
        original_copy(source, directory_descriptor, child_name, files, dirs)
        raise RuntimeError("raw-copy-failure-token")

    def fail_archiving(
        parent_descriptor: int,
        source: str,
        target: str,
        expected_source_identity: tuple[int, int],
        expected_parent_path: Path,
        expected_parent_identity: tuple[int, int],
    ) -> None:
        if target.endswith(".failed"):
            raise OSError("raw-failure-archive-token")
        original_rename(
            parent_descriptor,
            source,
            target,
            expected_source_identity,
            expected_parent_path,
            expected_parent_identity,
        )

    monkeypatch.setattr(package_export, "_copy_pair_child_at", copy_then_fail)
    monkeypatch.setattr(package_export, "_rename_pair_directory_at", fail_archiving)

    with pytest.raises(
        CounterfactualPackageExportUnavailable, match="counterfactual package export failed"
    ):
        export_counterfactual_ehr_world_pair(
            _worlds(InterventionKind.PHYSIOLOGY_SEVERITY),
            _descriptor(),
            tmp_path / "pair",
            metadata=_metadata(),
            derivation_oracle=IdentityPreservingTestDerivationOracle(),
            derivation_binding=test_derivation_binding(),
        )

    assert not (tmp_path / "pair").exists()
    assert not list(tmp_path.glob(".pair.*.partial"))
    assert not list(tmp_path.glob(".pair.*.failed"))


def test_export_pair_clears_a_restrictive_partial_root_before_archiving_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_copy = package_export._copy_pair_child_at

    def copy_restrict_root_then_fail(
        source: Path,
        directory_descriptor: int,
        child_name: str,
        files: set[str],
        dirs: set[str],
    ) -> None:
        original_copy(source, directory_descriptor, child_name, files, dirs)
        os.fchmod(directory_descriptor, 0o555)
        raise RuntimeError("raw-restrictive-root-copy-failure-token")

    monkeypatch.setattr(package_export, "_copy_pair_child_at", copy_restrict_root_then_fail)

    with pytest.raises(
        CounterfactualPackageExportUnavailable, match="counterfactual package export failed"
    ):
        export_counterfactual_ehr_world_pair(
            _worlds(InterventionKind.PHYSIOLOGY_SEVERITY),
            _descriptor(),
            tmp_path / "pair",
            metadata=_metadata(),
            derivation_oracle=IdentityPreservingTestDerivationOracle(),
            derivation_binding=test_derivation_binding(),
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
        derivation_binding=test_derivation_binding(),
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
        derivation_binding=test_derivation_binding(),
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
        "binding_none",
        "binding_object",
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
        "derivation_binding": test_derivation_binding(),
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
    elif case == "binding_none":
        kwargs["derivation_binding"] = None
    else:
        kwargs["derivation_binding"] = object()

    output = tmp_path / f"invalid-{case}"
    with pytest.raises(
        CounterfactualPackageExportUnavailable, match="counterfactual package export failed"
    ):
        export_counterfactual_ehr_world_pair(worlds, descriptor, output, **kwargs)  # type: ignore[arg-type]
    _assert_no_pair_output(tmp_path, output)


def test_export_pair_rejects_incomplete_non_test_binding_before_private_staging(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    mapping = test_derivation_binding().to_mapping()
    mapping["test_only"] = False
    incomplete_binding = type(test_derivation_binding()).from_mapping(mapping)
    temporary_calls = 0

    class RejectTemporaryDirectory:
        def __init__(self, **kwargs: object) -> None:
            nonlocal temporary_calls
            del kwargs
            temporary_calls += 1
            raise AssertionError("private staging must not start")

    monkeypatch.setattr(
        package_export.tempfile,
        "TemporaryDirectory",
        RejectTemporaryDirectory,
    )

    with pytest.raises(
        CounterfactualPackageExportUnavailable,
        match="counterfactual package export failed",
    ):
        export_counterfactual_ehr_world_pair(
            _worlds(InterventionKind.PHYSIOLOGY_SEVERITY),
            _descriptor(),
            tmp_path / "pair",
            metadata=_metadata(),
            derivation_oracle=IdentityPreservingTestDerivationOracle(),
            derivation_binding=incomplete_binding,
        )

    assert temporary_calls == 0
    _assert_no_pair_output(tmp_path, tmp_path / "pair")


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
            derivation_binding=test_derivation_binding(),
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
            derivation_binding=test_derivation_binding(),
        )

    assert oracle.calls == []
    assert collision.is_dir()


@pytest.mark.parametrize("tree_change", ("extra", "symlink", "special", "missing"))
def test_export_pair_archives_only_fixed_failure_content_after_copied_tree_rejection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tree_change: str
) -> None:
    """Catch a copied tree that is not the exact regular-file pair inventory."""
    original_copy = package_export._copy_pair_child_at
    copy_count = 0

    def copy_then_poison(
        source: Path,
        directory_descriptor: int,
        child_name: str,
        files: set[str],
        dirs: set[str],
    ) -> None:
        nonlocal copy_count
        original_copy(source, directory_descriptor, child_name, files, dirs)
        copy_count += 1
        if copy_count == 2:
            if tree_change == "extra":
                package_export._write_regular_at(
                    directory_descriptor,
                    "unapproved-token.txt",
                    b"hidden-tree-token",
                )
            elif tree_change == "symlink":
                os.symlink(
                    f"{child_name}/patients.csv",
                    "unapproved-link",
                    dir_fd=directory_descriptor,
                )
            elif tree_change == "special":
                os.mkfifo("unapproved-fifo", dir_fd=directory_descriptor)
            else:
                child_descriptor = package_export._open_relative_directory_at(
                    directory_descriptor, child_name
                )
                try:
                    os.unlink("patients.csv", dir_fd=child_descriptor)
                finally:
                    os.close(child_descriptor)

    monkeypatch.setattr(package_export, "_copy_pair_child_at", copy_then_poison)
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
            derivation_binding=test_derivation_binding(),
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
            derivation_binding=test_derivation_binding(),
        )

    assert raw_token not in str(error.value)
    _assert_failure_only(tmp_path, output, raw_token)


def test_export_pair_rejects_a_manifest_replaced_after_the_path_scan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Catch a post-scan replacement that would publish an out-of-envelope symlink."""
    original_scan = package_export._scan_exact_tree
    outside = tmp_path / "outside.txt"
    outside.write_text("outside-envelope-token", encoding="utf-8")

    def scan_then_replace(root: Path, files: set[str], dirs: set[str]) -> None:
        original_scan(root, files, dirs)
        manifest = root / "pair-manifest.json"
        manifest.unlink()
        manifest.symlink_to(outside)

    monkeypatch.setattr(package_export, "_scan_exact_tree", scan_then_replace)
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
            derivation_binding=test_derivation_binding(),
        )

    assert not output.exists()
    assert outside.read_text(encoding="utf-8") == "outside-envelope-token"
    assert not any(path.is_symlink() for path in _lifecycle_paths(tmp_path, output))


def test_export_pair_cleans_the_original_partial_inode_after_name_replacement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Catch cleanup reopening a replacement while the original child package remains."""
    original_scan = package_export._scan_exact_tree
    moved = tmp_path / "moved-original"

    def scan_then_move_and_fail(root: Path, files: set[str], dirs: set[str]) -> None:
        original_scan(root, files, dirs)
        root.rename(moved)
        root.mkdir()
        raise RuntimeError("moved-partial-token")

    monkeypatch.setattr(package_export, "_scan_exact_tree", scan_then_move_and_fail)
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
            derivation_binding=test_derivation_binding(),
        )

    assert not output.exists()
    assert not moved.exists()
    assert _lifecycle_paths(tmp_path, output) == []


def test_export_pair_never_follows_a_failure_file_injected_after_cleanup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Catch failure archival following a same-name symlink outside the lifecycle tree."""
    original_scan = package_export._scan_exact_tree
    original_clear = package_export._clear_pair_partial_tree
    external = tmp_path / "external.txt"
    external.write_text("external-file-token", encoding="utf-8")
    injected = False

    def scan_then_fail(root: Path, files: set[str], dirs: set[str]) -> None:
        original_scan(root, files, dirs)
        raise RuntimeError("trigger-failure-archive")

    def clear_then_inject(path: Path, *args: object) -> None:
        nonlocal injected
        original_clear(path, *args)
        if not injected:
            (path / "failure.json").symlink_to(external)
            injected = True

    monkeypatch.setattr(package_export, "_scan_exact_tree", scan_then_fail)
    monkeypatch.setattr(package_export, "_clear_pair_partial_tree", clear_then_inject)
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
            derivation_binding=test_derivation_binding(),
        )

    assert injected
    assert external.read_text(encoding="utf-8") == "external-file-token"
    assert not output.exists()
    for lifecycle in _lifecycle_paths(tmp_path, output):
        assert not (lifecycle / "failure.json").is_symlink()


def test_export_pair_completes_private_staging_cleanup_before_promotion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Catch a private cleanup failure being reported after a public target was promoted."""
    original_temporary_directory = package_export.tempfile.TemporaryDirectory

    class CleanupFailure:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self._wrapped = original_temporary_directory(*args, **kwargs)
            self._fail = kwargs.get("prefix") == "counterfactual-package-export-"

        def __enter__(self) -> str:
            return self._wrapped.__enter__()

        def __exit__(self, *args: object) -> bool | None:
            result = self._wrapped.__exit__(*args)
            if self._fail:
                raise OSError("private-cleanup-token")
            return result

    monkeypatch.setattr(package_export.tempfile, "TemporaryDirectory", CleanupFailure)
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
            derivation_binding=test_derivation_binding(),
        )

    assert not output.exists()


def test_export_pair_metadata_subclass_cannot_expand_visible_metadata(
    tmp_path: Path,
) -> None:
    """Catch dataclass subclass fields entering the run token or public manifest."""

    @dataclasses.dataclass(frozen=True)
    class ExtendedMetadata(PackageExportMetadata):
        truth: str = "hidden-patient-truth-token"

    base = _metadata()
    metadata = ExtendedMetadata(**dataclasses.asdict(base))
    worlds = _worlds(InterventionKind.PHYSIOLOGY_SEVERITY)
    assert package_export._pair_run_id(metadata, worlds) == package_export._pair_run_id(base, worlds)

    result = export_counterfactual_ehr_world_pair(
        worlds,
        _descriptor(),
        tmp_path / "pair",
        metadata=metadata,
        derivation_oracle=IdentityPreservingTestDerivationOracle(),
        derivation_binding=test_derivation_binding(),
    )

    manifest = json.loads((result / "pair-manifest.json").read_text(encoding="utf-8"))
    assert manifest["metadata"] == dataclasses.asdict(base)
    assert "hidden-patient-truth-token" not in (result / "pair-manifest.json").read_text(
        encoding="utf-8"
    )


def test_export_pair_start_race_raises_a_path_free_collision(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Catch the check/mkdir race leaking the absolute partial path."""
    original_mkdir = Path.mkdir
    injected = False

    def mkdir_with_competitor(path: Path, *args: object, **kwargs: object) -> None:
        nonlocal injected
        if (
            path.parent == tmp_path
            and path.name.startswith(".pair.")
            and path.name.endswith(".partial")
            and not injected
        ):
            original_mkdir(path, *args, **kwargs)
            injected = True
        original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mkdir_with_competitor)

    with pytest.raises(FileExistsError) as error:
        export_counterfactual_ehr_world_pair(
            _worlds(InterventionKind.PHYSIOLOGY_SEVERITY),
            _descriptor(),
            tmp_path / "pair",
            metadata=_metadata(),
            derivation_oracle=IdentityPreservingTestDerivationOracle(),
            derivation_binding=test_derivation_binding(),
        )

    assert injected
    assert str(tmp_path) not in str(error.value)
    assert str(error.value) == "run directory lifecycle path already exists"


def test_export_pair_promotion_rechecks_source_identity_inside_rename(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Catch a same-name attacker directory inserted at the promotion handoff."""
    original_rename = package_export._rename_pair_directory_at
    moved = tmp_path / "moved-promotion-owner"
    injected = False

    def rename_after_swap(
        parent_descriptor: int,
        source_name: str,
        destination_name: str,
        expected_source_identity: tuple[int, int],
        expected_parent_path: Path,
        expected_parent_identity: tuple[int, int],
    ) -> None:
        nonlocal injected
        if destination_name == "pair" and not injected:
            os.rename(
                source_name,
                moved.name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
            os.mkdir(source_name, dir_fd=parent_descriptor)
            injected = True
        original_rename(
            parent_descriptor,
            source_name,
            destination_name,
            expected_source_identity,
            expected_parent_path,
            expected_parent_identity,
        )

    monkeypatch.setattr(package_export, "_rename_pair_directory_at", rename_after_swap)
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
            derivation_binding=test_derivation_binding(),
        )

    assert injected
    assert not output.exists()
    assert not moved.exists()
    assert _lifecycle_paths(tmp_path, output) == []


def test_export_pair_failure_archive_rechecks_source_identity_inside_rename(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Catch a same-name attacker directory inserted at the archive handoff."""
    original_scan = package_export._scan_exact_tree
    original_rename = package_export._rename_pair_directory_at
    moved = tmp_path / "moved-archive-owner"
    injected = False

    def scan_then_fail(root: Path, files: set[str], dirs: set[str]) -> None:
        original_scan(root, files, dirs)
        raise RuntimeError("archive-handoff-trigger")

    def rename_after_swap(
        parent_descriptor: int,
        source_name: str,
        destination_name: str,
        expected_source_identity: tuple[int, int],
        expected_parent_path: Path,
        expected_parent_identity: tuple[int, int],
    ) -> None:
        nonlocal injected
        if destination_name.endswith(".failed") and not injected:
            os.rename(
                source_name,
                moved.name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
            os.mkdir(source_name, dir_fd=parent_descriptor)
            injected = True
        original_rename(
            parent_descriptor,
            source_name,
            destination_name,
            expected_source_identity,
            expected_parent_path,
            expected_parent_identity,
        )

    monkeypatch.setattr(package_export, "_scan_exact_tree", scan_then_fail)
    monkeypatch.setattr(package_export, "_rename_pair_directory_at", rename_after_swap)
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
            derivation_binding=test_derivation_binding(),
        )

    assert injected
    assert not output.exists()
    assert not moved.exists()
    assert _lifecycle_paths(tmp_path, output) == []


def test_export_pair_rebinds_the_promoted_root_to_the_visible_parent_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Catch success returning an attacker target after the pinned parent was moved."""
    original_rename = package_export._rename_pair_directory_at
    visible_parent = tmp_path / "destination"
    moved_parent = tmp_path / "moved-parent"
    output = visible_parent / "pair"
    injected = False

    def rename_after_parent_swap(
        parent_descriptor: int,
        source_name: str,
        destination_name: str,
        expected_source_identity: tuple[int, int],
        expected_parent_path: Path,
        expected_parent_identity: tuple[int, int],
    ) -> None:
        nonlocal injected
        if destination_name == output.name and not injected:
            visible_parent.rename(moved_parent)
            visible_parent.mkdir()
            output.mkdir()
            (output / "attacker.txt").write_text("attacker-parent-token", encoding="utf-8")
            injected = True
        original_rename(
            parent_descriptor,
            source_name,
            destination_name,
            expected_source_identity,
            expected_parent_path,
            expected_parent_identity,
        )

    monkeypatch.setattr(package_export, "_rename_pair_directory_at", rename_after_parent_swap)

    with pytest.raises(
        CounterfactualPackageExportUnavailable, match="counterfactual package export failed"
    ):
        export_counterfactual_ehr_world_pair(
            _worlds(InterventionKind.PHYSIOLOGY_SEVERITY),
            _descriptor(),
            output,
            metadata=_metadata(),
            derivation_oracle=IdentityPreservingTestDerivationOracle(),
            derivation_binding=test_derivation_binding(),
        )

    assert injected
    assert (output / "attacker.txt").read_text(encoding="utf-8") == "attacker-parent-token"
    assert not (moved_parent / output.name).exists()
