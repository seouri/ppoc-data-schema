# Temporal Drift Evaluator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, evaluator-only temporal-drift report for fictional native cohorts without introducing a filesystem, governed-data, or release boundary.

**Architecture:** Build a standalone `synthetic.temporal_drift` module over the existing in-memory `NativeCohort`, `CohortMember`, `ObservationFrame`, and `AgeRegimeDisorderTrajectory` types. A frozen policy defines age-window coverage floors and adjacent-window drift bounds; metric extraction remains private, while immutable aggregate comparisons and reports expose only fixed names, statuses, counts, and safe visible summaries. Hidden source-event checks emit status/reason only. The normal generator, package exporter, calibrator, held-out validator, privacy auditor, and smoke CLI remain unchanged.

**Tech Stack:** Python 3.12+, standard-library `dataclasses`, `enum`, `json`, `math`, `collections`, existing native cohort/observation/model types, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-08-31-temporal-drift-design.md`

## Global Constraints

- Input is only a typed fictional `NativeCohort` and `TemporalDriftPolicy`; no path, file, descriptor, key, artifact, report, output, or real-data argument is accepted.
- The module imports no `Path`, DuckDB, CSV/package/export/manifest lifecycle, calibration, held-out, privacy, or Synthea runtime.
- Required age windows are ordered, unique, non-overlapping, half-open `[lower_age_days, upper_age_days)` intervals with safe aggregate tokens.
- Reports contain only fixed aggregate metrics, safe window IDs, numeric visible summaries, counts, statuses, and reason codes; never patient/visit IDs, event payloads, hidden ages, hashes, paths, seeds other than aggregate cohort seed, or row sequences.
- Malformed typed evidence is `FAIL`; absent/private evidence or insufficient support is `UNEVALUABLE`; no missing value becomes zero or `PASS`.
- Hidden causal events may be inspected only in memory and only their aggregate status/reason is emitted. Evaluation must not mutate the cohort or policy.
- Every task ends with focused tests, Ruff for touched files, `git diff --check`, and a scoped commit.

---

### Task 1: Add frozen temporal policy, metric registries, and aggregate models

**Files:**
- Create: `src/synthetic/temporal_drift.py`
- Create: `tests/synthetic/test_temporal_drift_models.py`

**Interfaces:**
- Consumes: `require_aggregate_safe_token` from `synthetic.calibration`, `NativeCohort` types only for type checking.
- Produces: `TEMPORAL_DRIFT_REPORT_VERSION`, `TEMPORAL_METRICS`, `TEMPORAL_REASON_CODES`, `TemporalDriftStatus`, `TemporalWindowPolicy`, `TemporalDriftPolicy`, `TemporalComparison`, `TemporalCheck`, and `TemporalDriftReport` with immutable validated constructors and canonical serialization.

- [x] **Step 1: Write failing policy/model tests**

Add tests for valid values and exact rejection behavior. Use a fictional policy such as:

```python
TemporalDriftPolicy(
    policy_id="temporal-v1",
    policy_version="1",
    minimum_cohort_size=2,
    maximum_unevaluable_checks=1,
    windows=(
        TemporalWindowPolicy("early", 0, 730, 2, 1, 1, 0.5, 0.5, 400.0, 2.0, 0.5),
        TemporalWindowPolicy("late", 730, 1_460, 2, 1, 1, 0.5, 0.5, 365.0, 2.0, 0.5),
    ),
)
```

Assert frozen dataclasses, exact fixed metric/status/reason registries, positive support/minimum cohort values, finite nonnegative bounds, coverage fractions in `[0,1]`, safe IDs, ordered half-open windows, duplicate/overlap rejection, boolean rejection, mutable-input rejection, and unknown metric/reason rejection. Assert `UNEVALUABLE` comparisons null all numeric/support fields, causal comparisons null numeric fields even when passing, and report mappings use exactly the spec's top-level keys with compact sorted ASCII JSON plus newline only in `to_json_bytes()`.

- [x] **Step 2: Run the model tests to verify they fail**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_temporal_drift_models.py`

