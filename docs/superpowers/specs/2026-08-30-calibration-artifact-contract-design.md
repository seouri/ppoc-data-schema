# Aggregate Calibration Artifact Contract Design

**Status:** Implementation complete; aggregate-only contract; governed real-data calibration/evidence pending

## Purpose

Define the first safe slice of the roadmap's calibration-and-fidelity work: a strict, versioned contract for disclosure-controlled aggregate calibration artifacts. The contract gives later calibration, generation, held-out validation, and fidelity tooling a stable input boundary without adding a real-data reader, cohort-label allocator, prevalence estimator, or visible fixture integration.

This is an aggregate metadata and target contract, not a calibrated release. A valid artifact records what an authorized external calibrator released; it does not establish that the underlying data, target definitions, tolerances, or privacy decision are valid.

## Scope and boundaries

The slice adds an engine-neutral artifact model and loader under `src/synthetic/calibration.py` with focused tests. It accepts only a strict JSON aggregate artifact produced outside this repository and never accepts patient rows, longitudinal sequences, serialized examples, candidate matches, real-data roots, or hidden evaluator truth.

The slice does not read PPOC CSV snapshots, partition patients, run DuckDB aggregation, infer latent disease prevalence, tune generator parameters, modify `generate_smoke`, change visible CSVs or manifests, add a CLI, perform held-out validation, run a privacy audit, or implement a Synthea backend. It does not make a clinical, statistical, release, or privacy claim.

## Recommended architecture

### Artifact model

Add frozen `CalibrationArtifact`, `CalibrationDisclosurePolicy`, `CalibrationStratum`, and `CalibrationTarget` dataclasses. The public loader is `load_calibration_artifact(path: Path) -> CalibrationArtifact`; `CalibrationArtifact.from_mapping(value: object) -> CalibrationArtifact` supports tests and callers that already decoded JSON. The model exposes a strict `to_mapping()` and `canonical_json() -> str`; the latter is an ASCII JSON string that encodes deterministically as UTF-8. Strata and targets are semantically unordered: validation normalizes them to lexicographic `stratum_id` and `target_name` order, and serialization emits that order.

The artifact's top-level shape is:

```json
{
  "artifact_version": "calibration-artifact-v1",
  "artifact_id": "calibration-2026-08-24-v1",
  "source_snapshot": "2026-08-24",
  "source_partition": "calibration",
  "source_aggregate_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "schema_fingerprint": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "created_at": "2026-08-30T00:00:00Z",
  "disclosure_policy": {
    "policy_id": "policy-example-v1",
    "policy_version": "1",
    "minimum_cell_count": 10,
    "continuous_rounding_decimals": 3
  },
  "strata": [
    {
      "stratum_id": "age_regime=infancy|reference_sex=F",
      "dimensions": {"age_regime": "infancy", "reference_sex": "F"},
      "targets": [
        {
          "target_name": "height_z",
          "family": "physiology",
          "statistic": "mean",
          "unit": "z",
          "status": "released",
          "value": -0.03,
          "support_count": 120,
          "denominator": 120,
          "rounding_decimals": 3
        }
      ]
    }
  ]
}
```

The example is an illustrative aggregate shape only. It contains no real values, patient identifiers, sequences, or claim that the target is clinically appropriate.

The exact required keys are fixed by version `calibration-artifact-v1`. Top-level keys are `artifact_version`, `artifact_id`, `source_snapshot`, `source_partition`, `source_aggregate_sha256`, `schema_fingerprint`, `created_at`, `disclosure_policy`, and `strata`. A policy has exactly `policy_id`, `policy_version`, `minimum_cell_count`, and `continuous_rounding_decimals`. A stratum has exactly `stratum_id`, `dimensions`, and `targets`. A target has exactly `target_name`, `family`, `statistic`, `unit`, `status`, `value`, `support_count`, `denominator`, and `rounding_decimals`, plus `quantile_level` only when `statistic` is `quantile`. No other keys are accepted.

### Strict validation

