# Native Turner Ancillary Pathway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic evaluator-only projection and validator for fictional Turner-syndrome referral, workup, problem-list, and treatment rows in the exact PPOC schema, without changing the native Turner trajectory, visible runtime, or package export.

**Architecture:** A separate `synthetic.native.turner_ancillary` module consumes one typed `CohortMember`, an extracted `ResourceShape`, and a strict `TurnerAncillaryPolicy`. It owns a closed fictional vocabulary and the independent `turner-ancillary-id-v1` namespace, emits immutable exact-schema rows, and returns a fixed aggregate-only validation report. The native `TurnerSyndromeModule` remains responsible for female-reference eligibility, no birth-state deficit, progressive height/BMI behavior, and hidden treatment state; the ancillary projection exposes only descendants allowed by visible events and the private treatment gate.

**Tech Stack:** Python 3.12+, standard-library dataclasses/enums/hashlib/re/collections.abc/types, existing synthetic cohort/model/observation/resource contracts, pytest, Ruff, schema checker, and the repository's SDD review workflow.

**Spec:** `docs/superpowers/specs/2026-09-02-turner-ancillary-pathway-design.md`

## Global Constraints

- Accept only typed `CohortMember`, `ResourceShape`, and `TurnerAncillaryPolicy`; no descriptor paths, path-like values, CSV readers, arbitrary rows or field lists, keys, reports, output destinations, environment input, or governed data.
- Emit exactly `labs`, `medications`, `problem_list`, and `referrals` in that fixed order; every emitted row uses the supplied descriptor field order and empty strings for fields not represented by the pathway.
- Use only these fictional values: `SYN-TURNER-SYNDROME`, `SYN-TURNER-KARYOTYPE`, `SYN-TURNER-ENDOCRINE-EVIDENCE`, `Synthetic Pediatric Endocrinology`, `Synthetic estrogen intervention`, `Internal`, and `Synthetic`; none is an ICD, LOINC, RxNorm, or clinical value claim.
- A valid Turner frame maps visible `recognition` to one referral, visible `workup` to two lab component rows in one order, visible `diagnosis` to one unresolved problem row, and visible `diagnosis` plus a private `treatment_start` at or after diagnosis to one medication row. A private treatment event alone never creates a medication; treatment response/nonresponse creates no extra row.
- The upstream Turner module requires `reference_sex="F"`; the ancillary module must not infer reference eligibility from visible recorded sex, which may be `F` or `U`. The Turner trajectory has no birth-state deficit; latent onset, phenotype, treatment, and response state never become visible ancillary values.
- Healthy and every non-Turner member return four empty tuples. No row writes, derives, or implies `obesity_flag`.
- Projection is deterministic, nonmutating, random-free, and source-point/visit linked. IDs are opaque synthetic tokens derived only from the patient identity and fixed role under `turner-ancillary-id-v1`.
- Errors, reprs, checks, and reports are aggregate-only and omit patient/visit/row identifiers, ages, codes, values, hidden events, severity, truth hashes, paths, keys, and source evidence.
- Validator checks are exactly `pathway_scope`, `row_schema`, `causal_timing`, `cross_resource_links`, and `source_evidence`, in that order. Statuses are only `PASS`, `FAIL`, and `UNEVALUABLE`, with `FAIL > UNEVALUABLE > PASS`.
- Visible row/count/age/constant/visit-link checks run before private source validation. Missing or malformed private evidence is `UNEVALUABLE` only when no visible violation is independently demonstrable; a valid-frame/member or source-event binding mismatch is `FAIL/SOURCE_EVIDENCE_INVALID`.
- The module imports only standard-library helpers and native cohort/model/observation/resource contracts. Static tests reject calibration, real-data, held-out, privacy, DuckDB, filesystem, CSV, package/export, manifest, subprocess, environment, network, randomness, `obesity_flag`, and Synthea coupling.
- Each implementation task ends with focused tests, Ruff, `git diff --check`, and a scoped commit. Never stage generated caches, bytecode, SDD briefs, or reports.

---

### Task 1: Add strict models and deterministic Turner projection

**Files:**

- Create: `src/synthetic/native/turner_ancillary.py`
- Create: `tests/synthetic/test_turner_ancillary_models.py`
- Create: `tests/synthetic/test_turner_ancillary_projection.py`

