# Engine-Independent Golden Growth-Trajectory Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable, deterministic golden trajectory suite covering one healthy and nine growth-disorder scenario types across all pediatric age regimes, with fourteen forced-coverage cases (treated and untreated Turner, undernutrition, and excess-weight branches), without turning them into prevalence or release evidence.

**Architecture:** A typed evaluator module owns fourteen immutable fictional cases containing explicit hidden states and directional assertions. A runner generates each case twice through the existing age-regime/disorder kernels, checks aggregate structural/event/physiology invariants, and emits only safe case IDs, statuses, and reason codes; documentation and AST guards prevent file, governed-data, package, Synthea, or production coupling.

**Tech Stack:** Python 3.12+ standard-library `dataclasses`, `enum`, `json`, `math`, `re`, `collections.abc`; existing native age-regime/disorder models and kernels; pytest; Ruff; uv; Markdown.

**Spec:** `docs/superpowers/specs/2026-09-01-golden-trajectory-contract-design.md`

## Global Constraints

- `GOLDEN_TRAJECTORY_VERSION` is exactly `growth-golden-v1`.
- `GOLDEN_CASE_IDS` is exactly `("golden-healthy-v1", "golden-familial-short-stature-v1", "golden-constitutional-delay-v1", "golden-growth-hormone-deficiency-v1", "golden-pediatric-hypothyroidism-v1", "golden-celiac-disease-v1", "golden-small-for-gestational-age-catch-up-v1", "golden-small-for-gestational-age-persistent-v1", "golden-turner-syndrome-v1", "golden-turner-syndrome-untreated-v1", "golden-undernutrition-v1", "golden-undernutrition-untreated-v1", "golden-excess-weight-v1", "golden-excess-weight-treated-v1")`.
- The default age tuple is exactly `(0, 700, 730, 760, 3000, 4379, 4380, 4740, 5470, 5475, 6575, 7305)` with fixed puberty onset `4380`, tempo `1095`, and explicit finite fictional z-state values.
- The default disorder states are healthy `(None, 0.0)`, familial `(0, 1.0)`, constitutional delay `(4380, 1.0, delay=360)`, growth-hormone deficiency `(onset=3000, severity=1.0, treatment_start=3510, response=0.6)`, pediatric hypothyroidism `(onset=1460, severity=1.0, treatment_start=1850, response=0.6)`, celiac disease `(onset=2190, severity=1.0, treatment_start=2640, response=0.6)`, SGA catch-up `(onset=0, severity=0.7)`, SGA persistent `(onset=0, severity=1.2)`, treated Turner syndrome `(onset=1460, severity=1.0, treatment_start=1850, response=0.6)`, untreated Turner syndrome `(onset=1460, severity=1.0)`, treated undernutrition `(onset=2190, severity=1.0, treatment_start=2490, response=0.6)`, untreated undernutrition `(onset=2190, severity=1.0)`, untreated excess weight `(onset=2190, severity=1.0)`, and treated excess weight `(onset=2190, severity=1.0, treatment_start=2490, response=0.6)`.
- The runner is evaluator-only and in-memory. It accepts no path, CSV, output, package, descriptor, key, calibration, held-out, privacy, model, network, Java, or Synthea input.
- Hidden patient/state/point/event objects never enter ordinary mappings, manifests, logs, package files, or reports; reports contain only safe case IDs, statuses, and fixed reason codes.
- Invalid inputs raise exactly `GoldenTrajectoryUnavailable("golden trajectory suite unavailable")` without exception chaining or submitted-value echo.
- A golden `PASS` is forced-coverage development evidence only; it is not prevalence, demographic, clinical, task utility, privacy/non-matchability, held-out, scale, Synthea, or release evidence.
- The module imports only the existing evaluator contracts and standard-library modules; visible generation/exporter/calibration/held-out/prevalence/privacy/task/Synthea modules do not import or consume it automatically.
- Tests use only fictional `RegimeLinearTestReference` and repository development modules; no real or governed records, reference tables, network services, or external runtime are added.

---

### Task 1: Implement the immutable golden catalog, runner, and focused tests

**Files:**

- Create: `src/synthetic/golden_trajectories.py`
- Create: `tests/synthetic/test_golden_trajectories.py`

