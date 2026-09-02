# Optional Synthea Engine-Conformance Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a strict, aggregate-only declaration contract for a future pinned Synthea handoff while keeping the native generator, current runtime, and release gates unchanged.

**Architecture:** A small stdlib-only frozen dataclass parses and canonicalizes a fixed-version manifest containing only engine, extension, adapter, exporter, configuration, and license-notice identities. Documentation and AST regression tests make the optional route visible but fail closed: this repository neither imports nor executes Synthea, Java, network services, patient data, nor any future conformance runner.

**Tech Stack:** Python 3.12+ standard-library `dataclasses`, `hashlib`, `json`, `re`, `typing`; pytest; Ruff; uv; Markdown and existing synthetic boundary tests.

**Spec:** `docs/superpowers/specs/2026-09-01-synthea-conformance-contract-design.md`

## Global Constraints

- `SYNTHEA_CONFORMANCE_VERSION` is exactly `synthea-conformance-v1`.
- `SyntheaEngineManifest.engine_id` is exactly `synthea`.
- Repository fixtures are always `review_status="PENDING"` and `test_only=True`.
- A manifest is a declaration only; expose no `PASS` helper and never treat a valid declaration as conformance, clinical, prevalence, privacy, demographic, task-utility, reproducibility, or release evidence.
- All identifiers are bounded aggregate-safe tokens; all digest values are nonzero lowercase SHA-256 strings.
- JSON input is strict: exact keys, correct scalar types, duplicate-key rejection, nonfinite-number rejection, ASCII-only bytes, and no trailing non-whitespace content.
- Serialization is canonical sorted ASCII JSON with fixed separators and exactly one trailing newline; returned mappings and bytes must not expose caller-owned mutable state.
- The manifest records identities only. It contains no paths, patient/visit identifiers, rows, clinical values, hidden truth, event traces, keys, network locations, or review prose.
- Do not add a Synthea checkout, Java runtime, Generic Module Framework module, custom Java physiology, network download, external license artifact, PPOC translation, prevalence allocation, or engine runner.
- Do not import or automatically consume the contract from native generation, augmenter, exporter, calibration, held-out, prevalence, privacy, counterfactual, evaluator, or release modules.
- All tests and examples use fictional synthetic metadata only; no real or governed data is introduced.

---

### Task 1: Implement the strict aggregate-only manifest contract

**Files:**

- Create: `src/synthetic/synthea_conformance.py`
- Create: `tests/synthetic/test_synthea_conformance.py`

**Interfaces:**

- Produces `SYNTHEA_CONFORMANCE_VERSION: str`, `SyntheaConformanceUnavailable(Exception)`, and frozen `SyntheaEngineManifest` with `from_mapping(value: Mapping[str, object])`, `from_json_bytes(value: bytes)`, `to_mapping() -> dict[str, object]`, and `to_json_bytes() -> bytes`.
- `SyntheaEngineManifest` fields, in order, are `manifest_version`, `engine_id`, `engine_revision`, `engine_sha256`, `module_manifest_sha256`, `growth_extension_id`, `growth_extension_sha256`, `event_adapter_id`, `event_adapter_sha256`, `ppoc_exporter_id`, `ppoc_exporter_sha256`, `configuration_sha256`, `license_notice_id`, `review_status`, and `test_only`.
- The implementation imports only Python standard-library modules; it does not import project generators, schema exporters, evaluators, Synthea, Java bridges, filesystem/path APIs, CSV readers, subprocess APIs, or network clients.

- [x] **Step 1: Write the failing contract tests.**

  Build a fictional mapping helper using fixed token values such as `revision-20260901`, `growth-extension-v1`, and 64-character lowercase hexadecimal digests. Test that the valid mapping constructs the dataclass, exposes the fixed version/id, retains `PENDING`/`True`, and round-trips through `to_mapping()` and `to_json_bytes()`.

  Add tests that the dataclass is frozen, `to_mapping()` returns a fresh mapping, changing the source mapping after construction has no effect, canonical bytes are ASCII/sorted/newline-terminated, and `from_json_bytes(to_json_bytes())` is equal to the original object.

  Parameterize invalid mappings for missing and unknown keys, wrong scalar types (including `bool` where a string is required and `int` where `test_only` is required), wrong fixed version or engine id, unsupported review status, empty/overlong/unsafe identifier tokens, uppercase/zero/malformed digests, and non-boolean `test_only`. Assert every failure raises `SyntheaConformanceUnavailable` with the fixed message `synthea conformance manifest unavailable`, has no cause, and does not echo a submitted value.

  Add JSON-byte tests for duplicate keys, `NaN`, `Infinity`, non-ASCII bytes, non-object roots, and trailing non-whitespace content. Include an assertion that an `APPROVED` declaration still has no conformance-result method or truthy release helper, while repository fixture helpers remain `PENDING` and test-only.

