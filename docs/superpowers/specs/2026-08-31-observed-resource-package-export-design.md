# Observed Resource Exact-Schema Package Export

**Date:** 2026-08-31  
**Status:** Approved next implementation slice under the synthetic growth-fixture design  
**Parent:** [Synthetic Pediatric Growth Fixture System Design](2026-08-30-synthetic-growth-fixtures-design.md)  
**Prerequisite:** [Evaluator-Only Observed Resource Contract](2026-08-31-observed-resource-contract-design.md)

## Purpose

The observed-resource contract currently stops at an immutable in-memory bundle
with six base-resource row sets. This slice adds the narrow bridge needed to
exercise an exact PPOC-schema package in development: it validates and merges
one or more fictional observed bundles, writes the six base resources using the
repository descriptor, invokes an explicitly injected derivation oracle for
`patients_augmented` and `visits_augmented`, validates all eight resources, and
atomically promotes a synthetic package with a descriptor, structural report,
and manifest.

The bridge is an offline package boundary, not a new clinical generator. It
does not create latent disorder labels, estimate prevalence, fit demographics,
invent ancillary-resource events, read real data, consume calibration or
held-out artifacts, run a privacy audit, or invoke Synthea. The only values
written to base rows come from the already validated fictional bundles. The
oracle sees only staged visible base CSVs and an in-memory descriptor; private
observation frames, truth hashes, stream identities, and bundle objects never
cross the package boundary.

## Public interfaces

`synthetic.package_export` exposes:

```python
@dataclass(frozen=True)
class PackageExportMetadata:
    profile: str
    seed: int
    reference_time: str
    reference_id: str
    software_revision: str
    configuration_sha256: str
    reference_sha256: str | None = None


def export_exact_schema_package(
    descriptor: Mapping[str, object],
    base_rows: Mapping[str, Iterable[Mapping[str, object]]],
    output: Path,
    *,
    metadata: PackageExportMetadata,
    derivation_oracle: DerivationOracle,
    trusted_derivation_fingerprint: str,
    trusted_derivation_test_only: bool,
) -> Path: ...


def export_observed_resource_package(
    bundles: Iterable[ObservedResourceBundle],
    descriptor: Mapping[str, object],
    output: Path,
    *,
    metadata: PackageExportMetadata,
    derivation_oracle: DerivationOracle,
    trusted_derivation_fingerprint: str,
    trusted_derivation_test_only: bool,
) -> Path: ...
```

`PackageExportMetadata` is immutable and strict: `profile`,
`reference_id`, `reference_time`, and `software_revision` are nonempty
single-line strings; `seed` is an integer but not a boolean; and both digest
fields, when present, are lowercase 64-character SHA-256 strings. The
configuration digest is required and cannot be all zeroes. The profile is the
manifest profile and is not a clinical or privacy status.

`PackageExportUnavailable` is a `DerivationUnavailable` subclass used for
fail-closed package, oracle, and output-validation errors. Errors raised before
the run directory is created never contain patient or visit identifiers. A
failure after creation archives only `{"status":"FAILED","reason":"observed
package export failed"}` through the existing run lifecycle; raw oracle,
filesystem, and row exceptions are never serialized or re-raised as public
messages.

## Descriptor and input contract

The descriptor argument is an already-loaded mapping. The exporter copies it
through JSON-compatible in-memory data and never accepts or opens a descriptor
path. It must have exactly the repository's eight resources and the checked-in
schema fingerprint
`795724ec4838df8afa9c09b7c059fa76f644d7f8fb6dcc8ce808da203c2f8597`.
The exporter rejects unknown/missing resources, changed field order, changed
paths, changed types/constraints, unsafe resource paths, and non-JSON mapping
values before creating output. The fingerprint is exposed as
`EXPECTED_SCHEMA_FINGERPRINT` by `synthetic.schema_contract` so the check is
centralized rather than duplicated as an unlabelled constant.

`base_rows` must contain exactly the six existing base resources in
`BASE_RESOURCES` order. Every row is materialized before output creation and
must be a mapping whose keys are exactly the descriptor field names in order;
missing fields, extra fields, non-finite numbers, or non-string/number values
fail closed. The exporter does not accept augmented rows from callers: those
files can be created only by the injected oracle. Empty ancillary rows remain
valid and have schema-correct headers.

