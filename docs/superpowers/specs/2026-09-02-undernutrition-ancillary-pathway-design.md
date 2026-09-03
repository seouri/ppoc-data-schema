# Native Undernutrition Ancillary Pathway Contract

**Date:** 2026-09-02
**Status:** Implementation complete; evaluator-only fictional pathway consumed by the published `development-all-disorders` route
**Parent:** [Synthetic Pediatric Growth Fixture System Design](2026-08-30-synthetic-growth-fixtures-design.md)
**Implementation plan:** [Native Undernutrition Ancillary Pathway Implementation Plan](../plans/2026-09-02-undernutrition-ancillary-pathway.md)

## Purpose

Add a separate immutable, in-memory projection for fictional undernutrition
recognition, nutrition workup, diagnosis, referral, and treatment rows. The
projection preserves the checked-in PPOC resource shape while leaving the
generic observed bundle, visible generator, package exporter, and native
undernutrition trajectory kernel unchanged. It is ordinary synthetic
development and counterfactual-fixture support. It is not a clinical
terminology model, prevalence estimate, nutrition recommendation for a real
patient, privacy proof, or Synthea implementation. Every label and value is
fictional and must not be interpreted as an ICD, LOINC, RxNorm, or other
clinical terminology/value claim.

## Design choice and alternatives

Create `synthetic.native.undernutrition_ancillary` with its own frozen policy,
projection, fictional vocabulary, validator, and
`undernutrition-ancillary-id-v1` identifier namespace. The typed API accepts
one `CohortMember`, an already extracted `ResourceShape`, and a policy, then
returns exact-schema rows for the four ancillary resources. This keeps the
native module's hidden weight-first physiology and treatment state separate
from visible observation evidence and avoids widening the six-resource bundle
or runtime.

Do not add fields or resources to `datapackage.json`, repurpose clinical
terminology, change `UndernutritionModule`, widen the generic ancillary
validator, or integrate with `development-realistic` or package export. The
current descriptor has no dedicated nutrition-assessment resource; therefore
the workup rows use fictional component names and empty result values rather
than inventing measurements. A Synthea module is an optional later adapter,
not an alternative implementation in this native exact-schema contract.

## Undernutrition source behavior carried into the contract

`UndernutritionModule` is an uncalibrated evaluator-only trajectory module
with `kind=DisorderKind.UNDERNUTRITION` and `module_version="undernutrition-v1"`.
For a positive-severity state it emits the ordered source-event sequence
`latent_onset`, `observable_phenotype`, `recognition_opportunity`, `workup`,
`recorded_diagnosis`, and, when treatment is sampled,
`treatment_start` followed by `treatment_response` or
`treatment_nonresponse`. Onset is strictly after birth. BMI/weight decline
begins at onset, height decline begins only after
`height_onset_delay_days`, and treatment can partially recover both effects.
The zero-severity state has only its hidden `latent_onset` event and therefore
has no visible ancillary descendants.

Only recognition, workup, and recorded diagnosis have
`RecordedEvent` values in an observation frame. The trajectory's treatment
start is evaluator-held source state rather than a visible recorded event;
its response or nonresponse is never a resource row. The projection uses the
first recorded visible event of each `RecordedEventKind`. It resolves that
event's `opportunity_index` through the realized source-point opportunity to
the corresponding visible visit and never re-matches a source event to a
visit by age. Same-age visible events are valid when the registered
recognition/workup/diagnosis phase order is preserved.

## Public API

Create `src/synthetic/native/undernutrition_ancillary.py` with:

- `UNDERNUTRITION_ANCILLARY_RESOURCE_NAMES` and
  `UNDERNUTRITION_LAB_COMPONENT_NAMES` fixed tuples;
- `UndernutritionAncillaryPolicy(policy_id, policy_version, result_delay_days)`;
- `UndernutritionAncillaryProjection(patient_id, shape, rows)`;
- `UndernutritionAncillaryProjectionUnavailable`;
- `UndernutritionAncillaryValidationStatus`,
  `UndernutritionAncillaryCheck`, and
  `UndernutritionAncillaryValidationReport`;