Expected: collection failure because `synthetic.temporal_drift` and its models do not exist. Fix only test setup/import errors before implementation.

- [x] **Step 3: Implement strict frozen models and registries**

Implement the exact model fields in the spec. Use `Enum` values `PASS`, `FAIL`, and `UNEVALUABLE`; a closed metric registry in canonical order; and reason codes `OK`, `WITHIN_BOUND`, `INSUFFICIENT_SUPPORT`, `COHORT_TOO_SMALL`, `MISSING_EVIDENCE`, `STRUCTURAL_INVALID`, and `OUTSIDE_BOUND`. Validate numeric types with explicit boolean rejection and `math.isfinite`, freeze windows/policies/comparisons/checks, and reject identifier-like text in policy/report fields. Make `TemporalComparison.to_mapping()` omit no required fields but null all numeric fields for `UNEVALUABLE` and causal metrics. Make `TemporalDriftReport.to_mapping()` recursively JSON-compatible, sorted, and aggregate-only; `canonical_json()` must be compact sorted ASCII without a newline, `to_json_bytes()` adds exactly one newline, and `repr()` must be the fixed evaluator-safe form.

- [x] **Step 4: Run model tests, lint, and commit**

Run:

```bash
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_temporal_drift_models.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/temporal_drift.py tests/synthetic/test_temporal_drift_models.py
git diff --check
```

Commit:

```bash
git add src/synthetic/temporal_drift.py tests/synthetic/test_temporal_drift_models.py
git commit -m "build: add temporal drift policy models"
```

### Task 2: Compute visible age-window metrics and adjacent-window drift

**Files:**
- Modify: `src/synthetic/temporal_drift.py`
- Create: `tests/synthetic/test_temporal_drift_metrics.py`
- Create: `tests/synthetic/temporal_drift_fixtures.py`

**Interfaces:**
- Consumes: validated temporal policy and `NativeCohort` members with visible `ObservationFrame` visits/events and trajectory points.
- Produces: `validate_temporal_drift(cohort, policy) -> TemporalDriftReport` for visible metrics, private metric extraction helpers, and deterministic comparison ordering.

- [x] **Step 1: Write failing visible-metric tests and fictional fixtures**

Build the smallest typed fictional cohort fixture using existing `CohortMember`/native fixture helpers; never write CSVs or copy source rows. Add tests for lower-inclusive/upper-exclusive assignment, empty windows, growth-point and visible-visit coverage floors, visible event rates, interval means using consecutive visits within a window, and adjacent-window visit-count/event-rate step bounds. Assert support floors produce `UNEVALUABLE`, lower-bound coverage failures produce `FAIL`, upper-bound interval failures produce `FAIL`, zero steps pass, and comparison order is fixed. Assert visible aggregate values never include member IDs or event codes.

