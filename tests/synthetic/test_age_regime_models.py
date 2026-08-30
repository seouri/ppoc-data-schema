import math

import pytest

from synthetic.models import (
    AgeRegimePoint,
    AgeRegimeState,
    AgeRegimeTrajectory,
    GrowthRegime,
)


def test_age_regime_state_and_point_accept_valid_values() -> None:
    state = AgeRegimeState(
        "age-regimes-v1", 0.4, -0.2, 0.1, 0.0, 0.2, 4380, 900, 0.5, 0.1
    )
    point = AgeRegimePoint(
        patient_id="syn-patient-a", age_days=730, regime=GrowthRegime.TRANSITION,
        length_cm=90.7, height_cm=90.0, weight_kg=12.96, bmi=16.0,
        head_circumference_cm=48.0, length_z=0.0, height_z=0.0,
        weight_z=0.0, bmi_z=0.0, height_velocity_cm_per_year=6.0,
        weight_velocity_kg_per_year=2.0,
    )
    trajectory = AgeRegimeTrajectory((point,), state)
    assert trajectory.points[0].regime is GrowthRegime.TRANSITION
    assert trajectory.state.module_version == "age-regimes-v1"


@pytest.mark.parametrize("kwargs", [
    {"module_version": "", "birth_length_z": 0.0},
    {"module_version": "v1", "birth_length_z": math.nan},
    {"module_version": "v1", "puberty_onset_age_days": -1},
    {"module_version": "v1", "puberty_tempo_days": 0},
])
def test_age_regime_state_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    values: dict[str, object] = {
        "module_version": "age-regimes-v1", "birth_length_z": 0.0,
        "birth_weight_z": 0.0, "head_circumference_z": 0.0,
        "childhood_height_z": 0.0, "childhood_bmi_z": 0.0,
        "puberty_onset_age_days": 4380, "puberty_tempo_days": 900,
        "puberty_height_spurt_z": 0.5, "puberty_bmi_shift_z": 0.1,
    }
    values.update(kwargs)
    with pytest.raises(ValueError):
        AgeRegimeState(**values)


def test_age_regime_point_requires_regime_appropriate_measurements() -> None:
    with pytest.raises(ValueError, match="length"):
        AgeRegimePoint("syn-patient-a", 365, GrowthRegime.INFANCY, None, None, 8.0, None)
    with pytest.raises(ValueError, match="BMI"):
        AgeRegimePoint("syn-patient-a", 4000, GrowthRegime.PUBERTY, None, 150.0, 45.0, None)


def test_age_regime_point_rejects_nonphysical_identity() -> None:
    with pytest.raises(ValueError, match="weight"):
        AgeRegimePoint("syn-patient-a", 730, GrowthRegime.TRANSITION, 90.7, 90.0, 13.0, 16.0)


def test_age_regime_point_requires_finite_positive_weight() -> None:
    with pytest.raises(ValueError, match="weight"):
        AgeRegimePoint("syn-patient-a", 365, GrowthRegime.INFANCY, 75.0, None, None, None)


def test_age_regime_models_reject_boolean_numeric_values() -> None:
    with pytest.raises(ValueError, match="weight"):
        AgeRegimePoint("syn-patient-a", 365, GrowthRegime.INFANCY, 75.0, None, True, None)
    with pytest.raises(ValueError, match="birth_length_z"):
        AgeRegimeState("v1", True, 0.0, 0.0, 0.0, 0.0, 4380, 900, 0.0, 0.0)


def test_age_regime_point_rejects_overflowing_bmi_identity() -> None:
    with pytest.raises(ValueError, match="weight"):
        AgeRegimePoint("syn-patient-a", 4000, GrowthRegime.PUBERTY, None, 1e308, 1.0, 1.0)


def test_existing_latent_point_positional_contract_is_unchanged() -> None:
    from synthetic.models import LatentPoint
    point = LatentPoint("syn-patient-a", 730, 90.0, 16.0, 12.96, 0.0, 0.0)
    assert point.age_days == 730
    assert point.weight_kg == pytest.approx(12.96)
