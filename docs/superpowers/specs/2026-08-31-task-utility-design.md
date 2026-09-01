# Synthetic Growth Task-Utility Evaluation Contract

**Date:** 2026-08-31
**Status:** Approved next roadmap slice under the synthetic pediatric growth-fixture design
**Parent:** [Synthetic Pediatric Growth Fixture System Design](2026-08-30-synthetic-growth-fixtures-design.md)

**Tech Stack:** Python 3.12+, standard-library `dataclasses`, `enum`, `json`, `math`, `collections`, existing cohort/model/resource types, pytest, Ruff, and AST boundary tests.

## Purpose

This slice adds a deterministic, evaluator-only task-utility contract for a completely fictional native cohort. A development growth-screening pipeline supplies one process-local prediction per cohort member in stable cohort order. The evaluator privately compares those predictions with the member's latent healthy-versus-growth-disorder state and returns only aggregate discrimination, calibration, subgroup, and failure-mode summaries. It makes the intended task interface testable without turning synthetic success into a clinical claim.

The evaluator is deliberately a benchmark harness, not a growth-screening model, trainer, calibrator, prevalence estimator, or release gate. It does not decide which features a model should use and it does not tune a pipeline. A caller can run the same fixed pipeline over visible observations or an exact-schema package and pass its ordered outputs to this contract.

## Scope and boundaries

- The public entry point accepts only a typed fictional `NativeCohort`, an immutable `TaskUtilityPolicy`, and an immutable tuple of `TaskPrediction` values in the cohort's existing order. It accepts no path, file, descriptor, key, calibration artifact, held-out report, privacy input, real label, model object, callable, output destination, or counterfactual truth manifest.
- The prediction tuple contains only process-local task output: an optional binary decision and an optional probability-like score. It contains no patient ID, visit ID, latent label, diagnosis code, source row, or feature vector. A prediction without a decision is unevaluable; a score is valid only in `[0, 1]`.
- The evaluator reads `CohortMember.trajectory.disorder.kind` privately. Healthy is the negative class and every non-healthy `DisorderKind` is the positive growth-disorder class. This binary truth is never returned per member, serialized, hashed into a visible report, or included in exception text.
- Reports contain fixed aggregate counts, bounded numeric metrics, fixed subgroup labels from the descriptor-safe sex vocabulary, statuses, and reason codes. They never contain patient/member IDs, predictions, scores, labels, raw measurements, feature tuples, row sequences, or task outputs.
- This slice has no filesystem writer, CLI, package exporter, DuckDB dependency, governed calibration/held-out/privacy runtime, Synthea dependency, model training, hyperparameter search, or real-label comparison. It may import only the aggregate-safe-token helper from `synthetic.calibration`; it never loads calibration data. Package adaptation and counterfactual task replay remain caller-side/deferred gates.
- A report is development task-execution evidence only. It is not clinical validation, prevalence or demographic validation, real-data generalization, privacy/non-matchability evidence, or release authorization. Any future train-on-synthetic/test-on-real comparison requires separately governed labels, a frozen model and split, predeclared equivalence/noninferiority margins, and an approved protocol.

## Frozen policy and prediction contracts

The module exposes immutable values:

```python
@dataclass(frozen=True)
class TaskUtilityPolicy:
    policy_id: str
    policy_version: str
    minimum_cohort_size: int
    minimum_evaluable_members: int
    minimum_class_support: int
    maximum_unevaluable_members: int
    require_probability_scores: bool
    minimum_sensitivity: float
    minimum_specificity: float
    minimum_auroc: float
    maximum_brier_score: float
    subgroup_dimensions: tuple[str, ...]

@dataclass(frozen=True)
class TaskPrediction:
    predicted_disorder: bool | None
    risk_score: float | None = None
```

Policy identifiers are aggregate-safe tokens. Integer floors are positive except `maximum_unevaluable_members`, which is nonnegative. `minimum_evaluable_members` is the required overall count of predictions with a decision. `require_probability_scores` is a real boolean. Sensitivity, specificity, AUROC, and the Brier bound are finite probabilities in `[0, 1]`; booleans, nonfinite values, duplicate subgroup dimensions, and unsupported dimensions are rejected. The only supported subgroup dimension in this first version is `sex`; the policy must request `("sex",)` to exercise subgroup behavior and may use `()` for an overall-only smoke test. The policy is declared before evaluation, cannot be learned from predictions, and cannot contain target values for arbitrary metrics.

`TaskPrediction` is frozen. `predicted_disorder` must be a boolean or `None`; `risk_score` must be finite in `[0, 1]` when present. A `None` decision must not carry a score, because an unevaluable task output must not contribute partial truth. A decision may omit a score; this supports deterministic binary screeners. When `require_probability_scores` is false, AUROC and Brier are optional diagnostics and missing-score cells do not block an otherwise evaluable binary report; when it is true, every evaluable decision must carry a score and missing-score evidence makes the corresponding cell `UNEVALUABLE`.

