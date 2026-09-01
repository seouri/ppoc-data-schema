# Authoritative Derivation Oracle Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox ([ ]) syntax for tracking.

**Goal:** Add a strict, aggregate-only handoff contract that binds an augmented-derivation oracle to its schema, dependencies, reference standard, golden boundary evidence, parity result, and external review, then enforce that binding at the explicit exporter boundary.

**Architecture:** src/synthetic/derivation_binding.py owns immutable metadata models, strict parsing, aggregate report semantics, and the approval helper. BoundDerivationOracle wraps the existing low-level DerivationOracle without reading files or executing external commands. The package and smoke APIs accept an explicit binding and use the wrapper before copying augmented outputs; test-only bindings remain available for fictional CI while non-test calls require a complete approved handoff.

**Tech Stack:** Python 3.12+, standard-library dataclasses/JSON/enum/typing, existing pytest, ruff, exact descriptor helpers, and the current atomic package exporter. No new runtime dependencies.

**Spec:** docs/superpowers/specs/2026-09-01-derivation-oracle-binding-design.md

## Global Constraints

- The public contract version is exactly derivation-binding-v1.
- The required golden categories are exactly filter_order, age_boundaries, missingness, harrall_outlier, biv_filtering, velocity_variants, and rounding.
- Binding reports use only PASS, FAIL, and UNEVALUABLE, with precedence FAIL > UNEVALUABLE > PASS.
- The fixed report check order is contract, schema_contract, oracle_identity, reference_standard, golden_coverage, parity_evidence, synthetic_fuzz_evidence, review, classification.
- require_approved_derivation_binding may succeed only for a non-test binding whose report is PASS, whose parity status is PASS, and whose review status is APPROVED.
- Test-only bindings may be structurally valid and unevaluable for missing evidence, but they must remain test-only in package manifests and never satisfy the approval helper.
- Candidate/reference/golden/fuzz/review rows, paths, patient/visit identifiers, secrets, and hidden-truth material never enter a public binding/report representation; fixed safe evidence IDs and SHA-256 digests are explicitly allowed.
- The binding loader accepts already-loaded mappings only; it never opens a path, reads real data, runs an external harness, or invokes Synthea.
- The existing DerivationOracle still writes only the two descriptor-named augmented CSVs into isolated staging and returns DerivationResult.
- Existing atomic staging, base-resource hashes, descriptor checks, structural validation, manifest lifecycle, and fixed redacted export failures remain unchanged.
- The production command-line smoke entry point remains fail-closed because this repository contains no approved production oracle or binding.
- All tests use fictional values and no network, governed data, patient rows, golden rows, or Synthea checkout.

---

### Task 1: Add strict binding identity and evidence models

**Files:**

- Create: src/synthetic/derivation_binding.py
- Create: tests/synthetic/test_derivation_binding_models.py
- Modify: src/synthetic/__init__.py only if it currently re-exports public synthetic contracts; otherwise leave it unchanged.

**Interfaces:**

- Produces DERIVATION_BINDING_VERSION, REQUIRED_GOLDEN_CATEGORIES, DerivationBindingUnavailable, DerivationBindingStatus, DerivationBindingOracle, DerivationReferenceStandard, DerivationGoldenEvidence, DerivationReview, and DerivationBinding.
- DerivationBinding.from_mapping(value: Mapping[str, object]) -> DerivationBinding parses one exact mapping.
- DerivationBinding.to_mapping() -> dict[str, object] returns a fresh aggregate-only mapping.
- DerivationBinding.to_json_bytes() -> bytes returns canonical compact sorted ASCII JSON plus one newline.
- Later tasks consume the exact nested field names and attributes specified below; do not rename them between tasks.

- [x] **Step 1: Write failing model tests**

Create fictional fixtures in tests/synthetic/test_derivation_binding_models.py with the following shape. Use SHA equal to 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef and SHA2 equal to fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210.

The root keys are binding_version, binding_id, schema_fingerprint, oracle, reference_standard, golden_evidence, review, and test_only. The nested oracle keys are oracle_id, implementation_fingerprint, source_revision, dependency_fingerprint, and source_kind. The reference keys are standard_id, standard_fingerprint, and version. The golden keys are manifest_id, manifest_fingerprint, parity_contract, parity_report_id, parity_report_fingerprint, parity_status, candidate_implementation_fingerprint, reference_implementation_fingerprint, parity_schema_fingerprint, covered_categories, bidirectional_case_count, synthetic_fuzz_case_count, and fuzz_corpus_fingerprint. The review keys are review_id, review_fingerprint, reviewed_at, reviewer_role, and status.

