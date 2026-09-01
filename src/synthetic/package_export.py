from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
import re
import shutil
import stat
import tempfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from synthetic.base_resources import BASE_RESOURCES
from synthetic.csv_package import write_resource, write_synthetic_descriptor
from synthetic.derivation import DerivationOracle, DerivationUnavailable
from synthetic.manifest import RunManifest
from synthetic.native.ancillary import GHD_LAB_COMPONENT_NAMES, GHD_LAB_RESULT_FLAG
from synthetic.native.counterfactual_worlds import (
    CounterfactualEhrWorldPair,
    CounterfactualWorldValidationStatus,
    validate_counterfactual_ehr_worlds,
)
from synthetic.native.resources import (
    ObservedResourceBundle,
    ResourceShape,
    ResourceValidationStatus,
    validate_observed_resources,
)
from synthetic.run_directory import RunDirectory
from synthetic.schema_contract import (
    EXPECTED_SCHEMA_FINGERPRINT,
    field_names,
    resource_spec,
    schema_fingerprint,
    validate_resource_paths,
)
from synthetic.validate import validate_structure

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_FAILURE_REASON = "observed package export failed"
_PAIR_FAILURE_REASON = "counterfactual package export failed"
_AUGMENTED_RESOURCES = ("patients_augmented", "visits_augmented")
_PACKAGE_ARTIFACTS = {"datapackage.json", "validation-report.json", "manifest.json"}
_DIRECTORY_OPEN_FLAGS = (
    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
)
_FILE_OPEN_FLAGS = (
    os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
)


class PackageExportUnavailable(DerivationUnavailable):
    """Raised when an exact-schema package cannot be safely exported."""


class CounterfactualPackageExportUnavailable(PackageExportUnavailable):
    """Fixed redacted pair-export failure."""


def _require_output_available(output: Path) -> None:
    """Perform the read-only half of the no-replace output lifecycle check."""
    if not isinstance(output, Path):
        raise TypeError("output must be a Path")
    if os.path.lexists(output):
        raise FileExistsError("run directory target already exists")


def _is_run_lifecycle_collision(output: Path, run_id: str) -> bool:
    """Identify only the collision paths whose FileExistsError is public contract."""
    absolute = Path(os.path.abspath(output))
    return any(
        os.path.lexists(path)
        for path in (
            absolute,
            absolute.parent / f".{absolute.name}.{run_id}.partial",
            absolute.parent / f".{absolute.name}.{run_id}.failed",
        )
    )


def _start_run(output: Path, run_id: str) -> RunDirectory:
    """Start a run while redacting non-collision filesystem errors."""
    try:
        return RunDirectory.start(output, run_id)
    except FileExistsError:
        if _is_run_lifecycle_collision(output, run_id):
            raise
        raise PackageExportUnavailable(_FAILURE_REASON) from None
    except Exception:  # noqa: BLE001 - startup errors are deliberately redacted.
        raise PackageExportUnavailable(_FAILURE_REASON) from None


def _start_pair_run(output: Path, run_id: str) -> RunDirectory:
    """Start a pair run while preserving only deterministic lifecycle collisions."""
    try:
        return RunDirectory.start(output, run_id)
    except FileExistsError:
        if _is_run_lifecycle_collision(output, run_id):
            raise
        raise CounterfactualPackageExportUnavailable(_PAIR_FAILURE_REASON) from None
    except Exception:  # noqa: BLE001 - startup errors are deliberately redacted.
        raise CounterfactualPackageExportUnavailable(_PAIR_FAILURE_REASON) from None


