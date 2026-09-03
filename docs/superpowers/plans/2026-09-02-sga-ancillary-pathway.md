# Native SGA Ancillary Pathway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic evaluator-only projection and validator for
fictional SGA follow-up referral, birth-state/gestational-age evidence, and
problem-list rows in the exact PPOC schema, without changing existing modules,
the visible runtime, or package export.

**Architecture:** A separate `synthetic.native.sga_ancillary` module consumes
one typed `CohortMember`, an extracted `ResourceShape`, and a strict
`SgaAncillaryPolicy`. It owns fictional constants and an independent
deterministic ID namespace, emits immutable exact-schema rows, and returns a
fixed aggregate-only validation report. Hidden birth onset and catch-up versus
persistent branch state stay evaluator-only; medications are always empty
because the native SGA trajectory has no treatment event.

**Tech Stack:** Python 3.12+, standard-library dataclasses/enums/hashlib/re/
collections.abc/types, existing synthetic cohort/model/observation/resource
contracts, pytest, Ruff, schema checker.

**Spec:** `docs/superpowers/specs/2026-09-02-sga-ancillary-pathway-design.md`

## Global Constraints

- Accept only typed `CohortMember`, `ResourceShape`, and `SgaAncillaryPolicy`;
  no paths, path-like values, CSV readers, rows, keys, reports, output
  destinations, environment input, or governed data.
- Emit only `labs`, `medications`, `problem_list`, and `referrals` in fixed
  order; every row follows supplied descriptor field order and empty strings
  for missing values.
- Use only fictional constants: `SYN-SGA`, `SYN-SGA-GESTATIONAL-AGE`,
  `SYN-SGA-BIRTH-SIZE`, `Synthetic Neonatology Follow-up`, `Synthetic`, and
  `sga-ancillary-id-v1`; make no ICD/LOINC/RxNorm or clinical-value claim.
- A valid target frame maps visible recognition/workup/diagnosis to one
  referral/two labs/problem. Medication rows are always suppressed, including
  for any hidden or injected treatment state.
- Birth-onset, severity, and catch-up/persistent branch state never become
  visible text or values. Healthy and every non-SGA member return four empty
  tuples; no emitted row contains or derives `obesity_flag`.
- Projection is deterministic, nonmutating, random-free, and source-point/
  visit linked. Errors, reprs, checks, and reports omit IDs, ages, codes,
  values, events, severity, truth hashes, paths, keys, and source evidence.
- Validator statuses are fixed `PASS`, `FAIL`, and `UNEVALUABLE` with
  `FAIL > UNEVALUABLE > PASS`; visible event/count/age rules run before
  private-source validation.
- The module may import only standard-library helpers and native cohort/model/
  observation/resource types; static tests reject calibration, real-data,
  held-out, privacy, DuckDB, filesystem, CSV, package/export, manifest,
  subprocess, environment, network, randomness, and Synthea coupling.
- Each task ends with focused tests, Ruff, `git diff --check`, and a scoped
  commit; never stage generated caches or reports.

### Task 1: Add strict models and deterministic projection

**Files:**
- Create: `src/synthetic/native/sga_ancillary.py`
- Create: `tests/synthetic/test_sga_ancillary_models.py`
- Create: `tests/synthetic/test_sga_ancillary_projection.py`

**Interfaces:**
- Consumes: existing `CohortMember`, `ResourceShape`, `ResourceRow`, and
  `DisorderKind.SMALL_FOR_GESTATIONAL_AGE` values.
- Produces: frozen `SgaAncillaryPolicy` and `SgaAncillaryProjection`, fixed
  resource constants, and `project_sga_ancillary_resources(member, shape,
  policy)` for Task 2 and the docs.

- [x] **Step 1: Write failing model and projection tests**

  Use fictional SGA fixtures and the checked-in descriptor. Cover frozen
  models, safe tokens, exact resource order, immutable mappings, descriptor
  field order/types, empty-string conventions, constants, namespaced IDs,
  target and non-target emptiness, birth-onset/catch-up/persistent branches,
  every visible event combination, same-age events, nullable problem links,
  always-empty medications, deterministic replay, no mutation, and fixed
  redacted errors.

- [x] **Step 2: Run focused tests to verify they fail**

  ```bash
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_sga_ancillary_models.py tests/synthetic/test_sga_ancillary_projection.py
  ```

- [x] **Step 3: Implement models and projection**

  Define a separate frozen policy, projection, and redacted exception. Validate
  observation frame/member truth binding as the reviewed ancillary paths do.
  For target members, map first visible recognition/workup/diagnosis events to
  fixed fictional rows using source-point-linked visits; never emit medication
  rows or expose hidden birth/catch-up state. Build each row in descriptor
  order under a distinct deterministic namespace. Do not modify existing
  ancillary modules, runtime, exporter, or descriptor.

  The public signatures are:

  ```python
  def project_sga_ancillary_resources(
      member: CohortMember,
      shape: ResourceShape,
      policy: SgaAncillaryPolicy,
  ) -> SgaAncillaryProjection: ...
  ```

