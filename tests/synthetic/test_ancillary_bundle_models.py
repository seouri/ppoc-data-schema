from __future__ import annotations

import dataclasses
import json
from types import MappingProxyType

import pytest

from synthetic.native.ancillary_bundle import (
    ANCILLARY_BUNDLE_CHECK_NAMES,
    ANCILLARY_BUNDLE_REASON_CODES,
    AncillaryBundleCheck,
    AncillaryBundleValidationReport,
    AncillaryBundleValidationStatus,
)


def _checks(
    status: AncillaryBundleValidationStatus,
) -> tuple[AncillaryBundleCheck, ...]:
    reason = {
        AncillaryBundleValidationStatus.PASS: "OK",
        AncillaryBundleValidationStatus.FAIL: "BUNDLE_IDENTITY_INVALID",
        AncillaryBundleValidationStatus.UNEVALUABLE: "INSUFFICIENT_EVIDENCE",
    }[status]
    return tuple(AncillaryBundleCheck(name, status, reason) for name in ANCILLARY_BUNDLE_CHECK_NAMES)


def test_bundle_validation_models_are_closed_frozen_and_aggregate_only() -> None:
    checks = list(_checks(AncillaryBundleValidationStatus.PASS))
    checks[0] = AncillaryBundleCheck(
        "bundle_identity", AncillaryBundleValidationStatus.FAIL, "BUNDLE_IDENTITY_INVALID"
    )
    checks[-1] = AncillaryBundleCheck(
        "truth_boundary", AncillaryBundleValidationStatus.UNEVALUABLE, "INSUFFICIENT_EVIDENCE"
    )
    report = AncillaryBundleValidationReport(AncillaryBundleValidationStatus.FAIL, tuple(reversed(checks)))

    assert tuple(status.value for status in AncillaryBundleValidationStatus) == (
        "PASS",
        "FAIL",
        "UNEVALUABLE",
    )
    assert ANCILLARY_BUNDLE_CHECK_NAMES == (
        "bundle_identity",
        "base_resources",
        "ancillary_resources",
        "truth_boundary",
    )
    assert tuple(check.name for check in report.checks) == ANCILLARY_BUNDLE_CHECK_NAMES
    assert report.check_counts == {"PASS": 2, "FAIL": 1, "UNEVALUABLE": 1}
    assert isinstance(report.check_counts, MappingProxyType)
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.status = AncillaryBundleValidationStatus.PASS  # type: ignore[misc]
    with pytest.raises(TypeError):
        report.check_counts["PASS"] = 0  # type: ignore[index]

    encoded = json.dumps(report.to_mapping(), sort_keys=True)
    assert set(report.to_mapping()) == {"status", "check_counts", "checks"}
    assert "patient" not in encoded
    assert "source_frame" not in encoded
    assert "row" not in encoded
    assert "AncillaryBundleValidationReport" in repr(report)
    assert "source_frame" not in repr(report)
    assert "BUNDLE_IDENTITY_INVALID" in ANCILLARY_BUNDLE_REASON_CODES


def test_bundle_validation_models_reject_invalid_status_reason_and_aggregate_status() -> None:
    with pytest.raises(ValueError, match="check"):
        AncillaryBundleCheck("unknown", AncillaryBundleValidationStatus.PASS, "OK")
    with pytest.raises(ValueError, match="reason"):
        AncillaryBundleCheck("base_resources", AncillaryBundleValidationStatus.PASS, "BUNDLE_IDENTITY_INVALID")

    failed = list(_checks(AncillaryBundleValidationStatus.PASS))
    failed[0] = AncillaryBundleCheck(
        "bundle_identity", AncillaryBundleValidationStatus.FAIL, "BUNDLE_IDENTITY_INVALID"
    )
    with pytest.raises(ValueError, match="status"):
        AncillaryBundleValidationReport(AncillaryBundleValidationStatus.PASS, tuple(failed))
