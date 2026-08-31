from copy import deepcopy
from dataclasses import FrozenInstanceError

import pytest

from synthetic.calibration import ARTIFACT_VERSION, CalibrationArtifact


def valid_mapping() -> dict[str, object]:
    return {
        "artifact_version": "calibration-artifact-v1",
        "artifact_id": "calibration-2026-08-24-v1",
        "source_snapshot": "2026-08-24",
        "source_partition": "calibration",
        "source_aggregate_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "schema_fingerprint": "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210",
        "created_at": "2026-08-30T00:00:00Z",
        "disclosure_policy": {
            "policy_id": "policy-example-v1",
            "policy_version": "1",
            "minimum_cell_count": 10,
            "continuous_rounding_decimals": 3,
        },
        "strata": [
            {
                "stratum_id": "age_regime=infancy|reference_sex=F",
                "dimensions": {"reference_sex": "F", "age_regime": "infancy"},
                "targets": [
                    {
                        "target_name": "height_z",
                        "family": "physiology",
                        "statistic": "mean",
                        "unit": "z",
                        "status": "released",
                        "value": -0.03,
                        "support_count": 120,
                        "denominator": 120,
                        "rounding_decimals": 3,
                    }
                ],
            }
        ],
    }


def valid_mapping_with_target(**changes: object) -> dict[str, object]:
    value = valid_mapping()
    target = value["strata"][0]["targets"][0]  # type: ignore[index]
    target.update(changes)  # type: ignore[union-attr]
    return value


def valid_mapping_with_strata_and_targets_in_reverse_order() -> dict[str, object]:
    value = valid_mapping()
    value["strata"] = [
        {
            "stratum_id": "age_regime=infancy|reference_sex=M",
            "dimensions": {"reference_sex": "M", "age_regime": "infancy"},
            "targets": [
                {
                    "target_name": "service_rate",
                    "family": "utilization",
                    "statistic": "rate",
                    "unit": "per_year",
                    "status": "released",
                    "value": 0.3,
                    "support_count": 40,
                    "denominator": 120,
                    "rounding_decimals": 3,
                },
                {
                    "target_name": "height_z",
                    "family": "physiology",
                    "statistic": "mean",
                    "unit": "z",
                    "status": "released",
                    "value": -0.03,
                    "support_count": 120,
                    "denominator": 120,
                    "rounding_decimals": 3,
                },
            ],
        },
        value["strata"][0],
    ]
    return value


def test_valid_mapping_builds_frozen_artifact_and_canonical_shape() -> None:
    artifact = CalibrationArtifact.from_mapping(valid_mapping())

    assert artifact.artifact_version == "calibration-artifact-v1"
    assert artifact.strata[0].dimensions == (
        ("age_regime", "infancy"),
        ("reference_sex", "F"),
    )
    assert artifact.strata[0].stratum_id == "age_regime=infancy|reference_sex=F"
    assert artifact.strata[0].targets[0].value == -0.03
    assert artifact.to_mapping() == valid_mapping()
    assert artifact.to_mapping() is not artifact.to_mapping()
    assert isinstance(artifact.strata, tuple)
    assert isinstance(artifact.strata[0].targets, tuple)
    with pytest.raises(FrozenInstanceError):
        artifact.artifact_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("identifier", ["SYN-P-001", "SYN-V-001"])
@pytest.mark.parametrize(
    "metadata_channel",
    [
        "artifact_id",
        "source_snapshot",
        "disclosure_policy_id",
        "disclosure_policy_version",
        "age_regime",
        "target_name",
        "unit",
    ],
)
def test_artifact_rejects_fixture_identifiers_in_serialized_metadata(
    identifier: str, metadata_channel: str
) -> None:
    value = valid_mapping()
    if metadata_channel in {"artifact_id", "source_snapshot"}:
        value[metadata_channel] = identifier
    elif metadata_channel.startswith("disclosure_policy_"):
        policy_field = metadata_channel.removeprefix("disclosure_")
        value["disclosure_policy"][policy_field] = identifier  # type: ignore[index]
    elif metadata_channel == "age_regime":
        value["strata"][0]["dimensions"]["age_regime"] = identifier  # type: ignore[index]
        value["strata"][0]["stratum_id"] = f"age_regime={identifier}|reference_sex=F"  # type: ignore[index]
    else:
        value["strata"][0]["targets"][0][metadata_channel] = identifier  # type: ignore[index]

    with pytest.raises(ValueError, match="aggregate|identifier|record"):
        CalibrationArtifact.from_mapping(value)


