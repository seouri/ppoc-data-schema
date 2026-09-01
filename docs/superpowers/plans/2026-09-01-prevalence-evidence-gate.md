# Governed Multi-Run Prevalence Evidence Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a governed, aggregate-only multi-seed evidence gate that binds exact generated packages to their manifests and evaluates v1 demographic and recorded-outcome prevalence marginals against patient-disjoint held-out aggregates.

**Architecture:** Keep generation and the existing one-package held-out validator unchanged. Add a governed `synthetic.prevalence_evidence` module with strict package/manifest verification, an immutable multi-run configuration, per-run held-out evaluation, deterministic worst-case aggregate comparisons, and a redacted transactional writer/CLI. Use a separate aggregate report model so no hidden truth or patient-level evidence crosses into the output.

**Tech Stack:** Python 3.12+, standard-library dataclasses/hashlib/json/os/stat/pathlib, existing DuckDB-backed held-out validator and schema contract, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-01-prevalence-evidence-gate.md`

## Global Constraints

- Require at least three predeclared distinct expected seeds by default; never infer or adapt seeds from package contents.
- Accept only exact generated manifests with `metadata_only=false`, `status=STRUCTURE_VALIDATED`, matching file hashes, row counts, schema, and non-test derivation identity; reject test-only manifests.
- Keep v1 target scope to `outcome_layer=observed` demographic and recorded-outcome marginals; latent and observable prevalence are diagnostics only and registry-v2 joint strata remain deferred.
- Require all runs and all required target cells to be evaluable and passing for aggregate `PASS`; any failure is `FAIL`, and missing/under-supported evidence is `UNEVALUABLE`.
- Never expose package paths, real roots, keys, patient/visit IDs, rows, sequences, supports, denominators, hidden labels, or truth hashes in public mappings, summaries, exceptions, or reports.
- Use no-replace transactional output with canonical JSON, ASCII summary, strict reparse, fixed redacted failure archive, and no output promotion after any hard input or lifecycle error.
- Do not import the new governed module from visible generation, native, manifest, derivation, or package-export paths; CI fixtures remain wholly synthetic.

---

### Task 1: Define strict manifest/package identity models

**Files:**
- Create: `src/synthetic/prevalence_evidence.py`
- Create: `tests/synthetic/test_prevalence_evidence_models.py`
- Create: `tests/synthetic/prevalence_evidence_fixtures.py`

**Interfaces:**
- Consumes: `HeldoutRunConfig`, `HeldoutValidationResult`, `HeldoutComparison`, `FidelityPolicy`, `CalibrationArtifact`, `schema_fingerprint`, and package descriptor/resource contracts.
- Produces: immutable `PrevalenceRunSpec`, `PrevalenceEvidenceConfig`, `PackageIdentity`, `PrevalenceRunEvidence`, `PrevalenceEvidenceUnavailable`, strict manifest/tree/hash helpers, and fixed constants for report version and v1 family scope.

- [ ] **Step 1: Write the failing model and parser tests**

  Build a fictional exact-schema package fixture with a generated-style manifest, then assert model validation rejects fewer than three runs, duplicate or boolean seeds, non-`Path` roots, duplicate roots, empty profile/identity fields, missing or test-only derivation fingerprints, and mismatched expected seeds. Assert strict parsing rejects unknown/missing manifest keys, duplicate JSON keys, BOM, nonfinite values, oversized input, wrong status/metadata-only/version, malformed digests, invalid row counts, and file-hash entries outside the descriptor inventory. Assert `PackageIdentity` mappings contain only safe digests/tokens and never path strings.

- [ ] **Step 2: Run the focused tests to verify the API is absent**

  Run:

  ```sh
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_prevalence_evidence_models.py
  ```

  Expected: collection or assembly failures because `synthetic.prevalence_evidence` does not yet expose the models. Correct only fixture syntax before implementation.

- [ ] **Step 3: Implement strict immutable models and package verification**

  Implement exact-key strict JSON loading with secure no-follow regular-file reads and fixed redacted errors. Parse every manifest field emitted by `RunManifest.generated`, enforce generated/non-test status and all type/digest/token constraints, require expected seed equality, and verify descriptor-declared resource paths, exact allowed tree, row counts from `validate_structure`, and each `file_sha256` byte digest. Compute a deterministic package digest from the sorted verified file-hash mapping and a separate manifest byte digest. Reject symlinks, hard links, path traversal, extra files, missing files, descriptor/schema mismatch, and package-root identity changes. Store no root path in public mappings.

- [ ] **Step 4: Run focused tests, lint, and commit**

  ```sh
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_prevalence_evidence_models.py
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/prevalence_evidence.py tests/synthetic/test_prevalence_evidence_models.py tests/synthetic/prevalence_evidence_fixtures.py
  git diff --check
  ```

  Commit:

  ```sh
  git add src/synthetic/prevalence_evidence.py tests/synthetic/test_prevalence_evidence_models.py tests/synthetic/prevalence_evidence_fixtures.py
  git commit -m "feat: bind prevalence evidence package identities"
  ```

### Task 2: Evaluate one package and aggregate v1 prevalence comparisons

**Files:**
- Modify: `src/synthetic/prevalence_evidence.py`
- Create: `tests/synthetic/test_prevalence_evidence_integration.py`

**Interfaces:**
- Consumes: Task 1 `PrevalenceEvidenceConfig` and `PackageIdentity`, plus `validate_heldout`, `HeldoutRunConfig`, `compare_targets`, `HeldoutComparison`, and fixed target registry functions.
- Produces: `PrevalenceComparison`, `PrevalenceRunResult`, `PrevalenceEvidenceReport`, `evaluate_prevalence_evidence(config)`, deterministic family/count helpers, and aggregate-only serialization mappings.

- [ ] **Step 1: Write failing evaluation tests**

  Create at least three manifest-capable fictional packages with distinct seeds and a held-out fixture. Assert a successful aggregate report filters out physiology/observation/utilization comparisons, retains only demographics and recorded outcomes, records each safe package/manifest digest and identity, and sorts runs and target keys deterministically. Mutate one package to create a target failure and assert aggregate `FAIL`; remove/under-support a required target and assert `UNEVALUABLE`; assert a package with latent/observable diagnostic names cannot enter the report. Assert any profile/configuration/reference/software/PRNG/seed-derivation/derivation/schema mismatch fails before target computation, and duplicate package roots or expected seeds fail closed.

- [ ] **Step 2: Run integration tests to verify evaluation is absent**

  Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_prevalence_evidence_integration.py`

  Expected: failures because `evaluate_prevalence_evidence` and aggregate models are missing. Fix only fixture construction errors before implementation.

