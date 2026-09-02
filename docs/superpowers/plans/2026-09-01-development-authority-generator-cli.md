# Development-Only CDC-Backed Generator CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit, reproducible development CLI that uses the pinned CDC tables and source-matched augmenter to emit exact-schema smoke and healthy-plus-GHD cohort packages while retaining test-only classification and all real-data/release gates.

**Architecture:** Keep `scripts/augment.py` byte-for-byte unchanged and add a strict `CdcGrowthReference` adapter plus a small development runtime factory. The CLI composes those identities with the existing smoke generator, native cohort/resource projection, and atomic exact-schema exporter; no-profile invocation remains fail-closed and every successful package is marked `test_only_derivation=true`.

**Tech Stack:** Python 3.12+, standard-library CSV/JSON/hashlib/pathlib/dataclasses, existing NumPy-backed native growth and observation kernels, existing package exporter and derivation-binding contracts, the pinned `uv.lock` environment, pytest, Ruff, and the checked-in CDC/augmenter runtime closure.

**Spec:** `docs/superpowers/specs/2026-09-01-development-authority-generator-cli-design.md`

## Global Constraints

- Preserve all 14 files in `data/augment-runtime-manifest.json` byte-for-byte; the manifest digest and `scripts/augment.py` bytes must not change.
- Treat the CDC/augmenter pair as development-authoritative only: reproducibility within the explicit profiles is in scope; clinical validity, prevalence, demographic representativeness, privacy/non-matchability, and release approval are not.
- Set `test_only=true` in the development binding and never call `require_approved_derivation_binding` or mark a package clinically valid.
- Read no patient, visit, governed calibration, held-out, privacy, network, Synthea, model, or arbitrary diagnosis input; only the repository descriptor, pinned runtime/reference files, source metadata, and wholly generated rows are allowed.
- Use exact mapping/version tokens `cdc-lms-reference-v1`, `cdc-lms-mapping-v1`, `development-generator-v1`, `development-cohort-v1`, `development-augmenter-v1`, and `augment-runtime-v1` where their corresponding identities are required.
- Resolve the descriptor from the repository checkout by default, use metadata defaults `2026-09-01T00:00:00Z` and `development-generator-v1`, and reject output collisions without overwriting.
- Support only CDC reference sex `M` and `F`; keep the required `F/M/U` mapping structurally complete but assign the development cohort zero probability for visible `U`.
- Use the exact age schedules, observation probabilities, module prior, demographic weights, BMI 730-day boundary rule, `abs(L) < 1e-6` branch, `age_days / 30.4375` coordinate, and dependency digest stated in the spec.
- Keep latent trajectories, disorder state, source events, private observation truth, stream identities, patient-level diagnostics, paths, and subprocess text out of visible rows, mappings, manifests, reports, and exceptions.
- Every task is test-first, runs focused tests and Ruff, checks staged whitespace, and commits only its named files; pre-existing `__pycache__` directories remain unstaged.

## File and Responsibility Map

- `src/synthetic/cdc_reference.py`: strict manifest-backed CDC LMS table loader and inverse-LMS `GrowthReference`; it may import only immutable manifest-digest constants from `synthetic.augmenter_oracle` and never imports `scripts.augment` or patient input.
- `src/synthetic/augmenter_oracle.py`: existing source-matched oracle plus a redacted read-only runtime/lock verification helper.
- `src/synthetic/development_runtime.py`: fixed development binding, runtime composition, cohort configuration, configuration hashing, and cohort-to-package bridge.
- `src/synthetic/generate.py`: backward-compatible `generate_smoke` profile parameter, CLI argument parsing, explicit profile dispatch, and fixed public failures.
- `tests/synthetic/test_cdc_reference.py`: source-table parsing, equations, domains, fingerprints, and import-boundary tests.
- `tests/synthetic/test_development_runtime.py`: runtime identity, binding, fixed profile configuration, cohort projection, and package metadata tests.
- `tests/synthetic/test_generate_cli.py`: subprocess smoke/cohort/no-profile/collision/determinism tests; the scale case remains opt-in.
- `tests/synthetic/test_generate_smoke.py`: regression coverage for the default `smoke` Python API profile.
- `tests/synthetic/test_augmenter_oracle_boundaries.py` and `tests/synthetic/test_augmenter_oracle_docs.py`: explicit composition allow-list and documentation assertions.
- `docs/synthetic-generator.md`: user-facing CLI commands, profile semantics, output/lifecycle behavior, and non-claims.

---

### Task 1: Implement the strict CDC growth-reference adapter

