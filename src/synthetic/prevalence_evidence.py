"""Governed identity checks for aggregate multi-run prevalence evidence.

This module is deliberately an evaluator-side boundary.  It accepts generated
package locations only to produce safe, aggregate package identities; those
locations are never retained in public mappings or exception text.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from dataclasses import field as dataclass_field
from pathlib import Path

from synthetic.calibration_targets import (
    ETHNICITY_CATEGORY_SLUGS,
    RACE_CATEGORY_SLUGS,
    RECORDED_FLAGS,
    SEX_CATEGORY_SLUGS,
    is_registered_target_key,
)
from synthetic.heldout_validate import (
    HeldoutComparison,
    HeldoutRunConfig,
    HeldoutValidationReport,
    validate_heldout,
)
from synthetic.schema_contract import EXPECTED_SCHEMA_FINGERPRINT, schema_fingerprint
from synthetic.validate import validate_structure

PREVALENCE_EVIDENCE_REPORT_VERSION = "prevalence-evidence-report-v1"
PACKAGE_MANIFEST_MAX_BYTES = 1024 * 1024
V1_TARGET_FAMILIES = frozenset({"demographics", "recorded_outcome"})
_EVIDENCE_STATUSES = ("PASS", "FAIL", "UNEVALUABLE")
_OBSERVED_OUTCOME_LAYER = "outcome_layer=observed"

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

_TargetKey = tuple[str, str, str, str, str, float | None]
V1_REQUIRED_TARGET_KEYS: tuple[_TargetKey, ...] = tuple(
    sorted(
        (
            *(
                (_OBSERVED_OUTCOME_LAYER, f"sex_{slug}", "demographics", "proportion", "proportion", None)
                for slug in SEX_CATEGORY_SLUGS.values()
            ),
            (_OBSERVED_OUTCOME_LAYER, "race_multiselect", "demographics", "proportion", "proportion", None),
            *(
                (
                    _OBSERVED_OUTCOME_LAYER,
                    f"ethnicity_{slug}",
                    "demographics",
                    "proportion",
                    "proportion",
                    None,
                )
                for slug in ETHNICITY_CATEGORY_SLUGS.values()
            ),
            *(
                (_OBSERVED_OUTCOME_LAYER, f"race_{slug}", "demographics", "proportion", "proportion", None)
                for slug in RACE_CATEGORY_SLUGS.values()
            ),
            *(
                (_OBSERVED_OUTCOME_LAYER, flag, "recorded_outcome", "proportion", "proportion", None)
                for flag in RECORDED_FLAGS.values()
            ),
        )
    )
)


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


def _comparison_key(comparison: HeldoutComparison) -> _TargetKey:
    return (
        comparison.stratum_id,
        comparison.target_name,
        comparison.family,
        comparison.statistic,
        comparison.unit,
        comparison.quantile_level,
    )


def _is_v1_comparison(comparison: HeldoutComparison) -> bool:
    return (
        comparison.stratum_id == _OBSERVED_OUTCOME_LAYER
        and comparison.family in V1_TARGET_FAMILIES
        and is_registered_target_key(*_comparison_key(comparison))
    )


def _aggregate_status(statuses: tuple[str, ...]) -> str:
    if not statuses:
        return "UNEVALUABLE"
    if "FAIL" in statuses:
        return "FAIL"
    if "UNEVALUABLE" in statuses:
        return "UNEVALUABLE"
    return "PASS"


@dataclass(frozen=True)
class PrevalenceComparison:
    """One safe v1 target comparison aggregated across all predeclared runs."""

    stratum_id: str
    target_name: str
    family: str
    statistic: str
    unit: str
    quantile_level: float | None
    status: str
    heldout_value: int | float | None
    generated_minimum: int | float | None
    generated_maximum: int | float | None
    maximum_absolute_difference: float | None
    tolerance: float | None
    evaluable_count: int
    pass_count: int
    fail_count: int

    def __post_init__(self) -> None:
        target = HeldoutComparison(
            self.stratum_id,
            self.target_name,
            self.family,
            self.statistic,
            self.unit,
            self.quantile_level,
            "UNEVALUABLE",
            None,
            None,
            None,
            None,
        )
        if not _is_v1_comparison(target):
            raise ValueError("comparison must be a v1 observed target")
        if self.status not in _EVIDENCE_STATUSES:
            raise ValueError("status must be PASS, FAIL, or UNEVALUABLE")
        for field in ("evaluable_count", "pass_count", "fail_count"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field} must be a nonnegative integer")
        if self.pass_count + self.fail_count != self.evaluable_count:
            raise ValueError("evaluable counts must match pass and fail counts")
        values = (
            self.heldout_value,
            self.generated_minimum,
            self.generated_maximum,
            self.maximum_absolute_difference,
            self.tolerance,
        )
        if self.evaluable_count == 0:
            if any(value is not None for value in values):
                raise ValueError("unevaluable aggregate values must be null")
        elif any(value is None for value in values):
            raise ValueError("evaluable aggregate values must be present")
        else:
            for field in (
                "heldout_value",
                "generated_minimum",
                "generated_maximum",
                "maximum_absolute_difference",
                "tolerance",
            ):
                value = getattr(self, field)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError(f"{field} must be a finite aggregate value")
            assert self.heldout_value is not None
            assert self.generated_minimum is not None
            assert self.generated_maximum is not None
            assert self.maximum_absolute_difference is not None
            assert self.tolerance is not None
            if self.generated_minimum > self.generated_maximum:
                raise ValueError("generated range must be ordered")
            expected_difference = max(
                abs(float(self.heldout_value) - float(self.generated_minimum)),
                abs(float(self.heldout_value) - float(self.generated_maximum)),
            )
            if self.maximum_absolute_difference != expected_difference or self.tolerance < 0:
                raise ValueError("aggregate difference and tolerance must be valid")
        if self.status == "PASS" and self.fail_count:
            raise ValueError("passing comparison cannot contain failures")
        if self.status == "FAIL" and not self.fail_count:
            raise ValueError("failing comparison requires a failed run")
        if self.status == "PASS" and self.evaluable_count != self.pass_count:
            raise ValueError("passing comparison requires every run to pass")

    @property
    def canonical_key(self) -> _TargetKey:
        return (
            self.stratum_id,
            self.target_name,
            self.family,
            self.statistic,
            self.unit,
            self.quantile_level,
        )

    def to_mapping(self) -> dict[str, object]:
        value: dict[str, object] = {
            "stratum_id": self.stratum_id,
            "target_name": self.target_name,
            "family": self.family,
            "statistic": self.statistic,
            "unit": self.unit,
            "status": self.status,
            "heldout_value": self.heldout_value,
            "generated_minimum": self.generated_minimum,
            "generated_maximum": self.generated_maximum,
            "maximum_absolute_difference": self.maximum_absolute_difference,
            "tolerance": self.tolerance,
            "evaluable_count": self.evaluable_count,
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
        }
        if self.quantile_level is not None:
            value["quantile_level"] = self.quantile_level
        return value


@dataclass(frozen=True)
class PrevalenceRunResult:
    """Safe identity and v1-only status for one staged held-out evaluation."""

    identity: PackageIdentity
    status: str
    comparisons: tuple[HeldoutComparison, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.identity, PackageIdentity):
            raise TypeError("identity must be a PackageIdentity")
        if self.status not in _EVIDENCE_STATUSES:
            raise ValueError("status must be PASS, FAIL, or UNEVALUABLE")
        if not isinstance(self.comparisons, tuple) or not all(
            isinstance(comparison, HeldoutComparison) for comparison in self.comparisons
        ):
            raise TypeError("comparisons must be a tuple of HeldoutComparison values")
        if any(not _is_v1_comparison(comparison) for comparison in self.comparisons):
            raise ValueError("comparisons must contain only v1 observed targets")
        if len({_comparison_key(comparison) for comparison in self.comparisons}) != len(self.comparisons):
            raise ValueError("comparisons must not contain duplicate canonical keys")
        sorted_comparisons = tuple(sorted(self.comparisons, key=_comparison_key))
        if self.status != _aggregate_status(tuple(item.status for item in sorted_comparisons)):
            raise ValueError("status must match comparisons")
        object.__setattr__(self, "comparisons", sorted_comparisons)

    def to_mapping(self) -> dict[str, object]:
        return {
            "identity": self.identity.to_mapping(),
            "status": self.status,
            "comparisons": [comparison.to_mapping() for comparison in self.comparisons],
        }


@dataclass(frozen=True)
class _HeldoutIdentity:
    source_snapshot: str
    synthetic_artifact_id: str
    schema_fingerprint: str
    partition_policy: tuple[tuple[str, object], ...]
    disclosure_policy: tuple[tuple[str, object], ...]
    fidelity_policy: tuple[tuple[str, object], ...]
    heldout_aggregate_sha256: str = dataclass_field(repr=False)
    synthetic_aggregate_sha256: str = dataclass_field(repr=False)

    @classmethod
    def from_report(cls, report: HeldoutValidationReport) -> _HeldoutIdentity:
        return cls(
            source_snapshot=report.source_snapshot,
            synthetic_artifact_id=report.synthetic_artifact_id,
            schema_fingerprint=report.schema_fingerprint,
            partition_policy=tuple(sorted(report.partition_policy.items())),
            disclosure_policy=tuple(sorted(report.disclosure_policy.items())),
            fidelity_policy=tuple(sorted(report.fidelity_policy.to_report_mapping().items())),
            heldout_aggregate_sha256=report.heldout_aggregate_sha256,
            synthetic_aggregate_sha256=report.synthetic_aggregate_sha256,
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "source_snapshot": self.source_snapshot,
            "synthetic_artifact_id": self.synthetic_artifact_id,
            "schema_fingerprint": self.schema_fingerprint,
            "partition_policy": dict(self.partition_policy),
            "disclosure_policy": dict(self.disclosure_policy),
            "fidelity_policy": dict(self.fidelity_policy),
        }


def _generation_identity(identity: PackageIdentity) -> dict[str, object]:
    return {
        key: value
        for key, value in identity.to_mapping().items()
        if key not in {"seed", "package_sha256", "manifest_sha256"}
    }


@dataclass(frozen=True)
class PrevalenceEvidenceReport:
    report_version: str
    status: str
    generation_identity: Mapping[str, object]
    heldout_identity: _HeldoutIdentity
    runs: tuple[PrevalenceRunResult, ...]
    comparisons: tuple[PrevalenceComparison, ...]

    def __post_init__(self) -> None:
        if self.report_version != PREVALENCE_EVIDENCE_REPORT_VERSION:
            raise ValueError("report_version is incompatible")
        if self.status not in _EVIDENCE_STATUSES:
            raise ValueError("status must be PASS, FAIL, or UNEVALUABLE")
        if not isinstance(self.heldout_identity, _HeldoutIdentity):
            raise TypeError("heldout_identity must be a _HeldoutIdentity")
        if not isinstance(self.runs, tuple) or len(self.runs) < 3 or not all(
            isinstance(run, PrevalenceRunResult) for run in self.runs
        ):
            raise ValueError("runs must be a tuple of at least three PrevalenceRunResult values")
        if len({run.identity.seed for run in self.runs}) != len(self.runs):
            raise ValueError("run seeds must be distinct")
        expected_generation_identity = _generation_identity(self.runs[0].identity)
        if dict(self.generation_identity) != expected_generation_identity or any(
            _generation_identity(run.identity) != expected_generation_identity for run in self.runs[1:]
        ):
            raise ValueError("runs must share one generation identity")
        if not isinstance(self.comparisons, tuple) or not all(
            isinstance(comparison, PrevalenceComparison) for comparison in self.comparisons
        ):
            raise TypeError("comparisons must be a tuple of PrevalenceComparison values")
        sorted_runs = tuple(sorted(self.runs, key=lambda run: run.identity.seed))
        recomputed_comparisons = _aggregate_comparisons(sorted_runs)
        if self.comparisons != recomputed_comparisons:
            raise ValueError("comparisons must exactly match canonical run evidence")
        expected_status = _aggregate_status(tuple(item.status for item in recomputed_comparisons))
        if self.status != expected_status:
            raise ValueError("status must match v1 aggregate comparisons")
        object.__setattr__(self, "generation_identity", dict(expected_generation_identity))
        object.__setattr__(self, "runs", sorted_runs)
        object.__setattr__(self, "comparisons", recomputed_comparisons)

    def to_mapping(self) -> dict[str, object]:
        return {
            "report_version": self.report_version,
            "status": self.status,
            "generation_identity": dict(self.generation_identity),
            "heldout_identity": self.heldout_identity.to_mapping(),
            "runs": [run.to_mapping() for run in self.runs],
            "comparisons": [comparison.to_mapping() for comparison in self.comparisons],
        }


def _snapshot_matches_identity(snapshot: _VerifiedPackageSnapshot, identity: PackageIdentity) -> bool:
    file_payload = json.dumps(
        dict(snapshot.file_sha256), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")
    return (
        snapshot.manifest.get("profile") == identity.profile
        and snapshot.manifest.get("engine") == identity.engine
        and snapshot.manifest.get("seed") == identity.seed
        and snapshot.manifest.get("schema_fingerprint") == identity.schema_fingerprint
        and snapshot.manifest.get("reference_time") == identity.reference_time
        and snapshot.manifest.get("reference_id") == identity.reference_id
        and snapshot.manifest.get("reference_sha256") == identity.reference_sha256
        and snapshot.manifest.get("configuration_sha256") == identity.configuration_sha256
        and snapshot.manifest.get("software_revision") == identity.software_revision
        and snapshot.manifest.get("prng_family") == identity.prng_family
        and snapshot.manifest.get("seed_derivation_version") == identity.seed_derivation_version
        and snapshot.manifest.get("derivation_fingerprint") == identity.derivation_fingerprint
        and hashlib.sha256(file_payload).hexdigest() == identity.package_sha256
        and snapshot.manifest_sha256 == identity.manifest_sha256
    )


@contextmanager
def _staged_verified_package(spec: PrevalenceRunSpec, identity: PackageIdentity) -> Iterator[Path]:
    """Stage descriptor-pinned bytes, then verify the staged package before evaluation."""
    descriptor_fd: int | None = None
    try:
        descriptor_fd, root_identity = _open_pinned_directory(spec.package_root)
        snapshot = _verify_package_snapshot(descriptor_fd, spec.expected_seed)
        if not _snapshot_matches_identity(snapshot, identity):
            raise _unavailable()
        with tempfile.TemporaryDirectory(prefix="prevalence-evidence-stage-") as temporary_name:
            stage_root = Path(temporary_name) / "package"
            stage_root.mkdir(mode=0o700)
            for relative in sorted(snapshot.allowed_files):
                target = stage_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(_read_regular_at(descriptor_fd, relative))
                os.chmod(target, 0o400)
            _require_directory_identity(spec.package_root, root_identity)
            staged_identity = verify_package_identity(PrevalenceRunSpec(stage_root, spec.expected_seed))
            if staged_identity != identity:
                raise _unavailable()
            directories = sorted(
                (path for path in stage_root.rglob("*") if path.is_dir()),
                key=lambda path: len(path.parts),
                reverse=True,
            )
            try:
                for directory in directories:
                    os.chmod(directory, 0o500)
                os.chmod(stage_root, 0o500)
                yield stage_root
            finally:
                os.chmod(stage_root, 0o700)
                for directory in reversed(directories):
                    os.chmod(directory, 0o700)
    except PrevalenceEvidenceUnavailable:
        raise
    except Exception:  # noqa: BLE001 - all package-boundary failures stay fixed and redacted.
        raise _unavailable() from None
    finally:
        if descriptor_fd is not None:
            os.close(descriptor_fd)


def _aggregate_comparisons(runs: tuple[PrevalenceRunResult, ...]) -> tuple[PrevalenceComparison, ...]:
    indexed_runs = [{_comparison_key(item): item for item in run.comparisons} for run in runs]
    keys = sorted({key for indexed in indexed_runs for key in indexed} | set(V1_REQUIRED_TARGET_KEYS))
    aggregate: list[PrevalenceComparison] = []
    for key in keys:
        entries = tuple(indexed.get(key) for indexed in indexed_runs)
        present = tuple(entry for entry in entries if entry is not None)
        statuses = tuple(entry.status if entry is not None else "UNEVALUABLE" for entry in entries)
        evaluable = tuple(entry for entry in present if entry.status != "UNEVALUABLE")
        failures = tuple(entry for entry in evaluable if entry.status == "FAIL")
        if evaluable:
            heldout_values = {entry.heldout_value for entry in evaluable}
            if len(heldout_values) != 1:
                raise _unavailable()
            generated_values = tuple(entry.synthetic_value for entry in evaluable)
            differences = tuple(entry.difference for entry in evaluable)
            tolerances = tuple(entry.tolerance for entry in evaluable)
            if any(value is None for value in (*generated_values, *differences, *tolerances)):
                raise _unavailable()
            heldout_value = next(iter(heldout_values))
            if heldout_value is None:
                raise _unavailable()
            generated_minimum = min(value for value in generated_values if value is not None)
            generated_maximum = max(value for value in generated_values if value is not None)
            maximum_absolute_difference = max(value for value in differences if value is not None)
            tolerance = max(value for value in tolerances if value is not None)
        else:
            heldout_value = None
            generated_minimum = None
            generated_maximum = None
            maximum_absolute_difference = None
            tolerance = None
        aggregate.append(
            PrevalenceComparison(
                *key,
                _aggregate_status(statuses),
                heldout_value,
                generated_minimum,
                generated_maximum,
                maximum_absolute_difference,
                tolerance,
                len(evaluable),
                sum(entry.status == "PASS" for entry in evaluable),
                len(failures),
            )
        )
    return tuple(aggregate)


def evaluate_prevalence_evidence(config: PrevalenceEvidenceConfig) -> PrevalenceEvidenceReport:
    """Evaluate exact staged package bytes against one frozen held-out policy."""
    if not isinstance(config, PrevalenceEvidenceConfig):
        raise TypeError("config must be a PrevalenceEvidenceConfig")
    if config.heldout_template is None:
        raise _unavailable()
    try:
        initial = tuple((spec, verify_package_identity(spec)) for spec in config.runs)
        generation = _generation_identity(initial[0][1])
        if any(_generation_identity(identity) != generation for _, identity in initial[1:]):
            raise _unavailable()

        heldout_identity: _HeldoutIdentity | None = None
        run_results: list[PrevalenceRunResult] = []
        for spec, identity in initial:
            if verify_package_identity(spec) != identity:
                raise _unavailable()
            with _staged_verified_package(spec, identity) as staged_root:
                heldout_config = replace(
                    config.heldout_template,
                    synthetic_root=staged_root,
                    output=staged_root / "heldout-output-not-written",
                )
                result = validate_heldout(heldout_config)
                if verify_package_identity(PrevalenceRunSpec(staged_root, spec.expected_seed)) != identity:
                    raise _unavailable()
            if verify_package_identity(spec) != identity:
                raise _unavailable()
            report_identity = _HeldoutIdentity.from_report(result.report)
            if heldout_identity is None:
                heldout_identity = report_identity
            elif report_identity != heldout_identity:
                raise _unavailable()
            selected = tuple(item for item in result.report.comparisons if _is_v1_comparison(item))
            run_results.append(
                PrevalenceRunResult(
                    identity=identity,
                    status=_aggregate_status(tuple(item.status for item in selected)),
                    comparisons=selected,
                )
            )
        assert heldout_identity is not None
        sorted_runs = tuple(sorted(run_results, key=lambda run: run.identity.seed))
        comparisons = _aggregate_comparisons(sorted_runs)
        status = _aggregate_status(tuple(item.status for item in comparisons))
        return PrevalenceEvidenceReport(
            report_version=PREVALENCE_EVIDENCE_REPORT_VERSION,
            status=status,
            generation_identity=generation,
            heldout_identity=heldout_identity,
            runs=sorted_runs,
            comparisons=comparisons,
        )
    except PrevalenceEvidenceUnavailable:
        raise
    except Exception:  # noqa: BLE001 - governed input and held-out failures are redacted.
        raise _unavailable() from None


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
    "V1_REQUIRED_TARGET_KEYS",
    "V1_TARGET_FAMILIES",
    "PackageIdentity",
    "PrevalenceComparison",
    "PrevalenceEvidenceConfig",
    "PrevalenceEvidenceReport",
    "PrevalenceEvidenceUnavailable",
    "PrevalenceRunEvidence",
    "PrevalenceRunResult",
    "PrevalenceRunSpec",
    "evaluate_prevalence_evidence",
    "verify_package_identity",
]
