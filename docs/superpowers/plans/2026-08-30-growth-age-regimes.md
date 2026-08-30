# Growth Age-Regime Trajectories Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an engine-neutral, development-only physiology layer that generates coherent pediatric growth trajectories from birth through late adolescence across infancy, the 24-month measurement transition, childhood, puberty, and late adolescence without changing the visible eight-resource exporter.

**Architecture:** `models.py` gains validated age-regime enums, latent puberty/birth state, and richer evaluator-only trajectory points that can represent recumbent length, standing height, weight, BMI, head circumference, and derived velocities without changing the existing `LatentPoint` positional contract. `native/age_regimes.py` provides a versioned configuration and deterministic kernel using the existing `GrowthReference` interface, explicit two-dimension rules, a guarded length-to-height transition, and isolated named random streams. The existing healthy/disorder kernels and CSV mapping remain unchanged until a later integration slice.

**Tech Stack:** Python 3.12+, standard-library `dataclasses`, `enum`, `math`, NumPy named streams, existing `GrowthReference`, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-08-30-synthetic-growth-fixtures-design.md`

## Global Constraints

- `datapackage.json` remains the sole visible schema authority; this plan does not change CSV paths, headers, field order, types, null conventions, key semantics, or the eight-resource exporter.
- The existing `LatentPoint`, `HealthyKernel`, disorder modules, smoke profile, and test-only reference behavior remain backward compatible; new fields are appended only to new dataclasses or given defaults where an existing positional contract requires it.
- The age-regime layer is evaluator-only and development-only. Its latent state, regime points, puberty parameters, and velocities must not enter visible CSV rows, descriptors, manifests, ordinary loader APIs, or the current `generate_smoke` path.
- Each age regime uses exactly two independent anthropometric dimensions: recumbent length plus weight before the transition, and standing height plus BMI after the transition; the remaining anthropometric quantity is derived deterministically.
- The transition near 730 days uses an explicit length-to-height conversion and continuity guard; it must not silently create a discontinuity or independently sample all three of height, weight, and BMI.
- Every result is deterministic for identical reference identity, configuration, patient, named streams, and seed. Regime streams (`regime.birth`, `regime.childhood`, `regime.puberty`, `regime.residual`, and `regime.head`) are isolated from the existing `growth` stream and from one another.
- Unsupported metrics/domains, nonfinite or nonpositive reference values, invalid ages, invalid configurations, impossible transitions, and nonfinite velocities fail closed with `ValueError` or the reference’s documented lookup error.
- Default parameters are uncalibrated development scenarios. No real patient rows, diagnosis counts, clinical tables, prevalence estimates, or privacy evidence enter this plan.

---

### Task 1: Add validated age-regime model containers

**Files:**
- Modify: `src/synthetic/models.py`
- Create: `tests/synthetic/test_age_regime_models.py`

**Interfaces:**
- Produces `GrowthRegime(str, Enum)` values `infancy`, `transition`, `childhood`, `puberty`, and `adolescence`.
- Produces frozen `AgeRegimeState(module_version: str, birth_length_z: float, birth_weight_z: float, head_circumference_z: float, childhood_height_z: float, childhood_bmi_z: float, puberty_onset_age_days: int, puberty_tempo_days: int, puberty_height_spurt_z: float, puberty_bmi_shift_z: float)`.
- Produces frozen `AgeRegimePoint(patient_id: str, age_days: int, regime: GrowthRegime, length_cm: float | None, height_cm: float | None, weight_kg: float, bmi: float | None, head_circumference_cm: float | None, length_z: float | None, height_z: float | None, weight_z: float | None, bmi_z: float | None, height_velocity_cm_per_year: float | None, weight_velocity_kg_per_year: float | None)`.
- Produces frozen `AgeRegimeTrajectory(points: tuple[AgeRegimePoint, ...], state: AgeRegimeState)`.
- Consumes the existing `PatientState` and leaves existing `LatentPoint` and `LatentTrajectory` construction behavior unchanged.

- [ ] **Step 1: Write the failing model tests**

Create `tests/synthetic/test_age_regime_models.py`:

```python
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
        patient_id="syn-patient-a",
        age_days=730,
        regime=GrowthRegime.TRANSITION,
        length_cm=90.7,
        height_cm=90.0,
        weight_kg=12.96,
        bmi=16.0,
        head_circumference_cm=48.0,
        length_z=0.0,
        height_z=0.0,
        weight_z=0.0,
        bmi_z=0.0,
        height_velocity_cm_per_year=6.0,
        weight_velocity_kg_per_year=2.0,
    )
    trajectory = AgeRegimeTrajectory((point,), state)

    assert trajectory.points[0].regime is GrowthRegime.TRANSITION
    assert trajectory.state.module_version == "age-regimes-v1"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"module_version": "", "birth_length_z": 0.0},
        {"module_version": "v1", "birth_length_z": math.nan},
        {"module_version": "v1", "puberty_onset_age_days": -1},
        {"module_version": "v1", "puberty_tempo_days": 0},
    ],
)
def test_age_regime_state_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    values: dict[str, object] = {
        "module_version": "age-regimes-v1",
        "birth_length_z": 0.0,
        "birth_weight_z": 0.0,
        "head_circumference_z": 0.0,
        "childhood_height_z": 0.0,
        "childhood_bmi_z": 0.0,
        "puberty_onset_age_days": 4380,
        "puberty_tempo_days": 900,
        "puberty_height_spurt_z": 0.5,
        "puberty_bmi_shift_z": 0.1,
    }
    values.update(kwargs)

    with pytest.raises(ValueError):
        AgeRegimeState(**values)


