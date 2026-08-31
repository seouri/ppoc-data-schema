# Native Calibrated Cohort Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic in-memory native cohort orchestrator that samples released aggregate demographics, composes healthy and reviewed growth-disorder trajectories, and optionally returns validated observed-resource bundles without accepting governed patient data.

**Architecture:** Keep aggregate calibration consumption in a strict `CalibrationSamplingProfile` model, then compose the existing age-regime/disorder, observation-frame, and observed-resource contracts in a new `synthetic.cohort` module. The API is intentionally in-memory and evaluator/development-only; it never reads paths, writes files, calls package export, or enables the fail-closed production CLI.

**Tech Stack:** Python 3.12+, standard-library dataclasses/math/hashlib/collections, existing NumPy named streams, native trajectory/observation/resource contracts, existing calibration artifact and target registry, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-08-31-native-cohort-profile-design.md`

## Global Constraints

- Consume only an already-loaded `CalibrationArtifact`; never accept a real-data path, partition key, patient row, sequence, held-out report, privacy report, or hidden evaluator truth as a cohort input.
- Require complete released demographic target cells for the selected profile. A suppressed or missing target fails closed; it is never silently dropped, normalized to zero, or replaced by a hidden fallback.
- Keep latent module selection independent from recorded diagnosis targets; `growth_dx_flag` and `healthy_flag` remain aggregate evidence and are not final-label allocators.
- Reuse the existing age-regime/disorder kernel, observation-frame generator, resource projection, and resource validator; do not duplicate trajectory or visibility logic.
- Keep latent trajectory state, disorder state, source events, private measurement truth, truth hashes, and random-stream identities out of ordinary mappings, aggregate summaries, repr output, exceptions, and visible package files.
- The descriptor is an already-loaded mapping used only for shape extraction. The cohort module must not read descriptor paths/CSVs, import governed calibration-input/held-out/privacy modules, call package writers, or use output lifecycle code.
- Generation errors from an injected reference, module, observation, projection, or resource validator are wrapped in `CohortGenerationUnavailable("native cohort generation failed")`; configuration/calibration-contract errors may identify only fields or aggregate target names.
- No production reference, authoritative augmentation oracle, clinical terminology, ancillary-resource path, held-out gate, privacy evidence, clinical review, task-utility evaluation, or Synthea adapter is added or enabled.
- Every task ends with focused tests, Ruff for touched files, `git diff --check`, and a scoped commit; no real data, keys, generated artifacts, or caches may be staged.

---

### Task 1: Add strict cohort models and configuration

**Files:**
- Create: `src/synthetic/cohort.py`
- Create: `tests/synthetic/test_cohort_models.py`

**Interfaces:**
- Consumes: `DisorderKind`, `ObservationPolicy`, `AgeRegimeConfig`, `CalibrationArtifact`, and existing native resource type names.
- Produces: `CohortModuleWeight`, `CohortConfig`, `CohortGenerationUnavailable`, `CohortMember`, `NativeCohort`, and validation helpers for later tasks. Generation functions may initially raise a clear assembly error.

- [x] **Step 1: Write failing model tests**

Test immutable module weights and configs. Cover non-token profiles, nonpositive/boolean/oversized patient counts, boolean seeds, empty/duplicate/unsorted ages, non-`ObservationPolicy` values, malformed module-weight tuples, probabilities outside `[0,1]`, zero total probability, absence of a positive healthy module, absence of a positive nonhealthy module, duplicate module kinds, incomplete or duplicate `F/M/U` reference-sex mappings, and invalid age-regime configs. Assert exact accepted defaults only where the spec defines them and verify dataclasses are frozen.

Test `CohortMember` and `NativeCohort` representations/mappings with fictional native objects once minimal constructors are available. Assert `repr` does not contain latent disorder, source event, truth, hash, or stream material; `to_mapping()` contains only the visible frame/bundle data and aggregate counts.

- [x] **Step 2: Run model tests to verify the API is absent/incomplete**

Run:

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_cohort_models.py
```

