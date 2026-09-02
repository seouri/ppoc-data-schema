import dataclasses
import json
import math
from dataclasses import FrozenInstanceError

import pytest

from synthetic.golden_trajectories import (
    DEFAULT_GOLDEN_CASES,
    GOLDEN_CASE_IDS,
    GOLDEN_REASON_CODES,
    GOLDEN_TRAJECTORY_VERSION,
    GoldenCaseResult,
    GoldenPattern,
    GoldenStatus,
    GoldenTrajectoryCase,
    GoldenTrajectoryReport,
    GoldenTrajectoryUnavailable,
    run_golden_trajectory_suite,
)
from synthetic.models import (
    AgeRegimeDisorderTrajectory,
    AgeRegimeState,
    DisorderKind,
    GrowthRegime,
    LatentDisorderState,
    PatientState,
)
from synthetic.native.age_regime_disorder import AgeRegimeDisorderKernel
from synthetic.native.age_regimes import AgeRegimeTrajectoryKernel
from synthetic.native.clinical_modules import (
    CeliacDiseaseModule,
    ConstitutionalDelayModule,
    FamilialShortStatureModule,
    GrowthHormoneDeficiencyConfig,
    GrowthHormoneDeficiencyModule,
    HealthyGrowthModule,
    PediatricHypothyroidismModule,
    SmallForGestationalAgeModule,
)
from synthetic.randomness import NamedRandomStreams
from tests.synthetic.fakes import RegimeLinearTestReference

AGES = (0, 700, 730, 760, 3000, 4379, 4380, 4740, 5470, 5475, 6575, 7305)
REGIMES = tuple(GrowthRegime)
DISEASE_EVENTS = (
    "latent_onset",
    "observable_phenotype",
    "recognition_opportunity",
    "workup",
    "recorded_diagnosis",
)


def _modules() -> dict[DisorderKind, object]:
    return {
        DisorderKind.HEALTHY: HealthyGrowthModule(),
        DisorderKind.FAMILIAL_SHORT_STATURE: FamilialShortStatureModule(),
        DisorderKind.CONSTITUTIONAL_DELAY: ConstitutionalDelayModule(),
        DisorderKind.GROWTH_HORMONE_DEFICIENCY: GrowthHormoneDeficiencyModule(),
        DisorderKind.PEDIATRIC_HYPOTHYROIDISM: PediatricHypothyroidismModule(),
        DisorderKind.CELIAC_DISEASE: CeliacDiseaseModule(),
        DisorderKind.SMALL_FOR_GESTATIONAL_AGE: SmallForGestationalAgeModule(),
    }


