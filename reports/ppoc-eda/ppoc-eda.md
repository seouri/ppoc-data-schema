# PPOC pediatric EHR snapshot: an exploratory data analysis

A project-neutral reference for anyone analysing this extract. Every figure is measured from the delivered bundle; the report states what the data support, what they do not, and which checks this extract cannot answer at all.

## 0. How to use this report

Three ways in, depending on what you came for.

### 0.1 Three ways in

This report describes one snapshot of one pediatric primary-care EHR extract. It belongs to no project: it states what the data are, what they support, and what they cannot answer, and it leaves the research question to you.

**Where to start**

| if you are | start here |
| --- | --- |
| New to this extract | Read Part 1, then the not-applicable table in Part 2. Twenty minutes, and it will save days. |
| About to use a specific field | Find it in the Part 6 field index, then follow the finding it links to. |
| Explaining a number that looks wrong | Check the Part 7 artifact catalogue before assuming a bug in your code. |
| Planning a study | Part 1.4 first. The cohort selection invalidates several whole classes of question, and it is not visible in any field. |

Every number here was measured from the delivered bundle for snapshot `2026-08-24`; none is copied from another document without being recomputed. The cohort is pinned to 31 Dec 2024 and the extract was cut on 03 Feb 2025.

**What this report is not.** It is not a clinical validation, not a registered analysis, and not a statement about any individual child. Every figure is an aggregate, and any cell resting on fewer than 10 records is suppressed.

## 1. The snapshot

What this extract contains, how it was built, and what its construction forecloses.

### 1.1 Package identity and integrity

Everything in this report was computed from the typed DuckDB bundle of package `ppoc-pediatric-ehr` 1.0.0, snapshot `2026-08-24`, sha256 `425c6f873cefc149344570561a03b33c69a6a6af7fa18bc777c0429579507116`. The bundle is opened read-only and is never copied into this repository.

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

The extract is 8 tables carrying 254 columns between them. Grain matters more than row count here: three of the resources are keyed on something other than the patient or the visit, and one of them needs two columns to be unique.

**The eight resources**

| resource | rows | cols | grain | primary key | links to |
| --- | --- | --- | --- | --- | --- |
| patients | 250,588 | 11 | one row per patient | patient_id | — |
| patients_augmented | 250,588 | 87 | one row per patient | patient_id | patients |
| visits | 6,494,473 | 43 | one row per patient per encounter | visit_id | patients |
| visits_augmented | 6,494,473 | 82 | one row per patient per encounter | visit_id | visits |
| labs | 17,230,681 | 12 | one row per resulted component of a lab order | lab_order_id + result_line_num | patients; visits (partial) |
| medications | 3,823,049 | 8 | one row per medication order or historical record | med_record_id | patients; visits (partial) |
| problem_list | 1,709,584 | 5 | one row per problem-list entry | problem_list_id | patients |
| referrals | 349,827 | 6 | one row per referral order | referral_id | patients; visits (partial) |

`visit_id` on labs, medications, and referrals is a partial link by design, not a defect: an order placed outside a visit carries an identifier that resolves to no encounter in this extract. Section 3.2 measures how partial.

### 1.3 The two layers, and where they disagree

Every visit and every patient appears twice: once in the raw extract as PPOC delivered it, and once in an augmented layer that adds CDC-derived z-scores, percentiles, velocities, and flags. Where a field exists in both, the two should agree. Across all 6,494,473 joined visit rows, five of the six shared fields do.

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

**Implications for analysis.** Reading `visits.BMI` silently yields infant BMI values that the augmented layer deliberately suppresses, and the two layers will not reproduce each other's descriptive statistics. Choose a layer for a stated reason and record which; do not mix them within one analysis. The 536 rows where both are present and disagree are small enough to screen individually.

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

One qualification, because "no calendar axis" is easy to overstate: the cohort itself is pinned to 31 Dec 2024 and the extract was cut shortly after. Ages are relative to each child's birth, but the *window* is fixed and known, which is what makes the recency criterion in 1.4 a right-censoring rule rather than an unknown.

## 2. Checklist coverage

