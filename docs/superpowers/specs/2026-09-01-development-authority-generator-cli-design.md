# Development-Only CDC-Backed Generator CLI Design

**Date:** 2026-09-01
**Status:** Implementation complete; development-only/test-only route; clinical, population, privacy, and release gates pending
**Parent:** [Synthetic Pediatric Growth Fixture System Design](2026-08-30-synthetic-growth-fixtures-design.md)
**Inputs:** the pinned `scripts/augment.py` runtime and its checked-in manifest-listed reference tables

## Purpose

The repository currently has two useful synthetic-generation seams but no persistent command that composes them: the exact-schema smoke generator and the in-memory healthy-plus-growth-hormone-deficiency cohort. The supplied `scripts/augment.py` runtime contains the CDC LMS and longitudinal augmentation calculations needed to make those development artifacts useful, but its adapter is deliberately test-only and the production command-line entry point is fail-closed. This slice adds explicit development routes for smoke, coverage, and target-shaped profiles without presenting the imported implementation as clinically validated or release-authoritative.

The term development-authoritative in this design means that one explicitly selected, byte-pinned reference/oracle pair is authoritative for reproducibility within the development command. It does not mean clinical authority, prevalence validation, privacy/non-matchability proof, or release approval.

## Decisions and boundaries

### Recommended route: explicit development profiles

Add a small runtime composition layer that loads the checked-in CDC lookup tables as a strict `GrowthReference`, constructs the pinned `SourceMatchedAugmenterOracle`, constructs a matching test-only `DerivationBinding`, and dispatches one of two named profiles. The existing no-profile invocation remains fail-closed, so opting into development generation is visible in the command and cannot be confused with a production route.

The profiles are:

1. `development-smoke`: the existing `generate_smoke` contract, with healthy patients and visits at ages 730, 1095, and 1460 days, now using the CDC-backed reference and source-matched augmenter to produce a persistent exact-schema package.
2. `development-cohort`: the existing native cohort/resource projection contract, with fixed versioned development demographics, a healthy-plus-GHD module prior, a fixed longitudinal observation policy, and the same exact-schema exporter and augmenter oracle. The profile uses the full configured age-regime schedule and exports only visible resources; latent trajectories and observation truth remain evaluator-only.
3. `development-realistic`: an opt-in target-shaped native cohort profile that retains the same exact-schema/export boundary while freezing aggregate demographic weights and a healthy/GHD module prior derived from the checked-in snapshot shape. It enables the existing fictional recognition/workup/diagnosis descendants for GHD members and adds the fixed synthetic `E23.0` token at each GHD diagnosis visit so the pinned augmenter exposes the sampled synthetic growth-disorder flag; the token is not a clinical claim or caller-provided diagnosis payload.

The direct Python API remains compatible: `generate_smoke` keeps its current default metadata profile `smoke`, while the CLI passes an explicit `profile="development-smoke"` so the persistent package identifies the opted-in route. The smoke configuration hash includes that profile name; the cohort configuration hash includes the complete fixed profile configuration and reference fingerprint.

The command accepts an explicit output path, patient count, seed, and optional descriptor/reference-time/software-revision metadata with deterministic defaults. It refuses an existing or unsafe output path and never writes to the repository automatically. The fixed defaults are `datapackage.json` resolved from the repository checkout, `2026-09-01T00:00:00Z`, and `development-generator-v1`. A successful package manifest records the profile, schema fingerprint, CDC reference fingerprint, augmenter fingerprint, and `test_only_derivation=true`.

### Why the source remains test-only

The imported runtime manifest pins executable and lookup-table bytes, but `data/README.md` records that upstream provenance, licensing, and redistribution terms were not independently verified. The repository also has no completed clinical review, independent reference standard, bidirectional parity evidence, or approved non-test derivation binding for these bytes. Therefore the development profiles use a binding whose oracle and reference identities are pinned but whose evidence/review fields remain explicitly unevaluable/pending and whose `test_only` classification remains true.

No implementation may silently change `test_only` to false, call `require_approved_derivation_binding`, or relabel a package as clinically valid. A future non-test binding remains a separate reviewed gate.

## Reference adapter

Add `src/synthetic/cdc_reference.py` with a source-matched CDC reference implementation that reads only the manifest-listed non-patient lookup tables. Add `src/synthetic/development_runtime.py` for the fixed profile factories and runtime composition. The reference module must not import `scripts.augment` at module import time because that byte-preserved script performs relative-path loads and imports heavyweight third-party modules as a side effect.

