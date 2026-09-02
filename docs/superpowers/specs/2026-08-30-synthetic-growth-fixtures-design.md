# Synthetic Pediatric Growth Fixture System Design

**Date:** 2026-08-30
**Status:** Approved by the user after Synthea and synthetic-patient-generation review; ordinary development route separated from optional governed evaluation

## Purpose

Build deterministic, completely generated pediatric EHR fixture packages that have the same eight-resource schema as the PPOC data package. The fixtures must support ordinary development and controlled counterfactual experiments. Their highest-fidelity feature is longitudinal growth: healthy trajectories and clinically distinct growth-disorder trajectories must remain coherent across latent biology, observed measurements, derived growth metrics, healthcare utilization, diagnoses, treatment, and patient-level summaries.

Ordinary development uses completely generated state, pinned public/reference inputs, and versioned fictional configuration; it does not require a real-data root, calibration artifact, governance approval, or release evidence. If real data is used to tune a separate comparison route, it may be used only through a governed aggregate process. Patient-level records never become generator inputs or repository artifacts. Calibration, generation, held-out validation, and privacy auditing are distinct optional stages. A governed privacy audit measures linkage, membership, and attribute-inference risk under an explicit threat model; it cannot prove that no generated profile could ever be matched to any real person.

## Goals

1. Write all eight CSV resources declared by `datapackage.json`, using the same resource paths, field names, field order, types, null conventions, dialects, encodings, and key semantics.
2. Generate clinically coherent length or height, weight, BMI or weight-for-length, head-circumference, and velocity trajectories from pinned pediatric references and explicit biological models.
3. Represent infancy, prepubertal childhood, puberty, and late-adolescent growth as distinct but continuous biological regimes.
4. When a governed aggregate calibration artifact is supplied, approximate its disclosed real-data distributions for demographics, observation-window entry and exit, recorded growth diagnoses, growth flags, visit timing, measurement missingness and error, utilization, and ancillary-resource density; ordinary development profiles use explicit fictional distributions.
5. Maintain latent disorder truth separately from observable phenotype and the visible EHR, allowing incomplete observation, delayed recognition, absent or nonspecific diagnoses, imperfect treatment, and loss to follow-up.
6. Produce paired physiology, recognition or treatment, utilization, and measurement counterfactuals with an explicit causal change contract and machine-checkable invariants.
7. Make every result reproducible from a versioned configuration, optional calibration artifact, public reference set, terminology set, module set, software revision, pseudorandom-number-generator specification, reference time, and seed.
8. Validate structural correctness in every development run, with statistical fidelity, longitudinal and clinical fidelity, task utility, and privacy evaluated separately when the corresponding evidence is available.
9. Permit either the recommended native generator or an optional Synthea-backed implementation to satisfy one engine-independent output and validation contract.
10. Fail closed when required schema, derivation, or counterfactual integrity checks do not pass; apply clinical, statistical, task-utility, privacy, provenance, and release gates only to workflows that make those claims.

## Non-goals

- Reproduce any real patient, real patient sequence, or rare real clinical narrative.
- Treat a recorded ICD-10 code as perfect ground truth or equate recorded-diagnosis prevalence with latent disease prevalence.
- Claim that statistical similarity establishes biological validity, clinical validity, privacy, regulatory compliance, or authorization for real-data use.
- Make every ancillary clinical domain pathophysiologically complete in the first release. The first release models disorder-critical laboratories, medications, problems, and referrals causally; unrelated background resources may use reviewed conditional templates.
- Establish that re-identification risk is zero. The system can measure risk under documented attacks and approved decision rules, but it cannot prove safety against every present or future external data source.
- Automatically establish HIPAA de-identification, approve public release, or replace review by the data custodian and a qualified privacy expert.
- Generate fixtures by copying rows, resampling patient profiles, finding nearest patients, or fitting a patient-sequence model directly to patient records.
- Adopt Synthea's default pediatric growth, geography, utilization, or disease modules as the PPOC truth model without explicit replacement, mapping, and validation.

## Execution boundaries and optional governed evidence

The system has one ordinary-development boundary and three optional governed/evaluation boundaries:

1. **Ordinary development:** Reads only the public schema, pinned public reference/runtime files, and versioned fictional configuration; it generates all patient and event state and has no option for a real-data path. The native route is sufficient, and an optional Synthea-backed route is not a prerequisite.
2. **Governed calibration:** May read the calibration partition of the real eight-resource dataset. It emits disclosure-controlled aggregates and a calibration report, never patient rows, visit sequences, raw small cells, or candidate matches.
3. **Governed held-out validation:** Compares generated packages with a patient-disjoint real validation partition that was not used to construct calibration aggregates, clinical modules, tolerance selection, or attack models. It emits aggregate validation results only.
4. **Governed privacy audit:** Reads calibration-partition records, held-out records, generated packages, and prior relevant releases inside the governed environment. It emits aggregate attack metrics and a decision under a versioned risk policy. Candidate links and patient-level distances remain governed.

Partition assignment is stable at the patient level and recorded only in governed metadata when the optional governed route is used. No visit or resource row from a held-out patient may contribute to calibration. The generated CSV package is ordinary development data, not evidence that a real-data workflow is authorized or clinically validated.

## Engine-independent architecture

The canonical contract is independent of the implementation engine. The recommended native implementation is divided into focused modules:

- `synthetic/calibrate.py`: construct patient-disjoint partitions and compute disclosure-controlled aggregate calibration statistics with DuckDB.
- `synthetic/generate.py`: command-line orchestration, deterministic random streams, manifests, and output lifecycle.
- `synthetic/cohort.py`: source-population state, healthcare-system entry, observation windows, censoring, and baseline utilization.
- `synthetic/trajectories.py`: growth-reference calculations, age-regime transitions, latent anthropometry, disorder effects, puberty, and treatment response.
- `synthetic/clinical_modules.py`: versioned disease state machines and their observable clinical descendants.
- `synthetic/observations.py`: encounters, measurement availability and error, recognition, diagnoses, labs, medications, problems, and referrals.
- `synthetic/derive.py`: derive both augmented resources from generated base resources through an authoritative parity-tested derivation contract.
- `synthetic/validate.py`: run provenance, schema, relationship, derivation, clinical, longitudinal, distributional, task-utility, and counterfactual gates.
- `synthetic/privacy_audit.py`: run governed exact-reproduction, linkage, membership, attribute-disclosure, and composition attacks.
- `synthetic/config/`: versioned cohort, age-regime, disease-module, validation, counterfactual, and privacy-policy configuration.
- `synthetic/references/`: pinned, checksummed public growth and clinical-reference inputs with provenance.
- `tests/synthetic/`: unit, contract, invariant, integration, utility, attack, and deterministic-regression tests.

The generator streams resource rows where practical so an experiment cohort does not require all resources to reside in memory simultaneously. All engines must emit the same engine-neutral latent event trace, truth-manifest schema, base-resource contract, and run manifest before export.

## Implementation strategy and Synthea alternative

### Recommended route: native growth-first generator

The first implementation should be a small, purpose-built Python generator. This route provides direct control over pediatric reference equations, infancy and puberty regimes, two-degree anthropometric identities, PPOC observation semantics, counterfactual random-stream reuse, exact CSV derivation, and optional governed aggregate calibration. It also avoids making a JVM simulation framework a prerequisite for ordinary fixture generation.

### Optional route: Synthea-backed engine

A Synthea-backed engine is a valid optional alternative or later interoperability route if it implements the same engine-independent contracts. It is not a configuration-only substitution and is not required for ordinary development. The route requires:

1. A pinned Synthea source revision and documented license and attribution obligations.
2. A custom pediatric growth extension that replaces or bypasses the default height/BMI lifecycle where it cannot express this specification's infancy, puberty, disorder, and counterfactual requirements.
3. Versioned pediatric disease modules or custom Java physiology components whose transition logic, terminology, and source citations are reviewed independently of Synthea's bundled modules.
4. An engine-neutral event-trace adapter so latent onset, recognition, treatment, response, observation, and censoring have the same meanings in both engines.
5. A PPOC exporter that writes the exact eight-resource base schema; the authoritative augmentation implementation then derives augmented resources.
6. Replacement of default population, geography, utilization, and prevalence assumptions with an optional approved calibration artifact and cohort model when making population-fidelity claims.
7. The same content, structural, counterfactual, and no-real-data-input controls as the native route; privacy, provenance, and release gates apply when the Synthea route is used for those claims.

Building the entire fixture system as one Synthea Generic Module Framework JSON module is not a viable equivalent. A generic module runs inside Synthea's existing population and lifecycle machinery; it does not by itself replace pediatric growth physiology, cohort sampling, the observation model, exact PPOC export and augmentation, counterfactual orchestration, held-out validation, or privacy auditing.

Synthea's Generic Module Framework is well suited to encounter, condition, test, medication, referral, and treatment state transitions. Growth physiology that updates continuously and preserves anthropometric identities requires a custom Java module or lifecycle extension rather than JSON modules alone. Bundled adult modules must not be repurposed for pediatric disease without changing their onset, natural history, recognition, and treatment behavior.

### Optional hybrid use

After the native growth engine is validated, Synthea may supply unrelated background clinical events through a one-way adapter. The native engine remains authoritative for growth physiology, cohort observation, growth-related state machines, and counterfactual truth. Hybrid events must not alter growth-related descendants unless an explicitly reviewed bridge module declares that causal relationship.

### Engine decision rule

The native engine is the ordinary-development and release-one recommendation. A Synthea-backed engine becomes an accepted alternative for a corresponding claim only after an engine-conformance suite shows that it satisfies the same schema, derivation, longitudinal, disease-signature, counterfactual, task-utility, reproducibility, and applicable privacy gates. Agreement between engines is not itself a validity criterion: each must be validated against public references and governed held-out targets when population or release claims are made. Synthea may be retained as a baseline comparator even if it is never used to produce released fixtures.

## Schema contract

The checked-in `datapackage.json` is the sole schema authority. The implementation computes a schema fingerprint over resource names and paths, field names and order, types, constraints, missing values, primary and foreign keys, logical foreign keys, CSV dialects, and encodings. Snapshot-specific row counts, descriptions, and provenance do not contribute to the schema fingerprint.

Each generated package contains a synthetic descriptor that:

- preserves the schema fingerprint exactly;
- uses each resource path from the source descriptor, including the current augmented-visit filename;
- replaces real row counts and observed statistics with generated-package values;
- records that every individual and event is fictional;
- identifies the engine, generator, configuration, optional calibration, reference, terminology, clinical-module, seed, PRNG, reference-time, and manifest versions; and
- never contains hidden evaluator truth.

Base and augmented resources are not sampled independently. `patients_augmented` is derived from generated patients, visits, diagnoses, and problem lists. `visits_augmented` is derived from generated patients and visits through the authoritative derivation contract. This is required for cross-resource mathematical consistency.

## Derivation parity and claim boundary

The repository now includes the byte-pinned `scripts/augment.py` runtime and its checked-in nonpatient lookup tables. Its manifest and runtime checks resolve the documented filtering order, age-boundary, missingness, Harrall-outlier, biologically-implausible-value, EP/AP/LP velocity, and rounding behavior for ordinary development; an independent parity review remains necessary before clinical or release claims.

