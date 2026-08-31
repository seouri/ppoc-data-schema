from __future__ import annotations

import dataclasses

import pytest

from synthetic.cohort import (
    CalibrationSamplingProfile,
    CohortConfig,
    CohortModuleWeight,
    generate_native_cohort,
)
from synthetic.cohort_validation import (
    CohortComparison,
    CohortValidationPolicy,
    CohortValidationStatus,
    validate_native_cohort,
)
from synthetic.models import DisorderKind
from synthetic.native.clinical_modules import (
    GrowthHormoneDeficiencyModule,
    HealthyGrowthModule,
)
from synthetic.native.observations import ObservationPolicy, RecordedEventKind
from tests.synthetic.cohort_fixtures import aggregate_calibration_artifact
from tests.synthetic.fakes import RegimeLinearTestReference

_AGES = (0, 365, 730, 1460, 2190, 3650, 4380, 5110, 6200)


def _calibration() -> CalibrationSamplingProfile:
    return CalibrationSamplingProfile.from_artifact(aggregate_calibration_artifact())


def _modules() -> dict[DisorderKind, object]:
    return {
        DisorderKind.HEALTHY: HealthyGrowthModule(),
        DisorderKind.GROWTH_HORMONE_DEFICIENCY: GrowthHormoneDeficiencyModule(),
    }


def _config(**changes: object) -> CohortConfig:
    values: dict[str, object] = {
        "profile": "development-v1",
        "patient_count": 48,
        "seed": 20260831,
        "ages_days": _AGES,
        "observation_policy": ObservationPolicy(
            "cohort-observation-v1",
            0,
            6201,
        ),
        "module_weights": (
            CohortModuleWeight(DisorderKind.HEALTHY, 0.5),
            CohortModuleWeight(DisorderKind.GROWTH_HORMONE_DEFICIENCY, 0.5),
        ),
        "reference_sex_mapping": (("F", "F"), ("M", "M"), ("U", "U")),
    }
    values.update(changes)
    return CohortConfig(**values)  # type: ignore[arg-type]


def _policy(**changes: object) -> CohortValidationPolicy:
    values: dict[str, object] = {
        "policy_id": "cohort-profile-v1",
        "policy_version": "1",
        "minimum_cohort_size": 1,
        "minimum_cell_support": 1,
        "minimum_event_support": 1,
        "proportion_tolerance": 1.0,
        "growth_tolerances": {
            "height_z_score": 2.0,
            "bmi_z_score": 2.0,
            "height_velocity_cm_per_year": 1.0,
            "weight_velocity_kg_per_year": 1.0,
        },
        "required_age_windows": (("infant", 0, 730),),
    }
    values.update(changes)
    return CohortValidationPolicy(**values)  # type: ignore[arg-type]


def _cohort(**changes: object):
    values = {
        "config": _config(**changes),
        "reference": RegimeLinearTestReference(),
        "calibration": _calibration(),
        "modules": _modules(),
    }
    return generate_native_cohort(**values)


def _comparison(report, name: str):
    return next(item for item in report.comparisons if item.name == name)


def test_demographic_checks_project_blank_source_mass_into_visible_unknown() -> None:
    calibration = dataclasses.replace(
        _calibration(),
        sex_weights=(("F", 1.0), ("M", 0.0), ("U", 0.0)),
        ethnicity_weights=(
            ("", 0.25),
            ("Not Hispanic or Latino", 0.0),
            ("Hispanic or Latino", 0.0),
            ("Choose not to Answer", 0.0),
            ("Unknown", 0.75),
            ("Unable to collect", 0.0),
            ("Patient does not know", 0.0),
        ),
        race_weights=(
            ("", 0.25),
            ("American Indian or Alaska Native", 0.0),
            ("Another Race", 0.0),
            ("Asian", 0.0),
            ("Black or African American", 0.0),
            ("Choose not to answer", 0.0),
            ("Middle Eastern or Northern African", 0.0),
            ("Native Hawaiian or Other Pacific Islander", 0.0),
            ("Patient does not know", 0.0),
            ("Unable to collect", 0.0),
            ("Unknown", 0.75),
            ("White", 0.0),
        ),
    )
    cohort = generate_native_cohort(
        _config(patient_count=4),
        RegimeLinearTestReference(),
        calibration,
        modules=_modules(),
    )

    report = validate_native_cohort(cohort, _policy())

    assert _comparison(report, "demographics.sex.f").observed_value == 1.0
    assert _comparison(report, "demographics.sex.f").target_value == 1.0
    assert _comparison(report, "demographics.ethnicity.unknown").observed_value == 1.0
    assert _comparison(report, "demographics.ethnicity.unknown").target_value == 1.0
    assert _comparison(report, "demographics.race.unknown").observed_value == 1.0
    assert _comparison(report, "demographics.race.unknown").target_value == 1.0
    assert all("." in item.name for item in report.comparisons if item.layer == "demographics")


def test_demographic_checks_include_zero_support_categories_and_apply_tolerance() -> None:
    cohort = _cohort()
    report = validate_native_cohort(
        cohort,
        _policy(minimum_cell_support=2, proportion_tolerance=0.0),
    )

    names = [item.name for item in report.comparisons]
    assert names.index("demographics.sex.f") < names.index("demographics.sex.m")
    assert names.index("demographics.ethnicity.unknown") < names.index(
        "demographics.race.white"
    )
    assert any(
        item.layer == "demographics" and item.support == 0
        for item in report.comparisons
    )
    assert any(
        item.layer == "demographics"
        and item.status is CohortValidationStatus.FAIL
        and item.reason_code == "OUTSIDE_TOLERANCE"
        for item in report.comparisons
    )


