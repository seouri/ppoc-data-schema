# Native GHD Ancillary Pathway Contract

**Date:** 2026-08-31
**Status:** Implementation complete; evaluator-only fictional pathway; clinical, prevalence, privacy, and Synthea gates pending
**Parent:** [Synthetic Pediatric Growth Fixture System Design](2026-08-30-synthetic-growth-fixtures-design.md)

## Purpose

The native cohort and observation/resource contracts currently model growth
trajectories, visible visits, and fictional recognition/workup/diagnosis
descendants, while leaving `labs`, `medications`, `problem_list`, and
`referrals` empty. This slice adds the first disorder-critical ancillary
pathway for growth-hormone deficiency (GHD) as an immutable, in-memory
projection with exact descriptor field order and causal validation.

The pathway is a development and counterfactual-fixture contract. It is not a
clinical terminology model, prevalence estimator, authoritative augmentation
implementation, or release artifact. All values and labels are explicitly
fictional and are not presented as ICD, LOINC, RxNorm, or clinical reference
values.

## Design choice and alternatives

The recommended route is a small engine-neutral native projection module. It
accepts an existing fictional `CohortMember` and an already extracted
`ResourceShape`, then returns rows for the four ancillary resources. This
keeps hidden trajectory state and visible observation evidence separate,
avoids changing the established six-resource bundle/export boundary, and
leaves a narrow seam for later merging after package and derivation contracts
are reviewed.

Directly adding nonempty ancillary rows to `ObservedResourceBundle` is deferred
because its current validator intentionally treats ancillary rows as empty and
the package exporter still requires an authoritative derivation oracle.
Building the first pathway as a Synthea module is also deferred: it would not
replace the native growth physiology, exact PPOC field mapping, observation
contract, or derivation gate, and would introduce an engine-conformance
dependency before the native pathway is validated.

## Public API

Create `src/synthetic/native/ancillary.py` with these immutable records and
functions:

- `GhdAncillaryPolicy(policy_id, policy_version, result_delay_days)` — a
  versioned policy with aggregate-safe identifiers and a nonnegative result
  delay. The pathway terminology and record types remain fixed constants.
- `AncillaryResourceProjection(patient_id, shape, rows)` — visible fictional
  rows for exactly `labs`, `medications`, `problem_list`, and `referrals`.
  Every row uses the extracted descriptor field order and empty strings for
  missing values. Its mapping contains only the generated synthetic row
  values required by the exact schema; its `repr` contains no row payload,
  trajectory, severity, hidden-event, truth, or source-frame fields.
- `AncillaryValidationStatus`, `AncillaryCheck`, and
  `AncillaryValidationReport` — fixed aggregate/status-only validation values
  with `PASS`, `FAIL`, and `UNEVALUABLE` semantics.
- `project_ghd_ancillary_resources(member, shape, policy)` — a pure projection
  that does not mutate the member or perform random draws, file I/O, package
  writes, or governed imports.
- `validate_ghd_ancillary_resources(member, projection, policy)` — a pure
  aggregate-only validator. It never returns patient IDs, row identifiers,
  ages, codes, values, hidden events, or policy internals.

The projection is per member so callers can deliberately combine its exact
resource rows with a separately validated base bundle. A later integration
slice may add a cohort-level merger only after the ancillary row contract and
derivation boundary are reviewed.

## Causal pathway semantics

Only a member whose latent module kind is
`DisorderKind.GROWTH_HORMONE_DEFICIENCY` can produce GHD rows. The visible
observation frame is validated first. Source and visible event schedules must
remain in the existing causal order; malformed typed objects fail closed with
fixed redacted errors.

For a valid GHD member, the first matching visible event controls each
descendant:

| Visible source | Resource | Fixed fictional content | Link and timing |
| --- | --- | --- | --- |
| `recognition` | `referrals` | `requested_specialty="Synthetic Pediatric Endocrinology"`, `referral_number_of_visits=1` | linked to the recognition event's visible visit; referral age equals event age |
| `workup` | `labs` | one order with two fictional components, `SYN-GHD-IGF1` and `SYN-GHD-STIM`, with `result_flag="Synthetic"` and no LOINC claim | linked to the workup event's visible visit; order age equals event age; result age equals order age plus policy delay |
| `diagnosis` | `problem_list` | `pl_diag="SYN-GHD"` | no visit key; noted age equals diagnosis event age; unresolved row has an empty resolved age |
| visible diagnosis plus hidden `treatment_start` | `medications` | `med_record_type="Internal"`, `med_simple_generic_name="Synthetic growth hormone"` | linked to the diagnosis visit; order age equals diagnosis age; start age equals the hidden treatment event age; end age is empty |