Every item of the general EHR EDA checklist, mapped to what this snapshot can and cannot support.

### 2.1 The checklist, item by item

This part exists so that nobody has to wonder whether a standard check was skipped or was impossible. Of 44 items in the general EHR exploratory-analysis checklist, 31 are covered here, 4 are partially covered, and 9 cannot be run against this extract at all.

**Checklist coverage**

| checklist section | item | status | where, or why not |
| --- | --- | --- | --- |
| 0 Provenance | Extraction window | covered | Cohort and extract dates recovered from the delivery documents — 1.4 |
| 0 Provenance | Inclusion/exclusion logic | covered | The full four-step funnel — 1.4 |
| 0 Provenance | Vendor, version, migration events | covered | Epic against converted legacy records — 3.7 |
| 0 Provenance | Data dictionary present | covered | Committed under docs/, reconciled field by field — 1.1 |
| 0 Provenance | Raw vs CDM vs custom extract | covered | A custom extract plus a derived augmentation layer — 1.3 |
| 1 Structural | Row and table counts | covered | Against the manifest and the vendor's own counts — 1.1 |
| 1 Structural | Primary key uniqueness | covered | All eight resources — 3.1 |
| 1 Structural | Referential integrity | covered | 3.2 |
| 1 Structural | Duplicate patient detection | not applicable | No name, birth date, or linkage key survives de-identification — 1.5 |
| 1 Structural | Schema drift | covered | Live schema against the dictionary; three documented fields absent — 1.1 |
| 1 Structural | Grain per table | covered | Including that patient and age is not unique in visits — 3.1 |
| 2 Temporal | Timestamp semantics | covered | 3.3 |
| 2 Temporal | Impossible sequences | covered | 3.3 |
| 2 Temporal | Batch-entry clustering | not applicable | Ages are integer days; there is no time of day — 1.5 |
| 2 Temporal | System downtime gaps | not applicable | No calendar axis — 1.5 |
| 2 Temporal | Coding or vendor transition | partial | Epic against converted is computable; ICD-9 to ICD-10 is not, without dates |
| 2 Temporal | Age sanity | covered | 3.3 |
| 3 Missingness | Missingness per field | covered | 3.4 and the field index |
| 3 Missingness | Missingness pattern | covered | By age, sex, and encounter — 3.4 |
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

Every declared primary key holds. The labs resource needs all three of its declared columns to be unique, which is worth stating because joining on order and component alone will multiply rows.

**Declared keys, measured**

| resource | key | rows | distinct keys | unique |
| --- | --- | --- | --- | --- |
| patients | patient_id | 250,588 | 250,588 | yes |
| patients_augmented | patient_id | 250,588 | 250,588 | yes |
| visits | visit_id | 6,494,473 | 6,494,473 | yes |
| visits_augmented | visit_id | 6,494,473 | 6,494,473 | yes |
| medications | med_record_id | 3,823,049 | 3,823,049 | yes |
| problem_list | problem_list_id | 1,709,584 | 1,709,584 | yes |
| referrals | referral_id | 349,827 | 349,827 | yes |
| labs | lab_order_id + component + line | 17,230,681 | 17,230,681 | yes |

What is *not* a key is the combination a longitudinal analysis reaches for first. 5,478 patient-days (0.08% of 6,488,911) carry more than one visit, covering 11,040 visit rows (0.17% of all visits). `age_in_days` is therefore not unique within a patient.

**Implications for analysis.** Any trajectory ordered by age alone has ties, and any window function partitioned by patient and ordered by age will resolve them arbitrarily unless you say how. Decide whether to take the first row, the mean, or the non-null value, and apply it before the analysis rather than inside it.

### 3.2 Referential integrity and cross-resource linkage

`patient_id` resolves everywhere. `visit_id` does not, and the shortfall is large enough that treating it as a complete foreign key will quietly drop or duplicate rows.

**Visit linkage by resource**

| resource | rows | visit_id null | populated but unresolved | share of populated | unresolved patient_id |
| --- | --- | --- | --- | --- | --- |
| labs | 17,230,681 | 0.00% | 5,201,657 | 30.19% | 0 |
| medications | 3,823,049 | 0.00% | 1,592,437 | 41.65% | 0 |
| referrals | 349,827 | 7.10% | 98,623 | 30.35% | 0 |

