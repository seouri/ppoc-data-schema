"""Aggregate-only frozen-policy comparisons for held-out validation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from errno import ELOOP
from pathlib import Path
from types import MappingProxyType

import duckdb

from synthetic.calibrate import (
    CALIBRATION_REPORT_VERSION,
    DEFAULT_AGE_WINDOWS,
    CalibrationAgeWindow,
    CalibrationReport,
    CalibrationRunConfig,
    PartitionPolicy,
    _load_disclosure_policy,
    _load_partition_policy,
    _read_regular_file,
    _require_aggregate_detail,
    _require_safe_report_token,
    _strict_json_bytes,
    _write_exclusive_fsynced,
    load_calibration_report,
)
from synthetic.calibration import (
    ALLOWED_DIMENSION_KEYS,
    ALLOWED_STATISTICS,
    ALLOWED_TARGET_FAMILIES,
    CalibrationArtifact,
    CalibrationDisclosurePolicy,
    CalibrationStratum,
    CalibrationTarget,
    contains_indicator_components,
    load_calibration_artifact,
    require_aggregate_safe_token,
)
from synthetic.calibration_disclosure import _aggregate_sha256, disclose_targets
from synthetic.calibration_input import (
    MAX_GOVERNED_DESCRIPTOR_BYTES,
    prepare_input,
    prepare_synthetic_input,
)
from synthetic.calibration_targets import (
    TARGET_REGISTRY_VERSION,
    compute_raw_targets,
    is_registered_target_key,
)
from synthetic.run_directory import RunDirectory

MAX_FIDELITY_POLICY_BYTES = 1024 * 1024
HELDOUT_REPORT_VERSION = "heldout-validation-report-v1"
_HELDOUT_REPORT_FILENAME = "heldout-validation-report.json"
_HELDOUT_SUMMARY_FILENAME = "heldout-validation-summary.txt"
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_DIMENSION_VALUE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}\Z")
_FAMILIES = (
    "demographics",
    "observation",
    "physiology",
    "utilization",
    "recorded_outcome",
)
_COMPARISON_STATUSES = ("PASS", "FAIL", "UNEVALUABLE")
_RESERVED_DIMENSION_VALUES = frozenset({"latent", "truth", "sequence", "candidate"})
_FIDELITY_POLICY_KEYS = frozenset(
    {
        "policy_id",
        "policy_version",
        "target_registry_version",
        "minimum_evaluable_support",
        "proportion_floor",
        "proportion_z_score",
        "continuous_tolerances",
        "count_abs_tolerance",
        "required_families",
        "max_unevaluable_targets",
    }
)
_HELDOUT_REPORT_KEYS = frozenset(
    {
        "report_version",
        "status",
        "source_snapshot",
        "synthetic_artifact_id",
        "schema_fingerprint",
        "partition_policy",
        "disclosure_policy",
        "fidelity_policy",
        "heldout_aggregate_sha256",
        "synthetic_aggregate_sha256",
        "comparison_counts",
        "family_counts",
        "checks",
        "comparisons",
    }
)
_COMPARISON_KEYS = frozenset(
    {
        "stratum_id",
        "target_name",
        "family",
        "statistic",
        "unit",
        "status",
        "heldout_value",
        "synthetic_value",
        "difference",
        "tolerance",
    }
)
_CALIBRATION_CHECK_NAMES = frozenset(
    {"schema", "partition", "target_registry", "disclosure"}
)


def _require_integer(value: object, field: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")  # noqa: TRY004
    if minimum is not None and value < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    return value


def _require_finite_number(value: object, field: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")  # noqa: TRY004
    try:
        number = float(value)
    except OverflowError:
        raise ValueError(f"{field} must be a finite number") from None
    if not math.isfinite(number):
        raise ValueError(f"{field} must be a finite number")
    if minimum is not None and number < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    return number


def _require_sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase 64-hex sha256")
    return value


def _require_exact_keys(value: object, expected: frozenset[str], field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    if set(value) != expected:
        raise ValueError(f"{field} keys must match exactly")
    return value


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(
        {
            key: _freeze_mapping(item) if isinstance(item, Mapping) else item
            for key, item in sorted(value.items())
        }
    )


def _copy_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return {
        key: _copy_mapping(item) if isinstance(item, Mapping) else item
        for key, item in value.items()
    }


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    mapping: dict[str, object] = {}
    for key, value in pairs:
        if key in mapping:
            raise ValueError("fidelity policy JSON contains a duplicate key")
        mapping[key] = value
    return mapping


def _reject_nonfinite_json_constant(_value: str) -> None:
    raise ValueError("fidelity policy JSON contains a nonfinite value")


def _read_fidelity_policy(path: Path) -> bytes:
    if not isinstance(path, Path):
        raise ValueError("fidelity policy must be a Path")  # noqa: TRY004
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ValueError("fidelity policy requires secure no-follow opening")
    try:
        descriptor = os.open(path, os.O_RDONLY | nofollow | getattr(os, "O_NONBLOCK", 0))
    except FileNotFoundError:
        raise ValueError("fidelity policy path was not found") from None
    except OSError as exc:
        if exc.errno == ELOOP:
            raise ValueError("fidelity policy must be a regular non-symlink file") from None
        raise ValueError("fidelity policy could not be securely opened") from None
    try:
        initial_status = os.fstat(descriptor)
        if not stat.S_ISREG(initial_status.st_mode):
            raise ValueError("fidelity policy must be a regular non-symlink file")
        if initial_status.st_size > MAX_FIDELITY_POLICY_BYTES:
            raise ValueError("fidelity policy exceeds the maximum size")
        payload = os.read(descriptor, MAX_FIDELITY_POLICY_BYTES + 1)
        final_status = os.fstat(descriptor)
    except OSError:
        raise ValueError("fidelity policy could not be read") from None
    finally:
        os.close(descriptor)
    if (
        len(payload) > MAX_FIDELITY_POLICY_BYTES
        or final_status.st_size > MAX_FIDELITY_POLICY_BYTES
        or final_status.st_size > len(payload)
    ):
        raise ValueError("fidelity policy exceeds the maximum size")
    if payload.startswith(b"\xef\xbb\xbf"):
        raise ValueError("fidelity policy must not include a UTF-8 BOM")
    return payload


@dataclass(frozen=True)
class FidelityPolicy:
    """A versioned, fixed comparison policy loaded before any target evaluation."""

    policy_id: str
    policy_version: str
    target_registry_version: str
    minimum_evaluable_support: int
    proportion_floor: float
    proportion_z_score: float
    continuous_tolerances: Mapping[str, float]
    count_abs_tolerance: int
    required_families: tuple[str, ...]
    max_unevaluable_targets: int

    def __post_init__(self) -> None:
        require_aggregate_safe_token(self.policy_id, "policy_id")
        require_aggregate_safe_token(self.policy_version, "policy_version")
        require_aggregate_safe_token(self.target_registry_version, "target_registry_version")
        if self.target_registry_version != TARGET_REGISTRY_VERSION:
            raise ValueError("target_registry_version does not match the fixed target registry")
        _require_integer(self.minimum_evaluable_support, "minimum_evaluable_support", minimum=1)
        proportion_floor = _require_finite_number(self.proportion_floor, "proportion_floor", minimum=0.0)
        if proportion_floor > 1.0:
            raise ValueError("proportion_floor must be in [0, 1]")
        object.__setattr__(self, "proportion_floor", proportion_floor)
        proportion_z_score = _require_finite_number(
            self.proportion_z_score, "proportion_z_score", minimum=0.0
        )
        if proportion_z_score == 0:
            raise ValueError("proportion_z_score must be positive")
        object.__setattr__(self, "proportion_z_score", proportion_z_score)
        tolerances = _require_exact_keys(
            self.continuous_tolerances, frozenset(_FAMILIES), "continuous_tolerances"
        )
        frozen_tolerances: dict[str, float] = {}
        for family in _FAMILIES:
            frozen_tolerances[family] = _require_finite_number(
                tolerances[family], f"continuous_tolerances.{family}", minimum=0.0
            )
        object.__setattr__(self, "continuous_tolerances", MappingProxyType(frozen_tolerances))
        _require_integer(self.count_abs_tolerance, "count_abs_tolerance", minimum=0)
        _require_integer(self.max_unevaluable_targets, "max_unevaluable_targets", minimum=0)
        if not isinstance(self.required_families, (list, tuple)) or not self.required_families:
            raise ValueError("required_families must be a nonempty list or tuple")
        required = tuple(self.required_families)
        if not all(isinstance(family, str) and family in _FAMILIES for family in required):
            raise ValueError("required_families must contain approved families")
        if len(set(required)) != len(required):
            raise ValueError("required_families must not contain duplicates")
        if required != tuple(family for family in _FAMILIES if family in required):
            raise ValueError("required_families must use canonical family order")
        object.__setattr__(self, "required_families", required)

    def to_report_mapping(self) -> dict[str, str]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "target_registry_version": self.target_registry_version,
        }


def load_fidelity_policy(path: Path) -> FidelityPolicy:
    """Securely load the exact frozen fidelity-policy JSON object."""
    raw = _read_fidelity_policy(path)
    try:
        decoded = raw.decode("utf-8", errors="strict")
        value = json.loads(
            decoded,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonfinite_json_constant,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise ValueError("fidelity policy must be valid strict JSON") from exc
    mapping = _require_exact_keys(value, _FIDELITY_POLICY_KEYS, "fidelity policy")
    return FidelityPolicy(
        policy_id=mapping["policy_id"],  # type: ignore[arg-type]
        policy_version=mapping["policy_version"],  # type: ignore[arg-type]
        target_registry_version=mapping["target_registry_version"],  # type: ignore[arg-type]
        minimum_evaluable_support=mapping["minimum_evaluable_support"],  # type: ignore[arg-type]
        proportion_floor=mapping["proportion_floor"],  # type: ignore[arg-type]
        proportion_z_score=mapping["proportion_z_score"],  # type: ignore[arg-type]
        continuous_tolerances=mapping["continuous_tolerances"],  # type: ignore[arg-type]
        count_abs_tolerance=mapping["count_abs_tolerance"],  # type: ignore[arg-type]
        required_families=mapping["required_families"],  # type: ignore[arg-type]
        max_unevaluable_targets=mapping["max_unevaluable_targets"],  # type: ignore[arg-type]
    )


@dataclass(frozen=True)
class HeldoutRunConfig:
    """Explicit governed inputs for one held-out validation run."""

    real_root: Path
    real_descriptor: Path
    source_snapshot: str
    synthetic_root: Path
    calibration_artifact: Path
    calibration_report: Path
    partition_policy: PartitionPolicy
    disclosure_policy: CalibrationDisclosurePolicy
    partition_key: bytes
    fidelity_policy: FidelityPolicy
    age_windows: tuple[CalibrationAgeWindow, ...]
    output: Path

    def __post_init__(self) -> None:
        for field in (
            "real_root",
            "real_descriptor",
            "synthetic_root",
            "calibration_artifact",
            "calibration_report",
            "output",
        ):
            if not isinstance(getattr(self, field), Path):
                raise ValueError(f"{field} must be a Path")  # noqa: TRY004
        require_aggregate_safe_token(self.source_snapshot, "source_snapshot")
        if not isinstance(self.partition_policy, PartitionPolicy):
            raise ValueError("partition_policy must be a PartitionPolicy")  # noqa: TRY004
        if not isinstance(self.disclosure_policy, CalibrationDisclosurePolicy):
            raise ValueError(  # noqa: TRY004
                "disclosure_policy must be a CalibrationDisclosurePolicy"
            )
        if not isinstance(self.partition_key, bytes) or len(self.partition_key) < 16:
            raise ValueError("partition_key must contain at least 16 bytes")
        if not isinstance(self.fidelity_policy, FidelityPolicy):
            raise ValueError("fidelity_policy must be a FidelityPolicy")  # noqa: TRY004
        if not isinstance(self.age_windows, tuple) or not self.age_windows:
            raise ValueError("age_windows must be a nonempty immutable tuple")
        if not all(isinstance(window, CalibrationAgeWindow) for window in self.age_windows):
            raise ValueError("age_windows must contain CalibrationAgeWindow values")
        if len({window.window_id for window in self.age_windows}) != len(self.age_windows):
            raise ValueError("age_windows window_id values must be unique")
        for previous, current in zip(self.age_windows, self.age_windows[1:], strict=False):
            if current.lower_age_days < previous.upper_age_days:
                raise ValueError("age_windows must be ordered and non-overlapping")


def _require_stratum_id(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("stratum_id must be a nonempty canonical aggregate stratum")
    dimensions: list[tuple[str, str]] = []
    for component in value.split("|"):
        key, separator, dimension_value = component.partition("=")
        if not separator or key not in ALLOWED_DIMENSION_KEYS:
            raise ValueError("stratum_id must use approved canonical dimensions")
        if _DIMENSION_VALUE_RE.fullmatch(dimension_value) is None:
            raise ValueError("stratum_id must use approved canonical dimensions")
        require_aggregate_safe_token(dimension_value, f"stratum_id.{key}")
        if dimension_value.lower() in _RESERVED_DIMENSION_VALUES:
            raise ValueError("stratum_id must not encode hidden state")
        dimensions.append((key, dimension_value))
    if not 1 <= len(dimensions) <= 4:
        raise ValueError("stratum_id must contain one to four dimensions")
    if len({key for key, _ in dimensions}) != len(dimensions) or tuple(sorted(dimensions)) != tuple(dimensions):
        raise ValueError("stratum_id must use sorted unique dimensions")
    return value


def _require_target_metadata(value: object, field: str, *, target_name: bool = False) -> str:
    token = require_aggregate_safe_token(value, field)
    if target_name and contains_indicator_components(
        token,
        {
            "attribute_disclosure",
            "attribute_inference",
            "candidate",
            "composition",
            "differential_privacy",
            "latent",
            "linkage",
            "membership_inference",
            "model_inversion",
            "privacy_attack",
            "privacy_audit",
            "reidentification",
            "sequence",
            "singling_out",
            "truth",
        },
    ):
        raise ValueError(f"{field} must be aggregate-safe target metadata")
    return token


def _validate_disclosed_value(value: object, field: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite disclosed value")  # noqa: TRY004
    try:
        if not math.isfinite(value):
            raise ValueError(f"{field} must be a finite disclosed value")
    except OverflowError:
        raise ValueError(f"{field} must be a finite disclosed value") from None
    return value


@dataclass(frozen=True)
class HeldoutComparison:
    stratum_id: str
    target_name: str
    family: str
    statistic: str
    unit: str
    quantile_level: float | None
    status: str
    heldout_value: int | float | None
    synthetic_value: int | float | None
    difference: float | None
    tolerance: float | None

    def __post_init__(self) -> None:
        _require_stratum_id(self.stratum_id)
        _require_target_metadata(self.target_name, "target_name", target_name=True)
        if self.family not in ALLOWED_TARGET_FAMILIES:
            raise ValueError("family must be approved")
        if self.statistic not in ALLOWED_STATISTICS:
            raise ValueError("statistic must be approved")
        _require_target_metadata(self.unit, "unit")
        if self.statistic == "quantile":
            level = _require_finite_number(self.quantile_level, "quantile_level", minimum=0.0)
            if level > 1:
                raise ValueError("quantile_level must be in [0, 1]")
            object.__setattr__(self, "quantile_level", level)
        elif self.quantile_level is not None:
            raise ValueError("quantile_level is only valid for quantile targets")
        if self.status not in _COMPARISON_STATUSES:
            raise ValueError("status must be PASS, FAIL, or UNEVALUABLE")
        values = (self.heldout_value, self.synthetic_value, self.difference, self.tolerance)
        if self.status == "UNEVALUABLE":
            if any(value is not None for value in values):
                raise ValueError("UNEVALUABLE comparisons require null values")
            return
        if any(value is None for value in values):
            raise ValueError("evaluable comparisons require disclosed values, difference, and tolerance")
        _validate_disclosed_value(self.heldout_value, "heldout_value")
        _validate_disclosed_value(self.synthetic_value, "synthetic_value")
        difference = _require_finite_number(self.difference, "difference", minimum=0.0)
        tolerance = _require_finite_number(self.tolerance, "tolerance", minimum=0.0)
        expected_difference = abs(float(self.heldout_value) - float(self.synthetic_value))
        if difference != expected_difference:
            raise ValueError("difference must equal the absolute disclosed-value difference")
        if self.status != ("PASS" if difference <= tolerance else "FAIL"):
            raise ValueError("status must match difference and tolerance")
        object.__setattr__(self, "difference", difference)
        object.__setattr__(self, "tolerance", tolerance)

    def to_mapping(self) -> dict[str, object]:
        value: dict[str, object] = {
            "stratum_id": self.stratum_id,
            "target_name": self.target_name,
            "family": self.family,
            "statistic": self.statistic,
            "unit": self.unit,
            "status": self.status,
            "heldout_value": self.heldout_value,
            "synthetic_value": self.synthetic_value,
            "difference": self.difference,
            "tolerance": self.tolerance,
        }
        if self.statistic == "quantile":
            value["quantile_level"] = self.quantile_level
        return value


@dataclass(frozen=True)
class HeldoutCheck:
    name: str
    passed: bool
    detail: str

    def __post_init__(self) -> None:
        _require_safe_report_token(self.name, "check name")
        if not isinstance(self.passed, bool):
            raise ValueError("check passed must be a boolean")  # noqa: TRY004
        _require_aggregate_detail(self.detail, "check detail")
        if "\n" in self.detail or "\r" in self.detail:
            raise ValueError("check detail must be one line")

    def to_mapping(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


_TargetKey = tuple[str, str, str, str, str, float | None]


def _target_key(stratum_id: str, target: CalibrationTarget) -> _TargetKey:
    return (
        stratum_id,
        target.target_name,
        target.family,
        target.statistic,
        target.unit,
        target.quantile_level,
    )


def _index_targets(strata: tuple[CalibrationStratum, ...], label: str) -> dict[_TargetKey, CalibrationTarget]:
    if not isinstance(strata, tuple) or not all(isinstance(item, CalibrationStratum) for item in strata):
        raise ValueError(f"{label}_strata must be a tuple of CalibrationStratum values")
    indexed: dict[_TargetKey, CalibrationTarget] = {}
    for stratum in strata:
        for target in stratum.targets:
            key = _target_key(stratum.stratum_id, target)
            if not is_registered_target_key(*key):
                raise ValueError("target is outside the fixed target registry")
            if key in indexed:
                raise ValueError("duplicate canonical target key")
            indexed[key] = target
    return indexed


def _unevaluable_comparison(key: _TargetKey) -> HeldoutComparison:
    return HeldoutComparison(*key, "UNEVALUABLE", None, None, None, None)


def _is_evaluable(target: CalibrationTarget | None, policy: FidelityPolicy) -> bool:
    if target is None or target.status != "released" or target.support_count is None:
        return False
    if target.support_count < policy.minimum_evaluable_support:
        return False
    return target.statistic not in {"proportion", "rate"} or target.denominator is not None


def compare_targets(
    heldout_strata: tuple[CalibrationStratum, ...],
    synthetic_strata: tuple[CalibrationStratum, ...],
    policy: FidelityPolicy,
) -> tuple[HeldoutComparison, ...]:
    """Compare only matching disclosed aggregate targets under a fixed policy."""
    if not isinstance(policy, FidelityPolicy):
        raise TypeError("policy must be a FidelityPolicy")
    heldout_targets = _index_targets(heldout_strata, "heldout")
    synthetic_targets = _index_targets(synthetic_strata, "synthetic")
    comparisons: list[HeldoutComparison] = []
    for key in sorted(set(heldout_targets) | set(synthetic_targets)):
        heldout_target = heldout_targets.get(key)
        synthetic_target = synthetic_targets.get(key)
        if not _is_evaluable(heldout_target, policy) or not _is_evaluable(synthetic_target, policy):
            comparisons.append(_unevaluable_comparison(key))
            continue
        assert heldout_target is not None and synthetic_target is not None
        heldout_value = heldout_target.value
        synthetic_value = synthetic_target.value
        if heldout_value is None or synthetic_value is None:
            comparisons.append(_unevaluable_comparison(key))
            continue
        if heldout_target.statistic == "proportion":
            assert heldout_target.denominator is not None and synthetic_target.denominator is not None
            real_proportion = float(heldout_value)
            synthetic_proportion = float(synthetic_value)
            standard_error = max(
                math.sqrt(real_proportion * (1 - real_proportion) / heldout_target.denominator),
                math.sqrt(synthetic_proportion * (1 - synthetic_proportion) / synthetic_target.denominator),
            )
            tolerance = max(policy.proportion_floor, policy.proportion_z_score * standard_error)
        elif heldout_target.statistic == "count":
            tolerance = float(policy.count_abs_tolerance)
        else:
            tolerance = policy.continuous_tolerances[heldout_target.family]
        difference = abs(float(heldout_value) - float(synthetic_value))
        status = "PASS" if difference <= tolerance else "FAIL"
        comparisons.append(
            HeldoutComparison(
                *key,
                status,
                heldout_value,
                synthetic_value,
                difference,
                tolerance,
            )
        )
    return tuple(comparisons)


def comparison_counts(comparisons: tuple[HeldoutComparison, ...]) -> dict[str, int]:
    if not isinstance(comparisons, tuple) or not all(
        isinstance(comparison, HeldoutComparison) for comparison in comparisons
    ):
        raise ValueError("comparisons must be a tuple of HeldoutComparison values")
    counted = Counter(comparison.status for comparison in comparisons)
    return {status: counted[status] for status in _COMPARISON_STATUSES}


def family_counts(comparisons: tuple[HeldoutComparison, ...]) -> dict[str, dict[str, int]]:
    comparison_counts(comparisons)
    result: dict[str, dict[str, int]] = {}
    for family in _FAMILIES:
        counted = Counter(comparison.status for comparison in comparisons if comparison.family == family)
        if counted:
            result[family] = {status: counted[status] for status in _COMPARISON_STATUSES}
    return result


def validation_status(comparisons: tuple[HeldoutComparison, ...], policy: FidelityPolicy) -> str:
    """Return the global gate status without exposing any support or row data."""
    if not isinstance(policy, FidelityPolicy):
        raise TypeError("policy must be a FidelityPolicy")
    counts = comparison_counts(comparisons)
    if counts["FAIL"]:
        return "FAIL"
    evaluable_families = {
        comparison.family for comparison in comparisons if comparison.status in {"PASS", "FAIL"}
    }
    if counts["UNEVALUABLE"] > policy.max_unevaluable_targets:
        return "UNEVALUABLE"
    if any(family not in evaluable_families for family in policy.required_families):
        return "UNEVALUABLE"
    return "PASS"


def _validate_policy_identity(value: object, expected_keys: frozenset[str], field: str) -> Mapping[str, object]:
    mapping = _require_exact_keys(value, expected_keys, field)
    for key in expected_keys:
        require_aggregate_safe_token(mapping[key], f"{field}.{key}")
    return _freeze_mapping(mapping)


def _validate_counts(value: object, field: str) -> Mapping[str, object]:
    mapping = _require_exact_keys(value, frozenset(_COMPARISON_STATUSES), field)
    for status in _COMPARISON_STATUSES:
        _require_integer(mapping[status], f"{field}.{status}", minimum=0)
    return _freeze_mapping(mapping)


def _validate_family_counts(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError("family_counts must be an object")
    if not set(value).issubset(_FAMILIES):
        raise ValueError("family_counts must use approved target families")
    return _freeze_mapping({family: _validate_counts(counts, f"family_counts.{family}") for family, counts in value.items()})


def _comparison_sort_key(comparison: HeldoutComparison) -> _TargetKey:
    return (
        comparison.stratum_id,
        comparison.target_name,
        comparison.family,
        comparison.statistic,
        comparison.unit,
        comparison.quantile_level,
    )


@dataclass(frozen=True)
class HeldoutValidationReport:
    report_version: str
    status: str
    source_snapshot: str
    synthetic_artifact_id: str
    schema_fingerprint: str
    partition_policy: Mapping[str, object]
    disclosure_policy: Mapping[str, object]
    fidelity_policy: FidelityPolicy
    heldout_aggregate_sha256: str
    synthetic_aggregate_sha256: str
    comparison_counts: Mapping[str, object]
    family_counts: Mapping[str, object]
    checks: tuple[HeldoutCheck, ...]
    comparisons: tuple[HeldoutComparison, ...]

    def __post_init__(self) -> None:
        if self.report_version != HELDOUT_REPORT_VERSION:
            raise ValueError(f"report_version must be {HELDOUT_REPORT_VERSION}")
        if self.status not in _COMPARISON_STATUSES:
            raise ValueError("status must be PASS, FAIL, or UNEVALUABLE")
        require_aggregate_safe_token(self.source_snapshot, "source_snapshot")
        require_aggregate_safe_token(self.synthetic_artifact_id, "synthetic_artifact_id")
        _require_sha256(self.schema_fingerprint, "schema_fingerprint")
        _require_sha256(self.heldout_aggregate_sha256, "heldout_aggregate_sha256")
        _require_sha256(self.synthetic_aggregate_sha256, "synthetic_aggregate_sha256")
        object.__setattr__(
            self,
            "partition_policy",
            _validate_policy_identity(
                self.partition_policy, frozenset({"policy_id", "policy_version"}), "partition_policy"
            ),
        )
        object.__setattr__(
            self,
            "disclosure_policy",
            _validate_policy_identity(
                self.disclosure_policy, frozenset({"policy_id", "policy_version"}), "disclosure_policy"
            ),
        )
        if not isinstance(self.fidelity_policy, FidelityPolicy):
            raise ValueError("fidelity_policy must be a FidelityPolicy")  # noqa: TRY004
        counts = _validate_counts(self.comparison_counts, "comparison_counts")
        families = _validate_family_counts(self.family_counts)
        object.__setattr__(self, "comparison_counts", counts)
        object.__setattr__(self, "family_counts", families)
        if not isinstance(self.checks, tuple) or not self.checks or not all(
            isinstance(check, HeldoutCheck) for check in self.checks
        ):
            raise ValueError("checks must be a nonempty tuple of HeldoutCheck values")
        if len({check.name for check in self.checks}) != len(self.checks):
            raise ValueError("checks must not contain duplicate names")
        if not isinstance(self.comparisons, tuple) or not all(
            isinstance(comparison, HeldoutComparison) for comparison in self.comparisons
        ):
            raise ValueError("comparisons must be a tuple of HeldoutComparison values")
        if any(
            not is_registered_target_key(*_comparison_sort_key(comparison))
            for comparison in self.comparisons
        ):
            raise ValueError("comparison target is outside the fixed target registry")
        if len({_comparison_sort_key(comparison) for comparison in self.comparisons}) != len(self.comparisons):
            raise ValueError("comparisons must not contain duplicate canonical keys")
        sorted_comparisons = tuple(sorted(self.comparisons, key=_comparison_sort_key))
        if dict(counts) != comparison_counts(sorted_comparisons):
            raise ValueError("comparison_counts must match comparisons")
        if _copy_mapping(families) != family_counts(sorted_comparisons):
            raise ValueError("family_counts must match comparisons")
        if self.status != validation_status(sorted_comparisons, self.fidelity_policy):
            raise ValueError("status must match the frozen policy and comparisons")
        object.__setattr__(self, "checks", tuple(sorted(self.checks, key=lambda check: check.name)))
        object.__setattr__(self, "comparisons", sorted_comparisons)

    def to_mapping(self) -> dict[str, object]:
        return {
            "report_version": self.report_version,
            "status": self.status,
            "source_snapshot": self.source_snapshot,
            "synthetic_artifact_id": self.synthetic_artifact_id,
            "schema_fingerprint": self.schema_fingerprint,
            "partition_policy": _copy_mapping(self.partition_policy),
            "disclosure_policy": _copy_mapping(self.disclosure_policy),
            "fidelity_policy": self.fidelity_policy.to_report_mapping(),
            "heldout_aggregate_sha256": self.heldout_aggregate_sha256,
            "synthetic_aggregate_sha256": self.synthetic_aggregate_sha256,
            "comparison_counts": _copy_mapping(self.comparison_counts),
            "family_counts": _copy_mapping(self.family_counts),
            "checks": [check.to_mapping() for check in self.checks],
            "comparisons": [comparison.to_mapping() for comparison in self.comparisons],
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.to_mapping(), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        )

    def to_json_bytes(self) -> bytes:
        return (self.canonical_json() + "\n").encode("ascii")

    def human_summary(self) -> str:
        lines = [
            f"status: {self.status}",
            (
                "partition policy: "
                f"{self.partition_policy['policy_id']} {self.partition_policy['policy_version']}"
            ),
            (
                "disclosure policy: "
                f"{self.disclosure_policy['policy_id']} {self.disclosure_policy['policy_version']}"
            ),
            (
                "fidelity policy: "
                f"{self.fidelity_policy.policy_id} {self.fidelity_policy.policy_version} "
                f"{self.fidelity_policy.target_registry_version}"
            ),
            f"heldout aggregate sha256: {self.heldout_aggregate_sha256}",
            f"synthetic aggregate sha256: {self.synthetic_aggregate_sha256}",
            "comparison counts: " + " ".join(
                f"{status}={self.comparison_counts[status]}" for status in _COMPARISON_STATUSES
            ),
        ]
        for family, counts in self.family_counts.items():
            lines.append(
                "family counts: "
                + family
                + " "
                + " ".join(f"{status}={counts[status]}" for status in _COMPARISON_STATUSES)
            )
        lines.extend(
            f"check: {check.name} {'PASS' if check.passed else 'FAIL'} {check.detail}"
            for check in self.checks
        )
        return "\n".join(lines) + "\n"


def format_human_summary(report: HeldoutValidationReport) -> str:
    if not isinstance(report, HeldoutValidationReport):
        raise TypeError("report must be a HeldoutValidationReport")
    return report.human_summary()


@dataclass(frozen=True)
class HeldoutValidationResult:
    """Aggregate-only result with no retained input connection or record state."""

    report: HeldoutValidationReport

    def __post_init__(self) -> None:
        if not isinstance(self.report, HeldoutValidationReport):
            raise ValueError("report must be a HeldoutValidationReport")  # noqa: TRY004


def _calibration_config(
    config: HeldoutRunConfig, artifact: CalibrationArtifact
) -> CalibrationRunConfig:
    return CalibrationRunConfig(
        data_root=config.real_root,
        source_descriptor=config.real_descriptor,
        source_snapshot=config.source_snapshot,
        artifact_id=artifact.artifact_id,
        created_at=artifact.created_at,
        partition_policy=config.partition_policy,
        disclosure_policy=config.disclosure_policy,
        partition_key=config.partition_key,
        age_windows=config.age_windows,
    )


def _require_calibration_compatibility(
    config: HeldoutRunConfig,
    artifact: CalibrationArtifact,
    report: CalibrationReport,
) -> None:
    if report.report_version != CALIBRATION_REPORT_VERSION:
        raise ValueError("calibration report version is incompatible")
    if artifact.source_snapshot != config.source_snapshot:
        raise ValueError("calibration artifact snapshot is incompatible")
    if artifact.source_partition != "calibration":
        raise ValueError("calibration artifact partition is incompatible")
    if artifact.disclosure_policy != config.disclosure_policy:
        raise ValueError("calibration artifact disclosure policy is incompatible")
    if report.source_snapshot != config.source_snapshot:
        raise ValueError("calibration report snapshot is incompatible")
    if report.source_aggregate_sha256 != artifact.source_aggregate_sha256:
        raise ValueError("calibration aggregate identities are incompatible")
    if report.partition_policy != config.partition_policy.to_report_mapping():
        raise ValueError("calibration partition policy is incompatible")
    if config.fidelity_policy.target_registry_version != TARGET_REGISTRY_VERSION:
        raise ValueError("fidelity target registry is incompatible")
    for stratum in artifact.strata:
        for target in stratum.targets:
            if not is_registered_target_key(*_target_key(stratum.stratum_id, target)):
                raise ValueError("calibration artifact target registry is incompatible")
    check_names = tuple(check.name for check in report.checks)
    if (
        len(check_names) != len(_CALIBRATION_CHECK_NAMES)
        or set(check_names) != _CALIBRATION_CHECK_NAMES
        or not all(check.passed for check in report.checks)
    ):
        raise ValueError("calibration report checks are incompatible")
    if _aggregate_sha256(artifact.strata) != artifact.source_aggregate_sha256:
        raise ValueError("calibration artifact aggregate identity is incompatible")


def _load_synthetic_descriptor(root: Path) -> Mapping[str, object]:
    descriptor = _strict_json_bytes(
        _read_regular_file(
            root / "datapackage.json",
            "synthetic descriptor",
            maximum_bytes=MAX_GOVERNED_DESCRIPTOR_BYTES,
        ),
        "synthetic descriptor",
    )
    if descriptor.get("profile") != "tabular-data-package":
        raise ValueError("synthetic descriptor is not a tabular-data-package")
    return descriptor


def _require_schema_compatibility(
    artifact: CalibrationArtifact,
    report: CalibrationReport,
    real_schema_fingerprint: str,
    synthetic_schema_fingerprint: str,
) -> None:
    if len(
        {
            artifact.schema_fingerprint,
            report.schema_fingerprint,
            real_schema_fingerprint,
            synthetic_schema_fingerprint,
        }
    ) != 1:
        raise ValueError("schema fingerprints are incompatible")


def _family_coverage(
    comparisons: tuple[HeldoutComparison, ...], policy: FidelityPolicy
) -> bool:
    evaluable_families = {
        comparison.family
        for comparison in comparisons
        if comparison.status in {"PASS", "FAIL"}
    }
    return all(family in evaluable_families for family in policy.required_families)


def validate_heldout(config: HeldoutRunConfig) -> HeldoutValidationResult:
    """Validate one generated package against a patient-disjoint held-out partition."""
    if not isinstance(config, HeldoutRunConfig):
        raise TypeError("config must be a HeldoutRunConfig")
    artifact = load_calibration_artifact(config.calibration_artifact)
    calibration_report = load_calibration_report(config.calibration_report)
    _require_calibration_compatibility(config, artifact, calibration_report)
    calibration_config = _calibration_config(config, artifact)

    real_connection = duckdb.connect(":memory:")
    try:
        synthetic_connection = duckdb.connect(":memory:")
        try:
            if real_connection is synthetic_connection:
                raise ValueError("held-out inputs require independent connections")
            prepared_real = prepare_input(real_connection, calibration_config)
            synthetic_descriptor = _load_synthetic_descriptor(config.synthetic_root)
            prepared_synthetic = prepare_synthetic_input(
                synthetic_connection,
                config.synthetic_root,
                synthetic_descriptor,
            )
            _require_schema_compatibility(
                artifact,
                calibration_report,
                prepared_real.schema_fingerprint,
                prepared_synthetic.schema_fingerprint,
            )

            heldout_raw = compute_raw_targets(
                real_connection,
                prepared_real,
                calibration_config,
                partition_label="held_out",
            )
            synthetic_raw = compute_raw_targets(
                synthetic_connection,
                prepared_synthetic,
                calibration_config,
                partition_label="calibration",
            )
            heldout_strata = disclose_targets(heldout_raw, calibration_config)
            synthetic_strata = (
                disclose_targets(synthetic_raw, calibration_config) if synthetic_raw else ()
            )
        finally:
            synthetic_connection.close()
    finally:
        real_connection.close()

    comparisons = compare_targets(
        heldout_strata,
        synthetic_strata,
        config.fidelity_policy,
    )
    status = validation_status(comparisons, config.fidelity_policy)
    coverage = _family_coverage(comparisons, config.fidelity_policy)
    checks = (
        HeldoutCheck("schema", True, "schema contracts matched"),
        HeldoutCheck("partition", True, "partition policy matched"),
        HeldoutCheck("target_registry", True, "target registry matched"),
        HeldoutCheck("disclosure", True, "disclosure policy matched"),
        HeldoutCheck(
            "family_coverage",
            coverage,
            "required families available" if coverage else "required family unavailable",
        ),
    )
    report = HeldoutValidationReport(
        report_version=HELDOUT_REPORT_VERSION,
        status=status,
        source_snapshot=config.source_snapshot,
        synthetic_artifact_id=artifact.artifact_id,
        schema_fingerprint=prepared_real.schema_fingerprint,
        partition_policy=config.partition_policy.to_report_mapping(),
        disclosure_policy={
            "policy_id": config.disclosure_policy.policy_id,
            "policy_version": config.disclosure_policy.policy_version,
        },
        fidelity_policy=config.fidelity_policy,
        heldout_aggregate_sha256=_aggregate_sha256(heldout_strata),
        synthetic_aggregate_sha256=artifact.source_aggregate_sha256,
        comparison_counts=comparison_counts(comparisons),
        family_counts=family_counts(comparisons),
        checks=checks,
        comparisons=comparisons,
    )
    return HeldoutValidationResult(report)


def _parse_heldout_report(
    mapping: Mapping[str, object], fidelity_policy: FidelityPolicy
) -> HeldoutValidationReport:
    _require_exact_keys(mapping, _HELDOUT_REPORT_KEYS, "held-out report")
    policy_identity = _require_exact_keys(
        mapping["fidelity_policy"],
        frozenset({"policy_id", "policy_version", "target_registry_version"}),
        "held-out fidelity policy",
    )
    if dict(policy_identity) != fidelity_policy.to_report_mapping():
        raise ValueError("held-out fidelity policy identity is incompatible")

    raw_checks = mapping["checks"]
    if not isinstance(raw_checks, list):
        raise ValueError("held-out report checks must be a list")  # noqa: TRY004
    checks: list[HeldoutCheck] = []
    for raw_check in raw_checks:
        check = _require_exact_keys(
            raw_check,
            frozenset({"name", "passed", "detail"}),
            "held-out report check",
        )
        checks.append(
            HeldoutCheck(
                name=check["name"],  # type: ignore[arg-type]
                passed=check["passed"],  # type: ignore[arg-type]
                detail=check["detail"],  # type: ignore[arg-type]
            )
        )

    raw_comparisons = mapping["comparisons"]
    if not isinstance(raw_comparisons, list):
        raise ValueError("held-out report comparisons must be a list")  # noqa: TRY004
    comparisons: list[HeldoutComparison] = []
    for raw_comparison in raw_comparisons:
        if not isinstance(raw_comparison, Mapping):
            raise ValueError(  # noqa: TRY004
                "held-out report comparison must be an object"
            )
        expected_keys = (
            _COMPARISON_KEYS | {"quantile_level"}
            if raw_comparison.get("statistic") == "quantile"
            else _COMPARISON_KEYS
        )
        comparison = _require_exact_keys(
            raw_comparison,
            frozenset(expected_keys),
            "held-out report comparison",
        )
        comparisons.append(
            HeldoutComparison(
                stratum_id=comparison["stratum_id"],  # type: ignore[arg-type]
                target_name=comparison["target_name"],  # type: ignore[arg-type]
                family=comparison["family"],  # type: ignore[arg-type]
                statistic=comparison["statistic"],  # type: ignore[arg-type]
                unit=comparison["unit"],  # type: ignore[arg-type]
                quantile_level=comparison.get("quantile_level"),  # type: ignore[arg-type]
                status=comparison["status"],  # type: ignore[arg-type]
                heldout_value=comparison["heldout_value"],  # type: ignore[arg-type]
                synthetic_value=comparison["synthetic_value"],  # type: ignore[arg-type]
                difference=comparison["difference"],  # type: ignore[arg-type]
                tolerance=comparison["tolerance"],  # type: ignore[arg-type]
            )
        )

    return HeldoutValidationReport(
        report_version=mapping["report_version"],  # type: ignore[arg-type]
        status=mapping["status"],  # type: ignore[arg-type]
        source_snapshot=mapping["source_snapshot"],  # type: ignore[arg-type]
        synthetic_artifact_id=mapping["synthetic_artifact_id"],  # type: ignore[arg-type]
        schema_fingerprint=mapping["schema_fingerprint"],  # type: ignore[arg-type]
        partition_policy=mapping["partition_policy"],  # type: ignore[arg-type]
        disclosure_policy=mapping["disclosure_policy"],  # type: ignore[arg-type]
        fidelity_policy=fidelity_policy,
        heldout_aggregate_sha256=mapping["heldout_aggregate_sha256"],  # type: ignore[arg-type]
        synthetic_aggregate_sha256=mapping["synthetic_aggregate_sha256"],  # type: ignore[arg-type]
        comparison_counts=mapping["comparison_counts"],  # type: ignore[arg-type]
        family_counts=mapping["family_counts"],  # type: ignore[arg-type]
        checks=tuple(checks),
        comparisons=tuple(comparisons),
    )


def _reparse_written_report(run: RunDirectory, result: HeldoutValidationResult) -> None:
    report_bytes = _read_regular_file(
        run.partial_path / _HELDOUT_REPORT_FILENAME,
        "held-out report output",
    )
    summary_bytes = _read_regular_file(
        run.partial_path / _HELDOUT_SUMMARY_FILENAME,
        "held-out summary output",
    )
    report = _parse_heldout_report(
        _strict_json_bytes(report_bytes, "held-out report output"),
        result.report.fidelity_policy,
    )
    if report != result.report:
        raise ValueError("held-out output reparse does not match result")
    if report_bytes != report.to_json_bytes():
        raise ValueError("held-out report output is not canonical")
    try:
        summary = summary_bytes.decode("ascii", errors="strict")
    except UnicodeError:
        raise ValueError("held-out summary output is not canonical") from None
    if summary != report.human_summary() or summary_bytes != summary.encode("ascii"):
        raise ValueError("held-out summary output is not canonical")


def _lifecycle_run_id(report: HeldoutValidationReport) -> str:
    identity = (
        f"{report.synthetic_artifact_id}:"
        f"{report.fidelity_policy.policy_id}:"
        f"{report.fidelity_policy.policy_version}"
    )
    return hashlib.sha256(identity.encode("ascii")).hexdigest()


def _refuse_existing_lifecycle_path(
    output: Path, report: HeldoutValidationReport
) -> None:
    if os.path.lexists(output):
        raise FileExistsError("held-out output already exists")
    resolved = output.resolve()
    lifecycle_id = _lifecycle_run_id(report)
    lifecycle_paths = (
        resolved.parent / f".{resolved.name}.{lifecycle_id}.partial",
        resolved.parent / f".{resolved.name}.{lifecycle_id}.failed",
    )
    if any(os.path.lexists(path) for path in lifecycle_paths):
        raise FileExistsError("held-out output lifecycle path already exists")


def _prepare_failure_archive(run: RunDirectory) -> None:
    for filename in (_HELDOUT_REPORT_FILENAME, _HELDOUT_SUMMARY_FILENAME):
        try:
            os.unlink(run.partial_path / filename)
        except FileNotFoundError:
            continue
    with os.scandir(run.partial_path) as entries:
        if next(entries, None) is not None:
            raise OSError("held-out partial output could not be cleared")


def write_heldout_report(result: HeldoutValidationResult, output: Path) -> None:
    """Write, verify, and atomically promote a held-out validation report."""
    if not isinstance(result, HeldoutValidationResult):
        raise TypeError("result must be a HeldoutValidationResult")
    if not isinstance(output, Path):
        raise TypeError("output must be a Path")
    _refuse_existing_lifecycle_path(output, result.report)
    run = RunDirectory.start(output, _lifecycle_run_id(result.report))
    try:
        _write_exclusive_fsynced(
            run.partial_path / _HELDOUT_REPORT_FILENAME,
            result.report.to_json_bytes(),
        )
        _write_exclusive_fsynced(
            run.partial_path / _HELDOUT_SUMMARY_FILENAME,
            result.report.human_summary().encode("ascii"),
        )
        _reparse_written_report(run, result)
        run.promote()
    except Exception:  # noqa: BLE001 - every output failure archives redacted evidence
        try:
            _prepare_failure_archive(run)
            run.fail("held-out output validation failed")
        except Exception:  # noqa: BLE001 - lifecycle errors must remain redacted
            raise ValueError("held-out output could not be promoted") from None
        raise ValueError("held-out output could not be promoted") from None


class _RedactedArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        self.exit(2, "held-out arguments invalid\n")


def _argument_parser() -> argparse.ArgumentParser:
    parser = _RedactedArgumentParser(description="Run governed held-out validation")
    parser.add_argument("--real-root", required=True, type=Path)
    parser.add_argument("--descriptor", required=True, type=Path)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--synthetic-root", required=True, type=Path)
    parser.add_argument("--calibration-artifact", required=True, type=Path)
    parser.add_argument("--calibration-report", required=True, type=Path)
    parser.add_argument("--partition-policy", required=True, type=Path)
    parser.add_argument("--disclosure-policy", required=True, type=Path)
    parser.add_argument("--partition-key-file", required=True, type=Path)
    parser.add_argument("--frozen-policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> None:
    """Run the explicit-input governed held-out validation command."""
    parser = _argument_parser()
    arguments = parser.parse_args()
    try:
        config = HeldoutRunConfig(
            real_root=arguments.real_root,
            real_descriptor=arguments.descriptor,
            source_snapshot=arguments.snapshot,
            synthetic_root=arguments.synthetic_root,
            calibration_artifact=arguments.calibration_artifact,
            calibration_report=arguments.calibration_report,
            partition_policy=_load_partition_policy(arguments.partition_policy),
            disclosure_policy=_load_disclosure_policy(arguments.disclosure_policy),
            partition_key=_read_regular_file(arguments.partition_key_file, "partition key"),
            fidelity_policy=load_fidelity_policy(arguments.frozen_policy),
            age_windows=DEFAULT_AGE_WINDOWS,
            output=arguments.output,
        )
        result = validate_heldout(config)
        write_heldout_report(result, config.output)
    except Exception:  # noqa: BLE001 - CLI must not disclose governed exception details
        parser.exit(1, "held-out validation failed\n")
    if result.report.status != "PASS":
        parser.exit(1, "held-out validation failed\n")


if __name__ == "__main__":  # pragma: no cover - exercised through subprocess tests
    main()
