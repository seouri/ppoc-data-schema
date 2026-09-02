# In-Memory Paired Counterfactual EHR-Worlds Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans`. Each task is independently reviewed; implementation and test edits are delegated to fresh subagents. The controller may edit only this plan/spec and ignored SDD evidence.

**Goal:** Compose an already validated fictional trajectory counterfactual into paired, exact-schema in-memory EHR-world members and add an aggregate-only resource-level validator for the three supported interventions.

**Architecture:** Add `synthetic.native.counterfactual_worlds` as a one-way in-memory orchestration layer. It replays both trajectories through the same `ObservationPolicy` and `NamedRandomStreams` seed/index, projects base rows, projects and merges the reviewed GHD ancillary resources, and returns an immutable `CounterfactualEhrWorldPair`. A separate fixed report compares visible rows against the existing trajectory matrix. It does not change the trajectory, observation, resource, ancillary, package-export, or generic validators.

**Tech stack:** Python 3.12+, standard-library dataclasses/enums/mappings, existing native synthetic contracts, pytest, Ruff, schema checker, and `uv lock --check`.

**Spec:** `docs/superpowers/specs/2026-08-31-counterfactual-ehr-worlds-design.md`

## Global constraints

- Accept only the typed in-memory values named by the spec; descriptor input is an already loaded mapping and no file/path/output argument is allowed.
- Reuse the existing counterfactual, observation, resource, ancillary, and bundle contracts; do not duplicate schemas, draw random values in the assembler, or modify their validators.
- Use a base-compatible policy/descriptor in tests because observed `LENGTH` is intentionally not projectable into the current base visits resource.
- Keep trajectories, frames/truth, contexts, seeds, stream identities, descriptors, projections, and policy internals out of ordinary mappings, reprs, reports, and exceptions.
- Use fixed aggregate statuses/reasons and `FAIL > UNEVALUABLE > PASS`; visible structural violations are `FAIL`, private evidence absence is `UNEVALUABLE` only when no visible failure is independently decidable.
- Reject `UTILIZATION_INTENSITY`, `MEASUREMENT_ERROR_REMOVAL`, unknown intervention values, package/export/governed/real/privacy/model/callable/Synthea boundaries, and any permissive catch-all change.
- Controller edits only this spec/plan and ignored SDD ledger/review evidence; all implementation, test, and documentation edits are delegated.

---

### Task 1: Add immutable paired-world models and deterministic assembler

**Files:**

- Create: `src/synthetic/native/counterfactual_worlds.py`
- Create: `tests/synthetic/test_counterfactual_world_models.py`
- Create: `tests/synthetic/test_counterfactual_world_assembly.py`

- [x] Write failing tests for fixed statuses/reasons/check order, immutable report/model mappings, supported/deferred intervention handling, typed input validation, shared patient/demographics/policy/shape, exact six-resource output, source-frame binding, deterministic replay, and no mutation.
- [x] Add a deterministic base-compatible fixture builder with a loaded descriptor mapping and `length_availability_probability=0.0`; cover healthy/non-GHD/GHD and empty/partial visible descendants without real or governed inputs.
- [x] Implement `CounterfactualWorldCheck`, `CounterfactualWorldValidationReport`, `CounterfactualEhrWorldPair`, fixed redacted `CounterfactualWorldUnavailable`, and `assemble_counterfactual_ehr_worlds` exactly as specified. Re-run trajectory validation, generate both frames with the same named streams, project base rows, project/merge GHD ancillary resources, and retain hidden bindings only in `repr=False` fields.
- [x] Run focused model/assembly tests, Ruff on changed files, and `git diff --check`; commit `feat: assemble paired counterfactual EHR worlds`.

### Task 2: Implement aggregate resource-level counterfactual validation

**Files:**

- Modify: `src/synthetic/native/counterfactual_worlds.py`
- Create: `tests/synthetic/test_counterfactual_world_validation.py`
- Create: `tests/synthetic/test_counterfactual_world_boundaries.py`

