# Native Cohort Fidelity/Profile Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an evaluator-only, aggregate-safe report that profiles visible demographics, separate latent/observable/recorded layers, age-window growth summaries, and observation coverage for a generated native cohort.

**Architecture:** A new `synthetic.cohort_validation` module owns strict policy, comparison, and report models plus a pure `validate_native_cohort` evaluator. It consumes only the existing `NativeCohort` and an immutable in-memory policy; it does not import governed inputs, read or write paths, alter cohorts, or couple to held-out/package/privacy commands.

**Tech Stack:** Python 3.12+, standard-library dataclasses/enums/math/collections, existing synthetic cohort/models/native contracts, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-08-31-cohort-fidelity-profile-design.md`

## Global Constraints

- Consume only `NativeCohort` and `CohortValidationPolicy`; never accept paths, keys, descriptors, artifacts, reports, rows, DuckDB connections, or hidden truth as inputs.
- Keep latent module, observable phenotype, and recorded recognition/workup/diagnosis evidence in separately named aggregate checks; never equate healthy module membership with `healthy_flag`.
- Apply the same blank/nonresponse-to-visible-`Unknown` rule as native cohort generation and never disclose unrecoverable source categories as if they were visible values.
- Use fixed `PASS`/`FAIL`/`UNEVALUABLE` status semantics; underpowered evidence is not a pass, and no label allocation or mutation is permitted.
- Reports, mappings, reprs, and exceptions must not expose patient/visit IDs, event payloads, severity, paths, calibration supports/denominators, keys, truth hashes, or latent objects.
- Do not import `synthetic.calibrate`, `synthetic.calibration_input`, `synthetic.heldout_validate`, `synthetic.privacy_audit`, DuckDB, package writers, or output lifecycle helpers.
- Every task ends with focused tests, Ruff for touched files, `git diff --check`, and a scoped commit. Do not stage caches, real data, keys, or generated artifacts.

---

### Task 1: Add strict policy, comparison, and report models

**Files:**
- Create: `src/synthetic/cohort_validation.py`
- Create: `tests/synthetic/test_cohort_validation_models.py`

**Interfaces:**
- Consumes: `DisorderKind`, `NativeCohort`, `CalibrationSamplingProfile`, and `require_aggregate_safe_token` from existing modules.
- Produces: `CohortValidationStatus`, `CohortValidationPolicy`, `CohortComparison`, `CohortValidationReport`, fixed registries/constants, and a placeholder `validate_native_cohort` that raises a clear assembly error until Task 2.

- [x] **Step 1: Write the failing model tests**

  Test frozen dataclasses, exact enum values, safe policy IDs/versions, positive integer minima, finite nonnegative tolerances, canonical growth keys, sorted non-overlapping safe age windows, exact comparison layers/statuses/reason codes, null fields for `UNEVALUABLE`, targeted difference arithmetic, status-only aggregate diagnostics with null target fields, support/denominator constraints, fixed report comparison ordering, exact `to_mapping()` keys, and evaluator-safe `repr`. Include rejection of IDs, paths, truth terms, unknown keys, duplicate windows, booleans, NaN/infinite values, and mutable mappings.

- [x] **Step 2: Run the focused tests to verify they fail**

  Run: `uv run pytest -q tests/synthetic/test_cohort_validation_models.py`

  Expected: collection or import failure because `synthetic.cohort_validation` is not present.

- [x] **Step 3: Implement the immutable model layer**

  Define fixed status/layer/reason registries. Validate policy fields in `__post_init__`, freeze mappings with `MappingProxyType`, normalize age-window values into a canonical immutable representation, and reject unsupported growth keys. Define `CohortComparison` so `UNEVALUABLE` requires all numeric fields null; targeted `PASS`/`FAIL` comparisons require finite observed/target/difference/tolerance with exact `abs(observed-target)` arithmetic; status-only aggregate diagnostics permit a finite observed value with null target/difference/tolerance. Define `CohortValidationReport` with fixed version, profile/seed validation, sorted canonical comparisons, and aggregate-only `to_mapping()`/`repr()` methods. Add a temporary `validate_native_cohort` signature that raises `NotImplementedError` with no sensitive detail.

- [x] **Step 4: Run focused tests and lint**

  Run: `uv run pytest -q tests/synthetic/test_cohort_validation_models.py && uv run ruff check src/synthetic/cohort_validation.py tests/synthetic/test_cohort_validation_models.py`

  Expected: all model tests pass and Ruff reports no issues.

- [x] **Step 5: Commit**

  ```bash
  git add src/synthetic/cohort_validation.py tests/synthetic/test_cohort_validation_models.py
  git commit -m "build: add cohort validation models"
  ```

### Task 2: Implement aggregate demographic and layer checks

**Files:**
- Modify: `src/synthetic/cohort_validation.py`
- Create: `tests/synthetic/test_cohort_validation_layers.py`

**Interfaces:**
- Consumes: Task 1 models, `NativeCohort`, `CohortMember`, calibration profile weights, `DisorderKind`, `ClinicalEvent`, and `RecordedEventKind`.
- Produces: a working `validate_native_cohort(cohort, policy) -> CohortValidationReport` with cohort-size, visible-demographic, latent-module, observable-phenotype, and recorded-layer comparisons.

- [ ] **Step 1: Write failing layer-evaluation tests**

  Build deterministic fictional cohorts from existing fixtures. Assert projected `Unknown` target merging, canonical sex/ethnicity/race checks, tolerance pass/fail, minimum support `UNEVALUABLE`, cohort-size `UNEVALUABLE`, latent module counts, observable phenotype event counts, recorded recognition/workup/diagnosis counts, and the explicit absence of real healthy/growth-diagnosis targets. Assert no mutation and deterministic mapping.

- [ ] **Step 2: Run the focused tests to verify they fail**

  Run: `uv run pytest -q tests/synthetic/test_cohort_validation_layers.py`

  Expected: failures because the evaluator is still the Task 1 placeholder.

- [ ] **Step 3: Implement the pure aggregate evaluators**

  Validate the `NativeCohort`/policy types, materialize the immutable member tuple, and create fixed comparisons in canonical order. Count visible demographics from `member.demographics`, project aggregate source categories exactly as generation does, normalize category targets, and apply policy support/tolerance. Count trajectory disorder kinds and event-layer evidence without serializing member IDs. Treat layer diagnostics as status-only with null target/difference/tolerance and minimum evidence support. Wrap malformed evaluator object access into fixed aggregate comparisons or a fixed report status; never rethrow raw injected exception text.

- [ ] **Step 4: Run focused tests and lint**

  Run: `uv run pytest -q tests/synthetic/test_cohort_validation_layers.py tests/synthetic/test_cohort_validation_models.py && uv run ruff check src/synthetic/cohort_validation.py tests/synthetic/test_cohort_validation_layers.py tests/synthetic/test_cohort_validation_models.py`

  Expected: all focused tests pass and Ruff reports no issues.

- [ ] **Step 5: Commit**

  ```bash
  git add src/synthetic/cohort_validation.py tests/synthetic/test_cohort_validation_layers.py
  git commit -m "feat: profile cohort demographic layers"
  ```

### Task 3: Add age-window growth and observation coverage checks

**Files:**
- Modify: `src/synthetic/cohort_validation.py`
- Create: `tests/synthetic/test_cohort_validation_growth.py`
- Create: `tests/synthetic/test_cohort_validation_boundaries.py`

**Interfaces:**
- Consumes: Task 2 evaluator and models, `AgeRegimePoint`, `ObservationFrame`, `ObservedVisit`, and existing cohort fixtures.
- Produces: deterministic growth means, bounded velocity checks, coverage checks, overall status aggregation, redacted malformed-input behavior, and static boundary coverage.

- [ ] **Step 1: Write failing growth, coverage, and boundary tests**

  Assert each configured age window/metric mean, omission of the first `None` velocity, finite bound failure, insufficient support, no-visit/no-event coverage, `FAIL` for malformed typed members, and `UNEVALUABLE` for insufficient evidence. Add AST/import assertions forbidding governed imports, DuckDB, `Path` parameters, file/output calls, package writers, hidden-report arguments, and sensitive tokens in public output. Assert report ordering, overall status precedence, mapping/repr redaction, and no cohort mutation.

- [ ] **Step 2: Run focused tests to verify they fail**

  Run: `uv run pytest -q tests/synthetic/test_cohort_validation_growth.py tests/synthetic/test_cohort_validation_boundaries.py`

  Expected: growth/coverage and boundary assertions fail because the evaluator has no trajectory checks or boundary-safe implementation yet.

- [ ] **Step 3: Implement age-window and coverage evaluators**

  Iterate only evaluator-held trajectory points and observation frames. For each required window and canonical metric, collect finite values, calculate an arithmetic mean, apply minimum support and absolute bound, and emit a fixed comparison name. Add fixed `coverage.cohort_size`, `coverage.members_with_observation`, and `coverage.members_with_event` checks for cohort size, visited members, and members with recorded events; validate patient identity/age ordering without exposing offending values. Aggregate statuses as `FAIL` > `UNEVALUABLE` > `PASS`. Keep the module pure and avoid imports or calls that cross governed/filesystem/package boundaries.

- [ ] **Step 4: Run focused tests and lint**

  Run: `uv run pytest -q tests/synthetic/test_cohort_validation_growth.py tests/synthetic/test_cohort_validation_boundaries.py tests/synthetic/test_cohort_validation_layers.py tests/synthetic/test_cohort_validation_models.py && uv run ruff check src/synthetic/cohort_validation.py tests/synthetic/test_cohort_validation_growth.py tests/synthetic/test_cohort_validation_boundaries.py`

  Expected: all focused tests pass and Ruff reports no issues.

- [ ] **Step 5: Commit**

  ```bash
  git add src/synthetic/cohort_validation.py tests/synthetic/test_cohort_validation_growth.py tests/synthetic/test_cohort_validation_boundaries.py
  git commit -m "feat: add cohort growth profile checks"
  ```

### Task 4: Document and integrate the profile-report boundary

**Files:**
- Modify: `docs/synthetic-generator.md`
- Modify: `README.md`
- Modify: `tests/synthetic/test_cohort_boundaries.py`
- Create: `tests/synthetic/test_cohort_validation_docs.py`

**Interfaces:**
- Consumes: Task 3 public API and fixed semantics.
- Produces: concise user documentation, explicit non-claim/deferred-gate language, and regression assertions that the existing generator/held-out/privacy/package boundaries remain unchanged.

- [ ] **Step 1: Write failing documentation/boundary tests**

  Assert the guide and README name `validate_native_cohort`, policy/report statuses, separate latent/observable/recorded layers, blank-to-`Unknown` projection, growth summaries, and explicit non-claims for held-out, prevalence, clinical, privacy, non-matchability, package, and Synthea evidence. Assert the new module remains absent from governed runtime imports and the existing production CLI remains fail closed.

- [ ] **Step 2: Run focused tests to verify they fail**

  Run: `uv run pytest -q tests/synthetic/test_cohort_validation_docs.py tests/synthetic/test_cohort_boundaries.py`

  Expected: documentation assertions fail before the section is written.

- [ ] **Step 3: Add the guide section and boundary regression assertions**

  Document the exact Python API, canonical metrics, status semantics, evaluator-only nature, and example usage with a previously generated in-memory cohort. Add a short README roadmap paragraph linking to the guide. Extend boundary tests to scan/import the new module and assert no forbidden governed/filesystem/package coupling. Keep paragraphs on one physical Markdown line where repository conventions require it.

- [ ] **Step 4: Run focused tests, lint, and schema/whitespace checks**

  Run: `uv run pytest -q tests/synthetic/test_cohort_validation_docs.py tests/synthetic/test_cohort_boundaries.py && uv run ruff check src/synthetic/cohort_validation.py tests/synthetic/test_cohort_validation_*.py && python3 schema/build.py --check && git diff --check`

  Expected: all focused tests pass, Ruff passes, schema validation reports the checked-in resources, and whitespace check is clean.

- [ ] **Step 5: Commit**

  ```bash
  git add README.md docs/synthetic-generator.md tests/synthetic/test_cohort_boundaries.py tests/synthetic/test_cohort_validation_docs.py
  git commit -m "docs: document cohort fidelity profile"
  ```

### Task 5: Review and handoff

**Files:**
- Modify: `docs/superpowers/plans/2026-08-31-cohort-fidelity-profile.md`
- Create: `.superpowers/sdd/2026-08-31-cohort-fidelity-profile/ledger.md`

- [ ] **Step 1: Run the full focused synthetic suite and static checks**

  Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic && uv run ruff check src tests && python3 schema/build.py --check && git diff --check`.

- [ ] **Step 2: Dispatch a fresh broad reviewer**

  Review the merge-base-to-HEAD package against every spec/plan acceptance criterion, hidden truth/redaction behavior, status math, blank-category semantics, boundary imports, and regression risk. Record the report under `.superpowers/sdd/2026-08-31-cohort-fidelity-profile/broad-review.md`.

- [ ] **Step 3: Resolve findings through one implementer-only fix wave and scoped re-review**

  If the reviewer finds Critical/Important/Minor defects, send the complete findings to the original task implementer for a scoped fix, run the focused regression tests, and dispatch one fresh scoped re-review. Do not edit implementation files in the controller.

- [ ] **Step 4: Finalize plan/ledger metadata and commit**

  Mark completed checkboxes, record tests/review verdicts in the ignored ledger, run `git diff --check`, and commit only plan metadata and reviewed documentation if needed.