**Files:**
- Create: `src/synthetic/cdc_reference.py`
- Create: `tests/synthetic/test_cdc_reference.py`

**Interfaces:**
- Consumes: `data/augment-runtime-manifest.json`, its four LMS table entries (`statage_combined.csv`, `wtage_combined.csv`, `bmiagerev.csv`, `hcageinf.csv`), and the manifest digest constants in `synthetic.augmenter_oracle`.
- Produces: `CdcGrowthReference.from_repository(repository_root: Path) -> CdcGrowthReference`; `reference_id == "cdc-lms-reference-v1"`; `source_sha256: str`; `metrics`, `min_age_days`, `max_age_days`; and `value(metric: str, age_days: int, reference_sex: str, z: float) -> float`.

- [x] **Step 1: Write the failing reference tests**

Add tests with a repository-root fixture and no patient files:

```python
def test_repository_reference_exposes_manifest_backed_metrics() -> None:
    reference = CdcGrowthReference.from_repository(ROOT)

    assert reference.reference_id == "cdc-lms-reference-v1"
    assert reference.metrics == (
        "bmi",
        "head_circumference_cm",
        "height_cm",
        "length_cm",
        "weight_kg",
    )
    assert reference.min_age_days == 0
    assert reference.max_age_days == 7305
    assert len(reference.source_sha256) == 64
```

Add equation tests for a source row and an interpolated age. For `M`, age zero, and `z=0.0`, `length_cm` must equal the `M` column from `statage_combined.csv`; for an intermediate age, compare `value()` with a test-local `numpy.interp` of `L`, `M`, and `S`, using `math.isclose` at `1e-12` relative tolerance. Test both `abs(L) < 1e-6` logarithmic inversion through `_inverse_lms(l, m, s, z)` and nonzero Box-Cox inversion with a tiny temporary table parsed through `_parse_lms_table(source_bytes, metric)`.

Add contract tests that source sex `1` maps to `M`, source sex `2` maps to `F`, `U` and other sexes fail, unknown metrics fail, noninteger/negative ages fail, nonfinite `z` fails, and requests outside a metric's domain fail. Test the documented exception for `bmi` at exactly 730 days: it uses the 24-month row; 729 days remains outside the domain. Test digest drift, malformed UTF-8, duplicate headers/rows, nonfinite LMS values, nonpositive `M`/`S`, unsorted age rows, missing required columns, symlinked table paths, and an altered manifest.

Finally, parse the module source with `ast` and assert it does not import `scripts.augment`, `pandas`, `synthetic.generate`, or any governed input module.

- [x] **Step 2: Run the reference tests to verify they fail**

Run:

```sh
uv run pytest -q tests/synthetic/test_cdc_reference.py
```

Expected: collection or attribute failures because `synthetic.cdc_reference` and `CdcGrowthReference` do not yet exist. Correct only test-fixture syntax before implementation.

- [x] **Step 3: Implement the source-matched adapter**

Verify the manifest bytes against `AUGMENTER_RUNTIME_MANIFEST_SHA256`, resolve only the four expected relative table paths, reject absolute paths, traversal, backslashes, symlinks, nonregular files, duplicate entries, and digest/byte-count mismatches, then decode with strict UTF-8 while accepting the single source BOM through `utf-8-sig`. Require the source columns `Sex`, `Agemos`, `L`, `M`, and `S`; map integer `1`/`2` to `M`/`F`; reject unknown values; require finite `L`, positive finite `M`/`S`; and require unique, increasing ages for every sex series.

Store the source-month coordinate and LMS arrays per `(metric, reference_sex)`. Map `statage_combined.csv` to both `length_cm` and `height_cm`, `wtage_combined.csv` to `weight_kg`, `bmiagerev.csv` to `bmi`, and `hcageinf.csv` to `head_circumference_cm`. Use `numpy.interp` on `age_days / 30.4375`; allow the exact one-day smoke boundary by substituting 24.0 months only for `metric == "bmi" and age_days == 730`; reject all other out-of-domain values. Invert LMS with `abs(L) < 1e-6` for `M * exp(S * z)`, otherwise `M * (1 + L * S * z) ** (1 / L)`, and reject nonpositive/nonfinite results.

Compute `source_sha256` as SHA-256 over canonical JSON containing `reference_id="cdc-lms-reference-v1"`, mapping token `cdc-lms-mapping-v1`, the ordered table names, and their exact manifest digests. Expose `min_age_days=0` and `max_age_days=7305` for the age-regime kernel while enforcing each metric's own source domain inside `value()`.

