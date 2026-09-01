# Pair-Aware Exact-Schema Counterfactual Package Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export one validated fictional `CounterfactualEhrWorldPair` as two independently usable exact-schema PPOC packages inside one atomic, truth-free pair envelope.

**Architecture:** Add `export_counterfactual_ehr_world_pair` to the existing package-export boundary. It validates the pair, projects only each world's six visible resource-row mappings, invokes the existing `export_exact_schema_package` lifecycle once per child in private staging, then atomically promotes `baseline/`, `intervention/`, and a redacted `pair-manifest.json` with one outer `RunDirectory`. The existing generic `export_observed_resource_package` remains unchanged because its generic bundle validator intentionally rejects nonempty ancillary rows.

**Tech Stack:** Python 3.12+, standard-library dataclasses/json/hashlib/pathlib/shutil/tempfile, existing counterfactual-world/resource/schema/package-export/run-directory/derivation contracts, pytest, Ruff, `uv`, and the repository schema checker.

**Spec:** `docs/superpowers/specs/2026-08-31-counterfactual-package-export-design.md`

## Global Constraints

- Accept only a typed `CounterfactualEhrWorldPair`, an already-loaded descriptor mapping, a new output `Path`, explicit `PackageExportMetadata`, and explicit derivation-oracle trust values; never accept a descriptor path, real/governed data root, calibration, held-out, privacy, model, Synthea, or network input.
- Require `validate_counterfactual_ehr_worlds(worlds).status is PASS` before creating any caller-visible target, partial path, failed path, or pair manifest.
- Project only visible six-resource row mappings from the baseline/intervention bundles; for serialization, map only the exact GHD evaluator marker `labs.result_flag="Synthetic"` on GHD component rows to the descriptor missing-value sentinel `""` under fixed `serialization_projection` token `ghd-result-flag-empty-v1`; never mutate worlds or silently normalize any other value. Never pass pair objects, frames, truth, trajectories, reports, source objects, seeds/indexes, stream identities, or descriptors to the oracle or visible pair manifest.
- Do not call `export_observed_resource_package`; valid counterfactual bundles may contain nonempty GHD ancillary rows that its generic validator rejects. Reuse `export_exact_schema_package` so the six visible rows and the two oracle-owned augmented resources use the existing exact-schema lifecycle.
- Public output is exactly `pair-manifest.json`, `baseline/`, and `intervention/`; each child contains the existing eight descriptor-named CSVs plus `datapackage.json`, `validation-report.json`, and `manifest.json`.
- Use one outer no-replace `RunDirectory`; private child staging is temporary and removed automatically. Post-creation failures use fixed redacted `counterfactual package export failed` content and never overwrite an existing target.
- Pair manifests contain only fixed contract/matrix/`serialization_projection`/aggregate status, visible caller metadata, relative child paths, and child manifest SHA-256 digests. No patient/visit IDs, row values, ages, latent states, event payloads, truth hashes, or evaluator representations may appear.
- The exporter performs no random draws, leaves the existing smoke/observed exporters and generic validators behaviorally unchanged, and makes no prevalence, clinical, privacy, non-matchability, release, or Synthea claim.
- Controller edits only this plan/spec and ignored SDD evidence; all source, test, and user-facing documentation edits are delegated.

---

### Task 1: Add the pair API and atomic envelope lifecycle

**Files:**

- Modify: `src/synthetic/package_export.py`
- Create: `tests/synthetic/test_counterfactual_package_export.py`

**Interfaces:**

- Consumes: `CounterfactualEhrWorldPair`, `validate_counterfactual_ehr_worlds`, `PackageExportMetadata`, `export_exact_schema_package`, `RunDirectory`, and the existing schema/path helpers.
- Produces:

  ```python
  class CounterfactualPackageExportUnavailable(PackageExportUnavailable):
      """Fixed redacted pair-export failure."""

  def export_counterfactual_ehr_world_pair(
      worlds: CounterfactualEhrWorldPair,
      descriptor: Mapping[str, object],
      output: Path,
      *,
      metadata: PackageExportMetadata,
      derivation_oracle: DerivationOracle,
      trusted_derivation_fingerprint: str,
      trusted_derivation_test_only: bool,
  ) -> Path: ...
  ```

