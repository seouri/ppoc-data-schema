# Native Undernutrition Ancillary Pathway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic evaluator-only projection and validator for
fictional undernutrition recognition/referral, nutrition workup, unresolved
diagnosis, and causally gated nutrition-supplement rows in the exact PPOC
schema, without changing existing modules, visible runtime, or package export.

**Architecture:** A separate `synthetic.native.undernutrition_ancillary`
module consumes one typed `CohortMember`, an extracted `ResourceShape`, and a
strict `UndernutritionAncillaryPolicy`. It owns fictional constants and an
independent deterministic ID namespace, emits immutable exact-schema rows, and
returns a fixed aggregate-only validation report. Hidden undernutrition
trajectory and treatment state remain evaluator-only; the module is not
integrated into `development-realistic`, package export, calibration, or
Synthea.

**Tech Stack:** Python 3.12+, standard-library dataclasses/enums/hashlib/re/
collections.abc/types, existing synthetic cohort/model/observation/resource
contracts, pytest, Ruff, schema checker.

**Spec:** `docs/superpowers/specs/2026-09-02-undernutrition-ancillary-pathway-design.md`

## Global Constraints

- Accept only typed `CohortMember`, `ResourceShape`, and
  `UndernutritionAncillaryPolicy`; no paths, path-like values, CSV readers,
  rows, keys, reports, output destinations, environment input, or governed
  data.
- Emit only `labs`, `medications`, `problem_list`, and `referrals` in fixed
  order; every row follows supplied descriptor field order and empty strings
  for missing values.
- Use only the fictional constants `SYN-UNDERNUTRITION`,
  `SYN-UNDERNUTRITION-WEIGHT-EVIDENCE`,
  `SYN-UNDERNUTRITION-HEIGHT-EVIDENCE`, `Synthetic Pediatric Nutrition`,
  `Synthetic nutrition-supplement intervention`, `Internal`, and `Synthetic`
  under the `undernutrition-ancillary-id-v1` namespace; make no ICD, LOINC,
  RxNorm, or clinical-value claim.
- A valid target frame maps visible recognition/workup/diagnosis to one
  referral/two labs/problem and maps a private `treatment_start` to one
  fictional nutrition-supplement treatment row only when an observed diagnosis
  is present and the start is not earlier than that diagnosis. Hidden,
  censored, or unrecorded events never create rows.
- Healthy, GHD, hypothyroidism, celiac, SGA, Turner, excess-weight, familial
  short stature, constitutional delay, and every other non-target member return
  four empty tuples; no emitted row contains or derives `obesity_flag`.
- Projection is deterministic, nonmutating, random-free, and source-point/
  visit linked. Errors, reprs, and reports omit IDs, ages, codes, values,
  events, severity, truth hashes, paths, keys, and source evidence.
- Validator statuses are fixed `PASS`, `FAIL`, and `UNEVALUABLE` with
  `FAIL > UNEVALUABLE > PASS`; visible event/count/age rules run before
  private-source validation.
- The module may import only standard-library helpers and native cohort/model/
  observation/resource types; static tests reject calibration, real-data,
  held-out, privacy, DuckDB, filesystem, CSV, package/export, manifest,
  subprocess, environment, network, randomness, and Synthea coupling.
- Each task ends with focused tests, Ruff, `git diff --check`, and a scoped
  commit; never stage generated caches, bytecode, SDD briefs, or reports.

### Task 1: Add strict models and deterministic projection

**Files:**

- Create: `src/synthetic/native/undernutrition_ancillary.py`
- Create: `tests/synthetic/test_undernutrition_ancillary_models.py`
- Create: `tests/synthetic/test_undernutrition_ancillary_projection.py`

**Interfaces:**

- Consumes: typed `CohortMember`, `AgeRegimeDisorderTrajectory`,
  `ClinicalEvent`, `RecordedEvent`, `RecordedEventKind`, `ResourceShape`, and
  `ResourceRow`, with target kind
  `DisorderKind.UNDERNUTRITION` from `UndernutritionModule`.
