# Observed Resource Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Execute each task in an isolated worktree with a fresh implementer, then run the required review and fix gates before merge. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, evaluator-only in-memory bridge from validated observation frames to descriptor-shaped synthetic base-resource rows and fictional clinical descendants.

**Architecture:** `synthetic.native.resources` owns strict immutable descriptor-shape, demographic, row, descendant, bundle, and aggregate-report models. A pure projection consumes only an `ObservationFrame` plus an already-loaded descriptor mapping, preserves visible observation values and synthetic links, rejects unrepresentable observed length instead of relabeling it, and leaves ancillary resources empty. It never reads files, exports packages, consumes calibration/held-out/privacy inputs, or changes the production generator.

**Tech Stack:** Python 3.12+, standard-library `dataclasses`, `collections.abc`, `enum`, `hashlib`, `math`, `re`, `types`, existing evaluator observation models, pytest, Ruff, and the existing schema checker.

**Spec:** `docs/superpowers/specs/2026-08-31-observed-resource-contract-design.md`

## Global Constraints

- The module accepts an in-memory descriptor mapping only; no path, file handle, CSV reader, package writer, calibration artifact, held-out report, privacy report, seed, or arbitrary column list.
- The six base resources are `patients`, `visits`, `labs`, `medications`, `problem_list`, and `referrals`; augmented resources and package manifests are out of scope.
- Patient IDs and visit IDs remain synthetic; missing values use the existing empty-string convention; no latent truth, source events, hashes, stream identities, or private references enter mappings, repr, reports, or files.
- Only `WEIGHT`, `HEIGHT`, `HEAD_CIRCUMFERENCE`, and derived `BMI` map to descriptor-shaped visit fields; observed `LENGTH` raises `ResourceProjectionUnavailable`.
- Fixed unit conversions are weight kilograms × `35.274` to ounces and height centimeters ÷ `2.54` to inches; no clipping, resampling, or hidden-value substitution.
- Recognition, workup, and diagnosis descendants use only `RECORDED_EVENT_CODES`; codes remain fictional and are not asserted to be clinical terminology.
- Labs, medications, problem-list, and referral rows remain empty until separately reviewed causal/resource contracts exist.
- Reports expose only fixed `PASS`, `FAIL`, and `UNEVALUABLE` statuses, check names, reason codes, and counts.
- Boundary tests must show no imports or calls into calibration, held-out validation, privacy audit, CSV/package writers, smoke generation, schema file loading, or real-data paths.

---

### Task 1: Add strict resource-shape, demographic, row, and bundle models

**Files:**
- Create: `src/synthetic/native/resources.py`
- Create: `tests/synthetic/test_observed_resource_models.py`

**Interfaces:**
- Consumes: standard-library mappings and the observation-frame model types.
- Produces: `BASE_RESOURCE_NAMES`, `ResourceProjectionUnavailable`, `ResourceSpec`, `ResourceShape`, `SyntheticDemographics`, `ResourceRow`, `ClinicalDescendant`, `ObservedResourceBundle`, `ResourceValidationStatus`, `ResourceCheck`, `ResourceValidationReport`.

- [x] **Step 1: Write failing tests**

  Cover exact six-resource extraction from the checked-in descriptor mapping, ordered field names, missing/duplicate resource and field rejection, synthetic-only IDs, closed demographic values, immutable rows, fictional event-code enforcement, private source-frame references, missing-value mapping, fixed report check names, and status aggregation.

- [x] **Step 2: Run the focused model tests to verify they fail**

  Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_observed_resource_models.py`

  Expected: collection or assertion failures because the resource contract does not yet exist.

- [x] **Step 3: Implement the strict models**

  Parse only the descriptor's `resources`/`schema.fields` mappings into immutable `ResourceShape` values. Require all six base resource names, unique nonempty field-name strings, synthetic patient IDs, descriptor-valid demographic tokens, ordered immutable row pairs, fixed fictional descendant codes, and a private `ObservationFrame` on each bundle. Implement visible-only `to_mapping()` and `repr()` methods.

- [x] **Step 4: Run focused tests, Ruff, and diff checks**

  Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_observed_resource_models.py`; `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests`; `git diff --check`.

- [x] **Step 5: Commit**

  ```bash
  git add src/synthetic/native/resources.py tests/synthetic/test_observed_resource_models.py
  git commit -m "feat: add observed resource contract models"
  ```

### Task 2: Project observation frames into visible base-resource rows

**Files:**
- Modify: `src/synthetic/native/resources.py`
- Create: `tests/synthetic/test_observed_resource_projection.py`

**Interfaces:**
- Consumes: `ObservationFrame`, `ResourceShape`, and `SyntheticDemographics` from Task 1.
- Produces: `project_observed_resources(frame, descriptor, demographics=None) -> ObservedResourceBundle` and deterministic visible resource rows/clinical descendants.

- [x] **Step 1: Write failing projection tests**

  Cover default synthetic demographics, exact descriptor field order, one patient row, one row per visible visit, `weight_oz`/`height_in`/`head_circ_cm`/`BMI` conversion, empty-string missingness, fictional encounter/source tokens, event-to-visit links, diagnosis-slot placement, ancillary empty resources, deterministic replay, and observed-length rejection.