- [x] **Step 4: Run focused tests, lint, and commit**

```sh
uv run pytest -q tests/synthetic/test_cdc_reference.py
uv run ruff check src/synthetic/cdc_reference.py tests/synthetic/test_cdc_reference.py
git diff --check
git add src/synthetic/cdc_reference.py tests/synthetic/test_cdc_reference.py
git commit -m "feat: add pinned CDC growth reference"
```

### Task 2: Verify the runtime closure and build the development binding

**Files:**
- Modify: `src/synthetic/augmenter_oracle.py`
- Create: `src/synthetic/development_runtime.py`
- Create: `tests/synthetic/test_development_runtime.py`
- Modify: `tests/synthetic/test_augmenter_oracle_boundaries.py`

**Interfaces:**
- Consumes: `CdcGrowthReference`, `SourceMatchedAugmenterOracle`, `DerivationBinding`, `DerivationBindingReport`, `EXPECTED_SCHEMA_FINGERPRINT`, `AUGMENTER_RUNTIME_MANIFEST_SHA256`, and `uv.lock`.
- Produces: `verify_source_matched_runtime(repository_root: Path) -> None`; frozen `DevelopmentRuntime(reference, derivation_oracle, derivation_binding, dependency_fingerprint)`; and `build_development_runtime(repository_root: Path) -> DevelopmentRuntime`.

- [x] **Step 1: Write failing runtime and boundary tests**

Test the verification helper with the repository root, a copied root whose `uv.lock` byte differs, a missing lock, a modified manifest, a modified runtime file, and a symlinked runtime file. The success case returns `None`; every failure raises only `DerivationUnavailable("source-matched augmenter unavailable")` without path or subprocess text.

Test the factory's exact identities:

```python
def test_development_runtime_binds_reference_and_test_only_oracle() -> None:
    runtime = build_development_runtime(ROOT)

    assert runtime.reference.reference_id == "cdc-lms-reference-v1"
    assert runtime.reference.source_sha256 == runtime.derivation_binding.reference_standard.standard_fingerprint
    assert runtime.derivation_oracle.oracle_id == "augmenter-cli-v1"
    assert runtime.derivation_binding.binding_id == "development-augmenter-v1"
    assert runtime.derivation_binding.test_only is True
    assert runtime.derivation_binding.oracle.source_kind == "authoritative_implementation"
    assert runtime.derivation_binding.review.status == "PENDING"
    assert runtime.derivation_binding.golden_evidence.bidirectional_case_count == 0
    assert runtime.derivation_binding.golden_evidence.synthetic_fuzz_case_count == 0
```

Assert `validate_derivation_binding(...).status` is not `FAIL`, the binding schema fingerprint is exact, all required golden categories occur once, the dependency fingerprint equals `sha256((ROOT / "uv.lock").read_bytes()).hexdigest()`, and a runtime with a mismatched reference standard or oracle identity/fingerprint is rejected before composition. Have `DevelopmentRuntime.__post_init__` enforce the reference fingerprint/standard identity and oracle identity/fingerprint/classification invariants explicitly; `BoundDerivationOracle` must still reject a mismatched derivation result at derive time. Extend the boundary scanner so only `development_runtime.py` and `cdc_reference.py` may import `synthetic.augmenter_oracle`; all other visible/evaluator modules remain forbidden from importing the candidate adapter.

- [x] **Step 2: Run the runtime tests to verify they fail**

Run:

```sh
uv run pytest -q tests/synthetic/test_development_runtime.py tests/synthetic/test_augmenter_oracle_boundaries.py
```

Expected: missing-helper, missing-factory, or boundary failures. Correct only fixture setup before implementation.

- [x] **Step 3: Implement redacted runtime verification and binding construction**

Add the fixed lock digest and helper in `augmenter_oracle.py`:

```python
UV_LOCK_SHA256 = "d17f8c2613da7c59dd858fe1e39025ce72e0241fb0bbc400772ab4273a694810"


def verify_source_matched_runtime(repository_root: Path) -> None:
    """Verify the manifest-listed runtime and locked environment without leaking details."""
```

Require an exact `Path`, verify `uv.lock` as a regular non-symlink file with the fixed digest, call the existing `_verify_manifest`, and convert every ordinary exception to `_unavailable()`. Leave `SourceMatchedAugmenterOracle.derive()` and its private snapshot/output checks unchanged except for reusing this helper at the start of `_derive` so direct oracle calls receive the same lock gate.

