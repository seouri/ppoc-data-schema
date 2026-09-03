# All-disorder coverage development profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit `development-all-disorders` route that generates deterministic exact-schema fixtures covering every native growth trajectory and every reviewed ancillary projection without changing existing profiles.

**Architecture:** Add one engine-neutral multidisorder adapter that dispatches to the existing typed projections and validates/merges a fresh six-resource bundle. Extend native module selection with optional reference-sex eligibility, then add a separate runtime/CLI profile using conditional fictional coverage weights; the existing realistic GHD route remains unchanged. Update the guide, README roadmap link, and companion design/plan references so profile names and content boundaries stay consistent.

**Tech Stack:** Python 3.12+, standard-library dataclasses/enums/types, existing native cohort/observation/resource contracts, pytest, Ruff, exact-schema exporter, and the checked-in CDC/source-matched development runtime.

**Spec:** `docs/superpowers/specs/2026-09-03-all-disorder-development-profile-design.md`

## Global Constraints

- The new profile name is `development-all-disorders`; its configuration/artifact identity is `development-all-disorders-v1`.
- The F-reference prior is healthy `1/2` plus `1/18` for each of the nine nonhealthy kinds; the M-reference prior is healthy `1/2` plus `1/16` for each of the eight non-Turner kinds and Turner `0`.
- `CohortConfig.module_weights_by_reference_sex` is optional and defaults empty; when present, generation selects the matching canonical row before eligibility filtering, preserving all legacy callers and the unchanged `generate_native_cohort` signature.
- Demographic weights reuse the existing snapshot-shaped F/M/U, ethnicity, race, and race-multiselect values, but remain orthogonal to the fictional latent coverage prior.
- Turner may be selected only when `PatientState.reference_sex == "F"`; existing callers without sex-constrained modules keep their current selection behavior.
- Exact visible resources remain the six base resources plus `patients_augmented` and `visits_augmented`; the generic empty-ancillary validator and all existing profile APIs remain unchanged.
- Only the matching reviewed ancillary projector runs for a member; healthy, familial-short-stature, and constitutional-delay members receive four empty ancillary tuples.
- Merged all-disorder bundles remain local serialization sidecars and are not assigned to `CohortMember.bundle`; that field keeps its dependency-leaf GHD-only serializer contract.
- Fictional lab markers are converted to the descriptor empty-string sentinel only at all-disorder serialization; latent kind, state, truth, treatment, source frames, and row diagnostics never enter public mappings or files.
- No task reads real rows, adds a real/governed input, adds a Synthea dependency, adds a model/network call, or invents subtype prevalence.
- Every task ends with focused tests, Ruff for touched Python, `git diff --check`, and one scoped commit containing only its deliverable; ignored `.superpowers/sdd/` reports and caches remain unstaged.

---

### Task 1: Add the multidisorder projection and bundle adapter

**Files:**
- Create: `src/synthetic/native/multidisorder_ancillary.py`
- Create: `tests/synthetic/test_multidisorder_ancillary_models.py`
- Create: `tests/synthetic/test_multidisorder_ancillary_projection.py`
- Create: `tests/synthetic/test_multidisorder_ancillary_validation.py`
- Create: `tests/synthetic/test_multidisorder_ancillary_boundaries.py`

**Interfaces:**
- Consumes: `CohortMember`, `ResourceShape`, `ObservedResourceBundle`, the seven existing concrete projectors/validators, and the existing resource validator.
- Produces: `MultidisorderAncillaryPolicy`, `MultidisorderAncillaryProjection`, `MultidisorderAncillaryValidationStatus`, `MultidisorderAncillaryCheck`, `MultidisorderAncillaryValidationReport`, `MultidisorderAncillaryProjectionUnavailable`, `MultidisorderAncillaryBundleUnavailable`, `project_multidisorder_ancillary_resources(member, shape, policy)`, `validate_multidisorder_ancillary_resources(member, projection, policy)`, `merge_multidisorder_ancillary_resources(bundle, member, projection, policy)`, and `validate_multidisorder_ancillary_bundle(bundle, member, policy)`.

