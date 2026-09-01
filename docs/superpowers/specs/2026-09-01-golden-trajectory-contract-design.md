# Engine-Independent Golden Growth-Trajectory Contract

**Date:** 2026-09-01
**Status:** Approved next dependency-clearing roadmap slice
**Prerequisites:** native age-regime physiology, reviewed development-only disorder modules, and the evaluator-only composition kernel

## Purpose

The parent synthetic-fixture design requires a compact, deterministic golden
library that forces coverage of healthy and growth-disorder trajectories across
all pediatric age regimes. The repository currently has focused unit tests but
no reusable engine-neutral golden contract. This slice adds four fictional,
evaluator-only cases and an aggregate report runner. It makes longitudinal
growth behavior auditable without pretending that a small forced-coverage set
is representative prevalence or clinical evidence.

The native growth-first engine remains release one. The optional Synthea route
remains manifest-only and external; this contract does not import, execute, or
vendor Synthea, Java, network services, real data, or governed inputs.

## Public interface

Add `synthetic.golden_trajectories` with:

```python
GOLDEN_TRAJECTORY_VERSION = "growth-golden-v1"
GOLDEN_CASE_IDS = (
    "golden-healthy-v1",
    "golden-familial-short-stature-v1",
    "golden-constitutional-delay-v1",
    "golden-growth-hormone-deficiency-v1",
)

class GoldenTrajectoryUnavailable(ValueError): ...

class GoldenPattern(str, Enum):
    ZERO = "zero"
    CONSTANT_NEGATIVE = "constant_negative"
    DELAYED_RECOVERY = "delayed_recovery"
    PROGRESSION_RESPONSE = "progression_response"
    POSITIVE_AFTER_ONSET = "positive_after_onset"

class GoldenStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"

@dataclass(frozen=True, repr=False)
class GoldenTrajectoryCase: ...

@dataclass(frozen=True, repr=False)
class GoldenCaseResult: ...

@dataclass(frozen=True, repr=False)
class GoldenTrajectoryReport: ...

DEFAULT_GOLDEN_CASES: tuple[GoldenTrajectoryCase, ...]

def run_golden_trajectory_suite(
    reference: GrowthReference,
    *,
    modules: Mapping[DisorderKind, GrowthDisorderModule] | None = None,
    cases: tuple[GoldenTrajectoryCase, ...] = DEFAULT_GOLDEN_CASES,
) -> GoldenTrajectoryReport: ...
```

The exact `GoldenTrajectoryCase` fields are `case_id: str`,
`patient: PatientState`, `seed: int`, `ages_days: tuple[int, ...]`,
`physiology_state: AgeRegimeState`, `disorder_state: LatentDisorderState`,
`required_regimes: tuple[GrowthRegime, ...]`,
`required_event_types: tuple[str, ...]`, `height_pattern: GoldenPattern`,
`bmi_pattern: GoldenPattern`, and `pattern_probe_ages_days: tuple[int, ...]`.
`GoldenCaseResult` contains `case_id: str`, `status: GoldenStatus`, and
`reason_codes: tuple[str, ...]`. `GoldenTrajectoryReport` contains
`report_version: str`, `status: GoldenStatus`, and
`case_results: tuple[GoldenCaseResult, ...]`; its mapping and canonical JSON
serialization expose only those aggregate fields.

`GoldenTrajectoryCase` contains only typed evaluator inputs: a fictional
`PatientState`, nonnegative seed, strictly increasing ages, an explicit
`AgeRegimeState`, an explicit `LatentDisorderState`, the required-regime tuple,
required event types, and bounded height/BMI pattern declarations. The four
checked-in cases use `syn-golden-*` patient tokens, default age-regime state,
and fixed healthy, familial-short-stature, constitutional-delay, and treated
growth-hormone-deficiency states. Their hidden states never enter ordinary
mappings, manifests, reports, logs, or package files.

The four cases use the fixed age tuple
`(0, 700, 730, 760, 3000, 4379, 4380, 4740, 5470, 5475, 6575, 7305)`
with a default state of puberty onset `4380`, tempo `1095`, and all finite
z-score offsets set to explicit fictional constants. The constitutional-delay
case adds a `360`-day delay, the growth-hormone-deficiency case starts at day
`3000` with treatment at day `3510` and response `0.6`, and the familial case
has severity `1.0`. Probe ages are `(4380, 4740, 5470)` for delayed recovery,
`(3000, 3510, 3875, 5000)` for progression/response, and selected points from
the fixed age tuple for the zero and constant-negative patterns. The case
catalog is a forced-coverage test asset, not a cohort sampler. It does not
allocate disease prevalence or demographics.

