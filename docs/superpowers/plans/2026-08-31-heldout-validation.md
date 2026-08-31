# Patient-Disjoint Held-Out Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Goal: Compare a completely generated exact-schema package with a keyed, patient-disjoint held-out snapshot partition under a frozen aggregate fidelity policy, producing only deterministic aggregate evidence.

Architecture: Keep validation in a standalone synthetic.heldout_validate module. Reuse the governed calibration input/staging helpers and fixed DuckDB target registry, adding only a validated partition-label parameter and a synthetic-package staging path. Compare disclosure-controlled target cells against a strict FidelityPolicy, serialize a redacted aggregate report plus human summary transactionally, and leave generation/calibration APIs unable to consume held-out reports.

Tech Stack: Python 3.12+, DuckDB, standard-library csv/json/hashlib/math/os/dataclasses, existing calibration artifact/disclosure models, RunDirectory, pytest, Ruff.

Spec: docs/superpowers/specs/2026-08-31-heldout-validation-design.md

## Global Constraints

- datapackage.json remains the sole schema authority; real and generated descriptors must have the repository fingerprint and exact eight resources.
- Real root, real descriptor, snapshot, synthetic root, calibration artifact, calibration report, partition policy, disclosure policy, partition key, frozen fidelity policy, and output are explicit inputs; library callers provide age windows explicitly and the CLI uses the checked-in DEFAULT_AGE_WINDOWS registry; there is no default data path or patient partition file.
- The HMAC partition key and every patient/visit row remain process-local; no key, identifier, support, denominator, raw category, candidate link, sequence, or hidden truth appears in report, summary, error, filename, or manifest.
- The real target set uses only partition_label="held_out"; the synthetic target set stages every generated patient under an internal calibration label and never mixes the two connections.
- The existing fixed target registry, calibration-artifact-v1 loader, disclosure suppression, and clean physiology rules remain authoritative; no arbitrary SQL or columns are accepted.
- A frozen policy is loaded before comparison and is never learned from held-out values; no validator output reaches generation or tuning code.
- Missing, suppressed, or underpowered cells are UNEVALUABLE, never zero or PASS; evaluable out-of-tolerance cells are FAIL.
- Hard input/compatibility failures promote no report; comparison FAIL/UNEVALUABLE reports are valid aggregate evidence and exit the CLI with a nonzero gate status after promotion.
- Existing output/lifecycle paths are never overwritten. JSON is strict, canonical sorted ASCII with a trailing newline; all touched files pass Ruff, tests, git diff --check, and schema checks.

---

### Task 1: Parameterize the target registry and add secure synthetic staging

Files:
- Modify: src/synthetic/calibration_targets.py
- Modify: src/synthetic/calibration_input.py
- Modify: src/synthetic/calibrate.py
- Create: tests/synthetic/test_heldout_target_scope.py
- Modify: tests/synthetic/calibration_fixtures.py
- Create: tests/synthetic/heldout_fixtures.py

Interfaces:
- Consumes: existing CalibrationInput, CalibrationRunConfig, RawTarget, prepare_input, and exact descriptor helpers.
- Produces: compute_raw_targets(connection, prepared, config, *, partition_label="calibration") -> tuple[RawTarget, ...]; prepare_synthetic_input(connection, package_root, descriptor) -> CalibrationInput; and a test helper that writes an x-synthetic: true descriptor around fictional exact-schema rows.

- [ ] Step 1: Write failing partition-label and staging tests

Add tests proving that compute_raw_targets(..., partition_label="held_out") excludes calibration patients while the default continues to select calibration patients. Pass a deliberately invalid label ("all") and assert ValueError. Create a fictional package with datapackage.json, x-synthetic: true, and all eight resource files, call prepare_synthetic_input, and assert that its CalibrationInput exposes only aggregate metadata while the connection has every generated patient under the internal calibration label. Assert a descriptor without x-synthetic: true, a symlinked descriptor/resource, a path traversal, a duplicate primary key, and an unknown patient fail without leaking a patient token in the exception.

