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
DERIVATION_BINDING_CHECK_NAMES = (
    "contract",
    "schema_contract",
    "oracle_identity",
    "reference_standard",
    "golden_coverage",
    "parity_evidence",
    "synthetic_fuzz_evidence",
    "review",
    "classification",
)
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


_EVALUATION_STATUSES = {
    DerivationBindingStatus.PASS,
    DerivationBindingStatus.FAIL,
    DerivationBindingStatus.UNEVALUABLE,
}
_CHECK_REASON_CODES = {"OK", "MISSING_EVIDENCE", "OUTSIDE_POLICY", "STRUCTURAL_INVALID"}


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


def _status(value: object, allowed: set[str], field: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{field} has an invalid status")
    return value


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
    parity_status: str
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
        if not isinstance(self.parity_status, str) or self.parity_status not in {"PASS", "FAIL", "UNEVALUABLE"}:
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
    status: str

    def __post_init__(self) -> None:
        _optional_token(self.review_id, "review_id")
        _digest(self.review_fingerprint, "review_fingerprint", nullable=True)
        if self.reviewed_at is not None:
            _timestamp(self.reviewed_at, "reviewed_at")
        _optional_token(self.reviewer_role, "reviewer_role")
        if not isinstance(self.status, str) or self.status not in {"PENDING", "APPROVED", "REJECTED"}:
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


def _is_token(value: object) -> bool:
    return isinstance(value, str) and _TOKEN.fullmatch(value) is not None and not any(
        word in value.lower() for word in _UNSAFE
    )


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _is_timestamp(value: object) -> bool:
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def _is_count(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def _safe_token_or_none(value: object) -> str | None:
    return value if _is_token(value) else None


@dataclass(frozen=True)
class DerivationBindingCheck:
    """One aggregate-only evaluation result for a fixed binding check."""

    name: str
    status: DerivationBindingStatus
    reason_code: str
    compared_count: int | None
    mismatch_count: int | None

    def __post_init__(self) -> None:
        if self.name not in DERIVATION_BINDING_CHECK_NAMES:
            raise ValueError("check name is fixed")
        if self.status not in _EVALUATION_STATUSES:
            raise ValueError("check status is invalid")
        if self.reason_code not in _CHECK_REASON_CODES:
            raise ValueError("check reason_code is invalid")
        if self.status is DerivationBindingStatus.UNEVALUABLE:
            if self.compared_count is not None or self.mismatch_count is not None:
                raise ValueError("unevaluable check counts must be absent")
            if self.reason_code != "MISSING_EVIDENCE":
                raise ValueError("unevaluable check reason_code is invalid")
            return
        _count(self.compared_count, "compared_count")
        _count(self.mismatch_count, "mismatch_count")
        if self.mismatch_count > self.compared_count:
            raise ValueError("mismatch_count cannot exceed compared_count")
        if self.status is DerivationBindingStatus.PASS:
            if self.reason_code != "OK" or self.mismatch_count != 0:
                raise ValueError("passing check must have no mismatches")
        elif self.reason_code not in {"OUTSIDE_POLICY", "STRUCTURAL_INVALID"} or self.mismatch_count == 0:
            raise ValueError("failing check must have a positive policy or structural mismatch")

    def to_mapping(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status.value,
            "reason_code": self.reason_code,
            "compared_count": self.compared_count,
            "mismatch_count": self.mismatch_count,
        }


@dataclass(frozen=True)
class DerivationBindingReport:
    """Fixed aggregate report that never serializes evidence contents."""

    binding_version: str
    binding_id: str
    schema_fingerprint: str
    oracle_id: str | None
    reference_standard_id: str | None
    parity_report_id: str | None
    status: DerivationBindingStatus
    status_counts: Mapping[str, int]
    checks: tuple[DerivationBindingCheck, ...]

    def __post_init__(self) -> None:
        if self.binding_version != DERIVATION_BINDING_VERSION:
            raise ValueError("binding_version is fixed")
        _token(self.binding_id, "binding_id")
        _digest(self.schema_fingerprint, "schema_fingerprint")
        for name in ("oracle_id", "reference_standard_id", "parity_report_id"):
            _optional_token(getattr(self, name), name)
        if self.status not in _EVALUATION_STATUSES:
            raise ValueError("report status is invalid")
        if not isinstance(self.checks, tuple) or len(self.checks) != len(DERIVATION_BINDING_CHECK_NAMES):
            raise ValueError("report checks are fixed")
        if tuple(check.name for check in self.checks) != DERIVATION_BINDING_CHECK_NAMES:
            raise ValueError("report check order is fixed")
        if not all(isinstance(check, DerivationBindingCheck) for check in self.checks):
            raise TypeError("report checks are invalid")
        counts = _mapping(self.status_counts, "status_counts")
        _keys(counts, {"PASS", "FAIL", "UNEVALUABLE"}, "status_counts")
        for value in counts.values():
            _count(value, "status_counts")
        computed = {name: sum(check.status.value == name for check in self.checks) for name in counts}
        if dict(counts) != computed:
            raise ValueError("status_counts must match checks")
        computed_status = (
            DerivationBindingStatus.FAIL if computed["FAIL"] else
            DerivationBindingStatus.UNEVALUABLE if computed["UNEVALUABLE"] else
            DerivationBindingStatus.PASS
        )
        if self.status is not computed_status:
            raise ValueError("report status must match checks")
        object.__setattr__(self, "status_counts", MappingProxyType(dict(counts)))

    def to_mapping(self) -> dict[str, object]:
        return {
            "binding_version": self.binding_version,
            "binding_id": self.binding_id,
            "schema_fingerprint": self.schema_fingerprint,
            "oracle_id": self.oracle_id,
            "reference_standard_id": self.reference_standard_id,
            "parity_report_id": self.parity_report_id,
            "status": self.status.value,
            "status_counts": dict(self.status_counts),
            "checks": [check.to_mapping() for check in self.checks],
        }

    def to_json_bytes(self) -> bytes:
        return json.dumps(
            self.to_mapping(), ensure_ascii=True, separators=(",", ":"), sort_keys=True, allow_nan=False
        ).encode("ascii") + b"\n"


def _passing(name: str, compared_count: int = 1) -> DerivationBindingCheck:
    return DerivationBindingCheck(name, DerivationBindingStatus.PASS, "OK", compared_count, 0)


def _failing(name: str, reason_code: str, compared_count: int = 1) -> DerivationBindingCheck:
    return DerivationBindingCheck(name, DerivationBindingStatus.FAIL, reason_code, max(1, compared_count), 1)


def _unevaluable(name: str) -> DerivationBindingCheck:
    return DerivationBindingCheck(name, DerivationBindingStatus.UNEVALUABLE, "MISSING_EVIDENCE", None, None)


def _identity_status(values: tuple[object, ...], valid: tuple[bool, ...], name: str) -> DerivationBindingCheck:
    if any(value is None for value in values):
        return _unevaluable(name)
    if not all(valid):
        return _failing(name, "STRUCTURAL_INVALID", len(values))
    return _passing(name, len(values))


def validate_derivation_binding(
    binding: DerivationBinding, *, expected_schema_fingerprint: str
) -> DerivationBindingReport:
    """Evaluate aggregate derivation evidence without opening evidence bytes."""
    if not isinstance(binding, DerivationBinding):
        raise TypeError("binding must be a DerivationBinding")
    _digest(expected_schema_fingerprint, "expected_schema_fingerprint")

    oracle = binding.oracle
    standard = binding.reference_standard
    evidence = binding.golden_evidence
    review = binding.review

    contract = _passing("contract") if binding.binding_version == DERIVATION_BINDING_VERSION else _failing(
        "contract", "STRUCTURAL_INVALID"
    )
    schema_contract = _passing("schema_contract") if binding.schema_fingerprint == expected_schema_fingerprint else _failing(
        "schema_contract", "OUTSIDE_POLICY"
    )
    oracle_values = (
        getattr(oracle, "oracle_id", None), getattr(oracle, "implementation_fingerprint", None),
        getattr(oracle, "source_revision", None), getattr(oracle, "dependency_fingerprint", None),
        getattr(oracle, "source_kind", None),
    )
    oracle_identity = _identity_status(
        oracle_values,
        (_is_token(oracle_values[0]), _is_digest(oracle_values[1]), _is_token(oracle_values[2]),
         _is_digest(oracle_values[3]), oracle_values[4] in {"authoritative_implementation", "approved_parity_harness"}),
        "oracle_identity",
    )
    standard_values = (
        getattr(standard, "standard_id", None), getattr(standard, "standard_fingerprint", None),
        getattr(standard, "version", None),
    )
    reference_standard = _identity_status(
        standard_values,
        (_is_token(standard_values[0]), _is_digest(standard_values[1]), _is_token(standard_values[2])),
        "reference_standard",
    )

    categories = getattr(evidence, "covered_categories", None)
    count = getattr(evidence, "bidirectional_case_count", None)
    manifest_values = (getattr(evidence, "manifest_id", None), getattr(evidence, "manifest_fingerprint", None))
    if not isinstance(categories, tuple) or len(set(categories)) != len(categories) or not all(
        isinstance(category, str) for category in categories
    ):
        golden_coverage = _failing("golden_coverage", "STRUCTURAL_INVALID")
    elif set(categories) - set(REQUIRED_GOLDEN_CATEGORIES):
        golden_coverage = _failing("golden_coverage", "OUTSIDE_POLICY", len(categories))
    elif set(categories) != set(REQUIRED_GOLDEN_CATEGORIES) or not _is_count(count) or count < 7 or any(
        value is None for value in manifest_values
    ):
        golden_coverage = _unevaluable("golden_coverage")
    elif not _is_token(manifest_values[0]) or not _is_digest(manifest_values[1]):
        golden_coverage = _failing("golden_coverage", "STRUCTURAL_INVALID", count)
    else:
        golden_coverage = _passing("golden_coverage", count)

    parity_status = getattr(evidence, "parity_status", None)
    parity_values = (
        getattr(evidence, "parity_contract", None), getattr(evidence, "parity_report_id", None),
        getattr(evidence, "parity_report_fingerprint", None),
        getattr(evidence, "candidate_implementation_fingerprint", None),
        getattr(evidence, "reference_implementation_fingerprint", None),
        getattr(evidence, "parity_schema_fingerprint", None),
    )
    parity_identities_valid = (
        (parity_values[0] is None or parity_values[0] == "derivation-parity-v1") and
        (parity_values[1] is None or _is_token(parity_values[1])) and
        all(value is None or _is_digest(value) for value in parity_values[2:])
    )
    parity_identity_mismatch = (
        parity_values[3] is not None and parity_values[3] != oracle_values[1]
    ) or (parity_values[5] is not None and parity_values[5] != binding.schema_fingerprint)
    if parity_status == "FAIL":
        parity_evidence = _failing("parity_evidence", "OUTSIDE_POLICY")
    elif parity_status not in {"PASS", "UNEVALUABLE"} or not parity_identities_valid:
        parity_evidence = _failing("parity_evidence", "STRUCTURAL_INVALID")
    elif parity_identity_mismatch:
        parity_evidence = _failing("parity_evidence", "OUTSIDE_POLICY")
    elif parity_status == "PASS" and any(value is None for value in parity_values):
        parity_evidence = _failing("parity_evidence", "STRUCTURAL_INVALID")
    elif parity_status == "UNEVALUABLE" or any(value is None for value in parity_values):
        parity_evidence = _unevaluable("parity_evidence")
    else:
        parity_evidence = _passing("parity_evidence")

    fuzz_count = getattr(evidence, "synthetic_fuzz_case_count", None)
    fuzz_fingerprint = getattr(evidence, "fuzz_corpus_fingerprint", None)
    if fuzz_count is None:
        synthetic_fuzz_evidence = _unevaluable("synthetic_fuzz_evidence")
    elif not _is_count(fuzz_count):
        synthetic_fuzz_evidence = _failing("synthetic_fuzz_evidence", "STRUCTURAL_INVALID")
    elif fuzz_count == 0:
        synthetic_fuzz_evidence = _unevaluable("synthetic_fuzz_evidence")
    elif fuzz_fingerprint is None or not _is_digest(fuzz_fingerprint):
        synthetic_fuzz_evidence = _failing("synthetic_fuzz_evidence", "STRUCTURAL_INVALID", fuzz_count)
    else:
        synthetic_fuzz_evidence = _passing("synthetic_fuzz_evidence", fuzz_count)

    review_status = getattr(review, "status", None)
    review_values = (
        getattr(review, "review_id", None), getattr(review, "review_fingerprint", None),
        getattr(review, "reviewed_at", None), getattr(review, "reviewer_role", None),
    )
    complete_review = all(value is not None for value in review_values)
    if review_status == "REJECTED":
        review_check = _failing("review", "OUTSIDE_POLICY")
    elif review_status == "PENDING" and not complete_review:
        review_check = _unevaluable("review")
    elif review_status == "PENDING":
        review_check = _unevaluable("review") if binding.test_only else _failing("review", "OUTSIDE_POLICY")
    elif review_status != "APPROVED":
        review_check = _failing("review", "STRUCTURAL_INVALID")
    elif not complete_review:
        review_check = _unevaluable("review")
    elif not (_is_token(review_values[0]) and _is_digest(review_values[1]) and _is_timestamp(review_values[2]) and _is_token(review_values[3])):
        review_check = _failing("review", "STRUCTURAL_INVALID")
    else:
        review_check = _passing("review", len(review_values))

    prior_checks = (
        contract, schema_contract, oracle_identity, reference_standard, golden_coverage, parity_evidence,
        synthetic_fuzz_evidence, review_check,
    )
    if binding.test_only:
        classification = _failing("classification", "OUTSIDE_POLICY") if any(
            check.status is DerivationBindingStatus.FAIL for check in prior_checks
        ) else _passing("classification")
    elif any(check.status is DerivationBindingStatus.FAIL for check in prior_checks):
        classification = _failing("classification", "OUTSIDE_POLICY")
    elif any(check.status is DerivationBindingStatus.UNEVALUABLE for check in prior_checks):
        classification = _unevaluable("classification")
    else:
        classification = _passing("classification")

    checks = (*prior_checks, classification)
    status_counts = {status.value: sum(check.status is status for check in checks) for status in _EVALUATION_STATUSES}
    status = (
        DerivationBindingStatus.FAIL if status_counts["FAIL"] else
        DerivationBindingStatus.UNEVALUABLE if status_counts["UNEVALUABLE"] else
        DerivationBindingStatus.PASS
    )
    return DerivationBindingReport(
        DERIVATION_BINDING_VERSION,
        binding.binding_id,
        binding.schema_fingerprint,
        _safe_token_or_none(oracle_values[0]) if oracle_identity.status is not DerivationBindingStatus.UNEVALUABLE else None,
        _safe_token_or_none(standard_values[0]) if reference_standard.status is not DerivationBindingStatus.UNEVALUABLE else None,
        _safe_token_or_none(parity_values[1]) if parity_evidence.status is not DerivationBindingStatus.UNEVALUABLE else None,
        status,
        status_counts,
        checks,
    )


def require_approved_derivation_binding(
    binding: DerivationBinding, *, expected_schema_fingerprint: str
) -> None:
    """Require a complete, non-test binding with approved parity and review evidence."""
    report = validate_derivation_binding(binding, expected_schema_fingerprint=expected_schema_fingerprint)
    evidence = binding.golden_evidence
    approved = (
        report.status is DerivationBindingStatus.PASS and
        not binding.test_only and
        evidence.parity_status == "PASS" and
        binding.review.status == "APPROVED" and
        evidence.candidate_implementation_fingerprint == binding.oracle.implementation_fingerprint and
        evidence.parity_schema_fingerprint == binding.schema_fingerprint and
        binding.schema_fingerprint == expected_schema_fingerprint
    )
    if not approved:
        raise DerivationBindingUnavailable()
