# Native Excess-Weight Ancillary Pathway Contract

**Date:** 2026-09-02
**Status:** Approved for implementation; evaluator-only fictional pathway
**Parent:** [Synthetic Pediatric Growth Fixture System Design](2026-08-30-synthetic-growth-fixtures-design.md)

## Purpose

The native fixture engine already represents growth trajectories, visible
observation frames, and a reviewed GHD ancillary descendant path. The next
bounded pathway adds fictional excess-weight descendants as a separate,
immutable in-memory projection. It preserves the exact PPOC resource shape
without changing the generic observed bundle, the `development-realistic`
package route, or any release/gated-data boundary.

This is ordinary synthetic development and counterfactual-fixture support. It
is not a prevalence estimate, clinical terminology model, treatment
recommendation, obesity classifier, privacy proof, or Synthea implementation.
Every label and value is fictional. `EXCESS_WEIGHT` is a latent trajectory
kind; it must not be treated as, or write, the separately derived visible
`obesity_flag`.

## Design choice and alternatives

Use a new native module, `synthetic.native.excess_weight_ancillary`, with
separate models, constants, projection, and validator. Its API mirrors the
reviewed GHD contract but does not reuse GHD-specific constants or classes.
The module accepts only a typed `CohortMember`, an extracted `ResourceShape`,
and an aggregate-safe `ExcessWeightAncillaryPolicy`; it returns immutable
typed rows and aggregate-only validation status.

Do not widen `ObservedResourceBundle`, `ancillary_contract.py`, or the GHD
bundle merger. Do not integrate this projection into `development-realistic`
or package export in this slice. That later integration is a separately
reviewed item because it changes visible package composition and derivation
semantics. Do not add a Synthea module here: Synthea cannot replace the
native growth physiology, observation truth binding, exact PPOC shape, or
derivation boundary, and engine conformance is a separate optional route.

## Public API

Create `src/synthetic/native/excess_weight_ancillary.py` with:

- `ExcessWeightAncillaryPolicy(policy_id, policy_version, result_delay_days)`;
  IDs are aggregate-safe tokens and the delay is a nonnegative integer.
- `ExcessWeightAncillaryProjection(patient_id, shape, rows)`; rows contain
  exactly `labs`, `medications`, `problem_list`, and `referrals` in that
  order, with immutable tuples and descriptor-ordered fields.
- `ExcessWeightAncillaryValidationStatus`,
  `ExcessWeightAncillaryCheck`, and
  `ExcessWeightAncillaryValidationReport`; statuses are `PASS`, `FAIL`, and
  `UNEVALUABLE` with fixed aggregate-only check/reason values.
- `project_excess_weight_ancillary_resources(member, shape, policy)`;
  deterministic, random-free, nonmutating, and in-memory only.
- `validate_excess_weight_ancillary_resources(member, projection, policy)`;
  a status-only validator with no payload-bearing error/report boundary.

The projection mapping may contain generated synthetic patient and row IDs
because it represents exact-schema visible rows. `repr`, exceptions, checks,
and reports must not expose IDs, ages, codes, row values, events, severity,
truth hashes, paths, keys, or source evidence.

## Causal pathway semantics

Only a valid member whose latent module kind is
`DisorderKind.EXCESS_WEIGHT` can emit rows. The observation frame and member
truth binding are validated before any row is assembled. The first recorded
visible event of each kind controls its descendant; source-point identity,
not age-based re-matching, supplies the visit link.

| Visible source | Resource | Fixed fictional content | Link and timing |
| --- | --- | --- | --- |
| `recognition` | `referrals` | `requested_specialty="Synthetic Pediatric Nutrition"`, `referral_number_of_visits=1` | recognition event's visible visit; referral age equals event age |
| `workup` | `labs` | one order with `SYN-EXCESS-WEIGHT-LIPID` and `SYN-EXCESS-WEIGHT-A1C`; `result_flag="Synthetic"`; no LOINC or result value | workup event's visible visit; order age equals event age; result age equals order age plus policy delay |
| `diagnosis` | `problem_list` | `pl_diag="SYN-EXCESS-WEIGHT"`; unresolved row | nullable visit follows the schema; noted age equals diagnosis event age |
| `treatment_start` | none | no visible medication row | this latent event represents a behavioral/weight-management response in this slice, not a medication order |