Expected: collection or assembly failures because `synthetic.cohort` does not yet expose the required models. Correct only test-fixture syntax before implementation.

- [x] **Step 3: Implement immutable validation models**

Implement `CohortModuleWeight(kind, probability)` with a real `DisorderKind`, finite probability in `[0,1]`, and no boolean coercion. Implement `CohortConfig` with the exact fields from the spec. Use profile token validation consistent with the existing aggregate-safe token contract, patient count bounds `1..100_000`, integer seed, strict increasing nonnegative ages, explicit `ObservationPolicy`, positive healthy and nonhealthy weights, complete one-to-one `F/M/U` mapping, and `AgeRegimeConfig` type checks. Preserve caller order only for validated module-weight storage; later sampling normalizes a copied tuple deterministically.

Add `CohortGenerationUnavailable` as a `ValueError` subclass. Add private visible-mapping helpers and frozen `CohortMember`/`NativeCohort` containers. Their `to_mapping()` methods must never traverse or serialize `trajectory` or `frame.truth`; `repr` must be fixed evaluator-safe text. Keep generation methods as explicit placeholders until later tasks rather than exposing a partially working CLI.

- [x] **Step 4: Run focused tests and lint**

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_cohort_models.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/cohort.py tests/synthetic/test_cohort_models.py
git diff --check
```

- [x] **Step 5: Commit**

```sh
git add src/synthetic/cohort.py tests/synthetic/test_cohort_models.py
git commit -m "build: add native cohort models"
```

### Task 2: Extract a strict aggregate sampling profile

**Files:**
- Modify: `src/synthetic/cohort.py`
- Create: `tests/synthetic/test_cohort_calibration.py`
- Create: `tests/synthetic/cohort_fixtures.py`

**Interfaces:**
- Consumes: `CalibrationArtifact`, `CalibrationTarget`, `EXPECTED_SCHEMA_FINGERPRINT`, `TARGET_REGISTRY_VERSION`, and the fixed category registries in `synthetic.calibration_targets`.
- Produces: `CalibrationSamplingProfile.from_artifact(artifact)`, profile `to_mapping()`, and private weighted-categorical/projection helpers.

- [x] **Step 1: Write failing profile extraction tests**

Build a hand-authored aggregate-only artifact fixture with every required released target and realistic rounded proportions. Test extraction of all sex, ethnicity, and primary-race categories, `race_multiselect`, `healthy_flag`, and `growth_dx_flag`; artifact/schema/registry mismatch; wrong stratum; missing, duplicate, suppressed, non-proportion, null-denominator, nonfinite, and out-of-range targets; and rounded weights outside the one-percent sum envelope. Assert blank ethnicity/race targets remain present in the aggregate profile, profile mappings contain no support/denominator/path/key/identifier/truth fields, and recorded outcome rates do not influence module weights.

- [x] **Step 2: Run profile tests to verify failure**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_cohort_calibration.py`

Expected: the profile API is missing or incomplete. Fix only fixture construction errors before implementing.

- [x] **Step 3: Implement strict artifact-to-profile conversion**

Require an actual `CalibrationArtifact`, `source_partition == "calibration"`, the exact repository schema fingerprint, and registered target keys for every supplied target. Locate exactly one `outcome_layer=observed` stratum. Require released denominator-backed proportion targets for all mappings in `SEX_CATEGORY_SLUGS`, `ETHNICITY_CATEGORY_SLUGS`, `RACE_CATEGORY_SLUGS`, plus `race_multiselect`, `healthy_flag`, and `growth_dx_flag`. Reject suppressed/missing/duplicate or semantically mismatched cells before any sampling.

