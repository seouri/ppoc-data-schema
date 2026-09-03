# Source-Matched Augmenter Oracle Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a development-only `DerivationOracle` adapter that runs the byte-preserved augmenter CLI against staged synthetic package resources without enabling the production generator.

**Architecture:** The adapter verifies the checked-in 14-file runtime closure against the pinned manifest, snapshots that verified closure into a private temporary runtime root, and invokes the copied CLI with the current interpreter using `-E -s` and no shell. It accepts exactly the two timestamped CSV outputs, copies their bytes into descriptor-named augmented resources with exclusive creation, and returns a test-only derivation result; the existing package exporter remains responsible for schema and structural validation.

**Tech Stack:** Python 3.12+, standard-library `dataclasses`, `hashlib`, `json`, `os`, `pathlib`, `re`, `shutil`, `stat`, `subprocess`, `sys`, `tempfile`, existing `DerivationOracle`/`DerivationResult`/schema contracts, pytest, Ruff, uv, and the exact imported CLI/runtime data.

**Spec:** `docs/superpowers/specs/2026-09-01-augmenter-oracle-adapter-design.md`

## Global Constraints

- The adapter is development-only and always returns `DerivationResult(..., test_only=True)`; it must not change `generate.py`, the production CLI, or any authoritative binding.
- The copied runtime closure remains byte-identical; the adapter executes only a verified private snapshot of `scripts/augment.py`, `scripts/harrall_outliers.py`, the ten growth-reference CSVs, and `data/icd10cm-tabular-2026.csv`.
- The checked-in `data/augment-runtime-manifest.json` must match the fixed manifest SHA-256 `b50afc36eca61684380154129cdacf484e62d56fa6da55914adab18c2d94d1d6`; every listed file must be a regular non-symlink with the recorded size and digest.
- The supported subprocess command uses the current `sys.executable`, `-E -s`, no shell, private runtime `cwd`, private descriptor-relative synthetic input snapshot as `input_dir`, private output directory, and fixed `--output_format csv`.
- The output directory must contain exactly one `visits_augmented-YYYYMMDDHHMMSS.csv` and one `patients_augmented-YYYYMMDDHHMMSS.csv`, both regular non-symlink files; any other entry or duplicate fails closed.
- Only stable descriptor-named `visits_augmented.csv` and `patients_augmented.csv` destinations may be created, with exclusive creation and safe relative paths; base resources must remain byte-for-byte unchanged.
- Public failures use fixed `DerivationUnavailable` text and never expose subprocess output, input/output paths, rows, identifiers, diagnosis values, or runtime exception details.
- Tests and documentation use wholly synthetic exact-schema inputs; no patient, governed, calibration, held-out, privacy, network, or Synthea input is added, and the production command remains fail closed.
- The authoritative repository gate is `uv run ruff check src tests`; root and vendored-source Ruff findings remain informational because changing byte-preserved source is out of scope.

---

### Task 1: Implement the verified CLI oracle and focused tests

**Files:**

- Create: `src/synthetic/augmenter_oracle.py`
- Create: `tests/synthetic/test_augmenter_oracle.py`

**Interfaces:**

- Consumes: `data/augment-runtime-manifest.json`, the checked-in runtime closure, `synthetic.derivation.DerivationResult`, and descriptor `resource_spec` values.
- Produces: `AUGMENTER_ORACLE_ID = "augmenter-cli-v1"`, `AUGMENTER_RUNTIME_MANIFEST_SHA256 = "b50afc36eca61684380154129cdacf484e62d56fa6da55914adab18c2d94d1d6"`, and `SourceMatchedAugmenterOracle(repository_root: Path | None = None, *, timeout_seconds: float = 300.0)` with `oracle_id`, `implementation_fingerprint`, and `derive(package_root: Path, descriptor: dict[str, Any]) -> DerivationResult`.

- [x] **Step 1: Write the failing synthetic oracle tests.**

  Add a local helper that writes only `visits.csv`, `patients.csv`, and
  `problem_list.csv` with the exact descriptor headers and one or two fictional
  rows. Test `SourceMatchedAugmenterOracle().derive(...)` against that package
  root and assert `DerivationResult.oracle_id`, the fixed manifest fingerprint,
  and `test_only is True`. Assert that the two descriptor-named augmented files
  exist, have exact descriptor headers, and leave SHA-256 hashes of all three
  base files unchanged. Assert that the output directory is removed after
  return and no timestamped file remains in the package root.

  Add tests that monkeypatch `synthetic.augmenter_oracle.subprocess.run` and
  exercise the fixed failure boundary: a nonzero `returncode`, a
  `TimeoutExpired`, a missing runtime manifest, a changed manifest byte, an
  extra output file, an output directory, a symlinked expected output, duplicate
  timestamped outputs, an unsafe augmented descriptor path, and a pre-existing
  augmented destination. Each test must raise `DerivationUnavailable` with only
  the fixed message, make no augmented destination, and never include a fake
  path, subprocess stderr, or patient token. Include a test that verifies the
  subprocess command contains `-E`, `-s`, `--output_format`, and `csv`, uses
  `shell=False`, and runs with the private runtime root as `cwd`.