In `development_runtime.py`, define frozen `DevelopmentRuntime` and `build_development_runtime()`. Verify the runtime, load `CdcGrowthReference.from_repository()`, and construct `SourceMatchedAugmenterOracle(repository_root)`. Build `DerivationBinding.from_mapping()` with exact schema, `binding_id="development-augmenter-v1"`, oracle identity `augmenter-cli-v1`, implementation fingerprint `AUGMENTER_RUNTIME_MANIFEST_SHA256`, source revision `augment-runtime-v1`, `source_kind="authoritative_implementation"`, the locked digest, reference standard `cdc-lms-reference-v1`/the adapter fingerprint/`cdc-lms-mapping-v1`, all `REQUIRED_GOLDEN_CATEGORIES`, null evidence identifiers, zero evidence counts, `parity_status="UNEVALUABLE"`, pending review, and `test_only=True`. Make `DevelopmentRuntime.__post_init__` require the bound reference standard to equal the loaded adapter identity/fingerprint and the bound oracle identity/fingerprint/source kind to equal the constructed oracle/runtime constants. Do not serialize paths, table names, rows, or source prose into the binding.

- [x] **Step 4: Run focused tests, lint, and commit**

```sh
uv run pytest -q tests/synthetic/test_development_runtime.py tests/synthetic/test_augmenter_oracle_boundaries.py
uv run ruff check src/synthetic/augmenter_oracle.py src/synthetic/development_runtime.py tests/synthetic/test_development_runtime.py tests/synthetic/test_augmenter_oracle_boundaries.py
git diff --check
git add src/synthetic/augmenter_oracle.py src/synthetic/development_runtime.py tests/synthetic/test_development_runtime.py tests/synthetic/test_augmenter_oracle_boundaries.py
git commit -m "feat: compose development derivation runtime"
```

### Task 3: Add the backward-compatible smoke profile and explicit CLI dispatch

**Files:**
- Modify: `src/synthetic/generate.py`
- Modify: `tests/synthetic/test_generate_smoke.py`
- Create: `tests/synthetic/test_generate_cli.py`

**Interfaces:**
- Consumes: `DevelopmentRuntime`, `build_development_runtime`, existing `generate_smoke`, `PackageExportMetadata`, and the fixed CLI constants.
- Produces: `generate_smoke(..., profile: str = "smoke") -> Path`; `CLI_UNAVAILABLE_MESSAGE = "No production growth reference or authoritative derivation oracle is configured"`; and a `main()` that dispatches only `development-smoke` or `development-cohort` after parsing required operational arguments.

- [x] **Step 1: Write failing smoke/CLI tests**

Extend existing smoke tests to pass no profile and assert the manifest remains `profile == "smoke"`; add a profile override test that passes `profile="development-smoke"` and asserts the metadata profile/configuration hash change while all existing direct API behavior remains intact.

Add subprocess tests using `cwd=ROOT` and fresh temporary roots:

```python
def test_no_profile_remains_fail_closed(tmp_path: Path) -> None:
    output = tmp_path / "no-profile"
    result = subprocess.run(
        [sys.executable, "-m", "synthetic.generate",
         "--output", str(output), "--patients", "1", "--seed", "20260901"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert result.stderr.strip().endswith(CLI_UNAVAILABLE_MESSAGE)
    assert not output.exists()
```

Test an unknown profile with the same fixed message and no output. Test `development-smoke` with a small count (3) and assert the exact eight descriptor resources, `manifest.json` profile/reference/fingerprint/status fields, augmented headers, structural validation success, and no latent fields. Run the same seed into two different output roots and compare every non-manifest file hash. Test an existing target and an altered runtime through the CLI: neither may promote a package or expose a path/subprocess traceback.

- [x] **Step 2: Run smoke/CLI tests to verify they fail**

Run:

```sh
uv run pytest -q tests/synthetic/test_generate_smoke.py tests/synthetic/test_generate_cli.py
```

Expected: the profile parameter, CLI selector, and development route are absent. Correct only test command/fixture errors before implementation.

- [x] **Step 3: Implement the smoke profile parameter and CLI**

Add `profile: str = "smoke"` to `generate_smoke()` after the required binding argument. Validate it with the existing aggregate-safe token rule, include it in the canonical smoke configuration hash, and pass it to `PackageExportMetadata(profile=profile)`. Existing callers and tests must retain `profile="smoke"`.

Replace only the current `main()` dispatch body with an explicit parser:

```python
parser.add_argument("--profile", default=None)
parser.add_argument("--descriptor", type=Path, default=None)
parser.add_argument("--reference-time", default="2026-09-01T00:00:00Z")
parser.add_argument("--software-revision", default="development-generator-v1")
```