Before an augmented fixture can support a clinical or release claim, the project must obtain and pin one of the following:

1. the authoritative augmentation implementation and its dependencies; or
2. a custodian-approved executable reference harness plus golden inputs and outputs covering all documented boundary cases.

The visible package manifest records the derivation implementation fingerprint (a cryptographic oracle identity/hash) and test-only classification. The textual `oracle_id`, source revision, dependency fingerprint, parity evidence, and review metadata remain in the private derivation binding, which maps the fingerprint to the reviewed oracle without exposing those identifiers in ordinary package files. A clean-room reimplementation may be used only after bidirectional parity tests pass across reviewed golden cases and a governed synthetic fuzz corpus. Until then, ordinary development may use the pinned test-only oracle for structural and reproducibility checks; those augmented outputs cannot support clinical or release claims.

## Optional governed calibration

### Patient-disjoint partitions

Before measuring aggregates, the governed calibrator assigns patients to stable calibration and held-out validation partitions using a custodian-controlled keyed procedure. The split is stratified only through approved coarse variables and never exported at patient level. All rows belonging to a patient remain in one partition.

Calibration reports the partition policy, counts after disclosure control, and snapshot identity. Validation tolerances are selected from clinical references, sampling uncertainty, and calibration-partition resampling before held-out results are examined; the held-out partition must not become an iterative tuning set.

### Inputs and identity

Calibration accepts an explicit real-data root, source descriptor, snapshot label, partition policy, and disclosure policy. It validates real headers against the descriptor before measuring anything. The governed report may record input hashes, but the exportable calibration artifact contains only the snapshot label and a custodian-approved one-way aggregate source identity.

### Separate clean-physiology and observation-error targets

The calibrator must not interpret raw extreme measurements, velocities, or derived scores as latent biology. It produces two distinct target families:

- **Physiology targets:** calculated from measurements that pass the authoritative plausibility and BIV rules, including age-windowed distributions of starting score, within-patient slope, residual variation, channel crossing, and height, weight, BMI, weight-for-length, and head-circumference change.
- **Observation targets:** calculated from the relationship between raw and cleaned records, including missingness, rounding, duplicates, carry-forward, unit and decimal errors, digit transposition, height/weight switches, impossible values, visit-link incompleteness, and encounter-specific measurement availability.

No raw tail or maximum becomes a biological calibration target merely because it exists in the real snapshot.

### Aggregate targets

Subject to disclosure rules, the calibrator measures:

- patient sex, ethnicity, and race distributions and approved low-dimensional joint tables;
- source-cohort ages, healthcare-system entry and exit, observation duration, visit counts, inter-visit intervals, and encounter mixtures;
- measurement availability and observation-error rates conditional on coarse age regime and encounter type;
- clean trajectory summaries by clinically meaningful age windows;
- marginal and approved joint prevalence of `growth_dx_flag`, `healthy_flag`, chronic diagnosis, stunting, wasting, underweight, obesity, and selected observable phenotypes;
- growth-related diagnosis-code prevalence, first recorded age, co-occurrence, and aggregate timing relative to observable trajectory change;
- patient- and visit-level densities of disorder-critical and background labs, medications, problems, and referrals;
- incomplete logical visit-link rates; and
- approved hierarchical, correlation, or copula parameters needed to preserve low-dimensional relationships without exporting records or sequences.

Real data cannot directly reveal latent biological onset or undiagnosed disease prevalence. Calibration estimates observable change points, recognition opportunities, recorded diagnoses, and diagnosis delays. Pinned clinical configuration supplies reviewed assumptions for latent incidence, onset, nonrecognition, and treatment response.

### Disclosure control and optional differential privacy

The calibrator applies a versioned policy before writing any exportable artifact:

- suppress or coarsen cells below the approved minimum count;
- round counts and continuous summaries at policy-defined precision;
- reject high-dimensional tables, serialized sequences, record examples, and patient-attributable extrema;
- bound released covariances and correlations to approved strata;
- use hierarchical parent distributions for sparse strata only when that fallback is declared in advance; and
- emit a disclosure report listing suppressions and coarsenings without identifying affected patients.

Suppressed values are never silently converted to zero. Generation either uses an explicitly documented parent distribution or refuses a configuration that requires the suppressed statistic.

For calibration artifacts intended to leave the governed environment or support repeated releases, the preferred stronger option is patient-level differential privacy. Its policy must identify the patient as the accounting unit, bound each patient's contribution before noise, declare epsilon and delta, track composition across every released statistic and artifact version, and document implementation checks. Small-cell rules remain useful output controls but are not a substitute for a formal privacy guarantee.

## Synthetic cohort and observation frame

The generator distinguishes five layers:

1. **Source population:** fictional demographic, birth, familial, and baseline health factors.
2. **Latent disorder state:** underlying disease presence, onset, severity, and biological effects.
3. **Observable phenotype:** growth and symptoms that could be detected if measured.
4. **Healthcare observation:** system entry, encounters, measurement opportunities, dropout, and right censoring.
5. **Recorded EHR:** diagnoses, problems, tests, treatments, referrals, and derived summaries that appear in the eight resources.

When a population-fidelity evaluation is requested, PPOC-like prevalence is evaluated in the observed healthcare cohort with explicit denominators. Ordinary development profiles report configured fictional priors and do not claim real-population prevalence. Population prevalence, latent disorder prevalence, observable growth-phenotype prevalence, and recorded-diagnosis prevalence are reported separately and must never be used interchangeably.

### Deterministic patient state

