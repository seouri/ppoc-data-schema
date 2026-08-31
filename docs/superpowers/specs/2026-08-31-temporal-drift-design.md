# Temporal Drift Evaluation Contract

**Date:** 2026-08-31  
**Status:** Approved next roadmap slice under the synthetic pediatric growth-fixture design  
**Parent:** [Synthetic Pediatric Growth Fixture System Design](2026-08-30-synthetic-growth-fixtures-design.md)

## Purpose

This slice adds an evaluator-only temporal-drift gate for a completely fictional in-memory `NativeCohort`. It checks whether visit, observation, growth-window, and recorded-event sequences remain temporally coherent across the configured age windows and whether the hidden causal event schedule remains ordered. The output is a deterministic aggregate report with `PASS`, `FAIL`, or `UNEVALUABLE` checks.

Temporal drift here means an age-window or sequence behavior that falls outside a frozen development policy or violates a causal/time-order invariant. The policy is declared before evaluation and is not learned from the cohort. This is a development diagnostic, not evidence of real-population longitudinal fidelity, prevalence, clinical validity, privacy/non-matchability, task utility, or release readiness.

## Scope and boundaries

- Input is only a typed fictional `NativeCohort` and an explicit `TemporalDriftPolicy`. The public API accepts no path, file, descriptor, key, calibration artifact, held-out report, privacy input, output destination, or real-data row.
- The evaluator reads `CohortMember.frame` visible visits/events and `CohortMember.trajectory` evaluator-held points/events. Hidden source events may be inspected to validate causal order and timing, but their ages, payloads, hashes, patient IDs, and event traces never appear in mappings, `repr`, exception text, or reports.
- Metrics are computed in memory and returned as immutable objects. There is no CLI, filesystem writer, package exporter, manifest call, DuckDB dependency, calibration import, held-out import, privacy import, or Synthea dependency.
- Reports contain fixed metric names, age-window identifiers, aggregate counts, bounded numeric summaries for visible metrics, statuses, and fixed reason codes only. They contain no patient/visit identifiers, hidden event values, source paths, seeds, random streams, calibration supports/denominators, or row sequences.
- Malformed typed cohort evidence is `FAIL` with a fixed structural reason; missing or insufficient evidence is `UNEVALUABLE`, never `PASS`; a visible metric outside its frozen bound is `FAIL`.

## Frozen policy

The module exposes immutable `TemporalDriftPolicy`, `TemporalWindowPolicy`, and `TemporalCheck` values. Safe identifiers use the existing aggregate-token rules. Required age windows are ordered, non-overlapping, half-open intervals `(window_id, lower_age_days, upper_age_days)`.

`TemporalWindowPolicy` contains:

```python
@dataclass(frozen=True)
class TemporalWindowPolicy:
    window_id: str
    lower_age_days: int
    upper_age_days: int
    minimum_member_support: int
    minimum_growth_points: int
    minimum_visible_visits: int
    minimum_growth_coverage: float
    minimum_visible_visit_coverage: float
    maximum_mean_inter_visit_days: float
    maximum_visit_count_step: float
    maximum_recorded_event_rate_step: float
```

`TemporalDriftPolicy` contains:

```python
@dataclass(frozen=True)
class TemporalDriftPolicy:
    policy_id: str
    policy_version: str
    minimum_cohort_size: int
    maximum_unevaluable_checks: int
    windows: tuple[TemporalWindowPolicy, ...]
```

`minimum_member_support` is the number of members required for a window-level metric and must be positive. `minimum_growth_points` and `minimum_visible_visits` are nonnegative per-member coverage floors. `minimum_growth_coverage` and `minimum_visible_visit_coverage` are fractions in `[0, 1]` that the corresponding aggregate coverage must meet. `maximum_mean_inter_visit_days` bounds the aggregate mean gap among visible visits in the window. `maximum_visit_count_step` bounds the absolute change in mean visit count between adjacent windows. `maximum_recorded_event_rate_step` bounds the absolute change in the fraction of members with at least one recorded event between adjacent windows. All thresholds are finite and nonnegative (coverage fractions are additionally in `[0, 1]`); booleans, empty windows, duplicate IDs, unsafe IDs, reversed/overlapping bounds, and mutable inputs are rejected. The policy requires at least one window and a positive `minimum_cohort_size`.

