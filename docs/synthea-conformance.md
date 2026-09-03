# Optional Synthea engine-conformance declaration

**Status:** The declaration remains optional and development-only. An external-checkout Synthea development adapter is now implemented separately; the native growth-first generator remains the release-one route, and this declaration is still not a conformance result.

This guide documents aggregate review metadata for a possible external Synthea engine handoff. The executable development bridge is documented in [the Synthea backend guide](synthea-backend.md); this declaration remains independent of that bridge and implements no conformance runner. The declaration is fixed at `SYNTHEA_CONFORMANCE_VERSION = "synthea-conformance-v1"`, and every `SyntheaEngineManifest` uses `engine_id="synthea"`. A valid manifest is only a declaration of reviewed identities; it is never a conformance result.

## Aggregate manifest identities

The manifest accepts exactly these identities and review fields:

| Field | Declaration meaning |
| --- | --- |
| `manifest_version` | Fixed declaration contract version. |
| `engine_id` | Fixed engine family identifier. |
| `engine_revision` | Externally pinned engine revision identity. |
| `engine_sha256` | Digest of that pinned engine revision. |
| `module_manifest_sha256` | Digest of the versioned disease-module bundle manifest. |
| `growth_extension_id` | Pediatric growth-extension identity. |
| `growth_extension_sha256` | Digest of the pediatric growth extension. |
| `event_adapter_id` | Engine-neutral event-adapter identity. |
| `event_adapter_sha256` | Digest of the event adapter. |
| `ppoc_exporter_id` | Exact PPOC-schema exporter identity. |
| `ppoc_exporter_sha256` | Digest of the exact PPOC exporter. |
| `configuration_sha256` | Digest of the reviewed engine configuration. |
| `license_notice_id` | Aggregate identity of the reviewed license and attribution notice. |
| `review_status` | Declaration review state, never an execution or conformance result. |
| `test_only` | Whether the declaration is restricted to fictional test use. |

These are aggregate identities only. They contain no paths, network locations, patient or visit identifiers, rows, clinical values, event traces, hidden truth, keys, or arbitrary review prose. Repository fixtures must remain `review_status="PENDING"` and `test_only=True`; changing either field cannot promote a fixture, authorize execution, or establish evidence.

## Fictional review-metadata example

This copy-pasteable example uses fictional aggregate identities and serializes the declaration only as review metadata:

```python
from synthetic.synthea_conformance import (
    SYNTHEA_CONFORMANCE_VERSION,
    SyntheaEngineManifest,
)

manifest = SyntheaEngineManifest(
    manifest_version=SYNTHEA_CONFORMANCE_VERSION,
    engine_id="synthea",
    engine_revision="revision-20260901",
    engine_sha256="a" * 64,
    module_manifest_sha256="b" * 64,
    growth_extension_id="growth-extension-v1",
    growth_extension_sha256="c" * 64,
    event_adapter_id="event-adapter-v1",
    event_adapter_sha256="d" * 64,
    ppoc_exporter_id="ppoc-exporter-v1",
    ppoc_exporter_sha256="e" * 64,
    configuration_sha256="f" * 64,
    license_notice_id="apache-notice-v1",
    review_status="PENDING",
    test_only=True,
)

review_metadata = manifest.to_json_bytes()
```

`review_metadata` is canonical declaration metadata for review. It is not a command, package, patient record, engine output, validation report, or promotion artifact.

## External handoff prerequisites

A future runner must be supplied and reviewed outside this repository. Before any engine evaluation, that handoff must provide an externally pinned engine revision and digest, a versioned disease-module bundle, a custom pediatric growth extension, an engine-neutral event adapter, an exact PPOC exporter, a pinned configuration, a license/attribution review, and a matching approved non-test derivation binding. It must then pass all existing validation, counterfactual, task utility, reproducibility, privacy, clinical review, and release gates. The declaration satisfies none of those prerequisites by itself.

The engine-neutral growth and derivation boundaries remain authoritative. See the [parent synthetic growth-fixture design](superpowers/specs/2026-08-30-synthetic-growth-fixtures-design.md), the [synthetic generator and derivation-binding guide](synthetic-generator.md), and the [source-matched augmenter guide](augment-import.md). The approved declaration details are in the [optional Synthea manifest design](superpowers/specs/2026-09-01-synthea-conformance-contract-design.md).

## Implemented external development adapter