- [ ] **Step 1: Write failing model and dispatch tests.**

  Import the existing fixture builders from the ancillary tests, construct one valid member per `DisorderKind`, and assert the new policy rejects non-string/unsafe IDs, booleans, negative delays, and mutable objects. Assert the projection fixes row-key order to `("labs", "medications", "problem_list", "referrals")`, preserves descriptor field order, is frozen, and has an aggregate-only `repr`/mapping. Assert project dispatch returns the concrete rows for GHD, hypothyroidism, celiac, SGA, Turner, undernutrition, and excess weight, while healthy, familial short stature, and constitutional delay return four empty tuples. Assert malformed typed inputs raise exactly `multidisorder ancillary projection unavailable`.

- [ ] **Step 2: Run the new tests to verify they fail.**

  Run: `PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_multidisorder_ancillary_models.py tests/synthetic/test_multidisorder_ancillary_projection.py tests/synthetic/test_multidisorder_ancillary_validation.py tests/synthetic/test_multidisorder_ancillary_boundaries.py`

  Expected: collection fails because the multidisorder module and its public contracts do not yet exist.

- [ ] **Step 3: Implement the immutable adapter and bundle seam.**

  Define fixed resource/check/reason constants and aggregate-only frozen models. Keep the projection wrapper free of a public `kind` field; dispatch internally from the member's already-validated trajectory. Use a static mapping from each supported kind to its concrete policy class, projector, validator, projection class, and validator status. Construct a concrete policy by appending a fixed kind suffix to the aggregate-safe multidisorder policy identity; never accept caller callables or terminology. For empty kinds, require all four tuples to be empty. Map concrete validator statuses into fixed multidisorder statuses without copying concrete reason text or row values.

  Implement bundle validation with fixed checks `bundle_identity`, `base_resources`, `ancillary_resources`, and `truth_boundary` and precedence `FAIL > UNEVALUABLE > PASS`. Isolate the four ancillary tuples before calling `validate_observed_resources`; require exact patient/shape/source-frame binding, an empty base ancillary view, concrete projection validation, and every lab/medication/referral visit ID resolving to a visible base visit. Merge only a validated empty-ancillary bundle, return a fresh immutable `ObservedResourceBundle`, revalidate the merged result, and reject any second merge that would append nonempty ancillary rows with the fixed message `multidisorder ancillary bundle unavailable`; an empty projection for a non-ancillary kind is an immutable no-op because the plain bundle seam cannot carry hidden merge state. Keep the merged bundle as a local serialization sidecar; do not assign it to `CohortMember.bundle`, whose existing serializer remains GHD-only. Ensure all exception/repr/mapping paths omit IDs, ages, values, source objects, and latent state.

- [ ] **Step 4: Run focused tests to verify they pass.**

  Run the same four-test command from Step 2, then `PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/native/multidisorder_ancillary.py tests/synthetic/test_multidisorder_ancillary_*.py` and `git diff --check`.

  Expected: all adapter/model/projection/validation/boundary tests pass, Ruff exits 0, and whitespace is clean.

- [ ] **Step 5: Commit the adapter.**

  ```bash
  git add src/synthetic/native/multidisorder_ancillary.py tests/synthetic/test_multidisorder_ancillary_models.py tests/synthetic/test_multidisorder_ancillary_projection.py tests/synthetic/test_multidisorder_ancillary_validation.py tests/synthetic/test_multidisorder_ancillary_boundaries.py
  git commit -m "feat: add multidisorder ancillary bundle adapter"
  ```

### Task 2: Make native module selection reference-sex aware

**Files:**
- Modify: `src/synthetic/cohort.py`
- Create: `tests/synthetic/test_cohort_module_eligibility.py`

**Interfaces:**
- Consumes: existing `CohortConfig`, `CohortModuleWeight`, `PatientState`, and module mapping validation.
- Produces: the unchanged `generate_native_cohort` signature with deterministic optional filtering of a module's `required_reference_sex` attribute before each module draw.

