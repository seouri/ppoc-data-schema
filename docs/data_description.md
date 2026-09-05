# Pediatric EHR Dataset Description

## Overview

This dataset contains de-identified electronic health record (EHR) data for 250,588 unique pediatric patients aged 0-18 years. It encompasses demographic information, clinical visits, laboratory results, medications, problem lists, and specialty referrals. The data is structured for longitudinal analysis of pediatric growth, development, health outcomes, and healthcare utilization patterns.

**Key Characteristics:**
- **Total Unique Patients:** 250,588
- **Age Range:** 0-18 years (dates de-identified as age in days)
- **Primary Linkage:** `patient_id` across all files
- **Data Types:** Demographics, anthropometrics, diagnoses (ICD-10), lab results, medications, referrals
- **Augmented Files:** Enhanced with CDC-standardized growth metrics, Z-scores, velocities, and clinical flags
- **Use Cases:** Growth monitoring, longitudinal anthropometric modeling, care-pathway description, ML modeling for pediatric outcomes among *common* conditions
- **NOT suitable for:** rare-disease research, rare-exposure pharmacoepidemiology, uncommon-lab studies, or any mortality/survival outcome. See *Cohort Construction* below — these are excluded by the cohort definition, not merely sparse.

**Important Notes for LLMs:**
- All temporal data is de-identified; use `age_in_days` for chronological analysis (convert to years: divide by 365.25).
- Missing data is common in anthropometric and result fields; handle NaNs appropriately.
- **ICD-10 is a hierarchy; do not match codes exactly.** `E10` is type 1 diabetes and `E10.9` is type 1 diabetes without complications. Matching a code exactly counts one node of the tree, not the condition. In this extract 1,204 of the 1,327 three-character categories **never appear as a bare code**, so an exact-match query for them returns zero while the condition is present. Match on a prefix (`code LIKE 'E10%'`) or roll up to the level you mean, and say which level that is.
- **Not every null means missing.** A null `result_flag` means a *normal* result; a null `resolved_date_age_in_days` means a problem that is *currently active*. Treating either as missing discards the signal.
- **This is a selected cohort, not a primary-care population.** Every patient met a growth-measurement requirement and carries no rare diagnosis, medication, or lab. Do not read any frequency here as a population rate.
- ICD-10 codes follow standard medical conventions; validate formats.
- Augmented files require CDC reference data for calculations; ensure compatibility.

## Cohort Construction

The 250,588 patients are what remains after four successive exclusions applied by PPOC to its active-patient registry. Source: the delivery documents `ppoc-growth-charts-ai-project-data-extract-2025-02-03.pdf` and the accompanying cohort workbook. Every count below reconciles against the delivered data.

| Step | Criterion | Remaining |
| --- | --- | --- |
| 0 | On the PPOC active-patient registry | 437,996 |
| 1 | Age < 18 as of **31 Dec 2024** | 361,326 |
| 2 | Excluding patients of **2 practices that declined participation** | 352,017 |
| 3 | **≥ 5 growth measurements** of one type (height, weight, or head circumference) on distinct dates, spanning > 1095 days, with the last measurement < 400 days ago (children under 3 are exempted from the span requirement) | 290,175 |
| 4 | Carrying **no rare diagnosis, medication, or lab**, where rare = fewer than 11 occurrences in the data set | **250,588** |

Extract date: **03 Feb 2025**. "Active" on the registry requires living status = alive, not flagged as a test or inactive patient, an active PPOC PCP association, and either a visit in the last 3 years or one scheduled in the next 15 months.

**What step 4 removed.** The exclusion dropped the *patient*, not just the code:

| Vocabulary | Total | Classed rare and removed |
| --- | --- | --- |
| ICD-10 diagnosis codes | 30,493 | 18,604 (61%) |
| Simple generic medications | 2,503 | 1,391 (56%) |
| Lab procedures | 13,402 | 9,621 (72%) |

### Consequences you must design around

- **Rare conditions are absent by construction.** Any study of an uncommon diagnosis, drug, or lab is invalid here — the relevant patients were removed entirely, so the result will look like a true zero or a low rate rather than a missing population.
- **No deceased patients.** The registry requires living status = alive, so mortality is not an available outcome and any survival analysis is censored by construction.
- **Rich growth trajectories are an entry criterion, not a finding.** Every patient has ≥ 5 growth measurements of some type. Statistics such as "most patients have many height observations" describe step 3, not pediatric primary care.
- **Recency filtering right-censors the panel.** The last measurement falls within 400 days of 31 Dec 2024.
- **Two practices are missing entirely**, which is a site-level selection effect that no field in the data exposes.
- **Frequencies are not prevalences.** Steps 1–4 each shift the composition; none of them is random with respect to health.

