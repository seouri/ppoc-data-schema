# Synthetic Pediatric Growth Fixture System Design

**Date:** 2026-08-30
**Status:** Approved in conversation; awaiting review of this written specification

## Purpose

Build deterministic, completely generated pediatric EHR fixture packages that have the same eight-resource schema as the PPOC data package. The fixtures must be useful for ordinary development and for controlled counterfactual experiments. Their highest-fidelity feature is longitudinal growth: healthy trajectories and clinically distinct growth-disorder trajectories should be coherent across observed measurements, derived growth metrics, diagnoses, treatment, and patient-level summaries.

The generator may be calibrated from the real data only through a governed process. Patient-level records never become generator inputs or repository artifacts. A separate governed privacy audit must test whether generated longitudinal profiles provide a meaningful linkage or membership signal with respect to the real cohort.

## Goals

1. Write all eight CSV resources declared by `datapackage.json`, using the same resource paths, field names, field order, types, null conventions, dialects, encodings, and key semantics.
2. Generate clinically coherent height, weight, BMI, and related trajectories from pinned pediatric growth references and explicit disorder models.
3. Approximate disclosure-approved real-data distributions for demographics, recorded growth diagnoses, growth flags, visit timing, measurement missingness, utilization, and ancillary-resource density.
4. Maintain latent disorder truth separately from the visible EHR, allowing realistically incomplete and delayed recorded diagnoses.
5. Produce paired physiology and utilization counterfactuals with machine-checkable invariants.
6. Make every result reproducible from a versioned configuration, calibration artifact, reference set, software revision, and random seed.
7. Fail closed when schema, clinical, statistical, counterfactual, provenance, or privacy gates do not pass.

## Non-goals

- Reproduce any real patient, real patient sequence, or rare real clinical narrative.
- Treat a recorded ICD-10 code as perfect ground truth.
- Make the first release's labs, medications, and referrals pathophysiologically complete. Those resources will be schema-complete, linked, and statistically calibrated, but growth trajectories take priority.
- Establish that re-identification risk is zero. The system can measure risk under a documented threat model; it cannot prove that matching is impossible against every present or future external data source.
- Automatically establish HIPAA de-identification, approve public release, or replace review by the data custodian and a qualified privacy expert.
- Generate fixtures by copying rows, resampling patient profiles, finding nearest patients, or fitting a patient-sequence generative model.

## Governing boundaries

The system has three execution boundaries:

1. **Governed calibration:** May read the real eight-resource dataset. It emits disclosure-controlled aggregates and a calibration report, never patient rows, visit sequences, raw small cells, or candidate matches.
2. **Offline generation:** Reads only the public schema, pinned public reference tables, versioned configuration, and an approved calibration artifact. It has no option for a real-data path.
3. **Governed privacy audit:** Reads both real and generated packages inside the governed environment. It emits aggregate attack metrics and a verdict. Candidate links and patient-level distances remain inside the governed environment.

The generated CSV package is development data, not evidence that a real-data workflow is authorized or clinically validated.

## System architecture

The implementation is divided into focused modules:

- `synthetic/calibrate.py`: compute and disclosure-control aggregate calibration statistics with DuckDB.
- `synthetic/generate.py`: command-line orchestration, deterministic random streams, manifests, and output lifecycle.
- `synthetic/trajectories.py`: pediatric reference calculations, latent smooth trajectories, disorder effects, and treatment response.
- `synthetic/observations.py`: visits, measurement availability and error, diagnoses, labs, medications, problem-list entries, and referrals.
- `synthetic/derive.py`: derive both augmented resources from generated base resources.
- `synthetic/validate.py`: run provenance, schema, linkage, derivation, clinical, distributional, and counterfactual gates.
- `synthetic/privacy_audit.py`: run governed exact-reproduction, linkage, membership, and attribute-disclosure attacks.
- `synthetic/config/`: versioned cohort, archetype, validation, and privacy-policy configuration.
- `synthetic/references/`: pinned, checksummed public growth-reference inputs and their provenance.
- `tests/synthetic/`: unit, contract, invariant, integration, attack, and deterministic regression tests.

