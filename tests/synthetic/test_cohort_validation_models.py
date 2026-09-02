from __future__ import annotations

import dataclasses
import json
import math
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType

import pytest

from synthetic.cohort_validation import (
    COHORT_VALIDATION_REPORT_VERSION,
    GROWTH_TOLERANCE_KEYS,
    CohortComparison,
    CohortValidationPolicy,
    CohortValidationReport,
    CohortValidationStatus,
    validate_native_cohort,
)
from synthetic.models import DisorderKind


def valid_policy(**changes: object) -> CohortValidationPolicy:
    values: dict[str, object] = {
        "policy_id": "cohort-profile-v1",
        "policy_version": "1",
        "minimum_cohort_size": 10,
        "minimum_cell_support": 2,
        "minimum_event_support": 2,
        "proportion_tolerance": 0.05,
        "growth_tolerances": {
            "height_z_score": 2.0,
            "bmi_z_score": 2.0,
            "height_velocity_cm_per_year": 1.0,
            "weight_velocity_kg_per_year": 1.0,
        },
        "required_age_windows": (
            ("infant", 0, 730),
            ("childhood", 730, 4380),
        ),
    }
    values.update(changes)
    return CohortValidationPolicy(**values)  # type: ignore[arg-type]


def targeted_comparison(**changes: object) -> CohortComparison:
    values: dict[str, object] = {
        "name": "demographics.sex.F",
        "layer": "demographics",
        "status": CohortValidationStatus.PASS,
        "observed_value": 0.5,
        "target_value": 0.5,
        "difference": 0.0,
        "tolerance": 0.05,
        "support": 5,
        "denominator": 10,
        "reason_code": "WITHIN_TOLERANCE",
    }
    values.update(changes)
    return CohortComparison(**values)  # type: ignore[arg-type]


def status_only_comparison(**changes: object) -> CohortComparison:
    values: dict[str, object] = {
        "name": "latent_module.healthy",
        "layer": "latent",
        "status": CohortValidationStatus.PASS,
        "observed_value": 0.8,
        "target_value": None,
        "difference": None,
        "tolerance": None,
        "support": 8,
        "denominator": 10,
        "reason_code": "OBSERVED",
    }
    values.update(changes)
    return CohortComparison(**values)  # type: ignore[arg-type]


def unevaluable_comparison(**changes: object) -> CohortComparison:
    values: dict[str, object] = {
        "name": "growth.infant.height_z_score_mean",
        "layer": "growth",
        "status": CohortValidationStatus.UNEVALUABLE,
        "observed_value": None,
        "target_value": None,
        "difference": None,
        "tolerance": None,
        "support": 0,
        "denominator": 0,
        "reason_code": "INSUFFICIENT_SUPPORT",
    }
    values.update(changes)
    return CohortComparison(**values)  # type: ignore[arg-type]


def test_status_and_growth_registries_are_fixed() -> None:
    assert tuple(status.value for status in CohortValidationStatus) == (
        "PASS",
        "FAIL",
        "UNEVALUABLE",
    )
    assert GROWTH_TOLERANCE_KEYS == (
        "height_z_score",
        "bmi_z_score",
        "height_velocity_cm_per_year",
        "weight_velocity_kg_per_year",
    )
    assert tuple(kind.value for kind in DisorderKind) == (
        "healthy",
        "familial_short_stature",
        "constitutional_delay",
        "growth_hormone_deficiency",
        "pediatric_hypothyroidism",
        "celiac_disease",
        "small_for_gestational_age",
        "turner_syndrome",
    )


def test_policy_freezes_mappings_and_normalizes_age_windows() -> None:
    policy = valid_policy(growth_tolerances=dict(valid_policy().growth_tolerances))

    assert isinstance(policy.growth_tolerances, MappingProxyType)
    assert policy.required_age_windows == (
        ("infant", 0, 730),
        ("childhood", 730, 4380),
    )
    with pytest.raises(TypeError):
        policy.growth_tolerances["height_z_score"] = 3.0  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.policy_id = "other"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("policy_id", "patient-policy"),
        ("policy_version", "../version"),
        ("minimum_cohort_size", True),
        ("minimum_cohort_size", 0),
        ("minimum_cell_support", -1),
        ("minimum_event_support", 1.5),
        ("proportion_tolerance", True),
        ("proportion_tolerance", -0.01),
        ("proportion_tolerance", math.nan),
        ("proportion_tolerance", math.inf),
    ],
)
def test_policy_rejects_unsafe_or_invalid_scalar_values(field: str, value: object) -> None:
    with pytest.raises((TypeError, ValueError), match=field):
        valid_policy(**{field: value})


