# Evaluator-Only Observation Frame Contract

**Date:** 2026-08-31
**Status:** Implementation complete; evaluator-only; clinical, population, privacy, and release evidence pending
**Parent:** [Synthetic Pediatric Growth Fixture System Design](2026-08-30-synthetic-growth-fixtures-design.md)

## Purpose and boundary

The native trajectory and counterfactual layers currently describe latent growth physiology and causal event traces, but they do not yet model how a fictional patient becomes an observed longitudinal record. This slice adds the smallest engine-neutral observation frame needed to exercise visit selection, censoring, measurement availability/error, and recorded recognition descendants in development and counterfactual experiments.

The frame is evaluator-only. It consumes one completely fictional `AgeRegimeDisorderTrajectory` and an explicit immutable policy, and returns observable measurement/event records plus a private truth object. It does not write CSVs, alter `datapackage.json`, activate the fail-closed smoke CLI, consume calibration/held-out/privacy artifacts, or read any real-data path. It is not prevalence, demographic, clinical, temporal-drift, task-utility, privacy, non-matchability, or release evidence.

The frame is deliberately not the complete eight-resource EHR package. Labs, medications, problem-list rows, referrals, exact PPOC derivation, and package-level counterfactual worlds remain later gates that require their own causal/resource contracts and the authoritative augmentation implementation or parity harness.

## Inputs and deterministic streams

`generate_observation_frame(trajectory, policy, streams)` accepts only:

- an `AgeRegimeDisorderTrajectory` with one patient and strictly increasing latent points;
- an `ObservationPolicy` defined below; and
- the existing `NamedRandomStreams` for one fictional patient.

The patient ID must be a synthetic opaque ID beginning with `syn-`. No API accepts a path, descriptor, row reader, calibration artifact, held-out report, privacy report, or arbitrary column list.

The generator obtains independent named streams only from `NamedRandomStreams`:

- `observation.window` and `observation.censoring` for the effective observation window;
- `observation.visit.routine` for stable routine visit-opportunity realization;
- `observation.measurement-availability` for per-channel missingness;
- `observation.measurement-error` for additive/rounding error draws; and
- `observation.recognition` and `observation.recorded-event` for recognition/recording decisions.

Stream names are fixed tokens. Replaying the same trajectory, policy, seed, and patient index yields byte-equivalent visible observations and the same hidden truth hashes. A later counterfactual observation contract may reuse these names across worlds; this slice does not resample latent physiology.

## Strict policy models

`ObservationPolicy` is frozen and rejects unknown or malformed values. It contains:

- a nonempty `policy_version` token;
- nonnegative integer `window_start_age_days` and positive `window_end_age_days`, with start strictly before end;
- optional nonnegative `censor_age_days`, which truncates the effective window and may not precede the start;
- `visit_probability` in `[0, 1]`;
- independent measurement-availability probabilities for length, standing height, weight, and head circumference, each in `[0, 1]`;
- nonnegative finite additive-error standard deviations for each applicable measurement, with zero meaning no additive noise;
- an optional nonnegative integer `rounding_digits` bounded by six, applied after error; and
- `recognition_probability` and `diagnosis_probability` in `[0, 1]`, plus a nonnegative integer `recognition_delay_days`.

The policy may also declare a closed censoring mode (`NONE`, `ADMINISTRATIVE_END`, or `LOST_TO_FOLLOW_UP`). `ADMINISTRATIVE_END` ends at the administrative window bound; `LOST_TO_FOLLOW_UP` requires an explicit censor age strictly before that bound. The policy does not contain a prevalence target, diagnosis label, real-data path, seed, patient row, or hidden truth. A policy with no effective observation window, an impossible censoring bound, a nonfinite value, a boolean masquerading as an integer/number, or an unknown field fails closed.

The implementation may expose the policy as one frozen model or as frozen nested `ObservationWindowConfig`, `VisitOpportunityConfig`, `MeasurementModelConfig`, and `RecognitionConfig` models. If nested, unknown keys and mutable values are rejected at every level.

## Observable frame

The evaluator-only frame has the following conceptual components (names may be preserved as public dataclasses):

- `ObservationWindow`: entry age, effective exit age, administrative end age, and a closed censoring reason;
- `VisitOpportunity`: stable source-point index, age, closed encounter/trigger token, and realized/not-realized state (the realized flag is private truth; a visible visit is emitted only when true);
- `MeasurementObservation`: a closed channel (`LENGTH`, `HEIGHT`, `WEIGHT`, `HEAD_CIRCUMFERENCE`, or derived `BMI`), availability (`NOT_APPLICABLE`, `MISSING`, or `OBSERVED`), and recorded value; and
- `RecordedEvent`: a realized opportunity link or explicit null, age, closed event kind, and a code from a fixed fictional terminology registry.

