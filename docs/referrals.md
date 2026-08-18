### Data Description for `referrals.csv`

**Quick Reference**:
- **Dataset**: Referral records for pediatric patients (0–18 years) linking visits to specialty consultations.
- **Rows**: 349,827 (one row per referral).
- **Unique Patients**: 138,071 (unique `patient_id`).
- **Unique Visit IDs**: 298,616 (distinct `visit_id` values; not all resolve to `visits.csv`).
- **Unique Referrals**: 349,827 (unique `referral_id`).
- **Columns**: 6 (patient, visit, referral identifiers, date, specialty, visit count).
- **Key Uses**: Referral pattern analysis, specialty utilization, longitudinal care tracking, demographic-linked referral studies.
- **Tools**: Optimized for R (`dplyr`, `data.table`, `ggplot2`) or Python (`pandas`, `matplotlib`).
- **Time Span**: Referral dates as age in days (1 to 6,567 days, ~0–18 years).

**Dataset Overview**: The `referrals.csv` file contains referral records for 138,071 unique pediatric patients aged 0 to 18 years, totaling 349,827 referrals. Each row represents a single referral from a patient visit to a medical specialty, including de-identified dates, requested specialty, and the number of associated visits. This dataset enables analysis of referral patterns, specialty demand, and patient care pathways. It joins completely to `patients.csv` through `patient_id`; its `visit_id` relationship to `visits.csv` is logical but incomplete.

**File Structure**:
- **Format**: CSV (Comma-Separated Values)
- **Rows**: 349,827 (one row per referral)
- **Unique Patients**: 138,071 (unique `patient_id`)
- **Unique Visit IDs**: 298,616 (distinct `visit_id` values; not all resolve to `visits.csv`)
- **Unique Referrals**: 349,827 (unique `referral_id`)
- **Columns**: 6 (detailed below)

**Column Descriptions**:
1. **patient_id** (Character/String):
- Unique identifier for each patient (blinded).
- Primary key component; joins completely with `patients.csv` for demographics (sex, ethnicity, race_1 to race_8). The `visit_id` field is a logical but incomplete link to visit details (diagnoses and anthropometrics).
- 138,071 unique values.

2. **visit_id** (Character/String):
- Unique identifier for the visit associated with the referral (blinded).
- Logically links to `visits.csv` for visit context, including encounter type, age, and diagnoses; the link is incomplete.
- 298,616 unique values.

3. **referral_id** (Character/String):
- Unique identifier for each referral (blinded).
- Primary key (349,827 unique values).

4. **referral_date_age_in_days** (Integer):
- Age of the patient in days at the time of referral (referral date - date of birth).
- Range: 1 to 6,567 days (~0–18 years).
- No missing values.

