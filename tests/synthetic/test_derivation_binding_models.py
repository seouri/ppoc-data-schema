import json
from dataclasses import FrozenInstanceError, is_dataclass

import pytest

from synthetic.derivation_binding import (
    REQUIRED_GOLDEN_CATEGORIES,
    DerivationBinding,
    DerivationBindingOracle,
    DerivationBindingStatus,
    DerivationBindingUnavailable,
)

SHA = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
SHA2 = "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"


def fixture() -> dict[str, object]:
    return {
        "binding_version": "derivation-binding-v1",
        "binding_id": "binding-example-v1",
        "schema_fingerprint": SHA,
        "oracle": {"oracle_id": "oracle-example-v1", "implementation_fingerprint": SHA2,
                    "source_revision": "revision-example-v1", "dependency_fingerprint": SHA,
                    "source_kind": "authoritative_implementation"},
        "reference_standard": {"standard_id": "standard-example-v1", "standard_fingerprint": SHA2,
                                "version": "standard-version-1"},
        "golden_evidence": {"manifest_id": "golden-example-v1", "manifest_fingerprint": SHA,
                             "parity_contract": "derivation-parity-v1", "parity_report_id": "parity-report-example-v1",
                             "parity_report_fingerprint": SHA2, "parity_status": "PASS",
                             "candidate_implementation_fingerprint": SHA2,
                             "reference_implementation_fingerprint": SHA,
                             "parity_schema_fingerprint": SHA, "covered_categories": list(REQUIRED_GOLDEN_CATEGORIES),
                             "bidirectional_case_count": 7, "synthetic_fuzz_case_count": 100,
                             "fuzz_corpus_fingerprint": SHA2},
        "review": {"review_id": "review-example-v1", "review_fingerprint": SHA,
                    "reviewed_at": "2026-09-01T00:00:00Z", "reviewer_role": "data-custodian",
                    "status": "APPROVED"},
        "test_only": True,
    }


def test_valid_fixture_is_frozen_and_round_trips_without_aliasing():
    binding = DerivationBinding.from_mapping(fixture())
    assert is_dataclass(binding)
    assert isinstance(binding, DerivationBinding)
    assert isinstance(binding.oracle, DerivationBindingOracle)
    assert isinstance(binding.golden_evidence.covered_categories, tuple)
    with pytest.raises(FrozenInstanceError):
        binding.binding_id = "changed"
    result = binding.to_mapping()
    assert result == fixture()
    result["oracle"]["oracle_id"] = "changed"
    result["golden_evidence"]["covered_categories"].append("changed")
    assert binding.oracle.oracle_id == "oracle-example-v1"
    assert "changed" not in binding.golden_evidence.covered_categories


def test_canonical_json_is_sorted_compact_ascii_and_newline_terminated():
    expected = json.dumps(fixture(), ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode() + b"\n"
    assert DerivationBinding.from_mapping(fixture()).to_json_bytes() == expected


@pytest.mark.parametrize("where", ["oracle", "reference_standard", "golden_evidence", "review"])
def test_rejects_missing_and_extra_nested_keys(where):
    value = fixture()
    value[where].pop(next(iter(value[where])))
    with pytest.raises((TypeError, ValueError)):
        DerivationBinding.from_mapping(value)
    value = fixture()
    value[where]["extra"] = "nope"
    with pytest.raises((TypeError, ValueError)):
        DerivationBinding.from_mapping(value)


def test_rejects_duplicate_json_keys():
    text = json.dumps(fixture(), separators=(",", ":"))[:-1] + ',"binding_id":"duplicate"}'
    with pytest.raises(ValueError, match="duplicate"):
        DerivationBinding.from_json_bytes(text.encode())


@pytest.mark.parametrize("field,value", [
    ("binding_version", True), ("binding_id", 1), ("schema_fingerprint", None),
    ("test_only", 1), ("oracle", []), ("golden_evidence", object()),
])
def test_rejects_wrong_scalar_types(field, value):
    data = fixture()
    data[field] = value
    with pytest.raises((TypeError, ValueError)):
        DerivationBinding.from_mapping(data)


@pytest.mark.parametrize("field,value", [("schema_fingerprint", "bad"), ("binding_id", "patient-1"),
                                          ("binding_id", "../path"), ("binding_id", "row-1")])
def test_rejects_invalid_tokens_and_digests(field, value):
    data = fixture()
    data[field] = value
    with pytest.raises((TypeError, ValueError)):
        DerivationBinding.from_mapping(data)


@pytest.mark.parametrize("field,value", [("reviewed_at", "2026-09-01"), ("reviewed_at", "2026-09-01T00:00:00+00:00"),
                                          ("bidirectional_case_count", -1), ("synthetic_fuzz_case_count", True),
                                          ("parity_status", "UNKNOWN"), ("status", "UNKNOWN")])
def test_rejects_invalid_timestamps_counts_and_statuses(field, value):
    data = fixture()
    if field in {"reviewed_at", "bidirectional_case_count", "synthetic_fuzz_case_count", "parity_status"}:
        data["review"]["reviewed_at" if field == "reviewed_at" else field] = value
    else:
        data["review"][field] = value
    if field in {"bidirectional_case_count", "synthetic_fuzz_case_count", "parity_status"}:
        data["golden_evidence"][field] = value
    with pytest.raises((TypeError, ValueError)):
        DerivationBinding.from_mapping(data)


@pytest.mark.parametrize("categories", [["filter_order"] * 7, ["unknown"] + list(REQUIRED_GOLDEN_CATEGORIES[1:])])
def test_rejects_duplicate_or_unknown_categories(categories):
    data = fixture()
    data["golden_evidence"]["covered_categories"] = categories
    with pytest.raises((TypeError, ValueError)):
        DerivationBinding.from_mapping(data)


def test_rejects_nonfinite_count():
    data = fixture()
    data["golden_evidence"]["bidirectional_case_count"] = float("nan")
    with pytest.raises((TypeError, ValueError)):
        DerivationBinding.from_mapping(data)


def test_unavailable_error_is_fixed_and_redacted():
    error = DerivationBindingUnavailable("patient secret", RuntimeError("details"))
    assert str(error) == "derivation binding is unavailable"
    assert error.args == ("derivation binding is unavailable",)


def test_status_enum_values_are_fixed():
    assert DerivationBindingStatus.PENDING.value == "PENDING"
    assert DerivationBindingStatus.APPROVED.value == "APPROVED"
    assert DerivationBindingStatus.REJECTED.value == "REJECTED"
