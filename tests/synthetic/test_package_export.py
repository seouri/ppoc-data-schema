import copy
import dataclasses
import json
import shutil
from pathlib import Path
from types import MappingProxyType

import pytest

from synthetic.base_resources import build_base_rows
from synthetic.derivation import DerivationResult
from synthetic.models import LatentPoint, PatientState
from synthetic.package_export import (
    PackageExportMetadata,
    PackageExportUnavailable,
    export_exact_schema_package,
)
from synthetic.schema_contract import (
    EXPECTED_SCHEMA_FINGERPRINT,
    load_descriptor,
    schema_fingerprint,
)
from synthetic.validate import validate_structure
from tests.synthetic.fakes import IdentityPreservingTestDerivationOracle

ROOT = Path(__file__).resolve().parents[2]
TRUSTED_FINGERPRINT = "0123456789abcdef" * 4
PATIENT_TOKEN = "visible-patient-token"
VISIT_TOKEN = "visible-visit-token"
_DEFAULT = object()


def _descriptor() -> dict:
    return load_descriptor(ROOT / "datapackage.json")


def _metadata(**changes: object) -> PackageExportMetadata:
    values: dict[str, object] = {
        "profile": "observed-development",
        "seed": 20260831,
        "reference_time": "2026-08-31T00:00:00Z",
        "reference_id": "fictional-observed-reference-v1",
        "software_revision": "test-revision",
        "configuration_sha256": "a" * 64,
        "reference_sha256": "b" * 64,
    }
    values.update(changes)
    return PackageExportMetadata(**values)


def _base_rows(descriptor: dict) -> dict[str, list[dict[str, object]]]:
    return build_base_rows(
        descriptor,
        PatientState(PATIENT_TOKEN, "F", "F"),
        (
            LatentPoint(
                patient_id=PATIENT_TOKEN,
                age_days=1095,
                height_cm=100.0,
                bmi=16.0,
                weight_kg=16.0,
                height_z=0.0,
                bmi_z=0.0,
            ),
        ),
        seed=20260831,
    )


def _export(
    tmp_path: Path,
    *,
    descriptor: dict | None = None,
    base_rows: dict[str, list[dict[str, object]]] | None = None,
    output_name: str = "package",
    metadata: PackageExportMetadata | None = None,
    derivation_oracle: object = _DEFAULT,
    trusted_derivation_fingerprint: str = TRUSTED_FINGERPRINT,
    trusted_derivation_test_only: bool = True,
) -> Path:
    descriptor = _descriptor() if descriptor is None else descriptor
    return export_exact_schema_package(
        descriptor,
        _base_rows(descriptor) if base_rows is None else base_rows,
        tmp_path / output_name,
        metadata=_metadata() if metadata is None else metadata,
        derivation_oracle=(
            IdentityPreservingTestDerivationOracle()
            if derivation_oracle is _DEFAULT
            else derivation_oracle
        ),
        trusted_derivation_fingerprint=trusted_derivation_fingerprint,
        trusted_derivation_test_only=trusted_derivation_test_only,
    )


def _package_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _lifecycle_paths(tmp_path: Path, output_name: str = "package") -> list[Path]:
    return [path for path in tmp_path.iterdir() if path.name == output_name or path.name.startswith(f".{output_name}.")]


def test_metadata_has_exact_immutable_public_fields() -> None:
    assert tuple(field.name for field in dataclasses.fields(PackageExportMetadata)) == (
        "profile",
        "seed",
        "reference_time",
        "reference_id",
        "software_revision",
        "configuration_sha256",
        "reference_sha256",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        _metadata().profile = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"profile": ""}, "profile"),
        ({"reference_time": "line\nbreak"}, "reference_time"),
        ({"reference_id": ""}, "reference_id"),
        ({"software_revision": " "}, "software_revision"),
        ({"seed": True}, "seed"),
        ({"configuration_sha256": "0" * 64}, "configuration_sha256"),
        ({"configuration_sha256": "A" * 64}, "configuration_sha256"),
        ({"reference_sha256": "not-a-digest"}, "reference_sha256"),
    ],
)
def test_metadata_rejects_invalid_tokens_and_digests(
    changes: dict[str, object], error: str
) -> None:
    with pytest.raises((TypeError, ValueError), match=error):
        _metadata(**changes)


