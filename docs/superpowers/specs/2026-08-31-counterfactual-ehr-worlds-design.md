# In-Memory Paired Counterfactual EHR-World Contract

**Date:** 2026-08-31  
**Status:** Approved next roadmap slice under the native counterfactual, observation, resource, and GHD ancillary designs  
**Parent:** [Synthetic Pediatric Growth Fixture System Design](2026-08-30-synthetic-growth-fixtures-design.md)  
**Prerequisites:** [Counterfactual validity](2026-08-31-counterfactual-validity-design.md), [Observation frame](2026-08-31-observation-frame-design.md), [Observed-resource contract](2026-08-31-observed-resource-contract-design.md), [GHD ancillary pathway](2026-08-31-ghd-ancillary-pathway-design.md), and [GHD ancillary bundle integration](2026-08-31-ancillary-bundle-integration-design.md)

## Purpose and boundary

The native implementation now has the reviewed ingredients for one coherent fictional counterfactual patient: a validated paired latent trajectory, deterministic observation frames, exact descriptor-shaped base rows, and an evaluator-only GHD ancillary projection that can be merged into a six-resource bundle. This slice composes those ingredients into baseline and intervention EHR-world members and validates the causal change contract at the visible resource level.

The result is an in-memory evaluator object for development and counterfactual experiments. It is not a package exporter, a prevalence or demographic calibrator, a clinical simulator, a privacy or non-matchability proof, or a release artifact. It never reads a file, accepts governed or real data, writes a path, changes the smoke CLI, or claims that recorded diagnosis is latent disorder prevalence. Pair-aware exact-schema package export is a later gate. A Synthea adapter remains optional and later; it must conform to this contract rather than replacing it.

## Design choice and alternatives

The recommended route is a small engine-neutral module, `synthetic.native.counterfactual_worlds`, that consumes an already validated `CounterfactualPair` and already loaded typed inputs. It reuses the existing `NamedRandomStreams` seed/index for both worlds, so the observation process is replayed rather than independently resampled. It creates provisional `CohortMember` values, projects base resources, projects GHD ancillary resources, and merges them through the reviewed `merge_ghd_ancillary_resources` seam. The returned pair is frozen and retains hidden evaluator bindings only for revalidation.

Changing `CounterfactualPair` to carry resource rows is rejected because it would couple the trajectory contract to descriptor shape and make hidden truth easier to expose. Changing `ObservedResourceBundle` or its generic validator to understand counterfactual permissions is rejected because the base contract intentionally remains an empty-ancillary view. Writing two packages in this slice is rejected because package-level ordering, manifests, augmented derivation, and disclosure boundaries need a separate pair-aware export design. Building this as a Synthea module is an optional later adapter, not a substitute for native physiology, observation replay, exact-schema projection, or the aggregate validator here.

## Goals

1. Compose one already validated synthetic `CounterfactualPair` into two immutable, descriptor-shaped `CohortMember` values with the same patient, demographics, observation policy, shape, and deterministic observation streams.
2. Reuse existing observation generation, base-resource projection, GHD ancillary projection, and bundle integration without duplicating their schemas or silently repairing invalid inputs.
3. Validate visible resource-level invariants and permitted changes for all three currently supported interventions: `PHYSIOLOGY_SEVERITY`, `EARLIER_RECOGNITION`, and `TREATMENT_ADHERENCE`.
4. Keep hidden trajectories, observation truth, contexts, seeds, stream identities, and policy internals evaluator-only; ordinary mappings, reprs, reports, and exceptions must be aggregate-only or fixed redacted text.
5. Fail closed on unsupported/deferred interventions, malformed typed inputs, non-base-compatible descriptors, observed `LENGTH` measurements, identity/shape/frame mismatches, broken resource links, and any visible causal violation.
6. Provide deterministic, random-free assembly (the only draws occur inside the existing observation generator) and repeatable aggregate validation suitable for development fixtures and future counterfactual experiments.

## Non-goals and deferred gates

- No filesystem, CSV, package, manifest, output destination, descriptor path, real-data root, governed snapshot, calibration artifact, held-out report, privacy report, key, model, callable, DuckDB, or Synthea input.
- No pair-aware package export, augmented derivation, prevalence allocation, demographic calibration, clinical terminology expansion, disorder-specific pathway beyond reviewed GHD, temporal drift, task-utility experiment, clinical review, privacy/non-matchability evaluation, or release approval.
- No support for `UTILIZATION_INTENSITY` or `MEASUREMENT_ERROR_REMOVAL`; these remain rejected until their resource descendants and causal matrices are separately reviewed.
- No independent intervention-specific observation resampling. Differences must originate from the paired trajectory and the existing fixed observation/ancillary contracts.
- No claim that matching aggregate or visible resource rows proves that a generated profile cannot be linked to a real patient. Privacy and non-matchability evidence require the separately governed privacy gate.