~~~
def test_target_registry_can_select_held_out_without_mixing_partitions(tmp_path: Path) -> None:
    root = write_mock_snapshot(tmp_path / "snapshot", patient_count=12)
    config = test_config(root)
    with duckdb.connect(":memory:") as connection:
        prepared = prepare_input(connection, config)
        held_out = compute_raw_targets(connection, prepared, config, partition_label="held_out")
        calibration = compute_raw_targets(connection, prepared, config)
    assert held_out
    assert calibration
    assert held_out != calibration
    assert all("patient_id" not in target.stratum_id for target in held_out)
~~~

- [ ] Step 2: Run focused tests to verify the new APIs fail

Run: UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_heldout_target_scope.py

Expected: collection or call failure because compute_raw_targets has no partition_label keyword and prepare_synthetic_input is absent. Fix only test import/setup errors before implementation.

- [ ] Step 3: Refactor target SQL to use a validated parameter

Add a private _require_partition_label accepting exactly "calibration" and "held_out". Thread partition_label through _patient_targets, _utilization_targets, _age_window_targets, and _physiology_targets, defaulting each to "calibration". Replace every fixed partitions.partition_label = 'calibration' predicate with partitions.partition_label = ? and pass the label in the same parameter tuple as age bounds. Keep all relation/table names fixed literals, retain category allowlists and clean-physiology predicates, and keep the public default behavior byte-for-byte equivalent. Reject non-string/unknown labels before any query runs.

- [ ] Step 4: Factor exact-schema staging and implement synthetic staging

In calibration_input.py, factor the shared descriptor/path/header/all-varchar relation validation into a private helper that accepts a descriptor mapping and data root. Keep prepare_input using the HMAC assignment and minimum partition checks. Add prepare_synthetic_input that requires a Path package root, a mapping with x-synthetic is True, the exact eight resource set, and the repository schema fingerprint; stages and validates all resources through the shared helper; rejects a symlinked or non-regular package descriptor/resource; inserts every validated patient into patient_partitions with label calibration; computes aggregate row counts without enforcing a held-out minimum; and returns CalibrationInput without identifiers, paths, key bytes, or connections. Add a secure package descriptor reader in the held-out fixture/module boundary rather than following Path.read_text on a symlink.

In tests/synthetic/calibration_fixtures.py, add an optional write_synthetic_descriptor(root) helper that calls write_synthetic_descriptor with the checked-in descriptor and fictional row counts. In tests/synthetic/heldout_fixtures.py, add write_synthetic_package(root, patient_count=12, id_prefix="GEN") that writes independent identifiers and the generated descriptor marker using the existing fictional row builder; do not copy any real snapshot bytes.

- [ ] Step 5: Run target/staging tests, lint, and commit

Run:

~~~
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_heldout_target_scope.py tests/synthetic/test_calibration_input.py tests/synthetic/test_calibration_targets.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/calibration_targets.py src/synthetic/calibration_input.py src/synthetic/calibrate.py tests/synthetic/test_heldout_target_scope.py tests/synthetic/heldout_fixtures.py
git diff --check
~~~

Expected: focused tests pass and the existing calibration suite remains green. Commit:

~~~
git add src/synthetic/calibration_targets.py src/synthetic/calibration_input.py src/synthetic/calibrate.py tests/synthetic/test_heldout_target_scope.py tests/synthetic/calibration_fixtures.py tests/synthetic/heldout_fixtures.py
git commit -m "feat: scope calibration targets to held-out partitions"
~~~

### Task 2: Add strict frozen fidelity policy and aggregate comparison models

Files:
- Create: src/synthetic/heldout_validate.py
- Create: tests/synthetic/test_heldout_policy.py
- Create: tests/synthetic/test_heldout_comparison.py

Interfaces:
- Consumes: RawTarget, disclosed CalibrationStratum/CalibrationTarget, FidelityPolicy JSON, and TARGET_REGISTRY_VERSION.
- Produces: immutable FidelityPolicy, HeldoutComparison, HeldoutCheck, and HeldoutValidationReport; strict load_fidelity_policy(path), compare_targets(heldout_strata, synthetic_strata, policy), and canonical report serialization. No CLI or filesystem promotion is added in this task.

- [ ] Step 1: Write failing model/policy/comparison tests

Create a valid policy mapping with exact keys:

~~~
{
  "policy_id": "fidelity-v1",
  "policy_version": "1",
  "target_registry_version": "calibration-targets-v1",
  "minimum_evaluable_support": 2,
  "proportion_floor": 0.05,
  "proportion_z_score": 2.0,
  "continuous_tolerances": {
    "demographics": 0.05,
    "observation": 0.10,
    "physiology": 1.0,
    "utilization": 10.0,
    "recorded_outcome": 0.05
  },
  "count_abs_tolerance": 1,
  "required_families": ["demographics", "observation", "physiology", "utilization", "recorded_outcome"],
  "max_unevaluable_targets": 0
}
~~~

Test strict parsing (duplicate/unknown/missing keys, nonfinite numbers, unsafe tokens, wrong family map, booleans, negative values, duplicate/unknown required families, and registry drift). Build disclosed strata with released, suppressed, missing, proportion, count, mean, sd, and quantile targets. Assert comparisons use canonical matching, the size-aware proportion formula, family tolerances, count tolerance, and post-disclosure values. Assert missing/suppressed/under-support targets become UNEVALUABLE with all comparison values null, and an out-of-tolerance released target becomes FAIL. Assert required-family absence is UNEVALUABLE, and the report contains no supports/denominators or fictional IDs/paths.

- [ ] Step 2: Run policy/comparison tests to verify they fail

Run: UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_heldout_policy.py tests/synthetic/test_heldout_comparison.py

Expected: collection failure because synthetic.heldout_validate and its models do not exist.

- [ ] Step 3: Implement strict policy parsing and immutable models

In heldout_validate.py, define exact key sets and strict duplicate-key/nonfinite-constant JSON loaders using secure regular non-symlink reads, bounded to 1 MiB. Implement FidelityPolicy validation exactly as the spec: aggregate-safe token IDs, exact five-family tolerance map, positive minimum support/z-score, floor in [0,1], nonnegative count/unevaluable limits, and canonical required-family tuple. Implement HeldoutComparison with aggregate-safe target metadata, status in PASS/FAIL/UNEVALUABLE, optional finite disclosed values/difference/tolerance, and null values whenever status is UNEVALUABLE. Implement HeldoutCheck(name, passed, detail) with the existing aggregate report token/detail rules.

- [ ] Step 4: Implement fixed target matching, tolerance, and report serialization

Index targets by (stratum_id, target_name, family, statistic, unit, quantile_level). For every union key, mark UNEVALUABLE when either side is absent/suppressed, either released support is below policy minimum, a required denominator is absent, or a required family has no evaluable cell. Otherwise compute the absolute difference after disclosure rounding. Use:

~~~
se = max(
    math.sqrt(p_real * (1 - p_real) / n_real),
    math.sqrt(p_synthetic * (1 - p_synthetic) / n_synthetic),
)
tolerance = max(policy.proportion_floor, policy.proportion_z_score * se)
~~~

for proportions; use count_abs_tolerance for counts and continuous_tolerances[family] for all other statistics. Mark PASS for difference <= tolerance, else FAIL. Compute global status as FAIL if any failure, else UNEVALUABLE if unevaluable count exceeds the policy allowance or a required family has no evaluable cell, else PASS.

Define HeldoutValidationReport with exactly the spec's top-level keys, status, source/synthetic identity fields, policy identity mappings without paths/key IDs, aggregate hashes, status/family counts, checks, and sorted comparisons. Serialize only disclosed values; omit supports/denominators. Use canonical compact sorted ASCII JSON and a trailing newline. Add a human-summary formatter that emits status, policy IDs/versions, hashes, status/family counts, and check details but never target values or row data.

- [ ] Step 5: Run tests, lint, and commit

Run:

~~~
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_heldout_policy.py tests/synthetic/test_heldout_comparison.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/heldout_validate.py tests/synthetic/test_heldout_policy.py tests/synthetic/test_heldout_comparison.py
git diff --check
~~~

Commit:

~~~
git add src/synthetic/heldout_validate.py tests/synthetic/test_heldout_policy.py tests/synthetic/test_heldout_comparison.py
git commit -m "feat: add frozen held-out fidelity comparisons"
~~~

### Task 3: Wire governed orchestration, compatibility gates, CLI, and lifecycle