The repository now includes an opt-in adapter at `scripts/synthea_backend.py` and a versioned local overlay at `scripts/synthea/overlay/`. It accepts only a caller-supplied checkout at revision `d9d07a6eef91ee5144293b42ab64224d84d124f8`, verifies Java 17 and the checked-in Gradle 9.2.1 wrapper, copies the checkout into a private temporary root, runs a fixed pediatric FHIR export, projects healthy and fictional GHD growth trajectories into the exact PPOC schema, and delegates augmentation to the existing test-only binding. It never vendors or modifies Synthea, accepts real inputs, or exposes names, UUIDs, raw FHIR, hidden truth, or subprocess output.

Use the [Synthea backend guide](synthea-backend.md) for prerequisites and the one explicit command. A successful package manifest identifies `engine="synthea"` and `test_only_derivation=true`; the backend's in-memory report is aggregate-only. The implementation is development and engine-comparison infrastructure, not evidence that the Synthea declaration is conformant, that the fixed GHD prior matches real prevalence, or that generated profiles are non-matchable.

## Local Java/Gradle compatibility preflight

This repository does not vendor Synthea or execute it during ordinary generation. On 2026-09-03, a temporary checkout of the pinned Synthea revision `d9d07a6eef91ee5144293b42ab64224d84d124f8` was used for the external adapter and environment preflight. That revision declares Java source compatibility `17` and its checked-in Gradle wrapper is `9.2.1`.

The conservative local runtime is Homebrew `openjdk@17` `17.0.20.1`, selected explicitly without changing the system-default OpenJDK 26. Homebrew Gradle `9.7.1` is also installed, but it does not replace the Synthea wrapper: `./gradlew` continues to use the checked-in Gradle `9.2.1` distribution.

| Environment and command | Result | Meaning |
| --- | --- | --- |
| OpenJDK 26 + Synthea `./gradlew test` | Fails before compilation with `Unsupported class file major version 70` | The pinned Gradle wrapper is not compatible with Java 26. |
| OpenJDK 26 + Homebrew Gradle 9.7.1 | Main and test sources compile; the full test executor exits `134` | A newer Gradle removes the wrapper failure but does not resolve the separate test-process abort. |
| OpenJDK 17 + Synthea `./gradlew test` | Main and test sources compile; the full test executor still exits `134` | The exit `134` is independent of the Java 17 versus Java 26 choice and remains an open test-environment issue. |
| OpenJDK 17 + `./gradlew test --tests org.mitre.synthea.engine.GeneratorTest` | Passes | A focused Synthea test runs on the stable path. |
| OpenJDK 17 + `./run_synthea -p 1` | Passes and writes FHIR JSON | Basic patient generation works on the stable path. |

For the pinned Synthea workflow, select Java 17 explicitly and use a writable Gradle cache:

```sh
export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
export PATH="$JAVA_HOME/bin:$PATH"
export GRADLE_USER_HOME=/tmp/synthea-gradle-home
./gradlew test
./run_synthea -p 1
```

The cache path is an environment workaround, not a Synthea requirement; the preflight used it because this machine's default Gradle cache had a native-library/lock-file problem. Java 17 is the recommended reproducible choice for the pinned wrapper. Java 26 should not be treated as supported until the wrapper is upgraded to a Java-26-compatible Gradle version and the full test-process abort is resolved. These checks are an engineering preflight only, not Synthea conformance evidence.

## Current non-runtime boundary

This repository supplies the Python external adapter and the versioned fictional module overlay, but it does not supply the Synthea runtime, Java runtime, Gradle distribution, generated FHIR, external license artifact, or conformance runner described above. There is no Synthea implementation vendored in the repository, no Java runtime vendored in the repository, no conformance result, no patient data, no network access, and no release authorization in this repository. The adapter requires the caller to provide and verify the pinned checkout and Java 17 environment; a local workstation may have Java installed for that external run, but it does not change this repository boundary. A valid declaration cannot authorize execution and cannot imply Synthea conformance.

The declaration manifest contract is not imported automatically by generation, export, or evaluator code. The separate adapter reads only its caller-supplied pinned checkout, runs Java through the checked-in wrapper, translates the resulting fictional FHIR into exact-schema rows, and uses the existing test-only derivation binding; it does not download anything by default, accept real data, allocate validated prevalence, replace native growth physiology, bind an authoritative derivation oracle, or change the production command. The production CLI remains fail closed with `No production growth reference or authoritative derivation oracle is configured`.

Even an externally reviewed declaration does not prove clinical validity, pediatric growth or demographic fidelity, prevalence, task utility, reproducibility, privacy or non-matchability, release readiness, or Synthea conformance. Each remains a separate governed evidence decision.
