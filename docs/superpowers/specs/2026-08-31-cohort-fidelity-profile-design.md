# Native Cohort Fidelity/Profile Report

**Date:** 2026-08-31
**Status:** Implementation complete; evaluator-only, uncalibrated
**Parent:** [Synthetic Pediatric Growth Fixture System Design](2026-08-30-synthetic-growth-fixtures-design.md)
**Prerequisites:** [Native calibrated cohort profile](2026-08-31-native-cohort-profile-design.md), age-regime/disorder kernels, and evaluator observation/resource contracts

## Purpose

The native cohort layer now assembles deterministic fictional patients from released aggregate demographics, an explicit latent-module prior, age-regime trajectories, and the observation process. It currently exposes only a small count summary, so callers cannot inspect whether one generated cohort has the expected visible demographic mix, what latent module mix was actually sampled, how many patients exhibit observable or recorded event evidence, or whether growth summaries are complete and finite.

This slice adds a synthetic-only evaluator report over an already-generated `NativeCohort`. It is a profile/preflight diagnostic, not a governed real-data comparison. The report measures the visible cohort, preserves separate latent, observable, and recorded layers, summarizes growth and observation coverage by configured age windows, and applies a strict in-memory policy with explicit `PASS`, `FAIL`, and `UNEVALUABLE` statuses. It never reads a path, accepts a real-data row or key, imports the governed calibrator/held-out/privacy runtimes, or changes generated labels to meet a target.

## Goals

1. Provide one immutable `CohortValidationPolicy` that declares bounded sample-size, proportion, growth, and coverage tolerances before evaluation.
2. Produce one immutable aggregate-only `CohortValidationReport` with fixed checks and deterministic mappings.
3. Compare visible sex, ethnicity, and primary-race proportions with the aggregate sampling profile after applying the documented blank/nonresponse-to-`Unknown` projection. Do not compare a merged visible category with an unrecoverable source cell.
4. Report latent module prevalence from `trajectory.disorder.kind`, observable phenotype evidence from source events, and recorded recognition/workup/diagnosis evidence from the visible observation frame as different layers. Never equate `DisorderKind.HEALTHY` with the real `healthy_flag`, and never equate a fictional event code with a governed growth-diagnosis target.
5. Summarize age-window trajectory values and visit coverage using evaluator objects while keeping patient identifiers, event payloads, disorder severity, and truth hashes out of the report.
6. Make underpowered or missing evidence `UNEVALUABLE`, invalid values `FAIL`, and only policy-satisfied checks `PASS`.
7. Ensure equal cohort and policy inputs produce byte-equivalent mappings and no report contains hidden truth, source metadata, paths, or row-level details.
8. Leave the production CLI, package exporter, authoritative augmentation, governed held-out validation, privacy audit, clinical review, task utility, ancillary resources, and Synthea route unchanged and explicitly deferred.

## Non-goals and claim boundary

- The report does not load PPOC CSVs, calibration artifacts from paths, held-out data, privacy evidence, keys, descriptors, or package outputs.
- The report does not estimate or validate real latent prevalence. `recorded_growth_dx_probability` is retained as an aggregate profile datum but is not used as a target for fictional diagnosis events.
- The report does not infer `healthy_flag`, `growth_dx_flag`, chronic flags, or augmented fields. Healthy module membership, observable phenotype, and recorded event evidence remain separately named diagnostics.
- The report does not tune module weights, allocate labels, resample patients, change trajectories, or mutate a cohort.
- Growth summary thresholds are explicit development sanity bounds unless a caller supplies reviewed bounds; they are not WHO/CDC reference claims or clinical validity criteria.
- The report cannot prove representativeness, held-out fidelity, clinical validity, privacy, non-matchability, HIPAA status, release readiness, or Synthea conformance.

## Public interface

Add `synthetic.cohort_validation`:

