# Governed Privacy-Audit Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Execute each task in an isolated worktree with a fresh implementer, then run the required review and fix gates before merge.

Goal: Add a standalone aggregate-only privacy auditor for exact-schema synthetic growth fixtures, with explicit threat-model policy, mandatory identifier/reproduction gates, bounded linkage/membership/attribute/composition controls, and redacted lifecycle/CLI output.

Architecture: `synthetic.privacy_audit` stages each supplied package in a private DuckDB connection through the reviewed secure exact-schema helpers, derives fixed process-local patient profiles and hashed trajectory signatures, runs configured controls without arbitrary SQL or columns, and returns only an immutable aggregate report. Optional held-out, shadow, prior-release, negative-control, and positive-control inputs are explicit and missing required evidence is `UNEVALUABLE`.

Tech Stack: Python 3.12+, DuckDB, standard-library csv/json/hashlib/math/os/stat/datetime/dataclasses/argparse, existing schema and `RunDirectory` helpers, pytest, Ruff.

Spec: docs/superpowers/specs/2026-08-31-privacy-audit-design.md

## Global constraints

- `datapackage.json` remains the sole schema authority; every package has exactly the eight repository resources and the repository schema fingerprint.
- The real reference and held-out packages must not be synthetic; generated, shadow, prior-release, negative-control, and positive-control packages must explicitly carry `x-synthetic: true`.
- Descriptor and resource paths are regular non-symlink files below their supplied roots; JSON is bounded, UTF-8, duplicate-key rejecting, nonfinite rejecting, and never read through an unvalidated path.
- Patient/visit rows, visible identifiers, membership labels, feature vectors, profile hashes, candidate links, distances, keys, paths, and raw diagnosis values remain process-local; no exception, filename, report, summary, or manifest echoes them.
- No arbitrary SQL or caller-selected columns are accepted. Fixed profile fields and attacker-knowledge components are the only inputs to attacks.
- Identifier overlap and exact eligible longitudinal reproduction are mandatory zero thresholds. A failure is `FAIL`; it cannot be hidden by an aggregate pass.
- Missing, suppressed, inconsistent, or underpowered required evidence is `UNEVALUABLE`, never zero and never `PASS`. Optional unevaluable controls are recorded but do not block a policy that does not require them.
- Policy is loaded and frozen before package rows are staged; no observed value updates thresholds, feature selection, or generator behavior.
- Reports are aggregate-only, deterministic compact sorted ASCII JSON with a trailing newline plus a concise summary. No patient-level metrics, links, distances, attack examples, or undersized cells are serialized.
- The normal generator/exporter/trajectory/manifest modules must not import `privacy_audit`, governed input loaders, or report outputs. The auditor never writes into a package or calls generation/tuning code.
- Existing output, partial, and failed lifecycle paths are never overwritten. Hard failures promote no report and leave only a fixed redacted failure reason.
- All implementation and documentation changes pass the focused tests, full suite, Ruff, `python3 schema/build.py --check`, and `git diff --check` before merge/push.

---

### Task 1: Add strict privacy policy/report models and secure package profile extraction

Files:
- Create: `src/synthetic/privacy_audit.py`
- Create: `tests/synthetic/test_privacy_policy.py`
- Create: `tests/synthetic/test_privacy_inputs.py`
- Create: `tests/synthetic/privacy_fixtures.py`

Interfaces:
- Consumes: repository `datapackage.json`, secure descriptor/resource helpers, fictional exact-schema packages.
- Produces: immutable `PrivacyPolicy`, `PrivacyRunConfig`, internal profile/index helpers, strict `load_privacy_policy`, and aggregate-safe `PrivacyControlResult`, `PrivacyAuditReport`, and `PrivacyAuditResult` models. No attacks or CLI yet.

- [ ] Step 1: Write failing policy/input/model tests

Create a valid policy with the exact spec keys, all fixed attacker components, mandatory controls, subgroup configuration, thresholds, and review metadata. Assert duplicate/unknown/missing keys, nonfinite numbers, booleans, unsafe tokens, duplicate lists, unsupported components/controls, invalid dates, wrong fingerprint, and range errors fail without echoing values. Create fictional real/generated/held-out packages and assert real/synthetic marker rules, exact resource set/fingerprint, regular non-symlink descriptor/resources, path traversal rejection, malformed CSV/value rejection, duplicate keys, and no row/identifier leakage in errors. Assert `PrivacyAuditReport` rejects unsafe metrics and serializes canonical sorted ASCII bytes with exact keys.