**Interfaces:**

- Consumes: typed `CohortMember`, `AgeRegimeDisorderTrajectory`, `ClinicalEvent`, `RecordedEvent`, `RecordedEventKind`, `ResourceShape`, and `ResourceRow`.
- Produces: the frozen `TurnerAncillaryPolicy` and `TurnerAncillaryProjection` models, the fixed fictional constants, `TurnerAncillaryProjectionUnavailable`, and `project_turner_ancillary_resources(member, shape, policy)` for Task 2 and the documentation task.

- [x] **Step 1: Write failing model and projection tests**

  Build only fictional in-memory fixtures from `tests/synthetic/fakes.py` and
  the checked-in descriptor mapping. Assert the following exact contracts:

  ```python
  TURNER_ANCILLARY_RESOURCE_NAMES == (
      "labs", "medications", "problem_list", "referrals"
  )
  TURNER_DIAGNOSIS_CODE == "SYN-TURNER-SYNDROME"
  TURNER_KARYOTYPE_COMPONENT == "SYN-TURNER-KARYOTYPE"
  TURNER_ENDOCRINE_EVIDENCE_COMPONENT == "SYN-TURNER-ENDOCRINE-EVIDENCE"
  TURNER_LAB_COMPONENT_NAMES == (
      TURNER_KARYOTYPE_COMPONENT, TURNER_ENDOCRINE_EVIDENCE_COMPONENT
  )
  TURNER_REFERRAL_SPECIALTY == "Synthetic Pediatric Endocrinology"
  TURNER_MEDICATION_NAME == "Synthetic estrogen intervention"
  TURNER_MEDICATION_RECORD_TYPE == "Internal"
  TURNER_LAB_RESULT_FLAG == "Synthetic"
  ```

  Cover frozen policy/projection models, safe aggregate policy tokens, exact
  four-resource order, immutable row mappings, the supplied descriptor field
  order and scalar types, empty-string conventions, namespaced deterministic
  IDs, and redacted projection errors. Exercise target members with no
  visible events, each visible event alone, all visible events, same-age
  recognition/workup/diagnosis events, diagnosis with a private treatment
  start, no treatment, treatment before an observed diagnosis, and treatment
  with a censored diagnosis. Assert that recognition yields one referral,
  workup yields two component rows sharing one order ID, diagnosis yields one
  unresolved problem, and eligible treatment yields one medication linked to
  the diagnosis visit. Assert that hidden birth/onset/phenotype state,
  treatment response/nonresponse, and `obesity_flag` never enter rows.

  Also test Turner members with recorded sex `F` and `U`, because the native
  module's reference-sex requirement is upstream and visible recorded sex is
  not a sufficient eligibility test. Test healthy, GHD, hypothyroidism, celiac,
  SGA, undernutrition, excess-weight, and other non-target members for four
  empty tuples. Repeat identical typed inputs for equal mappings, snapshot
  the member/frame/shape/policy for no mutation, and assert no row ID equals
  or includes an input patient/visit identifier other than the required
  synthetic patient link.

- [x] **Step 2: Run focused tests to verify they fail**

  ```bash
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_turner_ancillary_models.py tests/synthetic/test_turner_ancillary_projection.py
  ```

  Expected: test collection fails because the Turner ancillary module and its
  public models do not yet exist.

