# Growth Augmenter Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vendor the supplied growth augmenter and its complete non-patient runtime closure for synthetic exact-schema development runs.

**Architecture:** Keep the supplied `scripts/augment.py` and `scripts/harrall_outliers.py` byte-identical and preserve their `data/` relative lookup contract. Vendor only the ten CDC/LMS/velocity reference tables and the ICD-10-CM chronic-code table that the CLI reads, record their hashes in a manifest, and expose only the repo-root CLI-only contract while keeping the raw CLI outside the default/no-profile and production generator paths and outside the authoritative derivation boundary. Explicit development profiles may use the separately documented, opt-in, test-only adapter through the exact-schema exporter for wholly synthetic packages.

**Tech Stack:** Python 3.12+, pandas, NumPy, SciPy, PyArrow, pytest, Ruff, uv, Frictionless-style `datapackage.json` headers.

**Spec:** `docs/superpowers/specs/2026-09-01-augment-import-design.md`

## Global Constraints

- The copied Python and reference files remain byte-identical to the supplied source files.
- Runtime reference files are exactly the ten CDC LMS/height-velocity CSVs and `icd10cm-tabular-2026.csv`; no patient or generated-output files are copied.
- The command expects `visits.csv`, `patients.csv`, and `problem_list.csv` in an explicit caller-provided input directory and uses `data/` references.
- The supported interface is CLI-only: run `uv run python scripts/augment.py ...` from the repository root; ordinary `import scripts.augment` is not supported by the byte-identical source.
- The raw CLI import is a development derivation candidate, not an authoritative oracle. The default/no-profile and production generator paths do not invoke the imported CLI. Explicit `development-smoke`, `development-cohort`, and `development-realistic` profiles may use the separately documented, opt-in, test-only `SourceMatchedAugmenterOracle` through the exact-schema exporter for staged wholly synthetic packages. This explicit development adapter remains outside authoritative, calibration, privacy, counterfactual, Synthea, and release decisions; it does not alter production fail-closed behavior or confer authority.
- Tests use only temporary wholly synthetic input rows and must verify augmented output headers against `datapackage.json`.
- `pandas`, `scipy`, and `pyarrow` are direct project dependencies alongside the existing NumPy dependency because the copied CLI imports or executes them.
- Do not add real patient, visit, problem-list, laboratory, medication, referral, output, notebook, cache, virtual-environment, credential, or source-repository metadata files.

---

