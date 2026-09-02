# Native GHD Ancillary-to-Bundle Integration Contract

**Date:** 2026-08-31
**Status:** Implementation complete; evaluator-only in-memory composition consumed by the opt-in realistic development package; paired-package, clinical, privacy, and release gates pending
**Parent:** [Synthetic Pediatric Growth Fixture System Design](2026-08-30-synthetic-growth-fixtures-design.md)

## Purpose

The native observation/resource layer currently creates an immutable six-resource
`ObservedResourceBundle`, but its four ancillary resources are deliberately empty.
The reviewed GHD pathway already produces exact-schema ancillary rows and an
aggregate validator. This slice composes those rows with a previously validated
base bundle so development and future counterfactual orchestration can operate
on one coherent in-memory EHR-world object. The explicit
`development-realistic` runtime now consumes that object, validates it, and
passes its six-resource rows to the existing exact-schema exporter; this module
itself remains a pure in-memory seam.

This is a synthetic-only evaluator contract. It does not add a package writer,
augmented derivation, prevalence evidence, clinical terminology, real-label
evaluation, privacy/non-matchability proof, or a Synthea implementation.

## Design choice and alternatives

The recommended route is a small engine-neutral composition module,
`synthetic.native.ancillary_bundle`. It returns the existing immutable
`ObservedResourceBundle` type rather than introducing a second row schema or
changing the package exporter. A merge is permitted only from a base bundle
whose ancillary tuples are empty, an exact `AncillaryResourceProjection`, and an
explicit `GhdAncillaryPolicy`. The merge validates both inputs before creating
a new bundle and never mutates the source bundle or projection.

The module also provides a full-bundle aggregate validator. It validates the
base rows using the established resource validator after isolating the four
ancillary tuples, then validates the extracted ancillary projection with the
existing GHD pathway validator. This keeps the established
`validate_observed_resources` empty-ancillary contract unchanged while giving
callers one fixed report for a merged bundle.

Directly changing the base validator to accept arbitrary ancillary rows is
rejected: it would make untyped rows appear valid and would couple the generic
resource contract to one disorder pathway. The generic observed-bundle export
path therefore remains empty-ancillary, while the explicit
`development-realistic` route is a narrow exception: it calls this merge,
serializes the fictional lab marker as the descriptor's empty-string sentinel,
and then uses the existing exact-schema exporter and source-matched augmenter.
Paired-world package export, non-target profiles, and authoritative derivation
remain deferred. A Synthea module remains an optional later adapter and is not a
replacement for this native contract.

## Public API

Create `src/synthetic/native/ancillary_bundle.py` with:

- `AncillaryBundleValidationStatus` — fixed `PASS`, `FAIL`, and `UNEVALUABLE`
  values with `FAIL > UNEVALUABLE > PASS` aggregation.
- `AncillaryBundleCheck` and `AncillaryBundleValidationReport` — immutable,
  fixed-order, aggregate-only checks and mappings. Reports contain statuses,
  counts, and fixed reason codes only.
- `merge_ghd_ancillary_resources(bundle, member, projection, policy)` — returns
  a new `ObservedResourceBundle` after validating the base bundle, member/frame
  binding, projection shape/patient identity, and GHD ancillary report.
- `validate_ghd_ancillary_bundle(bundle, member, policy)` — validates one merged
  or empty-ancillary bundle without returning row payloads or private evidence.

The public functions accept only typed in-memory values. They accept no
descriptor or filesystem path, CSV reader, row input, output destination,
calibration/held-out/privacy report, key, model, callable, or Synthea object.
Malformed typed inputs cross a fixed redacted exception/report boundary and do
not echo identifiers, ages, values, source objects, paths, or truth terms.

## Merge semantics

1. `bundle` must be an `ObservedResourceBundle` produced from the same fictional
   member frame and shape. Its `patients`, `visits`, clinical descendants, and
   private source frame must pass the existing resource validator when the four
   ancillary tuples are isolated.
2. `projection` must be an `AncillaryResourceProjection` with the same patient
   and exact shape. `validate_ghd_ancillary_resources(member, projection, policy)`
   must return `PASS`.
3. Every existing `labs`, `medications`, `problem_list`, and `referrals` tuple
   in the base bundle must be empty. The function never silently overwrites a
   prior projection.
