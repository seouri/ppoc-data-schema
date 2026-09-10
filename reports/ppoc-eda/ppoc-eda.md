# PPOC pediatric EHR snapshot: an exploratory data analysis

A project-neutral reference for anyone analysing this extract. Every figure is measured from the delivered bundle; the report states what the data support, what they do not, and which checks this extract cannot answer at all.

## Contents

- [0. How to use this report](#0-how-to-use-this-report)
  - [0.1 Three ways in](#01-three-ways-in)
- [1. The snapshot](#1-the-snapshot)
  - [1.1 Package identity and integrity](#11-package-identity-and-integrity)
  - [1.2 Resource map, grain, and keys](#12-resource-map-grain-and-keys)
  - [1.3 Two layers with different provenance](#13-two-layers-with-different-provenance)
  - [1.4 How this cohort was built](#14-how-this-cohort-was-built)
  - [1.5 The de-identification envelope](#15-the-de-identification-envelope)
- [2. Checklist coverage](#2-checklist-coverage)
  - [2.1 The checklist, item by item](#21-the-checklist-item-by-item)
- [3. Integrity](#3-integrity)
  - [3.1 Keys, grain, and uniqueness](#31-keys-grain-and-uniqueness)
  - [3.2 Referential integrity and cross-resource linkage](#32-referential-integrity-and-cross-resource-linkage)
  - [3.3 Age-axis consistency and impossible sequences](#33-age-axis-consistency-and-impossible-sequences)
  - [3.4 Missingness, by field and by age](#34-missingness-by-field-and-by-age)
  - [3.5 Nulls that are not missing, and sentinels that are not data](#35-nulls-that-are-not-missing-and-sentinels-that-are-not-data)
  - [3.6 Code systems, free text, and categorical hygiene](#36-code-systems-free-text-and-categorical-hygiene)
  - [3.7 Capture: measurement presence is not measurement occurrence](#37-capture-measurement-presence-is-not-measurement-occurrence)
  - [3.8 Same-day measurements that disagree](#38-same-day-measurements-that-disagree)
  - [3.9 Counting diagnosis codes: ICD-10 is a hierarchy](#39-counting-diagnosis-codes-icd-10-is-a-hierarchy)
- [4. Anthropometrics](#4-anthropometrics)
  - [4.1 Trajectory supply: how many heights each child has](#41-trajectory-supply-how-many-heights-each-child-has)
  - [4.2 Recording units and the measurement grid](#42-recording-units-and-the-measurement-grid)
  - [4.3 Distributions and plausibility bounds](#43-distributions-and-plausibility-bounds)
  - [4.4 Transcription-error signatures in the typed fields](#44-transcription-error-signatures-in-the-typed-fields)
  - [4.5 Repeated measurements: zero growth and apparent height loss](#45-repeated-measurements-zero-growth-and-apparent-height-loss)
  - [4.6 Derived z-scores and percentiles: bounds and saturation](#46-derived-z-scores-and-percentiles-bounds-and-saturation)
  - [4.7 Head circumference: a recoverable conversion defect](#47-head-circumference-a-recoverable-conversion-defect)
  - [4.8 The distributed delta and velocity fields](#48-the-distributed-delta-and-velocity-fields)
  - [4.9 Age- and sex-stratified growth profile](#49-age--and-sex-stratified-growth-profile)
  - [4.10 Within-child dependence in the height channel](#410-within-child-dependence-in-the-height-channel)
  - [4.11 BMI: recomputation and recorded categories](#411-bmi-recomputation-and-recorded-categories)
- [5. Clinical domains and cross-resource structure](#5-clinical-domains-and-cross-resource-structure)
  - [5.1 Diagnoses](#51-diagnoses)
  - [5.2 Laboratory results](#52-laboratory-results)
  - [5.3 Medications](#53-medications)
  - [5.4 Referrals](#54-referrals)
  - [5.5 Recorded identity and patient-level observation](#55-recorded-identity-and-patient-level-observation)
  - [5.6 Patient-level derived flags and summaries](#56-patient-level-derived-flags-and-summaries)
  - [5.7 The extract's growth orientation: tracked codes and referral pathways](#57-the-extracts-growth-orientation-tracked-codes-and-referral-pathways)
  - [5.8 Age at first record for each growth-relevant diagnosis code](#58-age-at-first-record-for-each-growth-relevant-diagnosis-code)
  - [5.9 Label, trajectory, and utilization do not line up](#59-label-trajectory-and-utilization-do-not-line-up)
  - [5.10 What a feature vector actually contains](#510-what-a-feature-vector-actually-contains)
  - [5.11 Treatment and workup: better timing than the label, and leakage](#511-treatment-and-workup-better-timing-than-the-label-and-leakage)
  - [5.12 The same code in two resources: encounter diagnoses against the problem list](#512-the-same-code-in-two-resources-encounter-diagnoses-against-the-problem-list)
  - [5.13 Referral timing against the diagnosis, and the subgroup it finds](#513-referral-timing-against-the-diagnosis-and-the-subgroup-it-finds)
  - [5.14 A shortcut audit: which fields encode the label](#514-a-shortcut-audit-which-fields-encode-the-label)
  - [5.15 The same screen over the numbers: derived columns and constructed features](#515-the-same-screen-over-the-numbers-derived-columns-and-constructed-features)
- [6. Field index](#6-field-index)
  - [6.1 Every column in the extract](#61-every-column-in-the-extract)
- [7. Artifact catalogue](#7-artifact-catalogue)
  - [7.1 Every artifact this report measured](#71-every-artifact-this-report-measured)
- [8. Methods and limitations](#8-methods-and-limitations)
  - [8.1 Methods, determinism, and limitations](#81-methods-determinism-and-limitations)

## 0. How to use this report

Three ways in, depending on what you came for.

### 0.1 Three ways in

This report describes one snapshot of one pediatric primary-care EHR extract. Through Part 4 it belongs to no project: it states what the data are, what they support, and what they cannot answer, and it leaves the research question to you. From 5.9 it stops being neutral on purpose. The extract was assembled upstream around one question — identifying abnormal growth early — and those sections work that question through, because the label it implies is already shipped in the data as `growth_dx_flag` and its shortcuts are not visible from a field-by-field description. Read them as a worked example of auditing a label, not as the report choosing your outcome.

**Where to start**

| if you are | start here |
| --- | --- |
| New to this extract | Read Part 1, then the not-applicable table in Part 2. Twenty minutes, and it will save days. |
| About to use a specific field | Find it in the Part 6 field index, then follow the finding it links to. |
| Explaining a number that looks wrong | Check the Part 7 artifact catalogue before assuming a bug in your code. |
| Planning a study | Part 1.4 first. The cohort selection invalidates several whole classes of question, and it is not visible in any field. |
| Building features or a model | 5.9 for whether the label can be predicted at all, then the shortcut screens in 5.14 and 5.15 before you fix a feature set. |

Every number here was measured from the delivered bundle for snapshot `2026-08-24`; none is copied from another document without being recomputed. The cohort date and the extract cut are stated once, in 1.4, and referenced from everywhere else that needs them.

**What this report is not.** It is not a clinical validation, not a registered analysis, and not a statement about any individual child. Every figure is an aggregate, and any cell resting on fewer than 10 records is suppressed.

## 1. The snapshot

What this extract contains, how it was built, and what its construction forecloses.

### 1.1 Package identity and integrity

Everything in this report was computed from the typed DuckDB bundle of package `ppoc-pediatric-ehr` 1.0.0, snapshot `2026-08-24`, sha256 `425c6f873cefc149344570561a03b33c69a6a6af7fa18bc777c0429579507116`. The bundle is opened read-only and is never copied into this repository. That snapshot label dates the bundle build, not the clinical window — it sits well after the extract was cut, and 1.4 gives the two dates that bound the data.

Three independent sources state how large this extract should be: the bundle manifest, the PPOC delivery documents committed under `docs/`, and the data itself. They are reconciled here before any other figure is computed, so that a bundle drawn from a different extract would be visible rather than silently profiled.

**Row counts, measured against both declared sources**

| resource | measured | bundle manifest | PPOC document | agrees |
| --- | --- | --- | --- | --- |
| patients | 250,588 | 250,588 | 250,588 | yes |
| patients_augmented | 250,588 | 250,588 | — | yes |
| visits | 6,494,473 | 6,494,473 | 6,494,473 | yes |
| visits_augmented | 6,494,473 | 6,494,473 | — | yes |
| labs | 17,230,681 | 17,230,681 | 17,230,681 | yes |
| medications | 3,823,049 | 3,823,049 | 3,823,049 | yes |
| problem_list | 1,709,584 | 1,709,584 | 1,709,584 | yes |
| referrals | 349,827 | 349,827 | 349,827 | yes |

A dash in the PPOC column means the resource was not part of the delivery: `patients_augmented` and `visits_augmented` are generated locally from the delivered files, so PPOC states no count for them. See 1.3.

**Distinct patients per resource, against the PPOC counts**

| resource | measured | PPOC document | agrees |
| --- | --- | --- | --- |
| visits | 250,588 | 250,588 | yes |
| problem_list | 238,823 | 238,823 | yes |
| labs | 247,271 | 247,271 | yes |
| medications | 236,323 | 236,323 | yes |
| referrals | 138,071 | 138,071 | yes |

The lab resource carries a second stated figure: 6,578,838 distinct lab orders behind the resulted components. The bundle holds 6,578,838. Across every count above, 0 disagree.

### 1.2 Resource map, grain, and keys

The package is 8 tables carrying 254 columns between them, but they do not share a provenance: 6 were delivered by PPOC and 2 are generated locally (1.3). Grain matters more than row count here: three of the resources are keyed on something other than the patient or the visit, and one of them needs two columns to be unique.

**The eight resources**

| resource | source | rows | cols | grain | primary key | links to |
| --- | --- | --- | --- | --- | --- | --- |
| patients | PPOC | 250,588 | 11 | one row per patient | patient_id | — |
| patients_augmented | scripts/augment.py | 250,588 | 87 | one row per patient | patient_id | patients |
| visits | PPOC | 6,494,473 | 43 | one row per patient per encounter | visit_id | patients |
| visits_augmented | scripts/augment.py | 6,494,473 | 82 | one row per patient per encounter | visit_id | visits |
| labs | PPOC | 17,230,681 | 12 | one row per resulted component of a lab order | lab_order_id + result_line_num | patients; visits (partial) |
| medications | PPOC | 3,823,049 | 8 | one row per medication order or historical record | med_record_id | patients; visits (partial) |
| problem_list | PPOC | 1,709,584 | 5 | one row per problem-list entry | problem_list_id | patients |
| referrals | PPOC | 349,827 | 6 | one row per referral order | referral_id | patients; visits (partial) |

Six resources were delivered by PPOC; the two augmented ones are generated locally from them. 1.3 explains why that distinction matters.

`visit_id` on labs, medications, and referrals is a partial link by design, not a defect: an order placed outside a visit carries an identifier that resolves to no encounter in this extract. Section 3.2 measures how partial.

### 1.3 Two layers with different provenance

**Only 6 of the 8 resources in this package came from PPOC.** The delivery comprised patients, visits, problem list, medications, labs, and referral orders; the data dictionary and the extract diagram committed under `docs/` describe those 6 and no others. The remaining 2 — `patients_augmented` and `visits_augmented` — are **generated locally** by `scripts/augment.py` from the delivered files, using CDC LMS reference tables, velocity rules, and outlier detection.

That distinction decides who can fix what. A defect in a delivered resource is the source system's and can only be worked around; a defect in the augmented layer belongs to a script in this repository and can be corrected by re-running it. Everything this report labels a *derivation* artifact — the truncated height z-score of 4.6, the double-converted head circumference of 4.7, the interval rule behind the velocity fields of 4.8 — is a property of that local step, not of the data PPOC sent.

Because the augmented layer is derived from the delivered one, the fields they share should agree exactly. Across all 6,494,473 joined visit rows, five of the six do.

**Shared visit fields, raw against augmented**

| field | rows differing | share |
| --- | --- | --- |
| height_in | 0 | 0.00% |
| weight_oz | 0 | 0.00% |
| head_circ_cm | 0 | 0.00% |
| encounter_type | 0 | 0.00% |
| age_in_days | 0 | 0.00% |
| BMI / bmi | 3,658,277 | 56.33% |

BMI is the exception, and the disagreement is structured rather than noisy. 1,703,005 visits carry a raw `BMI` where the augmented `bmi` is null, at a median age of 0.51 years; the augmented layer withholds BMI below age 2, where a CDC BMI-for-age reference does not apply, while the raw value is computed inside the source EHR at every age. A further 41 rows go the other way, and 536 carry both values differing by more than 0.01.

**The patient layer diverges further, and Part 5 works in it.** `patients` and `patients_augmented` also share `sex`, `ethnicity` and the race slots, over 250,588 joined patient rows. Sex agrees exactly; the other two do not, and the disagreement is a great deal larger than BMI's in relative terms.

**Shared patient fields, raw against augmented**

| field | populated, raw | populated, augmented | rows differing | share | distinct, raw | distinct, augmented |
| --- | --- | --- | --- | --- | --- | --- |
| sex | 250,588 | 250,588 | 0 | 0.00% | 3 | 3 |
| ethnicity | 245,124 | 199,143 | 45,981 | 18.35% | 6 | 2 |
| race_1 | 241,770 | 200,533 | 41,237 | 16.46% | 11 | 7 |

`race_1` stands for the eight race slots, which are cleaned the same way.

This is a documented transformation rather than a defect: `docs/patients_augmented.md` records that the augmented layer converts non-informative responses in `ethnicity` and `race_*` to null. On `ethnicity` it moves 45,981 patients from a recorded value to a null and collapses the vocabulary from 6 categories to 2. The 4 values that go are "Choose not to Answer", "Patient does not know", "Unable to collect", "Unknown" — every recorded form of non-response, and nothing else.

**Implications for analysis.** Reading `visits.BMI` silently yields infant BMI values that the augmented layer deliberately suppresses, and the two layers will not reproduce each other's descriptive statistics. Choose a layer for a stated reason and record which; do not mix them within one analysis. The 536 rows where both are present and disagree are small enough to screen individually. On the patient layer the consequence is sharper: 5.5 reports identity non-response as its own category and advises keeping it that way, which is only possible against the delivered `patients` table. In the augmented layer a declined answer and a question never asked are the same null, so take identity from `patients` whenever the distinction carries any weight.

### 1.4 How this cohort was built

This is the most consequential section of the report, because it describes a property of the data that no field exposes and that no amount of analysis can recover. The 250,588 patients here are what remains after four successive exclusions applied by PPOC to an active-patient registry of 437,996. The final count reconciles against the delivered data exactly: 250,588 patient rows.

*Figure — Cohort construction, registry to delivered extract. Rendered in `index.html` at `#fig-funnel`.*

**The four exclusions**

| step | criterion | excluded | remaining |
| --- | --- | --- | --- |
| 0 | On the PPOC active-patient registry |  | 437,996 |
| 1 | Age under 18 as of 31 Dec 2024 | 76,670 excluded | 361,326 |
| 2 | Excluding 2 practices that declined participation | 9,309 excluded | 352,017 |
| 3 | At least 5 growth measurements of one type on distinct dates, spanning over 1095 days, last measurement within 400 days | 61,842 excluded | 290,175 |
| 4 | Carrying no rare diagnosis, medication, or lab | 39,587 excluded | 250,588 |

"Active" on that registry means living status alive, not flagged as a test or inactive record, an active PPOC primary-care association, and either a visit in the last three years or one scheduled in the next fifteen months. The cohort is pinned to 31 Dec 2024 and the extract was cut on 03 Feb 2025.

The fourth exclusion is the one most likely to be missed, because it removed *patients* rather than codes. A diagnosis, medication, or lab occurring fewer than 11 times in the data set was classed rare, and every patient carrying one was dropped.

**What the rarity exclusion removed**

| vocabulary | distinct values | classed rare | share |
| --- | --- | --- | --- |
| ICD-10 diagnosis codes | 30,493 | 18,604 | 61% |
| Simple generic medications | 2,503 | 1,391 | 56% |
| Lab procedures | 13,402 | 9,621 | 72% |

**Implications for analysis.** Rare conditions, rare exposures and uncommon labs are absent by construction, not merely sparse: a study of any of them returns a confident low rate rather than an obviously missing population. 61% of diagnosis codes, 56% of medications and 72% of lab procedures left with their patients. Because the registry requires living status alive, there are no deceased patients and mortality is not an available outcome. Because entry required at least five growth measurements, trajectory richness is an entry criterion and not a finding about pediatric care. And because the last measurement had to fall within 400 days of the cohort date, the panel is right-censored by design. No frequency in this extract is a population prevalence.

Two ambiguities in the source documents are recorded rather than silently resolved. The cohort workbook describes the under-three exemption as applying to the span requirement for children who already have five measurements, while the extract diagram describes it as age under three with at least one measurement. The same two documents give the rarity threshold as "fewer than 11 occurrences" and "under 10 patients".

### 1.5 The de-identification envelope

`age_in_days` is the only clock. The extract carries no calendar date, no time of day, no site, practice, provider, or geography, and no free text from any note. That is stated once here and referenced from Part 2 rather than re-argued at each check it rules out.

**Checks this extract forecloses, and why**

| standard check | why it cannot be run |
| --- | --- |
| Duplicate-patient detection | no name, birth date, or linkage key survives |
| Batch-entry clustering | ages are integer days; there is no time of day |
| System downtime gaps | no calendar axis on which a void could appear |
| Missingness by site or provider | no such column exists in any resource |
| Calendar trend breaks and policy shifts | no calendar axis |
| Copy-forward of note text | no note text is included |
| Documentation timing | no timestamps |

One qualification, because "no calendar axis" is easy to overstate: the cohort itself is pinned to a fixed date and the extract was cut shortly after it, both given in 1.4. Ages are relative to each child's birth, but the *window* is fixed and known, which is what makes the recency criterion in 1.4 a right-censoring rule rather than an unknown.

## 2. Checklist coverage

Every item of the general EHR EDA checklist, mapped to what this snapshot can and cannot support.

### 2.1 The checklist, item by item

This part exists so that nobody has to wonder whether a standard check was skipped or was impossible. Of 45 items in the general EHR exploratory-analysis checklist, 32 are covered here, 4 are partially covered, and 9 cannot be run against this extract at all.

**Checklist coverage**

| checklist section | item | status | where, or why not |
| --- | --- | --- | --- |
| 0 Provenance | Extraction window | covered | Cohort and extract dates recovered from the delivery documents — 1.4 |
| 0 Provenance | Inclusion/exclusion logic | covered | The full four-step funnel — 1.4 |
| 0 Provenance | Vendor, version, migration events | covered | Epic against converted legacy records — 3.7 |
| 0 Provenance | Data dictionary present | covered | Committed under docs/; counts reconciled against it — 1.1, and every column listed against it — 6.1 |
| 0 Provenance | Raw vs CDM vs custom extract | covered | A custom extract plus a derived augmentation layer — 1.3 |
| 1 Structural | Row and table counts | covered | Against the manifest and the vendor's own counts — 1.1 |
| 1 Structural | Primary key uniqueness | covered | All eight resources — 3.1 |
| 1 Structural | Referential integrity | covered | 3.2 |
| 1 Structural | Duplicate patient detection | not applicable | No name, birth date, or linkage key survives de-identification — 1.5 |
| 1 Structural | Schema drift | covered | Live schema against the dictionary — 1.1; three documented medication classification fields absent — 5.3 |
| 1 Structural | Grain per table | covered | Including that patient and age is not unique in visits — 3.1 |
| 2 Temporal | Timestamp semantics | covered | 3.3 |
| 2 Temporal | Impossible sequences | covered | 3.3 |
| 2 Temporal | Batch-entry clustering | not applicable | Ages are integer days; there is no time of day — 1.5 |
| 2 Temporal | System downtime gaps | not applicable | No calendar axis — 1.5 |
| 2 Temporal | Coding or vendor transition | partial | Epic against converted is computable; ICD-9 to ICD-10 is not, without dates |
| 2 Temporal | Age sanity | covered | 3.3 |
| 3 Missingness | Missingness per field | covered | 3.4 and the field index |
| 3 Missingness | Missingness pattern | covered | By age — 3.4; by encounter type — 3.7 |
| 3 Missingness | Sentinel values | covered | 3.5 |
| 3 Missingness | Not measured vs measured negative | covered | Two fields whose nulls carry meaning — 3.5 |
| 3 Missingness | Missingness by site or provider | not applicable | No site, department, or provider column exists — 1.5 |
| 4 Distributional | Univariate distributions | covered | 4.3 |
| 4 Distributional | Unit inconsistencies | covered | 4.3 and 4.4 |
| 4 Distributional | Digit preference and rounding | covered | 4.2 |
| 4 Distributional | Categorical value counts | covered | 3.6 |
| 4 Distributional | Outlier detection | covered | Bounds reported before any exclusion is recommended — 4.3 |
| 4 Distributional | Cross-field plausibility | covered | Raw against augmented layers — 1.3 |
| 5 Terminology | Code system vintage | covered | 3.6 |
| 5 Terminology | Granularity consistency | covered | 3.6 |
| 5 Terminology | Problem list staleness | covered | 3.5 |
| 5 Terminology | Free text vs structured | covered | Laboratory result values are semi-structured text — 3.6 |
| 5 Terminology | Local or custom codes | covered | 3.6 |
| 6 Workflow | Copy-forward detection | partial | Detectable on measurements; no note text is included |
| 6 Workflow | Template or boilerplate detection | not applicable | No note text — 1.5 |
| 6 Workflow | Documentation timing | not applicable | No timestamps — 1.5 |
| 6 Workflow | Order/result reconciliation | covered | 3.6 |
| 7 Population | Cohort representativeness | partial | The cohort is not representative and 1.4 says exactly how; no external benchmark ships with this repository |
| 7 Population | Encounter type mix | covered | 3.7 |
| 7 Population | Follow-up time distribution | covered | 4.1 |
| 7 Population | Site or provider volume | not applicable | No such field — 1.5 |
| 8 Longitudinal | Calendar trend breaks | not applicable | No calendar axis. Age-axis profiles are reported instead and are not the same thing — 1.5 |
| 8 Longitudinal | Guideline or policy shift | not applicable | Requires calendar time — 1.5 |
| 8 Longitudinal | Vendor changeover effects | partial | The Epic against converted contrast only |
| 9 Label | Shortcut screen against the label | covered | Every value of seven categorical fields, scored again under a second index — 5.14; every numeric and constructed feature — 5.15 |

The not-applicable list is the part worth reading before you start. Every entry is a consequence of de-identification or of what the extract simply does not carry, and no amount of analysis recovers any of them.

**Checks this extract cannot support**

| check | why |
| --- | --- |
| Duplicate patient detection | No name, birth date, or linkage key survives de-identification — 1.5 |
| Batch-entry clustering | Ages are integer days; there is no time of day — 1.5 |
| System downtime gaps | No calendar axis — 1.5 |
| Missingness by site or provider | No site, department, or provider column exists — 1.5 |
| Template or boilerplate detection | No note text — 1.5 |
| Documentation timing | No timestamps — 1.5 |
| Site or provider volume | No such field — 1.5 |
| Calendar trend breaks | No calendar axis. Age-axis profiles are reported instead and are not the same thing — 1.5 |
| Guideline or policy shift | Requires calendar time — 1.5 |

**Implications for analysis.** Treat the second table as a design constraint rather than a gap to work around. A protocol that depends on provider variation, time-of-day effects, calendar trends, or deceased patients cannot be run on this extract, and discovering that after cohort construction is expensive.

## 3. Integrity

Keys, linkage, the age axis, missingness, terminology, and capture.

### 3.1 Keys, grain, and uniqueness

All 7 single-column primary keys the delivery documents declare hold exactly. Labs has no declared composite key — the data dictionary gives its grain as one row per result component and names no key — so the one below is reconstructed here, and it is minimal: `lab_order_id` + `result_line_num` is unique on its own across all 17,230,681 rows, and adding `result_component_name` changes nothing (17,230,681 groups either way).

The combination to avoid is the one an analysis reaches for instead. Joining on the order and the component *without* the line number collapses to 17,093,224 groups, 33,879 of which hold more than one row, so that join multiplies rows rather than matching them. 3.6 measures how far the duplicated lines disagree and what the source system says produces them.

**Primary keys, measured**

| resource | key | rows | distinct keys | unique |
| --- | --- | --- | --- | --- |
| patients | patient_id | 250,588 | 250,588 | yes |
| patients_augmented | patient_id | 250,588 | 250,588 | yes |
| visits | visit_id | 6,494,473 | 6,494,473 | yes |
| visits_augmented | visit_id | 6,494,473 | 6,494,473 | yes |
| medications | med_record_id | 3,823,049 | 3,823,049 | yes |
| problem_list | problem_list_id | 1,709,584 | 1,709,584 | yes |
| referrals | referral_id | 349,827 | 349,827 | yes |
| labs | lab_order_id + result_line_num | 17,230,681 | 17,230,681 | yes |

Every row compares the table's rows against its distinct key values. The labs key is the report's own reconstruction; the other 7 come from the delivery documents.

What is *not* a key is the combination a longitudinal analysis reaches for first. 5,478 patient-days (0.08% of 6,488,911) carry more than one visit, covering 11,040 visit rows (0.17% of all visits). `age_in_days` is therefore not unique within a patient.

**Implications for analysis.** Any trajectory ordered by age alone has ties, and any window function partitioned by patient and ordered by age will resolve them arbitrarily unless you say how. Decide whether to take the first row, the mean, or the non-null value, and apply it before the analysis rather than inside it — 3.8 measures how far the two values sit apart on the days that carry two, which is what makes that choice consequential rather than arbitrary.

### 3.2 Referential integrity and cross-resource linkage

`patient_id` resolves everywhere, measured on every one of the 7 resources that carry it: 0 rows across all of them reference a patient who is not in `patients`. `visit_id` does not, and the shortfall is large enough that treating it as a complete foreign key will quietly drop or duplicate rows.

**Visit linkage by resource**

| resource | rows | visit_id null | populated but unresolved | share of populated |
| --- | --- | --- | --- | --- |
| labs | 17,230,681 | 805 | 5,201,657 | 30.19% |
| medications | 3,823,049 | 0 | 1,592,437 | 41.65% |
| referrals | 349,827 | 24,830 | 98,623 | 30.35% |

The null column is a count rather than a share, because as a share the two cases were indistinguishable: labs carries 805 rows with no `visit_id` at all and medications carries none, and at two decimal places both rounded to zero. A null cannot be joined and does not pretend to be joinable, which makes it the one part of this that is not silent.

The table covers every resource carrying a `visit_id`. `problem_list` carries none, so a problem-list entry cannot be tied to an encounter under any join — not partially, as above, but not at all. That matters for anyone building a per-visit feature from diagnoses; 5.1 works from the constraint and this is where it is measured.

This is documented behaviour rather than corruption. The data dictionary states for each of these resources that the visit link "may not match to all" when the order was placed or the record documented outside a visit. The trap is that the column is populated on nearly every row, so a required-looking key silently fails to join.

**Implications for analysis.** Join to visits with an explicit outer join and count what fails, rather than an inner join that hides the loss. Anything computed per visit — encounter type, visit-level anthropometrics — is unavailable for the unresolved share, and that share is not random. Medications carry the one field that makes the dictionary's explanation checkable, and it does not fall the way the explanation suggests: an externally documented record — 5.3's outside or historical medication — is unresolved 18.2% of the time, while an order placed by a practice clinician is unresolved 45.8% of the time, 1,488,168 rows. Whatever produces the shortfall, it lands on practice orders rather than on outside documentation, so filtering to internal records selects for the problem instead of away from it. The two are not the same distinction — an internal phone refill has no encounter either — which is why the mechanism is left as the dictionary states it and only its incidence is reported here.

### 3.3 Age-axis consistency and impossible sequences

Age in days is the only clock, so ordering violations within a resource are visible directly. Counts below 10 are suppressed.

**Ordering and range checks**

| check | violating rows | rows checked | share | median violation | 95th pct |
| --- | --- | --- | --- | --- | --- |
| Lab result age earlier than lab order age | 583,055 | 14,947,495 | 3.901% | 1,229 d | 2,465 d |
| Medication start age earlier than order age | 329,107 | 3,539,983 | 9.297% | 43 d | 729 d |
| Medication end age earlier than start age | 12,709 | 3,179,759 | 0.400% | 2 d | 54 d |
| Problem resolved age earlier than noted age | 0 | 754,996 | 0.000% | — | — |
| Problem noted before birth | 650 | 1,702,300 | 0.038% | 7,468 d | 42,201 d |
| Lab ordered before birth | 47 | 17,230,681 | 0.000% | 129 d | 582 d |
| Medication ordered before birth | — | 3,823,049 | — | — | — |
| Visit recorded before birth | 0 | 6,494,473 | 0.000% | — | — |

An em dash in the violating-rows column means the count is nonzero but below the suppression threshold; a suppressed count gets no magnitude either. The last two columns are how far the violating rows are violated by, which a count alone does not say and which decides whether a check has found a rounding artifact or something else.

**The medication violations are explained, and the explanation is measurable.** For a historically documented medication the order date is the date the record was *written*, not when the drug was started, so the start can precede it by as long as the history goes back. 5.3's record type separates those from orders placed at the practice, and the violation is almost entirely theirs: 97.9% of externally documented records violate the ordering against 0.11% of internal ones — 325,707 rows against 3,400. The other mechanism at source, a charted approximation such as a month with no day stored as the first of that month, cannot be the main one: it would keep the gap inside a month, and only 44% of the violations are. End dates may sit in the future while a medication is active, which is the third row.

**The two before-birth rows are not the same kind of thing**, which only the magnitude shows. A lab ordered before birth sits a median of 129 days before it — a few months, which is what an order placed during the pregnancy and filed against the child would look like. A problem noted before birth sits a median of 7,468 days before it, decades rather than months, which no prenatal record explains: those 650 rows carry a wrong date rather than an early one. 5.12 excludes them from its lag comparison for exactly that reason.

**The lab violation is not explained by what the source says about it.** "Lab result and order ages derive from different source timestamps" describes a granularity artifact, and a granularity artifact does not have a median of 1,229 days. Whatever produces it, a result age sitting years before its order age is not a rounding difference, and this report cannot say what it is: no field in the extract distinguishes an order re-used for a later result from a mislinked one. Treat the pair as unordered rather than as nearly ordered.

**Implications for analysis.** Differences between two age fields in these resources are not reliable durations. Where you need an interval, take it from a single field across rows rather than between two fields on one row, and exclude historically documented medication records from any start-to-end calculation — 98% of them fail the most basic ordering check, so the exclusion is not a precaution. One limit on the checks themselves: a comparison can only run where both fields exist, so the resolved-before-noted row speaks for neither the 2,911 problems that carry a resolution date and no noted date nor any problem still open.

### 3.4 Missingness, by field and by age

Population was measured for all 176 columns in the extract, counting the repeated diagnosis and race families once each. 0 columns are entirely empty. The full table is Part 6; the 16 least-populated columns are below.

**The least-populated columns**

| resource | field | populated rows |
| --- | --- | --- |
| patients_augmented | dx_age_years_e24 | 1 |
| patients_augmented | dx_age_years_e72_11 | 1 |
| patients_augmented | dx_age_years_n25_0 | 1 |
| patients_augmented | dx_age_years_q78_1 | 2 |
| patients_augmented | dx_age_years_e22_0 | 3 |
| patients_augmented | dx_age_years_q78_0 | 10 |
| patients_augmented | dx_age_years_q77 | 15 |
| patients_augmented | dx_age_years_q87_4 | 17 |
| patients_augmented | dx_age_years_q98_5 | 17 |
| patients_augmented | dx_age_years_q98_0 | 26 |
| patients_augmented | dx_age_years_e23_6 | 31 |
| patients_augmented | dx_age_years_q87_2 | 32 |
| patients_augmented | dx_age_years_q96 | 36 |
| patients_augmented | dx_age_years_q98_4 | 42 |
| patients_augmented | dx_age_years_q87_3 | 46 |
| patients_augmented | dx_age_years_p04_3 | 53 |

A share is not shown because it would mislead: each of these columns is populated on some rows, and every one of them rounds to 100% missing against a quarter of a million patients, which would read as the empty columns the sentence above says do not exist. And every one of the 16 rows belongs to one family — the 34 `dx_age_years_*` columns, one per tracked diagnosis code, so this is a list of rare codes rather than a description of missingness; 5.7 and 5.8 are where they mean something. The sparsest column outside that family is `labs.result_loinc_code` at 92.2% missing.

A single missingness rate hides the thing that matters most for a longitudinal extract: whether a field is missing *at random* or missing *by age*. For the measurement channels it is emphatically the latter, and the size of it is worth having in words as well as in the figure below. Head circumference is on 57.1% of visits in the first year and 0.1% between 5 and 10. BMI is on 0.0% between 1 and 2 and 44.5% between 2 and 5, which is the age-2 floor of 1.3 rather than a change in practice. Height sits at 44.6% between 2 and 5 where weight sits at 99.8%, and that gap is the binding constraint 5.10 measures jointly.

*Figure — Share of visits carrying each measurement, by age band. Rendered in `index.html` at `#fig-missing-age`.*

**Implications for analysis.** Head circumference is an infant measurement and effectively disappears after age 2; BMI and its percentile are withheld below age 2 by the augmentation; height is recorded far less often than weight at every age. Any cohort defined by "has a complete measurement row" is therefore an age-selected cohort, and any model that drops incomplete rows inherits that selection. Report availability by age band before interpreting any age-stratified contrast.

### 3.5 Nulls that are not missing, and sentinels that are not data

Two of the largest null populations in this extract are not missing data at all, and reading them as missing throws away the majority of the signal in their columns.

**Laboratory result flags**

| result_flag | rows | meaning |
| --- | --- | --- |
| null | 15,550,985 | normal result |
| Abnormal | 704,327 | abnormal by the dictionary rule |
| High | 513,650 | abnormal by the dictionary rule |
| Low | 361,300 | abnormal by the dictionary rule |
| Sensitive | 62,794 | abnormal by the dictionary rule |
| Resistant | 10,278 | abnormal by the dictionary rule |
| High Panic | 9,744 | abnormal by the dictionary rule |
| (NONE) | 5,881 | normal result |
| Normal | 4,273 | abnormal by the dictionary rule |
| Panic | 3,056 | abnormal by the dictionary rule |
| Intermediate | 1,704 | abnormal by the dictionary rule |
| Low Panic | 1,406 | abnormal by the dictionary rule |
| Critical | 373 | abnormal by the dictionary rule |
| Negative | 188 | abnormal by the dictionary rule |
| High Off-Scale | 134 | abnormal by the dictionary rule |
| Susceptible-Dose Dependent | 123 | abnormal by the dictionary rule |
| Abnormal High | 99 | abnormal by the dictionary rule |
| Abnormal Low | 92 | abnormal by the dictionary rule |
| Invalid High | 84 | abnormal by the dictionary rule |
| Sig Change Up | 68 | abnormal by the dictionary rule |
| Positive | 35 | abnormal by the dictionary rule |
| Critical High | 23 | abnormal by the dictionary rule |
| Low Off-Scale | 17 | abnormal by the dictionary rule |
| Critical Low | 13 | abnormal by the dictionary rule |
| Class 0: Absent Allergen Specific IgE | — | abnormal by the dictionary rule |
| Delta Abnormal High | — | abnormal by the dictionary rule |
| Invalid Low | — | abnormal by the dictionary rule |
| Better | — | abnormal by the dictionary rule |
| Class 2: Moderate Level Allergen Specific IgE | — | abnormal by the dictionary rule |
| Delta Critical High | — | abnormal by the dictionary rule |
| In Process | — | abnormal by the dictionary rule |
| Class 3: High Level Allergen Specific IgE | — | abnormal by the dictionary rule |
| Sig Change Down | — | abnormal by the dictionary rule |
| Delta Abnormal Low | — | abnormal by the dictionary rule |
| Moderately Sensitive | — | abnormal by the dictionary rule |
| Worse | — | abnormal by the dictionary rule |

All 36 distinct values are listed. The null is one of them; 6.1 reports 35 for this column because `count(DISTINCT)` drops it.

The data dictionary defines `result_flag` as an HL7 abnormality category in which the value `(NONE)` means a normal result and anything else means abnormal. This extract contains 5,881 literal `(NONE)` values and 15,550,985 nulls — 90.3% of all lab rows, or 88.8% of the 14,947,495 that were actually resulted, which is the denominator that matters because a row with no result cannot carry a flag. The sentinel became a null somewhere between the source system and delivery, so **a null flag means normal, not unknown**. The meaning column above applies that rule and nothing else: the null and the literal `(NONE)` are the normal ones, and every other value is abnormal *by the dictionary's definition* — including the literal `Normal` and `Negative`, which are result text the HL7 category does not exempt. Where that reading matters, treat those rows as an unresolved conflict between the value and its category rather than as settled either way.

`problem_list.resolved_date_age_in_days` behaves the same way: the dictionary defines null as "problem currently active". 951,677 of 1,709,584 entries (55.7%) are null, which is a statement about 56% of problems being open, not about missing dates.

**Zero and blank values checked as possible sentinels**

| resource | field | pattern | rows |
| --- | --- | --- | --- |
| visits_augmented | height_in | zero height | 0 |
| visits_augmented | weight_oz | zero weight | 0 |
| visits_augmented | head_circ_cm | zero head circumference | — |
| labs | result_value | empty result string | 0 |
| patients | sex | blank sex | 0 |
| patients | race_1 | blank race_1 | 8,818 |
| patients | ethnicity | blank ethnicity | 5,464 |

A zero means the pattern was looked for and is absent; an em dash means it is present on fewer than 10 rows. The two are different findings and the column holds both.

**Implications for analysis.** Never impute or drop on `result_flag` or `resolved_date_age_in_days` nullity. The cost is easy to state: dividing the 1,673,815 abnormal flags by the rows that carry a flag at all gives an abnormal-result rate of 99.6%, and dividing them by the resulted rows gives 11.2%. The first is what dropping the nulls produces and it is wrong by a factor of nine. A problem-list resolution rate must count nulls as unresolved rather than excluding them, for the same reason.

### 3.6 Code systems, free text, and categorical hygiene

Diagnosis coding is almost entirely well-formed ICD-10. Of 14,714,503 filled encounter-diagnosis slots across 8,029 distinct codes, 145,992 (0.99%) do not match the ICD-10 shape; of 1,709,584 problem-list entries across 4,739 codes, 39,860 (2.33%).

**The non-conforming diagnosis values**

| value | slots |
| --- | --- |
| IMO0002 | 116,950 |
| U07.1 | 25,483 |
| IMO0001 | 3,443 |
| U09.9 | 77 |
| U07.0 | 39 |

These are proprietary placeholders the source EHR emits when a clinical term has no ICD-10 equivalent. They carry no diagnostic meaning and should be excluded from code-based cohort definitions rather than treated as unmapped diagnoses.

Laboratory results are the opposite case. `result_value` is a text column: of 17,230,681 rows, 7,621,449 (44.2%) parse as a number and 2,494,261 (14.5%) hold no value at all. Those are nulls, not empty strings — 3.5 looks for the empty string and finds none, so the two sections are measuring different things and agree. Among the rest, 487,168 are censored results carrying a comparator prefix, and the remainder are qualitative results, specimen descriptors, and administrative non-results. A LOINC code is present on 7.8% of rows, or 9.0% of the 14,947,495 that were resulted.

The key of 3.1 holds, but 33,879 order-and-component pairs appear on more than one result line and 23,679 of those (69.9%) carry disagreeing values. The data dictionary records the cause: a result may fail to link back to its original order, which duplicates the record.

**Categorical vocabularies before and after normalising case and internal whitespace**

| resource | field | distinct values | after normalising | collapsed |
| --- | --- | --- | --- | --- |
| labs | lab_procedure_name | 3,742 | 3,739 | 3 |
| medications | med_simple_generic_name | 1,073 | 1,073 | 0 |
| referrals | requested_specialty | 119 | 119 | 0 |

**Implications for analysis.** A naive numeric cast on `result_value` silently discards 7,114,971 of the 14,736,420 populated values — 48.3%, very nearly half — and turns a left-censored result into a missing one rather than a bound. Join labs on order *and* line number, which 3.1 shows is the key, rather than on order and component, or the duplicate lines will multiply rows and pick a value arbitrarily. The categorical vocabularies barely collapse under normalisation, so grouping by them is safe after trimming.

### 3.7 Capture: measurement presence is not measurement occurrence

Completeness by age says how often a column is filled. Encounter type says whether filling it could have meant a measurement.

**Measurement and diagnosis presence by encounter type**

| encounter type | visits | weight present | height present | first diagnosis |
| --- | --- | --- | --- | --- |
| Office Visit | 4,725,643 | 99.9% | 52.4% | 95.8% |
| Well Visit (Conv.) | 778,452 | 99.9% | 98.7% | 94.4% |
| Sick | 580,991 | 99.9% | 16.9% | 95.4% |
| Follow-Up | 92,370 | 99.8% | 24.9% | 93.1% |
| Walk-In | 79,679 | 99.9% | 8.7% | 96.9% |
| Consult | 32,355 | 99.9% | 53.7% | 99.6% |
| Conversion Encounter | 32,007 | 99.9% | 66.9% | 17.3% |
| Newborn | 31,142 | 99.9% | 87.5% | 99.1% |
| Telemedicine | 25,658 | 97.4% | 44.8% | 99.8% |
| Telephone | 22,053 | 99.3% | 50.1% | 34.8% |
| Weight Check | 16,295 | 99.9% | 37.7% | 96.4% |
| Clinical Support | 15,347 | 99.3% | 15.4% | 83.4% |
| Documentation | 13,107 | 98.3% | 84.4% | 8.6% |
| Immunization | 11,774 | 97.6% | 30.7% | 93.4% |
| New Patient | 11,410 | 99.9% | 79.8% | 98.1% |
| Nutrition | 5,406 | 99.8% | 73.8% | 99.5% |
| Medication Management | 4,345 | 99.9% | 75.9% | 93.3% |
| Nurse Only | 3,786 | 96.9% | 36.2% | 69.1% |
| Abstract | 3,672 | 99.4% | 83.1% | 9.0% |
| Flu | 2,104 | 96.4% | 13.7% | 99.4% |
| Lactation Consult | 1,384 | 100.0% | 11.6% | 99.7% |
| Lab | 1,351 | 97.0% | 37.3% | 78.7% |
| Lactation Encounter | 1,337 | 99.8% | 1.9% | 49.7% |
| Procedure visit | 678 | 97.8% | 56.3% | 96.0% |
| Pre-op/Pre-procedure Orders | 575 | 100.0% | 84.3% | 96.3% |
| Erroneous Encounter | 555 | 99.8% | 45.9% | 30.5% |
| Orders Only | 273 | 99.6% | 78.4% | 51.6% |
| External Contact | 211 | 100.0% | 99.5% | 2.4% |
| Patient Message | 209 | 95.7% | 30.6% | 18.2% |
| Evaluation | 143 | 99.3% | 74.1% | 94.4% |
| Lab Requisition | 63 | 96.8% | 14.3% | 90.5% |
| Scanned Document | 23 | 100.0% | 95.7% | 0.0% |
| Letter (Out) | 18 | 100.0% | 94.4% | 0.0% |
| Refill | 12 | 100.0% | 0.0% | 66.7% |
| History | 11 | 100.0% | 45.5% | 0.0% |
| Ophth Exam | 11 | 100.0% | 0.0% | 100.0% |
| Hospital | — | — | — | — |
| Routine Prenatal | — | — | — | — |
| Transcribe Orders | — | — | — | — |
| Patient Care Review | — | — | — | — |
| Episode Changes | — | — | — | — |
| Erroneous Telephone Encounter | — | — | — | — |
| ED | — | — | — | — |
| OurPractice Advisory | — | — | — | — |
| Treatment | — | — | — | — |

All 45 distinct values are listed. 9 carry too few visits to show a count.

Telephone encounters carry a weight on 99.3% of 22,053 visits, and they are not alone: 11 encounter types at which nobody could have put a child on a scale carry a weight on at least 95.7% of their visits, 65,247 in all — `Telemedicine`, `Telephone`, `Documentation`, `Abstract`, `Orders Only`, `External Contact`, `Patient Message`, `Scanned Document`, `Letter (Out)`, `Refill`, `History`. Presence does not discriminate between them and an office visit.

**One of the three explanations for that is testable, and it mostly fails.** A weight recorded at a telephone encounter was reported by a caregiver, carried from a nearby in-person encounter, or attached to an encounter whose type label does not describe how the patient was seen. The middle one predicts the value will equal a real one: 5.8% of telephone weights match an in-person weight for the same child within 7 days exactly, against 2.4% to 2.7% for in-person types where the same coincidence is just coincidence. So carrying explains a few points of excess and no more; for telemedicine, at 1.3%, it explains nothing at all. The other two remain, and those this extract genuinely cannot separate.

**Recording completeness by source system**

| encounter source | visits | height present | first diagnosis |
| --- | --- | --- | --- |
| Epic | 4,149,865 | 51.4% | 99.7% |
| converted from a legacy system | 2,344,608 | 58.7% | 86.1% |

The source-system split is the migration signal. Records converted from the practice network's previous EHR carry a first diagnosis on only 86.1% of encounters, which the data dictionary anticipates: converted encounters may be missing diagnosis information depending on the quality of the conversion. Height runs the other way — 58.7% on converted encounters against 51.4% on native ones — so the conversion is not uniformly lossy and the provenance field cannot be read as a quality score.

**Implications for analysis.** A visit-level indicator that a measurement is present is not evidence that a measurement was taken at that encounter. If your design counts measurement occasions — visit density, monitoring intensity, follow-up adherence — restrict to encounter types where physical measurement is possible rather than relying on presence, and the 11 types named above are the ones to drop first. And any diagnosis-based rate computed across the whole extract mixes two populations with very different coding completeness.

### 3.8 Same-day measurements that disagree

Section 3.1 shows that a patient-day can carry more than one visit. Where those visits each carry the same measurement, they often do not agree, and the size of the disagreement is a direct estimate of how far two records of the same child on the same day can sit apart.

**Patient-days carrying more than one value of a channel**

| channel | patient-days with 2 or more | of which they disagree | share disagreeing | median spread | 95th percentile | maximum |
| --- | --- | --- | --- | --- | --- | --- |
| height | 2,958 | 942 | 31.8% | 3.175 | 12.16 | 34.92 |
| weight | 5,319 | 2,648 | 49.8% | 0.118 | 3.64 | 36.57 |
| head circumference | 1,475 | 837 | 56.7% | 0.510 | 27.80 | 397.76 |

Spread columns are in each channel's own unit and describe only the disagreeing days, not the panel.

The height spread is the notable one. A median disagreement of 3.17 cm between two heights recorded for the same child on the same day is far larger in relative terms than the weight equivalent.

**It is not the length-to-height transition, which is the first explanation to reach for.** 4.5 locates that transition between two and three years, and mixing the two protocols on one day would concentrate the disagreements there. They are not concentrated there: 0.030% of patient-days in the transition window carry two heights that disagree, against 0.035% before it and 0.019% after. The largest group is the one the explanation cannot cover at all — 542 of the 942 disagreeing days fall under age two, where both values would have been recumbent lengths. What does change with age is the size rather than the frequency: a median of 1.91 cm under two against 6.34 cm from three, which is what a fixed relative error on a growing child looks like. A value carried from an earlier note remains a candidate; this report cannot test it.

The head-circumference row needs 4.7 beside it. Its maximum is not two people measuring differently: 30 of the 837 disagreeing days hold a value above 65 cm, which 4.7 shows is an inch-to-centimetre conversion applied twice. Among the days whose values are all plausible the median spread is 0.50 cm, and that is the number to read as a recording disagreement.

**Implications for analysis.** These days need a tie rule chosen before the analysis, not left to whatever order the query returns. Taking the minimum, the maximum, the mean, or the first row are all defensible and they give different answers; what is not defensible is not knowing which one you took. Deduplicate the patient-day before any window function, since 4.8 shows the derivation layer's own ambiguity on exactly these rows. Note that 4.5 takes the strongest rule available and drops these days from its panel entirely, which is one defensible answer and not the only one.

### 3.9 Counting diagnosis codes: ICD-10 is a hierarchy

ICD-10 is a tree, not a list. `E10` is type 1 diabetes and `E10.9` is type 1 diabetes without complications; a chart may carry either, and which one it carries is a coding decision rather than a clinical one. **A query that matches a code exactly therefore counts one node of the tree, not the concept.** This is the single most common way to undercount a diagnosis in this extract, and it fails silently — the query returns a number, just the wrong one.

The extract carries 8,963 distinct ICD-10-shaped codes across its two diagnosis resources — 2 further values are the source EHR's proprietary placeholders, which 3.6 says to exclude from code-based work and which are excluded from every figure here — of which only 123 are bare three-character categories. Rolling every code up to its category gives 1,326 categories, and **1,203 of those (90.7%) never appear as a bare code at all**. For those, an exact-match query returns zero while the condition is present.

**The undercount is all-or-nothing rather than graded**, which decides how to guard against it. Either a category never appears as a bare code, in which case a flat count returns zero and rolling up is the only way to see it at all — that is 1,203 of 1,326 — or it does appear, in which case rolling up usually adds nothing: across the 123 visible categories the subtree count is 1.00 times the literal one at the median and 1.00 at the ninetieth percentile. A handful are enormous, up to 52,206 times. So there is no safe middle where a flat count is approximately right; it is either exact or it is zero.

The effect is large enough to reorder a frequency table. Below, the six most common literal codes beside the six most common categories after rollup.

**The most common diagnoses, counted flat and rolled up**

| rank | literal code | patients | category | patients |
| --- | --- | --- | --- | --- |
| 1 | Z00.129 | 247,963 | Z00 | 250,354 |
| 2 | Z23 | 244,617 | Z23 | 244,617 |
| 3 | Z13.0 | 135,783 | Z13 | 188,758 |
| 4 | J06.9 | 134,337 | J06 | 134,368 |
| 5 | Z13.88 | 128,880 | H66 | 132,693 |
| 6 | R50.9 | 116,527 | J02 | 131,194 |

Two rankings side by side, not one: the rank column applies to each half separately, so a row pairs the nth literal code with the nth category and the two need have nothing to do with each other. Reordering is the point — read down the columns rather than across the rows.

`H66` is the clearest case. Counted literally it has 0 patients, because clinicians code the laterality-specific children instead. Counted as a subtree it has 132,693 — enough to place it among the most common conditions in the extract, where a flat count makes it invisible.

**The children a flat count misses**

| code | patients |
| --- | --- |
| H66.001 | 49,713 |
| H66.002 | 44,040 |
| H66.003 | 35,569 |
| H66.90 | 34,331 |
| H66.91 | 26,536 |

**Implications for analysis.** Match on a prefix (`code LIKE 'E10%'`) or roll up to the level you actually mean before counting, and say which level that is. Two cautions on prefixes: a code is a string, so compare against the code with its decimal point as stored, and a prefix of a prefix will over-match — `E1` is not a category. Where a frequency table is the deliverable rather than an input, report the rolled-up count and the literal one side by side, since the gap between them is itself a description of local coding practice.

## 4. Anthropometrics

The richest and most artifact-prone measurements in the extract.

### 4.1 Trajectory supply: how many heights each child has

250,267 of 250,588 patients (99.9%) carry at least one derived height, 235,594 (94.0%) carry five or more, and 181,970 (72.6%) carry ten or more.

**What is being counted.** Days, not rows, and the derived channel, not the recorded one. A patient-day can hold more than one visit (3.1), so heights are counted once per day — 2,123 patients carry a day with more than one, and counting rows would credit them with observations a design could not use. And the count is over `height_cm`, which the augmentation bounds: 17,971 recorded heights have no derived value, 9,086 patients lose at least one, and 53 carry a recorded height and no derived one at all, so they appear here at zero. 4.4 shows what the bound removes and why most of it should be removed. A curve built from `height_in` would sit slightly above this one.

*Figure — Patients retaining at least k height observations. Rendered in `index.html` at `#fig-supply`.*

**Height observations per patient**

| at least k heights | patients | share of cohort |
| --- | --- | --- |
| 1 | 250,267 | 99.9% |
| 3 | 245,438 | 97.9% |
| 5 | 235,594 | 94.0% |
| 10 | 181,970 | 72.6% |
| 15 | 104,729 | 41.8% |
| 20 | 43,326 | 17.3% |
| 25 | 15,929 | 6.4% |

One height per patient-day. The most any patient carries is 138.

**Implications for analysis.** Read this against 1.4 before treating it as a fact about pediatric care. Cohort entry required growth measurements, so a dense height series here is partly the selection rule and partly the underlying practice, and the two cannot be separated within this extract. They are not the same count, though, and the gap is worth holding: entry required five measurements **of one type** — which weight alone can satisfy — **on distinct dates spanning over 1095 days**, with the last within 400 days. This curve requires none of the span, none of the recency, and it counts one type rather than any. That is why 94% carrying five heights is not the entry rule restated. What the curve does support is a feasibility estimate: how many children remain if your design needs k observations of height.

### 4.2 Recording units and the measurement grid

Height and weight are captured in imperial units, and the metric columns are exact conversions of them — measured, not assumed. Across 3,491,662 visits carrying both a raw and a derived height, the largest disagreement with `height_in` times 2.54 is 0.0004 cm; across 6,483,007 weight pairs the largest disagreement with `weight_oz` times 0.0283495 is 0.00059 kg. Both sit inside the two-decimal rounding of the stored columns, which is why they are that small: there is no residue beyond the rounding for either channel.

The arithmetic being clean is what makes 4.4's unit findings interpretable: a value keyed in the wrong unit survives an exact conversion unchanged, so a wrong unit is a wrong *recording* and not a conversion defect. The check can only speak for rows that have a derived value, though. 17,971 of the 3,509,633 recorded heights have none, because the augmentation bounded them away, and those are exactly the clusters 4.4 identifies — so the population the warning is about is the one this check cannot see.

The recorded values are heaped on human-readable fractions, and the shares below nest rather than partition — every whole inch is also a half and a quarter inch, and every whole pound is also a whole ounce, so they are cumulative and do not sum. Of 3,509,633 heights, 80.0% fall on a quarter inch, 54.9% on a half inch and 31.0% on a whole inch. Of 6,488,028 weights, 54.4% fall on a whole ounce and 24.6% on a whole pound.

*Figure — Share of measurements falling on the coarse grid, by age. Rendered in `index.html` at `#fig-grid`.*

The two channels age in opposite directions. Height stays on its quarter-inch grid throughout childhood, while weight moves from ounce-level precision in infancy to whole pounds in adolescence, so the effective resolution of the weight channel degrades as children get older.

**Implications for analysis.** The grid, in the units the derived columns are written in: one quarter inch is 0.635 cm, one ounce is 0.0283 kg and one pound is 0.4536 kg. Those are the floors, and the weight floor is the one that moves — a channel recorded to the pound in adolescence resolves nothing finer than 0.45 kg however many decimals it is stored with. Any change smaller than roughly half the interval is not distinguishable from the rounding itself, which sets a floor on the smallest trajectory deflection that can be detected at all. Set detection thresholds at or above the grid, and state the assumed precision wherever a measurement is written out — the two decimals on `height_cm` are an honest record of an exact conversion and not a claim about the measurement, which is 0.635 cm coarse.

### 4.3 Distributions and plausibility bounds

The four measurement channels, summarised on the derived metric columns. The final two columns give the screening range each channel is checked against and how many values fall outside it; those are reported, not removed, because the decision to exclude belongs to the analysis rather than to this report.

**Measurement channels**

| channel | unit | values | min | 1st pct | median | 99th pct | max | review range | outside review range |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| height | cm | 3,491,662 | 37.47 | 48.26 | 92.71 | 173.41 | 196.60 | 30 to 200 | 0 |
| weight | kg | 6,483,007 | 0.01 | 2.81 | 14.52 | 78.65 | 513.92 | 0 to 160 | 217 |
| BMI | kg/m^2 | 1,955,339 | 8.12 | 13.29 | 16.70 | 32.42 | 219.51 | 5 to 60 | 44 |
| head circumference | cm | 1,635,690 | 0.00 | 33.00 | 44.00 | 53.00 | 505.46 | 0 to 80 | 13,742 |

The review range is a wide screening band, chosen to catch values no measurement could produce. It is not the tighter clinical band a channel may also have: 4.7 screens head circumference against 25 to 65 cm and counts more values outside it than this column does.

*Figure — Distribution of height (cm). Rendered in `index.html` at `#fig-dist-height_cm`.*

*Figure — Distribution of weight (kg). Rendered in `index.html` at `#fig-dist-weight_kg`.*

*Figure — Distribution of BMI (kg/m^2). Rendered in `index.html` at `#fig-dist-bmi`.*

*Figure — Distribution of head circumference (cm). Rendered in `index.html` at `#fig-dist-head_circ_cm`.*

**Implications for analysis.** Head circumference is the channel whose tails are worst, and 4.7 shows why — an arithmetic defect, not a measurement one. For the others the extremes are sparse but the bulk is clinically ordinary. Bound the raw imperial columns rather than the derived metric ones when screening, since a wrong unit survives an exact conversion unchanged.

### 4.4 Transcription-error signatures in the typed fields

**Method.** Each measurement is anchored by linear interpolation between the same child's previous and next measurement. Both neighbours must themselves be plausible and span no more than four years, so a bad neighbour cannot manufacture an anomaly. A height is anomalous more than 3 inches from that anchor, a weight more than 50% from it. A mechanism *reconciles* an anomaly when applying it to the recorded value lands back at the anchor — within 1 inch for height, and within the larger of 5% and 2 ounces for weight. That window is wide, deliberately, because a transcription error need not be exact; the cost is that two mechanisms can land in the same place, and the dropped-digit row below is where that happens.

**The null.** Each anomaly's anchor is replaced by the recorded value plus a deviation drawn from another anomaly in the same year-of-age band, 20 times. That preserves the distribution of deviations exactly and destroys only the arithmetic relationship between the recorded digits and the anchor, which is the thing under test. A mechanism that reconciles anomalies no more often than it reconciles these scrambled pairs has no evidence behind it, however many hits it returns.

**Height.** 7,443 anomalies in the testable interior. Mechanisms are tested one at a time and are not mutually exclusive, so the rows do not sum to the total.

**Height: mechanisms against the null**

| mechanism | reconciled | share | null | ratio |
| --- | --- | --- | --- | --- |
| height recorded in whole feet | 686 | 9.22% | 1.34% | 6.9x |
| centimetre value in the inch field | 91 | 1.22% | 0.67% | 1.8x |
| inch value where a centimetre is expected | 30 | 0.40% | 1.00% | 0.4x |
| decimal point misplaced | 11 | 0.15% | 2.80% | 0.1x |
| adjacent digit transposition | 40 | 0.54% | 0.69% | 0.8x |
| one digit omitted | 407 | 5.47% | 1.14% | 4.8x |
| one digit wrong (calibration class) | 4,024 | 54.06% | 50.15% | 1.1x |

*Figure — Height: observed against null, by mechanism. Rendered in `index.html` at `#fig-mech-h`.*

Adjacent digit transposition — the classic keying error, and the one most often assumed — reconciles fewer height anomalies than chance alone. The unit error is real and it is directional: a centimetre value in the inch field is enriched, while the arithmetically opposite reading sits at or below the null. That asymmetry is what a one-way data-entry confusion looks like; a spurious mechanism would be symmetric.

The dropped-digit row is mostly borrowed from the row above it, and it is worth showing why. Inserting a digit into a two-digit inch value always produces a three-digit one, which is never a plausible height, so the class can only fire on a value with a single-digit integer part. Among the 6,619 height anomalies whose integer part has two or more digits it reconciles 0. That leaves the short values, and there the whole-foot class has already claimed most of them: of the 407 anomalies this class reconciles, 315 are whole-foot entries too, which the one-inch window above makes almost unavoidable. What is left is 92 anomalies against a null of 37 — still enriched 2.5 times, so a dropped digit is real on this channel, but it accounts for 92 of the 7,443 anomalies rather than the 407 the row reads as. An overlapping class is not a spurious one; it is one whose headline belongs to its neighbour.

Two clusters are visible without any anchor at all. 1,371 visits record a `height_in` of 1 to 6 as an exact integer, median age 5.2 years — a height of 3 or 4 for a child three or four feet tall. And 143 record a `height_in` between 90 and 115, which read as inches is implausible and read as centimetres is an ordinary preschool stature at a median age of 3.1 years. The recording grid decides between the two readings: 35.0% of that cluster falls on the quarter-inch grid against 80.0% of all heights, so those values never passed through the inch-typing workflow.

**Weight.** 6,196 anomalies in the testable interior.

**Weight: mechanisms against the null**

| mechanism | reconciled | share | null | ratio |
| --- | --- | --- | --- | --- |
| pound value in the ounce field | 39 | 0.63% | 0.26% | 2.4x |
| ounce value where a pound is expected | 25 | 0.40% | 0.09% | 4.7x |
| kilogram value in the ounce field | 13 | 0.21% | 0.09% | 2.5x |
| gram value in the ounce field | 2 | 0.03% | 0.08% | 0.4x |
| decimal point misplaced | 1,208 | 19.50% | 1.13% | 17.2x |
| adjacent digit transposition | 77 | 1.24% | 6.65% | 0.2x |
| one digit omitted | 927 | 14.96% | 8.63% | 1.7x |
| one digit wrong (calibration class) | 795 | 12.83% | 25.39% | 0.5x |

Transposition is again below chance, so neither channel shows evidence of digit swapping. A misplaced decimal point, which the height channel does not show at all, is the dominant weight artifact: 1,208 anomalies at 17 times the null rate, the strongest enrichment against a null anywhere in this report. An ounce value has more digits than an inch value and no natural decimal point, so a factor of ten is both easy to key and hard to notice.

The dropped-digit row does **not** reduce the same way on this channel, and the height argument does not transfer: an ounce value has three or four digits, so inserting one can still land on a plausible weight. Of the 927 weight anomalies the class reconciles, 642 are claimed by no better-evidenced mechanism, against 476 expected under the null — a ratio of 1.3. The class is weaker here than the 927 in the table suggests, and weaker than the height residual, but it is not disposed of by the argument that reduces the height row.

The calibration row is why the null is not optional, and the two channels show why in opposite directions. Allowing any single digit to be wrong reconciles 54% of height anomalies against a 50% null, and 13% of weight anomalies against 25% — barely above chance on one channel and well below it on the other. Reported without a null the height row would look like the largest finding here.

**How strong is the transposition negative?** Only as strong as the share of transpositions the anomaly gate could have caught. Applying every adjacent digit swap to a sample of measurements in the testable interior gives that share directly: 69.7% of height swaps would displace a value past the gate, against 31.6% of weight swaps. The height negative is well powered; the weight negative rules out only large swaps, since a four-digit ounce value can absorb a swap without moving far.

**What the mechanisms account for**

| channel | anomalies | an enriched mechanism fits | only the calibration class | nothing beyond chance fits |
| --- | --- | --- | --- | --- |
| height | 7,443 | 869 | 4,011 | 2,563 |
| weight | 6,196 | 1,927 | 764 | 3,505 |

Only classes reconciling more than their own null count as explanations here, so the first column does not contradict the tables above. Excluded on that test: inch value where a centimetre is expected, decimal point misplaced, adjacent digit transposition for height, and gram value in the ounce field, adjacent digit transposition for weight. A row in the last column may still have had one of those fire on it; a class at chance explains nothing it happens to fit.

**Implications for analysis.** Digit transposition can be dropped from the checklist for this extract at the magnitude that displaces a measurement from its own trajectory; for weight the same test is only about a third sensitive, so a small swap is not ruled out. Unit confusion and decimal placement do matter, and both are cheap to screen because both produce values implausible on their face. Bound `height_in` and `weight_oz` before any conversion, and check the recording grid rather than the value alone — the grid separates a tall adolescent from a centimetre in the wrong field where magnitude cannot. Note also that 1,371 of the whole-foot entries and 143 of the centimetre cluster already carry a null `height_cm` — every value in both clusters: the derived layer's own bound removes them as a side effect, so anyone reading the derived channels is protected and anyone reading the raw ones is not.

### 4.5 Repeated measurements: zero growth and apparent height loss

Children do not shrink, so a recorded decrease is recording behaviour rather than physiology. That much is easy. What matters is that the behaviour is not one thing, and the interval between measurements separates the mechanisms.

**What the panel is.** A pair is one child's height on two different days. Of the 3,488,671 patient-days carrying a height, 942 are excluded before any pair is formed, because they carry two heights that disagree and there is no single value to difference — the same days 3.8 measures, and the largest same-day disagreements in the extract. 2,016 days carrying duplicate rows that agree are kept. The exclusion is small but it is not neutral for this section in particular: it removes the days where the record already contradicts itself about a child's height.

**Repeat height pairs at age 2 or later, by interval**

| interval | pairs | exactly zero change | any decrease | median loss |
| --- | --- | --- | --- | --- |
| up to 7 days | 25,968 | 47.86% | 21.31% | 0.69 cm |
| 8 to 30 days | 82,652 | 32.00% | 19.03% | 0.64 cm |
| 31 to 90 days | 170,521 | 16.38% | 10.51% | 0.64 cm |
| 91 to 180 days | 205,153 | 5.15% | 4.22% | 0.81 cm |
| 181 to 365 days | 368,248 | 1.57% | 1.44% | 0.79 cm |
| over 365 days | 893,691 | 0.64% | 0.66% | 0.64 cm |

At short intervals a child genuinely has not grown a measurable amount and the quarter-inch grid absorbs the rest. At long intervals both effects should vanish, and they do not entirely. The residue is small and its median size is about one grid step of 0.635 cm, which is the first clue that it is rounding rather than error.

Holding the interval fixed and varying age identifies the mechanisms directly.

*Figure — Apparent height loss by age, over 181-365 day intervals. Rendered in `index.html` at `#fig-loss-age`.*

**Apparent loss by age at the earlier measurement**

| age band (months) | pairs | any decrease | median loss, decreasing pairs | mean change, all pairs |
| --- | --- | --- | --- | --- |
| 18-24 | 63,685 | 0.53% | 1.27 cm | 5.51 cm |
| 24-30 | 52,826 | 1.21% | 0.99 cm | 5.20 cm |
| 30-36 | 19,242 | 3.65% | 1.25 cm | 3.75 cm |
| 36-42 | 32,650 | 0.44% | 1.63 cm | 6.19 cm |
| 42-48 | 4,512 | 0.64% | 1.27 cm | 4.90 cm |
| 48-60 | 37,302 | 0.37% | 1.91 cm | 5.68 cm |
| 60-84 | 64,090 | 0.33% | 1.92 cm | 5.14 cm |
| 84-120 | 76,194 | 0.36% | 1.60 cm | 4.70 cm |
| 120-144 | 37,388 | 0.47% | 1.25 cm | 4.87 cm |
| 144-168 | 26,514 | 2.78% | 0.64 cm | 4.04 cm |
| 168-192 | 14,518 | 11.39% | 0.64 cm | 1.79 cm |
| 192-216 | 2,566 | 23.69% | 0.64 cm | 0.54 cm |

Interval held to 181-365 days throughout. This table drops the age-2 floor the interval table above applies, deliberately: the first mechanism sits on the boundary itself, so the bands either side of it have to be visible. Bands carrying fewer than 50 pairs are omitted, and no band falls below it here. The last two columns have different denominators, as their labels say — a median over the pairs that decreased, a mean over every pair — so they are not two summaries of one distribution. Read the rate column with the pairs column beside it: the supply is uneven, from 76,194 pairs down to 2,566 in the 192-216 band, so the points on that curve are not equally precise.

Two separate excesses, with different signatures. The first is a narrow spike at 30 to 36 months, and it is the *rate* that marks it: 3.65% of pairs decrease there, against 1.21% in the band before and 0.44% in the band after. The median loss does not mark it at all — 1.25 cm in the spike against 1.63 cm immediately after it, and larger still through mid-childhood — so a reader scanning that column would miss the excess entirely. It is the age at which recumbent length gives way to standing height, and a standing height genuinely is shorter than a recumbent length for the same child: a change of measurement protocol recorded in a field that does not name the protocol.

*Figure — Apparent loss in adolescence, by sex. Rendered in `index.html` at `#fig-loss-sex`.*

**Adolescent bands split by recorded sex**

| age band (months) | female pairs | female decrease | female mean change | male pairs | male decrease | male mean change |
| --- | --- | --- | --- | --- | --- | --- |
| 144-168 | 12,858 | 5.29% | 2.53 cm | 13,656 | 0.41% | 5.46 cm |
| 168-192 | 7,127 | 18.59% | 0.70 cm | 7,391 | 4.45% | 2.83 cm |
| 192-216 | 1,346 | 28.83% | 0.22 cm | 1,220 | 18.03% | 0.89 cm |

The second excess is the adolescent rise, and the sex split identifies it. Girls reach the high rates about two years before boys, in the same order as growth cessation, while the mean change over the same interval falls towards zero. Once annual growth drops below the recording grid, re-measuring a child returns a lower value more and more often — 23.7% by 192-216 months, against a third of a percent in mid-childhood — and would approach one time in two for a child who had stopped growing entirely, which is a limit this panel does not reach. Restricting to ages 2 to 10, where growth is unambiguously ongoing, collapses the long-interval decrease rate from 0.663% to 0.083% — 565 pairs of 681,114.

A decrease of more than a centimetre over more than a year is larger than one grid step, so it is the part of the panel least easily explained by rounding. It is not a residue, though, and calling it one would overstate it: of the 1,188 such decreases with a further measurement after them, 765 (64%) sit at 144 months or later — inside the adolescent flattening just described — and only 345 (29%) fall in the ages 2 to 10 where growth is unambiguously ongoing. What follows is a statement about large long-interval decreases, not about what the two mechanisms leave behind.

They divide anyway. 684 (57.6%) are followed by a value back at or above the earlier level and 504 (42.4%) by one that stays below it. In the first the low value is the suspect; in the second it is corroborated and the earlier, higher measurement is the candidate error. Allowing 0.5 cm of slack below the earlier level — less than one grid step, so it is a choice rather than a rounding allowance — raises the first group to 725 and drops the persisting share to 39.0%.

**Implications for analysis.** Most apparent shrinkage here is not error and should not be filtered as an outlier: it is the recording grid acting on a flattened trajectory, plus a protocol change at two to three years. A synthetic or smoothed trajectory that lacks both will not resemble this panel. Where a decrease does need adjudication, 42% of long-interval losses over a centimetre persist into the next measurement, so a rule that always discards the lower value is wrong on that share.

### 4.6 Derived z-scores and percentiles: bounds and saturation

The derived channels are not a neutral restatement of the measurements. Each carries its own support, and they do not share one.

**Z-score channels**

| channel | values | minimum | maximum | beyond \|5\| |
| --- | --- | --- | --- | --- |
| height z | 3,491,616 | -4.9992 | 3.0000 | 0 |
| weight z | 6,482,932 | -4.9991 | 4.9995 | 0 |
| BMI z | 1,955,337 | -18.7803 | 6.7026 | 400 |
| head circ z | 1,635,640 | -17,485.9110 | 306,212.6000 | 16,663 |
| weight-for-length z | 2,027,317 | -145.6016 | 7.6285 | 1,123 |
| weight-for-stature z | 1,371,347 | -14.3445 | 7.4762 | 246 |

**Two of these channels are clamped, and one of them twice.** Height z and weight z both stop a ten-thousandth short of ±5 — height at -4.9992, weight at -4.9991 and 4.9995 — and the `beyond` column is 0 for each, which is a bound rather than a tail that happens to end. Height is then clamped again, far tighter, on one side only: at exactly 3.00. So the asymmetry that exposes it is between two bounds, not between a bound and a free tail.

The upper truncation leaves no pile-up at the boundary, so it is invisible in a summary: only 21 visits sit at or above +3. The tails are what give it away. Below, 9,637 of the 21,248 visits beyond -2.5 continue past -3 — 45.4%. Above, 34,732 visits sit beyond +2.5, so at the same rate roughly 15,800 of them would carry on past +3 rather than the 21 that do.

*Figure — Height z-score, both tails. Rendered in `index.html` at `#fig-hz`.*

**Percentile channels and their saturation points**

| channel | values | exactly 0 | share | exactly 100 | share |
| --- | --- | --- | --- | --- | --- |
| height | 3,491,616 | 2,801 | 0.080% | 0 | 0.000% |
| weight | 6,482,932 | 3,584 | 0.055% | 5,221 | 0.081% |
| BMI | 1,955,337 | 1,599 | 0.082% | 1,590 | 0.081% |
| head circumference | 1,635,640 | 3,623 | 0.222% | 15,897 | 0.972% |
| weight-for-length | 2,027,317 | 6,151 | 0.303% | 1,203 | 0.059% |
| weight-for-stature | 1,371,347 | 1,509 | 0.110% | 856 | 0.062% |

The height row is the truncation again, one transform along. A z of 3 is the 99.87th percentile, so a channel bounded there cannot reach 100 — and it does not, on any of its 3,491,616 values, against 5,221 for weight. The bound propagates, which is the clearest evidence that it is a property of the derivation and not of how the z was summarised. Head circumference is listed here for completeness; its percentile inherits the defect 4.7 measures in its z, so its saturation counts describe that defect rather than the children.

**Four channels carry mass the reference cannot produce**, counted in the `beyond` column above: head circ (16,663), weight-for-length (1,123), BMI (400), weight-for-stature (246). 4.7 takes up head circumference, where the cause is known and most of it is repairable. The other 3 are not explained anywhere in this report. Their extremes are reported so that a model consuming them does so knowingly; no mechanism has been established for them here.

**Implications for analysis.** The height channel cannot support any question about tall stature: its upper tail is absent, and a trajectory approaching the bound from below is distorted too. The percentile channels carry point masses at exactly 0 and 100 that are saturated rather than measured, so they are not continuous and should not be modelled as such. Because the 6 z channels do not share a support, a model consuming several of them together inherits the inconsistency silently. Recomputing from the raw measurement against a stated reference avoids most of this — but not for head circumference, where 4.7 shows the z transform is defective independently of the measurement, so recomputation is necessary there and not sufficient.

### 4.7 Head circumference: a recoverable conversion defect

15,025 visits carry a head circumference outside the conventional review range of 25 to 65 cm. Read as a distribution that looks like a badly behaved channel. Read as clusters, it looks like arithmetic.

**Head-circumference values by band**

| band | visits | median | minimum | maximum |
| --- | --- | --- | --- | --- |
| below 10 cm | 174 | 4.10 cm | 0.00 cm | 9.65 cm |
| 10 to under 25 cm | 943 | 18.00 cm | 10.00 cm | 24.77 cm |
| 25 to 65 cm (within review range) | 1,620,665 | 44.00 cm | 25.00 cm | 65.00 cm |
| over 65 to 200 cm | 13,472 | 110.49 cm | 65.50 cm | 193.04 cm |
| above 200 cm | 436 | 252.22 cm | 202.57 cm | 505.46 cm |

*Figure — Where head-circumference values fall. Rendered in `index.html` at `#fig-hc-bands`.*

The cluster between 65 and 200 cm is not noise. It holds 13,472 visits, and 13,467 of them — 99.96% — fall back inside the review range when divided by 2.54, with a median of 43.5 cm. That is an ordinary infant head circumference. These are centimetre values that were put through an inch-to-centimetre conversion a second time. A further 436 visits sit above 200 cm, of which 356 become plausible after dividing by 2.54 twice, consistent with the same conversion applied again.

This one defect explains most of the damage. Of 16,663 visits with an absolute head-circumference z-score above 5, 14,899 (89.4%) sit on a measurement outside the review range, and the double-converted cluster alone accounts for 13,467 of them. The remaining 1,764 visits carry a plausible measurement and still produce an extreme z, so the z transform is independently defective and repairing the units would not fully fix the channel. That is why 4.6 shows this channel with a maximum no measurement could produce.

**Implications for analysis.** A declared plausible range deletes all 15,025 out-of-range values, but 13,467 of those (89.6%) are ordinary infant measurements that one documented division restores. Repairing before bounding is strictly better than bounding alone, and it recovers most of the only measurement channel whose declared range removes a non-trivial share of values. The derived z-score is a separate matter: it stays unusable on 1,764 visits even after the units are fixed, so recompute it from the repaired measurement rather than consuming it as distributed.

### 4.8 The distributed delta and velocity fields

The augmented visit layer distributes `delta_height_cm`, `delta_weight_kg`, their two interval columns, and the velocity fields derived from them. These are **not** a lag over successive measurements, and reading them as one is the error this subsection exists to prevent. For each measurement the pipeline walks backwards to the most recent earlier measurement whose age gap meets an age-dependent minimum, skipping every measurement in between.

**Height and weight do not share a rule.** The minimum interval is shorter for weight in every band, which makes sense of a channel measured at nearly every visit, and it means the height rule carried across to the weight columns recovers the interval on 1,671,865 of 5,754,032 rows — 29%, against the 100% its own rule reaches.

**The interval rule for each channel, and what pins it**

| age band | height minimum | shortest height gap seen | weight minimum | shortest weight gap seen |
| --- | --- | --- | --- | --- |
| birth to 12 months | 90 days | 90 days | 30 days | 30 days |
| 1 to 2 years | 180 days | 180 days | 90 days | 90 days |
| 2 to 12 years | 335 days | 335 days | 180 days | 180 days |
| 13 years and over | 180 days | 180 days | 180 days | 180 days |

The rules were recovered rather than documented, so the evidence is beside them: inside each band the shortest interval the pipeline ever emits is exactly the minimum, which pins the floor from below. A floor the data never reach would not be identified at all, and none here is.

Two features of the table are worth stating before the check, because both look like errors and neither is. The height minimum rises to 335 days through mid-childhood and then falls back to 180 from 13, so adolescent velocities are computed over roughly half the window that mid-childhood ones are — the reversal is the pipeline's, not a transcription slip here. And the boundaries are identified only to the nearest interval the data actually contain: a rule stated in days is confirmed by reproduction, not by having excluded every neighbouring value.

Applying each rule reproduces that channel's fields. The recomputed age gap matches the distributed one on every row of both channels, and the population is not a subset chosen to make that true: the rule finds an earlier measurement for every row the pipeline gave a delta to, and for no other.

**Reproducing each channel, by what a recomputation starts from**

| channel | rows with a delta | interval matches | delta matches | velocity, from the measurement | velocity, from the published columns | delta under a naive lag |
| --- | --- | --- | --- | --- | --- | --- |
| height (cm) | 2,786,770 | 100.00% | 99.988% | 99.68% | 72.3% | 43.7% |
| weight (kg) | 5,754,032 | 100.00% | 99.987% | 99.67% | 53.1% | 36.4% |

Deltas match within one hundredth of a unit. The last column is the reading this section exists to rule out — a difference over successive measurement-bearing visits.

*Figure — The most common recorded measurement intervals. Rendered in `index.html` at `#fig-delta-gap`.*

**The two published columns do not regenerate the third.** A reader holds `delta_height_cm` and `delta_age_in_days_height`, not the measurement behind them, and dividing one by the other recovers 2,015,006 of 2,786,770 velocities — 72.3%, against 99.68% when the unrounded difference is taken from `height_cm` instead. The delta is published rounded to two decimals and the velocity is not computed from the rounded value. Weight behaves the same way, at 53.1%. So the interval rule alone is not enough to recompute a velocity: the unrounded difference is needed too, and it is not distributed.

**The year is 365 days, not 365.25.** Ages elsewhere in this extract convert at 365.25 and 5.8 says so explicitly; the velocity does not. The constant is worth more than a footnote because it is not recoverable by inspection — using 365.25 on the published columns drops the match from 72.3% to 40.1%, which is far enough from either figure to look like a different definition rather than a rounding choice.

Three residuals, and they are different in kind. 372,482 height rows differ from the recomputed delta by exactly one hundredth of a centimetre and are *inside* the matching tolerance above, because the pipeline rounds half to even while this check rounds half away from zero; heights come from a quarter-inch grid, so exact halfway cases are common rather than rare. 338 rows (0.012%) fall outside it, and every one of them sits on a patient-day carrying more than one height, where which earlier value was used is ambiguous; 3.8 measures how far those pairs sit apart. The third is the velocity's own: 8,801 rows fail the velocity check and 8,463 of them (96%) have a delta that matched, so the velocity residual is very nearly disjoint from the delta residual rather than a consequence of it.

**The velocity z-scores are a family of four, and the choice between them is not free.** The layer publishes the height velocity against 4 different pubertal-onset references, each with a matching percentile column, and nothing else in this report validates them.

**The height-velocity z-score references**

| reference | column | values |
| --- | --- | --- |
| no pubertal onset | `height_velocity_z_score` | 1,127,289 |
| earlier pubertal onset | `height_velocity_z_score_ep` | 977,101 |
| average pubertal onset | `height_velocity_z_score_ap` | 960,949 |
| later pubertal onset | `height_velocity_z_score_lp` | 961,074 |

Each has a `height_velocity_percentile` twin with the same population.

On the 960,949 visits carrying all three pubertal variants, the spread between the highest and lowest is a median of 0.89 z and 2.63 at the 95th percentile — larger than most contrasts this report measures, for the same child at the same visit. A further 1,659,481 visits carry a velocity with no velocity z-score at all. Which reference a result was computed against therefore has to be stated, and results computed against different ones cannot be pooled.

**Implications for analysis.** The delta and interval channels are usable as distributed, which a distributional summary alone could not establish. What must travel with them is the whole definition, and it has four parts: the channel's own interval rule, the 365-day year, the fact that the velocity divides the *unrounded* difference rather than the published delta, and the rounding of both to two decimals. Carry fewer than four and a recomputation disagrees — by a little if the rounding is missed, by a quarter of the rows if the published delta is divided, by more if the year is wrong. A velocity here is computed over an interval of at least 90 to 335 days depending on age and channel, not between adjacent visits, so it is already smoothed relative to a visit-to-visit rate and cannot be compared with one. Any synthetic series carrying a velocity must use the same rule or the two are not on the same scale. For the velocity z-scores, pick a pubertal-onset reference deliberately and say which.

### 4.9 Age- and sex-stratified growth profile

A reference table for anyone who needs to know what ordinary looks like in this extract before deciding what is unusual. Mean height z-scores run from -0.00 to 0.36 across the age and sex cells and mean weight z-scores from -0.17 to 0.65, so the cohort sits close to the reference population on average — a little heavier for its age than it is tall, and further from the reference on weight than on height — even though it is not a sample of one.

**Measurements and derived z-scores by age band and sex**

| age band (years) | sex | visits | patients | mean height | mean height z | height z SD | mean weight z | mean BMI z |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0-2 | F | 1,294,946 | 95,419 | 66.3 cm | 0.363 | 1.002 | -0.144 | — |
| 0-2 | M | 1,397,984 | 99,226 | 68.0 cm | 0.341 | 0.992 | -0.167 | — |
| 2-5 | F | 677,359 | 92,851 | 96.0 cm | 0.354 | 0.974 | 0.285 | 0.150 |
| 2-5 | M | 716,626 | 96,604 | 97.3 cm | 0.338 | 0.995 | 0.369 | 0.148 |
| 5-10 | F | 745,589 | 82,246 | 122.5 cm | 0.119 | 0.981 | 0.362 | 0.418 |
| 5-10 | M | 784,028 | 85,364 | 123.6 cm | 0.208 | 0.989 | 0.451 | 0.428 |
| 10-15 | F | 366,624 | 50,775 | 151.9 cm | 0.218 | 0.993 | 0.489 | 0.451 |
| 10-15 | M | 375,601 | 52,556 | 152.7 cm | 0.312 | 1.012 | 0.575 | 0.475 |
| 15-18 | F | 72,447 | 17,530 | 162.5 cm | -0.000 | 0.991 | 0.452 | 0.453 |
| 15-18 | M | 63,194 | 18,049 | 173.9 cm | 0.147 | 0.950 | 0.646 | 0.476 |

*Figure — Mean height z-score by age band and sex. Rendered in `index.html` at `#fig-profile`.*

**Implications for analysis.** Read the height-z column against 4.6 before using it: its upper tail is truncated at +3, so every mean here is pulled very slightly downward relative to an untruncated reference, and the effect grows in the bands where tall children are most numerous. The SD column is the more useful one for scaling, and it is close to 1 by construction of the z transform rather than as a finding.

### 4.10 Within-child dependence in the height channel

Repeated measurements of one child are not independent observations, and the size of that dependence decides how much information a visit count actually carries. Measured on the height z-score at age 2 or later — the boundary 5.8 justifies from the reference standard, and the one 4.5 and 4.9 also use — across 199,717 patients carrying 1,944,348 values between them, one per patient-day, with at least two each.

**Variance components and serial correlation**

| quantity | value | what it says |
| --- | --- | --- |
| between-child SD of patient means | 0.9140 | how far children sit from one another |
| within-child SD about a patient's own mean | 0.4253 | how much one child's channel moves |
| implied intraclass correlation | 0.8220 | share of variance that is between children |
| lag-1 autocorrelation | 0.9249 | correlation of successive values, 1,744,631 pairs |

Every row is measured on the same 1,944,348 values. The within-child SD is the root mean square of the per-patient SDs, which weights a child with two values like a child with forty; pooling by degrees of freedom instead gives 0.4112 and an intraclass correlation of 0.8316.

A child's height z-score is strongly self-similar: successive values correlate at 0.925, and 82.2% of the total variance is between children rather than within them. The design-effect consequence is blunt: where the dependence is a persistent difference between children, a child contributes about 1.2 independent observations in the limit of many measurements, not one per visit, however many visits are recorded. The two weightings above bracket that at 1.20 to 1.22, so the figure is not sensitive to the choice.

**Which dependence, though.** 1.2 is the limit for a persistent between-child level; it is not what the lag-1 correlation alone would imply. A purely serial process with no between-child component keeps accumulating information as a series lengthens, however high its lag-1 correlation, so the two rows of this table are not two measurements of the same thing and the limit follows from the variance split rather than from 0.925.

**Implications for analysis.** Resample and model at the patient level, not the visit level: a visit-level standard error on any quantity aggregated across this panel will be far too small. And treat these as sample statistics rather than the parameters of a process that would generate them — a patient's mean carries residual variation as well as the child's own level, so the between-child SD of patient means overstates the underlying channel SD, while the sample SD within a positively autocorrelated series understates its marginal SD. Both biases raise the intraclass correlation, so they lower 1.2: read it as a floor on what a child contributes rather than an estimate of it. Calibrate a generative model against these by simulation rather than by setting its parameters equal to them.

### 4.11 BMI: recomputation and recorded categories

BMI is the one derived channel that can be checked against its own inputs, and both halves of it check out. Across 1,955,339 visits carrying a BMI together with both a weight and a height, recomputing weight in kilograms over height in metres squared differs from the distributed value by a median of 9.7e-07 and never by more than 2.5e-05 — floating-point noise, nothing more. The channel is internally consistent, so a BMI here disagreeing with your own calculation means you used a different height or weight, not that the field is wrong.

The recorded category is the other half, and it is a coarsening of `bmi_percentile` rather than an independent judgement. Its boundaries are not documented in the extract, so they are read off the data below and then applied back to it: cutting the percentile at 5, 85 and 95 reproduces the distributed category on every one of the 1,955,337 categorised rows. The cut points are the conventional pediatric ones, and they are now checked rather than assumed.

**Recorded BMI categories**

| category | bmi_percentile | visits | share of categorised visits | patients ever in it |
| --- | --- | --- | --- | --- |
| underweight | 0.00 to 4.99 | 83,602 | 4.3% | 33,608 |
| normal | 5.00 to 84.99 | 1,338,418 | 68.4% | 193,723 |
| overweight | 85.00 to 94.99 | 280,226 | 14.3% | 84,669 |
| obese | 95.00 to 100.00 | 253,091 | 12.9% | 49,998 |

The last column does not partition the cohort: a child's category moves across childhood, so a patient is counted in every category they ever record. The four values sum to 361,998 over the 213,053 patients who carry any category at all.

*Figure — Distribution of recorded BMI categories. Rendered in `index.html` at `#fig-bmi-cat`.*

The category is present only where a BMI percentile is, which 1.3 and 3.4 show means age 2 or later — 2 visits carry a BMI with neither, which is why this table's total is 1,955,337 against the 1,955,339 above.

**Implications for analysis.** This is a distribution over recorded visits, not a prevalence: children with more visits contribute more rows, BMI is missing selectively by age and encounter type, and 1.4 shows the cohort is not a population sample. Aggregate to the patient before quoting any proportion, and note that the patient column here cannot be aggregated that way — it counts children ever in a category, so a proportion needs a category at a stated age or over a stated window, which is a choice this report does not make for you. State the age window, and prefer the continuous percentile to the category where the analysis allows it: the cut points above are the whole of what the category knows, so it discards everything between them.

## 5. Clinical domains and cross-resource structure

Diagnoses, laboratory results, medications, referrals, and demographics, then how they line up against each other. From 5.9 the part turns to the question the extract was built around — identifying abnormal growth early — and audits the label that question implies. 0.1 says why a project-neutral report works one question through.

### 5.1 Diagnoses

Diagnoses arrive two ways: up to 33 coded slots per encounter, and a problem list that is not visit-linked (3.2). 14,714,503 encounter slots are filled across 250,563 patients, and 6,154,801 visits (94.8%) carry at least a first diagnosis. The patient total is not the cohort: 25 children carry no encounter diagnosis anywhere in the extract.

*Figure — Coded diagnoses per visit. Rendered in `index.html` at `#fig-dx-slots`.*

**Most frequently recorded encounter diagnoses**

| ICD-10 | description | slots | patients |
| --- | --- | --- | --- |
| Z00.129 | Encounter for routine child health examination without abnormal findings | 2,494,658 | 247,896 |
| Z23 | Encounter for immunization | 1,438,556 | 244,583 |
| J06.9 | Acute upper respiratory infection, unspecified | 363,785 | 132,869 |
| J02.9 | Acute pharyngitis, unspecified | 323,876 | 113,944 |
| Z13.88 | Encounter for screening for disorder due to exposure to contaminants | 295,071 | 128,827 |
| Z13.0 | Encounter for screening for diseases of the blood and blood-forming organs and certain disorders involving the immune mechanism | 292,612 | 135,760 |
| R50.9 | Fever, unspecified | 265,363 | 115,401 |
| Z71.3 | Dietary counseling and surveillance | 230,303 | 81,930 |
| Z71.82 | Exercise counseling | 209,541 | 78,003 |
| R05.9 | Cough, unspecified | 199,083 | 91,945 |
| Z00.121 | Encounter for routine child health examination with abnormal findings | 163,509 | 72,084 |
| Z20.822 | Contact with and (suspected) exposure to COVID-19 | 160,041 | 65,268 |
| J02.0 | Streptococcal pharyngitis | 129,310 | 71,029 |
| B34.9 | Viral infection, unspecified | 125,662 | 68,886 |
| Z00.110 | Health examination for newborn under 8 days old | 124,627 | 105,062 |
| IMO0002 | [not in the ICD-10 lookup] | 116,950 | 42,737 |
| F90.2 | Attention-deficit hyperactivity disorder, combined type | 112,292 | 15,694 |
| Z29.3 | Encounter for prophylactic fluoride administration | 107,178 | 52,897 |
| Z68.53 | Body mass index [BMI] pediatric, 85th percentile to less than 95th percentile for age | 105,889 | 52,088 |
| J45.20 | Mild intermittent asthma, uncomplicated | 93,013 | 24,479 |
| R21 | Rash and other nonspecific skin eruption | 92,028 | 62,699 |
| K21.9 | Gastro-esophageal reflux disease without esophagitis | 90,172 | 31,748 |
| F41.9 | Anxiety disorder, unspecified | 81,476 | 24,519 |
| K59.00 | Constipation, unspecified | 80,647 | 39,182 |
| H66.001 | Acute suppurative otitis media without spontaneous rupture of ear drum, right ear | 76,772 | 49,374 |

The 25 most frequent of 8,029 distinct values, covering 52.8% of filled slots; the remaining 8,004 values hold the rest. Every count here is a recorded frequency within a selected cohort. Patients carrying any code that occurred fewer than 11 times were removed before delivery (1.4), so rare entries are absent by construction and nothing in this table is a population rate.

The problem list holds 1,709,584 entries for 238,823 patients, of which 44.3% of entries carry a resolved age. There is exactly one entry per patient and code — the entry count and the patient count in the table below are identical on every row for that reason, not by coincidence — so the problem list cannot say that a condition recurred, and an entry count over it is a patient count. As 3.5 shows, the remainder are open problems rather than missing dates.

**Most frequently recorded problem-list diagnoses**

| ICD-10 | description | entries | patients |
| --- | --- | --- | --- |
| U07.1 | COVID-19 | 26,260 | 26,260 |
| Z28.21 | Immunization not carried out because of patient refusal | 21,189 | 21,189 |
| F41.9 | Anxiety disorder, unspecified | 20,950 | 20,950 |
| K59.00 | Constipation, unspecified | 17,491 | 17,491 |
| Z00.129 | Encounter for routine child health examination without abnormal findings | 17,348 | 17,348 |
| K21.9 | Gastro-esophageal reflux disease without esophagitis | 17,184 | 17,184 |
| Z86.16 | Personal history of COVID-19 | 16,007 | 16,007 |
| J45.20 | Mild intermittent asthma, uncomplicated | 15,088 | 15,088 |
| L30.9 | Dermatitis, unspecified | 14,868 | 14,868 |
| R46.89 | Other symptoms and signs involving appearance and behavior | 14,789 | 14,789 |
| F80.9 | Developmental disorder of speech and language, unspecified | 13,661 | 13,661 |
| F80.1 | Expressive language disorder | 13,650 | 13,650 |
| L20.83 | Infantile (acute) (chronic) eczema | 13,282 | 13,282 |
| F90.2 | Attention-deficit hyperactivity disorder, combined type | 12,918 | 12,918 |
| IMO0002 | [not in the ICD-10 lookup] | 12,915 | 12,915 |
| R62.51 | Failure to thrive (child) | 12,503 | 12,503 |
| J30.9 | Allergic rhinitis, unspecified | 11,383 | 11,383 |
| Z91.018 | Allergy to other foods | 11,308 | 11,308 |
| J06.9 | Acute upper respiratory infection, unspecified | 11,197 | 11,197 |
| B08.1 | Molluscum contagiosum | 10,781 | 10,781 |
| Z38.00 | Single liveborn infant, delivered vaginally | 10,304 | 10,304 |
| R63.39 | Other feeding difficulties | 10,088 | 10,088 |
| R01.1 | Cardiac murmur, unspecified | 10,081 | 10,081 |
| G47.9 | Sleep disorder, unspecified | 9,772 | 9,772 |
| J45.909 | Unspecified asthma, uncomplicated | 9,502 | 9,502 |

The 25 most frequent of 4,739 distinct values, covering 20.7% of entries; the remaining 4,714 values hold the rest.

**Both tables above count literal codes**, which is the right unit for describing what gets typed but the wrong one for counting a condition. Rolling the same data up to the three-character category changes which diagnoses appear at all — see 3.9, and note that 1,203 of the 1,326 categories in this extract never appear as a bare code, so an exact-match query for them returns zero. The two tables above keep the source EHR's proprietary placeholders because they describe what gets typed; the rollup below drops them, because a placeholder has no category to roll up to and 3.6 says to exclude it from code-based work.

**The same diagnoses rolled up to their ICD-10 category**

| category | description | patients |
| --- | --- | --- |
| Z00 | Encounter for general examination without complaint, suspected or reported diagnosis | 250,354 |
| Z23 | Encounter for immunization | 244,617 |
| Z13 | Encounter for screening for other diseases and disorders | 188,758 |
| J06 | Acute upper respiratory infections of multiple and unspecified sites | 134,368 |
| H66 | Suppurative and unspecified otitis media | 132,693 |
| J02 | Acute pharyngitis | 131,194 |
| R50 | Fever of other and unknown origin | 119,263 |
| R05 | Cough | 115,563 |
| Z71 | Persons encountering health services for other counseling and medical advice, not elsewhere classified | 99,130 |
| Z20 | Contact with and (suspected) exposure to communicable diseases | 78,217 |
| R63 | Symptoms and signs concerning food and fluid intake | 76,097 |
| B34 | Viral infection of unspecified site | 74,947 |
| H10 | Conjunctivitis | 74,858 |
| Z68 | Body mass index [BMI] | 64,527 |
| R21 | Rash and other nonspecific skin eruption | 63,738 |
| P92 | Feeding problems of newborn | 62,842 |
| Z29 | Encounter for other prophylactic measures | 61,612 |
| K59 | Other functional intestinal disorders | 57,481 |
| H65 | Nonsuppurative otitis media | 57,167 |
| L20 | Atopic dermatitis | 52,206 |
| R09 | Other symptoms and signs involving the circulatory and respiratory system | 51,549 |
| J30 | Vasomotor and allergic rhinitis | 48,747 |
| R06 | Abnormalities of breathing | 48,551 |
| Z28 | Immunization not carried out and underimmunization status | 47,456 |
| J18 | Pneumonia, unspecified organism | 45,528 |

The 25 most frequent of 1,326 distinct values; 1,301 more are not shown.

**Implications for analysis.** Encounter diagnoses and problem-list entries answer different questions and should not be pooled without saying why: the first is what was coded at a contact, the second is what the chart asserts about the child, including resolved history. Neither is an adjudicated clinical truth, and a code's absence is not evidence a condition was absent.

### 5.2 Laboratory results

17,230,681 rows across 6,578,838 lab orders for 247,271 patients, of which 14,947,495 are resulted components. The other 2,283,186 are orders that produced no result and still occupy one row each, so a row is not a component and 2.6 rows per order is not a count of results: 4,295,652 orders returned anything at all, at 3.5 components each. The grain is the component, not the order, which is the single most common source of double counting in this resource.

**Most frequently ordered lab procedures**

| procedure | rows | patients |
| --- | --- | --- |
| CBC | 2,742,117 | 65,688 |
| CBC  DIFFERENTIAL | 1,660,900 | 65,105 |
| CE EXTERNAL LAB | 1,455,867 | 152,867 |
| URINALYSIS | 1,326,746 | 46,480 |
| POCT URINALYSIS DIPSTICK | 1,079,426 | 54,102 |
| COMPREHENSIVE METABOLIC PANEL | 475,461 | 28,764 |
| POCT COVID-19 NUCLEIC ACID (AMPLIFIED PROBE) | 432,267 | 80,837 |
| LEAD, BLOOD | 394,009 | 93,596 |
| COVID-19 (CORONAVIRUS 2019) PCR | 392,834 | 97,191 |
| POCT STREP A NUCLEIC ACID (AMPLIFIED PROBE) | 314,977 | 75,754 |
| POCT CBC WITH DIFF | 303,486 | 15,309 |
| POCT INFLUENZA A/B NUCLEIC ACID (AMPLIFIED PROBE) | 272,419 | 48,609 |
| POCT RAPID STREP A IMMUNOASSAY | 268,011 | 69,548 |
| POCT COVID-19, INFLUENZA, AND RSV NUCLEIC ACID (AMPLIFIED PROBE) | 267,208 | 22,586 |
| URINE CULTURE | 214,567 | 43,877 |
| POCT HEMOGLOBIN | 193,586 | 86,845 |
| RAPID STREP A, IMMUNOASSAY | 182,893 | 45,620 |
| POCT INFLUENZA A/B IMMUNOASSAY | 172,419 | 35,207 |
| LIPID PANEL | 148,974 | 23,764 |
| STREP A CULTURE | 147,291 | 37,984 |
| HEMOGLOBIN | 140,801 | 60,227 |
| THROAT CULTURE | 131,125 | 37,007 |
| URINALYSIS WITH MICROSCOPIC | 130,811 | 7,635 |
| STREP A NUCLEIC ACID DETECTION | 119,448 | 28,102 |
| INFLUENZA A/B NUCLEIC ACID | 112,796 | 22,382 |

The 25 most frequent of 3,742 distinct values, covering 75.9% of rows; the remaining 3,717 values hold the rest. Every count here is a recorded frequency within a selected cohort. Patients carrying any code that occurred fewer than 11 times were removed before delivery (1.4), so rare entries are absent by construction and nothing in this table is a population rate.

2,494,261 rows (14.5%) carry no result value at all, and 2,283,186 orders (34.7%) have no resulted component on any line. Both are expected rather than broken: the extract includes externally sourced labs that arrive without results. 3.6 covers how the values that do exist are shaped.

**Implications for analysis.** Count orders when you mean tests, rows filtered to a non-null `result_line_num` when you mean components, and never mix them in a rate — an unfiltered row count is neither. An order-with-no-result is a documented ordering event, not a missing result to impute.

### 5.3 Medications

3,823,049 medication records for 236,323 patients. A record is an order placed by a practice clinician or a documentation of an outside or historical medication, and the two behave differently.

**Record type and date completeness**

| record type | records | patients | start age present | end age present |
| --- | --- | --- | --- | --- |
| Internal | 3,250,374 | 229,099 | 98.7% | 91.6% |
| External | 572,675 | 158,974 | 58.1% | 69.1% |

The patient column does not partition the cohort: a child with both an outside history and a prescription from the practice is counted in both rows, and the two sum to 388,073 over the 236,323 patients who carry any medication record at all.

**Most frequently recorded medications**

| generic name | records | patients |
| --- | --- | --- |
| Amoxicillin | 351,609 | 136,002 |
| Albuterol Sulfate | 312,748 | 65,240 |
| Methylphenidate HCl | 219,731 | 13,658 |
| Dexmethylphenidate HCl | 124,415 | 8,083 |
| Amphetamine-Dextroamphetamine | 106,250 | 6,889 |
| Acetaminophen | 83,235 | 45,771 |
| Cefdinir | 81,224 | 41,608 |
| Sodium Fluoride | 78,612 | 31,439 |
| Fluticasone Propionate HFA | 77,412 | 19,545 |
| Amoxicillin-Pot Clavulanate | 76,894 | 47,580 |
| EPINEPHrine | 76,835 | 18,903 |
| Ibuprofen | 75,866 | 44,933 |
| Mupirocin | 74,769 | 51,626 |
| Hydrocortisone | 72,204 | 40,563 |
| Cetirizine HCl | 72,065 | 34,707 |
| Azithromycin | 69,883 | 46,509 |
| Cephalexin | 64,757 | 43,345 |
| Triamcinolone Acetonide | 60,074 | 31,238 |
| Nystatin | 58,782 | 34,023 |
| FLUoxetine HCl | 56,361 | 6,637 |
| Cholecalciferol | 55,797 | 40,031 |
| Erythromycin | 53,467 | 39,136 |
| Sertraline HCl | 49,233 | 6,289 |
| guanFACINE HCl | 48,115 | 6,701 |
| Spacer/Aero-Holding Chambers | 46,362 | 28,820 |

The 25 most frequent of 1,073 distinct values, covering 64.0% of records; the remaining 1,048 values hold the rest. Every count here is a recorded frequency within a selected cohort. Patients carrying any code that occurred fewer than 11 times were removed before delivery (1.4), so rare entries are absent by construction and nothing in this table is a population rate.

**The capitalisation is a convention, not corruption.** 93 of the 1,073 generic names carry tall-man lettering — `FLUoxetine HCl`, `guanFACINE HCl` — which pharmacy uses to make look-alike drug names hard to confuse. It is applied consistently: no drug appears under two capitalisations, which is why 3.6 finds this vocabulary collapses by nothing under case normalisation. Grouping is therefore safe, and normalising the case away is the one thing that would discard information.

**Three documented fields were never delivered.** The data dictionary describes 3 medication classification columns — `med_therapeutic_class`, `med_pharmaceutical_class`, `med_pharmaceutical_subclass` — and none is present in the extract. Any analysis by drug class has to map `med_simple_generic_name` itself.

**Implications for analysis.** A record is not an administration and not evidence the child took the drug. Externally documented records carry a documentation date in the order-date column and approximate start dates, so exposure windows built from them are unreliable — 98% of the external records that carry both dates have a start before their order, which 3.3 measures and attributes. Exclude them from any start-to-end calculation rather than treating the dates as noisy.

### 5.4 Referrals

349,827 referral orders for 138,071 patients. A referral is a recorded action, not an outcome: it says a clinician placed an order, not that the child was seen.

*Figure — Referrals by age at order. Rendered in `index.html` at `#fig-ref-age`.*

**Most frequently requested specialties**

| specialty | referrals | patients | median age |
| --- | --- | --- | --- |
| Otolaryngology | 35,723 | 29,567 | 3.99 y |
| Ophthalmology | 24,298 | 20,605 | 4.58 y |
| Orthopedic Surgery | 22,887 | 19,521 | 9.97 y |
| Allergy | 21,761 | 18,258 | 5.03 y |
| Behavioral Health | 21,748 | 16,442 | 9.29 y |
| Dermatology | 20,652 | 17,851 | 7.59 y |
| Audiology | 15,972 | 13,616 | 2.24 y |
| Gastroenterology | 14,344 | 12,467 | 5.57 y |
| Cardiology | 13,610 | 12,134 | 6.83 y |
| Neurology | 11,275 | 9,744 | 6.92 y |
| Nutrition | 11,035 | 8,910 | 9.39 y |
| Urology | 10,697 | 9,140 | 4.02 y |
| Speech Pathology | 9,879 | 7,634 | 3.84 y |
| Physical Therapy | 9,861 | 8,249 | 11.25 y |
| Early Intervention | 9,302 | 8,511 | 1.41 y |
| Developmental Medicine | 8,532 | 6,794 | 3.91 y |
| Endocrinology | 6,641 | 5,583 | 9.37 y |
| Occupational Therapy | 6,573 | 5,002 | 5.14 y |
| General Surgery | 4,206 | 3,889 | 3.78 y |
| Psychology | 4,134 | 3,537 | 9.03 y |
| Pulmonary Disease | 3,926 | 3,539 | 4.80 y |
| Plastic Surgery | 3,454 | 3,269 | 0.52 y |
| Psychiatry | 2,885 | 2,458 | 10.59 y |
| Podiatry | 2,863 | 2,608 | 11.48 y |
| Neurosurgery | 2,415 | 2,302 | 0.40 y |

The 25 most frequent of 119 distinct values, covering 92.6% of referrals naming a specialty; the remaining 94 values hold the rest. Every count here is a recorded frequency within a selected cohort. Patients carrying any code that occurred fewer than 11 times were removed before delivery (1.4), so rare entries are absent by construction and nothing in this table is a population rate.

27,452 referrals (7.85%) carry no requested specialty and 26,601 (7.6%) no requested visit count. The data dictionary also warns that referrals are not always documented in the source system, so absence of a referral is not evidence none was made.

**Implications for analysis.** This resource is positive-unlabelled: recorded referrals are real, but unrecorded ones are indistinguishable from referrals that never happened. Combined with the partial visit link measured in 3.2, a referral rate computed here is a documentation rate. Treat it as such and say so.

### 5.5 Recorded identity and patient-level observation

Identity fields are recorded categories, not attributes of the children. Blank, unknown and declined are not clinically equivalent to a recorded value but are all missing for the purpose of a subgroup comparison, so each table below marks them rather than leaving them to be spotted in a frequency-ordered list — without the marking, `Unknown` is simply the second-largest race. Together they come to 20.5% of ethnicity and 20.0% of first race, which is the figure the implication below is about. That the ethnicity figure matches the augmented layer's null share exactly is not a coincidence: 1.3 shows the augmentation converts these values and nothing else.

**Recorded sex**

| category | kind | patients | share |
| --- | --- | --- | --- |
| M | recorded | 127,699 | 51.0% |
| F | recorded | 122,883 | 49.0% |
| U | no answer | — | — |

Cells backed by fewer than 10 patients are suppressed. Non-response totals 0.0%.

**Recorded ethnicity**

| category | kind | patients | share |
| --- | --- | --- | --- |
| Not Hispanic or Latino | recorded | 170,594 | 68.1% |
| Hispanic or Latino | recorded | 28,549 | 11.4% |
| Choose not to Answer | no answer | 24,566 | 9.8% |
| Unknown | no answer | 20,834 | 8.3% |
| [blank] | no answer | 5,464 | 2.2% |
| Unable to collect | no answer | 450 | 0.2% |
| Patient does not know | no answer | 131 | 0.1% |

Cells backed by fewer than 10 patients are suppressed. Non-response totals 20.5%.

**First recorded race**

| category | kind | patients | share |
| --- | --- | --- | --- |
| White | recorded | 155,375 | 62.0% |
| Unknown | no answer | 23,085 | 9.2% |
| Choose not to answer | no answer | 17,534 | 7.0% |
| Another Race | recorded | 15,950 | 6.4% |
| Asian | recorded | 15,661 | 6.2% |
| Black or African American | recorded | 12,162 | 4.9% |
| [blank] | no answer | 8,818 | 3.5% |
| American Indian or Alaska Native | recorded | 625 | 0.2% |
| Middle Eastern or Northern African | recorded | 512 | 0.2% |
| Unable to collect | no answer | 492 | 0.2% |
| Native Hawaiian or Other Pacific Islander | recorded | 248 | 0.1% |
| Patient does not know | no answer | 126 | 0.1% |

Non-response totals 20.0%. Race is a multi-select of up to eight slots and only the first is shown: 13,191 patients (5.3%) have a second race recorded and 621 a third, so this table understates multiracial identity.

Observation per patient is dense, as the cohort rule in 1.4 requires. The median patient has 23 visits (quartiles 15 and 34, 95th percentile 56, maximum 244), spanning a median of 7.0 years (quartiles 3.3 and 10.9). The median patient's last recorded visit is at age 8.3 years.

**Implications for analysis.** Identity non-response is large enough to change a subgroup contrast on its own, so report it as its own category rather than dropping it — which requires the delivered `patients` table, because the augmented layer has already folded every non-response category into a null (1.3). And because entry to this cohort required both a measurement history and a recent visit, the visit distribution describes the selection as much as the care; it is a feasibility figure, not an estimate of pediatric utilisation.

### 5.6 Patient-level derived flags and summaries

The augmented patient layer carries seven boolean flags and a block of per-patient z-score summaries. They are conveniences computed from the visit layer, not independent observations, and each inherits whatever the channel it summarises does — the BMI flags inherit the age-2 floor of 1.3, so no visit under two can set one.

**The thresholds are not documented anywhere, so they are recovered here.** A visit sets the stunting flag below a height z of -2, the underweight flag below a BMI percentile of 5 and the obesity flag at or above 95. Those last two are exactly 4.11's category cut points, so `ever_underweight_flag` and `ever_obesity_flag` are that section's underweight and obese categories read over a whole record — 33,608 and 49,998 patients, and the counts match exactly, as one rule read two ways must. Note what this means for 4.6: the stunting flag sits at -2, which neither the upper bound at +3 nor the clamp at -5 comes near, so the height-z flags do not inherit that truncation. A tall-stature flag would, and the layer does not carry one.

**Patient-level flags**

| flag | set when the patient | patients | share of cohort |
| --- | --- | --- | --- |
| healthy_flag | carries none of the tracked conditions | 24,471 | 9.8% |
| chronic_dx_flag | any chronic diagnosis | 203,935 | 81.4% |
| growth_dx_flag | any of the tracked growth-relevant diagnoses | 35,907 | 14.3% |
| ever_stunting_flag | height z below the stunting threshold at any visit | 17,889 | 7.1% |
| ever_wasting_flag | weight-for-length or -stature below the wasting threshold | 66,704 | 26.6% |
| ever_underweight_flag | BMI below the underweight threshold at any visit | 33,608 | 13.4% |
| ever_obesity_flag | BMI at or above the obesity threshold at any visit | 49,998 | 20.0% |

*Figure — Patients carrying each derived flag. Rendered in `index.html` at `#fig-flags`.*

`growth_dx_flag` marks 35,907 patients. Where an age at diagnosis is observed (35,890 patients) its median is 0.027 years, and 25,208 of those (70.2%) are assigned their code within the first month of life. That is a statement about when the code was recorded, not about when a condition began.

The per-patient summaries below are sample statistics of the kind 4.10 warns about rather than parameters: a patient's mean carries residual variation as well as the child's own level, and a standard deviation taken within a positively autocorrelated series understates the channel's marginal spread. Averaging them across patients does not remove either bias.

**Per-patient z-score summaries, averaged over patients with more than one value**

| channel | patients | mean of patient means | mean of patient SDs |
| --- | --- | --- | --- |
| height | 248,172 | 0.2980 | 0.5147 |
| weight | 249,595 | 0.1275 | 0.5371 |
| BMI | 199,693 | 0.2927 | 0.5309 |

**Implications for analysis.** A flag is a recorded derivation, not an adjudicated clinical state, and the concentration of growth-diagnosis ages in the first month shows why: much of what the flag marks is perinatal coding rather than a growth trajectory that was observed and interpreted over years. Use the flags to describe the derived layer or to stratify descriptively; recompute from the visit layer against a stated rule if a flag is doing analytic work.

### 5.7 The extract's growth orientation: tracked codes and referral pathways

This extract was assembled around growth. Cohort entry required a growth-measurement history (1.4), and the augmentation layer records, for each patient, the age at which any of 33 specific diagnosis codes was first recorded. That panel is a design choice made upstream, and knowing which codes are in it is the difference between using the derived columns and guessing at them.

Because ICD-10 is a hierarchy (3.9), each code is counted here twice: as a literal string, and as a subtree including every descendant. The gap between the two columns is what a flat query would miss.

**The tracked growth-relevant diagnosis codes**

| ICD-10 | description | patients with a `dx_age_years_*` value | patients, literal code | patients, code and descendants | missed by a flat count |
| --- | --- | --- | --- | --- | --- |
| P92.6 | Failure to thrive in newborn | 14,428 | 14,428 | 14,428 | 0 |
| P07 | Disorders of newborn related to short gestation and low birth weight, not elsewhere classified | 11,014 | 0 | 11,029 | 11,029 |
| P05 | Disorders of newborn related to slow fetal growth and fetal malnutrition | 4,069 | 0 | 4,074 | 4,074 |
| E30.1 | Precocious puberty | 3,405 | 3,406 | 3,406 | 0 |
| P70 | Transitory disorders of carbohydrate metabolism specific to newborn | 3,353 | 0 | 3,354 | 3,354 |
| K90.0 | Celiac disease | 898 | 898 | 898 | 0 |
| E10 | Type 1 diabetes mellitus | 491 | 0 | 491 | 491 |
| E34.3 | Short stature due to endocrine disorder | 447 | 0 | 447 | 447 |
| E30.0 | Delayed puberty | 419 | 419 | 419 | 0 |
| E03.9 | Hypothyroidism, unspecified | 309 | 309 | 309 | 0 |
| Q90 | Down syndrome | 205 | 0 | 205 | 205 |
| E23.0 | Hypopituitarism | 150 | 150 | 150 | 0 |
| K50 | Crohn's disease [regional enteritis] | 113 | 0 | 113 | 113 |
| E34.4 | Constitutional tall stature | 83 | 83 | 83 | 0 |
| N18 | Chronic kidney disease (CKD) | 70 | 0 | 70 | 70 |
| K51 | Ulcerative colitis | 62 | 0 | 62 | 62 |
| Q87.1 | Congenital malformation syndromes predominantly associated with short stature | 58 | 0 | 58 | 58 |
| P04.3 | Newborn affected by maternal use of alcohol | 53 | 53 | 53 | 0 |
| Q87.3 | Congenital malformation syndromes involving early overgrowth | 46 | 46 | 46 | 0 |
| Q98.4 | Klinefelter syndrome, unspecified | 42 | 42 | 42 | 0 |
| Q96 | Turner's syndrome | 36 | 0 | 36 | 36 |
| Q87.2 | Congenital malformation syndromes predominantly involving limbs | 32 | 32 | 32 | 0 |
| E23.6 | Other disorders of pituitary gland | 31 | 31 | 31 | 0 |
| Q98.0 | Klinefelter syndrome karyotype 47, XXY | 26 | 26 | 26 | 0 |
| Q87.4 | Marfan syndrome | 17 | 0 | 17 | 17 |
| Q98.5 | Karyotype 47, XYY | 17 | 17 | 17 | 0 |
| Q77 | Osteochondrodysplasia with defects of growth of tubular bones and spine | 15 | 0 | 15 | 15 |
| Q78.0 | Osteogenesis imperfecta | 10 | 10 | 10 | 0 |

Codes carried by fewer patients than the suppression threshold are omitted. Counts are recorded frequencies inside a cohort that excluded every patient with a code seen fewer than 11 times (1.4), so this panel cannot be read as prevalence.

**The upstream derivation is hierarchical, and the two count columns verify it.** 14 of the 33 tracked codes have descendants in this extract; the other 19 have none, so both readings coincide and they cannot distinguish the two rules. Of the 14 that can, **0 match the literal count** — in every case the derived column follows the subtree. The evidence is starkest because **all 14 of those codes never appear as a literal string at all**: an exact-match query returns zero patients for `E10`, `P07`, `K50` and the rest, while the derived column correctly reports hundreds or thousands. 13 of the 14 are visible in the table above and 1 sits below the suppression threshold, so the check is stated over the whole panel and can be repeated over most of it.

4 codes (`P07`, `P05`, `E30.1`, `P70`) sit slightly below their subtree count. The shortfall is explained rather than unexplained: those patients carry the code only on a problem-list entry with no noted date, so no age could be determined. The derived column therefore means *the patient carries the code or one of its descendants **and** an age for it can be established* — not simply that the patient carries it.

The referral resource shows the same orientation from the action side. Grouping requested specialties into the families a growth question would reach for accounts for 36,182 of 349,827 referrals (10.3%).

**Referrals by growth-relevant specialty family**

| specialty family | referrals | share of all referrals | patients | median age |
| --- | --- | --- | --- | --- |
| Endocrinology | 6,916 | 1.98% | 5,790 | 9.40 y |
| Gastroenterology | 14,715 | 4.21% | 12,764 | 5.58 y |
| Nutrition and dietetics | 11,038 | 3.16% | 8,912 | 9.39 y |
| Nephrology | 1,087 | 0.31% | 937 | 6.03 y |
| Genetics | 2,426 | 0.69% | 2,116 | 3.20 y |
| all other specialties | 313,645 | 89.66% | — | — |

The last row is a residual rather than a family, which is why it carries no patient count: a child referred to two families appears in both of their patient columns, so those columns do not add up and a total would overstate the cohort. The em dashes here mean not applicable, not suppressed.

**Implications for analysis.** Use the derived columns when you want an age at first record and are content with the panel upstream chose; go to the raw diagnosis resources for anything else, and match by prefix when you do. These tables describe what the pipeline tracks, not what is clinically relevant to growth in general: a code absent from the panel may still be present in 5.1, and a specialty family here is a string match on a free-text field rather than a clinical taxonomy.

### 5.8 Age at first record for each growth-relevant diagnosis code

5.7 says which codes the tracked panel carries and how many patients carry each. This section says when. For every one of the 33 tracked codes, the tables below give the age at which the code was first recorded — its smallest, median, mean and largest value across the patients who carry it — beside the patient total counted over the code and all of its descendants.

Age here is the augmented layer's `dx_age_years_` column for the code, and that column was checked rather than assumed. For all 33 tracked codes, patient for patient, it reproduces exactly the earliest age at which the code or any of its descendants appears on either diagnosis resource: the minimum of `age_in_days` over prefix-matched encounter diagnoses and `noted_date_age_in_days` over prefix-matched problem-list entries, divided by 365.25 and rounded to three decimals. So the ages are already descendant-inclusive, and they are ages at first **record** — a patient whose only entry for the code is an undated problem-list row has no age at all, which is why the patient total and the aged count differ (5.7).

**Why this is two tables and not one.** The 28 codes shown split into two groups that answer different questions, and averaging across them describes neither. In the first, the median age at first record falls at or before age 2, and for most of them within days of birth — there the code documents a perinatal event and its age says when the child was born rather than when anything about growth was observed. In the second, the median falls later in childhood: the code was recorded when a child was brought in, measured and worked up, which is the only case where an age at first record approximates an age at onset. One table sorted by patient count interleaves the two and invites a reader to compare a perinatal code against a worked-up one as though the two ages meant the same thing.

**Why the line is at 2 years.** The cutoff comes from outside this distribution rather than from it. Two years is where the growth reference standard itself changes — a WHO chart covers birth to 24 months and a CDC chart 2 to 20 years — and this extract already carries that boundary: the augmented layer withholds BMI below age 2, where a CDC BMI-for-age reference does not apply (1.3), and two analyses in this report already restrict themselves to age 2 or later for the same reason — the repeat-height intervals of 4.5 and the growth profile of 4.9. It is also the convention by which catch-up growth in infants born small for gestational age is expected to be complete, so a code first recorded after it is unlikely to be documenting a birth event. And it is one subtraction on a recorded age, not a rule that needs interpreting. One caveat on that alignment: the ages here are diagnosis recording dates, not growth-chart crossings, so the reference boundary is what makes 2 years a meaningful line in this extract — it is not the mechanism that produced these numbers.

The cut is also robust. The highest median at or below the line is 1.798 years and the lowest above it is 3.261, and nothing lies between: **any boundary chosen in that gap produces exactly these two tables.** 13 codes fall on or below the line and 15 above. That check is worth making before believing any threshold in a descriptive table, and it is the difference between a cutoff that sorts the panel and one that merely cuts it somewhere.

**Panel one: perinatal-onset pattern — codes first recorded at or before age 2, in years**

| ICD-10 | description | patients, code and descendants | with an age | min | median | mean | max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P70 | Transitory disorders of carbohydrate metabolism specific to newborn | 3,354 | 3,353 | -0.003 | 0.003 | 0.026 | 7.162 |
| P05 | Disorders of newborn related to slow fetal growth and fetal malnutrition | 4,074 | 4,069 | 0.000 | 0.011 | 0.355 | 14.757 |
| Q98.5 | Karyotype 47, XYY | 17 | 17 | 0.000 | 0.014 | 0.896 | 5.971 |
| Q98.0 | Klinefelter syndrome karyotype 47, XXY | 26 | 26 | 0.000 | 0.018 | 2.109 | 13.530 |
| Q98.4 | Klinefelter syndrome, unspecified | 42 | 42 | 0.000 | 0.021 | 2.470 | 15.704 |
| P92.6 | Failure to thrive in newborn | 14,428 | 14,428 | -0.120 | 0.025 | 0.049 | 11.910 |
| P07 | Disorders of newborn related to short gestation and low birth weight, not elsewhere classified | 11,029 | 11,014 | -114.667 | 0.030 | 0.376 | 16.569 |
| Q90 | Down syndrome | 205 | 205 | 0.000 | 0.049 | 1.478 | 14.300 |
| Q96 | Turner's syndrome | 36 | 36 | 0.000 | 0.145 | 3.950 | 15.485 |
| P04.3 | Newborn affected by maternal use of alcohol | 53 | 53 | 0.000 | 0.498 | 2.498 | 11.387 |
| Q78.0 | Osteogenesis imperfecta | 10 | 10 | 0.008 | 1.633 | 2.483 | 10.119 |
| Q87.3 | Congenital malformation syndromes involving early overgrowth | 46 | 46 | 0.038 | 1.763 | 2.730 | 11.967 |
| Q87.2 | Congenital malformation syndromes predominantly involving limbs | 32 | 32 | 0.000 | 1.798 | 3.917 | 12.947 |

Median age at first record at or below 2 years, ordered by that median. Codes carried by fewer patients than the suppression threshold are omitted, and a code whose aged count falls below it keeps its patient total but not its four statistics. Counts are recorded frequencies inside a cohort that excluded every patient with a code seen fewer than 11 times (1.4), so this panel cannot be read as prevalence.

The membership is not what a reader would guess from the code chapters. The perinatal codes are in the first table as expected, and so are the chromosomal syndromes — `Q90` among them — because a karyotype is usually established in the nursery. The congenital *malformation* syndromes split down the middle: 3 of them fall on or below the line and 3 above it, `Q87.1` as late as 3.261 years. A malformation is present at birth by definition, so none of that spread is about onset — it dates when the coding caught up, and the spread says the lag varies widely inside a single ICD-10 chapter. It is recording lag, measured.

**Panel two: later-onset pattern — codes first recorded after age 2, in years**

| ICD-10 | description | patients, code and descendants | with an age | min | median | mean | max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Q87.1 | Congenital malformation syndromes predominantly associated with short stature | 58 | 58 | 0.000 | 3.261 | 4.085 | 15.329 |
| E34.4 | Constitutional tall stature | 83 | 83 | 0.088 | 4.047 | 4.836 | 14.891 |
| N18 | Chronic kidney disease (CKD) | 70 | 70 | 0.025 | 4.535 | 5.857 | 16.334 |
| Q77 | Osteochondrodysplasia with defects of growth of tubular bones and spine | 15 | 15 | 0.014 | 5.131 | 4.672 | 12.553 |
| Q87.4 | Marfan syndrome | 17 | 17 | 0.011 | 5.624 | 5.897 | 15.981 |
| E03.9 | Hypothyroidism, unspecified | 309 | 309 | 0.008 | 6.004 | 5.876 | 16.920 |
| K90.0 | Celiac disease | 898 | 898 | 0.027 | 7.199 | 7.630 | 17.462 |
| E10 | Type 1 diabetes mellitus | 491 | 491 | 0.873 | 7.858 | 7.876 | 16.553 |
| E30.1 | Precocious puberty | 3,406 | 3,405 | 0.016 | 7.871 | 7.002 | 17.046 |
| E23.6 | Other disorders of pituitary gland | 31 | 31 | 0.022 | 8.285 | 8.064 | 17.421 |
| E23.0 | Hypopituitarism | 150 | 150 | 0.036 | 9.027 | 8.792 | 16.047 |
| E34.3 | Short stature due to endocrine disorder | 447 | 447 | 0.019 | 10.387 | 9.618 | 16.780 |
| K50 | Crohn's disease [regional enteritis] | 113 | 113 | 0.679 | 11.064 | 10.813 | 17.268 |
| K51 | Ulcerative colitis | 62 | 62 | 0.096 | 11.950 | 10.731 | 16.389 |
| E30.0 | Delayed puberty | 419 | 419 | 6.075 | 13.637 | 13.480 | 17.035 |

Median age at first record above 2 years, ordered by that median. The same suppression and cohort caveats apply as in the table above.

**The mean and the median disagree by design, and the extremes are not clean.** `Q96` is the clearest case: a median of 0.145 years against a mean of 3.950 and a maximum of 15.485, because the same code is also recorded for older children, and one late record moves a mean that the median does not feel. The minimum is the more fragile column: it is one patient's value, and 3 codes have a negative one. `P07` reaches -114.667 years, which is a record dated before the child was born rather than a diagnosis age — 3.3 counts those directly. Read the median and the mean together; read the minimum as a data-quality probe.

Across the whole panel, `dx_age_years` — the age at which any tracked code was first recorded — is populated for 35,890 patients, with a median of 0.027 years against a mean of 1.488, a minimum of -114.667 and a maximum of 17.462. The gap between that median and that mean is the two panels above, summed.

**Implications for analysis.** These are ages at first record, so they date a coding event and not an onset; the difference matters most exactly where the median is smallest. If a design needs an index date per patient, take it from this column only for codes whose median puts the record after the birth episode, and state the choice. If a design needs age at onset, this extract does not carry it. Filter negative values explicitly rather than trusting a minimum, and where a code's aged count sits below its patient total, decide whether the undated patients belong in the denominator before computing a rate over them.

### 5.9 Label, trajectory, and utilization do not line up

A model that identifies abnormal growth early needs three things to line up: a label, a measurement history that precedes it, and a care-process record that does not simply give the answer away. In this extract none of the three lines up with the others, and the mismatches are large enough to decide a study design.

**The label mostly arrives before the trajectory does.** Of 35,890 patients carrying a growth diagnosis with a recorded age, 81.1% receive it before their first birthday, at a median age of 0.027 years. **18,157 of them (50.6%) have no height recorded at all before their diagnosis, and 75.9% have at most one.** 5.8 shows why: the tracked panel is dominated by codes first recorded within days of birth.

**That aggregate hides two different cohorts, so the rest of this section analyses them apart.** Splitting on each patient's own age at first growth diagnosis at the 2-year line 5.8 draws over the codes, 29,738 patients (82.9%) are diagnosed at or before age 2 at a median of 0.019 years, and 6,152 (17.1%) after it at a median of 8.235. The prior-height distribution is not a matter of degree between them — it inverts.

**Part one: heights available before the diagnosis, patients diagnosed at or before age 2**

| heights recorded first | patients | share of this stratum |
| --- | --- | --- |
| 0 | 17,698 | 59.5% |
| 1 | 8,836 | 29.7% |
| 2 | 1,464 | 4.9% |
| 3-4 | 987 | 3.3% |
| 5-9 | 693 | 2.3% |
| 10 or more | 60 | 0.2% |

59.5% have no prior height and only 10.8% have the two a trajectory needs.

**Part two: heights available before the diagnosis, patients diagnosed after age 2**

| heights recorded first | patients | share of this stratum |
| --- | --- | --- |
| 0 | 459 | 7.5% |
| 1 | 257 | 4.2% |
| 2 | 210 | 3.4% |
| 3-4 | 502 | 8.2% |
| 5-9 | 1,354 | 22.0% |
| 10 or more | 3,370 | 54.8% |

7.5% have no prior height and 88.4% have two or more.

*Figure — Height observations recorded before the growth diagnosis, by stratum. Rendered in `index.html` at `#fig-pre-heights`.*

**Part one has no trajectory to detect anything from.** For those 29,738 patients the code is not an outcome a growth curve could have anticipated, it is a fact recorded at or near birth, and only 10.8% carry the two prior heights a trajectory needs. **Part two is the opposite:** 88.4% of its 6,152 patients have two or more, and most have ten or more. So the 8,640 labelled patients with a usable history are not a random 24% of the cohort — 63% of them sit in part two. The 2-year cutoff is what separates a label that cannot be predicted from one that might be.

**Visit counts, lifetime and before the diagnosis**

| group | patients | median lifetime visits | mean lifetime | median before diagnosis | mean before diagnosis |
| --- | --- | --- | --- | --- | --- |
| no growth diagnosis | 214,681 | 23 | 26.02 | 23 | 26.02 |
| diagnosed at or before age 2 | 29,738 | 21 | 23.63 | 0 | 1.17 |
| diagnosed after age 2 | 6,152 | 30 | 33.47 | 19 | 20.94 |

Patients with no growth diagnosis have no index date, so their before-diagnosis count is their lifetime count. That is exactly the asymmetry the note below describes. The rows do not sum to the cohort: 17 flagged patients have no diagnosis age and so fall in neither stratum.

**Utilization separates the groups, but the separation is almost entirely part one.** Over a lifetime the three groups are close — 26.02 visits on average with no diagnosis, 23.63 in part one, 33.47 in part two. Counted up to the diagnosis they diverge, and unevenly: part one averages 1.17 prior visits against 26.02 for a patient with no index date at all, while part two averages 20.94 — close enough to the undiagnosed group that the asymmetry is a second-order problem there rather than the whole story. An undiagnosed patient has no index date and so contributes their whole record, which is what produces the gap.

A feature built from "observations before the index" therefore encodes which group a patient is in rather than anything about their growth, and for part one it does so in the counter-intuitive direction: those patients have *fewer* prior visits, not more. Note also that part two has the heaviest record of the three over a lifetime (33.47 visits), so its patients are not merely diagnosed later — they are seen more.

**Implications for analysis.** The two parts are different studies and should not be pooled. Part one cannot support early identification at all: there is no history before the label, so any score against it measures coding practice rather than growth. Part two can, and it is the population a trajectory-based model would actually train on — 6,152 patients, 88.4% of them with two or more prior heights. Report which part a result comes from; a metric computed over the pooled cohort is dominated by part one, which is 83% of it. Restricting to part two is defensible and should be stated rather than done silently, because it changes the population and it selects on the label's own timing. Fixing the utilization asymmetry still needs a common index date chosen without reference to the label — a fixed age, a matched visit number, or a sampled pseudo-index for unlabelled patients — and that is needed in part two as well, where it is smaller but not absent. And whichever part is used, the label is recorded coding practice and not an adjudicated growth assessment; 5.6 makes the same point about the flag itself.

### 5.10 What a feature vector actually contains

Height and weight are the two measurements a growth model needs together, and 3.4 gives each one's availability separately. Jointly is what matters, because a visit missing either contributes no complete observation.

**Visits carrying height, weight, and both**

| age band (years) | visits | height | weight | both | weight without height |
| --- | --- | --- | --- | --- | --- |
| 0-2 | 2,693,000 | 56.9% | 99.8% | 56.8% | 43.0% |
| 2-5 | 1,393,990 | 44.6% | 99.8% | 44.5% | 55.3% |
| 5-10 | 1,529,617 | 53.6% | 99.9% | 53.5% | 46.3% |
| 10-15 | 742,225 | 59.3% | 99.9% | 59.2% | 40.7% |
| 15-18 | 135,641 | 56.7% | 99.9% | 56.6% | 43.3% |

The joint rate tracks the height rate almost exactly: where a height exists a weight nearly always does too, so height alone is the binding constraint and the last column is what a height-and-weight model discards. It is worst at 2-5 years, where only 44.5% of visits carry both and 55.3% carry a weight with no height to pair it with.

**Derived flags among labelled and unlabelled patients**

| flag | set when the patient has | growth diagnosis | no growth diagnosis | ratio |
| --- | --- | --- | --- | --- |
| ever_stunting_flag | height below the stunting threshold | 21.8% | 4.7% | 4.65x |
| ever_wasting_flag | weight-for-length or -stature below wasting | 36.4% | 25.0% | 1.46x |
| ever_underweight_flag | BMI below the underweight threshold | 14.1% | 13.3% | 1.06x |
| ever_obesity_flag | BMI at or above the obesity threshold | 14.6% | 20.9% | 0.70x |
| chronic_dx_flag | any chronic diagnosis | 82.4% | 81.2% | 1.01x |
| healthy_flag | carries none of the tracked conditions | 0.0% | 11.4% | 0.00x |

Two rows here matter for anyone assembling a training set. `healthy_flag` is set for 0.0% of growth-diagnosed patients — it is **disjoint from the diagnosis flag by construction**, so using it as a negative class defines the outcome into the input and any model separating the two is learning the definition. `ever_stunting_flag`, by contrast, is a genuine correlate: 21.8% against 4.7%, a 4.7-fold enrichment derived from the measurements themselves rather than from the code.

**Cross-resource footprint by label**

| group | patients | has a referral | has a medication | has a lab |
| --- | --- | --- | --- | --- |
| growth diagnosis | 35,907 | 61.9% | 95.9% | 98.6% |
| no growth diagnosis | 214,681 | 54.0% | 94.0% | 98.7% |

**Implications for analysis.** Count complete observations, not visits: the usable input rate is the joint column, not the weight column, and it varies by more than ten points across childhood so a cohort defined by complete rows is age-selected. Never use `healthy_flag` as the negative class for a growth-diagnosis model. The cross-resource footprint is a weak discriminator — a referral is present for 61.9% of labelled against 54.0% of unlabelled patients — which is reassuring for leakage but means these resources add little on their own.

### 5.11 Treatment and workup: better timing than the label, and leakage

5.9 shows the diagnosis code arrives too early to be predicted from a growth curve for most of the labelled cohort, and identifies the later-diagnosed minority where it does not. The medication and laboratory resources carry a second set of growth signals, and they behave in the opposite way. Both matter: as features they leak, and as index events they are far better dated than the code.

**Growth and endocrine treatment and workup markers**

| marker | patients | with a growth diagnosis | share flagged | against the base rate | treated but unflagged | median age at first record |
| --- | --- | --- | --- | --- | --- | --- |
| growth hormone | 237 | 172 | 72.6% | 5.1x | 65 | 10.8 y |
| thyroid hormone | 541 | 335 | 61.9% | 4.3x | 206 | 7.7 y |
| GnRH agonist | 203 | 107 | 52.7% | 3.7x | 96 | 10.2 y |
| antithyroid | 31 | 8 | 25.8% | 1.8x | 23 | 11.1 y |
| mineralocorticoid | 60 | 9 | 15.0% | 1.0x | 51 | 13.3 y |

Matched by string against the free-text generic and procedure names, so these are indicative rather than a curated vocabulary. Hydrocortisone and estradiol are excluded deliberately: both are common in this population for topical and contraceptive indications that have nothing to do with growth.

**The laboratory workup, ordered by how much it discriminates**

| test | patients | share flagged | against the base rate | median age at first order |
| --- | --- | --- | --- | --- |
| karyotype | 20 | 50.0% | 3.49x | 6.1 y |
| estradiol | 1,198 | 32.9% | 2.30x | 12.2 y |
| luteinising hormone | 2,103 | 31.2% | 2.18x | 13.0 y |
| follicle-stimulating hormone | 2,379 | 28.9% | 2.02x | 13.4 y |
| testosterone | 2,083 | 28.3% | 1.98x | 13.3 y |
| growth hormone assay | 108 | 26.9% | 1.87x | 9.1 y |
| IGF-1 | 1,151 | 26.2% | 1.83x | 8.7 y |
| chromosomal microarray | 350 | 22.6% | 1.58x | 3.9 y |
| cortisol | 271 | 20.3% | 1.42x | 11.1 y |
| prolactin | 1,738 | 18.2% | 1.27x | 14.1 y |
| ferritin | 18,578 | 17.1% | 1.19x | 5.6 y |
| coeliac transglutaminase | 19,004 | 15.8% | 1.10x | 8.3 y |
| total IgA | 22,776 | 15.7% | 1.09x | 7.1 y |
| free thyroxine | 24,692 | 14.9% | 1.04x | 9.8 y |
| alkaline phosphatase | 26,555 | 14.5% | 1.01x | 9.1 y |
| thyroid stimulating hormone | 31,252 | 14.3% | 1.00x | 9.6 y |
| C-reactive protein | 21,357 | 14.0% | 0.98x | 7.0 y |
| erythrocyte sedimentation rate | 26,765 | 13.9% | 0.97x | 7.3 y |
| creatinine | 30,000 | 13.8% | 0.96x | 8.4 y |
| vitamin D | 11,796 | 11.8% | 0.82x | 11.0 y |

Ordered by lift. The same string-matching caveat applies, and a test's presence means it was ordered, not that it was abnormal — 3.6 shows result values are semi-structured text.

The panel splits cleanly in two. The specific endocrine and genetic tests carry real signal — karyotype leads at 3.49 times the base rate — while the general screens that accompany a growth evaluation carry almost none: 8 of the 20 tests sit below 1.1, together covering 195,193 patient-test pairs. Thyroid stimulating hormone is the clearest case, ordered for 31,252 patients at a lift of 1.00 — a high-volume feature carrying essentially no information about this label.

One bound on this table comes from 1.4. The cohort excluded every patient carrying a lab procedure seen fewer than 11 times, which removed 9,621 of 13,402 procedures along with their patients. The most specialised growth workup is therefore the most likely to be missing entirely, and the rarest test that survives here — karyotype, at 20 patients — sits just above that threshold. Read the sparse rows as a floor rather than a count.

**As features these leak.** Against a base rate of 14.3%, 237 patients ever prescribed growth hormone are 72.6% flagged — 5.1 times enriched. A model given medication history has been told the answer for those patients, and the same holds in weaker form for the other rows.

**And the label misses cases they identify.** 65 of those growth-hormone patients carry no growth diagnosis in the tracked panel at all, as do 850 of the 1,151 with an IGF-1 test. Being treated for a growth disorder and being labelled with one are substantially different populations here, which bounds how well any model scored against the code can do.

**The timing is the useful part.** The diagnosis code has a median age of 0.027 years (5.9). Growth hormone is first ordered at a median of 10.8 years, and the first growth workup or treatment of any kind at a median of 9.1 — roughly a decade later, and at an age where a trajectory exists. Taking the first growth workup or treatment as the index event instead of the code gives 1,410 patients, of whom **98.1% have at least two prior heights** and the median has 13. Only 0.6% have none. Against the code label's 24.1% and 50.6% respectively, that is a reversal. The index is also on the far side of the 2-year line 5.9 splits on: at a median of 9.1 years it lands squarely in that section's later-diagnosed part, which is the same population reached from the other direction.

**Implications for analysis.** If the diagnosis code is the label, treatment and workup records have to be excluded from the features or the model will read the answer off them; excluding them is easy because they are identifiable by name. The more useful move is to treat the first growth workup as the index event: it marks when a clinician became concerned, it is dated when a trajectory exists, and predicting it is the question an early-detection model is actually being asked. The cost is population size, 1,410 against 237 on treatment alone and 35,890 on the code, and the caveat is that a workup is an action rather than an adjudicated outcome — 5.4 makes the same point about referrals.

### 5.12 The same code in two resources: encounter diagnoses against the problem list

A growth code can reach the record two ways: coded at an encounter, or noted on the problem list. 5.7 established that the derived `dx_age_years_*` columns take the earliest of both. This asks what would be lost by taking only one, and whether the two agree on when the diagnosis happened.

Across the 39,896 patient-and-code pairs the tracked panel produces, only 19,984 (50.1%) appear in both resources. 14,430 (36.2%) are encounter-coded and never reach the problem list, and 5,482 (13.7%) are the reverse. **Neither resource alone is a complete record of the diagnosis.**

**Where each tracked code appears**

| ICD-10 | patient-code pairs | in both | encounter only | problem list only | found by encounters | found by problem list | median problem-list lag |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P92.6 | 14,428 | 4,386 | 9,936 | 106 | 99% | 31% | 0 d |
| P07 | 11,005 | 7,609 | 1,689 | 1,707 | 84% | 85% | 0 d |
| P05 | 4,069 | 2,526 | 467 | 1,076 | 74% | 89% | 0 d |
| E30.1 | 3,405 | 1,635 | 1,635 | 135 | 96% | 52% | 0 d |
| P70 | 3,351 | 1,010 | 179 | 2,162 | 35% | 95% | 0 d |
| K90.0 | 898 | 772 | 63 | 63 | 93% | 93% | -28 d |
| E10 | 491 | 441 | 23 | 27 | 95% | 95% | -6 d |
| E34.3 | 447 | 264 | 141 | 42 | 91% | 68% | 0 d |
| E30.0 | 419 | 273 | 116 | 30 | 93% | 72% | 0 d |
| E03.9 | 309 | 168 | 103 | 38 | 88% | 67% | 0 d |
| Q90 | 205 | 195 | 7 | 3 | 99% | 97% | 0 d |
| E23.0 | 150 | 133 | 5 | 12 | 92% | 97% | -161 d |
| K50 | 113 | 95 | 4 | 14 | 88% | 96% | -157 d |
| E34.4 | 83 | 60 | 12 | 11 | 87% | 86% | 0 d |
| N18 | 70 | 53 | 6 | 11 | 84% | 91% | -76 d |
| K51 | 62 | 50 | 7 | 5 | 92% | 89% | -132 d |
| Q87.1 | 58 | 51 | 3 | 4 | 93% | 95% | 0 d |
| P04.3 | 53 | 35 | 3 | 15 | 72% | 94% | 0 d |
| Q87.3 | 46 | 41 | 3 | 2 | 96% | 93% | -37 d |
| Q98.4 | 42 | 34 | 8 | 0 | 100% | 81% | -3 d |
| Q96 | 36 | 31 | 2 | 3 | 92% | 94% | -4 d |
| Q87.2 | 32 | 27 | 1 | 4 | 88% | 97% | -19 d |
| E23.6 | 31 | 21 | 4 | 6 | 81% | 87% | 0 d |
| Q98.0 | 26 | 22 | 2 | 2 | 92% | 92% | -4 d |
| Q87.4 | 17 | 13 | 2 | 2 | 88% | 88% | 0 d |
| Q98.5 | 17 | 15 | 0 | 2 | 88% | 100% | 0 d |
| Q77 | 15 | 14 | 1 | 0 | 100% | 93% | 0 d |
| Q78.0 | 10 | 10 | 0 | 0 | 100% | 100% | 0 d |

Codes with fewer than ten pairs are omitted. A negative lag means the problem list noted the diagnosis first.

The split is strongly code-dependent, which is the part that would catch an analysis out. Reading encounter diagnoses alone finds 35% of `P70` pairs; reading the problem list alone finds 31% of `P92.6` pairs. A single-resource cohort definition is therefore not uniformly incomplete — it is incomplete by a different amount for every condition, which biases comparisons between them.

Where both resources carry the code they mostly agree on the date: 12,373 of 19,984 pairs (61.9%) fall within a few days. When they disagree the problem list more often leads than lags — 26.9% against 11.2% — by a median of 33 days against 50, with 90th percentiles of 515 and 1217 days. That direction is consistent with the problem list carrying history noted before the code was used at a visit, which is what the data dictionary describes it as holding.

This comparison is restricted to ages between 0 and 18.5 years. The problem list carries noted ages down to -123 years, which 3.3 counts among its pre-birth entries; a single one of those turns a lead of days into a lead of a century, so they are excluded here rather than allowed to set the tail.

**Implications for analysis.** Take the union of both resources for any cohort definition or index date, and take the earliest record as the derived columns do. If you must use one resource, measure what it costs for your specific codes rather than assuming a uniform rate. And treat the 2,241 pairs where the problem list lags as a documentation delay rather than a later onset — the encounter had already coded it.

### 5.13 Referral timing against the diagnosis, and the subgroup it finds

5.7 gives the referral volume by specialty family. This asks the question that volume cannot: for a patient who has both, does the referral come before the diagnosis or after it, and does the answer identify a different kind of patient.

**Referral families against the growth diagnosis**

| specialty family | referred patients | label lift | median referral age | median diagnosis age | with both | median referral lag | referral first | within a month |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Endocrinology | 5,790 | 2.36x | 9.2 y | 7.14 y | 1,958 | 40 d | 24.2% | 36.0% |
| Gastroenterology | 12,764 | 1.57x | 5.3 y | 0.04 y | 2,867 | 188 d | 15.2% | 11.2% |
| Genetics | 2,116 | 1.83x | 3.1 y | 0.03 y | 554 | 365 d | 11.6% | 19.3% |
| Nephrology | 937 | 1.48x | 5.5 y | 0.04 y | 199 | 338 d | 16.6% | 18.6% |
| Nutrition and dietetics | 8,912 | 1.01x | 9.1 y | 0.03 y | 1,296 | 834 d | 12.7% | 5.9% |

Lift is against a base labelled rate of 14.3%. A negative lag would mean the referral came first; all five families are positive.

Two tiers again, as in the laboratory panel. Endocrinology carries the signal at 2.36 times the base rate across 5,790 referred patients, while nutrition and dietetics — the family a growth question might reach for first — sits at 1.01 across 8,912, which is no signal at all.

**Referrals follow the code, not the other way round.** Every family has a positive median lag, and only 24.2% of endocrinology pairs have the referral first. A referral is therefore not an earlier index event than the diagnosis in the way the laboratory workup of 5.11 is.

**But endocrinology selects a different population, and that is the useful part.** Among labelled patients referred to endocrinology the median diagnosis age is 7.14 years, against 0.027 for the labelled cohort as a whole (5.9), and 36.0% carry the code within 30 days of the referral. These are not the perinatal codes that dominate the label; they are diagnoses recorded in childhood, at the moment a referral was made.

**Heights recorded before the diagnosis, by referral**

| labelled patients | patients | no prior height | two or more | median prior heights |
| --- | --- | --- | --- | --- |
| with an endocrinology referral | 1,958 | 22.7% | 69.3% | 7 |
| without one | 33,932 | 52.2% | 21.5% | 0 |

That difference decides whether the label is learnable. Of the 1,958 labelled patients with an endocrinology referral, 69.3% have at least two prior heights and the median has 7; for everyone else those figures are 21.5% and zero. 5.9's finding — that half the labelled population has no trajectory before the code — is really a statement about the perinatal majority, and it inverts inside this subgroup.

**Implications for analysis.** Do not use a referral as an early index event; it lags the code in every family measured. Do use it as a cohort filter: an endocrinology referral marks the patients whose growth diagnosis was made in childhood with a measurement history behind it, which is the population an early-detection question is actually about. The cost is size, 1,958 against 35,890, and the caveat from 5.4 stands — a referral is a recorded action, and its absence is not evidence that none was warranted.

### 5.14 A shortcut audit: which fields encode the label

5.11 and 5.13 measure the leakage in a list of candidates chosen for being clinically obvious. This section runs the search those sections imply: every value of 7 categorical fields that 200 or more patients carry, scored against the label. 2,652 values meet that floor, out of 13,981 distinct ones. Lift is the share of patients carrying a value who also carry `growth_dx_flag`, over the cohort's 14.33% base rate; a lift of 1 is no information.

**What the positive class is made of bounds what every lift here means.** Of the 35,890 labelled patients with a diagnosis age, 29,738 (82.9%) are diagnosed at or before age 2 — 5.9's earlier stratum, the one with no measurement history before the code. A lift in this table is therefore mostly a statement about what co-occurs with perinatal coding, not about what precedes a growth problem. That does not make a leaking field safe to keep: a shortcut that works because the label is perinatal still works. It does mean a field that screens clean here has not been cleared for the later-diagnosed stratum, where the base rate, the timing and the available history are all different, and re-screening against a stratified label is the check this section does not perform.

A value counts once per patient, ever, with no temporal cut — which is what an unrestricted feature build sees, and it mixes leakage with concurrency: a code recorded at the same encounter as the diagnosis scores as high as one recorded years before it. Beside each lift is the same figure against the alternative index of 5.11, the first growth workup or treatment, which 1,410 patients carry at a base rate of 0.56%. It is suppressed where fewer than 10 patients back it, and where the value is itself part of the index definition — the somatropin, growth hormone and IGF records — since those score the index's maximum by construction rather than by discrimination.

**The raw diagnosis fields carry the label verbatim.** 26 screened codes are one of the tracked panel or a descendant of one (3.9, 5.7), and 26 of them are carried by no unlabelled patient at all, which is every code in that group — a lift of 6.98, the maximum the base rate allows. Dropping the `dx_age_years_*` columns therefore does not take the label out of a feature set: `enc_diag_*` and `pl_diag` reconstruct it exactly. The table below excludes that group and shows what is left.

**Diagnosis codes with the highest lift, excluding the tracked panel and its descendants**

| ICD-10 | description | patients | carry the label | lift | lift, workup index |
| --- | --- | --- | --- | --- | --- |
| H35.103 | Retinopathy of prematurity, unspecified, bilateral | 244 | 97.1% | 6.78x | — |
| P27.1 | Bronchopulmonary dysplasia originating in the perinatal period | 268 | 95.9% | 6.69x | — |
| H35.109 | Retinopathy of prematurity, unspecified, unspecified eye | 251 | 94.4% | 6.59x | — |
| P28.49 | Other apnea of newborn | 461 | 93.7% | 6.54x | — |
| P61.2 | Anemia of prematurity | 751 | 93.2% | 6.50x | 3.31x |

Top 5 by lift among codes carried by 200 or more patients.

What sits below the panel is the neighbourhood of a label 5.9 shows to be overwhelmingly perinatal: prematurity, its complications, and newborn morbidity. None is a growth code and none is tracked, but a patient carrying one was in the neonatal course that produced the label, and the screen reaches 1,578 untracked codes in all. That is the kind of shortcut a curated exclusion list does not reach: it is built by naming the condition, and none of these names the condition.

**The top of the lift distribution in the other 6 fields**

| field | value | patients | carry the label | lift | lift, workup index |
| --- | --- | --- | --- | --- | --- |
| medication | Insulin Disposable Pump | 214 | 100.0% | 6.98x | — |
| medication | Insulin Glargine | 327 | 98.5% | 6.87x | — |
| medication | Continuous Glucose Transmitter | 235 | 98.3% | 6.86x | — |
| medication | Continuous Glucose Sensor | 306 | 97.4% | 6.80x | — |
| medication | Glucagon | 364 | 97.3% | 6.79x | — |
| lab procedure | ALKALINE PHOSPHATASE | 813 | 51.8% | 3.61x | 6.56x |
| lab procedure | RSV AG EIA | 219 | 44.7% | 3.12x | — |
| lab procedure | ANDROSTENEDIONE | 225 | 42.2% | 2.95x | — |
| lab procedure | IGF BINDING PROTEIN 1(IGFBP-1) | 278 | 35.6% | 2.49x | — |
| lab procedure | ALK PHOS | 482 | 33.4% | 2.33x | — |
| referral specialty | Radiology | 203 | 43.3% | 3.03x | — |
| referral specialty | Pediatric Gastroenterology | 327 | 39.8% | 2.77x | — |
| referral specialty | Pediatric Ophthalmology | 286 | 39.5% | 2.76x | — |
| referral specialty | Pediatric Endocrinology | 233 | 38.2% | 2.67x | 16.02x |
| referral specialty | Endocrinology | 5,583 | 33.7% | 2.35x | 16.17x |
| encounter type | Clinical Support | 11,005 | 26.3% | 1.83x | 1.07x |
| encounter type | Immunization | 8,378 | 17.3% | 1.21x | 1.97x |
| encounter type | Lactation Encounter | 523 | 17.0% | 1.19x | — |
| encounter type | Lab | 1,216 | 16.7% | 1.17x | 1.75x |
| encounter type | Newborn | 22,924 | 15.5% | 1.08x | 1.09x |
| medication record type | External | 158,974 | 15.6% | 1.09x | 1.28x |
| medication record type | Internal | 229,099 | 14.6% | 1.02x | 1.02x |
| lab result flag | (NONE) | 3,696 | 41.3% | 2.88x | 0.91x |
| lab result flag | High Panic | 5,857 | 24.8% | 1.73x | 0.49x |
| lab result flag | Low Panic | 984 | 21.8% | 1.52x | — |
| lab result flag | Panic | 2,091 | 16.0% | 1.12x | 1.19x |
| lab result flag | High | 94,539 | 16.0% | 1.12x | 1.83x |

Top 5 values per field, by lift, among those carried by 200 or more patients.

Encounter type is the field the screen clears, and a measured null is as useful as a hit. Its highest value is `Clinical Support` at 1.83, and the types whose names promise growth surveillance sit at the base rate: the weight check at 0.98, the nutrition visit at 1.02. Nothing in the report would otherwise establish that, since an argument from the name alone points the other way.

The two fields added last behave differently from each other and neither carries much. Medication record type is flat — 1.09 for a patient with any external record against 1.02 for an internal one. The laboratory result flag is flat too, apart from one value: its most enriched is the literal `(NONE)` at 2.88 across 3,696 patients, which 3.5 shows is the string meaning *normal* and which became a null on nine rows in ten. A flag value asserting that nothing was abnormal is the one that discriminates, which is more plausibly a fact about which records still carry the sentinel than about the children carrying them.

**The medication screen finds what a curated list could not.** 16 of the 330 screened generic names lift higher than the 5.06 that 5.11 measures for growth hormone, and none of them is a growth treatment: `Insulin Disposable Pump`, `Insulin Glargine`, `Continuous Glucose Transmitter`, `Continuous Glucose Sensor`. Type 1 diabetes is in the tracked panel (5.7), so every product dispensed to a child who carries that code — consumables included — reconstructs part of the label. An exclusion list built by naming growth treatments does not catch a box of lancets.

**The unit of the screen decides the answer.** 5.11 matches `ALKALINE PHOSPHATASE` as a substring across the procedure name and the result component, finds 26,555 patients at a lift of 1.01, and reads it as a general screen carrying no information. Screened as a procedure name in its own right the same test is 813 patients at 3.61. Both figures are correct and they answer different questions: ordering the test deliberately is not the same event as receiving it inside a panel, and a substring match pools them.

**One column reconstructs the label on its own.** `visits_count_pre_dx` counts a patient's visits up to the diagnosis, and for a patient without one it equals the lifetime count. The inequality between the two columns is therefore the label: 35,793 patients have a shorter pre-diagnosis count and 35,793 of them are labelled, against 114 of the 214,795 others. That is 100.0% precision at 99.7% recall from a single comparison of two delivered columns. 5.9 makes the point about counts measured to an index date; this is the same asymmetry shipped as a column, and no model given the augmented patient table can avoid it.

**`visits_count_pre_dx` against `visits_count`**

| patients where | patients | carry the label | share |
| --- | --- | --- | --- |
| pre-diagnosis count is shorter than the lifetime count | 35,793 | 35,793 | 100.00% |
| the two counts are equal | 214,795 | 114 | 0.05% |

**The shortcut set belongs to the label, not to the extract.** The same features scored against the alternative index reorder completely. An endocrinology referral lifts 2.36 against the code and 16.15 against the workup, so 5.13's advice to use it as a cohort filter selects on the outcome under 5.11's recommended design; and the growth-hormone and IGF-1 records that 5.11 screens as leaking features are that design's definition of the label rather than features at all. Nothing here is transferable between the two.

**Named candidates against both labels**

| feature | patients | carry the code label | lift, code label | lift, workup index |
| --- | --- | --- | --- | --- |
| endocrinology referral (5.13) | 5,790 | 33.8% | 2.36x | 16.15x |
| growth hormone prescription (5.11) | 237 | 72.6% | 5.06x | — |
| stunting flag ever set (5.10) | 17,889 | 43.8% | 3.05x | 5.94x |
| failure to thrive or short stature in the child, R62.5x | 41,628 | 22.0% | 1.53x | 5.39x |
| pediatric BMI-percentile code, Z68.5x | 64,467 | 10.6% | 0.74x | 0.96x |
| any encounter converted from the legacy system | 137,210 | 9.3% | 0.65x | 1.42x |
| no converted encounter: recorded natively throughout | 113,378 | 20.4% | 1.43x | 0.50x |

Three rows deserve a second look. The pediatric BMI-percentile codes are the growth chart written into the diagnosis field and they carry no lift at all, because the label is perinatal rather than anthropometric — an obvious candidate that a screen clears and an argument would not. And the last two rows separate patients by nothing clinical at all: a record kept natively throughout lifts 1.43 against 0.65 for one carrying any encounter converted from the practice network's previous system, a 2.2-fold spread on a provenance field. 3.7 measures that field's effect on diagnosis completeness; this is what the same effect does to a label.

One bound on all of this comes from 1.4. The cohort excluded every code, medication and procedure seen fewer than 11 times along with the patients carrying them, and 5.11 measures how much of the laboratory vocabulary that removed. The rarest and most specific markers are the most likely to be gone, so a screen on this extract under-detects exactly the shortcuts it most wants to find.

**Implications for analysis.** Screen rather than enumerate: run this against your own label and index before building a feature set, and re-run it after any change to either. Exclude the fields that reconstruct the label — the raw diagnosis slots and the problem list, `visits_count_pre_dx`, and the treatment records of 5.11 — and remember that a field carrying no clinical meaning can still discriminate. A lift measured here is an upper bound on what a temporally honest feature could contribute, not an estimate of it: everything above is scored without a cut, so a value that only ever appears alongside the diagnosis scores as high as one that precedes it.

### 5.15 The same screen over the numbers: derived columns and constructed features

5.14 screens categorical fields, where a lift answers the question. A continuous column needs a statistic that does not depend on where a threshold is put, so this section uses the rank statistic: the probability that a labelled patient ranks above an unlabelled one, with ties at their mid-rank. 0.5 is no separation. Below it means the labelled patients rank lower, which is a direction rather than an absence, so the tables sort on distance from 0.5 and carry it as its own column.

The same caveat as 5.14 applies to every figure below, and for the same reason: 82.9% of the labelled patients with a diagnosis age are diagnosed at or before age 2, so a rank statistic here mostly separates the perinatal stratum of 5.9 from everyone else. A column that separates the pooled label may separate the later-diagnosed stratum better, worse, or not at all.

Every numeric column of the augmented patient layer is screened — 41 of them, after setting aside the label and the 34 `dx_age_years` columns that carry its age. Beside each is the same statistic among patients whose record reaches 5 years of age and spans 5 years, which is a coarse control for how much record exists rather than a matched design.

**The 10 delivered patient columns that separate the label most**

| column | patients | rank statistic | distance from neutral | long records only |
| --- | --- | --- | --- | --- |
| `visits_count_pre_dx` | 250,588 | 0.075 | 0.849 | 0.115 |
| `min_weight_z_score` | 250,577 | 0.305 | 0.390 | 0.320 |
| `min_head_circ_z_score` | 200,584 | 0.318 | 0.365 | 0.325 |
| `max_visit_age_days` | 250,588 | 0.339 | 0.322 | 0.376 |
| `min_height_z_score` | 250,261 | 0.345 | 0.311 | 0.346 |
| `mean_weight_z_score` | 250,577 | 0.353 | 0.294 | 0.396 |
| `count_bmi_z_score` | 250,588 | 0.359 | 0.281 | 0.421 |
| `std_height_z_score` | 248,172 | 0.640 | 0.280 | 0.653 |
| `visits_span_days` | 250,588 | 0.365 | 0.270 | 0.424 |
| `mean_head_circ_z_score` | 200,584 | 0.374 | 0.252 | 0.393 |

Of 41 columns screened, 12 sit within 0.05 of 0.5 and carry almost nothing on their own.

**After the column that is the label, growth and bookkeeping are interleaved.** `visits_count_pre_dx` leads at 0.075 because 5.14 shows it to be the label written as a count. Then the lowest weight z-score a child ever recorded at 0.305 — and immediately behind it the age at the last visit at 0.339, the number of BMI values at 0.359, and the span of the record at 0.365. **The shape of a patient's record separates this label about as well as the child's growth does**, because a labelled patient is younger and less observed when the label is perinatal (5.9).

Two columns further down the same screen are worth putting side by side; neither reaches the ten shown above. The count of head circumference measurements separates at 0.605 and the stunting flag at 0.586: **how often a child was measured carries more about this label than whether the measurement was low.** Meanwhile `visits_count` itself is 0.488, which is nothing — lifetime volume does not discriminate, and the rate at which that volume accumulates does.

**Constructed features, scored the same way**

| feature | patients | rank statistic | distance from neutral | long records only |
| --- | --- | --- | --- | --- |
| visits per year of record | 250,588 | 0.664 | 0.328 | 0.621 |
| median days between consecutive visits | 249,606 | 0.337 | 0.326 | 0.379 |
| problem-list entries | 250,588 | 0.633 | 0.267 | 0.645 |
| problem-list entries, excluding the tracked panel | 250,588 | 0.592 | 0.185 | 0.612 |
| distinct laboratory orders | 250,588 | 0.564 | 0.128 | 0.606 |
| share of visits carrying a height | 250,588 | 0.453 | 0.094 | 0.446 |
| medication records | 250,588 | 0.535 | 0.070 | 0.584 |
| head circumferences recorded after age 3 | 250,588 | 0.494 | 0.013 | 0.495 |
| distinct laboratory procedures | 250,588 | 0.497 | 0.006 | 0.574 |
| days carrying two or more heights (3.8) | 250,588 | 0.499 | 0.002 | 0.499 |
| position in the delivered patient file | 250,588 | 0.501 | 0.002 | 0.500 |

Features a modeller would build rather than find, each computed over the whole record with no temporal cut.

**Contact intensity separates the label, and it is not only censoring.** Visits per year runs 0.664 and the median gap between visits 0.337; restricted to records of 5 years or more they hold at 0.621 and 0.379. A model given visit timing has been told something about the label that no growth measurement supplied. Read the rate with its denominator in mind, though: it divides by a span that is itself a 0.365 separator.

The restriction controls the observation window and nothing else. Inside it 161,778 patients remain at a labelled rate of 10.4%, and their median age at diagnosis is still 0.077 years. The perinatal concentration survives the cut, so a separation that holds under it is bounded above by what an age-matched design would find, not established by it. Restricting on record length is the wrong axis for that: 5.9 splits the labelled class on age at diagnosis instead, and it is that split rather than this one which separates the patients who have a history before the label from the ones who do not.

**The problem-list count shows what contamination costs.** Counting every entry gives 0.633; counting only entries outside the tracked panel gives 0.592. The tracked codes reach the problem list (5.12), so the first number is part label and part utilisation, and only the second is a feature. A count over a diagnosis resource needs the label's own codes taken out of it before it means anything.

Several results are negative, and they are worth recording as such. Days carrying two or more heights — the same-day disagreement of 3.8, read as a sign of a clinician re-measuring — sit at 0.499. A patient's position in the delivered file is 0.501: the delivery is not ordered by anything related to the label, which is the one shortcut that would have been invisible in every other check in this report. The breadth of the laboratory workup is 0.497 across the whole cohort but 0.574 among long records, which is the pattern to expect when a flat result is itself an artifact of the age mix rather than a finding: a null measured over this cohort is not a null.

**Implications for analysis.** Screen continuous features the same way you screen categorical ones, and screen the ones you build as well as the ones you were given — the highest-ranking features here are a count of measurements and a rate of contact, neither of which looks like a leak in a feature list. Where a column describes the record rather than the child, either exclude it or make the observation window an explicit part of the design; 5.9's common index date is the same remedy arrived at from the other direction.

## 6. Field index

Every column, with its population, range, and the findings that govern it.

### 6.1 Every column in the extract

All 176 distinct columns across the 8 resources, with how much of each is populated and how many values it takes. A repeated family — the encounter-diagnosis slots, the race slots — appears once, named for the span it covers in that resource and summarised on its first member. The span differs between resources: `patients` and `patients_augmented` carry eight race columns, `visits_augmented` carries one, so a row reading `race_1` is the whole of that resource's race detail and not the first of eight.

Two sections read this index rather than describe it. 3.4 takes the least-populated columns from it, and 5.15 scores every numeric column of the augmented patient layer here against the growth label, which is where to look before treating any of them as a feature.

**Field index**

| resource | field | type | populated | missing | distinct values |
| --- | --- | --- | --- | --- | --- |
| patients | patient_id | VARCHAR | 250,588 | 0.0% | 250,588 |
| patients | sex | VARCHAR | 250,588 | 0.0% | 3 |
| patients | ethnicity | VARCHAR | 245,124 | 2.2% | 6 |
| patients | race_1..8 | VARCHAR | 241,770 | 3.5% | 11 |
| patients_augmented | patient_id | VARCHAR | 250,588 | 0.0% | 250,588 |
| patients_augmented | sex | VARCHAR | 250,588 | 0.0% | 3 |
| patients_augmented | ethnicity | VARCHAR | 199,143 | 20.5% | 2 |
| patients_augmented | race_1..8 | VARCHAR | 200,533 | 20.0% | 7 |
| patients_augmented | healthy_flag | BIGINT | 250,588 | 0.0% | 2 |
| patients_augmented | chronic_dx_flag | BIGINT | 250,588 | 0.0% | 2 |
| patients_augmented | growth_dx_flag | BIGINT | 250,588 | 0.0% | 2 |
| patients_augmented | ever_stunting_flag | BIGINT | 250,588 | 0.0% | 2 |
| patients_augmented | ever_wasting_flag | BIGINT | 250,588 | 0.0% | 2 |
| patients_augmented | ever_underweight_flag | BIGINT | 250,588 | 0.0% | 2 |
| patients_augmented | ever_obesity_flag | BIGINT | 250,588 | 0.0% | 2 |
| patients_augmented | visits_count | BIGINT | 250,588 | 0.0% | 173 |
| patients_augmented | visits_count_pre_dx | BIGINT | 250,588 | 0.0% | 170 |
| patients_augmented | min_visit_age_days | BIGINT | 250,588 | 0.0% | 4,793 |
| patients_augmented | max_visit_age_days | BIGINT | 250,588 | 0.0% | 6,559 |
| patients_augmented | visits_span_days | BIGINT | 250,588 | 0.0% | 5,635 |
| patients_augmented | dx_age_years | DOUBLE | 35,890 | 85.7% | 3,758 |
| patients_augmented | dx_age_years_e03_9 | DOUBLE | 309 | 99.9% | 283 |
| patients_augmented | dx_age_years_e10 | DOUBLE | 491 | 99.8% | 468 |
| patients_augmented | dx_age_years_e22_0 | DOUBLE | 3 | 100.0% | 3 |
| patients_augmented | dx_age_years_e23_0 | DOUBLE | 150 | 99.9% | 148 |
| patients_augmented | dx_age_years_e23_6 | DOUBLE | 31 | 100.0% | 31 |
| patients_augmented | dx_age_years_e24 | DOUBLE | 1 | 100.0% | 1 |
| patients_augmented | dx_age_years_e30_0 | DOUBLE | 419 | 99.8% | 365 |
| patients_augmented | dx_age_years_e30_1 | DOUBLE | 3,405 | 98.6% | 1,969 |
| patients_augmented | dx_age_years_e34_3 | DOUBLE | 447 | 99.8% | 418 |
| patients_augmented | dx_age_years_e34_4 | DOUBLE | 83 | 100.0% | 82 |
| patients_augmented | dx_age_years_e72_11 | DOUBLE | 1 | 100.0% | 1 |
| patients_augmented | dx_age_years_k50 | DOUBLE | 113 | 100.0% | 113 |
| patients_augmented | dx_age_years_k51 | DOUBLE | 62 | 100.0% | 60 |
| patients_augmented | dx_age_years_k90_0 | DOUBLE | 898 | 99.6% | 799 |
| patients_augmented | dx_age_years_n18 | DOUBLE | 70 | 100.0% | 69 |
| patients_augmented | dx_age_years_n25_0 | DOUBLE | 1 | 100.0% | 1 |
| patients_augmented | dx_age_years_p04_3 | DOUBLE | 53 | 100.0% | 41 |
| patients_augmented | dx_age_years_p05 | DOUBLE | 4,069 | 98.4% | 384 |
| patients_augmented | dx_age_years_p07 | DOUBLE | 11,014 | 95.6% | 973 |
| patients_augmented | dx_age_years_p70 | DOUBLE | 3,353 | 98.7% | 96 |
| patients_augmented | dx_age_years_p92_6 | DOUBLE | 14,428 | 94.2% | 222 |
| patients_augmented | dx_age_years_q77 | DOUBLE | 15 | 100.0% | 14 |
| patients_augmented | dx_age_years_q78_0 | DOUBLE | 10 | 100.0% | 10 |
| patients_augmented | dx_age_years_q78_1 | DOUBLE | 2 | 100.0% | 2 |
| patients_augmented | dx_age_years_q87_1 | DOUBLE | 58 | 100.0% | 57 |
| patients_augmented | dx_age_years_q87_2 | DOUBLE | 32 | 100.0% | 31 |
| patients_augmented | dx_age_years_q87_3 | DOUBLE | 46 | 100.0% | 45 |
| patients_augmented | dx_age_years_q87_4 | DOUBLE | 17 | 100.0% | 17 |
| patients_augmented | dx_age_years_q90 | DOUBLE | 205 | 99.9% | 109 |
| patients_augmented | dx_age_years_q96 | DOUBLE | 36 | 100.0% | 27 |
| patients_augmented | dx_age_years_q98_0 | DOUBLE | 26 | 100.0% | 17 |
| patients_augmented | dx_age_years_q98_4 | DOUBLE | 42 | 100.0% | 29 |
| patients_augmented | dx_age_years_q98_5 | DOUBLE | 17 | 100.0% | 13 |
| patients_augmented | count_weight_z_score | BIGINT | 250,588 | 0.0% | 174 |
| patients_augmented | mean_weight_z_score | DOUBLE | 250,577 | 0.0% | 45,164 |
| patients_augmented | std_weight_z_score | DOUBLE | 249,595 | 0.4% | 15,604 |
| patients_augmented | min_weight_z_score | DOUBLE | 250,577 | 0.0% | 47,190 |
| patients_augmented | max_weight_z_score | DOUBLE | 250,577 | 0.0% | 47,420 |
| patients_augmented | count_height_z_score | BIGINT | 250,588 | 0.0% | 97 |
| patients_augmented | mean_height_z_score | DOUBLE | 250,261 | 0.1% | 41,024 |
| patients_augmented | std_height_z_score | DOUBLE | 248,172 | 1.0% | 14,332 |
| patients_augmented | min_height_z_score | DOUBLE | 250,261 | 0.1% | 42,098 |
| patients_augmented | max_height_z_score | DOUBLE | 250,261 | 0.1% | 38,259 |
| patients_augmented | count_bmi_z_score | BIGINT | 250,588 | 0.0% | 92 |
| patients_augmented | mean_bmi_z_score | DOUBLE | 213,053 | 15.0% | 46,476 |
| patients_augmented | std_bmi_z_score | DOUBLE | 199,693 | 20.3% | 15,234 |
| patients_augmented | min_bmi_z_score | DOUBLE | 213,053 | 15.0% | 50,618 |
| patients_augmented | max_bmi_z_score | DOUBLE | 213,053 | 15.0% | 47,254 |
| patients_augmented | count_head_circ_z_score | BIGINT | 250,588 | 0.0% | 30 |
| patients_augmented | mean_head_circ_z_score | DOUBLE | 200,584 | 20.0% | 46,033 |
| patients_augmented | std_head_circ_z_score | DOUBLE | 188,063 | 25.0% | 23,188 |
| patients_augmented | min_head_circ_z_score | DOUBLE | 200,584 | 20.0% | 31,399 |
| patients_augmented | max_head_circ_z_score | DOUBLE | 200,584 | 20.0% | 36,528 |
| patients_augmented | count_weight_for_length_z_score | BIGINT | 250,588 | 0.0% | 61 |
| patients_augmented | mean_weight_for_length_z_score | DOUBLE | 220,449 | 12.0% | 42,565 |
| patients_augmented | std_weight_for_length_z_score | DOUBLE | 207,992 | 17.0% | 18,775 |
| patients_augmented | min_weight_for_length_z_score | DOUBLE | 220,449 | 12.0% | 42,518 |
| patients_augmented | max_weight_for_length_z_score | DOUBLE | 220,449 | 12.0% | 38,600 |
| patients_augmented | count_weight_for_stature_z_score | BIGINT | 250,588 | 0.0% | 63 |
| patients_augmented | mean_weight_for_stature_z_score | DOUBLE | 215,154 | 14.1% | 45,654 |
| patients_augmented | std_weight_for_stature_z_score | DOUBLE | 203,194 | 18.9% | 15,593 |
| patients_augmented | min_weight_for_stature_z_score | DOUBLE | 215,154 | 14.1% | 39,544 |
| patients_augmented | max_weight_for_stature_z_score | DOUBLE | 215,154 | 14.1% | 38,957 |
| visits | patient_id | VARCHAR | 6,494,473 | 0.0% | 250,588 |
| visits | visit_id | VARCHAR | 6,494,473 | 0.0% | 6,494,473 |
| visits | age_in_days | BIGINT | 6,494,473 | 0.0% | 6,563 |
| visits | encounter_type | VARCHAR | 6,494,473 | 0.0% | 45 |
| visits | orig_enc_source_Epic_yn | VARCHAR | 6,494,473 | 0.0% | 2 |
| visits | weight_oz | DOUBLE | 6,488,028 | 0.1% | 24,694 |
| visits | height_in | DOUBLE | 3,509,633 | 46.0% | 4,836 |
| visits | head_circ_cm | DOUBLE | 1,635,690 | 74.8% | 2,394 |
| visits | BMI | DOUBLE | 3,658,303 | 43.7% | 8,216 |
| visits | bmi_percentile | DOUBLE | 2,961,185 | 54.4% | 10,001 |
| visits | enc_diag_1..33 | VARCHAR | 6,154,801 | 5.2% | 6,892 |
| visits_augmented | patient_id | VARCHAR | 6,494,473 | 0.0% | 250,588 |
| visits_augmented | visit_id | VARCHAR | 6,494,473 | 0.0% | 6,494,473 |
| visits_augmented | sex | VARCHAR | 6,494,473 | 0.0% | 3 |
| visits_augmented | ethnicity | VARCHAR | 5,401,217 | 16.8% | 2 |
| visits_augmented | race_1 | VARCHAR | 5,423,318 | 16.5% | 7 |
| visits_augmented | age_in_days | BIGINT | 6,494,473 | 0.0% | 6,563 |
| visits_augmented | age_in_months | DOUBLE | 6,494,473 | 0.0% | 6,563 |
| visits_augmented | age_in_years | DOUBLE | 6,494,473 | 0.0% | 6,563 |
| visits_augmented | weight_oz | DOUBLE | 6,488,028 | 0.1% | 24,694 |
| visits_augmented | weight_kg | DOUBLE | 6,483,007 | 0.2% | 20,665 |
| visits_augmented | weight_outlier_flag | BIGINT | 6,488,028 | 0.1% | 2 |
| visits_augmented | delta_weight_kg | DOUBLE | 5,754,032 | 11.4% | 5,530 |
| visits_augmented | delta_age_in_days_weight | BIGINT | 5,754,032 | 11.4% | 3,424 |
| visits_augmented | weight_velocity | DOUBLE | 5,754,032 | 11.4% | 6,449 |
| visits_augmented | weight_z_score | DOUBLE | 6,482,932 | 0.2% | 81,802 |
| visits_augmented | weight_percentile | DOUBLE | 6,482,932 | 0.2% | 10,001 |
| visits_augmented | weight_for_length_z_score | DOUBLE | 2,027,317 | 68.8% | 70,036 |
| visits_augmented | weight_for_length_percentile | DOUBLE | 2,027,317 | 68.8% | 10,001 |
| visits_augmented | weight_for_stature_z_score | DOUBLE | 1,371,347 | 78.9% | 62,664 |
| visits_augmented | weight_for_stature_percentile | DOUBLE | 1,371,347 | 78.9% | 10,001 |
| visits_augmented | wasting_flag | BIGINT | 6,494,473 | 0.0% | 2 |
| visits_augmented | height_in | DOUBLE | 3,509,633 | 46.0% | 4,836 |
| visits_augmented | height_cm | DOUBLE | 3,491,662 | 46.2% | 4,568 |
| visits_augmented | height_outlier_flag | BIGINT | 3,509,633 | 46.0% | 2 |
| visits_augmented | delta_height_cm | DOUBLE | 2,786,770 | 57.1% | 2,683 |
| visits_augmented | delta_age_in_days_height | BIGINT | 2,786,770 | 57.1% | 3,135 |
| visits_augmented | height_velocity | DOUBLE | 2,786,770 | 57.1% | 6,653 |
| visits_augmented | height_velocity_z_score | DOUBLE | 1,127,289 | 82.6% | 78,625 |
| visits_augmented | height_velocity_z_score_ep | DOUBLE | 977,101 | 85.0% | 90,660 |
| visits_augmented | height_velocity_z_score_ap | DOUBLE | 960,949 | 85.2% | 78,394 |
| visits_augmented | height_velocity_z_score_lp | DOUBLE | 961,074 | 85.2% | 91,509 |
| visits_augmented | height_velocity_percentile | DOUBLE | 1,127,289 | 82.6% | 10,001 |
| visits_augmented | height_velocity_percentile_ep | DOUBLE | 977,101 | 85.0% | 10,001 |
| visits_augmented | height_velocity_percentile_ap | DOUBLE | 960,949 | 85.2% | 10,001 |
| visits_augmented | height_velocity_percentile_lp | DOUBLE | 961,074 | 85.2% | 10,001 |
| visits_augmented | height_z_score | DOUBLE | 3,491,616 | 46.2% | 62,757 |
| visits_augmented | height_percentile | DOUBLE | 3,491,616 | 46.2% | 9,988 |
| visits_augmented | stunting_flag | BIGINT | 6,494,473 | 0.0% | 2 |
| visits_augmented | head_circ_cm | DOUBLE | 1,635,690 | 74.8% | 2,394 |
| visits_augmented | head_circ_z_score | DOUBLE | 1,635,640 | 74.8% | 66,115 |
| visits_augmented | head_circ_percentile | DOUBLE | 1,635,640 | 74.8% | 10,001 |
| visits_augmented | bmi | DOUBLE | 1,955,339 | 69.9% | 380,344 |
| visits_augmented | bmi_z_score | DOUBLE | 1,955,337 | 69.9% | 71,202 |
| visits_augmented | bmi_percentile | DOUBLE | 1,955,337 | 69.9% | 10,001 |
| visits_augmented | bmi_category | VARCHAR | 1,955,337 | 69.9% | 4 |
| visits_augmented | underweight_flag | BIGINT | 6,494,473 | 0.0% | 2 |
| visits_augmented | obesity_flag | BIGINT | 6,494,473 | 0.0% | 2 |
| visits_augmented | encounter_type | VARCHAR | 6,494,473 | 0.0% | 45 |
| visits_augmented | orig_enc_source_Epic_yn | VARCHAR | 6,494,473 | 0.0% | 2 |
| visits_augmented | enc_diag_1..33 | VARCHAR | 6,154,801 | 5.2% | 6,892 |
| labs | patient_id | VARCHAR | 17,230,681 | 0.0% | 247,271 |
| labs | visit_id | VARCHAR | 17,229,876 | 0.0% | 2,859,084 |
| labs | lab_order_id | VARCHAR | 17,230,681 | 0.0% | 6,578,838 |
| labs | result_line_num | BIGINT | 14,947,495 | 13.3% | 149 |
| labs | lab_order_date_age_in_days | BIGINT | 17,230,681 | 0.0% | 6,578 |
| labs | lab_procedure_name | VARCHAR | 17,230,681 | 0.0% | 3,742 |
| labs | lab_procedure_description | VARCHAR | 17,230,681 | 0.0% | 18,834 |
| labs | lab_result_date_age_in_days | BIGINT | 14,947,495 | 13.3% | 6,613 |
| labs | result_component_name | VARCHAR | 14,947,495 | 13.3% | 12,902 |
| labs | result_loinc_code | VARCHAR | 1,350,102 | 92.2% | 2,194 |
| labs | result_value | VARCHAR | 14,736,420 | 14.5% | 104,312 |
| labs | result_flag | VARCHAR | 1,679,696 | 90.3% | 35 |
| medications | patient_id | VARCHAR | 3,823,049 | 0.0% | 236,323 |
| medications | visit_id | VARCHAR | 3,823,049 | 0.0% | 2,757,560 |
| medications | med_record_id | VARCHAR | 3,823,049 | 0.0% | 3,823,049 |
| medications | med_order_date_age_in_days | BIGINT | 3,823,049 | 0.0% | 6,605 |
| medications | med_start_date_age_in_days | BIGINT | 3,539,983 | 7.4% | 6,644 |
| medications | med_end_date_age_in_days | BIGINT | 3,372,709 | 11.8% | 6,939 |
| medications | med_record_type | VARCHAR | 3,823,049 | 0.0% | 2 |
| medications | med_simple_generic_name | VARCHAR | 3,823,049 | 0.0% | 1,073 |
| problem_list | patient_id | VARCHAR | 1,709,584 | 0.0% | 238,823 |
| problem_list | problem_list_id | VARCHAR | 1,709,584 | 0.0% | 1,709,584 |
| problem_list | noted_date_age_in_days | BIGINT | 1,702,300 | 0.4% | 6,930 |
| problem_list | resolved_date_age_in_days | BIGINT | 757,907 | 55.7% | 6,565 |
| problem_list | pl_diag | VARCHAR | 1,709,584 | 0.0% | 4,739 |
| referrals | patient_id | VARCHAR | 349,827 | 0.0% | 138,071 |
| referrals | visit_id | VARCHAR | 324,997 | 7.1% | 298,615 |
| referrals | referral_id | VARCHAR | 349,827 | 0.0% | 349,827 |
| referrals | referral_date_age_in_days | BIGINT | 349,827 | 0.0% | 6,535 |
| referrals | requested_specialty | VARCHAR | 322,375 | 7.8% | 119 |
| referrals | referral_number_of_visits | BIGINT | 323,226 | 7.6% | 6 |

## 7. Artifact catalogue

One row per known artifact, with its scale and whether it can be repaired.

### 7.1 Every artifact this report measured

One row per artifact, gathered from the findings that measured them. The class says who produced the artifact, which decides whether it can be repaired: a derivation artifact can be recomputed without touching the clinical record, a capture artifact cannot, a selection artifact is outside the extract entirely. 22 artifacts across 4 classes (capture, derivation, linkage, selection).

**Artifact catalogue**

| artifact | class | scale in this snapshot | recoverable? | section |
| --- | --- | --- | --- | --- |
| Raw and augmented BMI disagree on infants | derivation | 1,703,005 visits carry a raw BMI the augmented layer withholds; 536 differ outright | Yes — pick the layer deliberately and state which | 1.3 |
| Cohort selected on growth-measurement density and code rarity | selection | 437,996 registry members reduced to 250,588; 61% of diagnosis codes, 56% of medications and 72% of lab procedures removed with their patients | No — the excluded patients are not in this extract | 1.4 |
| A patient-day can carry more than one visit | capture | 5,478 patient-days holding 11,040 visits, the rows 3.8 finds disagreeing and four Part 4 sections deduplicate | Partly — define an explicit tie rule before ordering by age | 3.1 |
| Populated visit_id that resolves to no visit | linkage | up to 42% of populated values in a resource | No — treat visit linkage as partial by design | 3.2 |
| Age fields that violate their own ordering | capture | lab result before order, and medication start before order | No — do not treat differences between them as durations | 3.3 |
| Laboratory results are semi-structured text | capture | 487,168 comparator-prefixed values; only 44.2% of rows parse as a number | Yes — parse comparators explicitly rather than casting | 3.6 |
| Anthropometrics recorded on encounters with no physical contact | capture | weight present on 99% of 22,053 telephone encounters | Partly — restrict by encounter type before counting measurement occasions | 3.7 |
| Two measurements of one channel on one patient-day that disagree | capture | 942 patient-days for height, median spread 3.17 cm | Partly — define an explicit tie rule before ordering by age | 3.8 |
| Diagnosis codes counted flat rather than as a hierarchy | capture | 1,203 of 1,326 categories never appear as a bare three-character code | Yes — match on a prefix, or roll up before counting | 3.9 |
| Terminal-digit heaping on the imperial recording grid | capture | 80.0% of heights fall on a quarter inch | No — it is the precision the measurement actually has | 4.2 |
| Wrong-unit and decimal-place entry in the typed measurement fields | capture | 1,371 whole-foot heights, 143 centimetre values in the inch field, and a weight decimal artifact enriched 17-fold | Yes — bound and repair the raw imperial columns before converting | 4.4 |
| Apparent height loss from the recording grid on a flat trajectory | capture | 0.66% of pairs over a year apart, falling to 0.083% at ages 2 to 10 | Not a defect — do not filter it as an outlier | 4.5 |
| Height z-score truncated above at +3 while the lower tail runs to -5 | derivation | 21 visits at or above +3 where roughly 15,800 would be expected | Yes — recompute from the retained raw height | 4.6 |
| Head circumference passed through an inch-to-centimetre conversion a second time | derivation | 13,467 visits, 90% of all out-of-range values | Yes — divide by 2.54 before applying a plausible range, rather than deleting | 4.7 |
| Velocity computed over an age-dependent minimum interval, not between adjacent visits | derivation | 99.99% of height deltas reproduced under the interval rule against 43.7% under a naive lag; the two published columns regenerate only 72.3% of the velocity | Not a defect — carry the interval rule, the year length and the unrounded measurement alongside the field | 4.8 |
| Diagnosis label precedes the growth trajectory it would be predicted from | selection | 51% of labelled patients have no height recorded before their diagnosis | No — use a different label or a different index date | 5.9 |
| A derived flag that is disjoint from the diagnosis flag by construction | derivation | healthy_flag is set for 0.0% of growth-diagnosed patients | Yes — define the negative class explicitly instead | 5.10 |
| Treatment and workup records reveal the diagnosis, and date it a decade later than the code | capture | growth hormone is 5.1 times enriched for the label; its median order age is 10.8 years against 0.027 for the code | Yes — exclude them as features, or index on them instead | 5.11 |
| A diagnosis code's resource coverage depends on the code | capture | 36% of patient-code pairs appear only in encounter diagnoses and 14% only in the problem list | Yes — take the union of both resources, as the derived columns do | 5.12 |
| A growth diagnosis recorded at the referral rather than before it | capture | 36% of endocrinology-referred labelled patients carry the code within 30 days of the referral | No — but the subgroup it marks is the usable one | 5.13 |
| A derived column that is a function of the label | derivation | `visits_count_pre_dx` recovers `growth_dx_flag` at 100.0% precision and 99.7% recall | No — the column cannot be made label-free; exclude it | 5.14 |
| Contact intensity separates the label without measuring the child | derivation | visits per year of record ranks a labelled patient above an unlabelled one 0.664 of the time, against 0.488 for lifetime visit count | Yes — fix a common index date and observation window, or exclude the record-shape columns | 5.15 |

## 8. Methods and limitations

How these figures were computed and what would invalidate them.

### 8.1 Methods, determinism, and limitations

**Computation.** Every figure was computed with DuckDB against the typed bundle of `ppoc-pediatric-ehr` 1.0.0, snapshot `2026-08-24`, sha256 `425c6f873cefc149344570561a03b33c69a6a6af7fa18bc777c0429579507116`, opened read-only. The bundle is never copied into this repository and no row-level identifier is read into any output.

**Privacy.** Output is aggregate only. Cells backed by fewer than 10 records are suppressed centrally rather than probe by probe, so a new probe inherits the rule without having to remember it.

**Reproducibility.** The generator computes the finding set once and renders every output from it, so the HTML, the PDF, the Markdown mirror, and `findings.json` cannot disagree. Prose carries templates rather than literals: a number reaches an output only by way of the finding that measured it. Outputs are rewritten only when the finding set changes, so rebuilding an unchanged snapshot leaves the committed files untouched.

**Limitations.** Everything here is specific to this snapshot and would need recomputing for another extract. The report describes recording and derivation behaviour, not clinical truth: a value being implausible does not establish what the child actually measured, and a value being plausible does not establish that it was measured at all. Where a mechanism is inferred rather than observed the report says so and shows the evidence.
