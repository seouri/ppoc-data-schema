# Authoritative Derivation Oracle Binding Design

**Date:** 2026-09-01
**Status:** Implementation complete; approved non-test derivation binding and independent parity/review evidence pending
**Prerequisites:** the approved synthetic-growth-fixtures design, the exact-schema package exporter, and the evaluator-only derivation-parity gate

## Purpose

The repository can already compare two already-loaded augmented outputs, but it
does not have a governed way to bind the implementation that produced those
outputs to its executable source, dependency set, reference standard, golden
boundary evidence, parity result, and review decision. The parent design makes
that binding a prerequisite for calling augmented resources valid. This slice
adds the machine-checkable handoff contract without inventing the missing
clinical derivation logic or treating metadata as proof of clinical authority.

The contract is intentionally useful before an external oracle is available:
fictional test fixtures can carry a test-only binding, while a production
binding remains impossible to promote until its independently controlled
evidence and review fields are complete. The existing command-line entry point
continues to fail closed in this slice.

## Decision and alternatives

### Recommended: strict binding and evidence handoff

Add an immutable, aggregate-only `DerivationBinding` model and a validator that
accepts an already-loaded metadata mapping. The binding records stable
identities and digests for the candidate oracle, its dependencies, the
reference standard, the golden-case manifest, the parity report, and the
review decision. The validator checks exact shape, safe metadata, digest
syntax, fixed contract version, required boundary categories, evidence-status
coherence, and the relationship between test-only classification and review
status. A wrapper used by package generation verifies that the oracle's
returned `DerivationResult` agrees with the binding before any augmented output
is promoted.

This is the smallest slice that makes the external dependency explicit and
prevents a future caller from passing unrelated identity strings as if they
were an approved oracle. It does not claim that a self-reported digest or
review status is independently true; custody, code review, clinical review,
and release authorization remain outside the Python process.

### Alternative: implement a clean-room augmenter immediately

A clean-room implementation could compute the two augmented resources from
the existing descriptor and public references. It would still be
`UNVERIFIED_DERIVATION` until bidirectional parity passed over reviewed golden
cases and a governed synthetic-fuzz corpus. Implementing it now would create a
large clinical/algorithmic surface while leaving the release gate unresolved,
so it is deferred until a reference harness or authoritative implementation is
actually supplied.

### Alternative: build a Synthea adapter now

A Synthea adapter could provide background events, but it cannot define the
PPOC augmentation semantics. It would still need this binding, the exact
exporter, an engine-neutral event trace, pediatric growth replacement, and the
same parity and privacy gates. It is therefore a later conformance slice, not a
substitute for this dependency-clearing work.

## Scope and non-goals

This slice includes:

- a strict `derivation-binding-v1` in-memory metadata contract;
- aggregate-only validation with fixed check order and redacted failures;
- canonical serialization of the binding and its validation report;
- explicit identities for the candidate oracle, its dependencies, and the
  reference standard;
- a golden-evidence declaration covering every documented derivation boundary;
- binding of an aggregate parity-report identity and status;
- an explicit external review record and test-only classification;
- integration at the existing oracle/export boundary so identity or evidence
  drift fails closed; and
- documentation and fictional tests for the handoff and failure cases.

This slice does not:

- implement `scripts/augment.py`, a replacement derivation algorithm, LMS/WHO/
  CDC calculations, Harrall/BIV rules, velocity formulas, or terminology
  decisions;
- read real data, governed paths, patient rows, golden rows, or a Synthea
  checkout;
- execute an external harness or infer evidence from a file path;
- make `PASS` metadata clinically authoritative or authorize release;
- change the visible eight-resource schema, truth boundary, or package file
  names; or
- enable the production CLI without an approved non-test binding and an
  explicitly supplied oracle.

## Binding contract

The public version constant is:

```text
DERIVATION_BINDING_VERSION = "derivation-binding-v1"
```

`DerivationBinding.from_mapping(value)` accepts one JSON-like mapping with
exact top-level keys. Unknown keys, missing keys, duplicate JSON keys,
nonfinite values, unsafe tokens, paths, row/record indicators, and nested
objects in scalar positions fail closed. `to_mapping()` returns a fresh plain
mapping in canonical field order, and `to_json_bytes()` returns compact,
sorted, ASCII JSON with one trailing newline. No binding or report mapping may
contain patient/visit identifiers, rows, source paths, secrets, candidate
pairs, raw measurements, hidden truth, or private exception text.

The canonical shape is:

```json
{
  "binding_version": "derivation-binding-v1",
  "binding_id": "...",
  "schema_fingerprint": "<lowercase sha256>",
  "oracle": {
    "oracle_id": "...",
    "implementation_fingerprint": "<lowercase sha256>",
    "source_revision": "...",
    "dependency_fingerprint": "<lowercase sha256>",
    "source_kind": "authoritative_implementation"
  },
  "reference_standard": {
    "standard_id": "...",
    "standard_fingerprint": "<lowercase sha256>",
    "version": "..."
  },
  "golden_evidence": {
    "manifest_id": "...",
    "manifest_fingerprint": "<lowercase sha256>",
    "parity_contract": "derivation-parity-v1",
    "parity_report_id": "...",
    "parity_report_fingerprint": "<lowercase sha256>",
    "parity_status": "PASS",
    "candidate_implementation_fingerprint": "<lowercase sha256>",
    "reference_implementation_fingerprint": "<lowercase sha256>",
    "parity_schema_fingerprint": "<lowercase sha256>",
    "covered_categories": [
      "filter_order",
      "age_boundaries",
      "missingness",
      "harrall_outlier",
      "biv_filtering",
      "velocity_variants",
      "rounding"
    ],
    "bidirectional_case_count": 0,
    "synthetic_fuzz_case_count": 0,
    "fuzz_corpus_fingerprint": "<lowercase sha256>"
  },
  "review": {
    "review_id": "...",
    "review_fingerprint": "<lowercase sha256>",
    "reviewed_at": "YYYY-MM-DDTHH:MM:SSZ",
    "reviewer_role": "...",
    "status": "APPROVED"
  },
  "test_only": false
}
```

The example uses placeholders only to show types; a valid mapping must contain
real bounded tokens and valid digests. `source_kind` is one of
`authoritative_implementation` or `approved_parity_harness`. A handoff may
identify an approved harness as the executable authority when the source
implementation is unavailable, but it must still provide the same reference,
golden, parity, and review evidence.

`covered_categories` is compared with the fixed set above, not treated as a
free-form claim. `bidirectional_case_count` must be positive and the fuzz
count must be positive for a non-test binding. A stricter externally approved
policy may require larger counts; this contract never lowers those requirements
or silently treats an absent corpus as zero evidence. The exact golden inputs
and outputs remain in controlled custody and are represented here only by
stable IDs and digests.

The three parity identity fields are not decorative: the candidate fingerprint
must equal `oracle.implementation_fingerprint`, the parity schema fingerprint
must equal the top-level schema fingerprint, and the parity contract must equal
`derivation-parity-v1`. The reference fingerprint is required to be a valid
independently supplied implementation identity and is retained separately from
the reference-standard fingerprint. A parity report digest is evidence of the
report bytes held by the custodian; this process validates the declared
relationship but does not open or execute those bytes.

## Validation model and status semantics

The module exposes:

```python
validate_derivation_binding(
    binding: DerivationBinding,
    *,
    expected_schema_fingerprint: str,
) -> DerivationBindingReport
require_approved_derivation_binding(
    binding: DerivationBinding,
    *,
    expected_schema_fingerprint: str,
) -> None
```

The report has a fixed ordered check universe:

1. `contract`
2. `schema_contract`
3. `oracle_identity`
4. `reference_standard`
5. `golden_coverage`
6. `parity_evidence`
7. `synthetic_fuzz_evidence`
8. `review`
9. `classification`

Each check is `PASS`, `FAIL`, or `UNEVALUABLE`, with precedence
`FAIL > UNEVALUABLE > PASS`. A check is `FAIL` when visible metadata is
contradictory or outside the fixed contract; it is `UNEVALUABLE` when required
evidence is absent or explicitly unavailable; it is `PASS` only when every
field owned by that check is present, well-typed, and coherent. Reports expose
only check names, statuses, fixed reason codes, aggregate counts, the binding
ID, the expected schema fingerprint, and safe evidence identities. They do not
echo arbitrary metadata values or evidence details.

`require_approved_derivation_binding` succeeds only when the report is `PASS`,
`test_only` is `False`, the golden parity status is `PASS`, the review status
is `APPROVED`, and the implementation/reference/schema identities are all
consistent. A test-only binding may be structurally valid and can be used by
fictional CI through the existing test-oracle path, but it must remain marked
test-only in the package manifest and cannot satisfy a release claim. For a
test-only binding, absent golden/parity/fuzz evidence is allowed only as
`UNEVALUABLE` development metadata; it can never satisfy the approval helper.
A `PASS` parity report with a failing, missing, or unapproved handoff is not an
approved binding.

The validator cannot verify that an external digest names the bytes a custodian
reviewed or that a reviewer performed the stated work. Those are explicit
governance responsibilities. The model makes the claims auditable and prevents
accidental identity drift; it does not turn caller-provided metadata into
clinical authority.

## Oracle and exporter integration

The low-level `DerivationOracle` protocol remains responsible only for writing
the two descriptor-named augmented resources into the isolated staging tree
and returning `DerivationResult`. A `BoundDerivationOracle` adapter combines a
caller-supplied oracle with a validated `DerivationBinding` and performs these
checks around the existing call:

1. the binding's schema fingerprint equals the exact repository schema;
2. the binding's oracle ID and implementation fingerprint equal the oracle's
   declared and returned identities;
3. the returned `test_only` value equals the binding classification; and
4. an approved production call has passed
   `require_approved_derivation_binding` before staged outputs are copied.

