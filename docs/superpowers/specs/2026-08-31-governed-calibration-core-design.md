# Governed Aggregate Calibration Core Design

**Date:** 2026-08-31  
**Status:** Proposed next roadmap slice  
**Parent design:** [Synthetic Pediatric Growth Fixture System Design](2026-08-30-synthetic-growth-fixtures-design.md)  
**Prerequisite:** [Calibration artifact contract](2026-08-30-calibration-artifact-contract-design.md)

## Purpose and boundary

This slice implements the governed calibration core that turns an explicitly supplied PPOC snapshot and custodian-controlled patient partition procedure into disclosure-controlled aggregate targets. It gives the native generator a reproducible, reviewable calibration input without moving patient rows, visit sequences, identifiers, candidate matches, or hidden truth into the repository or an exportable artifact.

The calibrator is an offline governed tool. It may read a real snapshot only when an operator supplies the data root, source descriptor, snapshot label, partition policy, disclosure policy, and key material inside the governed environment. The repository contains no real snapshot and CI uses a wholly synthetic eight-resource mock package. The normal generator remains unable to accept a real-data path and does not consume calibration output in this slice.

This is an aggregate calibration implementation, not evidence that the generated cohort is representative, clinically valid, private, or authorized for release. Observable and recorded prevalence are measured; latent disorder prevalence and undiagnosed disease incidence remain configuration assumptions and are never inferred from a recorded diagnosis flag.

## Goals

1. Validate every resource in the supplied descriptor before measuring anything, including exact relative paths, encodings, dialects, headers, and the eight-resource contract.
2. Assign every patient and every linked resource row to one stable partition using a custodian-controlled keyed procedure, while retaining the assignment only in governed process state.
3. Prove that patient rows are not split between calibration and held-out partitions and fail closed on duplicate or unknown patient identifiers.
4. Compute a bounded, versioned set of aggregate demographic, cohort, observation, physiology, utilization, and recorded-outcome targets from patient-disjoint calibration data.
5. Keep physiology targets separate from observation-error targets and use only cleaned/available measurements for physiology summaries; raw tails never become biological targets merely because they are extreme.
6. Apply the existing disclosure-controlled `CalibrationArtifact` contract, including suppression and continuous-value rounding, and emit an aggregate-only report with deterministic hashes and no patient-level values.
7. Use DuckDB for the governed bulk scan while keeping the public API and output engine-neutral.
8. Make repeated runs byte-stable for identical inputs, policy versions, key, reference metadata, and creation timestamp.

## Non-goals

- No patient-level partition file, row export, sequence export, record example, nearest-neighbor result, candidate match, or evaluator truth.
- No latent disease label estimation, diagnosis-as-ground-truth interpretation, prevalence-forcing label allocation, or generator parameter tuning.
- No held-out validation, privacy attack, differential-privacy accounting, Synthea adapter, clinical reference approval, or release decision.
- No modification to visible synthetic CSV generation or consumption of an artifact by `generate_smoke`.
- No silent fallback from a missing, malformed, or suppressed statistic to zero.
- No dependence on a default data path, environment variable, current working directory, or implicit snapshot.

## Public API and configuration

Add `src/synthetic/calibrate.py` with focused immutable models and one orchestration entry point:

```python
@dataclass(frozen=True)
class PartitionPolicy:
    policy_id: str
    policy_version: str
    key_id: str
    calibration_basis_points: int
    minimum_partition_patients: int

@dataclass(frozen=True)
class CalibrationRunConfig:
    data_root: Path
    source_descriptor: Path
    source_snapshot: str
    artifact_id: str
    created_at: str
    partition_policy: PartitionPolicy
    disclosure_policy: CalibrationDisclosurePolicy
    partition_key: bytes
    age_windows: tuple[CalibrationAgeWindow, ...]

@dataclass(frozen=True)
class CalibrationResult:
    artifact: CalibrationArtifact
    report: CalibrationReport

def calibrate(config: CalibrationRunConfig) -> CalibrationResult:
    ...
```

`PartitionPolicy` validates canonical identifiers, a basis-point fraction in `1..9999`, a positive minimum count, and a nonempty key identifier. The key itself is supplied only as at least 16 in-memory bytes to `CalibrationRunConfig`; it is never serialized, hashed into a public identifier, or written to a report. The keyed assignment is `HMAC-SHA256(partition_key, patient_id)` interpreted as an unsigned big-endian integer modulo 10,000. Buckets below `calibration_basis_points` are `calibration`; the remainder is `held_out`. The algorithm and policy version are recorded, but patient assignments are not.

`CalibrationAgeWindow` contains a canonical window identifier and inclusive lower/exclusive upper age in days. The default public windows are `infancy` (`[0,730)`), `childhood` (`[730,3287)`), `puberty_window` (`[3287,5479)`), and `adolescence` (`[5479,7306)`). These are observable age bins for aggregation, not latent puberty labels. A run must provide at least one window, windows must be ordered and non-overlapping, and all upper bounds must be finite positive integers.