The checked-in default policy is not a clinical reference. Tests use a small fictional policy with explicit values. A future approved policy may add metrics only by changing the versioned registry and tests; arbitrary metric names are rejected.

## Metric registry and semantics

The fixed metric registry is:

```text
growth_window_coverage
visible_visit_coverage
visible_event_rate
mean_inter_visit_days
mean_visit_count_step
recorded_event_rate_step
causal_event_order
causal_event_timing
```

For each configured window, the evaluator assigns every trajectory point and visible visit/event to the inclusive-lower/exclusive-upper age interval. `growth_window_coverage` is the number of members with at least `minimum_growth_points` trajectory points in the window divided by cohort size, and passes when it meets `minimum_growth_coverage`. `visible_visit_coverage` is the number of members with at least `minimum_visible_visits` visible visits in the window divided by cohort size, and passes when it meets `minimum_visible_visit_coverage`. `visible_event_rate` is the fraction of members with one or more visible recorded events in the window. These visible aggregate values may be included in comparisons and are never tied to a member identifier.

`mean_inter_visit_days` uses consecutive visible visit ages within the window. A member with fewer than two visits contributes no interval; an empty interval population is `UNEVALUABLE`. A finite aggregate mean above the window policy bound is `FAIL`.

`mean_visit_count_step` compares adjacent-window mean visible visit counts. `recorded_event_rate_step` compares adjacent-window visible event rates. A step is `UNEVALUABLE` when either adjacent window lacks minimum support; a finite absolute step above the relevant bound is `FAIL`. The first window has no predecessor and receives no step comparison.

`causal_event_order` validates evaluator-held trajectory source events against the fixed phase order: `latent_onset`, `observable_phenotype`, `recognition_opportunity`, `workup`, `recorded_diagnosis`, `treatment_start`, and one terminal treatment outcome (`treatment_response` or `treatment_nonresponse`). Ages must be nondecreasing, phases strictly increasing, treatment outcomes must follow treatment start, hidden onset must remain hidden, and all events must belong to the member's patient. The report emits only `PASS`/`FAIL` and a fixed reason code.

`causal_event_timing` checks that every source event age is nonnegative and every visible visit/event remains inside the member's declared observation window. Existing trajectory/frame types enforce nonnegative point and window ages; this check does not require a hidden event to fall inside the visible window because pre-observation onset is valid. It does not disclose the event age or event type. A malformed hidden object is `FAIL`; absent evaluator truth is `UNEVALUABLE`.

## Report contract

`TemporalComparison` is immutable and aggregate-only:

```python
@dataclass(frozen=True, repr=False)
class TemporalComparison:
    metric: str
    window_id: str | None
    status: Literal["PASS", "FAIL", "UNEVALUABLE"]
    reason_code: str
    observed: float | int | None
    target: float | int | None
    difference: float | None
    support_count: int | None
```

`target` is the applicable lower/upper bound or `None` for invariant/diagnostic checks. For a lower-bound metric, `difference = max(0, target - observed)`; for an upper-bound metric, `difference = max(0, observed - target)`; for an adjacent-window step, `difference = max(0, abs(observed) - target)`. A passing visible comparison therefore has zero difference. `UNEVALUABLE` comparisons always null `observed`, `target`, `difference`, and `support_count`. Causal comparisons always null numeric fields even when they pass or fail. `TemporalComparison` validates fixed metric/status/reason registries, finite numeric fields, safe window IDs, and no identifier-like text. Its `repr` is evaluator-safe and omits all comparison payloads.

`TemporalDriftReport` is immutable and serializes exactly these top-level keys:

```text
report_version
policy_id
policy_version
cohort_profile
cohort_seed
cohort_size
status
status_counts
metric_counts
checks
comparisons
```