Every patient is produced from named pseudorandom substreams derived from the run seed and synthetic patient index. Demographics, birth state, growth potential, puberty, disorder incidence, treatment response, healthcare observation, measurement error, recognition, and background resources use separate substreams. The run manifest pins the PRNG family and version, seed-derivation algorithm, time-step semantics, and reference date.

Visible identifiers are newly generated synthetic identifiers and cannot contain hashes, substrings, ordering, or transformations of real identifiers. For the small visible `U` sex category, the hidden manifest assigns a synthetic growth-reference sex solely for reference calculations; the assignment is random, is not treated as gender identity, and has no real-person source.

### Anthropometric identities and age regimes

The latent model never generates length or height, weight, and BMI as three independent states. It uses only two independent anthropometric dimensions in each applicable regime and derives the third deterministically before observational noise:

- **Birth through less than 24 months:** generate recumbent length and weight; derive weight-for-length. Generate head circumference as a separate correlated process. Gestational age, birth size, prematurity, feeding, and catch-up or catch-down growth may affect this regime.
- **Transition near 24 months:** apply an explicit, versioned recumbent-length-to-standing-height transition and change the primary proportionality measure from weight-for-length to BMI-for-age. There is no discontinuity in underlying body size.
- **Age 2 through prepuberty:** generate standing height and BMI relative to pinned references; derive weight. Preserve stable growth channels with age-dependent residual correlation.
- **Puberty:** add patient-level pubertal timing, tempo, and growth-spurt intensity to target-height potential. Height velocity, BMI development, and sex-reference effects remain coupled without forcing identical timing across patients.
- **Late adolescence:** decelerate height velocity toward an internally consistent adult-height distribution while allowing weight and BMI to continue changing.

The model uses WHO standards for birth through age 2 and CDC references from age 2 through 20 unless the authoritative PPOC derivation contract requires a different source-compatible calculation. If source-compatible derived fields use a different reference, the generator records both roles: one pinned reference governs latent biology and another reproduces the source field. Severe obesity uses the pinned CDC extended BMI reference within its valid domain.

Patient-level target-height potential, birth state, smooth age-varying effects, puberty parameters, and short-timescale biological residuals produce stable but nonidentical trajectories. The latent model enforces physiological continuity. It does not make observed measurements artificially monotonic.

### Disease and growth-pattern state machines

Each disease module is a versioned state graph with the following common phases:

```text
susceptibility -> latent onset -> biological trajectory effect
               -> observable phenotype -> recognition opportunity
               -> workup -> recorded diagnosis -> treatment
               -> adherence -> response, nonresponse, or remission
```

Every transition declares its eligibility, age and risk dependence, hazard or deterministic trigger, affected latent variables, observable descendants, possible EHR events, terminology mappings, source citations, and named random stream. Every transition is written to the hidden event trace.

Release one contains separately reviewed modules for:

1. Healthy stable growth.
2. Familial short stature with low target-height potential and preserved prepubertal velocity.
3. Constitutional delay with delayed pubertal timing and later acceleration.
4. Growth-hormone deficiency with progressive linear-growth deceleration, workup and endocrine referral, optional growth-hormone treatment, adherence, and heterogeneous response.
5. Pediatric hypothyroidism with age-appropriate onset, linear-growth deceleration, relative weight or BMI effect, TSH/free-T4 workup, levothyroxine treatment, and heterogeneous response.
6. Celiac or reviewed chronic systemic disease with weight and then height effects, disease-specific testing or referral, treatment, and incomplete recovery.
7. Prematurity or SGA with birth-state origin and explicit catch-up or persistent short stature.
8. Turner syndrome as a distinct sex-reference-compatible module rather than a synonym for SGA.
9. Undernutrition or wasting with weight decline preceding or exceeding height decline.
10. Excess weight gain or obesity with sustained BMI rise that does not require linear-growth failure.

These are generative modules, not assertions that every diagnosis has one trajectory. Approved overlaps are encoded as explicit module interactions; release one does not sample an unconstrained Cartesian product. A clinical module cannot be enabled until its golden cases, citations, terminology mappings, and longitudinal signature assertions have been reviewed.

### Incidence, prevalence, and censoring

Latent disorders arise through age-, sex-reference-, birth-state-, familial-, and approved risk-dependent incidence or onset hazards. Healthcare-system entry, visit observation, and censoring are generated separately. Recognition and recorded diagnoses arise from observable evidence and opportunities rather than from a final label-allocation step.

Calibration may tune hazard intercepts, observation probabilities, and recognition parameters so simulated observed-cohort targets fall within predeclared tolerances. It may not assign patient labels solely to force the final recorded prevalence. When a requested cohort is too small to support rare-stratum claims, generation fails or labels those claims unevaluable; golden profiles never make prevalence claims.

### EHR observation and error process

The visible EHR is a lossy observation of the latent patient:

- visit timing depends on age, observation window, encounter type, baseline utilization, observable symptoms, follow-up intensity, and latent practice or calendar effects that are allowed by configuration;
- length or height, weight, head circumference, and other measurements are present according to age and encounter context;
- measurement error is applied after latent physical measurements and before derived calculations;
- error modes include ordinary device and technique variation, rounding, clothing or scale effects, duplicates, carry-forward, unit mistakes, decimal shifts, digit transposition, height/weight switches, and rare impossible values at reviewed rates;
- diagnosis and workup opportunities depend on visits and observable phenotype, with imperfect sensitivity, specificity, and delay;
- treatment may follow diagnosis, referral, or an explicitly configured alternative clinical pathway; and
- nullable or orphan logical `visit_id` values follow calibrated observation rules, while declared patient foreign keys and complete declared visit keys remain valid.