Files:
- Modify: src/synthetic/heldout_validate.py
- Create: tests/synthetic/test_heldout_integration.py
- Create: tests/synthetic/test_heldout_cli.py

Interfaces:
- Consumes: Task 1 staging/target scope, Task 2 policy/report models, existing CalibrationArtifact loader, CalibrationDisclosurePolicy, PartitionPolicy, RunDirectory, and DEFAULT_AGE_WINDOWS.
- Produces: immutable HeldoutRunConfig, HeldoutValidationResult, validate_heldout(config), write_heldout_report(result, output), and main() for python -m synthetic.heldout_validate.

- [ ] Step 1: Write failing integration/CLI/lifecycle tests

Use write_mock_snapshot for the fictional real side, write_synthetic_package for the generated side, and calibrate/write_calibration_result to create a compatible calibration artifact. Test a passing package, an intentionally shifted generated value that yields FAIL, and a high disclosure minimum/missing target that yields UNEVALUABLE. Assert real and synthetic connections are separate, all real held-out targets use the held-out label, artifact/schema/snapshot/disclosure/partition/registry mismatches fail before output, and the package marker is required.

Test that write_heldout_report promotes exactly heldout-validation-report.json and heldout-validation-summary.txt, reparses canonical bytes, refuses an existing output or hashed .partial/.failed lifecycle path, and archives only {"status":"FAILED","reason":"held-out output validation failed"} on write failure. Test CLI required flags:

~~~
--real-root --descriptor --snapshot --synthetic-root --calibration-artifact --calibration-report
--partition-policy --disclosure-policy --partition-key-file --frozen-policy --output
~~~

The CLI must return 0 for PASS, 1 for promoted FAIL/UNEVALUABLE reports, 1 with no output for hard failures, and 2 with held-out arguments invalid for parser errors. Assert stderr never contains source paths, key bytes, patient/visit IDs, or raw exception details.

- [ ] Step 2: Run integration tests to verify they fail

Run: UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_heldout_integration.py tests/synthetic/test_heldout_cli.py

Expected: collection or call failure because HeldoutRunConfig, orchestration, and CLI lifecycle are not implemented.

- [ ] Step 3: Implement explicit configuration and compatibility gates

Add HeldoutRunConfig validation for all Path/token/key/policy/window fields. In validate_heldout, load the real descriptor via prepare_input and the generated descriptor through a secure package reader; require x-synthetic: true, matching repository fingerprints, and exact eight resources. Load the calibration artifact and explicit calibration report through strict loaders; require artifact/report source_snapshot == config.source_snapshot, artifact/report source_partition == calibration where applicable, artifact/report schema fingerprints equal to both descriptors, artifact disclosure policy equal to the explicit disclosure policy, report source aggregate hash equal to artifact source_aggregate_sha256, report partition-policy identity equal to the loaded partition policy, and fidelity_policy.target_registry_version == TARGET_REGISTRY_VERSION. Reject any mismatch before aggregate computation.

Create independent in-memory DuckDB connections. On the real connection call prepare_input, then compute_raw_targets(..., partition_label="held_out"); on the synthetic connection call prepare_synthetic_input, then compute_raw_targets(..., partition_label="calibration"). Pass both raw sets through disclose_targets using the explicit disclosure policy. Build the synthetic aggregate hash from the supplied artifact and the held-out hash from its disclosed strata using the same canonical aggregate payload routine. Construct checks for schema, partition, target registry, disclosure, and family coverage, then return HeldoutValidationResult without retaining either connection or identifiers.

- [ ] Step 4: Implement transactional report output and CLI exit semantics

Use a lifecycle run ID derived from sha256(f"{artifact_id}:{policy_id}:{policy_version}".encode("ascii")), refusing pre-existing target/partial/failed paths. Write only heldout-validation-report.json and heldout-validation-summary.txt with exclusive, fsynced writes; reparse and byte-compare both before no-replace promotion. On hard output errors call RunDirectory.fail with the fixed aggregate reason and raise a redacted ValueError. In main, parse only the explicit flags above with a redacted parser, load policy/key/artifact/configuration, promote the report for all comparison statuses, and exit with 0/1 according to report status while emitting no exception detail.

- [ ] Step 5: Run integration/CLI tests, lint, and commit

