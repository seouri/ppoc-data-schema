# Governed Aggregate Calibration Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a governed, patient-disjoint aggregate calibrator that produces the existing disclosure-controlled calibration artifact and an aggregate-only report from an explicitly supplied eight-resource snapshot.

**Architecture:** Keep the existing `synthetic.calibration` artifact model as the export boundary. Add a small public orchestration module, a DuckDB-backed input/partition layer, a fixed target registry for demographics, recorded outcomes, utilization, observation, and clean growth summaries, and a report/serialization layer. The calibrator is only an offline tool with an explicit data root; visible generation never imports or consumes it. CI uses a wholly synthetic mock snapshot.

**Tech Stack:** Python 3.12+, DuckDB, standard-library `csv`/`json`/`hmac`/`hashlib`/`dataclasses`, pytest, Ruff, existing schema and run-directory utilities.

**Spec:** `docs/superpowers/specs/2026-08-31-governed-calibration-core-design.md`

## Global Constraints

- `datapackage.json` remains the sole schema authority; the supplied source descriptor must have the same schema fingerprint and exact eight resources.
- The data root, descriptor, snapshot, partition policy, disclosure policy, creation timestamp, and partition key are explicit inputs; there is no default real-data path.
- The HMAC partition key is process-only and never appears in an artifact, report, manifest, identifier, exception, or log.
- All rows for one patient stay in one internal `calibration` or `held_out` partition; patient IDs never leave governed process memory.
- Outputs contain only disclosure-controlled aggregate targets and aggregate validation metadata; no rows, sequences, identifiers, source paths, candidate links, or hidden truth.
- Physiological summaries use clean non-null derived values and exclude outlier/BIV-invalid observations; observation error is a separate target family.
- Suppressed targets remain null and are never converted to zero or silently used as a generator fallback.
- The existing `calibration-artifact-v1` model and loader remain strict and unchanged except where tests expose a directly relevant compatibility defect.
- The normal generator/exporter/trajectory paths must not import or call the calibrator or accept a real-data path.
- Failed runs must not promote partial output; existing output directories and files are never overwritten.
- Every task ends with focused tests, Ruff for touched files, `git diff --check`, and a scoped commit.

---

### Task 1: Add calibrator models, dependency, and synthetic snapshot fixture

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/synthetic/calibrate.py`
- Create: `tests/synthetic/calibration_fixtures.py`
- Create: `tests/synthetic/test_calibrate_models.py`

**Interfaces:**
- Consumes: `CalibrationDisclosurePolicy` from `synthetic.calibration`, `schema_fingerprint` from `synthetic.schema_contract`.
- Produces: immutable `PartitionPolicy`, `CalibrationAgeWindow`, `CalibrationRunConfig`, `CalibrationCheck`, `CalibrationReport`, `CalibrationResult`, `DEFAULT_AGE_WINDOWS`, and public `calibrate`/`write_calibration_result`/`main` names (the orchestration bodies may initially raise `NotImplementedError` until later tasks).

- [ ] **Step 1: Add the DuckDB runtime dependency and create a failing model test**

Add `duckdb>=1.3,<2` to `[project].dependencies` and refresh the lock with `uv lock`. Write tests that instantiate valid policies/windows/configuration and reject booleans, nonpositive counts, basis points outside `1..9999`, empty keys, overlapping windows, malformed tokens, empty key bytes, and invalid UTC timestamps. Use exact expected values:

```python
def test_partition_policy_uses_explicit_basis_points() -> None:
    policy = PartitionPolicy("partition-v1", "1", "key-2026", 8_000, 2)
    assert policy.calibration_basis_points == 8_000
    assert policy.minimum_partition_patients == 2

def test_default_windows_are_ordered_observation_bins() -> None:
    assert [window.window_id for window in DEFAULT_AGE_WINDOWS] == [
        "infancy", "childhood", "puberty_window", "adolescence"
    ]
    assert DEFAULT_AGE_WINDOWS[0].lower_age_days == 0
    assert DEFAULT_AGE_WINDOWS[-1].upper_age_days == 7_305