Disorder-critical resources are causal descendants of the applicable module. At minimum these include the reviewed combinations needed to prevent contradictions in growth-hormone deficiency, pediatric hypothyroidism, celiac disease, Turner syndrome, SGA follow-up, undernutrition, and obesity pathways. Unrelated background events may use conditional templates, but they cannot accidentally reveal hidden truth or contradict active medications, problems, tests, or referrals.

## Derived resources

Derivation computes unit conversions, BMI, reference z-scores and percentiles, velocities, outlier indicators, nutritional flags, and patient summaries from observed base data through the pinned derivation oracle. An observed height or weight error therefore propagates into BMI and other downstream values exactly as the source pipeline would handle it.

At minimum, validation independently recomputes and compares:

- ounces to kilograms and inches to centimeters;
- BMI from compatible observed standing height and weight;
- reference z-scores and percentiles within valid age, measurement, and size domains;
- delta measurements, elapsed days, and every EP/AP/LP annualized-velocity variant;
- stunting, wasting, underweight, obesity, and BMI-category thresholds;
- Harrall and BIV processing order and nullable outlier behavior;
- visit counts, visit spans, pre-diagnosis counts, first diagnosis ages, ever-flags, and z-score summaries; and
- base-to-augmented patient and visit identity.

Undefined calculations remain null rather than receiving plausible-looking fabricated values.

## Counterfactual packages

Counterfactual generation begins with a shared synthetic patient family, an explicit causal graph, and named random substreams. Each world is a complete eight-resource package with the normal schema. Stable synthetic patient IDs permit paired analysis; causal labels and hidden interventions are not added to visible CSVs.

Each intervention has a versioned change matrix that names the manipulated nodes, permitted descendants, invariant nodes, reused streams, resampled streams, and field-level assertions. The default contract is:

| Intervention | Latent disorder | Growth physiology | Visits or measurements | Recorded diagnosis | Treatment |
| --- | --- | --- | --- | --- | --- |
| Physiology or severity | May change | Changes | Opportunities fixed unless declared downstream | May change | May change if downstream |
| Earlier recognition | Unchanged | Unchanged until treatment | May add workup encounters | Changes | May begin earlier |
| Treatment or adherence | Unchanged | Changes only after intervention | May add follow-up | Fixed or explicitly downstream | Changes |
| Utilization intensity | Unchanged | Unchanged | Changes | May be delayed or absent | May be delayed if opportunity-dependent |
| Measurement-error removal | Unchanged | Unchanged | Values change; opportunities fixed | Unchanged unless a declared decision rule is rerun | Unchanged unless declared downstream |

The generator rejects an intervention whose requested change is not permitted by its causal graph. Validation compares event traces, causal-layer hashes, and visible descendants; equality of seeds alone is not evidence that invariants held.

### Truth manifest and event trace

The truth manifest is stored outside every visible package and contains:

- synthetic patient, family, world, and engine identifiers;
- intervention identity and causal change matrix;
- source-population factors, observation window, and censoring;
- latent modules, onsets, severities, puberty state, treatments, adherence, and responses;
- engine-neutral event trace and causal-layer hashes;
- reused and resampled random-stream identities;
- intended recorded-diagnosis behavior; and
- expected golden-case and counterfactual assertions.

Production-facing fixture APIs and ordinary development loaders must not expose this manifest or event trace. Evaluation tooling receives them through a separate explicit path.

## Output profiles

- **Golden:** A compact, checked-in pack with forced age-regime, disease-module, measurement-error, diagnosis-delay, treatment, derivation-boundary, censoring, and counterfactual coverage. It is deterministic and explicitly not prevalence-representative.
- **Development:** Defaults to 10,000 patients. It uses explicit fictional prevalence and distribution settings for development coverage; a separately governed calibration route may target real-population tolerances and is not required for ordinary fixtures.
- **Experiment:** Accepts a configured patient count and produces one or more paired worlds. It enforces minimum expected counts for requested strata.
- **Engine comparison:** Generates matched configuration-level cohorts from native and Synthea-backed engines without claiming patient-level correspondence. It is used only for conformance and sensitivity analysis.

Every run writes an initially unvalidated manifest containing the seed, PRNG and seed-derivation versions, schema fingerprint, engine identity, optional calibration identity, reference and terminology hashes, clinical-module hashes, configuration hash, software revision, reference time, row counts, output hashes, and (when augmented derivation is bound) the derivation implementation fingerprint. The private binding retains the textual oracle identity and review metadata; those fields are intentionally absent from visible manifests. A validated status is added only after all applicable gates pass. External-release approval is a separate governed status that this software cannot grant.

The generator refuses to overwrite an existing output directory. It writes to a run-specific temporary directory and promotes the result only after generation and nonprivacy structural checks complete. In a governed release workflow, a failed privacy audit marks the generated run rejected and prevents release; it does not delete governed evidence automatically.

## Privacy threat model and audit

### Claim boundary

The audit's strongest automated conclusion is: **under the documented recipient, release context, attacker knowledge, attacks, controls, and decision rules, the generated package did not exhibit a linkage, membership, or attribute-inference signal above the approved risk tolerances**. It may not state that a generated patient cannot be matched, that privacy risk is zero, or that a nearest synthetic profile represents the same person.

### Anticipated attacker knowledge

The default internal threat model assumes an attacker may know some combination of sex, race or ethnicity, approximate ages and timing of care, visit frequency, several longitudinal growth measurements, a growth diagnosis, and broad utilization. External-release review must update this model for information reasonably available to the anticipated recipient and for composition with prior releases.

### Attack design and controls

