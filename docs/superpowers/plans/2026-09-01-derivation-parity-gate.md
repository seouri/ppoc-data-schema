# Governed Augmented-Derivation Parity Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a strict in-memory parity harness that proves a candidate exact-schema augmented output agrees with an independently supplied reference while independently checking descriptor-declared deterministic relationships.

**Architecture:** Add `synthetic.derivation_parity` as a one-way evaluator boundary. It materializes only process-local base, candidate, and reference row mappings, validates the exact repository schema and row identities, recomputes safe deterministic conversions/summaries/flag relationships, and compares every augmented field with fixed tolerances. It returns only an aggregate immutable report; existing generation, package export, governed evaluators, and Synthea boundaries remain unchanged.

**Tech Stack:** Python 3.12+, standard-library dataclasses/enum/json/math/re/statistics and collections.abc, existing schema/base-resource contracts, pytest, Ruff, `uv`, and the repository schema checker.

**Spec:** `docs/superpowers/specs/2026-09-01-derivation-parity-gate-design.md`

## Global Constraints

- The public contract token is exactly `DERIVATION_PARITY_VERSION = "derivation-parity-v1"`.
- The evaluator accepts already-loaded mappings and row iterables only; it does not open paths, read CSV/Parquet, call DuckDB, write files, mutate inputs, call a generator, or consume calibration/held-out/privacy artifacts.
- `base_rows` has exactly `patients`, `visits`, `labs`, `medications`, `problem_list`, and `referrals`; candidate/reference mappings have exactly `patients_augmented` and `visits_augmented`.
- The checked-in `EXPECTED_SCHEMA_FINGERPRINT` and exact descriptor field order are required; no schema drift or arbitrary resource/field names are accepted.
- Identifiers, implementation IDs, policy IDs, and digests are validated but never emitted from row-level diagnostics; report mappings contain aggregate counts and safe contract identities only.
- Missing values are the descriptor empty sentinel or `None`; booleans are not numbers; nonfinite and unknown scalar values fail closed.
- Overall status precedence is `FAIL > UNEVALUABLE > PASS`; a passing report requires every fixed check to be evaluable and passing.
- Candidate/reference mismatch, structural invalidity, deterministic contradiction, schema drift, or unsafe values are `FAIL`; missing/underpowered required evidence is `UNEVALUABLE`, never zero or pass.
- Reports never contain patient/visit identifiers, diagnosis codes, raw values, row positions, source paths, hidden truth, trajectories, or evaluator representations.
- The module must not import `Path`, `csv`, `duckdb`, package/export, manifest, calibration, held-out, privacy, real-data, model, callable, network, or Synthea code and must expose no path/key/output arguments.
- CI fixtures are completely fictional. A passing report is a parity diagnostic, not clinical validity, prevalence, privacy/non-matchability, release authorization, or a Synthea conformance result.
- Controller edits only this plan/spec and ignored SDD evidence; implementation, test, and user-facing documentation edits are delegated.

---

### Task 1: Add strict parity models and canonical-safe input contracts

**Files:**

- Create: `src/synthetic/derivation_parity.py`
- Create: `tests/synthetic/test_derivation_parity_models.py`

**Interfaces:**

- Consumes: `EXPECTED_SCHEMA_FINGERPRINT`, `BASE_RESOURCES`, descriptor `resource_spec`/`field_names`, and standard-library immutable value patterns.
- Produces: `DERIVATION_PARITY_VERSION`, `DerivationParityUnavailable`, `DerivationParityStatus`, `DerivationImplementation`, `DerivationParityPolicy`, `DerivationParityCheck`, `DerivationParityReport`, and the public evaluator signature used by later tasks.

- [ ] **Step 1: Write the failing model and serialization tests.**

  Build small fictional mappings with the checked-in descriptor and assert the
  public constructors reject empty or unsafe implementation/policy tokens,
  malformed fingerprints, boolean/nonfinite/negative tolerances, invalid
  support floors, mutable/non-JSON values, duplicate check names, bad status
  counts, nonfinite maximum differences, and unknown report keys. Assert that
  valid values are immutable, `to_mapping()` returns fresh JSON-compatible
  aggregate mappings, `to_json_bytes()` is compact sorted ASCII JSON with one
  newline, and `repr()` contains no row, identifier, source, truth, or hidden
  evaluator values.

- [ ] **Step 2: Run the model tests to verify the API is absent.**

  Run:

  ```sh
  UV_CACHE_DIR=/tmp/ppoc-uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q tests/synthetic/test_derivation_parity_models.py
  ```

  Expected: collection fails because `synthetic.derivation_parity` and its
  public models do not yet exist. Correct only fixture/import syntax before
  implementation.