This is documented behaviour rather than corruption. The data dictionary states for each of these resources that the visit link "may not match to all" when the order was placed or the record documented outside a visit. The trap is that the column is populated on nearly every row, so a required-looking key silently fails to join.

**Implications for analysis.** Join to visits with an explicit outer join and count what fails, rather than an inner join that hides the loss. Anything computed per visit — encounter type, visit-level anthropometrics — is unavailable for the unresolved share, and that share is not random: it concentrates in orders placed outside encounters.

### 3.3 Age-axis consistency and impossible sequences

Age in days is the only clock, so ordering violations within a resource are visible directly. Counts below 10 are suppressed.

**Ordering and range checks**

| check | violating rows | rows checked | share |
| --- | --- | --- | --- |
| Lab result age earlier than lab order age | 583,055 | 14,947,495 | 3.901% |
| Medication start age earlier than order age | 329,107 | 3,539,983 | 9.297% |
| Medication end age earlier than start age | 12,709 | 3,179,759 | 0.400% |
| Problem resolved age earlier than noted age | 0 | 754,996 | 0.000% |
| Problem noted before birth | 650 | 1,702,300 | 0.038% |
| Lab ordered before birth | 47 | 17,230,681 | 0.000% |
| Medication ordered before birth | — | 3,823,049 | — |
| Visit recorded before birth | 0 | 6,494,473 | 0.000% |

An em dash in the violating-rows column means the count is nonzero but below the suppression threshold.

The lab and medication violations are the substantial ones, and both are documented at source. For a historically documented medication the order date is the date the record was *written*, not when the drug was started, and a charted approximation such as a month with no day is stored as the first of that month. End dates may sit in the future while a medication is active. Lab result and order ages derive from different source timestamps.

**Implications for analysis.** Differences between two age fields in these resources are not reliable durations. Where you need an interval, take it from a single field across rows rather than between two fields on one row, and exclude historically documented medication records from any start-to-end calculation.

### 3.4 Missingness, by field and by age

Population was measured for all 176 columns in the extract, counting the repeated diagnosis and race families once each. 0 columns are entirely empty. The full table is Part 6; the sixteen least-populated columns are below.

**The least-populated columns**

| resource | field | populated rows | missing |
| --- | --- | --- | --- |
| patients_augmented | dx_age_years_e24 | 1 | 100.0% |
| patients_augmented | dx_age_years_e72_11 | 1 | 100.0% |
| patients_augmented | dx_age_years_n25_0 | 1 | 100.0% |
| patients_augmented | dx_age_years_q78_1 | 2 | 100.0% |
| patients_augmented | dx_age_years_e22_0 | 3 | 100.0% |
| patients_augmented | dx_age_years_q78_0 | 10 | 100.0% |
| patients_augmented | dx_age_years_q77 | 15 | 100.0% |
| patients_augmented | dx_age_years_q87_4 | 17 | 100.0% |
| patients_augmented | dx_age_years_q98_5 | 17 | 100.0% |
| patients_augmented | dx_age_years_q98_0 | 26 | 100.0% |
| patients_augmented | dx_age_years_e23_6 | 31 | 100.0% |
| patients_augmented | dx_age_years_q87_2 | 32 | 100.0% |
| patients_augmented | dx_age_years_q96 | 36 | 100.0% |
| patients_augmented | dx_age_years_q98_4 | 42 | 100.0% |
| patients_augmented | dx_age_years_q87_3 | 46 | 100.0% |
| patients_augmented | dx_age_years_p04_3 | 53 | 100.0% |

A single missingness rate hides the thing that matters most for a longitudinal extract: whether a field is missing *at random* or missing *by age*. For the measurement channels it is emphatically the latter.

*Figure — Share of visits carrying each measurement, by age band. Rendered in `index.html` at `#fig-missing-age`.*

