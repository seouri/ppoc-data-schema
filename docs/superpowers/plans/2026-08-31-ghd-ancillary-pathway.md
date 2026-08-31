# Native GHD Ancillary Pathway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic evaluator-only projection and validator for fictional growth-hormone-deficiency laboratory, medication, problem-list, and referral rows in the repository's exact resource schema.

**Architecture:** A new `synthetic.native.ancillary` module consumes one existing `CohortMember`, an already extracted `ResourceShape`, and a versioned `GhdAncillaryPolicy`. It returns immutable row projections for the four ancillary resources and a status-only validator; it does not change `ObservedResourceBundle`, package export, augmented derivation, or the fail-closed CLI. Visible rows arise from recorded recognition/workup/diagnosis events, while a hidden treatment-start event may supply medication timing only after visible diagnosis.

**Tech Stack:** Python 3.12+, standard-library dataclasses/enums/hashlib/math/re/collections.abc/types, existing synthetic cohort/observation/resource contracts, pytest, Ruff, schema checker.

**Spec:** `docs/superpowers/specs/2026-08-31-ghd-ancillary-pathway-design.md`

## Global Constraints

- Accept only `CohortMember`, `ResourceShape`, and `GhdAncillaryPolicy`; never accept a descriptor path, `Path`, CSV reader, row input, key, report, output destination, or governed data.
- Emit only the four fixed resource names `labs`, `medications`, `problem_list`, and `referrals`; every row uses the supplied descriptor field order and empty strings for missing values.
- Use fixed fictional pathway strings (`SYN-GHD`, `SYN-GHD-IGF1`, `SYN-GHD-STIM`, `Synthetic Pediatric Endocrinology`, `Synthetic growth hormone`) and never label them as ICD, LOINC, RxNorm, or clinical reference values.
- Derive rows only from a valid synthetic observation frame and the existing GHD event trace: recognition creates a referral, workup creates two lab components, diagnosis creates a problem row, and visible diagnosis plus hidden `treatment_start` permits one medication.
- Healthy and non-GHD members return empty ancillary tuples; hidden treatment alone never creates a visible medication.
- Projection is deterministic, nonmutating, and random-free; its visible mapping contains only generated synthetic row values required by the exact schema, while validation reports/reprs/reasons/errors omit patient/visit IDs, row IDs, ages, codes, event payloads, severity, truth hashes, paths, keys, and source values.
- Validator statuses are fixed `PASS`, `FAIL`, and `UNEVALUABLE` with `FAIL > UNEVALUABLE > PASS`; reports expose only fixed check names, statuses, and reason codes.
- The module may import only standard-library helpers, `CohortMember`, native observation/model types, and `ResourceShape`/`ResourceRow`; it must not import calibration, real-data, held-out, privacy, DuckDB, filesystem, CSV, package-export, manifest, or Synthea code.
- Each task ends with focused tests, Ruff for touched files, `git diff --check`, and a scoped commit; never stage caches, generated packages, real data, keys, or reports outside ignored SDD scratch.

---

### Task 1: Add strict policy and projection value objects

**Files:**
- Create: `src/synthetic/native/ancillary.py`
- Create: `tests/synthetic/test_ancillary_models.py`

**Interfaces:**
- Consumes: `ResourceShape`, `ResourceRow`, fixed base-resource names, and aggregate-safe token validation.
- Produces: `GhdAncillaryPolicy`, `AncillaryResourceProjection`, `AncillaryValidationStatus`, `AncillaryCheck`, `AncillaryValidationReport`, fixed constants, and placeholder projection/validator signatures.

- [x] **Step 1: Write failing model tests**

  Build tests for frozen dataclasses, exact status values, safe policy IDs/versions, nonnegative result delay, fixed pathway constants, four-resource row-key order, immutable mappings, exact descriptor field order, empty-string normalization, synthetic patient-ID validation, duplicate field/resource rejection, fixed check/reason registries, report ordering/status precedence, exact mapping keys, and evaluator-safe `repr`. Include inputs with paths, truth terms, booleans, negative ages, non-finite values, arbitrary resource names, and mutable mappings.