Use these exact fictional values in the valid fixture:

~~~python
{
    "binding_version": "derivation-binding-v1",
    "binding_id": "binding-example-v1",
    "schema_fingerprint": SHA,
    "oracle": {
        "oracle_id": "oracle-example-v1",
        "implementation_fingerprint": SHA2,
        "source_revision": "revision-example-v1",
        "dependency_fingerprint": SHA,
        "source_kind": "authoritative_implementation",
    },
    "reference_standard": {
        "standard_id": "standard-example-v1",
        "standard_fingerprint": SHA2,
        "version": "standard-version-1",
    },
    "golden_evidence": {
        "manifest_id": "golden-example-v1",
        "manifest_fingerprint": SHA,
        "parity_contract": "derivation-parity-v1",
        "parity_report_id": "parity-report-example-v1",
        "parity_report_fingerprint": SHA2,
        "parity_status": "PASS",
        "candidate_implementation_fingerprint": SHA2,
        "reference_implementation_fingerprint": SHA,
        "parity_schema_fingerprint": SHA,
        "covered_categories": [
            "filter_order", "age_boundaries", "missingness",
            "harrall_outlier", "biv_filtering", "velocity_variants", "rounding",
        ],
        "bidirectional_case_count": 7,
        "synthetic_fuzz_case_count": 100,
        "fuzz_corpus_fingerprint": SHA2,
    },
    "review": {
        "review_id": "review-example-v1",
        "review_fingerprint": SHA,
        "reviewed_at": "2026-09-01T00:00:00Z",
        "reviewer_role": "data-custodian",
        "status": "APPROVED",
    },
    "test_only": True,
}
~~~

Assert that the fixture builds, is frozen, has tuple-backed categories, and round-trips through to_mapping without sharing mutable nested mappings. Assert that to_json_bytes equals compact sorted ASCII JSON plus one trailing newline. Add tests for missing/extra nested keys, duplicate JSON keys, wrong scalar types, booleans, nonfinite numbers, unsafe path/row/identifier tokens, invalid digests/timestamps/counts/statuses/categories, and the fixed redacted exception text.

- [x] **Step 2: Run the model tests and verify the expected failure**

Run:

~~~sh
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_derivation_binding_models.py
~~~

Expected: collection fails because synthetic.derivation_binding and its public models do not exist.

- [x] **Step 3: Implement the immutable nested models**

Use frozen dataclasses and MappingProxyType for nested mappings. Define these exact fields:

~~~python
@dataclass(frozen=True)
class DerivationBindingOracle:
    oracle_id: str
    implementation_fingerprint: str
    source_revision: str
    dependency_fingerprint: str
    source_kind: str

@dataclass(frozen=True)
class DerivationReferenceStandard:
    standard_id: str
    standard_fingerprint: str
    version: str

@dataclass(frozen=True)
class DerivationGoldenEvidence:
    manifest_id: str | None
    manifest_fingerprint: str | None
    parity_contract: str | None
    parity_report_id: str | None
    parity_report_fingerprint: str | None
    parity_status: str
    candidate_implementation_fingerprint: str | None
    reference_implementation_fingerprint: str | None
    parity_schema_fingerprint: str | None
    covered_categories: tuple[str, ...]
    bidirectional_case_count: int
    synthetic_fuzz_case_count: int
    fuzz_corpus_fingerprint: str | None

@dataclass(frozen=True)
class DerivationReview:
    review_id: str | None
    review_fingerprint: str | None
    reviewed_at: str | None
    reviewer_role: str | None
    status: str

@dataclass(frozen=True)
class DerivationBinding:
    binding_version: str
    binding_id: str
    schema_fingerprint: str
    oracle: DerivationBindingOracle
    reference_standard: DerivationReferenceStandard
    golden_evidence: DerivationGoldenEvidence
    review: DerivationReview
    test_only: bool
~~~