@pytest.mark.parametrize(
    "growth_tolerances",
    [
        {},
        {"height_z_score": 1.0},
        {
            "height_z_score": 1.0,
            "bmi_z_score": 1.0,
            "height_velocity_cm_per_year": 1.0,
            "weight_velocity_kg_per_year": 1.0,
            "extra": 1.0,
        },
        {
            "height_z_score": -1.0,
            "bmi_z_score": 1.0,
            "height_velocity_cm_per_year": 1.0,
            "weight_velocity_kg_per_year": 1.0,
        },
        {
            "height_z_score": math.nan,
            "bmi_z_score": 1.0,
            "height_velocity_cm_per_year": 1.0,
            "weight_velocity_kg_per_year": 1.0,
        },
    ],
)
def test_policy_rejects_unknown_or_invalid_growth_tolerances(
    growth_tolerances: dict[str, float],
) -> None:
    with pytest.raises((TypeError, ValueError), match="growth_tolerances"):
        valid_policy(growth_tolerances=growth_tolerances)


@pytest.mark.parametrize("number", [Fraction(1, 2), Decimal("0.5")])
def test_policy_rejects_non_json_numeric_types(number: object) -> None:
    with pytest.raises((TypeError, ValueError), match="proportion_tolerance"):
        valid_policy(proportion_tolerance=number)
    tolerances = dict(valid_policy().growth_tolerances)
    tolerances["height_z_score"] = number  # type: ignore[assignment]
    with pytest.raises((TypeError, ValueError), match="growth_tolerances"):
        valid_policy(growth_tolerances=tolerances)


@pytest.mark.parametrize(
    "windows",
    [
        (),
        [],
        (("bad window", 0, 730),),
        (("patient-window", 0, 730),),
        (("infant", True, 730),),
        (("infant", 730, 730),),
        (("infant", 800, 730),),
        (("infant", 0, -1),),
        (("infant", 730, 1000), ("childhood", 0, 730)),
        (("infant", 0, 730), ("infant", 730, 1000)),
    ],
)
def test_policy_rejects_empty_malformed_or_noncanonical_windows(
    windows: object,
) -> None:
    with pytest.raises((TypeError, ValueError), match="required_age_windows"):
        valid_policy(required_age_windows=windows)


def test_comparison_targeted_difference_and_status_are_consistent() -> None:
    comparison = targeted_comparison(
        observed_value=0.7,
        target_value=0.5,
        difference=abs(0.7 - 0.5),
        tolerance=0.2,
    )

    assert comparison.difference == abs(0.7 - 0.5)
    assert comparison.status is CohortValidationStatus.PASS
    assert comparison.to_mapping() == {
        "name": "demographics.sex.F",
        "layer": "demographics",
        "status": "PASS",
        "observed_value": 0.7,
        "target_value": 0.5,
        "difference": abs(0.7 - 0.5),
        "tolerance": 0.2,
        "support": 5,
        "denominator": 10,
        "reason_code": "WITHIN_TOLERANCE",
    }


def test_comparison_allows_status_only_aggregate_diagnostic() -> None:
    comparison = status_only_comparison()

    assert comparison.target_value is None
    assert comparison.difference is None
    assert comparison.tolerance is None
    assert comparison.to_mapping()["status"] == "PASS"


