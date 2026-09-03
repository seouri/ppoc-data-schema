# Native Excess-Weight Ancillary Pathway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Implementation, independent review, verification, and publication are complete; this plan is retained as historical provenance.

**Goal:** Add a deterministic evaluator-only projection and validator for fictional excess-weight laboratory, problem-list, and referral rows in the exact PPOC resource schema, with no medication descendant and no change to the existing GHD runtime/export path.

**Architecture:** A separate `synthetic.native.excess_weight_ancillary` module consumes one typed `CohortMember`, an extracted `ResourceShape`, and an aggregate-safe `ExcessWeightAncillaryPolicy`. It returns immutable rows for the four ancillary resources and a fixed aggregate report. The module mirrors the reviewed GHD contract but owns its fictional constants and ID namespace. It never integrates into `development-realistic`, `ancillary_bundle`, package export, calibration, or Synthea in this slice.

**Tech Stack:** Python 3.12+, standard-library dataclasses/enums/hashlib/re/collections.abc/types, existing synthetic cohort/observation/model/resource contracts, pytest, Ruff, schema checker.

**Spec:** `docs/superpowers/specs/2026-09-02-excess-weight-ancillary-pathway-design.md`

## Global Constraints

- Accept only `CohortMember`, `ResourceShape`, and `ExcessWeightAncillaryPolicy`; no paths, path-like values, CSV readers, rows, keys, reports, output destinations, environment input, or governed data.
- Emit only `labs`, `medications`, `problem_list`, and `referrals` in fixed order; every row uses supplied descriptor field order and empty strings for missing values.
- Use only fictional constants: `SYN-EXCESS-WEIGHT`, `SYN-EXCESS-WEIGHT-LIPID`, `SYN-EXCESS-WEIGHT-A1C`, `Synthetic Pediatric Nutrition`, and `Synthetic` lab marker. Do not claim ICD, LOINC, RxNorm, or clinical reference semantics.
- A valid `EXCESS_WEIGHT` frame maps recognition to one referral, workup to two labs, diagnosis to one unresolved problem row, and never maps `treatment_start` to medication. Hidden/unrecorded events do not create rows.
- Healthy, GHD, and other members return empty tuples; no emitted row contains or derives `obesity_flag`.
- Projection is deterministic, nonmutating, random-free, and source-point/visit linked. Errors, reprs, and reports omit patient IDs, row IDs, ages, codes, values, events, truth hashes, paths, keys, and source evidence.
- Validator statuses are fixed `PASS`, `FAIL`, and `UNEVALUABLE` with `FAIL > UNEVALUABLE > PASS`, and fixed five-check ordering.
- The module may import only standard-library helpers, native cohort/model/observation/resource types; static tests reject calibration, real-data, held-out, privacy, DuckDB, filesystem, CSV, package/export, manifest, subprocess, and Synthea coupling.
- Each task ends with focused tests, Ruff for touched files, `git diff --check`, and a scoped commit. Never stage generated caches or reports.

---

### Task 1: Add strict models and deterministic projection

**Files:**
- Create: `src/synthetic/native/excess_weight_ancillary.py`
- Create: `tests/synthetic/test_excess_weight_ancillary_models.py`
- Create: `tests/synthetic/test_excess_weight_ancillary_projection.py`

**Interfaces:**
- Consumes: `CohortMember`, `AgeRegimeDisorderTrajectory`, `ClinicalEvent`, observation event/frame types, `ResourceShape`, and `ResourceRow`.
- Produces: policy/projection value objects, fictional constants, `project_excess_weight_ancillary_resources`, and immutable exact-schema rows.

- [x] **Step 1: Write failing model and projection tests**

  Use existing fictional fixtures and the checked-in descriptor mapping. Cover frozen policy/projection objects, safe tokens, exact four-resource order, immutable mappings, descriptor field order, empty-string conventions, fictional constants, synthetic IDs, healthy/GHD emptiness, every visible event combination, no medication even with treatment, delayed results, same-age events, nullable problem links, deterministic IDs, no mutation, and fixed redacted errors.

- [x] **Step 2: Run focused tests to verify they fail**

  ```bash
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_excess_weight_ancillary_models.py tests/synthetic/test_excess_weight_ancillary_projection.py
  ```

  Expected: collection/import failure because the new module and fixtures do not yet exist.

- [x] **Step 3: Implement models and projection**

  Define a separate policy, projection, and redacted exception. Validate typed member/frame/truth binding exactly as the GHD projection does. For a target member, map only the first visible recognition/workup/diagnosis events to the fixed fictional rows; leave medications empty even when a latent `treatment_start` exists. Build rows in the supplied descriptor field order, use a namespaced deterministic ID helper, and return a mapping proxy. Do not import or modify GHD modules or runtime/export code.