The governed auditor performs:

1. **Identifier overlap:** require zero overlap between visible synthetic and real identifiers.
2. **Exact longitudinal reproduction:** hash normalized eligible profiles with at least three anthropometric observations and require zero complete reproductions. Common empty or structurally uninformative profiles are reported separately and never count as evidence of safety.
3. **Nearest-neighbor risk screening:** compare synthetic-to-calibration-real distances with held-out-real-to-calibration-real and synthetic-to-held-out-real controls on prespecified quasi-identifier and trajectory feature sets. Report distance distributions, uniqueness, nearest-versus-second-nearest margins, and rare-stratum results without treating proximity alone as identity disclosure.
4. **Linkage attacks:** attempt record linkage under multiple attacker-knowledge subsets. Compare high-confidence candidate rates and attack advantage with permutation, population-frequency, and held-out-real controls.
5. **Membership inference:** create multiple shadow calibration partitions and generated packages with known membership labels. Evaluate distance- and classifier-based attacks on untouched target runs; a single calibration-versus-held-out comparison is insufficient because it may measure distribution shift rather than membership leakage.
6. **Attribute disclosure:** test whether an apparent link permits sensitive diagnosis or trajectory attributes to be inferred materially better than approved population, stratum, and held-out baselines.
7. **Composition:** evaluate the package together with prior synthetic and calibration releases available to the intended recipient.
8. **Negative and positive controls:** an independent toy generator must not appear leaky merely because it differs from the real distribution, while intentionally copied or overfit generators must be detected.

### Risk policy and decisions

Decision rules live in a versioned privacy-policy file and identify the recipient class, release context, accounting unit, attacker knowledge, metrics, confidence method, subgroup handling, minimum evaluable sample, tolerances, approver, and review date. Zero identifier overlap and zero exact eligible longitudinal reproductions are mandatory engineering rules. Numeric linkage, membership, and attribute-inference thresholds are context-specific policy choices, not universal definitions of a very small risk.

The auditor reports point estimates and uncertainty across patient partitions, shadow runs, generator seeds, and rare groups. An aggregate pass cannot hide an evaluable subgroup failure. An underpowered attack is `UNEVALUABLE`, not `PASS`. A qualified privacy expert and data custodian determine whether the resulting evidence supports the intended release; the software cannot confer HIPAA status or approve release.

The exportable audit report contains aggregate metrics, uncertainty intervals, policy identity, control behavior, and decision reasons. It excludes identifiers, candidate pairs, patient-level distances, attack examples, and undersized cells.

## Validation framework

Validation produces machine-readable JSON plus a concise human-readable report. Calibration targets and acceptance tolerances are frozen before the governed held-out comparison. Statistical and clinical gates run across multiple predeclared generator seeds.

### Layer 1: structural and derivation validity

- provenance identities are present and mutually compatible;
- all eight resources have exact paths, headers, field order, types, null behavior, dialects, encodings, constraints, and schema fingerprint;
- declared keys and complete foreign keys resolve; foundation structural validation recomputes `x-logicalForeignKeys` null/orphan counts in the generated descriptor without rejecting them, while a later versioned observation/calibration policy may require selected logical links to be complete; the structural validation report itself contains only errors and row counts; and
- augmented values match the authoritative derivation oracle within declared numeric tolerances.

### Layer 2: statistical fidelity

- demographics, observation windows, visits, measurement availability, observation errors, diagnoses, flags, and resource densities meet size-aware marginal and joint tolerances;
- clean growth summaries meet age-regime-, sex-reference-, phenotype-, and disease-specific tolerances;
- rare groups use hierarchical estimates and explicit uncertainty rather than reproducing unstable small cells; and
- results are reported separately for population, latent disease, observed phenotype, observed healthcare cohort, and recorded diagnoses.

### Layer 3: longitudinal and clinical fidelity

- trajectories preserve anthropometric identities, continuity, valid reference domains, age-regime transitions, plausible velocity, channel crossing, puberty timing, and adult-height convergence;
- every disease module passes its onset-to-phenotype, recognition, workup, diagnosis, treatment, adherence, and response assertions;
- event-order, sequence-length, age-window, time-to-diagnosis, time-to-treatment, and outcome distributions do not exhibit progressive temporal drift; and
- a blinded clinical review samples healthy, disorder, noisy, censored, contradictory, and counterfactual charts using a prespecified rubric and adjudication process.

### Layer 4: task utility

- the intended growth-screening and counterfactual-analysis pipelines execute unchanged on the exact-schema package;
- task outputs are evaluated against hidden synthetic truth without exposing truth through visible APIs;
- where governed real labels and authorization exist, train-on-synthetic/test-on-real or equivalent fixed-model evaluations compare discrimination, calibration, subgroup behavior, and failure modes with predeclared equivalence or noninferiority margins; and
- synthetic task success is never interpreted as real-data clinical validation.

### Layer 5: counterfactual validity

- paired worlds share every node and stream declared invariant;
- manipulated nodes and permitted descendants change in the declared direction and time window;
- forbidden descendants do not change; and
- tests compare both hidden traces and visible fields.

### Layer 6: privacy evidence

- the governed auditor executes all applicable attacks and controls under an approved policy;
- the package is rejected if a mandatory rule fails;
- an unevaluable attack or subgroup blocks the corresponding release claim; and
- human release authorization remains separate from the automated result.

Golden runs apply structural, derivation, clinical, task-execution, and counterfactual assertions using forced coverage instead of population-fidelity claims. Ordinary development runs apply the structural, derivation, longitudinal, and counterfactual checks required by their profile; statistical, clinical, task-utility, and privacy layers are optional evidence workflows. Any release or use outside the ordinary synthetic-development context additionally requires the applicable evidence and human authorization.