def test_checked_in_fingerprint_is_exported_contract() -> None:
    assert EXPECTED_SCHEMA_FINGERPRINT == "795724ec4838df8afa9c09b7c059fa76f644d7f8fb6dcc8ce808da203c2f8597"
    assert schema_fingerprint(_descriptor()) == EXPECTED_SCHEMA_FINGERPRINT


def test_export_copies_json_compatible_descriptor_without_mutating_caller(tmp_path: Path) -> None:
    descriptor = _descriptor()
    original = copy.deepcopy(descriptor)

    _export(tmp_path, descriptor=MappingProxyType(descriptor))

    assert descriptor == original


def test_export_does_not_publish_unfingerprinted_descriptor_metadata(tmp_path: Path) -> None:
    descriptor = _descriptor()
    secrets = ("source-frame-token", "truth-token", "evaluator-artifact-token")
    descriptor["name"] = secrets[0]
    descriptor["provenance"] = secrets[1]
    descriptor["resources"][0]["evaluatorArtifact"] = secrets[2]
    assert schema_fingerprint(descriptor) == EXPECTED_SCHEMA_FINGERPRINT

    package = _export(tmp_path, descriptor=descriptor)

    serialized_package = b"".join(_package_bytes(package).values()).decode("utf-8")
    assert all(secret not in serialized_package for secret in secrets)


@pytest.mark.parametrize("mutation", ["missing", "unknown", "field-order", "unsafe-path"])
def test_export_rejects_nonexact_or_unsafe_descriptors_before_lifecycle(
    tmp_path: Path, mutation: str
) -> None:
    descriptor = _descriptor()
    if mutation == "missing":
        descriptor["resources"].pop()
    elif mutation == "unknown":
        descriptor["resources"].append(copy.deepcopy(descriptor["resources"][0]))
        descriptor["resources"][-1]["name"] = "unknown"
        descriptor["resources"][-1]["path"] = "unknown.csv"
    elif mutation == "field-order":
        descriptor["resources"][0]["schema"]["fields"][:2] = reversed(
            descriptor["resources"][0]["schema"]["fields"][:2]
        )
    else:
        descriptor["resources"][0]["path"] = "../outside.csv"

    with pytest.raises(PackageExportUnavailable):
        _export(tmp_path, descriptor=descriptor)
    assert _lifecycle_paths(tmp_path) == []


@pytest.mark.parametrize("mutation", ["missing", "unknown", "wrong-row-order", "augmented", "boolean", "nonfinite", "object"])
def test_export_rejects_malformed_or_augmented_caller_rows_before_lifecycle(
    tmp_path: Path, mutation: str
) -> None:
    descriptor = _descriptor()
    rows = _base_rows(descriptor)
    if mutation == "missing":
        rows.pop("referrals")
    elif mutation == "unknown":
        rows["unknown"] = []
    elif mutation == "wrong-row-order":
        patient = rows["patients"][0]
        rows["patients"][0] = dict(reversed(tuple(patient.items())))
    elif mutation == "augmented":
        rows["patients_augmented"] = []
    elif mutation == "boolean":
        rows["patients"][0]["sex"] = True
    elif mutation == "nonfinite":
        rows["visits"][0]["BMI"] = float("nan")
    else:
        rows["patients"][0]["ethnicity"] = {"not": "a scalar"}

    with pytest.raises(PackageExportUnavailable):
        _export(tmp_path, descriptor=descriptor, base_rows=rows)
    assert _lifecycle_paths(tmp_path) == []


