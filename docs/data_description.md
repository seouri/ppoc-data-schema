# Pediatric EHR Dataset Description

## Overview

This dataset contains de-identified electronic health record (EHR) data for 250,588 unique pediatric patients aged 0-18 years. It encompasses demographic information, clinical visits, laboratory results, medications, problem lists, and specialty referrals. The data is structured for longitudinal analysis of pediatric growth, development, health outcomes, and healthcare utilization patterns.

**Key Characteristics:**
- **Total Unique Patients:** 250,588
- **Age Range:** 0-18 years (dates de-identified as age in days)
- **Primary Linkage:** `patient_id` across all files
- **Data Types:** Demographics, anthropometrics, diagnoses (ICD-10), lab results, medications, referrals
- **Augmented Files:** Enhanced with CDC-standardized growth metrics, Z-scores, velocities, and clinical flags
- **Use Cases:** Growth monitoring, disease prevalence, pharmacoepidemiology, health disparities research, ML modeling for pediatric outcomes

**Important Notes for LLMs:**
- All temporal data is de-identified; use `age_in_days` for chronological analysis (convert to years: divide by 365.25).
- Missing data is common in anthropometric and result fields; handle NaNs appropriately.
- ICD-10 codes follow standard medical conventions; validate formats.
- Augmented files require CDC reference data for calculations; ensure compatibility.

## File Relationships

The datasets are interconnected via unique identifiers for multi-level analysis:

- **Patients** (`patients.csv`, `patients_augmented.csv`): Core demographics (sex, ethnicity, race). Linked to ALL other files via `patient_id`.
- **Visits** (`visits.csv`, `visits_augmented-20251209150512.csv`): Visit-level records (anthropometrics, diagnoses, encounter types). Linked to patients via `patient_id`; the augmented file also has a complete `visit_id` link to `visits.csv`.
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

**Augmented Files:** `patients_augmented.csv` and `visits_augmented-20251209150512.csv` add computed metrics (e.g., growth velocities, malnutrition flags) derived from base files.

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
- **Highlights:** Anthropometrics and diagnoses per visit; 72.8% "Office Visit"; up to 33 diagnoses; missing data in measurements.
- **LLM Uses:** Growth trend analysis; diagnosis prevalence; join with demographics for stratified insights.

### [Visits Augmented (`visits_augmented-20251209150512.csv`)](visits_augmented.md)
- **Rows:** 6,494,473 (one per visit)
- **Key Additions:** Converted units (kg, cm), Z-scores/percentiles (CDC LMS), velocities (kg/year, cm/year), flags (stunting, obesity), BMI categories
- **Highlights:** Clinically validated growth metrics; BIV filtering; outlier detection; malnutrition flags.
- **LLM Uses:** Advanced growth monitoring; ML for health predictions (e.g., obesity risk); velocity-based early intervention.

### [Labs (`labs.csv`)](labs.md)
- **Rows:** 17,230,681 (one per result component)
- **Key Columns:** `patient_id`, `visit_id`, `lab_order_id`, `lab_procedure_name` (3,742 types, e.g., "CBC"), `result_component_name`, `result_value`, `result_flag` (result interpretation/status flags)
- **Highlights:** Detailed lab results; LOINC codes; 92.2% missing LOINC; result interpretation/status flags.
- **LLM Uses:** Lab trend analysis; correlate with diagnoses/medications; identify abnormal patterns.

### [Medications (`medications.csv`)](medications.md)
- **Rows:** 3,823,049 (one per record)
- **Key Columns:** `patient_id`, `visit_id`, `med_record_id`, `med_order_date_age_in_days`, `med_simple_generic_name` (1,073 types, e.g., "Amoxicillin"), `med_record_type` (Internal/External)
- **Highlights:** Prescriptions/administrations; top meds: antibiotics/respiratory; date ranges may include negatives.
- **LLM Uses:** Medication adherence; pharmacoepidemiology; adverse event detection via diagnosis links.

### [Problem List (`problem_list.csv`)](problem_list.md)
- **Rows:** 1,709,584 (one per entry)
- **Key Columns:** `patient_id`, `problem_list_id`, `noted_date_age_in_days`, `resolved_date_age_in_days`, `pl_diag` (ICD-10, 4,739 unique)
- **Highlights:** Chronic conditions; top: COVID-19, anxiety, constipation; not complete (combine with visits).
- **LLM Uses:** Chronic disease tracking; resolution analysis; supplement visit diagnoses.

### [Referrals (`referrals.csv`)](referrals.md)
- **Rows:** 349,827 (one per referral)
- **Key Columns:** `patient_id`, `visit_id`, `referral_id`, `referral_date_age_in_days`, `requested_specialty` (119 unique nonblank values, e.g., "Otolaryngology"), `referral_number_of_visits`
- **Highlights:** Specialty consultations; top: ENT, ophthalmology; most have 1 or 6 visits.
- **LLM Uses:** Referral pattern analysis; specialty utilization; care pathway modeling.

## Example LLM Prompt Integration

For schema-driven Python loading, see [`schema/README.md`](../schema/README.md) for examples that read `datapackage.json`, resolve resource paths, apply declared encodings and nullable types, and inspect keys.

When using this dataset in prompts:
- **Specify Files:** "Analyze visits_augmented-20251209150512.csv for growth velocities by sex from patients.csv."
- **Linkages:** "Join problem_list.csv with visits.csv via patient_id to get full diagnosis history."
- **Calculations:** "Convert age_in_days to years: age_years = age_in_days / 365.25."
- **Missing Data:** "Handle NaNs in anthropometrics; use flags for malnutrition detection."
- **Augmented Insights:** "Use Z-scores from visits_augmented-20251209150512.csv for standardized growth comparisons."

## Important Considerations
- **Data Quality:** Outliers in measurements; non-response in demographics; BIV-filtered values in augmented files.
- **Privacy:** De-identified; avoid re-identification.
- **Performance:** Large files (6.5M visits); use efficient tools (pandas dtypes, chunking).
- **Clinical Standards:** CDC LMS for growth; ICD-10 for diagnoses.
- **Validation:** Cross-check linkages; verify ICD-10 formats.