- [x] **Step 3: Implement strict models and projection**

  Add `TurnerAncillaryPolicy(policy_id, policy_version, result_delay_days)` as
  a frozen aggregate-safe policy and
  `TurnerAncillaryProjection(patient_id, shape, rows)` as a frozen projection
  whose rows are an immutable mapping of four tuples. Add the fixed redacted
  `TurnerAncillaryProjectionUnavailable` exception and the constants listed
  in Step 1. The public projection signature is:

  ```python
  def project_turner_ancillary_resources(
      member: CohortMember,
      shape: ResourceShape,
      policy: TurnerAncillaryPolicy,
  ) -> TurnerAncillaryProjection:
      ...
  ```

  Before assembling a target projection, require a passing
  `validate_observation_frame`, a synthetic patient identity, a trajectory
  equal to `frame.truth.latent_trajectory`, trajectory events equal to
  `frame.truth.source_events`, a nonempty physiology, and realized
  opportunities paired one-to-one with visible visits. Resolve every visible
  event's `opportunity_index` through its realized source-point opportunity to
  the corresponding visible visit; do not match by age. Use the first
  `RecordedEvent` of each event kind after the frame has passed validation.

  For `DisorderKind.TURNER_SYNDROME`, assemble only these rows: recognition
  creates one referral with the exact fictional specialty and one requested
  visit; workup creates two labs with line numbers 1 and 2, the exact
  karyotype/endocrine-evidence component names, one shared deterministic
  `lab_order_id`, the exact in-memory `Synthetic` marker, and empty procedure,
  LOINC, and value fields; diagnosis creates one unresolved problem with the
  exact diagnosis token and no visit field; and diagnosis plus a private
  trajectory `ClinicalEvent(event_type="treatment_start")` at or after the
  diagnosis age creates one medication linked to the diagnosis visit, with
  order age at diagnosis, start age at the private treatment event, empty end
  age, `Internal` record type, and the synthetic estrogen-intervention name.
  Suppress medication when diagnosis is absent or the private start is before
  the observed diagnosis. Do not emit any response/nonresponse row.

  Build every row by iterating `shape.field_names(resource_name)`. Use empty
  strings for all omitted fields and derive opaque IDs from only
  `turner-ancillary-id-v1`, the synthetic patient ID, and a fixed role. Catch
  malformed typed inputs behind one fixed redacted exception without exposing
  values, source state, paths, or keys. Do not modify any existing ancillary
  module, runtime, exporter, descriptor, or Synthea code.

- [x] **Step 4: Run focused tests and lint**

  ```bash
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_turner_ancillary_models.py tests/synthetic/test_turner_ancillary_projection.py
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/native/turner_ancillary.py tests/synthetic/test_turner_ancillary_models.py tests/synthetic/test_turner_ancillary_projection.py
  git diff --check
  ```

- [x] **Step 5: Commit the projection task**

  ```bash
  git add src/synthetic/native/turner_ancillary.py tests/synthetic/test_turner_ancillary_models.py tests/synthetic/test_turner_ancillary_projection.py
  git commit -m "build: add Turner ancillary projection"
  ```

### Task 2: Add aggregate validation and static boundary tests

**Files:**

- Modify: `src/synthetic/native/turner_ancillary.py`
- Create: `tests/synthetic/test_turner_ancillary_validation.py`
- Create: `tests/synthetic/test_turner_ancillary_boundaries.py`

**Interfaces:**

- Consumes: Task 1's immutable projection, policy, exact row contract, fictional constants, and source-point/visit mapping.
- Produces: `TURNER_ANCILLARY_CHECK_NAMES`, fixed reason-code vocabulary, `TurnerAncillaryValidationStatus`, `TurnerAncillaryCheck`, `TurnerAncillaryValidationReport`, and `validate_turner_ancillary_resources(member, projection, policy)`.

- [x] **Step 1: Write failing validator and boundary tests**

  Assert the exact check order:

  ```python
  TURNER_ANCILLARY_CHECK_NAMES == (
      "pathway_scope",
      "row_schema",
      "causal_timing",
      "cross_resource_links",
      "source_evidence",
  )
  ```

  Cover passing target/non-target reports, `PASS`/`FAIL`/`UNEVALUABLE`
  statuses, fixed aggregate check counts, and `FAIL > UNEVALUABLE > PASS`
  precedence. Mutate only fictional in-memory copies to test wrong diagnosis,
  lab components, marker, specialty, medication, record type, IDs, scalar
  types, field order, empty values, duplicate rows, wrong resource counts,
  and a medication injected into an otherwise untreated projection. Test
  recognition/workup/diagnosis age mismatches, reversed phases, undelayed or
  reversed lab results, treatment before diagnosis, bad result line numbers,
  mismatched patient IDs, non-synthetic IDs, and referral/lab/medication links
  to visits that are not in the actual frame. Confirm the problem row retains
  the descriptor's no-visit-key semantics.

  Test source-point-specific linkage: a row linked to a real frame visit that
  belongs to a different opportunity must fail, even if its age equals the
  event age. Test missing and malformed private truth, valid-frame/member
  trajectory mismatch, invalid source-event binding, and visible violations
  combined with unavailable source evidence. The visible violation must
  remain `FAIL`, while source-only absence is `UNEVALUABLE`. Assert that
  reports and reprs contain only fixed names/statuses/reasons and no patient,
  visit, row, age, code, value, hidden-event, path, key, or source text.

  Parse the module with `ast` and reject imports or calls related to
  calibration, real/held-out data, privacy, DuckDB, filesystem/path APIs,
  CSV, package/export, manifests, subprocess, environment, network,
  randomness, Synthea, or `obesity_flag`. Reject public signatures that take
  paths, rows, keys, reports, output destinations, or descriptor mappings.