- [ ] **Step 3: Implement the immutable models and canonical mappings.**

  Implement exact model validation and fixed status/reason tokens. Keep all
  implementation and policy identities bounded and aggregate-safe. Define the
  fixed ordered check names from the spec and exact report keys. Suppress
  per-check counts and differences to `None` when a check is unevaluable,
  enforce nonnegative aggregate counts and finite bounded differences, and
  make all mappings defensive copies. Use one fixed redacted
  `DerivationParityUnavailable` public failure message; do not include input
  paths, IDs, field values, or exception details.

- [ ] **Step 4: Run focused model tests, Ruff, and commit.**

  ```sh
  UV_CACHE_DIR=/tmp/ppoc-uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q tests/synthetic/test_derivation_parity_models.py
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/derivation_parity.py tests/synthetic/test_derivation_parity_models.py
  git diff --check
  git add src/synthetic/derivation_parity.py tests/synthetic/test_derivation_parity_models.py
  git commit -m "feat: add derivation parity models"
  ```

### Task 2: Implement aggregate derivation-parity evaluation

**Files:**

- Modify: `src/synthetic/derivation_parity.py`
- Create: `tests/synthetic/test_derivation_parity_evaluation.py`

**Interfaces:**

- Consumes: Task 1 models plus the checked-in schema contract and the exact
  base/augmented resource field definitions.
- Produces:

  ```python
  def validate_derivation_parity(
      base_rows: Mapping[str, Iterable[Mapping[str, object]]],
      candidate_rows: Mapping[str, Iterable[Mapping[str, object]]],
      reference_rows: Mapping[str, Iterable[Mapping[str, object]]],
      descriptor: Mapping[str, object],
      *,
      candidate: DerivationImplementation,
      reference: DerivationImplementation,
      policy: DerivationParityPolicy,
  ) -> DerivationParityReport: ...
  ```

- [ ] **Step 1: Write failing evaluator tests.**

  Use only hand-built fictional rows and a descriptor mapping. Assert a valid
  candidate/reference triple produces a deterministic `PASS`; changing a
  candidate numeric field beyond the reference tolerance produces `FAIL`;
  changing an exact string/flag or introducing a missing row produces `FAIL`;
  missing required source values and support below policy produce
  `UNEVALUABLE`; and a structural invalidity still overrides unevaluable
  evidence. Cover duplicate IDs, unknown keys, bad field order, schema
  fingerprint drift, base/augmented key misalignment, informative
  ethnicity/race projection, age conversions, weight/height conversions,
  BMI age gating, patient counts/spans, diagnosis-age prefix minima, z-score
  summary statistics, percentile bounds, flag threshold relationships, and
  healthy-flag consistency. Verify all 82 augmented visit fields and all
  87 augmented patient fields participate in candidate/reference parity.

- [ ] **Step 2: Run evaluator tests to verify the expected failures.**

  ```sh
  UV_CACHE_DIR=/tmp/ppoc-uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q tests/synthetic/test_derivation_parity_evaluation.py
  ```

  Expected: the new tests fail because evaluation is not implemented. Fix only
  fixture construction errors before writing production logic.

- [ ] **Step 3: Implement private materialization and fixed aggregate checks.**

  Materialize each mapping exactly once into private tuples, validate exact
  resource sets and descriptor field order, canonicalize descriptor scalar
  types without accepting booleans or nonfinite values, and index only by
  descriptor primary keys. Validate base/candidate/reference key alignment and
  visible projections without placing row content in exceptions or reports.
  Recompute age, unit, BMI, patient summary, z-score summary, bounds, and
  available flag relationships using the exact constants and semantics in the
  spec. For BIV- or reference-dependent values, require candidate/reference
  agreement and do not invent a replacement value. Compare every augmented
  field with exact categorical/null semantics or the policy reference
  tolerance, record only aggregate compared/mismatch counts and maximum
  absolute difference, and apply `FAIL > UNEVALUABLE > PASS` precedence.
  Catch all public evaluator failures behind the fixed redacted exception.
  Do not add a writer, CLI, filesystem reader, generator hook, or package
  exporter integration.

- [ ] **Step 4: Run focused evaluation tests, lint, and commit.**

  ```sh
  UV_CACHE_DIR=/tmp/ppoc-uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q tests/synthetic/test_derivation_parity_evaluation.py tests/synthetic/test_derivation_parity_models.py
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/derivation_parity.py tests/synthetic/test_derivation_parity_*.py
  git diff --check
  git add src/synthetic/derivation_parity.py tests/synthetic/test_derivation_parity_evaluation.py
  git commit -m "feat: evaluate augmented derivation parity"
  ```