The generator streams resource rows where practical so an experiment cohort does not require all resources to reside in memory simultaneously.

## Schema contract

The checked-in `datapackage.json` is the sole schema authority. The implementation computes a schema fingerprint over resource names and paths, field names and order, types, constraints, missing values, primary and foreign keys, logical foreign keys, CSV dialects, and encodings. Snapshot-specific row counts, descriptions, and provenance do not contribute to the schema fingerprint.

Each generated package contains a synthetic descriptor that:

- preserves the schema fingerprint exactly;
- uses each resource path from the source descriptor, including the current augmented-visit filename;
- replaces real row counts and observed statistics with generated-package values;
- records that every individual and event is fictional;
- identifies the generator, configuration, calibration, reference, seed, and manifest versions; and
- never contains hidden evaluator truth.

Base and augmented resources are not sampled independently. `patients_augmented` is derived from generated patients, visits, diagnoses, and problem lists. `visits_augmented` is derived from generated patients and visits using the definitions in the schema documentation and pinned reference tables. This is required for cross-resource mathematical consistency.

## Governed calibration

### Inputs and identity

Calibration accepts an explicit real-data root, the source descriptor, a snapshot label, and a disclosure policy. It validates real headers against the descriptor before measuring anything. The output records input file hashes inside the governed report, but the exportable calibration artifact contains only the snapshot label and a one-way aggregate source identity approved by the custodian.

### Aggregate targets

The calibrator measures, subject to disclosure rules:

- patient sex, ethnicity, and race distributions and approved low-dimensional joint tables;
- ages at first and last recorded visit, visit counts, inter-visit intervals, and encounter-type mixtures;
- measurement availability conditional on age band and encounter type;
- distributions of trajectory summaries, including starting z-score, within-patient z-score slope, residual variation, crossing of major percentile bands, and age-windowed height, weight, and BMI changes;
- marginal and approved joint prevalence of `growth_dx_flag`, `healthy_flag`, chronic diagnosis, stunting, wasting, underweight, and obesity;
- growth-related diagnosis-code prevalence, first recorded age, co-occurrence, and aggregate timing relative to observable trajectory change;
- outlier and biologically implausible-value rates;
- patient- and visit-level densities for labs, medications, problems, and referrals;
- measurement, diagnosis, and ancillary-resource missingness and incomplete logical visit-link rates; and
- correlation or copula parameters needed to retain approved relationships without exporting patient records.

Real data cannot directly reveal latent biological onset. Calibration therefore estimates distributions of observable change points and diagnosis delays; archetype configuration supplies clinically reviewed latent-onset assumptions.

### Disclosure control

The calibrator applies a versioned policy before writing any exportable artifact:

- suppress cells below the approved minimum count, initially 20 for internal engineering;
- coarsen age and trajectory bins until cells meet the minimum;
- round counts and continuous summaries at policy-defined precision;
- reject high-dimensional tables and serialized sequences;
- exclude extrema or examples attributable to a single patient;
- bound covariance and correlation releases to approved strata; and
- emit a disclosure report listing suppressions and coarsenings without listing affected patients.

Suppressed values are never silently converted to zero. Generation either uses an explicitly documented parent distribution or refuses a configuration that requires the suppressed statistic.

## Synthetic cohort model

### Deterministic patient state

Every patient is produced from independent named random substreams derived from the run seed and synthetic patient index. Demographics, latent physiology, visit process, measurement process, diagnosis process, and ancillary resources use separate substreams. This permits a counterfactual to change one causal layer while reusing all unaffected random draws.

Visible identifiers are newly generated synthetic identifiers and cannot contain hashes, substrings, ordering, or transformations of real identifiers. For the very small visible `U` sex category, the hidden manifest assigns a synthetic growth-reference sex solely for reference calculations; the assignment is random and has no real-person source.

