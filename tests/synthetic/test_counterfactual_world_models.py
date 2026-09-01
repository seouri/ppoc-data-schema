from __future__ import annotations

import dataclasses
import json

import pytest

from synthetic.native.counterfactual_worlds import (
    COUNTERFACTUAL_WORLD_CHECK_NAMES,
    COUNTERFACTUAL_WORLD_REASON_CODES,
    CounterfactualWorldCheck,
    CounterfactualWorldValidationReport,
    CounterfactualWorldValidationStatus,
)


def _checks(
    status: CounterfactualWorldValidationStatus,
) -> tuple[CounterfactualWorldCheck, ...]:
    reason = {
        CounterfactualWorldValidationStatus.PASS: "OK",
        CounterfactualWorldValidationStatus.FAIL: "MALFORMED_WORLDS",
        CounterfactualWorldValidationStatus.UNEVALUABLE: "INSUFFICIENT_EVIDENCE",
    }[status]
    return tuple(CounterfactualWorldCheck(name, status, reason) for name in COUNTERFACTUAL_WORLD_CHECK_NAMES)


def test_world_report_is_immutable_canonical_and_aggregate_only() -> None:
    checks = list(_checks(CounterfactualWorldValidationStatus.PASS))
    checks[0] = CounterfactualWorldCheck(
        "pair_binding", CounterfactualWorldValidationStatus.FAIL, "MALFORMED_WORLDS"
    )
    checks[-1] = CounterfactualWorldCheck(
        "truth_boundary", CounterfactualWorldValidationStatus.UNEVALUABLE, "INSUFFICIENT_EVIDENCE"
    )

    report = CounterfactualWorldValidationReport(
        CounterfactualWorldValidationStatus.FAIL, tuple(reversed(checks))
    )

    assert tuple(status.value for status in CounterfactualWorldValidationStatus) == (
        "PASS",
        "FAIL",
        "UNEVALUABLE",
    )
    assert tuple(check.name for check in report.checks) == COUNTERFACTUAL_WORLD_CHECK_NAMES
    assert report.check_counts == {"PASS": 5, "FAIL": 1, "UNEVALUABLE": 1}
    assert set(report.to_mapping()) == {"status", "check_counts", "checks"}
    assert "patient_id" not in json.dumps(report.to_mapping(), sort_keys=True)
    assert "MALFORMED_WORLDS" in COUNTERFACTUAL_WORLD_REASON_CODES
    assert "CounterfactualWorldValidationReport" in repr(report)

    with pytest.raises(dataclasses.FrozenInstanceError):
        report.status = CounterfactualWorldValidationStatus.PASS  # type: ignore[misc]
    with pytest.raises(TypeError):
        report.check_counts["PASS"] = 0  # type: ignore[index]


def test_world_report_rejects_incomplete_or_status_incompatible_checks() -> None:
    with pytest.raises(ValueError, match="check"):
        CounterfactualWorldCheck("unknown", CounterfactualWorldValidationStatus.PASS, "OK")
    with pytest.raises(ValueError, match="reason"):
        CounterfactualWorldCheck("pair_binding", CounterfactualWorldValidationStatus.PASS, "MALFORMED_WORLDS")
    with pytest.raises(ValueError, match="every fixed"):
        CounterfactualWorldValidationReport(
            CounterfactualWorldValidationStatus.PASS,
            _checks(CounterfactualWorldValidationStatus.PASS)[:-1],
        )