4. The returned bundle preserves the base rows and clinical descendants by
   value, replaces only those four tuples with the projection rows, and retains
   the same private source frame. The result is a fresh frozen bundle whose
   ordinary mapping remains visible rows only; source truth stays evaluator
   private.
5. Empty projections are valid for healthy, non-GHD, or unrecognized members.
   The merge does not allocate rows, draw randomness, alter event schedules, or
   infer latent disease from recorded outcomes.

The merge re-runs the validators internally; a caller-supplied prior report is
never trusted because typed values can be mutated after a report was produced.
The member and bundle source frame must be the same object, the base patient row
must equal the member demographics, and every ancillary `visit_id` must resolve
to a visible base visit. A malformed or non-passing input fails atomically with
one fixed redacted integration exception. A second merge into an already
enriched bundle is rejected rather than overwritten.

## Full-bundle validation

`validate_ghd_ancillary_bundle` returns exactly these checks in order:

1. `bundle_identity` — typed bundle/member patient and shape/frame binding;
2. `base_resources` — established patient, visit, measurement, and descendant
   checks on the isolated base rows;
3. `ancillary_resources` — exact descriptor field order, row types, pathway
   values, causal timing, nullable links, and source evidence from the existing
   GHD validator; and
4. `truth_boundary` — ordinary serialization and representation contain no
   private source frame, latent trajectory, hidden event, or truth payload.

The base-resource check is performed against a fresh base view whose ancillary
tuples are empty; the ancillary check is performed against a fresh projection
view extracted from the merged rows. The generic
`validate_observed_resources` function therefore continues to reject nonempty
ancillary rows, and the smoke/cohort/generic observed-bundle paths remain
unchanged and continue to accept only legacy base bundles. The target-shaped
runtime is the explicit integration caller and uses `export_exact_schema_package`
after this typed validation rather than widening the generic validator.

`FAIL` means a typed row, shape, identity, causal, link, or boundary violation.
`UNEVALUABLE` means required private source evidence is absent or malformed and
no visible violation is independently demonstrable. The report never includes
patient or visit IDs, row IDs, ages, codes, measurements, trajectory state,
policy internals, hashes, paths, or source values.

## Determinism and boundaries

Merging and validating are pure, deterministic, and random-free. The module may
import only standard-library helpers plus the existing cohort, ancillary,
observation, and resource value contracts. Static tests must reject governed
calibration, real-data, held-out, privacy, DuckDB, filesystem, CSV,
package-export, manifest, model-training, and Synthea imports/calls. No CLI,
descriptor mutation, package write, or authoritative augmented resource is
added.

## Testing and documentation

Focused tests cover valid GHD/healthy/non-GHD merges, exact six-resource key and
field order, immutable nonmutation, same-shape/patient checks, duplicate merge
rejection, all ancillary causal/link failures, empty projections, malformed
private evidence, aggregate-only reports, mapping/repr redaction, and static
boundaries. Existing base-bundle tests must remain unchanged and continue to
assert that generic `validate_observed_resources` rejects nonempty ancillary
rows. Full pytest, Ruff, schema, whitespace, and broad review are required.

`README.md` and `docs/synthetic-generator.md` will describe this as an
evaluator-only in-memory composition seam used by the explicit
`development-realistic` ordinary package route and available for future
counterfactual worlds. They will explicitly defer paired package-level export,
authoritative derivation, prevalence/demographic calibration, held-out
validation, privacy or non-matchability evidence, clinical review, task utility
claims, other disorder pathways, release approval, and Synthea conformance.

## Acceptance criteria

1. A passing GHD projection merges into a passing immutable
   `ObservedResourceBundle` with all six resources in descriptor order.
2. Healthy/non-GHD/unrecognized members merge with four empty ancillary tuples
   and do not expose hidden treatment or latent labels.
3. Merge rejects nonempty base ancillary rows, patient/shape/frame mismatches,
   invalid projections, and failed base or pathway validation with fixed
   redacted errors.
4. Full-bundle validation catches malformed rows, broken links, causal timing,
   source-evidence, identity, and truth-boundary violations using only fixed
   aggregate statuses/reasons.
5. No public API, mapping, repr, exception, CLI, file, package, or manifest
   contains evaluator-held truth; no real-data or governed dependency is added.