- [ ] Step 2: Run the focused tests to verify they fail

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_privacy_policy.py tests/synthetic/test_privacy_inputs.py`

Expected: collection failure because `synthetic.privacy_audit` and privacy fixtures do not exist. Fix only test setup/import errors before implementation.

- [ ] Step 3: Implement strict policy and immutable aggregate models

Implement bounded secure JSON reading with duplicate-key and nonfinite rejection. Parse the exact policy contract from the spec, enforce fixed tokens/components/control IDs/subgroups, the SHA-256 schema fingerprint, date, minimums, and finite thresholds. Define report/control models that allow only aggregate metric keys and values, enforce status and sorted control IDs, and null/omit metrics for underpowered cells. Keep policy thresholds and paths out of report mappings except approved identity/review metadata.

- [ ] Step 4: Implement secure package staging and process-local profile extraction

Load descriptors only from `<root>/datapackage.json` through regular non-symlink bounded reads, require exact eight resources/fingerprint, and enforce marker polarity. Stage each package through the existing `_stage_validated_resources` and relation/link checks on its own DuckDB connection. Extract fixed per-patient demographics, visit ages/count, normalized anthropometric trajectory observations, and `growth_dx_flag` into private profile objects; derive trajectory/profile SHA-256 signatures and component buckets without returning them. Collect all declared primary-key/`*_id` values into private sets for overlap comparison. Ensure package connections and row maps are released from public result objects.

- [ ] Step 5: Run policy/input tests, lint, and commit

Run:

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_privacy_policy.py tests/synthetic/test_privacy_inputs.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/privacy_audit.py tests/synthetic/test_privacy_policy.py tests/synthetic/test_privacy_inputs.py tests/synthetic/privacy_fixtures.py
git diff --check
```

Commit: `git add src/synthetic/privacy_audit.py tests/synthetic/test_privacy_policy.py tests/synthetic/test_privacy_inputs.py tests/synthetic/privacy_fixtures.py && git commit -m "feat: add governed privacy audit contract"`

### Task 2: Implement mandatory overlap/reproduction, nearest-neighbor, and linkage controls

Files:
- Modify: `src/synthetic/privacy_audit.py`
- Create: `tests/synthetic/test_privacy_controls.py`

Interfaces:
- Consumes: Task 1 policy/profile indexes and optional held-out profiles.
- Produces: private fixed controls for identifier overlap, exact longitudinal reproduction, nearest-neighbor proximity, and linkage; each returns only `PrivacyControlResult` aggregates.

- [ ] Step 1: Write failing control tests

Test independent synthetic identifiers with copied IDs, copied eligible trajectories, empty/underpowered trajectories, exact/near/unique/tied component buckets, rare sex strata, held-out controls, permutation baselines, and mismatched package sizes. Assert mandatory overlap/reproduction failures, underpowered statuses, aggregate rates/intervals only, no IDs/hashes/pairs/distances/raw values, and deterministic results.

- [ ] Step 2: Run focused controls to verify failure

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_privacy_controls.py`

Expected: import or missing-control failures. Fix only fixture/import setup before implementation.

- [ ] Step 3: Implement identifier and exact trajectory controls

Compare private identifier sets across every primary-key and `*_id` field and calculate aggregate overlap rate with the policy threshold. Compare eligible trajectory signature sets, treating every generated signature present in the reference as a complete reproduction and keeping ineligible counts private. Mandatory zero rules fail closed before optional metrics; no identifier or hash enters a result.

- [ ] Step 4: Implement bucketed nearest-neighbor and linkage controls

Use fixed component buckets to calculate aggregate zero-proximity/unique-nearest/margin-bin rates without quadratic all-pairs scans or patient-level outputs. Require held-out controls when the policy requires them. For each selected attacker component and fixed full combination, calculate unique exact candidate rates, deterministic permutation controls, held-out-real controls, Wilson intervals, and maximum aggregate advantage. Suppress subgroup cells below minimum size and promote subgroup failures to the control status.

- [ ] Step 5: Run controls, lint, and commit

Run:

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_privacy_controls.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/privacy_audit.py tests/synthetic/test_privacy_controls.py
git diff --check
```

Commit: `git add src/synthetic/privacy_audit.py tests/synthetic/test_privacy_controls.py && git commit -m "feat: add privacy linkage and reproduction controls"`

### Task 3: Implement shadow membership, attribute disclosure, composition, and control packages

Files:
- Modify: `src/synthetic/privacy_audit.py`
- Create: `tests/synthetic/test_privacy_advanced_controls.py`
- Modify: `tests/synthetic/privacy_fixtures.py`

Interfaces:
- Consumes: Task 1/2 profile indexes, shadow manifest, optional prior/negative/positive package roots, and policy thresholds.
- Produces: strict shadow-manifest loader and aggregate membership, attribute, composition, negative-control, and positive-control results.

- [ ] Step 1: Write failing advanced-control tests

Create multiple shadow packages and private manifests with known member labels, copied/overfit and independent profiles, prior releases with repeated trajectories, and inconsistent/underpowered labels. Assert fewer than the policy minimum shadow runs, missing prior releases, unknown members, duplicate runs, and undersized groups are `UNEVALUABLE`. Assert overfit membership and copied composition fail, attribute accuracy is compared with majority/held-out baselines, independent negative controls pass, positive controls are detected, and output remains aggregate-only.