@dataclass(frozen=True)
class PackageExportMetadata:
    profile: str
    seed: int
    reference_time: str
    reference_id: str
    software_revision: str
    configuration_sha256: str
    reference_sha256: str | None = None

    def __post_init__(self) -> None:
        for name in ("profile", "reference_time", "reference_id", "software_revision"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value:
                raise ValueError(f"{name} must be a nonempty single-line string")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise TypeError("seed must be an integer")
        _require_digest("configuration_sha256", self.configuration_sha256, allow_placeholder=False)
        if self.reference_sha256 is not None:
            _require_digest("reference_sha256", self.reference_sha256, allow_placeholder=True)


def _require_digest(name: str, value: object, *, allow_placeholder: bool) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
    if not allow_placeholder and value == "0" * 64:
        raise ValueError(f"{name} cannot be a placeholder")
    return value


def _json_value(value: object) -> object:
    if isinstance(value, Mapping):
        converted: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("descriptor mapping keys must be strings")
            converted[key] = _json_value(item)
        return converted
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise TypeError("descriptor must contain only JSON-compatible values")


def _copy_descriptor(descriptor: Mapping[str, object]) -> dict[str, Any]:
    if not isinstance(descriptor, Mapping):
        raise TypeError("descriptor must be a mapping")
    copied = json.loads(json.dumps(_json_value(descriptor), allow_nan=False))
    if not isinstance(copied, dict):
        raise TypeError("descriptor must be a mapping")
    return copied


def _canonical_descriptor(descriptor: dict[str, Any]) -> dict[str, Any]:
    """Retain only schema-fingerprinted descriptor values for publication."""
    resources: list[dict[str, Any]] = []
    for source_resource in descriptor["resources"]:
        source_schema = source_resource["schema"]
        resource: dict[str, Any] = {
            "name": source_resource["name"],
            "path": source_resource["path"],
            "encoding": source_resource.get("encoding", "utf-8"),
            "dialect": source_resource.get("dialect", {}),
            "schema": {
                "fields": [
                    {
                        key: field[key]
                        for key in ("name", "type", "constraints")
                        if key in field
                    }
                    for field in source_schema["fields"]
                ],
                "missingValues": source_schema.get("missingValues", []),
                "primaryKey": source_schema.get("primaryKey"),
                "foreignKeys": source_schema.get("foreignKeys", []),
            },
        }
        logical_links = source_resource.get("x-logicalForeignKeys", [])
        if logical_links:
            resource["x-logicalForeignKeys"] = [
                {"fields": link["fields"], "reference": link["reference"]}
                for link in logical_links
            ]
        resources.append(resource)
    return {
        "profile": "tabular-data-package",
        "name": "ppoc-pediatric-ehr",
        "title": "PPOC Pediatric EHR Data Package",
        "resources": resources,
    }


def _allowed_tree(descriptor: dict[str, Any], names: tuple[str, ...]) -> tuple[set[str], set[str]]:
    files = {Path(resource_spec(descriptor, name)["path"]).as_posix() for name in names}
    dirs = {
        parent.as_posix()
        for item in files
        for parent in Path(item).parents
        if parent.as_posix() != "."
    }
    return files, dirs


def _scan_tree(root: Path, files: set[str], dirs: set[str]) -> None:
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        mode = path.lstat().st_mode
        allowed_file = relative in files and stat.S_ISREG(mode)
        allowed_dir = relative in dirs and stat.S_ISDIR(mode)
        if not (allowed_file or allowed_dir):
            raise DerivationUnavailable("unexpected run artifact")


def _open_pinned_directory(path: Path) -> tuple[int, tuple[int, int]]:
    """Open and identify a real directory without following its final component."""
    before = path.lstat()
    if not stat.S_ISDIR(before.st_mode):
        raise DerivationUnavailable("derivation staging directory was replaced")
    descriptor = os.open(path, _DIRECTORY_OPEN_FLAGS)
    opened = os.fstat(descriptor)
    identity = (opened.st_dev, opened.st_ino)
    if not stat.S_ISDIR(opened.st_mode) or identity != (before.st_dev, before.st_ino):
        os.close(descriptor)
        raise DerivationUnavailable("derivation staging directory was replaced")
    return descriptor, identity


def _require_directory_identity(path: Path, identity: tuple[int, int]) -> None:
    try:
        current = path.lstat()
    except OSError as error:
        raise DerivationUnavailable("derivation staging directory was replaced") from error
    if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != identity:
        raise DerivationUnavailable("derivation staging directory was replaced")


def _read_regular_at(directory_descriptor: int, relative: str) -> bytes:
    """Read a pinned regular file beneath a directory descriptor without symlinks."""
    path = Path(relative)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise DerivationUnavailable("unsafe staged resource path")
    parent_descriptor = os.dup(directory_descriptor)
    file_descriptor: int | None = None
    try:
        for component in path.parts[:-1]:
            child_descriptor = os.open(
                component,
                _DIRECTORY_OPEN_FLAGS,
                dir_fd=parent_descriptor,
            )
            child_status = os.fstat(child_descriptor)
            if not stat.S_ISDIR(child_status.st_mode):
                os.close(child_descriptor)
                raise DerivationUnavailable("staged resource parent is not a directory")
            os.close(parent_descriptor)
            parent_descriptor = child_descriptor
        file_descriptor = os.open(
            path.parts[-1],
            _FILE_OPEN_FLAGS,
            dir_fd=parent_descriptor,
        )
        file_status = os.fstat(file_descriptor)
        if not stat.S_ISREG(file_status.st_mode):
            raise DerivationUnavailable("staged resource is not a regular file")
        with os.fdopen(file_descriptor, "rb") as handle:
            file_descriptor = None
            return handle.read()
    except OSError as error:
        raise DerivationUnavailable("staged resource is unavailable") from error
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        os.close(parent_descriptor)


def _normalize_base_rows(
    descriptor: dict[str, Any], base_rows: Mapping[str, Iterable[Mapping[str, object]]]
) -> dict[str, list[dict[str, object]]]:
    if not isinstance(base_rows, Mapping) or tuple(base_rows) != BASE_RESOURCES:
        raise ValueError("base rows must contain exactly the required base resources")
    normalized: dict[str, list[dict[str, object]]] = {}
    for name in BASE_RESOURCES:
        rows = base_rows[name]
        if isinstance(rows, (str, bytes)) or not isinstance(rows, Iterable):
            raise TypeError("base resource rows must be iterable")
        expected_fields = field_names(descriptor, name)
        materialized: list[dict[str, object]] = []
        for row in rows:
            if not isinstance(row, Mapping) or tuple(row) != expected_fields:
                raise ValueError("base row keys do not match the descriptor")
            copied = dict(row)
            for value in copied.values():
                if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                    raise TypeError("base row values must be strings or finite numbers")
                if isinstance(value, float) and not math.isfinite(value):
                    raise ValueError("base row values must be finite")
            materialized.append(copied)
        normalized[name] = materialized
    return normalized


def _validate_preflight(
    descriptor: Mapping[str, object],
    base_rows: Mapping[str, Iterable[Mapping[str, object]]],
    output: Path,
    metadata: PackageExportMetadata,
    derivation_oracle: DerivationOracle | None,
    trusted_derivation_fingerprint: str,
    trusted_derivation_test_only: bool,
) -> tuple[
    dict[str, Any],
    dict[str, list[dict[str, object]]],
    Callable[[Path, dict[str, Any]], object],
    str,
]:
    if not isinstance(metadata, PackageExportMetadata):
        raise TypeError("metadata must be PackageExportMetadata")
    if derivation_oracle is None:
        raise DerivationUnavailable("authoritative derivation oracle is not configured")
    derive = getattr(derivation_oracle, "derive", None)
    if not callable(derive):
        raise DerivationUnavailable("authoritative derivation oracle is not configured")
    oracle_id = getattr(derivation_oracle, "oracle_id", None)
    if not isinstance(oracle_id, str) or not oracle_id.strip():
        raise DerivationUnavailable("authoritative derivation oracle is not configured")
    _require_digest(
        "trusted_derivation_fingerprint", trusted_derivation_fingerprint, allow_placeholder=False
    )
    if not isinstance(trusted_derivation_test_only, bool):
        raise TypeError("trusted_derivation_test_only must be a boolean")
    copied_descriptor = _copy_descriptor(descriptor)
    if schema_fingerprint(copied_descriptor) != EXPECTED_SCHEMA_FINGERPRINT:
        raise ValueError("descriptor does not match the exact schema contract")
    canonical_descriptor = _canonical_descriptor(copied_descriptor)
    if schema_fingerprint(canonical_descriptor) != EXPECTED_SCHEMA_FINGERPRINT:
        raise ValueError("descriptor does not match the exact schema contract")
    validate_resource_paths(canonical_descriptor, output)
    return (
        canonical_descriptor,
        _normalize_base_rows(canonical_descriptor, base_rows),
        derive,
        oracle_id,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2) + "\n")