### Task 1: Vendor the source-matched runtime closure

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/augment.py`
- Create: `scripts/harrall_outliers.py`
- Create: `data/statage_combined.csv`
- Create: `data/wtage_combined.csv`
- Create: `data/bmiagerev.csv`
- Create: `data/hcageinf.csv`
- Create: `data/wtstat.csv`
- Create: `data/wtleninf.csv`
- Create: `data/hvage_no_pub.csv`
- Create: `data/hvage_earlier_pub.csv`
- Create: `data/hvage_average_pub.csv`
- Create: `data/hvage_later_pub.csv`
- Create: `data/icd10cm-tabular-2026.csv`
- Create: `data/augment-runtime-manifest.json`
- Create: `data/README.md`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Test: `tests/test_augment_import.py`

**Interfaces:**
- Consumes: supplied source files under `/Users/joon/w/growth-ai/scripts` and `/Users/joon/w/growth-ai/data`; checked-in `datapackage.json` for test headers.
- Produces: runnable repo-root CLI `uv run python scripts/augment.py ...`, local CLI resolution of `detect_harrall_outliers`, bundled `data/` reference files, a manifest with exact relative paths/digests, and project dependencies sufficient for CSV and Parquet modes.

- [x] **Step 1: Write the failing closure test**

Add `tests/test_augment_import.py` with tests that (a) load the manifest and assert every listed path is relative, regular, present, and matches its recorded byte size and lowercase SHA-256; (b) assert the manifest's path set is the eleven exact runtime data names plus the two Python source names and `scripts/__init__.py`; (c) assert each CDC table has the expected `Sex`/LMS header and the ICD-10 table has `diag_name`/`chronic`; and (d) create a temporary synthetic input package from the descriptor headers, run the supported repo-root CLI in a subprocess, and assert the resulting column names equal the descriptor fields for `visits_augmented` and `patients_augmented`.

- [x] **Step 2: Run the focused test to verify it fails**

Run `PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_augment_import.py`. Expected: collection or assertions fail because the copied scripts, data files, manifest, and pandas/SciPy dependencies are not yet present.

- [x] **Step 3: Copy the exact runtime closure**

Copy the supplied `augment.py`, `harrall_outliers.py`, and empty `__init__.py` into `scripts/`; copy only the ten filenames listed in `load_cdc_data` and `data/icd10cm-tabular-2026.csv` into `data/`. Do not copy any source `input/`, `p3-data/`, patient, visit, problem-list, output, notebook, cache, environment, or repository-control files. Generate `data/augment-runtime-manifest.json` with a fixed manifest version, relative paths, byte sizes, SHA-256 digests, roles (`python`, `cdc_reference`, `icd10_reference`), and source-relative names; do not record absolute workstation paths or patient identifiers. Add `data/README.md` describing the lookup contract, the verified source-checkout snapshot and source-relative paths, the exact excluded classes, and the limits of provenance, licensing, validation, and redistribution evidence.

- [x] **Step 4: Declare dependencies and refresh the lock**

Add direct runtime requirements `pandas>=2.3.2,<3`, `scipy>=1.16.2,<2`, and `pyarrow>=23.0.0,<24` to `pyproject.toml` while retaining the existing NumPy constraint. Run `uv lock` and inspect the diff to ensure only dependency-resolution changes accompany the import.

- [x] **Step 5: Run the focused test to verify it passes**

Run `PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_augment_import.py`. The synthetic test must use only temporary files, exercise both augmentation functions, and pass without reading any path outside the repository's bundled reference tables and the temporary fixture.

- [x] **Step 6: Commit the task**

Run `git add data scripts pyproject.toml uv.lock tests/test_augment_import.py && git commit -m "feat: vendor source-matched growth augmenter"`.

### Task 2: Document the development-only integration boundary

**Files:**
- Modify: `README.md`
- Modify: `docs/synthetic-generator.md`
- Create: `docs/augment-import.md`
- Test: `tests/test_augment_import.py`

**Interfaces:**
- Consumes: Task 1's `scripts/augment.py`, `data/augment-runtime-manifest.json`, exact-schema descriptor, and dependency metadata.
- Produces: A runnable synthetic-only usage guide and current documentation that distinguishes the imported candidate from the authoritative derivation/export boundary.

- [x] **Step 1: Extend the focused documentation assertions**

Add assertions that `docs/augment-import.md` names the three required input files, the CSV/Parquet command shape, the manifest, synthetic-only use, and the non-authoritative boundary; assert README and `docs/synthetic-generator.md` no longer claim that no augmenter implementation is shipped and instead state that the imported candidate is not bound as authoritative.

- [x] **Step 2: Update the usage documentation**

Create `docs/augment-import.md` with setup (`uv sync`), a repo-root `uv run python scripts/augment.py ...` command using an explicit synthetic input directory and output directory, the expected timestamped outputs, the manifest/hash verification command, the exact base-resource requirements, and a prominent warning not to point the script at governed or real data. Update README and the synthetic-generator guide to link this document and retain the existing fail-closed authority statement.

- [x] **Step 3: Run focused documentation tests**

Run `PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_augment_import.py` and confirm all documentation assertions pass.

- [x] **Step 4: Commit the task**

Run `git add README.md docs/synthetic-generator.md docs/augment-import.md tests/test_augment_import.py && git commit -m "docs: describe imported growth augmenter"`.

### Task 3: Full verification and handoff

**Files:**
- Modify: `.superpowers/sdd/2026-09-01-augment-import/progress.md` (ignored ledger only)

**Interfaces:**
- Consumes: Task 1 and Task 2 commits and their focused test evidence.
- Produces: Reviewable branch with clean dependency, schema, test, and safety checks ready for final review and merge.

- [x] **Step 1: Run repository verification**

Run `PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q`, `PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests`, `PYTHONDONTWRITEBYTECODE=1 python3 schema/build.py --check`, and `git -c core.whitespace=cr-at-eol,-blank-at-eof diff --check main..HEAD`. Run an informational `PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check scripts/augment.py scripts/harrall_outliers.py` and record its inherited findings without changing byte-identical source. Also run a boundary scan confirming no tracked path under `data/` contains patient/input/output names and no synthetic package module imports `scripts.augment`.

- [x] **Step 2: Commit the verification ledger**

Append the task completion, review findings, and exact verification outputs to the ignored SDD ledger; do not stage the ledger.

- [x] **Step 3: Final review and handoff**

Generate the SDD review package from the merge base through `HEAD`, dispatch a broad code review, fix any Critical or Important finding through one reviewed fix round, then use `superpowers:finishing-a-development-branch` to merge fast-forward into `main`, push, fetch, and verify `HEAD` equals `origin/main`.

## Completion evidence

- Runtime closure: `scripts/augment.py` and `scripts/harrall_outliers.py`, the ten CDC/LMS/velocity tables, and `data/icd10cm-tabular-2026.csv` remain byte-identical to the supplied source snapshot; the manifest covers exactly 14 regular non-symlink files with matching sizes and SHA-256 digests.
- Focused closure test: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q tests/test_augment_import.py` — `5 passed`.
- Repository gates after the reviewed docs fixes: `python3 schema/build.py --check` — 8 resources validated; `uv lock --check` — resolved 17 packages; focused and targeted adapter/CLI checks passed; Ruff passed for changed tests, with only the documented inherited vendor findings left untouched to preserve source bytes.
- Review evidence: Task 1 closure review approved; Task 2 scoped review approved after the boundary fixes; final broad review approved with no Critical/Important/Minor findings. Reports are preserved under `.superpowers/sdd/2026-09-01-augment-import/` in the review worktrees.
- Boundary: the raw CLI remains a development candidate; the explicit `development-smoke`/`development-cohort`/`development-realistic` profiles may use the test-only adapter for wholly synthetic packages, while the default/no-profile and production command remain fail-closed and no authority is conferred.
- Publication: reviewed commits fast-forwarded `main` to `77939c4`; the final plan-closure commit and remote push follow the merged verification run.
