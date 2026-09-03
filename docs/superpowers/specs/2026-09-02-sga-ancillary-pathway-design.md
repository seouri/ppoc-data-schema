# Native SGA Ancillary Pathway Contract

**Date:** 2026-09-02
**Status:** Approved for implementation; evaluator-only fictional pathway
**Parent:** [Synthetic Pediatric Growth Fixture System Design](2026-08-30-synthetic-growth-fixtures-design.md)

## Purpose

Add a separate immutable, in-memory projection for fictional small-for-
gestational-age (SGA) follow-up rows. The projection preserves the exact PPOC
resource shape while leaving the generic observed bundle, visible generator,
package exporter, and SGA trajectory kernel unchanged. It is an ordinary
synthetic-development and counterfactual-fixture contract, not a clinical
terminology model, gestational-age estimator, prematurity classifier,
prevalence estimate, treatment recommendation, privacy proof, or Synthea
implementation. Every label is fictional and must not be interpreted as an
ICD, LOINC, RxNorm, or clinical value.

## Design choice and alternatives

Create `synthetic.native.sga_ancillary` with its own frozen policy, projection,
fictional constants, validator, and `sga-ancillary-id-v1` namespace. It accepts
one typed `CohortMember`, an extracted `ResourceShape`, and a policy, then
returns exact-schema rows for the four existing ancillary resources. This
keeps hidden birth-state/catch-up branch state separate from visible
observation evidence and avoids widening the six-resource bundle or runtime.

Do not add gestational-age fields to `datapackage.json`, repurpose existing
clinical codes, widen the generic bundle validator, or integrate this module
with `development-realistic` or package export. The current descriptor has no
dedicated gestational-age or birth-size resource; therefore the workup rows
use fictional component names and empty result values rather than inventing
measurements. A Synthea module is a later optional adapter, not part of this
native exact-schema contract.

## Public API

Create `src/synthetic/native/sga_ancillary.py` with:

- `SgaAncillaryPolicy(policy_id, policy_version, result_delay_days)`;
- `SgaAncillaryProjection(patient_id, shape, rows)`;
- `SgaAncillaryProjectionUnavailable`;
- `SgaAncillaryValidationStatus`, `SgaAncillaryCheck`, and
  `SgaAncillaryValidationReport`;
- `project_sga_ancillary_resources(member, shape, policy)`; and
- `validate_sga_ancillary_resources(member, projection, policy)`.

Rows contain exactly `labs`, `medications`, `problem_list`, and `referrals` in
that fixed order. Every row uses the supplied descriptor field order and
empty strings for fields not represented by this pathway. Reprs, exceptions,
checks, and reports omit IDs, ages, codes, values, events, severity, truth
hashes, paths, keys, and source evidence.

## Causal pathway semantics

Only a valid member whose latent kind is
`DisorderKind.SMALL_FOR_GESTATIONAL_AGE` can emit descendants. Validate the
observation frame and exact member-to-frame truth binding before projection.
The first recorded visible event of each kind controls its descendant and its
source point supplies the visible visit link.

| Visible source | Resource | Fixed fictional content | Link and timing |
| --- | --- | --- | --- |
| `recognition` | `referrals` | `requested_specialty="Synthetic Neonatology Follow-up"`, `referral_number_of_visits=1` | recognition event's visible visit; referral age equals event age |
| `workup` | `labs` | one order with `SYN-SGA-GESTATIONAL-AGE` and `SYN-SGA-BIRTH-SIZE`; `result_flag="Synthetic"`; no LOINC or result value | workup event's visible visit; order age equals event age; result age equals order age plus policy delay |
| `diagnosis` | `problem_list` | `pl_diag="SYN-SGA"`; unresolved row | no visit key; noted age equals diagnosis event age |
| any treatment event | `medications` | no row in this slice | SGA's native trajectory has no treatment descendant; injected medication rows are out of scope |

The birth phenotype at age zero and the catch-up versus persistent-height
branch remain hidden trajectory state. They never directly create a visible
row or alter the fictional labels. Recognition/workup/diagnosis descendants
are emitted at most once per event kind; hidden or unrecorded events never
create rows. A same-age event sequence is valid when its registered phase
order is valid.

