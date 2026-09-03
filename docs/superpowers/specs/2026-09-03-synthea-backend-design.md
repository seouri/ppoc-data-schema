# Synthea development backend design

**Date:** 2026-09-03
**Status:** Implemented opt-in development backend; external runtime and conformance evidence remain separate
**Parent contracts:** [synthetic pediatric growth fixture design](2026-08-30-synthetic-growth-fixtures-design.md), [Synthea manifest design](2026-09-01-synthea-conformance-contract-design.md)

## Purpose

Complete the optional Synthea-dependent development path without making Synthea, Java, or a JVM build a requirement for ordinary fixture generation. The backend accepts a caller-supplied, externally pinned Synthea checkout, generates completely fictional pediatric records, maps the FHIR R4 output into the engine-neutral PPOC base-resource contract, and delegates augmented resources to the existing development derivation oracle. Growth is the primary signal: Synthea's pediatric measurements provide the healthy trajectory, while a versioned growth overlay creates a reproducible GHD contrast and preserves height/weight/BMI identities before export.

This is a development bridge and engine-comparison implementation. It is not a clinical Synthea module release, a prevalence calibration, a privacy/non-matchability proof, or production authority. The existing native profiles and fail-closed default CLI remain behaviorally unchanged.

## Scope

The first executable backend slice supports:

1. Synthea revision `d9d07a6eef91ee5144293b42ab64224d84d124f8`, Java 17, and the checked-in Gradle wrapper 9.2.1.
2. A versioned local Generic Module Framework module that samples a fictional GHD event with fixed development prior `0.143291`, records an ICD-10-CM-compatible `E23.0` condition and an evaluation encounter, and never reads real diagnosis input.
3. Pediatric ages `0-18` generated to a fixed reference date. The engine's ordinary lifecycle supplies dense, correlated healthy height and weight measurements; the adapter retains only FHIR observations with anthropometry.
4. A deterministic post-export growth overlay (`synthea-growth-overlay-v1`) that identifies GHD from the versioned module event, gradually reduces stature from the healthy trajectory, scales weight to preserve BMI continuity, and recomputes BMI. Overlay parameters are fixed, bounded, and recorded in the configuration digest; hidden disorder state is not exported.
5. FHIR R4 parsing for `Patient`, `Encounter`, `Observation`, and `Condition` resources. The parser emits descriptor-shaped `patients`, `visits`, and empty ancillary base rows; diagnoses are placed in the nearest eligible visit without preserving Synthea identifiers.
6. Exact eight-resource package export through `export_exact_schema_package` and the existing test-only source-matched augmenter. The Synthea package manifest identifies `engine="synthea"`; native manifests continue to identify `engine="native"`.
7. An aggregate-only `SyntheaBackendReport` returned in memory, containing counts, revision/overlay/configuration digests, and trajectory summary metrics. It contains no paths, names, engine output identifiers, patient or visit IDs, raw FHIR, rows, hidden truth, or subprocess output.

The backend is opt-in. It is exposed by `scripts/synthea_backend.py` and a dedicated command, not by `synthetic.generate`'s ordinary profile selector. The native development profiles remain the one-command route for ordinary synthetic development.

## Non-goals and explicit limits

- No Synthea source, Java runtime, Gradle distribution, generated FHIR, or output package is vendored in this repository.
- No caller checkout is modified. The runner copies only the pinned source tree into a private temporary build root, rejects symlinks and tracked modifications, and applies the local module overlay there.
- No network is requested by the adapter itself. Gradle is run offline by default; an explicit `--allow-gradle-network` opt-in is required when a caller has not populated the dependency cache.
- The first slice does not claim parity with the native ten-disorder model. GHD and healthy trajectories are the reviewed comparison pair; other native disorder kinds remain a separate roadmap slice.
- The growth overlay is intentionally an adapter-layer extension rather than a claim that the upstream `LifecycleModule` was replaced. A future in-engine Java physiology extension may supersede it, but must satisfy the same engine-neutral tests.
- Synthea's names, addresses, UUIDs, claims, and unrelated clinical history are discarded. They are never copied into PPOC rows or aggregate reports.
- The backend does not accept real-data roots, governed calibration/held-out inputs, patient profiles, arbitrary module files, network URLs, diagnosis payloads, or caller-supplied hidden truth.