```python
class CohortValidationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNEVALUABLE = "UNEVALUABLE"

@dataclass(frozen=True)
class CohortValidationPolicy:
    policy_id: str
    policy_version: str
    minimum_cohort_size: int
    minimum_cell_support: int
    minimum_event_support: int
    proportion_tolerance: float
    growth_tolerances: Mapping[str, float]
    required_age_windows: tuple[tuple[str, int, int], ...]

@dataclass(frozen=True)
class CohortComparison:
    name: str
    layer: str
    status: CohortValidationStatus
    observed_value: float | int | None
    target_value: float | int | None
    difference: float | None
    tolerance: float | None
    support: int
    denominator: int
    reason_code: str

@dataclass(frozen=True, repr=False)
class CohortValidationReport:
    report_version: str
    policy_id: str
    cohort_profile: str
    seed: int
    status: CohortValidationStatus
    comparisons: tuple[CohortComparison, ...]

    def to_mapping(self) -> dict[str, object]: ...

def validate_native_cohort(
    cohort: NativeCohort,
    policy: CohortValidationPolicy,
) -> CohortValidationReport: ...
```

The exact constructor may use a frozen `AgeWindow` value object instead of raw triples if that better matches local conventions, but the serialized policy and report keys above are fixed. `growth_tolerances` has the canonical keys `height_z_score`, `bmi_z_score`, `height_velocity_cm_per_year`, and `weight_velocity_kg_per_year`; each value is a nonnegative finite absolute bound. Required age windows are sorted, non-overlapping, half-open `[lower, upper)` intervals and must use safe tokens. A window may be unevaluable when no trajectory point falls inside it.

`CohortComparison` is aggregate-only. `name`, `layer`, and `reason_code` are from fixed registries. A targeted comparison has finite observed/target/difference/tolerance for `PASS` or `FAIL`; difference must equal the absolute numeric difference. An aggregate diagnostic comparison has a finite observed value (or a count) and null target/difference/tolerance for `PASS` or `FAIL`; this is the form used for latent/observable/recorded layer rates and coverage checks. `UNEVALUABLE` comparisons always have null observed/target/difference/tolerance. Support and denominator are counts only. No comparison contains a patient ID, visit ID, event code, severity, source path, calibration support/denominator, or private truth hash.

## Metrics and semantics

### Visible demographic checks

The evaluator counts the visible `CohortMember.demographics` values. It projects the aggregate profile categories with the same fixed rules as generation: the empty source ethnicity/race category is added to visible `Unknown`, while nonempty values remain unchanged; primary race is `race_1`. The observed proportion is `count / cohort_size`. A category with fewer than `minimum_cell_support` observed members is `UNEVALUABLE` even when the aggregate profile has a released value. If the entire cohort is below `minimum_cohort_size`, all proportion checks are `UNEVALUABLE`. Otherwise a check is `PASS` when its absolute difference from the projected target is at most `proportion_tolerance`, and `FAIL` when it exceeds it. The report includes fixed category names in canonical order, including visible categories that have zero observed support.

The profile's rounded weights are normalized for target projection only. The report does not disclose the aggregate artifact's source denominator or support; target values are probabilities already present in the in-memory `CalibrationSamplingProfile`.

### Separate prevalence layers

The report emits fixed aggregate checks for:

- `latent_module.<module>`: the fraction of members whose evaluator-only trajectory state has that `DisorderKind`;
- `observable_phenotype`: the fraction of members with an observable phenotype source event in the private trajectory event trace; and
- `recorded_recognition`, `recorded_workup`, and `recorded_diagnosis`: fractions with the corresponding visible `ObservationFrame.events` kind.

These checks use a minimum event support. A zero-count layer is `PASS` for a cohort that is large enough and whose absence is an observed result; it is `UNEVALUABLE` only when the cohort or evidence is insufficient to evaluate the layer. They have no real-data target in this slice, so `target_value`, `difference`, and `tolerance` are null and the checks are status-only diagnostics with an aggregate observed rate. Their names explicitly identify the layer. A report with status `PASS` therefore means only that structural/profile checks and configured sanity bounds passed; it is not prevalence evidence.

### Age-window growth and observation summaries

For every required window and each trajectory metric, the evaluator collects finite values from `AgeRegimePoint` instances in the window. It reports the arithmetic mean and point support as aggregate comparisons against a zero-centered development bound. `height_z_score` and `bmi_z_score` use the corresponding z fields; velocity metrics use the derived velocity fields and omit the first point when it is `None`. A metric with fewer than `minimum_cell_support` values is `UNEVALUABLE`; a nonfinite or physically invalid typed value is `FAIL`; otherwise it is `PASS` when the absolute mean is at most the declared tolerance. The metric name includes the window token, for example `growth.infant.height_z_score_mean`.