- [x] **Step 2: Run focused validator tests to verify they fail**

  ```bash
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_turner_ancillary_validation.py tests/synthetic/test_turner_ancillary_boundaries.py
  ```

  Expected: collection or assertions fail because the validator and boundary
  regression tests are not implemented.

- [x] **Step 3: Implement the fixed aggregate validator**

  Add the public validator signature:

  ```python
  def validate_turner_ancillary_resources(
      member: CohortMember,
      projection: TurnerAncillaryProjection,
      policy: TurnerAncillaryPolicy,
  ) -> TurnerAncillaryValidationReport:
      ...
  ```

  Define frozen `TurnerAncillaryCheck` and
  `TurnerAncillaryValidationReport` values with fixed check names, fixed
  reason codes, immutable check counts, aggregate-only mappings, and the
  status precedence above. Validate visible row structure and descriptor
  order, synthetic patient/row IDs, constants, scalar types, row counts,
  empty conventions, actual frame visits, event ages, result delay, phase
  order, and treatment gating before consulting private source validation.
  A visible workup always expects exactly two labs in one order; a visible
  recognition expects one referral; a visible diagnosis expects one problem;
  and an eligible private treatment start plus visible diagnosis expects one
  medication. The medication tuple must be empty for every non-target member
  and for every target without that gate.

  Run the existing observation validator after all visible checks. Classify
  invalid observation/source binding as `FAIL/SOURCE_EVIDENCE_INVALID` and
  absent or malformed private evidence as
  `UNEVALUABLE/SOURCE_EVIDENCE_UNAVAILABLE` only when no visible failure is
  already established. After source and typed member-to-truth binding pass,
  compare source-point-specific event links and the deterministic expected
  projection. Never include source objects or row payloads in a report.

- [x] **Step 4: Run focused validation tests and lint**

  ```bash
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_turner_ancillary_validation.py tests/synthetic/test_turner_ancillary_boundaries.py
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/native/turner_ancillary.py tests/synthetic/test_turner_ancillary_validation.py tests/synthetic/test_turner_ancillary_boundaries.py
  git diff --check
  ```

- [x] **Step 5: Commit the validator task**

  ```bash
  git add src/synthetic/native/turner_ancillary.py tests/synthetic/test_turner_ancillary_validation.py tests/synthetic/test_turner_ancillary_boundaries.py
  git commit -m "test: validate Turner ancillary boundaries"
  ```

### Task 3: Document the ordinary-development contract

**Files:**

- Modify: `docs/synthetic-generator.md`
- Modify: `README.md`
- Create: `tests/synthetic/test_turner_ancillary_docs.py`

**Interfaces:**

- Consumes: finalized Task 1/2 public symbols, fictional vocabulary, and the existing Turner module/event semantics.
- Produces: a concise ordinary-development guide section, one README roadmap link, and documentation drift tests; no runtime or package integration.

- [x] **Step 1: Write failing documentation tests**

  Assert that the guide names every public type and function:
  `TurnerAncillaryPolicy`, `TurnerAncillaryProjection`,
  `TurnerAncillaryProjectionUnavailable`, `TurnerAncillaryValidationStatus`,
  `TurnerAncillaryCheck`, `TurnerAncillaryValidationReport`,
  `project_turner_ancillary_resources`, and
  `validate_turner_ancillary_resources`. Assert the exact fictional diagnosis,
  karyotype, endocrine-evidence, marker, referral, medication, record type,
  and `turner-ancillary-id-v1` values. Assert exact-schema/in-memory/
  evaluator-only status, female-reference upstream eligibility, no birth-state
  deficit, visible-event/source-point links, hidden treatment gating, two labs
  per workup, unresolved problem behavior, no `obesity_flag`, and four empty
  tuples for non-target members. Assert the guide explicitly defers runtime /
  package integration, prevalence/demographic calibration,
  privacy/non-matchability, clinical/release claims, real/held-out data, and
  optional Synthea conformance. Assert README links the guide, Turner plan,
  and Turner spec without copying the full guide.