Validate lowercase SHA-256 digests, bounded aggregate-safe tokens, exact UTC timestamps, source_kind values authoritative_implementation or approved_parity_harness, parity statuses PASS/FAIL/UNEVALUABLE, review statuses PENDING/APPROVED/REJECTED, nonnegative counts, and duplicate-free category tuples. Permit None only in the evidence/review fields declared nullable. Reject booleans, nonfinite numbers, arbitrary objects, paths, row/record indicators, patient/visit identifiers, and hidden-state words.

from_mapping must require the exact root and nested key sets above. Reject duplicate keys when parsing JSON with an object-pairs hook. to_mapping returns fresh dictionaries and a list for covered_categories. to_json_bytes is deterministic compact sorted ASCII JSON with one newline. DerivationBindingUnavailable must always expose exactly derivation binding is unavailable and discard caller exception text.

- [x] **Step 4: Run the model tests and verify they pass**

~~~sh
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_derivation_binding_models.py
~~~

Expected: all model round-trip, immutability, exact-key, hostile-input, digest, timestamp, and redaction tests pass.

- [x] **Step 5: Commit the model slice**

~~~sh
git add src/synthetic/derivation_binding.py tests/synthetic/test_derivation_binding_models.py
git commit -m "feat: add derivation binding models"
~~~

---

### Task 2: Add aggregate binding validation and approval semantics

**Files:**

- Modify: src/synthetic/derivation_binding.py
- Create: tests/synthetic/test_derivation_binding_evaluation.py

**Interfaces:**

- Produces DERIVATION_BINDING_CHECK_NAMES, DerivationBindingCheck, DerivationBindingReport, validate_derivation_binding, and require_approved_derivation_binding.
- validate_derivation_binding(binding: DerivationBinding, *, expected_schema_fingerprint: str) -> DerivationBindingReport uses an explicit expected fingerprint.
- require_approved_derivation_binding(binding: DerivationBinding, *, expected_schema_fingerprint: str) -> None raises DerivationBindingUnavailable unless approval requirements pass.

- [x] **Step 1: Write failing evaluator tests**

Using the Task 1 fixture, add tests for:

1. A complete non-test binding with all seven categories, positive bidirectional/fuzz counts, parity_status PASS, matching candidate/parity schema fingerprints, and review APPROVED produces nine ordered PASS checks and an overall PASS; the approval helper returns None.
2. A test-only binding with parity_status UNEVALUABLE, null evidence identities, zero counts, and review PENDING produces a structurally valid report with UNEVALUABLE evidence checks; the approval helper raises the fixed exception.
3. Missing golden categories, zero counts, missing digests, or missing review fields produce UNEVALUABLE rather than fabricated PASS.
4. Unknown categories, parity PASS with missing report/corpus evidence, candidate fingerprint mismatch, parity schema mismatch, rejected review, and non-test pending review produce FAIL in the owning check.
5. Reports have exactly the fixed check order, recomputed status counts, fixed reason codes OK/MISSING_EVIDENCE/OUTSIDE_POLICY/STRUCTURAL_INVALID, and no rows, paths, patient/visit identifiers, arbitrary review prose, or private text in mappings, JSON, repr, or exceptions. The fixed binding, oracle, reference-standard, and parity-report identities are the only serialized IDs.
6. Direct public construction rejects PASS with a positive mismatch count and OUTSIDE_POLICY with zero mismatches.

- [x] **Step 2: Run evaluator tests and verify expected failure**

~~~sh
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_derivation_binding_evaluation.py
~~~

Expected: collection fails because the report models and evaluator functions do not exist.

- [x] **Step 3: Implement fixed report models**

Define DERIVATION_BINDING_CHECK_NAMES in this exact order: contract, schema_contract, oracle_identity, reference_standard, golden_coverage, parity_evidence, synthetic_fuzz_evidence, review, classification. Define DerivationBindingStatus with PASS, FAIL, and UNEVALUABLE.

DerivationBindingCheck has name, status, reason_code, compared_count, and mismatch_count. UNEVALUABLE forces counts to None. Evaluable checks require nonnegative counts and mismatch_count <= compared_count; PASS requires zero mismatches and OK; an OUTSIDE_POLICY or STRUCTURAL_INVALID failure requires a positive mismatch count.

