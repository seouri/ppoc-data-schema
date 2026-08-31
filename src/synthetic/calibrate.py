"""Models for the governed aggregate calibration command.

This module deliberately contains no row loading or partitioning yet.  Those
steps are assembled only after their governed input and disclosure boundaries
are available.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import NoReturn

from synthetic.calibration import CalibrationArtifact, CalibrationDisclosurePolicy
from synthetic.calibration_input import (  # noqa: F401
    CalibrationInput,
    PartitionLabel,
    PartitionSummary,
    assign_partition,
    prepare_input,
)
from synthetic.calibration_targets import (  # noqa: F401
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
_IDENTIFIER_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*-[PV]-[0-9]{3,}\b", re.IGNORECASE)
_PATH_EXTENSION_RE = re.compile(r"\b[A-Za-z0-9_-]+\.(?:csv|tsv|json|parquet|txt|zip|gz)\b", re.IGNORECASE)
_SENSITIVE_DETAIL_WORDS = frozenset({"patient", "visit", "path", "key", "identifier"})


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
        bool(_IDENTIFIER_RE.search(value))
        or "/" in value
        or "\\" in value
        or bool(_PATH_EXTENSION_RE.search(value))
        or bool(words & _SENSITIVE_DETAIL_WORDS)
    )


def _require_aggregate_detail(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a nonempty aggregate detail")
    if _contains_sensitive_report_material(value):
        raise ValueError(f"{field} must be aggregate-only")
    return value


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
        _require_token(self.policy_id, "policy_id")
        _require_token(self.policy_version, "policy_version")
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
        _require_token(self.window_id, "window_id")
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
        _require_token(self.source_snapshot, "source_snapshot")
        _require_token(self.artifact_id, "artifact_id")
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
        for previous, current in zip(self.age_windows, self.age_windows[1:], strict=False):
            if current.lower_age_days < previous.upper_age_days:
                raise ValueError("age_windows must be ordered and non-overlapping")


@dataclass(frozen=True)
class CalibrationCheck:
    name: str
    passed: bool
    detail: str

    def __post_init__(self) -> None:
        _require_token(self.name, "check name")
        if not isinstance(self.passed, bool):
            raise ValueError("check passed must be a boolean")  # noqa: TRY004
        _require_aggregate_detail(self.detail, "check detail")

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
        _require_safe_report_token(self.report_version, "report_version")
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


def _not_assembled() -> NoReturn:
    raise NotImplementedError("calibrator is not assembled")


def calibrate(config: CalibrationRunConfig) -> CalibrationResult:
    """Run calibration once governed input/disclosure components are assembled."""
    _not_assembled()


def write_calibration_result(result: CalibrationResult, output: Path) -> None:
    """Write a successful calibration result once transactional output exists."""
    _not_assembled()


def main() -> None:
    """CLI placeholder assembled with the governed input pipeline."""
    _not_assembled()


if __name__ == "__main__":  # pragma: no cover - exercised after CLI assembly
    main()