**Interfaces:**

- Produces `GOLDEN_TRAJECTORY_VERSION`, `GOLDEN_CASE_IDS`, `GOLDEN_REASON_CODES`, `GoldenTrajectoryUnavailable`, `GoldenPattern`, `GoldenStatus`, frozen non-subclassable `GoldenTrajectoryCase`, `GoldenCaseResult`, `GoldenTrajectoryReport`, `DEFAULT_GOLDEN_CASES`, and `run_golden_trajectory_suite(reference, *, modules=None, cases=DEFAULT_GOLDEN_CASES) -> GoldenTrajectoryReport`.
- `GoldenTrajectoryCase` fields are `case_id`, `patient`, `seed`, `ages_days`, `physiology_state`, `disorder_state`, `required_regimes`, `required_event_types`, `height_pattern`, `bmi_pattern`, and `pattern_probe_ages_days`.
- `GoldenCaseResult` fields are `case_id`, `status`, and `reason_codes`; `GoldenTrajectoryReport` fields are `report_version`, `status`, and `case_results`.

- [x] **Step 1: Write the failing catalog and runner tests.**

  Define a test helper that returns the exact fixed default cases’ aggregate metadata and uses only `RegimeLinearTestReference`. Assert the fourteen default IDs and fixed version, the exact fixed age tuple, all five required `GrowthRegime` values, and the expected event sets for healthy, familial short stature, constitutional delay, treated growth-hormone deficiency, treated pediatric hypothyroidism, treated celiac disease, the two SGA branches, treated and untreated Turner syndrome, treated and untreated undernutrition, and untreated and treated excess weight.

  Test frozen/exact construction: mutate attempts fail, `repr` is a fixed evaluator-safe string, source mappings/tuples do not alias, patient/state subclasses are rejected, duplicate case IDs and malformed ages/pattern probes fail, and hidden states never appear in report mappings or canonical JSON bytes.

  Test `run_golden_trajectory_suite(RegimeLinearTestReference())` returns `PASS` with fourteen ordered case results, `("OK",)` reasons, canonical sorted ASCII JSON with one newline, and equal output on repeated calls. Verify every result covers infancy, transition, childhood, puberty, and adolescence; physical height/BMI/weight identities and velocities remain valid; required events are causally ordered; and each `GoldenPattern` is exercised, including delayed recovery, celiac weight-first decline, SGA birth catch-up/persistent height, Turner female-reference compatibility, untreated progressive-negative height, undernutrition delayed-progressive height and progressive-negative BMI, excess-weight sustained positive BMI and positive treatment response, and post-treatment improvement followed by a non-regressing post-response probe.

  Test failure boundaries with a custom reference that raises, a missing/wrong-kind module mapping, an invalid case, a nondeterministic module/reference, missing required regimes/events, and a deliberately broken directional pattern. Invalid inputs must raise the fixed unavailable exception with no cause/context or submitted patient/age/value echo; generated-case failures must return `FAIL` with only the fixed reason codes. Assert no `PASS` result can expose trajectory points, states, measurements, event payloads, seeds, or patient IDs.

- [x] **Step 2: Run focused tests to verify the red state.**

  ```sh
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_golden_trajectories.py
  ```

  Expected: collection fails because `synthetic.golden_trajectories` and its public classes do not yet exist.