Store aggregate weights in canonical registry order. Validate finite nonnegative values and a total within `0.99..1.01`, then normalize only the in-memory categorical weights. Preserve the recorded target rates separately as evidence fields; never turn them into module probabilities. Map aggregate blank ethnicity/race values to the visible `Unknown` category only in a private projection helper, and use a fixed rule for race slot two when `race_multiselect` is sampled. Keep `to_mapping()` aggregate-only and omit supports, denominators, source metadata beyond the safe artifact identity, and any patient-attributable material.

- [x] **Step 4: Run profile tests, lint, and commit**

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_cohort_calibration.py tests/synthetic/test_calibration_artifact_model.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/cohort.py tests/synthetic/test_cohort_calibration.py tests/synthetic/cohort_fixtures.py
git diff --check
```

Commit:

```sh
git add src/synthetic/cohort.py tests/synthetic/test_cohort_calibration.py tests/synthetic/cohort_fixtures.py
git commit -m "feat: consume aggregate cohort calibration"
```

### Task 3: Generate deterministic demographic/module trajectories

**Files:**
- Modify: `src/synthetic/cohort.py`
- Create: `tests/synthetic/test_cohort_generation.py`

**Interfaces:**
- Consumes: `CohortConfig`, `CalibrationSamplingProfile`, `GrowthReference`, `GrowthDisorderModule`, `AgeRegimeTrajectoryKernel`, `AgeRegimeDisorderKernel`, `PatientState`, `SyntheticDemographics`, `NamedRandomStreams`, and `synthetic_id`.
- Produces: `generate_native_cohort(config, reference, calibration, *, modules, descriptor=None) -> NativeCohort` with trajectory/frame assembly begun in this task and resource projection completed in Task 4.

- [x] **Step 1: Write failing deterministic generation tests**

Use only `RegimeLinearTestReference`, existing reviewed module implementations, an explicit observation policy, and the aggregate fixture. Assert repeated calls with equal inputs produce equal visible mappings and equal latent/truth hashes; reordering the module mapping does not change output; IDs are deterministic and unique; sampled demographics stay in the closed fictional vocabularies; at least one healthy and one nonhealthy member appear for a configured mixed prior; and a different seed changes a demographic/module draw without changing identifier format.

Assert the selected module receives the same `NamedRandomStreams` family used by `AgeRegimeDisorderKernel`, ages remain ordered, and each trajectory has the requested points. Add a regression proving `growth_dx_flag`/`healthy_flag` artifact values do not override a deliberately different explicit module prior.

- [x] **Step 2: Run generation tests to verify the orchestration is absent**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_cohort_generation.py`

Expected: failures because `generate_native_cohort` is not assembled. Correct only test fixture mistakes before implementation.

- [x] **Step 3: Implement deterministic demographic and module sampling**

Validate the reference exposes a callable `value` method and the modules mapping contains exactly the positive-prior kinds with matching `kind`/`module_version` behavior through the existing trajectory validator. Copy and canonicalize mappings before any draws. For each index, create `synthetic_id(config.seed, "patient", index)`; use `cohort.demographics` to sample recorded sex, ethnicity, race slot one, and the race-multiselect draw; map sampled recorded sex through the explicit reference-sex mapping; use `cohort.module` to sample one kind from normalized module weights; and construct `PatientState` plus `SyntheticDemographics`.

Instantiate `AgeRegimeTrajectoryKernel(reference, config.age_regime_config)` and `AgeRegimeDisorderKernel` for the selected module. Generate the trajectory with the same `NamedRandomStreams(config.seed, index)` object, then call `generate_observation_frame` with the configured observation policy. Require `validate_observation_frame(frame).status is PASS`; wrap reference/module/observation errors in the fixed redacted `CohortGenerationUnavailable` message. Keep the latent trajectory and frame truth in the evaluator-only `CohortMember`, never in its mapping.