def test_small_cohort_makes_all_proportion_checks_unevaluable() -> None:
    report = validate_native_cohort(
        _cohort(patient_count=1),
        _policy(minimum_cohort_size=2),
    )

    demographic = [item for item in report.comparisons if item.layer == "demographics"]
    assert demographic
    assert all(item.status is CohortValidationStatus.UNEVALUABLE for item in demographic)
    assert all(item.reason_code == "COHORT_TOO_SMALL" for item in demographic)
    assert all(item.target_value is None for item in demographic)


def test_latent_observable_and_recorded_layers_are_distinct_status_only_diagnostics() -> None:
    cohort = _cohort()
    report = validate_native_cohort(cohort, _policy())

    latent = [item for item in report.comparisons if item.layer == "latent"]
    assert [item.name for item in latent] == [
        "latent_module.healthy",
        "latent_module.familial_short_stature",
        "latent_module.constitutional_delay",
        "latent_module.growth_hormone_deficiency",
    ]
    assert sum(item.support for item in latent) == len(cohort.members)
    assert all(item.target_value is None for item in latent)

    observable = _comparison(report, "observable_phenotype")
    expected_observable = sum(
        any(event.event_type == "observable_phenotype" for event in member.trajectory.events)
        for member in cohort.members
    )
    assert observable.support == expected_observable
    assert observable.denominator == len(cohort.members)
    assert observable.target_value is None

    for event_kind, name in (
        (RecordedEventKind.RECOGNITION, "recorded_recognition"),
        (RecordedEventKind.WORKUP, "recorded_workup"),
        (RecordedEventKind.DIAGNOSIS, "recorded_diagnosis"),
    ):
        comparison = _comparison(report, name)
        expected = sum(
            any(event.event_kind is event_kind for event in member.frame.events)
            for member in cohort.members
        )
        assert comparison.support == expected
        assert comparison.denominator == len(cohort.members)
        assert comparison.target_value is None

    assert "healthy_flag" not in {item.name for item in report.comparisons}
    assert "growth_dx_flag" not in {item.name for item in report.comparisons}


def test_evaluation_is_deterministic_and_does_not_mutate_cohort() -> None:
    cohort = _cohort()
    before = cohort.to_mapping()

    first = validate_native_cohort(cohort, _policy())
    second = validate_native_cohort(cohort, _policy())

    assert first.to_mapping() == second.to_mapping()
    assert cohort.to_mapping() == before
    assert [member.to_mapping() for member in cohort.members] == [
        member.to_mapping() for member in cohort.members
    ]


def test_demographic_support_threshold_is_unevaluable_without_exposing_target() -> None:
    calibration = dataclasses.replace(
        _calibration(),
        sex_weights=(("F", 1.0), ("M", 0.0), ("U", 0.0)),
    )
    cohort = generate_native_cohort(
        _config(patient_count=4),
        RegimeLinearTestReference(),
        calibration,
        modules=_modules(),
    )

    comparison = _comparison(
        validate_native_cohort(cohort, _policy(minimum_cell_support=5)),
        "demographics.sex.f",
    )

    assert comparison.status is CohortValidationStatus.UNEVALUABLE
    assert comparison.reason_code == "INSUFFICIENT_SUPPORT"
    assert comparison.observed_value is None
    assert comparison.target_value is None


def test_validator_requires_native_cohort_and_policy_types() -> None:
    with pytest.raises(TypeError, match="cohort"):
        validate_native_cohort(object(), _policy())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="policy"):
        validate_native_cohort(_cohort(), object())  # type: ignore[arg-type]


def test_coverage_registry_uses_observation_not_visit_wording() -> None:
    comparison = CohortComparison(
        name="coverage.members_with_observation",
        layer="coverage",
        status=CohortValidationStatus.PASS,
        observed_value=1.0,
        target_value=None,
        difference=None,
        tolerance=None,
        support=1,
        denominator=1,
        reason_code="OBSERVED",
    )
    assert comparison.name == "coverage.members_with_observation"
    with pytest.raises(ValueError, match="name"):
        CohortComparison(
            name="coverage.members_with_visit",
            layer="coverage",
            status=CohortValidationStatus.PASS,
            observed_value=1.0,
            target_value=None,
            difference=None,
            tolerance=None,
            support=1,
            denominator=1,
            reason_code="OBSERVED",
        )


@pytest.mark.parametrize("field", ["frame", "trajectory"])
def test_malformed_member_access_returns_a_redacted_failure(field: str) -> None:
    cohort = _cohort(patient_count=1)
    member = cohort.members[0]
    object.__setattr__(member, field, object())

    report = validate_native_cohort(cohort, _policy())

    assert report.status is CohortValidationStatus.FAIL
    assert report.comparisons
    mapping = report.to_mapping()
    assert "syn-" not in str(mapping)
    assert "patient" not in str(mapping).lower()
    assert "truth" not in repr(report).lower()


def test_malformed_calibration_access_returns_a_redacted_failure() -> None:
    cohort = _cohort(patient_count=1)

    class ExplodingCalibration:
        @property
        def sex_weights(self) -> tuple[object, ...]:
            raise RuntimeError("syn-patient-secret calibration failure")

    object.__setattr__(cohort, "calibration", ExplodingCalibration())

    report = validate_native_cohort(cohort, _policy())

    assert report.status is CohortValidationStatus.FAIL
    assert report.comparisons[0].reason_code == "MALFORMED_COHORT"
    assert "syn-patient-secret" not in str(report.to_mapping())