- [x] **Step 2: Run the focused tests to verify they fail**

  Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_ancillary_models.py`

  Expected: import or collection failure because `synthetic.native.ancillary` is not present.

- [x] **Step 3: Implement the immutable model layer**

  Define `GHD_ANCILLARY_RESOURCE_NAMES = ("labs", "medications", "problem_list", "referrals")` and fixed fictional strings. Validate `GhdAncillaryPolicy` with `require_aggregate_safe_token` and strict integer rules. Define `AncillaryResourceProjection(patient_id, shape, rows)` so `rows` is a `MappingProxyType` containing exactly those four tuple-valued resource keys; every `ResourceRow` must match `shape.field_names(resource_name)`. Define `AncillaryValidationStatus`, fixed check/reason registries, `AncillaryCheck`, and `AncillaryValidationReport` with checks in `("pathway_scope", "row_schema", "causal_timing", "cross_resource_links", "source_evidence")`, immutable tuples, status precedence, aggregate-only `to_mapping`, and safe `repr`. Add `project_ghd_ancillary_resources(member, shape, policy)` and `validate_ghd_ancillary_resources(member, projection, policy)` stubs that raise only a fixed `AncillaryProjectionUnavailable` assembly error until later tasks.

- [x] **Step 4: Run focused tests and lint**

  Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_ancillary_models.py && UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/native/ancillary.py tests/synthetic/test_ancillary_models.py && git diff --check`

  Expected: all model tests pass and Ruff/whitespace checks are clean.

- [x] **Step 5: Commit**

  ```bash
  git add src/synthetic/native/ancillary.py tests/synthetic/test_ancillary_models.py
  git commit -m "build: add GHD ancillary pathway models"
  ```

### Task 2: Project visible GHD ancillary rows

**Files:**
- Modify: `src/synthetic/native/ancillary.py`
- Create: `tests/synthetic/test_ancillary_projection.py`

**Interfaces:**
- Consumes: Task 1 models, `CohortMember`, `AgeRegimeDisorderTrajectory`, `ClinicalEvent`, `ObservationFrame`, `RecordedEvent`, `RecordedEventKind`, `ResourceShape`, `ResourceRow`, and the existing observation validator.
- Produces: deterministic `project_ghd_ancillary_resources(member, shape, policy) -> AncillaryResourceProjection` with exact-schema rows and no random/I/O boundary.

- [x] **Step 1: Write failing projection tests**

  Use the existing fictional cohort fixtures and checked-in descriptor. Assert that a diagnosed GHD member emits one referral at recognition, two lab components at workup, one unresolved problem row at diagnosis, and a medication only when a hidden `treatment_start` follows a visible diagnosis. Assert fixed fictional values, empty LOINC/optional fields, result-age delay, diagnosis-visit medication link, nullable problem `visit_id`, exact field order, deterministic synthetic IDs, no rows for healthy/non-GHD or unrecognized GHD, no mutation, and byte-equivalent mappings on replay. Cover no-treatment and treatment cases plus valid same-age causal events.

