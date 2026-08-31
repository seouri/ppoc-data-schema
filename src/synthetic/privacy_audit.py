"""Strict private input contracts for the governed synthetic privacy auditor."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

import duckdb

from synthetic.calibration_input import (
    _load_governed_descriptor,
    _stage_validated_resources,
    _validate_descriptor_mapping,
)
from synthetic.schema_contract import (
    field_names,
    load_descriptor,
    resource_spec,
    schema_fingerprint,
)

REPORT_VERSION = "privacy-audit-report-v1"
MAX_PRIVACY_POLICY_BYTES = 1024 * 1024

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
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
_POLICY_KEYS = frozenset({
    "policy_id", "policy_version", "schema_fingerprint", "recipient_class", "release_context",
    "accounting_unit", "attacker_knowledge", "confidence_method", "minimum_evaluable_patients",
    "longitudinal_min_observations", "required_controls", "subgroups", "minimum_shadow_runs",
    "minimum_prior_releases", "review_date", "approver", "thresholds",
})
_THRESHOLD_KEYS = frozenset({
    "identifier_overlap_rate", "exact_reproduction_rate", "nearest_neighbor_zero_rate",
    "nearest_neighbor_unique_rate", "linkage_advantage", "membership_inference_advantage",
    "attribute_disclosure_advantage", "composition_reproduction_rate", "negative_control_advantage",
    "positive_control_advantage",
})
_COMPONENTS = frozenset({"demographics", "timing", "utilization", "trajectory", "diagnosis"})
_CONTROL_IDS = frozenset({
    "identifier_overlap", "exact_reproduction", "nearest_neighbor", "linkage",
    "membership_inference", "attribute_disclosure", "composition", "negative_control", "positive_control",
})
_MANDATORY_CONTROLS = frozenset({"identifier_overlap", "exact_reproduction"})
_STATUSES = frozenset({"PASS", "FAIL", "UNEVALUABLE"})
_SUBGROUPS = frozenset({"overall", "sex"})
_METRIC_KEYS = frozenset({
    "evaluated_count", "generated_count", "reference_count", "heldout_count", "overlap_count",
    "reproduction_count", "overlap_rate", "exact_reproduction_rate", "zero_proximity_rate",
    "unique_nearest_rate", "linkage_advantage", "membership_inference_advantage",
    "attribute_disclosure_advantage", "composition_reproduction_rate", "negative_control_advantage",
    "positive_control_advantage", "rate_ci_lower", "rate_ci_upper", "margin_zero_rate",
    "margin_positive_rate",
})


def _repository_fingerprint() -> str:
    return schema_fingerprint(load_descriptor(_REPOSITORY_ROOT / "datapackage.json"))


def _require_token(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _TOKEN_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be an aggregate-safe ASCII token")
    return value


def _require_integer(value: object, field_name: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field_name} must be an integer of at least {minimum}")
    return value


def _require_threshold(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} threshold must be finite")  # noqa: TRY004
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise ValueError(f"{field_name} threshold must be in [0, 1]")
    return number


def _require_exact_keys(value: Mapping[str, object], keys: frozenset[str], name: str) -> None:
    if set(value) != keys:
        raise ValueError(f"{name} keys are invalid")


def _canonical_subset(
    value: object, allowed: frozenset[str], field_name: str, *, nonempty: bool
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or (nonempty and not value):
        raise ValueError(f"{field_name} must be a {'nonempty ' if nonempty else ''}list")
    if not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} values must be strings")
    items = tuple(value)
    if len(set(items)) != len(items):
        raise ValueError(f"{field_name} contains duplicate values")
    if not set(items) <= allowed:
        kind = "component" if field_name == "attacker_knowledge" else "control"
        raise ValueError(f"{field_name} contains an unsupported {kind}")
    if items != tuple(sorted(items)):
        raise ValueError(f"{field_name} must be canonical sorted order")
    return items


@dataclass(frozen=True)
class PrivacyPolicy:
    policy_id: str
    policy_version: str
    schema_fingerprint: str
    recipient_class: str
    release_context: str
    accounting_unit: str
    attacker_knowledge: tuple[str, ...]
    confidence_method: str
    minimum_evaluable_patients: int
    longitudinal_min_observations: int
    required_controls: tuple[str, ...]
    subgroups: tuple[str, ...]
    minimum_shadow_runs: int
    minimum_prior_releases: int
    review_date: str
    approver: str
    thresholds: Mapping[str, float]

    def __post_init__(self) -> None:
        for name in ("policy_id", "policy_version", "recipient_class", "release_context", "approver"):
            _require_token(getattr(self, name), name)
        if not isinstance(self.schema_fingerprint, str) or _SHA256_RE.fullmatch(self.schema_fingerprint) is None:
            raise ValueError("schema_fingerprint must be lowercase SHA-256")
        if self.schema_fingerprint != _repository_fingerprint():
            raise ValueError("schema_fingerprint does not match repository")
        if self.accounting_unit != "patient":
            raise ValueError("accounting_unit must be patient")
        if self.confidence_method != "wilson_95":
            raise ValueError("confidence_method must be wilson_95")
        knowledge = _canonical_subset(self.attacker_knowledge, _COMPONENTS, "attacker_knowledge", nonempty=True)
        controls = _canonical_subset(self.required_controls, _CONTROL_IDS, "required_controls", nonempty=False)
        subgroups = _canonical_subset(self.subgroups, _SUBGROUPS, "subgroups", nonempty=True)
        object.__setattr__(self, "attacker_knowledge", knowledge)
        object.__setattr__(self, "required_controls", tuple(sorted(set(controls) | _MANDATORY_CONTROLS)))
        object.__setattr__(self, "subgroups", subgroups)
        _require_integer(self.minimum_evaluable_patients, "minimum_evaluable_patients", 3)
        _require_integer(self.longitudinal_min_observations, "longitudinal_min_observations", 3)
        _require_integer(self.minimum_shadow_runs, "minimum_shadow_runs", 0)
        _require_integer(self.minimum_prior_releases, "minimum_prior_releases", 0)
        if not isinstance(self.review_date, str):
            raise ValueError("review_date must be an exact Gregorian date")  # noqa: TRY004
        try:
            if date.fromisoformat(self.review_date).isoformat() != self.review_date:
                raise ValueError
        except ValueError as exc:
            raise ValueError("review_date must be an exact Gregorian date") from exc
        if not isinstance(self.thresholds, Mapping):
            raise ValueError("thresholds must be a mapping")  # noqa: TRY004
        _require_exact_keys(self.thresholds, _THRESHOLD_KEYS, "threshold")
        frozen = {
            name: _require_threshold(self.thresholds[name], name) for name in sorted(_THRESHOLD_KEYS)
        }
        object.__setattr__(self, "thresholds", MappingProxyType(frozen))

    @classmethod
    def from_mapping(cls, value: object) -> PrivacyPolicy:
        if not isinstance(value, Mapping):
            raise ValueError("privacy policy must be an object")  # noqa: TRY004
        _require_exact_keys(value, _POLICY_KEYS, "privacy policy")
        thresholds = value["thresholds"]
        if not isinstance(thresholds, Mapping):
            raise ValueError("thresholds must be a mapping")  # noqa: TRY004
        return cls(
            policy_id=value["policy_id"], policy_version=value["policy_version"],
            schema_fingerprint=value["schema_fingerprint"], recipient_class=value["recipient_class"],
            release_context=value["release_context"], accounting_unit=value["accounting_unit"],
            attacker_knowledge=tuple(value["attacker_knowledge"]), confidence_method=value["confidence_method"],
            minimum_evaluable_patients=value["minimum_evaluable_patients"],
            longitudinal_min_observations=value["longitudinal_min_observations"],
            required_controls=tuple(value["required_controls"]), subgroups=tuple(value["subgroups"]),
            minimum_shadow_runs=value["minimum_shadow_runs"],
            minimum_prior_releases=value["minimum_prior_releases"], review_date=value["review_date"],
            approver=value["approver"], thresholds=thresholds,
        )  # type: ignore[arg-type]

    def to_report_mapping(self) -> dict[str, str]:
        return {
            "policy_id": self.policy_id, "policy_version": self.policy_version,
            "recipient_class": self.recipient_class, "release_context": self.release_context,
            "accounting_unit": self.accounting_unit, "review_date": self.review_date,
        }


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("privacy policy contains a duplicate key")
        result[key] = value
    return result


def _reject_nonfinite_json(_value: str) -> None:
    raise ValueError("privacy policy contains a nonfinite number")


def _read_regular_bytes(path: Path, label: str, maximum: int) -> bytes:
    if not isinstance(path, Path):
        raise ValueError(f"{label} must be a Path")  # noqa: TRY004
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ValueError(f"{label} requires secure no-follow opening")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | nofollow)
    except OSError as exc:
        raise ValueError(f"{label} must be a regular non-symlink file") from exc
    try:
        initial = os.fstat(fd)
        if not os.path.isfile(path) or initial.st_size > maximum:
            raise ValueError(f"{label} must be a bounded regular file")
        chunks: list[bytes] = []
        total = 0
        while total <= maximum:
            block = os.read(fd, min(64 * 1024, maximum + 1 - total))
            if not block:
                break
            chunks.append(block)
            total += len(block)
        final = os.fstat(fd)
    except OSError as exc:
        raise ValueError(f"{label} could not be securely read") from exc
    finally:
        os.close(fd)
    payload = b"".join(chunks)
    if len(payload) > maximum or final.st_size > maximum or final.st_size > len(payload):
        raise ValueError(f"{label} exceeds the maximum size")
    return payload


def load_privacy_policy(path: Path) -> PrivacyPolicy:
    try:
        mapping = json.loads(
            _read_regular_bytes(path, "privacy policy", MAX_PRIVACY_POLICY_BYTES).decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonfinite_json,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise ValueError("privacy policy is invalid") from exc
    return PrivacyPolicy.from_mapping(mapping)


@dataclass(frozen=True)
class PrivacyRunConfig:
    real_root: Path
    synthetic_root: Path
    policy: Path
    output: Path
    heldout_root: Path | None = None
    shadow_manifest: Path | None = None
    prior_release_roots: tuple[Path, ...] = ()
    negative_control_root: Path | None = None
    positive_control_root: Path | None = None

    def __post_init__(self) -> None:
        for name in ("real_root", "synthetic_root", "policy", "output"):
            if not isinstance(getattr(self, name), Path):
                raise ValueError(f"{name} must be a Path")  # noqa: TRY004
        for name in ("heldout_root", "shadow_manifest", "negative_control_root", "positive_control_root"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, Path):
                raise ValueError(f"{name} must be a Path or None")
        if not isinstance(self.prior_release_roots, tuple) or not all(
            isinstance(item, Path) for item in self.prior_release_roots
        ):
            raise ValueError("prior_release_roots must be an immutable Path tuple")


def _metric_value(value: object, key: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("metrics must have finite aggregate numeric values")  # noqa: TRY004
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError("metrics must have finite nonnegative aggregate values")
    if (key.endswith(("_rate", "_advantage")) or key.startswith("rate_ci_")) and number > 1:
        raise ValueError("rate metrics must be in [0, 1]")
    return value


@dataclass(frozen=True)
class PrivacyControlResult:
    control_id: str
    status: Literal["PASS", "FAIL", "UNEVALUABLE"]
    metrics: Mapping[str, int | float]
    reason_code: str

    def __post_init__(self) -> None:
        if self.control_id not in _CONTROL_IDS:
            raise ValueError("control_id is unsupported")
        if self.status not in _STATUSES:
            raise ValueError("control status is invalid")
        _require_token(self.reason_code, "reason_code")
        if not isinstance(self.metrics, Mapping) or not set(self.metrics) <= _METRIC_KEYS:
            raise ValueError("metric keys are not aggregate-safe")
        if self.status == "UNEVALUABLE" and self.metrics:
            raise ValueError("unevaluable controls must omit metrics")
        metrics = {key: _metric_value(value, key) for key, value in sorted(self.metrics.items())}
        object.__setattr__(self, "metrics", MappingProxyType(metrics))

    def to_mapping(self) -> dict[str, object]:
        return {
            "control_id": self.control_id,
            "status": self.status,
            "metrics": dict(self.metrics),
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class PrivacyAuditReport:
    status: Literal["PASS", "FAIL", "UNEVALUABLE"]
    policy: PrivacyPolicy
    schema_fingerprint: str
    synthetic_artifact_id: str
    control_counts: Mapping[str, int]
    controls: tuple[PrivacyControlResult, ...]
    decision_reasons: tuple[str, ...]
    report_version: str = REPORT_VERSION

    def __post_init__(self) -> None:
        if self.report_version != REPORT_VERSION or self.status not in _STATUSES:
            raise ValueError("privacy report status or version is invalid")
        if not isinstance(self.policy, PrivacyPolicy):
            raise ValueError("privacy report policy is invalid")  # noqa: TRY004
        if self.schema_fingerprint != self.policy.schema_fingerprint:
            raise ValueError("privacy report fingerprint is incompatible")
        _require_token(self.synthetic_artifact_id, "synthetic_artifact_id")
        if not isinstance(self.controls, tuple) or not all(
            isinstance(control, PrivacyControlResult) for control in self.controls
        ):
            raise ValueError("privacy report controls must be an immutable tuple")
        ids = tuple(control.control_id for control in self.controls)
        if ids != tuple(sorted(ids)) or len(set(ids)) != len(ids):
            raise ValueError("privacy report controls must have sorted unique IDs")
        if not set(self.policy.required_controls) <= set(ids):
            raise ValueError("privacy report required control coverage is incomplete")
        for control in self.controls:
            if control.status == "UNEVALUABLE":
                continue
            evaluated_count = control.metrics.get("evaluated_count")
            if (
                isinstance(evaluated_count, bool)
                or not isinstance(evaluated_count, int)
                or evaluated_count < self.policy.minimum_evaluable_patients
            ):
                raise ValueError("evaluated controls require policy-minimum evaluated_count")
        expected_status = "FAIL" if any(control.status == "FAIL" for control in self.controls) else "PASS"
        if expected_status == "PASS" and any(
            control.control_id in self.policy.required_controls and control.status == "UNEVALUABLE"
            for control in self.controls
        ):
            expected_status = "UNEVALUABLE"
        if self.status != expected_status:
            raise ValueError("privacy report status does not match control results")
        if set(self.control_counts) != _STATUSES or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in self.control_counts.values()
        ):
            raise ValueError("privacy report control counts are invalid")
        expected = {name: sum(item.status == name for item in self.controls) for name in _STATUSES}
        if dict(self.control_counts) != expected:
            raise ValueError("privacy report control counts do not match controls")
        if not isinstance(self.decision_reasons, tuple) or not self.decision_reasons:
            raise ValueError("privacy report requires decision reasons")
        for reason in self.decision_reasons:
            _require_token(reason, "decision_reason")
        object.__setattr__(self, "control_counts", MappingProxyType(dict(self.control_counts)))
        object.__setattr__(self, "decision_reasons", tuple(sorted(set(self.decision_reasons))))

    def to_mapping(self) -> dict[str, object]:
        return {
            "report_version": self.report_version,
            "status": self.status,
            "policy": self.policy.to_report_mapping(),
            "schema_fingerprint": self.schema_fingerprint,
            "synthetic_artifact_id": self.synthetic_artifact_id,
            "control_counts": dict(self.control_counts),
            "controls": [control.to_mapping() for control in self.controls],
            "decision_reasons": list(self.decision_reasons),
        }

    def canonical_json_bytes(self) -> bytes:
        return (
            json.dumps(
                self.to_mapping(), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
            ).encode("ascii")
            + b"\n"
        )


@dataclass(frozen=True)
class PrivacyAuditResult:
    report: PrivacyAuditReport

    def __post_init__(self) -> None:
        if not isinstance(self.report, PrivacyAuditReport):
            raise ValueError("privacy audit result requires an aggregate report")  # noqa: TRY004


@dataclass(frozen=True)
class _PrivatePatientProfile:
    _patient_id: str = field(repr=False)
    _demographics: tuple[str, ...] = field(repr=False)
    _ages: tuple[int, ...] = field(repr=False)
    _visit_count: int = field(repr=False)
    _trajectory: tuple[tuple[int, float | None, float | None, float | None], ...] = field(repr=False)
    _growth_dx_flag: str | None = field(repr=False)
    _trajectory_signature: str = field(repr=False)
    _profile_signature: str = field(repr=False)
    _component_buckets: Mapping[str, object] = field(repr=False)


@dataclass(frozen=True)
class _PrivatePackage:
    patient_count: int
    _identifier_values: frozenset[str] = field(repr=False)
    _profiles: tuple[_PrivatePatientProfile, ...] = field(repr=False)
    _trajectory_signatures: frozenset[str] = field(repr=False)
    _profile_signatures: frozenset[str] = field(repr=False)
    _ineligible_profile_count: int = field(repr=False)


def _require_patient_links(connection: duckdb.DuckDBPyConnection, staged: Mapping[str, str]) -> None:
    patients_relation = staged["patients"]
    for name in _RESOURCE_NAMES:
        if name == "patients":
            continue
        relation = staged[name]
        missing = connection.execute(
            f'SELECT count(*) FROM "{relation}" AS item LEFT JOIN "{patients_relation}" AS patients '
            "ON item.patient_id = patients.patient_id WHERE patients.patient_id IS NULL"
        ).fetchone()[0]
        if missing:
            raise ValueError("package resource patient links are invalid")


def _private_identifiers(
    connection: duckdb.DuckDBPyConnection, descriptor: Mapping[str, Any], staged: Mapping[str, str]
) -> frozenset[str]:
    values: set[str] = set()
    descriptor_mapping = dict(descriptor)
    for name in _RESOURCE_NAMES:
        resource = resource_spec(descriptor_mapping, name)
        primary_key = resource["schema"].get("primaryKey")
        primary_fields = (primary_key,) if isinstance(primary_key, str) else tuple(primary_key or ())
        fields = set(primary_fields) | {
            field_name
            for field_name in field_names(descriptor_mapping, name)
            if field_name.endswith("_id")
        }
        for field_name in fields:
            rows = connection.execute(
                f'SELECT "{field_name}" FROM "{staged[name]}" '
                f'WHERE "{field_name}" IS NOT NULL AND "{field_name}" <> \'\''
            ).fetchall()
            values.update(value for (value,) in rows if isinstance(value, str))
    return frozenset(values)


def _profile_signature(
    trajectory: tuple[tuple[int, float | None, float | None, float | None], ...]
) -> str:
    payload = json.dumps(trajectory, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def _full_profile_signature(
    demographics: tuple[str, ...],
    ages: tuple[int, ...],
    visit_count: int,
    trajectory: tuple[tuple[int, float | None, float | None, float | None], ...],
    diagnosis: str | None,
) -> str:
    payload = json.dumps(
        {
            "demographics": demographics,
            "diagnosis": diagnosis,
            "timing": ages,
            "trajectory": trajectory,
            "utilization": visit_count,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def _private_profiles(
    connection: duckdb.DuckDBPyConnection, staged: Mapping[str, str], minimum: int
) -> tuple[tuple[_PrivatePatientProfile, ...], int]:
    patient_rows = connection.execute(
        f'SELECT patients.patient_id, patients.sex, patients.ethnicity, patients.race_1, patients.race_2, '
        f'patients.race_3, patients.race_4, patients.race_5, patients.race_6, patients.race_7, patients.race_8, '
        f'augmented.growth_dx_flag FROM "{staged["patients"]}" AS patients LEFT JOIN '
        f'"{staged["patients_augmented"]}" AS augmented ON patients.patient_id = augmented.patient_id '
        "ORDER BY patients.patient_id"
    ).fetchall()
    visit_rows = connection.execute(
        f'SELECT patient_id, age_in_days, height_cm, weight_kg, head_circ_cm '
        f'FROM "{staged["visits_augmented"]}" ORDER BY patient_id, age_in_days, visit_id'
    ).fetchall()
    observations: dict[str, list[tuple[int, float | None, float | None, float | None]]] = {}
    for patient_id, age, height, weight, head_circ in visit_rows:
        values = tuple(
            None if value in (None, "") else round(float(value), 6)
            for value in (height, weight, head_circ)
        )
        if any(value is not None for value in values):
            observations.setdefault(patient_id, []).append((int(age), *values))
    visit_counts = dict(
        connection.execute(
            f'SELECT patient_id, count(*) FROM "{staged["visits"]}" GROUP BY patient_id'
        ).fetchall()
    )
    profiles: list[_PrivatePatientProfile] = []
    ineligible = 0
    for row in patient_rows:
        patient_id, *demographics, growth_dx_flag = row
        trajectory = tuple(observations.get(patient_id, ()))
        if len(trajectory) < minimum:
            ineligible += 1
            continue
        demographic_values = tuple("" if value is None else str(value) for value in demographics)
        ages = tuple(observation[0] for observation in trajectory)
        diagnosis = None if growth_dx_flag in (None, "") else str(growth_dx_flag)
        visit_count = int(visit_counts.get(patient_id, 0))
        profiles.append(
            _PrivatePatientProfile(
                _patient_id=patient_id,
                _demographics=demographic_values,
                _ages=ages,
                _visit_count=visit_count,
                _trajectory=trajectory,
                _growth_dx_flag=diagnosis,
                _trajectory_signature=_profile_signature(trajectory),
                _profile_signature=_full_profile_signature(
                    demographic_values, ages, visit_count, trajectory, diagnosis
                ),
                _component_buckets=MappingProxyType(
                    {
                        "demographics": demographic_values,
                        "timing": ages,
                        "utilization": visit_count,
                        "trajectory": trajectory,
                        "diagnosis": diagnosis,
                    }
                ),
            )
        )
    return tuple(profiles), ineligible


def _load_private_package(
    package_root: Path, *, synthetic: bool, longitudinal_minimum: int
) -> _PrivatePackage:
    """Securely stage one exact-schema package and retain private audit inputs only."""
    if not isinstance(package_root, Path) or not isinstance(synthetic, bool):
        raise ValueError("package input is invalid")  # noqa: TRY004
    _require_integer(longitudinal_minimum, "longitudinal_minimum", 3)
    try:
        descriptor = _load_governed_descriptor(package_root / "datapackage.json")
        marker_present = "x-synthetic" in descriptor
        if (synthetic and descriptor.get("x-synthetic") is not True) or (not synthetic and marker_present):
            raise ValueError("package marker polarity is invalid")
        descriptor = _validate_descriptor_mapping(descriptor)
    except (TypeError, ValueError) as exc:
        raise ValueError("package descriptor or marker is invalid") from exc
    connection = duckdb.connect(":memory:")
    try:
        staged = _stage_validated_resources(connection, descriptor, package_root)
        _require_patient_links(connection, staged)
        identifiers = _private_identifiers(connection, descriptor, staged)
        profiles, ineligible = _private_profiles(connection, staged, longitudinal_minimum)
        patient_count = connection.execute(
            f'SELECT count(*) FROM "{staged["patients"]}"'
        ).fetchone()[0]
    except (duckdb.Error, TypeError, ValueError) as exc:
        raise ValueError("package data is invalid") from exc
    finally:
        connection.close()
    return _PrivatePackage(
        patient_count=patient_count,
        _identifier_values=identifiers,
        _profiles=profiles,
        _trajectory_signatures=frozenset(profile._trajectory_signature for profile in profiles),
        _profile_signatures=frozenset(profile._profile_signature for profile in profiles),
        _ineligible_profile_count=ineligible,
    )