`cohort_profile` and `cohort_seed` are already aggregate-safe cohort metadata. `checks` contain only fixed names, statuses, and reason codes. Comparisons are sorted by fixed metric order, window order, and status tie-breaker. The canonical JSON uses sorted keys, compact separators, ASCII, and a trailing newline only in `to_json_bytes()`. `repr(report)` contains no comparisons, values, IDs, hidden state, or event data.

Global status is `FAIL` if any comparison fails or structural evidence is invalid. Otherwise it is `UNEVALUABLE` when the cohort is below `minimum_cohort_size`, the number of unevaluable comparisons exceeds `maximum_unevaluable_checks`, or a required window lacks support. Otherwise it is `PASS`.

`validate_temporal_drift(cohort, policy) -> TemporalDriftReport` validates object types before reading members and never republishes an injected exception. A malformed member, trajectory, frame, or event produces a fixed aggregate `FAIL` comparison. A cohort with absent private truth produces `UNEVALUABLE` causal checks while visible metrics can still be evaluated. The evaluator does not mutate the cohort or policy.

## Testing requirements

Tests use only `NativeCohort` fixtures generated from existing fictional kernels and hand-built typed objects. They must cover:

1. frozen policy/window/comparison/report models, exact keys, enum/status consistency, finite nonnegative bounds, safe tokens, window ordering, support floors, and rejection of booleans, mutable mappings, IDs, paths, truth terms, and unknown metric/reason names;
2. lower-inclusive/upper-exclusive assignment, empty windows, minimum support, coverage counts, visible event rates, interval means, adjacent-window step tolerances, and deterministic ordering;
3. valid causal source-event order plus malformed ages, phase order, treatment outcome order, hidden-onset visibility, patient mismatch, and missing private truth;
4. `PASS`/`FAIL`/`UNEVALUABLE` precedence, null comparison fields for unevaluable checks, structural malformed-member handling, fixed reason codes, and no exception leakage;
5. deterministic canonical JSON and evaluator-safe `repr`, with reports free of synthetic patient/visit IDs, event codes, ages tied to a patient, latent state, event traces, hashes, paths, seeds beyond the aggregate cohort seed, calibration supports/denominators, and truth terms; and
6. AST/import boundary tests proving the module imports neither governed calibration/held-out/privacy runtimes nor DuckDB, `Path`, CSV/package/manifest/export writers, or Synthea, and exposes no path/key/report/output arguments.

The full repository suite, Ruff, schema check, and whitespace check remain required. No real or gated data is used.

## Documentation and deferred gates

`docs/synthetic-generator.md` and `README.md` add a concise evaluator-only temporal-drift section with the exact API, fixed metrics, age-window and causal-order semantics, status precedence, and non-claims. The section states that this report diagnoses development-sequence behavior only; it does not establish real-data temporal fidelity, growth-disorder prevalence, clinical validity, privacy/non-matchability, task utility, release readiness, or Synthea conformance.

This slice does not add a CLI, package-file reader, real/held-out comparison, calibration tuning loop, longitudinal model fitting, clinical review, task-utility experiment, privacy attack, prevalence estimator, or Synthea adapter. Those remain separate approved gates.

## Acceptance criteria

1. A valid fictional `NativeCohort` and frozen policy produce a deterministic aggregate-only temporal report.
2. Age-window coverage, visible sequence metrics, adjacent-window steps, and causal event invariants use the exact fixed semantics above.
3. Invalid visible or hidden temporal evidence fails with fixed aggregate reasons; missing/private evidence is `UNEVALUABLE`, never silently `PASS`.
4. No report, mapping, repr, or exception exposes patient/visit identifiers, hidden event values, event traces, paths, keys, or row sequences.
5. Existing generation, observation, resource export, calibration, held-out, privacy, schema, and CLI behavior remains unchanged.
6. Focused tests, full tests, Ruff, schema validation, whitespace checks, and an independent broad review pass before merge; `main` equals `origin/main` after push.
