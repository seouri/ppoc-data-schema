# Patient-Disjoint Held-Out Validation Design

**Date:** 2026-08-31
**Status:** Proposed next roadmap slice
**Parent design:** [Synthetic Pediatric Growth Fixture System Design](2026-08-30-synthetic-growth-fixtures-design.md)
**Prerequisite:** [Governed aggregate calibration core](2026-08-31-governed-calibration-core-design.md)

## Purpose and boundary

This slice adds a standalone, offline validator that compares a completely generated exact-schema package with the held-out patient partition of an explicitly supplied governed snapshot. The validator reuses the reviewed calibration target registry and disclosure contract, but it does not alter the calibrator, tune generator parameters, or make the generator consume held-out data. It is a fidelity gate for development and counterfactual fixture experiments, not clinical validation, prevalence authorization, privacy evidence, or a release decision.

The validator has two private inputs: a real snapshot and a keyed partition procedure. The key and all patient/visit rows remain inside one process-local DuckDB connection. The synthetic package is staged separately and must carry the generated descriptor's `x-synthetic: true` marker. Only disclosed aggregate comparisons, policy identities, hashes, and status counts leave the process.

The standalone boundary is intentional. Adding held-out logic to `calibrate` would couple source-target production to evaluation and make accidental adaptive tuning easier. A generic evaluator would broaden the attack surface and permit arbitrary columns to become report targets. `synthetic.heldout_validate` accepts the fixed registry only and has no API for custom SQL, patient partitions, rows, identifiers, candidate links, or hidden truth.

## Goals

1. Derive the held-out partition in governed process state with the same keyed HMAC procedure and partition policy used by calibration; never read or write a patient-level partition file.
2. Validate the real descriptor and generated package against the exact eight-resource schema, including safe paths, strict headers/dialects/encodings, primary keys, required values, enums, numeric ranges, and patient joins.
3. Compute the existing versioned aggregate target registry over real held-out rows and all generated rows without returning identifiers or sequences.
4. Compare only disclosure-controlled targets under a frozen, versioned fidelity policy. The policy is loaded before comparison and cannot be modified by the validator or an automated tuning loop.
5. Treat low support, suppression, missing target cells, and missing required families as `UNEVALUABLE`, never as zero or `PASS`. Report `FAIL` only for an evaluable target outside its frozen tolerance.
6. Emit deterministic machine-readable JSON and a concise human-readable summary with aggregate-only values/statuses, no supports or denominators, no paths, and no hidden truth.
7. Preserve the visible generator boundary: generation, exporters, trajectory modules, and manifests do not import or consume the validator, real-data path, partition key, or report.

## Non-goals

- No prevalence forcing, parameter fitting, adaptive resampling, temporal-drift analysis, task-utility experiment, privacy attack, linkage result, or Synthea adapter.
- No patient-level partition JSON, row/visit sequence export, identifier overlap report, nearest-neighbor result, candidate pair, attack score, or evaluator truth.
- No comparison against arbitrary columns, arbitrary strata, raw tails, or unapproved target names.
- No inference that recorded diagnosis flags equal latent disorder prevalence or that a passing aggregate gate establishes clinical validity.
- No default data root, descriptor, key, policy, snapshot, or output path; no overwrite of an existing output or lifecycle directory.
- No use of held-out targets in `synthetic.generate`, calibration fitting, or any automatic generator tuning loop.

## Public API and configuration

Add `src/synthetic/heldout_validate.py` with immutable models and one orchestration entry point:

```python
@dataclass(frozen=True)
class FidelityPolicy:
    policy_id: str
    policy_version: str
    target_registry_version: str
    minimum_evaluable_support: int
    proportion_floor: float
    proportion_z_score: float
    continuous_tolerances: Mapping[str, float]
    count_abs_tolerance: int
    required_families: tuple[str, ...]
    max_unevaluable_targets: int

@dataclass(frozen=True)
class HeldoutRunConfig:
    real_root: Path
    real_descriptor: Path
    source_snapshot: str
    synthetic_root: Path
    calibration_artifact: Path
    calibration_report: Path
    partition_policy: PartitionPolicy
    disclosure_policy: CalibrationDisclosurePolicy
    partition_key: bytes
    fidelity_policy: FidelityPolicy
    age_windows: tuple[CalibrationAgeWindow, ...]
    output: Path

@dataclass(frozen=True)
class HeldoutValidationResult:
    report: HeldoutValidationReport

def validate_heldout(config: HeldoutRunConfig) -> HeldoutValidationResult:
    ...
```

`FidelityPolicy` requires exact JSON keys. `continuous_tolerances` must contain exactly the five approved target families (`demographics`, `observation`, `physiology`, `utilization`, `recorded_outcome`) with finite nonnegative values. `required_families` must be a nonempty canonical subset of those families, with no duplicates. The minimum evaluable support is positive; the proportion floor is in `[0,1]`; the proportion z-score is positive; count tolerance and the unevaluable allowance are nonnegative integers. Policy identifiers and target registry version use aggregate-safe ASCII tokens. Unknown JSON keys, duplicate keys, nonfinite numbers, unsupported families, or invalid ranges fail closed.