- [x] **Step 2: Run the focused projection tests to verify they fail**

  Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_ancillary_projection.py`

  Expected: failures because the Task 1 projection is still a fixed assembly stub.

- [x] **Step 3: Implement the pure event-to-row projection**

  Validate the member, shape, policy, and `validate_observation_frame(member.frame)` status; failures raise `AncillaryProjectionUnavailable("GHD ancillary projection failed")` without raw details. Require a single synthetic patient identity and a GHD disorder kind; otherwise return four empty tuples. Build a source-point-to-visible-visit lookup from realized `frame.truth.opportunities` exactly as the existing resource projection does, and select the first visible `RecordedEvent` of each fixed kind. Emit full descriptor-ordered rows using these mappings: recognition -> referral (`Synthetic Pediatric Endocrinology`, count `1`); workup -> two `labs` components sharing one deterministic synthetic order ID with components `SYN-GHD-IGF1`/`SYN-GHD-STIM`, no LOINC, `result_flag="Synthetic"`, and result age `event.age_days + policy.result_delay_days`; diagnosis -> unresolved `problem_list` row with `SYN-GHD`; diagnosis plus the first hidden `treatment_start` -> one `medications` row linked to the diagnosis visit with `Internal`, `Synthetic growth hormone`, order age at diagnosis, and start age at treatment. Use a fixed SHA-256-derived opaque synthetic ID helper keyed only by the synthetic patient ID and resource role. Never copy severity, latent kind, hidden event text, or truth objects into rows or mappings.

- [x] **Step 4: Run projection tests and lint**

  Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_ancillary_projection.py tests/synthetic/test_ancillary_models.py && UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/native/ancillary.py tests/synthetic/test_ancillary_*.py && git diff --check`

  Expected: all model/projection tests pass and Ruff/whitespace checks are clean.

- [x] **Step 5: Commit**

  ```bash
  git add src/synthetic/native/ancillary.py tests/synthetic/test_ancillary_projection.py
  git commit -m "feat: project fictional GHD ancillary rows"
  ```

### Task 3: Add causal/link validator and tamper boundaries

**Files:**
- Modify: `src/synthetic/native/ancillary.py`
- Create: `tests/synthetic/test_ancillary_validation.py`
- Create: `tests/synthetic/test_ancillary_boundaries.py`

**Interfaces:**
- Consumes: Task 2 projection output and fixed validation models.
- Produces: `validate_ghd_ancillary_resources(member, projection, policy) -> AncillaryValidationReport` with fixed aggregate checks and redacted malformed-input behavior.

- [ ] **Step 1: Write failing validator and boundary tests**

  Assert clean GHD/healthy projections pass, non-GHD emptiness is accepted, and the validator returns fixed checks for pathway scope, row schema, causal timing, cross-resource links, and source evidence. Tamper IDs, field order, fixed fictional codes/values, event-kind order, duplicate rows, result delay, medication timing, visit links, source-frame status, and hidden-treatment/visible-diagnosis combinations; assert `FAIL` with fixed reason codes and no payload leakage. Add tests for absent/malformed private evidence returning `UNEVALUABLE`, status precedence, no mutation, no raw exception text, and mappings/reprs containing none of the synthetic row identifiers or event payloads. Add an AST/import/signature scanner that rejects governed/filesystem/package/Synthea dependencies, path-like/output arguments, and forbidden lifecycle calls in `synthetic.native.ancillary`.

- [ ] **Step 2: Run validator/boundary tests to verify they fail**

  Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_ancillary_validation.py tests/synthetic/test_ancillary_boundaries.py`

  Expected: validator and boundary assertions fail because the Task 1 validator remains a stub and Task 2 lacks defensive comparison logic.

- [ ] **Step 3: Implement fixed aggregate validation**

  Compare the supplied projection with the pathway expected from the member without serializing row payloads. Validate each row's exact resource/field order, synthetic IDs, patient and visit links, fixed fictional strings, result delay, duplicate/order constraints, and nullable problem-list semantics. Validate source-frame status and causal event ordering; treat absent/malformed private source evidence as `UNEVALUABLE` unless a visible row is independently invalid. Catch evaluator access failures and return fixed redacted checks rather than exception text. Keep report checks aggregate-only and make report status `FAIL` if any check fails, otherwise `UNEVALUABLE` if any check is unevaluable, otherwise `PASS`.

- [ ] **Step 4: Run focused validator/lint checks**

  Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_ancillary_validation.py tests/synthetic/test_ancillary_boundaries.py tests/synthetic/test_ancillary_projection.py tests/synthetic/test_ancillary_models.py && UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/native/ancillary.py tests/synthetic/test_ancillary_*.py && git diff --check`

  Expected: all focused tests pass and Ruff/whitespace checks are clean.