- Produces: frozen `UndernutritionAncillaryPolicy` and
  `UndernutritionAncillaryProjection`, fixed fictional constants,
  `UndernutritionAncillaryProjectionUnavailable`, and
  `project_undernutrition_ancillary_resources(member, shape, policy)` for Task
  2 and the documentation task.

- [ ] **Step 1: Write the failing model and projection tests**

  Build only fictional in-memory fixtures from `tests/synthetic/fakes.py` and
  the checked-in descriptor mapping. Assert these exact public constants and
  tuple values:

  ```python
  UNDERNUTRITION_ANCILLARY_RESOURCE_NAMES == (
      "labs", "medications", "problem_list", "referrals"
  )
  UNDERNUTRITION_DIAGNOSIS_CODE == "SYN-UNDERNUTRITION"
  UNDERNUTRITION_WEIGHT_COMPONENT == "SYN-UNDERNUTRITION-WEIGHT-EVIDENCE"
  UNDERNUTRITION_HEIGHT_COMPONENT == "SYN-UNDERNUTRITION-HEIGHT-EVIDENCE"
  UNDERNUTRITION_LAB_COMPONENT_NAMES == (
      UNDERNUTRITION_WEIGHT_COMPONENT,
      UNDERNUTRITION_HEIGHT_COMPONENT,
  )
  UNDERNUTRITION_LAB_RESULT_FLAG == "Synthetic"
  UNDERNUTRITION_REFERRAL_SPECIALTY == "Synthetic Pediatric Nutrition"
  UNDERNUTRITION_MEDICATION_NAME == (
      "Synthetic nutrition-supplement intervention"
  )
  UNDERNUTRITION_MEDICATION_RECORD_TYPE == "Internal"
  ```

  Cover frozen policies and projections, aggregate-safe policy tokens, the
  exact four-resource order, immutable row mappings, current descriptor field
  order and scalar types, empty-string conventions, namespaced deterministic
  IDs, and redacted projection errors. Exercise a target member with no
  visible events, recognition only, recognition plus workup, and all visible
  events; exercise same-age recognition/workup/diagnosis events and a
  zero-severity target with no visible descendants. Assert that recognition
  yields one referral, workup yields two component rows sharing one order ID,
  diagnosis yields one unresolved problem, and an eligible private treatment
  start yields one medication linked to the diagnosis visit. Assert that
  hidden onset, severity, treatment response/nonresponse, and `obesity_flag`
  never enter rows. Exercise treated and untreated `UndernutritionModule`
  states, a private treatment start before an observed diagnosis, and a
  treatment start with a censored diagnosis; the last two cases must suppress
  medication rows.

  Also test healthy, GHD, hypothyroidism, celiac, SGA, Turner, excess weight,
  familial short stature, constitutional delay, and another non-target kind
  for four empty tuples. Repeat identical typed inputs for equal mappings,
  snapshot member/frame/shape/policy for no mutation, and assert no generated
  row ID equals or includes an input visit identifier. The only identifier
  copied into an emitted row is the required synthetic patient link.

- [ ] **Step 2: Run focused tests to verify they fail**

  ```bash
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_undernutrition_ancillary_models.py tests/synthetic/test_undernutrition_ancillary_projection.py
  ```

  Expected: collection fails because the undernutrition ancillary module and
  its public models do not yet exist.

