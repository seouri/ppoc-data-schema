import json
from dataclasses import FrozenInstanceError

import pytest

from synthetic.derivation_binding import (
    DERIVATION_BINDING_CHECK_NAMES,
    REQUIRED_GOLDEN_CATEGORIES,
    DerivationBinding,
    DerivationBindingCheck,
    DerivationBindingStatus,
    DerivationBindingUnavailable,
    require_approved_derivation_binding,
    validate_derivation_binding,
)

SHA = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
SHA2 = "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
SHA3 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
ZERO_SHA = "0" * 64


def fixture(*, test_only: bool = False) -> dict[str, object]:
    return {
        "binding_version": "derivation-binding-v1",
        "binding_id": "binding-example-v1",
        "schema_fingerprint": SHA,
        "oracle": {
            "oracle_id": "oracle-example-v1",
            "implementation_fingerprint": SHA2,
            "source_revision": "revision-example-v1",
            "dependency_fingerprint": SHA,
            "source_kind": "authoritative_implementation",
        },
        "reference_standard": {
            "standard_id": "standard-example-v1",
            "standard_fingerprint": SHA2,
            "version": "standard-version-1",
        },
        "golden_evidence": {
            "manifest_id": "golden-example-v1",
            "manifest_fingerprint": SHA,
            "parity_contract": "derivation-parity-v1",
            "parity_report_id": "parity-report-example-v1",
            "parity_report_fingerprint": SHA2,
            "parity_status": "PASS",
            "candidate_implementation_fingerprint": SHA2,
            "reference_implementation_fingerprint": SHA,
            "parity_schema_fingerprint": SHA,
            "covered_categories": list(REQUIRED_GOLDEN_CATEGORIES),
            "bidirectional_case_count": 7,
            "synthetic_fuzz_case_count": 100,
            "fuzz_corpus_fingerprint": SHA2,
        },
        "review": {
            "review_id": "review-example-v1",
            "review_fingerprint": SHA,
            "reviewed_at": "2026-09-01T00:00:00Z",
            "reviewer_role": "data-custodian",
            "status": "APPROVED",
        },
        "test_only": test_only,
    }


def binding(*, test_only: bool = False) -> DerivationBinding:
    return DerivationBinding.from_mapping(fixture(test_only=test_only))


def corrupt(instance: object, **fields: object) -> None:
    for name, value in fields.items():
        object.__setattr__(instance, name, value)


def by_name(report: object) -> dict[str, object]:
    return {check.name: check for check in report.checks}  # type: ignore[attr-defined]


def test_complete_approved_binding_has_nine_passing_checks_and_is_approvable():
    value = binding()

    report = validate_derivation_binding(value, expected_schema_fingerprint=SHA)

    assert tuple(check.name for check in report.checks) == DERIVATION_BINDING_CHECK_NAMES
    assert [check.status for check in report.checks] == [DerivationBindingStatus.PASS] * 9
    assert report.status is DerivationBindingStatus.PASS
    assert report.schema_fingerprint == SHA
    assert report.status_counts == {"PASS": 9, "FAIL": 0, "UNEVALUABLE": 0}
    assert require_approved_derivation_binding(value, expected_schema_fingerprint=SHA) is None


def test_schema_mismatch_report_identifies_explicit_expected_schema():
    value = binding()

    report = validate_derivation_binding(value, expected_schema_fingerprint=SHA3)

    assert report.schema_fingerprint == SHA3
    assert value.schema_fingerprint == SHA
    assert by_name(report)["schema_contract"].status is DerivationBindingStatus.FAIL


@pytest.mark.parametrize(
    ("owner", "field", "check"),
    [
        ("binding", "schema_fingerprint", "schema_contract"),
        ("oracle", "dependency_fingerprint", "oracle_identity"),
        ("reference_standard", "standard_fingerprint", "reference_standard"),
        ("golden_evidence", "manifest_fingerprint", "golden_coverage"),
        ("golden_evidence", "parity_report_fingerprint", "parity_evidence"),
        ("golden_evidence", "reference_implementation_fingerprint", "parity_evidence"),
        ("golden_evidence", "fuzz_corpus_fingerprint", "synthetic_fuzz_evidence"),
        ("review", "review_fingerprint", "review"),
    ],
)
def test_forged_all_zero_digest_fails_evaluation_and_approval(owner, field, check):
    value = binding()
    target = value if owner == "binding" else getattr(value, owner)
    corrupt(target, **{field: ZERO_SHA})

    report = validate_derivation_binding(value, expected_schema_fingerprint=SHA)

    assert by_name(report)[check].status is DerivationBindingStatus.FAIL
    with pytest.raises(DerivationBindingUnavailable, match="^derivation binding is unavailable$"):
        require_approved_derivation_binding(value, expected_schema_fingerprint=SHA)