Resolve a missing descriptor to `Path(__file__).resolve().parents[2] / "datapackage.json"`. If `args.profile` is absent or not one of the two supported names, raise `SystemExit(CLI_UNAVAILABLE_MESSAGE)` before building a runtime or checking the output. For `development-smoke`, call `build_development_runtime(repository_root)` and `generate_smoke(..., reference=runtime.reference, derivation_oracle=runtime.derivation_oracle, derivation_binding=runtime.derivation_binding, profile="development-smoke")`. Catch ordinary generation/reference/binding/lifecycle errors at the CLI boundary and raise the fixed redacted `SystemExit("Synthetic development generation unavailable")`; preserve the no-profile message exactly. Do not add a real-data, calibration, held-out, privacy, Synthea, network, model, or arbitrary diagnosis argument.

- [x] **Step 4: Run focused tests, lint, and commit**

```sh
uv run pytest -q tests/synthetic/test_generate_smoke.py tests/synthetic/test_generate_cli.py
uv run ruff check src/synthetic/generate.py tests/synthetic/test_generate_smoke.py tests/synthetic/test_generate_cli.py
git diff --check
git add src/synthetic/generate.py tests/synthetic/test_generate_smoke.py tests/synthetic/test_generate_cli.py
git commit -m "feat: enable development smoke CLI profile"
```

### Task 4: Compose the fixed healthy-plus-GHD cohort package profile

**Files:**
- Modify: `src/synthetic/development_runtime.py`
- Modify: `tests/synthetic/test_development_runtime.py`
- Modify: `src/synthetic/generate.py`
- Modify: `tests/synthetic/test_generate_cli.py`

**Interfaces:**
- Consumes: `DevelopmentRuntime`, `CohortConfig`, `CalibrationSamplingProfile`, `generate_native_cohort`, `HealthyGrowthModule`, `GrowthHormoneDeficiencyModule`, `ObservationPolicy`, `export_exact_schema_package`, and the exact descriptor contract.
- Produces: `development_cohort_config(patient_count: int, seed: int) -> CohortConfig`; `development_calibration_profile() -> CalibrationSamplingProfile`; `build_development_cohort(runtime: DevelopmentRuntime, *, descriptor: Mapping[str, object], patient_count: int, seed: int) -> NativeCohort`; `generate_development_cohort(runtime: DevelopmentRuntime, *, descriptor_path: Path, output: Path, patient_count: int, seed: int, reference_time: str, software_revision: str) -> Path`; and the `development-cohort` CLI branch.

- [x] **Step 1: Write failing cohort-package tests**

Add a direct runner test with 64 patients and seed `20260901`. Assert a promoted package has exactly the eight descriptor resources, unique `syn-` patient/visit identifiers, longitudinal visits at every fixed age, both healthy and GHD latent module classes in the evaluator-held cohort before export, no visible latent module/severity/truth fields, empty but descriptor-shaped ancillary resources, and manifest fields `profile == "development-cohort"`, `reference_id == "cdc-lms-reference-v1"`, `reference_sha256 == runtime.reference.source_sha256`, `derivation_fingerprint == AUGMENTER_RUNTIME_MANIFEST_SHA256`, `test_only_derivation is True`, and status `STRUCTURE_VALIDATED_TEST_ORACLE`.

Assert the fixed configuration is exact:

```python
assert config.ages_days == (0, 365, 730, 1460, 2190, 3650, 4380, 5114, 5475, 6200, 7305)
assert config.observation_policy.window_start_age_days == 0
assert config.observation_policy.window_end_age_days == 7306
assert config.observation_policy.length_availability_probability == 0.0
assert config.observation_policy.height_availability_probability == 1.0
assert config.observation_policy.weight_availability_probability == 1.0
assert config.observation_policy.head_circumference_availability_probability == 1.0
assert tuple((item.kind, item.probability) for item in config.module_weights) == (
    (DisorderKind.HEALTHY, 0.5),
    (DisorderKind.GROWTH_HORMONE_DEFICIENCY, 0.5),
)
```

Test the `U`-sex weight is zero, the reference mapping remains `F/M/U` one-to-one, all demographic weights sum within the existing envelope, and the configuration hash is identical across repeated runs. Test a descriptor collision before generation and a missing/non-PASS bundle as fixed redacted failures with no promoted output.

- [x] **Step 2: Run cohort-package tests to verify they fail**

Run:

```sh
uv run pytest -q tests/synthetic/test_development_runtime.py tests/synthetic/test_generate_cli.py
```