- [x] **Step 3: Implement the minimal evaluator-only suite.**

  Define exact fixed constants, enums, fixed reason ordering, and a single redacted exception helper. Implement all three dataclasses with `frozen=True`, `repr=False`, exact built-in scalar/tuple/model checks, immutable copies, `__init_subclass__` rejection, safe case-ID validation, and no public hidden-state serialization. Require strict ages, strictly increasing in-domain pattern probes (which may be unobserved between trajectory sample ages), unique regimes/events, valid `GoldenPattern` values, and matching patient/disorder state kinds.

  Build `DEFAULT_GOLDEN_CASES` with the exact case IDs, age tuple, explicit `AgeRegimeState` values, explicit `LatentDisorderState` values, required regimes/events, and probes from the spec. Use default repository modules only when `modules is None`; otherwise copy a mapping and require exactly the ten `DisorderKind` keys without retaining mutable caller state.

  Implement the runner with an injected reference and `AgeRegimeTrajectoryKernel`/`AgeRegimeDisorderKernel`. For each case, generate twice with the explicit hidden state and identical `NamedRandomStreams`, then compute fixed aggregate checks for patient/trajectory type, all required regimes, event inclusion/order, positive finite measurements, height/BMI/weight identities, finite velocities, and direct module pattern semantics. Use `math.isclose(..., abs_tol=1e-12)` only for zero/equality checks; directional checks use strict signs, strict improvement during an active response interval, non-regression at the final post-response probe, and monotone birth-to-catch-up recovery for SGA. Convert per-case assertion failures to fixed reason codes and suite status; convert invalid inputs or kernel/module/reference failures to the fixed unavailable exception with `from None`.

  Implement `GoldenCaseResult.to_mapping()`, `GoldenTrajectoryReport.to_mapping()`, and `to_json_bytes()` using private scalar extractors rather than overridable methods, sorted compact ASCII JSON, `allow_nan=False`, and one trailing newline. Do not include `patient`, `age`, `state`, `point`, `event`, `seed`, `reference`, `module`, value, or hidden-truth fields in report output.

- [x] **Step 4: Run focused tests and lint.**

  ```sh
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_golden_trajectories.py
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/golden_trajectories.py tests/synthetic/test_golden_trajectories.py
  ```

  Expected: all catalog/runner tests pass and Ruff reports no errors.

- [x] **Step 5: Commit the core golden-suite task.**

  ```sh
  git add src/synthetic/golden_trajectories.py tests/synthetic/test_golden_trajectories.py
  git commit -m "feat: add golden growth trajectory suite"
  ```

---

### Task 2: Document and statically protect the evaluator boundary

**Files:**

- Create: `docs/golden-trajectories.md`
- Modify: `README.md`
- Modify: `docs/synthetic-generator.md`
- Create: `tests/synthetic/test_golden_trajectory_docs.py`
- Create: `tests/synthetic/test_golden_trajectory_boundaries.py`

**Interfaces:**

- Consumes `run_golden_trajectory_suite`, `DEFAULT_GOLDEN_CASES`, the native age-regime/disorder guide, and the optional Synthea handoff guide.
- Produces a fictional-reference usage example, explicit forced-coverage/non-claim language, and AST regression tests showing no file/governed/production coupling.

- [x] **Step 1: Write failing documentation and boundary tests.**

  Assert the guide names `growth-golden-v1`, all fourteen case IDs, all five age regimes, the ten disorder patterns, the injected-reference call, aggregate-only report fields, and the exact fixed unavailable message. Assert it says evaluator-only/in-memory/forced coverage and explicitly disclaims prevalence, demographic fidelity, clinical validity, task utility, privacy/non-matchability, held-out, scale, Synthea, and release evidence.

  Assert README and `docs/synthetic-generator.md` link the guide while retaining the production CLI’s exact fail-closed message. AST-parse every `src/synthetic` module and assert `golden_trajectories` imports only standard-library modules plus the named evaluator contracts, while generation, package export, calibration, held-out, prevalence, privacy, task, counterfactual package, and Synthea modules do not import it. Assert the golden module has no `Path`, `csv`, `os`, `subprocess`, `urllib`, `requests`, Java, Synthea, package-writer, or output-lifecycle symbols/calls.

- [x] **Step 2: Run docs/boundary tests to verify the red state.**

  ```sh
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_golden_trajectory_docs.py tests/synthetic/test_golden_trajectory_boundaries.py
  ```

  Expected: collection or assertions fail because the guide, links, and boundary tests do not yet exist.

- [x] **Step 3: Add the guide and cross-document roadmap language.**

  Create `docs/golden-trajectories.md` with a copy-pasteable call using `RegimeLinearTestReference`, the default catalog, and `report.to_json_bytes()`. Explain the fixed ages, hidden explicit states, all five regimes, event/pattern checks, deterministic repeated-run behavior, and fixed aggregate report. State that the catalog is deliberately not prevalence-representative, does not generate a package, and does not replace schema/export/derivation, calibration, held-out, privacy, clinical review, task utility, Synthea, or release gates.

  Link the guide from README and the synthetic-generator guide. State that the native engine remains release one, the production command remains fail closed, and the optional Synthea contract remains external and downstream. Keep paragraphs on one physical Markdown line where repository convention requires it.

