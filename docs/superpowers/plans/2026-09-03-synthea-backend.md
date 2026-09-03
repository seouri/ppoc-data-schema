# Synthea development backend implementation plan

> **Execution note:** Implement this plan test-first. The backend is an opt-in external-checkout route; the native generator, its ordinary profiles, and the default fail-closed CLI must remain behaviorally unchanged.

**Goal:** Generate a deterministic, completely fictional exact-schema PPOC package from a caller-supplied pinned Synthea checkout, with healthy and GHD longitudinal growth trajectories, fresh identifiers, and an aggregate-only in-memory run report.

**Architecture:** Keep process/toolchain integration in `scripts/synthea_backend.py`, outside the ordinary `src/synthetic` runtime. The script verifies a pinned checkout and Java 17, copies only regular source entries into a private temporary build root, supplies a versioned Generic Module Framework overlay, invokes the checked-in Gradle wrapper, parses FHIR R4 output into descriptor-shaped base rows, applies the deterministic GHD growth overlay, and calls the existing exact-schema exporter with `engine="synthea"`. Extend package metadata only enough for generated manifests to identify the engine; retain the native default. No Synthea source or runtime is vendored.

**Spec:** `docs/superpowers/specs/2026-09-03-synthea-backend-design.md`

## Global constraints

- Use the pinned revision `d9d07a6eef91ee5144293b42ab64224d84d124f8`; reject all other revisions.
- Require explicit Java major 17 and Gradle wrapper 9.2.1; reject Java 26 and implicit system Java.
- Run Gradle offline by default; permit dependency downloads only behind an explicit option.
- Never modify the caller checkout, read real patient data, accept arbitrary modules, or expose Synthea names, addresses, UUIDs, raw FHIR, hidden truth, command lines, or subprocess output.
- Use `apply_patch` for repository edits. Preserve existing untracked caches and unrelated changes.
- Keep public errors fixed and redacted: `synthea backend unavailable`.
- Use failing tests before production code for every slice; run focused tests before broad suites.

## Work packages

### Task 1: Engine identity in generated manifests

**Files:**
- Modify: `src/synthetic/package_export.py`
- Modify: `src/synthetic/manifest.py`
- Create: `tests/synthetic/test_manifest_engine.py`
- Modify only as needed: existing package-export tests

**Contract:** `PackageExportMetadata.engine` defaults to `"native"`; `RunManifest.generated(..., engine=...)` defaults to `"native"` and validates a bounded aggregate-safe engine token. The existing smoke/cohort packages serialize exactly as before except for no new field when the default is used. A caller supplying `engine="synthea"` receives a manifest with that engine value.

- [x] Write failing tests for default native behavior, Synthea engine serialization, invalid engine values, and no mutation of existing metadata constructors.
- [x] Run the focused tests and observe failure because metadata/manifest have no engine field.
- [x] Implement the smallest validated optional field and thread it through the exporter.
- [x] Run package-export, manifest, and native CLI tests; inspect manifest JSON and `git diff --check`.

### Task 2: Versioned Synthea Generic Module overlay

**Files:**
- Create: `scripts/synthea/overlay/modules/ppoc_growth_disorder.json`
- Create: `scripts/synthea/overlay/README.md`
- Create: `tests/synthetic/test_synthea_overlay.py`

**Contract:** The module has a fixed name/version, a `0.143291` fictional branch prior, one bounded delay, an `E23.0` condition onset, an evaluation encounter, two fictional lab observations, encounter end, and terminal state. The test validates JSON shape, exact transition coverage, no paths/URLs/real identifiers, and stable canonical digest. The overlay README identifies the module as fictional and development-only.

- [x] Add tests that fail when the overlay directory or exact transition contract is missing.
- [x] Add the module JSON and README with only the approved fictional values.
- [x] Verify JSON parsing, stable digest, and no unsafe content.

### Task 3: FHIR parser, typed observations, and growth overlay

**Files:**
- Modify: `scripts/synthea_backend.py` (initial parser-only slice)
- Create: `tests/synthetic/test_synthea_backend_parser.py`

**Contract:** Add immutable internal records for parsed patients, encounters, observations, and conditions. Implement strict JSON loading (duplicate-key and nonfinite rejection), transaction-bundle and per-patient-bundle traversal, demographic projection, anthropometric code extraction, date/age calculation, diagnosis assignment, fresh deterministic IDs, exact base row construction, and the formula in the spec. Parser output must be a plain mapping with all six base resource keys, descriptor-order rows, and empty ancillary lists. It must never expose source IDs in rows or report data.

- [x] Write hand-built FHIR fixtures and failing tests for patient/encounter/observation parsing, demographic fallback, diagnosis placement, transaction bundles, malformed JSON, unsupported values, and missing anthropometry.
- [x] Add typed records and parser functions using only standard-library JSON/date/math plus existing schema/ID helpers.
- [x] Add failing tests for healthy identity, GHD attenuation monotonicity, BMI identity, positive finite values, and deterministic repeated overlay output.
- [x] Implement the overlay with deterministic seed/index streams and bounded severity.
- [x] Add aggregate-only `SyntheaBackendReport` with canonical JSON and tests rejecting paths, identifiers, raw values, and mutable aliases.
- [x] Run parser/overlay tests and Ruff.

