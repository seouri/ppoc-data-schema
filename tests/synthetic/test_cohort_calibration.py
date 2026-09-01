from __future__ import annotations

import json
import math
from dataclasses import replace

import pytest

from synthetic import cohort
from synthetic.calibration import CalibrationArtifact, CalibrationTarget
from synthetic.calibration_targets import TARGET_REGISTRY_VERSION
from synthetic.cohort import CalibrationSamplingProfile
from synthetic.schema_contract import EXPECTED_SCHEMA_FINGERPRINT
from tests.synthetic.cohort_fixtures import (
    aggregate_calibration_artifact,
    aggregate_calibration_mapping,
)

EXPECTED_SEX_WEIGHTS = (("F", 0.49), ("M", 0.49), ("U", 0.02))
EXPECTED_ETHNICITY_CATEGORIES = (
    "",
    "Not Hispanic or Latino",
    "Hispanic or Latino",
    "Choose not to Answer",
    "Unknown",
    "Unable to collect",
    "Patient does not know",
)
EXPECTED_RACE_CATEGORIES = (
    "",
    "American Indian or Alaska Native",
    "Another Race",
    "Asian",
    "Black or African American",
    "Choose not to answer",
    "Middle Eastern or Northern African",
    "Native Hawaiian or Other Pacific Islander",
    "Patient does not know",
    "Unable to collect",
    "Unknown",
    "White",
)


def _mapping_target(mapping: dict[str, object], target_name: str) -> dict[str, object]:
    targets = mapping["strata"][0]["targets"]  # type: ignore[index]
    return next(target for target in targets if target["target_name"] == target_name)


def _artifact_target(artifact: CalibrationArtifact, target_name: str) -> CalibrationTarget:
    return next(
        target
        for stratum in artifact.strata
        for target in stratum.targets
        if target.target_name == target_name
    )


def test_profile_extracts_complete_released_targets_in_registry_order() -> None:
    profile = CalibrationSamplingProfile.from_artifact(
        aggregate_calibration_artifact()
    )

    assert profile.artifact_id == "cohort-aggregate-v1"
    assert profile.target_registry_version == TARGET_REGISTRY_VERSION
    assert profile.sex_weights == EXPECTED_SEX_WEIGHTS
    assert tuple(category for category, _ in profile.ethnicity_weights) == (
        EXPECTED_ETHNICITY_CATEGORIES
    )
    assert tuple(category for category, _ in profile.race_weights) == (
        EXPECTED_RACE_CATEGORIES
    )
    assert math.isclose(sum(value for _, value in profile.ethnicity_weights), 1.0)
    assert math.isclose(sum(value for _, value in profile.race_weights), 1.0)
    assert profile.race_multiselect_probability == 0.06
    assert profile.recorded_healthy_probability == 0.82
    assert profile.recorded_growth_dx_probability == 0.08


def test_profile_mapping_is_aggregate_only_and_preserves_blank_cells() -> None:
    profile = CalibrationSamplingProfile.from_artifact(
        aggregate_calibration_artifact()
    )

    mapping = profile.to_mapping()
    encoded = json.dumps(mapping, sort_keys=True)

    assert mapping["ethnicity_weights"][0] == {  # type: ignore[index]
        "category": "",
        "probability": 0.02,
    }
    assert mapping["race_weights"][0] == {  # type: ignore[index]
        "category": "",
        "probability": 0.01,
    }
    for forbidden in (
        "support_count",
        "denominator",
        "source_snapshot",
        "source_partition",
        "source_aggregate_sha256",
        "schema_fingerprint",
        "created_at",
        "disclosure_policy",
        "patient_id",
        "visit_id",
        "identifier",
        "truth",
        "path",
        "key",
    ):
        assert forbidden not in encoded


def test_profile_mapping_revalidates_postconstruction_mutation() -> None:
    sensitive = "/governed/real-patient.csv truth_hash"
    profile = CalibrationSamplingProfile.from_artifact(
        aggregate_calibration_artifact()
    )
    object.__setattr__(profile, "artifact_id", sensitive)

    with pytest.raises((TypeError, ValueError), match="calibration") as error:
        profile.to_mapping()
    assert sensitive not in str(error.value)


def test_profile_preserves_released_weights_and_normalizes_only_selection() -> None:
    mapping = aggregate_calibration_mapping()
    for name in ("sex_f", "sex_m", "sex_u"):
        _mapping_target(mapping, name).update(value=0.33, support_count=3300)

    profile = CalibrationSamplingProfile.from_artifact(
        CalibrationArtifact.from_mapping(mapping)
    )

    assert profile.sex_weights == (("F", 0.33), ("M", 0.33), ("U", 0.33))
    assert profile.to_mapping()["sex_weights"] == [
        {"category": "F", "probability": 0.33},
        {"category": "M", "probability": 0.33},
        {"category": "U", "probability": 0.33},
    ]
    assert cohort._select_weighted_category(profile.sex_weights, 0.331) == "F"