**Implications for analysis.** Head circumference is an infant measurement and effectively disappears after age 2; BMI and its percentile are withheld below age 2 by the augmentation; height is recorded far less often than weight at every age. Any cohort defined by "has a complete measurement row" is therefore an age-selected cohort, and any model that drops incomplete rows inherits that selection. Report availability by age band before interpreting any age-stratified contrast.

### 3.5 Nulls that are not missing, and sentinels that are not data

Two of the largest null populations in this extract are not missing data at all, and reading them as missing throws away the majority of the signal in their columns.

**Laboratory result flags**

| result_flag | rows | meaning |
| --- | --- | --- |
| null | 15,550,985 | normal result |
| Abnormal | 704,327 | abnormal |
| High | 513,650 | abnormal |
| Low | 361,300 | abnormal |
| Sensitive | 62,794 | abnormal |
| Resistant | 10,278 | abnormal |
| High Panic | 9,744 | abnormal |
| (NONE) | 5,881 | abnormal |

The data dictionary defines `result_flag` as an HL7 abnormality category in which the value `(NONE)` means a normal result and anything else means abnormal. This extract contains 5,881 literal `(NONE)` values and 15,550,985 nulls — 90.3% of all lab rows. The sentinel became a null somewhere between the source system and delivery, so **a null flag means normal, not unknown**.

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

**Implications for analysis.** Never impute or drop on `result_flag` or `resolved_date_age_in_days` nullity. An abnormal-result rate computed as "non-null flags over non-null flags" will read as 100%; the correct denominator is all resulted rows. A problem-list resolution rate must count nulls as unresolved rather than excluding them.

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

Laboratory results are the opposite case. `result_value` is a text column: of 17,230,681 rows, 7,621,449 (44.2%) parse as a number and 2,494,261 (14.5%) are empty. Among the rest, 487,168 are censored results carrying a comparator prefix, and the remainder are qualitative results, specimen descriptors, and administrative non-results. A LOINC code is present on only 7.8% of rows.

The declared key holds, but 33,879 order-and-component pairs appear on more than one result line and 23,679 of those (69.9%) carry disagreeing values. The data dictionary records the cause: a result may fail to link back to its original order, which duplicates the record.

**Categorical vocabularies before and after normalising case and internal whitespace**

| resource | field | distinct values | after normalising | collapsed |
| --- | --- | --- | --- | --- |
| labs | lab_procedure_name | 3,742 | 3,739 | 3 |
| medications | med_simple_generic_name | 1,073 | 1,073 | 0 |
| referrals | requested_specialty | 119 | 119 | 0 |

**Implications for analysis.** A naive numeric cast on `result_value` silently discards more than half the populated values and turns a left-censored result into a missing one rather than a bound. Join labs on order, component *and* line number, or the duplicate lines will multiply rows and pick a value arbitrarily. The categorical vocabularies barely collapse under normalisation, so grouping by them is safe after trimming.

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

Encounter types with fewer than 10,000 visits are omitted.

Telephone encounters carry a weight on 99.3% of 22,053 visits. A weight cannot be measured over the telephone, so those values were produced some other way — reported by a caregiver, carried from a nearby in-person encounter, or attached to an encounter whose type label does not describe how the patient was seen. Which of those it is cannot be determined from this extract.

**Recording completeness by source system**

| encounter source | visits | height present | first diagnosis |
| --- | --- | --- | --- |
| Epic | 4,149,865 | 51.4% | 99.7% |
| converted from a legacy system | 2,344,608 | 58.7% | 86.1% |

The source-system split is the migration signal. Records converted from the practice network's previous EHR carry a first diagnosis on only 86.1% of encounters, which the data dictionary anticipates: converted encounters may be missing diagnosis information depending on the quality of the conversion.

**Implications for analysis.** A visit-level indicator that a measurement is present is not evidence that a measurement was taken at that encounter. If your design counts measurement occasions — visit density, monitoring intensity, follow-up adherence — restrict to encounter types where physical measurement is possible rather than relying on presence. And any diagnosis-based rate computed across the whole extract mixes two populations with very different coding completeness.

## 4. Anthropometrics

The richest and most artifact-prone measurements in the extract.