- [x] **Step 2: Run the focused tests to verify the red state.**

  Run:

  ```sh
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_synthea_conformance.py
  ```

  Expected: collection fails because `synthetic.synthea_conformance` and its public contract do not yet exist.

- [x] **Step 3: Implement the minimal fail-closed contract.**

  Define the fixed version, field-name set, token and digest regular expressions, and one fixed redacted error message. Parse mappings through a copied dictionary; require exactly the declared keys; validate all strings, booleans, fixed values, and SHA-256 digests; and construct the frozen dataclass only after validation. Keep identifiers aggregate-safe by rejecting separators, whitespace/control characters, path-like components, URLs, and unsafe substrings associated with patient, row, clinical-value, truth, key, source, network, or runtime data.

  Parse JSON bytes by requiring a `bytes` input, decoding ASCII, using `object_pairs_hook` to reject duplicate keys, `parse_constant` to reject nonfinite values, and rejecting any root other than an object. Reuse the mapping validator and translate every implementation exception to `SyntheaConformanceUnavailable` without exception chaining. Emit `json.dumps(..., sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii") + b"\\n"` from a fresh mapping.

  Keep `SyntheaEngineManifest` immutable and string/bool-only so construction and returned mappings cannot retain mutable nested state. Define no execution, comparison, promotion, conformance-result, path-resolution, network, or release method.

- [x] **Step 4: Run focused tests and lint.**

  ```sh
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_synthea_conformance.py
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/synthea_conformance.py tests/synthetic/test_synthea_conformance.py
  ```

  Expected: all focused contract tests pass and Ruff reports no errors.

- [x] **Step 5: Commit the contract task.**

  ```sh
  git add src/synthetic/synthea_conformance.py tests/synthetic/test_synthea_conformance.py
  git commit -m "feat: add optional synthea conformance manifest"
  ```

---

### Task 2: Document and statically protect the optional boundary

**Files:**

- Create: `docs/synthea-conformance.md`
- Modify: `README.md`
- Modify: `docs/synthetic-generator.md`
- Create: `tests/synthetic/test_synthea_conformance_docs.py`
- Create: `tests/synthetic/test_synthea_conformance_boundaries.py`

**Interfaces:**

- Consumes `SyntheaEngineManifest`, the parent Synthea design, the engine-neutral growth/derivation guides, and the existing production fail-closed command.
- Produces a copy-pasteable fictional manifest example, explicit external-handoff prerequisites, and regression tests proving visible generation and evaluation code do not import or consume the manifest.

- [x] **Step 1: Write failing documentation and boundary tests.**

  Assert the new guide names the fixed contract/version/engine id, lists every manifest identity, labels the route optional/future/development-only, requires an externally pinned revision and license review, states that repository fixtures are `PENDING` and `test_only`, and explicitly says no Synthea implementation, Java runtime, conformance result, patient data, network access, or release authorization exists.

  Assert README and `docs/synthetic-generator.md` link the new guide while retaining the production command's no-authoritative-oracle/fail-closed statement. Parse all tracked Python under `src/synthetic` with `ast` and assert the manifest module's imports are standard-library-only and that generation, exporter, native, calibration, held-out, prevalence, privacy, counterfactual, and evaluator modules do not import `synthetic.synthea_conformance`. Assert the module source contains no imports or calls for `synthea`, `subprocess`, `pathlib.Path`, `csv`, `urllib`, `requests`, Java, or package-writing APIs.

- [x] **Step 2: Run documentation/boundary tests to verify the red state.**

  ```sh
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_synthea_conformance_docs.py tests/synthetic/test_synthea_conformance_boundaries.py
  ```

  Expected: collection or assertions fail because the guide, cross-document links, and regression tests do not yet exist.