### Task 3: Document the gate and protect evaluator/visible boundaries

**Files:**

- Modify: `docs/synthetic-generator.md`
- Modify: `README.md`
- Create: `tests/synthetic/test_derivation_parity_boundaries.py`
- Modify: `tests/synthetic/test_package_export_boundaries.py` only if a
  legitimate aggregate-safe import allowlist needs explicit registration.

**Interfaces:**

- Consumes: `validate_derivation_parity` and the report models from Tasks 1–2.
- Produces: user-facing evaluator-only usage documentation and static checks
  proving that visible generation/export and governed evaluators remain
  isolated.

- [ ] **Step 1: Write failing documentation and AST boundary tests.**

  Assert the guide and README name the exact contract token, function, input
  resource sets, candidate/reference distinction, deterministic checks,
  tolerance/status semantics, aggregate-only report fields, fixed redaction,
  and the requirement for an independently reviewed reference implementation.
  Assert the parity module has no forbidden imports, path/key/output
  arguments, filesystem readers/writers, hidden-truth names in mappings/reprs,
  or calls into visible generation, package export, calibration, held-out,
  privacy, model, network, or Synthea code. Assert the existing exporter and
  generator remain free of automatic parity-evaluator calls.

- [ ] **Step 2: Run boundary tests to confirm the missing documentation/guards.**

  ```sh
  UV_CACHE_DIR=/tmp/ppoc-uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q tests/synthetic/test_derivation_parity_boundaries.py
  ```

- [ ] **Step 3: Implement documentation and static boundary coverage.**

  Add a concise Python example that receives already-loaded fictional or
  privately controlled rows, calls `validate_derivation_parity`, and inspects
  only `report.status`/`report.to_mapping()`. State that a passing comparison
  binds candidate/reference implementations but does not establish clinical
  validity, real-population prevalence, privacy/non-matchability, release
  approval, or Synthea conformance. Keep the smoke CLI, package exporter, and
  governed input boundaries unchanged.

- [ ] **Step 4: Run docs/boundary tests, lint, schema, lock, and commit.**

  ```sh
  UV_CACHE_DIR=/tmp/ppoc-uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q tests/synthetic/test_derivation_parity_boundaries.py tests/synthetic/test_derivation_parity_models.py tests/synthetic/test_derivation_parity_evaluation.py
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv lock --check
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run python schema/build.py --check
  git diff --check
  git add docs/synthetic-generator.md README.md tests/synthetic/test_derivation_parity_boundaries.py tests/synthetic/test_package_export_boundaries.py
  git commit -m "docs: document derivation parity gate"
  ```

### Task 4: Independent review, full verification, merge, and push

**Files:**

- Modify: this plan (checkbox/evidence metadata only)
- Create/modify: ignored `.superpowers/sdd/2026-09-01-derivation-parity-gate/`

- [ ] **Step 1: Create the SDD ledger and run fresh scoped reviews after each task.**

  Record the plan identity, pre-flight conflict table, implementation
  commits, review package paths, findings, fix rounds, exact fix ranges, and
  PASS verdicts. Route every Critical/Important finding to the responsible
  implementer and run a scoped re-review before moving on. Record Minor
  findings and any rulings explicitly.

- [ ] **Step 2: Run a fresh broad review over the complete feature range.**

  Review exact schema/key alignment, deterministic formulas, support and
  status precedence, tolerance caps, redaction, input immutability, report
  serialization, reference-authority wording, and all forbidden boundaries.
  Resolve every Critical/Important finding through one consolidated fix wave
  and one scoped re-review.

- [ ] **Step 3: Run final feature verification.**

  ```sh
  UV_CACHE_DIR=/tmp/ppoc-uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv lock --check
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run python schema/build.py --check
  git diff --check
  ```

  Also evaluate the same fictional triple twice, assert byte-identical
  canonical reports and unchanged input mappings, scan all public report
  artifacts for row/identifier/truth tokens, and retain exact outputs in the
  ignored SDD evidence.

- [ ] **Step 4: Commit plan metadata and integrate.**

  Stage only this plan's checkbox/evidence changes, commit them, fast-forward
  the reviewed branch into `main`, rerun the full verification matrix on the
  merged tip, push `origin main`, and verify:

  ```sh
  test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
  ```

  Preserve unrelated caches/worktrees and retain this feature worktree and
  ignored SDD evidence unless cleanup is demonstrably safe.

## Completion evidence

Record implementation and fix commit IDs, scoped/broad review PASS reports,
focused and full test counts, Ruff/lock/schema/whitespace output, deterministic
serialization evidence, merged commit, push result, and local/remote parity
here before integration.