- [x] **Step 2: Run projection tests to verify they fail**

  Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_observed_resource_projection.py`

  Expected: failures because projection and resource rows are not implemented.

- [x] **Step 3: Implement pure projection**

  Require `validate_observation_frame(frame)` to be `PASS`; extract a shape from the in-memory descriptor; fill patient demographics with strict defaults; project visible measurements without accessing latent truth; reject any observed length; map fixed event codes to exact visible visits and next available `enc_diag_*` slots; and emit explicit empty tuples for labs, medications, problem-list, and referrals. Do not draw randomness or write files.

- [x] **Step 4: Run focused tests, full observation tests, Ruff, and diff checks**

  Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_observed_resource_models.py tests/synthetic/test_observed_resource_projection.py tests/synthetic/test_observation_models.py tests/synthetic/test_observation_generation.py tests/synthetic/test_observation_validation.py tests/synthetic/test_observation_boundaries.py`; `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests`; `git diff --check`.

- [x] **Step 5: Commit**

  ```bash
  git add src/synthetic/native/resources.py tests/synthetic/test_observed_resource_projection.py
  git commit -m "feat: project observation frames to resource rows"
  ```

### Task 3: Validate resource bundles and document boundaries

**Files:**
- Modify: `src/synthetic/native/resources.py`
- Create: `tests/synthetic/test_observed_resource_validation.py`
- Create: `tests/synthetic/test_observed_resource_boundaries.py`
- Modify: `docs/synthetic-generator.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: `ObservedResourceBundle`, `ObservationFrame`, and the fixed resource shape/projection contracts.
- Produces: `validate_observed_resources(bundle) -> ResourceValidationReport`, boundary assertions, usage documentation, and explicit deferred-gate language.

- [x] **Step 1: Write failing validation and boundary tests**

  Cover malformed/private source evidence → `UNEVALUABLE`; patient/field-order/key/unit/BMI/event/ancillary violations → `FAIL`; exact frame correspondence; no hidden-truth/report leakage; deterministic mappings; no governed/file/schema/CLI imports; and unchanged eight-resource descriptor behavior.

- [x] **Step 2: Run validation tests to verify they fail**

  Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_observed_resource_validation.py tests/synthetic/test_observed_resource_boundaries.py`

  Expected: failures because aggregate validation and boundary assertions are not implemented.

- [x] **Step 3: Implement fixed aggregate checks and documentation**

  Validate patient identity, extracted field order, exact frame visits, unit conversion/missingness/BMI identity, one-to-one fictional descendants, empty ancillary resources, and non-failing source-frame evidence. Keep reports aggregate-only and add a concise guide section with examples and limitations.

- [x] **Step 4: Run focused tests, full suite, Ruff, schema, and diff checks**

  Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q`; `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests`; `python3 schema/build.py --check`; `git diff --check`.

- [x] **Step 5: Commit**

  ```bash
  git add src/synthetic/native/resources.py tests/synthetic/test_observed_resource_validation.py tests/synthetic/test_observed_resource_boundaries.py docs/synthetic-generator.md README.md
  git commit -m "feat: validate observed resource bundles"
  ```

### Task 4: Independent reviews and handoff

- [x] Create the ignored SDD ledger for this plan and record implementation/review/fix status for each task.
- [x] Dispatch a fresh reviewer for each implementation task; resolve Critical/Important findings with fresh implementer fix rounds and scoped re-reviews.
- [x] Dispatch one broad final reviewer over the merge-base diff and resolve all Critical/Important findings.
- [x] Run full tests, Ruff, schema validation, diff checks, leakage/boundary checks, and a generated frame/resource smoke example from the feature worktree.
- [x] Merge to `main`, rerun verification on merged `main`, push, verify `HEAD == origin/main`, and remove only this slice's worktree/branch/ignored SDD workspace.

### Completion evidence

- Branch tip, review commits, focused/full test counts, schema/lint/diff output, merge/push hash parity, and cleanup evidence are recorded before handoff.

### Feature-branch evidence before integration

- Implementation/fix commits: `d53d749`, `ddfd1b0`, `d869baf`, `f1935af`, `487a69f`, `b6643c6`, `0a5414f`, `894c475`, `121d14f`, `ddee7ba`.
- Review outcome: task reviews and scoped re-reviews found and resolved all reported findings; broad re-review at `ddee7ba87177b76d956836e1e64232379f77aaeb` was `READY` with no Critical, Important, or Minor findings.
- Fresh verification: focused observed-resource suite `117 passed`; full suite `923 passed`; Ruff clean; schema checker `validated 8 resources in datapackage.json`; `git diff --check 2d74641..HEAD` clean; deterministic in-memory smoke report `PASS` with seven passing checks.

### Integration evidence

- Main fast-forward merge: `2d74641` → `4566feb0ca81ff97f33b60d12ab45aba46918d8f`.
- Merged-main verification at `4566feb`: full suite `923 passed`; focused suite `117 passed`; Ruff clean; schema checker `validated 8 resources in datapackage.json`; diff check clean; deterministic smoke report `PASS` with seven passing checks.
- Implementation push/parity checkpoint: `HEAD == origin/main == 4566feb0ca81ff97f33b60d12ab45aba46918d8f` immediately after the code merge; the later documentation-only evidence commit is separate.
- Cleanup: removed `.worktrees/observed-resource-contract`, deleted `codex/observed-resource-contract`, pruned worktree metadata; unrelated worktree `/private/tmp/ppoc-synthetic-growth-fixtures-foundation` preserved.
