# Evaluator-Only Observation Frame Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Execute each task in an isolated worktree with a fresh implementer, then run the required review and fix gates before merge.

Goal: Add the evaluator-only observation frame described in `docs/superpowers/specs/2026-08-31-observation-frame-design.md` without changing the visible eight-resource schema or production smoke CLI.

Architecture: `synthetic.native.observations` owns strict immutable observation policies, deterministic visit/measurement/event replay, private truth, and aggregate validation. It consumes only fictional native trajectories and named random streams. It does not import governed calibration, held-out validation, privacy audit, or visible package/export code.

## Global constraints

- No change to `datapackage.json`, visible CSV resources, `generate.py`, or package manifests.
- No real-data path, calibration artifact, held-out report, privacy report, arbitrary row reader, or hidden-truth input.
- Synthetic patient IDs, latent states, error deltas, event traces, hashes, seeds, and stream identities stay out of ordinary mappings, repr, reports, and visible files.
- Fixed stream names and deterministic replay; no uncontrolled resampling or clipping of invalid measurements.
- Unknown policy fields, event types, streams, or resource concepts fail closed.
- Reports use only `PASS`, `FAIL`, and `UNEVALUABLE` plus fixed aggregate metrics/reason codes.

### Task 1: Add strict observation policy, record, and truth models

Files:
- Create: `src/synthetic/native/observations.py`
- Create: `tests/synthetic/test_observation_models.py`

- [ ] Write failing tests for policy bounds/tokens, synthetic-only patient IDs, deterministic stream-name identity, visible mapping/repr leakage exclusion, strict visit/measurement/event records, and private truth construction.
- [ ] Run focused model tests and confirm expected failures.
- [ ] Implement immutable policy, visible observation records, private truth, and aggregate report models.
- [ ] Run focused tests, Ruff, and diff checks; commit `feat: add observation frame models`.

### Task 2: Implement deterministic observation-frame generation

Files:
- Modify: `src/synthetic/native/observations.py`
- Create: `tests/synthetic/test_observation_generation.py`

- [ ] Write failing tests for window/censoring, visit selection, independent availability, additive/rounding errors, BMI derivation, recognition/recorded-event delay, hidden event exclusion, and replay determinism.
- [ ] Run focused generation tests and confirm failures before implementation.
- [ ] Implement fixed stream orchestration and fail-closed source/event checks without changing the visible generator.
- [ ] Ensure malformed/nonpositive post-error measurements raise rather than clip or silently substitute latent values.
- [ ] Run focused tests, Ruff, and diff checks; commit `feat: generate evaluator observation frames`.

### Task 3: Implement aggregate validation and boundary tests

Files:
- Modify: `src/synthetic/native/observations.py`
- Create: `tests/synthetic/test_observation_validation.py`
- Create: `tests/synthetic/test_observation_boundaries.py`
- Modify: `docs/synthetic-generator.md`
- Modify: `README.md`

- [ ] Write failing tests for malformed evidence → `UNEVALUABLE`, invariant/causal violations → `FAIL`, no latent truth/report leakage, no governed imports, no schema/CLI changes, and deferred utilization/error-removal interventions.
- [ ] Implement fixed aggregate checks/reason codes and evaluator-only boundary assertions.
- [ ] Document the observation API, streams, hidden truth boundary, and deferred package/resource scope.
- [ ] Run focused tests, full suite, Ruff, schema check, and diff check; commit `feat: document evaluator observation frames`.

### Task 4: Independent reviews and handoff

- [ ] Create an ignored SDD ledger and record each task's implementation/review/fix status.
- [ ] Dispatch a fresh reviewer for every task; implement fixes through fresh implementer agents and run one scoped re-review after each fix round.
- [ ] Run one broad final review from merge base through branch tip and resolve all Critical/Important findings with fresh fix/re-review passes.
- [ ] From the feature worktree run full pytest, Ruff, schema check, staged diff checks, and targeted leakage/boundary checks.
- [ ] Merge to `main`, rerun all verification on merged `main`, push, verify `HEAD == origin/main`, and remove only this slice's worktree/branch/ignored SDD workspace.