A residual ambiguity in the source documents, recorded rather than silently resolved: the workbook describes the under-3 exemption as applying to the *span* requirement for children with ≥ 5 measurements, while the extract diagram describes it as age < 3 with *at least 1* measurement. The two documents also state the rarity threshold as "fewer than 11 occurrences" and "< 10 patients" respectively.

## File Relationships

The datasets are interconnected via unique identifiers for multi-level analysis:

- **Patients** (`patients.csv`, `patients_augmented.csv`): Core demographics (sex, ethnicity, race). Linked to ALL other files via `patient_id`.
- **Visits** (`visits.csv`, `visits_augmented.csv`): Visit-level records (anthropometrics, diagnoses, encounter types). Linked to patients via `patient_id`; the augmented file also has a complete `visit_id` link to `visits.csv`.
- **Labs** (`labs.csv`): Lab orders/results. Linked completely to patients via `patient_id`; `visit_id` is a logical but incomplete link to `visits.csv`.
- **Medications** (`medications.csv`): Prescriptions/administrations. Linked completely to patients via `patient_id`; `visit_id` is a logical but incomplete link to `visits.csv`.
- **Problem List** (`problem_list.csv`): Chronic/resolved conditions. Linked ONLY to patients via `patient_id` (not directly to visits; combine with visits for full diagnosis history).
- **Referrals** (`referrals.csv`): Specialty referrals. Linked completely to patients via `patient_id`; `visit_id` is a logical but incomplete link to `visits.csv`.

**Relationship Diagram:**
```
Patients (patient_id)
├── Visits (patient_id, visit_id)
│   ├── Labs (patient_id; logical/incomplete visit_id)
│   ├── Medications (patient_id; logical/incomplete visit_id)
│   └── Referrals (patient_id; logical/incomplete visit_id)
└── Problem List (patient_id)
```

**Augmented Files:** `patients_augmented.csv` and `visits_augmented.csv` add computed metrics (e.g., growth velocities, malnutrition flags) derived from base files.

**On the incomplete `visit_id` links:** this is documented, expected behaviour, not a data defect. Labs, medications, and referrals can be ordered or documented outside a visit, and those rows carry a `visit_id` that resolves to no visit in this extract. Treat visit linkage as partial by design.

## Dataset Summaries

### [Patients (`patients.csv`)](patients.md)
- **Rows:** 250,588 (one per patient)
- **Key Columns:** `patient_id` (unique), `sex` (F/M/U), `ethnicity` (6 recorded categories plus blank), `race_1` to `race_8` (up to 8 races)
- **Highlights:** Demographics for all patients; ~20.5% missing ethnicity, including ~16.5% race_1 non-response plus ~3.5% blank race_1 cells; multiracial support.
- **LLM Uses:** Cohort stratification by demographics; analyze health disparities; join with visits for demographic-linked outcomes.

### [Patients Augmented (`patients_augmented.csv`)](patients_augmented.md)
- **Rows:** 250,588 (one per patient)
- **Key Additions:** Visit counts, growth flags (stunting, wasting, obesity), diagnosis ages, Z-score summaries (weight, height, BMI, etc.)
- **Highlights:** Patient-level summaries from visits; flags for malnutrition/healthy status; ICD-10-specific diagnosis ages.
- **LLM Uses:** Identify at-risk patients; feature engineering for ML (e.g., predict chronic conditions); longitudinal summaries without visit-level data.

### [Visits (`visits.csv`)](visits.md)
- **Rows:** 6,494,473 (one per visit)
- **Key Columns:** `patient_id`, `visit_id`, `age_in_days`, `encounter_type` (45 types, e.g., "Office Visit"), `weight_oz`, `height_in`, `BMI`, `bmi_percentile`, `enc_diag_1` to `enc_diag_33` (ICD-10 codes)
- **Highlights:** Anthropometrics and diagnoses per visit; 72.8% "Office Visit"; up to 33 diagnoses; missing data in measurements. `BMI` and `bmi_percentile` are computed inside Epic and are present for infants, where the augmented `bmi` is deliberately null; encounters converted from a legacy EMR (`orig_enc_source_Epic_yn = "N"`) may be missing diagnosis information.
- **LLM Uses:** Growth trend analysis; diagnosis prevalence; join with demographics for stratified insights.

### [Visits Augmented (`visits_augmented.csv`)](visits_augmented.md)
- **Rows:** 6,494,473 (one per visit)
- **Key Additions:** Converted units (kg, cm), Z-scores/percentiles (CDC LMS), velocities (kg/year, cm/year), flags (stunting, obesity), BMI categories
- **Highlights:** Clinically validated growth metrics; BIV filtering; outlier detection; malnutrition flags.
- **LLM Uses:** Advanced growth monitoring; ML for health predictions (e.g., obesity risk); velocity-based early intervention.

