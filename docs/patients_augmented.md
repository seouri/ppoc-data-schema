### Data Description for `patients_augmented.csv`

**Quick Reference**:
- **Dataset**: Augmented demographic data for 250,588 unique pediatric patients (0–18 years) with visit summary statistics.
- **Rows**: 250,588 (one row per unique patient).
- **Unique Patients**: 250,588.
- **Columns**: 87 (11 original demographic fields plus 76 derived fields)
- **Key Uses**: Cohort selection, patient stratification, feature engineering for patient-level predictive modeling.
- **Tools**: Optimized for R (`dplyr`) or Python (`pandas`).
- **Augmentation**: Generated from `scripts/augment.py` using `visits_augmented-20251209150512.csv` and `problem_list.csv`.

**Dataset Overview**: The `patients_augmented.csv` file contains enhanced demographic data for 250,588 unique pediatric patients. It is created by augmenting the original `patients.csv` with longitudinal summaries derived from `visits_augmented-20251209150512.csv` and diagnosis information from `problem_list.csv`. Each row represents a single patient and includes all original demographic data plus new columns summarizing their clinical interactions, such as the total number of visits, the time span of their care, and summary statistics for various growth metrics. This dataset is ideal for patient-level analysis, cohort building, and creating features for predictive models.

**File Structure**:
- **Format**: CSV (Comma-Separated Values)
- **Rows**: 250,588
- **Unique Patients**: 250,588
- **Columns**: 87 (original 11 + 76 new augmented columns)
- **Generation**: Created by running `python scripts/augment.py input_dir [--output_dir output] [--output_format {csv,parquet}]`

**Column Descriptions (New and Augmented Columns)**: This dataset preserves all original columns from `patients.csv` and adds 76 derived columns, all computed as described in the `augment_patients` function in `scripts/augment.py`.

#### Healthy Flag

- **healthy_flag** (Integer, 0/1): 1 if the patient has no history of chronic diagnoses, growth-related diagnoses, stunting, wasting, underweight, or obesity (i.e., all of chronic_dx_flag, growth_dx_flag, ever_stunting_flag, ever_wasting_flag, ever_underweight_flag, ever_obesity_flag are 0); 0 otherwise. Calculated after all other flags.

#### Visit Summary Statistics

- **chronic_dx_flag** (Integer, 0/1): 1 if any of the patient's diagnosis codes (from visits or problem list) are in the chronic ICD-10 code set (`ICD10_CODES_CHRONIC`); 0 otherwise.

- **growth_dx_flag** (Integer, 0/1): 1 if any of the patient's diagnosis codes (from visits or problem list) start with any prefix in the growth-related ICD-10 code set (`ICD10_CODES_GROWTH`); 0 otherwise.

- **visits_count** (Integer): Total number of recorded visits for the patient (0 for patients with no visits).

- **visits_count_pre_dx** (Integer): Number of visits for the patient where `age_in_years` is less than `dx_age_years` (the minimum age at which any growth-related diagnosis was made). If `dx_age_years` is null, this value is equal to `visits_count`. This column is useful for analyzing patient history prior to the first growth-related diagnosis.

- **min_visit_age_days** (Integer): Age in days at the patient's first recorded visit (NaN if no visits).

- **max_visit_age_days** (Integer): Age in days at the patient's last recorded visit (NaN if no visits).

- **visits_span_days** (Integer): Duration between first and last visit (in days); 0 for a single visit, NaN for no visits.

#### Ever Malnutrition Flags

- **ever_stunting_flag** (Integer, 0/1): 1 if stunting (height_z_score < -2) ever occurred in any visit; 0 otherwise.

- **ever_wasting_flag** (Integer, 0/1): 1 if wasting (weight_for_length_z_score < -2 OR weight_for_stature_z_score < -2) ever occurred in any visit; 0 otherwise.

- **ever_underweight_flag** (Integer, 0/1): 1 if underweight (bmi_percentile < 5) ever occurred in any visit; 0 otherwise.