- [ ] **Step 3: Implement strict models and projection**

  Add the following public signature and frozen models:

  ```text
  project_undernutrition_ancillary_resources(
      member: CohortMember,
      shape: ResourceShape,
      policy: UndernutritionAncillaryPolicy,
  ) -> UndernutritionAncillaryProjection
  ```

  Define `UndernutritionAncillaryPolicy(policy_id, policy_version,
  result_delay_days)` with aggregate-safe ASCII token validation and a
  nonnegative integer delay. Define
  `UndernutritionAncillaryProjection(patient_id, shape, rows)` with frozen
  fields, fixed four-resource mapping order, tuple rows, exact field order,
  synthetic patient identity, and a redacted
  `UndernutritionAncillaryProjectionUnavailable` boundary.

  Before assembling a target projection, require a passing
  `validate_observation_frame`, a synthetic patient identity, a nonempty
  `AgeRegimeDisorderTrajectory`, a trajectory equal to
  `frame.truth.latent_trajectory`, trajectory events equal to
  `frame.truth.source_events`, and realized opportunities paired one-to-one
  with visible visits. Resolve each visible event's `opportunity_index` through
  its realized source-point opportunity to the corresponding visible visit;
  do not match by age. Use the first `RecordedEvent` of each event kind after
  the frame passes validation. Return four empty tuples for every valid
  non-target member and for a zero-severity target with no visible events.

  For `DisorderKind.UNDERNUTRITION`, assemble only these rows: recognition
  creates one referral with the exact fictional specialty and one requested
  visit; workup creates two labs with line numbers 1 and 2, the exact
  weight-evidence/height-evidence component names, one shared deterministic
  `lab_order_id`, the in-memory `Synthetic` marker, and empty procedure, LOINC,
  and result fields; diagnosis creates one unresolved problem with the exact
  diagnosis token and no visit field; and diagnosis plus a private trajectory
  `ClinicalEvent(event_type="treatment_start")` at or after the diagnosis age
  creates one medication linked to the diagnosis visit, with order age at
  diagnosis, start age at the private treatment event, empty end age,
  `Internal` record type, and the fictional nutrition-supplement name.
  Suppress medication when diagnosis is absent, censored, or later than the
  private treatment start. Do not emit a treatment response/nonresponse row.

  Build every row by iterating `shape.field_names(resource_name)`, using empty
  strings for unrepresented fields. Derive opaque IDs from only
  `undernutrition-ancillary-id-v1`, the synthetic patient ID, and a fixed role;
  use one `lab-order` ID for both lab components. Catch malformed typed inputs
  behind one fixed redacted exception without exposing values, source state,
  paths, or keys. Do not modify any existing module, runtime, exporter,
  descriptor, or Synthea code.

- [ ] **Step 4: Run focused tests and lint**

  ```bash
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_undernutrition_ancillary_models.py tests/synthetic/test_undernutrition_ancillary_projection.py
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/native/undernutrition_ancillary.py tests/synthetic/test_undernutrition_ancillary_models.py tests/synthetic/test_undernutrition_ancillary_projection.py
  git diff --check
  ```

- [ ] **Step 5: Commit the projection task**

  ```bash
  git add src/synthetic/native/undernutrition_ancillary.py tests/synthetic/test_undernutrition_ancillary_models.py tests/synthetic/test_undernutrition_ancillary_projection.py
  git commit -m "build: add undernutrition ancillary projection"
  ```

### Task 2: Add aggregate validation and static boundary tests

**Files:**

- Modify: `src/synthetic/native/undernutrition_ancillary.py`
- Create: `tests/synthetic/test_undernutrition_ancillary_validation.py`
- Create: `tests/synthetic/test_undernutrition_ancillary_boundaries.py`

**Interfaces:**

- Consumes: Task 1's immutable projection, policy, exact row contract,
  fictional constants, and source-point/visit mapping.
- Produces: `UNDERNUTRITION_ANCILLARY_CHECK_NAMES`, the fixed reason-code
  vocabulary, `UndernutritionAncillaryValidationStatus`,
  `UndernutritionAncillaryCheck`,
  `UndernutritionAncillaryValidationReport`, and
  `validate_undernutrition_ancillary_resources(member, projection, policy)`
  for Task 3.