DerivationBindingReport has binding_version, binding_id, schema_fingerprint, oracle_id, reference_standard_id, parity_report_id, status, status_counts, and checks. Require the fixed version, lowercase schema digest, exact check order, recomputed status counts, and FAIL > UNEVALUABLE > PASS precedence. Serialize only fixed aggregate fields; never include the complete binding or nested evidence.

The report also carries the safe oracle_id and reference_standard_id, plus parity_report_id when present, so a custodian can connect aggregate evidence without exposing patient/visit identifiers or source paths. These IDs use the same bounded aggregate-safe token validator as the binding and are suppressed to None when their owning evidence check is unevaluable.

- [x] **Step 4: Implement validate_derivation_binding**

Build the nine checks without opening or executing evidence bytes:

- contract passes only for derivation-binding-v1.
- schema_contract passes only when the binding schema equals the explicit expected fingerprint.
- oracle_identity passes only for complete valid oracle identities.
- reference_standard passes only for complete valid reference identities.
- golden_coverage passes only when the category set equals the fixed seven categories, the manifest identity is complete, and bidirectional_case_count is at least seven. Unknown categories or contradictory counts fail; incomplete coverage is unevaluable.
- parity_evidence passes only when parity_contract is derivation-parity-v1, report identity is complete, parity_status is PASS, candidate fingerprint equals oracle.implementation_fingerprint, parity_schema_fingerprint equals the top-level schema fingerprint, and a reference fingerprint is present. Declared FAIL or contradictory identity fails; missing evidence is unevaluable.
- synthetic_fuzz_evidence passes only for a positive count with a fingerprint. A positive count without a fingerprint fails. Zero/null evidence is unevaluable for non-test bindings and remains development-only unevaluable for test-only bindings.
- review passes only for complete identity, timestamp, role, and APPROVED. REJECTED fails; pending/absent evidence is unevaluable.
- classification passes for test_only true unless an explicit contradiction or rejected review exists. For test_only false, every evidence/review check must pass; missing evidence is unevaluable and contradictory evidence fails.

Suppress counts and details for unevaluable checks. Never convert missing values to passing zero evidence.

- [x] **Step 5: Implement the approval helper**

require_approved_derivation_binding calls the evaluator with the explicit expected fingerprint and raises DerivationBindingUnavailable unless the report is PASS, test_only is false, parity_status is PASS, review.status is APPROVED, and candidate/parity/schema identities match. The exception contains no binding or report values.

- [x] **Step 6: Run focused evaluator tests and lint**

~~~sh
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_derivation_binding_models.py tests/synthetic/test_derivation_binding_evaluation.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/derivation_binding.py tests/synthetic/test_derivation_binding_models.py tests/synthetic/test_derivation_binding_evaluation.py
~~~

Expected: focused tests pass and Ruff reports All checks passed!

- [x] **Step 7: Commit the evaluator slice**

~~~sh
git add src/synthetic/derivation_binding.py tests/synthetic/test_derivation_binding_evaluation.py
git commit -m "feat: validate derivation binding evidence"
~~~

---

### Task 3: Enforce binding-to-oracle identity at package generation

**Files:**

- Modify: src/synthetic/derivation_binding.py
- Modify: src/synthetic/package_export.py
- Modify: src/synthetic/generate.py
- Modify: tests/synthetic/fakes.py
- Modify: tests/synthetic/test_package_export.py
- Modify: tests/synthetic/test_package_export_boundaries.py
- Modify: tests/synthetic/test_generate_smoke.py
- Create: tests/synthetic/test_derivation_binding_integration.py
- Modify: tests/synthetic/test_observed_resource_package_export.py
- Modify: tests/synthetic/test_counterfactual_package_export.py
- Modify: tests/synthetic/test_counterfactual_package_export_boundaries.py
- Modify: tests/synthetic/test_cohort_resources.py
- Modify: docs/synthetic-generator.md
- Modify: docs/superpowers/specs/2026-08-31-counterfactual-package-export-design.md
- Modify: docs/superpowers/specs/2026-08-31-observed-resource-package-export-design.md

**Interfaces:**

- Produces BoundDerivationOracle(oracle: DerivationOracle, binding: DerivationBinding, *, expected_schema_fingerprint: str = EXPECTED_SCHEMA_FINGERPRINT) with oracle_id and derive(package_root, descriptor) -> DerivationResult.
- export_exact_schema_package and export_observed_resource_package replace trusted_derivation_fingerprint and trusted_derivation_test_only with required keyword derivation_binding: DerivationBinding.
- generate_smoke uses the same derivation_binding keyword.
- Existing fictional test-oracle behavior remains available through a test-only binding fixture.

