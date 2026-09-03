from __future__ import annotations

from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from synthetic import development_runtime
from synthetic.cohort import CohortConfig, CohortModuleWeight
from synthetic.development_runtime import build_development_runtime
from synthetic.models import DisorderKind
from synthetic.native.clinical_modules import TurnerSyndromeModule
from synthetic.package_export import PackageExportUnavailable
from synthetic.schema_contract import load_descriptor

ROOT = Path(__file__).resolve().parents[2]
_PATIENT_COUNT = 128
_SEED = 20260903


def _weight_row(
    config: CohortConfig, reference_sex: str
) -> tuple[tuple[DisorderKind, float], ...]:
    rows = dict(config.module_weights_by_reference_sex)
    return tuple((weight.kind, weight.probability) for weight in rows[reference_sex])


def test_all_disorder_configuration_binds_snapshot_demographics_and_conditional_priors() -> None:
    """Catches profile drift or a flat prior substituted for the exact F/M rows."""
    config = development_runtime.development_all_disorders_config(64, _SEED)
    calibration = development_runtime.development_all_disorders_calibration_profile()
    realistic = development_runtime.development_realistic_calibration_profile()

    female_row = _weight_row(config, "F")
    male_row = _weight_row(config, "M")
    assert config.profile == "development-all-disorders-v1"
    assert tuple(sex for sex, _ in config.module_weights_by_reference_sex) == ("F", "M")
    assert female_row == (
        (DisorderKind.HEALTHY, 1 / 2),
        (DisorderKind.FAMILIAL_SHORT_STATURE, 1 / 18),
        (DisorderKind.CONSTITUTIONAL_DELAY, 1 / 18),
        (DisorderKind.GROWTH_HORMONE_DEFICIENCY, 1 / 18),
        (DisorderKind.PEDIATRIC_HYPOTHYROIDISM, 1 / 18),
        (DisorderKind.CELIAC_DISEASE, 1 / 18),
        (DisorderKind.SMALL_FOR_GESTATIONAL_AGE, 1 / 18),
        (DisorderKind.TURNER_SYNDROME, 1 / 18),
        (DisorderKind.UNDERNUTRITION, 1 / 18),
        (DisorderKind.EXCESS_WEIGHT, 1 / 18),
    )
    assert male_row == (
        (DisorderKind.HEALTHY, 1 / 2),
        (DisorderKind.FAMILIAL_SHORT_STATURE, 1 / 16),
        (DisorderKind.CONSTITUTIONAL_DELAY, 1 / 16),
        (DisorderKind.GROWTH_HORMONE_DEFICIENCY, 1 / 16),
        (DisorderKind.PEDIATRIC_HYPOTHYROIDISM, 1 / 16),
        (DisorderKind.CELIAC_DISEASE, 1 / 16),
        (DisorderKind.SMALL_FOR_GESTATIONAL_AGE, 1 / 16),
        (DisorderKind.TURNER_SYNDROME, 0.0),
        (DisorderKind.UNDERNUTRITION, 1 / 16),
        (DisorderKind.EXCESS_WEIGHT, 1 / 16),
    )
    assert sum(probability for _, probability in female_row) == pytest.approx(1.0)
    assert sum(probability for _, probability in male_row) == pytest.approx(1.0)
    assert config.observation_policy.to_mapping() == {
        "policy_version": "development-all-disorders-observation-v1",
        "window_start_age_days": 0,
        "window_end_age_days": 7306,
        "censoring_mode": "none",
        "censor_age_days": None,
        "visit_probability": 1.0,
        "length_availability_probability": 0.0,
        "height_availability_probability": 1.0,
        "weight_availability_probability": 1.0,
        "head_circumference_availability_probability": 1.0,
        "length_error_sd_cm": 0.0,
        "height_error_sd_cm": 0.0,
        "weight_error_sd_kg": 0.0,
        "head_circumference_error_sd_cm": 0.0,
        "rounding_digits": None,
        "recognition_probability": 1.0,
        "diagnosis_probability": 1.0,
        "recognition_delay_days": 0,
    }
    assert config.age_regime_config.puberty_max_age_days == 5834
    assert config.age_regime_config.puberty_sampling_max_age_days == 5114
    assert calibration.artifact_id == "development-all-disorders-v1"
    assert calibration.sex_weights == realistic.sex_weights
    assert calibration.ethnicity_weights == realistic.ethnicity_weights
    assert calibration.race_weights == realistic.race_weights
    assert calibration.race_multiselect_probability == realistic.race_multiselect_probability
    assert development_runtime.development_cohort_config(
        1, _SEED
    ).module_weights_by_reference_sex == ()