```

- [ ] **Step 2: Run the focused test to verify the new API fails**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_calibrate_models.py`

Expected: collection failure because `synthetic.calibrate` and its models do not exist. Fix test syntax or fixture imports before implementing the API.

- [ ] **Step 3: Implement immutable models and validation**

In `src/synthetic/calibrate.py`, define:

```python
@dataclass(frozen=True)
class PartitionPolicy:
    policy_id: str
    policy_version: str
    key_id: str
    calibration_basis_points: int
    minimum_partition_patients: int

@dataclass(frozen=True)
class CalibrationAgeWindow:
    window_id: str
    lower_age_days: int
    upper_age_days: int

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
```

Validate identifiers with the same ASCII token rules used by the artifact model, require `Path` values without resolving away an explicit input, require at least 16 `bytes` key bytes, validate exact UTC timestamps with `datetime`, and enforce ordered non-overlapping age windows. Set `DEFAULT_AGE_WINDOWS` to `infancy 0..730`, `childhood 730..3287`, `puberty_window 3287..5479`, and `adolescence 5479..7306` using inclusive lower/exclusive upper bounds. Define `CalibrationCheck(name, passed, detail)` with aggregate detail only.

Define `CalibrationReport` as a frozen object whose mapping contains exactly `report_version`, `status`, `source_snapshot`, `schema_fingerprint`, `partition_policy`, `partition_counts`, `resource_row_counts`, `target_family_counts`, `suppression_counts`, `source_aggregate_sha256`, and `checks`. Its `canonical_json()` uses sorted keys, compact separators, ASCII JSON, and a trailing newline only in `to_json_bytes()`; reject patient/visit/path/key fields in report construction. Define `CalibrationResult(artifact, report)` and placeholders for `calibrate` and `write_calibration_result` that raise a clear “calibrator is not assembled” error until Task 5.

- [ ] **Step 4: Build a reusable exact-schema synthetic snapshot fixture**

In `tests/synthetic/calibration_fixtures.py`, add `write_mock_snapshot(root: Path, *, patient_count: int = 12) -> Path`. Load the checked-in descriptor, write all eight resources with `csv.DictWriter`, exact descriptor field order/dialect/encoding, and no real data. Include enough varied rows to exercise F/M/U sex, ethnicity/race categories, empty race positions, visits in every default age window, nullable weights/heights/head circumferences/BMI, `patients_augmented` flags and `dx_age_years`, clean and outlier `visits_augmented` z/velocity values, encounter types from the approved registry, and null/non-null logical visit IDs for labs/medications/referrals. Keep all identifiers deterministic fictional tokens such as `SYN-P-001` and `SYN-V-001`.

- [ ] **Step 5: Run model tests, lint, and commit**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_calibrate_models.py`; `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/calibrate.py tests/synthetic/test_calibrate_models.py tests/synthetic/calibration_fixtures.py`; `git diff --check`.

Expected: all focused tests pass. Commit:

```bash
    git add pyproject.toml uv.lock src/synthetic/calibrate.py tests/synthetic/test_calibrate_models.py tests/synthetic/calibration_fixtures.py