The CLI is `python -m synthetic.calibrate` and requires explicit `--data-root`, `--descriptor`, `--snapshot`, `--artifact-id`, `--created-at`, `--partition-policy`, `--disclosure-policy`, `--partition-key-file`, and `--output`. The key file is opened as a regular non-symlink file inside the governed environment and is not copied. The output directory must be new; an existing artifact or report is never overwritten. The CLI writes `calibration-artifact.json` and `calibration-report.json` only after the complete run succeeds.

## Input validation and patient-disjointness proof

The run first loads the supplied checked-in source descriptor through the schema contract and requires exactly these resources: `patients`, `patients_augmented`, `visits`, `visits_augmented`, `labs`, `medications`, `problem_list`, and `referrals`. The descriptor's schema fingerprint is compared with the repository contract fingerprint before the data root is opened; a descriptor from another snapshot or project is rejected. Every declared path must be a safe relative path below `data_root`, resolve to a regular non-symlink file, and be unique. Every file must be readable with the descriptor's declared encoding and dialect, and its first row must match `field_names(descriptor, resource)` byte-for-byte after decoding. A missing file, extra header, BOM, malformed CSV, or schema fingerprint mismatch stops the run before aggregation.

The `patients` resource is read first with all rows in a governed temporary relation. `patient_id` must be nonempty, unique, and represent the primary key declared by the descriptor. A keyed partition relation stores only `patient_id` and the two internal partition labels in the governed process. For every other resource, the calibrator verifies that `patient_id` is present, nonempty, and joins to exactly one patient. A missing or unknown patient key is an error, including in rows whose logical `visit_id` is nullable. `visit_id` may be null for labs, medications, and referrals exactly as the descriptor permits; incomplete logical visit links are measured as an observation target rather than treated as patient leakage.

All resource rows are joined to the internal partition relation before any aggregate is computed. A per-resource row count is retained separately for `calibration` and `held_out`; no patient identifier is retained in the result. The run fails if a patient appears in both partitions, if the minimum partition count is not met, or if a resource join would duplicate a patient row in a way that changes its declared grain. The report records only aggregate patient and row counts, policy identity, and validation status.

## Aggregate target registry

The calibrator uses a fixed versioned registry rather than turning arbitrary column names or values into output targets. Target names are canonical ASCII tokens accepted by the existing artifact model. Categories are mapped through an explicit slug table; values that could encode a patient, visit, row, sequence, truth, candidate, or attack result are rejected. Strata and targets are emitted in canonical lexicographic order.

The first registry version emits the following families. All targets are computed from the calibration partition only and are suppressed when their contributing support is below the disclosure minimum.

### Demographics

The patient-level `outcome_layer=observed` stratum contains proportions for recorded sex (`sex_f`, `sex_m`, `sex_u`), approved ethnicity categories and nonresponse categories, primary race categories and nonresponse categories, and a `race_multiselect` proportion. Demographic categories are recorded values, not inferred identity. Empty and nonresponse values retain separate approved categories so a generator can reproduce missingness rather than silently collapsing it.

### Recorded outcomes

The same patient-level stratum contains proportions for `healthy_flag`, `chronic_dx_flag`, `growth_dx_flag`, `ever_stunting_flag`, `ever_wasting_flag`, `ever_underweight_flag`, and `ever_obesity_flag`, plus age-at-first-recorded-diagnosis summaries when `dx_age_years` is present. These are explicitly recorded outcomes. The report labels them as observed/recorded and never calls them latent prevalence.

### Cohort and utilization

The `visit_window=all` stratum contains patient-level visit-count mean and quantiles, visit-span mean and quantiles, and visit-count support; visit-level encounter-type and Epic-origin proportions; and age-windowed inter-visit interval summaries. Encounter categories are mapped from an approved finite registry; an unregistered category is a validation error rather than an arbitrary target name.

### Observation process

The `visit_window=all` and age-windowed strata contain measurement-availability proportions for weight, height/length, head circumference, and BMI; missingness and duplicate/carry-forward indicators when the source schema exposes them; and nullable logical visit-link proportions for labs, medications, and referrals. These targets describe the observation process and are never included in physiology summaries.

### Physiology

The `age_regime=<window>|recorded_sex=<sex>` strata contain mean, standard deviation, and approved quantiles for clean `height_z_score`, `weight_z_score`, `bmi_z_score`, `height_velocity`, and `weight_velocity` values from `visits_augmented`. A measurement contributes only when its derived value is non-null and its corresponding outlier flag is not `1`; BIV-filtered nulls remain absent. Height and weight are therefore not independently treated as arbitrary raw observations, and extreme unclean values cannot become biological calibration targets. Support and denominator semantics are fixed by the registry and included in the aggregate report.

The physiology registry is deliberately limited to low-dimensional marginal summaries and approved pairwise correlations. It does not release serialized trajectories, ordered point lists, patient extrema, or high-dimensional covariance tables. Diagnosis timing relative to trajectory change is represented only by bounded aggregate age-window summaries, never by per-patient sequences.

## Disclosure and artifact construction