Rows are emitted only once per event kind. A GHD trajectory that is not
recognized or diagnosed therefore has no corresponding visible descendant;
hidden treatment never creates a medication without a visible diagnosis.
Non-GHD members must return four empty row tuples. The projection never uses
severity, latent labels, or hidden events as visible text or as an allocator;
the hidden treatment event is consulted only to preserve the causal timing of
an already observed diagnosis-to-treatment descendant.

IDs are deterministic fictional tokens derived from the member's synthetic
patient identity and fixed resource role. They are unique within the
projection contract and do not reproduce or hash any real identifier. The
visible projection mapping necessarily contains these generated patient and
row identifiers so it can represent exact-schema rows; validation reports,
reprs, and errors never expose them.

## Exact-schema row contract

The projection requires a `ResourceShape` containing the repository's six base
resources, but emits only these four resource names:

`labs`, `medications`, `problem_list`, and `referrals`.

Each emitted row contains every field declared by the shape in exact order.
Fields not listed in the pathway table use the existing empty-string missing
value convention. The projection does not accept a descriptor path, path-like
object, arbitrary field list, CSV reader, row input, key, report, or output
destination. It does not alter `datapackage.json` or the existing base bundle
validator.

## Validation contract

`validate_ghd_ancillary_resources` returns fixed checks in this order:

1. `pathway_scope` — the member kind and empty/nonempty row expectation agree;
2. `row_schema` — resource names, field order, field types, IDs, and fixed
   fictional values are valid;
3. `causal_timing` — recognition/workup/diagnosis/treatment descendants are
   ordered, result delay is applied, and treatment does not precede diagnosis;
4. `cross_resource_links` — patient IDs and visible visit IDs resolve to the
   member's frame as required, while problem rows retain their nullable visit
   link semantics; and
5. `source_evidence` — the frame and required source events are present and
   pass the existing observation validator.

`FAIL` represents malformed typed rows, an invalid ID/code/value, a causal or
   link violation, or an out-of-scope pathway row. `UNEVALUABLE` represents
   absent or malformed private source evidence when no visible row itself is
   demonstrably invalid. `FAIL` takes precedence over `UNEVALUABLE`, which
   takes precedence over `PASS`. Reports are aggregate-only and expose fixed
   check names, statuses, and reason codes; they never expose row payloads.

## Determinism, mutation, and error boundary

Projection has no random draws. Replaying the same fictional member, shape,
and policy produces byte-equivalent mappings. The member, frame, and shape are
never mutated. Public exceptions use fixed pathway messages and do not include
patient or visit IDs, event payloads, severity, paths, keys, truth hashes, or
source values.

The module may import only standard-library helpers, native models, the
observation contract, the cohort member type, and `ResourceShape`/`ResourceRow`
value contracts. Boundary tests must reject governed calibration, real-data,
held-out, privacy, DuckDB, filesystem, CSV, package-export, manifest, and
Synthea imports or calls, and must assert no path-like or output arguments in
the public projection/validation signatures.

## Testing and documentation

Tests use only existing fictional cohort fixtures and the checked-in
descriptor mapping. They cover healthy/non-GHD emptiness, every GHD event
combination, optional treatment, same-age causal events, result delay,
nullable problem visit links, exact field order and units/types, deterministic
IDs, malformed/tampered rows, no mutation, redacted mappings/errors, and
static boundary scans. The focused tests, full suite, Ruff, schema validation,
whitespace checks, and a fresh broad review are required before merge.

`docs/synthetic-generator.md` and `README.md` will document the GHD pathway as
an evaluator-only exact-row projection and explicitly defer terminology
validation, other disorders, package/export integration, augmented derivation,
prevalence calibration, held-out validation, privacy/non-matchability,
clinical review, task utility, and Synthea conformance.

## Deferred work

This slice does not add hypothyroidism, celiac disease, Turner/SGA,
undernutrition, obesity, unrelated background resources, new clinical codes,
authoritative `patients_augmented`/`visits_augmented` derivation, complete
eight-resource package export, cohort-level ancillary merging, temporal-drift
or task-utility evaluation, clinical validation, privacy evidence, or a
Synthea-backed engine.

## Acceptance criteria

1. A valid GHD member deterministically produces exact-schema fictional labs,
   a referral, a problem-list row, and an optional treatment medication only
   when the corresponding visible/causal events permit them.
2. Healthy and non-GHD members produce empty ancillary tuples without hidden
   truth leakage.
3. Every emitted row uses the supplied descriptor's exact field order,
   required keys, nullable conventions, and fictional values.
4. The aggregate validator catches malformed IDs/codes/values, reversed or
   duplicate descendants, treatment-before-diagnosis, broken visit links, and
   source-frame failures with fixed statuses and redacted output.
5. Projection is deterministic, nonmutating, random-free, and has no governed,
   filesystem, package, manifest, or Synthea boundary coupling.
6. Documentation states the exact API, causal semantics, fictional terminology
   boundary, and all deferred claims; focused/full tests, static checks,
   schema/whitespace checks, and broad review pass before merge.