5. **requested_specialty** (Character/String):
- Medical specialty to which the patient was referred.
- 121 unique values.
- Nullable; 27,452 rows are blank.
- Top specialties by referral count (based on 349,827 referrals):
     - `Otolaryngology`: 35,723 (10.2%)
     - `Ophthalmology`: 24,298 (6.9%)
     - `Orthopedic Surgery`: 22,887 (6.5%)
     - `Allergy`: 21,761 (6.2%)
     - `Behavioral Health`: 21,748 (6.2%)
     - `Dermatology`: 20,652 (5.9%)
     - `Audiology`: 15,972 (4.6%)
     - `Gastroenterology`: 14,344 (4.1%)
     - `Cardiology`: 13,610 (3.9%)
     - `Neurology`: 11,275 (3.2%)
     - `Nutrition`: 11,035 (3.2%)
     - `Urology`: 10,697 (3.1%)
     - `Speech Pathology`: 9,879 (2.8%)
     - `Physical Therapy`: 9,861 (2.8%)
     - `Early Intervention`: 9,302 (2.7%)
     - `Developmental Medicine`: 8,532 (2.4%)
     - `Endocrinology`: 6,641 (1.9%)
     - `Occupational Therapy`: 6,573 (1.9%)
     - `General Surgery`: 4,206 (1.2%)
     - `Psychology`: 4,134 (1.2%)
     - `Pulmonary Disease`: 3,926 (1.1%)
     - `Plastic Surgery`: 3,454 (1.0%)
     - `Psychiatry`: 2,885 (0.8%)
     - `Podiatry`: 2,863 (0.8%)
     - `Neurosurgery`: 2,415 (0.7%)
     - `Genetics`: 2,397 (0.7%)
     - `Sports Medicine`: 2,291 (0.6%)
     - `Sleep Medicine`: 1,898 (0.5%)
     - `Hematology`: 1,607 (0.5%)
     - `Obstetrics and Gynecology`: 1,500 (0.4%)
     - `Gynecology`: 1,430 (0.4%)
     - `Optometry`: 1,392 (0.4%)
     - `Rheumatology`: 1,048 (0.3%)
     - `Nephrology`: 1,044 (0.3%)
     - `Dental General Practice`: 852 (0.2%)
     - `Pediatrics`: 742 (0.2%)
     - `Pediatric Surgery`: 645 (0.2%)
     - `Infectious Diseases`: 564 (0.2%)
     - `Orthopedics`: 496 (0.1%)
     - `Urgent Care`: 457 (0.1%)
     - `Neuropsychology`: 427 (0.1%)
     - `Pediatric Cardiology`: 400 (0.1%)
     - `Oral and Maxillofacial Surgery`: 392 (0.1%)
     - `Pediatric Gastroenterology`: 371 (0.1%)
     - `Pediatric Ophthalmology`: 315 (0.1%)
     - `Vascular Surgery`: 304 (0.1%)
     - `Pediatric Endocrinology`: 275 (0.1%)
     - `Orthotics`: 252 (0.1%)
     - `Pediatric Orthopedic Surgery`: 245 (0.1%)
     - `Radiology`: 242 (0.1%)
     - `Pediatric Neurology`: 232 (0.1%)
     - `Hand Surgery`: 194 (0.1%)
     - `Travel Medicine`: 181 (0.1%)
     - `Physical Medicine and Rehabilitation`: 125 (0.1%)
     - `Pediatric Pulmonology`: 102 (0.1%)
     - `Lactation Services`: 93 (0.1%)
     - `Chiropractic Medicine`: 80 (0.1%)
     - `Oral Surgery`: 78 (0.1%)
     - `Hematology and Oncology`: 71 (0.1%)
     - `Toxicology`: 66 (0.1%)
     - `Feeding and Swallowing`: 65 (0.1%)
     - `Pediatric Rheumatology`: 61 (0.1%)
     - `Oncology`: 51 (0.1%)
     - `Pain Medicine`: 48 (0.1%)
     - `Cardiothoracic Surgery`: 48 (0.1%)
     - `Pediatric Nephrology`: 43 (0.1%)
     - `Neonatology`: 39 (0.1%)
     - `Pediatric Hematology and Oncology`: 32 (0.1%)
     - `Adolescent Medicine`: 32 (0.1%)
     - `Allergy and Immunology`: 30 (0.1%)
     - `Pediatric Neurosurgery`: 29 (0.1%)
     - `Immunology`: 27 (0.1%)
     - `Pediatric Genetics`: 26 (0.1%)
     - `OWL Clinic`: 26 (0.1%)
     - `Breast Surgery`: 24 (0.1%)
     - `Home Health Services`: 20 (0.1%)
     - `Pediatric Infectious Disease`: 19 (0.1%)
     - `Social Services`: 18 (0.1%)
     - `Pediatric Otolaryngology`: 18 (0.1%)
     - `Applied Behavior Analysis (ABA)`: 18 (0.1%)
     - `Pediatric Urology`: 17 (0.1%)
     - `Wound Care`: 16 (0.1%)
     - `Bariatrics`: 16 (0.1%)
     - `Dentistry`: 15 (0.1%)
     - `Internal Medicine`: 13 (0.1%)
     - `Pediatric Allergy`: 10 (0.1%)
     - `Orthodontics`: 10 (0.1%)
     - `Neuro-Ophthalmology`: 10 (0.1%)
     - `Joint Surgery`: 10 (0.1%)
     - `Family Medicine`: 10 (0.1%)
     - `Pediatric Immunology`: 9 (0.1%)
     - `Anesthesiology`: 8 (0.1%)
     - `Addiction Medicine`: 8 (0.1%)
     - `Pediatric Plastic Surgery`: 6 (0.1%)
     - `Pediatric Hematology`: 6 (0.1%)
     - `Pediatric Dermatology`: 6 (0.1%)
     - `Gender Management Services`: 6 (0.1%)
     - `Pediatric Rehabilitation`: 4 (0.1%)
     - `Endodontics`: 4 (0.1%)
     - `Burn Surgery`: 4 (0.1%)
     - `Medical Genetics`: 3 (0.1%)
     - `Dietitian`: 3 (0.1%)
     - `Child and Adolescent Psychiatry`: 3 (0.1%)
     - `Surgery`: 2 (0.1%)
     - `Pharmacy`: 2 (0.1%)
     - `Pediatric Physical Medicine and Rehabilitation`: 2 (0.1%)
     - `Occupational Medicine`: 2 (0.1%)
     - `Colon and Rectal Surgery`: 2 (0.1%)
     - `Cardiovascular Surgery`: 2 (0.1%)
     - `Alternative Medicine`: 2 (0.1%)
     - `Social Worker`: 1 (0.0%)
     - `Radiation Oncology`: 1 (0.0%)
     - `Perinatology`: 1 (0.0%)
     - `Hospice Services`: 1 (0.0%)
     - `Emergency Medicine`: 1 (0.0%)
     - `Certified Clinical Nurse Specialist`: 1 (0.0%)
     - `Cardiovascular Disease`: 1 (0.0%)
     - `Aerospace Medicine`: 1 (0.0%)
     - `Acupuncturist`: 1 (0.0%)