@pytest.mark.parametrize(
    ("sex_f", "expected_total"),
    [(0.48, 0.99), (0.50, 1.01)],
)
def test_profile_accepts_inclusive_weight_sum_envelope_boundaries(
    sex_f: float,
    expected_total: float,
) -> None:
    mapping = aggregate_calibration_mapping()
    _mapping_target(mapping, "sex_f").update(
        value=sex_f,
        support_count=round(sex_f * 10_000),
    )

    profile = CalibrationSamplingProfile.from_artifact(
        CalibrationArtifact.from_mapping(mapping)
    )

    assert sum(value for _, value in profile.sex_weights) == pytest.approx(
        expected_total
    )


@pytest.mark.parametrize("replacement", [0.98, 1.02])
def test_profile_rejects_rounded_category_totals_outside_one_percent_envelope(
    replacement: float,
) -> None:
    mapping = aggregate_calibration_mapping()
    sex_f = replacement - 0.51
    _mapping_target(mapping, "sex_f").update(
        value=sex_f,
        support_count=round(sex_f * 10_000),
    )

    with pytest.raises(ValueError, match="sex_weights.*sum"):
        CalibrationSamplingProfile.from_artifact(
            CalibrationArtifact.from_mapping(mapping)
        )


def test_profile_requires_actual_artifact_and_exact_compatibility_metadata() -> None:
    with pytest.raises(TypeError, match="CalibrationArtifact"):
        CalibrationSamplingProfile.from_artifact({})  # type: ignore[arg-type]

    wrong_partition = aggregate_calibration_artifact()
    object.__setattr__(wrong_partition, "source_partition", "held_out")
    with pytest.raises(ValueError, match="source_partition"):
        CalibrationSamplingProfile.from_artifact(wrong_partition)

    mapping = aggregate_calibration_mapping()
    mapping["schema_fingerprint"] = "b" * 64
    with pytest.raises(ValueError, match="schema_fingerprint"):
        CalibrationSamplingProfile.from_artifact(
            CalibrationArtifact.from_mapping(mapping)
        )


def test_profile_rejects_artifact_subclasses_before_virtual_attribute_access() -> None:
    sensitive = "/governed/real-patient.csv truth_hash"

    class ArmedArtifact(CalibrationArtifact):
        def __getattribute__(self, name: str) -> object:
            if name == "source_partition":
                try:
                    armed = object.__getattribute__(self, "_armed")
                except AttributeError:
                    armed = False
                if armed:
                    raise RuntimeError(sensitive)
            return super().__getattribute__(name)

    artifact = aggregate_calibration_artifact()
    armed = ArmedArtifact(
        artifact.artifact_version,
        artifact.artifact_id,
        artifact.source_snapshot,
        artifact.source_partition,
        artifact.source_aggregate_sha256,
        artifact.schema_fingerprint,
        artifact.created_at,
        artifact.disclosure_policy,
        artifact.strata,
    )
    object.__setattr__(armed, "_armed", True)

    with pytest.raises(TypeError, match="artifact") as error:
        CalibrationSamplingProfile.from_artifact(armed)
    assert sensitive not in str(error.value)


def test_profile_requires_exactly_one_observed_outcome_stratum() -> None:
    mapping = aggregate_calibration_mapping()
    stratum = mapping["strata"][0]  # type: ignore[index]
    stratum["stratum_id"] = "outcome_layer=modeled"
    stratum["dimensions"] = {"outcome_layer": "modeled"}
    with pytest.raises(ValueError, match="exactly one.*outcome_layer=observed"):
        CalibrationSamplingProfile.from_artifact(
            CalibrationArtifact.from_mapping(mapping)
        )

    artifact = aggregate_calibration_artifact()
    object.__setattr__(artifact, "strata", (artifact.strata[0], artifact.strata[0]))
    with pytest.raises(ValueError, match="exactly one.*outcome_layer=observed"):
        CalibrationSamplingProfile.from_artifact(artifact)


def test_profile_rejects_any_target_outside_fixed_registry_without_echoing_it() -> None:
    mapping = aggregate_calibration_mapping()
    mapping["strata"][0]["targets"].append(  # type: ignore[index]
        {
            "target_name": "unregistered_metric",
            "family": "demographics",
            "statistic": "proportion",
            "unit": "proportion",
            "status": "released",
            "value": 0.5,
            "support_count": 5000,
            "denominator": 10_000,
            "rounding_decimals": 2,
        }
    )

    with pytest.raises(ValueError, match="outside the fixed registry") as error:
        CalibrationSamplingProfile.from_artifact(
            CalibrationArtifact.from_mapping(mapping)
        )
    assert "unregistered_metric" not in str(error.value)


