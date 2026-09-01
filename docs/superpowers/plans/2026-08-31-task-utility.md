# Synthetic Growth Task-Utility Evaluator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, evaluator-only task-utility report for a fictional native cohort while preserving the hidden-truth and no-real-data boundaries.

**Architecture:** Build a standalone `synthetic.task_utility` module over `NativeCohort`, `CohortMember`, `AgeRegimeDisorderTrajectory`, and `SyntheticDemographics`. A frozen policy and prediction tuple feed private binary truth extraction. Immutable aggregate cells and a report expose only fixed metrics, counts, statuses, reasons, and safe subgroup scopes. The visible generator, exact-schema exporters, calibrator, held-out validator, privacy auditor, counterfactual trajectory layer, and smoke CLI remain unchanged.

**Tech Stack:** Python 3.12+, standard-library `dataclasses`, `enum`, `json`, `math`, `collections`, existing cohort/model/resource types, pytest, Ruff, and AST boundary tests.

**Spec:** `docs/superpowers/specs/2026-08-31-task-utility-design.md`

## Global Constraints

- Input is only an already-generated fictional `NativeCohort`, `TaskUtilityPolicy`, and an immutable prediction tuple aligned to cohort order. No path, file, descriptor, key, report, output, model/callable, real-data, held-out, privacy, calibration data, or Synthea argument is accepted. The module may use only the existing aggregate-safe-token helper from `synthetic.calibration`.
- Latent healthy/disorder state is process-local evaluator truth. It may affect aggregate counters and statuses only; no per-member truth, IDs, predictions, scores, measurements, or raw feature tuples may enter mappings, JSON, repr, or errors.
- Use fixed vocabulary and deterministic order for metrics, statuses, reasons, subgroup scopes, and serialized keys. Reject malformed types and hostile injected values without echoing them.
- Missing decisions/scores are unevaluable, never zero or a negative/healthy default. Structural corruption is `FAIL`; insufficient class/support evidence is `UNEVALUABLE`; evaluated out-of-bound metrics are `FAIL`.
- Do not add a CLI, filesystem writer, package/export integration, model fitting, real-label comparison, counterfactual package executor, or Synthea adapter in this slice.
- Every task ends with focused tests, Ruff for touched files, `git diff --check`, and a scoped commit. Preserve unrelated worktree files.

---

### Task 1: Add strict policy, prediction, cell, and report models

**Files:**
- Create: `src/synthetic/task_utility.py`
- Create: `tests/synthetic/test_task_utility_models.py`

**Interfaces:**
- Consumes: `require_aggregate_safe_token` and type-only existing cohort/resource/model values.
- Produces: `TASK_UTILITY_REPORT_VERSION`, `TASK_METRICS`, `TASK_REASON_CODES`, `TaskUtilityStatus`, `TaskUtilityPolicy`, `TaskPrediction`, `TaskUtilityMetric`, `TaskUtilityCell`, and `TaskUtilityReport` with frozen validation and canonical serialization.

- [ ] **Step 1: Write failing model tests**

  Add tests for valid policy/prediction/cell/report construction, exact fixed registries, booleans and nonfinite-number rejection, positive/zero floor semantics, `minimum_evaluable_members`/`maximum_unevaluable_members`, supported `sex` subgroup validation, frozen dataclasses, mapping proxies, explicit metric target/support/null rules, exact `member_count`/`evaluable_count`/`unevaluable_count` field names, truth-dependent count suppression on unevaluable cells, report `reason_code`, cell/report status/reason precedence including the allowed missing-output pass, fixed scope/metric/status-count order, evaluator-safe `repr`, and exact canonical JSON/newline behavior. Test that unknown keys/metrics/reasons, patient-like scopes, mutable tuples/mappings, inconsistent counts, and numeric evidence on unevaluable metrics fail closed.

- [ ] **Step 2: Run the model tests to verify they fail**

  Run `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_task_utility_models.py`. Expected: collection failure because `synthetic.task_utility` and its models do not exist.