- **ever_obesity_flag** (Integer, 0/1): 1 if obesity (bmi_percentile >= 95) ever occurred in any visit; 0 otherwise.

#### Diagnosis Age Columns

- **dx_age_years** (Float): Minimum age in years at which any growth-related ICD-10 code (from the set below) was diagnosed (from visits or problem list); NaN if none diagnosed.

- **dx_age_years_<code>** (Float):
  For each ICD-10 code in the growth-related disorders set (`ICD10_CODES_GROWTH`), a column named `dx_age_years_<code>` is created, where `<code>` is the ICD-10 code lowercased and with dots replaced by underscores (e.g., `E03.9` → `dx_age_years_e03_9`).
Each such column contains the minimum age in years at which the patient was first diagnosed with any code that *starts with* that ICD-10 code, from either visit-level diagnosis codes (`enc_diag_*`) or problem list diagnoses (`pl_diag`). If the patient was never diagnosed with a code starting with that prefix, the value is NaN.

The full set of growth-related ICD-10 codes (with descriptions) is:

- E03.9: Hypothyroidism, unspecified
- E10: Type 1 diabetes mellitus
- E22.0: Acromegaly and pituitary gigantism
- E23.0: Hypopituitarism
- E23.6: Other disorders of pituitary gland
- E24: Cushing's syndrome
- E30.0: Delayed puberty
- E30.1: Precocious puberty
- E34.3: Short stature due to endocrine disorder
- E34.4: Constitutional tall stature
- E72.11: Homocystinuria
- K50: Crohn's disease [regional enteritis]
- K51: Ulcerative colitis
- K90.0: Celiac disease
- N18: Chronic kidney disease (CKD)
- N25.0: Renal osteodystrophy
- P04.3: Newborn affected by maternal use of alcohol
- P05: Disorders of newborn related to slow fetal growth and fetal malnutrition
- P07: Disorders of newborn related to short gestation and low birth weight, not elsewhere classified
- P70: Transitory disorders of carbohydrate metabolism specific to newborn
- P92.6: Failure to thrive in newborn
- Q77: Osteochondrodysplasia with defects of growth of tubular bones and spine
- Q78.0: Osteogenesis imperfecta
- Q78.1: Polyostotic fibrous dysplasia
- Q87.1: Congenital malformation syndromes predominantly associated with short stature
- Q87.2: Congenital malformation syndromes predominantly involving limbs
- Q87.3: Congenital malformation syndromes involving early overgrowth
- Q87.4: Marfan syndrome
- Q90: Down syndrome
- Q96: Turner's syndrome
- Q98.0: Klinefelter syndrome karyotype 47, XXY
- Q98.4: Klinefelter syndrome, unspecified
- Q98.5: Karyotype 47, XYY

#### Z-Score Summary Statistics

For each of the following Z-score metrics, five summary statistics are calculated across all of a patient's visits:
- `count_*`: The number of non-null Z-score values.
- `mean_*`: The average Z-score.
- `std_*`: The standard deviation of the Z-scores.
- `min_*`: The minimum Z-score.
- `max_*`: The maximum Z-score.

These statistics are calculated for:
- **weight_z_score**: `count_weight_z_score`, `mean_weight_z_score`, `std_weight_z_score`, `min_weight_z_score`, `max_weight_z_score`
- **height_z_score**: `count_height_z_score`, `mean_height_z_score`, `std_height_z_score`, `min_height_z_score`, `max_height_z_score`
- **bmi_z_score**: `count_bmi_z_score`, `mean_bmi_z_score`, `std_bmi_z_score`, `min_bmi_z_score`, `max_bmi_z_score`
- **head_circ_z_score**: `count_head_circ_z_score`, `mean_head_circ_z_score`, `std_head_circ_z_score`, `min_head_circ_z_score`, `max_head_circ_z_score`
- **weight_for_length_z_score**: `count_weight_for_length_z_score`, `mean_weight_for_length_z_score`, `std_weight_for_length_z_score`, `min_weight_for_length_z_score`, `max_weight_for_length_z_score`
- **weight_for_stature_z_score**: `count_weight_for_stature_z_score`, `mean_weight_for_stature_z_score`, `std_weight_for_stature_z_score`, `min_weight_for_stature_z_score`, `max_weight_for_stature_z_score`


