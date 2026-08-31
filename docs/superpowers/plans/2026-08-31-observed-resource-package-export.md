# Observed Resource Exact-Schema Package Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bridge validated fictional observed-resource bundles into deterministic exact-PPOC-schema packages while preserving the trusted derivation and non-overwriting lifecycle.

**Architecture:** A new `synthetic.package_export` module owns strict export metadata, exact-schema/base-row normalization, staged derivation-oracle execution, structural validation, synthetic descriptor/manifest creation, and atomic promotion. `export_observed_resource_package` validates and deterministically merges immutable `ObservedResourceBundle` values before calling that shared lifecycle; `generate_smoke` delegates its existing base-row path to the same lifecycle so two exporters cannot drift.

**Tech Stack:** Python 3.12+, standard-library dataclasses/collections/copy/hashlib/json/pathlib/shutil/stat/tempfile, existing `DerivationOracle`, `RunDirectory`, `write_resource`, `write_synthetic_descriptor`, `validate_structure`, pytest, Ruff, and the repository schema checker.

**Spec:** `docs/superpowers/specs/2026-08-31-observed-resource-package-export-design.md`

## Global Constraints

- The descriptor argument to the new package APIs is an already-loaded mapping; no descriptor path, real-data path, CSV reader, calibration artifact, held-out report, privacy input, Synthea module, or CLI flag is accepted.
- The descriptor must have exactly the repository's eight resources and fingerprint `795724ec4838df8afa9c09b7c059fa76f644d7f8fb6dcc8ce808da203c2f8597`; expose this value once as `EXPECTED_SCHEMA_FINGERPRINT` from `synthetic.schema_contract`.
- Base input keys are exactly `patients`, `visits`, `labs`, `medications`, `problem_list`, and `referrals`; augmented rows are never caller input and may be supplied only by the injected derivation oracle.
- Bundle input is completely fictional, every bundle validation must be `PASS`, patient IDs and visit IDs must be globally unique, and bundle order is normalized by synthetic patient ID before merging.
- Output contains exactly the eight descriptor-named CSVs plus `datapackage.json`, `validation-report.json`, and `manifest.json`; no truth manifest, source frame, evaluator report, calibration artifact, held-out report, privacy report, or arbitrary extra file is exported.
- The exporter writes descriptor field order, declared dialect, declared encoding, and empty-string missing values; all rows are materialized and key-ordered before output creation.
- Derivation runs exactly once in a private staging directory; staged base hashes must remain unchanged, only the two descriptor-named augmented files may return, and oracle identity, trusted fingerprint, and test-only classification must match.
- Existing `RunDirectory` no-replace promotion and partial/failed paths are preserved. Post-creation failure archives only `{"status":"FAILED","reason":"observed package export failed"}`; raw errors and identifiers never enter public errors or artifacts.
- The exporter performs no random draws and does not import calibration, calibration-input, held-out, privacy, real-data, or Synthea modules. Structural/deterministic success is not prevalence, clinical, privacy/non-matchability, task-utility, release, or Synthea evidence.
- Existing smoke generation and fail-closed CLI behavior remain compatible; all new Python APIs require explicit injected metadata and derivation dependencies.

---

### Task 1: Implement strict metadata and shared exact-schema package lifecycle

**Files:**
- Create: `src/synthetic/package_export.py`
- Modify: `src/synthetic/schema_contract.py`
- Modify: `src/synthetic/manifest.py`
- Create: `tests/synthetic/test_package_export.py`

**Interfaces:**
- Consumes: `Mapping` descriptors, six-resource `base_rows`, `DerivationOracle`, `RunDirectory`, `write_resource`, `write_synthetic_descriptor`, and `validate_structure`.
- Produces: `PackageExportMetadata`, `PackageExportUnavailable`, `export_exact_schema_package(...) -> Path`, and `EXPECTED_SCHEMA_FINGERPRINT`.