The command is explicit about every governed input; the CLI uses the checked-in DEFAULT_AGE_WINDOWS registry, while library callers provide the age_windows tuple explicitly:

```sh
uv run python -m synthetic.heldout_validate \
  --real-root /governed/ppoc \
  --descriptor /governed/ppoc/datapackage.json \
  --snapshot 2026-08-24 \
  --synthetic-root /fixtures/development-20260830 \
  --calibration-artifact /approved/calibration/calibration-artifact.json \
  --calibration-report /approved/calibration/calibration-report.json \
  --partition-policy /governed/partition-policy.json \
  --disclosure-policy /governed/disclosure-policy.json \
  --partition-key-file /governed/partition.key \
  --frozen-policy /governed/fidelity-policy.json \
  --output /governed/heldout-report
```

The generated package descriptor is discovered only at `<synthetic-root>/datapackage.json`, opened as a regular non-symlink file, and required to declare `x-synthetic: true`. The real descriptor path is independent and must have the repository schema fingerprint. The calibration report is an explicit aggregate-only companion to the supplied artifact; its source snapshot, schema fingerprint, aggregate hash, and partition-policy identity must agree with the artifact and loaded policies. A compatibility failure between the artifact, report, policies, descriptors, snapshot, or target registry is a hard error before any report is promoted.

## Input staging and patient-disjointness proof

The validator opens the real descriptor and all eight real resources with the secure descriptor/path rules from `calibration_input`. It builds `patient_partitions(patient_id, partition_label)` in the private connection with the exact `assign_partition` HMAC-SHA256 algorithm. It checks nonempty and unique patient primary keys, complete patient joins for every resource, required values, lexical integers, finite numbers, enums, ranges, declared primary keys, and strict CSV parsing. A missing, extra, malformed, symlinked, absolute, parent-traversing, duplicate, or unknown resource fails before target computation.

The real connection retains only aggregate partition counts after staging. The target registry receives `partition_label="held_out"`, so no calibration-patient row contributes to the held-out aggregates. The validator additionally checks that every patient has exactly one label and that no resource row can join to more than one patient. The partition key is never included in a report, hash, exception, temporary filename, or output identifier.

The synthetic connection uses the same exact-schema staging and validation helpers but assigns every generated patient to an internal `calibration` label. This label means “the complete generated cohort” inside the target SQL; it is not a claim that generated records belong to the real calibration partition. The synthetic descriptor and all resource files are checked for regular non-symlink paths below `synthetic_root`, and the descriptor's fingerprint must equal the real/repository fingerprint. The package marker is provenance metadata, not a clinical or privacy approval.

## Target reuse and frozen comparison

`calibration_targets.compute_raw_targets` gains a validated `partition_label` keyword defaulting to `"calibration"`; the existing calibration call is unchanged. Every target query remains fixed registry SQL, with the label supplied as a parameter rather than interpolated. The validator computes:

1. raw held-out targets from real rows;
2. raw generated targets from the complete synthetic cohort; and
3. disclosure-controlled strata for both sides under the calibration artifact's disclosure policy.

The supplied calibration artifact and its explicit aggregate-only calibration report are loaded through strict loaders. The artifact's schema fingerprint, source snapshot, source partition, disclosure policy, and aggregate-only contract must match the real descriptor, command arguments, and explicit disclosure policy. The companion report must have the same source snapshot, schema fingerprint, source aggregate hash, and partition-policy identity as the artifact/calibration inputs. The frozen policy's `target_registry_version` must equal the checked-in `TARGET_REGISTRY_VERSION`; a future or unknown registry cannot be compared silently. The artifact is a compatibility anchor and synthetic-side reference; its target values are not used to tune or alter the generated package.

Targets are matched by the canonical tuple `(stratum_id, target_name, family, statistic, unit, quantile_level)`. A target is `UNEVALUABLE` when either side is missing, suppressed, has support below `minimum_evaluable_support`, lacks a required denominator, or belongs to a required family with no evaluable cell. The report does not expose support or denominator values. A released target is `PASS` when the absolute difference is within a frozen tolerance and `FAIL` otherwise.

For a proportion, the tolerance is:

```text
max(proportion_floor,
    proportion_z_score * sqrt(max(p_real * (1 - p_real) / n_real,
                                   p_synthetic * (1 - p_synthetic) / n_synthetic)))
```

where `n_real` and `n_synthetic` are internal disclosed denominators and the larger standard error is selected. For counts, the absolute difference must be at most `count_abs_tolerance`. For all other statistics, the tolerance is the frozen family value in `continuous_tolerances`. Tolerances are evaluated after disclosure rounding, use no adaptive estimate, and are never learned from held-out values.

The global report status is `FAIL` if any evaluable comparison fails. Otherwise it is `UNEVALUABLE` when the number of unevaluable comparisons exceeds `max_unevaluable_targets` or a required family has no evaluable cell; otherwise it is `PASS`. A `PASS` therefore means only that the declared aggregate cells were evaluable and within the frozen policy. It is not a prevalence, clinical, or privacy claim.

