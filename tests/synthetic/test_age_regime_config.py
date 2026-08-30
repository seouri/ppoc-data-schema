import pytest

from synthetic.models import GrowthRegime
from synthetic.native.age_regimes import AgeRegimeConfig, classify_age


def test_classifier_covers_all_regimes_at_explicit_boundaries() -> None:
    config = AgeRegimeConfig(
        transition_age_days=730,
        transition_window_days=30,
        maximum_age_days=7305,
    )
    puberty_age = 4380
    tempo = 900

    assert classify_age(0, puberty_age, tempo, config) is GrowthRegime.INFANCY
    assert classify_age(699, puberty_age, tempo, config) is GrowthRegime.INFANCY
    assert classify_age(700, puberty_age, tempo, config) is GrowthRegime.TRANSITION
    assert classify_age(760, puberty_age, tempo, config) is GrowthRegime.TRANSITION
    assert classify_age(761, puberty_age, tempo, config) is GrowthRegime.CHILDHOOD
    assert classify_age(puberty_age - 1, puberty_age, tempo, config) is GrowthRegime.CHILDHOOD
    assert classify_age(puberty_age, puberty_age, tempo, config) is GrowthRegime.PUBERTY
    assert classify_age(puberty_age + tempo, puberty_age, tempo, config) is GrowthRegime.PUBERTY
    assert classify_age(puberty_age + tempo + 1, puberty_age, tempo, config) is GrowthRegime.ADOLESCENCE


@pytest.mark.parametrize(
    "kwargs",
    [
        {"transition_age_days": -1},
        {"transition_window_days": -1},
        {"maximum_age_days": 729},
        {"puberty_min_age_days": 5000, "puberty_max_age_days": 4000},
        {"puberty_tempo_min_days": 0},
        {"maximum_age_days": 5000, "puberty_max_age_days": 4500, "puberty_tempo_max_days": 600},
        {"maximum_age_days": 760, "transition_window_days": 30},
        {"transition_age_days": 10, "transition_window_days": 30},
        {"puberty_min_age_days": 750},
        {"length_to_height_offset_cm": -0.1},
        {"max_transition_discontinuity_cm": 0.0},
    ],
)
def test_configuration_rejects_invalid_parameters(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        AgeRegimeConfig(**kwargs)


def test_classifier_rejects_invalid_age_or_puberty_schedule() -> None:
    config = AgeRegimeConfig()
    with pytest.raises(ValueError, match="age_days"):
        classify_age(-1, 4380, 900, config)
    with pytest.raises(ValueError, match="puberty"):
        classify_age(4380, 4380, 0, config)