- [ ] **Step 1: Write failing metadata, schema, and lifecycle tests**

  Add tests for the exact metadata fields and digest/token validation, the exported repository fingerprint, JSON-compatible descriptor copying, exact eight-resource rejection, six-resource row-key/order validation, and no augmented-row caller input. Build a fictional six-resource `base_rows` mapping from the existing checked-in descriptor and use `IdentityPreservingTestDerivationOracle` to assert that `export_exact_schema_package` produces exactly the eight descriptor CSVs plus `datapackage.json`, `validation-report.json`, and `manifest.json`. Assert generated descriptor `x-synthetic` is true, schema fingerprint is unchanged, the manifest uses the supplied profile/metadata and test-only status, structural validation has no errors, and all files are deterministic across two fresh destinations.

  Add negative tests for missing/unknown resources, changed field order/fingerprint, unsafe descriptor paths, malformed/non-finite row values, missing oracle, invalid trusted fingerprints, mismatched oracle fingerprint/classification, oracle base mutation, oracle extra artifact, missing augmented output, output collision, and failure-artifact redaction. Assert no patient/visit token, source frame, truth, or raw temporary path occurs in public exception text or `failure.json`.

- [ ] **Step 2: Run the new tests to verify they fail**

  Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_package_export.py`

  Expected: collection or assertion failures because `synthetic.package_export` and `EXPECTED_SCHEMA_FINGERPRINT` do not yet exist.

- [ ] **Step 3: Implement strict metadata, descriptor normalization, and export lifecycle**

  Add the following public shape and preserve the exact argument order:

  ```python
  @dataclass(frozen=True)
  class PackageExportMetadata:
      profile: str
      seed: int
      reference_time: str
      reference_id: str
      software_revision: str
      configuration_sha256: str
      reference_sha256: str | None = None

  def export_exact_schema_package(
      descriptor: Mapping[str, object],
      base_rows: Mapping[str, Iterable[Mapping[str, object]]],
      output: Path,
      *,
      metadata: PackageExportMetadata,
      derivation_oracle: DerivationOracle,
      trusted_derivation_fingerprint: str,
      trusted_derivation_test_only: bool,
  ) -> Path: ...
  ```

  Validate metadata before filesystem creation; copy the descriptor through JSON-compatible in-memory data; require `schema_fingerprint(copy) == EXPECTED_SCHEMA_FINGERPRINT`; materialize rows with exact `BASE_RESOURCES` keys and descriptor field-key tuples; and reject booleans, non-finite numbers, augmented caller rows, and unsafe paths. Add `EXPECTED_SCHEMA_FINGERPRINT` to `schema_contract.py` and a generic `RunManifest.generated(...)` constructor that retains the existing manifest fields while accepting the supplied profile.

  Move or share the existing `_allowed_tree`/`_scan_tree` logic in `package_export.py` without weakening its regular-file, symlink, or unexpected-entry checks. Use `RunDirectory.start` with the existing stable seed/patient-count/reference-time token shape, write six base files with `write_resource`, run the oracle once against staged copies, hash/check immutable bases, require exactly the two descriptor-named augmented outputs, copy only those outputs, call `validate_structure`, write the generated descriptor/report/manifest, and promote. Wrap post-creation failures in `PackageExportUnavailable` and call `run.fail` only with the fixed redacted reason.

- [ ] **Step 4: Run lifecycle tests, existing smoke tests, Ruff, and diff checks**

  Run:

  ```sh
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_package_export.py tests/synthetic/test_generate_smoke.py tests/synthetic/test_structural_validation.py tests/synthetic/test_run_directory.py
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/package_export.py src/synthetic/schema_contract.py src/synthetic/manifest.py tests/synthetic/test_package_export.py tests/synthetic/test_generate_smoke.py
  git diff --check
  ```

- [ ] **Step 5: Commit**

  ```sh
  git add src/synthetic/package_export.py src/synthetic/schema_contract.py src/synthetic/manifest.py tests/synthetic/test_package_export.py
  git commit -m "feat: add exact-schema package export lifecycle"
  ```

### Task 2: Merge observed bundles and reuse the lifecycle from smoke generation

**Files:**
- Modify: `src/synthetic/package_export.py`
- Modify: `src/synthetic/generate.py`
- Create: `tests/synthetic/test_observed_resource_package_export.py`
- Modify: `tests/synthetic/test_generate_smoke.py` only when a compatibility regression needs a focused assertion.

**Interfaces:**
- Consumes: `ObservedResourceBundle`, `ResourceShape`, `validate_observed_resources`, Task 1's `PackageExportMetadata`, and `export_exact_schema_package`.
- Produces: `export_observed_resource_package(bundles, descriptor, output, *, metadata, derivation_oracle, trusted_derivation_fingerprint, trusted_derivation_test_only) -> Path` and a smoke generator that delegates to the shared lifecycle.

- [ ] **Step 1: Write failing observed-bundle and smoke-delegation tests**

  Create two or more compatible fictional bundles from the existing observation fixture, project them, and assert that a package contains one patient row per bundle, all visits in deterministic synthetic-patient order, empty ancillary CSVs, fixed fictional diagnosis slots, and valid augmented rows from the test oracle. Export the same bundles in reversed iterable order and compare every non-manifest file plus manifest contents. Assert package files and reports contain no `ObservationFrame`, truth hashes, stream identities, private opportunity values, or source-frame tokens.

  Add tests that a non-PASS bundle, empty iterable, shape mismatch, duplicate patient ID, duplicate visit ID, and malformed row are rejected before any target/partial/failed path is created. Assert `generate_smoke` still emits the existing smoke profile, row counts, run-token behavior, manifest fields, and fail-closed CLI message while using the shared lifecycle; keep the existing `_scan_tree` import compatibility test.

- [ ] **Step 2: Run the observed-bundle tests to verify they fail**

  Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_observed_resource_package_export.py tests/synthetic/test_generate_smoke.py`

  Expected: collection failure for the missing bundle exporter, followed by the expected delegation assertions once the test imports are fixed.