- [ ] **Step 1: Write failing API, output, and deterministic tests.**

  Build one valid physiology pair with the existing fictional fixture and
  `IdentityPreservingTestDerivationOracle`. Assert that the function returns a
  pair root containing only `pair-manifest.json`, `baseline/`, and
  `intervention/`; each child contains the exact eleven existing package
  files; both children pass `validate_structure`; and the pair manifest has
  the fixed contract token, exact schema fingerprint, matrix/intervention,
  `PASS` aggregate status/counts, the fixed GHD serialization projection,
  visible metadata, fixed child paths, and
  child manifest digests. Export the same pair to two fresh destinations and
  compare every byte recursively.

  The failing test should import the new function/class before they exist and
  assert the fixed call shape:

  ```python
  result = export_counterfactual_ehr_world_pair(
      worlds,
      descriptor,
      tmp_path / "pair",
      metadata=metadata,
      derivation_oracle=IdentityPreservingTestDerivationOracle(),
      trusted_derivation_fingerprint=TRUSTED_FINGERPRINT,
      trusted_derivation_test_only=True,
  )
  assert result == tmp_path / "pair"
  ```

- [ ] **Step 2: Run the new tests and verify the expected failure.**

  Run:

  ```sh
  UV_CACHE_DIR=/tmp/ppoc-uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q tests/synthetic/test_counterfactual_package_export.py
  ```

  Expected: collection fails because the pair-export API is not implemented.

- [ ] **Step 3: Implement the minimal pair lifecycle.**

  Add a fixed pair failure reason and a pair-specific run-start helper that
  preserves `FileExistsError` for the final target and deterministic partial/
  failed collisions while redacting all other lifecycle errors. Require a
  typed pair and aggregate `PASS`, extract only
  `member.bundle.rows[name]` mappings for each name in `BASE_RESOURCES`, apply
  only the fixed GHD evaluator-marker-to-missing serialization projection, and
  derive a stable outer run token from the visible metadata and matrix
  version/intervention. Do not read hidden pair seed/index values.

  In a private `TemporaryDirectory`, call
  `export_exact_schema_package` once for the baseline row mapping and once for
  the intervention row mapping, using the same descriptor, metadata, oracle,
  trusted fingerprint, and test-only flag. Start the outer `RunDirectory` only
  after both child packages succeed, copy them into `baseline/` and
  `intervention/`, compute each child `manifest.json` SHA-256, and write the
  canonical aggregate-only pair manifest. Build an exact allowed-file and
  allowed-directory set from all descriptor resource paths plus the three
  child artifacts, scan the outer partial tree, and promote once. On any
  post-creation error call `run.fail` only with
  `{"status":"FAILED","reason":"counterfactual package export failed"}`
  before raising the fixed pair exception.

- [ ] **Step 4: Run the lifecycle tests and commit.**

  Run:

  ```sh
  UV_CACHE_DIR=/tmp/ppoc-uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q tests/synthetic/test_counterfactual_package_export.py
  UV_CACHE_DIR=/tmp/ppoc-uv-cache PYTHONDONTWRITEBYTECODE=1 uv run ruff check src/synthetic/package_export.py tests/synthetic/test_counterfactual_package_export.py
  git diff --check
  ```

  Commit:

  ```sh
  git add src/synthetic/package_export.py tests/synthetic/test_counterfactual_package_export.py
  git commit -m "feat: export paired counterfactual packages"
  ```

### Task 2: Bind world validation, ancillary rows, and failure safety

**Files:**

- Modify: `src/synthetic/package_export.py`
- Modify: `tests/synthetic/test_counterfactual_package_export.py`

**Interfaces:**

- Consumes: Task 1's pair API and the integrated seven-check world validator.
- Produces: a pair exporter that preserves nonempty GHD ancillary rows, calls
  the oracle exactly twice with visible child staging only, and fails closed
  before or after public run creation with fixed redaction.