- [ ] **Step 3: Implement per-run held-out evaluation and deterministic aggregation**

  Verify all package identities first and establish a canonical shared generation identity. For each package, create a `dataclasses.replace` copy of the held-out config with that package root and no output side effect, call the existing held-out evaluator, and retain only registered `demographics` and `recorded_outcome` comparisons. Reject any held-out result whose source/schema/policy identity is not shared. Aggregate by canonical target key with held-out value, generated min/max, maximum difference, tolerance, evaluable/pass/fail counts, and status. Use fail-over-unevaluable-over-pass precedence and require every run/cell to pass for aggregate `PASS`. Keep latent and observable layers out of target status and never mutate packages or feed results into generation.

- [ ] **Step 4: Run integration tests, lint, and commit**

  ```sh
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_prevalence_evidence_integration.py tests/synthetic/test_heldout_integration.py
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/prevalence_evidence.py tests/synthetic/test_prevalence_evidence_integration.py
  git diff --check
  ```

  Commit:

  ```sh
  git add src/synthetic/prevalence_evidence.py tests/synthetic/test_prevalence_evidence_integration.py
  git commit -m "feat: aggregate multi-run prevalence evidence"
  ```

### Task 3: Add redacted transactional report writer and CLI

**Files:**
- Modify: `src/synthetic/prevalence_evidence.py`
- Create: `tests/synthetic/test_prevalence_evidence_cli.py`

**Interfaces:**
- Consumes: `PrevalenceEvidenceReport`, `PrevalenceEvidenceResult`, `PrevalenceEvidenceConfig`, `RunDirectory`, and existing secure output helpers.
- Produces: `write_prevalence_evidence(result, output)`, canonical JSON/ASCII summary methods, and `python -m synthetic.prevalence_evidence` with every governed argument explicit.

- [ ] **Step 1: Write failing writer/CLI tests**

  Assert canonical JSON and summary round-trip exactly, no paths/keys/IDs/supports/denominators/raw rows appear, and reports include only safe aggregate identity and comparison fields. Assert output promotion for `PASS`, `FAIL`, and `UNEVALUABLE`, no overwrite or lifecycle collision, fixed redacted `failure.json` on write/reparse failure, and no promoted output after hard input failure. Assert CLI requires all explicit real/descriptor/snapshot/package-manifest/frozen-policy inputs and returns zero only for `PASS`; unknown flags and malformed inputs produce fixed redacted stderr.