Healthy, GHD, hypothyroidism, celiac disease, Turner syndrome, undernutrition,
excess weight, familial short stature, constitutional delay, and every other
non-SGA member return four empty tuples. No emitted row contains or derives
`obesity_flag`.

## Exact-schema row contract

The projection requires a `ResourceShape` containing the repository's six base
resources, but emits only the four ancillary names above. IDs are deterministic
fictional tokens derived only from the synthetic patient identity and fixed
resource role. They do not reproduce or hash real identifiers. The projection
accepts no descriptor path, path-like object, CSV reader, row input, key,
report, output destination, environment input, or governed data.

The two lab components are closed fictional labels. `result_loinc_code` and
`result_value` remain empty strings, as do unrelated fields; the synthetic
`result_flag` is an in-memory evaluator marker. The problem row is unresolved
with an empty `resolved_date_age_in_days`; the referral has one requested
visit. The medication resource is always an empty tuple, including for a
malformed or externally injected treatment state.

## Validation contract

`validate_sga_ancillary_resources` returns fixed checks in this order:

1. `pathway_scope` — the member kind and expected empty/nonempty row counts
   agree, including the always-empty medication rule;
2. `row_schema` — resource names, descriptor field order, scalar types, IDs,
   and fixed fictional values are valid;
3. `causal_timing` — recognition/workup/diagnosis descendants are ordered and
   the lab result delay is applied;
4. `cross_resource_links` — patient IDs and all referral/lab visit IDs resolve
   to actual frame visits while the problem row retains its nullable visit
   semantics; and
5. `source_evidence` — the frame and typed member-to-truth binding are valid.

Statuses are only `PASS`, `FAIL`, and `UNEVALUABLE`, with overall precedence
`FAIL > UNEVALUABLE > PASS`. Visible counts, ages, types, constants, links,
and the medication prohibition are checked before private source validation.
Thus an injected medication, wrong visible count, wrong age, or broken visit
link remains `FAIL` when truth is missing or invalid. Missing or malformed
private evidence is `UNEVALUABLE` only when no visible violation is provable;
an observation failure or a valid-frame/member trajectory/source-event binding
mismatch is `FAIL/SOURCE_EVIDENCE_INVALID`. Deterministic comparison with the
projection occurs only after source and binding pass.

Reports and checks are frozen, fixed-order, aggregate-only, and redacted. They
never return row values, IDs, ages, codes, hidden events, source evidence,
paths, or keys.

## Determinism, boundaries, and testing

Projection is deterministic, random-free, and nonmutating. The module imports
only standard-library helpers and the native cohort/model/observation/resource
contracts. Boundary tests reject calibration, real-data, held-out, privacy,
DuckDB, filesystem, CSV, package/export, manifest, subprocess, environment,
network, randomness, and Synthea coupling, plus `obesity_flag` leakage.

Tests use checked-in fictional fixtures and the descriptor mapping. They cover
birth-onset target members, catch-up and persistent branch emptiness, all
visible event combinations, same-age events, result delay, exact field order,
nullable problem links, always-empty medications, deterministic IDs,
malformed/tampered rows, missing/invalid source evidence, valid-frame/member
trajectory mismatch, visible-before-private precedence, no mutation,
redaction, and non-SGA emptiness.

## Documentation and deferred work

`docs/synthetic-generator.md` and `README.md` will add a concise evaluator-only
SGA section with the exact API, fictional values, causal rows, and hidden
birth-state boundary. Runtime/package integration, prevalence and demographic
calibration, privacy/non-matchability, clinical review, release authorization,
real or held-out data, gestational-age resource expansion, and optional Synthea
conformance remain deferred and are not ordinary-development prerequisites.

## Acceptance criteria

1. A valid SGA member deterministically produces exact-schema fictional
   referral/lab/problem rows only when their visible events are recorded;
   medications are always empty.
2. Healthy and non-SGA members produce empty ancillary tuples without hidden
   branch or birth-state leakage.
3. Every emitted row follows the supplied descriptor order, types, nullable
   conventions, and fictional values.
4. The aggregate validator catches scope, schema, timing, links, medication
   injection, and source/frame failures with fixed statuses and redacted
   output, while missing private evidence is unevaluable only absent visible
   failure.
5. Focused/full tests, static checks, schema/whitespace checks, and a broad
   review pass before merge; no visible runtime or package route changes.
