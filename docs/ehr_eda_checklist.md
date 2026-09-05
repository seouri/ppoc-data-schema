# EHR Data EDA Checklist

A practical, hierarchical checklist for exploratory data analysis on any new EHR export — designed to be run top-down before substantive analysis begins.

---

## 0. Pre-EDA: Data Provenance Check

Do this before opening any tables.

- [ ] Confirm extraction window (start/end dates) and whether it's a snapshot or incremental pull
- [ ] Confirm inclusion/exclusion logic used to generate the export (e.g., "all encounters," "active patients only")
- [ ] Note EHR vendor/version and any known migration events during the extraction window
- [ ] Get the data dictionary / schema documentation — flag any fields not documented
- [ ] Confirm whether this is raw EHR data, a CDM (OMOP, PCORnet, i2b2), or a custom extract — this changes what artifacts to expect

---

## 1. Structural Integrity Checks

- [ ] **Row/table counts**: do counts match what the source system reports, or an expected ballpark?
- [ ] **Primary key uniqueness**: duplicate patient IDs, encounter IDs, order IDs
- [ ] **Referential integrity**: orphaned foreign keys (e.g., labs referencing encounters that don't exist)
- [ ] **Duplicate patient detection**: same person, multiple MRNs (check on DOB + name + sex, or linkage keys if available)
- [ ] **Schema drift**: compare column names/types against the data dictionary; flag renamed/dropped/added fields
- [ ] **Grain check per table**: confirm the actual grain (one row per patient? per encounter? per result?) matches what's assumed

---

## 2. Temporal Consistency Checks

- [ ] **Timestamp logic**: entry_time vs event_time vs order_time — are these distinct fields, and which one are you actually using?
- [ ] **Impossible sequences**: discharge before admission, result before order, death date before last encounter
- [ ] **Batch-entry clustering**: histogram of timestamps by hour/minute — spikes at shift-change or midnight suggest batch charting, not real-time events
- [ ] **System downtime gaps**: look for suspicious data voids (e.g., a full day missing across all patients)
- [ ] **Coding/vendor transition dates**: look for a structural break in volume, coding scheme, or field usage at a specific date (EHR go-live, vendor migration, ICD-9→10 transition)
- [ ] **Date-of-birth / age sanity**: negative ages, ages >110, birth dates in the future

---

## 3. Missingness Profiling

- [ ] **Missingness rate per field**, sorted — don't just eyeball a few columns
- [ ] **Missingness pattern**: MCAR vs. informative — does missingness correlate with time, site, provider, or another variable?
- [ ] **Sentinel/default values masquerading as data**: 999, 9999, "01/01/1900", "N/A", "UNKNOWN", 0 used as null
- [ ] **Distinguish "not measured" from "measured normal/negative"** — especially for labs, vitals, and problem lists
- [ ] **Missingness by site/department/provider**: uneven capture across locations is common and often systematic, not random

---

## 4. Distributional / Plausibility Checks

- [ ] **Univariate distributions** for all continuous fields (labs, vitals, meds doses) — look for:
  - Implausible values (heart rate of 0 or 300, weight of 1000 kg)
  - Unit inconsistencies (lbs vs kg, mg vs g) — often shows up as bimodal distributions
  - Digit preference / rounding artifacts (e.g., BP always ending in 0)
- [ ] **Categorical value counts**: check for inconsistent category labels (e.g., "M"/"Male"/"MALE" all present)
- [ ] **Outlier detection**: flag values beyond physiologically plausible ranges before deciding to exclude or winsorize
- [ ] **Cross-field plausibility**: e.g., pregnancy flag on a male patient, pediatric-range vitals on an adult

---

## 5. Coding / Terminology Checks

- [ ] **Code system versioning**: confirm which vintage of ICD/CPT/LOINC/RxNorm is in use, and whether it changes mid-dataset
- [ ] **Granularity consistency**: mixed use of broad vs. specific codes for the same concept
- [ ] **Problem list staleness**: check whether resolved/historical diagnoses persist without resolution dates
- [ ] **Free-text vs. structured field overlap**: does the same clinical fact appear inconsistently in both, and do they agree?
- [ ] **Local/custom codes**: flag anything not mapping cleanly to a standard vocabulary

---

## 6. Workflow / Documentation Artifact Checks

- [ ] **Copy-forward detection**: identical note text (or near-identical, via string similarity/hashing) across consecutive encounters for the same patient
- [ ] **Template/boilerplate detection**: repeated exact phrases across many different patients (suggests smart-phrase/macro use, not patient-specific findings)
- [ ] **Documentation timing vs. clinical timing**: end-of-shift clustering, weekend/holiday dips in documentation volume
- [ ] **Order-result reconciliation**: orders with no corresponding result, results with no corresponding order

---

## 7. Population / Selection Checks

- [ ] **Cohort representativeness**: compare demographics of your export against known hospital/system-level demographics (age, sex, race/ethnicity distributions) to catch extraction bugs or unintended filtering
- [ ] **Encounter-type mix**: sanity-check ratio of inpatient/outpatient/ED/telehealth against what's expected
- [ ] **Follow-up time distribution**: look for suspicious cliffs (e.g., everyone's data stops exactly at extraction date — expected — vs. earlier unexplained truncation)
- [ ] **Site/provider volume over time**: sudden drops or spikes suggest a site coming online/offline or reporting change, not a true clinical trend

---

## 8. Longitudinal Stability Checks (if multi-year data)

- [ ] **Trend breaks**: plot key variables (diagnosis rates, order volumes, documentation length) over time and look for discontinuities aligned with system changes rather than clinical reality
- [ ] **Guideline/policy shift artifacts**: coding or screening practice changes (e.g., new screening guideline) that shift prevalence without a true incidence change
- [ ] **Vendor/version changeover effects**: re-check schema and value-set consistency before and after any known migration

---

## Suggested First Pass

Run **Sections 1–3** (structural, temporal, missingness) fully before touching anything downstream — most EHR analysis errors trace back to one of those three. Sections 4–8 are where you'd focus once basic integrity is confirmed.
