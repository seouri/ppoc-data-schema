"""Strict, immutable aggregate identity for derivation evidence."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from types import MappingProxyType

DERIVATION_BINDING_VERSION = "derivation-binding-v1"
REQUIRED_GOLDEN_CATEGORIES = (
    "filter_order", "age_boundaries", "missingness", "harrall_outlier",
    "biv_filtering", "velocity_variants", "rounding",
)
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
_UNSAFE = ("patient", "visit", "row", "record", "path", "source", "raw", "table", "column",
           "truth", "hidden", "internal", "secret", "private")


class DerivationBindingUnavailable(RuntimeError):
    """Raised when the binding cannot be supplied."""

    def __init__(self, *_: object) -> None:
        super().__init__("derivation binding is unavailable")


class DerivationBindingStatus(Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PASS = "PASS"
    FAIL = "FAIL"
    UNEVALUABLE = "UNEVALUABLE"


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field} must be a mapping")
    return MappingProxyType(dict(value))


def _keys(value: Mapping[str, object], expected: set[str], field: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{field} keys are fixed")
    if any(not isinstance(key, str) for key in value):
        raise TypeError(f"{field} keys must be strings")


def _token(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a bounded aggregate-safe token")
    if _TOKEN.fullmatch(value) is None or any(word in value.lower() for word in _UNSAFE):
        raise ValueError(f"{field} must be a bounded aggregate-safe token")
    return value


def _digest(value: object, field: str, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise ValueError(f"{field} must be lowercase SHA-256 hex")
    return value


def _count(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return value


def _optional_token(value: object, field: str) -> str | None:
    return None if value is None else _token(value, field)


def _status(value: object, allowed: set[str], field: str) -> DerivationBindingStatus:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{field} has an invalid status")
    return DerivationBindingStatus(value)


def _timestamp(value: object, field: str) -> str:
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        raise ValueError(f"{field} must be an exact UTC timestamp")
    try:
        datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an exact UTC timestamp") from error
    return value


@dataclass(frozen=True)
class DerivationBindingOracle:
    oracle_id: str
    implementation_fingerprint: str
    source_revision: str
    dependency_fingerprint: str
    source_kind: str

    def __post_init__(self) -> None:
        _token(self.oracle_id, "oracle_id")
        _digest(self.implementation_fingerprint, "implementation_fingerprint")
        _token(self.source_revision, "source_revision")
        _digest(self.dependency_fingerprint, "dependency_fingerprint")
        if self.source_kind not in {"authoritative_implementation", "approved_parity_harness"}:
            raise ValueError("source_kind has an invalid value")


@dataclass(frozen=True)
class DerivationReferenceStandard:
    standard_id: str
    standard_fingerprint: str
    version: str

    def __post_init__(self) -> None:
        _token(self.standard_id, "standard_id")
        _digest(self.standard_fingerprint, "standard_fingerprint")
        _token(self.version, "version")


@dataclass(frozen=True)
class DerivationGoldenEvidence:
    manifest_id: str | None
    manifest_fingerprint: str | None
    parity_contract: str | None
    parity_report_id: str | None
    parity_report_fingerprint: str | None
    parity_status: DerivationBindingStatus
    candidate_implementation_fingerprint: str | None
    reference_implementation_fingerprint: str | None
    parity_schema_fingerprint: str | None
    covered_categories: tuple[str, ...]
    bidirectional_case_count: int
    synthetic_fuzz_case_count: int
    fuzz_corpus_fingerprint: str | None

    def __post_init__(self) -> None:
        for name in ("manifest_id", "parity_contract", "parity_report_id"):
            _optional_token(getattr(self, name), name)
        for name in ("manifest_fingerprint", "parity_report_fingerprint", "candidate_implementation_fingerprint",
                     "reference_implementation_fingerprint", "parity_schema_fingerprint", "fuzz_corpus_fingerprint"):
            _digest(getattr(self, name), name, nullable=True)
        if not isinstance(self.parity_status, DerivationBindingStatus) or self.parity_status.value not in {"PASS", "FAIL", "UNEVALUABLE"}:
            raise ValueError("parity_status has an invalid status")
        if not isinstance(self.covered_categories, tuple) or len(set(self.covered_categories)) != len(self.covered_categories) or set(self.covered_categories) != set(REQUIRED_GOLDEN_CATEGORIES):
            raise ValueError("covered_categories must contain required categories exactly once")
        for category in self.covered_categories:
            _token(category, "covered_categories")
        _count(self.bidirectional_case_count, "bidirectional_case_count")
        _count(self.synthetic_fuzz_case_count, "synthetic_fuzz_case_count")


@dataclass(frozen=True)
class DerivationReview:
    review_id: str | None
    review_fingerprint: str | None
    reviewed_at: str | None
    reviewer_role: str | None
    status: DerivationBindingStatus

    def __post_init__(self) -> None:
        _optional_token(self.review_id, "review_id")
        _digest(self.review_fingerprint, "review_fingerprint", nullable=True)
        if self.reviewed_at is not None:
            _timestamp(self.reviewed_at, "reviewed_at")
        _optional_token(self.reviewer_role, "reviewer_role")
        if not isinstance(self.status, DerivationBindingStatus) or self.status.value not in {"PENDING", "APPROVED", "REJECTED"}:
            raise ValueError("status has an invalid status")


@dataclass(frozen=True)
class DerivationBinding:
    binding_version: str
    binding_id: str
    schema_fingerprint: str
    oracle: DerivationBindingOracle
    reference_standard: DerivationReferenceStandard
    golden_evidence: DerivationGoldenEvidence
    review: DerivationReview
    test_only: bool

    def __post_init__(self) -> None:
        if self.binding_version != DERIVATION_BINDING_VERSION:
            raise ValueError("binding_version is fixed")
        _token(self.binding_id, "binding_id")
        _digest(self.schema_fingerprint, "schema_fingerprint")
        if not isinstance(self.oracle, DerivationBindingOracle) or not isinstance(self.reference_standard, DerivationReferenceStandard) or not isinstance(self.golden_evidence, DerivationGoldenEvidence) or not isinstance(self.review, DerivationReview):
            raise TypeError("invalid binding identities")
        if not isinstance(self.test_only, bool):
            raise TypeError("test_only must be a boolean")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> DerivationBinding:
        root = _mapping(value, "binding")
        _keys(root, {"binding_version", "binding_id", "schema_fingerprint", "oracle", "reference_standard", "golden_evidence", "review", "test_only"}, "binding")
        oracle = _mapping(root["oracle"], "oracle")
        _keys(oracle, {"oracle_id", "implementation_fingerprint", "source_revision", "dependency_fingerprint", "source_kind"}, "oracle")
        standard = _mapping(root["reference_standard"], "reference_standard")
        _keys(standard, {"standard_id", "standard_fingerprint", "version"}, "reference_standard")
        golden = _mapping(root["golden_evidence"], "golden_evidence")
        _keys(golden, {"manifest_id", "manifest_fingerprint", "parity_contract", "parity_report_id", "parity_report_fingerprint", "parity_status", "candidate_implementation_fingerprint", "reference_implementation_fingerprint", "parity_schema_fingerprint", "covered_categories", "bidirectional_case_count", "synthetic_fuzz_case_count", "fuzz_corpus_fingerprint"}, "golden_evidence")
        review = _mapping(root["review"], "review")
        _keys(review, {"review_id", "review_fingerprint", "reviewed_at", "reviewer_role", "status"}, "review")
        categories = golden["covered_categories"]
        if not isinstance(categories, (list, tuple)):
            raise TypeError("covered_categories must be a sequence")
        return cls(root["binding_version"], root["binding_id"], root["schema_fingerprint"],
                   DerivationBindingOracle(**dict(oracle)), DerivationReferenceStandard(**dict(standard)),
                   DerivationGoldenEvidence(**{**dict(golden), "parity_status": _status(golden["parity_status"], {"PASS", "FAIL", "UNEVALUABLE"}, "parity_status"), "covered_categories": tuple(categories)}),
                   DerivationReview(**{**dict(review), "status": _status(review["status"], {"PENDING", "APPROVED", "REJECTED"}, "status")}), root["test_only"])

    @classmethod
    def from_json_bytes(cls, value: bytes) -> DerivationBinding:
        def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, item in pairs:
                if key in result:
                    raise ValueError("duplicate JSON object key")
                result[key] = item
            return result

        def reject_constant(value: str) -> None:
            raise ValueError("nonfinite JSON number")

        parsed = json.loads(value.decode("ascii"), object_pairs_hook=reject_duplicates, parse_constant=reject_constant)
        return cls.from_mapping(parsed)

    def to_mapping(self) -> dict[str, object]:
        def values(obj: object) -> dict[str, object]:
            return {field: getattr(obj, field).value if isinstance(getattr(obj, field), Enum) else getattr(obj, field) for field in obj.__dataclass_fields__}
        result = values(self)
        result["oracle"] = values(self.oracle)
        result["reference_standard"] = values(self.reference_standard)
        result["golden_evidence"] = values(self.golden_evidence)
        result["golden_evidence"]["covered_categories"] = list(self.golden_evidence.covered_categories)
        result["review"] = values(self.review)
        return result

    def to_json_bytes(self) -> bytes:
        return json.dumps(self.to_mapping(), ensure_ascii=True, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("ascii") + b"\n"