## Runner and report semantics

`run_golden_trajectory_suite` accepts an already-loaded injected growth
reference and optional modules. With no module mapping it constructs the four
versioned development modules already in the repository. It creates an
`AgeRegimeTrajectoryKernel` and an `AgeRegimeDisorderKernel` for each case,
generates twice with the same explicit hidden states and named streams, and
checks that the outputs are identical.

Each case must satisfy all of these aggregate checks:

1. output is an `AgeRegimeDisorderTrajectory` for the case's fictional patient;
2. every required age regime is present and points are strictly ordered;
3. every required event type is present in the existing causal order;
4. anthropometric identities, positive finite measurements, and derived
   velocities remain valid through the transition; and
5. the module's direct effect channels satisfy its declared `GoldenPattern` at
   the probe ages: `ZERO` requires all values to be zero;
   `CONSTANT_NEGATIVE` requires height to be negative and BMI zero;
   `DELAYED_RECOVERY` requires zero, negative, then zero height effects;
   `PROGRESSION_RESPONSE` requires zero, negative, then strictly improving
   height effects; and `POSITIVE_AFTER_ONSET` requires zero at onset and
   positive values thereafter. Healthy effects are zero; familial short
   stature uses constant-negative height and zero BMI; constitutional delay
   uses delayed recovery; and growth-hormone deficiency uses progression/
   response height and positive-after-onset BMI.

The result contains one `GoldenCaseResult` per case and a suite status of
`PASS` only when every case passes; otherwise it is `FAIL`. Each result exposes
only its safe case ID, status, and fixed reason codes. It never exposes patient
IDs, ages, states, points, measurements, event payloads, seeds, reference
values, module objects, or hidden truth. Invalid reference/module/case inputs
raise `GoldenTrajectoryUnavailable("golden trajectory suite unavailable")`
without exception chaining or submitted-value echo.

The fixed failure reason registry is
`("NONDETERMINISTIC", "MISSING_REGIME", "MISSING_EVENT",
"IDENTITY_VIOLATION", "HEIGHT_PATTERN", "BMI_PATTERN",
"INVALID_TRAJECTORY")`; a passing case has exactly `("OK",)`. A suite never
silently drops a case or changes the case order.

## Boundary and non-goals

- The module is evaluator-only and in-memory. It accepts no path, CSV, output,
  package, descriptor, key, calibration artifact, held-out report, model,
  network client, or Synthea object.
- It does not write a golden package, visible CSV, truth manifest, event trace,
  prevalence artifact, or release status. Exact-schema package export remains
  a separate caller-controlled gate, and augmented derivation remains subject
  to its explicit oracle/binding contract.
- A passing golden report proves only that the forced fictional scenarios met
  their declared structural and directional assertions for the injected
  reference/module versions. It is not prevalence, demographic fidelity,
  clinical validity, task utility, privacy/non-matchability, held-out,
  reproducibility-at-scale, Synthea, or release evidence.
- The catalog contains no real or governed records and makes no claim about
  PPOC patients or disease frequencies.
- Visible generation, package export, calibration, held-out, prevalence,
  privacy, counterfactual package, task-utility, and Synthea modules do not
  import or consume the golden runner automatically.

## Validation and documentation

Tests use only the repository's fictional `RegimeLinearTestReference` and
default development modules. They cover catalog immutability and exact case
validation, all four cases, all five regimes, physical identities, event
requirements, each directional pattern, repeated-run byte/equality
determinism, custom module/reference failures, malformed hidden states, and
report redaction. Static tests assert no filesystem, CSV, package, governed,
network, Synthea, or production-generator coupling. Documentation labels the
catalog as forced coverage and links the parent design, native trajectory
guide, and optional Synthea handoff guide.

## Deferred work

This slice does not create a patient-disjoint prevalence sample, calibrate
demographics or disease frequency, add clinical citations or human review,
produce an eight-resource golden package, run a 10,000-patient scale profile,
bind an authoritative augmenter, add a Synthea engine, or establish any
clinical, privacy, release, or non-matchability claim. Those remain separate
gates requiring their own approved inputs and review.