- [x] **Step 1: Write failing integration tests**

Assert that a matching fake oracle is delegated exactly once for a valid test-only binding; declared oracle ID mismatch, returned ID mismatch, returned fingerprint mismatch, and returned test_only mismatch raise fixed redacted failures. Assert that a non-test binding with missing evidence is rejected before the underlying oracle is called and before augmented output is copied. Assert that a complete approved non-test binding preserves existing base hashes, augmented outputs, structural validation, and manifests. Assert that all three exporter/generator entry points reject calls omitting derivation_binding. Assert that test package manifests retain the fingerprint and test-only marker but contain no binding evidence, review IDs, parity IDs, or hidden truth. Static scans must still find no path reader, real-data import, network call, Synthea import, or implicit binding invocation outside the explicit argument path.

- [x] **Step 2: Run integration tests and verify expected failure**

~~~sh
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_derivation_binding_integration.py tests/synthetic/test_package_export.py tests/synthetic/test_generate_smoke.py
~~~

Expected: collection or signature failures show the old loose exporter/generator contract.

- [x] **Step 3: Implement BoundDerivationOracle**

The constructor validates the binding against EXPECTED_SCHEMA_FINGERPRINT. For test-only bindings, reject only a FAIL report and permit UNEVALUABLE development evidence. For non-test bindings, call require_approved_derivation_binding before any staging directory or output file is created. Verify the underlying oracle exposes a nonempty oracle_id equal to binding.oracle.oracle_id.

derive delegates once and requires a DerivationResult-shaped return whose oracle_id, implementation_fingerprint, and test_only exactly equal the binding identities. Do not inspect arbitrary result attributes, retain rows, or include caller text in errors.

- [x] **Step 4: Replace loose exporter/generator trust arguments**

Update _validate_preflight and both package-export entry points so the caller supplies derivation_binding. Instantiate BoundDerivationOracle during preflight and use its derive method for isolated staging. Remove the old trusted fingerprint/classification parameters from all public and internal call sites; do not leave a compatibility path that bypasses the binding. Retain every existing lifecycle, descriptor, base-hash, unexpected-file, structural, and manifest check.

Update generate_smoke similarly. Add test_derivation_binding() to tests/synthetic/fakes.py using the fake oracle's fixed identity and test-only classification. Update every existing package/generator test and documentation example call to pass that fixture. Keep generate.main unavailable and unchanged.

- [x] **Step 5: Run integration tests and lint**

~~~sh
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_derivation_binding_models.py tests/synthetic/test_derivation_binding_evaluation.py tests/synthetic/test_derivation_binding_integration.py tests/synthetic/test_package_export.py tests/synthetic/test_package_export_boundaries.py tests/synthetic/test_generate_smoke.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/derivation_binding.py src/synthetic/package_export.py src/synthetic/generate.py tests/synthetic/fakes.py tests/synthetic/test_derivation_binding_integration.py tests/synthetic/test_package_export.py tests/synthetic/test_package_export_boundaries.py tests/synthetic/test_generate_smoke.py
~~~

Expected: focused tests pass and Ruff is clean.

- [x] **Step 6: Commit the integration slice**

~~~sh
git add src/synthetic/derivation_binding.py src/synthetic/package_export.py src/synthetic/generate.py tests/synthetic/fakes.py tests/synthetic/test_package_export.py tests/synthetic/test_package_export_boundaries.py tests/synthetic/test_generate_smoke.py tests/synthetic/test_derivation_binding_integration.py
git commit -m "feat: enforce derivation binding at export"
~~~

---

### Task 4: Document the handoff and preserve all boundaries

**Files:**

- Modify: docs/synthetic-generator.md
- Modify: README.md
- Modify: tests/synthetic/test_derivation_binding_boundaries.py
- Create: tests/synthetic/test_derivation_binding_docs.py

**Interfaces:**

- Consumes the final model, evaluator, and explicit exporter signatures from Tasks 1–3.
- Produces user-facing instructions for supplying an already-loaded binding and a boundary test proving the production CLI remains unavailable without an approved oracle.