- [x] **Step 2: Run the focused tests to verify the red state.**

  Run:

  ```sh
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_augmenter_oracle.py
  ```

  Expected: collection fails because `synthetic.augmenter_oracle` and
  `SourceMatchedAugmenterOracle` do not yet exist.

- [x] **Step 3: Implement the minimal verified runtime bridge.**

  In `src/synthetic/augmenter_oracle.py`, define the fixed constants and a
  safe internal `DerivationUnavailable` helper that always raises
  `DerivationUnavailable("source-matched augmenter unavailable")` without
  chaining the underlying exception. Validate the constructor's optional
  repository root as a `Path` and require a finite positive timeout.

  Implement `_verify_manifest(root)` by reading the manifest bytes once,
  comparing the fixed manifest digest, parsing strict JSON, requiring the fixed
  version and exact 14-entry path set, and checking each entry's relative path,
  regular/non-symlink destination, byte count, lowercase digest, and file bytes.
  Implement `_snapshot_runtime(root, temporary_root)` by copying only those
  verified relative files with `xb`/exclusive writes, recreating `scripts/` and
  `data/`, and rechecking the copied bytes against the manifest before use.

  Implement `derive` to reject a missing, symlinked, or non-directory package
  root; load and validate the descriptor paths for the two augmented resources
  as safe relative paths; verify and snapshot the runtime in a
  `TemporaryDirectory`; copy the descriptor-named `visits`, `patients`, and
  `problem_list` base resources through a pinned package-root descriptor into
  a private descriptor-relative synthetic input snapshot; create a second
  private output directory; and invoke the CLI with that input snapshot:

  ```python
  subprocess.run(
      [
          sys.executable,
          "-E",
          "-s",
          str(runtime_root / "scripts" / "augment.py"),
          str(input_root),
          "--output_dir",
          str(output_root),
          "--output_format",
          "csv",
      ],
      cwd=runtime_root,
      shell=False,
      check=False,
      capture_output=True,
      timeout=self.timeout_seconds,
  )
  ```

  Treat any invocation exception or nonzero return code as the fixed
  unavailable error. Inspect the private output directory with `lstat` and
  require exactly one filename matching each
  `^(visits|patients)_augmented-[0-9]{14}\.csv$`; reject all other entries and
  symlinks. Read the two bytes, then exclusively create the descriptor paths
  beneath the package root after checking every path component is a safe
  non-symlink directory. Return `DerivationResult` only after both writes
  succeed. Do not import `synthetic.package_export`, the native generator, or
  any governed/evaluator module.

- [x] **Step 4: Run the focused tests and lint.**

  Run:

  ```sh
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_augmenter_oracle.py
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/augmenter_oracle.py tests/synthetic/test_augmenter_oracle.py
  ```

  Expected: all focused oracle tests pass and Ruff reports no errors.

- [x] **Step 5: Commit the core adapter task.**

  ```sh
  git add src/synthetic/augmenter_oracle.py tests/synthetic/test_augmenter_oracle.py
  git commit -m "feat: add source-matched augmenter oracle"
  ```

---

### Task 2: Document and protect the candidate boundary

**Files:**

- Create: `docs/augmenter-oracle.md`
- Modify: `README.md`
- Modify: `docs/synthetic-generator.md`
- Create: `tests/synthetic/test_augmenter_oracle_docs.py`
- Create: `tests/synthetic/test_augmenter_oracle_boundaries.py`

**Interfaces:**

- Consumes: `SourceMatchedAugmenterOracle`, the existing exact-schema package-export API, the imported-augmenter guide, and the fail-closed production CLI contract.
- Produces: a copy-pasteable synthetic-only candidate-oracle example, explicit test-only/non-authoritative language, and static regression checks that visible generation does not import the adapter.

- [x] **Step 1: Write failing documentation and boundary assertions.**

  Assert the new guide names `SourceMatchedAugmenterOracle`, the fixed oracle
  identity/fingerprint, the explicit staged-package contract, the private
  snapshot and `-E -s` subprocess boundary, exact two-output rule, test-only
  classification, and the non-authoritative/fail-closed caveats. Assert README
  and `docs/synthetic-generator.md` link the guide and retain the statement
  that the production command has no configured authoritative oracle.

  Parse Python files under `src/synthetic` with `ast` and assert the adapter
  imports only standard-library modules plus `synthetic.derivation` and
  `synthetic.schema_contract`, while `synthetic.generate`,
  `synthetic.package_export`, native modules, calibration, held-out, privacy,
  prevalence, and Synthea modules do not import `synthetic.augmenter_oracle`.
  Assert the existing production CLI failure text remains unchanged.

- [x] **Step 2: Run the documentation/boundary tests to verify the red state.**

  Run:

  ```sh
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_augmenter_oracle_docs.py tests/synthetic/test_augmenter_oracle_boundaries.py
  ```

  Expected: assertions fail because the guide, links, and boundary tests do
  not yet exist.