def test_export_writes_only_exact_schema_package_and_is_deterministic(tmp_path: Path) -> None:
    descriptor = _descriptor()
    first = _export(tmp_path, descriptor=descriptor, output_name="first")
    second = _export(tmp_path, descriptor=descriptor, output_name="second")

    expected_csvs = {resource["path"] for resource in descriptor["resources"]}
    assert set(_package_bytes(first)) == expected_csvs | {
        "datapackage.json",
        "validation-report.json",
        "manifest.json",
    }
    assert _package_bytes(first) == _package_bytes(second)

    generated = json.loads((first / "datapackage.json").read_text(encoding="utf-8"))
    assert generated["x-synthetic"] is True
    assert generated["description"].startswith("Synthetic observed-development package")
    assert generated["version"] == "synthetic-observed-development-v1"
    assert generated["keywords"] == ["synthetic", "observed-development"]
    assert schema_fingerprint(generated) == EXPECTED_SCHEMA_FINGERPRINT
    assert validate_structure(first, generated).errors == ()

    manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["profile"] == "observed-development"
    assert manifest["seed"] == 20260831
    assert manifest["reference_time"] == "2026-08-31T00:00:00Z"
    assert manifest["reference_id"] == "fictional-observed-reference-v1"
    assert manifest["software_revision"] == "test-revision"
    assert manifest["configuration_sha256"] == "a" * 64
    assert manifest["reference_sha256"] == "b" * 64
    assert manifest["status"] == "STRUCTURE_VALIDATED_TEST_ORACLE"
    assert manifest["derivation_fingerprint"] == TRUSTED_FINGERPRINT
    assert set(manifest["row_counts"]) == {resource["name"] for resource in descriptor["resources"]}
    assert set(manifest["file_sha256"]) == expected_csvs | {
        "datapackage.json",
        "validation-report.json",
    }


def test_export_rejects_missing_oracle_and_invalid_trusted_configuration_before_lifecycle(
    tmp_path: Path,
) -> None:
    for index, changes in enumerate((
        {"derivation_oracle": None},
        {"trusted_derivation_fingerprint": "not-a-digest"},
        {"trusted_derivation_fingerprint": "0" * 64},
        {"trusted_derivation_test_only": 1},
    )):
        with pytest.raises((PackageExportUnavailable, TypeError, ValueError)):
            _export(tmp_path, output_name=f"invalid-{index}", **changes)
        assert _lifecycle_paths(tmp_path, f"invalid-{index}") == []


@pytest.mark.parametrize(
    "mode", ["identity", "fingerprint", "classification", "base", "extra", "missing-output"]
)
def test_oracle_failures_are_unavailable_and_do_not_promote(tmp_path: Path, mode: str) -> None:
    class HostileOracle(IdentityPreservingTestDerivationOracle):
        def derive(self, package_root: Path, descriptor: dict) -> DerivationResult:
            result = super().derive(package_root, descriptor)
            if mode == "identity":
                return DerivationResult("changed-oracle-id", result.implementation_fingerprint, True)
            if mode == "fingerprint":
                return DerivationResult(result.oracle_id, "f" * 64, True)
            if mode == "classification":
                return DerivationResult(result.oracle_id, result.implementation_fingerprint, False)
            if mode == "base":
                with (package_root / "patients.csv").open("a", encoding="utf-8") as handle:
                    handle.write("tampered\n")
            if mode == "extra":
                (package_root / "unexpected.txt").write_text("unexpected", encoding="utf-8")
            if mode == "missing-output":
                (package_root / "patients_augmented.csv").unlink()
            return result

    with pytest.raises(PackageExportUnavailable) as error:
        _export(tmp_path, derivation_oracle=HostileOracle())
    assert "observed package export failed" in str(error.value)
    assert not (tmp_path / "package").exists()
    failed = next(tmp_path.glob(".package.*.failed"))
    assert json.loads((failed / "failure.json").read_text(encoding="utf-8")) == {
        "status": "FAILED",
        "reason": "observed package export failed",
    }


