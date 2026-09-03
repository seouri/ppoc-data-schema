# Native Celiac Ancillary Pathway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic evaluator-only projection and validator for
fictional celiac-disease referral, serology laboratory, problem-list, and
treatment rows in the exact PPOC schema, without changing existing ancillary
modules or visible runtime/export routes.

**Architecture:** A separate `synthetic.native.celiac_ancillary` module
consumes one typed `CohortMember`, an extracted `ResourceShape`, and a strict
`CeliacAncillaryPolicy`. It owns fictional constants and a distinct
deterministic ID namespace, emits immutable exact-schema rows, and returns a
fixed aggregate-only validation report. It remains evaluator-only and is not
integrated into `development-realistic`, package export, calibration, or
Synthea.

**Tech Stack:** Python 3.12+, standard-library dataclasses/enums/hashlib/re/
collections.abc/types, existing synthetic cohort/model/observation/resource
contracts, pytest, Ruff, schema checker.

**Spec:** `docs/superpowers/specs/2026-09-02-celiac-ancillary-pathway-design.md`

## Global Constraints

- Accept only typed `CohortMember`, `ResourceShape`, and `CeliacAncillaryPolicy`;
  no paths, path-like values, CSV readers, rows, keys, reports, output
  destinations, environment input, or governed data.
- Emit only `labs`, `medications`, `problem_list`, and `referrals` in fixed
  order; every row uses supplied descriptor field order and empty strings for
  missing values.
- Use only fictional constants: `SYN-CELIAC-DISEASE`,
  `SYN-CELIAC-TTG-IGA`, `SYN-CELIAC-TOTAL-IGA`,
  `Synthetic Pediatric Gastroenterology`, `Synthetic gluten-free intervention`,
  `Internal`, and `Synthetic`; make no ICD/LOINC/RxNorm claim.
- A valid target frame maps visible recognition/workup/diagnosis to one
  referral/two labs/problem and maps a hidden `treatment_start` to one
  treatment row only when an observed diagnosis is present and the start is not
  earlier than that diagnosis. Hidden/unrecorded events never create rows.
- Healthy, GHD, hypothyroidism, SGA, Turner, undernutrition, excess-weight, and
  all other members return empty tuples; no emitted row contains or derives
  `obesity_flag`.
- Projection is deterministic, nonmutating, random-free, and source-point/
  visit linked. Errors, reprs, and reports omit IDs, ages, codes, values,
  events, severity, truth hashes, paths, keys, and source evidence.
- Validator statuses are fixed `PASS`, `FAIL`, and `UNEVALUABLE` with
  `FAIL > UNEVALUABLE > PASS`; visible event count/age rules run before
  private-source validation.
- The module may import only standard-library helpers and native cohort/model/
  observation/resource types; static tests reject calibration, real-data,
  held-out, privacy, DuckDB, filesystem, CSV, package/export, manifest,
  subprocess, and Synthea coupling.
- Each task ends with focused tests, Ruff, `git diff --check`, and a scoped
  commit; never stage generated caches or reports.

### Task 1: Add strict models and deterministic projection

**Files:**
- Create: `src/synthetic/native/celiac_ancillary.py`
- Create: `tests/synthetic/test_celiac_ancillary_models.py`
- Create: `tests/synthetic/test_celiac_ancillary_projection.py`

- [x] **Step 1: Write failing model and projection tests**

  Use fictional fixtures and the checked-in descriptor. Cover frozen models,
  safe tokens, exact resource order, immutable mappings, descriptor field order
  and types, empty-string conventions, constants, namespaced IDs, target and
  non-target emptiness, every visible event combination, optional/censored
  treatment, same-age events, nullable problem links, deterministic replay, no
  mutation, and fixed redacted errors.

- [x] **Step 2: Run focused tests to verify they fail**

  ```bash
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_celiac_ancillary_models.py tests/synthetic/test_celiac_ancillary_projection.py
  ```

- [x] **Step 3: Implement models and projection**

  Define a separate frozen policy, projection, and redacted exception. Validate
  observation frame/member truth binding as the reviewed ancillary paths do.
  For target members, map first visible recognition/workup/diagnosis events to
  fixed fictional rows and map eligible hidden treatment to one treatment row;
  suppress it if diagnosis is absent or later than the hidden start. Build
  every row in supplied descriptor order using a distinct deterministic
  namespace. Do not import or modify existing ancillary modules, runtime, or
  exporter.