def _write_canonical_json(path: Path, payload: object) -> None:
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n")


def _pair_run_id(metadata: PackageExportMetadata, worlds: CounterfactualEhrWorldPair) -> str:
    payload = {
        "metadata": dataclasses.asdict(metadata),
        "matrix_version": worlds.matrix.version,
        "intervention": worlds.matrix.intervention.value,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()[:12]


def _pair_base_rows(
    worlds: CounterfactualEhrWorldPair, descriptor: dict[str, Any]
) -> tuple[
    dict[str, list[dict[str, object]]], dict[str, list[dict[str, object]]]
]:
    lab_resource = resource_spec(descriptor, "labs")
    result_flag = next(
        field for field in lab_resource["schema"]["fields"] if field["name"] == "result_flag"
    )
    allowed_lab_flags = {str(value) for value in result_flag.get("constraints", {}).get("enum", [])}
    rows: list[dict[str, list[dict[str, object]]]] = []
    for member in (worlds.baseline, worlds.intervention):
        if not isinstance(member.bundle, ObservedResourceBundle):
            raise TypeError("counterfactual world is missing its resource bundle")
        member_rows = {
            name: [row.to_mapping() for row in member.bundle.rows[name]] for name in BASE_RESOURCES
        }
        for row in member_rows["labs"]:
            if (
                row["result_component_name"] in GHD_LAB_COMPONENT_NAMES
                and row["result_flag"] == GHD_LAB_RESULT_FLAG
            ):
                row["result_flag"] = ""
            elif row["result_flag"] not in {"", *allowed_lab_flags}:
                raise ValueError("lab result flag is not permitted by the exact schema")
        rows.append(member_rows)
    return rows[0], rows[1]


def _pair_allowed_tree(descriptor: dict[str, Any]) -> tuple[set[str], set[str]]:
    resource_paths = {
        Path(resource["path"]).as_posix()
        for resource in descriptor["resources"]
    }
    files = {"pair-manifest.json"}
    directories = {"baseline", "intervention"}
    for child in ("baseline", "intervention"):
        child_files = resource_paths | _PACKAGE_ARTIFACTS
        files.update((Path(child) / path).as_posix() for path in child_files)
        directories.update(
            (Path(child) / parent).as_posix()
            for path in child_files
            for parent in Path(path).parents
            if parent.as_posix() != "."
        )
    return files, directories


def _scan_exact_tree(root: Path, files: set[str], dirs: set[str]) -> None:
    _scan_tree(root, files, dirs)
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    actual_dirs = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_dir() and not path.is_symlink()
    }
    if actual_files != files or actual_dirs != dirs:
        raise DerivationUnavailable("pair export tree inventory does not match")