def test_golden_catalog_has_fixed_metadata_states_and_patterns() -> None:
    assert GOLDEN_TRAJECTORY_VERSION == "growth-golden-v1"
    assert GOLDEN_CASE_IDS == (
        "golden-healthy-v1",
        "golden-familial-short-stature-v1",
        "golden-constitutional-delay-v1",
        "golden-growth-hormone-deficiency-v1",
        "golden-pediatric-hypothyroidism-v1",
        "golden-celiac-disease-v1",
        "golden-small-for-gestational-age-catch-up-v1",
        "golden-small-for-gestational-age-persistent-v1",
    )
    assert GOLDEN_REASON_CODES == (
        "NONDETERMINISTIC",
        "MISSING_REGIME",
        "MISSING_EVENT",
        "IDENTITY_VIOLATION",
        "HEIGHT_PATTERN",
        "BMI_PATTERN",
        "INVALID_TRAJECTORY",
    )
    assert tuple(case.case_id for case in DEFAULT_GOLDEN_CASES) == GOLDEN_CASE_IDS
    assert all(case.ages_days == AGES for case in DEFAULT_GOLDEN_CASES)
    assert all(case.required_regimes == REGIMES for case in DEFAULT_GOLDEN_CASES)
    expected_physiology = {
        "module_version": "age-regimes-v1",
        "birth_length_z": 0.1,
        "birth_weight_z": -0.1,
        "head_circumference_z": 0.2,
        "childhood_height_z": 0.0,
        "childhood_bmi_z": 0.0,
        "puberty_onset_age_days": 4380,
        "puberty_tempo_days": 1095,
        "puberty_height_spurt_z": 0.5,
        "puberty_bmi_shift_z": 0.0,
    }
    assert all(
        dataclasses.asdict(case.physiology_state) == expected_physiology
        for case in DEFAULT_GOLDEN_CASES
    )
    assert [case.required_event_types for case in DEFAULT_GOLDEN_CASES] == [
        (),
        DISEASE_EVENTS,
        DISEASE_EVENTS,
        DISEASE_EVENTS + ("treatment_start", "treatment_response"),
        DISEASE_EVENTS + ("treatment_start", "treatment_response"),
        DISEASE_EVENTS + ("treatment_start", "treatment_response"),
        DISEASE_EVENTS,
        DISEASE_EVENTS,
    ]
    assert [case.disorder_state for case in DEFAULT_GOLDEN_CASES] == [
        LatentDisorderState(DisorderKind.HEALTHY, None, 0.0),
        LatentDisorderState(DisorderKind.FAMILIAL_SHORT_STATURE, 0, 1.0),
        LatentDisorderState(DisorderKind.CONSTITUTIONAL_DELAY, 4380, 1.0, puberty_delay_days=360),
        LatentDisorderState(
            DisorderKind.GROWTH_HORMONE_DEFICIENCY,
            3000,
            1.0,
            treatment_start_age_days=3510,
            treatment_response=0.6,
        ),
        LatentDisorderState(
            DisorderKind.PEDIATRIC_HYPOTHYROIDISM,
            1460,
            1.0,
            treatment_start_age_days=1850,
            treatment_response=0.6,
        ),
        LatentDisorderState(
            DisorderKind.CELIAC_DISEASE,
            2190,
            1.0,
            treatment_start_age_days=2640,
            treatment_response=0.6,
        ),
        LatentDisorderState(DisorderKind.SMALL_FOR_GESTATIONAL_AGE, 0, 0.7),
        LatentDisorderState(DisorderKind.SMALL_FOR_GESTATIONAL_AGE, 0, 1.2),
    ]
    assert [case.height_pattern for case in DEFAULT_GOLDEN_CASES] == [
        GoldenPattern.ZERO,
        GoldenPattern.CONSTANT_NEGATIVE,
        GoldenPattern.DELAYED_RECOVERY,
        GoldenPattern.PROGRESSION_RESPONSE,
        GoldenPattern.PROGRESSION_RESPONSE,
        GoldenPattern.PROGRESSION_RESPONSE,
        GoldenPattern.BIRTH_CATCH_UP,
        GoldenPattern.CONSTANT_NEGATIVE,
    ]
    assert [case.bmi_pattern for case in DEFAULT_GOLDEN_CASES] == [
        GoldenPattern.ZERO,
        GoldenPattern.ZERO,
        GoldenPattern.ZERO,
        GoldenPattern.POSITIVE_AFTER_ONSET,
        GoldenPattern.POSITIVE_AFTER_ONSET,
        GoldenPattern.PROGRESSION_RESPONSE,
        GoldenPattern.BIRTH_CATCH_UP,
        GoldenPattern.BIRTH_CATCH_UP,
    ]
    assert DEFAULT_GOLDEN_CASES[2].pattern_probe_ages_days == (4380, 4740, 5470)
    assert DEFAULT_GOLDEN_CASES[3].pattern_probe_ages_days == (3000, 3510, 3875, 5000)
    assert DEFAULT_GOLDEN_CASES[4].pattern_probe_ages_days == (1460, 1850, 2215, 3000)
    assert DEFAULT_GOLDEN_CASES[5].pattern_probe_ages_days == (2190, 2640, 3005, 3500)
    assert DEFAULT_GOLDEN_CASES[6].pattern_probe_ages_days == (0, 365, 730, 1825)
    assert DEFAULT_GOLDEN_CASES[7].pattern_probe_ages_days == (0, 365, 730, 1825)


