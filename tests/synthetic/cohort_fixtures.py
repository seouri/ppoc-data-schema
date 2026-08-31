"""Aggregate-only fixtures for native cohort profile tests."""

from __future__ import annotations

from synthetic.calibration import CalibrationArtifact
from synthetic.schema_contract import EXPECTED_SCHEMA_FINGERPRINT

_SEX_VALUES = (
    ("sex_f", 0.49),
    ("sex_m", 0.49),
    ("sex_u", 0.02),
)
_ETHNICITY_VALUES = (
    ("ethnicity_blank", 0.02),
    ("ethnicity_not_hispanic_or_latino", 0.65),
    ("ethnicity_hispanic_or_latino", 0.18),
    ("ethnicity_choose_not_to_answer", 0.03),
    ("ethnicity_unknown", 0.04),
    ("ethnicity_unable_to_collect", 0.03),
    ("ethnicity_does_not_know", 0.05),
)
_RACE_VALUES = (
    ("race_blank", 0.01),
    ("race_american_indian_or_alaska_native", 0.01),
    ("race_another", 0.03),
    ("race_asian", 0.08),
    ("race_black_or_african_american", 0.12),
    ("race_choose_not_to_answer", 0.02),
    ("race_middle_eastern_or_northern_african", 0.02),
    ("race_native_hawaiian_or_pacific_islander", 0.01),
    ("race_does_not_know", 0.02),
    ("race_unable_to_collect", 0.02),
    ("race_unknown", 0.04),
    ("race_white", 0.62),
)


def _target(
    target_name: str,
    value: float,
    *,
    family: str = "demographics",
) -> dict[str, object]:
    denominator = 10_000
    return {
        "target_name": target_name,
        "family": family,
        "statistic": "proportion",
        "unit": "proportion",
        "status": "released",
        "value": value,
        "support_count": max(1, round(value * denominator)),
        "denominator": denominator,
        "rounding_decimals": 2,
    }


def aggregate_calibration_mapping() -> dict[str, object]:
    """Return a complete, hand-authored, released aggregate profile artifact."""

    demographic_targets = [
        *(_target(name, value) for name, value in _SEX_VALUES),
        *(_target(name, value) for name, value in _ETHNICITY_VALUES),
        *(_target(name, value) for name, value in _RACE_VALUES),
        _target("race_multiselect", 0.06),
    ]
    recorded_targets = [
        _target("healthy_flag", 0.82, family="recorded_outcome"),
        _target("growth_dx_flag", 0.08, family="recorded_outcome"),
    ]
    return {
        "artifact_version": "calibration-artifact-v1",
        "artifact_id": "cohort-aggregate-v1",
        "source_snapshot": "snapshot-v1",
        "source_partition": "calibration",
        "source_aggregate_sha256": "a" * 64,
        "schema_fingerprint": EXPECTED_SCHEMA_FINGERPRINT,
        "created_at": "2026-08-31T00:00:00Z",
        "disclosure_policy": {
            "policy_id": "cohort-disclosure-v1",
            "policy_version": "1",
            "minimum_cell_count": 1,
            "continuous_rounding_decimals": 2,
        },
        "strata": [
            {
                "stratum_id": "outcome_layer=observed",
                "dimensions": {"outcome_layer": "observed"},
                "targets": [*demographic_targets, *recorded_targets],
            }
        ],
    }


def aggregate_calibration_artifact() -> CalibrationArtifact:
    return CalibrationArtifact.from_mapping(aggregate_calibration_mapping())