def _remove_tree_entry_at(directory_descriptor: int, name: str) -> None:
    status = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
    if stat.S_ISDIR(status.st_mode):
        child_descriptor = os.open(name, _DIRECTORY_OPEN_FLAGS, dir_fd=directory_descriptor)
        try:
            for child in os.scandir(child_descriptor):
                _remove_tree_entry_at(child_descriptor, child.name)
        finally:
            os.close(child_descriptor)
        os.rmdir(name, dir_fd=directory_descriptor)
    else:
        os.unlink(name, dir_fd=directory_descriptor)


def _clear_pair_partial_tree(partial_path: Path) -> None:
    directory_descriptor, identity = _open_pinned_directory(partial_path)
    try:
        for entry in os.scandir(directory_descriptor):
            _remove_tree_entry_at(directory_descriptor, entry.name)
        _require_directory_identity(partial_path, identity)
    finally:
        os.close(directory_descriptor)


def _pair_manifest(
    worlds: CounterfactualEhrWorldPair,
    metadata: PackageExportMetadata,
    report: object,
    child_manifest_sha256: Mapping[str, str],
) -> dict[str, object]:
    check_counts = getattr(report, "check_counts", None)
    if not isinstance(check_counts, Mapping):
        raise TypeError("counterfactual world report is malformed")
    return {
        "contract": "counterfactual-ehr-package-pair-v1",
        "schema_fingerprint": EXPECTED_SCHEMA_FINGERPRINT,
        "serialization_projection": "ghd-result-flag-empty-v1",
        "matrix_version": worlds.matrix.version,
        "intervention": worlds.matrix.intervention.value,
        "validation_status": CounterfactualWorldValidationStatus.PASS.value,
        "validation_check_counts": dict(check_counts),
        "metadata": dataclasses.asdict(metadata),
        "children": {
            name: {"path": name, "manifest_sha256": child_manifest_sha256[name]}
            for name in ("baseline", "intervention")
        },
    }