def test_case_is_frozen_redacted_exact_and_copies_tuple_inputs() -> None:
    source = DEFAULT_GOLDEN_CASES[1]
    ages = tuple(age for age in source.ages_days)
    regimes = tuple(regime for regime in source.required_regimes)
    events = tuple(event for event in source.required_event_types)
    probes = tuple(probe for probe in source.pattern_probe_ages_days)
    case = GoldenTrajectoryCase(
        source.case_id,
        source.patient,
        source.seed,
        ages,
        source.physiology_state,
        source.disorder_state,
        regimes,
        events,
        source.height_pattern,
        source.bmi_pattern,
        probes,
    )

    assert repr(case) == "<GoldenTrajectoryCase redacted>"
    assert case.ages_days is not ages
    assert case.required_regimes is not regimes
    assert case.required_event_types is not events
    assert case.pattern_probe_ages_days is not probes
    with pytest.raises(FrozenInstanceError):
        case.seed = 3  # type: ignore[misc]


def test_models_reject_subclasses_and_hostile_construction() -> None:
    class PatientSubclass(PatientState):
        pass

    class StateSubclass(AgeRegimeState):
        pass

    class DisorderSubclass(LatentDisorderState):
        pass

    source = DEFAULT_GOLDEN_CASES[0]
    patient = PatientSubclass("syn-golden-hostile", "F", "F")
    state = StateSubclass(**dataclasses.asdict(source.physiology_state))
    disorder = DisorderSubclass(DisorderKind.HEALTHY, None, 0.0)
    for replacement in (
        {"patient": patient},
        {"physiology_state": state},
        {"disorder_state": disorder},
    ):
        with pytest.raises((TypeError, ValueError)):
            dataclasses.replace(source, **replacement)

    for model in (GoldenTrajectoryCase, GoldenCaseResult, GoldenTrajectoryReport):
        with pytest.raises(TypeError):
            type("Hostile", (model,), {})


class NumericSubclass(float):
    pass


class TextSubclass(str):
    pass


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("module_version", TextSubclass("age-regimes-v1")),
        ("birth_length_z", NumericSubclass(0.1)),
        ("birth_weight_z", True),
        ("birth_weight_z", 0),
        ("head_circumference_z", math.nan),
        ("childhood_height_z", math.inf),
        ("childhood_bmi_z", "0.0"),
        ("puberty_onset_age_days", True),
        ("puberty_onset_age_days", 3286),
        ("puberty_tempo_days", 1095.0),
        ("puberty_tempo_days", 729),
        ("puberty_height_spurt_z", NumericSubclass(0.5)),
        ("puberty_height_spurt_z", 0.19),
        ("puberty_bmi_shift_z", False),
        ("puberty_bmi_shift_z", 0.31),
    ],
)
def test_case_rejects_every_malformed_nested_physiology_field(field: str, value: object) -> None:
    source = dataclasses.replace(DEFAULT_GOLDEN_CASES[0], case_id="golden-physiology-validation-v1")
    state = dataclasses.replace(source.physiology_state)
    object.__setattr__(state, field, value)

    with pytest.raises((TypeError, ValueError)):
        dataclasses.replace(source, physiology_state=state)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("kind", "healthy"),
        ("onset_age_days", True),
        ("severity", NumericSubclass(0.0)),
        ("severity", 0),
        ("severity", math.nan),
        ("puberty_delay_days", False),
        ("treatment_start_age_days", True),
        ("treatment_response", NumericSubclass(0.0)),
        ("treatment_response", 0),
        ("treatment_response", math.inf),
    ],
)
def test_case_rejects_every_malformed_nested_disorder_field(field: str, value: object) -> None:
    source = dataclasses.replace(DEFAULT_GOLDEN_CASES[0], case_id="golden-disorder-validation-v1")
    state = dataclasses.replace(source.disorder_state)
    object.__setattr__(state, field, value)

    with pytest.raises((TypeError, ValueError)):
        dataclasses.replace(source, disorder_state=state)


