import dataclasses
import math

import pytest

from synthetic.models import GrowthRegime, PatientState
from synthetic.native.age_regimes import AgeRegimeConfig, AgeRegimeTrajectoryKernel
from synthetic.randomness import NamedRandomStreams


class RegimeReference:
    reference_id = "regime-test-reference-v1"
    min_age_days = 0
    max_age_days = 7305

    def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
        del reference_sex
        age_years = age_days / 365.25
        height = 74.0 + 5.5 * age_years + 3.0 * z
        if metric == "length_cm":
            return height + 0.7
        if metric == "weight_kg":
            return 8.5 + 2.0 * age_years + 0.5 * z
        if metric == "head_circumference_cm":
            return 46.0 + 1.5 * age_years + 1.0 * z
        if metric == "height_cm":
            return height
        if metric == "bmi":
            return 15.5 + 0.2 * age_years + 0.5 * z
        raise KeyError(metric)


PATIENT = PatientState("syn-patient-a", "F", "F")


def test_sampled_state_can_be_replayed_without_resampling() -> None:
    kernel = AgeRegimeTrajectoryKernel(RegimeReference())
    streams = NamedRandomStreams(20260830, 0)
    state = kernel.sample_state(streams)

    replayed = kernel.generate(PATIENT, (0, 730, 761, 4380), streams, state=state)
    ordinary = kernel.generate(PATIENT, (0, 730, 761, 4380), streams)

    assert replayed.state == ordinary.state
    assert replayed.points == ordinary.points


def test_state_replay_rejects_wrong_version_or_puberty_domain() -> None:
    kernel = AgeRegimeTrajectoryKernel(RegimeReference())
    state = kernel.sample_state(NamedRandomStreams(5, 0))

    with pytest.raises(ValueError, match="module_version"):
        kernel.generate(
            PATIENT,
            (730,),
            NamedRandomStreams(5, 0),
            state=dataclasses.replace(state, module_version="other-v1"),
        )
    with pytest.raises(ValueError, match="puberty"):
        kernel.generate(
            PATIENT,
            (730,),
            NamedRandomStreams(5, 0),
            state=dataclasses.replace(state, puberty_onset_age_days=0),
        )


def test_kernel_generates_all_regimes_with_two_dimension_identities() -> None:
    ages = (0, 365, 699, 700, 730, 760, 761, 3000, 4380, 5281, 7305)
    trajectory = AgeRegimeTrajectoryKernel(RegimeReference()).generate(
        PATIENT, ages, NamedRandomStreams(20260830, 0)
    )

    assert [point.regime for point in trajectory.points] == [
        GrowthRegime.INFANCY,
        GrowthRegime.INFANCY,
        GrowthRegime.INFANCY,
        GrowthRegime.TRANSITION,
        GrowthRegime.TRANSITION,
        GrowthRegime.TRANSITION,
        GrowthRegime.CHILDHOOD,
        GrowthRegime.CHILDHOOD,
        GrowthRegime.PUBERTY,
        GrowthRegime.ADOLESCENCE,
        GrowthRegime.ADOLESCENCE,
    ]
    infant = trajectory.points[1]
    assert infant.length_cm is not None
    assert infant.height_cm is None
    assert infant.bmi is None
    assert infant.head_circumference_cm is not None
    transition = trajectory.points[4]
    assert transition.length_cm is not None
    assert transition.height_cm is not None
    assert transition.bmi is not None
    for point in trajectory.points[6:]:
        assert point.length_cm is None
        assert point.height_cm is not None
        assert point.bmi is not None
        assert point.weight_kg == pytest.approx(
            point.bmi * (point.height_cm / 100.0) ** 2
        )
    assert all(
        point.height_velocity_cm_per_year is None
        or math.isfinite(point.height_velocity_cm_per_year)
        for point in trajectory.points
    )
    assert all(
        point.weight_velocity_kg_per_year is None
        or math.isfinite(point.weight_velocity_kg_per_year)
        for point in trajectory.points
    )


def test_transition_uses_explicit_length_to_height_conversion_without_jump() -> None:
    trajectory = AgeRegimeTrajectoryKernel(RegimeReference()).generate(
        PATIENT, (700, 730, 761), NamedRandomStreams(5, 0)
    )
    converted = trajectory.points[1].length_cm - 0.7

    assert trajectory.points[1].height_cm == pytest.approx(converted)
    assert abs(trajectory.points[2].height_cm - converted) < 3.0