- [ ] **Step 2: Run CLI tests to verify the lifecycle is absent**

  Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_prevalence_evidence_cli.py`

  Expected: failures because writer/parser/CLI interfaces are incomplete. Correct only fixture syntax before implementation.

- [ ] **Step 3: Implement canonical redacted output lifecycle and CLI**

  Add exact report parsing/validation, deterministic human summary, lifecycle identity derived only from safe report identity, exclusive fsynced writes, strict reparse, no-replace promotion, and fixed failure archival matching existing governed validators. Define an argument parser with explicit repeated package-root and expected-seed inputs plus all held-out policy/artifact/key files; redact parser and runtime errors; return exit status one for non-PASS evidence without disclosing details. Never echo any supplied path or partition key.

- [ ] **Step 4: Run CLI tests, lint, and commit**

  ```sh
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_prevalence_evidence_cli.py tests/synthetic/test_prevalence_evidence_integration.py
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/prevalence_evidence.py tests/synthetic/test_prevalence_evidence_cli.py
  git diff --check
  ```

  Commit:

  ```sh
  git add src/synthetic/prevalence_evidence.py tests/synthetic/test_prevalence_evidence_cli.py
  git commit -m "feat: publish prevalence evidence reports"
  ```

### Task 4: Protect boundaries and document governed use

**Files:**
- Modify: `docs/synthetic-generator.md`
- Modify: `README.md`
- Create: `tests/synthetic/test_prevalence_evidence_boundaries.py`
- Modify: `tests/synthetic/test_heldout_boundaries.py` only if shared documentation assertions need extension

**Interfaces:**
- Consumes: completed `synthetic.prevalence_evidence` API and current deferred-gate wording.
- Produces: explicit operator documentation, target-layer caveats, CLI example, and AST/import/redaction boundary tests proving visible generation remains isolated.

- [ ] **Step 1: Write failing docs/boundary tests**

  Assert documentation names the module/API, minimum predeclared seeds, exact manifest/package binding, recorded-vs-latent/observable scope, fail/unevaluable semantics, aggregate-only redaction, no adaptive prevalence forcing, explicit CLI inputs, and the unchanged Synthea/held-out/privacy/release caveats. AST-scan visible generator, native, manifest, derivation, and package-export roots to ensure they do not import `synthetic.prevalence_evidence`; scan the governed module for no visible-generator import or hidden-truth serialization path.

- [ ] **Step 2: Run boundary tests to verify the documentation is absent**

  Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_prevalence_evidence_boundaries.py tests/synthetic/test_heldout_boundaries.py`

  Expected: failures for missing documentation and boundary assertions. Correct only test-fixture syntax before implementation.

- [ ] **Step 3: Implement documentation and boundary assertions**

  Add a concise governed-use section with a command template that uses explicit repeated package roots and seeds, explain that only observed demographic/recorded-outcome marginals are evidence, and state that latent/observable prevalence, clinical validity, privacy/non-matchability, task utility, Synthea conformance, and release remain separate gates. Extend AST deny lists only for visible roots; do not make the new governed module visible to generation.

- [ ] **Step 4: Run boundary tests, lint, and commit**

  ```sh
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_prevalence_evidence_boundaries.py tests/synthetic/test_heldout_boundaries.py
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/prevalence_evidence.py tests/synthetic/test_prevalence_evidence_boundaries.py
  git diff --check
  ```

  Commit:

  ```sh
  git add src/synthetic/prevalence_evidence.py tests/synthetic/test_prevalence_evidence_boundaries.py docs/synthetic-generator.md README.md tests/synthetic/test_heldout_boundaries.py
  git commit -m "docs: govern prevalence evidence boundary"
  ```

### Task 5: Whole-branch verification and handoff

**Files:**
- Modify: `docs/superpowers/plans/2026-09-01-prevalence-evidence-gate.md` (check completed steps and add completion evidence)
- Create: `.superpowers/sdd/2026-09-01-prevalence-evidence-gate/broad-review.md` (git-ignored review artifact)

**Interfaces:**
- Consumes: all prior tasks and the spec.
- Produces: evidence that the full synthetic suite, focused boundary/lifecycle tests, Ruff, lock, schema, and diff checks pass before integration.

- [ ] **Step 1: Run the full verification matrix**

  ```sh
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run uv lock --check
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run python schema/build.py --check
  git diff --check
  ```

- [ ] **Step 2: Record broad review and completion evidence**

  Use a fresh architecture-level reviewer to inspect the complete diff against the spec, record findings and rulings in `.superpowers/sdd/2026-09-01-prevalence-evidence-gate/broad-review.md`, update this plan with commit IDs and verification output, and leave unrelated pre-existing caches/worktrees untouched.

- [ ] **Step 3: Commit plan metadata and prepare integration**

  ```sh
  git add docs/superpowers/plans/2026-09-01-prevalence-evidence-gate.md
  git commit -m "docs: record prevalence evidence integration"
  ```

  Then use `superpowers:finishing-a-development-branch` to merge the reviewed branch to `main`, push it, and verify `HEAD` equals `origin/main`.
