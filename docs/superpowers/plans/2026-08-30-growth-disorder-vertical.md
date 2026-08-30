# Growth Disorder Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an engine-neutral latent disorder layer that produces directionally coherent healthy, familial-short-stature, constitutional-delay, and growth-hormone-deficiency trajectories with hidden event traces, without exporting latent truth or claiming calibrated prevalence.

**Architecture:** `models.py` gains validated latent disorder state and trajectory containers. Versioned module classes in `native/clinical_modules.py` sample deterministic state from named random streams, apply height/BMI z-score effects, and emit ordered latent/observable clinical events. `native/trajectories.py` wraps the existing healthy reference kernel, re-materializes height and BMI through the reference after module effects, derives weight, and returns a latent trajectory object that is not consumed by the visible CSV exporter in this slice.

**Tech Stack:** Python 3.12+, standard-library `dataclasses`, `enum`, `math`, NumPy named streams, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-08-30-synthetic-growth-fixtures-design.md`

## Global Constraints

- The existing `HealthyKernel` default behavior, named `growth` stream, `LatentPoint` fields, height/BMI-to-weight identity, and exact eight-resource export remain backward compatible.
- Latent disorder state and event traces are evaluator-only objects; they must not enter visible CSV rows, generated descriptors, ordinary loader APIs, or manifests.
- Modules are versioned scenario mechanisms, not prevalence estimates or clinical validation; no real patient rows, diagnosis counts, clinical reference tables, or calibration artifacts enter this plan.
- Effects are applied to only two independent anthropometric dimensions (`height_z` and `bmi_z`); weight is always re-derived from the resulting BMI and height.
- All generated values and transition ages are deterministic for identical module configuration, patient, named streams, and seed; module streams must not consume the baseline `growth` stream.
- Latent event order is causal and deterministic: onset precedes phenotype, recognition, workup, diagnosis, treatment, and response; absent treatment produces no treatment descendants.
- Unsupported ages, nonfinite effects, nonphysical reference output, invalid probabilities, and impossible schedules fail closed with `ValueError`.
- Default module parameters are explicitly uncalibrated development scenarios and must not be described as representative of real prevalence, demographics, or outcomes.

---

### Task 1: Add validated latent disorder and trajectory models

**Files:**
- Modify: `src/synthetic/models.py`
- Create: `tests/synthetic/test_latent_models.py`

**Interfaces:**
- Produces `DisorderKind` string enum values `healthy`, `familial_short_stature`, `constitutional_delay`, and `growth_hormone_deficiency`.
- Produces frozen `LatentDisorderState(kind: DisorderKind, onset_age_days: int | None, severity: float, puberty_delay_days: int = 0, treatment_start_age_days: int | None = None, treatment_response: float = 0.0)`.
- Produces frozen `LatentTrajectory(points: tuple[LatentPoint, ...], disorder: LatentDisorderState, events: tuple[ClinicalEvent, ...])`.
- Consumes the existing `LatentPoint` and `ClinicalEvent` models without changing their existing fields or positional construction behavior.

- [ ] **Step 1: Write the failing model tests**

Create `tests/synthetic/test_latent_models.py`:

```python
import math

import pytest

from synthetic.models import ClinicalEvent, DisorderKind, LatentDisorderState, LatentPoint, LatentTrajectory


def test_disorder_state_accepts_valid_treatment_schedule() -> None:
    state = LatentDisorderState(
        kind=DisorderKind.GROWTH_HORMONE_DEFICIENCY,
        onset_age_days=900,
        severity=0.8,
        treatment_start_age_days=1200,
        treatment_response=0.6,
    )

    assert state.kind is DisorderKind.GROWTH_HORMONE_DEFICIENCY
    assert state.treatment_start_age_days == 1200


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": "", "onset_age_days": 0, "severity": 0.5},
        {"kind": DisorderKind.HEALTHY, "onset_age_days": -1, "severity": 0.5},
        {"kind": DisorderKind.HEALTHY, "onset_age_days": 0, "severity": math.nan},
        {"kind": DisorderKind.HEALTHY, "onset_age_days": 0, "severity": -0.1},
        {
            "kind": DisorderKind.HEALTHY,
            "onset_age_days": 1000,
            "severity": 0.5,
            "treatment_start_age_days": 999,
        },
        {
            "kind": DisorderKind.HEALTHY,
            "onset_age_days": 0,
            "severity": 0.5,
            "treatment_response": 1.1,
        },
    ],
)
def test_disorder_state_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        LatentDisorderState(**kwargs)