- [x] **Step 4: Run docs/boundary tests, lint, whitespace, and commit.**

  ```sh
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_golden_trajectory_docs.py tests/synthetic/test_golden_trajectory_boundaries.py
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests
  git -c core.whitespace=cr-at-eol,-blank-at-eof diff --check main..HEAD
  git add README.md docs/synthetic-generator.md docs/golden-trajectories.md tests/synthetic/test_golden_trajectory_docs.py tests/synthetic/test_golden_trajectory_boundaries.py
  git commit -m "docs: bound golden trajectory coverage"
  ```

---

### Task 3: Review, verify, merge, and push

**Files:**

- Modify: `.superpowers/sdd/2026-09-01-golden-trajectory-contract/progress.md` (ignored SDD ledger only)

**Interfaces:**

- Consumes Task 1/2 commits, focused reports, native kernel tests, and repository schema/lock gates.
- Produces a reviewed branch that advances trajectory coverage without changing visible generation, package lifecycle, source data, or remote state before verification.

- [x] **Step 1: Run the complete verification matrix.**

  ```sh
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests
  PYTHONDONTWRITEBYTECODE=1 python3 schema/build.py --check
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv lock --check
  git -c core.whitespace=cr-at-eol,-blank-at-eof diff --check main..HEAD
  ```

  Also inspect the diff for only planned files, scan changed paths for patient/real/governed/output artifacts, run the golden focused suite, scan imports for forbidden coupling, and verify `python -m synthetic.generate --output /tmp/golden-contract-smoke --patients 1 --seed 1` still exits with the unchanged fail-closed message and creates no output.

- [x] **Step 2: Dispatch scoped and broad reviews.**

  Generate a merge-base-to-`HEAD` review package. Use a fresh Task 1 reviewer and a fresh Task 2 reviewer, then one broad reviewer on the most capable model. Review strict case/model immutability, hostile subclass behavior, deterministic kernel reuse, physical identity and directional assertions, aggregate report redaction, documentation accuracy, AST boundaries, and unchanged production fail-closed behavior. Route every Critical/Important finding through one fix/re-review loop per SDD rules; record Minor findings and rulings in the ledger.

- [x] **Step 3: Merge, rerun, push, and confirm parity.**

  Use the finishing workflow: run the full suite on the feature branch, inspect status and staged names, fast-forward `main`, rerun the full suite and all required checks on merged `main`, push `origin main`, fetch, and verify `git rev-parse main` equals `git rev-parse origin/main`. Preserve unrelated untracked caches and remove only this clean feature worktree/branch after successful parity.

  ```sh
  git rev-parse main
  git rev-parse origin/main
  ```

## Self-review checklist

- [x] Every spec field, default case, age/regime/event/pattern rule, fixed reason, serialization rule, error boundary, and deferred claim maps to a task.
- [x] Every plan step contains concrete files, interfaces, test behavior, commands, and expected outcomes without unspecified implementation or validation work.
- [x] Task 1 output names match Task 2 documentation/tests and Task 3 review/verification commands.
- [x] The plan never authorizes real/governed data, patient packages, Java/Synthea execution, network access, prevalence allocation, or release promotion.

## Completion evidence

- Task 1 was independently reviewed over `990004b..5374021`; the fresh review approved the catalog, runner, strict validation, deterministic repeated generation, redaction, and evaluator-only boundaries with no findings.
- Task 2 was independently reviewed over the historical slice. A dynamic-import AST gap was fixed through TDD in `8534585` and `70ba7b5`; scoped re-review and final broad review approved direct, relative, module/function/builtins aliases, positional/`name=` literals, forbidden-runtime coverage, and computed-target exclusion with no findings.
- Merged `main` verification: `2492 passed, 4 skipped`; focused golden suite `93 passed`; Ruff, schema validation, `uv lock --check`, whitespace checks, and fail-closed CLI tests passed.
- The published suite remains evaluator-only and forced-coverage: no patient package, prevalence allocation, governed input, Synthea/Java runtime, network access, or release/clinical/privacy evidence was added.