The adapter parses the source LMS columns with strict UTF-8/BOM handling, maps source sex `1` to `M` and `2` to `F`, rejects unknown source sexes, validates finite positive LMS parameters, and uses the same interpolation and inverse LMS equations as the augmenter. Age interpolation uses `age_days / 30.4375` in source-month coordinates, not a rounded day grid, so the generated values follow the source runtime's `numpy.interp` convention. The near-zero-LMS branch uses the same `abs(L) < 1e-6` threshold as the source implementation.

The metric mapping is fixed and documented: `statage_combined.csv` supplies both the development `length_cm` and `height_cm` series, `wtage_combined.csv` supplies `weight_kg`, `bmiagerev.csv` supplies `bmi`, and `hcageinf.csv` supplies `head_circumference_cm`. The age-regime kernel applies its existing transition conversion; reusing the combined stature series is an explicit development approximation, not a claim that the source table separates every clinical measurement concept. The BMI series starts at the CDC 24-month boundary; the adapter uses the boundary row for the one-day-equivalent age edge in the existing 730-day smoke profile and records that behavior in tests/documentation.

The reference exposes `reference_id`, `source_sha256` (the aggregate reference fingerprint), `metrics`, `min_age_days`, and `max_age_days` and rejects requests outside each metric's source domain, except for the documented smoke boundary handling. Its aggregate fingerprint is the SHA-256 of canonical JSON containing `cdc-lms-reference-v1`, the ordered table names, each exact table digest, and the metric-mapping version token. It accepts no patient rows, governed paths, calibration artifacts, or output paths.

## Development binding and oracle composition

Add a runtime factory in `src/synthetic/development_runtime.py` that calls a redacted, read-only `verify_source_matched_runtime(repository_root)` helper in `src/synthetic/augmenter_oracle.py` before constructing the oracle, then binds the oracle identity/fingerprint to the reference identity/fingerprint and repository schema fingerprint. The binding uses `derivation-binding-v1`, binding ID `development-augmenter-v1`, `source_kind="authoritative_implementation"`, `source_revision="augment-runtime-v1"`, and `sha256(uv.lock bytes)` as `dependency_fingerprint`; the helper rejects a missing or changed lock file against the pinned digest `d17f8c2613da7c59dd858fe1e39025ce72e0241fb0bbc400772ab4273a694810` before generation. It also carries complete required category names, null evidence identifiers and zero case counts where evidence is unavailable, pending review, and `test_only=true`. The binding is aggregate-only and contains no paths, rows, source prose, patient identifiers, or hidden truth.

The existing `SourceMatchedAugmenterOracle` continues to snapshot and execute only the verified runtime closure in a private subprocess. Its return classification remains `test_only=true`; its fixed redacted failures, output inventory checks, base-resource hash checks, and exclusive output promotion remain unchanged. `BoundDerivationOracle` is used at the exporter boundary, so an oracle/reference/binding fingerprint mismatch fails before augmented resources are promoted.

The source-matched oracle is used for all three profiles. The native generator does not import or execute the vendored script directly; only the explicit CLI composition layer supplies the oracle to the existing exporter. The source script itself remains byte-for-byte unchanged.

## Cohort profile configuration

`development-cohort` uses the fixed in-code profile `development-cohort-v1` rather than reading a real or governed calibration file. Its age schedule is `(0, 365, 730, 1460, 2190, 3650, 4380, 5114, 5475, 6200, 7305)` days and its observation policy is `window=[0,7306)`, no censoring, visit probability `1.0`, length availability `0.0`, height/weight/head-circumference availability `1.0`, zero measurement error, no rounding, and recognition/diagnosis probabilities `0.0`. The module prior is healthy `0.50` and growth-hormone deficiency `0.50`. The demographic profile uses F/M/U weights `0.50/0.50/0.00`; the zero U weight is required because the CDC tables contain only M/F rows, while the one-to-one recorded-to-reference mapping remains structurally complete. Ethnicity/race weights, race multiselect behavior, the observation policy, measurement-error settings, module versions, and age schedule are immutable named configuration values with aggregate-safe identifiers.