### 4.1 Trajectory supply: how many heights each child has

250,267 of 250,588 patients (99.9%) carry at least one derived height, 235,651 (94.0%) carry five or more, and 182,037 (72.6%) carry ten or more.

*Figure — Patients retaining at least k height observations. Rendered in `index.html` at `#fig-supply`.*

**Height observations per patient**

| at least k heights | patients | share of cohort |
| --- | --- | --- |
| 1 | 250,267 | 99.9% |
| 3 | 245,449 | 97.9% |
| 5 | 235,651 | 94.0% |
| 10 | 182,037 | 72.6% |
| 15 | 104,838 | 41.8% |
| 20 | 43,501 | 17.4% |
| 25 | 16,040 | 6.4% |

**Implications for analysis.** Read this against 1.4 before treating it as a fact about pediatric care. Cohort entry required at least five growth measurements of *some* type, so a dense height series here is partly the selection rule and partly the underlying practice; the two cannot be separated within this extract. What the curve does support is a feasibility estimate: how many children remain if your design needs k observations.

### 4.2 Recording units and the measurement grid

Height and weight are captured in imperial units and the metric columns are exact conversions of them. The recorded values are heaped on human-readable fractions: of 3,509,633 heights, 31.0% fall on a whole inch, 54.9% on a half inch and 80.0% on a quarter inch. Of 6,488,028 weights, 54.4% fall on a whole ounce and 24.6% on a whole pound.

*Figure — Share of measurements falling on the coarse grid, by age. Rendered in `index.html` at `#fig-grid`.*

The two channels age in opposite directions. Height stays on its quarter-inch grid throughout childhood, while weight moves from ounce-level precision in infancy to whole pounds in adolescence, so the effective resolution of the weight channel degrades as children get older.

**Implications for analysis.** One quarter inch is 0.635 cm, and the derived `height_cm` carries two decimals it has not earned. Any change smaller than roughly half the rounding interval is not distinguishable from the rounding itself, which sets a floor on the smallest trajectory deflection that can be detected at all. State the assumed precision wherever a measurement is written out, and set detection thresholds at or above the grid.

### 4.3 Distributions and plausibility bounds

The four measurement channels, summarised on the derived metric columns. The final column counts values outside a conventional review range; those are reported, not removed, because the decision to exclude belongs to the analysis rather than to this report.

**Measurement channels**

| channel | unit | values | min | 1st pct | median | 99th pct | max | outside review range |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| height | cm | 3,491,662 | 37.47 | 48.26 | 92.71 | 173.41 | 196.60 | 0 |
| weight | kg | 6,483,007 | 0.01 | 2.81 | 14.52 | 78.65 | 513.92 | 217 |
| BMI | kg/m^2 | 1,955,339 | 8.12 | 13.29 | 16.70 | 32.42 | 219.51 | 44 |
| head circumference | cm | 1,635,690 | 0.00 | 33.00 | 44.00 | 53.00 | 505.46 | 13,742 |

*Figure — Distribution of height (cm). Rendered in `index.html` at `#fig-dist-height_cm`.*

*Figure — Distribution of weight (kg). Rendered in `index.html` at `#fig-dist-weight_kg`.*

*Figure — Distribution of BMI (kg/m^2). Rendered in `index.html` at `#fig-dist-bmi`.*

*Figure — Distribution of head circumference (cm). Rendered in `index.html` at `#fig-dist-head_circ_cm`.*

**Implications for analysis.** Head circumference is the channel whose tails are worst, and 4.4 shows why. For the others the extremes are sparse but the bulk is clinically ordinary. Bound the raw imperial columns rather than the derived metric ones when screening, since a wrong unit survives an exact conversion unchanged.

### 4.4 Transcription-error signatures in the typed fields

**Method.** Each measurement is anchored by linear interpolation between the same child's previous and next measurement. Both neighbours must themselves be plausible and span no more than four years, so a bad neighbour cannot manufacture an anomaly. A height is anomalous more than 3 inches from that anchor, a weight more than 50% from it. A mechanism *reconciles* an anomaly when applying it to the recorded value lands back at the anchor.

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

