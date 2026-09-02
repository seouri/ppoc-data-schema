# Native Calibrated Cohort Profile

**Date:** 2026-08-31
**Status:** Implementation complete; evaluator/development-only; prevalence, clinical, privacy, and release gates pending
**Parent:** [Synthetic Pediatric Growth Fixture System Design](2026-08-30-synthetic-growth-fixtures-design.md)
**Prerequisites:** [Age-regime disorder integration](2026-08-30-age-regime-disorder-integration-design.md), [governed calibration core](2026-08-31-governed-calibration-core-design.md), [evaluator observation frame](2026-08-31-observation-frame-design.md), and [observed resource contract](2026-08-31-observed-resource-contract-design.md)

## Purpose

The repository now has deterministic healthy and growth-disorder trajectory kernels, an evaluator-only observation frame, descriptor-shaped observed resource bundles, an exact-schema package bridge, and a governed aggregate calibration artifact. It does not yet have the native cohort layer that composes those pieces into a reproducible healthy-plus-disorder development population. This slice adds that missing in-memory orchestration boundary.

The cohort profile samples fictional demographics from explicitly released aggregate calibration cells, chooses latent modules from an explicit clinical prior, generates age-regime trajectories, projects them through the observation process, and optionally produces validated observed-resource bundles. It keeps latent module truth and trajectory state in evaluator-only objects and exposes only visible frame/bundle mappings through ordinary serialization.

This slice does not turn recorded diagnosis prevalence into latent disease prevalence, assign labels to force a final observed rate, fit parameters from patient rows, or claim that the resulting population is representative. The calibration artifact supplies aggregate demographic and recorded-outcome targets; explicit module priors and observation policies remain versioned caller inputs. Held-out fidelity evaluation is the later gate that determines whether those choices reproduce approved targets.

## Goals

1. Add one strict, deterministic native cohort API that can generate healthy and one or more reviewed growth-disorder modules from injected public references and policies.
2. Consume only an already-loaded `CalibrationArtifact`; never accept a real-data path, partition key, patient row, sequence, held-out report, privacy report, or hidden evaluator truth as a cohort input.
3. Require complete released demographic target cells for the selected profile. A suppressed or missing target fails closed; it is never silently dropped, normalized to zero, or replaced by a hidden real-data fallback.
4. Sample recorded sex, ethnicity, primary race, and the approved race-multiselect indicator from aggregate weights, preserving an explicit mapping for blank/nonresponse cells into the visible fictional category vocabulary.
5. Keep latent module selection independent from recorded diagnosis targets. The caller supplies an explicit module prior; `growth_dx_flag` and `healthy_flag` are retained as aggregate calibration evidence and are not used as a final-label allocator.
6. Reuse the existing age-regime/disorder kernel, observation-frame generator, resource projection, and resource validator rather than duplicating trajectory or visibility logic.
7. Guarantee deterministic patient identifiers, demographic draws, module choices, trajectories, observations, and bundle ordering for equal profile, seed, reference, policy, calibration artifact, and module configuration.
8. Fail closed on malformed calibration artifacts, incompatible schema/registry metadata, invalid module priors, unsupported reference-sex mappings, invalid observation results, duplicate identifiers, and any hidden-truth or filesystem boundary attempt.

## Non-goals and deferred gates

- No CSV, package, manifest, descriptor-path, real-data, key-file, DuckDB, or CLI input is accepted by the cohort API.
- No production growth reference or authoritative augmentation oracle is bundled; `synthetic.generate` remains fail closed and exact-schema package promotion remains an explicit caller step.
- No disorder module is enabled by an artifact target alone. A module requires a caller-supplied reviewed implementation and an explicit positive prior.
- No prevalence-forcing allocator, iterative fitting loop, or optimizer is included. Recorded diagnosis/flag targets are checked later by governed held-out validation.
- No new clinical terminology, disorder-critical laboratories, medications, problem-list rows, referrals, utilization-intensity counterfactual, task-utility evaluation, clinical review, privacy/non-matchability evidence, or Synthea adapter is added.
- No claim of demographic representativeness, latent disease prevalence, clinical validity, privacy, release readiness, or real-patient non-matchability is made by this API.

## Public interfaces

Add `synthetic.cohort` with the following immutable models and functions:

```python
@dataclass(frozen=True)
class CohortModuleWeight:
    kind: DisorderKind
    probability: float

@dataclass(frozen=True)
class CohortConfig:
    profile: str
    patient_count: int
    seed: int
    ages_days: tuple[int, ...]
    observation_policy: ObservationPolicy
    module_weights: tuple[CohortModuleWeight, ...]
    reference_sex_mapping: tuple[tuple[str, str], ...]
    age_regime_config: AgeRegimeConfig = field(default_factory=AgeRegimeConfig)

@dataclass(frozen=True)
class CalibrationSamplingProfile:
    artifact_id: str
    target_registry_version: str
    sex_weights: tuple[tuple[str, float], ...]
    ethnicity_weights: tuple[tuple[str, float], ...]
    race_weights: tuple[tuple[str, float], ...]
    race_multiselect_probability: float
    recorded_healthy_probability: float
    recorded_growth_dx_probability: float

    @classmethod
    def from_artifact(cls, artifact: CalibrationArtifact) -> CalibrationSamplingProfile: ...

@dataclass(frozen=True, repr=False)
class CohortMember:
    demographics: SyntheticDemographics
    trajectory: AgeRegimeDisorderTrajectory
    frame: ObservationFrame
    bundle: ObservedResourceBundle | None

@dataclass(frozen=True, repr=False)
class NativeCohort:
    profile: str
    seed: int
    members: tuple[CohortMember, ...]
    calibration: CalibrationSamplingProfile

def generate_native_cohort(
    config: CohortConfig,
    reference: GrowthReference,
    calibration: CalibrationSamplingProfile,
    *,
    modules: Mapping[DisorderKind, GrowthDisorderModule],
    descriptor: Mapping[str, object] | None = None,
) -> NativeCohort: ...
```

`CohortConfig` validates an aggregate-safe profile token, a positive bounded patient count, a nonnegative integer seed, strictly increasing unique ages, an explicit observation policy, at least one healthy and one positive nonhealthy module prior, probabilities in `[0,1]` with positive total, a complete one-to-one `F/M/U` reference-sex mapping, and an immutable age-regime configuration. Module probabilities are normalized only after validation and their normalized values are not written to visible records.

`CalibrationSamplingProfile.from_artifact` accepts only `CalibrationArtifact` values whose source partition is `calibration`, schema fingerprint is the checked-in contract, and every target belongs to `TARGET_REGISTRY_VERSION`. It reads the single `outcome_layer=observed` stratum and requires released, denominator-backed proportion targets for every registered sex, ethnicity, and primary-race category, `race_multiselect`, `healthy_flag`, and `growth_dx_flag`. Any missing, duplicate, suppressed, non-proportion, wrong-denominator, or out-of-range cell fails closed. Rounded weights must sum within a fixed one-percent envelope of one; sampling uses their normalized sum while preserving the artifact identity and values in the evaluator profile. Blank ethnicity/race cells remain distinct in the aggregate profile and are mapped to the visible `Unknown` category only at projection time through a fixed documented rule.

The calibration profile contains aggregate values only. Its mapping and representation omit source paths, partition keys, patient/visit identifiers, target supports/denominators, hidden labels, and attack output. `recorded_healthy_probability` and `recorded_growth_dx_probability` are evidence for later validation and are not read by module selection.

`generate_native_cohort` validates the injected reference, module mapping, descriptor shape when supplied, and calibration/profile compatibility before sampling. It creates `syn-` patient identifiers with the existing versioned identifier function. For each index, a `cohort.demographics` stream samples sex, ethnicity, race slot one, and the explicit race-multiselect Bernoulli; a separate `cohort.module` stream samples the latent module. The selected module receives the same patient and named streams used by `AgeRegimeDisorderKernel`, so latent states are sampled once and remain available for evaluator replay. The function then calls `generate_observation_frame` with the configured policy and validates `PASS`; a non-PASS frame is a generation error rather than a silently empty patient. When a descriptor mapping is supplied, it calls `project_observed_resources` with the sampled demographics and requires a resource-validation `PASS`. Every member has one patient, globally unique synthetic identifiers, and no shared mutable state.

`CohortMember.to_mapping()` returns only visible demographics, the visible observation-frame mapping, and (when present) the visible observed-resource mapping. It never includes the latent trajectory, disorder state, source events, private measurement truth, truth hashes, random streams, or calibration supports. `NativeCohort.to_mapping()` returns only profile, seed, member count, bundle count, visible visit count, and visible event count. Both classes use evaluator-only representations that do not print hidden values in `repr`.

## Demographic and prevalence semantics