## External checkout and toolchain contract

The runner requires a `Path` to a checkout and verifies, before creating a work root:

- `git rev-parse HEAD` equals the pinned revision above;
- tracked working-tree and index diffs are empty (untracked build/output files are ignored);
- the checkout has `gradlew`, `build.gradle`, and `gradle/wrapper/gradle-wrapper.properties` as regular files;
- `build.gradle` declares Java source compatibility 17; and
- the wrapper distribution is exactly Gradle 9.2.1.

The caller must supply `JAVA_HOME` or `--java-home`. The selected `java -version` must report major version 17. Java 26, an implicit system Java, and a missing/ambiguous `JAVA_HOME` fail closed. The runner never changes the caller's shell environment.

The private work root excludes `.git`, `.gradle`, `build`, and `output`. Every copied source entry must be a regular file or directory; symlinks, special files, path traversal, and copy races fail with the fixed public error `synthea backend unavailable`. The module directory is copied from the repository's versioned overlay and its canonical file digest is included in the run configuration.

## Synthea invocation

The runner invokes the checked-in wrapper with argument arrays and `shell=False`:

```text
./gradlew --no-daemon --offline -Dorg.gradle.vfs.watch=false run \
  --args="-s SEED -p N -a 0-18 -r YYYYMMDD -d OVERLAY \
          --exporter.fhir.export=true --exporter.fhir.transaction_bundle=false \
          --exporter.baseDirectory=FHIR_OUTPUT/"
```

`--allow-gradle-network` only removes `--offline`; it does not add arbitrary URLs or pass through unchecked arguments. The runner sets a finite timeout, captures output privately, and discards it on both success and failure. Synthea must produce at least one patient bundle per requested member and no patient bundle may contain a non-pediatric birth age relative to the run reference date.

## Versioned module and growth overlay

`scripts/synthea/overlay/modules/ppoc_growth_disorder.json` is the only module accepted by this slice. Its transition graph is deliberately small: fixed prior, one delay, condition onset, ambulatory evaluation encounter, two fictional laboratory observations, encounter end, and terminal state. The module uses `E23.0` only as a fictional development token consumed by the existing augmenter; it does not assert a clinical code-system mapping or prevalence claim. The parser recognizes the token only in output produced by this pinned overlay.

The Python overlay operates on typed parsed observations, never raw JSON. For each GHD patient and age `a` days, it applies:

```text
severity = 0.10 + 0.06 * deterministic_unit_interval(seed, patient_index, "growth")
factor(a) = 1 - severity * min(1, max(0, (a - 365) / 5114))
height_cm' = height_cm * factor(a)
weight_kg' = weight_kg * factor(a)^2
bmi' = weight_kg' / (height_cm' / 100)^2
```

Values are finite, positive, and rounded only when serialized through the descriptor contract. The overlay is continuous at one year, monotone in its attenuation, and leaves healthy observations unchanged. A parser/overlay test uses hand-built FHIR resources to verify both groups, monotonicity, identity, and deterministic repeated runs.

## FHIR-to-PPOC projection

The parser reads only UTF-8 JSON files below the private FHIR output root. It supports both one-bundle-per-patient JSON and a transaction bundle. It rejects duplicate keys, nonfinite numbers, unsupported resource shapes, missing Patient identity/birth date, impossible dates, and observations with nonfinite or nonpositive anthropometric values.

For each patient, FHIR `gender` maps to `F/M/U`; US Core race and ethnicity extension text maps to the descriptor enum, with absent or unsupported values projected to `Unknown`. Up to eight race slots are populated; all remaining slots are `Unknown`. Patient IDs are `synthetic_id(seed, "synthea-patient", sorted_index)` and visit IDs are `synthetic_id(seed, "synthea-visit", stable_patient_index * 100000 + visit_index)`. Synthea IDs and generated names are lookup-only and never leave the parser.

An eligible visit is an encounter/date group containing height, weight, BMI, or head-circumference observations. Height is LOINC `8302-2`, weight `29463-7`, BMI `39156-5`, and head circumference `9843-4`; code matching is exact and system-independent because the parser consumes only the pinned module/exporter output. Missing BMI is derived from height and weight at age 730 days or older. The base row uses inches, ounces, centimeters, and the schema's uppercase `BMI` field, with `orig_enc_source_Epic_yn="N"` and `encounter_type="Office Visit"`.