### [Labs (`labs.csv`)](labs.md)
- **Rows:** 17,230,681 (one per result component)
- **Key Columns:** `patient_id`, `visit_id`, `lab_order_id`, `lab_procedure_name` (3,742 types, e.g., "CBC"), `result_component_name`, `result_value`, `result_flag` (result interpretation/status flags)
- **Highlights:** Detailed lab results; LOINC codes; 92.2% missing LOINC. **A null `result_flag` means a normal result** — per the data dictionary, any non-null value indicates abnormal. Care Everywhere (outside) labs are included without results, so a null `result_value` is often "no result was transmitted" rather than "not measured". Result lines may not link back to their original order, producing duplicate records.
- **LLM Uses:** Lab trend analysis; correlate with diagnoses/medications; identify abnormal patterns.

### [Medications (`medications.csv`)](medications.md)
- **Rows:** 3,823,049 (one per record)
- **Key Columns:** `patient_id`, `visit_id`, `med_record_id`, `med_order_date_age_in_days`, `med_simple_generic_name` (1,073 types, e.g., "Amoxicillin"), `med_record_type` (Internal/External)
- **Highlights:** Prescriptions/administrations; top meds: antibiotics/respiratory. Date anomalies are documented, not corrupt: for historically documented medications the order date is the *documentation* date and start dates may be approximate (a charted "Jan 2022" is stored as 1 Jan 2022), and end dates may be in the future while a medication is active.
- **Not delivered:** the data dictionary documents `med_therapeutic_class`, `med_pharmaceutical_class`, and `med_pharmaceutical_subclass`, but **none of the three is present in the extract**. Drug-class analysis requires mapping `med_simple_generic_name` yourself.
- **LLM Uses:** Medication utilization for common drugs; adverse event detection via diagnosis links. Not rare-exposure pharmacoepidemiology — see *Cohort Construction*.

### [Problem List (`problem_list.csv`)](problem_list.md)
- **Rows:** 1,709,584 (one per entry)
- **Key Columns:** `patient_id`, `problem_list_id`, `noted_date_age_in_days`, `resolved_date_age_in_days`, `pl_diag` (ICD-10, 4,739 unique)
- **Highlights:** Chronic conditions; top: COVID-19, anxiety, constipation; not complete (combine with visits). **A null `resolved_date_age_in_days` means the problem is currently active**, not that the date is missing.
- **LLM Uses:** Chronic disease tracking; resolution analysis; supplement visit diagnoses.

### [Referrals (`referrals.csv`)](referrals.md)
- **Rows:** 349,827 (one per referral)
- **Key Columns:** `patient_id`, `visit_id`, `referral_id`, `referral_date_age_in_days`, `requested_specialty` (119 unique nonblank values, e.g., "Otolaryngology"), `referral_number_of_visits`
- **Highlights:** Specialty consultations; top: ENT, ophthalmology; most have 1 or 6 visits.
- **LLM Uses:** Referral pattern analysis; specialty utilization; care pathway modeling.

## Example LLM Prompt Integration

For schema-driven Python loading, see [`schema/README.md`](../schema/README.md) for examples that read `datapackage.json`, resolve resource paths, apply declared encodings and nullable types, and inspect keys.

When using this dataset in prompts:
- **Specify Files:** "Analyze visits_augmented.csv for growth velocities by sex from patients.csv."
- **Linkages:** "Join problem_list.csv with visits.csv via patient_id to get full diagnosis history."
- **Calculations:** "Convert age_in_days to years: age_years = age_in_days / 365.25."
- **Missing Data:** "Handle NaNs in anthropometrics; use flags for malnutrition detection."
- **Augmented Insights:** "Use Z-scores from visits_augmented.csv for standardized growth comparisons."

## Important Considerations
- **Diagnosis counting:** ICD-10 is hierarchical. Count a code together with its descendants, not as a literal string; see the exploratory analysis at section 3.9 for the size of the effect and section 5.7 for a worked verification against the derived columns.
- **Selection:** The cohort is heavily selected (see *Cohort Construction*). Rare conditions, deceased patients, and two practices are absent by construction; frequencies are not prevalences.
- **Data Quality:** Outliers in measurements; non-response in demographics; BIV-filtered values in augmented files. Null does not always mean missing — see the notes on `result_flag` and `resolved_date_age_in_days`.
- **Privacy:** De-identified; avoid re-identification.
- **Performance:** Large files (6.5M visits); use efficient tools (pandas dtypes, chunking).
- **Clinical Standards:** CDC LMS for growth; ICD-10 for diagnoses.
- **Validation:** Cross-check linkages; verify ICD-10 formats.