- [x] **Step 4: Run focused tests and lint**

  ```bash
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_celiac_ancillary_models.py tests/synthetic/test_celiac_ancillary_projection.py
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/native/celiac_ancillary.py tests/synthetic/test_celiac_ancillary_models.py tests/synthetic/test_celiac_ancillary_projection.py
  git diff --check
  ```

- [x] **Step 5: Commit**

  ```bash
  git add src/synthetic/native/celiac_ancillary.py tests/synthetic/test_celiac_ancillary_models.py tests/synthetic/test_celiac_ancillary_projection.py
  git commit -m "build: add celiac ancillary projection"
  ```

### Task 2: Add aggregate validator and static boundary tests

**Files:**
- Modify: `src/synthetic/native/celiac_ancillary.py`
- Create: `tests/synthetic/test_celiac_ancillary_validation.py`
- Create: `tests/synthetic/test_celiac_ancillary_boundaries.py`

- [x] **Step 1: Write failing validator and boundary tests**

  Cover fixed order/status precedence, valid target/non-target reports, wrong
  constants/IDs/types, duplicate/count violations, result delay,
  treatment-before-diagnosis, broken patient/visit links, invalid/missing source
  evidence, immutable/redacted reports, forbidden imports/signatures, no
  I/O/randomness, no `obesity_flag`, and visible-event count/age failures with
  missing or invalid truth.

- [x] **Step 2: Run focused tests to verify they fail**

  ```bash
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_celiac_ancillary_validation.py tests/synthetic/test_celiac_ancillary_boundaries.py
  ```

- [x] **Step 3: Implement the validator**

  Independently validate visible row structure, links to actual frame visits,
  treatment gating, and expected counts/ages derived from valid visible events
  before invoking private-source validation. Derive typed hidden treatment
  eligibility before that validation, and classify a valid-frame/member truth
  binding mismatch as `FAIL/SOURCE_EVIDENCE_INVALID`. Compare to deterministic
  expected projection only after source evidence and binding pass. Return fixed
  redacted reasons; missing private evidence is `UNEVALUABLE` only when no
  visible violation is provable.

- [x] **Step 4: Run focused tests and lint**

  ```bash
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_celiac_ancillary_validation.py tests/synthetic/test_celiac_ancillary_boundaries.py
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/native/celiac_ancillary.py tests/synthetic/test_celiac_ancillary_validation.py tests/synthetic/test_celiac_ancillary_boundaries.py
  git diff --check
  ```

- [x] **Step 5: Commit**

  ```bash
  git add src/synthetic/native/celiac_ancillary.py tests/synthetic/test_celiac_ancillary_validation.py tests/synthetic/test_celiac_ancillary_boundaries.py
  git commit -m "test: validate celiac ancillary boundaries"
  ```

### Task 3: Document the ordinary-development contract

**Files:**
- Modify: `docs/synthetic-generator.md`
- Modify: `README.md`
- Create: `tests/synthetic/test_celiac_ancillary_docs.py`

- [x] **Step 1: Write failing documentation tests**

  Assert the guide names all public API types including `CeliacAncillaryCheck`,
  exact fictional constants, exact-schema/in-memory evaluator-only status,
  eligible treatment rule, and deferred boundaries; assert README links the
  guide and celiac roadmap slice.

- [x] **Step 2: Implement documentation and tests**

  Add a concise section near the existing ancillary guidance. State that latent
  celiac disease is not a clinical code claim and visible descendants are
  fictional; keep package integration, prevalence, privacy, clinical, release,
  and Synthea material deferred. Add one concise README roadmap sentence and no
  copied guide text.

- [x] **Step 3: Run focused docs checks**

  ```bash
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_celiac_ancillary_docs.py
  git diff --check
  ```

- [x] **Step 4: Commit**

  ```bash
  git add docs/synthetic-generator.md README.md tests/synthetic/test_celiac_ancillary_docs.py
  git commit -m "docs: describe celiac ancillary fixtures"
  ```

### Task 4: Review, verify, merge, and push

- [x] Run the complete repository suite, Ruff, schema check, lock check, and
  whitespace check.
- [x] Package an independent broad review from the roadmap item's merge base;
  fix every Critical/Important/Minor finding and run a scoped rereview for each
  fix wave.
- [x] Inspect staged names/stat/diff, excluding untracked `__pycache__`
  directories; commit final checklist metadata only after verification.
- [x] Push `main`, fetch, and verify `HEAD` equals `origin/main`.
- [x] Mark this plan complete only after publication parity exists.
