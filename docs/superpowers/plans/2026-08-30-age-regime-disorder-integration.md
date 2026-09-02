# Age-Regime Disorder Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compose the existing growth-disorder modules with age-regime physiology so healthy, familial-short-stature, constitutional-delay, and growth-hormone-deficiency trajectories remain coherent from infancy through adolescence without changing the visible eight-resource exporter.

**Architecture:** Add an evaluator-only `AgeRegimeDisorderKernel` that samples age-regime and disorder state from isolated named streams, replays the age-regime kernel with any explicit constitutional-delay schedule adjustment, and applies module effects through a regime-aware two-dimension bridge. Return a frozen `AgeRegimeDisorderTrajectory` containing physiology, hidden disorder state, and hidden events; keep existing healthy/disorder kernels, smoke generation, CSV mapping, descriptors, and manifests unchanged.

**Tech Stack:** Python 3.12+, standard-library dataclasses/enum/math, NumPy named streams, existing `GrowthReference` and `GrowthDisorderModule` protocols, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-08-30-age-regime-disorder-integration-design.md`

## Global Constraints

- `datapackage.json` remains the sole visible schema authority; this plan does not change CSV paths, headers, rows, manifests, ordinary loader APIs, or the eight-resource exporter.
- Existing `LatentPoint`, `LatentTrajectory`, `HealthyKernel`, `DisorderTrajectoryKernel`, `generate_smoke`, and their tests remain backward compatible.
- Every new state, event trace, age-regime point, z-score, velocity, and composition result is evaluator-only and never enters visible CSVs, descriptors, manifests, or resource mappers.
- Before transition, the effect bridge adjusts length plus weight; at and after transition it adjusts height plus BMI; the remaining quantity is derived deterministically.
- Length-to-height conversion and transition continuity remain active after effects; nonfinite/nonphysical reference, derived, effect, and velocity values fail closed.
- Identical reference identity, configuration, patient, module version/configuration, named streams, and seed reproduce identical state, points, disorder state, and events. The composition never requests `growth`.
- The age-regime replay seam preserves ordinary `AgeRegimeTrajectoryKernel.generate(...)` behavior and existing call sites.
- Constitutional delay shifts age-regime puberty onset by `puberty_delay_days` and does not apply its overlapping negative height delta a second time; an out-of-domain shifted schedule is an error.
- Defaults remain uncalibrated development scenarios. The evaluator-only follow-on modules include pediatric hypothyroidism and celiac disease; they do not widen this kernel into visible ancillary resources. No real rows, diagnosis counts, clinical tables, prevalence estimates, demographic calibration, privacy evidence, or Synthea implementation enters this plan.

---

### Task 1: Add explicit age-regime state sampling and replay

**Files:**
- Modify: `src/synthetic/native/age_regimes.py`
- Modify: `tests/synthetic/test_age_regime_kernel.py`

**Interfaces:**
- Produces `AgeRegimeTrajectoryKernel.sample_state(streams: NamedRandomStreams) -> AgeRegimeState`.
- Extends `AgeRegimeTrajectoryKernel.generate(patient, ages_days, streams, *, state: AgeRegimeState | None = None) -> AgeRegimeTrajectory` without changing existing calls.

- [x] **Step 1: Write failing replay tests**

Add to `tests/synthetic/test_age_regime_kernel.py`:

```python
import dataclasses


def test_sampled_state_can_be_replayed_without_resampling() -> None:
    kernel = AgeRegimeTrajectoryKernel(RegimeLinearTestReference())
    streams = NamedRandomStreams(20260830, 0)
    state = kernel.sample_state(streams)

    replayed = kernel.generate(PATIENT, (0, 730, 761, 4380), streams, state=state)
    ordinary = kernel.generate(PATIENT, (0, 730, 761, 4380), streams)

    assert replayed.state == ordinary.state
    assert replayed.points == ordinary.points


def test_state_replay_rejects_wrong_version_or_puberty_domain() -> None:
    kernel = AgeRegimeTrajectoryKernel(RegimeLinearTestReference())
    state = kernel.sample_state(NamedRandomStreams(5, 0))

    with pytest.raises(ValueError, match="module_version"):
        kernel.generate(
            PATIENT, (730,), NamedRandomStreams(5, 0),
            state=dataclasses.replace(state, module_version="other-v1"),
        )
    with pytest.raises(ValueError, match="puberty"):
        kernel.generate(
            PATIENT, (730,), NamedRandomStreams(5, 0),
            state=dataclasses.replace(state, puberty_onset_age_days=0),
        )
