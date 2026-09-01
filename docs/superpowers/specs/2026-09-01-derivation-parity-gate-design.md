# Governed Augmented-Derivation Parity Gate

**Date:** 2026-09-01
**Status:** Approved design for the next roadmap slice
**Parent:** [Synthetic Pediatric Growth Fixture System Design](2026-08-30-synthetic-growth-fixtures-design.md)
**Prerequisites:** the exact-schema package exporter, the native observation/resource contracts, and the governed prevalence/held-out evidence boundary

## Purpose

The repository's exact-schema exporters currently require an injected
`DerivationOracle`, but the only oracle used in CI is a test fixture that
proves lifecycle behavior rather than augmented-resource correctness. This
slice adds a standalone, aggregate-only parity harness for the two augmented
resources. It compares a candidate augmented output with an independently
supplied reference output and independently recomputes the deterministic
relationships that are declared by the checked-in descriptor.

The harness closes the dependency-clearing gate for an approved derivation
parity procedure. It does not pretend that a test oracle or a reference file
is clinically authoritative: a separately reviewed implementation, reference
standard, code-set decision, and data-custodian approval are still required
before any output is called clinically valid or released. It is deliberately
usable with completely fictional rows in CI and with privately loaded
reference/candidate rows in a governed environment.

## Scope and non-goals

The implementation is an in-memory evaluator in
`src/synthetic/derivation_parity.py`. It accepts already-loaded mappings and
row iterables only. It does not open paths, read CSV/Parquet files, call
DuckDB, write a report, mutate a package, invoke a generator, tune a model,
consume calibration/held-out/privacy evidence, or import Synthea. A caller
that needs a file-level gate must load both outputs through an independently
controlled process and pass the resulting rows to this API.

The harness does not implement CDC/WHO/LMS tables, the Harrall outlier
algorithm, a chronic-diagnosis code set, a clinical terminology service, or a
Synthea module. Reference-dependent growth scores, percentiles, velocity
scores, and clinical code decisions are checked against the supplied
reference output and exact schema constraints; they are not regenerated from
invented parameters. The harness is not a prevalence estimator, a privacy or
non-matchability proof, a clinical validation, a release authorization, or a
claim that generated profiles cannot be matched to real people.

## Public contract

The module exposes the fixed contract token
`DERIVATION_PARITY_VERSION = "derivation-parity-v1"`, the exception
`DerivationParityUnavailable`, and these immutable values:

```python
class DerivationParityStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNEVALUABLE = "UNEVALUABLE"


@dataclass(frozen=True)
class DerivationImplementation:
    implementation_id: str
    fingerprint: str
    test_only: bool


@dataclass(frozen=True)
class DerivationParityPolicy:
    policy_id: str
    policy_version: str
    minimum_patient_rows: int
    minimum_visit_rows: int
    deterministic_tolerance: float
    reference_tolerance: float


def validate_derivation_parity(
    base_rows: Mapping[str, Iterable[Mapping[str, object]]],
    candidate_rows: Mapping[str, Iterable[Mapping[str, object]]],
    reference_rows: Mapping[str, Iterable[Mapping[str, object]]],
    descriptor: Mapping[str, object],
    *,
    candidate: DerivationImplementation,
    reference: DerivationImplementation,
    policy: DerivationParityPolicy,
) -> DerivationParityReport: ...
```

`DerivationImplementation.implementation_id` is a bounded aggregate-safe
token; `fingerprint` is lowercase SHA-256 hex; and `test_only` is an explicit
boolean. Policy identifiers are likewise bounded tokens. Tolerances are
finite, nonnegative, and below the fixed contract cap; the policy cannot
silently request an unbounded comparison. The report includes the two safe
implementation mappings and policy identity, but not the policy's secret
inputs or any row value.

`base_rows` contains exactly the six base resources in descriptor order:
`patients`, `visits`, `labs`, `medications`, `problem_list`, and `referrals`.
`candidate_rows` and `reference_rows` contain exactly
`patients_augmented` and `visits_augmented`. Every row must be a mapping whose
keys are the exact descriptor field names in field order. Rows are
materialized privately, sorted by their descriptor primary keys, and never
retained by the public report. Missing values are the descriptor's empty
sentinel or `None`; booleans are never accepted as numbers; finite numeric
strings may be parsed according to the descriptor type; and nonfinite or
unknown values fail closed.

## Checks and status semantics

The report has a fixed ordered check universe:

1. `schema_contract` — the descriptor has the exact repository schema
   fingerprint and exactly the required base and augmented resources.
2. `base_shape` — base keys, primary keys, row uniqueness, and the
   descriptor-declared visible types are valid.
3. `candidate_shape` and `reference_shape` — augmented keys, row keys, types,
   nullability, enums, finite values, and descriptor bounds are valid.
4. `patient_key_alignment` and `visit_key_alignment` — candidate and
   reference keys agree with each other and with the base resources, and every
   augmented visit points to an existing base patient/visit.
5. `patient_identity_projection` — patient identifiers and recorded sex are
   preserved; ethnicity and race values follow the descriptor's informative
   vocabulary, mapping base nonresponse values to the empty sentinel; and the
   candidate and reference projections agree.
6. `visit_identity_projection` — visit identifiers, patient identifiers,
   recorded demographics, age, measurements, encounter fields, and diagnosis
   slots are copied from the base contract, with base `BMI` treated as the
   source concept for derived lowercase `bmi` rather than as an equality
   assertion.
7. `deterministic_age_conversion` — `age_in_months` equals
   `round(age_in_days / 30.4375, 2)` and `age_in_years` equals
   `round(age_in_days / 365.25, 3)` whenever the source age is present.