def test_age_regime_point_requires_regime_appropriate_measurements() -> None:
    with pytest.raises(ValueError, match="length"):
        AgeRegimePoint(
            "syn-patient-a", 365, GrowthRegime.INFANCY, None, None, 8.0, None
        )
    with pytest.raises(ValueError, match="BMI"):
        AgeRegimePoint(
            "syn-patient-a", 4000, GrowthRegime.PUBERTY, None, 150.0, 45.0, None
        )


def test_age_regime_point_rejects_nonphysical_identity() -> None:
    with pytest.raises(ValueError, match="weight"):
        AgeRegimePoint(
            "syn-patient-a", 730, GrowthRegime.TRANSITION, 90.7, 90.0, 13.0, 16.0
        )


def test_existing_latent_point_positional_contract_is_unchanged() -> None:
    from synthetic.models import LatentPoint

    point = LatentPoint("syn-patient-a", 730, 90.0, 16.0, 12.96, 0.0, 0.0)

    assert point.age_days == 730
    assert point.weight_kg == pytest.approx(12.96)
```

- [ ] **Step 2: Run the model tests to verify they fail**

Run: `uv run pytest -q tests/synthetic/test_age_regime_models.py`

Expected: collection fails because the age-regime model types are not yet defined.

- [ ] **Step 3: Implement the validated age-regime model types**

In `src/synthetic/models.py`:

1. Add `GrowthRegime` with exactly the five string values in the interface.
2. Add frozen `AgeRegimeState` and reject an empty/non-string module version, nonfinite z-score or effect values, nonnegative-integer puberty onset ages, and nonpositive/noninteger puberty tempo.
3. Add frozen `AgeRegimePoint` with the field order in the interface. Validate a nonempty patient ID, a nonnegative integer age, a `GrowthRegime`, finite positive weight, optional finite positive length/height/BMI/head circumference, and finite optional z-scores and velocities.
4. Enforce representation rules: infancy requires length and weight and does not require standing height or BMI; transition requires length and standing height and permits BMI when it is derived from weight and height; childhood, puberty, and adolescence require standing height and BMI and do not accept a recumbent length. Head circumference is optional because references may not supply it after infancy.
5. When both standing height and BMI are present, require `weight_kg == bmi * (height_cm / 100) ** 2` within `1e-9` relative and absolute tolerance. Do not independently validate or generate a weight-for-length score in this slice.
6. Add frozen `AgeRegimeTrajectory`; require a tuple of `AgeRegimePoint` objects and an `AgeRegimeState`, and reject empty, mixed-patient, or non-increasing point sequences. Leave all existing dataclasses and positional construction behavior unchanged.

- [ ] **Step 4: Run the model tests and existing synthetic suite**

Run: `uv run pytest -q tests/synthetic/test_age_regime_models.py && uv run pytest -q tests/synthetic`

Expected: the new model tests and all existing synthetic tests pass.

- [ ] **Step 5: Run focused lint and commit**

Run: `uv run ruff check src/synthetic/models.py tests/synthetic/test_age_regime_models.py`

```bash
git add src/synthetic/models.py tests/synthetic/test_age_regime_models.py
git commit -m "feat: add age-regime trajectory models"
```

---

### Task 2: Add the versioned age-regime configuration and classifier

**Files:**
- Create: `src/synthetic/native/age_regimes.py`
- Create: `tests/synthetic/test_age_regime_config.py`

**Interfaces:**
- Produces frozen `AgeRegimeConfig` with `module_version = "age-regimes-v1"`, transition, reference-domain, puberty, catch-up, residual, and continuity parameters.
- Produces `classify_age(age_days: int, puberty_onset_age_days: int, puberty_tempo_days: int, config: AgeRegimeConfig) -> GrowthRegime`.
- Consumes `GrowthRegime` and `AgeRegimeState` from Task 1 and does not alter `HealthyKernel` or the disorder-module configuration.

- [ ] **Step 1: Write the failing configuration and classifier tests**

Create `tests/synthetic/test_age_regime_config.py`:

```python
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
```

- [ ] **Step 2: Run the configuration tests to verify they fail**

Run: `uv run pytest -q tests/synthetic/test_age_regime_config.py`

Expected: collection fails because `AgeRegimeConfig` and `classify_age` are not defined.

- [ ] **Step 3: Implement the validated configuration and classifier**

In `src/synthetic/native/age_regimes.py`:

1. Add frozen `AgeRegimeConfig` with `module_version: ClassVar[str] = "age-regimes-v1"` and these development-only defaults: `transition_age_days=730`, `transition_window_days=30`, `maximum_age_days=7305`, `puberty_min_age_days=3287`, `puberty_max_age_days=5114`, `puberty_tempo_min_days=730`, `puberty_tempo_max_days=1460`, `catch_up_days=730`, `head_circumference_decay_days=730`, `residual_sd=0.1`, `length_to_height_offset_cm=0.7`, `max_transition_discontinuity_cm=3.0`, `puberty_height_spurt_min=0.2`, `puberty_height_spurt_max=0.8`, `puberty_bmi_shift_min=-0.2`, and `puberty_bmi_shift_max=0.3`.
2. Validate all age values as nonnegative integers, all durations as positive integers where a duration is required, all scales as finite numeric values, ordered min/max pairs, `puberty_max_age_days + puberty_tempo_max_days <= maximum_age_days`, `transition_age_days + transition_window_days < maximum_age_days`, and a strictly positive continuity tolerance. Reject booleans explicitly.
3. Implement `classify_age` with the exact boundary policy used in the tests: ages below `transition_age_days - transition_window_days` are `INFANCY`; ages through `transition_age_days + transition_window_days` are `TRANSITION`; ages before puberty onset are `CHILDHOOD`; ages through onset plus tempo are `PUBERTY`; later ages are `ADOLESCENCE`. Reject negative ages and nonpositive puberty tempo.
4. Keep configuration/version metadata separate from calibrated prevalence or clinical evidence; no default is allowed to be described as representative.

- [ ] **Step 4: Run the configuration tests and existing suite**

Run: `uv run pytest -q tests/synthetic/test_age_regime_config.py && uv run pytest -q tests/synthetic`

Expected: all configuration and existing synthetic tests pass.

- [ ] **Step 5: Run lint and commit**

Run: `uv run ruff check src/synthetic/native/age_regimes.py tests/synthetic/test_age_regime_config.py`

```bash
git add src/synthetic/native/age_regimes.py tests/synthetic/test_age_regime_config.py
git commit -m "feat: add age-regime configuration"
```

---

### Task 3: Implement deterministic age-regime physiology

**Files:**
- Modify: `src/synthetic/native/age_regimes.py`
- Modify: `tests/synthetic/fakes.py`
- Create: `tests/synthetic/test_age_regime_kernel.py`

**Interfaces:**
- Produces `AgeRegimeTrajectoryKernel(reference: GrowthReference, config: AgeRegimeConfig | None = None)`.
- Produces `AgeRegimeTrajectoryKernel.generate(patient: PatientState, ages_days: tuple[int, ...], streams: NamedRandomStreams) -> AgeRegimeTrajectory`.
- Consumes `GrowthReference.value(...)`, `AgeRegimeConfig`, `classify_age`, `AgeRegimeState`, and `AgeRegimePoint` from Tasks 1–2.
- Never calls the existing `HealthyKernel` or modifies the current `generate_smoke`/`DisorderTrajectoryKernel` paths; integration with visible resources and disorder effects is a later slice.

- [ ] **Step 1: Write failing kernel tests**

Add a test-only `RegimeLinearTestReference` to `tests/synthetic/fakes.py` and create `tests/synthetic/test_age_regime_kernel.py`:

```python
class RegimeLinearTestReference:
    """Test-only reference with all metrics required by the age-regime kernel."""

    reference_id = "regime-linear-test-reference-v1"
    min_age_days = 0
    max_age_days = 7305

    def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
        del reference_sex
        age_years = age_days / 365.25
        standing_height = 74.0 + 5.5 * age_years + 3.0 * z
        if metric == "length_cm":
            return standing_height + 0.7
        if metric == "weight_kg":
            return 8.5 + 2.0 * age_years + 0.5 * z
        if metric == "head_circumference_cm":
            return 46.0 + 1.5 * age_years + 1.0 * z
        if metric == "height_cm":
            return standing_height
        if metric == "bmi":
            return 15.5 + 0.2 * age_years + 0.5 * z
        raise KeyError(metric)