Conditions are normalized to their code text and associated with the referenced encounter when present. Otherwise, a condition is assigned to the first anthropometric visit on or after its onset date, or the final eligible visit when the onset is after observation end. At most 33 diagnosis slots are populated in stable code order. Ancillary resources remain empty in this slice; the existing augmenter derives both augmented resources from the base rows.

The report's `healthy_count` is the non-GHD trajectory group: it means no fictional `E23.0` event or growth attenuation was applied, not that unrelated synthetic Synthea conditions were removed. Those unrelated synthetic diagnosis codes may remain in visit slots; Synthea labs, medications, problem-list entries, and referrals remain empty in this first adapter slice.

## Package, manifest, and report boundary

The backend calls the exact-schema exporter with `PackageExportMetadata(engine="synthea", profile="synthea-development", ...)`. Its configuration hash covers the pinned engine revision, wrapper version, Java major, module digest, growth overlay digest, seed, patient count, reference date, and parser contract version. The package's generated descriptor remains governance-stripped and retains the exact schema fingerprint. The existing test-only derivation binding remains required; a Synthea run never promotes the source-matched oracle to non-test authority.

`SyntheaBackendReport` is returned only to the caller. It has fixed aggregate fields: report version, engine revision, module/overlay/configuration digests, requested/generated patient counts, healthy/GHD counts, visit and anthropometry counts, mean/min/max observed age, and a status. It serializes canonical sorted JSON for tests but is not written into the eight-resource package. No report field may contain a path, row, identifier, patient-level value, raw FHIR, command line, or subprocess text.

## Failure behavior

All toolchain, checkout, overlay, subprocess, FHIR, parser, package, and validation failures are redacted to `synthea backend unavailable`. Existing output roots are rejected before execution and are never overwritten. A failed run leaves no promoted package; the exporter may retain only its existing fixed failure archive. Invalid Java, revision, module digest, unsupported FHIR, missing anthropometry, wrong patient count, and failed exact-schema/augmentation validation are all ordinary backend failures, not partial success.

The command exits zero only after the package is promoted and its manifest/validation report pass. It prints the package path and aggregate report only after success; neither output contains patient identifiers or raw engine output. The backend never changes the default/no-profile failure text of `synthetic.generate`.

## Verification plan

1. Unit tests cover strict toolchain/revision checks, safe checkout copying, Java-major rejection, module digest stability, FHIR parser shape/date/code handling, demographic projection, overlay invariants, identifier non-reuse, and report aggregate-only serialization.
2. Adapter integration tests use a tiny fake Synthea checkout and a fake wrapper executable to exercise command construction, failure redaction, no-overwrite behavior, and deterministic mapping without Java or network access.
3. An opt-in pinned-checkout smoke test runs one or two pediatric Synthea patients under Java 17 when the checkout and offline Gradle cache are available. It asserts both the FHIR parser and exact eight-resource exporter; it is skipped when the external prerequisite is absent.
4. A development comparison test runs native and Synthea routes against shared engine-neutral growth contracts: healthy continuity, GHD attenuation, measurement identity, exact schema, deterministic reruns, and aggregate group counts. It does not demand identical patient records or use engine agreement as truth.
5. Existing native, augmenter, privacy, governance, and fail-closed CLI suites run unchanged. Documentation tests are updated to distinguish the implemented external adapter from the still-unvendored runtime and from optional clinical/release evidence.

## Acceptance criteria

- A pinned, Java-17, opt-in Synthea checkout can generate a deterministic exact-schema package without modifying the checkout or accepting real data.
- The package contains healthy and GHD longitudinal anthropometry, with GHD prevalence shaped by the fixed fictional prior and a monotone, BMI-consistent growth overlay.
- The parser and exporter discard Synthea identifiers/names and generate fresh IDs; repeated same-seed runs have identical non-manifest file hashes while different seeds differ.
- The package manifest identifies `engine="synthea"`, remains `test_only_derivation=true`, and contains no hidden state or patient-level diagnostics.
- The default/native CLI remains unchanged and fail-closed without an explicit development profile.
- Documentation states exactly what this backend does and does not establish; clinical, population, privacy/non-matchability, held-out, and release decisions remain separate gates.
