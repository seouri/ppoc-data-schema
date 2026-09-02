# Golden growth-trajectory forced coverage

**Status:** Evaluator-only, in-memory, fictional development contract. The catalog version is `growth-golden-v1`.

This guide describes a deterministic forced coverage suite for auditing structural and directional behavior in the native growth-trajectory evaluator. It is deliberately a compact case catalog, not a cohort sampler: it allocates neither disease prevalence nor demographics, and it does not generate a package. The native generator remains the release-one route, while the [optional Synthea handoff](synthea-conformance.md) remains external and downstream.

## Fixed fictional catalog

The catalog contains exactly fourteen fictional cases: `golden-healthy-v1`, `golden-familial-short-stature-v1`, `golden-constitutional-delay-v1`, `golden-growth-hormone-deficiency-v1`, `golden-pediatric-hypothyroidism-v1`, `golden-celiac-disease-v1`, `golden-small-for-gestational-age-catch-up-v1`, `golden-small-for-gestational-age-persistent-v1`, `golden-turner-syndrome-v1`, `golden-turner-syndrome-untreated-v1`, `golden-undernutrition-v1`, `golden-undernutrition-untreated-v1`, `golden-excess-weight-v1`, and `golden-excess-weight-treated-v1`. Each case uses the same fixed age tuple `(0, 700, 730, 760, 3000, 4379, 4380, 4740, 5470, 5475, 6575, 7305)` so the runner must encounter all five `GrowthRegime` values: `infancy`, `transition`, `childhood`, `puberty`, and `adolescence`.

Every case contains hidden explicit states for physiology and disorder timing. These states, the fictional patient token, seed, points, measurements, velocities, and event payloads are evaluator-only and never enter the report mapping or canonical JSON. The default state uses a fixed puberty onset at day 4380, fixed tempo of 1095 days, and explicit fictional finite z-score offsets. Those numbers are deterministic test inputs, not clinical timing or distribution claims.

The evaluator checks anthropometric identities, positive finite measurements, finite derived velocities, strictly ordered points, required regimes, required causal event types, and repeated-run equality. It also probes the development modules directly for `zero`, `constant_negative`, `delayed_recovery`, `progression_response`, `progressive_negative`, `positive_after_onset`, `birth_catch_up`, `delayed_progressive`, `progressive_positive`, and `positive_progression_response` directional patterns. The healthy case uses zero height and BMI effects; familial short stature uses a constant-negative height effect and zero BMI effect; constitutional delay uses delayed recovery in height and zero BMI effect; treated growth-hormone deficiency and treated pediatric hypothyroidism use progression/response in height and positive-after-onset BMI; celiac disease uses weight/BMI-first decline, delayed height decline, and progression/response in both channels; the SGA cases start below reference size at birth, with BMI recovering by the first year while height either catches up by five years or remains persistently short; Turner cases require the female reference, have no birth deficit, and cover both progressive untreated height impairment and treated height response with a positive-after-onset BMI effect; undernutrition cases cover an earlier weight/BMI decline, delayed progressive height impairment, and partial treatment response; and excess-weight cases cover sustained positive BMI growth without requiring a linear-growth effect, including an optional partial treatment response.

Pattern probes may be unobserved ages between trajectory samples because they evaluate a module's direct effect channel rather than add visible measurements. Constitutional delay uses probes `(4380, 4740, 5470)` to require zero, negative, then recovered height effect. Treated growth-hormone deficiency uses probes `(3000, 3510, 3875, 5000)`, treated pediatric hypothyroidism uses `(1460, 1850, 2215, 3000)`, and treated Turner syndrome uses `(1460, 1850, 2215, 3000)` to require zero at onset, negative at treatment, strict improvement during the active response interval, and no later regression at the post-response probe; a plateau is allowed after response completion. Untreated Turner syndrome uses `(1460, 2372, 3285, 4000)` to require progressive negative height effects followed by a bounded plateau and positive-after-onset BMI. Celiac disease uses `(2190, 2640, 3005, 3500)` for both height and BMI, with a delayed height effect and the same treatment-response monotonicity. Both SGA cases use `(0, 365, 730, 1825)`: the birth effect is negative, the BMI channel is monotone toward zero by day 365, and the height channel either reaches zero by day 1825 or remains constant and negative in the persistent branch. Treated undernutrition uses `(2190, 2490, 2672, 3000)` to require weight/BMI-first decline and partial response, while untreated undernutrition uses `(2190, 2370, 3100, 3500)` to require zero height effect during its delay followed by a bounded plateau and progressive negative BMI. Untreated excess weight uses `(2190, 2555, 2920, 3500)` to require a positive BMI rise followed by a sustained plateau, while treated excess weight uses `(2190, 2490, 2672, 2990)` to require a positive BMI effect that decreases without rebound after treatment.

## Repository-root example

The following copy-pasteable example uses only the repository's fictional `RegimeLinearTestReference`; it is not a clinical growth reference. Run it from the repository root after `uv sync`:

```python
from synthetic.golden_trajectories import (
    DEFAULT_GOLDEN_CASES,
    run_golden_trajectory_suite,
)
from tests.synthetic.fakes import RegimeLinearTestReference

reference = RegimeLinearTestReference()  # wholly fictional test reference
report = run_golden_trajectory_suite(reference, cases=DEFAULT_GOLDEN_CASES)
print(report.to_json_bytes().decode("ascii"), end="")
```

The top-level aggregate-only report fields are `report_version`, `status`, and `case_results`. Each item in `case_results` contains only `case_id`, `status`, and fixed `reason_codes`; a passing case has `reason_codes` equal to `("OK",)`. Repeating the call with the same injected reference and catalog produces identical report bytes. Invalid reference, module, or case inputs raise exactly `GoldenTrajectoryUnavailable("golden trajectory suite unavailable")` without echoing submitted values and without exception chaining.

## Evidence boundary

A `PASS` means only that these fourteen forced fictional scenarios satisfied their declared structural, event, identity, directional, and deterministic checks for the injected reference and module versions. It is not prevalence evidence, demographic fidelity, clinical validity, task utility, privacy/non-matchability evidence, held-out evidence, scale evidence, Synthea conformance, or release evidence. It makes no claim about PPOC patients, real growth trajectories, disease frequencies, or profile uniqueness.

This evaluator does not replace schema validation, exact-schema export, augmented derivation and authoritative binding, aggregate calibration, patient-disjoint held-out validation, clinical review, privacy review, task-utility evaluation, reproducibility-at-scale, or release approval. It writes no CSV, manifest, truth file, package, or output directory, and no visible generation or export path imports it automatically.

`EXCESS_WEIGHT` is evaluator-only and neither implies nor writes `obesity_flag`; that field remains separately derived from observed BMI percentile.

For surrounding boundaries, see the [parent synthetic growth-fixture design](superpowers/specs/2026-08-30-synthetic-growth-fixtures-design.md), the [native age-regime trajectory guide](synthetic-generator.md#development-only-age-regime-smoke-example), and the [optional Synthea engine-conformance guide](synthea-conformance.md).