- Note: Top specialties include Otolaryngology (ear/nose/throat), Ophthalmology (eye care), and Orthopedic Surgery (bone/joint issues), reflecting common pediatric referral needs.

6. **referral_number_of_visits** (Integer):
- Number of visits associated with the referral.
- Range: 1 to 10 (most referrals have 1 visit).
- Nullable; 26,601 rows are blank.
- Distribution (based on 349,827 referrals):
     - 1: 108,736 (31.1%)
     - 6: 213,345 (61.0%)
     - 3: 608 (0.2%)
     - 5: 476 (0.1%)
     - 10: 60 (0.0%)
     - 4: 1 (0.0%)
- Note: The majority of referrals (61.0%) have 6 visits, followed by 1 visit (31.1%). Values of 6 may indicate a standard follow-up schedule.

**Key Notes**:
- **De-identification**: `referral_date_age_in_days` replaces dates to protect privacy; no absolute dates available.
- **Missing Data**: There are 24,830 blank `visit_id` values, 27,452 blank `requested_specialty` values, and 26,601 blank `referral_number_of_visits` values.
- **Data Quality**: Specialty names are standardized; validate for consistency. Age range (1–6,567 days) aligns with pediatric focus.
- **Unique Counts**: Not all patients have referrals (138,071 of 250,588 total). There are 298,616 distinct referral visit IDs, but 98,623 non-null referral rows do not resolve to `visits.csv`, so this is not a complete visit-coverage count.
- **Linkage**: `patient_id` is a complete foreign key to `patients.csv`. `visit_id` is a logical but incomplete link to `visits.csv`; 98,623 non-null referral rows have visit identifiers absent from `visits.csv`, in addition to the 24,830 null visit IDs.

**Example Use Cases for LLMs**:
- Summarize referral patterns by `requested_specialty` or age group (`referral_date_age_in_days`).
- Analyze specialty utilization across demographics (e.g., from `patients.csv`: referrals for Otolaryngology by sex or ethnicity).
- Identify high-referral conditions by linking to `visits.csv` diagnoses (`enc_diag_*`) or `problem_list.csv` (`pl_diag`).
- Study referral outcomes using `referral_number_of_visits` (e.g., average visits per specialty).
- Perform longitudinal analysis of patient referral history (via `patient_id`).
- Predict referral needs using machine learning (e.g., based on visit patterns and demographics).
- Explore healthcare disparities in referrals by race, ethnicity, or sex from joined datasets.

**Important Considerations**:
- **Dataset Size**: 349,827 rows are manageable with standard tools (`pandas`, `dplyr`), but joining with larger datasets (e.g., `visits.csv` at 6.5M rows) may require efficient processing (e.g., chunking or `data.table`).
- **Unique Patients/Visit IDs**: 138,071 patients and 298,616 distinct `visit_id` values support longitudinal analyses; visit-level enrichment is conditional on the incomplete link to `visits.csv`.
- **Age Ranges**: Convert `referral_date_age_in_days` to years (divide by 365.25) for age-based groupings.
- **Specialty Variance**: 121 unique specialties; focus on top categories for summary analyses.
- **Visit Count Interpretation**: Most referrals have 1 or 6 visits; investigate if 6 represents a protocol or data artifact.
- **Privacy**: Respect de-identification; avoid re-identification attempts.
- **Computational Notes**: Memory-effective processing recommended; possible need for parallelization when joining large datasets.

**Example Code**:
```python
import pandas as pd

# Define the dtype dictionary for referrals.csv columns
dtype_dict = {
    "patient_id": "string",                    # Character/String for unique patient identifier
    "visit_id": "string",                      # Character/String for unique visit identifier
    "referral_id": "string",                   # Character/String for unique referral identifier
    "referral_date_age_in_days": "int32",      # Integer for age in days (1 to 6,567)
    "requested_specialty": "category",         # Categorical for 121 specialty types
    "referral_number_of_visits": "Int8",       # Nullable integer for visit count (1 to 10)
}

# Read the CSV file with specified dtypes
df = pd.read_csv("../p3-data/all/referrals.csv", dtype=dtype_dict)
```