- [ ] **Step 1: Write the failing eligibility tests.**

  Build a config with positive healthy/Turner weights and a module mapping containing `HealthyGrowthModule()` and `TurnerSyndromeModule()`. Generate a female-reference cohort and assert Turner can occur; generate a male-reference cohort and assert no member is assigned Turner and no module sampling error occurs. Add a mixed all-module mapping test asserting a module with no `required_reference_sex` remains eligible for both sexes, a malformed non-string requirement fails with the existing redacted generation boundary, and reordering the input mapping leaves visible mappings/counts unchanged.

- [ ] **Step 2: Run the eligibility tests to verify they fail.**

  Run: `PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_cohort_module_eligibility.py`

  Expected: the male-reference case intermittently reaches `TurnerSyndromeModule` and fails its patient eligibility check.

- [ ] **Step 3: Implement conditional filtering without changing existing draws.**

  Create a private helper that receives the canonical sorted positive weights, copied modules, and the sampled reference sex. Treat absent `required_reference_sex` as unrestricted; require a present value to be a nonempty string; retain only matching modules. Construct `PatientState` before module selection, call the helper using the existing `cohort.module` stream, and pass the filtered positive weights to `_select_weighted_category`, which already normalizes any positive total. Keep healthy eligible and preserve the current sorted-kind behavior and all public signatures.

- [ ] **Step 4: Run focused and regression tests.**

  Run: `PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_cohort_module_eligibility.py tests/synthetic/test_cohort_generation.py tests/synthetic/test_cohort_models.py`, then Ruff on the touched Python/tests and `git diff --check`.

  Expected: new eligibility tests and existing cohort tests pass with no change to unrestricted module behavior.

- [ ] **Step 5: Commit conditional selection.**

  ```bash
  git add src/synthetic/cohort.py tests/synthetic/test_cohort_module_eligibility.py
  git commit -m "feat: honor reference-sex module eligibility"
  ```

### Task 3: Add the all-disorder runtime profile and CLI route

**Files:**
- Modify: `src/synthetic/development_runtime.py`
- Modify: `src/synthetic/generate.py`
- Create: `tests/synthetic/test_all_disorder_runtime.py`
- Modify: `tests/synthetic/test_generate_cli.py`
- Modify: `tests/synthetic/test_development_scale.py`
- Modify: `tests/test_augment_import.py`

**Interfaces:**
- Consumes: Task 1 adapter APIs, Task 2 conditional module selection, existing CDC runtime/exporter, and all ten native module constructors.
- Produces: `development_all_disorders_calibration_profile()`, `development_all_disorders_config(patient_count, seed)`, `build_development_all_disorders_cohort(...)`, `generate_development_all_disorders_cohort(...)`, and CLI profile `development-all-disorders`.

- [ ] **Step 1: Write failing runtime/CLI tests.**

  Assert the new calibration artifact ID, demographic weights, observation policy, and exact conditional prior rows. Build a sufficiently large deterministic cohort and assert all ten kinds occur, Turner occurs only for F reference members, equal seeds give equal visible mappings and module count vectors, and changed seeds alter a draw. Assert the configuration hash changes when a prior, eligibility policy, module version, or ancillary policy changes. Add a CLI test that runs `development-all-disorders` into a fresh temporary root and checks the exact eight-resource inventory, schema fingerprint, manifest profile/identity, unique IDs, generic event descendants, nonempty rows for supported pathway kinds, GHD-only `E23.0`, and no latent/truth tokens. Add a scale-marked 10,000-patient CLI composition check behind `SYNTHETIC_RUN_SCALE=1`; do not alter the existing scale defaults.

- [ ] **Step 2: Run the new tests to verify they fail.**

  Run: `PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_all_disorder_runtime.py tests/synthetic/test_generate_cli.py -k 'all_disorder or no_profile or unknown_profile' tests/synthetic/test_development_scale.py -k all_disorder`

  Expected: collection or execution fails because the profile builders and CLI dispatch are absent.

