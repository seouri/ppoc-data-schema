from __future__ import annotations

import dataclasses
import json
import math

import pytest

from synthetic.cohort import (
    CalibrationSamplingProfile,
    CohortConfig,
    CohortGenerationUnavailable,
    CohortMember,
    CohortModuleWeight,
    NativeCohort,
    generate_native_cohort,
)
from synthetic.models import (
    AgeRegimeDisorderTrajectory,
    AgeRegimePoint,
    AgeRegimeState,
    AgeRegimeTrajectory,
    DisorderKind,
    GrowthRegime,
    LatentDisorderState,
)
from synthetic.native.age_regimes import AgeRegimeConfig
from synthetic.native.observations import (
    CensoringMode,
    ObservationFrame,
    ObservationPolicy,
    ObservationTruth,
    ObservationWindow,
)
from synthetic.native.resources import (
    BASE_RESOURCE_NAMES,
    ObservedResourceBundle,
    ResourceRow,
    ResourceShape,
    ResourceSpec,
    SyntheticDemographics,
)


def _policy() -> ObservationPolicy:
    return ObservationPolicy("cohort-observation-v1", 0, 731)


def _module_weights() -> tuple[CohortModuleWeight, ...]:
    return (
        CohortModuleWeight(DisorderKind.HEALTHY, 0.8),
        CohortModuleWeight(DisorderKind.GROWTH_HORMONE_DEFICIENCY, 0.2),
    )


def _config(**changes: object) -> CohortConfig:
    values: dict[str, object] = {
        "profile": "development-v1",
        "patient_count": 12,
        "seed": 7,
        "ages_days": (0, 365, 730),
        "observation_policy": _policy(),
        "module_weights": _module_weights(),
        "reference_sex_mapping": (("F", "F"), ("M", "M"), ("U", "U")),
    }
    values.update(changes)
    return CohortConfig(**values)  # type: ignore[arg-type]


def _calibration() -> CalibrationSamplingProfile:
    return CalibrationSamplingProfile(
        artifact_id="aggregate-artifact-v1",
        target_registry_version="calibration-targets-v1",
        sex_weights=(("F", 0.5), ("M", 0.49), ("U", 0.01)),
        ethnicity_weights=(("Unknown", 1.0),),
        race_weights=(("Unknown", 1.0),),
        race_multiselect_probability=0.1,
        recorded_healthy_probability=0.9,
        recorded_growth_dx_probability=0.1,
    )


def _trajectory(patient_id: str = "syn-cohort-member") -> AgeRegimeDisorderTrajectory:
    point = AgeRegimePoint(
        patient_id,
        365,
        GrowthRegime.INFANCY,
        75.0,
        None,
        9.0,
        None,
    )
    state = AgeRegimeState(
        "age-regimes-v1", 0.0, 0.0, 0.0, 0.0, 0.0, 4380, 900, 0.0, 0.0
    )
    return AgeRegimeDisorderTrajectory(
        AgeRegimeTrajectory((point,), state),
        LatentDisorderState(DisorderKind.HEALTHY, None, 0.0),
        (),
    )


def _frame(
    trajectory: AgeRegimeDisorderTrajectory | None = None,
    patient_id: str = "syn-cohort-member",
) -> ObservationFrame:
    window = ObservationWindow(0, 731, 731, CensoringMode.NONE)
    truth = ObservationTruth(
        patient_id,
        window,
        (),
        (),
        (),
        (),
        latent_trajectory_hash="a" * 64,
        truth_hash="b" * 64,
        policy=_policy(),
        latent_trajectory=trajectory,
    )
    return ObservationFrame(patient_id, "cohort-observation-v1", window, (), (), truth)


def _bundle(frame: ObservationFrame) -> ObservedResourceBundle:
    shape = ResourceShape(
        tuple(ResourceSpec(name, ("patient_id",)) for name in BASE_RESOURCE_NAMES)
    )
    rows = {
        name: (ResourceRow(name, (("patient_id", frame.patient_id),)),)
        if name == "patients"
        else ()
        for name in BASE_RESOURCE_NAMES
    }
    return ObservedResourceBundle(frame.patient_id, shape, rows, (), frame)


def _member(*, include_bundle: bool = True) -> CohortMember:
    trajectory = _trajectory()
    frame = _frame(trajectory)
    return CohortMember(
        SyntheticDemographics("syn-cohort-member"),
        trajectory,
        frame,
        _bundle(frame) if include_bundle else None,
    )


def test_cohort_models_are_frozen_and_defaults_are_explicit() -> None:
    weight = CohortModuleWeight(DisorderKind.HEALTHY, 1)
    config = _config()

    assert weight.probability == 1.0
    assert config.age_regime_config == AgeRegimeConfig()
    assert config.module_weights == _module_weights()
    with pytest.raises(dataclasses.FrozenInstanceError):
        weight.probability = 0.5  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.seed = 9  # type: ignore[misc]


@pytest.mark.parametrize("kind", ["healthy", None, 1])
def test_module_weight_rejects_non_enum_kinds(kind: object) -> None:
    with pytest.raises(TypeError, match="kind"):
        CohortModuleWeight(kind, 0.5)  # type: ignore[arg-type]


@pytest.mark.parametrize("probability", [True, -0.1, 1.1, math.inf, math.nan, "0.5"])
def test_module_weight_rejects_coercive_or_invalid_probabilities(probability: object) -> None:
    with pytest.raises((TypeError, ValueError), match="probability"):
        CohortModuleWeight(DisorderKind.HEALTHY, probability)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "profile",
    ["", "has whitespace", "../profile", "patient-profile", "truth-profile", 3],
)
def test_config_rejects_non_aggregate_safe_profiles(profile: object) -> None:
    with pytest.raises((TypeError, ValueError), match="profile"):
        _config(profile=profile)


