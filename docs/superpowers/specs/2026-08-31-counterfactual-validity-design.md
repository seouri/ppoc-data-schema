# Counterfactual Fixture Validity Contract

**Date:** 2026-08-31
**Status:** Approved roadmap slice under the parent synthetic growth-fixture design

## Purpose

Add an evaluator-only native contract for paired synthetic growth trajectories. The contract makes the causal change matrix executable, preserves shared synthetic patient state and named random-stream invariants, and checks hidden event traces and trajectory-layer hashes without exposing evaluator truth through visible fixture output.

This slice is a trajectory replay/validation layer. It does not infer effects from real records, tune a generator from held-out data, claim clinical validity, establish privacy or non-matchability, or make the currently fail-closed smoke CLI a production cohort generator. It works with the existing `AgeRegimeDisorderKernel`; package-level counterfactual EHR worlds remain deferred until observation, diagnosis, treatment, and ancillary-resource generation exist.

## Scope and boundaries

- Input is a fictional `AgeRegimeDisorderKernel`, patient, ages, and explicit intervention. No real-data root, calibration artifact, held-out report, privacy report, or patient-row reader is accepted.
- The paired worlds are hidden `AgeRegimeDisorderTrajectory` objects. The contract never changes the eight-resource schema, visible CSVs, or manifests.
- Stable synthetic patient identity and the sampled age-regime/disorder states are the pairing keys. Intervention labels, causal hashes, stream identities, hidden state, and event traces remain evaluator-only.
- The baseline and intervention share the same patient and sampled states. Reused streams must have identical identities and resampled streams must be distinct; seed equality alone is insufficient.
- Reports contain only aggregate check statuses, counts, and fixed reason codes. They never contain patient IDs, hidden values, event payloads, hashes, paths, or candidate links.
- A truth manifest is written only to a separately supplied new path if requested. Visible packages never contain it, and ordinary package serialization exposes no truth fields.

## Intervention matrix

The fixed interventions are:

| Intervention | Manipulated nodes | Permitted descendants | Required invariants |
| --- | --- | --- | --- |
| `physiology_severity` | `growth_physiology` | none in this slice | `age_regime`, `latent_disorder` before onset, `recognition`, `treatment` |
| `earlier_recognition` | `recognition` | event trace timing only | `age_regime`, `latent_disorder`, `growth_physiology`, `treatment` |
| `treatment_adherence` | `treatment` | post-treatment growth physiology | `age_regime`, `latent_disorder`, pre-treatment growth physiology, recognition trace |

The matrix is versioned and strict. Unknown nodes, duplicate entries, overlapping manipulated/invariant nodes, undeclared stream names, or assertions outside the permitted causal scope fail closed. Utilization-intensity and measurement-error-removal are explicitly rejected until the observation/resource layer exists. A caller may provide a stricter matrix for a specific experiment, but cannot weaken the fixed intervention semantics without a new reviewed version.

## Engine-neutral world contract

The implementation exposes immutable evaluator objects:

- `CounterfactualChangeMatrix` identifies one intervention, causal node sets, reused/resampled stream names, and trajectory assertions.
- `CounterfactualContext` identifies a patient, seed, intervention, and matrix and provides deterministic named stream access; it contains no real-data path.
- `CounterfactualPair` contains baseline plus one intervention `AgeRegimeDisorderTrajectory` and the matrix used to build them. Hidden fields are excluded from ordinary mappings/repr.
- `generate_counterfactual_pair` samples the latent states once, replays them through fresh deterministic stream instances, applies one supported intervention without uncontrolled randomness, and returns the pair only after structural validation.
- `validate_counterfactual_pair` returns an aggregate-only `CounterfactualValidationReport` with fixed checks for shared state, stream reuse, hidden causal layers, event traces, and directional trajectory assertions.
- `write_truth_manifest` writes a canonical evaluator-only JSON manifest outside the trajectory result and refuses an existing destination.

The trajectory contract compares z-score layers and event traces, not raw centimetre monotonicity. It validates finite values, event ordering, age coverage, and intervention-specific pre/post-onset or pre/post-treatment windows. No visible resource rows are read or generated in this slice.

## Assertions and status

Trajectory assertions use fixed expectations: invariant layers must hash equally, manipulated layers must differ when the intervention is evaluable, and permitted descendant layers may differ only where declared. Directional checks compare z-score deltas over the declared pre/post windows. A permitted descendant is not forced to differ, but an observed change outside the permitted causal set fails closed.

Each check is `PASS`, `FAIL`, or `UNEVALUABLE`. Missing resources, empty paired patient sets, malformed rows, missing stream evidence, or an absent hidden layer needed by the matrix are `UNEVALUABLE`, never a pass. The report is `FAIL` when any check fails; otherwise it is `UNEVALUABLE` when a required check cannot be evaluated; otherwise `PASS`. This is causal-contract evidence only, not clinical efficacy or privacy evidence.

## Reproducibility and leakage controls

The kernel receives deterministic named streams derived from the existing `sha256-v1`/`PCG64DXSM` contract. Shared streams are addressed without a world identifier; resampled streams are explicitly rejected for the current replay interventions. The context records only aggregate-safe stream names and deterministic identities. Canonical layer and event hashes are used internally for comparisons and may appear only in the external truth manifest, never in a report or visible package.

No visible package mapping is produced by this trajectory-only module. Truth-manifest serialization is explicit and separate from the existing CSV/manifest paths.

## Deferred work

This slice does not add exact-schema package generation, prevalence allocation, observation-error fitting, temporal-drift metrics, task-utility evaluation, a clinical review workflow, a production growth reference, or a Synthea adapter. Those remain separate approved gates. A complete exact-schema counterfactual world can be supplied by a future native generator or Synthea-conforming adapter; this replay contract is the trajectory-layer component shared by both engines.