## Fixed metrics and status semantics

The fixed metric registry is:

```text
sensitivity
specificity
precision
balanced_accuracy
auroc
brier_score
false_positive_count
false_negative_count
```

Overall metrics use the complete cohort. A member contributes to confusion metrics only when its prediction has a decision. `sensitivity` and `specificity` require at least `minimum_class_support` evaluable positive and negative truth members; `precision` requires at least one predicted-positive member; and `balanced_accuracy` requires both class supports. `auroc` and `brier_score` require a risk score for every evaluable member and at least one positive and one negative truth member. Missing decisions are counted as unevaluable members; decisions without scores increment an aggregate missing-score count but remain eligible for binary metrics. Neither condition is treated as healthy, disorder, or zero-risk evidence.

For evaluable cells, metrics are defined as follows:

- `sensitivity = true_positive / (true_positive + false_negative)`;
- `specificity = true_negative / (true_negative + false_positive)`;
- `precision = true_positive / (true_positive + false_positive)`;
- `balanced_accuracy = (sensitivity + specificity) / 2`;
- `auroc` is the exact rank statistic over probability scores, with tied scores receiving midranks;
- `brier_score` is the mean squared difference between each probability score and the private binary truth;
- `false_positive_count` and `false_negative_count` are aggregate failure-mode counts.

Policy thresholds apply only to sensitivity, specificity, AUROC, and Brier score. A metric passes when it meets its declared bound, fails when it is evaluable and outside the bound, and is unevaluable when its support or required score evidence is absent. `precision`, `balanced_accuracy`, and failure-mode counts are diagnostic metrics with no target bound; they pass when evaluable. Overall status precedence is `FAIL` for any evaluated threshold failure or malformed typed evidence, then `UNEVALUABLE` when the cohort is below `minimum_cohort_size`, the overall evaluable decision count is below `minimum_evaluable_members`, a required metric/cell lacks support, `require_probability_scores` is true and score evidence is missing, or the unevaluable-member count exceeds the policy allowance, otherwise `PASS`. When probability scores are optional, an `auroc`/`brier_score` metric with missing scores is reported as `UNEVALUABLE` diagnostic evidence but does not block the cell. A present subgroup with insufficient class support remains an unevaluable required cell.

The reason registry is closed:

```text
OK
WITHIN_BOUND
OUTSIDE_BOUND
COHORT_TOO_SMALL
INSUFFICIENT_SUPPORT
MISSING_PREDICTION
MISSING_SCORE
STRUCTURAL_INVALID
```

Subgroup cells are emitted only for requested `sex` categories present in the fixed vocabulary (`F`, `M`, `U`) and the aggregate `overall` cell. A subgroup with fewer than `minimum_class_support` positive or negative truth members is `UNEVALUABLE`; it is not suppressed into a misleading pass. Aggregate status/count summaries are safe for development logs, while all member-level rows remain process-local.

Cell status/reason precedence is fixed: structural corruption is `FAIL/STRUCTURAL_INVALID`; otherwise any evaluated threshold failure is `FAIL/OUTSIDE_BOUND`; otherwise a missing decision, missing required score, or insufficient class/support evidence is `UNEVALUABLE` with reason precedence `MISSING_PREDICTION`, then `MISSING_SCORE`, then `INSUFFICIENT_SUPPORT`; otherwise the cell is `PASS/WITHIN_BOUND`. A `COHORT_TOO_SMALL` reason is reserved for the report-level minimum cohort/evaluable floors. Optional score metrics can remain `UNEVALUABLE/MISSING_SCORE` inside a passing binary cell when `require_probability_scores` is false. The overall cell may therefore be `UNEVALUABLE/MISSING_PREDICTION` while the report is `PASS` when the missing-decision count is at most `maximum_unevaluable_members` and every required metric passes; this is the explicit missing-output allowance, not a hidden pass for an unevaluable metric.

## Aggregate report contract