git commit -m "build: add calibration run models"
```

### Task 2: Validate the descriptor, load governed relations, and enforce partitions

**Files:**
- Create: `src/synthetic/calibration_input.py`
- Create: `tests/synthetic/test_calibration_input.py`
- Modify: `src/synthetic/calibrate.py`

**Interfaces:**
- Consumes: `CalibrationRunConfig`, `PartitionPolicy`, and `CalibrationAgeWindow` from `synthetic.calibrate`; existing `load_descriptor`, `field_names`, `resource_spec`, and `schema_fingerprint` helpers.
- Produces: `PartitionLabel`, `PartitionSummary`, `CalibrationInput`, `assign_partition(patient_id, policy, key)`, and `prepare_input(connection, config) -> CalibrationInput`.

- [ ] **Step 1: Write failing input/partition tests**

Using `write_mock_snapshot`, test that `assign_partition` is stable for repeated calls, changes when the key changes, returns only `calibration`/`held_out`, and never exposes the digest. Test `prepare_input` returns the repository schema fingerprint, counts both partitions, reports per-resource row counts, and leaves no patient IDs in `PartitionSummary` or `CalibrationInput` mappings. Add rejection cases for a missing resource, symlink resource, absolute/parent path, wrong header, duplicate patient, unknown patient in any resource, malformed required age, partition key too short, and a policy that leaves either partition below its minimum.

```python
def test_prepare_input_proves_all_rows_use_one_patient_partition(tmp_path: Path) -> None:
    root = write_mock_snapshot(tmp_path / "snapshot")
    config = test_config(root)
    with duckdb.connect(":memory:") as connection:
        prepared = prepare_input(connection, config)
    assert set(prepared.partition_summary.patient_counts) == {"calibration", "held_out"}
    assert all(value >= 2 for value in prepared.partition_summary.patient_counts.values())
    assert "SYN-P-001" not in json.dumps(prepared.partition_summary.to_mapping())
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_calibration_input.py`

Expected: collection failure because `synthetic.calibration_input` and `prepare_input` do not exist.

- [ ] **Step 3: Implement safe descriptor and relation loading**

Create `calibration_input.py` with immutable summaries and private helpers. Require the descriptor's resource name set to equal the eight required names and compare its fingerprint to the checked-in repository descriptor fingerprint. Validate each declared relative path below `data_root` without following symlinks; open each file once with strict descriptor encoding/dialect and `csv.reader(strict=True)` to verify exact headers before registering it with DuckDB. Use all-varchar staging so empty strings remain distinguishable from nulls. Use quoted/parameterized DuckDB paths and no user-controlled SQL identifiers.

Read `patients` first, reject empty or duplicate `patient_id`, compute `assign_partition` with `hmac.new(key, patient_id.encode("utf-8"), hashlib.sha256).digest()`, interpret the digest as a big-endian integer, and use modulo 10,000 against `calibration_basis_points`. Create a temporary `patient_partitions(patient_id, partition_label)` relation only inside the connection. For each remaining resource, verify nonempty `patient_id` and a complete join to the patient relation; preserve nullable `visit_id` only where the descriptor permits it. Validate required numeric fields with `try_cast` checks and reject malformed values rather than treating them as missing. Compute aggregate patient counts and per-resource row counts by partition without returning identifiers. Keep row-grain checks to the declared primary key: duplicate declared primary keys fail, while nullable logical visit links are counted later.

Define `CalibrationInput` with `descriptor`, `schema_fingerprint`, `partition_summary`, and `resource_names`; do not include the connection, key, data root, or identifier collections. Ensure all raised `ValueError` messages name only the resource/field/policy, never a patient or visit value.

- [ ] **Step 4: Wire the input API into calibrate imports and run tests**

Export the input types/functions from `synthetic.calibrate` only as named imports needed by downstream tasks; do not import them into generation modules. Run focused tests and lint:

```bash
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_calibration_input.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/calibration_input.py src/synthetic/calibrate.py tests/synthetic/test_calibration_input.py
git diff --check
```

- [ ] **Step 5: Commit**

```bash
git add src/synthetic/calibration_input.py src/synthetic/calibrate.py tests/synthetic/test_calibration_input.py
git commit -m "feat: enforce governed calibration partitions"
```

### Task 3: Compute the fixed aggregate target registry with DuckDB

**Files:**
- Create: `src/synthetic/calibration_targets.py`
- Create: `tests/synthetic/test_calibration_targets.py`
- Modify: `src/synthetic/calibrate.py`

**Interfaces:**
- Consumes: `CalibrationInput`, the live DuckDB connection containing validated relations, `CalibrationRunConfig`, and `CalibrationAgeWindow`.
- Produces: `RawTarget`, `TARGET_REGISTRY_VERSION`, approved category/encounter registries, and `compute_raw_targets(connection, prepared, config) -> tuple[RawTarget, ...]`.

- [ ] **Step 1: Define target metadata and write failing semantic tests**

Define:

```python
@dataclass(frozen=True)
class RawTarget:
    stratum_id: str
    dimensions: tuple[tuple[str, str], ...]
    target_name: str
    family: str
    statistic: str
    unit: str
    value: int | float
    support_count: int
    denominator: int | None
    quantile_level: float | None = None
