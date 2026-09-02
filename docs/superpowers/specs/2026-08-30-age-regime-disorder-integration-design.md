# Age-Regime Disorder Integration Design

**Status:** Implementation complete; evaluator-only, uncalibrated

## Purpose

Add an evaluator-only composition layer that applies the repository's reviewed
growth-disorder scenario modules to the age-regime physiology layer. The result
will support coherent healthy, familial-short-stature, constitutional-delay,
growth-hormone-deficiency, undernutrition, and excess-weight trajectories from infancy through adolescence,
while preserving the existing visible eight-resource fixture package and its
exact-schema smoke contract.

This is a development mechanism, not a calibration release. It will not claim
that module frequencies, timing, treatment response, or observed trajectories
represent PPOC or any clinical population.

## Scope and boundaries

The slice adds a new engine-neutral evaluator API. It does not change
`datapackage.json`, CSV headers or rows, manifests, ordinary loader APIs,
`generate_smoke`, the existing `HealthyKernel`, or the existing
`DisorderTrajectoryKernel` output. It does not add prevalence, demographic,
utilization, ancillary-resource, counterfactual, clinical-reference,
privacy-audit, or Synthea behavior.

All returned disorder state, event traces, regime state, z-scores, and
age-regime points remain hidden evaluator objects. No truth manifest or event
trace is emitted by this API.

## Recommended architecture

### Composition kernel

Add `AgeRegimeDisorderKernel` in a new
`src/synthetic/native/age_regime_disorder.py` module:

```python
AgeRegimeDisorderKernel(
    physiology: AgeRegimeTrajectoryKernel,
    module: GrowthDisorderModule,
).generate(
    patient: PatientState,
    ages_days: tuple[int, ...],
    streams: NamedRandomStreams,
) -> AgeRegimeDisorderTrajectory
```

The constructor validates the same module contract as
`DisorderTrajectoryKernel`: a `DisorderKind`, nonempty `module_version`, and
callable state, effect, and event methods. The composition kernel never calls
`HealthyKernel`, `DisorderTrajectoryKernel`, a CSV writer, or a resource mapper.
When a module exposes the optional `validate_patient(patient)` eligibility hook,
the composition kernel invokes it before any reference-backed baseline
generation; this keeps reference-incompatible scenarios fail-closed without
changing modules that do not need patient eligibility.

### Evaluator container

Add a frozen `AgeRegimeDisorderTrajectory` model containing:

- `physiology: AgeRegimeTrajectory` — the age-regime points and sampled
  age-regime state;
- `disorder: LatentDisorderState` — the module state; and
- `events: tuple[ClinicalEvent, ...]` — the module's hidden event trace.

Construction rejects the wrong model types, non-tuple event collections, and
mismatched patient IDs. Empty events are valid for healthy or zero-effect
modules; nonempty traces must pass the existing causal event validator. The
container is evaluator-only and does not replace `LatentTrajectory`.

### Age-regime state injection

The age-regime kernel gains a backward-compatible evaluator method for
sampling and replaying a validated `AgeRegimeState`: `sample_state(streams)`
and `generate(..., *, state=...)`. The ordinary `generate(...)` path still
samples its own state exactly as before. A supplied state must use the current
age-regime module version and satisfy the configured puberty domain; residual
and head streams remain deterministic and isolated.

The disorder composition samples age-regime state and disorder state from
their separate named streams before generating points. This permits a module
to make an explicit, deterministic schedule adjustment without resampling the
patient's birth or childhood channels.

## Effect bridge and causal policy

Existing modules expose `height_z_delta` and `bmi_z_delta`. The adapter treats
these as generic linear-size and body-composition effect channels only at the
composition boundary:

- before the 24-month transition, the height channel adjusts `length_z` and
  the BMI channel adjusts the independently generated `weight_z`; length and
  weight are then re-requested from the reference;
- at transition, the same two channels adjust length and weight, standing
  height is derived with the configured length-to-height conversion, and BMI
  is derived from that height and weight; and
- after transition, the channels adjust `height_z` and `bmi_z`, and weight is
  derived from standing height and BMI.

This preserves the two-independent-dimensions rule and all physical
identities. It is an explicit uncalibrated adapter convention, not a claim
that a BMI z-score is a validated infant weight z-score.

The adapter applies finite effect deltas at the requested ages and rejects
nonfinite or nonphysical reference and derived values. It recomputes
age-regime velocities from the adjusted comparable body size and weight, and
rechecks transition continuity after effects are applied.

Constitutional delay has one explicit timing rule: its sampled
`puberty_delay_days` shifts the age-regime puberty onset, bounded by the
configured puberty domain and maximum age. The module's overlapping negative
height effect is not applied a second time in the shifted pubertal interval;
the shifted smooth-step is the adapter's physiology representation, while
the module still supplies its hidden state and causal event schedule. Other
modules retain their existing effect functions unchanged. If a shifted
schedule cannot fit the configured domain, generation fails closed.

The healthy module is a valid composition case. Its zero effects and empty
events produce physiology equal to the ordinary age-regime kernel for the same
state and streams, wrapped in the evaluator container.

## Randomness and reproducibility

The composition uses the existing age-regime streams
`regime.birth`, `regime.childhood`, `regime.puberty`, `regime.residual`, and
`regime.head`, plus the module's existing `disorder.<kind>` stream. It never
requests the existing `growth` stream. Identical reference identity,
configuration, patient, module version/configuration, named streams, and seed
produce identical state, points, disorder state, and events.

The adapter does not infer prevalence from module selection and does not add a
final label-allocation step. Module selection remains an explicit caller
choice until a later governed cohort/calibration slice.

## Validation and tests

The implementation will use TDD and add focused tests for:

1. the evaluator container's type, patient, and causal-event validation;
2. deterministic healthy composition equivalence;
3. familial short stature effects before and after transition without breaking
   the length/weight and height/BMI identities;
4. constitutional-delay puberty-onset shifting, bounded recovery semantics,
   and event preservation;
5. growth-hormone-deficiency, undernutrition, and excess-weight onset, treatment,
   response/nonresponse events, and post-treatment trajectory changes;
6. all five age regimes, sparse transition samples, derived velocities, and
   adjusted continuity;
7. isolated stream recording and the absence of `growth` requests;
8. invalid module contracts, module state/kind mismatches, malformed events,
   unsupported domains, nonfinite deltas, overflow, and nonphysical reference
   values; and
9. a structural check that no visible schema, exporter, smoke, or manifest path
   imports the evaluator integration.

The existing full test suite, Ruff, schema check, and whitespace check remain
required. The new tests use only the injected test reference under
`tests/synthetic`; no real rows or clinical reference tables are added.

## Documentation

`docs/synthetic-generator.md` will gain a short section showing construction
with the injected reference and one reviewed module. It will state that the
composition is evaluator-only, the module state/events are hidden, defaults
are uncalibrated, the pre-transition effect bridge is a development convention,
and visible CSV generation remains unchanged. It will explicitly defer
prevalence/demographic calibration, disorder-critical EHR descendants,
held-out validation, privacy auditing, and Synthea conformance.

## Deferred work

This design intentionally stops before:

- adding incidence, cohort, observation, or prevalence calibration;
- producing diagnosis, laboratory, medication, referral, utilization, or
  patient-summary descendants;
- generating complete visible packages from age-regime trajectories;
- counterfactual world orchestration and change matrices;
- public WHO/CDC reference artifacts or clinical validation;
- governed held-out validation or linkage/membership/attribute-inference
  audits; and
- implementing or comparing a Synthea-backed engine.

Those are separate gates after this evaluator composition is verified.