- [ ] **Step 3: Implement the profile using existing exporter boundaries.**

  Add fixed profile/policy/version constants and a canonical ten-kind module factory. Define the all-disorder demographic builder by copying only the existing realistic aggregate-shaped values with a distinct artifact identity. Define conditional F/M prior tuples exactly as the spec states; bind them through the optional validated `CohortConfig.module_weights_by_reference_sex` table, select the matching row before Task 2 eligibility filtering, and include the table in the configuration hash together with all ten module versions, eligibility policy, observation policy, snapshot identity, and ancillary policy. Pass all ten modules to `generate_native_cohort`, preserving the existing two-profile module map for legacy routes.

  Add the all-disorder runtime builders and route. In visible projection, call the multidisorder projector/merge once per member, convert every typed `Synthetic` lab marker to `""`, and add only the existing `E23.0` token at GHD diagnosis visits. Keep the old `include_realistic_pathway` branch and GHD policy untouched. Wrap failures in the existing fixed package-export message. Add `development-all-disorders` to the explicit profile set and dispatch only that name to the new runner; do not add input flags or change no-profile behavior. Update profile phrase assertions in augmenter-boundary tests to recognize the fourth explicit development profile.

- [ ] **Step 4: Run focused runtime/CLI tests and static checks.**

  Run the focused command from Step 2, then `PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/cohort.py src/synthetic/development_runtime.py src/synthetic/generate.py tests/synthetic/test_all_disorder_runtime.py tests/synthetic/test_generate_cli.py tests/synthetic/test_development_scale.py tests/test_augment_import.py`, `python3 schema/build.py --check`, and `git diff --check`.

  Expected: all non-scale tests pass; scale tests remain skipped unless explicitly enabled; Ruff/schema/whitespace checks exit 0.

- [ ] **Step 5: Commit the runtime route.**

  ```bash
  git add src/synthetic/development_runtime.py src/synthetic/generate.py src/synthetic/cohort.py tests/synthetic/test_all_disorder_runtime.py tests/synthetic/test_generate_cli.py tests/synthetic/test_development_scale.py tests/test_augment_import.py
  git commit -m "feat: add all-disorder development profile"
  ```

### Task 4: Document and reconcile the roadmap

**Files:**
- Modify: `docs/synthetic-generator.md`
- Modify: `README.md`
- Modify: `docs/augment-import.md`
- Modify: `docs/augmenter-oracle.md`
- Modify: `docs/superpowers/specs/2026-09-01-development-authority-generator-cli-design.md`
- Modify: `docs/superpowers/plans/2026-09-01-development-authority-generator-cli.md`
- Modify: `docs/superpowers/specs/2026-08-30-synthetic-growth-fixtures-design.md`
- Create: `tests/synthetic/test_all_disorder_docs.py`

**Interfaces:**
- Consumes: the published Task 3 profile names and the all-disorder spec.
- Produces: synchronized ordinary-development instructions and one concise README roadmap link.

- [ ] **Step 1: Write failing documentation assertions.**

  Assert the guide contains the exact command `uv run python -m synthetic.generate --profile development-all-disorders --output /tmp/ppoc-development-all-disorders --patients 1000 --seed 20260901`, the conditional prior table, `development-all-disorders-v1`, snapshot-shaped demographics, Turner reference-sex rule, all seven ancillary dispatch targets, GHD-only `E23.0`, fictional coverage/non-prevalence wording, exact-schema/hidden-truth boundaries, and the unchanged no-profile failure string. Assert README contains links to the new spec and plan but no copied guide paragraph. Assert augment/import/oracle docs list all four explicit development profiles. Assert completed parent spec/plan language no longer says the new profile is absent while retaining historical GHD-only compatibility statements.

- [ ] **Step 2: Run docs tests to verify they fail.**

  Run: `PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_all_disorder_docs.py tests/test_augment_import.py`

  Expected: assertions fail because the guide and companion references do not name the new profile.