`export_observed_resource_package` materializes the bundle iterable, requires at
least one bundle, and validates every bundle with
`validate_observed_resources`. Every report must be `PASS`; a non-PASS bundle
is rejected before output creation. All bundles must have the exact descriptor
shape, one unique synthetic patient ID, and globally unique synthetic visit
IDs. Bundles are sorted by synthetic patient ID before rows are merged, so
reordering the caller's iterable cannot change package bytes. The merged base
rows contain no private source-frame values and no evaluator-only descendants
outside their fixed fictional diagnosis slots.

## Export lifecycle

The exporter uses the existing `RunDirectory` lifecycle. It derives a stable
run token from the metadata seed, merged patient count, and reference time;
the target, sibling partial path, and sibling failed path must all be new. It
then:

1. validates the descriptor, metadata, oracle identity, trusted fingerprint,
   and all base rows before creating the run;
2. writes only the six base CSVs with `write_resource`, preserving descriptor
   field order, dialect, encoding, and empty-string missingness;
3. copies those six files into a private temporary staging directory and
   records their hashes;
4. calls `derivation_oracle.derive(staging, descriptor_mapping)` exactly once;
5. verifies the oracle returned a nonempty identity, the trusted fingerprint
   and test-only classification match, both descriptor-named augmented files
   exist as regular files, no unexpected staging entries exist, and every
   staged base hash is unchanged;
6. copies only the two augmented files into the partial run and rejects any
   base mutation, symlink, special file, extra file, or missing output;
7. validates all eight resources with `validate_structure`, writes the
   generated `x-synthetic` descriptor through `write_synthetic_descriptor`,
   and writes the aggregate structural `validation-report.json`;
8. writes a `RunManifest` with the supplied profile and metadata, row counts,
   trusted derivation fingerprint, and hashes for every package file except
   the manifest itself; and
9. promotes the partial directory with the existing no-replace rename.

The generated package contains exactly the eight descriptor-named CSVs plus
`datapackage.json`, `validation-report.json`, and `manifest.json`. No truth
manifest, evaluator report, source frame, calibration artifact, held-out
report, privacy report, or arbitrary extra file is exported. A test-only oracle
produces a structurally valid development package whose manifest status
identifies the test-only derivation; it is not a validated or release-approved
fixture.

## Existing smoke integration

`generate_smoke` continues to accept a descriptor path, injected growth
reference, and injected derivation oracle. Its patient/trajectory loop remains
unchanged, but it delegates the six-base-row package lifecycle to
`export_exact_schema_package`. The existing smoke profile, run-token shape,
manifest fields, test-only status, and fail-closed behavior remain compatible
with current tests. This avoids maintaining two subtly different staged-oracle
implementations.

The observed-resource bridge does not make the production CLI available: the
CLI still fails closed until an approved production reference and oracle are
configured. The new Python API is intended for development and evaluator
fixtures with explicit test-only dependencies.

## Determinism and privacy boundary

The exporter performs no random draws. Given equal descriptor bytes, metadata,
base rows, oracle implementation, and oracle configuration, the visible CSV,
descriptor, structural report, and manifest bytes are reproducible except for
the manifest's expected file hashes being derived from those same bytes. Bundle
iteration order is normalized by synthetic patient ID, and each bundle's rows
retain their validated age/event order.

The exporter never imports calibration, calibration-input, held-out, privacy,
real-data, or Synthea modules. Boundary tests scan the complete visible native
and exporter package for forbidden imports and calls, assert that no private
observation tokens occur in package files or reports, and verify that oracle
mutation and extra-artifact attempts fail closed. Structural validity and
deterministic bytes are not prevalence fidelity, clinical validity, privacy or
non-matchability evidence, task utility, release authorization, or Synthea
conformance.

## Acceptance criteria

The slice is complete when:

1. strict metadata, exact descriptor fingerprint, six-base-row input, and
   bundle cardinality/identity checks fail closed without identifier leakage;
2. one or more validated fictional bundles produce deterministic exact-schema
   eight-resource packages with descriptor-prescribed headers, encodings,
   missing values, and row relationships;
3. only an injected oracle can supply augmented resources, and oracle
   mutations, symlinks, missing outputs, extra artifacts, fingerprint
   mismatches, and test-only mismatches cannot promote a package;
4. existing smoke generation uses the shared lifecycle without changing its
   visible output contract or fail-closed CLI behavior;
5. generated descriptors, reports, manifests, and package files contain no
   private frame/truth values, source paths, identifiers beyond visible
   synthetic resource rows, or evaluator artifacts;
6. output collisions and failures follow the existing non-overwriting
   partial/failed lifecycle; and
7. focused tests, the complete suite, Ruff, schema validation, diff checks, a
   deterministic package smoke run, and a fresh broad review pass before merge.