def export_counterfactual_ehr_world_pair(
    worlds: CounterfactualEhrWorldPair,
    descriptor: Mapping[str, object],
    output: Path,
    *,
    metadata: PackageExportMetadata,
    derivation_oracle: DerivationOracle,
    trusted_derivation_fingerprint: str,
    trusted_derivation_test_only: bool,
) -> Path:
    """Export a validated fictional world pair as two exact-schema child packages."""
    try:
        _require_output_available(output)
    except FileExistsError:
        raise
    except Exception:  # noqa: BLE001 - pair boundary errors are deliberately redacted.
        raise CounterfactualPackageExportUnavailable(_PAIR_FAILURE_REASON) from None

    try:
        if not isinstance(worlds, CounterfactualEhrWorldPair):
            raise TypeError("worlds must be a CounterfactualEhrWorldPair")
        report = validate_counterfactual_ehr_worlds(worlds)
        if report.status is not CounterfactualWorldValidationStatus.PASS:
            raise ValueError("counterfactual world validation did not pass")
        copied_descriptor = _copy_descriptor(descriptor)
        baseline_rows, intervention_rows = _pair_base_rows(worlds, copied_descriptor)
    except Exception:  # noqa: BLE001 - pair pre-creation errors are deliberately redacted.
        raise CounterfactualPackageExportUnavailable(_PAIR_FAILURE_REASON) from None

    try:
        with tempfile.TemporaryDirectory(prefix="counterfactual-package-export-") as temporary:
            staging = Path(temporary)
            try:
                baseline = export_exact_schema_package(
                    copied_descriptor,
                    baseline_rows,
                    staging / "baseline",
                    metadata=metadata,
                    derivation_oracle=derivation_oracle,
                    trusted_derivation_fingerprint=trusted_derivation_fingerprint,
                    trusted_derivation_test_only=trusted_derivation_test_only,
                )
                intervention = export_exact_schema_package(
                    copied_descriptor,
                    intervention_rows,
                    staging / "intervention",
                    metadata=metadata,
                    derivation_oracle=derivation_oracle,
                    trusted_derivation_fingerprint=trusted_derivation_fingerprint,
                    trusted_derivation_test_only=trusted_derivation_test_only,
                )
            except Exception:  # noqa: BLE001 - pair pre-creation errors are deliberately redacted.
                raise CounterfactualPackageExportUnavailable(_PAIR_FAILURE_REASON) from None

            run = _start_pair_run(output, _pair_run_id(metadata, worlds))
            try:
                for child_name, child_package in (("baseline", baseline), ("intervention", intervention)):
                    shutil.copytree(child_package, run.partial_path / child_name)
                child_manifest_sha256 = {
                    child_name: _sha256(run.partial_path / child_name / "manifest.json")
                    for child_name in ("baseline", "intervention")
                }
                _write_canonical_json(
                    run.partial_path / "pair-manifest.json",
                    _pair_manifest(worlds, metadata, report, child_manifest_sha256),
                )
                allowed_files, allowed_dirs = _pair_allowed_tree(copied_descriptor)
                _scan_exact_tree(run.partial_path, allowed_files, allowed_dirs)
                return run.promote()
            except Exception:  # noqa: BLE001 - archive every post-creation failure safely.
                try:
                    _clear_pair_partial_tree(run.partial_path)
                    run.fail(_PAIR_FAILURE_REASON)
                except Exception:  # noqa: BLE001 - retain the redacted public failure if archival fails.
                    raise CounterfactualPackageExportUnavailable(_PAIR_FAILURE_REASON) from None
                raise CounterfactualPackageExportUnavailable(_PAIR_FAILURE_REASON) from None
    except (FileExistsError, CounterfactualPackageExportUnavailable):
        raise
    except Exception:  # noqa: BLE001 - private staging failures are deliberately redacted.
        raise CounterfactualPackageExportUnavailable(_PAIR_FAILURE_REASON) from None