@pytest.mark.parametrize(
    ("case_index", "state"),
    [
        (0, LatentDisorderState(DisorderKind.HEALTHY, 123, 9.0)),
        (1, LatentDisorderState(DisorderKind.FAMILIAL_SHORT_STATURE, 1, 1.0)),
        (
            2,
            LatentDisorderState(DisorderKind.CONSTITUTIONAL_DELAY, 4380, 1.0, puberty_delay_days=0),
        ),
        (
            3,
            LatentDisorderState(
                DisorderKind.GROWTH_HORMONE_DEFICIENCY,
                3000,
                1.0,
                treatment_start_age_days=3510,
                treatment_response=0.5,
            ),
        ),
    ],
)
def test_fixed_cases_reject_incoherent_or_drifted_disorder_states(
    case_index: int, state: LatentDisorderState
) -> None:
    with pytest.raises((TypeError, ValueError)):
        dataclasses.replace(DEFAULT_GOLDEN_CASES[case_index], disorder_state=state)


def test_custom_case_ids_accept_coherent_nondefault_disorder_states() -> None:
    alternatives = (
        LatentDisorderState(DisorderKind.FAMILIAL_SHORT_STATURE, 0, 0.8),
        LatentDisorderState(
            DisorderKind.CONSTITUTIONAL_DELAY,
            4380,
            0.8,
            puberty_delay_days=180,
        ),
        LatentDisorderState(
            DisorderKind.GROWTH_HORMONE_DEFICIENCY,
            1000,
            0.8,
            treatment_start_age_days=1510,
            treatment_response=0.4,
        ),
    )
    for index, state in enumerate(alternatives, start=1):
        case = dataclasses.replace(
            DEFAULT_GOLDEN_CASES[index],
            case_id=f"golden-custom-{index}-v1",
            disorder_state=state,
        )
        assert case.disorder_state == state


def test_runner_revalidates_bypassed_invalid_exact_case_with_fixed_error() -> None:
    source = DEFAULT_GOLDEN_CASES[0]
    invalid = object.__new__(GoldenTrajectoryCase)
    for field in dataclasses.fields(GoldenTrajectoryCase):
        object.__setattr__(invalid, field.name, getattr(source, field.name))
    object.__setattr__(
        invalid,
        "disorder_state",
        LatentDisorderState(DisorderKind.HEALTHY, 123, 9.0),
    )

    with pytest.raises(GoldenTrajectoryUnavailable) as captured:
        run_golden_trajectory_suite(RegimeLinearTestReference(), cases=(invalid,))
    assert str(captured.value) == "golden trajectory suite unavailable"
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