```

```python
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
        point.height_velocity_cm_per_year is None or math.isfinite(point.height_velocity_cm_per_year)
        for point in trajectory.points
    )
    assert all(
        point.weight_velocity_kg_per_year is None or math.isfinite(point.weight_velocity_kg_per_year)
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
        "regime.birth", "regime.childhood", "regime.puberty", "regime.residual", "regime.head"
    }
    assert "growth" not in streams.names


def test_kernel_rejects_out_of_domain_or_nonphysical_reference_values() -> None:
    with pytest.raises(ValueError, match="domain"):
        AgeRegimeTrajectoryKernel(RegimeReference()).generate(
            PATIENT, (7306,), NamedRandomStreams(5, 0)
        )

    class BadReference(RegimeReference):
        def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
            if metric == "head_circumference_cm":
                return math.nan
            return super().value(metric, age_days, reference_sex, z)

    with pytest.raises(ValueError, match="finite and positive"):
        AgeRegimeTrajectoryKernel(BadReference()).generate(
            PATIENT, (365,), NamedRandomStreams(5, 0)
        )


def test_kernel_rejects_transition_discontinuity() -> None:
    class JumpReference(RegimeReference):
        def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
            value = super().value(metric, age_days, reference_sex, z)
            if metric == "height_cm" and age_days > 760:
                return value + 10.0
            return value

    with pytest.raises(ValueError, match="transition"):
        AgeRegimeTrajectoryKernel(JumpReference()).generate(
            PATIENT, (730, 761), NamedRandomStreams(5, 0)
        )