- [x] **Step 2: Run metric tests to verify they fail**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_temporal_drift_metrics.py`

Expected: failures because `validate_temporal_drift` and metric extraction are not implemented.

- [x] **Step 3: Implement deterministic visible metrics**

Validate `NativeCohort` and `TemporalDriftPolicy` types before reading members. For each window, count members meeting the configured growth-point/visible-visit floors, calculate coverage fractions, count members with visible recorded events, and calculate mean inter-visit days from each member's sorted visible visit ages with at least two visits. Use only finite numeric values and aggregate counts. Emit lower-bound coverage comparisons with `difference=max(0,target-observed)`, upper-bound interval comparisons with `difference=max(0,observed-target)`, and `UNEVALUABLE` when the contributing member support is below `minimum_member_support` or no interval exists. Compare adjacent mean visit counts and visible event rates with `difference=max(0,abs(step)-target)`; omit the first-window step comparison. Never serialize per-member arrays, IDs, event codes, or raw sequences.

- [x] **Step 4: Run metric tests, lint, and commit**

Run:

```bash
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_temporal_drift_metrics.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/temporal_drift.py tests/synthetic/test_temporal_drift_metrics.py tests/synthetic/temporal_drift_fixtures.py
git diff --check
```

Commit:

```bash
git add src/synthetic/temporal_drift.py tests/synthetic/test_temporal_drift_metrics.py tests/synthetic/temporal_drift_fixtures.py
git commit -m "feat: compute temporal drift metrics"
```

### Task 3: Validate hidden causal order, timing, status precedence, and report assembly

**Files:**
- Modify: `src/synthetic/temporal_drift.py`
- Create: `tests/synthetic/test_temporal_drift_causal.py`
- Modify: `tests/synthetic/test_temporal_drift_metrics.py`

**Interfaces:**
- Consumes: visible metric comparisons from Task 2 and evaluator-held `AgeRegimeDisorderTrajectory`/`ObservationTruth` objects.
- Produces: fixed causal-order/timing comparisons and final status/check aggregation in `validate_temporal_drift`.

- [x] **Step 1: Write failing causal/status tests**

Add tests for valid phase-ordered source events; reversed phases; decreasing ages; treatment outcome before treatment start; both treatment outcomes; hidden onset made visible; event patient mismatch; negative event ages; visible visit/event outside its observation window; missing private truth; malformed member/frame/trajectory; cohort below minimum size; and mixed visible FAIL plus causal UNEVALUABLE evidence. Assert malformed evidence yields fixed `STRUCTURAL_INVALID`/`FAIL`, missing truth yields `MISSING_EVIDENCE`/`UNEVALUABLE`, FAIL dominates UNEVALUABLE, and no raw exception text, event age, event code, or patient token appears in any report/repr/error.

- [x] **Step 2: Run causal tests to verify they fail**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_temporal_drift_causal.py`

Expected: failures because causal validation and global status aggregation are incomplete.

- [x] **Step 3: Implement causal checks and report assembly**

Implement fixed phase validation over source events without returning their values. Treat absent `ObservationTruth` or unavailable evaluator-held source events as `UNEVALUABLE`, not PASS. Validate source event ages are nonnegative, phases are strictly ordered, treatment outcomes are terminal and follow treatment start, hidden onset remains hidden, and all event patient references match the member internally; catch malformed injected objects and replace them with fixed aggregate structural comparisons. Validate visible records against their existing observation window. Add `cohort_size`, `causal_event_order`, and `causal_event_timing` checks, combine visible and causal comparisons in canonical order, compute status precedence exactly as the spec, and return `TemporalDriftReport` without mutating inputs. Ensure all caught exceptions become fixed statuses/reasons and never include exception text.

- [x] **Step 4: Run focused temporal suite, lint, and commit**

Run:

```bash
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_temporal_drift_models.py tests/synthetic/test_temporal_drift_metrics.py tests/synthetic/test_temporal_drift_causal.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/temporal_drift.py tests/synthetic/test_temporal_drift_models.py tests/synthetic/test_temporal_drift_metrics.py tests/synthetic/test_temporal_drift_causal.py
git diff --check
```

Commit:

```bash
git add src/synthetic/temporal_drift.py tests/synthetic/test_temporal_drift_models.py tests/synthetic/test_temporal_drift_metrics.py tests/synthetic/test_temporal_drift_causal.py
git commit -m "feat: validate temporal causal drift"
```

### Task 4: Add documentation and visible-boundary regression

**Files:**
- Modify: `docs/synthetic-generator.md`
- Modify: `README.md`
- Create: `tests/synthetic/test_temporal_drift_boundaries.py`

**Interfaces:**
- Consumes: the public temporal policy/report/evaluator API and the temporal-drift spec.
- Produces: user-facing evaluator-only documentation and AST/import protections for visible generation/export/trajectory paths.

- [x] **Step 1: Write failing documentation and AST tests**

