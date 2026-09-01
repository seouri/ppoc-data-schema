"""Immutable, aggregate-only contracts for derivation parity evaluation."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

DERIVATION_PARITY_VERSION = "derivation-parity-v1"
DERIVATION_PARITY_CHECK_NAMES = (
    "schema_contract", "base_shape", "candidate_shape", "reference_shape",
    "patient_key_alignment", "visit_key_alignment", "patient_identity_projection",
    "visit_identity_projection", "deterministic_age_conversion",
    "deterministic_unit_conversion", "deterministic_bmi",
    "deterministic_patient_summaries", "clinical_flag_relationships",
    "reference_field_parity", "support",
)
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_TOLERANCE_CAP = 1_000_000.0
_REASONS = MappingProxyType({
    "PASS": frozenset({"OK", "WITHIN_TOLERANCE"}),
    "FAIL": frozenset({"OUTSIDE_TOLERANCE", "STRUCTURAL_INVALID"}),
    "UNEVALUABLE": frozenset({"INSUFFICIENT_SUPPORT", "MISSING_EVIDENCE"}),
})
DERIVATION_PARITY_REASON_CODES = frozenset(code for codes in _REASONS.values() for code in codes)


class DerivationParityUnavailable(RuntimeError):
    """Raised when parity cannot be evaluated."""

    _MESSAGE = "derivation parity evaluation is unavailable"

    def __init__(self, *_: object) -> None:
        super().__init__(self._MESSAGE)


class DerivationParityStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNEVALUABLE = "UNEVALUABLE"


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or _SAFE_TOKEN.fullmatch(value) is None:
        raise ValueError(f"{field} must be a bounded aggregate-safe token")
    lowered = value.lower()
    if any(word in lowered for word in ("patient", "visit", "row", "path", "source", "truth", "/", "\\")):
        raise ValueError(f"{field} contains unsafe material")
    return value


def _finite(value: object, field: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or (nonnegative and result < 0) or result >= _TOLERANCE_CAP:
        raise ValueError(f"{field} is outside the permitted range")
    return result


def _count(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return value


@dataclass(frozen=True)
class DerivationImplementation:
    implementation_id: str
    fingerprint: str
    test_only: bool

    def __post_init__(self) -> None:
        _token(self.implementation_id, "implementation_id")
        if not isinstance(self.fingerprint, str) or _SHA256.fullmatch(self.fingerprint) is None:
            raise ValueError("fingerprint must be lowercase SHA-256 hex")
        if not isinstance(self.test_only, bool):
            raise TypeError("test_only must be a boolean")

    def to_mapping(self) -> dict[str, object]:
        return {"implementation_id": self.implementation_id, "fingerprint": self.fingerprint, "test_only": self.test_only}

    def __repr__(self) -> str:
        return "DerivationImplementation(<aggregate-safe>)"


@dataclass(frozen=True)
class DerivationParityPolicy:
    policy_id: str
    policy_version: str
    minimum_patient_rows: int
    minimum_visit_rows: int
    deterministic_tolerance: float
    reference_tolerance: float

    def __post_init__(self) -> None:
        _token(self.policy_id, "policy_id")
        _token(self.policy_version, "policy_version")
        if not isinstance(self.minimum_patient_rows, int) or isinstance(self.minimum_patient_rows, bool) or self.minimum_patient_rows < 1:
            raise ValueError("minimum_patient_rows must be at least one")
        if not isinstance(self.minimum_visit_rows, int) or isinstance(self.minimum_visit_rows, bool) or self.minimum_visit_rows < 1:
            raise ValueError("minimum_visit_rows must be at least one")
        object.__setattr__(self, "deterministic_tolerance", _finite(self.deterministic_tolerance, "deterministic_tolerance", nonnegative=True))
        object.__setattr__(self, "reference_tolerance", _finite(self.reference_tolerance, "reference_tolerance", nonnegative=True))

    def to_mapping(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "minimum_patient_rows": self.minimum_patient_rows,
            "minimum_visit_rows": self.minimum_visit_rows,
            "deterministic_tolerance": self.deterministic_tolerance,
            "reference_tolerance": self.reference_tolerance,
        }

    def __repr__(self) -> str:
        return "DerivationParityPolicy(<aggregate-safe>)"


@dataclass(frozen=True, init=False)
class DerivationParityCheck:
    name: str
    status: DerivationParityStatus
    reason_code: str
    compared_count: int | None
    mismatch_count: int | None
    maximum_absolute_difference: float | None

    def __init__(self, name: str, status: DerivationParityStatus, reason_code: str,
                 compared_count: int | None, mismatch_count: int | None,
                 maximum_absolute_difference: float | None, **kwargs: object) -> None:
        if kwargs:
            raise TypeError("unknown check fields")
        if name not in DERIVATION_PARITY_CHECK_NAMES:
            raise ValueError("unknown check name")
        if not isinstance(status, DerivationParityStatus):
            raise TypeError("status must be a DerivationParityStatus")
        if reason_code not in _REASONS[status.value]:
            raise ValueError("reason_code is incompatible with status")
        if status is DerivationParityStatus.UNEVALUABLE:
            compared_count = mismatch_count = None
            maximum_absolute_difference = None
        else:
            if compared_count is None or mismatch_count is None:
                raise ValueError("evaluable checks require counts")
            _count(compared_count, "compared_count")
            _count(mismatch_count, "mismatch_count")
            if mismatch_count > compared_count:
                raise ValueError("mismatch_count exceeds compared_count")
            if maximum_absolute_difference is None:
                raise ValueError("evaluable checks require maximum difference")
            maximum_absolute_difference = _finite(maximum_absolute_difference, "maximum_absolute_difference", nonnegative=True)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "reason_code", reason_code)
        object.__setattr__(self, "compared_count", compared_count)
        object.__setattr__(self, "mismatch_count", mismatch_count)
        object.__setattr__(self, "maximum_absolute_difference", maximum_absolute_difference)

    def to_mapping(self) -> dict[str, object]:
        return {"name": self.name, "status": self.status.value, "reason_code": self.reason_code,
                "compared_count": self.compared_count, "mismatch_count": self.mismatch_count,
                "maximum_absolute_difference": self.maximum_absolute_difference}

    def __repr__(self) -> str:
        return f"DerivationParityCheck(name={self.name!r}, status={self.status.value!r})"


@dataclass(frozen=True, init=False)
class DerivationParityReport:
    contract: str
    schema_fingerprint: str
    policy: DerivationParityPolicy
    candidate: DerivationImplementation
    reference: DerivationImplementation
    patient_row_count: int
    visit_row_count: int
    status: DerivationParityStatus
    status_counts: Mapping[str, int]
    checks: tuple[DerivationParityCheck, ...]

    def __init__(self, contract: object = None, schema_fingerprint: object = None,
                 policy: object = None, candidate: object = None,
                 reference: object = None, patient_row_count: object = None,
                 visit_row_count: object = None, status: object = None,
                 status_counts: object = None, checks: object = None,
                 **extra: object) -> None:
        values = {"contract": contract, "schema_fingerprint": schema_fingerprint,
                  "policy": policy, "candidate": candidate, "reference": reference,
                  "patient_row_count": patient_row_count, "visit_row_count": visit_row_count,
                  "status": status, "status_counts": status_counts, "checks": checks, **extra}
        expected = {"contract", "schema_fingerprint", "policy", "candidate", "reference", "patient_row_count", "visit_row_count", "status", "status_counts", "checks"}
        if set(values) != expected:
            raise ValueError("report keys are fixed")
        if values["contract"] != DERIVATION_PARITY_VERSION:
            raise ValueError("contract is fixed")
        if not isinstance(values["schema_fingerprint"], str) or _SHA256.fullmatch(values["schema_fingerprint"]) is None:
            raise ValueError("schema_fingerprint must be lowercase SHA-256 hex")
        if not isinstance(values["policy"], DerivationParityPolicy) or not isinstance(values["candidate"], DerivationImplementation) or not isinstance(values["reference"], DerivationImplementation):
            raise TypeError("invalid report identities")
        patients, visits = values["patient_row_count"], values["visit_row_count"]
        _count(patients, "patient_row_count")
        _count(visits, "visit_row_count")
        status = values["status"]
        if not isinstance(status, DerivationParityStatus):
            raise TypeError("status must be a DerivationParityStatus")
        checks = tuple(values["checks"]) if isinstance(values["checks"], Iterable) and not isinstance(values["checks"], (str, bytes, Mapping)) else ()
        if not all(isinstance(item, DerivationParityCheck) for item in checks):
            raise TypeError("checks must contain DerivationParityCheck values")
        if len(checks) != len(DERIVATION_PARITY_CHECK_NAMES) or tuple(item.name for item in checks) != DERIVATION_PARITY_CHECK_NAMES:
            raise ValueError("checks must use the fixed ordered check names")
        raw_counts = values["status_counts"]
        if not isinstance(raw_counts, Mapping) or set(raw_counts) != {"PASS", "FAIL", "UNEVALUABLE"}:
            raise ValueError("status_counts keys are fixed")
        counts = {key: _count(raw_counts[key], f"status_counts.{key}") for key in raw_counts}
        expected_counts = {key: sum(item.status.value == key for item in checks) for key in counts}
        if counts != expected_counts or status.value != max((item.status for item in checks), key=lambda item: {DerivationParityStatus.PASS: 0, DerivationParityStatus.UNEVALUABLE: 1, DerivationParityStatus.FAIL: 2}[item]).value:
            raise ValueError("status_counts or status does not match checks")
        for key, value in values.items():
            object.__setattr__(self, key, value)
        object.__setattr__(self, "checks", checks)
        object.__setattr__(self, "status_counts", MappingProxyType(counts))

    def to_mapping(self) -> dict[str, object]:
        return {"contract": self.contract, "schema_fingerprint": self.schema_fingerprint,
                "policy": self.policy.to_mapping(), "candidate": self.candidate.to_mapping(),
                "reference": self.reference.to_mapping(), "patient_row_count": self.patient_row_count,
                "visit_row_count": self.visit_row_count, "status": self.status.value,
                "status_counts": dict(self.status_counts), "checks": [item.to_mapping() for item in self.checks]}

    def to_json_bytes(self) -> bytes:
        return json.dumps(self.to_mapping(), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii") + b"\n"

    def __repr__(self) -> str:
        return f"DerivationParityReport(status={self.status.value!r}, checks={len(self.checks)})"


def validate_derivation_parity(
    base_rows: Mapping[str, Iterable[Mapping[str, object]]],
    candidate_rows: Mapping[str, Iterable[Mapping[str, object]]],
    reference_rows: Mapping[str, Iterable[Mapping[str, object]]],
    descriptor: Mapping[str, object], *, candidate: DerivationImplementation,
    reference: DerivationImplementation, policy: DerivationParityPolicy,
) -> DerivationParityReport:
    raise DerivationParityUnavailable()