def test_mapping_normalizes_stratum_and_target_order() -> None:
    value = valid_mapping_with_strata_and_targets_in_reverse_order()

    artifact = CalibrationArtifact.from_mapping(value)

    assert [stratum.stratum_id for stratum in artifact.strata] == sorted(
        stratum["stratum_id"] for stratum in value["strata"]  # type: ignore[index]
    )
    assert [target.target_name for target in artifact.strata[-1].targets] == [
        "height_z",
        "service_rate",
    ]


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda value: value.__setitem__("source_path", "real/data"), "keys"),
        (
            lambda value: value["strata"][0]["targets"][0].__setitem__("patient_id", "P1"),  # type: ignore[index]
            "keys",
        ),
        (lambda value: value.pop("artifact_id"), "keys"),
        (lambda value: value.__setitem__("strata", []), "strata"),
        (
            lambda value: value["strata"][0]["targets"].append(  # type: ignore[index]
                deepcopy(value["strata"][0]["targets"][0])  # type: ignore[index]
            ),
            "duplicate target",
        ),
    ],
)
def test_mapping_rejects_missing_unknown_or_duplicate_shape(
    mutate: object, match: str
) -> None:
    value = valid_mapping()
    mutate(value)  # type: ignore[operator]

    with pytest.raises(ValueError, match=match):
        CalibrationArtifact.from_mapping(value)


@pytest.mark.parametrize(
    "value",
    [
        [],
        {"artifact_version": ARTIFACT_VERSION},
        {**valid_mapping(), "disclosure_policy": "not-an-object"},
        {**valid_mapping(), "strata": "not-a-list"},
        {
            **valid_mapping(),
            "strata": [{**valid_mapping()["strata"][0], "dimensions": []}],  # type: ignore[index]
        },
        {
            **valid_mapping(),
            "strata": [{**valid_mapping()["strata"][0], "targets": {}}],  # type: ignore[index]
        },
    ],
)
def test_mapping_rejects_wrong_root_and_nested_types(value: object) -> None:
    with pytest.raises(ValueError):
        CalibrationArtifact.from_mapping(value)


@pytest.mark.parametrize(
    ("field", "replacement", "match"),
    [
        ("artifact_version", "calibration-artifact-v2", "artifact_version"),
        ("source_partition", "training", "source_partition"),
        ("source_aggregate_sha256", "A" * 64, "sha256"),
        ("schema_fingerprint", "g" * 64, "sha256"),
        ("created_at", "2026-02-30T00:00:00Z", "created_at"),
        ("artifact_id", "calibration/path", "artifact_id"),
    ],
)
def test_artifact_transport_values_fail_closed(
    field: str, replacement: object, match: str
) -> None:
    value = valid_mapping()
    value[field] = replacement

    with pytest.raises(ValueError, match=match):
        CalibrationArtifact.from_mapping(value)


def test_stratum_rejects_reserved_values_excess_dimensions_and_noncanonical_id() -> None:
    reserved = valid_mapping()
    reserved["strata"][0]["dimensions"]["age_regime"] = "latent"  # type: ignore[index]
    too_many = valid_mapping()
    too_many["strata"][0]["dimensions"].update(  # type: ignore[index]
        {"race": "A", "ethnicity": "B", "encounter_type": "C"}
    )
    noncanonical = valid_mapping()
    noncanonical["strata"][0]["stratum_id"] = "reference_sex=F|age_regime=infancy"  # type: ignore[index]

    for value in (reserved, too_many, noncanonical):
        with pytest.raises(ValueError):
            CalibrationArtifact.from_mapping(value)


def test_suppressed_target_is_explicitly_null_and_not_zero() -> None:
    value = valid_mapping()
    target = value["strata"][0]["targets"][0]  # type: ignore[index]
    target.update(  # type: ignore[union-attr]
        statistic="proportion",
        status="suppressed",
        value=None,
        support_count=None,
        denominator=None,
        rounding_decimals=0,
    )

    parsed = CalibrationArtifact.from_mapping(value)

    assert parsed.strata[0].targets[0].value is None
    assert parsed.strata[0].targets[0].support_count is None


@pytest.mark.parametrize(
    ("statistic", "value"),
    [
        ("count", 1.5),
        ("proportion", 1.01),
        ("sd", -0.1),
        ("rate", -1.0),
    ],
)
def test_statistic_domains_fail_closed(statistic: str, value: object) -> None:
    mapping = valid_mapping_with_target(statistic=statistic, value=value)

    with pytest.raises(ValueError, match="value|statistic"):
        CalibrationArtifact.from_mapping(mapping)


def test_quantile_requires_level_and_other_statistics_omit_it() -> None:
    missing_level = valid_mapping_with_target(statistic="quantile")
    present_on_mean = valid_mapping_with_target(quantile_level=0.5)
    valid_quantile = valid_mapping_with_target(statistic="quantile", quantile_level=0.5)

    for value in (missing_level, present_on_mean):
        with pytest.raises(ValueError, match="quantile_level"):
            CalibrationArtifact.from_mapping(value)
    assert CalibrationArtifact.from_mapping(valid_quantile).strata[0].targets[0].quantile_level == 0.5