- [x] **Step 1: Write failing documentation and boundary tests**

Assert that the guide and README state the binding version, all seven required categories, test-only versus approved non-test behavior, aggregate-only/no-row/no-path/no-secret serialization, FAIL > UNEVALUABLE > PASS, the explicit derivation_binding argument, no external harness execution, continued CLI fail-closed behavior, and the fact that software validation is not clinical, privacy, prevalence, Synthea, or release authorization. Add source scans rejecting imports or calls from calibration, held-out, privacy, native trajectory, temporal, prevalence, or Synthea modules except through the explicit exporter/generator parameter path.

- [x] **Step 2: Run documentation tests and verify expected failure**

~~~sh
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_derivation_binding_docs.py tests/synthetic/test_derivation_binding_boundaries.py
~~~

Expected: assertions fail because the guide and README do not yet describe the binding contract.

- [x] **Step 3: Update the guide and README**

Add an authoritative derivation binding section immediately after the parity section. Show a fictional test-only DerivationBinding.from_mapping example and an explicit exporter call, but no real paths, rows, review prose, or production secrets. Explain that the custodian retains golden inputs/outputs, fuzz rows, and parity report bytes; only safe IDs/digests are recorded in the repository. State that an approved binding is necessary but not sufficient for clinical or release claims and that Synthea remains an optional later engine-conformance route.

Replace every old example passing trusted_derivation_fingerprint or trusted_derivation_test_only with derivation_binding=. Keep IdentityPreservingTestDerivationOracle explicitly test-only and keep the command-line failure text unchanged.

- [x] **Step 4: Run docs/boundary tests and lint**

~~~sh
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_derivation_binding_docs.py tests/synthetic/test_derivation_binding_boundaries.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests
~~~

Expected: all documentation/boundary tests pass and Ruff reports All checks passed!

- [x] **Step 5: Commit documentation and boundary coverage**

~~~sh
git add README.md docs/synthetic-generator.md tests/synthetic/test_derivation_binding_boundaries.py tests/synthetic/test_derivation_binding_docs.py
git commit -m "docs: document derivation binding handoff"
~~~

---

### Task 5: Final verification and handoff evidence

**Files:**

- Modify: docs/superpowers/plans/2026-09-01-derivation-oracle-binding.md to mark completed checkboxes and record verification evidence.
- Create (ignored SDD workspace): .superpowers/sdd/2026-09-01-derivation-oracle-binding/progress.md and per-task review reports.

- [x] **Step 1: Run the full repository verification matrix**

Run each command separately from the isolated worktree and retain complete output in the SDD evidence directory:

~~~sh
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv lock --check
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run python schema/build.py --check
git diff --check 603b874e4ddecff2ddaa91136a7146d6bc40e19b..HEAD
~~~

Expected: full suite passes with zero failures, Ruff is clean, lockfile resolves, eight resources validate, and diff check emits no output.

- [x] **Step 2: Run deterministic and redaction checks**

Construct the same fictional binding twice, call to_json_bytes twice, and assert byte equality and unchanged input mappings. Scan binding/report mappings, JSON bytes, reprs, and fixed exceptions for patient, visit, row, path, truth, secret, slash, and the fictional IDs used only in input fixtures. Assert no report contains nested evidence, arbitrary review text, or rows.

- [x] **Step 3: Perform fresh broad review**

Package the complete feature diff and dispatch a final reviewer on the most capable available model. The review must independently trace the spec, all five tasks, the exporter boundary, exact redaction, and no-real-data/no-Synthea boundary. Resolve every Critical/Important finding in one consolidated fix wave, rerun focused review, and record residual Minor rulings in the SDD ledger.

- [ ] **Step 4: Verify integration state before merge**

Confirm the feature worktree is clean except ignored SDD evidence, inspect staged names/stat/whitespace, verify git log contains only scoped commits after 603b874, and run git rev-parse HEAD. Do not remove unrelated caches or existing worktrees.

- [ ] **Step 5: Merge and push only after review and verification**

From the main checkout, fast-forward main to the reviewed feature tip, push origin main, fetch origin main, and verify git rev-parse HEAD equals git rev-parse origin/main. Preserve pre-existing untracked __pycache__ directories. Record the final hash and verification outputs in the completion evidence.
