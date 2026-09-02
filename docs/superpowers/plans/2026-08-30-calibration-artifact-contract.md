# Aggregate Calibration Artifact Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a strict, disclosure-controlled aggregate calibration-artifact model and JSON loader that later synthetic calibration and generation work can consume without accepting real patient records or hidden evaluator truth.

**Architecture:** Keep the artifact boundary engine-neutral in `synthetic.calibration`. Frozen dataclasses validate the in-memory contract, normalize aggregate ordering, and emit canonical JSON; a separate path loader adds duplicate-key, encoding, file-type, and size guards before invoking the model. Documentation and structural tests make explicit that no visible generator, exporter, schema, manifest, or native trajectory path consumes the artifact in this slice.

**Tech Stack:** Python 3.12+, standard-library `dataclasses`, `collections.abc`, `datetime`, `json`, `math`, `os`, `pathlib`, `re`, and `stat`; pytest; Ruff; existing schema checker.

**Spec:** `docs/superpowers/specs/2026-08-30-calibration-artifact-contract-design.md`

## Global Constraints

- The only accepted version is `calibration-artifact-v1`; the only accepted `source_partition` is `calibration`.
- Top-level, policy, stratum, and target keys are exact; unknown keys, missing keys, duplicate JSON keys, and duplicate semantic strata/targets fail closed.
- The artifact contains aggregate scalar targets only: no patient rows, visit sequences, serialized examples, candidate links, hidden truth, real-data paths, or attack output.
- `source_aggregate_sha256` and `schema_fingerprint` are lowercase 64-character hexadecimal SHA-256 strings.
- `created_at` is a valid UTC timestamp in exact `YYYY-MM-DDTHH:MM:SSZ` form; tokens are ASCII-safe, bounded, path-free, and reject identity/serialized-record indicators.
- Strata use at most four allowlisted coarse dimensions and a canonical lexicographically ordered `key=value` `stratum_id` joined with `|`; strata and targets serialize in sorted order.
- Released targets meet `minimum_cell_count`; suppressed targets carry null value/support/denominator and `rounding_decimals: 0`, never numeric zero.
- Allowed families are `demographics`, `observation`, `physiology`, `utilization`, and `recorded_outcome`; allowed statistics are `count`, `proportion`, `mean`, `sd`, `quantile`, and `rate`.
- JSON loading is UTF-8 without BOM, rejects nonfinite constants and booleans in numeric positions, rejects symlinks/directories/special files, and reads no more than `MAX_CALIBRATION_ARTIFACT_BYTES = 4 * 1024 * 1024` plus one byte.
- `canonical_json()` uses `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)`; canonical output is provenance/reproducibility metadata, not a privacy guarantee.
- Do not add a real-data reader, DuckDB aggregation, prevalence estimator, generator integration, CLI, held-out validation, privacy audit, Synthea backend, CSV, manifest, descriptor, or clinical reference table.
- Tests and fixtures use only in-memory or temporary completely synthetic mappings/files; existing visible generation and schema behavior stay unchanged.

---

### Task 1: Implement the strict in-memory artifact model

**Files:**
- Create: `src/synthetic/calibration.py`
- Create: `tests/synthetic/test_calibration_artifact_model.py`

**Interfaces:**
- Produces `CalibrationDisclosurePolicy(policy_id: str, policy_version: str, minimum_cell_count: int, continuous_rounding_decimals: int)`.
- Produces `CalibrationTarget(target_name: str, family: str, statistic: str, unit: str, status: str, value: int | float | None, support_count: int | None, denominator: int | None, rounding_decimals: int, quantile_level: float | None = None)`.
- Produces `CalibrationStratum(stratum_id: str, dimensions: tuple[tuple[str, str], ...], targets: tuple[CalibrationTarget, ...])`.
- Produces `CalibrationArtifact(artifact_version: str, artifact_id: str, source_snapshot: str, source_partition: str, source_aggregate_sha256: str, schema_fingerprint: str, created_at: str, disclosure_policy: CalibrationDisclosurePolicy, strata: tuple[CalibrationStratum, ...])`.
- Produces `CalibrationArtifact.from_mapping(value: object) -> CalibrationArtifact` and `CalibrationArtifact.to_mapping() -> dict[str, object]`.
- Exposes `ARTIFACT_VERSION = "calibration-artifact-v1"`, `MAX_CALIBRATION_ARTIFACT_BYTES = 4 * 1024 * 1024`, and the allowlists needed by the loader task.

- [x] **Step 1: Write failing model tests**

Create a synthetic mapping helper whose only stratum is `age_regime=infancy|reference_sex=F` and whose released target is a physiology mean for `height_z`. Assert that parsing yields frozen dataclasses, tuple-backed strata/targets, canonical dimension ordering, and a newly allocated mapping:

```python
def test_valid_mapping_builds_frozen_artifact_and_canonical_shape() -> None:
    artifact = CalibrationArtifact.from_mapping(valid_mapping())

    assert artifact.artifact_version == "calibration-artifact-v1"
    assert artifact.strata[0].dimensions == (
        ("age_regime", "infancy"),
        ("reference_sex", "F"),
    )
    assert artifact.strata[0].stratum_id == "age_regime=infancy|reference_sex=F"
    assert artifact.strata[0].targets[0].value == -0.03
    assert artifact.to_mapping() == valid_mapping()
    assert artifact.to_mapping() is not artifact.to_mapping()


def test_mapping_normalizes_stratum_and_target_order() -> None:
    value = valid_mapping_with_strata_and_targets_in_reverse_order()

    artifact = CalibrationArtifact.from_mapping(value)

    assert [stratum.stratum_id for stratum in artifact.strata] == sorted(
        stratum["stratum_id"] for stratum in value["strata"]
    )
    assert [target.target_name for target in artifact.strata[-1].targets] == [
        "height_z",
        "visit_rate",
    ]
```

Add parametrized rejection tests for missing/unknown keys and wrong root/nested types; the test cases must include an extra top-level `source_path`, an extra target `patient_id`, an empty `strata` list, and a duplicate target name. Add strict-value tests for the wrong artifact version, non-calibration partition, uppercase/non-hex hash, malformed UTC timestamp, invalid token/path separator, reserved hidden-state dimension values, more than four dimensions, and a noncanonical `stratum_id`.

Add disclosure/statistic tests covering:

```python
def test_suppressed_target_is_explicitly_null_and_not_zero() -> None:
    value = valid_mapping()
    target = value["strata"][0]["targets"][0]
    target.update(
        statistic="proportion",
        status="suppressed",
        value=None,
        support_count=None,
        denominator=None,
        rounding_decimals=0,
    )

    parsed = CalibrationArtifact.from_mapping(value)

    assert parsed.strata[0].targets[0].value is None
    assert parsed.strata[0].targets[0].support_count is None


@pytest.mark.parametrize("statistic,value", [
    ("count", 1.5),
    ("proportion", 1.01),
    ("sd", -0.1),
    ("rate", -1.0),
])
def test_statistic_domains_fail_closed(statistic: str, value: object) -> None:
    mapping = valid_mapping_with_target(statistic=statistic, value=value)

    with pytest.raises(ValueError, match="value|statistic"):
        CalibrationArtifact.from_mapping(mapping)
```

The tests must also cover quantile-level presence/absence, minimum support, denominator positivity and support ordering, count rounding of zero, continuous precision bounds, positive policy minimum, boolean-as-number rejection, finite-number rejection, and family/name rejection for `latent`, `truth`, `patient`, `sequence`, `candidate`, `match`, `row`, and `resource` indicators.

- [x] **Step 2: Run the model tests to verify the red state**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_calibration_artifact_model.py`

Expected: collection/test failure because `synthetic.calibration` and its model API do not yet exist. Correct any test syntax or fixture errors before implementing the module.

- [x] **Step 3: Implement the frozen model and validators**

In `src/synthetic/calibration.py`:

1. Define the constants and immutable dataclasses above. Use `__post_init__` for basic type/domain checks and an artifact-level validator for policy-dependent disclosure checks. Treat booleans as invalid wherever an integer or finite number is required.
2. Define exact key sets for the top-level, policy, stratum, and target objects. `from_mapping` requires `collections.abc.Mapping`, checks string keys and exact sets, and never coerces values. It cannot recover duplicate keys from a Python mapping; the JSON loader in Task 2 supplies that guarantee.
3. Validate ASCII token regex `[A-Za-z0-9][A-Za-z0-9._:-]{0,127}` for artifact/snapshot/policy/target/unit values and the 63-character trailing variant for dimension values. Reject whitespace, `/`, `\\`, and case-insensitive indicators `patient`, `visit`, `identifier`, `uuid`, `sequence`, `truth`, `candidate`, `match`, `row`, and `resource`; allow the exact contract dimension keys even when their spelling contains an indicator.
4. Validate allowlisted dimensions, one-to-four dimensions, reserved hidden-state dimension values, canonical sorted `stratum_id`, unique strata, unique target names, and lexicographic normalization of strata/targets.
5. Validate target families/statistics/status, quantile-level shape, finite scalar values, count/proportion/sd/rate domains, support/denominator integers, minimum support, suppression nulls, rounding precision, and positive released denominators for proportion/rate. Normalize non-count values and quantile levels to finite floats while retaining integer count values.
6. Validate exact artifact version, calibration partition, lowercase 64-hex hashes, valid exact UTC timestamp, positive policy minimum, and policy precision `0..9`.
7. Implement `to_mapping()` with fresh dict/list containers, sorted dimensions, and omission of `quantile_level` except for quantile targets. Do not import or reference any generator, schema, manifest, native trajectory, CSV, DuckDB, or real-data module.

- [x] **Step 4: Run model tests and the synthetic regression suite**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_calibration_artifact_model.py tests/synthetic`