def test_profile_rejects_missing_duplicate_and_suppressed_required_targets() -> None:
    missing = aggregate_calibration_mapping()
    targets = missing["strata"][0]["targets"]  # type: ignore[index]
    targets[:] = [target for target in targets if target["target_name"] != "sex_u"]
    with pytest.raises(ValueError, match="sex_u.*missing"):
        CalibrationSamplingProfile.from_artifact(
            CalibrationArtifact.from_mapping(missing)
        )

    duplicate = aggregate_calibration_artifact()
    stratum = duplicate.strata[0]
    object.__setattr__(stratum, "targets", (*stratum.targets, stratum.targets[0]))
    with pytest.raises(ValueError, match="duplicate.*target"):
        CalibrationSamplingProfile.from_artifact(duplicate)

    suppressed = aggregate_calibration_mapping()
    _mapping_target(suppressed, "race_blank").update(
        status="suppressed",
        value=None,
        support_count=None,
        denominator=None,
        rounding_decimals=0,
    )
    with pytest.raises(ValueError, match="race_blank.*released"):
        CalibrationSamplingProfile.from_artifact(
            CalibrationArtifact.from_mapping(suppressed)
        )


def test_profile_rejects_semantically_malformed_required_targets() -> None:
    non_proportion = aggregate_calibration_mapping()
    _mapping_target(non_proportion, "healthy_flag").update(
        statistic="mean",
        denominator=None,
    )
    with pytest.raises(ValueError, match="outside the fixed registry"):
        CalibrationSamplingProfile.from_artifact(
            CalibrationArtifact.from_mapping(non_proportion)
        )

    null_denominator = aggregate_calibration_artifact()
    object.__setattr__(
        _artifact_target(null_denominator, "growth_dx_flag"), "denominator", None
    )
    with pytest.raises(ValueError, match="growth_dx_flag.*denominator"):
        CalibrationSamplingProfile.from_artifact(null_denominator)

    nonfinite = aggregate_calibration_artifact()
    object.__setattr__(_artifact_target(nonfinite, "sex_f"), "value", math.nan)
    with pytest.raises(ValueError, match="sex_f.*finite"):
        CalibrationSamplingProfile.from_artifact(nonfinite)

    out_of_range = aggregate_calibration_artifact()
    object.__setattr__(_artifact_target(out_of_range, "race_white"), "value", 1.1)
    with pytest.raises(ValueError, match=r"race_white.*\[0, 1\]"):
        CalibrationSamplingProfile.from_artifact(out_of_range)


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("denominator", 0),
        ("denominator", True),
        ("denominator", -1),
        ("support_count", True),
        ("support_count", -1),
        ("support_count", 10_001),
    ],
)
def test_profile_rejects_invalid_denominator_and_support_bounds(
    field_name: str,
    bad_value: object,
) -> None:
    artifact = aggregate_calibration_artifact()
    object.__setattr__(_artifact_target(artifact, "sex_f"), field_name, bad_value)

    with pytest.raises(ValueError, match="sex_f.*denominator|sex_f.*support"):
        CalibrationSamplingProfile.from_artifact(artifact)


def test_profile_rejects_inconsistent_ratio_and_cross_cell_denominator() -> None:
    inconsistent_ratio = aggregate_calibration_mapping()
    _mapping_target(inconsistent_ratio, "sex_f")["support_count"] = 3900
    with pytest.raises(ValueError, match="sex_f.*support_count.*denominator"):
        CalibrationSamplingProfile.from_artifact(
            CalibrationArtifact.from_mapping(inconsistent_ratio)
        )

    inconsistent_denominator = aggregate_calibration_mapping()
    _mapping_target(inconsistent_denominator, "sex_f").update(
        denominator=20_000,
        support_count=9800,
    )
    with pytest.raises(ValueError, match="denominators must match"):
        CalibrationSamplingProfile.from_artifact(
            CalibrationArtifact.from_mapping(inconsistent_denominator)
        )


def test_profile_accepts_value_consistent_at_declared_rounding_precision() -> None:
    mapping = aggregate_calibration_mapping()
    _mapping_target(mapping, "race_multiselect").update(
        value=0.06,
        support_count=649,
    )

    profile = CalibrationSamplingProfile.from_artifact(
        CalibrationArtifact.from_mapping(mapping)
    )

    assert profile.race_multiselect_probability == 0.06