- [x] **Step 4: Run focused tests and lint**

  ```bash
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_excess_weight_ancillary_models.py tests/synthetic/test_excess_weight_ancillary_projection.py
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/native/excess_weight_ancillary.py tests/synthetic/test_excess_weight_ancillary_models.py tests/synthetic/test_excess_weight_ancillary_projection.py
  git diff --check
  ```

- [x] **Step 5: Commit**

  ```bash
  git add src/synthetic/native/excess_weight_ancillary.py tests/synthetic/test_excess_weight_ancillary_models.py tests/synthetic/test_excess_weight_ancillary_projection.py
  git commit -m "build: add excess-weight ancillary projection"
  ```

### Task 2: Add aggregate validator and static boundary tests

**Files:**
- Modify: `src/synthetic/native/excess_weight_ancillary.py`
- Create: `tests/synthetic/test_excess_weight_ancillary_validation.py`
- Create: `tests/synthetic/test_excess_weight_ancillary_boundaries.py`

**Interfaces:**
- Consumes: Task 1 typed rows and the existing observation validator.
- Produces: `ExcessWeightAncillaryValidationStatus`, `ExcessWeightAncillaryCheck`, `ExcessWeightAncillaryValidationReport`, and `validate_excess_weight_ancillary_resources`.

- [x] **Step 1: Write failing validator and boundary tests**

  Assert fixed check ordering/status precedence, valid target and non-target reports, malformed rows, duplicate rows, wrong fictional constants, invalid IDs/types, bad timing/result delay, broken visit/patient links, missing or invalid source evidence, immutable aggregate mappings, redacted repr/error text, forbidden imports/signatures, no I/O/randomness, and explicit separation from `obesity_flag`.

- [x] **Step 2: Run focused tests to verify they fail**

  ```bash
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_excess_weight_ancillary_validation.py tests/synthetic/test_excess_weight_ancillary_boundaries.py
  ```

- [x] **Step 3: Implement the validator**

  Check visible structure independently, then compare typed rows to the deterministic expected projection when source evidence passes. Return only fixed reason codes. Treat unavailable private evidence as `UNEVALUABLE` unless visible rows already fail; keep medication emptiness as a pathway invariant. Do not include patient/visit/row IDs, ages, codes, values, or source details in diagnostics.

- [x] **Step 4: Run focused tests and lint**

  ```bash
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_excess_weight_ancillary_validation.py tests/synthetic/test_excess_weight_ancillary_boundaries.py
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/native/excess_weight_ancillary.py tests/synthetic/test_excess_weight_ancillary_validation.py tests/synthetic/test_excess_weight_ancillary_boundaries.py
  git diff --check
  ```

- [x] **Step 5: Commit**

  ```bash
  git add src/synthetic/native/excess_weight_ancillary.py tests/synthetic/test_excess_weight_ancillary_validation.py tests/synthetic/test_excess_weight_ancillary_boundaries.py
  git commit -m "test: validate excess-weight ancillary boundaries"
  ```

### Task 3: Document the ordinary-development contract

**Files:**
- Modify: `docs/synthetic-generator.md`
- Modify: `README.md`
- Create: `tests/synthetic/test_excess_weight_ancillary_docs.py`

**Interfaces:**
- Consumes: the new public API and pathway contract.
- Produces: concise user-facing documentation and drift tests; no runtime integration.

- [x] **Step 1: Write failing documentation tests**

  Assert the guide names the API, exact fictional constants, evaluator-only status, no-medication rule, and explicit `EXCESS_WEIGHT`/`obesity_flag` separation; assert README links the guide and the guide does not claim prevalence, privacy, clinical, release, or Synthea evidence.

- [x] **Step 2: Implement documentation and tests**

  Add a concise section near the existing GHD guidance and one README link/roadmap sentence. Keep optional governance workflows separate and do not duplicate the full guide in README.

- [x] **Step 3: Run focused documentation tests and checks**

  ```bash
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_excess_weight_ancillary_docs.py
  git diff --check
  ```

- [x] **Step 4: Commit**

  ```bash
  git add docs/synthetic-generator.md README.md tests/synthetic/test_excess_weight_ancillary_docs.py
  git commit -m "docs: describe excess-weight ancillary fixtures"
  ```

### Task 4: Review, verify, merge, and push

- [x] Run the complete synthetic suite, Ruff, schema check, lock check, and whitespace check.
- [x] Package a review diff for an independent broad reviewer; address every Critical/Important/Minor finding and rereview any fix.
- [x] Inspect staged names/stat/diff, excluding untracked `__pycache__` directories; commit any final scoped fixes.
- [x] Merge to `main`, push `origin/main`, fetch, and verify `HEAD` equals `origin/main`.
- [x] Mark this plan complete only after the pushed commit and verification evidence exist.
