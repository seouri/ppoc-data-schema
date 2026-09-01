"""Governed identity checks for aggregate multi-run prevalence evidence.

This module is deliberately an evaluator-side boundary.  It accepts generated
package locations only to produce safe, aggregate package identities; those
locations are never retained in public mappings or exception text.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from synthetic.heldout_validate import HeldoutRunConfig
from synthetic.schema_contract import EXPECTED_SCHEMA_FINGERPRINT, schema_fingerprint
from synthetic.validate import validate_structure

PREVALENCE_EVIDENCE_REPORT_VERSION = "prevalence-evidence-report-v1"
PACKAGE_MANIFEST_MAX_BYTES = 1024 * 1024
V1_TARGET_FAMILIES = frozenset({"demographics", "recorded_outcome"})

_FAILURE_REASON = "prevalence evidence package is unavailable"
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_MANIFEST_KEYS = frozenset(
    {
        "manifest_version",
        "generator_version",
        "profile",
        "engine",
        "seed",
        "schema_fingerprint",
        "reference_time",
        "reference_id",
        "configuration_sha256",
        "software_revision",
        "prng_family",
        "seed_derivation_version",
        "status",
        "reference_sha256",
        "derivation_fingerprint",
        "metadata_only",
        "row_counts",
        "file_sha256",
    }
)
_PACKAGE_ARTIFACTS = frozenset({"datapackage.json", "validation-report.json", "manifest.json"})
_RESOURCE_NAMES = (
    "patients",
    "patients_augmented",
    "visits",
    "visits_augmented",
    "labs",
    "medications",
    "problem_list",
    "referrals",
)
_DIRECTORY_OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_FILE_OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)


class PrevalenceEvidenceUnavailable(ValueError):
    """Fixed redacted failure for untrusted evidence-package material."""


def _unavailable() -> PrevalenceEvidenceUnavailable:
    return PrevalenceEvidenceUnavailable(_FAILURE_REASON)


def _require_token(value: object) -> str:
    if not isinstance(value, str) or _TOKEN_RE.fullmatch(value) is None:
        raise _unavailable()
    return value


def _require_digest(value: object, *, allow_zero: bool = False) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise _unavailable()
    if not allow_zero and value == "0" * 64:
        raise _unavailable()
    return value


def _require_seed(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _unavailable()
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _reject_nonfinite(_value: str) -> None:
    raise ValueError("nonfinite JSON value")


def _strict_json_bytes(payload: bytes) -> dict[str, object]:
    if payload.startswith(b"\xef\xbb\xbf"):
        raise _unavailable()
    try:
        decoded = payload.decode("utf-8")
        value = json.loads(
            decoded,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError):
        raise _unavailable() from None
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise _unavailable()
    return value


def _open_pinned_directory(path: Path) -> tuple[int, tuple[int, int]]:
    try:
        before = os.lstat(path)
        if not stat.S_ISDIR(before.st_mode):
            raise _unavailable()
        descriptor = os.open(path, _DIRECTORY_OPEN_FLAGS)
        opened = os.fstat(descriptor)
    except (OSError, PrevalenceEvidenceUnavailable):
        raise _unavailable() from None
    identity = (opened.st_dev, opened.st_ino)
    if not stat.S_ISDIR(opened.st_mode) or identity != (before.st_dev, before.st_ino):
        os.close(descriptor)
        raise _unavailable()
    return descriptor, identity


def _require_directory_identity(path: Path, identity: tuple[int, int]) -> None:
    try:
        current = os.lstat(path)
    except OSError:
        raise _unavailable() from None
    if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != identity:
        raise _unavailable()


def _relative_parts(relative: str) -> tuple[str, ...]:
    path = Path(relative)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise _unavailable()
    return path.parts


def _read_regular_at(directory_descriptor: int, relative: str, *, maximum_bytes: int | None = None) -> bytes:
    parts = _relative_parts(relative)
    parent = os.dup(directory_descriptor)
    file_descriptor: int | None = None
    try:
        for component in parts[:-1]:
            child = os.open(component, _DIRECTORY_OPEN_FLAGS, dir_fd=parent)
            opened = os.fstat(child)
            if not stat.S_ISDIR(opened.st_mode):
                os.close(child)
                raise _unavailable()
            os.close(parent)
            parent = child
        entry = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISREG(entry.st_mode) or entry.st_nlink != 1:
            raise _unavailable()
        file_descriptor = os.open(parts[-1], _FILE_OPEN_FLAGS, dir_fd=parent)
        opened = os.fstat(file_descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or (
            opened.st_dev,
            opened.st_ino,
        ) != (entry.st_dev, entry.st_ino):
            raise _unavailable()
        payload = bytearray()
        while True:
            chunk = os.read(file_descriptor, 65536)
            if not chunk:
                break
            payload.extend(chunk)
            if maximum_bytes is not None and len(payload) > maximum_bytes:
                raise _unavailable()
        return bytes(payload)
    except (OSError, PrevalenceEvidenceUnavailable):
        raise _unavailable() from None
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        os.close(parent)


def _allowed_tree(descriptor: Mapping[str, object]) -> tuple[frozenset[str], frozenset[str]]:
    resources = descriptor.get("resources")
    if not isinstance(resources, list) or len(resources) != len(_RESOURCE_NAMES):
        raise _unavailable()
    files: set[str] = set(_PACKAGE_ARTIFACTS)
    names: list[str] = []
    for resource in resources:
        if not isinstance(resource, Mapping):
            raise _unavailable()
        name = resource.get("name")
        relative = resource.get("path")
        if not isinstance(name, str) or not isinstance(relative, str):
            raise _unavailable()
        if name not in _RESOURCE_NAMES or name in names:
            raise _unavailable()
        names.append(name)
        parts = _relative_parts(relative)
        canonical = Path(*parts).as_posix()
        if canonical in files:
            raise _unavailable()
        files.add(canonical)
    if tuple(names) != _RESOURCE_NAMES:
        raise _unavailable()
    directories = {
        parent.as_posix()
        for relative in files
        for parent in Path(relative).parents
        if parent.as_posix() != "."
    }
    return frozenset(files), frozenset(directories)


def _scan_exact_tree_at(directory_descriptor: int, files: frozenset[str], directories: frozenset[str]) -> None:
    def scan(parent: int, prefix: tuple[str, ...]) -> None:
        try:
            with os.scandir(parent) as entries:
                names = sorted(entry.name for entry in entries)
        except OSError:
            raise _unavailable() from None
        for name in names:
            relative = "/".join((*prefix, name))
            try:
                metadata = os.stat(name, dir_fd=parent, follow_symlinks=False)
            except OSError:
                raise _unavailable() from None
            if stat.S_ISDIR(metadata.st_mode) and relative in directories:
                try:
                    child = os.open(name, _DIRECTORY_OPEN_FLAGS, dir_fd=parent)
                except OSError:
                    raise _unavailable() from None
                try:
                    opened = os.fstat(child)
                    if not stat.S_ISDIR(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
                        metadata.st_dev,
                        metadata.st_ino,
                    ):
                        raise _unavailable()
                    scan(child, (*prefix, name))
                finally:
                    os.close(child)
            elif stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1 and relative in files:
                continue
            else:
                raise _unavailable()

    scan(directory_descriptor, ())


def _strict_descriptor(payload: bytes) -> dict[str, object]:
    descriptor = _strict_json_bytes(payload)
    try:
        if descriptor.get("profile") != "tabular-data-package":
            raise _unavailable()
        if schema_fingerprint(descriptor) != EXPECTED_SCHEMA_FINGERPRINT:
            raise _unavailable()
    except (KeyError, TypeError, ValueError, PrevalenceEvidenceUnavailable):
        raise _unavailable() from None
    _allowed_tree(descriptor)
    return descriptor


def _parse_manifest(payload: bytes, expected_seed: int, allowed_files: frozenset[str], resource_names: tuple[str, ...]) -> dict[str, object]:
    manifest = _strict_json_bytes(payload)
    if set(manifest) != _MANIFEST_KEYS:
        raise _unavailable()
    if manifest["manifest_version"] != "1" or manifest["status"] != "STRUCTURE_VALIDATED":
        raise _unavailable()
    if manifest["metadata_only"] is not False:
        raise _unavailable()
    seed = _require_seed(manifest["seed"])
    if seed != expected_seed:
        raise _unavailable()
    for field in (
        "generator_version", "profile", "engine", "schema_fingerprint", "reference_time",
        "reference_id", "software_revision", "prng_family", "seed_derivation_version",
    ):
        _require_token(manifest[field])
    for field in ("schema_fingerprint", "configuration_sha256", "reference_sha256", "derivation_fingerprint"):
        _require_digest(manifest[field])
    row_counts = manifest["row_counts"]
    if not isinstance(row_counts, Mapping) or set(row_counts) != set(resource_names):
        raise _unavailable()
    for count in row_counts.values():
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise _unavailable()
    file_hashes = manifest["file_sha256"]
    expected_hash_files = set(allowed_files) - {"manifest.json"}
    if not isinstance(file_hashes, Mapping) or set(file_hashes) != expected_hash_files:
        raise _unavailable()
    for relative, digest in file_hashes.items():
        if not isinstance(relative, str):
            raise _unavailable()
        _relative_parts(relative)
        _require_digest(digest, allow_zero=True)
    return manifest


def _validated_row_counts(directory_descriptor: int, descriptor: Mapping[str, object]) -> dict[str, int]:
    """Run the legacy structural checker only over bytes read through pinned descriptors."""
    resources = descriptor["resources"]
    if not isinstance(resources, list):
        raise _unavailable()
    with tempfile.TemporaryDirectory(prefix="prevalence-evidence-") as staging_name:
        staging = Path(staging_name)
        for resource in resources:
            if not isinstance(resource, Mapping) or not isinstance(resource.get("path"), str):
                raise _unavailable()
            target = staging / resource["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_read_regular_at(directory_descriptor, resource["path"]))
        report = validate_structure(staging, dict(descriptor))
    if report.errors:
        raise _unavailable()
    return report.row_counts


@dataclass(frozen=True)
class _VerifiedPackageSnapshot:
    descriptor: Mapping[str, object]
    manifest: Mapping[str, object]
    allowed_files: frozenset[str]
    allowed_directories: frozenset[str]
    descriptor_sha256: str
    manifest_sha256: str
    row_counts: Mapping[str, int]
    file_sha256: Mapping[str, str]


def _verify_package_snapshot(
    directory_descriptor: int,
    expected_seed: int,
) -> _VerifiedPackageSnapshot:
    """Read one coherent package snapshot strictly through a pinned directory."""
    descriptor_payload = _read_regular_at(
        directory_descriptor,
        "datapackage.json",
        maximum_bytes=PACKAGE_MANIFEST_MAX_BYTES,
    )
    descriptor = _strict_descriptor(descriptor_payload)
    allowed_files, allowed_dirs = _allowed_tree(descriptor)
    _scan_exact_tree_at(directory_descriptor, allowed_files, allowed_dirs)
    manifest_payload = _read_regular_at(
        directory_descriptor,
        "manifest.json",
        maximum_bytes=PACKAGE_MANIFEST_MAX_BYTES,
    )
    resource_names = tuple(resource["name"] for resource in descriptor["resources"])
    manifest = _parse_manifest(manifest_payload, expected_seed, allowed_files, resource_names)
    if manifest["schema_fingerprint"] != schema_fingerprint(descriptor):
        raise _unavailable()
    row_counts = _validated_row_counts(directory_descriptor, descriptor)
    if row_counts != dict(manifest["row_counts"]):
        raise _unavailable()
    file_hashes = {
        relative: hashlib.sha256(_read_regular_at(directory_descriptor, relative)).hexdigest()
        for relative in sorted(set(allowed_files) - {"manifest.json"})
    }
    if file_hashes != dict(manifest["file_sha256"]):
        raise _unavailable()
    _scan_exact_tree_at(directory_descriptor, allowed_files, allowed_dirs)
    return _VerifiedPackageSnapshot(
        descriptor=descriptor,
        manifest=manifest,
        allowed_files=allowed_files,
        allowed_directories=allowed_dirs,
        descriptor_sha256=hashlib.sha256(descriptor_payload).hexdigest(),
        manifest_sha256=hashlib.sha256(manifest_payload).hexdigest(),
        row_counts=row_counts,
        file_sha256=file_hashes,
    )


def _configured_root_identity(root: Path) -> tuple[int, int]:
    descriptor, identity = _open_pinned_directory(root)
    os.close(descriptor)
    return identity


@dataclass(frozen=True)
class PrevalenceRunSpec:
    package_root: Path
    expected_seed: int

    def __post_init__(self) -> None:
        if not isinstance(self.package_root, Path):
            raise TypeError("package_root must be a Path")
        if isinstance(self.expected_seed, bool) or not isinstance(self.expected_seed, int):
            raise TypeError("expected_seed must be an integer")


@dataclass(frozen=True)
class PrevalenceEvidenceConfig:
    runs: tuple[PrevalenceRunSpec, ...]
    heldout_template: HeldoutRunConfig | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.runs, tuple) or not all(isinstance(run, PrevalenceRunSpec) for run in self.runs):
            raise TypeError("runs must be an immutable tuple of PrevalenceRunSpec values")
        if len(self.runs) < 3:
            raise ValueError("runs must contain at least three predeclared packages")
        if len({run.expected_seed for run in self.runs}) != len(self.runs):
            raise ValueError("expected_seed values must be distinct")
        roots = {os.path.realpath(os.path.abspath(run.package_root)) for run in self.runs}
        if len(roots) != len(self.runs):
            raise ValueError("package_root values must be distinct")
        identities = tuple(_configured_root_identity(run.package_root) for run in self.runs)
        if len(set(identities)) != len(identities):
            raise ValueError("package_root values must have distinct directory identities")
        if self.heldout_template is not None and not isinstance(self.heldout_template, HeldoutRunConfig):
            raise TypeError("heldout_template must be a HeldoutRunConfig")


@dataclass(frozen=True)
class PackageIdentity:
    profile: str
    engine: str
    seed: int
    schema_fingerprint: str
    reference_time: str
    reference_id: str
    reference_sha256: str
    configuration_sha256: str
    software_revision: str
    prng_family: str
    seed_derivation_version: str
    derivation_fingerprint: str
    package_sha256: str
    manifest_sha256: str

    def __post_init__(self) -> None:
        _require_seed(self.seed)
        for field in (
            "profile", "engine", "schema_fingerprint", "reference_time", "reference_id",
            "software_revision", "prng_family", "seed_derivation_version",
        ):
            _require_token(getattr(self, field))
        for field in (
            "schema_fingerprint", "reference_sha256", "configuration_sha256", "derivation_fingerprint",
            "package_sha256", "manifest_sha256",
        ):
            _require_digest(getattr(self, field))

    def to_mapping(self) -> dict[str, object]:
        return {
            "profile": self.profile,
            "engine": self.engine,
            "seed": self.seed,
            "schema_fingerprint": self.schema_fingerprint,
            "reference_time": self.reference_time,
            "reference_id": self.reference_id,
            "reference_sha256": self.reference_sha256,
            "configuration_sha256": self.configuration_sha256,
            "software_revision": self.software_revision,
            "prng_family": self.prng_family,
            "seed_derivation_version": self.seed_derivation_version,
            "derivation_fingerprint": self.derivation_fingerprint,
            "package_sha256": self.package_sha256,
            "manifest_sha256": self.manifest_sha256,
        }


@dataclass(frozen=True)
class PrevalenceRunEvidence:
    """Safe per-run identity material; evaluation output is added in Task 2."""

    identity: PackageIdentity

    def __post_init__(self) -> None:
        if not isinstance(self.identity, PackageIdentity):
            raise TypeError("identity must be a PackageIdentity")


def verify_package_identity(spec: PrevalenceRunSpec) -> PackageIdentity:
    """Verify one exact generated package without exposing its location on failure."""
    if not isinstance(spec, PrevalenceRunSpec):
        raise TypeError("spec must be a PrevalenceRunSpec")
    descriptor_fd: int | None = None
    try:
        descriptor_fd, root_identity = _open_pinned_directory(spec.package_root)
        initial = _verify_package_snapshot(descriptor_fd, spec.expected_seed)
        final = _verify_package_snapshot(descriptor_fd, spec.expected_seed)
        if (
            initial.descriptor_sha256 != final.descriptor_sha256
            or initial.manifest_sha256 != final.manifest_sha256
            or initial.allowed_files != final.allowed_files
            or initial.allowed_directories != final.allowed_directories
            or initial.row_counts != final.row_counts
            or initial.file_sha256 != final.file_sha256
        ):
            raise _unavailable()
        _require_directory_identity(spec.package_root, root_identity)
        package_payload = json.dumps(
            dict(final.file_sha256), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("ascii")
        return PackageIdentity(
            profile=str(final.manifest["profile"]),
            engine=str(final.manifest["engine"]),
            seed=spec.expected_seed,
            schema_fingerprint=str(final.manifest["schema_fingerprint"]),
            reference_time=str(final.manifest["reference_time"]),
            reference_id=str(final.manifest["reference_id"]),
            reference_sha256=str(final.manifest["reference_sha256"]),
            configuration_sha256=str(final.manifest["configuration_sha256"]),
            software_revision=str(final.manifest["software_revision"]),
            prng_family=str(final.manifest["prng_family"]),
            seed_derivation_version=str(final.manifest["seed_derivation_version"]),
            derivation_fingerprint=str(final.manifest["derivation_fingerprint"]),
            package_sha256=hashlib.sha256(package_payload).hexdigest(),
            manifest_sha256=final.manifest_sha256,
        )
    except PrevalenceEvidenceUnavailable:
        raise
    except Exception:  # noqa: BLE001 - package input failures are deliberately redacted.
        raise _unavailable() from None
    finally:
        if descriptor_fd is not None:
            os.close(descriptor_fd)


__all__ = [
    "PACKAGE_MANIFEST_MAX_BYTES",
    "PREVALENCE_EVIDENCE_REPORT_VERSION",
    "V1_TARGET_FAMILIES",
    "PackageIdentity",
    "PrevalenceEvidenceConfig",
    "PrevalenceEvidenceUnavailable",
    "PrevalenceRunEvidence",
    "PrevalenceRunSpec",
    "verify_package_identity",
]