def test_recorded_outcomes_remain_evidence_and_do_not_change_sampling_weights() -> None:
    first = aggregate_calibration_mapping()
    second = aggregate_calibration_mapping()
    _mapping_target(second, "healthy_flag").update(value=0.2, support_count=2000)
    _mapping_target(second, "growth_dx_flag").update(
        value=0.7,
        support_count=7000,
    )

    left = CalibrationSamplingProfile.from_artifact(
        CalibrationArtifact.from_mapping(first)
    )
    right = CalibrationSamplingProfile.from_artifact(
        CalibrationArtifact.from_mapping(second)
    )

    assert left.sex_weights == right.sex_weights
    assert left.ethnicity_weights == right.ethnicity_weights
    assert left.race_weights == right.race_weights
    assert "module" not in json.dumps(right.to_mapping(), sort_keys=True)
    assert right.recorded_healthy_probability == 0.2
    assert right.recorded_growth_dx_probability == 0.7


def test_private_sampling_and_projection_helpers_use_fixed_visible_rules() -> None:
    weights = (("first", 0.25), ("second", 0.75))

    assert cohort._select_weighted_category(weights, 0.0) == "first"
    assert cohort._select_weighted_category(weights, 0.249999) == "first"
    assert cohort._select_weighted_category(weights, 0.25) == "second"
    assert cohort._select_weighted_category(weights, 0.999999) == "second"
    assert cohort._project_visible_category("") == "Unknown"
    assert cohort._project_visible_category("White") == "White"
    assert cohort._project_race_slots("", None) == ("Unknown",) * 8
    assert cohort._project_race_slots("White", "Asian") == (
        "White",
        "Asian",
        "Unknown",
        "Unknown",
        "Unknown",
        "Unknown",
        "Unknown",
        "Unknown",
    )


def test_public_profile_constructor_requires_fixed_registry_categories_and_totals() -> None:
    profile = CalibrationSamplingProfile.from_artifact(
        aggregate_calibration_artifact()
    )

    with pytest.raises(ValueError, match="target_registry_version"):
        replace(profile, target_registry_version="calibration-targets-v9")
    for field_name, bad_weights in (
        ("sex_weights", profile.sex_weights[:-1]),
        ("ethnicity_weights", tuple(reversed(profile.ethnicity_weights))),
        ("race_weights", (*profile.race_weights, ("Extra", 0.0))),
        ("sex_weights", (("/real/patient.csv", 0.49), *profile.sex_weights[1:])),
        ("ethnicity_weights", (("truth", 0.02), *profile.ethnicity_weights[1:])),
        ("race_weights", (("identifier", 0.01), *profile.race_weights[1:])),
    ):
        with pytest.raises(ValueError, match=field_name) as error:
            replace(profile, **{field_name: bad_weights})
        assert "/real/patient.csv" not in str(error.value)
        assert "truth" not in str(error.value)
        assert "identifier" not in str(error.value)

    for total, first_value in ((0.98, 0.47), (1.02, 0.51)):
        invalid = (("F", first_value), *profile.sex_weights[1:])
        assert sum(value for _, value in invalid) == pytest.approx(total)
        with pytest.raises(ValueError, match="sex_weights.*sum"):
            replace(profile, sex_weights=invalid)

    assert repr(profile) == "CalibrationSamplingProfile(<aggregate-only>)"
    assert profile.artifact_id not in repr(profile)


@pytest.mark.parametrize(
    ("mutation", "secret"),
    [
        ("target_name", "/private/real-patient.csv"),
        ("target_family", "patient-secret"),
        ("target_value", "/private/key/truth.csv"),
        ("stratum_id", "/private/real-patient.csv"),
        ("dimensions", "/private/key/truth.csv"),
        ("duplicate_stratum", "/private/real-patient.csv"),
    ],
)
def test_profile_errors_never_echo_malicious_postconstruction_values(
    mutation: str,
    secret: str,
) -> None:
    artifact = aggregate_calibration_artifact()
    target = _artifact_target(artifact, "sex_f")
    stratum = artifact.strata[0]
    if mutation == "target_name":
        object.__setattr__(target, "target_name", secret)
    elif mutation == "target_family":
        object.__setattr__(target, "family", secret)
    elif mutation == "target_value":
        object.__setattr__(target, "value", secret)
    elif mutation == "stratum_id":
        object.__setattr__(stratum, "stratum_id", secret)
    elif mutation == "dimensions":
        object.__setattr__(stratum, "dimensions", (("outcome_layer", secret),))
    else:
        extra = aggregate_calibration_artifact().strata[0]
        object.__setattr__(extra, "stratum_id", secret)
        object.__setattr__(extra, "targets", (extra.targets[0], extra.targets[0]))
        object.__setattr__(artifact, "strata", (*artifact.strata, extra))

    with pytest.raises((TypeError, ValueError)) as error:
        CalibrationSamplingProfile.from_artifact(artifact)
    assert secret not in str(error.value)
    for forbidden in ("/private", "patient", "key", "truth", ".csv"):
        assert forbidden not in str(error.value).lower()


def test_fixture_uses_checked_in_schema_contract() -> None:
    assert aggregate_calibration_artifact().schema_fingerprint == (
        EXPECTED_SCHEMA_FINGERPRINT
    )
