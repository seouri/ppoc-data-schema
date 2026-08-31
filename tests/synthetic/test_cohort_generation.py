from __future__ import annotations

import dataclasses
import json

import pytest

from synthetic.cohort import (
    CalibrationSamplingProfile,
    CohortConfig,
    CohortGenerationUnavailable,
    CohortModuleWeight,
    generate_native_cohort,
)
from synthetic.models import DisorderKind
from synthetic.native.clinical_modules import (
    GrowthHormoneDeficiencyModule,
    HealthyGrowthModule,
)
from synthetic.native.observations import (
    ObservationPolicy,
    ObservationValidationStatus,
    validate_observation_frame,
)
from tests.synthetic.cohort_fixtures import aggregate_calibration_artifact
from tests.synthetic.fakes import RegimeLinearTestReference

_AGES = (0, 365, 730, 1460, 2190, 3650, 4380, 5110, 6200)
_REFERENCE_SEX_MAPPING = (("F", "F"), ("M", "M"), ("U", "U"))


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
        "reference_sex_mapping": _REFERENCE_SEX_MAPPING,
    }
    values.update(changes)
    return CohortConfig(**values)  # type: ignore[arg-type]


def _draw_signature(cohort: object) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            member.demographics.sex,
            member.demographics.ethnicity,
            member.demographics.races,
            member.trajectory.disorder.kind,
        )
        for member in cohort.members  # type: ignore[attr-defined]
    )


def test_equal_inputs_replay_visible_latent_and_truth_results() -> None:
    config = _config()
    calibration = _calibration()
    modules = _modules()

    first = generate_native_cohort(
        config,
        RegimeLinearTestReference(),
        calibration,
        modules=modules,
    )
    replay = generate_native_cohort(
        config,
        RegimeLinearTestReference(),
        calibration,
        modules=dict(reversed(tuple(modules.items()))),
    )

    assert first.to_mapping() == replay.to_mapping()
    assert [member.to_mapping() for member in first.members] == [
        member.to_mapping() for member in replay.members
    ]
    assert [member.trajectory for member in first.members] == [
        member.trajectory for member in replay.members
    ]
    assert [member.frame.truth.latent_trajectory_hash for member in first.members] == [
        member.frame.truth.latent_trajectory_hash for member in replay.members
    ]
    assert [member.frame.truth.truth_hash for member in first.members] == [
        member.frame.truth.truth_hash for member in replay.members
    ]


def test_generation_has_unique_ids_closed_demographics_and_mixed_modules() -> None:
    cohort = generate_native_cohort(
        _config(),
        RegimeLinearTestReference(),
        _calibration(),
        modules=_modules(),
    )

    patient_ids = tuple(member.demographics.patient_id for member in cohort.members)
    assert len(patient_ids) == len(set(patient_ids)) == 48
    assert all(patient_id.startswith("syn-") for patient_id in patient_ids)
    assert {member.trajectory.disorder.kind for member in cohort.members} >= {
        DisorderKind.HEALTHY,
        DisorderKind.GROWTH_HORMONE_DEFICIENCY,
    }
    assert all(member.demographics.sex in {"F", "M", "U"} for member in cohort.members)
    assert all(member.demographics.ethnicity for member in cohort.members)
    assert all(len(member.demographics.races) == 8 for member in cohort.members)
    assert all(all(race for race in member.demographics.races) for member in cohort.members)
    assert all(member.bundle is None for member in cohort.members)

    for member in cohort.members:
        assert tuple(point.age_days for point in member.trajectory.physiology.points) == _AGES
        assert all(
            point.patient_id == member.demographics.patient_id
            for point in member.trajectory.physiology.points
        )
        assert validate_observation_frame(member.frame).status is ObservationValidationStatus.PASS


def test_seed_changes_draws_without_changing_identifier_contract() -> None:
    first = generate_native_cohort(
        _config(seed=101),
        RegimeLinearTestReference(),
        _calibration(),
        modules=_modules(),
    )
    second = generate_native_cohort(
        _config(seed=102),
        RegimeLinearTestReference(),
        _calibration(),
        modules=_modules(),
    )

    assert _draw_signature(first) != _draw_signature(second)
    assert all(member.demographics.patient_id.startswith("syn-") for member in second.members)