def test_matching_all_zero_implementation_fingerprints_cannot_pass_evaluation():
    value = binding()
    corrupt(value.oracle, implementation_fingerprint=ZERO_SHA)
    corrupt(value.golden_evidence, candidate_implementation_fingerprint=ZERO_SHA)

    report = validate_derivation_binding(value, expected_schema_fingerprint=SHA)

    assert by_name(report)["oracle_identity"].status is DerivationBindingStatus.FAIL
    assert by_name(report)["parity_evidence"].status is DerivationBindingStatus.FAIL
    with pytest.raises(DerivationBindingUnavailable, match="^derivation binding is unavailable$"):
        require_approved_derivation_binding(value, expected_schema_fingerprint=SHA)


def test_all_zero_expected_and_submitted_schema_fingerprints_are_invalid():
    value = binding()
    corrupt(value, schema_fingerprint=ZERO_SHA)
    corrupt(value.golden_evidence, parity_schema_fingerprint=ZERO_SHA)

    with pytest.raises(ValueError, match="expected_schema_fingerprint"):
        validate_derivation_binding(value, expected_schema_fingerprint=ZERO_SHA)
    with pytest.raises(ValueError, match="expected_schema_fingerprint"):
        require_approved_derivation_binding(value, expected_schema_fingerprint=ZERO_SHA)


def test_test_only_pending_binding_keeps_absent_evidence_unevaluable_and_is_not_approvable():
    data = fixture(test_only=True)
    data["golden_evidence"].update({  # type: ignore[index]
        "manifest_id": None,
        "manifest_fingerprint": None,
        "parity_contract": None,
        "parity_report_id": None,
        "parity_report_fingerprint": None,
        "parity_status": "UNEVALUABLE",
        "candidate_implementation_fingerprint": None,
        "reference_implementation_fingerprint": None,
        "parity_schema_fingerprint": None,
        "bidirectional_case_count": 0,
        "synthetic_fuzz_case_count": 0,
        "fuzz_corpus_fingerprint": None,
    })
    data["review"] = {
        "review_id": None,
        "review_fingerprint": None,
        "reviewed_at": None,
        "reviewer_role": None,
        "status": "PENDING",
    }
    value = DerivationBinding.from_mapping(data)

    report = validate_derivation_binding(value, expected_schema_fingerprint=SHA)
    checks = by_name(report)

    assert report.status is DerivationBindingStatus.UNEVALUABLE
    for name in ("golden_coverage", "parity_evidence", "synthetic_fuzz_evidence", "review"):
        assert checks[name].status is DerivationBindingStatus.UNEVALUABLE
        assert checks[name].compared_count is None
        assert checks[name].mismatch_count is None
    assert report.parity_report_id is None
    with pytest.raises(DerivationBindingUnavailable, match="^derivation binding is unavailable$"):
        require_approved_derivation_binding(value, expected_schema_fingerprint=SHA)


def test_unevaluable_parity_evidence_suppresses_its_report_identity():
    value = binding(test_only=True)
    corrupt(value.golden_evidence, parity_status="UNEVALUABLE")

    report = validate_derivation_binding(value, expected_schema_fingerprint=SHA)

    assert by_name(report)["parity_evidence"].status is DerivationBindingStatus.UNEVALUABLE
    assert report.parity_report_id is None


@pytest.mark.parametrize(
    ("field", "value", "check"),
    [
        ("covered_categories", REQUIRED_GOLDEN_CATEGORIES[:-1], "golden_coverage"),
        ("bidirectional_case_count", 0, "golden_coverage"),
        ("manifest_fingerprint", None, "golden_coverage"),
        ("synthetic_fuzz_case_count", 0, "synthetic_fuzz_evidence"),
    ],
)
def test_missing_or_zero_evidence_is_unevaluable_not_a_fabricated_pass(field, value, check):
    value_binding = binding()
    corrupt(value_binding.golden_evidence, **{field: value})

    result = validate_derivation_binding(value_binding, expected_schema_fingerprint=SHA)

    item = by_name(result)[check]
    assert item.status is DerivationBindingStatus.UNEVALUABLE
    assert item.reason_code == "MISSING_EVIDENCE"
    assert item.compared_count is None
    assert item.mismatch_count is None


def test_null_fuzz_count_is_unevaluable_not_structurally_invalid():
    value = binding(test_only=True)
    corrupt(value.golden_evidence, synthetic_fuzz_case_count=None)

    result = validate_derivation_binding(value, expected_schema_fingerprint=SHA)

    item = by_name(result)["synthetic_fuzz_evidence"]
    assert item.status is DerivationBindingStatus.UNEVALUABLE
    assert item.reason_code == "MISSING_EVIDENCE"
    assert item.compared_count is None
    assert item.mismatch_count is None