- [x] **Step 2: Implement documentation and tests**

  Add one concise `## Evaluator-only Turner ancillary pathway` section beside
  the existing excess-weight, hypothyroidism, celiac, and SGA sections in
  `docs/synthetic-generator.md`. State the exact API and vocabulary, that all
  labels are fictional rather than clinical terminology, that the current
  descriptor has the four named resource shapes and empty-string missing-value
  conventions, and that the projection is typed/in-memory only. Explain that
  the native Turner module's `reference_sex="F"` eligibility and no-birth-
  deficit trajectory remain upstream hidden state; recorded sex is not used to
  infer reference eligibility. Describe recognition/referral, workup/two
  labs, diagnosis/problem, and visible-diagnosis-plus-private-treatment/
  medication descendants, including source-point visit linking and treatment
  suppression when diagnosis is absent or censored. State that no response
  event or `obesity_flag` is emitted.

  Add one short README sentence linking the guide, spec, and plan. Preserve
  existing roadmap wording and do not move governance material into the new
  section; deferred claims are boundaries of what this ordinary-development
  fixture contract asserts, not prerequisites for using it.

- [x] **Step 3: Run focused documentation checks**

  ```bash
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_turner_ancillary_docs.py
  git diff --check
  ```

- [x] **Step 4: Commit the documentation task**

  ```bash
  git add docs/synthetic-generator.md README.md tests/synthetic/test_turner_ancillary_docs.py
  git commit -m "docs: describe Turner ancillary fixtures"
  ```

### Task 4: Review, verify, merge, and push

**Files:**

- Modify: `.superpowers/sdd/2026-09-02-turner-ancillary-pathway/progress.md` (ignored SDD ledger only)

**Interfaces:**

- Consumes: the Task 1–3 commits, focused reports, exact descriptor contract, and existing repository validation gates.
- Produces: a reviewed Turner ancillary slice ready to merge without modifying native growth generation, real-data boundaries, runtime composition, or package inventory.

- [x] **Step 1: Run the complete verification matrix**

  ```bash
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q -p no:cacheprovider
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests
  PYTHONDONTWRITEBYTECODE=1 python3 schema/build.py --check
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv lock --check
  git diff --check
  ```

  Inspect the staged names, stat, and diff for only the planned source,
  tests, and documentation files. Scan tracked and staged paths for patient
  rows, real-data inputs, output artifacts, and forbidden runtime/package
  imports. Confirm the public generator and package exporter are unchanged,
  and run the existing fail-closed CLI checks. Record commands/results in the
  ignored SDD ledger and task reports without staging those artifacts.

- [x] **Step 2: Dispatch scoped task reviews and one broad review**

  Create review packages from the exact Task 1, Task 2, and Task 3 base/head
  ranges, and dispatch an independent reviewer for each. Then create a
  merge-base-to-`HEAD` package and dispatch the most capable available broad
  reviewer. The broad review must check exact descriptor order/types,
  source-point linkage, hidden treatment gating, female-reference boundary,
  fixed status precedence, redaction, namespace isolation, static imports,
  documentation accuracy, and unchanged runtime/package behavior. Address
  every Critical, Important, and Minor finding through the SDD fix/re-review
  loop before publication; record any parked ruling in the ledger.

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
  no visible runtime/package integration, no real or governed patient input,
  and no clinical, prevalence, privacy, release, or Synthea conformance
  claim.

## Plan self-review

- [x] Every spec requirement has a named test or documentation/verification step.
- [x] All public names, function signatures, fixed strings, resource order, check order, and status precedence are consistent across the spec and plan.
- [x] The plan contains no placeholder, unspecified validation, or implicit clinical terminology choice.
- [x] The plan does not authorize Synthea execution, real-data access, package integration, or visible runtime changes.
