# Development Scale-Profile Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in 10,000-patient development-profile integration gate that composes the native cohort, longitudinal/task evaluators, exact-schema exporter, and verified source-matched augmenter across a fixed seed set.

**Architecture:** Keep production modules unchanged. Add a test-only scale harness that constructs the existing fictional inputs, generates one descriptor-shaped cohort per seed, runs the existing aggregate evaluators, and exports a temporary eight-resource package with the existing test-only derivation binding. Register a `scale` pytest marker and require `SYNTHETIC_RUN_SCALE=1`, so normal CI remains fast while the scheduled gate is explicit and reproducible.

**Tech Stack:** Python 3.12+, pytest, existing native synthetic contracts, source-matched augmenter oracle, exact-schema exporter, Ruff, Frictionless-style descriptor checks.

**Spec:** `docs/superpowers/specs/2026-09-01-development-scale-profile-design.md`

## Global Constraints

- Use exactly 10,000 patients and seeds `20260830`, `20260831`, and `20260901`.
- Enable the test only when `SYNTHETIC_RUN_SCALE=1`; retain the `scale` marker.
- Use only checked-in fictional references, aggregate fixtures, and temporary output paths.
- Do not import the scale harness into `src/synthetic` or change the production CLI.
- Construct task predictions from visible observation events only; never access latent disorder state for predictions.
- Use the source-matched augmenter only through `SourceMatchedAugmenterOracle` and the existing test-only binding identity.
- Require exact descriptor resource order, schema fingerprint, package tree, and row counts.
- Preserve the existing six-resource generic bundle contract; ancillary clinical transitions remain in their dedicated evaluator tests.
- Do not stage or remove pre-existing generated caches outside the feature files.

---

### Task 1: Add the opt-in scale integration test

**Files:**
- Create: `tests/synthetic/test_development_scale.py`
- Modify: `pyproject.toml`
- Test: `tests/synthetic/test_development_scale.py`

**Interfaces:**
- Consumes: `generate_native_cohort`, `validate_native_cohort`, `validate_temporal_drift`, `evaluate_task_utility`, `export_exact_schema_package`, `SourceMatchedAugmenterOracle`, and existing fictional test fixtures.
- Produces: one parameterized `scale` test over the fixed seed set, with exact 10,000-member and eight-resource assertions.

- [ ] **Step 1: Write the failing scale test.**

Create a parameterized test marked `scale` and skipped unless `SYNTHETIC_RUN_SCALE == "1"`. Build a fixed `ObservationPolicy` covering ages `0, 365, 730, 1460, 2190, 3650, 4380, 5114, 5475, 6200, 7305`, with visits and visible height/weight/head circumference always available, length unavailable, no measurement error, and no recorded recognition/diagnosis. Generate with the existing aggregate fixture, `RegimeLinearTestReference`, healthy/GHD modules, and the checked-in descriptor. Assert 10,000 members, 110,000 visible visits, unique synthetic patient/visit IDs, and no `FAIL` comparison in the cohort report. Run temporal drift across five fixed half-open age windows and assert its report type/cohort size; build one `TaskPrediction` per member from visible diagnosis events only, run task utility, and assert its report type/cohort size. Export the six-resource bundles with `export_exact_schema_package` and a candidate augmenter binding into `tmp_path`; assert all eight descriptor resources, 10,000 patient rows, 110,000 visit rows, the augmented row counts, exact schema fingerprint, manifest seed, and exact package inventory.

Register the marker in `pyproject.toml` so the test has no unknown-marker warning.

- [ ] **Step 2: Run the scale test without opt-in and verify it is skipped.**

Run:

```sh
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_development_scale.py
```

Expected: all parameterized cases are skipped because the explicit scale opt-in is absent.

- [ ] **Step 3: Run one fixed seed with opt-in and verify the intended red state.**

Run:

```sh
SYNTHETIC_RUN_SCALE=1 PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_development_scale.py -k 20260830
```

Expected: collection succeeds and the new assertions expose any missing scale harness behavior or row-count mismatch before documentation is added.

- [ ] **Step 4: Implement only the test harness and exact assertions.**

Use test-local helpers for descriptor loading, fixed policies, candidate binding, visible-only task predictions, package row counts, and recursive package inventory. Keep all test inputs fictional and temporary. Do not add a production wrapper or relax existing validators to make the scale case pass.