The fixed synthetic demographic weights are: ethnicity `blank/not Hispanic/Hispanic/choose not to answer/unknown/unable to collect/patient does not know = 0.02/0.65/0.18/0.03/0.04/0.03/0.05`; race `blank/American Indian or Alaska Native/Another Race/Asian/Black or African American/Choose not to answer/Middle Eastern or Northern African/Native Hawaiian or Other Pacific Islander/Patient does not know/Unable to collect/Unknown/White = 0.01/0.01/0.03/0.08/0.12/0.02/0.02/0.01/0.02/0.02/0.04/0.62`; and race multiselect probability `0.06`. The legacy aggregate fields `recorded_healthy_probability` and `recorded_growth_dx_probability` are fixed at `0.0` because this route does not claim recorded-outcome prevalence; visible event recording is controlled solely by the explicit observation policy above.

The target-shaped `development-realistic` profile is versioned as `development-realistic-v1` and pins `schema/stats.json` snapshot `2026-08-24` in its configuration hash. It uses the same age schedule and measurement policy, but sets the healthy/GHD module prior to `214681/250588` and `35907/250588` and enables recognition/diagnosis recording at `1.0` for the existing fictional event descendants. The exporter adds the fixed synthetic `E23.0` token at each sampled GHD diagnosis visit; the pinned source augmenter therefore derives a visible `growth_dx_flag` for those synthetic members, while no caller-supplied diagnosis is accepted. Its visible demographic weights are derived from the checked-in aggregate snapshot: source-missing ethnicity/race cells are folded into `Unknown`, the U sex weight remains zero because the CDC reference has no U series, and race multiselect is `13191/250588`. The observed `growth_dx_flag` count is used only to shape the latent module prior; the generated sample's flag count is a reproducible synthetic scenario outcome, not observed prevalence, clinical validity, or population representativeness.

The default cohort prior is an experiment configuration, not a prevalence estimate. Documentation must state that the profile is useful for healthy/disorder trajectory coverage and package integration, while real-population prevalence and demographic calibration remain separate governed evidence. A future calibrated route may supply an already-approved aggregate artifact through an explicitly designed boundary; this slice does not add that reader or feed back from held-out evidence.

The cohort route converts each passing in-memory `ObservedResourceBundle` into the existing six base-resource row mapping in stable patient order, then calls `export_exact_schema_package` with development metadata and the bound source-matched oracle. Empty ancillary resources remain descriptor-shaped and visible; hidden trajectory/observation truth never enters rows, manifests, reports, or ordinary mappings.

## CLI contract

Extend `python -m synthetic.generate` with an explicit profile selector. Without `--profile`, or with an unknown profile, it emits the existing fixed unavailable message and creates no output. The supported commands are:

```sh
uv run python -m synthetic.generate \
  --profile development-smoke \
  --output /tmp/ppoc-development-smoke \
  --patients 1000 \
  --seed 20260901

uv run python -m synthetic.generate \
  --profile development-cohort \
  --output /tmp/ppoc-development-cohort \
  --patients 1000 \
  --seed 20260901

uv run python -m synthetic.generate \
  --profile development-realistic \
  --output /tmp/ppoc-development-realistic \
  --patients 1000 \
  --seed 20260901
```

The profile selector is required for generation. After the required operational arguments parse, a missing or unknown profile emits the existing fixed unavailable message; parser errors for missing required flags retain argparse behavior. `--descriptor` defaults to the repository `datapackage.json`; `--reference-time` and `--software-revision` default to `2026-09-01T00:00:00Z` and `development-generator-v1` but remain overrideable for reproducibility experiments. Patient count is bounded by the existing cohort limit and must be positive. The CLI's public failure remains redacted; malformed reference tables, manifest drift, binding mismatch, subprocess failure, output collision, schema failure, and partial-lifecycle failures do not expose paths, rows, or subprocess text.

The smoke profile keeps the existing three-visit visible contract. The cohort and target-shaped profiles default to the versioned full age schedule and emit the exact descriptor resources through the same package lifecycle. No profile accepts a real-data root, patient input directory, calibration path, held-out report, privacy input, network address, Synthea checkout, model, or arbitrary diagnosis payload.

## Data flow

```text
CLI --profile
    |
    +--> verified CDC reference adapter ------------------+
    |                                                      |
    +--> development-only calibration/module config       |
    |                                                      v
    +--> smoke generator OR native cohort/resource projection
                                                           |
                                                           v
                           exact-schema exporter + BoundDerivationOracle
                                                           |
                                                           v
                    staged base rows -> pinned augment.py subprocess
                                                           |
                                                           v
                         validated eight-resource package + manifest
```