## Aggregate-only report and lifecycle

`HeldoutValidationReport` is a strict immutable model whose top-level mapping contains exactly:

```text
report_version
status
source_snapshot
synthetic_artifact_id
schema_fingerprint
partition_policy
disclosure_policy
fidelity_policy
heldout_aggregate_sha256
synthetic_aggregate_sha256
comparison_counts
family_counts
checks
comparisons
```

`comparisons` contains only canonical aggregate metadata and disclosed values: `stratum_id`, `target_name`, `family`, `statistic`, `unit`, optional `quantile_level`, `status`, `heldout_value`, `synthetic_value`, `difference`, and `tolerance`. Values are null for `UNEVALUABLE`; support counts, denominators, paths, identifiers, raw categories outside the registry, and source rows are never serialized. Comparison metadata is sorted canonically and validated against the existing token/dimension rules. `family_counts` and `comparison_counts` contain status counts only. Policy mappings expose IDs/versions, not key IDs or paths.

`heldout_aggregate_sha256` is the SHA-256 of the canonical, disclosure-controlled held-out target payload; `synthetic_aggregate_sha256` is the artifact's existing aggregate hash. The hashes are integrity identities, not privacy proofs. JSON uses compact sorted ASCII serialization and a trailing newline. The human report contains the status, policy identities, aggregate hashes, counts by status/family, and check outcomes on one concise line per item; it never includes target values, supports, paths, or row details.

Writing uses `RunDirectory` with a lifecycle ID derived from the artifact ID and fidelity-policy identity. The output directory must be new; partial output is written under a hidden run directory, reparsed and byte-compared, then promoted without replacement. A failure leaves only a redacted `failure.json` with `status=FAILED` and an aggregate reason. A comparison `FAIL` or `UNEVALUABLE` is a valid report and is returned to the CLI with a nonzero gate exit after promotion; malformed inputs and compatibility failures produce no promoted report.

## Testing strategy

Tests use only fictional exact-schema packages. A real-side fixture is partitioned with a deterministic test key; a generated-side fixture has a synthetic descriptor marker and independent visible identifiers. Required tests include:

- deterministic partition reuse, all-resource disjointness, minimum-partition enforcement, and rejection of patient partition files or identifiers in output;
- secure descriptor/package loading, synthetic marker enforcement, unsafe/symlink/absolute/parent paths, wrong headers/encodings, malformed values, duplicate keys, unknown patients, and schema-fingerprint drift;
- exact target-registry reuse for held-out and generated labels, including clean physiology exclusion of outlier/BIV-null values and observation/physiology separation;
- strict frozen-policy parsing, target-registry compatibility, artifact/disclosure/snapshot compatibility, required-family coverage, size-aware proportion tolerance, family continuous tolerance, count tolerance, rounding, suppression, and missing-cell `UNEVALUABLE` behavior;
- deterministic report/hash bytes, canonical comparison ordering, no patient/visit IDs, source paths, key bytes, supports, denominators, hidden truth, or arbitrary target names;
- PASS, FAIL, and UNEVALUABLE lifecycle behavior, output collision refusal, redacted failure artifacts, CLI required-input handling, and no partial promotion on hard failure; and
- an AST/import regression proving visible generation/export/trajectory modules do not import `heldout_validate`, `calibrate`, or governed real-data paths.

The full repository suite, Ruff, schema check, and whitespace check remain required. CI invokes the validator only with synthetic fixtures and fictional keys; a governed data root is never configured in CI.

## Deferred roadmap gates

This slice does not implement prevalence allocation, observation-error parameter fitting, temporal-drift metrics, task utility, privacy auditing/non-matchability, or the optional Synthea backend. Those gates consume this report only after their own frozen policies, hidden-truth boundaries, and governed review are defined. In particular, an aggregate fidelity pass cannot satisfy the requested “cannot be matched to real patient data” validation; the later privacy-audit slice must run identifier-overlap, exact-reproduction, nearest-neighbor, linkage, membership, attribute-disclosure, and composition controls under an approved risk policy.

## Acceptance criteria

1. A synthetic exact-schema package and an independently keyed test snapshot produce deterministic held-out validation JSON and a concise summary with no rows, identifiers, paths, keys, supports, denominators, or hidden truth.
2. Every comparison uses only the fixed target registry and the frozen policy; no held-out value reaches generation or tuning code.
3. Out-of-tolerance evaluable cells are `FAIL`; suppressed, missing, or underpowered cells are `UNEVALUABLE`, never zero or `PASS`.
4. Schema, descriptor, source/artifact/policy, synthetic provenance, and partition incompatibilities fail closed before promotion.
5. Identical approved inputs and metadata produce byte-identical reports; changed snapshot, policy, key, artifact, or aggregate changes the appropriate identity/status.
6. The normal generator remains offline and cannot accept a real-data path or validator output.
7. Full tests, Ruff, schema validation, and whitespace checks pass, and `main` equals `origin/main` after the reviewed merge/push.