## Public API

Create `src/synthetic/native/counterfactual_worlds.py` with the following immutable public values and functions. Names are part of this contract and must not be broadened with convenience aliases that accept untyped inputs.

```python
class CounterfactualWorldValidationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNEVALUABLE = "UNEVALUABLE"

@dataclass(frozen=True, repr=False)
class CounterfactualWorldCheck:
    name: str
    status: CounterfactualWorldValidationStatus
    reason_code: str

@dataclass(frozen=True, repr=False)
class CounterfactualWorldValidationReport:
    status: CounterfactualWorldValidationStatus
    checks: tuple[CounterfactualWorldCheck, ...]

@dataclass(frozen=True, repr=False)
class CounterfactualEhrWorldPair:
    baseline: CohortMember
    intervention: CohortMember
    matrix: CounterfactualChangeMatrix
    observation_policy: ObservationPolicy
    shape: ResourceShape

def assemble_counterfactual_ehr_worlds(
    pair: CounterfactualPair,
    demographics: SyntheticDemographics,
    observation_policy: ObservationPolicy,
    descriptor: Mapping[str, object],
    ancillary_policy: GhdAncillaryPolicy,
) -> CounterfactualEhrWorldPair:
    ...

def validate_counterfactual_ehr_worlds(
    worlds: CounterfactualEhrWorldPair,
) -> CounterfactualWorldValidationReport:
    ...
```

The exact public names may be adjusted during implementation only if the spec, plan, tests, and documentation are changed together before code is written. The pair/report mapping and repr are visible contract surfaces; all trajectory, frame truth, context, seed, patient-index, shape internals, and private source objects are excluded.

`CounterfactualEhrWorldPair` exposes only baseline/intervention member mappings plus fixed contract, matrix version, intervention, policy mapping, and descriptor shape metadata that is already safe under the existing resource contract. It does not expose the latent pair, source truth, stream identities, or row objects as private objects through a mapping. The public validator accepts only this typed pair and returns fixed checks in canonical order.

## Module dependency boundary

The new module is one-way and in-memory. It may import standard-library dataclass/enum/mapping helpers and the existing `CohortMember`, counterfactual value/validation types, observation policy/frame/generator/stream identities, resource shape/demographics/projection/validation types, ancillary policy/projection/validation types, and ancillary-bundle merge/full-bundle validation functions. It must not import filesystem, path, CSV, package-export, manifest, calibration, held-out, privacy, governed-data, DuckDB, model-training, Synthea, CLI, or network modules. Static tests must reject those imports, calls, and public argument names such as `path`, `output`, `root`, `key`, `real_data`, `calibration`, `heldout`, `privacy`, `model`, `callable`, and `manifest`.

The module must not import the counterfactual truth-manifest writer or depend on its filesystem helpers. Descriptor input is an already loaded `Mapping[str, object]`; `ResourceShape.from_descriptor` extracts shape in memory. No descriptor mapping is mutated or retained as a caller-owned mutable object.

## Assembly semantics

1. Require typed `CounterfactualPair`, `SyntheticDemographics`, `ObservationPolicy`, descriptor mapping, and `GhdAncillaryPolicy`. Reject any deferred or unknown intervention with one fixed `CounterfactualWorldUnavailable("counterfactual EHR worlds unavailable")` message that contains no identifier, value, or private exception text.
2. Re-run `validate_counterfactual_pair(pair)` and require `PASS`. A prior report is not trusted. Verify that demographics identify the paired synthetic patient and derive one `ResourceShape` from the already loaded descriptor.
3. Create `NamedRandomStreams(run_seed, patient_index)` from the hidden baseline context and pass the same stream object configuration to `generate_observation_frame` for baseline and intervention trajectories. Use the same policy instance and no world-specific seed, index, or policy. Observation stream identities are compared by the hidden contexts and fixed `observation_stream_identity` values; the assembler itself performs no random draws.
4. Require both generated frames to pass `validate_observation_frame`. A descriptor that cannot represent an observed `LENGTH` measurement must fail closed through the existing `ResourceProjectionUnavailable` boundary; integration fixtures therefore use a base-compatible policy or trajectory.
5. Construct provisional members with the shared demographics, each hidden trajectory, each frame, and `bundle=None`. Project each base frame with `project_observed_resources(frame, descriptor, demographics)`, project each provisional member with `project_ghd_ancillary_resources(member, shape, ancillary_policy)`, and merge with `merge_ghd_ancillary_resources`. Construct final members with the fresh merged bundle. The assembler never silently drops, fills, or overwrites visible rows.
6. Require each integrated bundle to pass `validate_ghd_ancillary_bundle` using its corresponding final member and policy. Require both bundles to share exact shape, patient row, visit identity semantics, and source-frame object binding. Any failure crosses the fixed redacted unavailability exception.
7. Return a fresh frozen `CounterfactualEhrWorldPair` bound to the original hidden pair and contexts for later validation. Assembly is deterministic for the same typed inputs and does not mutate the pair, demographics, policy, descriptor, trajectories, frames, or projections.

