"""Strict in-memory contract for disclosure-controlled calibration artifacts."""

from __future__ import annotations

import json
import math
import os
import re
import stat
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from errno import ELOOP
from pathlib import Path

ARTIFACT_VERSION = "calibration-artifact-v1"
MAX_CALIBRATION_ARTIFACT_BYTES = 4 * 1024 * 1024

TOP_LEVEL_KEYS = frozenset(
    {
        "artifact_version",
        "artifact_id",
        "source_snapshot",
        "source_partition",
        "source_aggregate_sha256",
        "schema_fingerprint",
        "created_at",
        "disclosure_policy",
        "strata",
    }
)
DISCLOSURE_POLICY_KEYS = frozenset(
    {
        "policy_id",
        "policy_version",
        "minimum_cell_count",
        "continuous_rounding_decimals",
    }
)
STRATUM_KEYS = frozenset({"stratum_id", "dimensions", "targets"})
TARGET_KEYS = frozenset(
    {
        "target_name",
        "family",
        "statistic",
        "unit",
        "status",
        "value",
        "support_count",
        "denominator",
        "rounding_decimals",
    }
)
QUANTILE_TARGET_KEYS = TARGET_KEYS | {"quantile_level"}

ALLOWED_DIMENSION_KEYS = frozenset(
    {
        "age_regime",
        "reference_sex",
        "recorded_sex",
        "race",
        "ethnicity",
        "encounter_type",
        "disorder_kind",
        "visit_window",
        "measurement_channel",
        "observation_status",
        "outcome_layer",
    }
)
ALLOWED_TARGET_FAMILIES = frozenset(
    {"demographics", "observation", "physiology", "utilization", "recorded_outcome"}
)
ALLOWED_STATISTICS = frozenset({"count", "proportion", "mean", "sd", "quantile", "rate"})
ALLOWED_STATUSES = frozenset({"released", "suppressed"})

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_DIMENSION_VALUE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_UTC_TIMESTAMP_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
_IDENTIFIER_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*-[PV]-[0-9]{3,}\b", re.IGNORECASE)
_PATH_EXTENSION_RE = re.compile(
    r"\b[A-Za-z0-9_-]+\.(?:csv|tsv|json|parquet|txt|zip|gz)\b", re.IGNORECASE
)
_RECORD_INDICATORS = frozenset(
    {"patient", "visit", "identifier", "uuid", "sequence", "truth", "candidate", "match", "row", "resource"}
)
_AGGREGATE_UNSAFE_WORDS = frozenset({"patient", "visit", "path", "key", "identifier"})
_ATTACK_OUTPUT_INDICATORS = frozenset(
    {
        "attribute_disclosure",
        "attribute_inference",
        "composition",
        "differential_privacy",
        "linkage",
        "membership_inference",
        "model_inversion",
        "privacy_audit",
        "privacy_attack",
        "reidentification",
        "singling_out",
    }
)
_TARGET_NAME_INDICATORS = _RECORD_INDICATORS | _ATTACK_OUTPUT_INDICATORS | {"latent"}
_RESERVED_DIMENSION_VALUES = frozenset({"latent", "truth", "sequence", "candidate"})
_MAX_STRATUM_DIMENSIONS = 4


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")  # noqa: TRY004
    return value