- [x] **Step 4: Run generation tests, lint, and commit**

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_cohort_generation.py tests/synthetic/test_cohort_models.py tests/synthetic/test_cohort_calibration.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/cohort.py tests/synthetic/test_cohort_generation.py
git diff --check
```

Commit:

```sh
git add src/synthetic/cohort.py tests/synthetic/test_cohort_generation.py
git commit -m "feat: generate native cohort trajectories"
```

### Task 4: Project and validate observed-resource bundles

**Files:**
- Modify: `src/synthetic/cohort.py`
- Create: `tests/synthetic/test_cohort_resources.py`

**Interfaces:**
- Consumes: `generate_native_cohort` trajectory/frame members, an already-loaded exact descriptor mapping, `project_observed_resources`, and `validate_observed_resources`.
- Produces: completed `NativeCohort` members with optional `bundle`, `NativeCohort.to_mapping()`, and stable aggregate visible counts.

- [x] **Step 1: Write failing resource-integration tests**

Pass the checked-in descriptor mapping and assert every member has a `PASS` observed-resource bundle with exact six-resource shape, descriptor field order, sampled demographics, unique patient/visit IDs, and empty ancillary rows under the current contract. Reorder descriptor resource entries and assert the shape contract rejects the mismatch rather than silently changing schema semantics. Test no descriptor (`bundle is None`), malformed descriptor, a policy that produces a non-PASS frame, and a projection error caused by observed infancy length; all failures must be redacted and no filesystem output created.

Assert `CohortMember.to_mapping()` and `NativeCohort.to_mapping()` exclude latent module kinds, severity, source events, truth hashes, stream names, supports/denominators, and calibration private fields while retaining visible rows and aggregate counts. Confirm the returned bundles can be passed to `export_observed_resource_package` by a caller but the cohort function itself never imports or calls the package exporter.

- [x] **Step 2: Run resource tests to verify the bridge is incomplete**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_cohort_resources.py`

Expected: failures because descriptor projection is not wired. Fix only fixture mistakes before implementation.

- [x] **Step 3: Implement optional descriptor projection and aggregate result**

When `descriptor` is supplied, require a mapping and extract `ResourceShape` before sampling. After each passing frame, call `project_observed_resources(frame, descriptor, demographics)` and require `validate_observed_resources(bundle).status is PASS`; any failure is wrapped in `CohortGenerationUnavailable` without raw IDs or values. When absent, leave `bundle=None` and do not inspect paths or perform file I/O. Enforce global uniqueness of patient IDs and visit IDs before returning.

Implement `NativeCohort.to_mapping()` with only the profile, seed, member count, bundle count, visible visit count, and visible event count. Implement member mappings with visible frame/bundle projections only. Keep the calibration object and evaluator truth reachable only through typed in-memory attributes, not mapping or repr traversal.

- [x] **Step 4: Run integration tests, lint, and commit**

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_cohort_resources.py tests/synthetic/test_cohort_generation.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/cohort.py tests/synthetic/test_cohort_resources.py
git diff --check
```

Commit:

```sh
git add src/synthetic/cohort.py tests/synthetic/test_cohort_resources.py
git commit -m "feat: project native cohort resources"
```

### Task 5: Document the boundary and protect visible generation paths

**Files:**
- Modify: `docs/synthetic-generator.md`
- Modify: `README.md`
- Modify: `tests/synthetic/test_cohort_boundaries.py`
- Modify: `tests/synthetic/test_package_export_boundaries.py` only if a shared visible-path assertion must include `cohort.py`

**Interfaces:**
- Consumes: the completed in-memory cohort API and the parent synthetic-fixture claims/deferred-gate language.
- Produces: a user-facing native cohort usage section and AST/inspection assertions that preserve the no-governed-input and no-file-output boundary.

- [x] **Step 1: Write failing boundary/documentation tests**

Assert the guide and README name `generate_native_cohort`, `CalibrationSamplingProfile`, aggregate-only released target requirements, explicit module priors, healthy-plus-disorder coverage, optional descriptor mapping, hidden-truth exclusion, no real-data path, and the unchanged fail-closed CLI. Assert deferred prevalence validation, held-out, privacy/non-matchability, clinical validity, task utility, ancillary resources, authoritative derivation, release, and Synthea claims remain present. AST-scan `synthetic.cohort` and visible generation/native modules for forbidden imports/calls, path readers, output lifecycle calls, governed path/key/report argument names, and package-writer dependencies.

- [x] **Step 2: Run documentation/boundary tests to verify the section is absent**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_cohort_boundaries.py tests/synthetic/test_package_export_boundaries.py`