- [ ] **Step 5: Run the focused scale test and marker checks.**

Run the opt-in single-seed command from Step 3, then run the default focused command. The single-seed run must pass; the default run must remain skipped.

- [ ] **Step 6: Commit Task 1.**

```sh
git add tests/synthetic/test_development_scale.py pyproject.toml
git commit -m "test: add development scale profile gate"
```

### Task 2: Document the scheduled gate and claims

**Files:**
- Modify: `README.md`
- Modify: `docs/synthetic-generator.md`
- Modify: `tests/synthetic/test_development_scale.py`

**Interfaces:**
- Consumes: Task 1's marker, environment opt-in, fixed seed set, and package assertions.
- Produces: a copy-pasteable scheduled command, explicit output/claim boundary, and documentation regression assertions.

- [ ] **Step 1: Add failing documentation assertions.**

Extend the scale test's documentation checks to require `SYNTHETIC_RUN_SCALE=1`, `pytest -m scale`, `20260830`, `20260831`, `20260901`, `10000`, the all-eight-resource statement, and the explicit non-claims for prevalence, clinical, privacy/non-matchability, held-out, Synthea, and release evidence.

- [ ] **Step 2: Update the usage documentation.**

Add a concise “Scheduled development scale profile” section to `docs/synthetic-generator.md` with the exact command:

```sh
SYNTHETIC_RUN_SCALE=1 uv run pytest -m scale tests/synthetic/test_development_scale.py
```

Name the fixed seed set, 10,000-patient size, temporary package behavior, eight-resource/derivation/longitudinal/task checks, and the opt-in reason. Add a README roadmap paragraph linking to the section and clearly state that the gate is composition evidence only and does not bind the augmenter, prove prevalence or clinical validity, evaluate against real labels, establish privacy/non-matchability, run Synthea, or authorize release.

- [ ] **Step 3: Run documentation assertions and lint.**

Run the focused test without opt-in, Ruff on changed test files, schema validation, and the whitespace check for the feature diff. Confirm no production synthetic module imports the scale test or source augmenter.

- [ ] **Step 4: Commit Task 2.**

```sh
git add README.md docs/synthetic-generator.md tests/synthetic/test_development_scale.py
git commit -m "docs: describe scheduled development scale gate"
```

### Task 3: Independent review, full verification, and integration

**Files:**
- Modify: `.superpowers/sdd/2026-09-01-development-scale-profile/progress.md` (ignored ledger only)

**Interfaces:**
- Consumes: Task 1 and Task 2 commits, focused scale evidence, and the parent acceptance criteria.
- Produces: fresh scoped reviews, a broad review, full verification, merged/pushed `main`, and verified ref parity.

- [ ] **Step 1: Record the SDD ledger and generate review packages.**

Record the feature base SHA, task implementation/review/fix results, exact focused commands, and any deferred minor findings in the ignored ledger. Generate one review package per task from the recorded base through the task tip; do not pass the whole plan or session transcript to reviewers.

- [ ] **Step 2: Resolve review findings through implementer-only fix rounds.**

For each Critical or Important finding, dispatch the original task implementer with the complete finding, run the focused red/green checks, generate a fix review package, and obtain one scoped re-review. Do not hand implementation fixes to the reviewer.

- [ ] **Step 3: Run the scheduled scale matrix and repository verification.**

Run all three opt-in fixed seeds, the default full suite, Ruff for `src tests`, `python3 schema/build.py --check`, `uv lock --check`, and `git -c core.whitespace=cr-at-eol,-blank-at-eof diff --check BASE..HEAD`. Record exact outputs and preserve any generated cache files.

- [ ] **Step 4: Dispatch a broad final review.**

Review the complete branch for scope drift, hidden-truth leakage, accidental real-data paths, flaky resource/memory assertions, marker behavior, and stale claims. Resolve every Critical/Important finding with one fix/re-review round.

- [ ] **Step 5: Merge, verify, push, and confirm parity.**

After the merged-result full suite and all checks pass, fast-forward `main`, rerun the merged verification, push `origin main`, fetch, and confirm `git rev-parse HEAD` equals `git rev-parse origin/main`. Preserve the feature worktree if generated untracked files prevent safe removal; never force-delete them.