The dropped-digit row does not survive inspection, and it is worth showing why. Inserting a digit into a two-digit inch value always produces a three-digit one, which is never a plausible height, so the class can only fire on a value with a single-digit integer part. Among the 6,619 height anomalies whose integer part has two or more digits it reconciles 0. Its entire 5.47% is the whole-foot family reached by another route.

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

Transposition is again below chance, so neither channel shows evidence of digit swapping. A misplaced decimal point, which the height channel does not show at all, is the dominant weight artifact: 1,208 anomalies at 17 times the null rate, the strongest enrichment measured anywhere in this report. An ounce value has more digits than an inch value and no natural decimal point, so a factor of ten is both easy to key and hard to notice.

The calibration row is why the null is not optional. Allowing any single digit to be wrong reconciles about half of all height anomalies and reconciles almost exactly as many randomly paired values. Reported without a null it would look like the largest finding here.

**How strong is the transposition negative?** Only as strong as the share of transpositions the anomaly gate could have caught. Applying every adjacent digit swap to a sample of measurements in the testable interior gives that share directly: 69.7% of height swaps would displace a value past the gate, against 31.6% of weight swaps. The height negative is well powered; the weight negative rules out only large swaps, since a four-digit ounce value can absorb a swap without moving far.

**What the mechanisms account for**

| channel | anomalies | a named mechanism fits | only the calibration class | nothing fits |
| --- | --- | --- | --- | --- |
| height | 7,443 | 939 | 3,989 | 2,515 |
| weight | 6,196 | 1,987 | 742 | 3,467 |

**Implications for analysis.** Digit transposition can be dropped from the checklist for this extract at the magnitude that displaces a measurement from its own trajectory; for weight the same test is only about a third sensitive, so a small swap is not ruled out. Unit confusion and decimal placement do matter, and both are cheap to screen because both produce values implausible on their face. Bound `height_in` and `weight_oz` before any conversion, and check the recording grid rather than the value alone — the grid separates a tall adolescent from a centimetre in the wrong field where magnitude cannot. Note also that 1,371 of the whole-foot entries and 143 of the centimetre cluster already carry a null `height_cm`: the derived layer's own bound removes them as a side effect, so anyone reading the derived channels is protected and anyone reading the raw ones is not.

### 4.5 Repeated measurements: zero growth and apparent height loss

Children do not shrink, so a recorded decrease is recording behaviour rather than physiology. That much is easy. What matters is that the behaviour is not one thing, and the interval between measurements separates the mechanisms.

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

| age band (months) | pairs | any decrease | median loss | mean change |
| --- | --- | --- | --- | --- |
| 18-24 | 63,685 | 0.53% | 1.27 cm | 5.51 cm |
| 24-30 | 52,826 | 1.21% | 0.99 cm | 5.20 cm |
| 30-36 | 19,242 | 3.65% | 1.25 cm | 3.75 cm |
| 36-42 | 32,650 | 0.44% | 1.63 cm | 6.19 cm |
| 48-60 | 37,302 | 0.37% | 1.91 cm | 5.68 cm |
| 60-84 | 64,090 | 0.33% | 1.92 cm | 5.14 cm |
| 84-120 | 76,194 | 0.36% | 1.60 cm | 4.70 cm |
| 120-144 | 37,388 | 0.47% | 1.25 cm | 4.87 cm |
| 144-168 | 26,514 | 2.78% | 0.64 cm | 4.04 cm |
| 168-192 | 14,518 | 11.39% | 0.64 cm | 1.79 cm |
| 192-216 | 2,566 | 23.69% | 0.64 cm | 0.54 cm |

Two separate excesses, with different signatures. The first is a narrow spike at 30 to 36 months carrying a median loss of over a centimetre — the age at which recumbent length gives way to standing height, and a standing height genuinely is shorter than a recumbent length for the same child. It is a change of measurement protocol recorded in a field that does not name the protocol.

*Figure — Apparent loss in adolescence, by sex. Rendered in `index.html` at `#fig-loss-sex`.*

**Adolescent bands split by recorded sex**