@pytest.mark.parametrize(
    "changes",
    [
        {"support_count": 9},
        {"denominator": 0},
        {"support_count": 121, "denominator": 120},
        {"statistic": "count", "value": 12, "rounding_decimals": 1},
        {"rounding_decimals": 4},
    ],
)
def test_released_target_enforces_disclosure_support_denominator_and_precision(
    changes: dict[str, object]
) -> None:
    with pytest.raises(ValueError):
        CalibrationArtifact.from_mapping(valid_mapping_with_target(**changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"minimum_cell_count": 0},
        {"minimum_cell_count": True},
        {"continuous_rounding_decimals": 10},
        {"continuous_rounding_decimals": True},
    ],
)
def test_policy_requires_positive_integer_floor_and_bounded_precision(
    changes: dict[str, object]
) -> None:
    value = valid_mapping()
    value["disclosure_policy"].update(changes)  # type: ignore[union-attr]

    with pytest.raises(ValueError):
        CalibrationArtifact.from_mapping(value)


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"value": True}, "value"),
        ({"support_count": True}, "support_count"),
        ({"denominator": True}, "denominator"),
        ({"value": float("inf")}, "value"),
        ({"statistic": "quantile", "quantile_level": float("nan")}, "quantile_level"),
        ({"statistic": "proportion", "value": 0.5, "denominator": None}, "denominator"),
        ({"statistic": "rate", "value": 0.5, "denominator": None}, "denominator"),
    ],
)
def test_numeric_values_are_strict_and_required_statistic_denominators_are_positive(
    changes: dict[str, object], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        CalibrationArtifact.from_mapping(valid_mapping_with_target(**changes))


def test_non_count_values_and_quantile_levels_normalize_to_float() -> None:
    mean = CalibrationArtifact.from_mapping(valid_mapping_with_target(value=1))
    quantile = CalibrationArtifact.from_mapping(
        valid_mapping_with_target(statistic="quantile", value=1, quantile_level=0)
    )

    assert mean.strata[0].targets[0].value == 1.0
    assert isinstance(mean.strata[0].targets[0].value, float)
    assert quantile.strata[0].targets[0].quantile_level == 0.0


@pytest.mark.parametrize(
    "family",
    ["latent", "truth", "patient", "sequence", "candidate", "match", "row", "resource"],
)
def test_target_family_rejects_hidden_or_record_like_indicators(family: str) -> None:
    with pytest.raises(ValueError, match="family"):
        CalibrationArtifact.from_mapping(valid_mapping_with_target(family=family))


@pytest.mark.parametrize(
    "target_name",
    [
        "latent",
        "truth",
        "patient",
        "visit_rate",
        "sequence",
        "candidate",
        "match",
        "row",
        "resource",
    ],
)
def test_target_name_rejects_hidden_or_record_like_indicators(target_name: str) -> None:
    with pytest.raises(ValueError, match="target_name"):
        CalibrationArtifact.from_mapping(valid_mapping_with_target(target_name=target_name))


def test_target_name_accepts_approved_growth_dx_flag_without_weakening_component_guards() -> None:
    artifact = CalibrationArtifact.from_mapping(
        valid_mapping_with_target(target_name="growth_dx_flag")
    )

    assert artifact.strata[0].targets[0].target_name == "growth_dx_flag"
    for unsafe in (
        "row",
        "height_row_mean",
        "heightRowMean",
        "ABCRowMetric",
        "patient_count",
        "APIKeyMetric",
        "SYN-P-001",
        "target.csv",
        "privacyAuditScore",
    ):
        with pytest.raises(ValueError, match="target_name"):
            CalibrationArtifact.from_mapping(valid_mapping_with_target(target_name=unsafe))


@pytest.mark.parametrize(
    "target_name",
    [
        "membership_inference_risk",
        "linkage_score",
        "Privacy_Attack_Score",
        "attribute_inference_score",
        "Attribute_Disclosure",
        "composition",
        "differential_privacy",
        "model_inversion_risk",
        "privacy_audit",
        "reidentification_score",
        "singling_out_risk",
    ],
)
def test_target_name_rejects_attack_and_privacy_outputs(target_name: str) -> None:
    with pytest.raises(ValueError, match="target_name"):
        CalibrationArtifact.from_mapping(valid_mapping_with_target(target_name=target_name))


def test_model_rejects_overflowing_numeric_value_as_controlled_validation_error() -> None:
    with pytest.raises(ValueError, match="value must be a finite number") as error:
        CalibrationArtifact.from_mapping(valid_mapping_with_target(value=10**400))

    assert error.value.__cause__ is None