**Original Columns Preserved**: All original columns from `patients.csv` are retained. The demographic columns `ethnicity` and `race_*` are cleaned to convert non-informative string values to `pd.NA`.
- `patient_id`
- `sex`
- `ethnicity` (cleaned)
- `race_1` to `race_8` (cleaned)

**Key Notes**:
- **Patient-Level Summary**: This dataset provides a high-level summary of each patient's clinical history, complementing the granular data in `visits_augmented-20251209150512.csv`.
- **Data Cleaning**: The `ethnicity` and `race_*` columns are cleaned as part of the augmentation process, converting values like `Unknown` or `Choose not to Answer` (ethnicity) and `Choose not to answer` (race) to `NA`.
- **Handling of No-Visit Patients**: Patients present in `patients.csv` but not in `visits.csv` will have a `visits_count` of 0 and `NaN` for all other added columns.

**Example Use Cases for LLMs**:
- Identify patient cohorts based on visit frequency (e.g., patients with more than 10 visits).
- Analyze the distribution of `visits_span_days` to understand patient engagement over time.
- Stratify patients by `mean_bmi_z_score` to identify patients with consistently high or low BMI.
- Use the malnutrition ever-flags and diagnosis flags (ever_stunting_flag, ever_wasting_flag, ever_underweight_flag, ever_obesity_flag, growth_dx_flag, chronic_dx_flag) to identify patients with history of growth disorders or nutritional issues.
- Use the summary statistics as features in machine learning models to predict patient-level outcomes.

**Important Considerations**:
- **Linkage**: This dataset can be joined with `visits_augmented-20251209150512.csv` using `patient_id` to combine patient-level summaries with visit-level details.
- **NaN Values**: The age, span, and Z-score statistic columns will contain `NaN` for patients without any visits or with no relevant measurements. This should be handled appropriately during analysis.