Run:

~~~
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_heldout_integration.py tests/synthetic/test_heldout_cli.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/heldout_validate.py tests/synthetic/test_heldout_integration.py tests/synthetic/test_heldout_cli.py
git diff --check
~~~

Commit:

~~~
git add src/synthetic/heldout_validate.py tests/synthetic/test_heldout_integration.py tests/synthetic/test_heldout_cli.py
git commit -m "feat: add governed held-out validation command"
~~~

### Task 4: Document the gate and protect visible generator boundaries

Files:
- Modify: docs/synthetic-generator.md
- Modify: README.md
- Create: tests/synthetic/test_heldout_boundaries.py

Interfaces:
- Consumes: the implemented CLI/report contract and roadmap language from the held-out design.
- Produces: user-facing usage guidance, explicit non-claims, and regression tests proving no visible generator/export/trajectory path imports or consumes held-out validation or governed real data.

- [ ] Step 1: Write failing boundary/documentation tests

Add an AST/import test over src/synthetic/generate.py, src/synthetic/manifest.py, src/synthetic/native/, and src/synthetic/derivation.py that fails if they import synthetic.heldout_validate, synthetic.calibrate, synthetic.calibration_input, or Path/CLI arguments named real_root, data_root, partition_key, or heldout_report. Add documentation assertions for the complete command flags, PASS/FAIL/UNEVALUABLE semantics, synthetic-only CI, and explicit deferrals to privacy, temporal drift, task utility, prevalence, and Synthea.

- [ ] Step 2: Run the boundary tests to verify they fail

Run: UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_heldout_boundaries.py

Expected: failure because the new documentation section and boundary test do not yet exist.

- [ ] Step 3: Update documentation and add boundary guard

Add a concise “Patient-disjoint held-out validation” section to docs/synthetic-generator.md and the relevant README roadmap section. Include the exact command from the spec, explain that the partition is derived privately from the keyed policy, describe aggregate target matching and frozen tolerances, state that suppressed/missing/underpowered cells are UNEVALUABLE, and state that a passing report is not prevalence, clinical, privacy, or release evidence. Make the command's no-default/no-real-data-in-CI boundary explicit.

Implement the AST test with ast.parse and only reject the named imports/argument identifiers in visible modules; do not reject the validator itself or calibration tests. Keep all documentation paragraphs on one physical Markdown line where the repository convention requires it.

- [ ] Step 4: Run documentation/boundary tests, lint, and commit

Run:

~~~
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_heldout_boundaries.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check tests/synthetic/test_heldout_boundaries.py
git diff --check
~~~

Commit:

~~~
git add docs/synthetic-generator.md README.md tests/synthetic/test_heldout_boundaries.py
git commit -m "docs: explain held-out validation boundary"
~~~

### Task 5: Whole-branch verification and handoff

Files:
- Modify: none unless a review fix is required.

Interfaces:
- Consumes: all prior task commits, the held-out design/spec, and the SDD ledger/review reports.
- Produces: verified branch ready for final review, merge, push, and remote-parity confirmation.

- [ ] Step 1: Run the complete verification matrix

Run:

~~~
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests
python3 schema/build.py --check
git diff --check
~~~

Expected: all tests pass, Ruff reports no errors, schema validation validates all eight resources, and whitespace check is clean. Confirm no real data or key files are tracked with git status --short and git diff --stat.

- [ ] Step 2: Dispatch the broad whole-branch review

Create a review package from the branch merge base through HEAD and dispatch the most capable reviewer. The reviewer must check every acceptance criterion, every deferred minor in the SDD ledger, strict report redaction, partition disjointness, target-registry reuse, lifecycle behavior, and visible generator boundaries. If findings exist, dispatch one fix subagent with the complete list, run exactly one scoped re-review, and record any residual ruling in the ledger.

- [ ] Step 3: Finish, merge, push, and verify remote parity

After the whole-branch review is clean, use superpowers:finishing-a-development-branch to merge the reviewed branch to main, push origin/main, and verify:

~~~
git rev-parse HEAD
git rev-parse origin/main
git status --short
~~~

Expected: the two revisions are equal and the worktree is clean. Remove only this plan's SDD workspace; leave unrelated worktrees untouched.