```

Keep the existing all-regime, determinism, and stream-recording tests unchanged.

- [x] **Step 2: Run replay tests to verify they fail**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_age_regime_kernel.py -k replay`

Expected: collection or test failure because `sample_state` and the `state` keyword are not implemented.

- [x] **Step 3: Implement the replay seam**

In `src/synthetic/native/age_regimes.py`:

1. Refactor `_sample_state` into public `sample_state(streams)` returning only `AgeRegimeState`; preserve the five stream names and distributions.
2. Add `_validate_state(state)` requiring an `AgeRegimeState`, the current `module_version`, onset within configured puberty age bounds, tempo within configured tempo bounds, and onset plus tempo no later than `maximum_age_days`.
3. Add keyword-only `state: AgeRegimeState | None = None` to `generate`. If absent, sample state; if supplied, validate it and do not resample birth/childhood/puberty channels. In both cases obtain residual/head generators by their existing names and run the existing point construction, physical guards, velocities, and continuity validation.
4. Preserve ordinary `generate(patient, ages_days, streams)` behavior; the replay seam is evaluator-only and no visible path may import it.

- [x] **Step 4: Run focused and regression tests**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_age_regime_kernel.py && UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic`

Expected: replay and all existing synthetic tests pass.

- [x] **Step 5: Run lint and commit**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/native/age_regimes.py tests/synthetic/test_age_regime_kernel.py`

```bash
git add src/synthetic/native/age_regimes.py tests/synthetic/test_age_regime_kernel.py
git commit -m "feat: add age-regime state replay"
```

---

### Task 2: Add the evaluator composition container and shared module validators

**Files:**
- Modify: `src/synthetic/models.py`
- Modify: `src/synthetic/native/trajectories.py`
- Create: `tests/synthetic/test_age_regime_disorder_models.py`
- Modify: `tests/synthetic/test_disorder_trajectories.py`

**Interfaces:**
- Produces frozen `AgeRegimeDisorderTrajectory(physiology: AgeRegimeTrajectory, disorder: LatentDisorderState, events: tuple[ClinicalEvent, ...])`.
- Produces `validate_growth_disorder_module(module: object) -> None` and `validate_disorder_events(patient: PatientState, state: LatentDisorderState, events: tuple[ClinicalEvent, ...]) -> None` in `synthetic.native.trajectories`.

- [x] **Step 1: Write failing container and validator tests**

Create `tests/synthetic/test_age_regime_disorder_models.py`:

```python
import pytest

from synthetic.models import (
    AgeRegimeDisorderTrajectory, AgeRegimePoint, AgeRegimeState,
    AgeRegimeTrajectory, ClinicalEvent, DisorderKind, GrowthRegime,
    LatentDisorderState, PatientState,
)
from synthetic.native.trajectories import validate_disorder_events


def _physiology() -> AgeRegimeTrajectory:
    state = AgeRegimeState(
        "age-regimes-v1", 0.0, 0.0, 0.0, 0.0, 0.0, 4380, 900, 0.0, 0.0
    )
    point = AgeRegimePoint(
        "syn-patient-a", 365, GrowthRegime.INFANCY, 75.0, None, 9.0, None
    )
    return AgeRegimeTrajectory((point,), state)


def test_composition_container_accepts_healthy_empty_events() -> None:
    result = AgeRegimeDisorderTrajectory(
        _physiology(), LatentDisorderState(DisorderKind.HEALTHY, None, 0.0), ()
    )
    assert result.physiology.points[0].patient_id == "syn-patient-a"
    assert result.disorder.kind is DisorderKind.HEALTHY
    assert result.events == ()


def test_container_rejects_patient_mismatch_and_non_tuple_events() -> None:
    with pytest.raises(ValueError, match="patient"):
        AgeRegimeDisorderTrajectory(
            _physiology(), LatentDisorderState(DisorderKind.HEALTHY, None, 0.0),
            (ClinicalEvent("other", 0, "latent_onset", None, True),),
        )
    with pytest.raises(ValueError, match="tuple"):
        AgeRegimeDisorderTrajectory(
            _physiology(), LatentDisorderState(DisorderKind.HEALTHY, None, 0.0), []
        )


def test_shared_event_validator_keeps_terminal_treatment_rules() -> None:
    state = LatentDisorderState(
        DisorderKind.GROWTH_HORMONE_DEFICIENCY, 100, 0.8,
        treatment_start_age_days=300, treatment_response=0.6,
    )
    events = (
        ClinicalEvent("syn-patient-a", 300, "treatment_start", None, False),
        ClinicalEvent("syn-patient-a", 400, "treatment_response", None, False),
    )
    validate_disorder_events(PatientState("syn-patient-a", "F", "F"), state, events)
```