def test_missing_review_fields_are_unevaluable_not_an_approval():
    value = binding()
    corrupt(value.review, review_id=None)

    result = validate_derivation_binding(value, expected_schema_fingerprint=SHA)

    item = by_name(result)["review"]
    assert item.status is DerivationBindingStatus.UNEVALUABLE
    assert item.reason_code == "MISSING_EVIDENCE"
    assert item.compared_count is None
    assert item.mismatch_count is None


@pytest.mark.parametrize(
    ("mutate", "check"),
    [
        (lambda value: corrupt(value.golden_evidence, covered_categories=("unknown",)), "golden_coverage"),
        (lambda value: corrupt(value.golden_evidence, parity_status="PASS", parity_report_id=None), "parity_evidence"),
        (lambda value: corrupt(value.golden_evidence, parity_status="FAIL"), "parity_evidence"),
        (lambda value: corrupt(value.golden_evidence, candidate_implementation_fingerprint=SHA3), "parity_evidence"),
        (lambda value: corrupt(value.golden_evidence, parity_schema_fingerprint=SHA3), "parity_evidence"),
        (lambda value: corrupt(value.golden_evidence, fuzz_corpus_fingerprint=None), "synthetic_fuzz_evidence"),
        (lambda value: corrupt(value.review, status="REJECTED"), "review"),
        (lambda value: corrupt(value.review, status="PENDING"), "review"),
    ],
)
def test_contradictory_evidence_fails_its_own_check(mutate, check):
    value = binding()
    mutate(value)

    report = validate_derivation_binding(value, expected_schema_fingerprint=SHA)

    item = by_name(report)[check]
    assert item.status is DerivationBindingStatus.FAIL
    assert item.reason_code in {"OUTSIDE_POLICY", "STRUCTURAL_INVALID"}
    assert item.compared_count is not None
    assert item.mismatch_count is not None and item.mismatch_count > 0


@pytest.mark.parametrize("field", ["candidate_implementation_fingerprint", "parity_schema_fingerprint"])
def test_unevaluable_parity_with_a_supplied_fingerprint_mismatch_fails(field):
    value = binding(test_only=True)
    corrupt(value.golden_evidence, parity_status="UNEVALUABLE", **{field: SHA3})

    result = validate_derivation_binding(value, expected_schema_fingerprint=SHA)

    item = by_name(result)["parity_evidence"]
    assert item.status is DerivationBindingStatus.FAIL
    assert item.reason_code == "OUTSIDE_POLICY"


def test_report_is_fixed_aggregate_only_and_exception_is_redacted():
    value = binding()
    corrupt(value.review, reviewer_role="private-reviewer", review_id="review-private-v1")
    report = validate_derivation_binding(value, expected_schema_fingerprint=SHA)
    rendered = json.dumps(report.to_mapping(), sort_keys=True) + repr(report) + report.to_json_bytes().decode()

    assert report.to_mapping().keys() == {
        "binding_version", "binding_id", "schema_fingerprint", "oracle_id",
        "reference_standard_id", "parity_report_id", "status", "status_counts", "checks",
    }
    assert tuple(check["name"] for check in report.to_mapping()["checks"]) == DERIVATION_BINDING_CHECK_NAMES
    assert report.status_counts == {"PASS": 7, "FAIL": 2, "UNEVALUABLE": 0}
    for forbidden in ("patient", "visit", "row", "path", "private", "reviewer", "golden-example-v1"):
        assert forbidden not in rendered.lower()
    with pytest.raises(DerivationBindingUnavailable) as error:
        require_approved_derivation_binding(value, expected_schema_fingerprint=SHA)
    assert str(error.value) == "derivation binding is unavailable"
    assert "private" not in repr(error.value).lower()


def test_check_model_rejects_impossible_status_and_count_combinations():
    with pytest.raises(ValueError):
        DerivationBindingCheck("contract", DerivationBindingStatus.PASS, "OK", 1, 1)
    with pytest.raises(ValueError):
        DerivationBindingCheck("contract", DerivationBindingStatus.FAIL, "OUTSIDE_POLICY", 1, 0)
    with pytest.raises(ValueError):
        DerivationBindingCheck("contract", DerivationBindingStatus.UNEVALUABLE, "MISSING_EVIDENCE", 1, 0)
    valid = DerivationBindingCheck("contract", DerivationBindingStatus.UNEVALUABLE, "MISSING_EVIDENCE", None, None)
    with pytest.raises(FrozenInstanceError):
        valid.name = "review"