### Latent reference trajectories

At a dense internal age grid, the model generates correlated height, weight, and BMI states relative to the pinned growth references. Patient-level intercepts, smooth age-varying deviations, and short-timescale residuals create stable but non-identical trajectories. The model converts latent reference scores to physical measurements with the same pinned LMS or equivalent reference equations used by derivation.

The model enforces physiological continuity but does not make observed measurements artificially monotonic. Observation error, rounding, clothing and scale effects, and rare configured outliers are introduced only in the observation layer.

### Clinical archetypes

The first release includes the following configurable archetypes:

1. Healthy stable growth.
2. Familial short stature: low but approximately channel-parallel height with otherwise preserved velocity.
3. Constitutional delay: childhood deceleration or delayed pubertal acceleration followed by partial or complete recovery.
4. Growth-hormone deficiency: progressive height-score decline with relatively preserved or increased weight/BMI.
5. Hypothyroidism: height-velocity reduction with relative weight/BMI increase.
6. Celiac or chronic systemic disease: coupled height and weight faltering, with weight commonly changing first.
7. SGA or Turner-like limited growth: low early or persistent height with incomplete catch-up.
8. Undernutrition or wasting: weight decline preceding or exceeding height decline.
9. Excess weight gain or obesity: sustained BMI rise without requiring linear-growth failure.

These are trajectory archetypes, not claims that all diagnoses within an archetype have identical biology. Configuration maps archetypes to compatible recorded diagnosis families. Patients may have approved overlapping processes, but the initial configuration limits overlap combinations to clinically reviewed pairs rather than taking an unconstrained Cartesian product.

Each disorder process has a latent onset, severity, progression shape, and optional treatment. Treatment has configurable delay, adherence, and partial, full, or absent response. Golden cases force coverage of boundary behaviors; population profiles sample them according to calibration and clinical configuration.

### Prevalence

The generator does not optimize a single disorder percentage. It targets a vector of disclosure-approved marginals and joints, including recorded growth diagnosis, trajectory phenotype, malnutrition flags, obesity, chronic disease, and the repository's strict healthy definition. Latent disorder prevalence and recorded diagnosis prevalence are distinct because diagnosis can be absent, delayed, or nonspecific.

For statistical profiles, a constrained allocation step assigns archetypes and recorded-diagnosis propensities so expected counts match target tolerances. A run fails rather than claiming prevalence fidelity when its cohort size cannot support the configured rare strata. Golden profiles explicitly skip prevalence claims.

## EHR observation process

The visible EHR is a lossy observation of the latent patient:

- visit timing depends on age, encounter type, baseline utilization, observed symptoms, and configured follow-up intensity;
- the presence of weight, height, head circumference, and diagnoses depends on age and encounter context;
- observed measurements add calibrated error, rounding, missingness, and rare outliers;
- diagnosis opportunities depend on visits and observable physiology, while sensitivity and delay remain imperfect;
- treatment events can follow recorded diagnosis, referral, or a configured independent clinical pathway;
- supportive labs, medications, problems, and referrals are sampled from schema-valid templates conditional on broad clinical and utilization state; and
- nullable or orphan logical `visit_id` values follow calibrated rates, while declared patient foreign keys and declared complete visit keys remain valid.

Ancillary values use fictional, clinically plausible combinations drawn from controlled templates. The first release validates schema, linkage, rates, and broad compatibility, but does not claim detailed disease-specific laboratory simulation.

## Derived resources

Derivation computes unit conversions, BMI, reference z-scores and percentiles, velocities, outlier indicators, nutritional flags, and patient summaries from the observed base data. It follows the checked-in resource documentation and versioned reference inputs.

At minimum, validation recomputes and compares:

- ounces to kilograms and inches to centimeters;
- BMI from compatible observed height and weight;
- reference z-scores and percentiles within their valid age and size domains;
- delta measurements, elapsed days, and annualized velocities;
- stunting, wasting, underweight, obesity, and BMI-category thresholds;
- nullable outlier behavior when measurements are absent;
- visit counts, visit spans, pre-diagnosis counts, first diagnosis ages, ever-flags, and z-score summary statistics; and
- base-to-augmented patient and visit identity.

Undefined calculations remain null rather than receiving plausible-looking fabricated derived values.

## Counterfactual packages

Counterfactual generation begins with a shared synthetic patient family and named random substreams. Each world is a complete eight-resource package with the normal schema. Stable synthetic patient IDs permit direct paired analysis; no causal label is added to the visible CSVs.

### Physiology counterfactual

The counterfactual changes the latent trajectory archetype, onset, severity, or treatment response while holding demographics, visit opportunities, measurement-availability draws, general utilization propensity, and unrelated clinical events fixed. Measurements, derived growth fields, growth-related diagnoses, and physiologically downstream events may change. Validation compares manifests and event traces to prove that unrelated layers did not change.

### Utilization counterfactual

The counterfactual holds latent physiology, treatment response, demographics, and underlying unrelated conditions fixed while changing visit frequency, encounter mix, measurement availability, or diagnosis-recording opportunities. Visible derived summaries may change because different observations are available; hidden latent truth may not.

### Truth manifest

The truth manifest is stored outside each visible package and contains:

- synthetic patient and counterfactual-family identifiers;
- world identifier and intervention description;
- latent archetypes, onsets, severities, and treatment responses;
- causal-layer hashes used to check invariants;
- intended recorded diagnosis behavior; and
- expected golden-case and counterfactual assertions.

Production-facing fixture APIs and ordinary development loaders must not expose this manifest. Evaluation tooling receives it through a separate explicit path.

## Output profiles

- **Golden:** A compact, checked-in pack with forced archetype, missingness, diagnosis-delay, treatment, derivation-boundary, and counterfactual coverage. It is deterministic and explicitly not prevalence-representative.
- **Development:** Defaults to 10,000 patients. It targets common prevalence and distributional tolerances and is generated outside Git.
- **Experiment:** Accepts a configured patient count and produces one or more paired worlds. It enforces minimum expected counts for requested strata.

Every run writes an initially unvalidated manifest containing the seed, schema fingerprint, calibration identity, reference hashes, configuration hash, software revision, row counts, and output hashes. A validated status is added only after all gates applicable to the profile pass. External-release approval is a separate governed status that this software cannot grant.

The generator refuses to overwrite an existing output directory. It writes to a run-specific temporary directory and promotes the result only after generation and non-privacy structural checks complete. A failed privacy audit marks the generated run rejected and prevents release; it does not delete governed evidence automatically.

## Privacy threat model and audit

### Claim boundary

The audit's strongest automated conclusion is: **no meaningful linkage or membership signal was detected above the approved thresholds under the documented attack model**. It may not state that a generated patient cannot be matched under every possible attack or that privacy risk is zero.

### Anticipated attacker knowledge

The default internal threat model assumes an attacker may know some combination of sex, race or ethnicity, approximate ages and timing of care, visit frequency, several longitudinal growth measurements, a growth diagnosis, and broad utilization. External-release review must update this model for information reasonably available to the anticipated recipient and for composition with prior releases.

### Required attacks

The governed auditor performs:

1. **Identifier overlap:** require zero overlap between visible synthetic identifiers and real identifiers.
2. **Exact longitudinal reproduction:** hash normalized eligible profiles with at least three anthropometric observations and require zero complete profile reproductions. Common empty or structurally uninformative profiles are reported separately and never counted as evidence of safety.
3. **Nearest-neighbor disclosure:** compare synthetic-to-real distances on prespecified quasi-identifier and trajectory feature sets with held-out-real-to-training-real distances. Report distance-to-closest-record distributions, uniqueness, nearest-versus-second-nearest margins, and rare-stratum results.
4. **Linkage attacks:** attempt record linkage under multiple attacker-knowledge subsets. Report high-confidence candidate rates and attack advantage over permutation or population-frequency baselines.
5. **Membership inference:** compare real patients included in calibration with held-out real patients using distance- and classifier-based attacks against the generated package.
6. **Attribute disclosure:** test whether a close apparent match permits sensitive diagnosis or trajectory attributes to be inferred materially better than approved population or stratum baselines.
7. **Composition:** test the new package together with prior synthetic releases intended for the same recipient when such releases exist.