def _require_integer(value: object, field: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")  # noqa: TRY004
    if minimum is not None and value < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    return value


def _require_finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")  # noqa: TRY004
    try:
        number = float(value)
    except OverflowError:
        raise ValueError(f"{field} must be a finite number") from None
    if not math.isfinite(number):
        raise ValueError(f"{field} must be a finite number")
    return number


def _metadata_components(value: str) -> tuple[str, ...]:
    acronym_separated = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", value)
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", acronym_separated)
    return tuple(re.findall(r"[a-z0-9]+", normalized.lower()))


def contains_aggregate_unsafe_material(value: str) -> bool:
    words = frozenset(_metadata_components(value))
    return bool(words & _AGGREGATE_UNSAFE_WORDS)


def contains_indicator_components(value: str, indicators: Collection[str]) -> bool:
    """Match whole delimiter/camel-case components, including multiword indicators."""
    components = _metadata_components(value)
    for indicator in indicators:
        indicator_components = _metadata_components(indicator)
        width = len(indicator_components)
        if width and any(
            components[index : index + width] == indicator_components
            for index in range(len(components) - width + 1)
        ):
            return True
    return False


def contains_serialized_metadata_unsafe_material(value: str) -> bool:
    """Detect governed identifiers and paths in serialized aggregate metadata."""
    return (
        contains_aggregate_unsafe_material(value)
        or bool(_IDENTIFIER_RE.search(value))
        or "/" in value
        or "\\" in value
        or bool(_PATH_EXTENSION_RE.search(value))
    )


def _validate_token(value: object, field: str, *, dimension_value: bool = False) -> str:
    token = _require_string(value, field)
    pattern = _DIMENSION_VALUE_RE if dimension_value else _TOKEN_RE
    if pattern.fullmatch(token) is None:
        raise ValueError(f"{field} must be an ASCII token without whitespace or path separators")
    if contains_serialized_metadata_unsafe_material(token):
        raise ValueError(f"{field} must be aggregate-safe")
    if contains_indicator_components(token, _RECORD_INDICATORS):
        raise ValueError(f"{field} must not contain record or hidden-state indicators")
    return token


def require_aggregate_safe_token(value: object, field: str) -> str:
    """Validate a serialized artifact metadata token against the shared boundary."""
    return _validate_token(value, field)


def _validate_target_name(value: object) -> str:
    target_name = _require_string(value, "target_name")
    if _TOKEN_RE.fullmatch(target_name) is None:
        raise ValueError("target_name must be an ASCII token without whitespace or path separators")
    if contains_serialized_metadata_unsafe_material(target_name):
        raise ValueError("target_name must be aggregate-safe")
    if contains_indicator_components(target_name, _TARGET_NAME_INDICATORS):
        raise ValueError("target_name must not contain record, hidden-state, or attack-output indicators")
    return target_name


def _validate_exact_keys(value: Mapping[object, object], expected: frozenset[str], field: str) -> None:
    if not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} keys must be strings")
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise ValueError(f"{field} keys must match exactly; missing={missing}, unknown={unknown}")


def _require_mapping(value: object, field: str) -> Mapping[object, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")  # noqa: TRY004
    return value


def _require_list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")  # noqa: TRY004
    return value


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate key in JSON object: {key}")
        value[key] = item
    return value


def _reject_nonfinite_json_constant(value: str) -> object:
    raise ValueError(f"nonfinite JSON constant is not allowed: {value}")


def _validate_sha256(value: object, field: str) -> str:
    text = _require_string(value, field)
    if _SHA256_RE.fullmatch(text) is None:
        raise ValueError(f"{field} must be a lowercase 64-hex sha256")
    return text


def _validate_created_at(value: object) -> str:
    created_at = _require_string(value, "created_at")
    if _UTC_TIMESTAMP_RE.fullmatch(created_at) is None:
        raise ValueError("created_at must be an exact UTC timestamp")
    try:
        datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValueError("created_at must be a valid Gregorian UTC timestamp") from exc
    return created_at


@dataclass(frozen=True)
class CalibrationDisclosurePolicy:
    policy_id: str
    policy_version: str
    minimum_cell_count: int
    continuous_rounding_decimals: int

    def __post_init__(self) -> None:
        _validate_token(self.policy_id, "policy_id")
        _validate_token(self.policy_version, "policy_version")
        _require_integer(self.minimum_cell_count, "minimum_cell_count", minimum=1)
        precision = _require_integer(self.continuous_rounding_decimals, "continuous_rounding_decimals")
        if not 0 <= precision <= 9:
            raise ValueError("continuous_rounding_decimals must be in 0..9")


@dataclass(frozen=True)
class CalibrationTarget:
    target_name: str
    family: str
    statistic: str
    unit: str
    status: str
    value: int | float | None
    support_count: int | None
    denominator: int | None
    rounding_decimals: int
    quantile_level: float | None = None

    def __post_init__(self) -> None:
        _validate_target_name(self.target_name)
        family = _require_string(self.family, "family")
        if family not in ALLOWED_TARGET_FAMILIES:
            raise ValueError(f"family must be one of {sorted(ALLOWED_TARGET_FAMILIES)}")
        statistic = _require_string(self.statistic, "statistic")
        if statistic not in ALLOWED_STATISTICS:
            raise ValueError(f"statistic must be one of {sorted(ALLOWED_STATISTICS)}")
        _validate_token(self.unit, "unit")
        status = _require_string(self.status, "status")
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"status must be one of {sorted(ALLOWED_STATUSES)}")
        rounding_decimals = _require_integer(self.rounding_decimals, "rounding_decimals", minimum=0)

        if status == "suppressed":
            if self.value is not None or self.support_count is not None or self.denominator is not None:
                raise ValueError("suppressed targets require null value, support_count, and denominator")
            if rounding_decimals != 0:
                raise ValueError("suppressed targets require rounding_decimals=0")
        else:
            if self.value is None:
                raise ValueError("released targets require a value")
            if self.support_count is None:
                raise ValueError("released targets require support_count")
            _require_integer(self.support_count, "support_count", minimum=0)
            if self.denominator is not None:
                denominator = _require_integer(self.denominator, "denominator", minimum=1)
                if self.support_count > denominator:
                    raise ValueError("support_count must not exceed denominator")

            if statistic == "count":
                count = _require_integer(self.value, "value", minimum=0)
                if rounding_decimals != 0:
                    raise ValueError("count targets require rounding_decimals=0")
                object.__setattr__(self, "value", count)
            else:
                numeric_value = _require_finite_number(self.value, "value")
                if statistic == "proportion" and not 0 <= numeric_value <= 1:
                    raise ValueError("proportion value must be in [0, 1]")
                if statistic in {"sd", "rate"} and numeric_value < 0:
                    raise ValueError(f"{statistic} value must be nonnegative")
                object.__setattr__(self, "value", numeric_value)
            if statistic in {"proportion", "rate"} and self.denominator is None:
                raise ValueError(f"{statistic} targets require a positive denominator")

        if statistic == "quantile":
            if self.quantile_level is None:
                raise ValueError("quantile_level is required for quantile targets")
            quantile_level = _require_finite_number(self.quantile_level, "quantile_level")
            if not 0 <= quantile_level <= 1:
                raise ValueError("quantile_level must be in [0, 1]")
            object.__setattr__(self, "quantile_level", quantile_level)
        elif self.quantile_level is not None:
            raise ValueError("quantile_level is only allowed for quantile targets")