Expected: all new model tests and all pre-existing synthetic tests pass.

- [x] **Step 5: Review and commit the model task**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/calibration.py tests/synthetic/test_calibration_artifact_model.py` and `git diff --check`.

```bash
git add src/synthetic/calibration.py tests/synthetic/test_calibration_artifact_model.py
git commit -m "feat: add calibration artifact model"
```

### Task 2: Add the guarded JSON loader and canonical serialization

**Files:**
- Modify: `src/synthetic/calibration.py`
- Create: `tests/synthetic/test_calibration_artifact_loader.py`

**Interfaces:**
- Consumes the Task 1 `CalibrationArtifact.from_mapping` and `CalibrationArtifact.to_mapping` APIs.
- Produces `load_calibration_artifact(path: Path) -> CalibrationArtifact`.
- Produces `CalibrationArtifact.canonical_json() -> str` using the exact serialization arguments in the global constraints.

- [x] **Step 1: Write failing loader and serialization tests**

Use `tmp_path` and only synthetic JSON text. Assert that a valid file loads equal to the in-memory artifact and that canonical output is compact, ASCII, key-sorted, and stable regardless of input object/list ordering:

```python
def test_loader_and_canonical_json_are_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(json.dumps(valid_mapping()), encoding="utf-8")
    second.write_text(
        json.dumps(valid_mapping_with_strata_and_targets_in_reverse_order()),
        encoding="utf-8",
    )

    left = load_calibration_artifact(first)
    right = load_calibration_artifact(second)

    assert left == right
    assert left.canonical_json() == right.canonical_json()
    assert " " not in left.canonical_json()
    assert "\\n" not in left.canonical_json()
    assert "\\ud" not in left.canonical_json().lower()
```

Add tests that a duplicate key at the top level and in a nested target raises `ValueError`; JSON `NaN`, `Infinity`, `-Infinity`, a UTF-8 BOM, invalid UTF-8, and a non-object root raise `ValueError` without a parser traceback. Add path tests for a missing path, symlink, directory, FIFO/special file where supported, exact `MAX_CALIBRATION_ARTIFACT_BYTES` acceptance, and `MAX_CALIBRATION_ARTIFACT_BYTES + 1` rejection. Ensure a file that grows beyond the limit during reading is rejected by asserting the read path does not return a partial artifact.

- [x] **Step 2: Run loader tests to verify the red state**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_calibration_artifact_loader.py`

Expected: collection/test failure because `load_calibration_artifact` and `canonical_json` are not yet implemented. Correct only test fixture mistakes before adding the loader.

- [x] **Step 3: Implement guarded decoding and canonical output**

In `src/synthetic/calibration.py`:

1. Implement `load_calibration_artifact(path)` using `Path.lstat()` and `stat.S_ISREG`; reject a symlink, directory, or special file before opening. Check the initial size and read at most `MAX_CALIBRATION_ARTIFACT_BYTES + 1` bytes; reject an over-limit result so a file that grows after `stat` cannot bypass the cap. Convert `OSError`, `UnicodeError`, BOM detection, and JSON decode failures to field/rule-specific `ValueError` messages.
2. Decode strict UTF-8 without BOM. Pass an `object_pairs_hook` that raises on duplicate keys at every nesting level and a `parse_constant` hook that raises on nonfinite JSON constants. Require the decoded root to be a mapping, then call `CalibrationArtifact.from_mapping`.
3. Implement `canonical_json()` with exactly `json.dumps(self.to_mapping(), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)`. It returns the JSON string; all model numbers have already been normalized and no nonfinite value can serialize.
4. Keep loader/module imports standard-library only and preserve Task 1's strict model behavior. Do not add path, partition, row, or source-data fields to the schema.

- [x] **Step 4: Run loader, model, and full repository checks**

