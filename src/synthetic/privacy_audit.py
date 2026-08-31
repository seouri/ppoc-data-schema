"""Strict private input contracts for the governed synthetic privacy auditor."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
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
from synthetic.run_directory import RunDirectory
from synthetic.schema_contract import (
    field_names,
    load_descriptor,
    resource_spec,
    schema_fingerprint,
)

REPORT_VERSION = "privacy-audit-report-v1"
MAX_PRIVACY_POLICY_BYTES = 1024 * 1024
MAX_PRIVACY_SHADOW_MANIFEST_BYTES = 1024 * 1024
_PRIVACY_REPORT_FILENAME = "privacy-audit-report.json"
_PRIVACY_SUMMARY_FILENAME = "privacy-audit-summary.txt"

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
    "identifier_count", "reproduction_count", "overlap_rate", "exact_reproduction_rate",
    "zero_proximity_rate", "unique_nearest_rate", "heldout_zero_proximity_rate",
    "heldout_unique_nearest_rate", "unique_candidate_rate", "permutation_unique_rate",
    "heldout_unique_candidate_rate",
    "linkage_advantage", "membership_inference_advantage", "attribute_disclosure_advantage",
    "composition_reproduction_rate", "negative_control_advantage", "positive_control_advantage",
    "shadow_run_count", "prior_release_count", "membership_match_rate",
    "attribute_attack_accuracy", "reference_majority_accuracy", "heldout_majority_accuracy",
    "advantage_ci_lower", "advantage_ci_upper",
    "rate_ci_lower", "rate_ci_upper", "margin_zero_rate", "margin_positive_rate",
})
_FIXED_COMPONENT_ORDER = ("demographics", "timing", "utilization", "trajectory", "diagnosis")
_WILSON_95_Z = 1.959963984540054


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
        if not stat.S_ISREG(initial.st_mode) or initial.st_size > maximum:
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


@dataclass(frozen=True)
class _PrivateShadowRun:
    """One private labelled shadow package; labels never leave the audit process."""

    run_id: str
    _package: _PrivatePackage = field(repr=False)
    _member_trajectory_signatures: frozenset[str] = field(repr=False)


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


def _unevaluable_control(control_id: str, reason_code: str) -> PrivacyControlResult:
    return PrivacyControlResult(control_id, "UNEVALUABLE", {}, reason_code)


def _wilson_95_interval(successes: int, total: int) -> tuple[float, float]:
    """Return the fixed, rounded Wilson interval for one aggregate count."""
    if total <= 0 or not 0 <= successes <= total:
        raise ValueError("Wilson interval inputs are invalid")
    proportion = successes / total
    squared_z = _WILSON_95_Z**2
    denominator = 1 + squared_z / total
    centre = (proportion + squared_z / (2 * total)) / denominator
    spread = (_WILSON_95_Z / denominator) * math.sqrt(
        (proportion * (1 - proportion) / total) + squared_z / (4 * total**2)
    )
    return round(max(0.0, centre - spread), 6), round(min(1.0, centre + spread), 6)


def _with_interval(
    metrics: dict[str, int | float], successes: int, total: int
) -> dict[str, int | float]:
    lower, upper = _wilson_95_interval(successes, total)
    return metrics | {"rate_ci_lower": lower, "rate_ci_upper": upper}


def _packages_have_patient_evidence(policy: PrivacyPolicy, *packages: _PrivatePackage) -> bool:
    return all(package.patient_count >= policy.minimum_evaluable_patients for package in packages)


def _packages_have_profile_evidence(policy: PrivacyPolicy, *packages: _PrivatePackage) -> bool:
    return all(len(package._profiles) >= policy.minimum_evaluable_patients for package in packages)


def _evaluate_identifier_overlap_control(
    policy: PrivacyPolicy, reference: _PrivatePackage, generated: _PrivatePackage
) -> PrivacyControlResult:
    """Evaluate the mandatory private identifier-overlap gate without retaining identifiers."""
    if (
        not _packages_have_patient_evidence(policy, reference, generated)
        or not reference._identifier_values
        or not generated._identifier_values
    ):
        return _unevaluable_control("identifier_overlap", "insufficient_evidence")
    overlap_count = len(reference._identifier_values & generated._identifier_values)
    identifier_count = len(generated._identifier_values)
    overlap_rate = round(overlap_count / identifier_count, 6)
    metrics = _with_interval(
        {
            "evaluated_count": generated.patient_count,
            "reference_count": reference.patient_count,
            "identifier_count": identifier_count,
            "overlap_count": overlap_count,
            "overlap_rate": overlap_rate,
        },
        overlap_count,
        identifier_count,
    )
    if overlap_count:
        return PrivacyControlResult(
            "identifier_overlap", "FAIL", metrics, "identifier_overlap_detected"
        )
    if overlap_rate > policy.thresholds["identifier_overlap_rate"]:
        return PrivacyControlResult(
            "identifier_overlap", "FAIL", metrics, "identifier_overlap_threshold_exceeded"
        )
    return PrivacyControlResult("identifier_overlap", "PASS", metrics, "no_identifier_overlap")


def _evaluate_exact_reproduction_control(
    policy: PrivacyPolicy, reference: _PrivatePackage, generated: _PrivatePackage
) -> PrivacyControlResult:
    """Evaluate mandatory exact eligible-trajectory reproduction privately."""
    if not _packages_have_profile_evidence(policy, reference, generated):
        return _unevaluable_control("exact_reproduction", "insufficient_evidence")
    reproduction_count = sum(
        profile._trajectory_signature in reference._trajectory_signatures
        for profile in generated._profiles
    )
    evaluated_count = len(generated._profiles)
    reproduction_rate = round(reproduction_count / evaluated_count, 6)
    metrics = _with_interval(
        {
            "evaluated_count": evaluated_count,
            "reference_count": len(reference._profiles),
            "reproduction_count": reproduction_count,
            "exact_reproduction_rate": reproduction_rate,
        },
        reproduction_count,
        evaluated_count,
    )
    if reproduction_count:
        return PrivacyControlResult(
            "exact_reproduction", "FAIL", metrics, "exact_reproduction_detected"
        )
    if reproduction_rate > policy.thresholds["exact_reproduction_rate"]:
        return PrivacyControlResult(
            "exact_reproduction", "FAIL", metrics, "exact_reproduction_threshold_exceeded"
        )
    return PrivacyControlResult("exact_reproduction", "PASS", metrics, "no_exact_reproduction")


def _component_tuple(
    profile: _PrivatePatientProfile, components: tuple[str, ...]
) -> tuple[object, ...]:
    return tuple(profile._component_buckets[name] for name in components)


def _bucket_counts(
    profiles: tuple[_PrivatePatientProfile, ...], components: tuple[str, ...]
) -> dict[tuple[object, ...], int]:
    counts: dict[tuple[object, ...], int] = {}
    for profile in profiles:
        key = _component_tuple(profile, components)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _nearest_outcomes(
    queries: tuple[_PrivatePatientProfile, ...], reference: tuple[_PrivatePatientProfile, ...]
) -> tuple[int, int, int]:
    """Return exact, unique-nearest, and tied-nearest counts through fixed bucket indexes."""
    bucket_indexes: dict[tuple[int, ...], dict[tuple[object, ...], set[int]]] = {}
    for bitmask in range(1, 1 << len(_FIXED_COMPONENT_ORDER)):
        positions = tuple(
            index for index in range(len(_FIXED_COMPONENT_ORDER)) if bitmask & (1 << index)
        )
        index: dict[tuple[object, ...], set[int]] = {}
        for reference_index, profile in enumerate(reference):
            vector = _component_tuple(profile, _FIXED_COMPONENT_ORDER)
            key = tuple(vector[position] for position in positions)
            index.setdefault(key, set()).add(reference_index)
        bucket_indexes[positions] = index
    exact_count = unique_count = tied_count = 0
    for profile in queries:
        vector = _component_tuple(profile, _FIXED_COMPONENT_ORDER)
        nearest_count = len(reference)
        matched_components = 0
        for match_count in range(len(_FIXED_COMPONENT_ORDER), 0, -1):
            candidate_indexes: set[int] = set()
            for positions, index in bucket_indexes.items():
                if len(positions) != match_count:
                    continue
                candidate_indexes.update(index.get(tuple(vector[position] for position in positions), set()))
            if candidate_indexes:
                nearest_count = len(candidate_indexes)
                matched_components = match_count
                break
        if matched_components == len(_FIXED_COMPONENT_ORDER):
            exact_count += 1
        if nearest_count == 1:
            unique_count += 1
        else:
            tied_count += 1
    return exact_count, unique_count, tied_count


def _nearest_metrics(
    reference: _PrivatePackage, generated: _PrivatePackage, heldout: _PrivatePackage | None
) -> dict[str, int | float]:
    evaluated_count = len(generated._profiles)
    zero_count, unique_count, tied_count = _nearest_outcomes(
        generated._profiles, reference._profiles
    )
    metrics: dict[str, int | float] = {
        "evaluated_count": evaluated_count,
        "zero_proximity_rate": round(zero_count / evaluated_count, 6),
        "unique_nearest_rate": round(unique_count / evaluated_count, 6),
        "margin_zero_rate": round(tied_count / evaluated_count, 6),
        "margin_positive_rate": round(unique_count / evaluated_count, 6),
    }
    if heldout is not None:
        heldout_zero, heldout_unique, _ = _nearest_outcomes(generated._profiles, heldout._profiles)
        metrics.update(
            {
                "heldout_count": len(heldout._profiles),
                "heldout_zero_proximity_rate": round(heldout_zero / evaluated_count, 6),
                "heldout_unique_nearest_rate": round(heldout_unique / evaluated_count, 6),
            }
        )
    return _with_interval(
        metrics,
        zero_count,
        evaluated_count,
    )


def _evaluate_nearest_neighbor_control(
    policy: PrivacyPolicy,
    reference: _PrivatePackage,
    generated: _PrivatePackage,
    *,
    heldout: _PrivatePackage | None,
) -> PrivacyControlResult:
    """Evaluate fixed private component-bucket nearest-neighbor aggregate screens."""
    required = "nearest_neighbor" in policy.required_controls
    if heldout is None:
        if required:
            return _unevaluable_control("nearest_neighbor", "heldout_required")
        packages = (reference, generated)
    else:
        packages = (reference, generated, heldout)
    if not _packages_have_profile_evidence(policy, *packages):
        return _unevaluable_control("nearest_neighbor", "insufficient_evidence")
    metrics = _nearest_metrics(reference, generated, heldout)
    if metrics["zero_proximity_rate"] > policy.thresholds["nearest_neighbor_zero_rate"]:
        return PrivacyControlResult(
            "nearest_neighbor", "FAIL", metrics, "zero_proximity_threshold_exceeded"
        )
    if metrics["unique_nearest_rate"] > policy.thresholds["nearest_neighbor_unique_rate"]:
        return PrivacyControlResult(
            "nearest_neighbor", "FAIL", metrics, "unique_nearest_threshold_exceeded"
        )
    reason = "nearest_neighbor_within_threshold" if heldout is not None else "nearest_neighbor_reference_only"
    return PrivacyControlResult("nearest_neighbor", "PASS", metrics, reason)


def _permuted_bucket_counts(
    profiles: tuple[_PrivatePatientProfile, ...], components: tuple[str, ...]
) -> dict[tuple[object, ...], int]:
    """Deterministically break cross-component associations without exporting permuted keys."""
    columns = [
        tuple(profile._component_buckets[name] for profile in profiles) for name in components
    ]
    count = len(profiles)
    keys = tuple(
        tuple(column[(index + offset + 1) % count] for offset, column in enumerate(columns))
        for index in range(count)
    )
    counts: dict[tuple[object, ...], int] = {}
    for key in keys:
        counts[key] = counts.get(key, 0) + 1
    return counts


def _unique_candidate_rate(
    queries: tuple[_PrivatePatientProfile, ...],
    counts: Mapping[tuple[object, ...], int],
    components: tuple[str, ...],
) -> float:
    return round(
        sum(counts.get(_component_tuple(profile, components), 0) == 1 for profile in queries)
        / len(queries),
        6,
    )


def _linkage_selections(policy: PrivacyPolicy) -> tuple[tuple[str, ...], ...]:
    individual = tuple((component,) for component in policy.attacker_knowledge)
    full = tuple(policy.attacker_knowledge)
    return individual if len(full) == 1 else individual + (full,)


def _linkage_candidate_metrics(
    reference: _PrivatePackage,
    generated: _PrivatePackage,
    heldout: _PrivatePackage | None,
    queries: tuple[_PrivatePatientProfile, ...],
    selections: tuple[tuple[str, ...], ...],
) -> dict[str, int | float]:
    candidates: list[tuple[float, float, float, float | None, int]] = []
    for components in selections:
        generated_rate = _unique_candidate_rate(
            queries, _bucket_counts(reference._profiles, components), components
        )
        heldout_rate = (
            _unique_candidate_rate(queries, _bucket_counts(heldout._profiles, components), components)
            if heldout is not None
            else None
        )
        permutation_rate = _unique_candidate_rate(
            queries, _permuted_bucket_counts(reference._profiles, components), components
        )
        candidates.append(
            (
                max(0.0, generated_rate - max(permutation_rate, heldout_rate or 0.0)),
                generated_rate,
                permutation_rate,
                heldout_rate,
                len(queries),
            )
        )
    advantage, unique_rate, permutation_rate, heldout_rate, evaluated_count = max(
        candidates, key=lambda item: (item[0], item[1], item[2])
    )
    successes = round(unique_rate * evaluated_count)
    metrics: dict[str, int | float] = {
        "evaluated_count": evaluated_count,
        "unique_candidate_rate": unique_rate,
        "permutation_unique_rate": permutation_rate,
        "linkage_advantage": round(advantage, 6),
    }
    if heldout is not None and heldout_rate is not None:
        metrics.update(
            {
                "heldout_count": len(heldout._profiles),
                "heldout_unique_candidate_rate": heldout_rate,
            }
        )
    return _with_interval(
        metrics,
        successes,
        evaluated_count,
    )


def _linkage_query_groups(
    policy: PrivacyPolicy, generated: _PrivatePackage
) -> tuple[tuple[_PrivatePatientProfile, ...], ...]:
    groups = [generated._profiles]
    if "sex" in policy.subgroups:
        by_sex: dict[str, list[_PrivatePatientProfile]] = {}
        for profile in generated._profiles:
            by_sex.setdefault(profile._demographics[0], []).append(profile)
        groups.extend(
            tuple(group)
            for _, group in sorted(by_sex.items())
            if len(group) >= policy.minimum_evaluable_patients
        )
    return tuple(groups)


def _evaluate_linkage_control(
    policy: PrivacyPolicy,
    reference: _PrivatePackage,
    generated: _PrivatePackage,
    *,
    heldout: _PrivatePackage | None,
) -> PrivacyControlResult:
    """Evaluate fixed exact-key linkage rates against private held-out and permutation baselines."""
    required = "linkage" in policy.required_controls
    if heldout is None:
        if required:
            return _unevaluable_control("linkage", "heldout_required")
        packages = (reference, generated)
    else:
        packages = (reference, generated, heldout)
    if not _packages_have_profile_evidence(policy, *packages):
        return _unevaluable_control("linkage", "insufficient_evidence")
    group_metrics = tuple(
        _linkage_candidate_metrics(
            reference, generated, heldout, group, _linkage_selections(policy)
        )
        for group in _linkage_query_groups(policy, generated)
    )
    metrics = max(
        group_metrics, key=lambda item: (item["linkage_advantage"], item["unique_candidate_rate"])
    )
    subgroup_failed = any(
        item["linkage_advantage"] > policy.thresholds["linkage_advantage"]
        for item in group_metrics[1:]
    )
    if metrics["linkage_advantage"] > policy.thresholds["linkage_advantage"]:
        reason = (
            "subgroup_linkage_threshold_exceeded"
            if subgroup_failed
            else "linkage_threshold_exceeded"
        )
        return PrivacyControlResult("linkage", "FAIL", metrics, reason)
    reason = "linkage_within_threshold" if heldout is not None else "linkage_reference_permutation_only"
    return PrivacyControlResult("linkage", "PASS", metrics, reason)


_SHADOW_MANIFEST_KEYS = frozenset({"version", "runs"})
_SHADOW_RUN_KEYS = frozenset({"run_id", "package_root", "members"})


def _load_private_shadow_runs(
    manifest_path: Path, reference: _PrivatePackage, policy: PrivacyPolicy
) -> tuple[_PrivateShadowRun, ...]:
    """Load exact-versioned shadow inputs without retaining manifest labels or paths in results."""
    try:
        payload = _read_regular_bytes(
            manifest_path, "privacy shadow manifest", MAX_PRIVACY_SHADOW_MANIFEST_BYTES
        )
        manifest = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonfinite_json,
        )
        if not isinstance(manifest, Mapping):
            raise TypeError
        _require_exact_keys(manifest, _SHADOW_MANIFEST_KEYS, "privacy shadow manifest")
        if manifest["version"] != "privacy-shadow-v1" or not isinstance(manifest["runs"], list):
            raise ValueError
        profiles_by_id = {profile._patient_id: profile for profile in reference._profiles}
        runs: list[_PrivateShadowRun] = []
        run_ids: set[str] = set()
        for entry in manifest["runs"]:
            if not isinstance(entry, Mapping):
                raise TypeError
            _require_exact_keys(entry, _SHADOW_RUN_KEYS, "privacy shadow run")
            run_id = _require_token(entry["run_id"], "shadow run_id")
            package_root = entry["package_root"]
            members = entry["members"]
            if run_id in run_ids or not isinstance(package_root, str) or not package_root:
                raise ValueError
            if not isinstance(members, list) or not members or not all(isinstance(item, str) for item in members):
                raise ValueError
            if len(set(members)) != len(members):
                raise ValueError
            try:
                member_signatures = frozenset(profiles_by_id[item]._trajectory_signature for item in members)
            except KeyError as exc:
                raise ValueError from exc
            if len(member_signatures) != len(members):
                raise ValueError
            runs.append(
                _PrivateShadowRun(
                    run_id,
                    _load_private_package(
                        Path(package_root), synthetic=True, longitudinal_minimum=policy.longitudinal_min_observations
                    ),
                    member_signatures,
                )
            )
            run_ids.add(run_id)
    except (OSError, RecursionError, TypeError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("privacy shadow manifest is invalid") from exc
    return tuple(runs)


def _evaluate_membership_inference_control(
    policy: PrivacyPolicy,
    reference: _PrivatePackage,
    shadow_runs: tuple[_PrivateShadowRun, ...],
) -> PrivacyControlResult:
    """Run the fixed exact-trajectory membership screen across every supplied shadow run."""
    if not shadow_runs or len(shadow_runs) < policy.minimum_shadow_runs:
        return _unevaluable_control("membership_inference", "insufficient_shadow_runs")
    if len({run.run_id for run in shadow_runs}) != len(shadow_runs):
        return _unevaluable_control("membership_inference", "invalid_shadow_runs")
    if not _packages_have_profile_evidence(policy, reference):
        return _unevaluable_control("membership_inference", "insufficient_evidence")
    candidates: list[dict[str, int | float]] = []
    for run in shadow_runs:
        labels = tuple(
            profile._trajectory_signature in run._member_trajectory_signatures for profile in reference._profiles
        )
        positives = sum(labels)
        negatives = len(labels) - positives
        if positives < policy.minimum_evaluable_patients or negatives < policy.minimum_evaluable_patients:
            return _unevaluable_control("membership_inference", "inconsistent_shadow_labels")
        scores = tuple(profile._trajectory_signature in run._package._trajectory_signatures for profile in reference._profiles)
        true_positive = sum(label and score for label, score in zip(labels, scores, strict=True))
        false_positive = sum(not label and score for label, score in zip(labels, scores, strict=True))
        true_positive_rate = true_positive / positives
        false_positive_rate = false_positive / negatives
        match_count = sum(scores)
        candidates.append(
            {
                "evaluated_count": len(labels),
                "membership_match_rate": round(match_count / len(labels), 6),
                "membership_inference_advantage": round(max(0.0, true_positive_rate - false_positive_rate), 6),
                "_match_count": match_count,
                "_true_positive": true_positive,
                "_false_positive": false_positive,
                "_positive_count": positives,
                "_negative_count": negatives,
            }
        )
    metrics = max(
        candidates,
        key=lambda item: (item["membership_inference_advantage"], item["membership_match_rate"]),
    )
    match_count = int(metrics.pop("_match_count"))
    true_positive = int(metrics.pop("_true_positive"))
    false_positive = int(metrics.pop("_false_positive"))
    positive_count = int(metrics.pop("_positive_count"))
    negative_count = int(metrics.pop("_negative_count"))
    metrics["shadow_run_count"] = len(shadow_runs)
    reported = _with_interval(metrics, match_count, int(metrics["evaluated_count"]))
    true_positive_lower, true_positive_upper = _wilson_95_interval(true_positive, positive_count)
    false_positive_lower, false_positive_upper = _wilson_95_interval(false_positive, negative_count)
    reported["advantage_ci_lower"] = round(max(0.0, true_positive_lower - false_positive_upper), 6)
    reported["advantage_ci_upper"] = round(max(0.0, true_positive_upper - false_positive_lower), 6)
    advantage = float(reported["membership_inference_advantage"])
    if advantage > policy.thresholds["membership_inference_advantage"]:
        return PrivacyControlResult(
            "membership_inference", "FAIL", reported, "membership_inference_threshold_exceeded"
        )
    return PrivacyControlResult("membership_inference", "PASS", reported, "membership_inference_within_threshold")


def _majority_accuracy(labels: tuple[str, ...], targets: tuple[str, ...]) -> float:
    if not labels or not targets:
        raise ValueError("sensitive labels are unavailable")
    counts: dict[str, int] = {}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1
    majority = max(counts, key=lambda label: (counts[label], label))
    return round(sum(target == majority for target in targets) / len(targets), 6)


def _nonempty_sensitive_labels(package: _PrivatePackage) -> tuple[str, ...] | None:
    labels = tuple(profile._growth_dx_flag for profile in package._profiles)
    if any(label not in {"0", "1"} for label in labels):
        return None
    return tuple(label for label in labels if label is not None)


def _evaluate_attribute_disclosure_control(
    policy: PrivacyPolicy,
    reference: _PrivatePackage,
    generated: _PrivatePackage,
    *,
    heldout: _PrivatePackage | None,
) -> PrivacyControlResult:
    """Evaluate the allowlisted growth-flag attack against majority and held-out baselines."""
    required = "attribute_disclosure" in policy.required_controls
    if heldout is None and required:
        return _unevaluable_control("attribute_disclosure", "heldout_required")
    packages = (reference, generated) if heldout is None else (reference, generated, heldout)
    if not _packages_have_profile_evidence(policy, *packages):
        return _unevaluable_control("attribute_disclosure", "insufficient_evidence")
    reference_labels = _nonempty_sensitive_labels(reference)
    heldout_labels = _nonempty_sensitive_labels(heldout) if heldout is not None else ()
    if reference_labels is None or heldout_labels is None:
        return _unevaluable_control("attribute_disclosure", "inconsistent_sensitive_labels")
    reference_index: dict[str, _PrivatePatientProfile] = {}
    duplicate_reference_signatures: set[str] = set()
    for profile in reference._profiles:
        if profile._trajectory_signature in reference_index:
            duplicate_reference_signatures.add(profile._trajectory_signature)
        reference_index[profile._trajectory_signature] = profile
    generated_counts: dict[str, int] = {}
    for profile in generated._profiles:
        generated_counts[profile._trajectory_signature] = generated_counts.get(profile._trajectory_signature, 0) + 1
    pairs = tuple(
        (profile, reference_index[profile._trajectory_signature])
        for profile in generated._profiles
        if profile._trajectory_signature in reference_index
        and profile._trajectory_signature not in duplicate_reference_signatures
        and generated_counts[profile._trajectory_signature] == 1
    )
    if len(pairs) < policy.minimum_evaluable_patients:
        return _unevaluable_control("attribute_disclosure", "insufficient_evidence")
    if any(reference_profile._growth_dx_flag is None for _, reference_profile in pairs):
        return _unevaluable_control("attribute_disclosure", "inconsistent_sensitive_labels")
    targets = tuple(reference_profile._growth_dx_flag for _, reference_profile in pairs)
    # The attack only uses a generated trajectory to select a unique reference candidate.
    # The sensitive flag is read privately from that candidate, never from the generated package.
    predictions = tuple(reference_index[generated_profile._trajectory_signature]._growth_dx_flag for generated_profile, _ in pairs)
    if any(target not in {"0", "1"} or prediction not in {"0", "1"} for target, prediction in zip(targets, predictions, strict=True)):
        return _unevaluable_control("attribute_disclosure", "inconsistent_sensitive_labels")
    attack_count = sum(prediction == target for prediction, target in zip(predictions, targets, strict=True))
    attack_accuracy = round(attack_count / len(pairs), 6)
    reference_baseline = _majority_accuracy(reference_labels, targets)
    baseline = reference_baseline
    metrics: dict[str, int | float] = {
        "evaluated_count": len(pairs),
        "attribute_attack_accuracy": attack_accuracy,
        "reference_majority_accuracy": reference_baseline,
    }
    if heldout is not None:
        heldout_baseline = _majority_accuracy(heldout_labels, targets)
        metrics["heldout_count"] = len(heldout._profiles)
        metrics["heldout_majority_accuracy"] = heldout_baseline
        baseline = max(baseline, heldout_baseline)
    advantage = round(max(0.0, attack_accuracy - baseline), 6)
    metrics["attribute_disclosure_advantage"] = advantage
    reported = _with_interval(metrics, attack_count, len(pairs))
    if advantage > policy.thresholds["attribute_disclosure_advantage"]:
        return PrivacyControlResult(
            "attribute_disclosure", "FAIL", reported, "attribute_disclosure_threshold_exceeded"
        )
    return PrivacyControlResult("attribute_disclosure", "PASS", reported, "attribute_disclosure_within_threshold")


def _evaluate_composition_control(
    policy: PrivacyPolicy,
    generated: _PrivatePackage,
    prior_releases: tuple[_PrivatePackage, ...],
) -> PrivacyControlResult:
    """Compare generated trajectories only with the explicitly supplied prior synthetic releases."""
    if not prior_releases or len(prior_releases) < policy.minimum_prior_releases:
        return _unevaluable_control("composition", "insufficient_prior_releases")
    if not _packages_have_profile_evidence(policy, generated, *prior_releases):
        return _unevaluable_control("composition", "insufficient_evidence")
    prior_signatures = frozenset().union(*(package._trajectory_signatures for package in prior_releases))
    reproduction_count = sum(
        profile._trajectory_signature in prior_signatures for profile in generated._profiles
    )
    evaluated_count = len(generated._profiles)
    reproduction_rate = round(reproduction_count / evaluated_count, 6)
    metrics = _with_interval(
        {
            "evaluated_count": evaluated_count,
            "prior_release_count": len(prior_releases),
            "reproduction_count": reproduction_count,
            "composition_reproduction_rate": reproduction_rate,
        },
        reproduction_count,
        evaluated_count,
    )
    if reproduction_rate > policy.thresholds["composition_reproduction_rate"]:
        return PrivacyControlResult("composition", "FAIL", metrics, "composition_threshold_exceeded")
    return PrivacyControlResult("composition", "PASS", metrics, "composition_within_threshold")


def _control_harness_advantage(
    policy: PrivacyPolicy,
    reference: _PrivatePackage,
    control: _PrivatePackage,
    heldout: _PrivatePackage | None,
) -> tuple[int, int, float] | None:
    packages = (reference, control) if heldout is None else (reference, control, heldout)
    if not _packages_have_profile_evidence(policy, *packages):
        return None
    linkage = _linkage_candidate_metrics(
        reference, control, heldout, control._profiles, _linkage_selections(policy)
    )
    reproduction_count = sum(
        profile._trajectory_signature in reference._trajectory_signatures for profile in control._profiles
    )
    reproduction_rate = reproduction_count / len(control._profiles)
    return len(control._profiles), reproduction_count, round(
        max(float(linkage["linkage_advantage"]), reproduction_rate), 6
    )


def _evaluate_control_package(
    control_id: Literal["negative_control", "positive_control"],
    policy: PrivacyPolicy,
    reference: _PrivatePackage,
    package: _PrivatePackage | None,
    *,
    heldout: _PrivatePackage | None,
) -> PrivacyControlResult:
    if package is None:
        return _unevaluable_control(control_id, "control_package_missing")
    try:
        harness = _control_harness_advantage(policy, reference, package, heldout)
    except (ArithmeticError, TypeError, ValueError):
        return _unevaluable_control(control_id, "control_harness_unavailable")
    if harness is None:
        return _unevaluable_control(control_id, "insufficient_evidence")
    evaluated_count, reproduction_count, advantage = harness
    metric_name = f"{control_id}_advantage"
    metrics = _with_interval(
        {
            "evaluated_count": evaluated_count,
            "reproduction_count": reproduction_count,
            metric_name: advantage,
        },
        reproduction_count,
        evaluated_count,
    )
    threshold = policy.thresholds[metric_name]
    if control_id == "negative_control":
        if advantage >= threshold:
            return PrivacyControlResult(control_id, "FAIL", metrics, "negative_control_threshold_exceeded")
        return PrivacyControlResult(control_id, "PASS", metrics, "negative_control_within_threshold")
    if advantage >= threshold:
        return PrivacyControlResult(control_id, "PASS", metrics, "positive_control_detected")
    return PrivacyControlResult(control_id, "FAIL", metrics, "positive_control_not_detected")


def _evaluate_negative_control(
    policy: PrivacyPolicy,
    reference: _PrivatePackage,
    package: _PrivatePackage | None,
    *,
    heldout: _PrivatePackage | None,
) -> PrivacyControlResult:
    """Confirm the fixed harness stays below its false-alarm threshold on an independent package."""
    return _evaluate_control_package("negative_control", policy, reference, package, heldout=heldout)


def _evaluate_positive_control(
    policy: PrivacyPolicy,
    reference: _PrivatePackage,
    package: _PrivatePackage | None,
    *,
    heldout: _PrivatePackage | None,
) -> PrivacyControlResult:
    """Confirm the fixed harness detects a supplied copied or overfit package."""
    return _evaluate_control_package("positive_control", policy, reference, package, heldout=heldout)


def _synthetic_artifact_id(package_root: Path) -> str:
    """Derive a report-safe artifact identity from the synthetic descriptor only."""
    try:
        descriptor = _load_governed_descriptor(package_root / "datapackage.json")
        if descriptor.get("x-synthetic") is not True:
            raise ValueError
        _validate_descriptor_mapping(descriptor)
        name = _require_token(descriptor.get("name"), "synthetic artifact name")
        version = _require_token(descriptor.get("version"), "synthetic artifact version")
        return _require_token(f"{name}:{version}", "synthetic_artifact_id")
    except (TypeError, ValueError) as exc:
        raise ValueError("synthetic artifact identity is invalid") from exc


def _load_optional_package(
    package_root: Path | None, *, synthetic: bool, policy: PrivacyPolicy
) -> tuple[_PrivatePackage | None, bool]:
    """Return a package or an aggregate-only unavailable marker for optional evidence."""
    if package_root is None:
        return None, False
    try:
        return (
            _load_private_package(
                package_root,
                synthetic=synthetic,
                longitudinal_minimum=policy.longitudinal_min_observations,
            ),
            False,
        )
    except (OSError, TypeError, ValueError):
        return None, True


def _optional_control_result(
    control_id: str,
    unavailable: bool,
    evaluate: Any,
) -> PrivacyControlResult:
    """Keep optional malformed packages confined to their own aggregate control."""
    if unavailable:
        return _unevaluable_control(control_id, "optional_package_invalid")
    try:
        return evaluate()
    except (ArithmeticError, TypeError, ValueError):
        return _unevaluable_control(control_id, "control_evaluation_unavailable")


def _heldout_control_result(
    control_id: str, heldout_invalid: bool, evaluate: Any
) -> PrivacyControlResult:
    """Confine a supplied invalid held-out package to each dependent aggregate control."""
    if heldout_invalid:
        return _unevaluable_control(control_id, "optional_package_invalid")
    return _optional_control_result(control_id, False, evaluate)


def _decision_reasons(controls: tuple[PrivacyControlResult, ...], policy: PrivacyPolicy) -> tuple[str, ...]:
    if any(control.status == "FAIL" for control in controls):
        return ("evaluated_control_failed",)
    if any(
        control.control_id in policy.required_controls and control.status == "UNEVALUABLE"
        for control in controls
    ):
        return ("required_control_unevaluable",)
    return ("all_required_controls_passed",)


def audit_privacy(config: PrivacyRunConfig) -> PrivacyAuditResult:
    """Evaluate explicit packages privately and return only canonical aggregate evidence."""
    if not isinstance(config, PrivacyRunConfig):
        raise TypeError("config must be a PrivacyRunConfig")
    try:
        return _audit_privacy(config)
    except (KeyError, duckdb.Error, OSError, RecursionError, TypeError, UnicodeError, ValueError):
        raise ValueError("privacy audit inputs invalid") from None


def _audit_privacy(config: PrivacyRunConfig) -> PrivacyAuditResult:
    """Perform one private evaluation after the public boundary has validated the call."""
    policy = load_privacy_policy(config.policy)
    synthetic_artifact_id = _synthetic_artifact_id(config.synthetic_root)
    reference = _load_private_package(
        config.real_root, synthetic=False, longitudinal_minimum=policy.longitudinal_min_observations
    )
    generated = _load_private_package(
        config.synthetic_root, synthetic=True, longitudinal_minimum=policy.longitudinal_min_observations
    )
    heldout, heldout_invalid = _load_optional_package(
        config.heldout_root, synthetic=False, policy=policy
    )
    prior_releases: list[_PrivatePackage] = []
    prior_invalid = False
    for root in config.prior_release_roots:
        package, invalid = _load_optional_package(root, synthetic=True, policy=policy)
        prior_invalid = prior_invalid or invalid
        if package is not None:
            prior_releases.append(package)
    negative, negative_invalid = _load_optional_package(
        config.negative_control_root, synthetic=True, policy=policy
    )
    positive, positive_invalid = _load_optional_package(
        config.positive_control_root, synthetic=True, policy=policy
    )
    shadow_runs: tuple[_PrivateShadowRun, ...] = ()
    shadow_invalid = False
    if config.shadow_manifest is not None:
        try:
            shadow_runs = _load_private_shadow_runs(config.shadow_manifest, reference, policy)
        except (OSError, TypeError, ValueError):
            shadow_invalid = True

    controls = (
        _evaluate_identifier_overlap_control(policy, reference, generated),
        _evaluate_exact_reproduction_control(policy, reference, generated),
        _heldout_control_result(
            "nearest_neighbor",
            heldout_invalid,
            lambda: _evaluate_nearest_neighbor_control(policy, reference, generated, heldout=heldout),
        ),
        _heldout_control_result(
            "linkage",
            heldout_invalid,
            lambda: _evaluate_linkage_control(policy, reference, generated, heldout=heldout),
        ),
        _optional_control_result(
            "membership_inference",
            shadow_invalid,
            lambda: _evaluate_membership_inference_control(policy, reference, shadow_runs),
        ),
        _heldout_control_result(
            "attribute_disclosure",
            heldout_invalid,
            lambda: _evaluate_attribute_disclosure_control(policy, reference, generated, heldout=heldout),
        ),
        _optional_control_result(
            "composition",
            prior_invalid,
            lambda: _evaluate_composition_control(policy, generated, tuple(prior_releases)),
        ),
        _optional_control_result(
            "negative_control",
            heldout_invalid or negative_invalid,
            lambda: _evaluate_negative_control(policy, reference, negative, heldout=heldout),
        ),
        _optional_control_result(
            "positive_control",
            heldout_invalid or positive_invalid,
            lambda: _evaluate_positive_control(policy, reference, positive, heldout=heldout),
        ),
    )
    sorted_controls = tuple(sorted(controls, key=lambda control: control.control_id))
    status: Literal["PASS", "FAIL", "UNEVALUABLE"]
    if any(control.status == "FAIL" for control in sorted_controls):
        status = "FAIL"
    elif any(
        control.control_id in policy.required_controls and control.status == "UNEVALUABLE"
        for control in sorted_controls
    ):
        status = "UNEVALUABLE"
    else:
        status = "PASS"
    counts = {name: sum(control.status == name for control in sorted_controls) for name in _STATUSES}
    return PrivacyAuditResult(
        PrivacyAuditReport(
            status=status,
            policy=policy,
            schema_fingerprint=policy.schema_fingerprint,
            synthetic_artifact_id=synthetic_artifact_id,
            control_counts=counts,
            controls=sorted_controls,
            decision_reasons=_decision_reasons(sorted_controls, policy),
        )
    )


def _privacy_human_summary(report: PrivacyAuditReport) -> str:
    return "\n".join(
        (
            f"status: {report.status}",
            f"policy: {report.policy.policy_id} {report.policy.policy_version}",
            f"synthetic artifact: {report.synthetic_artifact_id}",
            "control counts: " + " ".join(
                f"{status}={report.control_counts[status]}" for status in sorted(_STATUSES)
            ),
            "decision reasons: " + " ".join(report.decision_reasons),
        )
    ) + "\n"


def _write_exclusive_fsynced(path: Path, payload: bytes) -> None:
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600
    )
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("privacy output write did not progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _reparse_written_privacy_report(run: RunDirectory, result: PrivacyAuditResult) -> None:
    report_bytes = _read_regular_bytes(
        run.partial_path / _PRIVACY_REPORT_FILENAME, "privacy report output", MAX_PRIVACY_POLICY_BYTES
    )
    summary_bytes = _read_regular_bytes(
        run.partial_path / _PRIVACY_SUMMARY_FILENAME, "privacy summary output", MAX_PRIVACY_POLICY_BYTES
    )
    try:
        parsed = json.loads(
            report_bytes.decode("ascii"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonfinite_json,
        )
        summary_bytes.decode("ascii")
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise ValueError("privacy output cannot be reparsed") from exc
    expected_report = result.report.canonical_json_bytes()
    expected_summary = _privacy_human_summary(result.report).encode("ascii")
    if (
        not isinstance(parsed, Mapping)
        or dict(parsed) != result.report.to_mapping()
        or report_bytes != expected_report
        or summary_bytes != expected_summary
    ):
        raise ValueError("privacy output is not canonical")


def _privacy_lifecycle_token(report: PrivacyAuditReport) -> str:
    identity = f"{report.synthetic_artifact_id}:{report.policy.policy_id}:{report.policy.policy_version}"
    return hashlib.sha256(identity.encode("ascii")).hexdigest()


def _refuse_privacy_lifecycle_collision(output: Path, report: PrivacyAuditReport) -> None:
    if os.path.lexists(output):
        raise FileExistsError("privacy output already exists")
    absolute = Path(os.path.abspath(output))
    token = _privacy_lifecycle_token(report)
    lifecycle_paths = (
        absolute.parent / f".{absolute.name}.{token}.partial",
        absolute.parent / f".{absolute.name}.{token}.failed",
    )
    if any(os.path.lexists(path) for path in lifecycle_paths):
        raise FileExistsError("privacy output lifecycle path already exists")


def _prepare_privacy_failure_archive(run: RunDirectory) -> None:
    for filename in (_PRIVACY_REPORT_FILENAME, _PRIVACY_SUMMARY_FILENAME):
        try:
            os.unlink(run.partial_path / filename)
        except FileNotFoundError:
            continue
    with os.scandir(run.partial_path) as entries:
        if next(entries, None) is not None:
            raise OSError("privacy partial output could not be cleared")


def write_privacy_report(result: PrivacyAuditResult, output: Path) -> None:
    """Write only a canonical aggregate report and summary, then promote without replacement."""
    if not isinstance(result, PrivacyAuditResult):
        raise TypeError("result must be a PrivacyAuditResult")
    if not isinstance(output, Path):
        raise TypeError("output must be a Path")
    try:
        _refuse_privacy_lifecycle_collision(output, result.report)
        run = RunDirectory.start(output, _privacy_lifecycle_token(result.report))
    except FileExistsError:
        raise FileExistsError("privacy output lifecycle collision") from None
    except (OSError, TypeError, ValueError):
        raise ValueError("privacy output initialization failed") from None
    try:
        _write_exclusive_fsynced(
            run.partial_path / _PRIVACY_REPORT_FILENAME, result.report.canonical_json_bytes()
        )
        _write_exclusive_fsynced(
            run.partial_path / _PRIVACY_SUMMARY_FILENAME,
            _privacy_human_summary(result.report).encode("ascii"),
        )
        _reparse_written_privacy_report(run, result)
        run.promote()
    except Exception:  # noqa: BLE001 - output errors are always redacted and non-promoting
        try:
            _prepare_privacy_failure_archive(run)
            run.fail("privacy output validation failed")
        except Exception:  # noqa: BLE001 - lifecycle errors must not disclose governed details
            raise ValueError("privacy output could not be promoted") from None
        raise ValueError("privacy output could not be promoted") from None


class _RedactedArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        self.exit(2, "privacy audit arguments invalid\n")


def _argument_parser() -> argparse.ArgumentParser:
    parser = _RedactedArgumentParser(description="Run governed privacy audit")
    parser.add_argument("--real-root", required=True, type=Path)
    parser.add_argument("--synthetic-root", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--heldout-root", type=Path)
    parser.add_argument("--shadow-manifest", type=Path)
    parser.add_argument("--prior-release-root", action="append", type=Path, default=[])
    parser.add_argument("--negative-control-root", type=Path)
    parser.add_argument("--positive-control-root", type=Path)
    return parser


def main() -> None:
    """Run the explicit-input privacy auditor with redacted command-line failures."""
    parser = _argument_parser()
    arguments = parser.parse_args()
    try:
        config = PrivacyRunConfig(
            real_root=arguments.real_root,
            synthetic_root=arguments.synthetic_root,
            policy=arguments.policy,
            output=arguments.output,
            heldout_root=arguments.heldout_root,
            shadow_manifest=arguments.shadow_manifest,
            prior_release_roots=tuple(arguments.prior_release_root),
            negative_control_root=arguments.negative_control_root,
            positive_control_root=arguments.positive_control_root,
        )
        result = audit_privacy(config)
        write_privacy_report(result, config.output)
    except Exception:  # noqa: BLE001 - all governed failure details remain process-local
        parser.exit(1, "privacy audit failed\n")
    if result.report.status != "PASS":
        parser.exit(1, "privacy audit failed\n")


if __name__ == "__main__":  # pragma: no cover - subprocess exercises the CLI
    main()