- [ ] **Step 3: Update the guide and companion roadmap references.**

  Add one concise profile paragraph/command block near the existing explicit profiles. State that demographics mirror the snapshot shape but subtype labels are unavailable, the F/M conditional fictional prior is coverage-only, Turner is F-reference-only, only matching reviewed projections create ancillary rows, GHD alone receives `E23.0`, and the exact exporter/manifest/hidden-truth boundaries remain. Add one README sentence linking the guide, spec, and plan; do not duplicate the guide. Add a dated follow-on note to the completed CLI/parent design and plan so their three-profile historical scope is explicit and the all-disorder route is discoverable. Update augmenter docs to list the fourth explicit profile without changing their fail-closed claims.

- [ ] **Step 4: Run docs tests and checks.**

  Run the command from Step 2, `PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check tests/synthetic/test_all_disorder_docs.py`, and `git diff --check`.

  Expected: documentation assertions pass, Ruff exits 0, and no whitespace errors remain.

- [ ] **Step 5: Commit documentation.**

  ```bash
  git add docs/synthetic-generator.md README.md docs/augment-import.md docs/augmenter-oracle.md docs/superpowers/specs/2026-09-01-development-authority-generator-cli-design.md docs/superpowers/plans/2026-09-01-development-authority-generator-cli.md docs/superpowers/specs/2026-08-30-synthetic-growth-fixtures-design.md tests/synthetic/test_all_disorder_docs.py
  git commit -m "docs: describe all-disorder development profile"
  ```

### Task 5: Independent review, full verification, and publication

**Files:**
- Modify: `docs/superpowers/plans/2026-09-03-all-disorder-coverage-profile.md`
- Create: `.superpowers/sdd/2026-09-03-all-disorder-coverage-profile/progress.md` (ignored ledger and reports only)

**Interfaces:**
- Consumes: completed Tasks 1–4 and their scoped commits.
- Produces: a reviewed, verified `main` commit published to `origin/main` with exact SHA parity.

- [ ] **Step 1: Record the ledger and task reviews.**

  Run `bash /Users/joon/.codex/plugins/cache/openai-api-curated/superpowers/1e285826/skills/subagent-driven-development/scripts/sdd-workspace docs/superpowers/plans/2026-09-03-all-disorder-coverage-profile.md`, record the plan identity, task-pair/file conflict scan, each implementer BASE, focused evidence, review package, findings, fix rounds, and completion line. Generate each task review package from its recorded BASE through the task tip and require separate spec-compliance and quality verdicts. Fix every Critical/Important/Minor finding through the prescribed implementer/re-review loop; do not edit reviewed code in the controller session.

- [ ] **Step 2: Run repository-wide verification.**

  Run `PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q`, `PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests`, `python3 schema/build.py --check`, `uv lock --check`, and `git diff --check`. If runtime is acceptable, run the new 10,000-patient scale profile with `SYNTHETIC_RUN_SCALE=1` and record its output separately from ordinary CI.

- [ ] **Step 3: Obtain the broad review.**

  Generate `review-package` from the plan merge base through the final task tip and dispatch the most capable independent reviewer. Point it at the ledger's deferred-minor/ruling lines. If findings exist, dispatch one fix agent for the complete list, run exactly one scoped re-review, and record any residual ruling before integration.

- [ ] **Step 4: Merge and push.**

  After fresh green verification and a clean broad review, use the finishing workflow to merge the feature branch into `main`, rerun the full suite on the merged result, push `main` to `origin`, and verify `git rev-parse HEAD`, `git rev-parse main`, and `git rev-parse origin/main` are identical. Preserve the pre-existing untracked caches and all ignored SDD reports.

## Plan self-review

- The spec's projection, conditional-selection, runtime, CLI, documentation, hidden-truth, exact-schema, testing, and publication criteria map to Tasks 1–5.
- No real-derived subtype prevalence is used; the existing snapshot-shaped realistic GHD route remains explicitly compatible.
- All public names used by later tasks are defined in Task 1 or Task 3 before consumption.
- `TBD`, `TODO`, `FIXME`, and vague "write tests later" placeholders are absent; each task names files, interfaces, commands, and expected outcomes.