The profile samples demographics from aggregate weights rather than copying or resampling patient records. A blank ethnicity/race cell is an observed nonresponse category in the calibration artifact; the visible resource vocabulary has no blank category, so the fixed projection maps it to `Unknown` and records that lossy mapping in the profile contract. Race slot one is sampled from the released primary-race distribution. When the race-multiselect draw succeeds, slot two is sampled from the same approved distribution; slots three through eight remain `Unknown` because no higher-order aggregate target is released by the current registry. This is an explicit approximation, not evidence that the source's full multiselect structure was reproduced.

The latent prior is the only source of module prevalence in this slice. It may be based on a separately approved clinical configuration, but the API does not infer it from `growth_dx_flag`, `healthy_flag`, or any other recorded outcome. A healthy module can have no recorded diagnosis event; a disorder module can remain unrecognized under the observation policy. The resulting observed diagnosis and flag rates are measured by later held-out validation rather than forced by a final allocation pass.

## Hidden truth and serialization boundary

The cohort holds trajectories and observation truth only to support evaluator validation and counterfactual experiments. No ordinary mapping, aggregate summary, exception, log, or package export includes those objects. Callers that need evaluator truth must retain the returned in-memory `CohortMember.trajectory` and `ObservationFrame.truth` in evaluator-controlled storage and must use the existing external truth-manifest contract; this slice does not add a new truth writer.

The descriptor is an already-loaded mapping and is used only to extract the existing six-resource shape. The cohort module never reads a descriptor path or CSV, imports governed calibration-input/held-out/privacy modules, calls a package writer, or accepts a real-data argument. A future CLI may construct this API only after an approved public reference, module configuration, terminology/resource descendants, authoritative derivation oracle, and full validation gates exist.

## Validation and failure behavior

All input/configuration validation occurs before the first patient draw. Generation errors from a reference, module, observation, projection, or resource validator are wrapped in `CohortGenerationUnavailable("native cohort generation failed")`; the public exception never includes a patient ID, visit ID, path, truth hash, or raw module error. Configuration and calibration-contract errors use field/target names only and remain actionable.

The generated member sequence is sorted by construction index and remains deterministic. If a descriptor is supplied, bundles are returned in that same stable patient order and can be passed directly to the reviewed `export_observed_resource_package` bridge. This slice does not call the bridge, so no output directory or lifecycle artifact is created.

## Testing strategy

Tests use only the checked-in fictional references, module implementations, descriptor mapping, and a hand-built aggregate `CalibrationArtifact`; no real snapshot or calibration path is opened. Required tests cover strict model/config validation, complete released target extraction, target-registry and schema checks, suppressed/missing target rejection, rounded-weight normalization, blank/nonresponse mapping, deterministic demographics/module choices/trajectories, healthy-plus-disorder coverage, reference-sex mapping, frame/resource validation, descriptor shape mismatch, non-PASS frame failure, duplicate identifiers, no hidden truth in mappings/reprs, and fail-closed exception redaction.

Boundary tests extend the visible-generation scan to include `synthetic.cohort`: it may import the in-memory `synthetic.calibration` model, native kernels, and resource/observation contracts, but it may not import calibration input, the calibrator, held-out validation, privacy auditing, real-data helpers, Synthea, package writers, path readers, or output lifecycle code. Tests also assert that `generate.py` remains fail closed and that no cohort function accepts a governed path, key, or report argument.

## Acceptance criteria

1. A strict aggregate calibration profile can be loaded from a `CalibrationArtifact` only when all required released demographic/recorded-outcome targets and the exact schema/registry contract are present; suppression and drift fail closed.
2. Equal explicit inputs produce byte-equivalent visible mappings and equal latent/observation hashes for a cohort containing both healthy and growth-disorder members; reordered caller module mappings do not alter output.
3. Every generated member has a deterministic fictional patient ID, sampled aggregate demographics, one age-regime/disorder trajectory, a passing observation frame, and, when requested, a passing descriptor-shaped observed-resource bundle.
4. No ordinary mapping, repr, exception, or source file boundary exposes latent disorder truth, private measurement truth, source paths, calibration supports/denominators, keys, or patient/visit values outside the visible fictional records.
5. The production CLI, exact-schema lifecycle, authoritative augmentation, held-out validation, privacy audit, clinical approval, and Synthea route remain unchanged and explicitly deferred.
6. Focused tests, full tests, Ruff, schema validation, whitespace checks, and a fresh broad review pass before merge; `main` equals `origin/main` after push.
