# Pair-Aware Exact-Schema Counterfactual Package Export

**Date:** 2026-08-31
**Status:** Implementation complete; synthetic/test-only pair export; authoritative derivation, privacy, and release evidence pending
**Parent:** [In-Memory Paired Counterfactual EHR-Worlds](2026-08-31-counterfactual-ehr-worlds-design.md)
**Prerequisite:** [Observed Resource Exact-Schema Package Export](2026-08-31-observed-resource-package-export-design.md)

## Purpose

The repository can now compose and validate one fictional paired
counterfactual into two in-memory exact-schema resource bundles, and it can
export one or more bundles through a tested exact-schema package lifecycle.
This slice connects those contracts without changing either one: it exports
the baseline and intervention worlds as two separately usable PPOC packages
inside one atomic pair envelope and records only aggregate pairing metadata.

Each child directory is an ordinary exact-schema synthetic package with the
same eight descriptor-named resources, generated descriptor, structural
report, and run manifest as the existing observed-resource exporter. The
parent output is an envelope, not a PPOC package: it contains `baseline/`,
`intervention/`, and `pair-manifest.json`. A caller can pass either child
directory to existing package readers and structural validators without
interpreting a new resource, world column, or schema extension.

This is a development/evaluator export seam for completely fictional input.
It does not create latent trajectories, tune prevalence or demographics,
derive clinical truth, fit observation error, validate clinical utility,
measure privacy, prove non-matchability, authorize release, or invoke
Synthea. Augmented resources remain owned by the explicitly injected
derivation oracle already required by the child exporter.

## Public interface

`synthetic.package_export` exposes one new function:

```python
def export_counterfactual_ehr_world_pair(
    worlds: CounterfactualEhrWorldPair,
    descriptor: Mapping[str, object],
    output: Path,
    *,
    metadata: PackageExportMetadata,
    derivation_oracle: DerivationOracle,
    derivation_binding: DerivationBinding,
) -> Path: ...
```

The function returns the promoted pair-envelope path. Its fixed child paths
are `output / "baseline"` and `output / "intervention"`. The caller supplies
one visible `PackageExportMetadata`; the same metadata is passed to both child
exports. The pair exporter never reads the hidden pair seed, patient index,
trajectory, frame truth, source objects, or stream identities to construct
public metadata. The package metadata seed is caller-owned provenance for the
export and must not be treated as hidden counterfactual truth.

`CounterfactualPackageExportUnavailable` is a fixed redacted
`PackageExportUnavailable` subclass. Invalid worlds, non-PASS aggregate
validation, descriptor/oracle failures, staging failures, and post-creation
validation failures are exposed only as
`counterfactual package export failed`. An existing target or deterministic
pair lifecycle sibling remains a `FileExistsError`, matching the existing
no-replace package contract; no identifier, path, row, oracle, or exception
text is echoed.

## Input and validation contract

1. The exporter first requires a new output path and a typed
   `CounterfactualEhrWorldPair`. It re-runs
   `validate_counterfactual_ehr_worlds(worlds)` and requires aggregate
   `PASS`; `FAIL` and `UNEVALUABLE` pairs never create a caller-visible target,
   partial path, failed path, or pair manifest.
2. It obtains only the two visible `ObservedResourceBundle` values from the
   pair. The aggregate world validator already re-runs the integrated GHD
   ancillary and isolated-base checks; the exporter then copies only the six
   visible resource-row mappings from each bundle for serialization. The
   in-memory GHD projection intentionally uses the evaluator marker
   `labs.result_flag="Synthetic"`, which is not a value in the unchanged real
   descriptor enum. Immediately before pair serialization, and only for a row
   whose `result_component_name` is one of the two GHD components and whose
   flag is exactly that evaluator marker, the pair exporter writes the
   descriptor's missing-value sentinel `""`. This is an explicit
   `ghd-result-flag-empty-v1` serialization projection, not a mutation or
   repair of the world; every other field and row is preserved, and any other
   enum-invalid flag is rejected. It deliberately does not call
   `export_observed_resource_package`, whose generic bundle validator rejects
   the nonempty GHD ancillary rows that this pair contract has already
   validated. The exact-schema child lifecycle still rejects malformed rows,
   checks the loaded eight-resource descriptor, and validates every written
   file. No pair object, source frame, truth object, trajectory, report, or
   evaluator reference crosses the oracle boundary.
3. The same descriptor mapping, metadata, trusted derivation fingerprint, and
   test-only classification are used for both child packages. The child
   exporter therefore owns all descriptor fingerprint, row-key, augmented
   output, structural validation, manifest, and no-replace checks; this layer
   does not duplicate or weaken them.

## Pair export lifecycle

The pair exporter is all-or-nothing at the public output boundary:

1. Validate the typed pair, aggregate report, output availability, and fixed
   input boundary before creating a public run directory.
2. In a private temporary directory, call `export_exact_schema_package`
   exactly once for the baseline bundle's six visible resource mappings and
   exactly once for the intervention bundle's six visible resource mappings.
   The two calls use the same caller-supplied metadata and oracle contract.
   Their package bytes are independent of the temporary directory name.