Run:

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_calibration_artifact_model.py tests/synthetic/test_calibration_artifact_loader.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests
python3 schema/build.py --check
git diff --check
```

Expected: all commands exit zero; the full suite retains the pre-task test count plus the new tests.

- [x] **Step 5: Review and commit the loader task**

Inspect `git diff --stat`, `git diff --cached --check`, and the changed file names, then run:

```bash
git add src/synthetic/calibration.py tests/synthetic/test_calibration_artifact_loader.py
git commit -m "feat: add guarded calibration artifact loader"
```

### Task 3: Document the boundary and prove no visible integration

**Files:**
- Modify: `docs/synthetic-generator.md`
- Create: `tests/synthetic/test_calibration_artifact_boundary.py`

**Interfaces:**
- Consumes `load_calibration_artifact` only in the documentation example and boundary tests.
- Produces a user-facing aggregate-artifact usage section and an AST-based structural assertion that visible generation/export/schema/manifest/native paths do not import or call the calibration loader.

- [x] **Step 1: Write failing boundary tests**

Create a test that walks these repository-relative paths: `src/synthetic/generate.py`, `src/synthetic/csv_package.py`, `src/synthetic/manifest.py`, `src/synthetic/schema_contract.py`, and every `src/synthetic/native/*.py`. Parse each file with `ast.parse` and fail if an import targets `synthetic.calibration` or if a call/name references `load_calibration_artifact`. Also add a documentation-presence test that requires the new section title and loader example; that assertion is the intentional red test because the section is not present yet.

```python
def test_visible_paths_do_not_import_or_call_calibration_loader() -> None:
    for path in visible_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assert not forbidden_calibration_import(tree), path
        assert not forbidden_calibration_call(tree), path


def test_docs_name_the_aggregate_only_boundary() -> None:
    text = (REPOSITORY_ROOT / "docs/synthetic-generator.md").read_text(encoding="utf-8")
    assert "Aggregate calibration artifacts (development boundary)" in text
    assert "load_calibration_artifact" in text
```

- [x] **Step 2: Run the boundary tests to verify the red state**

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_calibration_artifact_boundary.py`

Expected: the documentation-presence test fails because the section does not exist yet; the AST assertion may already pass because the visible paths are intentionally not integrated. Resolve only test setup errors before implementation.

- [x] **Step 3: Add the documentation and structural assertions**

In `docs/synthetic-generator.md`, add a concise section titled `Aggregate calibration artifacts (development boundary)` that shows:

```python
from pathlib import Path
from synthetic.calibration import load_calibration_artifact

artifact = load_calibration_artifact(Path("approved-calibration.json"))
print(artifact.artifact_id, len(artifact.strata))
```

State that the file is a disclosure-controlled aggregate from the governed `calibration` partition, that strict keys/types/tokens/support/suppression/file checks apply, that suppressed cells remain null, and that the loader does not read PPOC CSVs, calibrate prevalence, tune trajectories, validate clinical fidelity, prove non-matchability, or authorize release. State that generator consumption, held-out validation, privacy auditing, and an optional Synthea adapter are separate deferred gates.

Implement `visible_paths()` and AST helpers in the boundary test. Keep the check focused on imports and call/name references so documentation strings do not create false positives. Do not import calibration from `synthetic/__init__.py` or any visible runtime path.

- [x] **Step 4: Run the complete verification gate**

Run:

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests
python3 schema/build.py --check
git diff --check
```

Expected: all repository checks exit zero, the structural test confirms no visible integration, and the docs identify the slice as aggregate-only and uncalibrated.

- [x] **Step 5: Review and commit the boundary task**

Inspect the staged names/stat and whitespace, then run:

```bash
git add docs/synthetic-generator.md tests/synthetic/test_calibration_artifact_boundary.py
git commit -m "docs: document calibration artifact boundary"
```

## Final review and handoff

### Completion evidence

- Model, guarded loader, canonical serialization, documentation, and AST boundary tests are implemented and complete.
- Final adversarial review approved the metadata guards, UUID and embedded synthetic-ID rejection, pre-open regular-file check, controlled JSON errors, separator-obfuscated `row` rejection, and preservation of `growth_dx_flag`.
- Focused artifact model/loader/boundary suite: `137 passed`; broader calibration suite: `326 passed`; full repository suite: `2664 passed, 4 skipped`.
- Ruff, schema validation, lock validation, and `git diff --check` passed; the four skips are opt-in 10,000-member development scale tests.
- The contract remains aggregate-only; later governed calibration, native cohort consumption, held-out validation, privacy auditing, and optional Synthea work are separate roadmap gates.

- After Task 3, run the full test, Ruff, schema, and whitespace commands again from the feature worktree.
- Review the complete branch against the approved spec: no real-data reader or generator integration, no hidden truth transport, exact disclosure semantics, deterministic ordering/serialization, and bounded loader behavior.
- Remove generated `__pycache__` directories before reporting a clean worktree.
- Merge to `main` and push only after the final code review and verification gate; then verify `HEAD` equals `origin/main`.
