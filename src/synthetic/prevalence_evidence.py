"""Governed identity checks for aggregate multi-run prevalence evidence.

This module is deliberately an evaluator-side boundary.  It accepts generated
package locations only to produce safe, aggregate package identities; those
locations are never retained in public mappings or exception text.
"""

from __future__ import annotations

import argparse
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

from synthetic.calibrate import (
    DEFAULT_AGE_WINDOWS,
    _load_disclosure_policy,
    _load_partition_policy,
    _read_regular_file,
    _write_exclusive_fsynced,
)
from synthetic.calibration_targets import (
    ETHNICITY_CATEGORY_SLUGS,
    RACE_CATEGORY_SLUGS,
    RECORDED_FLAGS,
    SEX_CATEGORY_SLUGS,
    TARGET_REGISTRY_VERSION,
)
from synthetic.heldout_validate import (
    HeldoutComparison,
    HeldoutRunConfig,
    HeldoutValidationReport,
    load_fidelity_policy,
    validate_heldout,
)
from synthetic.run_directory import RunDirectory
from synthetic.schema_contract import EXPECTED_SCHEMA_FINGERPRINT, schema_fingerprint
from synthetic.validate import validate_structure

PREVALENCE_EVIDENCE_REPORT_VERSION = "prevalence-evidence-report-v1"
PACKAGE_MANIFEST_MAX_BYTES = 1024 * 1024
MAX_PREVALENCE_EVIDENCE_OUTPUT_BYTES = 8 * 1024 * 1024
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
_REPORT_FILENAME = "prevalence-evidence-report.json"
_SUMMARY_FILENAME = "prevalence-evidence-summary.txt"
_REPORT_KEYS = frozenset(
    {
        "report_version",
        "status",
        "generation_identity",
        "heldout_identity",
        "runs",
        "comparisons",
    }
)
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
_V1_TARGET_KEYS = frozenset(
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
V1_REQUIRED_TARGET_KEYS: tuple[_TargetKey, ...] = tuple(sorted(_V1_TARGET_KEYS))


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
    _root_identities: tuple[tuple[int, int], ...] = dataclass_field(
        init=False,
        repr=False,
        compare=False,
    )

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
        object.__setattr__(self, "_root_identities", identities)
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
    return _comparison_key(comparison) in _V1_TARGET_KEYS


def _aggregate_status(statuses: tuple[str, ...]) -> str:
    if not statuses:
        return "UNEVALUABLE"
    if "FAIL" in statuses:
        return "FAIL"
    if "UNEVALUABLE" in statuses:
        return "UNEVALUABLE"
    return "PASS"


def _normalize_v1_comparisons(
    comparisons: tuple[HeldoutComparison, ...],
) -> tuple[HeldoutComparison, ...]:
    indexed = {_comparison_key(comparison): comparison for comparison in comparisons}
    if len(indexed) != len(comparisons):
        raise ValueError("comparisons must not contain duplicate canonical keys")
    return tuple(
        indexed.get(
            key,
            HeldoutComparison(*key, "UNEVALUABLE", None, None, None, None),
        )
        for key in V1_REQUIRED_TARGET_KEYS
    )


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
    maximum_tolerance_exceedance: float | None
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
            self.maximum_tolerance_exceedance,
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
                "maximum_tolerance_exceedance",
            ):
                value = getattr(self, field)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError(f"{field} must be a finite aggregate value")
            for field in ("heldout_value", "generated_minimum", "generated_maximum"):
                value = getattr(self, field)
                assert isinstance(value, (int, float)) and not isinstance(value, bool)
                if not 0 <= value <= 1:
                    raise ValueError(f"{field} must be a proportion in [0, 1]")
            assert self.heldout_value is not None
            assert self.generated_minimum is not None
            assert self.generated_maximum is not None
            assert self.maximum_absolute_difference is not None
            assert self.maximum_tolerance_exceedance is not None
            if self.generated_minimum > self.generated_maximum:
                raise ValueError("generated range must be ordered")
            if self.evaluable_count == 1 and self.generated_minimum != self.generated_maximum:
                raise ValueError("one evaluable run must have identical generated extrema")
            expected_difference = max(
                abs(float(self.heldout_value) - float(self.generated_minimum)),
                abs(float(self.heldout_value) - float(self.generated_maximum)),
            )
            if self.maximum_absolute_difference != expected_difference:
                raise ValueError("aggregate difference must match the disclosed range")
            if self.maximum_tolerance_exceedance > self.maximum_absolute_difference:
                raise ValueError("tolerance exceedance cannot exceed the maximum difference")
            if self.fail_count and self.maximum_tolerance_exceedance <= 0:
                raise ValueError("failed comparisons require a positive tolerance exceedance")
            if not self.fail_count and self.maximum_tolerance_exceedance > 0:
                raise ValueError("non-failing comparisons cannot exceed tolerance")
        if self.status == "FAIL" and not self.fail_count:
            raise ValueError("failing comparison requires a failed run")
        if self.status != "FAIL" and self.fail_count:
            raise ValueError("only failing comparisons can contain failed runs")
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
            "maximum_tolerance_exceedance": self.maximum_tolerance_exceedance,
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
    comparisons: tuple[HeldoutComparison, ...] = dataclass_field(repr=False)

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
        normalized_comparisons = _normalize_v1_comparisons(self.comparisons)
        if self.status != _aggregate_status(tuple(item.status for item in normalized_comparisons)):
            raise ValueError("status must match comparisons")
        object.__setattr__(self, "comparisons", normalized_comparisons)

    def to_mapping(self) -> dict[str, object]:
        return {
            "identity": self.identity.to_mapping(),
            "status": self.status,
            "comparison_count": len(self.comparisons),
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
    comparisons: tuple[PrevalenceComparison, ...] = dataclass_field(repr=False)

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
        if self.heldout_identity.schema_fingerprint != expected_generation_identity["schema_fingerprint"]:
            raise ValueError("held-out and generation schema identities must match")
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

    def canonical_json_bytes(self) -> bytes:
        """Return the stable, aggregate-only public report serialization."""
        return _canonical_json_bytes(self.to_mapping())

    def human_summary(self) -> str:
        """Return a deterministic ASCII-only operational summary without values or locations."""
        status_counts = {status: sum(item.status == status for item in self.comparisons) for status in _EVIDENCE_STATUSES}
        return "\n".join(
            (
                "Governed multi-run prevalence evidence",
                f"Report version: {self.report_version}",
                f"Status: {self.status}",
                f"Run count: {len(self.runs)}",
                f"Comparison count: {len(self.comparisons)}",
                f"Passing comparisons: {status_counts['PASS']}",
                f"Failing comparisons: {status_counts['FAIL']}",
                f"Unevaluable comparisons: {status_counts['UNEVALUABLE']}",
                f"Schema fingerprint: {self.generation_identity['schema_fingerprint']}",
                "Target scope: observed demographics and recorded outcomes",
                "",
            )
        )

    def lifecycle_identity(self) -> str:
        """Return a stable safe identity used only to derive a no-replace lifecycle token."""
        identity = {
            "report_version": self.report_version,
            "generation_identity": dict(self.generation_identity),
            "heldout_identity": self.heldout_identity.to_mapping(),
        }
        return hashlib.sha256(_canonical_json_bytes(identity)).hexdigest()


@dataclass(frozen=True)
class PrevalenceEvidenceResult:
    """A validated prevalence-evidence report suitable for transactional publication."""

    report: PrevalenceEvidenceReport

    def __post_init__(self) -> None:
        if not isinstance(self.report, PrevalenceEvidenceReport):
            raise TypeError("report must be a PrevalenceEvidenceReport")


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
def _staged_verified_package(
    spec: PrevalenceRunSpec,
    identity: PackageIdentity,
    configured_root_identity: tuple[int, int],
) -> Iterator[Path]:
    """Stage descriptor-pinned bytes, then verify the staged package before evaluation."""
    descriptor_fd: int | None = None
    try:
        descriptor_fd, root_identity = _open_pinned_directory(spec.package_root)
        if root_identity != configured_root_identity:
            raise _unavailable()
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
            maximum_tolerance_exceedance = max(
                float(difference) - float(tolerance)
                for difference, tolerance in zip(differences, tolerances, strict=True)
                if difference is not None and tolerance is not None
            )
        else:
            heldout_value = None
            generated_minimum = None
            generated_maximum = None
            maximum_absolute_difference = None
            maximum_tolerance_exceedance = None
        aggregate.append(
            PrevalenceComparison(
                *key,
                _aggregate_status(statuses),
                heldout_value,
                generated_minimum,
                generated_maximum,
                maximum_absolute_difference,
                maximum_tolerance_exceedance,
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
        initial = tuple(
            (
                spec,
                root_identity,
                _verify_package_identity(spec, configured_root_identity=root_identity),
            )
            for spec, root_identity in zip(config.runs, config._root_identities, strict=True)
        )
        generation = _generation_identity(initial[0][2])
        if any(_generation_identity(identity) != generation for _, _, identity in initial[1:]):
            raise _unavailable()

        heldout_identity: _HeldoutIdentity | None = None
        run_results: list[PrevalenceRunResult] = []
        for spec, root_identity, identity in initial:
            if _verify_package_identity(spec, configured_root_identity=root_identity) != identity:
                raise _unavailable()
            with _staged_verified_package(spec, identity, root_identity) as staged_root:
                heldout_config = replace(
                    config.heldout_template,
                    synthetic_root=staged_root,
                    output=staged_root / "heldout-output-not-written",
                )
                result = validate_heldout(heldout_config)
                if verify_package_identity(PrevalenceRunSpec(staged_root, spec.expected_seed)) != identity:
                    raise _unavailable()
            if _verify_package_identity(spec, configured_root_identity=root_identity) != identity:
                raise _unavailable()
            report_identity = _HeldoutIdentity.from_report(result.report)
            if report_identity.schema_fingerprint != generation["schema_fingerprint"]:
                raise _unavailable()
            if heldout_identity is None:
                heldout_identity = report_identity
            elif report_identity != heldout_identity:
                raise _unavailable()
            selected = _normalize_v1_comparisons(
                tuple(item for item in result.report.comparisons if _is_v1_comparison(item))
            )
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


def _verify_package_identity(
    spec: PrevalenceRunSpec,
    *,
    configured_root_identity: tuple[int, int] | None = None,
) -> PackageIdentity:
    if not isinstance(spec, PrevalenceRunSpec):
        raise TypeError("spec must be a PrevalenceRunSpec")
    descriptor_fd: int | None = None
    try:
        descriptor_fd, root_identity = _open_pinned_directory(spec.package_root)
        if configured_root_identity is not None and root_identity != configured_root_identity:
            raise _unavailable()
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


def verify_package_identity(spec: PrevalenceRunSpec) -> PackageIdentity:
    """Verify one exact generated package without exposing its location on failure."""
    return _verify_package_identity(spec)


def _canonical_json_bytes(mapping: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            mapping,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


def _require_exact_mapping(value: object, keys: frozenset[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != keys or not all(isinstance(key, str) for key in value):
        raise ValueError("prevalence evidence report is invalid")
    return value


def _parse_public_identity(value: object) -> PackageIdentity:
    keys = frozenset(PackageIdentity.__annotations__)
    mapping = _require_exact_mapping(value, keys)
    try:
        return PackageIdentity(
            profile=mapping["profile"],  # type: ignore[arg-type]
            engine=mapping["engine"],  # type: ignore[arg-type]
            seed=mapping["seed"],  # type: ignore[arg-type]
            schema_fingerprint=mapping["schema_fingerprint"],  # type: ignore[arg-type]
            reference_time=mapping["reference_time"],  # type: ignore[arg-type]
            reference_id=mapping["reference_id"],  # type: ignore[arg-type]
            reference_sha256=mapping["reference_sha256"],  # type: ignore[arg-type]
            configuration_sha256=mapping["configuration_sha256"],  # type: ignore[arg-type]
            software_revision=mapping["software_revision"],  # type: ignore[arg-type]
            prng_family=mapping["prng_family"],  # type: ignore[arg-type]
            seed_derivation_version=mapping["seed_derivation_version"],  # type: ignore[arg-type]
            derivation_fingerprint=mapping["derivation_fingerprint"],  # type: ignore[arg-type]
            package_sha256=mapping["package_sha256"],  # type: ignore[arg-type]
            manifest_sha256=mapping["manifest_sha256"],  # type: ignore[arg-type]
        )
    except (KeyError, TypeError, ValueError, PrevalenceEvidenceUnavailable):
        raise ValueError("prevalence evidence report is invalid") from None


def _validate_generation_identity(value: object) -> dict[str, object]:
    fields = frozenset(PackageIdentity.__annotations__) - {"seed", "package_sha256", "manifest_sha256"}
    mapping = _require_exact_mapping(value, fields)
    try:
        for field in (
            "profile",
            "engine",
            "schema_fingerprint",
            "reference_time",
            "reference_id",
            "software_revision",
            "prng_family",
            "seed_derivation_version",
        ):
            _require_token(mapping[field])
        for field in (
            "schema_fingerprint",
            "reference_sha256",
            "configuration_sha256",
            "derivation_fingerprint",
        ):
            _require_digest(mapping[field])
    except (KeyError, PrevalenceEvidenceUnavailable):
        raise ValueError("prevalence evidence report is invalid") from None
    if mapping["schema_fingerprint"] != EXPECTED_SCHEMA_FINGERPRINT:
        raise ValueError("prevalence evidence report is invalid")
    return dict(mapping)


def _validate_heldout_identity(value: object) -> dict[str, object]:
    mapping = _require_exact_mapping(
        value,
        frozenset(
            {
                "source_snapshot",
                "synthetic_artifact_id",
                "schema_fingerprint",
                "partition_policy",
                "disclosure_policy",
                "fidelity_policy",
            }
        ),
    )
    try:
        _require_token(mapping["source_snapshot"])
        _require_token(mapping["synthetic_artifact_id"])
        _require_digest(mapping["schema_fingerprint"])
        for name in ("partition_policy", "disclosure_policy"):
            policy = _require_exact_mapping(mapping[name], frozenset({"policy_id", "policy_version"}))
            _require_token(policy["policy_id"])
            _require_token(policy["policy_version"])
        fidelity = _require_exact_mapping(
            mapping["fidelity_policy"],
            frozenset({"policy_id", "policy_version", "target_registry_version"}),
        )
        for token in fidelity.values():
            _require_token(token)
    except (KeyError, PrevalenceEvidenceUnavailable):
        raise ValueError("prevalence evidence report is invalid") from None
    if fidelity["target_registry_version"] != TARGET_REGISTRY_VERSION:
        raise ValueError("prevalence evidence report is invalid")
    return {
        "source_snapshot": mapping["source_snapshot"],
        "synthetic_artifact_id": mapping["synthetic_artifact_id"],
        "schema_fingerprint": mapping["schema_fingerprint"],
        "partition_policy": dict(mapping["partition_policy"]),
        "disclosure_policy": dict(mapping["disclosure_policy"]),
        "fidelity_policy": dict(mapping["fidelity_policy"]),
    }


def _parse_prevalence_comparison(value: object) -> PrevalenceComparison:
    if not isinstance(value, Mapping):
        raise TypeError("prevalence evidence report is invalid")
    required = frozenset(
        {
            "stratum_id",
            "target_name",
            "family",
            "statistic",
            "unit",
            "status",
            "heldout_value",
            "generated_minimum",
            "generated_maximum",
            "maximum_absolute_difference",
            "maximum_tolerance_exceedance",
            "evaluable_count",
            "pass_count",
            "fail_count",
        }
    )
    if set(value) not in {required, required | {"quantile_level"}}:
        raise ValueError("prevalence evidence report is invalid")
    try:
        return PrevalenceComparison(
            stratum_id=value["stratum_id"],  # type: ignore[arg-type]
            target_name=value["target_name"],  # type: ignore[arg-type]
            family=value["family"],  # type: ignore[arg-type]
            statistic=value["statistic"],  # type: ignore[arg-type]
            unit=value["unit"],  # type: ignore[arg-type]
            quantile_level=value.get("quantile_level"),  # type: ignore[arg-type]
            status=value["status"],  # type: ignore[arg-type]
            heldout_value=value["heldout_value"],  # type: ignore[arg-type]
            generated_minimum=value["generated_minimum"],  # type: ignore[arg-type]
            generated_maximum=value["generated_maximum"],  # type: ignore[arg-type]
            maximum_absolute_difference=value["maximum_absolute_difference"],  # type: ignore[arg-type]
            maximum_tolerance_exceedance=value["maximum_tolerance_exceedance"],  # type: ignore[arg-type]
            evaluable_count=value["evaluable_count"],  # type: ignore[arg-type]
            pass_count=value["pass_count"],  # type: ignore[arg-type]
            fail_count=value["fail_count"],  # type: ignore[arg-type]
        )
    except (KeyError, TypeError, ValueError, PrevalenceEvidenceUnavailable):
        raise ValueError("prevalence evidence report is invalid") from None


def _parse_prevalence_evidence_report(value: object) -> dict[str, object]:
    """Strictly parse public report fields without reconstructing withheld run values."""
    mapping = _require_exact_mapping(value, _REPORT_KEYS)
    if mapping["report_version"] != PREVALENCE_EVIDENCE_REPORT_VERSION or mapping["status"] not in _EVIDENCE_STATUSES:
        raise ValueError("prevalence evidence report is invalid")
    generation = _validate_generation_identity(mapping["generation_identity"])
    heldout = _validate_heldout_identity(mapping["heldout_identity"])
    if heldout["schema_fingerprint"] != generation["schema_fingerprint"]:
        raise ValueError("prevalence evidence report is invalid")
    raw_runs = mapping["runs"]
    raw_comparisons = mapping["comparisons"]
    if not isinstance(raw_runs, list) or len(raw_runs) < 3 or not isinstance(raw_comparisons, list):
        raise ValueError("prevalence evidence report is invalid")
    identities: list[PackageIdentity] = []
    run_statuses: list[str] = []
    required_comparison_count = len(V1_REQUIRED_TARGET_KEYS)
    for item in raw_runs:
        run = _require_exact_mapping(
            item,
            frozenset({"identity", "status", "comparison_count"}),
        )
        identity = _parse_public_identity(run["identity"])
        if (
            run["status"] not in _EVIDENCE_STATUSES
            or isinstance(run["comparison_count"], bool)
            or not isinstance(run["comparison_count"], int)
            or run["comparison_count"] != required_comparison_count
        ):
            raise ValueError("prevalence evidence report is invalid")
        if _generation_identity(identity) != generation:
            raise ValueError("prevalence evidence report is invalid")
        identities.append(identity)
        run_statuses.append(run["status"])
    if len({identity.seed for identity in identities}) != len(identities) or identities != sorted(
        identities, key=lambda identity: identity.seed
    ):
        raise ValueError("prevalence evidence report is invalid")
    comparisons = tuple(_parse_prevalence_comparison(item) for item in raw_comparisons)
    if tuple(sorted(comparisons, key=lambda item: item.canonical_key)) != comparisons or len(
        {item.canonical_key for item in comparisons}
    ) != len(comparisons):
        raise ValueError("prevalence evidence report is invalid")
    if {item.canonical_key for item in comparisons} != set(V1_REQUIRED_TARGET_KEYS):
        raise ValueError("prevalence evidence report is invalid")
    run_count = len(raw_runs)
    failed_run_count = run_statuses.count("FAIL")
    unevaluable_run_count = run_statuses.count("UNEVALUABLE")
    pass_run_count = run_statuses.count("PASS")
    for comparison in comparisons:
        if comparison.evaluable_count > run_count:
            raise ValueError("prevalence evidence report is invalid")
        missing_count = run_count - comparison.evaluable_count
        if (
            comparison.fail_count > failed_run_count
            or missing_count > failed_run_count + unevaluable_run_count
            or comparison.pass_count < pass_run_count
        ):
            raise ValueError("prevalence evidence report is invalid")
        expected_status = (
            "FAIL"
            if comparison.fail_count
            else "UNEVALUABLE"
            if missing_count
            else "PASS"
        )
        if comparison.status != expected_status:
            raise ValueError("prevalence evidence report is invalid")
    comparison_status = _aggregate_status(tuple(item.status for item in comparisons))
    run_status = _aggregate_status(tuple(run_statuses))
    if mapping["status"] != comparison_status or mapping["status"] != run_status:
        raise ValueError("prevalence evidence report is invalid")
    target_count = len(comparisons)
    failed_cell_count = sum(item.fail_count for item in comparisons)
    missing_cell_count = sum(run_count - item.evaluable_count for item in comparisons)
    passed_cell_count = sum(item.pass_count for item in comparisons)
    if not (
        failed_run_count <= failed_cell_count <= failed_run_count * target_count
        and unevaluable_run_count <= missing_cell_count
        <= (unevaluable_run_count + failed_run_count) * target_count
        and pass_run_count * target_count <= passed_cell_count
    ):
        raise ValueError("prevalence evidence report is invalid")
    return {
        "report_version": mapping["report_version"],
        "status": mapping["status"],
        "generation_identity": generation,
        "heldout_identity": heldout,
        "runs": [dict(item) for item in raw_runs],
        "comparisons": [item.to_mapping() for item in comparisons],
    }


def _reparse_written_prevalence_evidence(run: RunDirectory, result: PrevalenceEvidenceResult) -> None:
    report_bytes = _read_regular_file(
        run.partial_path / _REPORT_FILENAME,
        "prevalence evidence report output",
        maximum_bytes=MAX_PREVALENCE_EVIDENCE_OUTPUT_BYTES,
    )
    summary_bytes = _read_regular_file(
        run.partial_path / _SUMMARY_FILENAME,
        "prevalence evidence summary output",
        maximum_bytes=MAX_PREVALENCE_EVIDENCE_OUTPUT_BYTES,
    )
    try:
        parsed = _parse_prevalence_evidence_report(_strict_json_bytes(report_bytes))
        summary = summary_bytes.decode("ascii", errors="strict")
    except (UnicodeError, ValueError, PrevalenceEvidenceUnavailable):
        raise ValueError("prevalence evidence output cannot be reparsed") from None
    report = result.report
    if (
        parsed != report.to_mapping()
        or report_bytes != report.canonical_json_bytes()
        or summary != report.human_summary()
        or summary_bytes != summary.encode("ascii")
    ):
        raise ValueError("prevalence evidence output is not canonical")


def _lifecycle_run_id(report: PrevalenceEvidenceReport) -> str:
    return report.lifecycle_identity()


def _refuse_existing_lifecycle_path(output: Path, report: PrevalenceEvidenceReport) -> None:
    if os.path.lexists(output):
        raise FileExistsError("prevalence evidence output already exists")
    absolute = Path(os.path.abspath(output))
    lifecycle = _lifecycle_run_id(report)
    candidates = (
        absolute.parent / f".{absolute.name}.{lifecycle}.partial",
        absolute.parent / f".{absolute.name}.{lifecycle}.failed",
    )
    if any(os.path.lexists(path) for path in candidates):
        raise FileExistsError("prevalence evidence output lifecycle path already exists")


def _prepare_failure_archive(run: RunDirectory) -> None:
    for filename in (_REPORT_FILENAME, _SUMMARY_FILENAME):
        try:
            os.unlink(run.partial_path / filename)
        except FileNotFoundError:
            continue
    with os.scandir(run.partial_path) as entries:
        if next(entries, None) is not None:
            raise OSError("prevalence evidence partial output could not be cleared")


def write_prevalence_evidence(result: PrevalenceEvidenceResult, output: Path) -> None:
    """Write a canonical aggregate report and summary using no-replace promotion."""
    if not isinstance(result, PrevalenceEvidenceResult):
        raise TypeError("result must be a PrevalenceEvidenceResult")
    if not isinstance(output, Path):
        raise TypeError("output must be a Path")
    try:
        _refuse_existing_lifecycle_path(output, result.report)
        run = RunDirectory.start(output, _lifecycle_run_id(result.report))
    except FileExistsError:
        raise FileExistsError("prevalence evidence output lifecycle collision") from None
    except (OSError, TypeError, ValueError):
        raise ValueError("prevalence evidence output initialization failed") from None
    try:
        _write_exclusive_fsynced(run.partial_path / _REPORT_FILENAME, result.report.canonical_json_bytes())
        _write_exclusive_fsynced(run.partial_path / _SUMMARY_FILENAME, result.report.human_summary().encode("ascii"))
        _reparse_written_prevalence_evidence(run, result)
        run.promote()
    except Exception:  # noqa: BLE001 - no output failure detail may cross this boundary.
        try:
            _prepare_failure_archive(run)
            run.fail("prevalence evidence output validation failed")
        except Exception:  # noqa: BLE001 - lifecycle errors remain fixed and redacted.
            raise ValueError("prevalence evidence output could not be promoted") from None
        raise ValueError("prevalence evidence output could not be promoted") from None


class _RedactedArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        self.exit(2, "prevalence evidence arguments invalid\n")


def _argument_parser() -> argparse.ArgumentParser:
    parser = _RedactedArgumentParser(
        description="Run governed multi-run prevalence evidence", allow_abbrev=False
    )
    parser.add_argument("--real-root", required=True, type=Path)
    parser.add_argument("--descriptor", required=True, type=Path)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--calibration-artifact", required=True, type=Path)
    parser.add_argument("--calibration-report", required=True, type=Path)
    parser.add_argument("--partition-policy", required=True, type=Path)
    parser.add_argument("--disclosure-policy", required=True, type=Path)
    parser.add_argument("--partition-key-file", required=True, type=Path)
    parser.add_argument("--frozen-policy", required=True, type=Path)
    parser.add_argument("--package-root", required=True, action="append", type=Path)
    parser.add_argument("--expected-seed", required=True, action="append", type=int)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> None:
    """Run the explicit-input prevalence evidence gate with fixed redacted failures."""
    parser = _argument_parser()
    arguments = parser.parse_args()
    if (
        len(arguments.package_root) != len(arguments.expected_seed)
        or len(arguments.package_root) < 3
        or len(set(arguments.expected_seed)) != len(arguments.expected_seed)
    ):
        parser.error("package root and seed counts differ")
    try:
        runs = tuple(
            PrevalenceRunSpec(package_root, expected_seed)
            for package_root, expected_seed in zip(arguments.package_root, arguments.expected_seed, strict=True)
        )
        template = HeldoutRunConfig(
            real_root=arguments.real_root,
            real_descriptor=arguments.descriptor,
            source_snapshot=arguments.snapshot,
            synthetic_root=arguments.package_root[0],
            calibration_artifact=arguments.calibration_artifact,
            calibration_report=arguments.calibration_report,
            partition_policy=_load_partition_policy(arguments.partition_policy),
            disclosure_policy=_load_disclosure_policy(arguments.disclosure_policy),
            partition_key=_read_regular_file(arguments.partition_key_file, "partition key"),
            fidelity_policy=load_fidelity_policy(arguments.frozen_policy),
            age_windows=DEFAULT_AGE_WINDOWS,
            output=arguments.output,
        )
        report = evaluate_prevalence_evidence(PrevalenceEvidenceConfig(runs=runs, heldout_template=template))
        result = PrevalenceEvidenceResult(report)
        write_prevalence_evidence(result, arguments.output)
    except Exception:  # noqa: BLE001 - no governed argument or evaluator details leave the process.
        parser.exit(1, "prevalence evidence failed\n")
    if result.report.status != "PASS":
        parser.exit(1, "prevalence evidence failed\n")


if __name__ == "__main__":  # pragma: no cover - subprocess tests exercise this command.
    main()


__all__ = [
    "MAX_PREVALENCE_EVIDENCE_OUTPUT_BYTES",
    "PACKAGE_MANIFEST_MAX_BYTES",
    "PREVALENCE_EVIDENCE_REPORT_VERSION",
    "V1_REQUIRED_TARGET_KEYS",
    "V1_TARGET_FAMILIES",
    "PackageIdentity",
    "PrevalenceComparison",
    "PrevalenceEvidenceConfig",
    "PrevalenceEvidenceReport",
    "PrevalenceEvidenceResult",
    "PrevalenceEvidenceUnavailable",
    "PrevalenceRunEvidence",
    "PrevalenceRunResult",
    "PrevalenceRunSpec",
    "evaluate_prevalence_evidence",
    "verify_package_identity",
    "write_prevalence_evidence",
]