### Engineering thresholds

Thresholds live in a versioned privacy-policy file and are included in the audit report. The initial internal engineering policy requires:

- zero identifier overlap;
- zero exact eligible longitudinal-profile reproductions;
- membership-inference ROC AUC no greater than 0.55, with the upper bound of a configured bootstrap confidence interval also no greater than 0.55;
- linkage and attribute-inference attack advantage no greater than 0.05, with the upper confidence bound no greater than 0.05;
- no rare stratum failing a stricter policy solely because it is hidden by an all-cohort average; and
- successful disclosure-policy validation of the calibration artifact.

These are conservative engineering defaults, not a universal definition of "very small" risk. A qualified privacy expert and data custodian may replace them with a recipient- and release-specific approved policy. The software refuses an external-release audit unless an approved policy identity and review date are supplied.

The exportable audit report contains aggregate metrics, confidence intervals, policy versions, and pass/fail reasons. It excludes real or synthetic patient-level distances, candidate pairs, rare raw cells, and attack examples.

## Validation gates

Validation produces machine-readable JSON plus a concise human-readable report. Gates run in this order:

1. **Provenance gate:** required seed, schema, calibration, reference, configuration, and software identities are present and compatible.
2. **Schema gate:** all eight resources have exact paths, headers, field order, parseable types, null behavior, dialects, encodings, constraints, and schema fingerprint.
3. **Relationship gate:** keys are unique where required; declared patient and complete visit links resolve; logical visit links reproduce configured null and orphan behavior.
4. **Derivation gate:** augmented values recompute from base values within declared numeric tolerances.
5. **Clinical gate:** trajectories are continuous, reference domains are respected, archetype signatures and treatment responses meet explicit assertions, and observed noise does not corrupt latent physiology.
6. **Distribution gate:** applicable prevalence, demographic, trajectory, missingness, utilization, diagnosis-delay, and resource-density targets fall within size-aware tolerances.
7. **Counterfactual gate:** paired worlds share all causal layers declared invariant and differ in the intended layer and its descendants.
8. **Privacy gate:** the governed privacy audit passes the approved policy for the intended use and recipient.

Golden runs apply gates 1–5 and 7, using forced-coverage expectations instead of gate 6. Internal development runs apply gates 1–7. Any release or use outside the governed development context additionally requires gate 8 and human authorization.

## Command-line interfaces

The intended interfaces are:

```sh
uv run python -m synthetic.calibrate \
  --data-root /governed/ppoc \
  --snapshot 2026-08-24 \
  --policy synthetic/config/disclosure-policy.json \
  --output /governed/calibration

uv run python -m synthetic.generate \
  --profile development \
  --patients 10000 \
  --seed 20260830 \
  --calibration /approved/calibration.json \
  --output /fixtures/development-20260830

uv run python -m synthetic.validate \
  --package /fixtures/development-20260830

uv run python -m synthetic.privacy_audit \
  --real-root /governed/ppoc \
  --synthetic-root /fixtures/development-20260830 \
  --policy /governed/approved-risk-policy.json \
  --output /governed/audit-report
```

Configuration files are strict: unknown keys, missing versions, incompatible schema fingerprints, invalid probabilities, unsupported overlaps, and impossible prevalence constraints are errors rather than warnings.

## Error handling and run lifecycle