- [ ] **Step 3: Implement strict frozen models**

  Implement the exact spec fields and fixed registries, including the `require_probability_scores` switch, report `reason_code`, and explicit `TaskUtilityMetric`/`TaskUtilityCell` fields. Enforce `[0,1]` probabilities, positive supports, nonnegative unevaluable allowance, exact `sex` subgroup tuple, immutable nested mappings, aggregate-only scope tokens, status/reason compatibility, metric-specific target/support/null fields, and suppression of truth-dependent counts on unevaluable cells. Implement exact cell/report status-reason precedence, including the bounded missing-output allowance, and canonical compact sorted ASCII serialization. Ensure invalid public inputs return the static `unavailable` structural fallback report without echoing values, and `repr()` never includes latent or prediction values.

- [ ] **Step 4: Run model tests, lint, and commit**

  Run focused pytest, Ruff on the touched module/test, and `git diff --check`. Commit `build: add task utility contract models`.

### Task 2: Implement deterministic overall metrics

**Files:**
- Modify: `src/synthetic/task_utility.py`
- Create: `tests/synthetic/test_task_utility_metrics.py`
- Create: `tests/synthetic/task_utility_fixtures.py`

**Interfaces:**
- Consumes: validated `NativeCohort`, `TaskUtilityPolicy`, and ordered `TaskPrediction` tuple.
- Produces: `evaluate_task_utility(cohort, predictions, policy) -> TaskUtilityReport` with overall confusion, threshold, AUROC, and Brier calculations.

- [ ] **Step 1: Write failing metric tests and typed fictional fixtures**

  Build tiny `CohortMember` values with healthy and disorder latent states, visible observations, and safe synthetic IDs. Add tests for exact confusion counts/rates, tied-score midrank AUROC, Brier score, binary-only diagnostics, missing decision/score handling, threshold pass/fail, cohort-size/support floors, and deterministic repeated JSON. Assert no member ID, truth, score, or raw observation appears in the report mapping or repr.

- [ ] **Step 2: Run metric tests to verify they fail**

  Run `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_task_utility_metrics.py`. Expected: failures because the evaluator and metric extraction do not exist.

- [ ] **Step 3: Implement private metric extraction and public evaluation**

  Validate exact types and prediction length before reading members. Privately classify healthy versus nonhealthy disorder kinds, accumulate confusion and score counters, compute exact rank-statistic AUROC with tied midranks, and compute Brier only when all evaluable decisions have finite scores. Apply threshold/support/unevaluable precedence and the optional-score switch from the spec and emit fixed overall cells. Never retain or serialize per-member arrays or values.

- [ ] **Step 4: Run metrics, lint, and commit**

  Run focused pytest, Ruff, and whitespace checks. Commit `feat: evaluate synthetic growth task metrics`.

### Task 3: Add fixed sex subgroup and failure-mode aggregation

**Files:**
- Modify: `src/synthetic/task_utility.py`
- Create: `tests/synthetic/test_task_utility_subgroups.py`

**Interfaces:**
- Consumes: Task 2 evaluator and `SyntheticDemographics.sex` only for fixed subgroup assignment.
- Produces: deterministic cells for observed `sex:F`, `sex:M`, and `sex:U` categories in that order, aggregate false-positive/false-negative counts, and overall status aggregation. Categories absent from the cohort are omitted.

- [ ] **Step 1: Write failing subgroup/status tests**

  Test requested versus empty subgroup policies, fixed category order, minimum class support, subgroup threshold failure, missing predictions by subgroup, aggregate failure-mode counts, and precedence where one subgroup fails or is unevaluable. Assert subgroup scopes cannot be caller-defined, absent categories are omitted, and no demographics beyond fixed sex are accepted.

- [ ] **Step 2: Run subgroup tests to verify they fail**

  Run `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_task_utility_subgroups.py`. Expected: failures until subgroup cell construction and report aggregation are implemented.

- [ ] **Step 3: Implement fixed subgroup cells and report invariants**

  Partition only by the closed `F/M/U` values, compute each observed category cell with the same private metric path, sort scopes deterministically, and ensure report status/counts exactly match cell statuses. Treat malformed demographic values or latent state as structural failure without echoing values. Keep subgroup labels aggregate-safe and never include patient IDs.