- `project_undernutrition_ancillary_resources(member, shape, policy)`; and
- `validate_undernutrition_ancillary_resources(member, projection, policy)`.

The projection mapping contains exactly `labs`, `medications`,
`problem_list`, and `referrals` in that order. Each value is an immutable
tuple of `ResourceRow` values built in the supplied descriptor field order.
Projection mappings may contain the synthetic patient and row identifiers
required by the exact schema. Reprs, projection exceptions, validation
checks, and reports are aggregate-only and omit identifiers, ages, codes,
values, events, severity, truth hashes, paths, keys, and source evidence.

## Closed fictional vocabulary

The module owns these exact constants; callers cannot provide replacement
terminology:

| Constant | Exact fictional value | Use |
| --- | --- | --- |
| `UNDERNUTRITION_DIAGNOSIS_CODE` | `SYN-UNDERNUTRITION` | unresolved `problem_list.pl_diag` |
| `UNDERNUTRITION_WEIGHT_COMPONENT` | `SYN-UNDERNUTRITION-WEIGHT-EVIDENCE` | first lab component label |
| `UNDERNUTRITION_HEIGHT_COMPONENT` | `SYN-UNDERNUTRITION-HEIGHT-EVIDENCE` | second lab component label |
| `UNDERNUTRITION_LAB_RESULT_FLAG` | `Synthetic` | in-memory evaluator marker |
| `UNDERNUTRITION_REFERRAL_SPECIALTY` | `Synthetic Pediatric Nutrition` | referral specialty |
| `UNDERNUTRITION_MEDICATION_NAME` | `Synthetic nutrition-supplement intervention` | fictional treatment name |
| `UNDERNUTRITION_MEDICATION_RECORD_TYPE` | `Internal` | medication record type |
| identifier namespace | `undernutrition-ancillary-id-v1` | deterministic ID material |

The two lab components are closed fictional labels. They have no LOINC code,
result value, or clinical interpretation; `result_loinc_code` and
`result_value` remain empty strings. The diagnosis token is not an ICD code,
the medication name is not a RxNorm name, and the referral, marker, and
component labels are not clinical values. The nutrition-supplement treatment
is represented only by the fictional medication label in this evaluator
fixture; it is not a treatment recommendation.

## Causal pathway semantics

Only a valid member whose latent kind is
`DisorderKind.UNDERNUTRITION` can emit descendants. Validate the observation
frame and the typed member-to-truth binding before assembling rows. Hidden
onset, phenotype, severity, and treatment-response state never becomes a row
or terminology/value claim.

| Visible source | Resource | Fixed fictional content | Link and timing |
| --- | --- | --- | --- |
| `recognition` | `referrals` | `requested_specialty="Synthetic Pediatric Nutrition"`, `referral_number_of_visits=1` | recognition event's source-point visit; referral age equals event age |
| `workup` | `labs` | one order with `SYN-UNDERNUTRITION-WEIGHT-EVIDENCE` and `SYN-UNDERNUTRITION-HEIGHT-EVIDENCE`; `result_flag="Synthetic"`; empty LOINC and result values | workup event's source-point visit; both order ages equal event age; both result ages equal order age plus policy delay |
| `diagnosis` | `problem_list` | `pl_diag="SYN-UNDERNUTRITION"`; unresolved row | problem schema has no visit key; noted age equals diagnosis event age |
| visible `diagnosis` plus private `treatment_start` | `medications` | `med_record_type="Internal"`, `med_simple_generic_name="Synthetic nutrition-supplement intervention"` | diagnosis event's source-point visit; order age equals diagnosis age; start age equals private treatment age only when not earlier than diagnosis; end age empty |

Each visible descendant is emitted at most once per event kind. A private
treatment start never creates a medication without an observed diagnosis. If
the observation frame censors the diagnosis, or a malformed/tampered private
treatment age precedes the observed diagnosis, suppress the medication rather
than implying an unobserved diagnosis. A treatment response or nonresponse
event creates no additional resource. The medication tuple is empty when
there is no eligible private treatment start.

