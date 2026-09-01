# Governed Multi-Run Prevalence Evidence Gate

**Date:** 2026-09-01
**Status:** Approved design for implementation

## Purpose

Add a governed, aggregate-only evidence gate that tests whether multiple independently generated pediatric fixture packages reproduce the disclosure-approved held-out demographic and recorded-outcome marginals without allowing validation to force prevalence or reveal patient-level material. The gate is an evaluation boundary around existing generation and held-out validation; it is not a generator, calibrator, privacy proof, or release authorization.

## Scope and decision

The implementation is a standalone `synthetic.prevalence_evidence` module with an explicit Python API and CLI. It accepts a predeclared, immutable set of generated package roots and expected seeds, plus the already governed held-out-validation inputs and frozen fidelity policy. It validates each package's exact manifest, descriptor, resource inventory, row counts, file hashes, and generation identity before invoking the existing held-out evaluator. It then reports v1 demographic and recorded-outcome comparisons separately from latent and observable phenotype diagnostics.

The gate does not change `synthetic.generate`, the native cohort API, package export, calibration, privacy auditing, or the Synthea route. The visible generator remains unable to read governed paths or reports. Synthea remains an optional later engine only after engine-conformance and this same gate.

## Requirements

### Explicit inputs and identity

- The API accepts only `Path` values for generated package roots and an ordered tuple of `PrevalenceRunSpec(package_root, expected_seed)` values. At least three runs are required by default; expected seeds must be distinct and are compared to each exact package manifest.
- The caller supplies a `HeldoutRunConfig` template, but the gate replaces only its synthetic root for each run and never writes its held-out output. All real-data paths, partition keys, calibration artifacts, and reports remain governed inputs and are never copied into the result.
- Each package must contain exactly the descriptor-declared CSV resources, `datapackage.json`, `validation-report.json`, and `manifest.json`, with no symlinks, hard links, path traversal, extra files, or missing files. Resource paths must remain beneath the package root.
- The manifest JSON must be strict UTF-8 without a BOM, duplicate keys, nonfinite values, oversized input, or unknown fields. It must be manifest version `1`, `metadata_only=false`, `status=STRUCTURE_VALIDATED`, and a non-test generated package. Its `row_counts` and `file_sha256` entries must match the exact package tree and bytes; the manifest itself is bound by its canonical byte digest because generated manifests intentionally do not hash themselves.
- The manifest schema fingerprint must match the descriptor, held-out artifact, and real descriptor. Every run must share one profile, engine, schema fingerprint, reference time and identity (including reference digest), configuration digest, software revision, PRNG family, seed-derivation version, and nonempty derivation fingerprint. No test-only derivation is accepted. Package digests and manifest digests are aggregate identity values, not patient identifiers.
- Package roots must be pairwise distinct and resolve to distinct directory identities. Configuration construction privately seals each physical directory identity, and every pinned source descriptor used during evaluation must match it, so replacing a declared root fails closed. This configuration seal binds the directory object rather than its bytes: in-place immutability before evaluation remains an operator precondition, while the evaluator binds and repeatedly verifies the exact manifest/package bytes from evaluation start through completion.

### Target scope and comparison

- v1 evaluates only target keys in the `outcome_layer=observed` stratum whose families are `demographics` or `recorded_outcome`. This includes sex, ethnicity, race, race multiselect, and registered recorded flags such as `healthy_flag`, `growth_dx_flag`, `chronic_dx_flag`, and anthropometric outcome flags. It reuses `validate_heldout`, `compare_targets`, and the fixed disclosure/fidelity policies.
- Latent module prevalence and observable phenotype prevalence remain separately labeled diagnostics from `cohort_validation`; they are not compared to held-out real-data targets and cannot affect the evidence status. Joint demographic/prevalence strata are deferred to target-registry v2.
- Every required v1 cell must be evaluable and pass in every run. A failed comparison makes the run and aggregate `FAIL`; if no comparison fails but any required run/cell is missing, suppressed, or under-supported, the status is `UNEVALUABLE`; only all-pass runs and cells produce `PASS`.
- Across seeds, aggregation is deterministic and sorted by canonical target key. For each key, the report may expose the held-out aggregate value, the generated minimum and maximum, maximum absolute difference, `maximum_tolerance_exceedance = max(difference - tolerance)`, and pass/evaluable/fail counts. This paired worst-run margin is positive exactly when at least one evaluable run fails; no standalone aggregate tolerance is published because independently maximizing differences and tolerances would destroy their decision pairing. It never exposes per-run comparison values, support counts, denominators, raw rows, identifiers, sequences, category combinations beyond registered aggregate keys, or hidden truth.

### Lifecycle, redaction, and non-interference

- The report and human summary contain only safe policy identities, schema and artifact identities, run count, seed values or safe seed identities, package/manifest digests, aggregate comparisons, checks, and statuses. A public per-run status is a redacted summary bound to the validated in-memory run before serialization; because its cells are deliberately withheld, standalone reparse checks its fixed comparison count and report-level feasibility rather than reconstructing individual run values, and writer equality binds it back to the in-memory report before promotion. They contain no package paths, real roots, partition keys, patient or visit IDs, raw values, supports, denominators, hidden module labels, truth hashes, or exception details.
- Output uses the existing no-replace run lifecycle and canonical JSON plus ASCII summary. Both files are written, semantically reparsed, and verified before promotion. Reparse requires the exact v1 key universe, fixed per-run comparison coverage, counts bounded by run count, status/count/margin consistency, and agreement between run, comparison, and report status. Any input, identity, comparison, or output failure produces no promoted report; failure archives only a fixed redacted `failure.json`.
- The gate performs no adaptive tuning, prevalence forcing, label allocation, package mutation, report feedback, or output overwrite. Validation results cannot be passed back into generation through this API.
- The CLI requires every governed input explicitly, emits only fixed redacted argument/failure messages, exits zero only for aggregate `PASS`, and never supplies default roots, keys, snapshots, reports, or seeds.

## Validation and test requirements

Tests use wholly fictional packages and a test-only derivation fixture only to exercise rejection; a passing evidence fixture must be classified as non-test in its manifest without claiming production authority. Tests cover strict manifest parsing, duplicate/nonfinite/BOM/size rejection, symlink and hard-link/tree rejection, file and row-count tampering, descriptor/schema mismatch, package and manifest digest binding, duplicate or unexpected seeds, root disjointness, every cross-run identity mismatch, test-only derivation rejection, per-run target filtering, worst-case deterministic aggregation, redaction, transactional lifecycle, CLI explicitness, and AST boundaries proving the visible generator does not import this governed module.

The gate remains evidence of aggregate distributional agreement under one frozen held-out partition and policy. It does not establish latent disease prevalence, biological or clinical validity, privacy/non-matchability, task utility, release approval, or authorization for real-data use.