| age band (months) | female pairs | female decrease | female mean change | male pairs | male decrease | male mean change |
| --- | --- | --- | --- | --- | --- | --- |
| 144-168 | 12,858 | 5.29% | 2.53 cm | 13,656 | 0.41% | 5.46 cm |
| 168-192 | 7,127 | 18.59% | 0.70 cm | 7,391 | 4.45% | 2.83 cm |
| 192-216 | 1,346 | 28.83% | 0.22 cm | 1,220 | 18.03% | 0.89 cm |

The second excess is the adolescent rise, and the sex split identifies it. Girls reach the high rates about two years before boys, in the same order as growth cessation, while the mean change over the same interval falls towards zero. Once annual growth drops below the recording grid, re-measuring a child who has stopped growing returns a lower value about as often as a higher one. Restricting to ages 2 to 10, where growth is unambiguously ongoing, collapses the long-interval decrease rate from 0.663% to 0.083% — 565 pairs of 681,114.

What survives both explanations divides again. Of 1,188 decreases over a centimetre across more than a year that are followed by a further measurement, 725 (61.0%) are followed by a value back at or above the earlier level, and 463 (39.0%) by one that stays below it. In the first the low value is the suspect; in the second it is corroborated and the earlier, higher measurement is the candidate error.

**Implications for analysis.** Most apparent shrinkage here is not error and should not be filtered as an outlier: it is the recording grid acting on a flattened trajectory, plus a protocol change at two to three years. A synthetic or smoothed trajectory that lacks both will not resemble this panel. Where a decrease does need adjudication, 39% of long-interval losses persist into the next measurement, so a rule that always discards the lower value is wrong on that share.

### 4.6 Derived z-scores and percentiles: bounds and saturation

The derived channels are not a neutral restatement of the measurements. Each carries its own support, and they do not share one.

**Z-score channels**

| channel | values | minimum | maximum | beyond |5| |
| --- | --- | --- | --- | --- |
| height z | 3,491,616 | -4.9992 | 3.0000 | 0 |
| weight z | 6,482,932 | -4.9991 | 4.9995 | 0 |
| BMI z | 1,955,337 | -18.7803 | 6.7026 | 400 |
| head circ z | 1,635,640 | -17,485.9115 | 306,212.5991 | 16,663 |
| weight-for-length z | 2,027,317 | -145.6016 | 7.6285 | 1,123 |
| weight-for-stature z | 1,371,347 | -14.3445 | 7.4762 | 246 |

The height z-score is bounded above at exactly 3.00 while its lower tail runs past -4.99. The truncation leaves no pile-up at the boundary, so it is invisible in a summary: only 21 visits sit at or above +3. The asymmetry is what exposes it. In the lower tail 45.4% of the mass beyond |z| = 2.5 continues past 3; if the upper tail behaved the same way roughly 15,800 visits would sit above +3.

*Figure — Height z-score, both tails. Rendered in `index.html` at `#fig-hz`.*

**Percentile channels and their saturation points**

| channel | values | exactly 0 | share | exactly 100 | share |
| --- | --- | --- | --- | --- | --- |
| height | 3,491,616 | 2,801 | 0.080% | 0 | 0.000% |
| weight | 6,482,932 | 3,584 | 0.055% | 5,221 | 0.081% |
| BMI | 1,955,337 | 1,599 | 0.082% | 1,590 | 0.081% |
| weight-for-length | 2,027,317 | 6,151 | 0.303% | 1,203 | 0.059% |
| weight-for-stature | 1,371,347 | 1,509 | 0.110% | 856 | 0.062% |

**Implications for analysis.** The height channel cannot support any question about tall stature: its upper tail is absent, and a trajectory approaching the bound from below is distorted too. The percentile channels carry point masses at exactly 0 and 100 that are saturated rather than measured, so they are not continuous and should not be modelled as such. Because the four z channels do not share a support, a model consuming several of them together inherits the inconsistency silently. Recomputing from the raw measurement against a stated reference avoids all of this.

## 6. Field index

Every column, with its population, range, and the findings that govern it.

### 6.1 Every column in the extract