- [ ] **Step 1: Write failing validator and boundary tests**

  Assert the exact check order:

  ```python
  UNDERNUTRITION_ANCILLARY_CHECK_NAMES == (
      "pathway_scope",
      "row_schema",
      "causal_timing",
      "cross_resource_links",
      "source_evidence",
  )
  ```

  Cover passing target/non-target reports, `PASS`/`FAIL`/`UNEVALUABLE`
  statuses, fixed check counts, immutable reports, and
  `FAIL > UNEVALUABLE > PASS` precedence. Mutate only fictional in-memory
  copies to test wrong diagnosis, lab components, result marker, specialty,
  medication, record type, IDs, scalar types, field order, empty values,
  duplicate rows, and wrong resource counts. Inject a medication into a
  target with no eligible private treatment and into a non-target projection.
  Test visible recognition/workup/diagnosis age mismatches, reversed phases,
  undelayed or reversed lab results, treatment before diagnosis, bad result
  line numbers, mismatched patient IDs, non-synthetic IDs, and referral/lab/
  medication links to visits absent from the actual frame. Confirm the problem
  row retains the descriptor's no-visit-key semantics.

  Test source-point-specific linkage: a row linked to a real frame visit that
  belongs to a different opportunity must fail even if its age equals the
  event age. Test missing and malformed private truth, valid-frame/member
  trajectory mismatch, invalid source-event binding, and visible violations
  combined with unavailable source evidence. Visible violations remain
  `FAIL`, while source-only absence is `UNEVALUABLE`. Assert that reports and
  reprs contain only fixed names/statuses/reasons and no patient, visit, row,
  age, code, value, hidden-event, path, key, or source text.

  Parse the module with `ast` and reject imports or calls related to
  calibration, real/held-out data, privacy, DuckDB, filesystem/path APIs,
  CSV, package/export, manifests, subprocess, environment, network,
  randomness, Synthea, or `obesity_flag`. Reject public signatures that take
  paths, rows, keys, reports, output destinations, or descriptor mappings.

- [ ] **Step 2: Run focused validator tests to verify they fail**

  ```bash
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_undernutrition_ancillary_validation.py tests/synthetic/test_undernutrition_ancillary_boundaries.py
  ```

  Expected: collection or assertions fail because the validator and static
  boundary regression tests are not implemented.

- [ ] **Step 3: Implement the fixed aggregate validator**

  Add the following public signature:

  ```text
  validate_undernutrition_ancillary_resources(
      member: CohortMember,
      projection: UndernutritionAncillaryProjection,
      policy: UndernutritionAncillaryPolicy,
  ) -> UndernutritionAncillaryValidationReport
  ```

  Define frozen `UndernutritionAncillaryCheck` and
  `UndernutritionAncillaryValidationReport` values with fixed check names,
  fixed reason codes, immutable status counts, and aggregate-only mappings.
  Use exactly `PASS`, `FAIL`, and `UNEVALUABLE`, with
  `FAIL > UNEVALUABLE > PASS`. Validate visible row structure and descriptor
  order, synthetic patient/row IDs, constants, scalar types, row counts,
  empty conventions, actual frame visits, event ages, result delay, phase
  order, and treatment gating before consulting private source validation.

  A visible workup always expects exactly two labs in one order; a visible
  recognition expects one referral; a visible diagnosis expects one problem;
  and an eligible private treatment start plus visible diagnosis expects one
  medication. The medication tuple is empty for every non-target member and
  for every target without that gate. Extract the typed treatment start before
  source validation. If that private value is malformed or unavailable, leave
  its expected count unknown and report source unavailability only when no
  independently visible failure exists; a visible medication without a
  visible diagnosis remains a visible scope failure.

  Run `validate_observation_frame(member.frame)` after all visible checks.
  Classify invalid observation/source binding as
  `FAIL/SOURCE_EVIDENCE_INVALID` and absent or malformed private evidence as
  `UNEVALUABLE/SOURCE_EVIDENCE_UNAVAILABLE` only when no visible failure is
  already established. The binding must require the member trajectory to
  equal `frame.truth.latent_trajectory`, member events to equal
  `frame.truth.source_events`, matching synthetic patient identities, and a
  nonempty physiology. After source and binding pass, compare source-point
  event links and the deterministic expected projection. Never include source
  objects or row payloads in a report.

