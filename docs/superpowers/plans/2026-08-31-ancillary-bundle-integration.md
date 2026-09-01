# Native GHD Ancillary-to-Bundle Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compose the validated fictional GHD ancillary rows with an existing observed-resource bundle in memory, preserving exact descriptor schema, hidden-truth separation, and the generic empty-ancillary validator contract.

**Architecture:** Add `synthetic.native.ancillary_bundle` with an immutable, in-memory merge function and a fixed aggregate full-bundle validator. The module isolates the base six-resource rows before calling `validate_observed_resources`, extracts an `AncillaryResourceProjection` for the four ancillary rows, and delegates pathway semantics to `validate_ghd_ancillary_resources`. It does not modify the package exporter, descriptor, CLI, or generic resource validator.

**Tech Stack:** Python 3.12+, standard-library dataclasses/enums/types, existing synthetic cohort/ancillary/observation/resource contracts, pytest, Ruff, schema checker.

**Spec:** `docs/superpowers/specs/2026-08-31-ancillary-bundle-integration-design.md`

## Global constraints

- Accept only typed in-memory `ObservedResourceBundle`, `CohortMember`, `AncillaryResourceProjection`, and `GhdAncillaryPolicy` values.
- Preserve exact `BASE_RESOURCE_NAMES`, descriptor field order, immutable tuples/mappings, and the existing generic validator's rejection of nonempty ancillary rows.
- Merge only an empty-ancillary base bundle and a passing pathway projection; never overwrite or silently repair rows.
- Keep source frames, latent trajectories, hidden events, identifiers, row values, and policy internals out of reports, reprs, exceptions, and ordinary mappings.
- Use fixed `PASS`, `FAIL`, and `UNEVALUABLE` statuses/reasons with aggregate-only output; no public path, output, key, report, model, callable, real-data, governed, package, manifest, or Synthea boundary.
- Controller may edit only this plan/spec and ignored SDD evidence; implementation and test changes are delegated to subagents.

---

### Task 1: Add strict bundle composition models and merge seam

**Files:**
- Create: `src/synthetic/native/ancillary_bundle.py`
- Create: `tests/synthetic/test_ancillary_bundle_models.py`
- Create: `tests/synthetic/test_ancillary_bundle_merge.py`

- [ ] Write failing tests for fixed statuses/reasons/check order, immutable reports, valid/invalid typed inputs, exact six-resource rows, empty-ancillary precondition, same patient/shape/frame binding, fresh bundle identity, no mutation, and deterministic mappings.
- [ ] Run focused tests to confirm collection/behavior failures.
- [ ] Implement the redacted merge seam and frozen aggregate models. Isolate ancillary rows before the generic validator; call the existing GHD validator before composing the fresh `ObservedResourceBundle`.
- [ ] Run focused tests, Ruff, and `git diff --check`; commit `feat: merge GHD ancillary rows into observed bundles`.

### Task 2: Add full-bundle validation and adversarial boundaries

**Files:**
- Modify: `src/synthetic/native/ancillary_bundle.py`
- Create: `tests/synthetic/test_ancillary_bundle_validation.py`
- Create: `tests/synthetic/test_ancillary_bundle_boundaries.py`

- [ ] Write failing validator/boundary tests for malformed rows, broken patient/visit links, field order, causal timing, hidden-treatment/visible-diagnosis suppression, absent/malformed source evidence, truth/repr/mapping leakage, and forbidden imports/arguments/calls.
- [ ] Implement `validate_ghd_ancillary_bundle` with fixed checks for `bundle_identity`, `base_resources`, `ancillary_resources`, and `truth_boundary`, preserving `FAIL > UNEVALUABLE > PASS` and redacted fallback behavior.
- [ ] Run the focused integration suite, Ruff, and whitespace checks; commit `test: validate integrated GHD ancillary bundles`.

### Task 3: Document the composition seam and preserve regressions

**Files:**
- Modify: `docs/synthetic-generator.md`
- Modify: `README.md`
- Create: `tests/synthetic/test_ancillary_bundle_docs.py`

- [ ] Add failing documentation assertions for exact API, merge preconditions, full-bundle report, hidden-truth boundary, generic validator behavior, and explicit deferrals.
- [ ] Add a concise usage section and README roadmap paragraph describing the in-memory evaluator seam; state that package export, augmented derivation, prevalence, privacy/non-matchability, clinical review, task utility, other disorders, release, and Synthea remain deferred.
- [ ] Run docs/boundary tests, full Ruff, schema check, and whitespace checks; commit `docs: document ancillary bundle integration`.

### Task 4: Review, verify, and hand off

**Files:**
- Modify: this plan (checkbox/evidence metadata only)
- Create: `.superpowers/sdd/2026-08-31-ancillary-bundle-integration/ledger.md` and ignored review reports

- [ ] Run focused tests and a fresh scoped review after each implementation task; route every finding to the implementing subagent and re-review the exact fix range until PASS.
- [ ] Run a fresh broad review across the complete feature range, checking hidden-truth non-disclosure, exact shape, immutable merge semantics, generic-validator preservation, causal/link checks, docs/non-claims, and prohibited boundaries.
- [ ] Run full pytest with bytecode disabled, full Ruff, `uv lock --check`, schema validation, and `git diff --check`; update only plan/ledger metadata.
- [ ] Merge the feature branch to `main` with `--no-ff`, push, verify `HEAD == origin/main`, and retain the worktree/SDD evidence.