def test_conditional_module_prior_rows_must_match_the_flat_module_registry() -> None:
    """Catches an incomplete sex-specific row reaching module selection."""
    config = development_runtime.development_all_disorders_config(1, _SEED)
    female_row = dict(config.module_weights_by_reference_sex)["F"]

    with pytest.raises(ValueError, match="flat module registry"):
        replace(
            config,
            module_weights_by_reference_sex=(("F", female_row[:-1]),),
        )


def test_all_disorder_cohort_is_deterministic_covers_every_kind_and_filters_turner() -> None:
    """Catches missing modules, nondeterministic draws, or Turner assigned outside F reference."""
    runtime = build_development_runtime(ROOT)
    descriptor = load_descriptor(ROOT / "datapackage.json")

    first = development_runtime.build_development_all_disorders_cohort(
        runtime,
        descriptor=descriptor,
        patient_count=_PATIENT_COUNT,
        seed=_SEED,
    )
    replay = development_runtime.build_development_all_disorders_cohort(
        runtime,
        descriptor=descriptor,
        patient_count=_PATIENT_COUNT,
        seed=_SEED,
    )
    changed = development_runtime.build_development_all_disorders_cohort(
        runtime,
        descriptor=descriptor,
        patient_count=_PATIENT_COUNT,
        seed=_SEED + 1,
    )

    first_counts = Counter(member.trajectory.disorder.kind for member in first.members)
    replay_counts = Counter(member.trajectory.disorder.kind for member in replay.members)
    assert set(first_counts) == set(DisorderKind)
    assert first_counts == replay_counts
    assert [member.to_mapping() for member in first.members] == [
        member.to_mapping() for member in replay.members
    ]
    assert [member.to_mapping() for member in first.members] != [
        member.to_mapping() for member in changed.members
    ]
    assert all(
        member.trajectory.disorder.kind is not DisorderKind.TURNER_SYNDROME
        or member.demographics.sex == "F"
        for member in first.members
    )


@pytest.mark.parametrize("commitment", ("prior", "eligibility", "module", "ancillary"))
def test_all_disorder_configuration_hash_commits_every_selection_boundary(
    monkeypatch: pytest.MonkeyPatch,
    commitment: str,
) -> None:
    """Catches selection or ancillary drift that leaves the manifest identity unchanged."""
    runtime = build_development_runtime(ROOT)
    config = development_runtime.development_all_disorders_config(1, _SEED)
    calibration = development_runtime.development_all_disorders_calibration_profile()
    baseline = development_runtime._configuration_sha256(runtime, config, calibration)

    if commitment == "prior":
        rows = dict(config.module_weights_by_reference_sex)
        female = list(rows["F"])
        female[0] = CohortModuleWeight(DisorderKind.HEALTHY, 0.49)
        config = replace(
            config,
            module_weights_by_reference_sex=(("F", tuple(female)), ("M", rows["M"])),
        )
    elif commitment == "eligibility":
        monkeypatch.setattr(
            development_runtime,
            "_ALL_DISORDER_ELIGIBILITY_POLICY_VERSION",
            "reference-sex-module-eligibility-v2",
        )
    elif commitment == "module":
        monkeypatch.setattr(TurnerSyndromeModule, "module_version", "turner-syndrome-v2")
    else:
        original = development_runtime.development_all_disorders_ancillary_policy

        def changed_policy() -> object:
            return replace(original(), result_delay_days=8)

        monkeypatch.setattr(
            development_runtime,
            "development_all_disorders_ancillary_policy",
            changed_policy,
        )

    assert baseline != development_runtime._configuration_sha256(
        runtime, config, calibration
    )


def test_all_disorder_runner_redacts_ancillary_projection_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches a typed-sidecar failure leaking details or promoting partial output."""
    sensitive = "fictional-row-details /private/input.csv"

    def unavailable_projection(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise RuntimeError(sensitive)

    monkeypatch.setattr(
        development_runtime,
        "project_multidisorder_ancillary_resources",
        unavailable_projection,
    )
    output = tmp_path / "failed-package"

    with pytest.raises(PackageExportUnavailable) as caught:
        development_runtime.generate_development_all_disorders_cohort(
            build_development_runtime(ROOT),
            descriptor_path=ROOT / "datapackage.json",
            output=output,
            patient_count=1,
            seed=_SEED,
            reference_time="2026-09-03T00:00:00Z",
            software_revision="all-disorder-test-v1",
        )

    assert caught.value.args == ("observed package export failed",)
    assert sensitive not in repr(caught.value)
    assert not output.exists()