- [ ] **Step 1: Add failing safety and matrix tests.**

  Parameterize valid physiology, earlier-recognition, and treatment-adherence
  pairs. Assert each child retains its correct visible matrix differences and
  nonempty GHD `labs`, `medications`, `problem_list`, and `referrals` rows
  where the world validator permits them; assert both child structural reports
  pass. Add tests that an `UNEVALUABLE` or `FAIL` world, malformed bundle,
  descriptor, oracle, trusted fingerprint/classification, output collision,
  duplicate lifecycle sibling, or missing world bundle raises the fixed pair
  error before a final/partial/failed output exists.

  Use a recording oracle to assert exactly two calls, distinct child staging
  roots, only visible CSVs plus the descriptor mapping, and no
  `CounterfactualEhrWorldPair`, frame, truth, trajectory, report, or source
  object. Add post-creation failure tests by injecting a copy/tree or manifest
  failure and assert the failed sibling contains only fixed failure content,
  no raw exception, identifier, temporary path, or hidden token, and the final
  target is absent.

- [ ] **Step 2: Run the tests and confirm each new regression fails.**

  Run:

  ```sh
  UV_CACHE_DIR=/tmp/ppoc-uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q tests/synthetic/test_counterfactual_package_export.py
  ```

- [ ] **Step 3: Harden implementation without changing existing exporters.**

  Ensure pair preflight rejects non-PASS aggregate validation before any
  public lifecycle path, maps each visible `ResourceRow.to_mapping()` in
  descriptor/base order, applies only the fixed GHD evaluator-marker-to-missing
  projection, and passes all six resources—including nonempty GHD ancillary
  rows—through `export_exact_schema_package`. Keep the child oracle
  boundary and child structural validation delegated to the existing
  lifecycle. Scan copied child trees for symlinks, special files, missing
  resources, or arbitrary entries before writing the pair manifest. Preserve
  deterministic bytes, fixed child order, no-replace promotion, and fixed
  redacted errors.

- [ ] **Step 4: Run integration tests and commit.**

  Run:

  ```sh
  UV_CACHE_DIR=/tmp/ppoc-uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q tests/synthetic/test_counterfactual_package_export.py tests/synthetic/test_observed_resource_package_export.py tests/synthetic/test_generate_smoke.py
  UV_CACHE_DIR=/tmp/ppoc-uv-cache PYTHONDONTWRITEBYTECODE=1 uv run ruff check src/synthetic/package_export.py tests/synthetic/test_counterfactual_package_export.py
  git diff --check
  ```

  Commit:

  ```sh
  git add src/synthetic/package_export.py tests/synthetic/test_counterfactual_package_export.py
  git commit -m "test: harden counterfactual package export"
  ```

### Task 3: Document the pair envelope and protect package boundaries

**Files:**

- Modify: `docs/synthetic-generator.md`
- Modify: `README.md`
- Create: `tests/synthetic/test_counterfactual_package_export_boundaries.py`
- Modify: `tests/synthetic/test_package_export_boundaries.py` only to register
  the legitimate in-memory counterfactual imports/calls.

**Interfaces:**

- Consumes: Task 1/2's `export_counterfactual_ehr_world_pair` API, child
  package contract, and aggregate pair manifest.
- Produces: user-facing usage documentation and static regressions preventing
  filesystem, real/governed-data, calibration, held-out, privacy, model,
  network, Synthea, or hidden-truth leakage through the pair API.

- [ ] **Step 1: Write failing documentation and boundary tests.**

  Assert the guide and README name the exact function/class, explain the
  `baseline/` and `intervention/` child layout, list the pair manifest's
  aggregate-only fields, state that each child remains an exact eleven-file
  package, identify the explicit test-only oracle, and retain all prevalence,
  demographic, clinical, temporal-drift, task-utility, privacy/non-matchability,
  release, and Synthea deferrals. Assert the pair module/package-export AST
  has no forbidden imports, filesystem readers/writers beyond existing
  lifecycle helpers, path-like public arguments, hidden truth object names in
  mappings/reprs, or calls to `export_observed_resource_package`.

- [ ] **Step 2: Run the new tests to verify they fail before documentation/guards.**

  Run:

  ```sh
  UV_CACHE_DIR=/tmp/ppoc-uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q tests/synthetic/test_counterfactual_package_export_boundaries.py
  ```