Healthy and every non-undernutrition member return four empty tuples,
including GHD, hypothyroidism, celiac disease, SGA, Turner syndrome,
excess weight, familial short stature, constitutional delay, and future kinds.
The pathway never emits, writes, or derives `obesity_flag`; that field remains
separately derived from observed BMI-percentile data in any later route.

Identifiers are deterministic opaque synthetic tokens derived only from the
synthetic patient identity and fixed resource role using the
`undernutrition-ancillary-id-v1` namespace. They are never copied from,
hashed from, or matched to real identifiers. The same `lab-order` identifier
is shared by the two component rows, while line numbers distinguish the
components.

## Exact-schema row contract

The supplied `ResourceShape` must contain all six base resources in the
descriptor's fixed order. The current checked-in `datapackage.json` supplies
the following emitted-resource field order:

```text
labs: patient_id, visit_id, lab_order_id, result_line_num,
      lab_order_date_age_in_days, lab_procedure_name,
      lab_procedure_description, lab_result_date_age_in_days,
      result_component_name, result_loinc_code, result_value, result_flag
medications: patient_id, visit_id, med_record_id,
             med_order_date_age_in_days, med_start_date_age_in_days,
             med_end_date_age_in_days, med_record_type,
             med_simple_generic_name
problem_list: patient_id, problem_list_id, noted_date_age_in_days,
              resolved_date_age_in_days, pl_diag
referrals: patient_id, visit_id, referral_id, referral_date_age_in_days,
           requested_specialty, referral_number_of_visits
```

Every emitted row includes every field in the supplied shape and preserves
its exact order and scalar type. Unlisted fields use the repository's
empty-string missing-value convention. This includes lab procedure metadata,
`result_loinc_code`, `result_value`, medication end date, and problem-list
resolved date. The problem row has no `visit_id` because the current
descriptor does not define one; referral, lab, and medication visit IDs must
be source-point-linked visible synthetic visit IDs.

The module accepts no descriptor path, path-like object, CSV reader, arbitrary
row or field list, key, report, output destination, environment input, or
governed data. It does not edit `datapackage.json`.

## Validation contract

`validate_undernutrition_ancillary_resources` returns exactly five fixed
checks in this order:

1. `pathway_scope` — undernutrition target/non-target scope, expected
   descendant counts, and diagnosis-plus-private-treatment medication gate;
2. `row_schema` — four-resource order, descriptor field order, scalar types,
   deterministic opaque IDs, fictional constants, and empty conventions;
3. `causal_timing` — visible phase order, event-to-row ages,
   diagnosis-to-medication ordering, and delayed lab results;
4. `cross_resource_links` — patient identity and every referral/lab/medication
   visit ID resolve to the member's actual visible frame visits, while the
   problem row keeps its schema-defined nullable visit semantics; and
5. `source_evidence` — the observation frame and typed member-to-truth
   binding pass the existing observation validator, including source-event and
   source-point linkage when that evidence is available.

Statuses are only `PASS`, `FAIL`, and `UNEVALUABLE`, with overall precedence
`FAIL > UNEVALUABLE > PASS`. The fixed reason vocabulary is aggregate-only:
`OK` for `PASS`; `PATIENT_MISMATCH`, `SCHEMA_SHAPE_INVALID`,
`ROW_SCHEMA_INVALID`, `PATHWAY_SCOPE_INVALID`, `CAUSAL_TIMING_INVALID`,
`CROSS_RESOURCE_LINK_INVALID`, `SOURCE_EVIDENCE_INVALID`,
`MALFORMED_PROJECTION`, `INVALID_ID`, `INVALID_CODE`, `INVALID_VALUE`,
`DUPLICATE_ROW`, `EVENT_ORDER_INVALID`, `TIMING_INVALID`,
`VISIT_REFERENCE_INVALID`, and `PATHWAY_OUT_OF_SCOPE` for `FAIL`; and
`MALFORMED_ANCILLARY`, `MALFORMED_MEMBER`, `INSUFFICIENT_EVIDENCE`, and
`SOURCE_EVIDENCE_UNAVAILABLE` for `UNEVALUABLE`.