Expected: the new documentation assertions fail before the section and boundary updates exist.

- [x] **Step 3: Update documentation and boundary scan**

Add a concise Python example using an already-loaded calibration artifact/profile, explicit module weights and observation policy, an injected test reference, and optional descriptor mapping. State that blank/nonresponse mapping and race-slot approximation are explicit, that recorded flags do not allocate latent disease, and that the returned trajectory/truth objects are evaluator-only. Explain how a caller may separately pass returned bundles to the reviewed package bridge without implying package generation is enabled.

Extend the AST scanner with `src/synthetic/cohort.py`, allow only in-memory calibration artifact and native dependencies, and reject calibrator/input/held-out/privacy/real-data/Synthea imports, path readers, package writers, and output lifecycle calls. Keep the production `generate.py` CLI fail-closed.

- [x] **Step 4: Run task checks and commit**

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_cohort_boundaries.py tests/synthetic/test_package_export_boundaries.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/cohort.py tests/synthetic/test_cohort_boundaries.py
git diff --check
```

Commit:

```sh
git add src/synthetic/cohort.py docs/synthetic-generator.md README.md tests/synthetic/test_cohort_boundaries.py tests/synthetic/test_package_export_boundaries.py
git commit -m "docs: document native cohort boundary"
```

### Task 6: Independent reviews and integration evidence

**Files:**
- Review only: all files changed by Tasks 1–5 plus this spec and plan.
- Modify only through the responsible implementer when a review finding is real; never patch a reviewer finding directly in the controller.

**Interfaces:**
- Consumes: task commits, task review reports, the spec, and the SDD ledger.
- Produces: clean broad review, full verification evidence, merged/pushed `main`, and cleanup of only this slice.

- [x] **Step 1: Create the plan-owned SDD ledger and dispatch fresh task reviewers**

Use the plan-specific SDD workspace and record the task dependency/conflict scan before Task 1. For each implementation task, generate a review package from the recorded task base through its commit and dispatch a fresh reviewer. Resolve every Critical/Important finding through an implementer-only fix round followed by exactly one scoped re-review; record residual Minor findings and rulings.

- [x] **Step 2: Run the broad whole-branch review**

Dispatch the most capable fresh reviewer over the full branch range. Require checks for aggregate-target extraction, suppression behavior, recorded-versus-latent prevalence separation, deterministic named-stream use, healthy/disorder coverage, observation/resource PASS gating, hidden-truth redaction, no filesystem/governed boundaries, descriptor handling, docs claims, and all acceptance criteria. Resolve load-bearing findings with one final implementer/re-review wave as required by the SDD workflow.

- [x] **Step 3: Run final verification before integration**

From the feature worktree run focused cohort tests, the complete `pytest` suite, Ruff, schema validation, `git diff --check`, and a staged-file audit. Confirm no real data, key material, generated package, path, or hidden truth artifact is tracked. Record exact test counts and the branch tip in the ledger.

- [ ] **Step 4: Merge, push, parity, and cleanup**

Using the finishing-development-branch workflow, fast-forward the reviewed branch into `main`, rerun full verification on merged `main`, push `origin/main`, and verify `git rev-parse HEAD` equals `git rev-parse origin/main`. Remove only this plan's worktree, branch, and ignored SDD workspace; preserve unrelated worktrees and pre-existing generated caches.