def test_recorded_outcome_targets_do_not_allocate_latent_modules() -> None:
    calibration = _calibration()
    inverted_recorded_evidence = dataclasses.replace(
        calibration,
        recorded_healthy_probability=0.01,
        recorded_growth_dx_probability=0.99,
    )
    config = _config(
        module_weights=(
            CohortModuleWeight(DisorderKind.HEALTHY, 0.9),
            CohortModuleWeight(DisorderKind.GROWTH_HORMONE_DEFICIENCY, 0.1),
        )
    )

    baseline = generate_native_cohort(
        config,
        RegimeLinearTestReference(),
        calibration,
        modules=_modules(),
    )
    changed_evidence = generate_native_cohort(
        config,
        RegimeLinearTestReference(),
        inverted_recorded_evidence,
        modules=_modules(),
    )

    assert _draw_signature(baseline) == _draw_signature(changed_evidence)
    assert [member.trajectory for member in baseline.members] == [
        member.trajectory for member in changed_evidence.members
    ]


def test_reference_sex_mapping_is_applied_before_reference_calls() -> None:
    class RecordingReference(RegimeLinearTestReference):
        def __init__(self) -> None:
            self.reference_sexes: list[str] = []

        def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
            self.reference_sexes.append(reference_sex)
            return super().value(metric, age_days, reference_sex, z)

    calibration = dataclasses.replace(
        _calibration(),
        sex_weights=(("F", 1.0), ("M", 0.0), ("U", 0.0)),
    )
    reference = RecordingReference()

    cohort = generate_native_cohort(
        _config(
            patient_count=3,
            reference_sex_mapping=(("F", "M"), ("M", "F"), ("U", "U")),
        ),
        reference,
        calibration,
        modules=_modules(),
    )

    assert all(member.demographics.sex == "F" for member in cohort.members)
    assert reference.reference_sexes
    assert set(reference.reference_sexes) == {"M"}


@pytest.mark.parametrize(
    "modules",
    [
        {DisorderKind.HEALTHY: HealthyGrowthModule()},
        {
            DisorderKind.HEALTHY: HealthyGrowthModule(),
            DisorderKind.GROWTH_HORMONE_DEFICIENCY: GrowthHormoneDeficiencyModule(),
            DisorderKind.FAMILIAL_SHORT_STATURE: HealthyGrowthModule(),
        },
        {
            DisorderKind.HEALTHY: HealthyGrowthModule(),
            DisorderKind.GROWTH_HORMONE_DEFICIENCY: HealthyGrowthModule(),
        },
    ],
)
def test_module_mapping_must_exactly_match_positive_prior_kinds(
    modules: dict[DisorderKind, object],
) -> None:
    with pytest.raises((TypeError, ValueError), match="modules"):
        generate_native_cohort(
            _config(),
            RegimeLinearTestReference(),
            _calibration(),
            modules=modules,  # type: ignore[arg-type]
        )


def test_generation_failure_is_redacted_from_mapping_repr_and_exception() -> None:
    class SensitiveReference(RegimeLinearTestReference):
        def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
            del metric, age_days, reference_sex, z
            raise RuntimeError("real-patient-123 /governed/source.csv truth_hash")

    with pytest.raises(CohortGenerationUnavailable) as error:
        generate_native_cohort(
            _config(patient_count=1),
            SensitiveReference(),
            _calibration(),
            modules=_modules(),
        )

    assert str(error.value) == "native cohort generation failed"
    encoded = json.dumps(error.value.args) + repr(error.value)
    assert "real-patient" not in encoded
    assert "source.csv" not in encoded
    assert "truth_hash" not in encoded


def test_reference_must_expose_callable_value_before_sampling() -> None:
    with pytest.raises(TypeError, match="reference"):
        generate_native_cohort(
            _config(),
            object(),  # type: ignore[arg-type]
            _calibration(),
            modules=_modules(),
        )