Add assertions that the guide and README name `TemporalDriftPolicy`, `TemporalWindowPolicy`, `validate_temporal_drift`, fixed metrics, half-open windows, `PASS`/`FAIL`/`UNEVALUABLE`, hidden causal checks, and all non-claims. AST-scan `src/synthetic/generate.py`, `src/synthetic/manifest.py`, `src/synthetic/derivation.py`, `src/synthetic/native/`, `src/synthetic/package_export.py`, and `src/synthetic/csv_package.py` to reject imports/calls to `synthetic.temporal_drift`, `Path`, file/output lifecycle functions, calibration/held-out/privacy runtimes, and path/key/report/output argument names; allow the evaluator module and tests.

- [x] **Step 2: Run boundary tests to verify they fail**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_temporal_drift_boundaries.py`

Expected: failure because the documentation section and boundary test do not exist.

- [x] **Step 3: Implement documentation and AST guard**

Add one concise “Evaluator-only temporal-drift validation” section to the guide and a matching README paragraph. Show the exact in-memory call shape, explain visible age-window metrics and adjacent-window steps, explain status precedence and hidden causal checks, and state that reports diagnose development sequence behavior only. Explicitly defer real-data temporal fidelity, prevalence, clinical validity, privacy/non-matchability, task utility, release, and Synthea claims. Keep existing command examples unchanged and preserve one-physical-line paragraphs where required. Implement the AST guard with `ast.parse` over only visible modules; reject forbidden imports/calls and public argument names without scanning evaluator internals.

- [x] **Step 4: Run documentation/boundary tests, lint, and commit**

Run:

```bash
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_temporal_drift_boundaries.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check tests/synthetic/test_temporal_drift_boundaries.py
git diff --check
```

Commit:

```bash
git add docs/synthetic-generator.md README.md tests/synthetic/test_temporal_drift_boundaries.py
git commit -m "docs: explain temporal drift evaluator"
```

### Task 5: Independent review, verification, merge, and push

**Files:**
- Review only: all temporal-drift source/tests/docs, the spec, and this plan.
- Modify only through an implementer if review finds a defect; the controller may update only the ignored SDD ledger and tracked plan checkboxes.

**Interfaces:**
- Consumes: the complete temporal-drift feature branch and review packages.
- Produces: a reviewed branch with final verification and remote parity.

- [x] **Step 1: Create SDD ledger, conflict scan, and task review packages**

Record the base branch and every shared-interface conflict in `.superpowers/sdd/2026-08-31-temporal-drift/progress.md`: Task 1↔2 model/metric types, Task 1↔3 status/report assembly, Task 1↔4 public boundary/docs, Task 2↔3 private truth/visible metrics, and Task 3↔4 evaluator isolation. Generate one exact review package per implementation task from its parent commit to its task commit and dispatch a fresh reviewer for each; reviewers must inspect the task brief, current source, focused tests, and diff without editing source.

- [x] **Step 2: Resolve findings through implementer-only fixes and scoped re-reviews**

For each Critical/Important finding, dispatch one implementer with the exact reproduction and regression requirement, generate a package from the fix parent to fix head, and dispatch a fresh scoped re-review. Preserve safe Minor observations in the ledger. Allow at most one broad fix wave after the whole-slice review; do not weaken hidden-truth, no-filesystem, or aggregate-only boundaries.

- [x] **Step 3: Run final verification before integration**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv lock --check
python3 schema/build.py --check
git diff --check
git status --short --branch
```

Confirm the feature diff contains only temporal-drift source/tests/docs/spec/plan changes, no generated packages, real data, keys, or temporary outputs, and that the report/repr/error probes contain no patient/visit IDs or hidden event values.

- [ ] **Step 4: Merge, push, and verify parity**

Fast-forward local `main` from the reviewed branch, rerun the full verification matrix on merged `main`, push `origin main`, and verify `git rev-parse HEAD` equals `git rev-parse origin/main`. Preserve the temporal-drift worktree and ignored SDD reports when they contain review evidence; leave unrelated worktrees untouched.