```

Tests should assert the mock snapshot produces deterministic targets for sex, ethnicity/race and multiselect demographics; all recorded flags; visit count/span and encounter/Epic proportions; weight/height/head-circumference/BMI availability and nullable logical visit links; and physiology mean/sd/quantiles by default age window and recorded sex. Assert that `target_name` values never contain record/hidden/attack indicators, every stratum ID is canonical, and only approved encounter categories are accepted.

- [ ] **Step 2: Run target tests to verify they fail**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_calibration_targets.py`

Expected: collection failure because `synthetic.calibration_targets` does not exist.

- [ ] **Step 3: Implement the versioned registry and SQL aggregations**

In `calibration_targets.py`, define `TARGET_REGISTRY_VERSION = "calibration-targets-v1"`, explicit mappings for every descriptor ethnicity/race value (including blank/nonresponse labels), all descriptor encounter types, the seven recorded flag columns, the four measurement availability columns, three logical-link resources, and five physiology metrics. Map category slugs through constants; reject an observed category not in a registry rather than generating a target name from it.

Use DuckDB CTEs over the partitioned relations. Build:

1. patient-level proportions in `outcome_layer=observed` for demographics, multiselect race, and recorded flags;
2. patient-level visit-count/span means and `0.5`/`0.9` quantiles in `visit_window=all`;
3. visit-level encounter and Epic-origin proportions, plus age-windowed inter-visit intervals using `lag(age_in_days) over (partition by patient_id order by age_in_days, visit_id)`;
4. age-windowed measurement-availability proportions and nullable logical-link proportions; and
5. clean physiology summaries in `age_regime=<window>|recorded_sex=<sex>` from `visits_augmented`, joining demographics from `patients`, using `try_cast`, non-null derived values, and corresponding outlier flags not equal to `1`. Exclude BIV-null values and do not aggregate raw height/weight tails. Use DuckDB `quantile_cont` and sample standard deviation only when support is at least two; otherwise emit no raw target and let the report count the absent registry cell.

For proportions, `support_count` is the positive category/flag/link numerator and `denominator` is the eligible unit count; for means/sd/quantiles, `support_count` is the number of finite contributors and `denominator` is null. For visit-level targets, the eligible unit is a visit; for patient-level targets, it is a patient. Sort raw targets by canonical `stratum_id`, `target_name`, and statistic before returning. Do not return patient identifiers, SQL rows, or sequences.

- [ ] **Step 4: Verify exact semantics and boundary behavior**

Run:

```bash
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_calibration_targets.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/calibration_targets.py src/synthetic/calibrate.py tests/synthetic/test_calibration_targets.py
git diff --check
```

Add regressions for outlier exclusion, BIV-null exclusion, empty demographic values, age lower/upper boundaries, zero positive-category support, unknown encounter category, and no accidental target names containing `patient`, `visit`, `row`, `sequence`, `truth`, `candidate`, or privacy-attack indicators.

- [ ] **Step 5: Commit**

```bash
git add src/synthetic/calibration_targets.py src/synthetic/calibrate.py tests/synthetic/test_calibration_targets.py
git commit -m "feat: compute governed calibration targets"
```

### Task 4: Apply disclosure controls and construct aggregate-only artifact/report

**Files:**
- Create: `src/synthetic/calibration_disclosure.py`
- Create: `tests/synthetic/test_calibration_disclosure.py`
- Modify: `src/synthetic/calibrate.py`

**Interfaces:**
- Consumes: `RawTarget`, `CalibrationRunConfig`, `CalibrationInput`, and existing `CalibrationArtifact`, `CalibrationStratum`, and `CalibrationTarget` models.
- Produces: `disclose_targets(raw_targets, config) -> tuple[CalibrationStratum, ...]`, `build_result(strata, prepared, config) -> CalibrationResult`, and canonical aggregate hashing/report serialization.

- [ ] **Step 1: Write failing suppression, rounding, and hash tests**