Hidden or unrecorded events never create visible descendants. There is at
most one referral, one problem row, and one two-component lab order. The
`medications` tuple is always empty, including when a treatment event is
present. This intentional omission avoids implying a pharmacologic treatment
from a behavioral trajectory; a future reviewed treatment-program/referral
contract may add a different resource.

Healthy, GHD, and all other module kinds return four empty tuples. No row
contains an `obesity_flag`; that field remains separately derived from the
observed BMI-percentile trajectory and is not a synonym for latent
`EXCESS_WEIGHT`.

IDs are deterministic opaque synthetic tokens using an excess-weight-specific
namespace, for example
`excess-weight-ancillary-id-v1<unit-separator>{patient_id}<unit-separator>{role}`.
They are never copied from, hashed from, or matched to real identifiers.

## Exact-schema row contract

The supplied `ResourceShape` must contain the repository's six base resources.
Each emitted row has every descriptor field in exact order. Fields not listed
above use the existing empty-string missing convention, including lab
procedure metadata, LOINC, values, and nullable resolved dates. The module
does not accept descriptor paths, path-like objects, CSV readers, row inputs,
arbitrary field lists, reports, keys, or output destinations and does not edit
`datapackage.json`.

## Validation contract

The validator emits these fixed checks in order:

1. `pathway_scope` — module kind and empty/nonempty row expectations agree;
2. `row_schema` — resource names, field order, scalar types, fixed fictional
   values, opaque IDs, and empty conventions are valid;
3. `causal_timing` — event ages and delayed lab results are ordered;
4. `cross_resource_links` — patient and visible visit links resolve while
   problem rows retain nullable visit semantics; and
5. `source_evidence` — the observation frame and its source binding pass the
   existing observation validator.

`FAIL` represents a visible structural, value, timing, link, or scope
violation. `UNEVALUABLE` represents absent or malformed private evidence when
no visible row is independently invalid. Overall precedence is
`FAIL > UNEVALUABLE > PASS`. Reports expose only fixed check names, statuses,
and redacted reason codes. A missing hidden treatment event is not an error,
and no medication expectation is inferred from it.

## Determinism and boundary

Projection has no random draws, filesystem or package I/O, environment reads,
network calls, or governed imports. Repeating the same typed inputs produces
byte-equivalent mappings and never mutates the member, frame, shape, or policy.
Malformed typed input crosses one fixed redacted projection error boundary.
Static boundary tests must reject calibration, real-data, held-out, privacy,
DuckDB, CSV, filesystem, export, manifest, subprocess, and Synthea coupling.

## Testing and documentation

Tests use only checked-in fictional cohort fixtures and the descriptor mapping.
They cover healthy/GHD emptiness, every visible event combination, treatment
without medication, delayed results, same-age events, nullable problem links,
exact field order/types, deterministic namespace IDs, tampering and duplicate
rows, no mutation, redacted mappings/errors, and static boundaries. Focused
tests, full synthetic tests, Ruff, schema validation, whitespace checks, and
an independent broad review are required before merge.

`docs/synthetic-generator.md` documents the API and explicitly separates
latent `EXCESS_WEIGHT` from observed `obesity_flag`. `README.md` links to the
guide. This slice remains evaluator-only; package/export integration,
authoritative augmentation, prevalence calibration, held-out comparison,
privacy/non-matchability review, clinical review, and Synthea conformance are
deferred.

## Acceptance criteria

1. A valid excess-weight member deterministically produces only the fictional
   descendants permitted by recorded recognition, workup, and diagnosis;
   medications are always empty in this contract.
2. Non-target members produce four empty ancillary tuples without hidden-truth
   leakage, and no row writes or implies `obesity_flag`.
3. Every row follows the supplied descriptor's exact field order and missing
   value conventions.
4. Validation catches malformed IDs/codes/values, duplicates, wrong counts,
   reversed or undelayed lab results, broken links, and source-frame failures
   using fixed aggregate statuses with redacted output.
5. The module is deterministic, nonmutating, random-free, and free of
   filesystem, package, governed-data, manifest, and Synthea coupling.
6. Focused/full tests, static checks, schema/whitespace checks, and broad
   review pass before publication.