The immutable `TaskUtilityMetric` contains `name`, `status`, `reason_code`, `observed`, `target`, and `support_count`. `target` is populated only for the four policy-bounded metrics (`minimum_sensitivity`, `minimum_specificity`, `minimum_auroc`, and `maximum_brier_score`); diagnostic metrics use null targets. `support_count` is the number of evaluable members contributing to that metric, or null when the metric is unevaluable. An evaluable metric always has finite `observed` and `support_count`; an unevaluable metric has null `observed`, `target`, and `support_count`. The immutable `TaskUtilityCell` contains `scope`, `status`, `reason_code`, `member_count`, `evaluable_count`, `unevaluable_count`, `missing_score_count`, `positive_count`, `negative_count`, `true_positive`, `true_negative`, `false_positive`, `false_negative`, and the fixed tuple of `TaskUtilityMetric` values. A cell whose status is `UNEVALUABLE` suppresses all truth-dependent counts (`positive_count`, `negative_count`, `true_positive`, `true_negative`, `false_positive`, and `false_negative`) to null; its member/evaluable/unevaluable/missing-score counts remain aggregate-safe. Structural-invalid cells use zero structural counts, null truth-dependent counts, and null metric evidence. The immutable `TaskUtilityReport` contains policy identity, cohort profile/seed/size, overall status, fixed `status_counts` keyed exactly by `PASS`/`FAIL`/`UNEVALUABLE` over cells, fixed `metric_counts` keyed exactly by `TASK_METRICS` with the number of cells carrying each metric, `evaluable_count`, `unevaluable_count`, and a tuple of immutable cells. Report and cell mappings use exact keys and recursively JSON-compatible values; canonical JSON is compact, sorted ASCII without a newline, and `to_json_bytes()` adds exactly one newline. `repr()` for report, cell, metric, and prediction is evaluator-safe and does not expose hidden values.

No cell mapping contains a member ID, score, truth label, feature name, raw measurement, or arbitrary caller-provided text. Cell order is fixed (`overall`, then the observed `sex:F`, `sex:M`, and `sex:U` cells in that order); absent categories have no cell. Metric order is fixed by `TASK_METRICS`; `status_counts` equals the cell-status histogram and `metric_counts` gives the count for every fixed metric name. A structural-invalid fallback report uses only the static safe identities `unavailable`, seed `0`, size `0`, one `overall` cell with `FAIL/STRUCTURAL_INVALID`, zero structural counts, null truth-dependent counts, and null metric evidence; it never echoes an invalid policy/cohort/prediction value. The evaluator never mutates the cohort, policy, or prediction tuple.

The report also carries a `reason_code`: `OK` or `WITHIN_BOUND` for a passing report, `OUTSIDE_BOUND` or `STRUCTURAL_INVALID` for a failing report, and `COHORT_TOO_SMALL`, `INSUFFICIENT_SUPPORT`, `MISSING_PREDICTION`, or `MISSING_SCORE` for an unevaluable report. The report-level reason reflects the highest-precedence blocking condition.

## Evaluation algorithm

1. Validate exact `NativeCohort`, `TaskUtilityPolicy`, and tuple-of-`TaskPrediction` types, including length equality. Any malformed typed object returns one fixed structural `FAIL` report using the static fallback identities and no offending value, rather than raising an error that could echo caller-controlled data.
2. For each member/prediction pair, privately derive the binary truth from `DisorderKind`, read only the visible demographic sex for subgroup assignment, and count missing decisions/scores. No per-member result is retained in the returned report.
3. Build the overall cell and requested fixed sex cells from aggregate counters. Compute the metrics above using deterministic arithmetic, exact rank/tie handling, and explicit support floors.
4. Apply policy bounds and status/reason precedence. A required overall threshold failure or subgroup threshold failure blocks the report. A present subgroup with insufficient class support is `UNEVALUABLE` and makes the report `UNEVALUABLE`; an absent sex category is not emitted and does not block. Optional score metrics may be unevaluable without blocking only when `require_probability_scores` is false.
5. Return an immutable report whose mappings contain only aggregate-safe values. Re-running with the same cohort, policy, and prediction tuple yields byte-identical JSON; changing prediction order or values changes only aggregate results and never reveals which member contributed.

## Testing and acceptance

Tests cover:

- strict frozen policy/prediction/cell/report models, exact registries, type/range/duplicate rejection, immutable mappings, canonical serialization, and evaluator-safe representations;
- deterministic confusion metrics, ties-correct AUROC, Brier score, missing decision/score semantics, threshold pass/fail, support floors, cohort-size and unevaluable-member precedence, and fixed subgroup cell order;
- latent truth and patient/member IDs never appearing in mappings, JSON, repr, or error text, including hostile IDs and malformed injected objects;
- repeated evaluation byte identity, input immutability, no real-data/path/model/callable arguments, and AST/import boundaries excluding governed runtimes, package writers, `Path`, CSV, DuckDB, and Synthea;
- guide and README usage examples that show a visible-pipeline prediction tuple and explicitly distinguish task-execution diagnostics from clinical utility, real-data generalization, privacy, prevalence, release, and Synthea evidence.

The slice is complete when the evaluator is fully typed and deterministic, aggregate reports cannot expose hidden truth or member-level outputs, the focused and full test suites plus Ruff/schema/whitespace checks pass, and the main branch contains the reviewed implementation. It does not satisfy the future package-level counterfactual-analysis or governed real-label evaluation gates.
