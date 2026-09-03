# Native Pediatric-Hypothyroidism Ancillary Pathway Contract

**Date:** 2026-09-02
**Status:** Implementation complete; evaluator-only fictional pathway consumed by the published `development-all-disorders` route
**Parent:** [Synthetic Pediatric Growth Fixture System Design](2026-08-30-synthetic-growth-fixtures-design.md)
**Implementation plan:** [Native Pediatric-Hypothyroidism Ancillary Pathway Implementation Plan](../plans/2026-09-02-pediatric-hypothyroidism-ancillary-pathway.md)

## Purpose

The native fixture engine has a pediatric-hypothyroidism trajectory module but
keeps its clinical descendants hidden. This slice adds a separate immutable,
in-memory projection for fictional thyroid workup, diagnosis, referral, and
treatment rows. It preserves the exact PPOC resource shape and does not change
the generic observed bundle, `development-realistic` runtime, package export,
or any real/gated-data boundary.

This is ordinary synthetic development and counterfactual-fixture support. It
is not a clinical terminology model, treatment recommendation, prevalence
estimate, privacy proof, or Synthea implementation. All labels are fictional
and must not be interpreted as ICD, LOINC, or RxNorm values.

## Design choice and alternatives

Create `synthetic.native.pediatric_hypothyroidism_ancillary` with separate
models, constants, projection, and validator. Its typed API mirrors the
reviewed excess-weight and GHD contracts but owns its own namespaced IDs and
fictional strings. It accepts only one typed `CohortMember`, an extracted
`ResourceShape`, and an aggregate-safe policy.

Do not widen `ObservedResourceBundle`, change GHD modules, or add a generic
ancillary utility in this slice. Do not integrate into `development-realistic`
or package export; that visible-output change is a later reviewed item. Do not
build a Synthea module here: Synthea cannot replace native growth physiology,
observation truth binding, exact PPOC mapping, or the derivation boundary, and
engine conformance remains optional downstream work.

## Public API

Create `src/synthetic/native/pediatric_hypothyroidism_ancillary.py` with:

- `PediatricHypothyroidismAncillaryPolicy(policy_id, policy_version,
  result_delay_days)`;
- `PediatricHypothyroidismAncillaryProjection(patient_id, shape, rows)`;
- `PediatricHypothyroidismAncillaryValidationStatus`,
  `PediatricHypothyroidismAncillaryCheck`, and
  `PediatricHypothyroidismAncillaryValidationReport`;
- `project_pediatric_hypothyroidism_ancillary_resources(member, shape,
  policy)`; and
- `validate_pediatric_hypothyroidism_ancillary_resources(member, projection,
  policy)`.

Rows contain exactly `labs`, `medications`, `problem_list`, and `referrals` in
fixed order. Projection mappings may contain generated synthetic patient and
row identifiers required by the exact schema. Reprs, exceptions, checks, and
reports must not expose identifiers, ages, codes, values, events, severity,
truth hashes, paths, keys, or source evidence.

## Causal pathway semantics

Only a valid member whose latent kind is
`DisorderKind.PEDIATRIC_HYPOTHYROIDISM` can emit descendants. Validate the
observation frame and member-to-truth binding before assembling rows. The
first recorded visible event of each kind controls its descendant and source
point identity supplies the visible visit link.

| Visible source | Resource | Fixed fictional content | Link and timing |
| --- | --- | --- | --- |
| `recognition` | `referrals` | `requested_specialty="Synthetic Pediatric Endocrinology"`, `referral_number_of_visits=1` | recognition event's visible visit; referral age equals event age |
| `workup` | `labs` | one order with `SYN-HYPOTHYROIDISM-TSH` and `SYN-HYPOTHYROIDISM-FREE-T4`; `result_flag="Synthetic"`; no LOINC or result value | workup event's visible visit; order age equals event age; result age equals order age plus policy delay |
| `diagnosis` | `problem_list` | `pl_diag="SYN-PEDIATRIC-HYPOTHYROIDISM"`; unresolved row | nullable visit follows the schema; noted age equals diagnosis event age |
| visible `diagnosis` plus hidden `treatment_start` | `medications` | `med_record_type="Internal"`, `med_simple_generic_name="Synthetic levothyroxine"` | linked to diagnosis visit; order age equals diagnosis age; start age equals hidden treatment age only when it is no earlier than observed diagnosis; end age empty |