- [x] **Step 4: Run focused tests and lint**

  ```bash
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_sga_ancillary_models.py tests/synthetic/test_sga_ancillary_projection.py
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/native/sga_ancillary.py tests/synthetic/test_sga_ancillary_models.py tests/synthetic/test_sga_ancillary_projection.py
  git diff --check
  ```

- [x] **Step 5: Commit**

  ```bash
  git add src/synthetic/native/sga_ancillary.py tests/synthetic/test_sga_ancillary_models.py tests/synthetic/test_sga_ancillary_projection.py
  git commit -m "build: add SGA ancillary projection"
  ```

### Task 2: Add aggregate validator and static boundary tests

**Files:**
- Modify: `src/synthetic/native/sga_ancillary.py`
- Create: `tests/synthetic/test_sga_ancillary_validation.py`
- Create: `tests/synthetic/test_sga_ancillary_boundaries.py`

**Interfaces:**
- Consumes: Task 1's projection, policy, exact row contract, and source-point
  binding.
- Produces: `SgaAncillaryValidationStatus`, `SgaAncillaryCheck`,
  `SgaAncillaryValidationReport`, and
  `validate_sga_ancillary_resources(member, projection, policy)` for Task 3.

- [x] **Step 1: Write failing validator and boundary tests**

  Cover fixed order/status precedence, valid target/non-target reports, wrong
  constants/IDs/types, duplicates/count violations, result delay, timing,
  injected medication prohibition, broken patient/visit links, invalid/missing
  source, immutable/redacted reports, forbidden imports/signatures/no I/O/
  randomness/no obesity flag, visible-event checks with missing or invalid
  truth, and valid-frame/member trajectory mismatch.

- [x] **Step 2: Run focused tests to verify they fail**

  ```bash
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_sga_ancillary_validation.py tests/synthetic/test_sga_ancillary_boundaries.py
  ```

- [x] **Step 3: Implement the validator**

  Independently validate visible row structure, actual frame visits, always
  empty medications, expected counts/ages, and source-independent constants
  before invoking private source validation. Classify valid-frame/member truth
  binding mismatch as `FAIL/SOURCE_EVIDENCE_INVALID`; classify missing or
  malformed private evidence as `UNEVALUABLE` only without a visible failure.
  Compare with deterministic expected projection only after source and binding
  pass. Return fixed redacted reasons.

  The validator signature is:

  ```python
  def validate_sga_ancillary_resources(
      member: CohortMember,
      projection: SgaAncillaryProjection,
      policy: SgaAncillaryPolicy,
  ) -> SgaAncillaryValidationReport: ...
  ```

- [x] **Step 4: Run focused tests and lint**

  ```bash
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_sga_ancillary_validation.py tests/synthetic/test_sga_ancillary_boundaries.py
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/native/sga_ancillary.py tests/synthetic/test_sga_ancillary_validation.py tests/synthetic/test_sga_ancillary_boundaries.py
  git diff --check
  ```

- [x] **Step 5: Commit**

  ```bash
  git add src/synthetic/native/sga_ancillary.py tests/synthetic/test_sga_ancillary_validation.py tests/synthetic/test_sga_ancillary_boundaries.py
  git commit -m "test: validate SGA ancillary boundaries"
  ```

### Task 3: Document the ordinary-development contract

**Files:**
- Modify: `docs/synthetic-generator.md`
- Modify: `README.md`
- Create: `tests/synthetic/test_sga_ancillary_docs.py`

**Interfaces:**
- Consumes: finalized Task 1/2 public symbol names and fictional constants.
- Produces: the ordinary-development guide section and README roadmap links;
  no runtime or package code changes.

- [x] **Step 1: Write failing documentation tests**

  Assert the guide names every public API type and function, exact fictional
  constants, exact-schema/in-memory/evaluator-only status, birth-state and
  always-empty medication rule, and deferred boundaries; assert README links
  the guide and SGA roadmap slice.

- [x] **Step 2: Implement documentation and tests**

  Add a concise SGA section beside the existing ancillary guidance. State that
  the descriptor has no dedicated gestational-age resource, so fictional lab
  components carry empty values; latent birth/catch-up state is hidden and the
  labels are nonclinical. Keep runtime/package integration, prevalence,
  privacy, clinical, release, real/held-out, and Synthea material deferred.
  Add one concise README roadmap sentence without copying guide text.

- [x] **Step 3: Run focused docs checks**

  ```bash
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_sga_ancillary_docs.py
  git diff --check
  ```

- [x] **Step 4: Commit**

  ```bash
  git add docs/synthetic-generator.md README.md tests/synthetic/test_sga_ancillary_docs.py
  git commit -m "docs: describe SGA ancillary fixtures"
  ```

### Task 4: Review, verify, merge, and push

- [x] Run the complete repository suite, Ruff, schema check, lock check, and
  whitespace check.
- [x] Package an independent broad review from this item's merge base; fix
  every Critical/Important/Minor finding and run scoped rereviews.
- [x] Inspect staged names/stat/diff, excluding untracked `__pycache__`
  directories; commit final checklist metadata only after verification.
- [x] Push `main`, fetch, and verify `HEAD` equals `origin/main`.
- [x] Mark this plan complete only after publication parity exists.