The assembler retains hidden `CounterfactualPair`, run seed/index, stream identities, and source objects only in non-visible fields needed to re-run validation. These fields must be `repr=False`, excluded from mappings, and inaccessible through report serialization. The constructor rejects a manually fabricated pair whose members, matrix, policy, shape, demographics, or hidden pair binding do not agree.

## Visible resource change matrix

The validator uses the existing trajectory matrix as the authoritative causal permission and adds the following resource-level checks. It compares canonical visible `ResourceRow.to_mapping()` values and `ClinicalDescendant.to_mapping()` values, never private object identity or truth payload.

### Shared invariants for every supported intervention

- Same synthetic patient and exact `SyntheticDemographics` mapping.
- Same observation policy version/window/censoring metadata and the same hidden run seed, patient index, and observation stream identities.
- Same patient row, visit IDs, visit ages, encounter types, Epic-origin fields, and visit ordering.
- Same measurement channel applicability/availability and visible visit structure. Measurement values may change only where the intervention-specific rules below allow it.
- Same descriptor-derived six-resource shape and exact field order. Every visible row has the correct resource name, field order, patient identity, and resolved visit link.
- No rows outside the existing six-resource bundle; no private truth, latent labels, hidden event payloads, or evaluator object reprs in visible mappings.

### `PHYSIOLOGY_SEVERITY`

Only recorded growth measurement values (`height`, `weight`, `head_circumference`, and derived `bmi` fields where the existing projector records them) may differ, and only as a consequence of the paired physiology trajectory. Measurement availability, values marked missing/not-applicable, visit rows, visible event trace, clinical descendants, and all four ancillary resource collections must be equal. The underlying trajectory validator remains responsible for growth-direction and pre-onset assertions; the world validator fails if any unrelated resource changes.

### `EARLIER_RECOGNITION`

Growth measurement values, availability, visits, patient rows, and physiological resource rows must be equal. The visible recorded event trace may change only through the existing recognition/workup/diagnosis projection. Event-derived clinical descendants and GHD ancillary rows may change when the existing pathway permits them, with the same patient and resolved visit links. No visit or measurement opportunity may be added or removed by recognition alone.

### `TREATMENT_ADHERENCE`

Patient rows, visits, measurement availability, event trace, clinical descendants, and ancillary resources must remain equal. Growth measurement values may differ only at ages on or after the first hidden `treatment_start` event; values before treatment, missingness, and not-applicable channels must remain equal. If no treatment start exists, all visible measurements remain invariant. The treatment start and response evidence are private and never appear in the report.

The validator does not invent permissive differences for future resource columns. A difference outside the fixed matrix is `FAIL`, even when it might be clinically plausible.

## Aggregate validator contract

`validate_counterfactual_ehr_worlds` returns exactly these checks in order:

1. `pair_binding` — typed world pair, hidden pair, matrix, patient, and world labels agree;
2. `shared_demographics` — demographics and patient rows are equal and descriptor-valid;
3. `shared_observation` — policy/window/stream metadata and frame identity agree;
4. `observation_invariants` — visits, opportunities represented by visible observations, channel availability, and event-window rules satisfy the shared contract;
5. `resource_invariants` — exact six-resource shape, row keys/order, links, descendants, and shared fields validate;
6. `permitted_changes` — only the intervention's fixed visible changes occur, including treatment-age gating; and
7. `truth_boundary` — mappings/reprs/reports contain no hidden evidence or nested private objects.

Statuses are fixed `PASS`, `FAIL`, and `UNEVALUABLE`, with precedence `FAIL > UNEVALUABLE > PASS`. Fixed reason codes are limited to `OK`, one reason per named visible failure, and `MALFORMED_WORLDS`/`INSUFFICIENT_EVIDENCE`. A visible typed row, identity, shape, link, window, measurement, event, or causal violation is `FAIL`. Missing or malformed private evidence is `UNEVALUABLE` only when no independently visible violation is demonstrable; if both are present, `FAIL` wins. Reports contain only check names, statuses, reason codes, and status counts, never patient IDs, visit IDs, row values, ages, codes, trajectory states, hashes, stream names/identities, seeds, or source objects.

