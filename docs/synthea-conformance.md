# Optional Synthea engine-conformance declaration

**Status:** Optional, future, development-only handoff contract. The native growth-first generator remains the release-one route.

This guide documents aggregate review metadata for a possible external Synthea engine handoff. It implements no engine adapter or conformance runner. The declaration is fixed at `SYNTHEA_CONFORMANCE_VERSION = "synthea-conformance-v1"`, and every `SyntheaEngineManifest` uses `engine_id="synthea"`. A valid manifest is only a declaration of reviewed identities; it is never a conformance result.

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

## Current non-runtime boundary

This repository currently supplies none of the Synthea runtime, pinned module bundle, pediatric extension, event adapter, exact engine exporter, external license artifact, or conformance runner described above. There is no Synthea implementation, no Java runtime, no conformance result, no patient data, no network access, and no release authorization in this repository. A valid declaration cannot authorize execution and cannot imply Synthea conformance.

The manifest contract is not imported automatically by generation, export, or evaluator code. It does not read a checkout, run Java, download anything, generate patients, translate engine output, write PPOC packages, allocate prevalence, replace pediatric growth physiology, bind an authoritative derivation oracle, or change the production command. The production CLI remains fail closed with `No production growth reference or authoritative derivation oracle is configured`.

Even an externally reviewed declaration does not prove clinical validity, pediatric growth or demographic fidelity, prevalence, task utility, reproducibility, privacy or non-matchability, release readiness, or Synthea conformance. Each remains a separate governed evidence decision.