3. Start one top-level `RunDirectory` with a stable run token derived only
   from the visible export metadata and matrix version/intervention, never
   from patient identifiers or hidden trajectory values. Copy the two already
   promoted child packages into `baseline/` and `intervention/` beneath the
   top-level partial directory.
4. Write `pair-manifest.json` with canonical JSON containing only:

   - contract token `counterfactual-ehr-package-pair-v1`;
   - exact schema fingerprint;
   - matrix version and intervention token;
   - `serialization_projection` set to the fixed token
     `ghd-result-flag-empty-v1`;
   - aggregate world-validation status and fixed status counts;
   - the caller-supplied visible profile/reference/configuration/software
     metadata, excluding hidden pair context; and
   - relative child paths and each child `manifest.json` SHA-256 digest.

   It contains no patient or visit identifiers, row values, ages, latent
   states, event payloads, source frames, truth hashes, seeds/indexes,
   stream names/identities, descriptor contents, paths outside the envelope,
   oracle exceptions, or evaluator object representations.

5. Scan the top-level partial tree against the exact allowed inventory: the
   pair manifest, the two child directories, and each child's eight resource
   files plus `datapackage.json`, `validation-report.json`, and `manifest.json`.
   Reject symlinks, special files, missing files, extra files, and unexpected
   directories. Promote the top-level partial path with the existing
   no-replace rename.

If any step after top-level creation fails, archive the partial run through
the existing lifecycle using only `{"status":"FAILED","reason":"counterfactual
package export failed"}` as public failure content. The target is never
overwritten. Private child staging is removed by its temporary-directory
lifecycle and is never returned or copied into a failed public path.

## Determinism and child-package semantics

Given equal validated worlds, descriptor bytes, metadata, oracle
implementation/configuration, and trusted derivation contract, the baseline
child, intervention child, pair manifest, and all file bytes are reproducible
across fresh output locations. The envelope always uses the fixed child order
`baseline`, then `intervention`; it does not sort or resample the pair.

The child package manifests retain the existing package-export metadata and
structural row/file hashes. The pair manifest binds those manifests by hash
and identifies the causal matrix and fixed serialization projection, but it
does not claim that the two packages are clinically valid,
prevalence-calibrated, private, non-matchable, or release-ready. Visible
differences remain governed solely by the already validated resource-level
counterfactual matrix; the exporter performs no clinical repair, augmentation,
or broadening of permitted changes.

## Testing and boundary requirements

Tests use only fictional pairs and the existing test-only identity-preserving
derivation oracle. They must cover:

- valid export for the supported physiology, recognition, and treatment
  matrices, with each child passing `validate_structure` and containing the
  exact eleven package files;
- exact top-level inventory, fixed child paths, pair-manifest fields,
  manifest-digest binding, the explicit GHD serialization projection, and
  absence of hidden truth/evaluator tokens;
- deterministic byte equality across two fresh destinations and stable
  child ordering;
- exactly two oracle calls receiving child staging roots and no pair/hidden
  objects;
- rejection before public output creation for non-PASS/unevaluable worlds,
  malformed bundles, invalid descriptor/oracle metadata, and output/lifecycle
  collisions;
- redacted post-creation failure archival, no target overwrite, and no
  arbitrary child or pair artifacts;
- ordinary child packages remaining compatible with the existing structural
  validator and package-export boundary tests; source-world GHD evaluator
  markers remain unchanged while serialized child flags are blank and
  schema-valid; and
- recursive AST/import/public-signature checks preventing real/governed data,
  calibration, held-out, privacy, Synthea, model, network, or new filesystem
  readers from entering the pair API, while allowing the existing lifecycle
  helpers and in-memory world/bundle contracts.

Documentation must show the pair API, the two-child exact-schema layout, the
aggregate-only pair manifest, the explicit injected test oracle, and the
distinction between a child package and its non-package envelope. It must
retain the separate deferrals for prevalence/demographic calibration,
authoritative augmentation, temporal drift, task utility, clinical validity,
privacy/non-matchability, release approval, and Synthea conformance.

## Deferred work

This slice does not implement cohort-scale pair generation, package merging
of multiple patients, authoritative augmented derivation, prevalence or
demographic calibration, observation-error fitting, temporal drift, task
utility, clinical review, privacy auditing, non-matchability proof, release
approval, or a Synthea adapter. A Synthea route remains optional and must
conform to the native trajectory, observation, resource, pair-validation, and
child-package contracts before it can produce an accepted pair envelope.

## Acceptance criteria

1. A previously passing fictional `CounterfactualEhrWorldPair` produces one
   atomically promoted envelope with two independently valid exact-schema
   child packages and one safe pair manifest.
2. The pair exporter invokes the existing child lifecycle exactly twice and
   never passes hidden evaluator objects to the oracle or visible artifacts.
3. Pair validation, descriptor/schema, child structural, derivation, output
   inventory, no-replace, and redaction checks fail closed with fixed public
   behavior.
4. Fresh-destination exports are byte-identical and existing child package,
   CLI, generic validator, and schema contracts remain unchanged.
5. Focused tests, full pytest, Ruff, schema validation, diff checks, a
   deterministic two-destination export, and a fresh broad review pass before
   merge; the reviewed branch is merged to `main`, pushed, and verified with
   `HEAD == origin/main`.