@pytest.mark.parametrize("patient_count", [True, 0, -1, 100_001, 2.5, "10"])
def test_config_rejects_invalid_patient_counts(patient_count: object) -> None:
    with pytest.raises((TypeError, ValueError), match="patient_count"):
        _config(patient_count=patient_count)


@pytest.mark.parametrize("seed", [True, -1, 1.5, "7"])
def test_config_rejects_invalid_seeds(seed: object) -> None:
    with pytest.raises((TypeError, ValueError), match="seed"):
        _config(seed=seed)


@pytest.mark.parametrize(
    "ages_days",
    [(), [0, 1], (0, 0), (365, 0), (0, True), (0, -1), (0, 7306)],
)
def test_config_rejects_invalid_age_schedules(ages_days: object) -> None:
    with pytest.raises((TypeError, ValueError), match="ages_days"):
        _config(ages_days=ages_days)


def test_config_requires_an_observation_policy_and_age_regime_config() -> None:
    with pytest.raises(TypeError, match="observation_policy"):
        _config(observation_policy={})
    with pytest.raises(TypeError, match="age_regime_config"):
        _config(age_regime_config={})


@pytest.mark.parametrize(
    "module_weights",
    [
        [],
        (),
        (object(),),
        (
            CohortModuleWeight(DisorderKind.HEALTHY, 0.0),
            CohortModuleWeight(DisorderKind.GROWTH_HORMONE_DEFICIENCY, 0.0),
        ),
        (CohortModuleWeight(DisorderKind.GROWTH_HORMONE_DEFICIENCY, 1.0),),
        (CohortModuleWeight(DisorderKind.HEALTHY, 1.0),),
        (
            CohortModuleWeight(DisorderKind.HEALTHY, 0.5),
            CohortModuleWeight(DisorderKind.HEALTHY, 0.2),
            CohortModuleWeight(DisorderKind.CONSTITUTIONAL_DELAY, 0.3),
        ),
    ],
)
def test_config_rejects_malformed_or_incomplete_module_weights(
    module_weights: object,
) -> None:
    with pytest.raises((TypeError, ValueError), match="module_weights"):
        _config(module_weights=module_weights)


@pytest.mark.parametrize(
    "reference_sex_mapping",
    [
        [],
        (),
        (("F", "F"), ("M", "M")),
        (("F", "F"), ("F", "M"), ("U", "U")),
        (("F", "F"), ("M", "F"), ("U", "U")),
        (("F", "F"), ("M", "M"), ("X", "U")),
        (("F", "F"), ("M", "M"), ("U", "X")),
        (("F",), ("M", "M"), ("U", "U")),
    ],
)
def test_config_requires_complete_one_to_one_reference_sex_mapping(
    reference_sex_mapping: object,
) -> None:
    with pytest.raises((TypeError, ValueError), match="reference_sex_mapping"):
        _config(reference_sex_mapping=reference_sex_mapping)


def test_member_mapping_serializes_only_visible_contracts() -> None:
    member = _member()

    mapping = member.to_mapping()
    encoded = json.dumps(mapping, sort_keys=True)

    assert set(mapping) == {"demographics", "frame", "bundle"}
    assert mapping["demographics"]["patient_id"] == "syn-cohort-member"  # type: ignore[index]
    assert mapping["frame"]["contract"] == "observation-frame-v1"  # type: ignore[index]
    assert mapping["bundle"]["contract"] == "observed-resource-bundle-v1"  # type: ignore[index]
    assert "healthy" not in encoded
    assert "source_events" not in encoded
    assert "truth_hash" not in encoded
    assert "latent_trajectory_hash" not in encoded
    assert "stream" not in encoded
    assert repr(member) == "CohortMember(<evaluator-only>)"
    assert "syn-cohort-member" not in repr(member)


def test_member_without_bundle_omits_bundle_mapping() -> None:
    assert set(_member(include_bundle=False).to_mapping()) == {"demographics", "frame"}


def test_member_rejects_wrong_types_and_patient_mismatches() -> None:
    trajectory = _trajectory()
    frame = _frame(trajectory)
    demographics = SyntheticDemographics("syn-cohort-member")

    with pytest.raises(TypeError, match="demographics"):
        CohortMember(object(), trajectory, frame, None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="trajectory"):
        CohortMember(demographics, object(), frame, None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="frame"):
        CohortMember(demographics, trajectory, object(), None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="patient"):
        CohortMember(
            SyntheticDemographics("syn-other-member"), trajectory, frame, None
        )


def test_native_cohort_mapping_contains_only_visible_aggregate_counts() -> None:
    member = _member()
    cohort = NativeCohort("development-v1", 7, (member,), _calibration())

    assert cohort.to_mapping() == {
        "profile": "development-v1",
        "seed": 7,
        "member_count": 1,
        "bundle_count": 1,
        "visible_visit_count": 0,
        "visible_event_count": 0,
    }
    assert repr(cohort) == "NativeCohort(<evaluator-only>)"
    assert "syn-cohort-member" not in repr(cohort)
    assert "aggregate-artifact-v1" not in json.dumps(cohort.to_mapping())


def test_native_cohort_validates_container_types() -> None:
    calibration = _calibration()
    with pytest.raises(TypeError, match="members"):
        NativeCohort("development-v1", 7, [_member()], calibration)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="calibration"):
        NativeCohort("development-v1", 7, (), object())  # type: ignore[arg-type]


def test_generation_placeholder_fails_without_exposing_partial_results() -> None:
    assert issubclass(CohortGenerationUnavailable, ValueError)
    with pytest.raises(CohortGenerationUnavailable, match="assembly is not available"):
        generate_native_cohort(
            _config(),
            object(),
            _calibration(),
            modules={},
        )