def test_unevaluable_comparison_requires_null_numeric_values() -> None:
    assert unevaluable_comparison().to_mapping()["observed_value"] is None
    with pytest.raises(ValueError, match="UNEVALUABLE"):
        unevaluable_comparison(observed_value=0.0)
    with pytest.raises(ValueError, match="UNEVALUABLE"):
        unevaluable_comparison(difference=0.0)


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "patient_profile"},
        {"name": "growth.infant.unknown_mean"},
        {"layer": "unknown"},
        {"reason_code": "unknown"},
        {"status": "PASS"},
        {"support": True},
        {"support": -1},
        {"denominator": True},
        {"support": 11},
        {"difference": math.nan},
        {"tolerance": math.inf},
    ],
)
def test_comparison_rejects_unsafe_registry_or_numeric_values(changes: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        targeted_comparison(**changes)


@pytest.mark.parametrize("number", [Fraction(1, 2), Decimal("0.5")])
def test_comparison_rejects_non_json_numeric_types(number: object) -> None:
    with pytest.raises((TypeError, ValueError), match="observed_value"):
        targeted_comparison(observed_value=number)
    with pytest.raises((TypeError, ValueError), match="target_value"):
        targeted_comparison(target_value=number)


@pytest.mark.parametrize(
    ("name", "layer"),
    [
        ("demographics.sex.X", "demographics"),
        ("demographics.ethnicity.arbitrary", "demographics"),
        ("coverage.unknown", "coverage"),
        ("coverage.members_with_recorded_event", "coverage"),
        ("cohort_size", "coverage"),
    ],
)
def test_comparison_rejects_unknown_names_and_inconsistent_cohort_layer(
    name: str, layer: str
) -> None:
    with pytest.raises((TypeError, ValueError), match="(name|layer)"):
        targeted_comparison(name=name, layer=layer)


def test_comparison_rejects_inconsistent_targeted_status_and_reason() -> None:
    with pytest.raises(ValueError, match="status"):
        targeted_comparison(
            observed_value=0.8,
            target_value=0.5,
            difference=0.3,
            tolerance=0.05,
            status=CohortValidationStatus.PASS,
            reason_code="OUTSIDE_TOLERANCE",
        )
    with pytest.raises(ValueError, match="difference"):
        targeted_comparison(difference=0.1)
    with pytest.raises(ValueError, match="reason"):
        targeted_comparison(reason_code="OUTSIDE_TOLERANCE")


def test_report_canonicalizes_order_and_has_an_aggregate_only_mapping() -> None:
    comparisons = (
        status_only_comparison(),
        targeted_comparison(),
        unevaluable_comparison(),
    )
    report = CohortValidationReport(
        report_version=COHORT_VALIDATION_REPORT_VERSION,
        policy_id="cohort-profile-v1",
        cohort_profile="development-v1",
        seed=7,
        status=CohortValidationStatus.UNEVALUABLE,
        comparisons=comparisons,
    )

    assert [item.name for item in report.comparisons] == [
        "demographics.sex.F",
        "latent_module.healthy",
        "growth.infant.height_z_score_mean",
    ]
    mapping = report.to_mapping()
    assert set(mapping) == {
        "report_version",
        "policy_id",
        "cohort_profile",
        "seed",
        "status",
        "comparisons",
    }
    assert mapping["status"] == "UNEVALUABLE"
    encoded = json.dumps(mapping, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert encoded == json.dumps(report.to_mapping(), sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert "syn-" not in repr(report)
    assert "truth" not in repr(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.status = CohortValidationStatus.PASS  # type: ignore[misc]


def test_report_rejects_empty_comparison_sets() -> None:
    with pytest.raises(ValueError, match="nonempty"):
        CohortValidationReport(
            report_version=COHORT_VALIDATION_REPORT_VERSION,
            policy_id="cohort-profile-v1",
            cohort_profile="development-v1",
            seed=7,
            status=CohortValidationStatus.PASS,
            comparisons=(),
        )


@pytest.mark.parametrize(
    "status",
    [CohortValidationStatus.PASS, CohortValidationStatus.FAIL],
)
def test_report_status_must_match_comparison_precedence(status: CohortValidationStatus) -> None:
    comparison_status = CohortValidationStatus.FAIL
    report = CohortValidationReport(
        report_version=COHORT_VALIDATION_REPORT_VERSION,
        policy_id="cohort-profile-v1",
        cohort_profile="development-v1",
        seed=7,
        status=CohortValidationStatus.FAIL,
        comparisons=(
            targeted_comparison(
                status=comparison_status,
                reason_code="OUTSIDE_TOLERANCE",
                observed_value=0.9,
                difference=abs(0.9 - 0.5),
                tolerance=0.05,
            ),
        ),
    )
    if status is CohortValidationStatus.PASS:
        with pytest.raises(ValueError, match="status"):
            dataclasses.replace(report, status=status)


def test_validate_native_cohort_requires_a_native_cohort() -> None:
    with pytest.raises(TypeError, match="cohort"):
        validate_native_cohort(object(), valid_policy())  # type: ignore[arg-type]