@dataclass(frozen=True)
class CalibrationStratum:
    stratum_id: str
    dimensions: tuple[tuple[str, str], ...]
    targets: tuple[CalibrationTarget, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.dimensions, tuple):
            raise ValueError("dimensions must be an immutable tuple")  # noqa: TRY004
        if not 1 <= len(self.dimensions) <= _MAX_STRATUM_DIMENSIONS:
            raise ValueError("dimensions must contain one to four entries")

        normalized_dimensions: list[tuple[str, str]] = []
        for dimension in self.dimensions:
            if not isinstance(dimension, tuple) or len(dimension) != 2:
                raise ValueError("dimensions entries must be key-value tuples")
            key, raw_dimension_value = dimension
            if not isinstance(key, str) or key not in ALLOWED_DIMENSION_KEYS:
                raise ValueError("dimension key is not allowed")
            dimension_value = _validate_token(
                raw_dimension_value, f"dimensions.{key}", dimension_value=True
            )
            if dimension_value.lower() in _RESERVED_DIMENSION_VALUES:
                raise ValueError("dimension values must not encode hidden state")
            normalized_dimensions.append((key, dimension_value))
        if len({key for key, _ in normalized_dimensions}) != len(normalized_dimensions):
            raise ValueError("dimension keys must be unique")
        normalized_dimensions.sort()
        expected_stratum_id = "|".join(f"{key}={value}" for key, value in normalized_dimensions)
        if self.stratum_id != expected_stratum_id:
            raise ValueError("stratum_id must use canonical sorted dimensions")
        object.__setattr__(self, "dimensions", tuple(normalized_dimensions))

        if not isinstance(self.targets, tuple) or not self.targets:
            raise ValueError("targets must be a nonempty immutable tuple")
        if not all(isinstance(target, CalibrationTarget) for target in self.targets):
            raise ValueError("targets must contain CalibrationTarget values")
        if len({target.target_name for target in self.targets}) != len(self.targets):
            raise ValueError("duplicate target_name")
        object.__setattr__(self, "targets", tuple(sorted(self.targets, key=lambda target: target.target_name)))