Also test that an object missing `module_version`, `sample_state`,
`height_z_delta`, `bmi_z_delta`, or `events` is rejected by
`validate_growth_disorder_module`. Update existing disorder tests only to prove
shared validation preserves current behavior and messages.

- [x] **Step 2: Run new tests to verify they fail**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_age_regime_disorder_models.py`

Expected: collection fails because the new model and validators are undefined.

- [x] **Step 3: Implement the container and validator reuse**

In `src/synthetic/models.py`, add frozen `AgeRegimeDisorderTrajectory` after
`AgeRegimeTrajectory`. Validate both model types, `events` as a tuple of
`ClinicalEvent`, and every event patient ID against the physiology patient ID;
empty events are valid for healthy/zero-effect modules. Do not add conversion to
`LatentTrajectory`.

In `src/synthetic/native/trajectories.py`:

1. Move the constructor checks into `validate_growth_disorder_module` without changing exception types/messages.
2. Rename `_validate_events` to public `validate_disorder_events`, preserving terminal-treatment, ordering, patient, and state checks.
3. Make `DisorderTrajectoryKernel.__init__` and `.generate` call the shared functions; do not alter healthy baseline or `LatentPoint` output.

- [x] **Step 4: Run focused and regression tests**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_age_regime_disorder_models.py tests/synthetic/test_disorder_trajectories.py && UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic`

Expected: focused tests and the complete synthetic suite pass.

- [x] **Step 5: Run lint and commit**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/models.py src/synthetic/native/trajectories.py tests/synthetic/test_age_regime_disorder_models.py tests/synthetic/test_disorder_trajectories.py`

```bash
git add src/synthetic/models.py src/synthetic/native/trajectories.py tests/synthetic/test_age_regime_disorder_models.py tests/synthetic/test_disorder_trajectories.py
git commit -m "feat: add age-regime disorder composition contract"
```

---

### Task 3: Implement the deterministic age-regime disorder kernel

**Files:**
- Create: `src/synthetic/native/age_regime_disorder.py`
- Create: `tests/synthetic/test_age_regime_disorder.py`

**Interfaces:**
- Produces `AgeRegimeDisorderKernel(physiology: AgeRegimeTrajectoryKernel, module: GrowthDisorderModule)`.
- Produces `AgeRegimeDisorderKernel.generate(patient: PatientState, ages_days: tuple[int, ...], streams: NamedRandomStreams) -> AgeRegimeDisorderTrajectory`.

- [x] **Step 1: Write failing integration tests**

Create `tests/synthetic/test_age_regime_disorder.py` using
`RegimeLinearTestReference` from `tests.synthetic.fakes`. Cover healthy
equivalence, familial effects in both representations, constitutional-delay
onset shifting without double application, growth-hormone-deficiency treatment
events/effects, stream isolation, and nonfinite module deltas:

```python
def test_healthy_composition_matches_age_regime_physiology() -> None:
    physiology = AgeRegimeTrajectoryKernel(RegimeLinearTestReference())
    baseline = physiology.generate(PATIENT, AGES, NamedRandomStreams(7, 0))
    result = AgeRegimeDisorderKernel(physiology, HealthyGrowthModule()).generate(
        PATIENT, AGES, NamedRandomStreams(7, 0)
    )
    assert result.physiology == baseline
    assert result.disorder.kind is DisorderKind.HEALTHY
    assert result.events == ()


def test_familial_effect_preserves_identities_across_regimes() -> None:
    physiology = AgeRegimeTrajectoryKernel(RegimeLinearTestReference())
    healthy = AgeRegimeDisorderKernel(physiology, HealthyGrowthModule()).generate(
        PATIENT, AGES, NamedRandomStreams(8, 0)
    )
    familial = AgeRegimeDisorderKernel(
        physiology, FamilialShortStatureModule(FamilialShortStatureConfig(
            severity_min=0.8, severity_max=0.8
        ))
    ).generate(PATIENT, AGES, NamedRandomStreams(8, 0))

    for base, adjusted in zip(healthy.physiology.points, familial.physiology.points):
        if base.length_z is not None:
            assert adjusted.length_z < base.length_z
        if base.height_z is not None:
            assert adjusted.height_z < base.height_z
        if adjusted.bmi is not None and adjusted.height_cm is not None:
            assert adjusted.weight_kg == pytest.approx(
                adjusted.bmi * (adjusted.height_cm / 100.0) ** 2
            )
