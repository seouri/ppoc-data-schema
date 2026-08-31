import hashlib
import json
from pathlib import Path

from synthetic.calibrate import (
    DEFAULT_AGE_WINDOWS,
    CalibrationInput,
    CalibrationRunConfig,
    PartitionPolicy,
    PartitionSummary,
)
from synthetic.calibration import CalibrationDisclosurePolicy
from synthetic.calibration_disclosure import build_result, disclose_targets
from synthetic.calibration_targets import RawTarget


def config() -> CalibrationRunConfig:
    return CalibrationRunConfig(
        data_root=Path("synthetic-snapshot"),
        source_descriptor=Path("datapackage.json"),
        source_snapshot="snapshot-v1",
        artifact_id="calibration-v1",
        created_at="2026-08-31T12:00:00Z",
        partition_policy=PartitionPolicy("partition-v1", "1", "key-2026", 8_000, 2),
        disclosure_policy=CalibrationDisclosurePolicy("disclosure-v1", "1", 3, 2),
        partition_key=b"0123456789abcdef",
        age_windows=DEFAULT_AGE_WINDOWS,
    )


def prepared() -> CalibrationInput:
    counts = {"calibration": 8, "held_out": 4}
    resource_counts = {
        resource: dict(counts)
        for resource in (
            "patients", "patients_augmented", "visits", "visits_augmented", "labs", "medications", "problem_list", "referrals"
        )
    }
    return CalibrationInput(
        descriptor={},
        schema_fingerprint="a" * 64,
        partition_summary=PartitionSummary(counts, resource_counts),
        resource_names=tuple(resource_counts),
    )


def raw_targets() -> tuple[RawTarget, ...]:
    return (
        RawTarget("outcome_layer=observed", (("outcome_layer", "observed"),), "height_z_mean", "physiology", "mean", "zscore", 1.2349, 2, None),
        RawTarget("outcome_layer=observed", (("outcome_layer", "observed"),), "sex_f", "demographics", "proportion", "fraction", 0.33339, 3, 9),
        RawTarget("outcome_layer=observed", (("outcome_layer", "observed"),), "weight_z_q90", "physiology", "quantile", "zscore", 2.9876, 5, None, 0.9),
    )


def test_disclosure_suppresses_before_rounding_and_rounds_released_continuous_values() -> None:
    strata = disclose_targets(raw_targets(), config())
    targets = {target.target_name: target for target in strata[0].targets}

    assert targets["height_z_mean"].status == "suppressed"
    assert targets["height_z_mean"].value is None
    assert targets["height_z_mean"].support_count is None
    assert targets["height_z_mean"].denominator is None
    assert targets["height_z_mean"].rounding_decimals == 0
    assert targets["sex_f"].value == 0.33
    assert targets["sex_f"].rounding_decimals == 2
    assert 0 <= targets["sex_f"].value <= 1
    assert targets["weight_z_q90"].value == 2.99


def test_disclosed_targets_have_order_independent_canonical_aggregate_hash() -> None:
    left = build_result(disclose_targets(raw_targets(), config()), prepared(), config())
    right = build_result(disclose_targets(tuple(reversed(raw_targets())), config()), prepared(), config())

    assert left.artifact.source_aggregate_sha256 == right.artifact.source_aggregate_sha256
    assert left.artifact.source_aggregate_sha256 == hashlib.sha256(
        json.dumps(
            [{
                "stratum_id": "outcome_layer=observed",
                "dimensions": {"outcome_layer": "observed"},
                "targets": [
                    {"target_name": "height_z_mean", "family": "physiology", "statistic": "mean", "unit": "zscore", "status": "suppressed", "value": None, "support_count": None, "denominator": None, "rounding_decimals": 0},
                    {"target_name": "sex_f", "family": "demographics", "statistic": "proportion", "unit": "fraction", "status": "released", "value": 0.33, "support_count": 3, "denominator": 9, "rounding_decimals": 2},
                    {"target_name": "weight_z_q90", "family": "physiology", "statistic": "quantile", "unit": "zscore", "status": "released", "value": 2.99, "support_count": 5, "denominator": None, "rounding_decimals": 2, "quantile_level": 0.9},
                ],
            }],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def test_report_is_aggregate_only_without_target_support_or_governed_input_details() -> None:
    result = build_result(disclose_targets(raw_targets(), config()), prepared(), config())
    report_json = result.report.canonical_json()

    assert result.report.status == "AGGREGATES_ONLY"
    assert result.report.source_aggregate_sha256 == result.artifact.source_aggregate_sha256
    assert "support_count" not in report_json
    assert "denominator" not in report_json
    assert "patient_id" not in report_json
    assert "visit_id" not in report_json
    assert "data_root" not in report_json
    assert "source_descriptor" not in report_json
    assert "key_id" not in report_json