@dataclass(frozen=True)
class CalibrationArtifact:
    artifact_version: str
    artifact_id: str
    source_snapshot: str
    source_partition: str
    source_aggregate_sha256: str
    schema_fingerprint: str
    created_at: str
    disclosure_policy: CalibrationDisclosurePolicy
    strata: tuple[CalibrationStratum, ...]

    def __post_init__(self) -> None:
        if self.artifact_version != ARTIFACT_VERSION:
            raise ValueError(f"artifact_version must be {ARTIFACT_VERSION}")
        _validate_token(self.artifact_id, "artifact_id")
        _validate_token(self.source_snapshot, "source_snapshot")
        if self.source_partition != "calibration":
            raise ValueError("source_partition must be calibration")
        _validate_sha256(self.source_aggregate_sha256, "source_aggregate_sha256")
        _validate_sha256(self.schema_fingerprint, "schema_fingerprint")
        _validate_created_at(self.created_at)
        if not isinstance(self.disclosure_policy, CalibrationDisclosurePolicy):
            raise ValueError("disclosure_policy must be a CalibrationDisclosurePolicy")  # noqa: TRY004
        if not isinstance(self.strata, tuple) or not self.strata:
            raise ValueError("strata must be a nonempty immutable tuple")
        if not all(isinstance(stratum, CalibrationStratum) for stratum in self.strata):
            raise ValueError("strata must contain CalibrationStratum values")
        if len({stratum.stratum_id for stratum in self.strata}) != len(self.strata):
            raise ValueError("duplicate stratum_id")
        object.__setattr__(self, "strata", tuple(sorted(self.strata, key=lambda stratum: stratum.stratum_id)))

        policy = self.disclosure_policy
        for stratum in self.strata:
            for target in stratum.targets:
                if target.status == "released":
                    if target.support_count is None or target.support_count < policy.minimum_cell_count:
                        raise ValueError("released support_count is below minimum_cell_count")
                    if target.rounding_decimals > policy.continuous_rounding_decimals:
                        raise ValueError("rounding_decimals exceeds policy precision")

    @classmethod
    def from_mapping(cls, value: object) -> CalibrationArtifact:
        root = _require_mapping(value, "artifact")
        _validate_exact_keys(root, TOP_LEVEL_KEYS, "artifact")

        policy_value = _require_mapping(root["disclosure_policy"], "disclosure_policy")
        _validate_exact_keys(policy_value, DISCLOSURE_POLICY_KEYS, "disclosure_policy")
        policy = CalibrationDisclosurePolicy(
            policy_id=policy_value["policy_id"],  # type: ignore[arg-type]
            policy_version=policy_value["policy_version"],  # type: ignore[arg-type]
            minimum_cell_count=policy_value["minimum_cell_count"],  # type: ignore[arg-type]
            continuous_rounding_decimals=policy_value["continuous_rounding_decimals"],  # type: ignore[arg-type]
        )

        raw_strata = _require_list(root["strata"], "strata")
        if not raw_strata:
            raise ValueError("strata must not be empty")
        strata = tuple(cls._stratum_from_mapping(raw_stratum) for raw_stratum in raw_strata)
        return cls(
            artifact_version=root["artifact_version"],  # type: ignore[arg-type]
            artifact_id=root["artifact_id"],  # type: ignore[arg-type]
            source_snapshot=root["source_snapshot"],  # type: ignore[arg-type]
            source_partition=root["source_partition"],  # type: ignore[arg-type]
            source_aggregate_sha256=root["source_aggregate_sha256"],  # type: ignore[arg-type]
            schema_fingerprint=root["schema_fingerprint"],  # type: ignore[arg-type]
            created_at=root["created_at"],  # type: ignore[arg-type]
            disclosure_policy=policy,
            strata=strata,
        )

    @staticmethod
    def _stratum_from_mapping(value: object) -> CalibrationStratum:
        raw_stratum = _require_mapping(value, "stratum")
        _validate_exact_keys(raw_stratum, STRATUM_KEYS, "stratum")
        raw_dimensions = _require_mapping(raw_stratum["dimensions"], "dimensions")
        if not raw_dimensions:
            raise ValueError("dimensions must not be empty")
        if not all(isinstance(key, str) for key in raw_dimensions):
            raise ValueError("dimension keys must be strings")
        dimensions = tuple((key, raw_dimensions[key]) for key in sorted(raw_dimensions))

        raw_targets = _require_list(raw_stratum["targets"], "targets")
        if not raw_targets:
            raise ValueError("targets must not be empty")
        targets = tuple(CalibrationArtifact._target_from_mapping(raw_target) for raw_target in raw_targets)
        return CalibrationStratum(
            stratum_id=raw_stratum["stratum_id"],  # type: ignore[arg-type]
            dimensions=dimensions,  # type: ignore[arg-type]
            targets=targets,
        )

    @staticmethod
    def _target_from_mapping(value: object) -> CalibrationTarget:
        raw_target = _require_mapping(value, "target")
        statistic = raw_target.get("statistic")
        expected_keys = QUANTILE_TARGET_KEYS if statistic == "quantile" else TARGET_KEYS
        _validate_exact_keys(raw_target, expected_keys, "target")
        return CalibrationTarget(
            target_name=raw_target["target_name"],  # type: ignore[arg-type]
            family=raw_target["family"],  # type: ignore[arg-type]
            statistic=raw_target["statistic"],  # type: ignore[arg-type]
            unit=raw_target["unit"],  # type: ignore[arg-type]
            status=raw_target["status"],  # type: ignore[arg-type]
            value=raw_target["value"],  # type: ignore[arg-type]
            support_count=raw_target["support_count"],  # type: ignore[arg-type]
            denominator=raw_target["denominator"],  # type: ignore[arg-type]
            rounding_decimals=raw_target["rounding_decimals"],  # type: ignore[arg-type]
            quantile_level=raw_target.get("quantile_level"),  # type: ignore[arg-type]
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "artifact_version": self.artifact_version,
            "artifact_id": self.artifact_id,
            "source_snapshot": self.source_snapshot,
            "source_partition": self.source_partition,
            "source_aggregate_sha256": self.source_aggregate_sha256,
            "schema_fingerprint": self.schema_fingerprint,
            "created_at": self.created_at,
            "disclosure_policy": {
                "policy_id": self.disclosure_policy.policy_id,
                "policy_version": self.disclosure_policy.policy_version,
                "minimum_cell_count": self.disclosure_policy.minimum_cell_count,
                "continuous_rounding_decimals": self.disclosure_policy.continuous_rounding_decimals,
            },
            "strata": [self._stratum_to_mapping(stratum) for stratum in self.strata],
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.to_mapping(), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        )

    @staticmethod
    def _stratum_to_mapping(stratum: CalibrationStratum) -> dict[str, object]:
        return {
            "stratum_id": stratum.stratum_id,
            "dimensions": {key: value for key, value in stratum.dimensions},
            "targets": [CalibrationArtifact._target_to_mapping(target) for target in stratum.targets],
        }

    @staticmethod
    def _target_to_mapping(target: CalibrationTarget) -> dict[str, object]:
        value: dict[str, object] = {
            "target_name": target.target_name,
            "family": target.family,
            "statistic": target.statistic,
            "unit": target.unit,
            "status": target.status,
            "value": target.value,
            "support_count": target.support_count,
            "denominator": target.denominator,
            "rounding_decimals": target.rounding_decimals,
        }
        if target.statistic == "quantile":
            value["quantile_level"] = target.quantile_level
        return value


