import json
import math
from dataclasses import FrozenInstanceError

import pytest

from synthetic.derivation_parity import (
    DERIVATION_PARITY_CHECK_NAMES,
    DERIVATION_PARITY_VERSION,
    DerivationImplementation,
    DerivationParityCheck,
    DerivationParityPolicy,
    DerivationParityReport,
    DerivationParityStatus,
)
from synthetic.schema_contract import EXPECTED_SCHEMA_FINGERPRINT


def implementation(name="candidate"):
    return DerivationImplementation(name, "a" * 64, True)


def policy(**overrides):
    values = {
        "policy_id": "parity-policy",
        "policy_version": "v1",
        "minimum_patient_rows": 1,
        "minimum_visit_rows": 1,
        "deterministic_tolerance": 0.001,
        "reference_tolerance": 0.01,
    }
    values.update(overrides)
    return DerivationParityPolicy(**values)


def check(name, status=DerivationParityStatus.PASS, reason_code="OK"):
    return DerivationParityCheck(name, status, reason_code, 1, 0, 0.0)


def report(**overrides):
    values = {
        "contract": DERIVATION_PARITY_VERSION,
        "schema_fingerprint": EXPECTED_SCHEMA_FINGERPRINT,
        "policy": policy(),
        "candidate": implementation(),
        "reference": implementation("reference"),
        "patient_row_count": 1,
        "visit_row_count": 1,
        "status": DerivationParityStatus.PASS,
        "status_counts": {"PASS": 15, "FAIL": 0, "UNEVALUABLE": 0},
        "checks": tuple(check(name) for name in DERIVATION_PARITY_CHECK_NAMES),
    }
    values.update(overrides)
    return DerivationParityReport(**values)


@pytest.mark.parametrize("field,value", [("implementation_id", ""), ("implementation_id", "patient/id")])
def test_implementation_rejects_unsafe_tokens(field, value):
    with pytest.raises((TypeError, ValueError)):
        DerivationImplementation(value, "a" * 64, True)


@pytest.mark.parametrize("field,value", [("fingerprint", "x"), ("fingerprint", "A" * 64), ("test_only", 1)])
def test_implementation_rejects_bad_values(field, value):
    values = {"implementation_id": "candidate", "fingerprint": "a" * 64, "test_only": True}
    values[field] = value
    with pytest.raises((TypeError, ValueError)):
        DerivationImplementation(**values)


@pytest.mark.parametrize("field,value", [("policy_id", ""), ("policy_version", "bad/value"), ("minimum_patient_rows", -1), ("minimum_visit_rows", True), ("deterministic_tolerance", -1), ("deterministic_tolerance", math.inf), ("reference_tolerance", math.nan)])
def test_policy_rejects_bad_values(field, value):
    values = {"policy_id": "p", "policy_version": "v", "minimum_patient_rows": 1, "minimum_visit_rows": 1, "deterministic_tolerance": 0.1, "reference_tolerance": 0.1}
    values[field] = value
    with pytest.raises((TypeError, ValueError)):
        DerivationParityPolicy(**values)


def test_valid_models_are_immutable_and_serialize_as_safe_aggregates():
    value = report()
    with pytest.raises(FrozenInstanceError):
        value.patient_row_count = 2
    mapping = value.to_mapping()
    assert mapping is not value.to_mapping()
    assert mapping["checks"][0]["name"] == "schema_contract"
    mapping["checks"][0]["name"] = "changed"
    assert value.checks[0].name == "schema_contract"
    encoded = value.to_json_bytes()
    assert encoded.endswith(b"\n")
    assert encoded == json.dumps(json.loads(encoded), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode() + b"\n"
    assert "patient" not in repr(value).lower()
    assert "candidate" not in repr(value).lower()


def test_report_rejects_duplicate_checks_bad_counts_and_unknown_keys():
    duplicate = tuple(check(name) for name in DERIVATION_PARITY_CHECK_NAMES[:-1]) + (check("schema_contract"),)
    with pytest.raises((TypeError, ValueError)):
        report(checks=duplicate)
    with pytest.raises((TypeError, ValueError)):
        report(status_counts={"PASS": 14, "FAIL": 0, "UNEVALUABLE": 0})
    with pytest.raises((TypeError, ValueError)):
        DerivationParityCheck("schema_contract", DerivationParityStatus.PASS, "OK", 1, 0, math.inf)
    with pytest.raises((TypeError, ValueError)):
        DerivationParityCheck("schema_contract", DerivationParityStatus.PASS, "OK", 1, 0, 0.0, extra="x")


def test_unevaluable_check_suppresses_evidence():
    item = DerivationParityCheck("schema_contract", DerivationParityStatus.UNEVALUABLE, "MISSING_EVIDENCE", 9, 2, 1.0)
    assert item.compared_count is None
    assert item.mismatch_count is None
    assert item.maximum_absolute_difference is None