Rows are emitted at most once per event kind. A hidden treatment event never
creates a medication without a visible diagnosis. If treatment precedes an
observed diagnosis because the frame censors the diagnosis visit, suppress the
medication rather than implying an unobserved diagnosis. Same-age causal
events are valid when their order remains the registered phase order.

Healthy, GHD, excess-weight, and all other kinds return four empty tuples.
The pathway does not write or infer `obesity_flag`; that field remains a
separately derived observed BMI-percentile field in any later package route.

IDs are deterministic opaque synthetic tokens using a distinct
`pediatric-hypothyroidism-ancillary-id-v1` namespace. They are never copied
from or derived from real identifiers.

## Exact-schema row contract

The supplied `ResourceShape` must contain the six repository base resources.
Each row includes every descriptor field in exact order. Unlisted fields use
the existing empty-string missing convention, including lab procedure metadata,
LOINC, result values, and nullable resolved dates. The module accepts no
descriptor path, path-like value, CSV reader, arbitrary row/field list, key,
report, or output destination and does not edit `datapackage.json`.

## Validation contract

The validator emits five fixed checks in this order:

1. `pathway_scope` — target kind, descendant counts, and medication gating;
2. `row_schema` — resource names, descriptor order, scalar types, fictional
   constants, opaque IDs, and empty conventions;
3. `causal_timing` — visible event ages, diagnosis-to-treatment ordering, and
   delayed lab results;
4. `cross_resource_links` — patient and visible visit IDs resolve to the
   member's visible frame; problem rows retain nullable visit semantics; and
5. `source_evidence` — observation frame and private source binding pass the
   existing observation validator.

`FAIL` is a visible structural, scope, value, timing, link, or invalid-source
violation. `UNEVALUABLE` is absent or malformed private evidence when no
visible violation is independently demonstrable. Overall precedence is
`FAIL > UNEVALUABLE > PASS`.

Visible `RecordedEvent` values remain available even when private truth is
missing or invalid. Therefore the validator must independently derive expected
counts and event ages from valid visible events before attempting private
source comparison: a visible workup requires two labs, a visible recognition
requires one referral, a visible diagnosis requires one problem row, and a
visible diagnosis plus an eligible hidden treatment start requires one
medication. If visible rows violate those count/age rules, the corresponding
check is `FAIL` even when `source_evidence` is `UNEVALUABLE` or `FAIL`.
Source-point/visit correspondence that needs private opportunities is checked
only when source evidence is valid. Reports expose fixed check names, statuses,
and reason codes only; no row payload is returned.

## Determinism and boundary

Projection has no random draws, filesystem/package I/O, environment reads,
network calls, or governed imports. Replaying identical typed inputs produces
byte-equivalent mappings and never mutates member, frame, shape, or policy.
Malformed inputs cross one fixed redacted projection error. Static tests must
reject calibration, real-data, held-out, privacy, DuckDB, CSV, filesystem,
package/export, manifest, subprocess, and Synthea coupling.

## Testing and documentation

Tests use only checked-in fictional cohort fixtures and the descriptor mapping.
They cover healthy/GHD/non-target emptiness, every visible event combination,
optional and censored treatment, same-age events, delayed results, nullable
problem links, exact fields/types, deterministic IDs, tampering/duplicates,
visible-event checks with missing/invalid truth, no mutation, and redacted
output. Focused/full tests, Ruff, schema, whitespace, and an independent broad
review are required before merge.

`docs/synthetic-generator.md` documents the API and fictional terminology;
`README.md` links to the guide. Runtime/package integration, prevalence and
demographic calibration, held-out comparison, privacy/non-matchability review,
clinical review, release authorization, and optional Synthea conformance are
deferred.

## Acceptance criteria

1. A valid pediatric-hypothyroidism member deterministically produces only the
   referral, two thyroid labs, problem row, and causally eligible medication
   permitted by visible events; hidden treatment alone never creates a row.
2. Non-target members produce four empty tuples without hidden-truth leakage;
   no row writes or implies `obesity_flag`.
3. Every row follows the supplied descriptor's exact field order/types and
   missing-value conventions.
4. Validation catches malformed IDs/codes/values, wrong counts, duplicates,
   reversed or undelayed results, treatment-before-diagnosis, broken links,
   and source failures. Visible count/age violations remain `FAIL` despite
   unavailable private truth.
5. Projection is deterministic, nonmutating, random-free, and free of
   filesystem, package, governed-data, manifest, and Synthea coupling.
6. Focused/full tests, static checks, schema/whitespace checks, documentation,
   and broad review pass before publication.