- [ ] **Step 4: Run focused validation tests and lint**

  ```bash
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_undernutrition_ancillary_validation.py tests/synthetic/test_undernutrition_ancillary_boundaries.py
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/native/undernutrition_ancillary.py tests/synthetic/test_undernutrition_ancillary_validation.py tests/synthetic/test_undernutrition_ancillary_boundaries.py
  git diff --check
  ```

- [ ] **Step 5: Commit the validator task**

  ```bash
  git add src/synthetic/native/undernutrition_ancillary.py tests/synthetic/test_undernutrition_ancillary_validation.py tests/synthetic/test_undernutrition_ancillary_boundaries.py
  git commit -m "test: validate undernutrition ancillary boundaries"
  ```

### Task 3: Document the ordinary-development contract

**Files:**

- Modify: `docs/synthetic-generator.md`
- Modify: `README.md`
- Create: `tests/synthetic/test_undernutrition_ancillary_docs.py`

**Interfaces:**

- Consumes: finalized Task 1/2 public symbols, fictional vocabulary, exact
  descriptor field order, and the existing `UndernutritionModule` event
  semantics.
- Produces: a concise ordinary-development guide section, one README roadmap
  link to the guide/spec/plan, and documentation drift tests; no runtime,
  package, descriptor, or Synthea integration.

- [ ] **Step 1: Write the failing documentation tests**

  Assert that the guide names every public type and function:
  `UndernutritionAncillaryPolicy`, `UndernutritionAncillaryProjection`,
  `UndernutritionAncillaryProjectionUnavailable`,
  `UndernutritionAncillaryValidationStatus`,
  `UndernutritionAncillaryCheck`,
  `UndernutritionAncillaryValidationReport`,
  `project_undernutrition_ancillary_resources`, and
  `validate_undernutrition_ancillary_resources`. Assert the exact fictional
  diagnosis, weight/height component, marker, referral, medication, record
  type, and `undernutrition-ancillary-id-v1` values. Assert
  exact-schema/in-memory/evaluator-only status, undernutrition's
  weight-first/delayed-height source boundary, visible-event/source-point
  links, hidden treatment gating, two labs per workup, unresolved problem
  behavior, fictional nutrition-supplement treatment, no `obesity_flag`, and
  four empty tuples for non-target members. Assert the guide explicitly
  defers runtime/package integration, prevalence/demographic calibration,
  privacy/non-matchability, clinical/nutrition/release claims, real/held-out
  data, dedicated resource/terminology expansion, and optional Synthea
  conformance. Assert README links the guide, undernutrition plan, and spec
  without copying the full guide.

- [ ] **Step 2: Implement documentation and tests**

  Add one concise `## Evaluator-only undernutrition ancillary pathway`
  section beside the existing excess-weight, hypothyroidism, celiac, SGA, and
  Turner sections in `docs/synthetic-generator.md`. State the exact API and
  vocabulary, that all labels are fictional rather than clinical terminology,
  that the current descriptor has the four named resource shapes and
  empty-string missing-value conventions, and that the projection is typed,
  in-memory, and evaluator-only. Explain that
  `UndernutritionModule`'s weight/BMI-first decline, delayed height effect,
  and optional partial recovery remain hidden upstream state. Describe
  recognition/referral, workup/two labs, diagnosis/problem, and visible-
  diagnosis-plus-private-treatment/medication descendants, including
  source-point visit linking and treatment suppression when diagnosis is
  absent, censored, or later than treatment. State that response/nonresponse
  creates no row, nutrition-supplement wording is fictional, and no
  `obesity_flag` is emitted.

  Add one short README sentence linking the guide, spec, and plan. Preserve
  existing governance wording and do not move clinical or data-access claims
  into the new section; deferred claims are explicit boundaries of this
  ordinary-development fixture contract.