Construct `RawTarget` values with support below and above `minimum_cell_count`, continuous values requiring rounding, counts, proportions, means, and quantiles. Assert suppressed artifact targets have null value/support/denominator and zero rounding precision; released continuous targets use policy precision; proportions remain in `[0, 1]`; and identical disclosed targets yield identical lowercase SHA-256 hashes regardless of input order. Assert report JSON contains no patient/visit IDs, source path, key ID material, or target-level supports.

- [ ] **Step 2: Run focused tests to verify they fail**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_calibration_disclosure.py`

Expected: collection failure because disclosure helpers do not exist.

- [ ] **Step 3: Implement disclosure and artifact construction**

Implement support suppression before rounding. For released count values require a nonnegative integer and zero rounding decimals; for continuous values use the existing policy precision and reject nonfinite values. Build canonical dimensions/targets through `CalibrationStratum` and `CalibrationTarget`, preserving sorted order and exact artifact-model constraints. For a suppressed raw target create a `CalibrationTarget(status="suppressed", value=None, support_count=None, denominator=None, rounding_decimals=0)`.

Create a canonical aggregate payload from only disclosed stratum/target mappings with sorted keys and compact ASCII JSON, hash it with SHA-256, and pass the digest to `CalibrationArtifact` with `source_partition="calibration"`, the prepared schema fingerprint, configured snapshot/artifact ID/timestamp, and configured disclosure policy. Build `CalibrationReport` with `status="AGGREGATES_ONLY"`, aggregate partition/resource counts, target-family and suppression totals, the same hash, and checks for schema, partition, target registry, and disclosure pass. Report only family-level counts; never copy `RawTarget.support_count` or `.denominator` into report JSON.

- [ ] **Step 4: Verify disclosure and artifact compatibility**

Run focused tests, all existing calibration-artifact tests, Ruff, and whitespace:

```bash
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_calibration_disclosure.py tests/synthetic/test_calibration_artifact_model.py tests/synthetic/test_calibration_artifact_loader.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/calibration_disclosure.py src/synthetic/calibrate.py tests/synthetic/test_calibration_disclosure.py
git diff --check
```

- [ ] **Step 5: Commit**

```bash
git add src/synthetic/calibration_disclosure.py src/synthetic/calibrate.py tests/synthetic/test_calibration_disclosure.py
git commit -m "feat: disclose aggregate calibration artifacts"
```

### Task 5: Assemble the calibrator, add transactional CLI output, and document usage

**Files:**
- Modify: `src/synthetic/calibrate.py`
- Create: `tests/synthetic/test_calibrate_integration.py`
- Create: `tests/synthetic/test_calibrate_cli.py`
- Modify: `tests/synthetic/test_calibration_artifact_boundary.py`
- Modify: `docs/synthetic-generator.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: `prepare_input`, `compute_raw_targets`, `disclose_targets`, `build_result`, `CalibrationRunConfig`, and existing `RunDirectory`.
- Produces: working `calibrate(config)`, `write_calibration_result(result, output)`, and `python -m synthetic.calibrate` behavior.

- [ ] **Step 1: Write failing end-to-end and CLI tests**

With `write_mock_snapshot`, call `calibrate(test_config(root))` and assert both partitions meet policy, the artifact validates through `CalibrationArtifact.from_mapping`, report status is `AGGREGATES_ONLY`, and repeated calls have identical artifact/report bytes. Add a CLI test that writes a key file, runs all required explicit flags, and checks only `calibration-artifact.json` and `calibration-report.json` appear under the new output. Test existing output collision, missing key/flag, malformed snapshot, and failure leaves no promoted output. Assert `generate.py`, `base_resources.py`, `csv_package.py`, and native trajectory modules do not import `synthetic.calibrate` or `synthetic.calibration_input`.