The validator re-runs `validate_counterfactual_pair`, both `validate_observation_frame` calls, both integrated GHD bundle validators, and the isolated-base resource checks. It must not trust a report stored on the object or a caller-computed comparison. A malformed private frame truth can yield `UNEVALUABLE` for evidence-dependent checks, but malformed visible rows remain independently `FAIL`.

## Truth and representation boundary

`CounterfactualEhrWorldPair.to_mapping()` contains a fixed contract token, matrix version, intervention token, policy mapping, shape metadata, and visible baseline/intervention member mappings. `CohortMember.to_mapping()` and `ObservedResourceBundle.to_mapping()` retain their existing safe contracts. The pair's `repr` is a fixed evaluator-only label and the report/check reprs are aggregate-only. The implementation must recursively inspect mappings, tuples, dataclasses, and reprs in boundary tests to ensure that a private `ObservationTruth`, trajectory, context, stream generator, policy wrapper, descriptor mapping, or source object cannot leak through an accidental nested field.

Exception messages are fixed literals. The assembler and validator must not echo patient IDs, intervention values supplied by an attacker, descriptor keys, row values, exception text, file paths, or hidden truth terms. No logging or debug hook is added.

## Testing strategy

Tests use only deterministic synthetic fixtures already present in the repository or newly created fictional values. A base-compatible descriptor/policy has `length_availability_probability=0.0` (or otherwise no observed length) because the current six-resource base projection intentionally rejects observed `LENGTH`. Focused tests must cover:

- valid assembly and deterministic replay for all three supported interventions;
- GHD, healthy, non-GHD, and unrecognized frames, including empty ancillary projections where appropriate;
- exact six-resource shape and field order, shared demographics, visit identity, source-frame binding, and fresh immutable members/bundles;
- rejection of deferred/unknown interventions, prior trajectory/report failures, observed-length projection, malformed descriptor/policy/demographics, and all identity/shape/frame mismatches;
- validator detection of tampered visit ages/IDs, measurement availability/values, event traces, clinical descendants, ancillary rows/links, field order, policy metadata, and treatment-before-start differences;
- permitted physiology, recognition, and treatment differences, including no-treatment-start and empty/partial visible-event cases;
- `FAIL` versus `UNEVALUABLE` precedence for malformed private truth and independently visible violations;
- aggregate-only mapping/repr/report/exception redaction, nested hidden-object injection, immutability/no mutation, and deterministic status counts;
- AST/import boundary tests rejecting filesystem, package/export, governed, real-data, privacy, model, callable, manifest, and Synthea dependencies and forbidden public argument names; and
- documentation assertions for the exact API, in-memory-only boundary, visible change matrix, deferred package export, and optional later Synthea adapter.

The full repository suite, Ruff, schema validation, lock check, and whitespace checks remain required. No test loads a real snapshot or a gated data root.

## Documentation and roadmap

`docs/synthetic-generator.md` gains an “In-memory paired counterfactual EHR worlds” section with a short usage example, base-compatible descriptor caveat, validation report semantics, visible change matrix, hidden-truth boundary, and failure behavior. `README.md` gains one roadmap paragraph after the ancillary-bundle section. Both documents state that this is a synthetic-only evaluator seam, not prevalence/demographic evidence, privacy/non-matchability evidence, clinical validity, task utility, package/release evidence, or Synthea conformance. They identify pair-aware exact-schema export as the next package gate and Synthea as an optional later adapter.

## Acceptance criteria

1. A previously passing fictional trajectory pair assembles into two immutable six-resource EHR-world members with one shared patient/demographic/observation identity and deterministic replay.
2. All three supported intervention matrices pass their allowed visible resource comparisons; unsupported/deferred kinds are rejected with a fixed redacted exception.
3. The aggregate validator catches identity, shape, visit, measurement, event, ancillary, treatment-age, and truth-boundary violations and preserves `FAIL > UNEVALUABLE > PASS`.
4. Ordinary mappings, reprs, reports, exceptions, and documentation contain no latent trajectory, observation truth, seeds, stream identities, private source objects, or row-level evaluator evidence.
5. No filesystem, real/governed-data, package/export, privacy, model, callable, or Synthea dependency is added, and existing generic/base validators remain unchanged.
6. Focused and full verification pass, the implementation receives scoped and broad fresh review, and the reviewed feature is merged to `main` and pushed with `HEAD == origin/main`.