- [ ] Step 2: Run advanced tests to verify failure

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_privacy_advanced_controls.py`

Expected: missing loader/control implementation. Fix only fixture/import setup before implementation.

- [ ] Step 3: Implement strict shadow-manifest loading and membership inference

Read a bounded regular manifest with exact `privacy-shadow-v1` keys. Keep member identifiers process-local, validate against reference patients without echoing unknown values, load each synthetic shadow package separately, and map labels through internal trajectory signatures. Evaluate the fixed exact-match score attack across the required number of shadows, report only maximum advantage/intervals/counts, and return `UNEVALUABLE` when evidence is absent or underpowered.

- [ ] Step 4: Implement attribute disclosure and composition

For uniquely linked eligible trajectories, infer only the recorded growth-diagnosis flag internally and compare accuracy with reference majority and held-out baselines. Compare eligible generated signatures with every explicit prior synthetic release; report aggregate reproduction rates and fail above the policy threshold. Never serialize diagnosis values, prior paths, signatures, or candidate details.

- [ ] Step 5: Implement negative/positive controls and commit

Run the fixed linkage/reproduction harness against supplied independent negative and intentionally copied/overfit positive roots. A negative result passes only below its threshold; a positive result passes only when the harness detects the configured minimum signal. Missing required roots are `UNEVALUABLE`. Run tests/lint/diff checks and commit:

`git add src/synthetic/privacy_audit.py tests/synthetic/test_privacy_advanced_controls.py tests/synthetic/privacy_fixtures.py && git commit -m "feat: add privacy shadow and composition controls"`

### Task 4: Add orchestration, report lifecycle, CLI, docs, and boundary tests

Files:
- Modify: `src/synthetic/privacy_audit.py`
- Create: `tests/synthetic/test_privacy_integration.py`
- Create: `tests/synthetic/test_privacy_cli.py`
- Create: `tests/synthetic/test_privacy_boundaries.py`
- Modify: `docs/synthetic-generator.md`
- Modify: `README.md`

Interfaces:
- Consumes: all controls and policy/config models.
- Produces: `audit_privacy`, `write_privacy_report`, CLI parser/exit behavior, aggregate summary, documentation, and visible-generator import regression.

- [ ] Step 1: Write failing integration/CLI/boundary tests

Test a clean independent package yielding `PASS` when optional controls are not required, copied package yielding `FAIL`, missing required evidence yielding `UNEVALUABLE`, subgroup suppression, deterministic bytes, report collision/refusal, redacted failure artifacts, and parser statuses. Assert CLI required flags and optional repeated roots, exit 0/1/2, no path/ID/key/raw exception leakage, and that visible generation/export/trajectory/manifest modules do not import privacy-audit or governed input code.

- [ ] Step 2: Run integration tests to verify failure

Run: `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_privacy_integration.py tests/synthetic/test_privacy_cli.py tests/synthetic/test_privacy_boundaries.py`

Expected: missing orchestration/CLI/docs implementation. Fix only import/fixture setup before implementation.

- [ ] Step 3: Implement orchestration and global decision

Validate `PrivacyRunConfig`, load the frozen policy before staging, open independent package connections, run all applicable controls, promote any evaluated fail, mark required missing/underpowered controls unevaluable, and compute global `FAIL`/`UNEVALUABLE`/`PASS` exactly as the spec. Release no row data or connections through `PrivacyAuditResult`.

- [ ] Step 4: Implement canonical lifecycle output and CLI

Derive a safe lifecycle token from synthetic descriptor identity and policy identity, refuse target/partial/failed collisions, write only report and summary with exclusive fsynced files, reparse/byte-compare, and atomically promote. On failure leave only the fixed redacted failure reason. Add explicit required/optional flags and redacted parser/exit handling.

- [ ] Step 5: Update docs and boundary assertions; run focused checks and commit

Document the qualified privacy claim, required evidence, command, statuses, aggregate-only report, and distinction from non-matchability/release approval. Assert privacy, temporal drift, task utility, prevalence, and Synthea remain separate roadmap gates where appropriate. Run focused tests, Ruff, schema, and whitespace checks; commit:

`git add src/synthetic/privacy_audit.py tests/synthetic/test_privacy_integration.py tests/synthetic/test_privacy_cli.py tests/synthetic/test_privacy_boundaries.py docs/synthetic-generator.md README.md && git commit -m "feat: add governed privacy audit orchestration"`

### Task 5: Independent reviews, follow-up fixes, and handoff

- [ ] Create the SDD ledger under an ignored workspace and record each task's implementation/review/fix status.
- [ ] Dispatch a fresh reviewer for each task and implementer-only fix rounds for every finding; run exactly one scoped re-review after the fix round.
- [ ] Run a broad final review from the merge base through the branch tip. Resolve all Critical/Important findings with fresh fix/re-review passes; record residual Minor findings explicitly.
- [ ] From the feature worktree run the full suite, Ruff, schema check, and staged diff checks. Verify the report contains no identifiers, paths, keys, profile hashes, distances, attack examples, or undersized cells.
- [ ] Merge to `main`, rerun the full verification suite on merged `main`, push, and verify `HEAD == origin/main`. Remove only this slice's worktree/branch/ignored SDD workspace after handoff.