- Calibration stops before profiling when a real header differs from the descriptor.
- Generation stops when a calibration artifact fails disclosure validation, requires a suppressed value with no parent fallback, or targets too few patients for the requested distributional claims.
- Output directories must not already exist.
- Partial files remain in a run-specific temporary directory with a failure manifest and are never labeled validated.
- Validation reports all independent gate failures in one run where doing so does not risk cascading misleading results.
- Privacy failure marks a run `REJECTED_PRIVACY`; candidate-match details remain governed.
- No command publishes, uploads, commits, or copies a package outside its supplied output location.

## Testing strategy

### Unit tests

- reference-score inversion and percentile calculations;
- smooth trajectory components and each archetype's age-windowed effects;
- treatment onset and response;
- deterministic named random substreams;
- measurement error, missingness, diagnosis delay, and logical-link sampling;
- derived units, BMI, velocities, flags, and summaries; and
- disclosure suppression, coarsening, and policy parsing.

### Contract and integration tests

- generate a small package and compare its schema fingerprint with the source descriptor;
- parse every generated field through the descriptor;
- verify all primary, foreign, and logical-link semantics;
- recompute augmented resources independently from base resources;
- generate each golden archetype and assert its intended observable signature;
- generate paired physiology and utilization worlds and assert causal invariants;
- prove identical seeds and versions produce identical hashes;
- prove different seeds produce disjoint visible identifiers; and
- run the calibrator against a wholly synthetic mock "real" package so CI never needs governed data.

### Privacy attack tests

- an intentionally copied longitudinal profile must fail exact-reproduction and linkage gates;
- an intentionally overfit calibration fixture must fail membership inference;
- a rare uniquely identifying pattern must fail the rare-stratum gate;
- a genuinely independent toy generator must pass the configured toy thresholds; and
- exported reports must be scanned to ensure they contain no identifiers, candidate pairs, patient-level distances, or undersized cells.

### Scale tests

A scheduled development-profile test exercises bounded-memory generation, all eight resources, derivation, and statistical validation at 10,000 patients. CI uses the golden and small integration profiles.

## Acceptance criteria

The first implementation is complete when:

1. A golden package and a 10,000-patient development package can be generated deterministically from approved non-patient inputs.
2. Both packages contain all eight resources and match the source schema fingerprint.
3. Augmented values and patient summaries are derived and pass independent recomputation.
4. Every clinical archetype has at least one reviewed golden case and a population-level trajectory-signature test.
5. Recorded growth-diagnosis prevalence, major growth flags, demographics, visit patterns, and missingness meet configured size-aware targets in the development profile.
6. Physiology and utilization counterfactual packages pass their invariant checks.
7. An intentionally leaky package is rejected by privacy tests.
8. A governed privacy audit can produce an aggregate report without exporting patient-level comparison data.
9. Documentation clearly distinguishes synthetic development utility, statistical fidelity, privacy-audit results, and clinical or release authorization.

## Design decisions

- Use a mechanistic, reference-based longitudinal generator rather than a row-resampling, nearest-neighbor, GAN, or general patient-sequence synthesizer.
- Combine population generation with a small hand-reviewed golden case library.
- Calibrate from governed, disclosure-controlled aggregates rather than patient records.
- Preserve hidden latent truth and allow diagnoses to be delayed or absent.
- Model physiology and utilization counterfactuals as separate causal interventions.
- Derive augmented resources from synthetic base resources.
- Treat privacy as an explicit attack-tested release gate with a bounded claim, not as an automatic consequence of calling data synthetic.

## Privacy guidance references

- [HHS guidance on methods for de-identification of protected health information](https://www.hhs.gov/hipaa/for-professionals/special-topics/de-identification/index.html): identification risk is context-dependent and not zero; Expert Determination requires documented methods and results supporting a very small risk for anticipated recipients.
- [NIST synthetic-data privacy evaluation methods](https://pages.nist.gov/HLG-MOS_Synthetic_Data_Test_Drive/): examples include reproduced unique records, apparent matches, disclosure measures, and membership inference.