- [x] Write failing tests that tamper with demographics, patient rows, visits, measurements, events, descendants, ancillary rows/links, policy metadata, hidden bindings, and treatment-age gating; assert permitted changes for physiology severity, earlier recognition, treatment adherence, no-treatment-start, and empty/partial event cases.
- [x] Add validators for pair binding, shared demographics, shared observation, observation invariants, resource invariants, permitted changes, and truth boundary with fixed reason codes and status precedence.
- [x] Re-run `validate_counterfactual_pair`, both observation-frame validators, both integrated ancillary-bundle validators, and isolated base-resource checks; classify malformed private evidence as `UNEVALUABLE` only when no visible violation is provable.
- [x] Add static AST/import/public-signature tests rejecting filesystem, path/output/root/key, package/export, manifest, calibration/held-out/privacy, real/governed, DuckDB, model/callable, and Synthea dependencies; ensure no truth-manifest writer import.
- [x] Run focused validation/boundary tests, Ruff, and whitespace checks; commit `test: validate paired counterfactual EHR resources`.

### Task 3: Document the world composer, matrix, and deferrals

**Files:**

- Modify: `docs/synthetic-generator.md`
- Modify: `README.md`
- Create: `tests/synthetic/test_counterfactual_world_docs.py`

- [x] Write failing documentation assertions for the exact public API, loaded-descriptor/base-compatible caveat, deterministic shared streams, seven report checks, resource-level matrix, redaction, fixed failure boundary, and no-export/no-real/Synthea deferrals.
- [x] Add a concise usage section showing assembly from an existing `CounterfactualPair`, shared `SyntheticDemographics`/`ObservationPolicy`, loaded descriptor, GHD policy, and aggregate validation. Do not publish private truth or a package-writing recipe.
- [x] State that pair-aware exact-schema export is a separate development-only bridge and Synthea is an optional adapter only after conformance; retain existing prevalence, calibration, held-out, privacy, clinical, utility, release, and non-matchability boundaries.
- [x] Run documentation tests, full Ruff, schema check, lock check, and whitespace checks; commit `docs: document paired counterfactual EHR worlds`.

### Task 4: Review, verify, merge, and push

**Files:**

- Modify: this plan (checkbox/evidence metadata only)
- Create/modify: `.superpowers/sdd/2026-08-31-counterfactual-ehr-worlds/ledger.md` and ignored review reports

- [x] Run the SDD package script and a fresh scoped review after each implementation task; route every finding to the implementer and re-review the exact fix range until PASS.
- [x] Run a fresh broad review across the complete feature range for matrix correctness, visible-resource comparisons, hidden-truth non-disclosure, deterministic stream reuse, exact shape, failure redaction, unchanged generic validators, docs, and prohibited boundaries.
- [x] Run full pytest with bytecode disabled, full Ruff, `uv lock --check`, schema validation, and `git diff --check`; record exact outputs in ignored SDD evidence and update only metadata here.
- [x] Merge the reviewed feature branch to `main` with `--no-ff`, push, verify `HEAD == origin/main`, and retain the feature worktree and SDD evidence for auditability.

## Evidence template

- Focused implementation/review commits: `5fde779`, `3fee811`, `454f3f1`, `5ad3edc`, `c22f56e`, `0e543e8`, `958c1c0`, `1641f14`, `3da01c5`.
- Scoped review/fix/re-review: PASS for Tasks 1–3; broad fix re-review PASS; follow-up private-evidence re-review PASS; full-gate allowlist re-review PASS.
- Broad review: PASS after consolidated fix `958c1c0` and follow-up `1641f14`; reports retained in ignored SDD evidence.
- Full verification: `1798 passed`; `uv run ruff check src tests` passed; `uv lock --check` passed; `python3 schema/build.py --check` validated 8 resources; `git diff --check` passed. Repository-wide Ruff retains six pre-existing findings in `schema/build.py` and `schema/profile.py` (EXE001/I001/PLW1510), outside this feature range.
- Merge/push parity: no-fast-forward merge `94d13f4`; pushed to `origin/main`; verified local `HEAD == origin/main == 94d13f4`.

## Deferred roadmap gates

This slice does not satisfy authoritative augmented derivation, prevalence or demographic calibration, held-out fidelity, temporal drift, task utility, clinical validity, privacy/non-matchability, release authorization, or Synthea conformance. Pair-aware exact-schema package export is implemented as a separate development-only bridge; an optional Synthea adapter remains downstream of the native conformance suite.