All 176 distinct columns across the 8 resources, with how much of each is populated and how many values it takes. Repeated families — the 33 encounter-diagnosis slots and the 8 race slots — appear once each, summarised on their first member.

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
| visits_augmented | race_1..8 | VARCHAR | 5,423,318 | 16.5% | 7 |
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

One row per artifact, gathered from the findings that measured them. The class says who produced the artifact, which decides whether it can be repaired: a derivation artifact can be recomputed without touching the clinical record, a capture artifact cannot, a selection artifact is outside the extract entirely. 11 artifacts across 4 classes (capture, derivation, linkage, selection).

**Artifact catalogue**

| artifact | class | scale in this snapshot | recoverable? | section |
| --- | --- | --- | --- | --- |
| Raw and augmented BMI disagree on infants | derivation | 1,703,005 visits carry a raw BMI the augmented layer withholds; 536 differ outright | Yes — pick the layer deliberately and state which | 1.3 |
| Cohort selected on growth-measurement density and code rarity | selection | 437,996 registry members reduced to 250,588; 61% of diagnosis codes, 56% of medications and 72% of lab procedures removed with their patients | No — the excluded patients are not in this extract | 1.4 |
| A patient-day can carry more than one visit | capture | 5,478 patient-days holding 11,040 visits | Partly — define an explicit tie rule before ordering by age | 3.1 |
| Populated visit_id that resolves to no visit | linkage | up to 42% of populated values in a resource | No — treat visit linkage as partial by design | 3.2 |
| Age fields that violate their own ordering | capture | lab result before order, and medication start before order | No — do not treat differences between them as durations | 3.3 |
| Laboratory results are semi-structured text | capture | 487,168 comparator-prefixed values; only 44.2% of rows parse as a number | Yes — parse comparators explicitly rather than casting | 3.6 |
| Anthropometrics recorded on encounters with no physical contact | capture | weight present on 99% of 22,053 telephone encounters | Partly — restrict by encounter type before counting measurement occasions | 3.7 |
| Terminal-digit heaping on the imperial recording grid | capture | 80.0% of heights fall on a quarter inch | No — it is the precision the measurement actually has | 4.2 |
| Wrong-unit and decimal-place entry in the typed measurement fields | capture | 1,371 whole-foot heights, 143 centimetre values in the inch field, and a weight decimal artifact enriched 17-fold | Yes — bound and repair the raw imperial columns before converting | 4.4 |
| Apparent height loss from the recording grid on a flat trajectory | capture | 0.66% of pairs over a year apart, falling to 0.083% at ages 2 to 10 | Not a defect — do not filter it as an outlier | 4.5 |
| Height z-score truncated above at +3 while the lower tail runs to -5 | derivation | 21 visits at or above +3 where roughly 15,800 would be expected | Yes — recompute from the retained raw height | 4.6 |

## 8. Methods and limitations

How these figures were computed and what would invalidate them.

### 8.1 Methods, determinism, and limitations

**Computation.** Every figure was computed with DuckDB against the typed bundle of `ppoc-pediatric-ehr` 1.0.0, snapshot `2026-08-24`, sha256 `425c6f873cefc149344570561a03b33c69a6a6af7fa18bc777c0429579507116`, opened read-only. The bundle is never copied into this repository and no row-level identifier is read into any output.

**Privacy.** Output is aggregate only. Cells backed by fewer than 10 records are suppressed centrally rather than probe by probe, so a new probe inherits the rule without having to remember it.

**Reproducibility.** The generator computes the finding set once and renders every output from it, so the HTML, the PDF, the Markdown mirror, and `findings.json` cannot disagree. Prose carries templates rather than literals: a number reaches an output only by way of the finding that measured it. Outputs are rewritten only when the finding set changes, so rebuilding an unchanged snapshot leaves the committed files untouched.

**Limitations.** Everything here is specific to this snapshot and would need recomputing for another extract. The report describes recording and derivation behaviour, not clinical truth: a value being implausible does not establish what the child actually measured, and a value being plausible does not establish that it was measured at all. Where a mechanism is inferred rather than observed the report says so and shows the evidence.