```

Use these fixed configurations for deterministic timing assertions:

```python
def test_constitutional_delay_shifts_puberty_once() -> None:
    class FixedOnsetKernel(AgeRegimeTrajectoryKernel):
        def sample_state(self, streams: NamedRandomStreams) -> AgeRegimeState:
            return dataclasses.replace(
                super().sample_state(streams), puberty_onset_age_days=4380
            )

    physiology = FixedOnsetKernel(
        RegimeLinearTestReference(), AgeRegimeConfig(
            residual_sd=0.0,
            puberty_min_age_days=4380,
            puberty_max_age_days=4740,
        )
    )
    module = ConstitutionalDelayModule(
        ConstitutionalDelayConfig(
            expected_puberty_age_days=4380,
            puberty_delay_min_days=360,
            puberty_delay_max_days=360,
        )
    )
    result = AgeRegimeDisorderKernel(physiology, module).generate(
        PATIENT, (4380, 4740, 4741, 5100), NamedRandomStreams(9, 0)
    )

    assert result.disorder.puberty_delay_days == 360
    assert result.physiology.state.puberty_onset_age_days == 4740
    assert result.physiology.points[0].height_z == pytest.approx(
        result.physiology.points[1].height_z
    )
    assert result.events[0].event_type == "latent_onset"


def test_growth_hormone_deficiency_keeps_treatment_events_and_changes_growth() -> None:
    physiology = AgeRegimeTrajectoryKernel(
        RegimeLinearTestReference(), AgeRegimeConfig(residual_sd=0.0)
    )
    module = GrowthHormoneDeficiencyModule(
        GrowthHormoneDeficiencyConfig(
            onset_min_age_days=3000,
            onset_max_age_days=3000,
            treatment_probability=1.0,
            treatment_delay_days=0,
            response_days=365,
            treatment_response_min=0.6,
            treatment_response_max=0.6,
        )
    )
    result = AgeRegimeDisorderKernel(physiology, module).generate(
        PATIENT, (2999, 3000, 3365, 4000, 5000), NamedRandomStreams(10, 0)
    )

    assert result.physiology.points[2].height_z < result.physiology.points[1].height_z
    assert [event.event_type for event in result.events][-2:] == [
        "treatment_start", "treatment_response"
    ]
```

Add negative tests for wrong module kind/state, malformed event patient IDs,
shifted schedules outside the configured domain, extreme reference values,
sparse transition continuity, and missing required module methods.

- [x] **Step 2: Run integration tests to verify they fail**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_age_regime_disorder.py`

Expected: collection fails because `AgeRegimeDisorderKernel` is undefined.

- [x] **Step 3: Implement the minimal composition kernel**

Create `src/synthetic/native/age_regime_disorder.py`:

1. Validate the physiology kernel type and call `validate_growth_disorder_module(module)` in the constructor.
2. In `generate`, sample age-regime state then module state from the same `NamedRandomStreams`; require a `LatentDisorderState` whose kind matches `module.kind`.
3. For constitutional delay, add `disorder_state.puberty_delay_days` to the sampled age-regime onset with `dataclasses.replace`; skip that module's overlapping `height_z_delta` so the shifted smooth-step represents the delay once. Let the replay seam reject schedules outside configured bounds.
4. Generate baseline physiology through `physiology.generate(..., state=adjusted_state)`; never call `HealthyKernel`, `DisorderTrajectoryKernel`, or visible package code.
5. For non-constitutional modules, add finite `height_z_delta` and `bmi_z_delta` to `length_z`/`weight_z` before transition, re-request length/weight, and derive transition height/BMI. After transition add them to `height_z`/`bmi_z`, re-request height/BMI, and derive weight. Preserve head circumference.
6. Recompute comparable-size and weight velocities, construct validated `AgeRegimePoint` objects, and recheck adjusted transition continuity with the common-boundary rule.
7. Validate `tuple(module.events(patient, disorder_state))` using `validate_disorder_events` and return `AgeRegimeDisorderTrajectory`.
8. Catch arithmetic overflow and reject every nonfinite/nonpositive reference, derived, delta, or velocity value with controlled `ValueError`.

Keep helpers focused on z-effect re-evaluation, velocity recomputation, and
adjusted continuity. Do not add a manifest field or duplicate CSV mapping.