Expected: the fixed profile factory and cohort CLI branch are missing. Correct only fixture setup before implementation.

- [x] **Step 3: Implement fixed cohort configuration and export bridge**

In `development_runtime.py`, add immutable builders for `CalibrationSamplingProfile` and `CohortConfig`, named `development_calibration_profile()` and `development_cohort_config()`. Use profile/artifact identity `development-cohort-v1`, target registry `calibration-targets-v1`, sex weights `(F=0.50, M=0.50, U=0.00)`, ethnicity weights `(blank=0.02, Not Hispanic or Latino=0.65, Hispanic or Latino=0.18, Choose not to Answer=0.03, Unknown=0.04, Unable to collect=0.03, Patient does not know=0.05)`, race weights `(blank=0.01, American Indian or Alaska Native=0.01, Another Race=0.03, Asian=0.08, Black or African American=0.12, Choose not to answer=0.02, Middle Eastern or Northern African=0.02, Native Hawaiian or Other Pacific Islander=0.01, Patient does not know=0.02, Unable to collect=0.02, Unknown=0.04, White=0.62)`, race multiselect `0.06`, and legacy recorded-outcome fields `0.0`. Use the exact age tuple and observation policy from the spec, `reference_sex_mapping=(('F','F'),('M','M'),('U','U'))`, healthy/GHD weights `0.5/0.5`, and the existing default `AgeRegimeConfig`.

Implement `build_development_cohort()` as the in-memory composition seam: call `generate_native_cohort(config, runtime.reference, calibration, modules={...}, descriptor=descriptor)`, require every member bundle to be present and `validate_observed_resources(bundle).status is PASS`, and return the typed `NativeCohort` for evaluator-only tests. Implement `generate_development_cohort()` to preflight `_require_output_available(output)` before cohort sampling, load the exact descriptor, call the builder, and flatten rows in member order into exactly `BASE_RESOURCE_NAMES`. Compute a canonical JSON configuration hash over the profile version, all fixed policy/weight mappings, ages, module versions, and reference identity/fingerprint; do not include patient IDs or truth. Call `export_exact_schema_package()` with `PackageExportMetadata(profile="development-cohort", reference_id=runtime.reference.reference_id, reference_sha256=runtime.reference.source_sha256, configuration_sha256=hash, ...)`, the source-matched oracle, and the test-only binding.

Wrap reference, cohort, projection, and export failures in the existing redacted package failure contract. Never call `to_mapping()` on latent trajectories for export and never place a disorder label in any public package artifact.

In `generate.py`, add the `development-cohort` branch that builds the same runtime and calls `generate_development_cohort()` with parsed metadata. Keep both profile names explicit; no profile continues to raise `CLI_UNAVAILABLE_MESSAGE`.

- [x] **Step 4: Run focused tests, lint, and commit**

```sh
uv run pytest -q tests/synthetic/test_development_runtime.py tests/synthetic/test_generate_cli.py
uv run ruff check src/synthetic/development_runtime.py src/synthetic/generate.py tests/synthetic/test_development_runtime.py tests/synthetic/test_generate_cli.py
git diff --check
git add src/synthetic/development_runtime.py src/synthetic/generate.py tests/synthetic/test_development_runtime.py tests/synthetic/test_generate_cli.py
git commit -m "feat: add development cohort package profile"
```

### Task 5: Update the user guide and boundary/documentation contracts

**Files:**
- Modify: `docs/synthetic-generator.md`
- Modify: `tests/synthetic/test_augmenter_oracle_docs.py`
- Modify: `tests/synthetic/test_augmenter_oracle_boundaries.py`
- Modify: `tests/synthetic/test_cohort_boundaries.py` only to include new explicit runtime allow-list assertions

**Interfaces:**
- Consumes: the two working CLI profiles, `build_development_runtime`, the source-matched candidate/oracle guides, and the existing exact-schema output contract.
- Produces: copy-pasteable development commands and tests proving that explicit development composition is enabled without turning the default/no-profile path into a production route.

- [x] **Step 1: Write failing documentation and boundary tests**

Require the guide to contain both exact commands:

```text
uv run python -m synthetic.generate --profile development-smoke --output /tmp/ppoc-development-smoke --patients 1000 --seed 20260901
uv run python -m synthetic.generate --profile development-cohort --output /tmp/ppoc-development-cohort --patients 1000 --seed 20260901
```