- [ ] **Step 3: Run focused documentation checks**

  ```bash
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_undernutrition_ancillary_docs.py
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check tests/synthetic/test_undernutrition_ancillary_docs.py
  git diff --check
  ```

- [ ] **Step 4: Commit the documentation task**

  ```bash
  git add docs/synthetic-generator.md README.md tests/synthetic/test_undernutrition_ancillary_docs.py
  git commit -m "docs: describe undernutrition ancillary fixtures"
  ```

### Task 4: Review, verify, merge, and push

**Files:**

- Modify: `.superpowers/sdd/2026-09-02-undernutrition-ancillary-pathway/progress.md` (ignored SDD ledger only)

**Interfaces:**

- Consumes: the Task 1–3 commits, focused reports, exact descriptor contract,
  current `UndernutritionModule`/event semantics, and existing repository
  validation gates.
- Produces: a reviewed undernutrition ancillary slice ready to merge without
  modifying native growth generation, real-data boundaries, runtime
  composition, package inventory, descriptor, or Synthea code.

- [ ] **Step 1: Run the complete verification matrix**

  ```bash
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q -p no:cacheprovider
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests
  PYTHONDONTWRITEBYTECODE=1 python3 schema/build.py --check
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv lock --check
  git diff --check
  ```

  Inspect `git status --short`, staged names, staged stat, and staged diff
  for only the planned module, tests, and documentation files. Scan tracked
  and staged paths for patient rows, real-data inputs, output artifacts, and
  forbidden runtime/package imports. Confirm the public generator, package
  exporter, `datapackage.json`, and Synthea surface are unchanged. Record
  command results in the ignored SDD ledger and task reports without staging
  those artifacts.

- [ ] **Step 2: Dispatch scoped task reviews and one broad review**

  Create review packages from the exact Task 1, Task 2, and Task 3 base/head
  ranges and dispatch an independent reviewer for each. Then create a
  merge-base-to-`HEAD` package and dispatch the broad reviewer. The broad
  review must check exact descriptor order/types, source-point linkage,
  hidden treatment gating, two fictional empty-result labs, nutrition-
  supplement fictional wording, fixed status precedence, redaction,
  namespace isolation, static imports, documentation accuracy, and unchanged
  runtime/package/descriptor behavior. Address every Critical, Important,
  and Minor finding through the SDD fix/re-review loop before publication;
  record any parked ruling in the ledger.

- [ ] **Step 3: Inspect, merge, rerun, and push**

  Before publication, inspect `git status --short`, staged names/stat/diff,
  and `git diff --check`, preserving unrelated untracked caches and reports.
  Commit only scoped final checklist metadata or fixes. Use the finishing
  workflow to fast-forward `main` from the reviewed branch, rerun the full
  verification matrix on merged `main`, push `origin/main`, fetch, and verify
  exact parity:

  ```bash
  git rev-parse main
  git rev-parse origin/main
  test "$(git rev-parse main)" = "$(git rev-parse origin/main)"
  ```

- [ ] **Step 4: Mark the plan complete after parity**

  Update the ignored ledger and this plan's final checklist only after the
  pushed commit and parity check exist. The published slice must still have
  no visible runtime/package/descriptor integration, no real or governed
  patient input, and no clinical, prevalence, privacy, release, or Synthea
  conformance claim.

## Plan self-review

- [ ] Every spec requirement has a named test or documentation/verification
  step.
- [ ] All public names, function signatures, fixed strings, resource order,
  field order, check order, and status precedence are consistent across the
  spec and plan.
- [ ] The plan contains no unresolved requirement, unspecified validation, or
  implicit clinical terminology choice.
- [ ] The plan does not authorize Synthea execution, real-data access,
  package/descriptor integration, or visible runtime changes.
