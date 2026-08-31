from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
import shutil
import stat
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from synthetic.base_resources import BASE_RESOURCES
from synthetic.csv_package import write_resource, write_synthetic_descriptor
from synthetic.derivation import DerivationOracle, DerivationUnavailable, require_augmented_outputs
from synthetic.manifest import RunManifest
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
_AUGMENTED_RESOURCES = ("patients_augmented", "visits_augmented")
_PACKAGE_ARTIFACTS = {"datapackage.json", "validation-report.json", "manifest.json"}


class PackageExportUnavailable(DerivationUnavailable):
    """Raised when an exact-schema package cannot be safely exported."""


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
) -> tuple[dict[str, Any], dict[str, list[dict[str, object]]]]:
    if not isinstance(metadata, PackageExportMetadata):
        raise TypeError("metadata must be PackageExportMetadata")
    if not isinstance(output, Path):
        raise TypeError("output must be a Path")
    if derivation_oracle is None or not callable(getattr(derivation_oracle, "derive", None)):
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
    validate_resource_paths(copied_descriptor, output)
    return copied_descriptor, _normalize_base_rows(copied_descriptor, base_rows)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2) + "\n")


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
        copied_descriptor, normalized_rows = _validate_preflight(
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
    run = RunDirectory.start(output, run_id)
    try:
        row_counts: dict[str, int] = {}
        for name in BASE_RESOURCES:
            resource = resource_spec(copied_descriptor, name)
            row_counts[name] = write_resource(
                run.partial_path / resource["path"], resource, normalized_rows[name]
            )

        with tempfile.TemporaryDirectory(prefix="synthetic-derive-") as staging_name:
            staging = Path(staging_name)
            staging_parent_entries = set(staging.parent.iterdir())
            stage_descriptor = _copy_descriptor(copied_descriptor)
            validate_resource_paths(stage_descriptor, staging)
            for name in BASE_RESOURCES:
                resource = resource_spec(stage_descriptor, name)
                source = run.partial_path / resource["path"]
                target = staging / resource["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            base_hashes = {
                resource_spec(stage_descriptor, name)["path"]: _sha256(
                    staging / resource_spec(stage_descriptor, name)["path"]
                )
                for name in BASE_RESOURCES
            }
            partial_base_hashes = {
                resource_spec(copied_descriptor, name)["path"]: _sha256(
                    run.partial_path / resource_spec(copied_descriptor, name)["path"]
                )
                for name in BASE_RESOURCES
            }
            derivation = derivation_oracle.derive(staging, stage_descriptor)
            if set(staging.parent.iterdir()) != staging_parent_entries:
                raise DerivationUnavailable("derivation escaped staging directory")
            returned_oracle_id = getattr(derivation, "oracle_id", None)
            if not isinstance(returned_oracle_id, str) or not returned_oracle_id.strip():
                raise DerivationUnavailable("derivation oracle returned no identity")
            if returned_oracle_id != derivation_oracle.oracle_id:
                raise DerivationUnavailable("derivation oracle identity changed")
            implementation_fingerprint = getattr(derivation, "implementation_fingerprint", None)
            if implementation_fingerprint != trusted_derivation_fingerprint:
                raise DerivationUnavailable("derivation fingerprint does not match trusted configuration")
            test_only = getattr(derivation, "test_only", None)
            if not isinstance(test_only, bool) or test_only != trusted_derivation_test_only:
                raise DerivationUnavailable("derivation test-only classification does not match")
            allowed_files, allowed_dirs = _allowed_tree(
                copied_descriptor, BASE_RESOURCES + _AUGMENTED_RESOURCES
            )
            _scan_tree(staging, allowed_files, allowed_dirs)
            for name in BASE_RESOURCES:
                staged = staging / resource_spec(copied_descriptor, name)["path"]
                if not staged.is_file() or not stat.S_ISREG(staged.lstat().st_mode):
                    raise DerivationUnavailable("derivation removed or replaced a base resource")
            if any(_sha256(staging / path) != digest for path, digest in base_hashes.items()):
                raise DerivationUnavailable("derivation mutated a base resource")
            for path, digest in partial_base_hashes.items():
                partial = run.partial_path / path
                if not partial.is_file() or not stat.S_ISREG(partial.lstat().st_mode) or _sha256(partial) != digest:
                    raise DerivationUnavailable("derivation mutated a base resource")
            require_augmented_outputs(staging, copied_descriptor, oracle_id=returned_oracle_id)
            for name in _AUGMENTED_RESOURCES:
                resource = resource_spec(copied_descriptor, name)
                source = staging / resource["path"]
                target = run.partial_path / resource["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as handle:
                    handle.write(source.read_bytes())

        csv_files, csv_dirs = _allowed_tree(
            copied_descriptor, tuple(item["name"] for item in copied_descriptor["resources"])
        )
        _scan_tree(run.partial_path, csv_files, csv_dirs)
        report = validate_structure(run.partial_path, copied_descriptor)
        if report.errors:
            raise ValueError("structural validation failed")
        row_counts.update(report.row_counts)
        write_synthetic_descriptor(run.partial_path, copied_descriptor, row_counts)
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