def load_calibration_artifact(path: Path) -> CalibrationArtifact:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ValueError("calibration artifact requires secure no-follow opening")

    flags = os.O_RDONLY | nofollow | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        raise ValueError("calibration artifact path was not found") from None
    except OSError as error:
        if error.errno == ELOOP:
            raise ValueError("calibration artifact path must be a regular file") from None
        raise ValueError("calibration artifact could not be securely opened") from None

    try:
        initial_status = os.fstat(descriptor)
        if not stat.S_ISREG(initial_status.st_mode):
            raise ValueError("calibration artifact path must be a regular file")
        if initial_status.st_size > MAX_CALIBRATION_ARTIFACT_BYTES:
            raise ValueError("calibration artifact exceeds the maximum size")
        payload = os.read(descriptor, MAX_CALIBRATION_ARTIFACT_BYTES + 1)
        final_status = os.fstat(descriptor)
    except OSError:
        raise ValueError("calibration artifact could not be read") from None
    finally:
        os.close(descriptor)

    if (
        len(payload) > MAX_CALIBRATION_ARTIFACT_BYTES
        or final_status.st_size > MAX_CALIBRATION_ARTIFACT_BYTES
        or final_status.st_size > len(payload)
    ):
        raise ValueError("calibration artifact exceeds the maximum size")
    if payload.startswith(b"\xef\xbb\xbf"):
        raise ValueError("calibration artifact must not include a UTF-8 BOM")
    try:
        decoded = payload.decode("utf-8", errors="strict")
    except UnicodeError:
        raise ValueError("calibration artifact must be strict UTF-8") from None
    try:
        value = json.loads(
            decoded,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonfinite_json_constant,
        )
    except (json.JSONDecodeError, RecursionError):
        raise ValueError("calibration artifact must be valid JSON") from None

    if not isinstance(value, Mapping):
        raise ValueError("calibration artifact JSON root must be an object")  # noqa: TRY004
    return CalibrationArtifact.from_mapping(value)