### Follow-on: undernutrition trajectory coverage (2026-09-02)

- [x] Add a versioned, frozen `UndernutritionConfig` and `UndernutritionModule` with weight/BMI-first decline, delayed progressive height impairment, and optional partial treatment recovery/nonresponse.
- [x] Register `DisorderKind.UNDERNUTRITION`, its named counterfactual stream, built-in module contract, and treated/untreated golden forced-coverage cases without changing the visible generator or package schema.
- [x] Add deterministic, schedule, overflow, state-kind, treatment, age-regime composition, and golden-pattern tests; add the `delayed_progressive` pattern and update evaluator-only documentation while retaining nutrition-specific ancillary pathways as deferred.

### Follow-on: excess-weight trajectory coverage (2026-09-02)

- [x] Add a versioned, frozen `ExcessWeightConfig` and `ExcessWeightModule` with sustained positive BMI growth, zero linear-growth effect, and optional partial treatment recovery/nonresponse.
- [x] Register `DisorderKind.EXCESS_WEIGHT`, its named counterfactual stream, built-in module contract, and untreated/treated golden forced-coverage cases without changing the visible generator or package schema.
- [x] Add deterministic, schedule, overflow, state-kind, treatment, age-regime composition, and golden-pattern tests; add `progressive_positive` and `positive_progression_response` patterns and retain obesity-specific ancillary projection as deferred.

### Follow-on: pediatric hypothyroidism golden coverage (2026-09-02)

- [x] Register the versioned pediatric-hypothyroidism native module and extend the golden catalog from four to five fictional cases, retaining aggregate-only report fields and the existing evaluator boundary.
- [x] Add fixed onset/treatment probes `(1460, 1850, 2215, 3000)` with progression/response height and positive-after-onset BMI assertions; update the golden guide and companion plan/spec language.
- [x] Verify the new module, golden catalog, cohort diagnostics, and existing synthetic suite; visible generation, package export, GHD ancillary rows, prevalence, privacy, clinical, and Synthea paths remain unchanged.

### Follow-on: celiac-disease-like trajectory coverage (2026-09-02)

- [x] Add a versioned, frozen `CeliacDiseaseConfig` and `CeliacDiseaseModule` with weight/BMI-first decline, delayed height impairment, optional treatment, and partial recovery/nonresponse branches.
- [x] Register `DisorderKind.CELIAC_DISEASE`, its named counterfactual stream, built-in module contract, and golden forced-coverage case without changing the visible generator or package schema.
- [x] Add deterministic, schedule, overflow, state-kind, treatment, age-regime composition, and golden-catalog tests; update evaluator-only documentation and keep disease-specific ancillary projection deferred.

### Follow-on: prematurity/SGA trajectory coverage (2026-09-02)

- [x] Add a versioned, frozen `SmallForGestationalAgeConfig` and `SmallForGestationalAgeModule` with birth-state length/weight deficits, faster BMI catch-up, and catch-up versus persistent-height branches.
- [x] Register `DisorderKind.SMALL_FOR_GESTATIONAL_AGE`, its named counterfactual stream, built-in module contract, and two golden forced-coverage cases without adding visible birth-state or ancillary resources.
- [x] Add deterministic, schedule, overflow, state-kind, birth-onset, stream, composition, and golden-pattern tests; update evaluator-only documentation and keep gestational-age/prematurity clinical descendants deferred.

### Follow-on: Turner syndrome trajectory coverage (2026-09-02)

- [x] Add a versioned, frozen `TurnerSyndromeConfig` and `TurnerSyndromeModule` with female-reference compatibility, no SGA-like birth deficit, progressive height impairment, relative BMI increase, and optional treatment response.
- [x] Register `DisorderKind.TURNER_SYNDROME`, its named counterfactual stream, built-in module contract, and two golden forced-coverage cases (treated and untreated) without changing the visible generator or package schema.
- [x] Add deterministic, schedule, overflow, state-kind, sex-reference, stream, age-regime composition, and golden-pattern tests; cover treated response and untreated progressive-negative height; update evaluator-only documentation and keep Turner karyotype/estrogen and other ancillary pathways deferred.