Also require `development-authoritative`, `cdc-lms-reference-v1`, `test_only_derivation=true`, the fixed age schedule, the zero-U rationale, the 730-day BMI boundary, exact eight-resource output, no-profile fixed message, no real/governed inputs, and explicit deferred clinical/prevalence/privacy/non-matchability/held-out/Synthea/release gates. Update the candidate-guide cross-document test to accept the new statement that only explicit development profiles compose the candidate while retaining the exact no-profile failure string.

Add a boundary test that scans `development_runtime.py` for forbidden real-data/calibration/held-out/privacy/Synthea imports and arguments, allows only the declared descriptor/runtime/package-export reads, rejects network/process escapes outside the existing oracle, and confirms `generate.py` has no `--real-root`, `--calibration`, `--heldout`, `--privacy`, `--synthea`, or model option.

- [x] **Step 2: Run documentation/boundary tests to verify they fail**

Run:

```sh
uv run pytest -q tests/synthetic/test_augmenter_oracle_docs.py tests/synthetic/test_augmenter_oracle_boundaries.py tests/synthetic/test_cohort_boundaries.py
```

Expected: missing CLI documentation or an overly strict candidate-import boundary. Correct only assertions that target stale wording before editing prose or scanner allow-lists.

- [x] **Step 3: Document the explicit development route and preserve the no-profile boundary**

Add a `## Explicit development CLI profiles` section near the current-scope material. Explain that `development-smoke` preserves the three-visit smoke contract and that `development-cohort` emits the fixed healthy/GHD, full-age, visible-resource profile. Document the defaults, collision behavior, deterministic rerun rule (compare distinct output roots), manifest fields, source/runtime lock pins, the BMI 730-day boundary, zero-U mapping, empty ancillary resources, and the fact that all outputs remain test-only.

Rewrite stale sentences that say the command is entirely unavailable to say precisely: the default/no-profile invocation remains fail-closed with `No production growth reference or authoritative derivation oracle is configured`; explicit development profiles use the pinned source-matched runtime and do not establish production authority. Keep the existing candidate augmenter and optional Synthea links, and preserve every deferred-gate/non-claim statement.

Adjust `test_augmenter_oracle_boundaries.py` so exactly `development_runtime.py` and `cdc_reference.py` are allowed to import `synthetic.augmenter_oracle`; retain the scanner's rejection of that import everywhere else. Keep `test_cohort_boundaries.py`'s in-memory cohort restrictions unchanged and add only the explicit composition module's allow-list checks.

- [x] **Step 4: Run focused tests, lint, and commit**

```sh
uv run pytest -q tests/synthetic/test_augmenter_oracle_docs.py tests/synthetic/test_augmenter_oracle_boundaries.py tests/synthetic/test_cohort_boundaries.py
uv run ruff check tests/synthetic/test_augmenter_oracle_docs.py tests/synthetic/test_augmenter_oracle_boundaries.py tests/synthetic/test_cohort_boundaries.py
git diff --check
git add docs/synthetic-generator.md tests/synthetic/test_augmenter_oracle_docs.py tests/synthetic/test_augmenter_oracle_boundaries.py tests/synthetic/test_cohort_boundaries.py
git commit -m "docs: document development generator profiles"
```

### Task 6: Add opt-in source-backed scale coverage and run the complete verification suite

**Files:**
- Modify: `tests/synthetic/test_development_scale.py`
- Modify: `tests/synthetic/test_generate_cli.py`
- Modify: `docs/synthetic-generator.md` to distinguish the existing native direct scale test from the new CLI composition scale test

**Interfaces:**
- Consumes: both explicit profile runners, the pinned CDC reference/oracle, the existing `SYNTHETIC_RUN_SCALE=1` marker, and all repository validators.
- Produces: opt-in 10,000-patient evidence that the development route can sustain the existing exact-schema/trajectory/derivation composition without adding multi-minute work to ordinary CI.

- [x] **Step 1: Write the opt-in scale assertions**

Add a `@pytest.mark.scale` test guarded by `os.environ.get("SYNTHETIC_RUN_SCALE") == "1"` that runs `development-cohort` with the existing 10,000-patient count, the fixed age schedule, and a temporary output root. Assert exact package row counts, unique synthetic IDs, manifest schema/reference/derivation/test-only fields, and no latent truth in any package artifact. Keep the current 10,000-patient native validation profile and its three fixed seeds; do not add a real-data comparison or prevalence assertion.

- [x] **Step 2: Run the scale test in its normal skipped mode**

```sh
uv run pytest -q tests/synthetic/test_development_scale.py tests/synthetic/test_generate_cli.py
```

Expected: all ordinary tests pass and the scale case is skipped with its explicit opt-in reason.

- [x] **Step 3: Run the opt-in scale test**