Visible `RecordedEvent` values remain available even when private truth is
missing or invalid. Consequently, visible structure, constants, counts,
ages, medication gating that is independently decidable, and actual visible
visit links are checked before private source validation. A visible workup
requires two lab rows, a visible recognition requires one referral, a visible
diagnosis requires one problem row, and a visible diagnosis plus an eligible
private treatment start requires one medication. A visible violation remains
`FAIL` even when source evidence is `UNEVALUABLE` or `FAIL`. Missing or
malformed private evidence is `UNEVALUABLE` only when no visible violation is
independently demonstrable. A valid-frame/member trajectory or source-event
binding mismatch is `FAIL/SOURCE_EVIDENCE_INVALID`. Deterministic comparison
with the expected projection occurs only after source evidence and binding
pass.

Reports and checks are frozen, fixed-order, aggregate-only values. They never
return row values, identifiers, ages, codes, hidden treatment, trajectories,
source evidence, paths, or keys.

## Determinism, boundaries, and testing

Projection is deterministic, random-free, nonmutating, and in-memory. The
module imports only standard-library helpers and the native cohort, model,
observation, and resource contracts. It does not import calibration,
real-data, held-out, privacy, DuckDB, filesystem, CSV, package/export,
manifest, subprocess, environment, network, or Synthea modules. Static
boundary tests reject those imports and APIs, plus `obesity_flag` leakage,
descriptor/path inputs, arbitrary row inputs, and output or package writes.

Tests use only checked-in fictional cohort fixtures and an in-memory
descriptor mapping. They cover frozen models, safe tokens, exact resource and
field order, all visible event combinations, optional and censored treatment,
source-point visit binding, same-age phase order, delayed lab results,
nullable problem links, exact scalar types, deterministic IDs, no latent
severity or treatment-response leakage, no mutation, tampered/duplicate rows,
always-empty non-undernutrition resources, missing/invalid source evidence,
visible-before-private precedence, redacted errors/reports, and the absence
of `obesity_flag`.

## Documentation and deferred work

`docs/synthetic-generator.md` will document the exact API, fictional
terminology, undernutrition source-event schedule, weight-first/delayed-height
trajectory boundary, hidden treatment gate, nutrition-supplement fictional
label, and exact-schema/in-memory boundary. `README.md` will link the guide,
spec, and implementation plan without duplicating the guide.

Runtime and package integration, prevalence or demographic calibration,
privacy/non-matchability evaluation, clinical review or nutrition guidance,
release authorization, real or held-out data, and optional Synthea
conformance remain deferred. Dedicated nutrition resources, clinical
terminology mappings, and any serialization of the in-memory `Synthetic`
marker require separate reviewed contracts. They are not prerequisites for
ordinary synthetic development, and no deferred workflow may introduce
patient rows or alter this typed projection contract.

## Acceptance criteria

1. A valid undernutrition member deterministically emits only the fictional
   referral, two-component lab order, unresolved problem, and causally
   eligible nutrition-supplement medication permitted by visible events and
   private treatment state.
2. A hidden treatment start alone never creates a medication, a censored or
   later observed diagnosis suppresses treatment until the visible diagnosis
   gate is satisfied, and treatment response/nonresponse creates no extra row.
3. Healthy and every non-undernutrition member produce four empty tuples
   without hidden onset, severity, or treatment-response leakage; no row
   contains or derives `obesity_flag`.
4. Every emitted row follows the supplied descriptor's exact field order,
   scalar types, empty-string conventions, source-point-linked visit IDs, and
   deterministic namespace IDs.
5. The aggregate validator catches scope, schema, fictional-value, count,
   duplicate, timing, delayed-result, medication-gate, patient/visit-link,
   frame, and source-binding failures while preserving fixed status
   precedence and redaction.
6. Focused/full tests, static boundary checks, schema/whitespace checks,
   documentation checks, and an independent broad review pass before any
   future merge or publication; this slice does not modify visible runtime or
   package export.