def test_puberty_profile_is_deterministic_and_changes_only_after_onset() -> None:
    baseline_config = AgeRegimeConfig(
        puberty_height_spurt_min=0.0,
        puberty_height_spurt_max=0.0,
        puberty_bmi_shift_min=0.0,
        puberty_bmi_shift_max=0.0,
    )
    spurt_config = AgeRegimeConfig(
        puberty_height_spurt_min=0.8,
        puberty_height_spurt_max=0.8,
        puberty_bmi_shift_min=0.2,
        puberty_bmi_shift_max=0.2,
    )
    ages = (3000, 4380, 4830, 5281)
    baseline = AgeRegimeTrajectoryKernel(RegimeReference(), baseline_config).generate(
        PATIENT, ages, NamedRandomStreams(5, 0)
    )
    with_spurt = AgeRegimeTrajectoryKernel(RegimeReference(), spurt_config).generate(
        PATIENT, ages, NamedRandomStreams(5, 0)
    )

    assert with_spurt.points[0].height_z == pytest.approx(baseline.points[0].height_z)
    assert with_spurt.points[1].height_z == pytest.approx(baseline.points[1].height_z)
    assert with_spurt.points[2].height_z > baseline.points[2].height_z
    assert with_spurt.points[3].height_z > baseline.points[3].height_z
    assert with_spurt.state == AgeRegimeTrajectoryKernel(
        RegimeReference(), spurt_config
    ).generate(PATIENT, ages, NamedRandomStreams(5, 0)).state


def test_kernel_uses_only_isolated_regime_streams() -> None:
    class RecordingStreams(NamedRandomStreams):
        names: list[str]

        def __init__(self, run_seed: int, patient_index: int) -> None:
            super().__init__(run_seed, patient_index)
            self.names = []

        def generator(self, name: str):
            self.names.append(name)
            return super().generator(name)

    streams = RecordingStreams(5, 0)
    AgeRegimeTrajectoryKernel(RegimeReference()).generate(PATIENT, (0, 730, 4380), streams)

    assert set(streams.names) == {
        "regime.birth",
        "regime.childhood",
        "regime.puberty",
        "regime.residual",
        "regime.head",
    }
    assert "growth" not in streams.names


@pytest.mark.parametrize(
    "ages_days",
    [[], (), (0, 0), (1, 0), (-1,), (True,), (7306,)],
)
def test_kernel_rejects_invalid_age_sequences(ages_days: object) -> None:
    with pytest.raises(ValueError, match="ages_days"):
        AgeRegimeTrajectoryKernel(RegimeReference()).generate(
            PATIENT, ages_days, NamedRandomStreams(5, 0)  # type: ignore[arg-type]
        )


def test_kernel_rejects_out_of_domain_reference_values() -> None:
    with pytest.raises(ValueError, match="domain"):
        AgeRegimeTrajectoryKernel(RegimeReference()).generate(
            PATIENT, (7306,), NamedRandomStreams(5, 0)
        )


@pytest.mark.parametrize("bad_value", [math.nan, 0.0, True, 10**1000])
def test_kernel_rejects_nonphysical_reference_values(bad_value: object) -> None:
    class BadReference(RegimeReference):
        def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
            if metric == "head_circumference_cm":
                return bad_value  # type: ignore[return-value]
            return super().value(metric, age_days, reference_sex, z)

    with pytest.raises(ValueError, match="finite and positive"):
        AgeRegimeTrajectoryKernel(BadReference()).generate(
            PATIENT, (365,), NamedRandomStreams(5, 0)
        )


def test_kernel_rejects_declared_reference_domain() -> None:
    class NarrowReference(RegimeReference):
        min_age_days = 365
        max_age_days = 7000

    with pytest.raises(ValueError, match="reference domain"):
        AgeRegimeTrajectoryKernel(NarrowReference()).generate(
            PATIENT, (0,), NamedRandomStreams(5, 0)
        )
    with pytest.raises(ValueError, match="reference domain"):
        AgeRegimeTrajectoryKernel(NarrowReference()).generate(
            PATIENT, (7001,), NamedRandomStreams(5, 0)
        )


def test_kernel_converts_transition_bmi_overflow_to_value_error() -> None:
    class ExtremeTransitionReference(RegimeReference):
        def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
            if metric == "length_cm":
                return 1e308
            return super().value(metric, age_days, reference_sex, z)

    with pytest.raises(ValueError, match="derived BMI.*finite and positive"):
        AgeRegimeTrajectoryKernel(ExtremeTransitionReference()).generate(
            PATIENT, (730,), NamedRandomStreams(5, 0)
        )


def test_kernel_converts_post_transition_weight_overflow_to_value_error() -> None:
    class ExtremePostTransitionReference(RegimeReference):
        def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
            if metric == "height_cm":
                return 1e308
            return super().value(metric, age_days, reference_sex, z)

    with pytest.raises(ValueError, match="derived weight.*finite and positive"):
        AgeRegimeTrajectoryKernel(ExtremePostTransitionReference()).generate(
            PATIENT, (1000,), NamedRandomStreams(5, 0)
        )


@pytest.mark.parametrize("ages_days", [(730, 761), (699, 761), (699, 3000)])
def test_kernel_rejects_transition_discontinuity_across_sparse_samples(
    ages_days: tuple[int, int],
) -> None:
    class JumpReference(RegimeReference):
        def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
            value = super().value(metric, age_days, reference_sex, z)
            if metric == "height_cm" and age_days > 760:
                return value + 10.0
            return value

    with pytest.raises(ValueError, match="transition"):
        AgeRegimeTrajectoryKernel(JumpReference()).generate(
            PATIENT, ages_days, NamedRandomStreams(5, 0)
        )