@pytest.mark.parametrize(
    "replacement",
    [
        {"case_id": "patient-secret"},
        {"seed": True},
        {"ages_days": (0, 0)},
        {"ages_days": [0, 1]},
        {"required_regimes": (GrowthRegime.INFANCY, GrowthRegime.INFANCY)},
        {"required_event_types": ("latent_onset", "latent_onset")},
        {"pattern_probe_ages_days": (5, 4)},
        {"pattern_probe_ages_days": (0, 7306)},
        {"height_pattern": "zero"},
    ],
)
def test_case_rejects_malformed_values(replacement: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        dataclasses.replace(DEFAULT_GOLDEN_CASES[0], **replacement)


def test_default_runner_passes_deterministically_with_safe_canonical_report() -> None:
    left = run_golden_trajectory_suite(RegimeLinearTestReference())
    right = run_golden_trajectory_suite(RegimeLinearTestReference())

    assert left == right
    assert left.status is GoldenStatus.PASS
    assert left.report_version == GOLDEN_TRAJECTORY_VERSION
    assert tuple(result.case_id for result in left.case_results) == GOLDEN_CASE_IDS
    assert all(result.status is GoldenStatus.PASS for result in left.case_results)
    assert all(result.reason_codes == ("OK",) for result in left.case_results)
    expected_mapping = {
        "case_results": [
            {"case_id": case_id, "reason_codes": ["OK"], "status": "PASS"}
            for case_id in GOLDEN_CASE_IDS
        ],
        "report_version": "growth-golden-v1",
        "status": "PASS",
    }
    assert left.to_mapping() == expected_mapping
    assert left.to_json_bytes() == (
        json.dumps(
            expected_mapping,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("ascii")
        + b"\n"
    )
    payload = left.to_json_bytes().decode("ascii")
    for forbidden in (
        "syn-golden",
        "patient_id",
        "ages_days",
        "physiology_state",
        "disorder_state",
        "points",
        "measurements",
        "events",
        "seed",
        "reference",
        "module",
    ):
        assert forbidden not in payload


def test_default_cases_generate_all_regimes_physical_identities_and_ordered_events() -> None:
    reference = RegimeLinearTestReference()
    modules = _modules()
    for case in DEFAULT_GOLDEN_CASES:
        module = modules[case.disorder_state.kind]
        result = AgeRegimeDisorderKernel(AgeRegimeTrajectoryKernel(reference), module).generate(
            case.patient,
            case.ages_days,
            NamedRandomStreams(case.seed, 0),
            physiology_state=case.physiology_state,
            disorder_state=case.disorder_state,
        )
        assert type(result) is AgeRegimeDisorderTrajectory
        assert tuple(dict.fromkeys(point.regime for point in result.physiology.points)) == REGIMES
        assert tuple(event.event_type for event in result.events) == case.required_event_types
        assert [event.age_days for event in result.events] == sorted(
            event.age_days for event in result.events
        )
        for index, point in enumerate(result.physiology.points):
            assert math.isfinite(point.weight_kg) and point.weight_kg > 0
            if point.height_cm is not None and point.bmi is not None:
                assert point.height_cm > 0 and point.bmi > 0
                assert point.weight_kg == pytest.approx(point.bmi * (point.height_cm / 100) ** 2)
            if index == 0:
                assert point.height_velocity_cm_per_year is None
                assert point.weight_velocity_kg_per_year is None
            else:
                assert math.isfinite(point.height_velocity_cm_per_year)
                assert math.isfinite(point.weight_velocity_kg_per_year)


def test_each_declared_directional_pattern_matches_direct_module_effects() -> None:
    modules = _modules()
    for case in DEFAULT_GOLDEN_CASES:
        module = modules[case.disorder_state.kind]
        height = tuple(
            module.height_z_delta(case.disorder_state, age) for age in case.pattern_probe_ages_days
        )
        bmi = tuple(
            module.bmi_z_delta(case.disorder_state, age) for age in case.pattern_probe_ages_days
        )
        if case.height_pattern is GoldenPattern.ZERO:
            assert height == tuple(0.0 for _ in height)
        elif case.height_pattern is GoldenPattern.CONSTANT_NEGATIVE:
            assert all(value < 0 for value in height)
            assert len(set(height)) == 1
        elif case.height_pattern is GoldenPattern.DELAYED_RECOVERY:
            assert height[0] == 0 and height[1] < 0 and height[2] == 0
        elif case.height_pattern is GoldenPattern.BIRTH_CATCH_UP:
            assert height[0] < 0
            assert height[0] < height[1] <= height[2] <= height[3]
            assert height[3] == 0
        else:
            assert height[0] == 0 and height[1] < 0
            assert height[2] > height[1] and height[3] >= height[2]
        if case.bmi_pattern is GoldenPattern.ZERO:
            assert bmi == tuple(0.0 for _ in bmi)
        elif case.bmi_pattern is GoldenPattern.PROGRESSION_RESPONSE:
            assert bmi[0] == 0 and bmi[1] < 0
            assert bmi[1] < bmi[2] <= bmi[3]
        elif case.bmi_pattern is GoldenPattern.BIRTH_CATCH_UP:
            assert bmi[0] < 0
            assert bmi[0] < bmi[1] <= bmi[2] <= bmi[3]
            assert bmi[3] == 0
        else:
            assert bmi[0] == 0 and all(value > 0 for value in bmi[1:])


def test_nondeterministic_reference_returns_only_fixed_failure_reason() -> None:
    class NondeterministicReference(RegimeLinearTestReference):
        def __init__(self) -> None:
            self.calls = 0

        def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
            self.calls += 1
            return super().value(metric, age_days, reference_sex, z) + self.calls * 1e-8

    report = run_golden_trajectory_suite(
        NondeterministicReference(), cases=(DEFAULT_GOLDEN_CASES[0],)
    )

    assert report.status is GoldenStatus.FAIL
    assert report.case_results == (
        GoldenCaseResult("golden-healthy-v1", GoldenStatus.FAIL, ("NONDETERMINISTIC",)),
    )


def test_hostile_physical_output_returns_identity_violation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = DEFAULT_GOLDEN_CASES[0]
    trajectory = AgeRegimeDisorderKernel(
        AgeRegimeTrajectoryKernel(RegimeLinearTestReference()), HealthyGrowthModule()
    ).generate(
        case.patient,
        case.ages_days,
        NamedRandomStreams(case.seed, 0),
        physiology_state=case.physiology_state,
        disorder_state=case.disorder_state,
    )
    object.__setattr__(
        trajectory.physiology.points[0],
        "weight_kg",
        trajectory.physiology.points[0].weight_kg + 1.0,
    )

    def hostile_generate(*args: object, **kwargs: object) -> AgeRegimeDisorderTrajectory:
        del args, kwargs
        return trajectory

    monkeypatch.setattr(AgeRegimeDisorderKernel, "generate", hostile_generate)
    report = run_golden_trajectory_suite(RegimeLinearTestReference(), cases=(case,))

    assert report.case_results[0].reason_codes == ("IDENTITY_VIOLATION",)


@pytest.mark.parametrize(
    ("point_index", "field", "value"),
    [
        (0, "head_circumference_cm", -1.0),
        (4, "bmi", None),
        (0, "height_cm", 50.0),
        (2, "height_cm", None),
        (4, "length_cm", 100.0),
        (4, "head_circumference_cm", 50.0),
        (4, "height_z", None),
        (0, "weight_kg", True),
        (1, "height_velocity_cm_per_year", math.nan),
    ],
)
def test_hostile_malformed_measurements_never_pass(
    monkeypatch: pytest.MonkeyPatch,
    point_index: int,
    field: str,
    value: object,
) -> None:
    case = DEFAULT_GOLDEN_CASES[0]
    trajectory = AgeRegimeDisorderKernel(
        AgeRegimeTrajectoryKernel(RegimeLinearTestReference()), HealthyGrowthModule()
    ).generate(
        case.patient,
        case.ages_days,
        NamedRandomStreams(case.seed, 0),
        physiology_state=case.physiology_state,
        disorder_state=case.disorder_state,
    )
    object.__setattr__(trajectory.physiology.points[point_index], field, value)

    def hostile_generate(*args: object, **kwargs: object) -> AgeRegimeDisorderTrajectory:
        del args, kwargs
        return trajectory

    monkeypatch.setattr(AgeRegimeDisorderKernel, "generate", hostile_generate)
    report = run_golden_trajectory_suite(RegimeLinearTestReference(), cases=(case,))

    assert report.status is GoldenStatus.FAIL
    assert report.case_results[0].reason_codes in (
        ("IDENTITY_VIOLATION",),
        ("INVALID_TRAJECTORY",),
    )


def test_hostile_wrong_patient_output_returns_invalid_trajectory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = DEFAULT_GOLDEN_CASES[0]
    trajectory = AgeRegimeDisorderKernel(
        AgeRegimeTrajectoryKernel(RegimeLinearTestReference()), HealthyGrowthModule()
    ).generate(
        case.patient,
        case.ages_days,
        NamedRandomStreams(case.seed, 0),
        physiology_state=case.physiology_state,
        disorder_state=case.disorder_state,
    )
    object.__setattr__(trajectory.physiology.points[0], "patient_id", "syn-golden-hostile")

    def hostile_generate(*args: object, **kwargs: object) -> AgeRegimeDisorderTrajectory:
        del args, kwargs
        return trajectory

    monkeypatch.setattr(AgeRegimeDisorderKernel, "generate", hostile_generate)
    report = run_golden_trajectory_suite(RegimeLinearTestReference(), cases=(case,))

    assert report.case_results[0].reason_codes == ("INVALID_TRAJECTORY",)


def test_missing_regime_event_and_broken_pattern_are_fixed_case_failures() -> None:
    sparse = dataclasses.replace(DEFAULT_GOLDEN_CASES[0], ages_days=(1000, 3000))
    sparse_report = run_golden_trajectory_suite(RegimeLinearTestReference(), cases=(sparse,))
    assert sparse_report.case_results[0].reason_codes == ("MISSING_REGIME",)

    class EmptyFamilialEvents(FamilialShortStatureModule):
        module_version = "familial-empty-events-test-v1"

        def events(self, patient: PatientState, state: LatentDisorderState) -> tuple[()]:
            del patient, state
            return ()

    modules = _modules()
    modules[DisorderKind.FAMILIAL_SHORT_STATURE] = EmptyFamilialEvents()
    with pytest.raises(GoldenTrajectoryUnavailable, match="unavailable"):
        run_golden_trajectory_suite(
            RegimeLinearTestReference(),
            modules=modules,
            cases=(DEFAULT_GOLDEN_CASES[1],),
        )

    class BrokenFamilialPattern(FamilialShortStatureModule):
        module_version = "familial-broken-pattern-test-v1"

        def height_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
            del state, age_days
            return 0.0

    modules[DisorderKind.FAMILIAL_SHORT_STATURE] = BrokenFamilialPattern()
    broken_pattern = run_golden_trajectory_suite(
        RegimeLinearTestReference(),
        modules=modules,
        cases=(DEFAULT_GOLDEN_CASES[1],),
    )
    assert broken_pattern.case_results[0].reason_codes == ("HEIGHT_PATTERN",)


def test_progression_response_accepts_complete_nonregressing_recovery() -> None:
    class CompleteRecoveryModule(GrowthHormoneDeficiencyModule):
        module_version = "growth-hormone-deficiency-complete-recovery-test-v1"

        def height_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
            assert state.onset_age_days is not None
            if age_days <= state.onset_age_days:
                return 0.0
            assert state.treatment_start_age_days is not None
            if age_days <= state.treatment_start_age_days:
                return -(age_days - state.onset_age_days) / (
                    state.treatment_start_age_days - state.onset_age_days
                )
            return min(
                -1.0 + (age_days - state.treatment_start_age_days) / 365.0,
                0.1,
            )

        def bmi_z_delta(self, state: LatentDisorderState, age_days: int) -> float:
            assert state.onset_age_days is not None
            return 0.0 if age_days <= state.onset_age_days else 0.1

    modules = _modules()
    modules[DisorderKind.GROWTH_HORMONE_DEFICIENCY] = CompleteRecoveryModule()

    report = run_golden_trajectory_suite(
        RegimeLinearTestReference(),
        modules=modules,
        cases=(DEFAULT_GOLDEN_CASES[3],),
    )

    assert report.status is GoldenStatus.PASS
    assert report.case_results[0].reason_codes == ("OK",)


def test_custom_case_accepts_matching_alternate_module_timing() -> None:
    config = GrowthHormoneDeficiencyConfig(treatment_delay_days=100)
    treatment_start = 3520
    state = LatentDisorderState(
        DisorderKind.GROWTH_HORMONE_DEFICIENCY,
        3000,
        1.0,
        treatment_start_age_days=treatment_start,
        treatment_response=0.6,
    )
    case = dataclasses.replace(
        DEFAULT_GOLDEN_CASES[3],
        case_id="golden-ghd-alternate-timing-v1",
        disorder_state=state,
        pattern_probe_ages_days=(3000, treatment_start, treatment_start + 365, 5000),
    )
    modules = _modules()
    modules[DisorderKind.GROWTH_HORMONE_DEFICIENCY] = GrowthHormoneDeficiencyModule(config)

    report = run_golden_trajectory_suite(
        RegimeLinearTestReference(), modules=modules, cases=(case,)
    )

    assert report.status is GoldenStatus.PASS
    assert report.case_results[0] == GoldenCaseResult(case.case_id, GoldenStatus.PASS, ("OK",))


@pytest.mark.parametrize(
    ("modules", "cases"),
    [
        ({DisorderKind.HEALTHY: HealthyGrowthModule()}, DEFAULT_GOLDEN_CASES),
        ({**_modules(), DisorderKind.HEALTHY: object()}, DEFAULT_GOLDEN_CASES),
        (None, list(DEFAULT_GOLDEN_CASES)),
        (None, (DEFAULT_GOLDEN_CASES[0], DEFAULT_GOLDEN_CASES[0])),
    ],
)
def test_invalid_suite_inputs_raise_fixed_unavailable_without_sensitive_context(
    modules: object, cases: object
) -> None:
    with pytest.raises(GoldenTrajectoryUnavailable) as captured:
        run_golden_trajectory_suite(
            RegimeLinearTestReference(),
            modules=modules,
            cases=cases,  # type: ignore[arg-type]
        )
    assert str(captured.value) == "golden trajectory suite unavailable"
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


def test_reference_failure_is_redacted_without_exception_context_or_value_echo() -> None:
    class RaisingReference(RegimeLinearTestReference):
        def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
            del metric, age_days, reference_sex, z
            raise RuntimeError("syn-golden-secret-patient 4380")

    with pytest.raises(GoldenTrajectoryUnavailable) as captured:
        run_golden_trajectory_suite(RaisingReference())
    assert str(captured.value) == "golden trajectory suite unavailable"
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert captured.value.__suppress_context__ is False


def test_result_and_report_reject_inconsistent_or_overridable_values() -> None:
    with pytest.raises((TypeError, ValueError)):
        GoldenCaseResult("golden-safe-v1", GoldenStatus.PASS, ("MISSING_EVENT",))
    with pytest.raises((TypeError, ValueError)):
        GoldenCaseResult("golden-safe-v1", GoldenStatus.FAIL, ("OK",))
    with pytest.raises((TypeError, ValueError)):
        GoldenCaseResult("golden-safe-v1", GoldenStatus.FAIL, ("BMI_PATTERN", "HEIGHT_PATTERN"))
    passing = GoldenCaseResult("golden-safe-v1", GoldenStatus.PASS, ("OK",))
    report = GoldenTrajectoryReport(GOLDEN_TRAJECTORY_VERSION, GoldenStatus.PASS, (passing,))
    assert repr(passing) == "<GoldenCaseResult redacted>"
    assert repr(report) == "<GoldenTrajectoryReport aggregate>"
    with pytest.raises((TypeError, ValueError)):
        GoldenTrajectoryReport(GOLDEN_TRAJECTORY_VERSION, GoldenStatus.FAIL, (passing,))