- [ ] **Step 2: Run integration tests to verify assembly is incomplete**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_calibrate_integration.py tests/synthetic/test_calibrate_cli.py`

Expected: failures because `calibrate` still has the Task 1 placeholder and CLI parsing/output are not assembled.

- [ ] **Step 3: Implement orchestration and fail-closed output**

In `calibrate`, validate the config, open a private in-memory DuckDB connection, call `prepare_input`, call `compute_raw_targets`, call `build_result`, and assert report/artifact aggregate hashes match before returning. Close the connection before returning. Do not import `load_calibration_artifact` and do not expose the connection or key.

Implement `write_calibration_result` with `RunDirectory.start(output, result.artifact.artifact_id)`. Write canonical artifact bytes and report bytes into the partial directory with exclusive creation, promote only after both files are flushed and reparsed successfully, and call `fail` with an aggregate reason on any exception. Refuse output paths that are existing directories, files, symlinks, or contain reserved files. Ensure failure messages contain no data root or identifiers.

Implement `argparse` flags exactly as specified by the design. Load partition/disclosure policy JSON with strict duplicate-key decoding, load the partition key as exact bytes from a regular non-symlink file, require explicit `--created-at` and `--snapshot`, and use `DEFAULT_AGE_WINDOWS` unless a future versioned age-window file is explicitly added. Do not accept `--real-data`, hidden truth, patient partition files, or generator output paths as alternate inputs.

- [ ] **Step 4: Update docs and boundary tests**

Document the governed-only command, key-file handling, synthetic-only CI, target families, suppression semantics, report status, and the fact that this is not prevalence validation, clinical validation, privacy evidence, or release authorization. Keep the existing generator examples unchanged and state that no visible generator path consumes the artifact. Extend the AST boundary test to reject imports/calls to `synthetic.calibrate`, `synthetic.calibration_input`, and `prepare_input` from visible generation/export/trajectory modules while allowing the calibrator package itself.

- [ ] **Step 5: Run task tests, full suite, lint, schema, and commit**

Run:

```bash
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_calibrate_integration.py tests/synthetic/test_calibrate_cli.py tests/synthetic/test_calibration_artifact_boundary.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests
python3 schema/build.py --check
git diff --check
```

Expected: all tests pass, schema validation reports eight resources, and Ruff/whitespace are clean. Commit:

```bash
git add src/synthetic/calibrate.py src/synthetic/calibration_input.py src/synthetic/calibration_targets.py src/synthetic/calibration_disclosure.py tests/synthetic docs/synthetic-generator.md README.md
git commit -m "feat: add governed aggregate calibrator"
```

### Task 6: Independent final review and integration evidence

**Files:**
- Review only: all files changed by Tasks 1–5 and the design/plan documents.
- Modify only through the implementer if review finds a defect; never patch a reviewer finding directly in the controller.

**Interfaces:**
- Consumes: the complete feature branch and task review reports.
- Produces: final review report, clean verification evidence, and a merge-ready branch.

- [ ] **Step 1: Run the repository’s task-level and whole-branch review workflows**

For each task, inspect the diff against its brief, run the focused tests, and record findings in the SDD ledger. Then run a fresh final review covering: exact schema/header/encoding checks, keyed partition non-leakage, no identifier/path/key output, target registry completeness, clean physiology versus observation separation, disclosure behavior, hash determinism, CLI no-overwrite lifecycle, generator boundary, dependency lock, documentation claims, and all acceptance criteria in the spec.

- [ ] **Step 2: Resolve findings through scoped implementer follow-ups**

If a reviewer reports a real defect, dispatch the responsible implementer with the exact file/line, failing test or reproduction, and requested regression. Re-run the scoped review after each fix. Do not broaden target families, add real data, or weaken suppression/path/partition controls to make a test pass.

- [ ] **Step 3: Run final verification before integration**

Run the full pytest suite, Ruff, schema check, `git diff --check`, and a clean-tree check. Confirm the feature branch contains only the governed calibrator slice and its tests/docs. Check that no files under a real-data root, key material, patient partition, generated artifact, or temporary output are staged.

- [ ] **Step 4: Merge, push, and verify remote parity**

Using the finishing-development-branch workflow, update local `main` fast-forward-only, merge the feature branch with the repository’s normal merge style, rerun full verification on merged `main`, push `origin main`, and verify `git rev-parse HEAD` equals `git rev-parse origin/main`. Remove the clean feature worktree and branch only after remote parity is confirmed.