def test_latent_trajectory_is_frozen_and_keeps_hidden_events_separate() -> None:
    point = LatentPoint("syn-patient-a", 730, 90.0, 16.0, 12.96, 0.0, 0.0)
    event = ClinicalEvent("syn-patient-a", 0, "latent_onset", None, True)
    trajectory = LatentTrajectory(
        points=(point,),
        disorder=LatentDisorderState(DisorderKind.HEALTHY, None, 0.0),
        events=(event,),
    )

    assert trajectory.points == (point,)
    assert trajectory.events[0].hidden is True
    with pytest.raises(AttributeError):
        trajectory.points = ()
```

- [ ] **Step 2: Run the model tests to verify they fail**

Run: `uv run pytest -q tests/synthetic/test_latent_models.py`

Expected: collection fails because `DisorderKind`, `LatentDisorderState`, and `LatentTrajectory` are not defined.

- [ ] **Step 3: Implement the validated model types**

In `src/synthetic/models.py`:

1. Add a `DisorderKind(str, Enum)` with exactly the four values listed in the interface.
2. Add frozen `LatentDisorderState` validation: `kind` must be a `DisorderKind`, onset and treatment ages must be nonnegative integers or `None`, severity must be finite and nonnegative, puberty delay must be a nonnegative integer, treatment must not precede onset, and treatment response must be finite in `[0, 1]`.
3. Add frozen `LatentTrajectory` after `ClinicalEvent`, storing the exact tuple types in the interface. Reject no additional values; module-specific schedule validation belongs to each module configuration.
4. Leave all existing dataclasses and field ordering intact so existing positional tests continue to work.

- [ ] **Step 4: Run the model tests and existing suite**

Run: `uv run pytest -q tests/synthetic/test_latent_models.py && uv run pytest -q tests/synthetic`

Expected: the new model tests and all existing tests pass.

- [ ] **Step 5: Run lint and commit**

Run: `uv run ruff check src/synthetic/models.py tests/synthetic/test_latent_models.py`

```bash
git add src/synthetic/models.py tests/synthetic/test_latent_models.py
git commit -m "feat: add latent disorder trajectory models"
```

---

### Task 2: Implement the first four versioned clinical modules

**Files:**
- Create: `src/synthetic/native/clinical_modules.py`
- Create: `tests/synthetic/test_clinical_modules.py`

**Interfaces:**
- Produces `GrowthDisorderModule` protocol with `kind`, `sample_state(patient, streams)`, `height_z_delta(state, age_days)`, `bmi_z_delta(state, age_days)`, and `events(patient, state)` methods.
- Produces `HealthyGrowthModule`, `FamilialShortStatureModule`, `ConstitutionalDelayModule`, and `GrowthHormoneDeficiencyModule`.
- Each module has a frozen configuration with finite, validated parameters; defaults are uncalibrated development scenarios.
- Consumes `PatientState`, `ClinicalEvent`, `DisorderKind`, `LatentDisorderState`, and `NamedRandomStreams` from earlier tasks.

- [ ] **Step 1: Write failing module behavior tests**

Create `tests/synthetic/test_clinical_modules.py`:

```python
import pytest

from synthetic.models import DisorderKind, PatientState
from synthetic.native.clinical_modules import (
    ConstitutionalDelayModule,
    FamilialShortStatureModule,
    GrowthHormoneDeficiencyModule,
    HealthyGrowthModule,
)
from synthetic.randomness import NamedRandomStreams


PATIENT = PatientState("syn-patient-a", "F", "F")


def test_healthy_module_has_no_effects_or_events() -> None:
    module = HealthyGrowthModule()
    state = module.sample_state(PATIENT, NamedRandomStreams(5, 0))

    assert state.kind is DisorderKind.HEALTHY
    assert state.severity == 0.0
    assert module.height_z_delta(state, 1000) == 0.0
    assert module.bmi_z_delta(state, 1000) == 0.0
    assert module.events(PATIENT, state) == ()