**Example Code**:
```python
import pandas as pd

# Define dtypes for efficient loading
# The dx_age_years_<code> columns below are generated for every code in ICD10_CODES_GROWTH.
dtype_dict = {
    # Original patient columns
    "patient_id": "string",
    "sex": "category",
    "ethnicity": "category",
    "race_1": "category",
    "race_2": "category",
    "race_3": "category",
    "race_4": "category",
    "race_5": "category",
    "race_6": "category",
    "race_7": "category",
    "race_8": "category",
    # Visit summary columns
    "healthy_flag": "int8",
    "chronic_dx_flag": "int8",
    "growth_dx_flag": "int8",
    "ever_stunting_flag": "int8",
    "ever_wasting_flag": "int8",
    "ever_underweight_flag": "int8",
    "ever_obesity_flag": "int8",
    "visits_count": "int16",
    "visits_count_pre_dx": "int16",
    "min_visit_age_days": "Int16",  # Nullable integer to handle NaNs
    "max_visit_age_days": "Int16",
    "visits_span_days": "Int16",
    # Diagnosis Age Columns (aggregate + full ICD10_CODES_GROWTH set)
    "dx_age_years": "float32",            # Minimum age at any growth-related diagnosis
    "dx_age_years_e03_9": "float32",      # Hypothyroidism, unspecified
    "dx_age_years_e10": "float32",        # Type 1 diabetes mellitus
    "dx_age_years_e22_0": "float32",      # Acromegaly and pituitary gigantism
    "dx_age_years_e23_0": "float32",      # Hypopituitarism
    "dx_age_years_e23_6": "float32",      # Other disorders of pituitary gland
    "dx_age_years_e24": "float32",        # Cushing's syndrome
    "dx_age_years_e30_0": "float32",      # Delayed puberty
    "dx_age_years_e30_1": "float32",      # Precocious puberty
    "dx_age_years_e34_3": "float32",      # Short stature due to endocrine disorder
    "dx_age_years_e34_4": "float32",      # Constitutional tall stature
    "dx_age_years_e72_11": "float32",     # Homocystinuria
    "dx_age_years_k50": "float32",        # Crohn's disease [regional enteritis]
    "dx_age_years_k51": "float32",        # Ulcerative colitis
    "dx_age_years_k90_0": "float32",      # Celiac disease
    "dx_age_years_n18": "float32",        # Chronic kidney disease (CKD)
    "dx_age_years_n25_0": "float32",      # Renal osteodystrophy
    "dx_age_years_p04_3": "float32",      # Newborn affected by maternal use of alcohol
    "dx_age_years_p05": "float32",        # Disorders of newborn related to slow fetal growth and fetal malnutrition
    "dx_age_years_p07": "float32",        # Disorders of newborn related to short gestation and low birth weight, not elsewhere classified
    "dx_age_years_p70": "float32",        # Transitory disorders of carbohydrate metabolism specific to newborn
    "dx_age_years_p92_6": "float32",      # Failure to thrive in newborn
    "dx_age_years_q77": "float32",        # Osteochondrodysplasia with defects of growth of tubular bones and spine
    "dx_age_years_q78_0": "float32",      # Osteogenesis imperfecta
    "dx_age_years_q78_1": "float32",      # Polyostotic fibrous dysplasia
    "dx_age_years_q87_1": "float32",      # Congenital malformation syndromes predominantly associated with short stature
    "dx_age_years_q87_2": "float32",      # Congenital malformation syndromes predominantly involving limbs
    "dx_age_years_q87_3": "float32",      # Congenital malformation syndromes involving early overgrowth
    "dx_age_years_q87_4": "float32",      # Marfan syndrome
    "dx_age_years_q90": "float32",        # Down syndrome
    "dx_age_years_q96": "float32",        # Turner's syndrome
    "dx_age_years_q98_0": "float32",      # Klinefelter syndrome karyotype 47, XXY
    "dx_age_years_q98_4": "float32",      # Klinefelter syndrome, unspecified
    "dx_age_years_q98_5": "float32",      # Karyotype 47, XYY
    # Z-score statistics columns
    "count_weight_z_score": "Int16",
    "mean_weight_z_score": "float32",
    "std_weight_z_score": "float32",
    "min_weight_z_score": "float32",
    "max_weight_z_score": "float32",
    "count_height_z_score": "Int16",
    "mean_height_z_score": "float32",
    "std_height_z_score": "float32",
    "min_height_z_score": "float32",
    "max_height_z_score": "float32",
    "count_bmi_z_score": "Int16",
    "mean_bmi_z_score": "float32",
    "std_bmi_z_score": "float32",
    "min_bmi_z_score": "float32",
    "max_bmi_z_score": "float32",
    "count_head_circ_z_score": "Int8",
    "mean_head_circ_z_score": "float32",
    "std_head_circ_z_score": "float32",
    "min_head_circ_z_score": "float32",
    "max_head_circ_z_score": "float32",
    "count_weight_for_length_z_score": "Int8",
    "mean_weight_for_length_z_score": "float32",
    "std_weight_for_length_z_score": "float32",
    "min_weight_for_length_z_score": "float32",
    "max_weight_for_length_z_score": "float32",
    "count_weight_for_stature_z_score": "Int8",
    "mean_weight_for_stature_z_score": "float32",
    "std_weight_for_stature_z_score": "float32",
    "min_weight_for_stature_z_score": "float32",
    "max_weight_for_stature_z_score": "float32"
}

# Load augmented dataset
df_patients_aug = pd.read_csv("output/patients_augmented.csv", dtype=dtype_dict)

# Example: Find patients with high mean BMI Z-score
high_bmi_patients = df_patients_aug[df_patients_aug["mean_bmi_z_score"] > 1.5]
print(high_bmi_patients.describe())
```