- [ ] **Step 3: Implement deterministic bundle merging and smoke delegation**

  Implement `export_observed_resource_package` with the exact signature above. Materialize a nonempty iterable, require `validate_observed_resources(bundle).status is PASS` for every item, require `bundle.shape == ResourceShape.from_descriptor(descriptor)`, reject duplicate synthetic patient/visit identifiers without echoing them, sort by patient ID, and pass only `row.to_mapping()` values for the six base resources into `export_exact_schema_package`. Do not pass bundle objects, source frames, descendants, hidden truth, or evaluator reports to the oracle.

  Refactor `generate_smoke` only enough to construct `PackageExportMetadata(profile="smoke", ...)` and call `export_exact_schema_package`; preserve its public signature, configuration hash, reference digest behavior, run token, `_scan_tree` compatibility, and explicit unavailable-oracle CLI. No random stream, trajectory, or clinical behavior changes are allowed in this task.

- [ ] **Step 4: Run focused integration tests, full synthetic regression, Ruff, and diff checks**

  Run:

  ```sh
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_observed_resource_package_export.py tests/synthetic/test_generate_smoke.py tests/synthetic/test_observed_resource_models.py tests/synthetic/test_observed_resource_projection.py tests/synthetic/test_observed_resource_validation.py tests/synthetic/test_observed_resource_boundaries.py
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests
  git diff --check
  ```

- [ ] **Step 5: Commit**

  ```sh
  git add src/synthetic/package_export.py src/synthetic/generate.py tests/synthetic/test_observed_resource_package_export.py tests/synthetic/test_generate_smoke.py
  git commit -m "feat: export observed resources as exact-schema packages"
  ```

### Task 3: Document package usage and protect visible boundaries

**Files:**
- Modify: `docs/synthetic-generator.md`
- Modify: `README.md`
- Create: `tests/synthetic/test_package_export_boundaries.py`