def test_familial_short_stature_preserves_velocity_with_constant_height_offset() -> None:
    module = FamilialShortStatureModule()
    state = module.sample_state(PATIENT, NamedRandomStreams(5, 0))

    assert state.kind is DisorderKind.FAMILIAL_SHORT_STATURE
    assert module.height_z_delta(state, 730) < 0
    assert module.height_z_delta(state, 5000) == pytest.approx(
        module.height_z_delta(state, 730)
    )
    assert module.bmi_z_delta(state, 2000) == 0.0
    assert [event.event_type for event in module.events(PATIENT, state)] == [
        "latent_onset",
        "observable_phenotype",
        "recognition_opportunity",
        "workup",
        "recorded_diagnosis",
    ]


def test_constitutional_delay_has_temporary_puberty_effect_and_ordered_events() -> None:
    module = ConstitutionalDelayModule()
    state = module.sample_state(PATIENT, NamedRandomStreams(5, 0))
    puberty_age = module.config.expected_puberty_age_days
    delayed_end = puberty_age + state.puberty_delay_days

    assert module.height_z_delta(state, puberty_age - 1) == 0.0
    assert module.height_z_delta(state, puberty_age + state.puberty_delay_days // 2) < 0
    assert module.height_z_delta(state, delayed_end + module.config.recovery_days) == 0.0
    ages = [event.age_days for event in module.events(PATIENT, state)]
    assert ages == sorted(ages)
    assert ages[0] == puberty_age


def test_growth_hormone_deficiency_progresses_and_treatment_has_response() -> None:
    module = GrowthHormoneDeficiencyModule()
    state = module.sample_state(PATIENT, NamedRandomStreams(5, 0))
    assert state.kind is DisorderKind.GROWTH_HORMONE_DEFICIENCY
    assert state.onset_age_days is not None
    onset = state.onset_age_days
    assert module.height_z_delta(state, onset - 1) == 0.0
    untreated = module.height_z_delta(state, onset + module.config.progression_days)
    assert untreated < 0
    if state.treatment_start_age_days is not None:
        response_age = state.treatment_start_age_days + module.config.response_days
        assert module.height_z_delta(state, response_age) > untreated
        event_types = [event.event_type for event in module.events(PATIENT, state)]
        assert "treatment_start" in event_types
        assert "treatment_response" in event_types


def test_module_sampling_is_reproducible_and_uses_named_streams() -> None:
    modules = (FamilialShortStatureModule(), ConstitutionalDelayModule(), GrowthHormoneDeficiencyModule())
    for module in modules:
        left = module.sample_state(PATIENT, NamedRandomStreams(123, 7))
        right = module.sample_state(PATIENT, NamedRandomStreams(123, 7))
        assert left == right
```

- [ ] **Step 2: Run module tests to verify they fail**

Run: `uv run pytest -q tests/synthetic/test_clinical_modules.py`

Expected: collection fails because `clinical_modules.py` is not present.

- [ ] **Step 3: Implement validated module configurations and effects**

In `src/synthetic/native/clinical_modules.py`:

1. Define the protocol exactly as specified. Modules must use a stream name scoped by `disorder.<kind.value>` and must never call the baseline `growth` stream.
2. `HealthyGrowthModule` returns a healthy zero-severity state, zero effects, and no events.
3. `FamilialShortStatureModule` samples a severity uniformly between validated `severity_min` and `severity_max` (default `0.7` and `1.3`), applies a constant negative height-z offset and zero BMI-z offset, and emits ordered onset/phenotype/recognition/workup/diagnosis events at its validated schedule.
4. `ConstitutionalDelayModule` samples a nonnegative puberty delay (default range `180`–`720` days), applies zero height effect before expected puberty, a negative triangular delay effect through the delayed-puberty interval, and returns to zero after `recovery_days` (default `730`). Its event schedule begins at expected puberty.
5. `GrowthHormoneDeficiencyModule` samples onset in a validated age interval (default `730`–`3652` days), severity, and optional treatment using a validated probability. Height effect is zero before onset, becomes progressively more negative over `progression_days`, and recovers only after treatment according to `treatment_response` and `response_days`; BMI effect is a bounded positive consequence of the untreated fraction. Untreated states emit no treatment descendants.
6. Use `ClinicalEvent.hidden=True` only for latent onset; observable phenotype and downstream events are visible in the latent event trace but are not exported by this plan. Keep `code=None` until terminology mapping is separately reviewed.
7. Validate every configuration’s integer ages/durations, ordered bounds, probabilities in `[0,1]`, and finite nonnegative magnitudes. Sort events by age and a fixed causal phase order, rejecting impossible schedules.

- [ ] **Step 4: Run focused tests, full suite, and lint**

Run: `uv run pytest -q tests/synthetic/test_clinical_modules.py && uv run pytest -q tests/synthetic && uv run ruff check src/synthetic/native/clinical_modules.py tests/synthetic/test_clinical_modules.py`

Expected: all module and existing tests pass, with no Ruff findings.

- [ ] **Step 5: Commit the modules**

```bash
git add src/synthetic/native/clinical_modules.py tests/synthetic/test_clinical_modules.py
git commit -m "feat: add growth disorder clinical modules"
```

---

### Task 3: Add the disorder-aware latent trajectory kernel

**Files:**
- Create: `src/synthetic/native/trajectories.py`
- Create: `tests/synthetic/test_disorder_trajectories.py`

**Interfaces:**
- Produces `DisorderTrajectoryKernel(healthy: HealthyKernel, module: GrowthDisorderModule)`.
- Produces `generate(patient, ages_days, streams) -> LatentTrajectory`.
- Consumes `HealthyKernel`, `GrowthDisorderModule`, `LatentDisorderState`, `LatentPoint`, `LatentTrajectory`, and the existing reference guard semantics.
- Does not change `generate_smoke`, CSV mapping, visible descriptors, or ordinary loader APIs.

- [ ] **Step 1: Write failing trajectory tests**

Create `tests/synthetic/test_disorder_trajectories.py`:

```python
import pytest

from synthetic.models import DisorderKind, PatientState
from synthetic.native.clinical_modules import (
    ConstitutionalDelayModule,
    FamilialShortStatureModule,
    HealthyGrowthModule,
)
from synthetic.native.healthy import HealthyKernel
from synthetic.native.trajectories import DisorderTrajectoryKernel
from synthetic.randomness import NamedRandomStreams
from tests.synthetic.fakes import LinearTestReference


PATIENT = PatientState("syn-patient-a", "F", "F")
AGES = (730, 1095, 1460, 4000, 5000)


def test_healthy_module_matches_existing_healthy_kernel() -> None:
    reference = LinearTestReference()
    baseline = HealthyKernel(reference).generate(
        PATIENT, AGES, NamedRandomStreams(20260830, 0)
    )
    result = DisorderTrajectoryKernel(
        HealthyKernel(reference), HealthyGrowthModule()
    ).generate(PATIENT, AGES, NamedRandomStreams(20260830, 0))

    assert result.disorder.kind is DisorderKind.HEALTHY
    assert result.points == baseline
    assert result.events == ()


def test_familial_short_stature_is_constant_height_shift_and_keeps_weight_identity() -> None:
    reference = LinearTestReference()
    baseline = HealthyKernel(reference).generate(
        PATIENT, AGES, NamedRandomStreams(20260830, 0)
    )
    result = DisorderTrajectoryKernel(
        HealthyKernel(reference), FamilialShortStatureModule()
    ).generate(PATIENT, AGES, NamedRandomStreams(20260830, 0))

    shifts = [point.height_z - base.height_z for point, base in zip(result.points, baseline)]
    assert shifts == pytest.approx([shifts[0]] * len(shifts))
    for point in result.points:
        assert point.weight_kg == pytest.approx(point.bmi * (point.height_cm / 100) ** 2)


def test_constitutional_delay_has_no_effect_before_puberty_and_returns_after_recovery() -> None:
    reference = LinearTestReference()
    result = DisorderTrajectoryKernel(
        HealthyKernel(reference), ConstitutionalDelayModule()
    ).generate(PATIENT, AGES, NamedRandomStreams(20260830, 0))
    puberty_age = ConstitutionalDelayModule().config.expected_puberty_age_days

    assert result.points[0].height_z == pytest.approx(
        HealthyKernel(reference).generate(PATIENT, (730,), NamedRandomStreams(20260830, 0))[0].height_z
    )
    assert result.disorder.kind is DisorderKind.CONSTITUTIONAL_DELAY
    assert [event.event_type for event in result.events][0] == "latent_onset"
    assert puberty_age >= 3650
```

- [ ] **Step 2: Run trajectory tests to verify they fail**

Run: `uv run pytest -q tests/synthetic/test_disorder_trajectories.py`

Expected: collection fails because `native/trajectories.py` is not present.

- [ ] **Step 3: Implement the minimal disorder-aware kernel**

In `src/synthetic/native/trajectories.py`:

1. Validate that the wrapped `HealthyKernel` and module are present. Preserve the baseline kernel’s age ordering, configured bounds, and optional reference-domain checks by delegating baseline generation first.
2. Sample module state after baseline generation using the module’s scoped stream. For every baseline point, compute adjusted height/BMI z-scores from module deltas, require finite deltas, call the wrapped reference again for `height_cm` and `bmi`, require finite positive values, and derive weight exactly from those two dimensions.
3. Preserve patient ID and age, and return a new `LatentTrajectory` with adjusted points, module state, and module events. Do not copy hidden state into any CSV/resource mapper.
4. Verify module event patient IDs match the requested patient and event ages are nonnegative and nondecreasing; reject an event after an impossible treatment/response schedule with `ValueError`.
5. Keep the baseline `growth` stream untouched by requiring modules to use their own named streams; identical healthy module output must equal `HealthyKernel.generate` exactly.

- [ ] **Step 4: Run focused tests, full suite, and checks**

Run: `uv run pytest -q tests/synthetic/test_disorder_trajectories.py && uv run pytest -q && uv run ruff check src tests && python3 schema/build.py --check && git diff --check`

Expected: all tests pass, Ruff is clean, the eight schema resources validate, and Git reports no whitespace errors.

- [ ] **Step 5: Commit the trajectory kernel**

```bash
git add src/synthetic/native/trajectories.py tests/synthetic/test_disorder_trajectories.py
git commit -m "feat: add disorder-aware latent trajectories"
```

---

### Task 4: Document the latent-module boundary

**Files:**
- Modify: `docs/synthetic-generator.md`

**Interfaces:**
- Consumes: `DisorderTrajectoryKernel`, the four module names, and `LatentTrajectory` from Tasks 1–3.
- Produces: a concise development-only usage section that explains hidden truth/event traces, directionally coherent but uncalibrated scenarios, and the fact that visible CSV generation remains unchanged.

- [ ] **Step 1: Add the development-module section**

Document a Python example that constructs a `DisorderTrajectoryKernel` from the existing injected test reference and a module, then states that `LatentTrajectory.disorder` and `.events` are evaluator-only and are not exported. List the four modules and their directional signatures without calling their defaults clinically representative. State that prevalence, demographic calibration, disorder-critical labs/medications/referrals, held-out validation, and privacy auditing remain later gates.

- [ ] **Step 2: Verify the repository**

Run: `uv run pytest -q && uv run ruff check src tests && python3 schema/build.py --check && git diff --check`

Expected: all tests pass, Ruff is clean, eight schema resources validate, and Git reports no whitespace errors.

- [ ] **Step 3: Commit the documentation**

```bash
git add docs/synthetic-generator.md
git commit -m "docs: describe latent growth disorder modules"
```

---

## Completion gate

Before merging this plan, verify that:

- All four module types produce deterministic states and ordered event traces with latent truth separate from observable descendants.
- Familial short stature preserves a constant height-z offset, constitutional delay has a bounded temporary effect, and growth-hormone deficiency has progressive impairment with optional treatment response.
- Healthy-module output is byte-for-byte/point-for-point identical to the existing healthy kernel for the same inputs.
- Anthropometric identities, reference guards, age ordering, and named random-stream isolation pass independent tests.
- No latent truth, event trace, clinical data, prevalence claim, or privacy claim enters the visible eight-resource fixture package.
- Full pytest, Ruff, schema, and whitespace checks pass, and the documentation labels defaults as uncalibrated development scenarios.