- [x] **Step 3: Add the guide and cross-document boundary language.**

  Create `docs/augmenter-oracle.md` with `uv sync`, a wholly synthetic input
  package requirement, a Python example that constructs the oracle and passes
  it explicitly to `export_exact_schema_package` with a matching test-only
  binding, the exact output/manifest expectations, and a warning not to use
  governed or real data. Explain that the adapter snapshots and executes the
  imported runtime, accepts CSV only, and leaves schema/structure validation to
  the exporter. State that the source-match and runtime hash do not prove
  clinical validity, prevalence or demographic fidelity, privacy or
  non-matchability, release readiness, or Synthea conformance.

  Link the new guide from README and the synthetic-generator guide. Keep the
  production `synthetic.generate` command fail closed and describe this oracle
  as a candidate that cannot become authoritative without the existing parity,
  golden, review, clinical, and release gates.

- [x] **Step 4: Run documentation/boundary tests and commit.**

  ```sh
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_augmenter_oracle_docs.py tests/synthetic/test_augmenter_oracle_boundaries.py
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests
  git -c core.whitespace=cr-at-eol,-blank-at-eof diff --check main..HEAD
  git add README.md docs/synthetic-generator.md docs/augmenter-oracle.md tests/synthetic/test_augmenter_oracle_docs.py tests/synthetic/test_augmenter_oracle_boundaries.py
  git commit -m "docs: bound augmenter oracle candidate"
  ```

---

### Task 3: Whole-branch verification and handoff

**Files:**

- Modify: `.superpowers/sdd/2026-09-01-augmenter-oracle-adapter/progress.md` (ignored ledger only)

**Interfaces:**

- Consumes: Task 1 and Task 2 commits, their focused reports, the source-matched runtime manifest, and the existing exact-schema test suite.
- Produces: a reviewed branch ready to merge without changing source bytes, patient data boundaries, native generation behavior, or remote branch state.

- [x] **Step 1: Run the complete verification matrix.**

  Run:

  ```sh
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests
  PYTHONDONTWRITEBYTECODE=1 python3 schema/build.py --check
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv lock --check
  git -c core.whitespace=cr-at-eol,-blank-at-eof diff --check main..HEAD
  ```

  Also compare every manifest-listed file with its source checkout bytes,
  check the fixed runtime fingerprint, run `uv run python scripts/augment.py
  --help`, scan tracked paths for patient/input/output artifacts, and scan
  visible synthetic modules for forbidden adapter imports. Record the exact
  outputs in the ignored ledger and report files.

- [x] **Step 2: Review each task and the whole branch.**

  Generate a review package from the merge base through `HEAD` and dispatch a
  fresh reviewer for each task plus one broad reviewer. Route every Critical
  or Important finding to the implementer through one fix/re-review loop per
  SDD rules; record Minor findings and rulings in the ledger. The final review
  must cover runtime snapshot integrity, subprocess isolation, output/path
  validation, failure redaction, synthetic-only boundaries, exact source-byte
  preservation, docs, and unchanged production fail-closed behavior.

- [x] **Step 3: Merge, verify, push, and confirm parity.**

  Use the finishing workflow to fast-forward `main` from the reviewed feature
  branch, rerun the full test suite and required checks on merged `main`, push
  `origin main`, fetch, and verify:

  ```sh
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
```

Remove only this plan's temporary worktree after the clean final review and
merge; leave unrelated worktrees, caches, and pre-existing untracked files
untouched.

## Completion evidence

- Runtime implementation and tests were already merged into `main`; fixes `31dab99` (descriptor-relative private input snapshot) and `4e26fa7` (literal dynamic-import boundary scan) were independently re-reviewed and merged.
- Documentation/spec/plan reconciliation `0769e6c` records the private input snapshot contract and was independently re-reviewed with approval.
- Current main targeted matrix: adapter, docs, boundary, development-runtime, and CLI tests — `102 passed, 1 skipped`; final broad review focused matrix — `119 passed, 1 skipped`.
- Current main full suite: `2503 passed, 4 skipped`; `uv run ruff check src tests` passed; `python3 schema/build.py --check` validated 8 resources; `uv lock --check` resolved 17 packages; CRLF-safe diff checks passed.
- Security/identity checks: child input is snapshot-derived through the pinned package-root descriptor; output writes remain descriptor-relative and exclusive; fixed public failure redaction and traceback-local tests pass; all 14 manifest-listed runtime files remain byte-identical to `/Users/joon/w/growth-ai`; manifest and lock fingerprints match the pinned values; no patient-like data paths are tracked.
- Boundary: explicit `development-smoke`/`development-cohort`/`development-realistic` profiles may compose this test-only, wholly synthetic, non-authoritative adapter; default/no-profile and production `synthetic.generate` remain fail-closed. Vendor Ruff’s 10 inherited findings were recorded as informational and the byte-preserved sources were not modified.
- Review: Task 1, Task 2, and final broad review packages, plus all fix/re-review reports, are preserved under `.superpowers/sdd/2026-09-01-augmenter-oracle-adapter/` in the local ignored evidence paths.
