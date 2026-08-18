### Data Description for `problem_list.csv`

**Quick Reference**:
- **Dataset**: Pediatric problem list records for 238,824 unique children (0–18 years).
- **Rows**: 1,709,585 (one row per problem list entry, including header).
- **Unique Patients**: 238,824 (unique `patient_id`).
- **Unique Problem List Entries**: 1,709,585 (unique `problem_list_id`).
- **Columns**: 5 (patient, problem list, dates, diagnosis).
- **Key Uses**: Chronic and resolved condition tracking, diagnosis prevalence, longitudinal patient analysis, linkage with visits and demographics.
- **Tools**: Optimized for R (`dplyr`, `data.table`) or Python (`pandas`).
- **Time Span**: Not directly available; dates are de-identified as age in days.

**Dataset Overview**: The `problem_list.csv` file contains pediatric problem list records for 238,824 unique children aged 0 to 18 years, totaling 1,709,584 entries. Each row represents a single problem list entry for a patient, including identifiers, de-identified dates (as age in days), and diagnosis codes. The dataset can be joined with `patients.csv` (demographics) using `patient_id`.

**File Structure**:
- **Format**: CSV (Comma-Separated Values)
- **Rows**: 1,709,585 (one row per problem list entry, including header)
- **Unique Patients**: 238,824 (unique `patient_id`)
- **Unique Problem List Entries**: 1,709,585 (unique `problem_list_id`)
- **Columns**: 5 (detailed below)

**Column Descriptions**:
1. **patient_id** (Character/String):
- Unique identifier for each patient (blinded).
- Joins with `patients.csv` for demographic data (sex, ethnicity, race_1 to race_8).
- 238,824 unique values.

2. **problem_list_id** (Character/String):
- Unique identifier for each problem list entry (blinded).
- Primary key (1,709,585 unique values).

3. **noted_date_age_in_days** (Integer):
- Age in days when the problem was first noted (problem start date - date of birth).
- Range: -44,891 to 6,601 days.
- Negative values may indicate data entry errors or pre-birth documentation.

4. **resolved_date_age_in_days** (Integer):
- Age in days when the problem was resolved (problem end date - date of birth).
- Range: -84 to 6,605 days.
- Null or missing values may indicate ongoing problems or incomplete records.

5. **pl_diag** (Character/String):
- ICD-10 diagnosis code for the problem list entry.
- 4,740 unique values.

**Top 10 Most Frequent pl_diag Values**:

| ICD-10 Code | Count  | Description                                                              |
|-------------|--------|--------------------------------------------------------------------------|
| U07.1       | 26,260 | COVID-19                                                                 |
| Z28.21      | 21,189 | Immunization not carried out because of patient refusal                  |
| F41.9       | 20,950 | Anxiety disorder, unspecified                                            |
| K59.00      | 17,491 | Constipation, unspecified                                                |
| Z00.129     | 17,348 | Encounter for routine child health examination without abnormal findings |
| K21.9       | 17,184 | Gastro-esophageal reflux disease without esophagitis                     |
| Z86.16      | 16,007 | Personal history of COVID-19                                             |
| J45.20      | 15,088 | Mild intermittent asthma, uncomplicated                                  |
| L30.9       | 14,868 | Dermatitis, unspecified                                                  |
| R46.89      | 14,789 | Other symptoms and signs involving appearance and behavior               |

**Key Notes**:
- **Problem List is not a complete record**: Not all ICD-10 codes appearing in `visits.csv` (`enc_diag_*` columns) are listed in the Problem List, and the age fields may not be consistent between files. The Problem List may omit acute or transient diagnoses, and some chronic conditions may only appear in visit-level data. For a comprehensive view of each patient’s diagnoses and history, it is highly recommended to combine `problem_list.csv` and `visits.csv`.
- **De-identification**: Dates are converted to age in days to protect privacy; no absolute dates available.
- **Missing Data**: `resolved_date_age_in_days` may be missing for ongoing problems or incomplete records. Negative values in date fields may indicate anomalies.
- **Data Quality**: Outliers in date fields (e.g., negative ages) may represent data entry errors; cleaning is recommended.
- **Diagnosis Codes**: `pl_diag` contains 4,740 unique ICD-10 values. Validate code formats for analysis.
- **Linkage**: `patient_id` enables joining with `patients.csv` for demographics.

**Example Use Cases for LLMs**:
- Summarize prevalence of chronic or resolved conditions by age group (`noted_date_age_in_days`).
- Analyze diagnosis patterns using `pl_diag`, stratified by demographic groups from `patients.csv` (e.g., sex, ethnicity, race).
- Identify common chronic conditions and their resolution rates.
- Study longitudinal problem list history for individual patients.
- Link problem list entries to visits and medications for comprehensive patient history.
- Use machine learning to predict chronic condition risk or resolution likelihood.

**Important Considerations**:
- **Dataset Size**: 1.7M rows require efficient processing (e.g., `data.table` or chunking in Python).
- **Unique Patients**: 238,824 unique `patient_id` values enable longitudinal analyses, joinable with `patients.csv`.
- **Date Ranges**: Wide and occasionally negative ranges suggest data cleaning needed; convert to years if grouping (divide by 365.25).
- **Missing Data**: Handle blanks in `resolved_date_age_in_days` carefully (e.g., assume ongoing if missing).
- **Diagnosis Variance**: 4,740 unique `pl_diag` values; focus on high-frequency diagnoses for summary statistics.
- **Privacy**: Respect de-identification; avoid re-identification attempts.
- **Computational Notes**: Memory-effective processing recommended; possible need for parallelization.

**Example Code**:
```python
import pandas as pd

# Define the dtype dictionary for problem_list.csv columns
dtype_dict = {
    "patient_id": "string",                    # Character/String for unique patient identifier
    "problem_list_id": "string",               # Character/String for unique problem list entry
    "noted_date_age_in_days": "int32",         # Integer for age in days when problem was noted
    "resolved_date_age_in_days": "Int32",      # Nullable integer for age in days when problem was resolved
    "pl_diag": "string",                       # Character/String for diagnosis code
}

# Read the CSV file with specified dtypes
df = pd.read_csv("../p3-data/all/problem_list.csv", dtype=dtype_dict)
```