Each target is computed with an internal support count and denominator. Counts and denominators are released only through the existing artifact fields after the support threshold has passed; continuous values are rounded to the configured `continuous_rounding_decimals`. A target with support below `minimum_cell_count` becomes `status=suppressed` with null value, support count, and denominator. Suppression is reported by count and target family, never by listing affected strata or values that could reveal a small cell. No suppressed value is converted to zero.

Before constructing `CalibrationArtifact`, the calibrator builds a canonical aggregate payload containing only sorted stratum/target metadata and disclosed values. `source_aggregate_sha256` is the lowercase SHA-256 of that payload. The artifact then uses the existing strict `calibration-artifact-v1` model with `source_partition=calibration` and the checked-in schema fingerprint. The artifact contains only the snapshot label, opaque aggregate source hash, policy identity, strata, and target aggregates; it contains no data-root path, partition key, patient identifier, visit identifier, raw category not in the registry, or report path.

`CalibrationReport` is a separate aggregate-only JSON document with a version, status `AGGREGATES_ONLY`, snapshot label, schema fingerprint, partition-policy identity (excluding key material), partition patient/row counts, target-family counts, suppression counts, aggregate hash, and a list of validation checks with pass/fail status. It contains no target-level support or denominator values beyond the already disclosure-controlled artifact, and it never contains a candidate link or attack metric.

## Execution flow and failure handling

1. Validate configuration, policy versions, key bytes, descriptor fingerprint, resource paths, headers, encodings, and dialects.
2. Load the eight CSV resources into governed DuckDB temporary relations using safe, parameterized path handling and all-varchar staging where needed for exact missing-value semantics.
3. Build and validate the keyed patient partition relation; verify primary-key uniqueness and complete declared patient joins.
4. Materialize only partition-scoped aggregate relations and compute the fixed target registry.
5. Apply support suppression, rounding, finite-number checks, category allowlists, and canonical ordering.
6. Construct the strict artifact and aggregate report, recompute the aggregate hash, and assert that the artifact hash matches the report.
7. Write both output files transactionally into a new output directory and leave no partial output on failure.

Any header mismatch, path violation, malformed value in a required field, duplicate primary key, unknown patient, missing partition, target-registry drift, nonfinite statistic, hash mismatch, or output collision is a hard error. Errors do not include patient identifiers in raised messages or written reports. A failed run cannot be interpreted as a suppressed or empty calibration.

## Testing strategy

Tests create a wholly synthetic temporary package with all eight exact-schema resources and a small, intentionally varied population. No fixture row is copied from a real snapshot. The test package includes healthy and recorded-growth-disorder flags, multiple age windows, missing measurements, nullable/orphan logical visit links, clean and outlier growth summaries, and enough support to exercise both released and suppressed targets.

Required tests include:

- deterministic HMAC partition assignment, policy validation, minimum-partition enforcement, and proof that all resources remain patient-disjoint;
- rejection of missing resources, unsafe/symlink paths, duplicate patients, unknown patient keys, wrong headers, wrong encodings, malformed CSV, and schema-fingerprint drift;
- exact target semantics for demographics, recorded flags, utilization, observation availability/link incompleteness, age-window summaries, clean physiology, and suppression/rounding;
- exclusion of outlier/BIV-null values from physiology targets and separation of observation targets from physiology targets;
- canonical artifact/report bytes, aggregate hash stability, absence of patient/visit IDs and source paths, and no hidden truth in either output;
- CLI output lifecycle, key-file handling, output collision rejection, and no partial outputs after a failure; and
- structural regression proving that visible generator/exporter/trajectory modules do not import or consume the calibrator or its real-data path.

The full repository suite, Ruff, schema check, and whitespace check remain required. CI never runs with a real-data root or a real partition key.

## Documentation and deferred gates

`docs/synthetic-generator.md` gains a governed-calibration section with the command shape, required inputs, synthetic-only CI statement, target-family semantics, suppression behavior, and a warning that the artifact is not prevalence validation or privacy evidence. The section points to the held-out validation and privacy-audit roadmap items and explains that only an authorized operator may provide real calibration data.

This slice does not make the generator consume the artifact. The next calibration/fidelity slice can add compatibility checks, parameter fitting, held-out validation, temporal-drift metrics, and task-utility evaluation only after the artifact registry and governed report are reviewed. The later privacy slice remains responsible for linkage, membership, attribute-disclosure, composition, and optional differential-privacy decisions.

## Acceptance criteria

1. A supplied synthetic mock package with all eight resources produces a deterministic `calibration-artifact-v1` artifact and aggregate-only report.
2. Every released target is traceable to an approved registry definition, has support at or above policy minimum, and uses the correct family and age/sex stratum.
3. Small cells are suppressed without leaking their values, and no raw rows, sequences, identifiers, paths, or hidden truth appear in either output.
4. A malformed or non-patient-disjoint input fails before any artifact or report is promoted.
5. Identical approved inputs and metadata produce identical artifact/report bytes; changed snapshot, policy, key, or aggregate changes are visible through the appropriate identity/hash fields.
6. The implementation uses the existing artifact contract, preserves the offline generator boundary, and adds no real data or clinical reference table.
7. Full tests, Ruff, schema validation, and whitespace checks pass before merge; `main` and `origin/main` are equal after push.