- [ ] **Step 4: Run subgroup tests, all task tests, lint, and commit**

  Run all `tests/synthetic/test_task_utility_*.py`, Ruff on touched files, and whitespace checks. Commit `feat: add synthetic task utility subgroup diagnostics`.

### Task 4: Add boundaries, documentation, and regression coverage

**Files:**
- Create: `tests/synthetic/test_task_utility_boundaries.py`
- Create: `tests/synthetic/test_task_utility_docs.py`
- Modify: `docs/synthetic-generator.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: the public task evaluator contract and repository documentation.
- Produces: AST/import guards, documentation examples, explicit non-claims, and regression assertions that existing generator/export/CLI behavior is unchanged.

- [ ] **Step 1: Write failing boundary/documentation tests**

  Add AST checks over `src/synthetic/task_utility.py` rejecting `Path`, CSV, DuckDB, filesystem lifecycle, package/export/manifest, governed calibration/held-out/privacy, Synthea, and model-training imports/calls, plus public path/key/report/output/model/callable argument names. Permit only the aggregate-safe-token helper from `synthetic.calibration`. Add docs assertions for exact API, tuple alignment, fixed metrics/statuses, optional score semantics, hidden-truth boundary, and explicit deferrals/non-claims. Add a regression test that ordinary `to_mapping()` methods remain truth-free.

- [ ] **Step 2: Run boundary/docs tests to verify they fail**

  Run `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_task_utility_boundaries.py tests/synthetic/test_task_utility_docs.py`. Expected: failures until the module and docs satisfy the guards.

- [ ] **Step 3: Implement the AST guards and guide/README section**

  Keep the evaluator module standard-library/in-memory only. Document a visible-pipeline adapter pattern that produces ordered `TaskPrediction` values, explain aggregate-only outputs and threshold/support semantics, and state that synthetic task diagnostics do not establish clinical utility, real-data performance, prevalence, privacy/non-matchability, release readiness, or Synthea conformance. Keep paragraphs on one physical line where repository conventions require it.

- [ ] **Step 4: Run focused suite, Ruff, schema, and commit**

  Run the task utility suite, full Ruff, `uv lock --check`, `uv run python schema/build.py --check`, and `git diff --check`. Commit `docs: document synthetic task utility evaluator`.

### Task 5: Review, verify, and hand off

**Files:**
- Modify: `docs/superpowers/plans/2026-08-31-task-utility.md` (checkbox metadata only)
- Create: `.superpowers/sdd/2026-08-31-task-utility/ledger.md` and task/review reports (ignored SDD workspace)

**Interfaces:**
- Consumes: completed implementation, task-focused reports, and the repository verification commands.
- Produces: scoped implementation/review evidence, final broad review, a clean tracked branch, and a merged/pushed main commit whose `HEAD` equals `origin/main`.

- [ ] **Step 1: Run fresh scoped reviews after each implementation task**

  For each task, create the exact review package at the implementation commit's parent/head, dispatch a fresh reviewer, record PASS or findings in the ledger, and route every finding to a fresh implementer. Do not implement fixes in the controller. Re-review the exact fix range until PASS; preserve all reports.

- [ ] **Step 2: Run one broad review across the complete slice**

  Dispatch a fresh reviewer on the complete feature range. Require explicit checks for hidden-truth non-disclosure, aggregate-only serialization, support/status precedence, no real-data/path/model boundary, deterministic metrics, exact schema compatibility, documentation/non-claims, and regression safety. Route any finding through an implementer and scoped re-review.

- [ ] **Step 3: Verify and update plan metadata**

  Run full pytest with `PYTHONDONTWRITEBYTECODE=1`, Ruff, `uv lock --check`, schema check, and `git diff --check`. Update only checkbox metadata and evidence references in this plan/ledger; commit plan metadata separately.

- [ ] **Step 4: Merge and push**

  From the primary checkout, verify the main worktree is clean except pre-existing ignored/untracked pycache, merge `codex/task-utility` with `--no-ff`, push `main`, verify `git rev-parse HEAD` equals `origin/main`, and retain the isolated worktree and SDD reports for auditability.