The adapter never loads a path from the binding, executes an external command,
reads a real package, or adds metadata to visible CSV rows. Existing atomic
staging, base-resource hash checks, unexpected-file checks, structural
validation, and manifest lifecycle remain in force. The exporter records the
bound implementation fingerprint and the existing test-only status; it does
not serialize hidden evidence or the binding's review material into a released
package. Any mismatch raises the existing fixed redacted derivation failure.

The current smoke example and fictional test oracle use an explicit test-only
binding. No production binding is checked into the repository, and the CLI
continues to emit its unavailable-oracle failure until a caller supplies a
reviewed non-test binding and oracle through a future explicit configuration
route.

## Evidence and review boundary

The handoff records the following minimum evidence categories because the
parent design identifies them as unresolved augmentation semantics:

- filtering order;
- age boundaries, including the 24-month transition;
- missingness and nullable output behavior;
- Harrall outlier handling;
- biologically implausible-value filtering;
- EP/AP/LP velocity variants; and
- rounding behavior.

The golden manifest must identify at least one reviewed bidirectional case in
each category. The parity report must be produced by the evaluator-only gate
using independently supplied candidate/reference rows, and its digest must
bind the implementation and reference identities declared here. The synthetic
fuzz corpus must be governed, patient-free, and represented by an aggregate
count and digest; its rows never enter this repository or the public binding.

The review record identifies an external review decision by safe ID, digest,
timestamp, and reviewer role. `APPROVED` means the named custodian/reviewer
approved the stated scope under their process; it is not a software-generated
clinical or privacy determination. The fixed report reason codes are `OK`,
`MISSING_EVIDENCE`, `OUTSIDE_POLICY`, and `STRUCTURAL_INVALID`; no arbitrary
review prose is serialized. Clinical validity, prevalence, held-out fidelity,
privacy/non-matchability, task utility, Synthea conformance, and release
authorization remain separate gates.

## Failure and security behavior

- Invalid mappings raise one fixed `DerivationBindingUnavailable` exception
  whose text contains no caller values, paths, IDs, or nested errors.
- Missing evidence is `UNEVALUABLE`, never a fabricated `PASS` or zero count.
- Contradictory statuses, counts, digests, identities, or test-only/review
  combinations are `FAIL`.
- Unknown fields, duplicate keys, unsafe strings, nonfinite numbers, booleans
  in integer positions, and negative counts are rejected.
- The validator accepts only already-loaded mappings and never mutates them.
- Binding and report representations remain aggregate-only and safe for logs.
- A failed binding cannot cause the exporter to copy either augmented output.
- The binding does not weaken descriptor foreign-key, structural, lifecycle,
  manifest, or derivation-parity checks already in the repository.

## Testing strategy

Tests use fictional IDs and digests only. They cover:

- exact root and nested key sets and canonical round trips;
- valid test-only and approved non-test mappings;
- missing, extra, duplicate, reordered, or wrong-type metadata;
- unsafe path/row/identifier material and hostile scalar objects;
- invalid digests, timestamps, tokens, counts, category sets, and statuses;
- absent evidence versus contradictory evidence and fixed report precedence;
- parity/reference/schema identity mismatches;
- review/classification coherence and test-only manifest behavior;
- redacted exception and serializer output;
- wrapper rejection when an oracle's returned identity changes;
- wrapper rejection before any augmented file is copied for an unapproved
  binding; and
- preservation of the existing CLI fail-closed and no-real-data/no-Synthea
  import boundaries.

The full repository suite, Ruff, lockfile check, schema check, and a focused
deterministic serialization/redaction exercise are required before integration.
No test invokes a network service, a real-data path, a Synthea checkout, or a
governed artifact.

## Acceptance criteria

1. `derivation-binding-v1` has immutable models, strict exact-key parsing,
   canonical serialization, fixed status/reason semantics, and aggregate-only
   reports.
2. Every required evidence category is fixed in code; an incomplete category
   set, missing parity/fuzz evidence, or contradictory status cannot produce an
   approved binding.
3. Approved non-test bindings require `PASS` parity, complete golden coverage,
   positive governed fuzz evidence, matching schema/oracle/reference identities,
   and an external `APPROVED` review record.
4. Test-only bindings remain available for fictional CI and are visibly
   classified as test-only; they cannot satisfy the production approval helper.
5. The exporter/oracle boundary verifies binding-to-result identity and
   classification before copying augmented outputs and preserves its existing
   atomic failure behavior.
6. No visible generator, CLI, native trajectory module, calibration evaluator,
   held-out evaluator, privacy auditor, or Synthea adapter automatically
   imports or consumes the binding evidence.
7. Documentation explains how a custodian supplies the external manifest and
   golden/parity evidence without placing rows, paths, or secrets in the
   repository, and clearly states that software validation is not clinical or
   release authorization.

## Roadmap relationship

This is a dependency-clearing gate immediately after the in-memory derivation
parity evaluator. It does not close the parent design's authoritative-oracle
acceptance criterion until a real externally controlled handoff is supplied.
The next possible implementation slice is either the controlled oracle
integration once that handoff exists or, independently, the optional Synthea
engine-conformance adapter. Neither route may bypass this binding contract.