## Command-line interfaces

The intended engine-independent interfaces are:

```sh
uv run python -m synthetic.calibrate \
  --data-root /governed/ppoc \
  --snapshot 2026-08-24 \
  --partition-policy /governed/partition-policy.json \
  --disclosure-policy synthetic/config/disclosure-policy.json \
  --output /governed/calibration

uv run python -m synthetic.generate \
  --engine native \
  --profile development \
  --patients 10000 \
  --seed 20260830 \
  --calibration /approved/calibration.json \
  --output /fixtures/development-20260830

uv run python -m synthetic.validate \
  --package /fixtures/development-20260830

uv run python -m synthetic.heldout_validate \
  --real-root /governed/ppoc \
  --partition /governed/heldout-partition.json \
  --synthetic-root /fixtures/development-20260830 \
  --frozen-policy /governed/fidelity-policy.json \
  --output /governed/heldout-report

uv run python -m synthetic.privacy_audit \
  --real-root /governed/ppoc \
  --synthetic-root /fixtures/development-20260830 \
  --policy /governed/approved-risk-policy.json \
  --output /governed/audit-report
```

An accepted Synthea adapter uses `--engine synthea` and a pinned engine configuration. It may invoke Java internally, but visible CLI results, manifests, failure states, and validation semantics remain identical. Configuration files are strict: unknown keys, missing versions, incompatible fingerprints, invalid probabilities, unsupported overlaps, undeclared causal changes, and impossible prevalence constraints are errors rather than warnings.

## Error handling and run lifecycle

- Calibration stops before profiling when a real header differs from the descriptor or patient-disjoint partitioning cannot be demonstrated.
- When a governed calibration artifact is supplied, generation stops if it fails disclosure validation, requires a suppressed value without a declared parent fallback, or targets too few patients for requested claims.
- A Synthea-backed run stops if its revision, module hashes, custom physiology extension, event adapter, or exporter differs from the approved engine manifest.
- Output directories must not already exist.
- Partial files remain in a run-specific temporary directory with a failure manifest and are never labeled validated.
- A route without a pinned derivation oracle remains `UNVERIFIED_DERIVATION` for augmented claims; the ordinary development route uses the checked-in test-only oracle and reports its test-only status explicitly.
- Validation reports independent gate failures together where doing so does not create cascading, misleading results.
- Held-out validation data cannot be used by an automated tuning loop.
- Privacy failure marks a run `REJECTED_PRIVACY`; candidate-match details remain governed.
- No command publishes, uploads, commits, or copies a package outside its supplied output location.

## Testing strategy

### Unit tests

- WHO, CDC, extended-BMI, score-inversion, percentile, and source-compatible calculations;
- deterministic derivation of weight from height and BMI and of BMI from observed height and weight;
- birth, infancy, 24-month transition, prepubertal, puberty, and late-adolescent behavior;
- target height, pubertal tempo and intensity, smooth trajectory components, and every disease module's age-windowed effects;
- incidence, system entry, censoring, recognition, treatment, adherence, and response;
- deterministic named random substreams and PRNG-version behavior;
- every measurement-error mode, missingness, diagnosis delay, and logical-link rule;
- disorder-critical ancillary-resource transitions; and
- disclosure suppression, differential-privacy contribution bounds when enabled, composition accounting, and risk-policy parsing.

### Contract and integration tests

- generate a small package and compare its schema fingerprint with the source descriptor;
- parse every generated field through the descriptor;
- verify all primary, foreign, and logical-link semantics;
- recompute augmented resources independently through the pinned derivation oracle;
- generate every golden age regime, disease module, error mode, and censoring boundary;
- generate each counterfactual class and assert its causal change matrix;
- prove identical seeds and versions produce identical hashes;
- prove different seeds produce disjoint visible identifiers;
- prove no visible API or file exposes the truth manifest or event trace; and
- run the calibrator against a wholly synthetic mock real package so CI never needs governed data.

### Engine-conformance tests

- run native and Synthea-backed engines against the same engine-neutral golden contracts;
- verify exact PPOC schema and derivation parity for both;
- verify disease-state and event-trace semantics rather than expecting identical random patients;
- verify that Synthea defaults cannot bypass approved population, physiology, module, or exporter configuration; and
- compare longitudinal and task metrics as sensitivity analysis without using cross-engine agreement as ground truth.

### Statistical and clinical tests

- evaluate frozen targets over multiple seeds with uncertainty intervals;
- detect temporal drift by age window, event order, and sequence length;
- test every disease module's phenotype, diagnosis delay, treatment, and response distribution;
- test subgroup and intersectional fidelity only where support is sufficient; and
- exercise the blinded clinical-review export without revealing real records or hidden evaluator truth to the reviewed application.

### Privacy attack tests

- an intentionally copied longitudinal profile must fail exact-reproduction and linkage rules;
- intentionally overfit shadow generators must fail membership inference;
- a rare uniquely identifying pattern must fail the relevant rare-stratum rule;
- a genuinely independent toy generator must pass negative controls even when its distribution is imperfect;
- underpowered attacks must return `UNEVALUABLE`; and
- exported reports must contain no identifiers, candidate pairs, patient-level distances, attack examples, or undersized cells.

### Scale tests

A scheduled development-profile test exercises bounded-memory generation, all eight resources, derivation, longitudinal validation, and task execution at 10,000 patients across the required seed set. CI uses golden and small integration profiles. Governed held-out and privacy tests run only in their authorized environments.

## Acceptance criteria

