from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from synthetic.calibration import CalibrationStratum, CalibrationTarget
from synthetic.heldout_validate import (
    FidelityPolicy,
    HeldoutCheck,
    HeldoutValidationReport,
    compare_targets,
    validation_status,
)
from tests.synthetic.test_heldout_policy import valid_policy_mapping


def target(
    name: str,
    family: str,
    statistic: str,
    value: float | None,
    *,
    support: int | None = 20,
    denominator: int | None = None,
    quantile_level: float | None = None,
    status: str = "released",
) -> CalibrationTarget:
    return CalibrationTarget(
        target_name=name,
        family=family,
        statistic=statistic,
        unit="unit",
        status=status,
        value=value,
        support_count=support,
        denominator=denominator,
        rounding_decimals=0,
        quantile_level=quantile_level,
    )


def stratum(*targets: CalibrationTarget, sex: str = "F") -> CalibrationStratum:
    dimensions = (("recorded_sex", sex),)
    return CalibrationStratum(
        stratum_id=f"recorded_sex={sex}", dimensions=dimensions, targets=targets
    )


def policy(**changes: object) -> FidelityPolicy:
    return FidelityPolicy(**valid_policy_mapping(**changes))  # type: ignore[arg-type]


def test_compare_targets_uses_canonical_matching_and_frozen_tolerances() -> None:
    heldout = (
        stratum(
            target("sex_f", "demographics", "proportion", 0.50, denominator=20),
            target("encounters", "utilization", "count", 10),
            target("height_mean", "physiology", "mean", 2.0),
            target("height_sd", "physiology", "sd", 1.5),
            target("height_q50", "physiology", "quantile", 2.0, quantile_level=0.5),
        ),
    )
    synthetic = (
        stratum(
            target("height_q50", "physiology", "quantile", 2.8, quantile_level=0.5),
            target("height_sd", "physiology", "sd", 2.4),
            target("height_mean", "physiology", "mean", 2.9),
            target("encounters", "utilization", "count", 11),
            target("sex_f", "demographics", "proportion", 0.70, denominator=100),
        ),
    )

    comparisons = compare_targets(heldout, synthetic, policy(required_families=["demographics"]))

    assert [comparison.target_name for comparison in comparisons] == [
        "encounters", "height_mean", "height_q50", "height_sd", "sex_f"
    ]
    indexed = {comparison.target_name: comparison for comparison in comparisons}
    assert indexed["sex_f"].difference == pytest.approx(0.2)
    assert indexed["sex_f"].tolerance == pytest.approx(2 * (0.5 * 0.5 / 20) ** 0.5)
    assert indexed["sex_f"].status == "PASS"
    assert indexed["encounters"].tolerance == 1
    assert indexed["encounters"].status == "PASS"
    assert indexed["height_mean"].tolerance == 1.0
    assert indexed["height_mean"].status == "PASS"
    assert indexed["height_sd"].status == "PASS"
    assert indexed["height_q50"].status == "PASS"


def test_compare_targets_marks_missing_suppressed_and_under_support_unevaluable() -> None:
    heldout = (
        stratum(
            target("missing", "demographics", "count", 2),
            target("suppressed", "observation", "count", None, support=None, status="suppressed"),
            target("small", "physiology", "mean", 1.0, support=1),
        ),
    )
    synthetic = (
        stratum(
            target("suppressed", "observation", "count", 2),
            target("small", "physiology", "mean", 1.1),
        ),
    )

    comparisons = compare_targets(heldout, synthetic, policy())

    assert {comparison.status for comparison in comparisons} == {"UNEVALUABLE"}
    for comparison in comparisons:
        assert (
            comparison.heldout_value,
            comparison.synthetic_value,
            comparison.difference,
            comparison.tolerance,
        ) == (None, None, None, None)


def test_compare_targets_marks_evaluable_out_of_tolerance_target_failed() -> None:
    comparisons = compare_targets(
        (stratum(target("height_mean", "physiology", "mean", 2.0)),),
        (stratum(target("height_mean", "physiology", "mean", 3.1)),),
        policy(required_families=["physiology"]),
    )

    assert comparisons[0].status == "FAIL"
    assert comparisons[0].difference == pytest.approx(1.1)
    assert comparisons[0].tolerance == 1.0


def test_report_is_canonical_redacted_and_unevaluable_for_missing_required_family() -> None:
    comparisons = compare_targets(
        (stratum(target("height_mean", "physiology", "mean", 2.0)),),
        (stratum(target("height_mean", "physiology", "mean", 2.1)),),
        policy(required_families=["demographics", "physiology"], max_unevaluable_targets=1),
    )
    report = HeldoutValidationReport(
        report_version="heldout-validation-report-v1",
        status="UNEVALUABLE",
        source_snapshot="snapshot-v1",
        synthetic_artifact_id="synthetic-v1",
        schema_fingerprint="a" * 64,
        partition_policy={"policy_id": "partition-v1", "policy_version": "1"},
        disclosure_policy={"policy_id": "disclosure-v1", "policy_version": "1"},
        fidelity_policy=policy(required_families=["demographics", "physiology"]).to_report_mapping(),
        heldout_aggregate_sha256="b" * 64,
        synthetic_aggregate_sha256="c" * 64,
        comparison_counts={"PASS": 1, "FAIL": 0, "UNEVALUABLE": 0},
        family_counts={"physiology": {"PASS": 1, "FAIL": 0, "UNEVALUABLE": 0}},
        checks=(HeldoutCheck("family_coverage", False, "required family is unavailable"),),
        comparisons=comparisons,
    )

    assert validation_status(comparisons, policy(required_families=["demographics", "physiology"])) == "UNEVALUABLE"
    payload = report.canonical_json()
    assert set(report.to_mapping()) == {
        "report_version", "status", "source_snapshot", "synthetic_artifact_id", "schema_fingerprint",
        "partition_policy", "disclosure_policy", "fidelity_policy", "heldout_aggregate_sha256",
        "synthetic_aggregate_sha256", "comparison_counts", "family_counts", "checks", "comparisons",
    }
    assert report.to_json_bytes() == (payload + "\n").encode("ascii")
    assert "support" not in payload
    assert "denominator" not in payload
    assert "SYN-P-001" not in payload
    assert "/governed/ppoc" not in payload
    assert "heldout_value" in payload
    assert "2.0" in payload
    assert "2.1" in payload
    assert "2.0" not in report.human_summary()
    assert "2.1" not in report.human_summary()
    assert "SYN-P-001" not in report.human_summary()
    with pytest.raises(FrozenInstanceError):
        report.status = "PASS"  # type: ignore[misc]


def test_report_and_check_reject_sensitive_metadata() -> None:
    with pytest.raises(ValueError, match="aggregate"):
        HeldoutCheck("patient_check", True, "matched contract")