- [x] **Step 3: Add the guide and cross-document links.**

  Write `docs/synthea-conformance.md` with a fictional Python snippet that creates a `SyntheaEngineManifest` using only aggregate identities and serializes it for review metadata. Explain that a future runner must supply the pinned engine revision and digest, versioned module bundle, pediatric growth extension, event adapter, exact PPOC exporter, configuration, license/attribution review, derivation binding, and all existing validation, counterfactual, task-utility, reproducibility, privacy, clinical, and release gates. Explain that this repository currently supplies none of that runtime and that a valid declaration cannot authorize execution or imply conformance.

  Link the guide from README and `docs/synthetic-generator.md`. Keep the native generator as release one, preserve its fail-closed authoritative-oracle behavior, and state that this contract is not imported automatically by generation, export, or evaluator code.

- [x] **Step 4: Run docs/boundary tests, lint, and commit.**

  ```sh
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_synthea_conformance_docs.py tests/synthetic/test_synthea_conformance_boundaries.py
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests
  git -c core.whitespace=cr-at-eol,-blank-at-eof diff --check main..HEAD
  git add README.md docs/synthetic-generator.md docs/synthea-conformance.md tests/synthetic/test_synthea_conformance_docs.py tests/synthetic/test_synthea_conformance_boundaries.py
  git commit -m "docs: bound optional synthea route"
  ```

---

### Task 3: Review, verify, merge, and push

**Files:**

- Modify: `.superpowers/sdd/2026-09-01-synthea-conformance-contract/progress.md` (ignored SDD ledger only)

**Interfaces:**

- Consumes the Task 1 and Task 2 commits, focused reports, and existing package/schema gates.
- Produces a reviewed branch ready to merge without changing native generation, source-data boundaries, or remote branch state.

- [x] **Step 1: Run the complete verification matrix.**

  ```sh
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q
  PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests
  PYTHONDONTWRITEBYTECODE=1 python3 schema/build.py --check
  UV_CACHE_DIR=/tmp/ppoc-uv-cache uv lock --check
  git -c core.whitespace=cr-at-eol,-blank-at-eof diff --check main..HEAD
  ```

  Also inspect the diff for only the planned files, scan tracked paths for patient/input/output artifacts, scan visible synthetic modules for forbidden manifest imports, and verify that the production CLI still fails closed with its existing message. Record exact commands/results in the ignored ledger and report files.

- [x] **Step 2: Dispatch scoped and broad reviews.**

  Generate a merge-base-to-`HEAD` review package. Use a fresh reviewer for Task 1, a fresh reviewer for Task 2, and one broad reviewer covering strict parsing, canonical bytes, mutation isolation, token/privacy boundaries, documentation accuracy, native non-imports, source-data scope, and unchanged production behavior. Route every Critical or Important finding to the implementer through one fix/re-review loop; record Minor findings and rulings in the ledger.

- [x] **Step 3: Merge, rerun, push, and confirm parity.**

  Use the finishing workflow: inspect branch/worktree status and staged names, fast-forward `main` from this reviewed branch, rerun the full suite and required checks on merged `main`, push `origin main`, fetch, and verify `git rev-parse main` equals `git rev-parse origin/main`. Preserve unrelated untracked files and report any worktree-cleanup refusal rather than force-removing user-owned artifacts.

  ```sh
  git rev-parse main
  git rev-parse origin/main
  ```

## Self-review checklist

- [x] Every public field, fixed value, parser rejection, serialization rule, boundary, and deferred item in the spec maps to Task 1 tests/implementation or Task 2 docs/static tests.
- [x] No plan step uses placeholder wording or an unspecified validation instruction.
- [x] The method names, field names, fixed strings, and test-only semantics are consistent across the spec, implementation task, documentation task, and verification task.
- [x] The plan never authorizes Synthea execution, source checkout access, network downloads, patient data, or release promotion.

## Completion evidence

- Task 1 implementation and hardening were reviewed over `741e32c..9e844f7`; the fresh review approved the strict aggregate-only contract with no findings.
- Task 2 documentation and boundary tests were reviewed over the historical slice; the fix rounds added literal dynamic-import detection, static alias resolution, and `scripts/augment.py` coverage. Scoped and broad re-reviews approved the final test-only changes through `9555c55` with no findings.
- Merged `main` verification: `2482 passed, 4 skipped`; focused Synthea suite `113 passed`; Ruff, schema validation, `uv lock --check`, whitespace checks, and fail-closed CLI tests passed.
- The published route remains declaration-only: no Synthea checkout, Java runtime, network access, patient data, exporter integration, or release/conformance promotion was added.