- [x] **Step 4: Run focused and complete synthetic tests**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_age_regime_disorder.py tests/synthetic/test_age_regime_disorder_models.py && UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic`

Expected: focused integration tests and the complete synthetic suite pass.

- [x] **Step 5: Run lint and commit**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/native/age_regime_disorder.py tests/synthetic/test_age_regime_disorder.py`

```bash
git add src/synthetic/native/age_regime_disorder.py tests/synthetic/test_age_regime_disorder.py
git commit -m "feat: integrate age-regime disorder trajectories"
```

---

### Task 4: Document the evaluator-only composition boundary

**Files:**
- Modify: `docs/synthetic-generator.md`

**Interfaces:**
- Consumes `AgeRegimeDisorderKernel`, `AgeRegimeDisorderTrajectory`, and the existing injected reference/module examples.
- Produces documentation distinguishing evaluator-only composition from visible smoke output and calibrated clinical/EHR generation.

- [x] **Step 1: Update the usage guide**

Add a section after the age-regime example that:

1. Constructs `AgeRegimeDisorderKernel(AgeRegimeTrajectoryKernel(reference), FamilialShortStatureModule())` with ages spanning infancy, transition, puberty, and adolescence.
2. States that `result.physiology`, `result.disorder`, and `result.events` are hidden evaluator objects, not CSV, descriptor, manifest, or ordinary-loader fields.
3. Explains the pre-transition length/weight bridge, post-transition height/BMI bridge, derived identities, adjusted transition continuity, and constitutional-delay schedule rule.
4. Labels all native modules as uncalibrated scenarios and states module selection is not prevalence estimation.
5. Defers diagnosis/lab/medication/referral descendants, prevalence/demographic calibration, held-out validation, privacy auditing, counterfactual worlds, clinical reference approval, and Synthea conformance.
6. Preserves the healthy age-730+ three-visit smoke/export boundary and non-matchability limitation.

Do not present the pre-transition BMI-to-weight bridge as a validated infant
clinical score or claim generated profiles cannot be matched to real data.

- [x] **Step 2: Verify documentation and repository checks**

Run:

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests
python3 schema/build.py --check
git diff --check
```

Expected: all tests pass, Ruff is clean, eight schema resources validate, and Git reports no whitespace errors.

- [x] **Step 3: Commit the documentation**

```bash
git add docs/synthetic-generator.md
git commit -m "docs: describe age-regime disorder composition"
```

---

## Completion gate

Before merging this plan, verify that:

- Ordinary age-regime generation remains deterministic and behaviorally unchanged when no replay state is supplied.
- `AgeRegimeDisorderTrajectory` validates hidden physiology, disorder state, event types, and patient identities without replacing `LatentTrajectory`.
- All reviewed native modules compose across infancy, transition, childhood, puberty, and adolescence; familial effects adjust both representations, constitutional delay shifts puberty exactly once, and treatment events remain causally ordered.
- Pre-transition outputs contain length plus weight, transition derives height/BMI explicitly, post-transition outputs contain height plus BMI and derive weight, and adjusted identities/velocities are finite.
- Sparse transition pairs, shifted schedules, extreme references, nonfinite effects, malformed module contracts, wrong state kinds, and malformed events fail closed.
- The composition requests regime and disorder streams but never `growth`; identical seeds and inputs reproduce physiology, disorder state, and events.
- No age-regime/disorder state or event trace enters `datapackage.json`, visible CSVs, manifests, smoke generation, or resource mapping.
- Full pytest, Ruff, schema, and whitespace checks pass from the feature branch, and documentation labels the layer uncalibrated/evaluator-only with calibration, privacy, counterfactual, clinical, and Synthea work deferred.

## Completion evidence

- The replay seam and evaluator composition were already integrated in `d0ab698`; the final review hardening is in `566f00b`, with compatibility fixture updates in `0c18029` and adjusted-reference error normalization in `617a1de`.
- Fresh adversarial and current-main reviews found and closed direct event/physiology validation gaps, zero-effect hook-parity drift, sparse adjusted-transition continuity bypasses, active empty-event traces, and adjusted-reference `TypeError` leakage. The post-fix review approved `617a1de`.
- Integrated verification passed: `2653 passed, 4 skipped`; Ruff passed; `python schema/build.py --check` validated 8 resources; `uv lock --check` passed; and `git diff --check` was clean.
- The composition remains evaluator-only: hidden age-regime/disorder state, event traces, z-scores, velocities, and module selection do not enter the visible eight-resource package, descriptors, manifests, smoke generation, or ordinary loaders. Defaults remain uncalibrated, and prevalence, clinical, privacy, counterfactual-world, and Synthea gates remain deferred.