def test_dynamic_oracle_callable_and_identity_are_pinned_during_preflight(
    tmp_path: Path,
) -> None:
    class DynamicOracle:
        implementation_fingerprint = TRUSTED_FINGERPRINT

        def __init__(self) -> None:
            self.identity = "identity-preserving-test-oracle-v1"
            self.derive_lookups = 0
            self.derive_calls = 0

        @property
        def oracle_id(self) -> str:
            return self.identity

        @property
        def derive(self):
            self.derive_lookups += 1

            def mutate_identity(package_root: Path, descriptor: dict) -> DerivationResult:
                self.derive_calls += 1
                result = IdentityPreservingTestDerivationOracle().derive(
                    package_root, descriptor
                )
                self.identity = "changed-during-derivation"
                return DerivationResult(
                    self.identity, result.implementation_fingerprint, result.test_only
                )

            return mutate_identity

    oracle = DynamicOracle()

    with pytest.raises(PackageExportUnavailable):
        _export(tmp_path, derivation_oracle=oracle)

    assert oracle.derive_lookups == 1
    assert oracle.derive_calls == 1
    assert not (tmp_path / "package").exists()


def test_oracle_cannot_replace_staging_root_with_symlink_to_existing_sibling(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    temporary_root = tmp_path / "temporary"
    temporary_root.mkdir()
    sibling = temporary_root / "existing-sibling"
    sibling.mkdir()
    staging = temporary_root / "controlled-temporary-directory"

    class PersistentTemporaryDirectory:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

        def __enter__(self) -> str:
            staging.mkdir()
            return str(staging)

        def __exit__(self, *args: object) -> None:
            del args

    monkeypatch.setattr(
        "synthetic.package_export.tempfile.TemporaryDirectory",
        PersistentTemporaryDirectory,
    )

    class ReplacingOracle(IdentityPreservingTestDerivationOracle):
        def derive(self, package_root: Path, descriptor: dict) -> DerivationResult:
            shutil.copytree(package_root, sibling, dirs_exist_ok=True)
            result = IdentityPreservingTestDerivationOracle().derive(sibling, descriptor)
            shutil.rmtree(package_root)
            package_root.symlink_to(sibling, target_is_directory=True)
            return result

    with pytest.raises(PackageExportUnavailable):
        _export(tmp_path, derivation_oracle=ReplacingOracle())

    assert not (tmp_path / "package").exists()


@pytest.mark.parametrize("resource_entry", ["directory", "symlink"])
def test_existing_output_wins_before_resource_path_inspection(
    tmp_path: Path, resource_entry: str
) -> None:
    output = tmp_path / "package"
    output.mkdir()
    resource_path = output / "patients.csv"
    if resource_entry == "directory":
        resource_path.mkdir()
    else:
        resource_path.symlink_to(output / "unrelated.csv")

    with pytest.raises(FileExistsError):
        _export(tmp_path)


def test_export_refuses_existing_output_without_overwriting(tmp_path: Path) -> None:
    output = tmp_path / "package"
    output.mkdir()
    (output / "keep.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        _export(tmp_path)
    assert (output / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_post_creation_exception_and_failure_artifact_are_redacted(tmp_path: Path) -> None:
    raw_temporary_path = str(tmp_path / "raw-temporary-path")
    secrets = (PATIENT_TOKEN, VISIT_TOKEN, "source-frame-token", "truth-token", raw_temporary_path)

    class LeakyOracle(IdentityPreservingTestDerivationOracle):
        def derive(self, package_root: Path, descriptor: dict) -> DerivationResult:
            del package_root, descriptor
            raise RuntimeError(" ".join(secrets))

    with pytest.raises(PackageExportUnavailable) as error:
        _export(tmp_path, derivation_oracle=LeakyOracle())
    failed = next(tmp_path.glob(".package.*.failed"))
    public_text = str(error.value) + (failed / "failure.json").read_text(encoding="utf-8")
    assert "observed package export failed" in public_text
    assert all(secret not in public_text for secret in secrets)