```sh
SYNTHETIC_RUN_SCALE=1 uv run pytest -q -m scale tests/synthetic/test_development_scale.py tests/synthetic/test_generate_cli.py
```

Expected: the 10,000-patient fictional package completes, validates, and is written only beneath pytest's temporary directory. If source-backed output fails, fix only deterministic reference/runtime/performance defects; do not relax the test-only or exact-schema checks.

- [x] **Step 4: Run full verification and inspect the staged scope**

```sh
uv run pytest -q
uv run ruff check src tests
python3 schema/build.py --check
uv lock --check
git add tests/synthetic/test_development_scale.py tests/synthetic/test_generate_cli.py docs/synthetic-generator.md
git -c core.whitespace=cr-at-eol,-blank-at-eof diff --cached --check
git status --short --branch
```

Stage only the named scale test/documentation files before the cached-whitespace check; confirm no real-data files, generated packages, lock changes, or cache directories are staged. Read the final diff against the spec and verify the source runtime manifest and `scripts/augment.py` hashes are unchanged.

- [x] **Step 5: Commit the scale/verification changes**

```sh
git add tests/synthetic/test_development_scale.py tests/synthetic/test_generate_cli.py docs/synthetic-generator.md
git commit -m "test: exercise development generator at scale"
```

### Task 7: Fresh review, integration, and publication

**Files:**
- Review: all files changed by Tasks 1–6 and `docs/superpowers/specs/2026-09-01-development-authority-generator-cli-design.md`
- Modify: only the responsible task files if a review finding is confirmed

**Interfaces:**
- Consumes: task commits, focused/full verification output, the design spec, and the repository's existing review/merge conventions.
- Produces: a reviewed `main` commit published to `origin/main`, with the source closure, test-only classification, no-profile boundary, and docs all synchronized.

- [x] **Step 1: Perform a fresh read-only review**

Check every spec acceptance criterion against code and tests. Inspect the staged names/stat, `git diff --cached --check`, manifest digest, `uv.lock` digest, source-script bytes, CLI error strings, package inventory, configuration hash inputs, and documentation claims. Search for `TODO`, `TBD`, `FIXME`, `test_only=False`, `require_approved_derivation_binding`, real-data argument names, and hidden-truth fields in visible serializers.

- [x] **Step 2: Resolve review findings with focused test-first fixes**

For each confirmed finding, add the smallest failing regression test, implement the narrow fix in the owning file, rerun the affected focused suite and Ruff, inspect the diff, and commit a scoped fix. Do not broaden the runtime to governed evidence or change the source-matched bytes.

- [x] **Step 3: Re-run final verification**

```sh
uv run pytest -q
uv run ruff check src tests
python3 schema/build.py --check
uv lock --check
git diff --check
git status --short --branch
```

- [x] **Step 4: Merge/push and verify the remote**

After review and all checks pass, push `main` using the repository's approved Git workflow. Verify:

```sh
git rev-parse HEAD
git rev-parse origin/main
git status --short --branch
```

`HEAD` and `origin/main` must match, and only pre-existing intentionally untracked cache directories may remain outside the commit.

## Completion evidence

- Tasks 1–6 were implemented and covered by focused reviews and fix rounds. The CDC adapter hardening covered four-table-only reads, intermediate and terminal symlink rejection, digest/manifest drift, strict LMS domains, BMI day-730 handling, P3/P97 generation-only clamping, and constructor compatibility.
- Runtime/binding reviews covered locked source closure, exact identity/fingerprint/classification invariants, direct-oracle lock drift, binding-version enforcement, and visible-generator/deferred-import boundaries. CLI, cohort, documentation, and scale reviews approved the explicit profiles and test-only claims.
- The final CLI advisory was resolved by `b930e56`; its subprocess test now uses a runtime root without the default descriptor and exercises custom descriptor, reference-time, and software-revision forwarding. The advisory re-review approved it with no findings.
- Current-main focused verification: `160 passed` for CDC/reference/kernel/runtime contracts, `27 passed, 4 skipped` for smoke/CLI/scale-focused tests, and `29 passed` for augmenter/privacy boundaries; Ruff passed. The repository-wide suite is `2492 passed, 4 skipped`, schema validation and `uv lock --check` pass, and source/runtime/lock hashes remain `e7fe76af...`, `b50afc36...`, and `d17f8c26...` respectively.
- The published profiles remain development-only and test-only: no-profile/unknown-profile invocation is fail-closed, no approved binding or clinical validity is inferred, and no real/governed patient, calibration, held-out, privacy, model, network, Synthea, or release input is accepted.