The report also includes fixed observation coverage checks named `coverage.cohort_size`, `coverage.members_with_observation`, and `coverage.members_with_event`: cohort size, members with at least one visit, and members with at least one recorded event. These are counts and fractions only. Missing frames, mismatched patient identities, duplicate member IDs, nonmonotone ages, or malformed evaluator objects produce `FAIL` without including offending values in the public exception or report. A valid cohort generated by `generate_native_cohort` should pass these structural checks; direct hand-built malformed inputs are intentionally detectable.

## Status aggregation and failure behavior

The report contains a fixed check ordering: `cohort_size`, visible demographics in registry order, latent modules in `DisorderKind` order, recorded layer checks, then age-window growth checks and observation coverage. Overall status is `FAIL` if any check fails, `UNEVALUABLE` if no check fails but at least one check is unevaluable, and `PASS` otherwise.

`validate_native_cohort` accepts only a `NativeCohort` and `CohortValidationPolicy`. It validates policy and cohort object types before accessing members. It never catches and republishes patient-level exception text. Unexpected malformed evaluator input is represented by a fixed `FAIL` comparison or a fixed `UNEVALUABLE` comparison, depending on whether the evidence is invalid or insufficient; no raw exception leaves the function. Policy construction errors remain actionable field-level errors and contain no patient data.

## Reproducibility and serialization

The report preserves the cohort profile and seed, policy identity, fixed report version, comparison order, and aggregate numeric values. `to_mapping()` recursively returns ordinary JSON-compatible values and excludes the `NativeCohort.calibration` object, module prior, trajectories, frames, bundles, event traces, source reference, and all row identifiers. `repr(report)` is evaluator-safe and does not include comparison payloads. Equal inputs must serialize to identical canonical JSON when encoded with sorted keys; changing a cohort seed or policy must be observable through the seed or comparison values.

## Boundary and testing requirements

Tests use the checked-in fictional reference, hand-built aggregate calibration profile, and generated `NativeCohort` fixtures only. They must cover:

1. frozen policy/comparison/report models, exact keys, enum/status consistency, safe tokens, finite bounds, window ordering, and constructor rejection;
2. projected blank/unknown demographic targets, canonical category ordering, target normalization, support thresholds, and tolerance pass/fail behavior;
3. distinct latent/observable/recorded rates, including a healthy member not being counted as a real healthy flag and a disorder member without a recorded diagnosis;
4. age-window growth means, missing first-point velocity, zero/insufficient support, nonfinite or malformed evaluator values, and coverage checks;
5. deterministic replay and report mapping/repr redaction of IDs, event codes, severity, calibration support/denominator, paths, truth, and latent state;
6. malformed cohort/member/frame/trajectory behavior with fixed aggregate statuses and no exception leakage; and
7. AST/import boundary tests proving the module imports neither governed calibration/held-out/privacy runtimes nor DuckDB, does not accept path/key/report arguments, and does not write files or call package/export lifecycle functions.

Documentation adds a concise profile-report section to `docs/synthetic-generator.md` and a roadmap sentence to `README.md`. It must state the exact API, the separate prevalence layers, the projected `Unknown` rule, `PASS`/`FAIL`/`UNEVALUABLE` semantics, and the non-claims. Existing held-out, privacy, package-export, and Synthea boundaries remain unchanged.

## Acceptance criteria

1. A strict in-memory policy and report model rejects malformed fields and emits only fixed aggregate keys.
2. Generated demographic checks use the same blank/nonresponse projection as the cohort and compare only visible, recoverable categories.
3. Latent module, observable phenotype, and recorded event diagnostics remain separate and never use recorded calibration flags as allocators or targets.
4. Growth means and coverage checks are deterministic, age-windowed, bounded, and explicit about insufficient support.
5. Equal inputs produce byte-equivalent report mappings; no report, repr, or exception exposes patient/visit identifiers, event payloads, calibration supports/denominators, or hidden truth.
6. Existing generation, package export, held-out, privacy, schema, and CLI behavior remains unchanged; no governed or filesystem boundary is introduced.
7. Focused tests, full tests, Ruff, schema validation, whitespace checks, and a fresh broad review pass before merge; `main` equals `origin/main` after push.