- [ ] **Step 5: Commit**

  ```bash
  git add src/synthetic/native/ancillary.py tests/synthetic/test_ancillary_validation.py tests/synthetic/test_ancillary_boundaries.py
  git commit -m "test: validate GHD ancillary causal boundaries"
  ```

### Task 4: Document the pathway and preserve existing boundaries

**Files:**
- Modify: `docs/synthetic-generator.md`
- Modify: `README.md`
- Create: `tests/synthetic/test_ancillary_docs.py`

**Interfaces:**
- Consumes: Task 3 public API and fixed semantics.
- Produces: user-facing exact-row usage documentation and regression assertions that package/export, derivation, held-out, privacy, CLI, and existing empty-ancillary contracts remain unchanged.

- [ ] **Step 1: Write failing documentation tests**

  Assert the guide names `GhdAncillaryPolicy`, `AncillaryResourceProjection`, `AncillaryValidationReport`, `project_ghd_ancillary_resources`, and `validate_ghd_ancillary_resources`; describes all four resources, fixed fictional values, event-to-row timing, hidden-treatment/visible-diagnosis rule, exact field order, result delay, aggregate statuses, evaluator-only boundary, and every deferred claim. Assert README links the guide and does not present the pathway as package/export, prevalence, clinical, privacy/non-matchability, derivation, release, or Synthea evidence.

- [ ] **Step 2: Run documentation tests to verify they fail**

  Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_ancillary_docs.py`

  Expected: assertions fail before the documentation section is added.

- [ ] **Step 3: Add the guide section and docs assertions**

  Add a concise evaluator-only GHD ancillary section with an exact Python example using a previously generated in-memory `CohortMember` and `ResourceShape`, the four resource-row mappings, validation/status semantics, and explicit fictional-terminology and hidden-truth boundaries. Add one README roadmap paragraph. State that `ObservedResourceBundle`, exact-schema export, augmented derivation, other disorders, held-out validation, privacy/non-matchability, clinical review, task utility, and Synthea remain unchanged/deferred. Keep existing production CLI fail-closed and empty-ancillary tests intact.

- [ ] **Step 4: Run documentation/static/schema checks**

  Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_ancillary_docs.py tests/synthetic/test_ancillary_boundaries.py tests/synthetic/test_cohort_boundaries.py && UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests && python3 schema/build.py --check && git diff --check`

  Expected: focused tests pass, Ruff/schema/whitespace checks are clean, and the existing base-resource boundary suite remains green.

- [ ] **Step 5: Commit**

  ```bash
  git add README.md docs/synthetic-generator.md tests/synthetic/test_ancillary_docs.py
  git commit -m "docs: document GHD ancillary pathway"
  ```

### Task 5: Review and handoff

**Files:**
- Modify: `docs/superpowers/plans/2026-08-31-ghd-ancillary-pathway.md`
- Create: `.superpowers/sdd/2026-08-31-ghd-ancillary-pathway/ledger.md`

- [ ] **Step 1: Run full synthetic and repository checks**

  Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic && UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests && python3 schema/build.py --check && git diff --check`.

- [ ] **Step 2: Dispatch a fresh broad reviewer**

  Review the merge-base-to-HEAD package against every spec/plan acceptance criterion, especially exact field order, visible/hidden event separation, optional treatment semantics, deterministic IDs, causal timing, nullable links, redaction, unchanged bundle/export behavior, and governed/filesystem/package/Synthea boundaries. Record findings under `.superpowers/sdd/2026-08-31-ghd-ancillary-pathway/broad-review.md`.

- [ ] **Step 3: Resolve findings through one implementer-only fix wave and scoped re-review**

  If the broad reviewer identifies any Critical/Important/Minor defect, send complete findings to the relevant original implementer for one scoped fix wave, rerun focused tests, and dispatch one fresh scoped re-review. The controller must not edit implementation files.

- [ ] **Step 4: Finalize plan/ledger metadata and commit**

  Mark completed checkboxes, record all review/fix/re-review and verification evidence in the ignored ledger, run `git diff --check`, and commit only plan metadata.