All visible output is generated from synthetic state. The only files read by the runtime composition layer are the descriptor, the manifest-listed CDC/runtime files, and source code metadata needed to identify the pinned checkout. The augmenter subprocess receives only the staged synthetic package and a private temporary output directory.

## Failure and lifecycle behavior

- A missing or altered runtime-manifest entry, source-table digest, malformed LMS row, unsupported metric/sex, or reference-domain request fails before package creation.
- A missing or mismatched development binding, oracle classification, or reference fingerprint fails before any augmented output is copied.
- Existing output directories, symlinks, partial paths, unexpected runtime artifacts, extra augmenter outputs, and package schema violations use the existing no-overwrite and redacted failure boundaries.
- Any oracle failure or post-creation validation failure archives/removes the partial package through the existing exporter lifecycle; no partial package is reported as successful.
- Generated manifests identify the development profile and test-only derivation status; they never include latent disease state, private truth, subprocess output, source paths, or patient-level diagnostics.

## Testing strategy

Use test-first changes with wholly fictional inputs and temporary output roots.

1. Reference tests validate source-table parsing, source-sex mapping, exact metric coverage, LMS interpolation/inverse equations, 730-day BMI boundary behavior, domain failures, source fingerprints, and deterministic repeated calls. Include comparison fixtures that calculate the same z-score/value pair using the vendored algorithm's equations without importing patient data.
2. Runtime-composition tests verify the fixed development binding, oracle/reference fingerprint agreement, test-only manifest classification, rejection of modified runtime files, and no import-time execution of the vendored script.
3. CLI smoke tests invoke the real module with the development profile, assert an exact eight-resource package, schema/manifest/validation success, augmented headers, deterministic non-manifest bytes across distinct output roots with the same seed, and no promoted package on collisions or failure (only the existing quarantined failure artifact may remain). A no-profile invocation must retain the fixed fail-closed message.
4. CLI cohort tests run small healthy-plus-GHD coverage and target-shaped packages, assert unique synthetic identifiers, both module classes, longitudinal visible visits, exact descriptor resources, aggregate-only manifest fields, fictional event descendants and the synthetic `E23.0` token where enabled, and no latent truth in visible files. An opt-in scale test may run the existing 10,000-patient profile through the development oracle; it remains scheduled and does not become ordinary CI.
5. Boundary scanners must continue to reject governed calibration/held-out/privacy imports, patient-data readers, network/process escapes, and hidden truth in public mappings. The vendored source and its manifest bytes are not edited.
6. Run the focused generator/reference/oracle suites, the complete pytest suite, Ruff, schema validation, lock validation, staged whitespace checks, and a fresh read-only review. Verify the merged `main` commit equals `origin/main` after publication.

## Claims and deferred gates

This slice establishes a reproducible development route for three synthetic package profiles using a pinned source-matched CDC runtime. It does not establish that the CDC tables' upstream provenance or license has been independently verified, that the augmenter is clinically valid, that generated prevalence or demographics match a real population, that a profile cannot be matched to a real patient, or that any package is approved for release.

The following remain separate gates: independent reference-standard and clinical review; non-test derivation binding and parity evidence; real-population prevalence/demographic calibration; patient-disjoint held-out validation; temporal drift and task utility against governed targets; privacy evaluation and non-matchability review; complete ancillary clinical pathways; optional Synthea conformance; and release authorization. The CLI must not infer or mark any of those gates complete from a successful local package.

## Acceptance criteria

1. The exact source-matched runtime closure remains byte-identical and manifest-verified.
2. A strict CDC-backed `GrowthReference` covers every metric required by the smoke and cohort profiles and reproduces the source interpolation/inverse-LMS convention, including the documented 730-day edge.
3. `development-smoke`, `development-cohort`, and `development-realistic` each produce persistent exact-schema packages through the existing atomic exporter and source-matched augmenter, with `test_only_derivation=true` and aggregate-only manifests.
4. The default/no-profile CLI remains fail-closed, and all malformed inputs, collisions, oracle mismatches, and lifecycle failures remain redacted and leave no successful partial package.
5. Small fictional CLI runs, deterministic reruns, boundary tests, and the opt-in scale profile pass; no governed or patient data is read or added.
6. Documentation clearly separates development reproducibility from clinical, prevalence, privacy, non-matchability, Synthea, and release claims, and the complete verification/review/push handoff passes.
