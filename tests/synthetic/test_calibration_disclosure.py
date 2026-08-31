import hashlib
import json
from pathlib import Path

import pytest

from synthetic import calibration_disclosure
from synthetic.calibrate import (
    DEFAULT_AGE_WINDOWS,
    CalibrationInput,
    CalibrationRunConfig,
    PartitionPolicy,
    PartitionSummary,
)
from synthetic.calibration import CalibrationDisclosurePolicy, CalibrationStratum, CalibrationTarget
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
        RawTarget("outcome_layer=observed", (("outcome_layer", "observed"),), "diagnosis_age_years_mean", "recorded_outcome", "mean", "year", 1.2349, 2, None),
        RawTarget("outcome_layer=observed", (("outcome_layer", "observed"),), "sex_f", "demographics", "proportion", "proportion", 0.33339, 3, 9),
        RawTarget("outcome_layer=observed", (("outcome_layer", "observed"),), "diagnosis_age_years_q90", "recorded_outcome", "quantile", "year", 2.9876, 5, None, 0.9),
    )


def test_disclosure_suppresses_before_rounding_and_rounds_released_continuous_values() -> None:
    strata = disclose_targets(raw_targets(), config())
    targets = {target.target_name: target for target in strata[0].targets}

    assert targets["diagnosis_age_years_mean"].status == "suppressed"
    assert targets["diagnosis_age_years_mean"].value is None
    assert targets["diagnosis_age_years_mean"].support_count is None
    assert targets["diagnosis_age_years_mean"].denominator is None
    assert targets["diagnosis_age_years_mean"].rounding_decimals == 0
    assert targets["sex_f"].value == 0.33
    assert targets["sex_f"].rounding_decimals == 2
    assert 0 <= targets["sex_f"].value <= 1
    assert targets["diagnosis_age_years_q90"].value == 2.99


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
                    {"target_name": "diagnosis_age_years_mean", "family": "recorded_outcome", "statistic": "mean", "unit": "year", "status": "suppressed", "value": None, "support_count": None, "denominator": None, "rounding_decimals": 0},
                    {"target_name": "diagnosis_age_years_q90", "family": "recorded_outcome", "statistic": "quantile", "unit": "year", "status": "released", "value": 2.99, "support_count": 5, "denominator": None, "rounding_decimals": 2, "quantile_level": 0.9},
                    {"target_name": "sex_f", "family": "demographics", "statistic": "proportion", "unit": "proportion", "status": "released", "value": 0.33, "support_count": 3, "denominator": 9, "rounding_decimals": 2},
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


def test_released_count_target_preserves_integer_value_at_zero_precision() -> None:
    count = RawTarget(
        "outcome_layer=observed",
        (("outcome_layer", "observed"),),
        "cohort_total",
        "demographics",
        "count",
        "person",
        7,
        3,
        None,
    )

    target = disclose_targets((count,), config())[0].targets[0]

    assert target.status == "released"
    assert target.value == 7
    assert target.rounding_decimals == 0


def test_raw_count_rejects_noninteger_value() -> None:
    with pytest.raises(ValueError, match="count"):
        RawTarget(
            "outcome_layer=observed",
            (("outcome_layer", "observed"),),
            "cohort_total",
            "demographics",
            "count",
            "person",
            7.5,
            3,
            None,
        )


@pytest.mark.parametrize(
    "unsafe_value", ["patient-material", "visit-material", "path-material", "key-material"]
)
def test_result_rejects_unsafe_direct_artifact_metadata(unsafe_value: str) -> None:
    with pytest.raises(ValueError, match="aggregate-safe"):
        values = config().__dict__ | {"artifact_id": unsafe_value}
        CalibrationRunConfig(**values)


@pytest.mark.parametrize(
    ("unsafe_value", "raw_factory"),
    [
        ("patient-material", lambda value: RawTarget("outcome_layer=observed", (("outcome_layer", "observed"),), "height_z_mean", "physiology", "mean", value, 1.2, 3, None)),
        ("visit-material", lambda value: RawTarget("outcome_layer=observed", (("outcome_layer", "observed"),), "height_z_mean", "physiology", "mean", value, 1.2, 3, None)),
        ("path-material", lambda value: RawTarget(f"outcome_layer={value}", (("outcome_layer", value),), "height_z_mean", "physiology", "mean", "zscore", 1.2, 3, None)),
        ("key-material", lambda value: RawTarget(f"outcome_layer={value}", (("outcome_layer", value),), "height_z_mean", "physiology", "mean", "zscore", 1.2, 3, None)),
    ],
)
def test_disclosure_rejects_unsafe_nested_artifact_values(unsafe_value: str, raw_factory: object) -> None:
    raw = raw_factory(unsafe_value)  # type: ignore[operator]
    with pytest.raises(ValueError, match="aggregate-safe"):
        disclose_targets((raw,), config())


def test_artifact_and_report_json_contain_only_aggregate_safe_metadata() -> None:
    result = build_result(disclose_targets(raw_targets(), config()), prepared(), config())

    for payload in (result.artifact.canonical_json(), result.report.canonical_json()):
        assert "patient_id" not in payload
        assert "visit_id" not in payload
        assert "source_path" not in payload
        assert "key_id" not in payload


def test_result_rejects_direct_continuous_targets_with_wrong_precision_or_unrounded_value() -> None:
    def direct_target(value: float, rounding_decimals: int) -> tuple[CalibrationStratum, ...]:
        return (
            CalibrationStratum(
                "outcome_layer=observed",
                (("outcome_layer", "observed"),),
                (CalibrationTarget("height_z_mean", "physiology", "mean", "zscore", "released", value, 3, None, rounding_decimals),),
            ),
        )

    with pytest.raises(ValueError, match="policy precision"):
        build_result(direct_target(1.23, 0), prepared(), config())
    with pytest.raises(ValueError, match="already rounded"):
        build_result(direct_target(1.234, 2), prepared(), config())


@pytest.mark.parametrize(
    ("support_count", "expected_status"), [(2, "suppressed"), (4, "released")]
)
def test_result_rejects_unregistered_target_before_hashing(
    monkeypatch: pytest.MonkeyPatch, support_count: int, expected_status: str
) -> None:
    raw = RawTarget(
        "outcome_layer=observed",
        (("outcome_layer", "observed"),),
        "invented_metric",
        "demographics",
        "proportion",
        "proportion",
        0.5,
        support_count,
        8,
    )
    strata = disclose_targets((raw,), config())
    assert strata[0].targets[0].status == expected_status

    def reject_hashing(_strata: object) -> str:
        pytest.fail("unregistered target reached aggregate hashing")

    monkeypatch.setattr(calibration_disclosure, "_aggregate_sha256", reject_hashing)

    with pytest.raises(ValueError) as exc_info:
        build_result(strata, prepared(), config())

    assert str(exc_info.value) == "calibration target is outside the fixed registry"
