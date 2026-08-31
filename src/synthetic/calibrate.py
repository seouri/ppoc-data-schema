"""Governed aggregate calibration models, orchestration, and command line."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType

import duckdb

if __name__ == "__main__":
    # Keep runtime type identity stable when dependencies import the public module.
    sys.modules["synthetic.calibrate"] = sys.modules[__name__]

from synthetic.calibration import (
    CalibrationArtifact,
    CalibrationDisclosurePolicy,
    contains_serialized_metadata_unsafe_material,
    require_aggregate_safe_token,
)
from synthetic.calibration_disclosure import build_result, disclose_targets
from synthetic.calibration_input import (  # noqa: F401
    CalibrationInput,
    PartitionLabel,
    PartitionSummary,
    assign_partition,
    prepare_input,
    prepare_synthetic_input,
)
from synthetic.calibration_targets import (  # noqa: F401
    DIAGNOSIS_AGE_SUMMARIES,
    ENCOUNTER_CATEGORY_SLUGS,
    ETHNICITY_CATEGORY_SLUGS,
    LOGICAL_LINK_RESOURCES,
    MEASUREMENT_AVAILABILITY,
    PHYSIOLOGY_METRICS,
    RACE_CATEGORY_SLUGS,
    RECORDED_FLAGS,
    SEX_CATEGORY_SLUGS,
    TARGET_REGISTRY_VERSION,
    RawTarget,
    compute_raw_targets,
)
from synthetic.run_directory import RunDirectory

# Downstream calibration stages consume this governed boundary without exposing it to generators.

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_UTC_TIMESTAMP_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
_REPORT_KEYS = frozenset(
    {
        "report_version",
        "status",
        "source_snapshot",
        "schema_fingerprint",
        "partition_policy",
        "partition_counts",
        "resource_row_counts",
        "target_family_counts",
        "suppression_counts",
        "source_aggregate_sha256",
        "checks",
    }
)
_PARTITION_LABELS = frozenset({"calibration", "held_out"})
_RESOURCE_NAMES = frozenset(
    {
        "patients",
        "patients_augmented",
        "visits",
        "visits_augmented",
        "labs",
        "medications",
        "problem_list",
        "referrals",
    }
)
_TARGET_FAMILIES = frozenset(
    {"demographics", "observation", "physiology", "utilization", "recorded_outcome"}
)
_SENSITIVE_DETAIL_WORDS = frozenset({"patient", "visit", "path", "key", "identifier"})
_AGGREGATE_CHECK_DETAILS = frozenset(
    {
        ("schema", "schema contract matched"),
        ("partition", "partition counts available"),
        ("target_registry", "target registry complete"),
        ("disclosure", "disclosure controls applied"),
    }
)
_ARTIFACT_FILENAME = "calibration-artifact.json"
_REPORT_FILENAME = "calibration-report.json"
MAX_CALIBRATION_REPORT_BYTES = 1024 * 1024
CALIBRATION_REPORT_VERSION = "calibration-report-v1"
_PARTITION_POLICY_KEYS = frozenset(
    {
        "policy_id",
        "policy_version",
        "key_id",
        "calibration_basis_points",
        "minimum_partition_patients",
    }
)
_DISCLOSURE_POLICY_KEYS = frozenset(
    {
        "policy_id",
        "policy_version",
        "minimum_cell_count",
        "continuous_rounding_decimals",
    }
)


def _require_token(value: object, field: str) -> str:
    if not isinstance(value, str) or _TOKEN_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be an ASCII token without whitespace or path separators")
    return value


def _require_integer(value: object, field: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")  # noqa: TRY004
    if minimum is not None and value < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    return value


def _require_sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase 64-hex sha256")
    return value


def _require_utc_timestamp(value: object) -> str:
    if not isinstance(value, str) or _UTC_TIMESTAMP_RE.fullmatch(value) is None:
        raise ValueError("created_at must be an exact UTC timestamp")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValueError("created_at must be a valid Gregorian UTC timestamp") from exc
    return value


def _contains_sensitive_report_material(value: str) -> bool:
    """Detect values that could carry governed identifiers, paths, or key material."""
    camel_separated = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)
    words = frozenset(re.findall(r"[a-z0-9]+", camel_separated.lower()))
    return (
        contains_serialized_metadata_unsafe_material(value)
        or bool(words & _SENSITIVE_DETAIL_WORDS)
    )


def _require_aggregate_detail(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a nonempty aggregate detail")
    if _contains_sensitive_report_material(value):
        raise ValueError(f"{field} must be aggregate-only")
    return value


def _require_calibration_check_detail(name: str, value: object, field: str) -> str:
    detail = _require_aggregate_detail(value, field)
    if (name, detail) not in _AGGREGATE_CHECK_DETAILS:
        raise ValueError(f"{field} must be aggregate-only")
    return detail


def _require_safe_report_token(value: object, field: str) -> str:
    token = _require_token(value, field)
    if _contains_sensitive_report_material(token):
        raise ValueError(f"{field} must be aggregate-only")
    return token


@dataclass(frozen=True)
class PartitionPolicy:
    policy_id: str
    policy_version: str
    key_id: str
    calibration_basis_points: int
    minimum_partition_patients: int

    def __post_init__(self) -> None:
        require_aggregate_safe_token(self.policy_id, "policy_id")
        require_aggregate_safe_token(self.policy_version, "policy_version")
        _require_token(self.key_id, "key_id")
        basis_points = _require_integer(self.calibration_basis_points, "calibration_basis_points")
        if not 1 <= basis_points <= 9_999:
            raise ValueError("calibration_basis_points must be in 1..9999")
        _require_integer(self.minimum_partition_patients, "minimum_partition_patients", minimum=1)

    def to_report_mapping(self) -> dict[str, str]:
        """Return the public policy identity without any key identifier."""
        return {"policy_id": self.policy_id, "policy_version": self.policy_version}


@dataclass(frozen=True)
class CalibrationAgeWindow:
    window_id: str
    lower_age_days: int
    upper_age_days: int

    def __post_init__(self) -> None:
        require_aggregate_safe_token(self.window_id, "window_id")
        lower = _require_integer(self.lower_age_days, "lower_age_days", minimum=0)
        upper = _require_integer(self.upper_age_days, "upper_age_days", minimum=1)
        if lower >= upper:
            raise ValueError("age window upper_age_days must be greater than lower_age_days")


DEFAULT_AGE_WINDOWS = (
    CalibrationAgeWindow("infancy", 0, 730),
    CalibrationAgeWindow("childhood", 730, 3287),
    CalibrationAgeWindow("puberty_window", 3287, 5479),
    CalibrationAgeWindow("adolescence", 5479, 7306),
)


@dataclass(frozen=True)
class CalibrationRunConfig:
    data_root: Path
    source_descriptor: Path
    source_snapshot: str
    artifact_id: str
    created_at: str
    partition_policy: PartitionPolicy
    disclosure_policy: CalibrationDisclosurePolicy
    partition_key: bytes
    age_windows: tuple[CalibrationAgeWindow, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.data_root, Path):
            raise ValueError("data_root must be a Path")  # noqa: TRY004
        if not isinstance(self.source_descriptor, Path):
            raise ValueError("source_descriptor must be a Path")  # noqa: TRY004
        require_aggregate_safe_token(self.source_snapshot, "source_snapshot")
        require_aggregate_safe_token(self.artifact_id, "artifact_id")
        _require_utc_timestamp(self.created_at)
        if not isinstance(self.partition_policy, PartitionPolicy):
            raise ValueError("partition_policy must be a PartitionPolicy")  # noqa: TRY004
        if not isinstance(self.disclosure_policy, CalibrationDisclosurePolicy):
            raise ValueError("disclosure_policy must be a CalibrationDisclosurePolicy")  # noqa: TRY004
        if not isinstance(self.partition_key, bytes) or len(self.partition_key) < 16:
            raise ValueError("partition_key must contain at least 16 bytes")
        if not isinstance(self.age_windows, tuple) or not self.age_windows:
            raise ValueError("age_windows must be a nonempty immutable tuple")
        if not all(isinstance(window, CalibrationAgeWindow) for window in self.age_windows):
            raise ValueError("age_windows must contain CalibrationAgeWindow values")
        if len({window.window_id for window in self.age_windows}) != len(self.age_windows):
            raise ValueError("age window_id values must be unique")
        for previous, current in zip(self.age_windows, self.age_windows[1:], strict=False):
            if current.lower_age_days < previous.upper_age_days:
                raise ValueError("age_windows must be ordered and non-overlapping")


@dataclass(frozen=True)
class CalibrationCheck:
    name: str
    passed: bool
    detail: str

    def __post_init__(self) -> None:
        name = _require_safe_report_token(self.name, "check name")
        if not isinstance(self.passed, bool):
            raise ValueError("check passed must be a boolean")  # noqa: TRY004
        _require_calibration_check_detail(name, self.detail, "check detail")

    def to_mapping(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


def _require_aggregate_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an aggregate mapping")
    return value


def _require_count(value: object, field: str) -> int:
    return _require_integer(value, field, minimum=0)


def _validate_partition_counts(value: object, field: str) -> Mapping[str, object]:
    mapping = _require_aggregate_mapping(value, field)
    if set(mapping) != _PARTITION_LABELS:
        raise ValueError(f"{field} must contain only aggregate partition counts")
    for label, count in mapping.items():
        _require_count(count, f"{field}.{label}")
    return mapping


def _validate_resource_row_counts(value: object) -> Mapping[str, object]:
    mapping = _require_aggregate_mapping(value, "resource_row_counts")
    if not set(mapping).issubset(_RESOURCE_NAMES):
        raise ValueError("resource_row_counts must contain only aggregate resource counts")
    for resource, counts in mapping.items():
        _validate_partition_counts(counts, f"resource_row_counts.{resource}")
    return mapping


def _validate_family_counts(value: object, field: str) -> Mapping[str, object]:
    mapping = _require_aggregate_mapping(value, field)
    if not set(mapping).issubset(_TARGET_FAMILIES):
        raise ValueError(f"{field} must contain only aggregate target-family counts")
    for family, count in mapping.items():
        _require_count(count, f"{field}.{family}")
    return mapping


def _validate_partition_policy(value: object) -> Mapping[str, object]:
    mapping = _require_aggregate_mapping(value, "partition_policy")
    if set(mapping) != {"policy_id", "policy_version"}:
        raise ValueError("partition_policy must contain only aggregate policy identity")
    _require_safe_report_token(mapping["policy_id"], "partition_policy.policy_id")
    _require_safe_report_token(mapping["policy_version"], "partition_policy.policy_version")
    return mapping


def _freeze_aggregate_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(
        {
            key: _freeze_aggregate_mapping(item) if isinstance(item, Mapping) else item
            for key, item in value.items()
        }
    )


def _copy_aggregate_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return {
        key: _copy_aggregate_mapping(item) if isinstance(item, Mapping) else item
        for key, item in value.items()
    }


@dataclass(frozen=True)
class CalibrationReport:
    report_version: str
    status: str
    source_snapshot: str
    schema_fingerprint: str
    partition_policy: Mapping[str, object]
    partition_counts: Mapping[str, object]
    resource_row_counts: Mapping[str, object]
    target_family_counts: Mapping[str, object]
    suppression_counts: Mapping[str, object]
    source_aggregate_sha256: str
    checks: tuple[CalibrationCheck, ...]

    def __post_init__(self) -> None:
        if self.report_version != CALIBRATION_REPORT_VERSION:
            raise ValueError(
                f"report_version must be {CALIBRATION_REPORT_VERSION}"
            )
        if self.status != "AGGREGATES_ONLY":
            raise ValueError("status must be AGGREGATES_ONLY")
        _require_safe_report_token(self.source_snapshot, "source_snapshot")
        _require_sha256(self.schema_fingerprint, "schema_fingerprint")
        _require_sha256(self.source_aggregate_sha256, "source_aggregate_sha256")
        validators = {
            "partition_policy": _validate_partition_policy,
            "partition_counts": lambda value: _validate_partition_counts(value, "partition_counts"),
            "resource_row_counts": _validate_resource_row_counts,
            "target_family_counts": lambda value: _validate_family_counts(value, "target_family_counts"),
            "suppression_counts": lambda value: _validate_family_counts(value, "suppression_counts"),
        }
        for field, validator in validators.items():
            validated = validator(getattr(self, field))
            object.__setattr__(self, field, _freeze_aggregate_mapping(validated))
        if not isinstance(self.checks, tuple) or not self.checks:
            raise ValueError("checks must be a nonempty immutable tuple")
        if not all(isinstance(check, CalibrationCheck) for check in self.checks):
            raise ValueError("checks must contain CalibrationCheck values")

    def to_mapping(self) -> dict[str, object]:
        return {
            "report_version": self.report_version,
            "status": self.status,
            "source_snapshot": self.source_snapshot,
            "schema_fingerprint": self.schema_fingerprint,
            "partition_policy": _copy_aggregate_mapping(self.partition_policy),
            "partition_counts": _copy_aggregate_mapping(self.partition_counts),
            "resource_row_counts": _copy_aggregate_mapping(self.resource_row_counts),
            "target_family_counts": _copy_aggregate_mapping(self.target_family_counts),
            "suppression_counts": _copy_aggregate_mapping(self.suppression_counts),
            "source_aggregate_sha256": self.source_aggregate_sha256,
            "checks": [check.to_mapping() for check in self.checks],
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.to_mapping(), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        )

    def to_json_bytes(self) -> bytes:
        return (self.canonical_json() + "\n").encode("ascii")


@dataclass(frozen=True)
class CalibrationResult:
    artifact: CalibrationArtifact
    report: CalibrationReport

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, CalibrationArtifact):
            raise ValueError("artifact must be a CalibrationArtifact")  # noqa: TRY004
        if not isinstance(self.report, CalibrationReport):
            raise ValueError("report must be a CalibrationReport")  # noqa: TRY004


def calibrate(config: CalibrationRunConfig) -> CalibrationResult:
    """Build disclosure-controlled aggregates using one private live connection."""
    if not isinstance(config, CalibrationRunConfig):
        raise TypeError("config must be a CalibrationRunConfig")
    connection = duckdb.connect(":memory:")
    try:
        prepared = prepare_input(connection, config)
        raw_targets = compute_raw_targets(connection, prepared, config)
        strata = disclose_targets(raw_targets, config)
        result = build_result(strata, prepared, config)
        if result.artifact.source_aggregate_sha256 != result.report.source_aggregate_sha256:
            raise ValueError("aggregate hashes do not match")
        return result
    finally:
        connection.close()


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    mapping: dict[str, object] = {}
    for key, value in pairs:
        if key in mapping:
            raise ValueError("JSON contains a duplicate key")
        mapping[key] = value
    return mapping


def _reject_nonfinite_json(_value: str) -> None:
    raise ValueError("JSON contains a nonfinite value")


def _strict_json_bytes(raw: bytes, label: str) -> Mapping[str, object]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_json,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise ValueError(f"{label} JSON is invalid") from exc
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} JSON must be an object")
    return value


def _require_exact_keys(
    mapping: Mapping[str, object], expected: frozenset[str], label: str
) -> Mapping[str, object]:
    if set(mapping) != expected:
        raise ValueError(f"{label} JSON has unexpected keys")
    return mapping


def _read_regular_file(
    path: Path, label: str, *, maximum_bytes: int | None = None
) -> bytes:
    if not isinstance(path, Path):
        raise ValueError(f"{label} must be a Path")  # noqa: TRY004
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ValueError(f"{label} requires secure no-follow opening")
    try:
        descriptor = os.open(path, os.O_RDONLY | nofollow | getattr(os, "O_NONBLOCK", 0))
    except OSError as exc:
        raise ValueError(f"{label} must be a regular non-symlink file") from exc
    try:
        initial_status = os.fstat(descriptor)
        if not stat.S_ISREG(initial_status.st_mode):
            raise ValueError(f"{label} must be a regular non-symlink file")
        if maximum_bytes is not None and initial_status.st_size > maximum_bytes:
            raise ValueError(f"{label} exceeds the maximum size")
        chunks: list[bytes] = []
        size = 0
        while True:
            read_size = 64 * 1024
            if maximum_bytes is not None:
                read_size = min(read_size, maximum_bytes + 1 - size)
                if read_size <= 0:
                    break
            chunk = os.read(descriptor, read_size)
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        final_status = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    payload = b"".join(chunks)
    if maximum_bytes is not None and (
        len(payload) > maximum_bytes
        or final_status.st_size > maximum_bytes
        or final_status.st_size > len(payload)
    ):
        raise ValueError(f"{label} exceeds the maximum size")
    return payload


def _load_partition_policy(path: Path) -> PartitionPolicy:
    mapping = _require_exact_keys(
        _strict_json_bytes(_read_regular_file(path, "partition policy"), "partition policy"),
        _PARTITION_POLICY_KEYS,
        "partition policy",
    )
    return PartitionPolicy(
        policy_id=mapping["policy_id"],  # type: ignore[arg-type]
        policy_version=mapping["policy_version"],  # type: ignore[arg-type]
        key_id=mapping["key_id"],  # type: ignore[arg-type]
        calibration_basis_points=mapping["calibration_basis_points"],  # type: ignore[arg-type]
        minimum_partition_patients=mapping["minimum_partition_patients"],  # type: ignore[arg-type]
    )


def _load_disclosure_policy(path: Path) -> CalibrationDisclosurePolicy:
    mapping = _require_exact_keys(
        _strict_json_bytes(_read_regular_file(path, "disclosure policy"), "disclosure policy"),
        _DISCLOSURE_POLICY_KEYS,
        "disclosure policy",
    )
    return CalibrationDisclosurePolicy(
        policy_id=mapping["policy_id"],  # type: ignore[arg-type]
        policy_version=mapping["policy_version"],  # type: ignore[arg-type]
        minimum_cell_count=mapping["minimum_cell_count"],  # type: ignore[arg-type]
        continuous_rounding_decimals=mapping["continuous_rounding_decimals"],  # type: ignore[arg-type]
    )


def _artifact_json_bytes(artifact: CalibrationArtifact) -> bytes:
    return (artifact.canonical_json() + "\n").encode("ascii")


def _write_exclusive_fsynced(path: Path, payload: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("output write did not progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _parse_report(mapping: Mapping[str, object]) -> CalibrationReport:
    _require_exact_keys(mapping, _REPORT_KEYS, "calibration report")
    raw_checks = mapping["checks"]
    if not isinstance(raw_checks, list):
        raise TypeError("calibration report checks must be a list")
    checks: list[CalibrationCheck] = []
    for raw_check in raw_checks:
        if not isinstance(raw_check, Mapping) or set(raw_check) != {"name", "passed", "detail"}:
            raise ValueError("calibration report check is invalid")
        checks.append(
            CalibrationCheck(
                name=raw_check["name"],  # type: ignore[arg-type]
                passed=raw_check["passed"],  # type: ignore[arg-type]
                detail=raw_check["detail"],  # type: ignore[arg-type]
            )
        )
    return CalibrationReport(
        report_version=mapping["report_version"],  # type: ignore[arg-type]
        status=mapping["status"],  # type: ignore[arg-type]
        source_snapshot=mapping["source_snapshot"],  # type: ignore[arg-type]
        schema_fingerprint=mapping["schema_fingerprint"],  # type: ignore[arg-type]
        partition_policy=mapping["partition_policy"],  # type: ignore[arg-type]
        partition_counts=mapping["partition_counts"],  # type: ignore[arg-type]
        resource_row_counts=mapping["resource_row_counts"],  # type: ignore[arg-type]
        target_family_counts=mapping["target_family_counts"],  # type: ignore[arg-type]
        suppression_counts=mapping["suppression_counts"],  # type: ignore[arg-type]
        source_aggregate_sha256=mapping["source_aggregate_sha256"],  # type: ignore[arg-type]
        checks=tuple(checks),
    )


def load_calibration_report(path: Path) -> CalibrationReport:
    """Securely load a strict aggregate-only calibration report."""
    return _parse_report(
        _strict_json_bytes(
            _read_regular_file(
                path,
                "calibration report",
                maximum_bytes=MAX_CALIBRATION_REPORT_BYTES,
            ),
            "calibration report",
        )
    )


def _reparse_written_result(run: RunDirectory, result: CalibrationResult) -> None:
    artifact_bytes = _read_regular_file(run.partial_path / _ARTIFACT_FILENAME, "artifact output")
    report_bytes = _read_regular_file(run.partial_path / _REPORT_FILENAME, "report output")
    artifact = CalibrationArtifact.from_mapping(_strict_json_bytes(artifact_bytes, "artifact output"))
    report = _parse_report(_strict_json_bytes(report_bytes, "report output"))
    if artifact != result.artifact or report != result.report:
        raise ValueError("calibration output reparse does not match result")
    if artifact_bytes != _artifact_json_bytes(artifact) or report_bytes != report.to_json_bytes():
        raise ValueError("calibration output is not canonical")
    if artifact.source_aggregate_sha256 != report.source_aggregate_sha256:
        raise ValueError("calibration output aggregate hashes do not match")


def _refuse_existing_lifecycle_path(output: Path, artifact_id: str) -> None:
    if os.path.lexists(output):
        raise FileExistsError("calibration output already exists")
    resolved = output.resolve()
    lifecycle_id = _lifecycle_run_id(artifact_id)
    lifecycle_paths = (
        resolved.parent / f".{resolved.name}.{lifecycle_id}.partial",
        resolved.parent / f".{resolved.name}.{lifecycle_id}.failed",
    )
    if any(os.path.lexists(path) for path in lifecycle_paths):
        raise FileExistsError("calibration output lifecycle path already exists")


def _lifecycle_run_id(artifact_id: str) -> str:
    """Derive a fixed filesystem-safe lifecycle token without exposing the public ID."""
    validated = _require_token(artifact_id, "artifact_id")
    return hashlib.sha256(validated.encode("ascii")).hexdigest()


def write_calibration_result(result: CalibrationResult, output: Path) -> None:
    """Write, verify, and atomically promote a new aggregate calibration directory."""
    if not isinstance(result, CalibrationResult):
        raise TypeError("result must be a CalibrationResult")
    if not isinstance(output, Path):
        raise TypeError("output must be a Path")
    _refuse_existing_lifecycle_path(output, result.artifact.artifact_id)
    run = RunDirectory.start(output, _lifecycle_run_id(result.artifact.artifact_id))
    try:
        _write_exclusive_fsynced(
            run.partial_path / _ARTIFACT_FILENAME, _artifact_json_bytes(result.artifact)
        )
        _write_exclusive_fsynced(
            run.partial_path / _REPORT_FILENAME, result.report.to_json_bytes()
        )
        _reparse_written_result(run, result)
        run.promote()
    except Exception:  # noqa: BLE001 - every output failure must archive aggregate-only evidence
        try:
            run.fail("calibration output validation failed")
        except Exception:  # noqa: BLE001 - promotion failure must still be redacted
            raise ValueError("calibration output could not be promoted") from None
        raise ValueError("calibration output could not be promoted") from None


class _RedactedArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        self.exit(2, "calibration arguments invalid\n")


def _argument_parser() -> argparse.ArgumentParser:
    parser = _RedactedArgumentParser(
        description="Run governed aggregate calibration", allow_abbrev=False
    )
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--descriptor", required=True, type=Path)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--partition-policy", required=True, type=Path)
    parser.add_argument("--disclosure-policy", required=True, type=Path)
    parser.add_argument("--partition-key-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> None:
    """Run the explicit-input governed calibration command."""
    parser = _argument_parser()
    arguments = parser.parse_args()
    try:
        config = CalibrationRunConfig(
            data_root=arguments.data_root,
            source_descriptor=arguments.descriptor,
            source_snapshot=arguments.snapshot,
            artifact_id=arguments.artifact_id,
            created_at=arguments.created_at,
            partition_policy=_load_partition_policy(arguments.partition_policy),
            disclosure_policy=_load_disclosure_policy(arguments.disclosure_policy),
            partition_key=_read_regular_file(arguments.partition_key_file, "partition key"),
            age_windows=DEFAULT_AGE_WINDOWS,
        )
        write_calibration_result(calibrate(config), arguments.output)
    except Exception:  # noqa: BLE001 - CLI must not disclose governed exception details
        parser.exit(1, "calibration failed\n")


if __name__ == "__main__":  # pragma: no cover - exercised after CLI assembly
    main()