`CalibrationArtifact.from_mapping` rejects non-object roots, unknown keys, duplicate keys, missing required keys, wrong JSON types, empty collections, noncanonical identifiers, nonfinite numbers, booleans in numeric positions, uppercase or malformed lowercase-hex SHA-256 values in either hash field, a source partition other than `calibration`, non-UTC timestamps, duplicate strata, duplicate target names within a stratum, noncanonical `stratum_id` values, and patient-, visit-, serialized-record-, sequence-, truth-, or candidate-like user fields. The decoder uses a duplicate-key hook so JSON aliases cannot silently overwrite one another. `load_calibration_artifact` applies duplicate-key detection while decoding bytes; callers using `from_mapping` are responsible for supplying a mapping that has not already lost duplicate-key information because a Python mapping cannot retain duplicate keys.

The loader rejects symlinks, directories, special files, and artifacts larger than `4 MiB` (`MAX_CALIBRATION_ARTIFACT_BYTES = 4 * 1024 * 1024`) before parsing. It reads at most `MAX_CALIBRATION_ARTIFACT_BYTES + 1` bytes so growth after the initial size check also fails closed; input must be UTF-8 without a BOM. It reads one JSON artifact only; it never follows a real-data root or opens CSV, database, archive, or serialized-record inputs.

Identifiers and tokens use ASCII-safe bounded forms: artifact, snapshot, policy, target, and unit tokens match `[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`; dimension values match the same form with at most 63 trailing characters. They contain no whitespace or path separator and are rejected when they contain identity or serialized-record indicators such as `patient`, `visit`, `identifier`, `uuid`, `sequence`, `truth`, `candidate`, `match`, `row`, or `resource` (case-insensitive). The exact contract keys are not user-controlled tokens: in particular, the allowlisted `visit_window` and `recorded_sex` dimension keys remain valid despite those substrings. Strata contain at most four coarse dimensions and must contain at least one. Dimension keys are an allowlist (`age_regime`, `reference_sex`, `recorded_sex`, `race`, `ethnicity`, `encounter_type`, `disorder_kind`, `visit_window`, `measurement_channel`, `observation_status`, and `outcome_layer`); values are bounded nonempty tokens, may not be one of the reserved hidden-state terms (`latent`, `truth`, `sequence`, or `candidate`), and may not encode identifiers or serialized records. The `stratum_id` is the lexicographically ordered `key=value` join of its dimensions, using `|` between pairs, preventing duplicate semantic strata under alternate dimension ordering.

Target families are an allowlist of `demographics`, `observation`, `physiology`, `utilization`, and `recorded_outcome`. `latent`, `truth`, `patient`, `sequence`, and `candidate` families are invalid. Target names are bounded tokens and may not contain patient, visit, identifier, sequence, truth, candidate, match, row, or resource terminology. This namespace separation prevents an aggregate artifact from becoming an evaluator-truth transport.

### Disclosure semantics

`created_at` is a valid Gregorian RFC 3339 UTC timestamp with the exact form `YYYY-MM-DDTHH:MM:SSZ` (no fractional seconds, offset spelling, or leap seconds); `artifact_id`, `source_snapshot`, and policy identifiers are tokens rather than paths. Each target has a `status` of `released` or `suppressed`. A released target requires a finite value, a support count at least the policy's `minimum_cell_count`, and a nonnegative integer `rounding_decimals` no greater than the policy's continuous precision. A suppressed target must have `value: null`, `support_count: null`, `denominator: null`, and `rounding_decimals: 0`; suppression is never represented as numeric zero. Released denominators, when present, are positive integers no smaller than support count; `proportion` and `rate` targets require a released positive denominator. The artifact does not export suppressed counts or extrema.

Allowed statistics are `count`, `proportion`, `mean`, `sd`, `quantile`, and `rate`. Counts are integers at least zero; proportions are finite values in `[0, 1]`; standard deviations and rates are finite and nonnegative; means and quantiles are finite. A quantile requires a `quantile_level` in `[0, 1]`; other statistics must omit it. Released counts use zero rounding decimals. These are transport-level domains, not clinical validity rules.

