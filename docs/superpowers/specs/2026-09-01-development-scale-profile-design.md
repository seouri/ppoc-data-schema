# Development Scale-Profile Test Design

**Date:** 2026-09-01
**Status:** Implementation complete; opt-in test-only scale gate; clinical, population, privacy, and release evidence pending
**Parent:** [Synthetic Pediatric Growth Fixture System Design](2026-08-30-synthetic-growth-fixtures-design.md)
**Prerequisites:** Native cohort generation, observation/resource projection, exact-schema package export, the source-matched augmenter candidate, cohort validation, temporal-drift evaluation, and task-utility evaluation

## Purpose

The parent synthetic-fixture specification requires a scheduled development-profile test at 10,000 patients across a fixed seed set. The repository already has the native cohort, exact-schema, candidate-derivation, longitudinal, and task-evaluation contracts, but no single scale gate proves that they compose at development size. This slice adds that missing integration evidence and, as a bounded follow-on, checks the target-shaped realistic package's GHD descendants without changing production generation or claiming clinical, prevalence, privacy, or release validation.

## Scope and fixed contract

The scale gate is an opt-in pytest test marked `scale` and enabled only when `SYNTHETIC_RUN_SCALE=1`. The native direct check uses exactly three fixed seeds `(20260830, 20260831, 20260901)` and exactly 10,000 fictional members per seed. The two CLI composition checks use seed `20260901` and exactly 10,000 fictional members each: one for the legacy `development-cohort` profile and one for the target-shaped `development-realistic` profile. Each run uses the checked-in CDC runtime or fictional test reference appropriate to its existing route, the aggregate-only fictional calibration fixture, healthy/GHD native modules, all five age-regime coverage ages, and an observation policy with every supported visit and height/weight/head-circumference channel observed. Length is disabled for resource projection because the current visits schema has no visible length field; this is an explicit schema boundary, not a value substitution.

For each native seed the direct test:

1. Generates a descriptor-shaped `NativeCohort` with unique synthetic patient and visit identifiers.
2. Runs `validate_native_cohort` with a fixed development sanity policy and requires no `FAIL` comparison.
3. Runs `validate_temporal_drift` over infancy, transition, childhood, puberty, and adolescence with fixed support/coverage bounds and records the aggregate report status.
4. Runs `evaluate_task_utility` on an ordered, deterministic, visible-only prediction tuple; the test checks cohort-sized execution and structural status, never task clinical success.
5. Exports all six base resources plus the two augmented resources through `export_exact_schema_package` and `SourceMatchedAugmenterOracle` under the existing test-only derivation binding.
6. Verifies the promoted package has the exact eight descriptor resources, expected patient/visit row counts, schema fingerprint, manifest seed, and no extra files.

The `development-cohort` CLI check retains the existing empty-ancillary assertions. The `development-realistic` CLI check verifies the exact package inventory and schema, unique synthetic identifiers, 110,000 visits, target-shaped GHD relationships (`labs = 2 * problem_list = 2 * referrals` and `growth_dx_flag` equals the problem-list count), conditional medication bounds, and the serialization sentinel for typed fictional lab rows. It also requires the manifest's row counts to match the package. These assertions are content/integrity checks only; they do not infer clinical prevalence from the frozen development scenario.

The scale test does not write to the repository, read governed or real data, use hidden truth to construct predictions, or alter the production CLI. The legacy generic route retains empty ancillary rows; the realistic CLI check uses only its already-reviewed narrow GHD projection/merge exception and the exact exporter serialization sentinel. Other ancillary pathways and clinical transitions remain covered by their dedicated evaluator tests.

## Memory and lifecycle boundary

The gate is a scheduled integration budget, not a clinical or performance SLA. It keeps one in-memory cohort and one staged package per parameterized run, uses the existing no-overwrite package lifecycle, and relies on the cohort's fixed patient-count upper bound. The test reports no patient-level values, IDs, distances, or truth objects. A run is successful only when the package exporter promotes a structurally valid eight-resource package; any derivation or structural failure fails the gate.

## Documentation and claims

`docs/synthetic-generator.md` identifies the opt-in command, the three fixed native seeds, and the two 10,000-patient CLI profiles; `README.md` keeps the concise link to that guide. The guide states that the scale gate demonstrates local composition, target-shaped descendant integrity, and resource-count readiness only; it is not prevalence fidelity, clinical validity, governed held-out evidence, task utility on real labels, privacy/non-matchability evidence, Synthea conformance, or release approval. The source-matched augmenter remains a development derivation candidate and is never imported by the native generator.

## Acceptance criteria

1. The scale test is skipped by default and runs only with the explicit environment opt-in and `scale` marker.
2. All three fixed 10,000-member native runs generate descriptor-shaped cohorts without a cohort-validation `FAIL`; each CLI profile additionally completes its 10,000-patient package run.
3. Longitudinal and task evaluators execute for every seed and return their fixed aggregate report types without structural failure.
4. Every run exports all eight exact-schema resources with 10,000 patient rows and the configured number of visible visits, plus both augmented outputs produced by the verified candidate oracle; the realistic CLI package also preserves the reviewed GHD ancillary row relationships and serialization sentinel.
5. Package schema fingerprints, manifest identities, and exact tree inventories pass without repository or governed-data writes.
6. Focused scale tests, documentation assertions, Ruff, schema validation, whitespace checks, a broad review, and merged `main` verification pass. The default full suite remains unchanged except for reporting the scale test as skipped.