- [ ] **Step 3: Implement documentation and boundary coverage.**

  Add a concise example that receives a previously assembled pair and a
  caller-loaded descriptor, invokes the pair exporter with explicit metadata
  and test-only oracle, and then passes `output / "baseline"` or
  `output / "intervention"` to ordinary structural/package tooling. State that
  the top-level envelope is not itself a PPOC package, the pair manifest is
  not a truth manifest, and successful structure is not prevalence, clinical,
  privacy, non-matchability, release, or Synthea evidence. Extend existing
  static allowlists only for the new in-memory world validator and API.

- [ ] **Step 4: Run docs/boundary tests and commit.**

  Run:

  ```sh
  UV_CACHE_DIR=/tmp/ppoc-uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q tests/synthetic/test_counterfactual_package_export_boundaries.py tests/synthetic/test_counterfactual_package_export.py
  UV_CACHE_DIR=/tmp/ppoc-uv-cache PYTHONDONTWRITEBYTECODE=1 uv run ruff check src tests
  python3 schema/build.py --check
  git diff --check
  ```

  Commit:

  ```sh
  git add docs/synthetic-generator.md README.md tests/synthetic/test_counterfactual_package_export_boundaries.py tests/synthetic/test_package_export_boundaries.py
  git commit -m "docs: document counterfactual package export"
  ```

### Task 4: Independent review, full verification, merge, and push

**Files:**

- Modify: this plan (checkbox/evidence metadata only)
- Create/modify: ignored `.superpowers/sdd/2026-08-31-counterfactual-package-export/` evidence

- [ ] **Step 1: Create the SDD ledger and run fresh scoped review after each task.**

  Record the plan identity, non-overlapping file ownership, implementation
  commits, review findings, fix rounds, exact fix ranges, and PASS verdicts.
  Every Critical/Important finding goes to an implementer for a bounded fix;
  the reviewer then rechecks only that exact range before the next task.

- [ ] **Step 2: Run a fresh broad review over the complete feature range.**

  Review matrix preservation, nonempty ancillary export, child exact-schema
  inventories, oracle/staging boundaries, deterministic bytes, pair-manifest
  redaction, no-replace/failure lifecycle, unchanged existing exporters,
  documentation, and prohibited imports/arguments. Resolve all Critical and
  Important findings through one consolidated implementer fix wave and one
  scoped re-review.

- [ ] **Step 3: Run final feature verification.**

  From the feature worktree run:

  ```sh
  UV_CACHE_DIR=/tmp/ppoc-uv-cache PYTHONDONTWRITEBYTECODE=1 uv run pytest -q
  UV_CACHE_DIR=/tmp/ppoc-uv-cache PYTHONDONTWRITEBYTECODE=1 uv run ruff check src tests
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv lock --check
  python3 schema/build.py --check
  git diff --check
  ```

  Also run a deterministic two-destination pair export, assert the exact
  `23`-entry recursive file inventory (22 child package files plus the pair
  manifest), compare all bytes, validate both child descriptors structurally,
  and scan every public artifact for truth/frame/source/evaluator tokens.
  Record exact outputs and any unchanged repository-wide lint baseline in the
  ignored SDD evidence.

- [ ] **Step 4: Merge and push.**

  Update only plan metadata with commit hashes and evidence. Merge the feature
  branch to `main` using `git merge --no-ff`, rerun the focused and full gates
  on merged `main`, push `origin main`, and verify:

  ```sh
  test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
  ```

  Retain the feature worktree and ignored SDD evidence for auditability; do
  not remove unrelated worktrees or generated files.

## Acceptance evidence template

- Implementation/review commits: pending.
- Scoped reviews and exact fix re-reviews: pending.
- Broad review: pending.
- Feature verification: pending.
- Merge/push parity: pending.

## Deferred roadmap gates

This slice does not satisfy authoritative augmented derivation, prevalence or
demographic calibration, held-out fidelity, temporal drift, task utility,
clinical validity, privacy/non-matchability, release authorization, or Synthea
conformance. The next item remains the separately designed prevalence and
demographic calibration/held-out evidence sequence; a Synthea adapter remains
optional and downstream of native conformance.