The policy records only policy identity and aggregate release parameters. `minimum_cell_count` is a positive integer and `continuous_rounding_decimals` is an integer from 0 through 9. The policy does not embed a real-data path, patient partition, row count, suppressed-cell list, or attack output. The artifact may record a source snapshot label and one-way aggregate source identity, but no source identifier or patient-attributable provenance; custodian review remains responsible for the meaning and disclosure risk of those labels.

### Deterministic serialization

`to_mapping()` returns a newly allocated mapping in the contract's canonical field shape; callers cannot mutate the dataclass's internal tuples through it. `canonical_json()` uses exactly `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)` and returns the resulting string; numeric values are normalized during validation and no nonfinite value is serializable. Round-tripping a valid artifact preserves all values and emits normalized stratum/target ordering. Canonical serialization is for provenance and reproducibility; it is not a release signature or privacy guarantee.

## Data flow

The intended later flow is `governed calibrator -> disclosure policy -> aggregate artifact -> offline generator/validator`. This slice implements only the artifact boundary. A caller can load an approved artifact and inspect targets, but no existing generator path consumes it yet. The visible eight-resource smoke profile remains unchanged and continues to require its injected reference and derivation oracle.

## Error handling

All malformed artifacts fail closed with `ValueError` and messages naming the invalid field or contract rule. File-type and size failures also use controlled `ValueError`; no parser traceback or partial object is returned. The loader does not coerce strings to numbers, booleans to integers, suppressed values to zero, or unknown target families to a generic bucket.

The model does not catch or reinterpret governance decisions. A syntactically valid artifact may still be unusable for a future generator if its reference, module, schema, policy, or calibration identity is incompatible; compatibility checks are a later consumer responsibility.

## Testing and verification

Tests use only in-memory synthetic mappings and temporary synthetic JSON files. They cover:

1. valid artifact construction, canonical serialization, and load/round-trip equality;
2. strict top-level, nested-key, duplicate-key, type, timestamp, and hash validation;
3. calibration-partition enforcement and rejection of real-data-path or patient-like fields;
4. canonical coarse strata, dimension-count limits, duplicate semantic strata, and target-name uniqueness;
5. released versus suppressed target semantics, minimum support, denominator rules, and statistic-specific numeric domains;
6. rejection of latent/truth/sequence families and identifier-like target or dimension tokens;
7. symlink, directory, special-file, and oversized-artifact rejection where the platform permits those fixtures; and
8. a structural assertion that no visible generator, exporter, schema, manifest, smoke, or native trajectory module imports or consumes calibration artifacts.

The full repository pytest suite, Ruff, schema check, and whitespace check remain required. No real CSV, database, patient row, clinical reference table, or Synthea source is added.

## Documentation

`docs/synthetic-generator.md` will gain a short section explaining how to load an aggregate artifact, the strict aggregate-only and calibration-partition boundary, suppression semantics, and the fact that this loader does not calibrate prevalence, validate clinical fidelity, or establish privacy. It will point to later governed calibration, held-out validation, privacy audit, and Synthea-conformance gates without implying that any is complete.

## Deferred work

This slice intentionally stops before:

- reading or partitioning real PPOC records;
- computing aggregate targets with DuckDB or any other calibrator;
- choosing demographic, prevalence, observation-error, longitudinal, temporal-drift, or task-utility tolerances;
- consuming calibration targets in generation or assigning module labels from them;
- held-out validation or clinical chart review;
- linkage, membership-inference, attribute-disclosure, composition, or differential-privacy audits; and
- a Synthea adapter or engine-conformance suite.

## Acceptance criteria

- Only the strict aggregate artifact model/loader, focused tests, and usage documentation change.
- No artifact can carry patient rows, longitudinal sequences, candidate links, latent truth, or a real-data path through the accepted schema.
- Suppression is explicit and never silently coerced to zero; released cells meet the declared support floor.
- The loader is deterministic, versioned, provenance-aware, and fails closed on malformed or incompatible transport values.
- Existing visible generation and schema behavior remain unchanged, with all repository checks passing.
