# Counterfactual Fixture Validity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Execute each task in an isolated worktree with a fresh implementer, then run the required review and fix gates before merge.

Goal: Add the evaluator-only native trajectory replay contract described in `docs/superpowers/specs/2026-08-31-counterfactual-validity-design.md`, so paired fictional growth trajectories can be generated from the existing age-regime/disorder kernel and checked against a versioned causal change matrix without exposing hidden truth.

Architecture: `synthetic.native.counterfactual` owns strict immutable matrices, trajectory-pair replay, aggregate validation reports, deterministic shared-stream identities, and an explicit external truth-manifest writer. It does not import governed calibration, held-out validation, or privacy audit code, and it does not alter the current fail-closed smoke generator or visible package schema.

Tech Stack: Python 3.12+, standard-library `dataclasses`, `enum`, `hashlib`, `json`, `math`, `os`, `re`, `stat`, `pathlib`, existing schema/randomness helpers, pytest, Ruff.

## Global constraints

- The parent `datapackage.json` remains untouched; this slice adds no visible resource, truth column, or manifest field.
- Only completely fictional kernel/patient/age inputs are accepted. No real-data path, calibration artifact, held-out report, privacy report, or arbitrary row reader is accepted.
- Patient IDs, hidden truth, event payloads, layer hashes, stream identities, and manifest paths never enter aggregate reports or exception text.
- Replayed streams must be identical across worlds; no uncontrolled resampling is permitted in the supported interventions. A shared seed is not a causal proof.
- Unknown nodes, fields, resources, assertions, or intervention kinds fail closed. No implicit `may_change` broadening.
- Reports use fixed aggregate metrics/reason codes and statuses `PASS`, `FAIL`, `UNEVALUABLE`; underpowered or missing evidence is never a pass.
- Truth manifests are explicit, external, canonical, and non-overwriting; visible mapping methods exclude all hidden state.
- Run focused tests, full pytest, Ruff, schema validation, and diff checks before handoff.

### Task 1: Add strict matrix, context, resource, and world models

Files:
- Create: `src/synthetic/native/counterfactual.py`
- Create: `tests/synthetic/test_counterfactual_models.py`

Interfaces:
- Consumes: existing `AgeRegimeDisorderKernel`, `NamedRandomStreams`, fictional `PatientState`, and age tuples.
- Produces: intervention enum, fixed/default matrices, immutable `CounterfactualContext`, `CounterfactualPair`, and canonical-safe trajectory/hash helpers.

- [ ] Write failing tests for fixed interventions, strict tokens/nodes/sets, duplicate/unknown keys, supported/unsupported intervention rejection, hidden-field repr/mapping exclusion, and deterministic replay stream identities.
- [ ] Run focused model tests and confirm the expected import/implementation failures.
- [ ] Implement strict immutable models and default matrices; keep descriptor and visible package code out of this evaluator-only module.
- [ ] Ensure contexts expose only named stream generators/identities and reject path-like or real-data inputs.
- [ ] Run focused tests, Ruff, and diff checks; commit `feat: add counterfactual contract models`.

### Task 2: Implement paired builder orchestration and causal validation

Files:
- Modify: `src/synthetic/native/counterfactual.py`
- Create: `tests/synthetic/test_counterfactual_validation.py`

Interfaces:
- Consumes: existing `AgeRegimeDisorderKernel`, patient, ages, pair/matrix models.
- Produces: `generate_counterfactual_pair`, `validate_counterfactual_pair`, aggregate check/report models, and fixed layer/event comparisons.

- [ ] Write failing tests for shared patient/state replay, baseline/intervention contexts, supported severity/recognition/adherence interventions, explicit utilization/measurement-error rejection, invariant-layer equality, permitted changes, forbidden changes, event ordering, stream reuse, age/treatment coverage, and `PASS`/`FAIL`/`UNEVALUABLE` semantics.
- [ ] Run focused validation tests and confirm failures before implementation.
- [ ] Implement builder invocation with deterministic contexts and fail-closed structural checks; do not catch errors into misleading passes.
- [ ] Compare canonical hidden layer values and normalized event traces privately, trajectory z-score direction and invariants, and aggregate check counts/reason codes only.
- [ ] Run focused tests, Ruff, and diff checks; commit `feat: validate counterfactual worlds`.

### Task 3: Add external truth-manifest lifecycle, docs, and boundaries

Files:
- Modify: `src/synthetic/native/counterfactual.py`
- Create: `tests/synthetic/test_counterfactual_manifest.py`
- Create: `tests/synthetic/test_counterfactual_boundaries.py`
- Modify: `docs/synthetic-generator.md`
- Modify: `README.md`

Interfaces:
- Consumes: validated trajectory pairs and aggregate reports.
- Produces: canonical external truth manifest writer, evaluator/visible boundary tests, usage guide, roadmap status.

- [ ] Write failing manifest/lifecycle/boundary tests for duplicate destination, symlink/path rejection, canonical bytes, no hidden keys in ordinary package/manifest paths, no imports from governed modules, and no real-data path flags.
- [ ] Implement bounded regular-file lifecycle and explicit external manifest serialization; preserve hidden values only in the external evaluator artifact.
- [ ] Document the builder API, matrices, validation statuses, truth-manifest boundary, and limitation that this slice is not prevalence, task-utility, privacy, or release evidence.
- [ ] Run focused tests, full suite, Ruff, schema check, and diff check; commit `feat: document counterfactual fixture validation`.

### Task 4: Independent reviews and handoff

- [ ] Create an ignored SDD ledger and record each task's implementation/review/fix status.
- [ ] Dispatch a fresh reviewer for every task; implement fixes through fresh implementer agents and run one scoped re-review after each fix round.
- [ ] Run one broad final review from merge base through branch tip and resolve all Critical/Important findings with fresh fix/re-review passes.
- [ ] From the feature worktree run full pytest, Ruff, schema check, staged diff checks, and targeted leakage checks.
- [ ] Merge to `main`, rerun all verification on merged `main`, push, verify `HEAD == origin/main`, and remove only this slice's worktree/branch/ignored SDD workspace.