def export_exact_schema_package(
    descriptor: Mapping[str, object],
    base_rows: Mapping[str, Iterable[Mapping[str, object]]],
    output: Path,
    *,
    metadata: PackageExportMetadata,
    derivation_oracle: DerivationOracle,
    trusted_derivation_fingerprint: str,
    trusted_derivation_test_only: bool,
) -> Path:
    """Export staged, oracle-augmented rows as an atomically promoted package."""
    try:
        _require_output_available(output)
        copied_descriptor, normalized_rows, derive, oracle_id = _validate_preflight(
            descriptor,
            base_rows,
            output,
            metadata,
            derivation_oracle,
            trusted_derivation_fingerprint,
            trusted_derivation_test_only,
        )
    except (FileExistsError, PackageExportUnavailable):
        raise
    except Exception:  # noqa: BLE001 - public package errors are deliberately redacted.
        raise PackageExportUnavailable(_FAILURE_REASON) from None

    run_id = hashlib.sha256(
        f"{metadata.seed}:{len(normalized_rows['patients'])}:{metadata.reference_time}".encode()
    ).hexdigest()[:12]
    run = _start_run(output, run_id)
    try:
        row_counts: dict[str, int] = {}
        for name in BASE_RESOURCES:
            resource = resource_spec(copied_descriptor, name)
            row_counts[name] = write_resource(
                run.partial_path / resource["path"], resource, normalized_rows[name]
            )

        partial_descriptor, partial_identity = _open_pinned_directory(run.partial_path)
        try:
            partial_base_hashes = {
                resource_spec(copied_descriptor, name)["path"]: hashlib.sha256(
                    _read_regular_at(
                        partial_descriptor,
                        resource_spec(copied_descriptor, name)["path"],
                    )
                ).hexdigest()
                for name in BASE_RESOURCES
            }
            with tempfile.TemporaryDirectory(prefix="synthetic-derive-") as outer_name:
                outer = Path(outer_name)
                staging = outer / "staging"
                staging.mkdir()
                outer_descriptor, outer_identity = _open_pinned_directory(outer)
                try:
                    staging_descriptor, staging_identity = _open_pinned_directory(staging)
                    try:
                        stage_descriptor = _copy_descriptor(copied_descriptor)
                        validate_resource_paths(stage_descriptor, staging)
                        for name in BASE_RESOURCES:
                            resource = resource_spec(stage_descriptor, name)
                            source = run.partial_path / resource["path"]
                            target = staging / resource["path"]
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copyfile(source, target)
                        base_hashes = {
                            resource_spec(stage_descriptor, name)["path"]: hashlib.sha256(
                                _read_regular_at(
                                    staging_descriptor,
                                    resource_spec(stage_descriptor, name)["path"],
                                )
                            ).hexdigest()
                            for name in BASE_RESOURCES
                        }

                        derivation = derive(staging, stage_descriptor)
                        _require_directory_identity(outer, outer_identity)
                        _require_directory_identity(staging, staging_identity)
                        current_oracle_id = getattr(derivation_oracle, "oracle_id", None)
                        if not isinstance(current_oracle_id, str) or not current_oracle_id.strip():
                            raise DerivationUnavailable("derivation oracle returned no identity")
                        if current_oracle_id != oracle_id:
                            raise DerivationUnavailable("derivation oracle identity changed")
                        returned_oracle_id = getattr(derivation, "oracle_id", None)
                        if not isinstance(returned_oracle_id, str) or not returned_oracle_id.strip():
                            raise DerivationUnavailable("derivation oracle returned no identity")
                        if returned_oracle_id != oracle_id:
                            raise DerivationUnavailable("derivation oracle identity changed")
                        implementation_fingerprint = getattr(
                            derivation, "implementation_fingerprint", None
                        )
                        if implementation_fingerprint != trusted_derivation_fingerprint:
                            raise DerivationUnavailable(
                                "derivation fingerprint does not match trusted configuration"
                            )
                        test_only = getattr(derivation, "test_only", None)
                        if not isinstance(test_only, bool) or test_only != trusted_derivation_test_only:
                            raise DerivationUnavailable(
                                "derivation test-only classification does not match"
                            )
                        allowed_files, allowed_dirs = _allowed_tree(
                            copied_descriptor, BASE_RESOURCES + _AUGMENTED_RESOURCES
                        )
                        outer_files = {
                            (Path("staging") / path).as_posix() for path in allowed_files
                        }
                        outer_dirs = {"staging"} | {
                            (Path("staging") / path).as_posix() for path in allowed_dirs
                        }
                        _scan_tree(outer, outer_files, outer_dirs)
                        _require_directory_identity(outer, outer_identity)
                        _require_directory_identity(staging, staging_identity)
                        staged_payloads = {
                            resource_spec(copied_descriptor, name)["path"]: _read_regular_at(
                                staging_descriptor,
                                resource_spec(copied_descriptor, name)["path"],
                            )
                            for name in BASE_RESOURCES + _AUGMENTED_RESOURCES
                        }
                        if any(
                            hashlib.sha256(staged_payloads[path]).hexdigest() != digest
                            for path, digest in base_hashes.items()
                        ):
                            raise DerivationUnavailable("derivation mutated a base resource")
                        _require_directory_identity(outer, outer_identity)
                        _require_directory_identity(staging, staging_identity)
                    finally:
                        os.close(staging_descriptor)
                finally:
                    os.close(outer_descriptor)

                _require_directory_identity(run.partial_path, partial_identity)
                if any(
                    hashlib.sha256(_read_regular_at(partial_descriptor, path)).hexdigest()
                    != digest
                    for path, digest in partial_base_hashes.items()
                ):
                    raise DerivationUnavailable("derivation mutated a base resource")
                for name in _AUGMENTED_RESOURCES:
                    resource = resource_spec(copied_descriptor, name)
                    target = run.partial_path / resource["path"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("xb") as handle:
                        handle.write(staged_payloads[resource["path"]])
        finally:
            os.close(partial_descriptor)

        csv_files, csv_dirs = _allowed_tree(
            copied_descriptor, tuple(item["name"] for item in copied_descriptor["resources"])
        )
        _scan_tree(run.partial_path, csv_files, csv_dirs)
        report = validate_structure(run.partial_path, copied_descriptor)
        if report.errors:
            raise ValueError("structural validation failed")
        row_counts.update(report.row_counts)
        write_synthetic_descriptor(
            run.partial_path,
            copied_descriptor,
            row_counts,
            profile=metadata.profile,
        )
        _write_json(run.partial_path / "validation-report.json", dataclasses.asdict(report))
        package_files = csv_files | _PACKAGE_ARTIFACTS
        _scan_tree(run.partial_path, package_files - {"manifest.json"}, csv_dirs)
        file_sha256 = {
            path.relative_to(run.partial_path).as_posix(): _sha256(path)
            for path in sorted(run.partial_path.rglob("*"))
            if path.is_file() and not path.is_symlink()
        }
        manifest = RunManifest.generated(
            profile=metadata.profile,
            seed=metadata.seed,
            schema_fingerprint=schema_fingerprint(copied_descriptor),
            reference_time=metadata.reference_time,
            reference_id=metadata.reference_id,
            reference_sha256=metadata.reference_sha256,
            configuration_sha256=metadata.configuration_sha256,
            software_revision=metadata.software_revision,
            derivation_fingerprint=trusted_derivation_fingerprint,
            test_only_derivation=trusted_derivation_test_only,
            row_counts=row_counts,
            file_sha256=file_sha256,
        )
        (run.partial_path / "manifest.json").write_bytes(manifest.to_json_bytes())
        _scan_tree(run.partial_path, package_files, csv_dirs)
        return run.promote()
    except Exception:  # noqa: BLE001 - archive every post-creation failure safely.
        try:
            run.fail(_FAILURE_REASON)
        except Exception:  # noqa: BLE001 - retain the redacted public failure if archival fails.
            raise PackageExportUnavailable(_FAILURE_REASON) from None
        raise PackageExportUnavailable(_FAILURE_REASON) from None


def export_observed_resource_package(
    bundles: Iterable[ObservedResourceBundle],
    descriptor: Mapping[str, object],
    output: Path,
    *,
    metadata: PackageExportMetadata,
    derivation_oracle: DerivationOracle,
    trusted_derivation_fingerprint: str,
    trusted_derivation_test_only: bool,
) -> Path:
    """Export validated observed-resource bundles through the exact-schema lifecycle."""
    try:
        _require_output_available(output)
        materialized = tuple(bundles)
        if not materialized:
            raise ValueError("at least one observed resource bundle is required")
        expected_shape = ResourceShape.from_descriptor(descriptor)
        patient_ids: set[str] = set()
        visit_ids: set[str] = set()
        for bundle in materialized:
            if validate_observed_resources(bundle).status is not ResourceValidationStatus.PASS:
                raise ValueError("observed resource validation did not pass")
            if bundle.shape != expected_shape:
                raise ValueError("observed resource shape does not match descriptor")
            if bundle.patient_id in patient_ids:
                raise ValueError("duplicate observed synthetic patient")
            patient_ids.add(bundle.patient_id)
            for row in bundle.rows["visits"]:
                visit_id = row.to_mapping()["visit_id"]
                if visit_id in visit_ids:
                    raise ValueError("duplicate observed synthetic visit")
                visit_ids.add(visit_id)
        ordered = tuple(sorted(materialized, key=lambda bundle: bundle.patient_id))
        base_rows = {
            name: [row.to_mapping() for bundle in ordered for row in bundle.rows[name]]
            for name in BASE_RESOURCES
        }
    except FileExistsError:
        raise
    except Exception:  # noqa: BLE001 - bundle-boundary failures are deliberately redacted.
        raise PackageExportUnavailable(_FAILURE_REASON) from None

    return export_exact_schema_package(
        descriptor,
        base_rows,
        output,
        metadata=metadata,
        derivation_oracle=derivation_oracle,
        trusted_derivation_fingerprint=trusted_derivation_fingerprint,
        trusted_derivation_test_only=trusted_derivation_test_only,
    )
