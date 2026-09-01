# Optional Synthea Engine-Conformance Manifest Design

**Date:** 2026-09-01
**Status:** Approved optional, development-only roadmap slice
**Prerequisites:** the engine-neutral synthetic growth contracts, exact-schema package exporter, derivation binding, and native validation gates

## Purpose

The repository's native growth-first engine remains the release-one route, and
no Synthea checkout or Java runtime is present in this repository. The parent
design permits Synthea as an optional interoperability and engine-comparison
route, but only after the same growth, observation, derivation, longitudinal,
counterfactual, task-utility, reproducibility, privacy, and release gates.
This slice defines a strict aggregate-only manifest for a future pinned Synthea
engine without importing, executing, or vendoring Synthea. It makes the future
handoff auditable while keeping the current generator unchanged and fail
closed.

## Public interface

Add `synthetic.synthea_conformance` with:

```python
SYNTHEA_CONFORMANCE_VERSION = "synthea-conformance-v1"

@dataclass(frozen=True)
class SyntheaEngineManifest:
    manifest_version: str
    engine_id: str
    engine_revision: str
    engine_sha256: str
    module_manifest_sha256: str
    growth_extension_id: str
    growth_extension_sha256: str
    event_adapter_id: str
    event_adapter_sha256: str
    ppoc_exporter_id: str
    ppoc_exporter_sha256: str
    configuration_sha256: str
    license_notice_id: str
    review_status: str
    test_only: bool

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "SyntheaEngineManifest": ...
    @classmethod
    def from_json_bytes(cls, value: bytes) -> "SyntheaEngineManifest": ...
    def to_mapping(self) -> dict[str, object]: ...
    def to_json_bytes(self) -> bytes: ...
```

`manifest_version` is fixed to `synthea-conformance-v1`; `engine_id` is fixed
to `synthea`; and `review_status` is one of `PENDING`, `APPROVED`, or
`REJECTED`. Repository fixtures must use `review_status="PENDING"` and
`test_only=True`. A manifest is a declaration, not a conformance result; this
slice intentionally exposes no `PASS` helper and cannot authorize execution
or release.

All identifier fields are bounded aggregate-safe tokens. All digest fields are
nonzero lowercase SHA-256 values. `from_mapping` requires exactly the declared
keys, rejects wrong types, unsafe tokens, zero or uppercase digests, duplicate
JSON keys, nonfinite JSON numbers, non-ASCII JSON, and trailing non-whitespace
content. `to_json_bytes` emits canonical sorted ASCII JSON with one trailing
newline and no caller-owned mutable state.

## Engine handoff boundary

The manifest records only aggregate identities for the pinned Synthea engine,
module bundle, custom pediatric growth extension, engine-neutral event adapter,
PPOC exporter, configuration, and license/attribution notice. It contains no
filesystem paths, patient or visit identifiers, rows, clinical values, hidden
truth, event traces, keys, network locations, or arbitrary review prose.

The contract does not read a Synthea checkout, invoke Java, download modules,
translate Synthea output, allocate prevalence, replace pediatric growth
physiology, or write PPOC resources. A future runner must supply an externally
controlled pinned revision and license review, custom growth physiology,
versioned disease modules, event-trace adapter, exact-schema exporter,
configuration, and the matching non-test derivation binding before any output
can be considered for conformance evaluation.

## Safety and evidence boundary

- The manifest is development metadata only. `test_only=True` and `PENDING`
  fixtures are suitable for fictional parser tests and cannot be promoted by
  changing a field in the caller.
- The native generator, imported augmenter, package exporter, calibration,
  held-out, prevalence, privacy, counterfactual, and evaluator modules do not
  import or consume this manifest contract automatically.
- A valid manifest does not prove clinical validity, growth-disorder or
  demographic fidelity, prevalence, privacy or non-matchability, task utility,
  reproducibility, release readiness, or Synthea conformance.
- No test uses real or governed data, a Synthea checkout, a network service,
  Java execution, or an external license artifact. The optional route remains
  downstream of the existing derivation-binding, validation, clinical-review,
  privacy, and release gates.

## Verification and documentation

Fictional tests cover strict key/type/token/digest validation, canonical
serialization, duplicate/nonfinite/non-ASCII JSON rejection, review and
test-only semantics, and mutation isolation. Static boundary tests assert the
module imports only the standard library and aggregate-safe local contracts,
does not import `Path`, CSV, subprocess, package writers, Synthea, or governed
evaluators, and is not imported by visible generation or validation modules.
Documentation labels this as a future optional Synthea handoff contract,
links the parent Synthea design and engine-neutral guides, and states that no
Synthea implementation or conformance result exists yet.

## Deferred work

This slice does not vendor or implement Synthea, add a Generic Module Framework
JSON module, add custom Java physiology, run engine comparisons, bind an
authoritative oracle, generate cohort-scale packages, or claim any clinical,
prevalence, privacy, demographic, task, release, or Synthea evidence. Those
require the external pinned-engine handoff and the full engine-conformance
suite under independent review.
