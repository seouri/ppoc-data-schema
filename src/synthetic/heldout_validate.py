"""Aggregate-only frozen-policy comparisons for held-out validation."""

from __future__ import annotations

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

from synthetic.calibrate import _require_aggregate_detail, _require_safe_report_token
from synthetic.calibration import (
    ALLOWED_DIMENSION_KEYS,
    ALLOWED_STATISTICS,
    ALLOWED_TARGET_FAMILIES,
    CalibrationStratum,
    CalibrationTarget,
    contains_indicator_components,
    contains_serialized_metadata_unsafe_material,
    require_aggregate_safe_token,
)
from synthetic.calibration_targets import TARGET_REGISTRY_VERSION

MAX_FIDELITY_POLICY_BYTES = 1024 * 1024
HELDOUT_REPORT_VERSION = "heldout-validation-report-v1"
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


def _require_stratum_id(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("stratum_id must be a nonempty canonical aggregate stratum")
    if contains_serialized_metadata_unsafe_material(value):
        raise ValueError("stratum_id must be aggregate-safe")
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
    fidelity_policy: Mapping[str, object]
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
        object.__setattr__(
            self,
            "fidelity_policy",
            _validate_policy_identity(
                self.fidelity_policy,
                frozenset({"policy_id", "policy_version", "target_registry_version"}),
                "fidelity_policy",
            ),
        )
        counts = _validate_counts(self.comparison_counts, "comparison_counts")
        families = _validate_family_counts(self.family_counts)
        object.__setattr__(self, "comparison_counts", counts)
        object.__setattr__(self, "family_counts", families)
        if not isinstance(self.checks, tuple) or not self.checks or not all(
            isinstance(check, HeldoutCheck) for check in self.checks
        ):
            raise ValueError("checks must be a nonempty tuple of HeldoutCheck values")
        if not isinstance(self.comparisons, tuple) or not all(
            isinstance(comparison, HeldoutComparison) for comparison in self.comparisons
        ):
            raise ValueError("comparisons must be a tuple of HeldoutComparison values")
        if len({_comparison_sort_key(comparison) for comparison in self.comparisons}) != len(self.comparisons):
            raise ValueError("comparisons must not contain duplicate canonical keys")
        sorted_comparisons = tuple(sorted(self.comparisons, key=_comparison_sort_key))
        if dict(counts) != comparison_counts(sorted_comparisons):
            raise ValueError("comparison_counts must match comparisons")
        if _copy_mapping(families) != family_counts(sorted_comparisons):
            raise ValueError("family_counts must match comparisons")
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
            "fidelity_policy": _copy_mapping(self.fidelity_policy),
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
                f"{self.fidelity_policy['policy_id']} {self.fidelity_policy['policy_version']} "
                f"{self.fidelity_policy['target_registry_version']}"
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