```

- [ ] **Step 2: Run the kernel tests to verify they fail**

Run: `uv run pytest -q tests/synthetic/test_age_regime_kernel.py`

Expected: collection fails because `AgeRegimeTrajectoryKernel` is not implemented.

- [ ] **Step 3: Implement the minimal deterministic kernel**

In `src/synthetic/native/age_regimes.py`:

1. Validate `ages_days` as a unique, increasing tuple of nonnegative integers bounded by `config.maximum_age_days`; honor optional integer `reference.min_age_days` and `reference.max_age_days` attributes and reject a request outside the declared domain.
2. Sample one `AgeRegimeState` per patient using only named streams: birth z-scores from `regime.birth`, childhood channel z-scores from `regime.childhood`, puberty onset/tempo/effects from `regime.puberty`, short-timescale residuals from `regime.residual`, and head-circumference residuals from `regime.head`. Do not request or advance the existing `growth` stream.
3. For infancy, compute age-decaying birth/catch-up z-scores, request `length_cm`, `weight_kg`, and `head_circumference_cm`, and populate only the recumbent-length/weight identity plus optional head circumference. For transition ages, request the same pre-transition quantities, convert standing height as `length_cm - config.length_to_height_offset_cm`, and derive BMI from that height and weight. For childhood, puberty, and adolescence, compute stable childhood z-scores plus a monotonic smooth-step pubertal height/BMI offset, request `height_cm` and `bmi`, and derive weight from them.
4. Use a deterministic smooth-step function `3*t*t - 2*t*t*t` for `t` clamped to `[0, 1]`; apply pubertal offsets only at and after the sampled onset, with the effect plateauing after `puberty_tempo_days`. The reference remains responsible for age-specific adult-height deceleration; the kernel must not claim a clinical velocity distribution.
5. Treat head circumference as optional after `config.head_circumference_decay_days`; omit it when the point is past the transition regime. Reject every nonfinite or nonpositive reference result before constructing a point.
6. Compute height velocity from comparable body size (`height_cm` after conversion, or `length_cm - offset` before conversion) and weight velocity over elapsed days using `365.25 / delta_days`. Set the first point’s velocities to `None`; reject nonfinite derived velocities.
7. Before returning `AgeRegimeTrajectory`, enforce the transition continuity tolerance between adjacent points crossing the transition window. Preserve patient IDs and ages, keep all latent state inside the returned evaluator-only object, and never call a CSV/resource mapper. Keep `RegimeLinearTestReference` under `tests/synthetic/fakes.py`; it is test-only and must not be imported by production code.

- [ ] **Step 4: Run focused kernel tests and the existing suite**

Run: `uv run pytest -q tests/synthetic/test_age_regime_kernel.py && uv run pytest -q tests/synthetic`

Expected: the new kernel tests and all existing synthetic tests pass.

- [ ] **Step 5: Run lint and commit**

Run: `uv run ruff check src/synthetic/native/age_regimes.py tests/synthetic/test_age_regime_kernel.py`

```bash
git add src/synthetic/native/age_regimes.py tests/synthetic/test_age_regime_kernel.py
git commit -m "feat: add deterministic age-regime kernel"
```

---

### Task 4: Document the age-regime boundary and evaluator-only usage

**Files:**
- Modify: `docs/synthetic-generator.md`

**Interfaces:**
- Consumes `AgeRegimeTrajectoryKernel`, `AgeRegimeConfig`, `AgeRegimePoint`, and `AgeRegimeTrajectory` from Tasks 1–3.
- Produces concise documentation of the age-regime API, transition semantics, uncalibrated defaults, and the unchanged visible smoke/export path.

- [ ] **Step 1: Update the usage guide**

In `docs/synthetic-generator.md`:

1. Clarify the current-scope paragraph to say that the visible smoke export remains healthy, age-730-and-older, and three-visit only; it does not export the new latent age-regime state.
2. Add a development-only example using `AgeRegimeTrajectoryKernel` with an injected test reference and ages spanning `0`, `730`, puberty, and `7305` days. Explain that the reference must provide `length_cm`, `weight_kg`, `head_circumference_cm`, `height_cm`, and `bmi` metrics for this example.
3. Describe the five regimes, the pre/post-24-month two-dimension rule, the explicit length-to-height conversion, and evaluator-only velocity/head-circumference fields. State that `AgeRegimeTrajectory.state` and `.points` are not exported to any CSV or manifest.
4. State that defaults are uncalibrated development scenarios; no WHO/CDC clinical table is bundled; prevalence, demographic calibration, disorder-critical descendants, held-out validation, privacy auditing, and Synthea conformance remain later gates.
5. Replace ambiguous “example below” wording with “smoke example” where the guide now contains more than one Python example. Keep the guide’s non-matchability limitation intact.

- [ ] **Step 2: Verify documentation and repository checks**

Run: `uv run pytest -q && uv run ruff check src tests && python3 schema/build.py --check && git diff --check`

Expected: all tests pass, Ruff is clean, eight schema resources validate, and Git reports no whitespace errors.

- [ ] **Step 3: Commit the documentation**

```bash
git add docs/synthetic-generator.md
git commit -m "docs: describe age-regime trajectories"
```

---

## Completion gate

Before merging this plan, verify that:

- `GrowthRegime`, `AgeRegimeState`, `AgeRegimePoint`, and `AgeRegimeTrajectory` are validated and do not change the existing `LatentPoint` contract.
- Birth/infancy uses length plus weight, standing-age regimes use height plus BMI, weight is derived after the transition, and the transition conversion is continuous within its declared tolerance.
- Puberty timing, tempo, smooth-step effects, late-adolescent regime labeling, head circumference, and velocities are deterministic and tested across multiple ages.
- The kernel rejects unsupported domains, nonphysical reference values, impossible schedules, discontinuities, nonfinite velocities, and invalid configurations.
- Named regime streams are isolated from the existing `growth` stream and identical inputs reproduce identical state and points.
- No age-regime latent state, evaluator point, clinical claim, prevalence claim, real patient row, or privacy evidence enters the visible eight-resource fixture package.
- Full pytest, Ruff, schema, and whitespace checks pass from the feature branch, and documentation labels the layer as uncalibrated development-only behavior.
