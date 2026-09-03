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
    CeliacDiseaseModule,
    ConstitutionalDelayModule,
    ExcessWeightModule,
    FamilialShortStatureModule,
    GrowthHormoneDeficiencyModule,
    HealthyGrowthModule,
    PediatricHypothyroidismModule,
    SmallForGestationalAgeModule,
    TurnerSyndromeModule,
    UndernutritionModule,
)
from synthetic.native.observations import ObservationPolicy
from tests.synthetic.cohort_fixtures import aggregate_calibration_artifact
from tests.synthetic.fakes import RegimeLinearTestReference

_AGES = (0, 365, 730, 1460, 2190, 3650, 4380, 5110, 6200)
_REFERENCE_SEX_MAPPING = (("F", "F"), ("M", "M"), ("U", "U"))


def _calibration(
    sex_weights: tuple[tuple[str, float], ...],
) -> CalibrationSamplingProfile:
    return dataclasses.replace(
        CalibrationSamplingProfile.from_artifact(aggregate_calibration_artifact()),
        sex_weights=sex_weights,
    )


def _config(
    module_weights: tuple[CohortModuleWeight, ...],
    *,
    patient_count: int = 40,
) -> CohortConfig:
    return CohortConfig(
        profile="module-eligibility-v1",
        patient_count=patient_count,
        seed=20260903,
        ages_days=_AGES,
        observation_policy=ObservationPolicy("module-eligibility-v1", 0, 6201),
        module_weights=module_weights,
        reference_sex_mapping=_REFERENCE_SEX_MAPPING,
    )


def _healthy_turner_modules() -> dict[DisorderKind, object]:
    return {
        DisorderKind.HEALTHY: HealthyGrowthModule(),
        DisorderKind.TURNER_SYNDROME: TurnerSyndromeModule(),
    }


def _all_modules() -> dict[DisorderKind, object]:
    return {
        DisorderKind.HEALTHY: HealthyGrowthModule(),
        DisorderKind.FAMILIAL_SHORT_STATURE: FamilialShortStatureModule(),
        DisorderKind.CONSTITUTIONAL_DELAY: ConstitutionalDelayModule(),
        DisorderKind.GROWTH_HORMONE_DEFICIENCY: GrowthHormoneDeficiencyModule(),
        DisorderKind.PEDIATRIC_HYPOTHYROIDISM: PediatricHypothyroidismModule(),
        DisorderKind.CELIAC_DISEASE: CeliacDiseaseModule(),
        DisorderKind.SMALL_FOR_GESTATIONAL_AGE: SmallForGestationalAgeModule(),
        DisorderKind.TURNER_SYNDROME: TurnerSyndromeModule(),
        DisorderKind.UNDERNUTRITION: UndernutritionModule(),
        DisorderKind.EXCESS_WEIGHT: ExcessWeightModule(),
    }


def test_turner_selection_is_limited_to_female_reference_patients() -> None:
    config = _config(
        (
            CohortModuleWeight(DisorderKind.HEALTHY, 0.05),
            CohortModuleWeight(DisorderKind.TURNER_SYNDROME, 0.95),
        )
    )

    female_reference = generate_native_cohort(
        config,
        RegimeLinearTestReference(),
        _calibration((("F", 1.0), ("M", 0.0), ("U", 0.0))),
        modules=_healthy_turner_modules(),
    )
    male_reference = generate_native_cohort(
        config,
        RegimeLinearTestReference(),
        _calibration((("F", 0.0), ("M", 1.0), ("U", 0.0))),
        modules=_healthy_turner_modules(),
    )

    assert DisorderKind.TURNER_SYNDROME in {
        member.trajectory.disorder.kind for member in female_reference.members
    }
    assert {member.trajectory.disorder.kind for member in male_reference.members} == {
        DisorderKind.HEALTHY
    }


def test_mixed_all_module_draws_are_eligible_and_mapping_order_independent() -> None:
    modules = _all_modules()
    config = _config(
        tuple(
            CohortModuleWeight(kind, 0.8 if kind is DisorderKind.HEALTHY else 0.02)
            for kind in modules
        ),
        patient_count=80,
    )
    calibration = _calibration((("F", 0.5), ("M", 0.5), ("U", 0.0)))

    first = generate_native_cohort(
        config,
        RegimeLinearTestReference(),
        calibration,
        modules=modules,
    )
    reordered = generate_native_cohort(
        config,
        RegimeLinearTestReference(),
        calibration,
        modules=dict(reversed(tuple(modules.items()))),
    )

    sex_and_kind = {
        (member.demographics.sex, member.trajectory.disorder.kind) for member in first.members
    }
    assert ("F", DisorderKind.HEALTHY) in sex_and_kind
    assert ("M", DisorderKind.HEALTHY) in sex_and_kind
    assert ("M", DisorderKind.TURNER_SYNDROME) not in sex_and_kind
    assert first.to_mapping() == reordered.to_mapping()
    assert [member.to_mapping() for member in first.members] == [
        member.to_mapping() for member in reordered.members
    ]


def test_malformed_module_requirement_fails_at_redacted_generation_boundary() -> None:
    sensitive = "real-patient-eligibility /governed/eligibility.csv truth_hash"

    class MalformedRequirementHealthyModule(HealthyGrowthModule):
        required_reference_sex = (sensitive,)

    modules = _healthy_turner_modules()
    modules[DisorderKind.HEALTHY] = MalformedRequirementHealthyModule()

    with pytest.raises(CohortGenerationUnavailable) as error:
        generate_native_cohort(
            _config(
                (
                    CohortModuleWeight(DisorderKind.HEALTHY, 0.5),
                    CohortModuleWeight(DisorderKind.TURNER_SYNDROME, 0.5),
                ),
                patient_count=1,
            ),
            RegimeLinearTestReference(),
            _calibration((("F", 1.0), ("M", 0.0), ("U", 0.0))),
            modules=modules,
        )

    assert error.value.args == ("native cohort generation failed",)
    encoded = json.dumps(error.value.args) + repr(error.value)
    assert "real-patient" not in encoded
    assert "eligibility.csv" not in encoded
    assert "truth_hash" not in encoded
