# All-disorder coverage development profile design

**Date:** 2026-09-03  
**Status:** Design approved for implementation  
**Parent:** [Synthetic Pediatric Growth Fixture System Design](2026-08-30-synthetic-growth-fixtures-design.md)

## Purpose

The repository already contains deterministic trajectory modules and six
disorder-specific ancillary projections, but the opt-in `development-realistic`
package route composes only healthy and growth-hormone-deficiency (GHD)
members. This slice adds a separate `development-all-disorders` profile that
exercises every reviewed trajectory module and its available fictional
descendants while preserving the existing three profiles and the exact
eight-resource package schema. The result remains wholly generated and
development-only.

The profile is intended for trajectory coverage, joins, downstream feature
development, and counterfactual experiments. It is a fictional coverage
scenario, not a clinical simulator, a prevalence estimate, or evidence that
the generated profiles cannot be linked to a real patient.

## Scope and compatibility

The existing `development-smoke`, `development-cohort`, and
`development-realistic` profiles remain byte- and behavior-compatible. The new
profile is an explicit fourth CLI profile; the no-profile and unknown-profile
fail-closed behavior is unchanged. The generic observed-resource validator
continues to reject nonempty ancillary rows, and the existing GHD bundle API
continues to expose its original signatures and semantics.

The new route changes only the explicit all-disorder path. It does not add a
real-data reader, calibration-file reader, Synthea dependency, model, network
call, or new descriptor resource. It uses the already checked-in CDC reference,
source-matched development augmenter, and exact-schema exporter used by the
current realistic route.

## Scenario prior and demographics

The all-disorder route uses the same snapshot-shaped demographic weights as the
current realistic profile: the checked-in `schema/stats.json` snapshot
`2026-08-24`, source-missing ethnicity/race cells folded into visible
`Unknown`, F/M reference-compatible sampling, and zero U sampling because the
pinned CDC reference has no U series. Those demographic weights are orthogonal
to the latent coverage prior. No mutually exclusive subtype counts are
available in the snapshot: `growth_dx_flag`, `healthy_flag`, stunting,
wasting, underweight, obesity, and individual diagnosis-code counts are
overlapping observed marginals, not labels for these ten modules. The fixed
coverage prior is:

| Reference sex | healthy | each compatible nonhealthy module | Turner syndrome |
| --- | ---: | ---: | ---: |
| F | `1/2` | `1/18` for all nine nonhealthy kinds | `1/18` |
| M | `1/2` | `1/16` for the eight non-Turner kinds | `0` |

The F row sums to one across healthy plus nine nonhealthy kinds; the M row
sums to one across healthy plus eight compatible nonhealthy kinds. These are
fixed fictional coverage weights chosen to exercise every trajectory family,
not prevalence, incidence, diagnosis, or representativeness estimates. The
existing `development-realistic` profile retains its original healthy/GHD
prior (`214681/250588` and `35907/250588`) for users who need its
snapshot-shaped aggregate growth-diagnosis scenario.

The all-disorder profile uses the existing full age schedule, exact observation
policy, zero measurement error, and recognition/diagnosis recording at `1.0`.
Turner is reference-sex constrained: module selection applies the conditional
weight row for the sampled reference sex before the deterministic module draw.
Thus a male-reference member cannot be assigned Turner, while F/M demographic
weights remain intact. Existing callers without sex-constrained modules see
unchanged selection behavior.

The native cohort configuration gains one optional, validated
`module_weights_by_reference_sex` table. Its default is empty, preserving the
legacy flat `module_weights` behavior and `generate_native_cohort` signature.
When present, a sampled reference-sex key selects its canonical weight tuple
before the existing eligibility filter; the all-disorder profile binds the
exact F and M rows above and retains the flat tuple only as the kernel/module
registry superset. The U row is not sampled because its demographic weight is
zero.

## All-disorder ancillary contract

Add `synthetic.native.multidisorder_ancillary` as a pure in-memory adapter over
the existing typed projection modules. It defines:

- `MultidisorderAncillaryPolicy`, a frozen aggregate-safe policy with
  `policy_id`, `policy_version`, and nonnegative `result_delay_days`;
- `MultidisorderAncillaryProjection`, a frozen exact-shape wrapper containing
  only `patient_id`, `ResourceShape`, and the four ordered resource tuples
  `labs`, `medications`, `problem_list`, and `referrals`;
- `project_multidisorder_ancillary_resources(member, shape, policy)`, which
  dispatches by the already-generated trajectory kind to the matching reviewed
  projector; and
- `validate_multidisorder_ancillary_resources(member, projection, policy)`,
  which dispatches to the matching reviewed validator and exposes fixed
  aggregate statuses/checks without returning row values or latent kind/state.

Healthy, familial-short-stature, and constitutional-delay members have no
reviewed ancillary descendants and therefore return four empty tuples. The
other seven nonhealthy kinds dispatch to their existing projection and
validation modules. The adapter never accepts caller callables, arbitrary
terminology, row payloads, paths, or output destinations. It wraps malformed
inputs in the fixed redacted message `multidisorder ancillary projection
unavailable`.