8. `deterministic_unit_conversion` — non-filtered `weight_kg` and `height_cm`
   agree with the descriptor-declared conversions `weight_oz / 35.274` and
   `round(height_in * 2.54, 3)`. When an approved BIV rule makes a value
   missing, the harness checks the candidate/reference agreement and does not
   infer a replacement measurement.
9. `deterministic_bmi` — for age at least 24 months and two positive filtered
   measurements, lowercase `bmi` equals
   `weight_kg / (height_cm / 100) ** 2` within the deterministic tolerance;
   otherwise it is missing.
10. `deterministic_patient_summaries` — visit counts, first/last ages, spans,
    diagnosis-age prefix minima, and z-score summary counts/minima/maxima are
    consistent with the privately materialized base/augmented rows whenever
    the required source values exist. Standard deviation uses the fixed
    population definition (`ddof=0`); no summary statistic is fabricated for
    an empty source set.
11. `clinical_flag_relationships` — required binary flags are in `{0, 1}`;
    stunting, wasting, underweight, and obesity flags never contradict their
    available z-score/percentile thresholds; `healthy_flag` is one only when
    all of its declared adverse-history flags are zero. Unknown diagnosis
    code-set membership is not guessed by this harness and remains a
    reference-dependent comparison.
12. `reference_field_parity` — every candidate/reference augmented field is
    compared after canonical type conversion. Strings, identifiers, flags,
    and nulls are exact; finite numbers use `reference_tolerance`. The check
    reports only aggregate compared/mismatch counts and the maximum absolute
    difference.
13. `support` — both augmented resources meet the policy's minimum patient
    and visit row support. A missing or underpowered reference is
    `UNEVALUABLE`, never an implicit zero or pass.

Structural, identity, deterministic, bound, or candidate/reference mismatch
is `FAIL`. If no check fails but a required source is missing or support is
below policy, the affected check and overall report are `UNEVALUABLE`. The
overall status precedence is `FAIL > UNEVALUABLE > PASS`, and `PASS` requires
every check to be evaluable and passing. The report never emits row-level
errors, identifiers, feature values, raw diagnosis codes, or candidate
distances.

Reference-dependent fields are not weakened by omission: an augmented field
that is present in the exact descriptor must be present (or explicitly
missing) in both outputs and is included in parity. The candidate and
reference implementation fingerprints are evidence identities, not proof
that either implementation is clinically correct. An independently reviewed
reference implementation and a fixed reference fixture are prerequisites for
using a passing report in a release decision.

## Report and serialization boundary

`DerivationParityCheck` contains only `name`, `status`, `reason_code`,
`compared_count`, `mismatch_count`, and `maximum_absolute_difference`.
`DerivationParityReport` contains exactly `contract`, `schema_fingerprint`,
`policy`, `candidate`, `reference`, `patient_row_count`, `visit_row_count`,
`status`, `status_counts`, and the fixed ordered `checks` tuple. Counts are
nonnegative integers; numeric differences are finite and bounded; values are
suppressed to `null` for an unevaluable check. `to_mapping()` returns a fresh,
JSON-compatible aggregate mapping. `to_json_bytes()` is canonical compact,
sorted, ASCII JSON with one trailing newline. `repr()` for every public value
is evaluator-safe and excludes rows, IDs, source values, and hidden objects.

The API raises only the fixed redacted `DerivationParityUnavailable` message
for malformed input or evaluator failure. It does not include a path,
identifier, diagnosis code, raw value, exception detail, or row position in
an exception or report. It does not mutate any supplied mapping, row, or
iterable.

## Testing and boundaries

Tests use small fictional six-resource bases and augmented rows with a
deterministic reference/candidate pair. They cover exact schema and row-key
validation, duplicate/missing IDs, informative demographic projection, age,
unit, BMI, summary, flag, bound, null, tolerance, and support semantics;
candidate/reference mismatch; canonical serialization; input immutability;
fixed redaction; and absence of hidden values in mappings/reprs.

Static boundary tests scan the parity module and visible generation/export
roots. The parity module must not import `Path`, `csv`, `duckdb`,
`package_export`, `manifest`, `calibration`, `heldout`, `privacy`, real-data,
model, callable, network, or Synthea code; it must not expose path/key/output
arguments; and it must not serialize names such as `trajectory`, `truth`,
`latent`, `source`, `row`, or `patient_id` except inside private validation
logic and fixed descriptor field comparisons. Visible generation, native,
manifest, derivation, and package-export code do not call the parity evaluator
automatically in this slice, so a report cannot feed back into generation.

Documentation names the API as an evaluator-only parity gate, distinguishes a
candidate/reference comparison from clinical authority, and retains the
separate prevalence, held-out, privacy/non-matchability, clinical, task
utility, release, and optional Synthea boundaries. CI remains wholly
fictional; any governed use must load data privately and obtain independent
review of the reference implementation and reference standards.

## Acceptance criteria

1. A valid fictional base/candidate/reference triple produces a deterministic
   aggregate-only `PASS` report whose canonical bytes are stable across
   repeated evaluation.
2. Every required augmented field is schema-checked and compared, while
   schema-declared deterministic age, unit, BMI, identity, summary, and flag
   relationships are independently recomputed where their source values are
   available.
3. A candidate mismatch, malformed row, unsafe scalar, duplicate key, schema
   drift, or contradictory deterministic value fails closed without leaking
   row material; missing or underpowered required evidence is explicitly
   `UNEVALUABLE`.
4. Existing exporters, smoke generation, governed evaluators, package schema,
   and Synthea decisions remain behaviorally unchanged.
5. Focused tests, full pytest, Ruff, lock, schema, whitespace, and fresh
   boundary review pass before integration. This gate is a dependency-clearing
   parity harness, not clinical or release authorization.