### Task 4: Checkout/toolchain verification and isolated runner

**Files:**
- Modify: `scripts/synthea_backend.py`
- Create: `tests/synthetic/test_synthea_backend_runner.py`

**Contract:** Add `SyntheaBackendConfig`, `SyntheaBackendUnavailable`, and runner helpers. Verify revision, tracked cleanliness, regular required files, Java 17, wrapper 9.2.1, and overlay digest. Copy only regular entries to a private temporary root; reject symlinks/special files. Build argument arrays with `shell=False`, fixed pediatric age/date/export flags, finite timeout, and offline-by-default behavior. Accept only caller-selected checkout, Java home, output, patient count, seed, descriptor, reference date, software revision, timeout, and explicit network opt-in.

- [x] Write failing fake-checkout/fake-wrapper tests for revision and Java rejection, copy isolation, command shape, timeout/failure redaction, no checkout mutation, and output collisions.
- [x] Implement strict verification and private copy helpers.
- [x] Implement subprocess invocation with captured/discarded output and fixed public failures.
- [x] Verify the runner never writes a promoted package before subprocess and parser success.
- [x] Run runner tests and Ruff.

### Task 5: Exact-schema package orchestration and optional CLI

**Files:**
- Modify: `scripts/synthea_backend.py`
- Create: `tests/synthetic/test_synthea_backend_integration.py`
- Create: `tests/synthetic/test_synthea_backend_cli.py`

**Contract:** `generate_synthea_package(...)` verifies the environment, runs Synthea, parses/overlays rows, builds a configuration digest, calls `build_development_runtime` and `export_exact_schema_package` with `engine="synthea"`, and returns `SyntheaBackendResult(package, report)`. The script CLI accepts only explicit backend arguments and prints a package path plus aggregate report after success. It never modifies `synthetic.generate`; no-profile behavior remains unchanged.

- [x] Write failing fake-wrapper integration tests for exact eight resources, manifest engine/test-only fields, GHD and healthy groups, fresh IDs, deterministic reruns, different-seed divergence, and no promoted output after failure.
- [x] Implement orchestration and package export using the existing test-only development binding.
- [x] Add an opt-in pinned-checkout smoke test guarded by `SYNTHEA_CHECKOUT`/Java17/offline-cache availability; skip rather than weaken ordinary CI when unavailable.
- [x] Run focused integration and CLI tests; run the ordinary generator regression tests.

### Task 6: Documentation and conformance boundary update

**Files:**
- Modify: `docs/synthea-conformance.md`
- Modify: `docs/synthetic-generator.md`
- Modify: `README.md` only if a concise link is needed
- Create: `docs/synthea-backend.md`
- Create: `tests/synthetic/test_synthea_backend_docs.py`
- Update: this plan/spec status lines after implementation

**Contract:** Existing docs must say the external adapter is implemented and show the one explicit command, while retaining that Synthea is not vendored, the Java/Gradle preflight is external, the native route remains ordinary/release-one, and clinical/population/privacy/non-matchability/held-out/release/Synthea conformance evidence remains separate. Remove stale “no engine adapter” wording where it contradicts the implementation; retain “no vendored runtime/conformance result/authorization.”

- [x] Write failing documentation tests for the new command, fixed revision/Java17, package/manifest boundary, growth overlay, no-real-data boundary, and native fail-closed boundary.
- [x] Add the concise backend guide and links; update existing Synthea and synthetic-generator sections only where behavior changed.
- [x] Run docs tests, all focused Synthea tests, `git diff --check`, and a fresh content review.

### Task 7: Verification and integration review

**Files:** no new source expected.

- [x] Run `PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q -p no:cacheprovider` for the complete Python suite.
- [x] Run `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src tests` and the focused backend/overlay Ruff check. The broader `scripts` scan still reports pre-existing style findings in the byte-preserved imported `augment.py`/`harrall_outliers.py` files.
- [x] Run schema checks and deterministic fake-backend and real-adapter reruns.
- [x] Run the pinned Java17 Synthea smoke when external prerequisites are available; record the independent full-test `134` as an environment issue, not backend evidence.
- [x] Review the working-tree names/stat/diff and preserve unrelated untracked artifacts.

## Final acceptance checklist

- [x] All focused and complete tests pass; the optional external smoke passes when enabled and is skipped with the prerequisite reason otherwise.
- [x] The pinned external checkout remains unchanged after a backend run.
- [x] Exact schema and augmented resources are validated; the manifest uses `engine="synthea"` and `test_only_derivation=true`.
- [x] Healthy and GHD longitudinal growth are present, deterministic, BMI-consistent, and aggregate-reported without hidden state.
- [x] Fresh synthetic IDs are used; no Synthea identifiers, names, raw FHIR, paths, or subprocess details escape.
- [x] Native profiles/default CLI behavior is unchanged.
- [x] Documentation clearly distinguishes development bridge behavior from conformance, clinical, prevalence, privacy/non-matchability, held-out, and release claims.