Add `merge_multidisorder_ancillary_resources` and
`validate_multidisorder_ancillary_bundle` in the same module. The merge accepts
only an empty-ancillary `ObservedResourceBundle`, the matching immutable
projection, and the explicit policy; validates identity, descriptor shape,
source-frame binding, base resources, concrete pathway rows, and visit links;
then returns a fresh six-resource bundle. A second merge that would append
nonempty ancillary rows, or any failed validation, is rejected atomically with
`multidisorder ancillary bundle unavailable`; an empty projection for a member without a reviewed ancillary
pathway is the required immutable no-op and cannot carry a hidden merge marker.
Bundle reports use fixed aggregate checks in the order
`bundle_identity`, `base_resources`, `ancillary_resources`, `truth_boundary`
and the existing precedence `FAIL > UNEVALUABLE > PASS`. Public mappings and
`repr` contain no source frame, trajectory, hidden event, treatment state, row
identifier, or patient-level diagnostic.

The merged bundle is an in-memory serialization sidecar, as in the existing
GHD package path; it is not assigned back to `CohortMember.bundle`. That member
field retains its dependency-leaf GHD-only serializer contract, while the
all-disorder runtime passes the fresh merged bundle directly to the unchanged
visible-resource exporter.

The adapter uses each module's existing fictional constants and deterministic
ID namespace. It does not combine two disorder projections for one member,
invent a gestational-age resource, infer treatment from visible data, or alter
the generic empty-ancillary validator.

## Runtime and package route

Extend `development_runtime.py` with immutable builders:

- `development_all_disorders_calibration_profile()` returns the snapshot-shaped
  demographic weights with artifact identity `development-all-disorders-v1`;
- `development_all_disorders_config(patient_count, seed)` returns the
  fixed full-age observation policy and the ten scenario priors above;
- `build_development_all_disorders_cohort(...)` builds the cohort
  with all ten native modules; and
- `generate_development_all_disorders_cohort(...)` projects the
  typed bundles, merges the matching ancillary rows, converts every in-memory
  fictional lab marker `Synthetic` to the descriptor's empty-string sentinel,
  adds only the existing fixed `E23.0` token for GHD diagnosis visits, and
  sends the six visible resources through the unchanged exact-schema exporter.

The configuration hash must bind the new profile identity, all ten module
versions, the exact prior tuple, demographic weights, observation policy,
snapshot identity, and the all-disorder ancillary policy. The manifest profile
is `development-all-disorders`. No latent module name, severity,
trajectory, truth, or treatment state may enter package CSVs, descriptors,
manifests, validation reports, or public mappings.

Extend `synthetic.generate` with the new explicit profile and no other CLI
arguments. The existing realistic route continues to call only the GHD adapter;
the all-disorder route is the only caller of the multidisorder adapter.

## Testing

Tests must cover:

1. conditional prior key/order/sum identity, frozen profile/config values,
   deterministic equal-seed output, and changed-seed variation;
2. all ten module constructors and trajectory generation, including Turner
   filtering for non-F reference sex and at least one Turner member in a
   sufficiently large deterministic cohort;
3. projection dispatch for every kind, empty conventions for healthy/familial/
   constitutional members, concrete validator status propagation, exact row
   and field order, visit-link resolution, immutable nonmutation, duplicate
   merge rejection, and redacted malformed-input behavior;
4. the new CLI route's exact eight-resource inventory, schema fingerprint,
   deterministic synthetic identifiers, visible generic event descendants,
   per-pathway ancillary constants/row relationships, GHD-only `E23.0` and
   `growth_dx_flag` behavior, lab-marker serialization sentinel, and absence of
   latent/truth tokens; and
5. existing profile regression tests, boundary/import scans, Ruff, schema
   validation, whitespace checks, and a full pytest run.

Small focused tests may use a fixed patient count chosen to cover all modules;
the scheduled scale test may additionally run the new profile at `10000`
patients behind the existing `SYNTHETIC_RUN_SCALE=1` opt-in. No test may read
real CSV rows or assert disorder-specific clinical prevalence.

## Documentation

Add a concise profile section to `docs/synthetic-generator.md` with the exact
command, conditional prior table, demographic/snapshot source shape, Turner eligibility,
ancillary dispatch, visible serialization behavior, and non-claims. Update the
README's single synthetic-generator link paragraph with one roadmap link to the
new spec/plan; do not copy the guide into README. Existing GHD and
disorder-specific in-memory sections remain accurate for their original APIs,
while the new section states that the all-disorder profile is the only ordinary
package route that composes all reviewed ancillary projections.

## Acceptance criteria

1. The new explicit CLI profile produces deterministic, exact-schema packages
   containing trajectories and typed fictional descendants for every reviewed
   disorder kind at sufficient cohort size.
2. The existing three profiles, generic validator, exporter, and no-profile
   fail-closed contract remain unchanged.
3. Turner assignments respect reference-sex eligibility without changing the
   configured F/M demographic distribution.
4. All bundle/projection reports and exceptions are aggregate-only and redacted;
   no latent truth is exported.
5. Focused and full tests, Ruff, schema, whitespace, independent task reviews,
   and a broad review pass; the reviewed changes are merged to `main`, pushed,
   and verified at identical local/remote SHAs.

## Deferred work

This slice does not claim subtype prevalence, clinical validity, real-data
fidelity, privacy/non-matchability, release approval, or Synthea conformance.
Those are separate workflows and are not prerequisites for ordinary synthetic
development. The existing optional Synthea contract remains an alternative
future engine adapter, not a dependency of this native profile.