**Interfaces:**
- Consumes: Task 1/2 package and bundle APIs, existing smoke/derivation contracts, and the parent synthetic-fixture claims boundary.
- Produces: a user-facing exact-schema package-export example, explicit test-only/oracle limitations, and structural regression tests.

- [ ] **Step 1: Write failing documentation and boundary tests**

  Add AST/import tests over `src/synthetic/package_export.py`, `src/synthetic/generate.py`, `src/synthetic/manifest.py`, `src/synthetic/native/`, and `src/synthetic/derivation.py` that reject imports or calls into calibration, calibration-input, held-out, privacy, real-data, Synthea, package-path readers, or random generation beyond existing smoke behavior. Assert no exporter API parameter is named `real_root`, `data_root`, `partition_key`, `heldout_report`, or `privacy_policy` and that the CLI still fails closed.

  Add documentation assertions for the exact API, already-loaded descriptor mapping, explicit injected test oracle, all eleven output files, redacted failure behavior, deterministic bundle sorting, and explicit deferrals to prevalence/demographic calibration, ancillary clinical pathways, held-out validation, privacy/non-matchability, task utility, clinical validity, release, and Synthea conformance.

- [ ] **Step 2: Run the boundary tests to verify they fail**

  Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_package_export_boundaries.py`

  Expected: failure because the package-export documentation and boundary test do not yet exist.

- [ ] **Step 3: Update documentation and implement boundary guards**

  Add an “Exact-schema observed-resource package export” section to `docs/synthetic-generator.md` with a complete Python example using `PackageExportMetadata`, `export_observed_resource_package`, and the existing test-only oracle. Explain that descriptor mappings are caller-loaded, bundles must already validate, augmented rows are oracle-owned, outputs are synthetic-only development artifacts, and package structural success is not privacy/non-matchability or prevalence evidence. Update the README observed-resource paragraph to point to this section and remove the stale statement that no package export exists while retaining all deferred-gate claims.

  Implement the boundary test with recursive AST parsing and attribute-call checks. Keep the production CLI unavailable and ensure package exporter imports remain limited to standard-library helpers plus existing schema, manifest, lifecycle, derivation, validation, CSV writer, and observed-resource contracts.

- [ ] **Step 4: Run documentation/boundary tests, full suite, Ruff, schema, and diff checks**

  Run:

  ```sh
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_package_export_boundaries.py tests/synthetic/test_observed_resource_package_export.py
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests
  python3 schema/build.py --check
  git diff --check
  ```

- [ ] **Step 5: Commit**

  ```sh
  git add docs/synthetic-generator.md README.md tests/synthetic/test_package_export_boundaries.py
  git commit -m "docs: explain observed resource package export"
  ```

### Task 4: Independent reviews and handoff

- [ ] Create `.superpowers/sdd/2026-08-31-observed-resource-package-export/progress.md` with this plan identity, a pre-flight conflict table, and implementation/review/fix entries for each task.
- [ ] Dispatch a fresh implementer and task reviewer for each task; resolve every Critical/Important finding through implementer-only fix rounds and one scoped re-review per round, recording any deferred Minor only in the ledger.
- [ ] Dispatch the most capable broad reviewer over the merge-base diff, resolve all Critical/Important findings with one complete fix wave and one scoped re-review, and record rulings before integration.
- [ ] From the feature worktree run the focused package/bundle suites, complete `pytest`, Ruff, schema validation, `git diff --check`, deterministic two-destination smoke, output-file inventory, and a leakage/boundary scan.
- [ ] Merge to `main`, rerun verification on merged `main`, push, verify `HEAD == origin/main`, and remove only this slice's worktree/branch/ignored SDD workspace.

## Completion evidence

- Implementation and fix commit IDs, task-review verdicts, broad-review verdict, focused/full test counts, schema/lint/diff output, deterministic package smoke result, exact output inventory, merge/push parity, and cleanup evidence are recorded before handoff.