The ordinary development route is complete when its content and integrity criteria (exact schema, coherent trajectories, deterministic generation, hidden-truth exclusion, and counterfactual invariants) pass. The additional criteria below apply when the project seeks population, clinical, privacy, task-utility, Synthea, or release claims; they are not prerequisites for ordinary development fixtures.

The full native implementation is complete for its applicable claims when:

1. The authoritative augmentation implementation or approved parity harness is pinned and its boundary cases pass.
2. A golden package and a 10,000-patient development package can be generated deterministically from approved nonpatient inputs.
3. Both packages contain all eight resources and match the source schema fingerprint.
4. Anthropometric identities and age-regime transitions pass independent biological and derivation checks.
5. Every enabled disease module has cited transition logic, reviewed terminology, at least one reviewed golden case, and population-level longitudinal signature tests.
6. Disorder-critical laboratories, medications, problems, and referrals are causally coherent with enabled modules.
7. When population-fidelity evaluation is requested, population, latent disease, observable phenotype, observed-cohort, and recorded-diagnosis prevalences are separately reported; applicable held-out demographic, growth, visit, missingness, error, and resource targets meet frozen size-aware tolerances over multiple seeds.
8. The intended growth-screening workflow runs unchanged, its synthetic-truth metrics are reported, and any authorized real holdout task comparison uses predeclared margins.
9. Every counterfactual class passes its change-matrix and invariant checks.
10. Blinded clinical review passes the prespecified rubric or all material disagreements are resolved and documented.
11. Intentionally leaky packages are rejected, independent negative controls behave as expected, and underpowered attacks are not reported as passes.
12. A governed privacy audit can produce an aggregate report without exporting patient-level comparison data.
13. Documentation clearly distinguishes ordinary synthetic development utility and content controls from optional statistical fidelity, task utility, privacy evidence, clinical validation, and release authorization.

An optional Synthea-backed implementation is accepted only after all applicable criteria above and the engine-conformance suite pass. It is not required for release one.

## Design decisions

- Make the fixture and validation contracts engine-independent; implement the native growth-first engine first and retain Synthea as an optional conforming backend, hybrid background-event source, and comparator.
- Use a mechanistic, reference-based longitudinal generator rather than row resampling, nearest-neighbor synthesis, a GAN, or a general patient-sequence model.
- Generate only two independent anthropometric dimensions in each age regime and derive the third.
- Model infancy, childhood, puberty, and late adolescence explicitly.
- Separate source population, latent disease, observable phenotype, healthcare observation, and recorded EHR.
- Represent growth disorders as cited clinical state machines with disorder-critical descendants.
- Combine population generation with a small hand-reviewed golden-case library.
- Calibrate clean physiology and observation errors separately from patient-disjoint, disclosure-controlled aggregates.
- Preserve hidden latent truth and permit diagnoses to be delayed, nonspecific, or absent.
- Define counterfactuals through explicit causal change matrices and named random streams.
- Derive augmented resources only through an authoritative parity-tested contract.
- Treat privacy as context-specific attack evidence and human-governed release review, not as an automatic consequence of calling data synthetic.
- Prefer patient-level differential privacy for exportable calibration artifacts that support external or repeated releases.

## References informing the design

- [Synthea repository, pinned review revision](https://github.com/synthetichealth/synthea/tree/d9d07a6eef91ee5144293b42ab64224d84d124f8): lifecycle architecture, modules, exporters, seeds, and implementation baseline inspected for this revision.
- [Synthea Generic Module Framework](https://github.com/synthetichealth/synthea/wiki/Generic-Module-Framework): state-and-transition pattern for clinical events.
- [Synthea pediatric growth trajectory](https://synthetichealth.github.io/synthea/build/javadoc/org/mitre/synthea/world/concepts/PediatricGrowthTrajectory.html): NHANES-derived annual correlated BMI trajectory approach from ages 2 through 20.
- [Walonoski et al., Synthea](https://pmc.ncbi.nlm.nih.gov/articles/PMC7651916/): intended uses and limits of general-purpose synthetic patients.
- [Chen et al., Synthea validation](https://pmc.ncbi.nlm.nih.gov/articles/PMC6416981/): realistic demographics or service frequencies do not guarantee realistic downstream outcomes.
- [Walonoski et al., longitudinal drift](https://pmc.ncbi.nlm.nih.gov/articles/PMC9552284/): first-order event fidelity can coexist with progressive sequence drift.
- [CDC growth-chart guidance](https://www.cdc.gov/growth-chart-training/hcp/using-growth-charts/who-using.html): WHO birth-to-age-2 and CDC age-2-to-20 transition considerations.
- [CDC growth charts](https://www.cdc.gov/growthcharts/index.htm): CDC references and extended BMI-for-age charts.
- [Cole et al., SITAR](https://pmc.ncbi.nlm.nih.gov/articles/PMC2992626/): size, tempo, and velocity representation of pubertal growth.
- [Daymont et al., pediatric EHR growth-data errors](https://pmc.ncbi.nlm.nih.gov/articles/PMC7651915/): error mechanisms and longitudinal plausibility validation.
- [HHS guidance on PHI de-identification](https://www.hhs.gov/hipaa/for-professionals/special-topics/de-identification/index.html): identification risk is context-dependent and not zero; Expert Determination requires documented methods and results for anticipated recipients.
- [NIST SP 800-226](https://www.nist.gov/publications/guidelines-evaluating-differential-privacy-guarantees): evaluation of differential-privacy guarantees and implementation hazards.
- [Stadler et al., Synthetic Data -- Anonymisation Groundhog Day](https://www.usenix.org/system/files/sec22summer_stadler.pdf): similarity tests alone can underestimate disclosure risk.