The visible `ObservationFrame` contains:

- realized visit records with a stable synthetic visit ID, patient ID, latent-point age, and observable measurements (`length_cm`, `height_cm`, `weight_kg`, `bmi`, and optional `head_circumference_cm`), where unavailable or structurally inapplicable values are represented by the channel status rather than a latent substitute;
- recorded recognition/workup/diagnosis descendants that survive the policy, each with a synthetic patient ID, age, fixed event kind, and a registered fictional code; and
- policy/version metadata and aggregate counts only.

Before the length/standing-height transition, the applicable stature channel is `LENGTH`; after it, it is `HEIGHT`. Head circumference becomes `NOT_APPLICABLE` outside the supported age domain. `MISSING` means an eligible measurement was not recorded. Observed BMI is recomputed from the observed standing height and weight when both are present; it is `None` otherwise and is never independently sampled. Measurements are never silently replaced with latent values. A nonpositive or nonfinite post-error measurement is a hard generation error, not a clipped clinical value.

Visit IDs are deterministic opaque tokens derived from the synthetic patient ID, policy version, and stable opportunity index. They are not real identifiers and are not intended to establish a package-level key contract. Routine opportunity indices do not change when another domain's realization count changes.

Only source events marked observable by the native event trace may become records. `latent_onset` and any `hidden=True` event remain private. A recorded descendant requires a realized opportunity and observable evidence; it cannot precede its source event, a selected visit, or the configured recognition delay. Workup and diagnosis events must follow recognition in the existing causal phase order. A healthy diagnosis is rejected unless the policy explicitly enables a fictional false-positive pathway. Treatment-response events remain hidden/deferred until a treatment/adherence observation contract is approved.

## Private truth and leakage boundary

`ObservationTruth` retains the effective window, all stable opportunity decisions, per-channel applicability/availability decisions, latent values and numeric error deltas, source-to-recorded-event decisions, and the source event trace needed by an evaluator to test observation fidelity and future measurement-error-removal counterfactuals. It may include canonical hashes of the latent trajectory and truth payload. Carry-forward, unit swaps, decimal shifts, digit transposition, impossible values, and height/weight swaps are explicitly out of scope for this first slice.

Truth is never returned by `ObservationFrame.to_mapping()`, `repr(frame)`, visible observations, ordinary manifests, or aggregate validation reports. The public mapping contains only fixed metadata, visible records, and counts. Any future external truth-manifest writer remains the sole explicit evaluator artifact boundary.

## Validation contract

`validate_observation_frame(frame)` returns an aggregate-only immutable report with `PASS`, `FAIL`, or `UNEVALUABLE` status and fixed reason codes. It checks:

1. one synthetic patient and strict source/observed age ordering;
2. effective-window and censoring compliance;
3. each observation references a selected latent point exactly once;
4. finite positive measurements and BMI identity when both inputs exist;
5. no hidden latent event appears in visible records;
6. event ordering, source-age/visit/delay constraints, and permitted event types; and
7. required evidence, including at least one selected visit and one evaluable measurement when the policy requests them.

Malformed or missing hidden evidence is `UNEVALUABLE`, never a pass. A true invariant or forbidden-visible-change violation is `FAIL`. Reports contain only counts, check IDs, statuses, and fixed reason codes; they never contain patient IDs, ages tied to a patient, measurement values, error deltas, event payloads, stream identities, paths, or hashes.

## Supported and deferred behavior

This slice supports deterministic routine visit selection, explicit window censoring, independent measurement availability, additive/rounding measurement error, and recognition/recorded-event projection from the existing latent trace. It intentionally does not implement utilization-intensity counterfactuals, measurement-error removal, diagnosis sensitivity calibration, disorder prevalence allocation, event-driven opportunity generation, carry-forward/gross measurement errors, labs, medications, problem-list rows, referrals, ancillary-resource generation, exact-schema export, clinical reference tables, or Synthea integration. Those features may consume this frame only after their own reviewed matrices, policies, and package/resource contracts exist.

## Acceptance criteria

The slice is complete when:

1. strict policy/frame/truth/report models reject malformed and unknown inputs;
2. repeated generation with the same named streams is deterministic and independent streams are used for visits, availability, error, and recognition;
3. visible observations preserve positivity, BMI identity, effective-window/censoring bounds, and causal event ordering;
4. hidden latent state, error decisions, and source traces cannot enter ordinary mappings, repr, reports, or visible package files;
5. missing or underpowered evidence is `UNEVALUABLE`, while real invariant violations are `FAIL`;
6. utilization and measurement-error-removal interventions remain rejected until a later counterfactual slice; and
7. focused tests, full pytest, Ruff, schema validation, diff checks, and a broad review pass before merge.
