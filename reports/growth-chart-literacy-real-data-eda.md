# Real-data exploratory analysis for GrowthChartLiteracy

**Analysis date:** 2026-09-04
**Sources:** sections 1–5 and 7–10 from the CSV snapshot at `/Users/joon/w/p3-data/all`; section 6 from the typed DuckDB bundle `ppoc.duckdb` (package `ppoc-pediatric-ehr` 1.0.0, snapshot `2026-08-24`, sha256 `425c6f873cefc149344570561a03b33c69a6a6af7fa18bc777c0429579507116`), read-only
**Scope:** aggregate-only descriptive analysis of the real, de-identified PPOC snapshot; no patient-level identifiers or row-level records are included in this report.

## Executive summary

The snapshot contains **250,588 patients** and **6,494,473 augmented visits** spanning ages 0.00–17.99 years on the de-identified age clock. The data are longitudinal and clinically rich, but observation is uneven: encounter volume, anthropometric recording, diagnosis capture, referral capture, and the presence of a later follow-up visit all vary by age and source system.

For the GrowthChartLiteracy question, the strongest usable signal is the repeated height trajectory. Height is available at **99.9% of patients** at least once, **97.9%** have at least three height-derived observations across all ages, and **75.1%** retain at least three at age 2 years or later. That supports longitudinal trajectory work, while the visit-level completeness table shows why the missingness must remain explicit rather than being treated as random.

The distributed anthropometric layer also contains clinically important quality hazards. In particular, the head-circumference channel extends beyond the review range of 25–65 cm in **15,025 visits**, and head-circumference z-scores beyond ±5 occur in **16,663 visits**. These are data-quality findings, not clinical diagnoses. Weight-for-length, weight-for-stature, BMI, and head-circumference z-scores should be screened before they are used to construct stimuli or outcomes.

Section 6 profiles these and other characteristic EHR artifacts directly, and three of its findings change how the derived layer can be used. First, the distributed **height z-score is truncated at exactly +3** while its lower tail runs to −5: only **21 visits** sit at or above +3 where roughly **15,800** would be expected, so the tall-stature tail of the height channel is effectively absent. Second, **13,467 of the 15,025** out-of-range head circumferences are ordinary infant measurements that were put through an inch-to-centimetre conversion a second time, which makes that channel largely recoverable rather than simply unusable, though its z transform is separately defective. Third, the distributed **`delta_*` and velocity fields cannot be reproduced** from any natural definition of a successive height change (19.0% agreement at best), so velocity must be recomputed rather than consumed as supplied. Alongside these, height is recorded on a quarter-inch grid in **80.0%** of visits, which sets a floor on the trajectory deflection that is detectable at all.

The patient-level `growth_dx_flag` is present in **35,907 patients**; its median recorded age is **0.027 years**, with **70.1%** of age-observed flagged patients assigned a code in the first month. This supports the source project’s decision to treat diagnosis-code flags as descriptive rather than as a direct label of multi-year trajectory interpretation.

The candidate diagnosis/healthy-arm split also shows why a utilization covariate needs a common index date: flagged patients average **4.57** visits before diagnosis versus **14.02** for the healthy arm, even though their lifetime means are **25.32** versus **14.02**. The corresponding AUROCs are **0.131** for the pre-diagnosis count and **0.7447** for lifetime count; **45.8%** of flagged patients have no exact healthy-arm count match. This is a design diagnostic for the discarded flag-based arm, not a registered referral endpoint.

Referrals provide a useful action/care-pathway inventory—**349,827 records from 138,071 patients**—but this report does not estimate a referral/utilization prediction endpoint. That analysis is intentionally deferred in the GrowthChartLiteracy design; here referrals are described as recorded actions with positive-unlabeled and incomplete visit-linkage limitations.

### Clinical reading of the summary

A growth percentile, z-score, BMI category, or flag is a screening datum that must be interpreted in age, sex, measurement-quality, trajectory, and clinical-context frames. The report therefore emphasizes distributions, missingness, repeated-measure structure, and ascertainment rather than labeling individual children or recommending care.

## 1. Data provenance and analytic frame

The source project frames this dataset as a de-identified pediatric EHR panel from one US primary-care network. Calendar dates are absent; `age_in_days` is the only temporal axis. The augmented visit file contains CDC-LMS-derived growth metrics, velocities, flags, encounter metadata, and up to 33 encounter diagnosis fields. The source project’s plan is the clinical and methodological frame for this report: §Cohort and Data, §Preliminary Analysis, and the descriptions in `docs/data/` were read before analysis.

The files below were read in place from the supplied data directory. The augmented files are treated as derived data products; the base files are retained in the inventory so row counts and file lineage can be checked.

| resource | rows | size_mb | modified | grain |
| --- | --- | --- | --- | --- |
| patients.csv | 250,588 | 12.2 | 2025-03-17 15:06:11 -0400 | patient |
| patients_augmented-20251209150512.csv | 250,588 | 70.8 | 2026-07-01 14:23:58 -0400 | patient |
| visits.csv | 6,494,473 | 673.9 | 2025-03-17 15:07:35 -0400 | visit |
| visits_augmented-20251209150512.csv | 6,494,473 | 1,583.4 | 2026-07-01 14:24:17 -0400 | visit |
| labs.csv | 17,230,681 | 1,951.2 | 2025-03-17 15:05:35 -0400 | result component |
| medications.csv | 3,823,049 | 278.9 | 2025-03-17 15:06:10 -0400 | medication record |
| problem_list.csv | 1,709,584 | 60.6 | 2025-03-17 15:06:18 -0400 | problem-list entry |
| referrals.csv | 349,827 | 18.2 | 2025-03-17 15:06:21 -0400 | referral record |

### Linkage and grain

The augmented patient file has 250,588 rows and 250,588 distinct patient identifiers. The augmented visit file has 6,494,473 rows, 250,588 distinct patients, and 6,494,473 distinct visit identifiers. The referral file has 349,827 rows, 138,071 referred patients, and 349,827 distinct referral identifiers. The problem list has 1,709,584 rows and 238,823 patients.

The `patient_id` link resolves for essentially all rows in the patient-centered resources in this snapshot. Referral `visit_id` is a logical, incomplete link: the report measures that directly below. Labs, medications, and problem-list entries are treated as patient-linked resources; they are not assumed to be complete visit-level captures.

## 2. Patient composition and observation

### Sex, ethnicity, and race recording

Sex is nearly complete. Ethnicity and race are presented with non-response categories collapsed, because blank, unknown, unable-to-collect, and patient-does-not-know responses are not clinically equivalent to a substantive category but are all missing for subgroup inference.

**Recorded sex**

| category | patients | pct |
| --- | --- | --- |
| M | 127,699 | 51.0% |
| F | 122,883 | 49.0% |
| U | 6 | 0.0% |

**Ethnicity, with non-response grouped**

| category | patients | pct |
| --- | --- | --- |
| Not Hispanic or Latino | 170,594 | 68.1% |
| Missing / non-response | 51,445 | 20.5% |
| Hispanic or Latino | 28,549 | 11.4% |

**Primary race, with non-response grouped**

| category | patients | pct |
| --- | --- | --- |
| White | 155,375 | 62.0% |
| Missing / non-response | 50,055 | 20.0% |
| Another Race | 15,950 | 6.4% |
| Asian | 15,661 | 6.2% |
| Black or African American | 12,162 | 4.9% |
| American Indian or Alaska Native | 625 | 0.2% |
| Middle Eastern or Northern African | 512 | 0.2% |
| Native Hawaiian or Other Pacific Islander | 248 | 0.1% |

At least one later race field is populated for **11,169 patients (4.5%)**. 2,796 patients have a blank primary race field but a later race field populated; this is a data-structure reason to avoid interpreting `race_1` as a complete multiracial representation without checking all race columns.

### Visit history and age observation

Across patient rows, the median recorded visit count is **23** (IQR 15–34; range 1–244). The median observed span is **7.02 years** (IQR 3.31–10.87). The median first visit occurs at 0.02 years and the median last visit at 8.27 years.

| age_band | patients | median_visits | median_span_years |
| --- | --- | --- | --- |
| 0-<2 years | 194,651 | 25.00 | 6.15 |
| 2-<5 years | 32,420 | 21.00 | 11.07 |
| 5-<10 years | 20,212 | 14.00 | 7.41 |
| 10-<15 years | 3,305 | 10.00 | 5.00 |

**Clinical implication.** This is a birth-entry-heavy but right-censored panel: entering near birth does not mean a child is observed through adolescence, and a missing later record is not evidence that a condition was absent. Age-stratified denominators and a minimum look-forward rule are essential for any action/outcome analysis.

## 3. Visits, encounter context, and measurement availability

### Visit-level completeness by age

The denominators below are visits, not unique patients. Repeated measurements from high-utilization children therefore contribute more rows. BMI is structurally sparse below age 2 in the augmented pipeline, so its early missingness should not be interpreted as an isolated data-entry failure.

| age_band | visits | patients | height_present | height_present_pct | weight_present | weight_present_pct | bmi_present | bmi_present_pct | head_circ_present | head_circ_present_pct | any_diagnosis | any_diagnosis_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0-<2 years | 2,693,000 | 194,651 | 1,532,155 | 56.9% | 2,686,810 | 99.8% | 0 | 0.0% | 1,464,993 | 54.4% | 2,504,156 | 93.0% |
| 2-<5 years | 1,393,990 | 189,457 | 621,757 | 44.6% | 1,391,593 | 99.8% | 620,181 | 44.5% | 169,908 | 12.2% | 1,307,860 | 93.8% |
| 5-<10 years | 1,529,617 | 167,610 | 820,482 | 53.6% | 1,527,804 | 99.9% | 818,875 | 53.5% | 785 | 0.1% | 1,473,200 | 96.3% |
| 10-<15 years | 742,225 | 103,331 | 440,374 | 59.3% | 741,311 | 99.9% | 439,516 | 59.2% | 4 | 0.0% | 736,067 | 99.2% |
| 15-18 years | 135,641 | 35,579 | 76,894 | 56.7% | 135,489 | 99.9% | 76,767 | 56.6% | 0 | 0.0% | 135,326 | 99.8% |

### Encounter types

Encounter type is a care-process signal, not a physiologic signal. The predominance of office and well-visit records is useful for understanding capture, but should not be used as a proxy for a child’s clinical state.

| encounter_type | visits | pct_visits | patients |
| --- | --- | --- | --- |
| Office Visit | 4,725,643 | 72.8% | 250,266 |
| Well Visit (Conv.) | 778,452 | 12.0% | 97,553 |
| Sick | 580,991 | 8.9% | 72,589 |
| Follow-Up | 92,370 | 1.4% | 35,741 |
| Walk-In | 79,679 | 1.2% | 16,184 |
| Consult | 32,355 | 0.5% | 23,872 |
| Conversion Encounter | 32,007 | 0.5% | 8,412 |
| Newborn | 31,142 | 0.5% | 22,924 |
| Telemedicine | 25,658 | 0.4% | 19,808 |
| Telephone | 22,053 | 0.3% | 13,063 |
| Weight Check | 16,295 | 0.3% | 10,102 |
| Clinical Support | 15,347 | 0.2% | 11,005 |
| Documentation | 13,107 | 0.2% | 11,183 |
| Immunization | 11,774 | 0.2% | 8,378 |
| New Patient | 11,410 | 0.2% | 10,888 |

### Epic versus converted-source recording

The augmented source flag is evaluated as a completeness stratifier. A lower diagnosis or anthropometric capture rate in converted records would indicate ascertainment differences rather than a clinical difference between children.

| source | visits | height_present_pct | weight_present_pct | bmi_present_pct | any_diagnosis_pct |
| --- | --- | --- | --- | --- | --- |
| Y | 4,149,865 | 51.2% | 99.9% | 31.0% | 99.7% |
| N | 2,344,608 | 58.4% | 99.7% | 28.5% | 86.2% |

The visit diagnosis slots contain at least one code on **94.8% of visits**; the median number of occupied slots is 2.0 and the 95th percentile is 6.0. Diagnosis completeness should be reported alongside encounter source because converted records may be less richly coded.

## 4. Longitudinal anthropometric structure

### Height trajectory supply

Across all ages, 250,261 patients have at least one height-derived observation, 245,443 have at least three, and 235,646 have at least five. Restricting to age 2 years or later leaves 213,072 patients with at least one height, 188,282 with at least three, and 159,677 with at least five. Among patients with any age-2-or-later height, the median number of retained heights is 8.0.

Among successive age-2-or-later height measurements, the median gap is **1.00 years** (IQR 0.44–1.03; 95th percentile 1.32). **1.2%** of gaps exceed two years. This is clinically relevant censoring: a sparse trajectory may reflect follow-up, transfer, measurement choice, or data capture rather than stable physiology.

### Within-child dependence

The pooled lag-1 autocorrelation of successive age-2-or-later height z-scores is **0.924** across 1,746,433 pairs. Among patients with at least five age-2-or-later height observations, the between-patient standard deviation of patient mean height z-score is 0.909, while the median within-patient standard deviation is 0.346 (IQR 0.250–0.465). These values support patient-level resampling and mixed/repeated-measures reasoning; treating visits as independent would overstate precision.

### Age- and sex-stratified growth profile

The following table is visit-level and descriptive. Height z-score summaries use nonmissing height z-scores; BMI percentile summaries use nonmissing BMI percentiles and are limited to age 2 years or later. The threshold shares are screening descriptors, not diagnoses.

| age_band | sex | visits | height_n | height_z_median | height_z_p25 | height_z_p75 | height_z_lt_minus2_pct | height_z_gt_plus2_pct | bmi_n | bmi_percentile_median | bmi_lt5_pct | bmi_ge95_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2-<5 years | F | 677,359 | 303,825 | 0.36 | -0.31 | 1.02 | 0.9% | 4.5% | 303,113 | 57.8 | 6.5% | 8.5% |
| 2-<5 years | M | 716,626 | 317,930 | 0.34 | -0.32 | 1.02 | 1.1% | 4.8% | 317,066 | 56.8 | 6.9% | 9.4% |
| 2-<5 years | U | 5 | 0 | NA | NA | NA | NA | NA | 0 | NA | NA | NA |
| 5-<10 years | F | 745,589 | 393,897 | 0.13 | -0.53 | 0.78 | 1.7% | 2.7% | 393,140 | 66.4 | 2.9% | 13.2% |
| 5-<10 years | M | 784,028 | 426,585 | 0.20 | -0.46 | 0.88 | 1.3% | 3.6% | 425,735 | 66.2 | 3.3% | 14.5% |
| 10-<15 years | F | 366,624 | 214,074 | 0.22 | -0.45 | 0.89 | 1.3% | 3.6% | 213,626 | 68.2 | 2.9% | 14.7% |
| 10-<15 years | M | 375,601 | 226,300 | 0.31 | -0.38 | 1.01 | 1.1% | 5.0% | 225,890 | 69.0 | 3.8% | 18.4% |
| 15-18 years | F | 72,447 | 38,957 | -0.01 | -0.67 | 0.67 | 1.9% | 2.3% | 38,892 | 67.5 | 2.2% | 12.8% |
| 15-18 years | M | 63,194 | 37,937 | 0.14 | -0.49 | 0.78 | 1.1% | 3.0% | 37,875 | 68.6 | 3.6% | 16.3% |

**Patient-level age-2-or-later ever-patterns**

| sex | patients | patients_with_height | patients_ever_stunting | patients_ever_wasting | patients_with_bmi | patients_ever_underweight | patients_ever_obesity |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F | 122,883 | 104,628 | 3,758 | 8,121 | 104,625 | 15,697 | 22,466 |
| M | 127,699 | 108,444 | 3,477 | 7,678 | 108,428 | 17,911 | 27,532 |
| U | 6 | 0 | 0 | 0 | 0 | 0 | 0 |

The patient-level table answers a different question from the visit-level table: whether a child ever had a recorded threshold crossing while observed. It remains subject to informative measurement, follow-up, and source capture. It should not be interpreted as population prevalence without a defined surveillance denominator.

### Velocity measures

The augmented velocity fields are calculated only when the pipeline finds a prior measurement and a sufficient age interval. Their distributions should be inspected for interval effects, implausible jumps, and the influence of sparse endpoints before being used as model inputs. The robust summaries are included in the channel table below; no velocity threshold is used here to label an individual child.

## 5. Anthropometric distributions and data quality

### Robust channel distributions

Quantiles are shown because the maximum is highly sensitive to data-entry and transformation errors. Z-score fields are not assumed to be clinically valid solely because they are numeric.

| channel | unit | n | minimum | p001 | p01 | p05 | median | p95 | p99 | p999 | maximum |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| weight_kg | kg | 6,483,007 | 0.01 | 2.24 | 2.81 | 3.60 | 14.52 | 55.34 | 78.65 | 112.04 | 513.92 |
| height_cm | cm | 3,491,662 | 37.47 | 45.72 | 48.26 | 52.07 | 92.71 | 160.02 | 173.41 | 184.15 | 196.60 |
| bmi | kg/m^2 | 1,955,339 | 8.12 | 12.42 | 13.29 | 14.11 | 16.70 | 25.62 | 32.42 | 41.69 | 219.51 |
| head_circ_cm | cm | 1,635,690 | 0.00 | 30.25 | 33.00 | 34.29 | 44.00 | 50.00 | 53.00 | 124.46 | 505.46 |
| weight_z_score | z | 6,482,932 | -5.00 | -3.59 | -2.46 | -1.63 | 0.16 | 2.06 | 2.88 | 3.80 | 5.00 |
| height_z_score | z | 3,491,616 | -5.00 | -3.73 | -2.21 | -1.37 | 0.31 | 1.88 | 2.50 | 2.91 | 3.00 |
| bmi_z_score | z | 1,955,337 | -18.78 | -3.78 | -2.49 | -1.55 | 0.36 | 2.18 | 2.73 | 3.79 | 6.70 |
| weight_for_length_z_score | z | 2,027,317 | -145.60 | -4.57 | -3.19 | -2.21 | -0.19 | 1.64 | 2.45 | 3.62 | 7.63 |
| weight_for_stature_z_score | z | 1,371,347 | -14.34 | -3.94 | -2.80 | -1.88 | 0.10 | 1.85 | 2.63 | 3.67 | 7.48 |
| head_circ_z_score | z | 1,635,640 | -17,485.91 | -5.74 | -2.47 | -1.52 | 0.11 | 1.93 | 3.74 | 198.86 | 306,212.60 |
| height_velocity | cm/year | 2,786,770 | -47.12 | -2.12 | 0.03 | 3.12 | 7.82 | 33.11 | 43.58 | 52.57 | 81.80 |
| weight_velocity | kg/year | 5,754,032 | -620.28 | -11.04 | -2.29 | 0.50 | 3.20 | 11.41 | 16.54 | 22.54 | 724.19 |

### Review thresholds and transformation checks

Rows with a raw weight but no derived weight are 5,021; rows with a raw height but no derived height are 17,971. Under the source project’s review thresholds, |weight z| > 5 occurs in 0 rows and |BMI z| > 5 in 400 rows. The corresponding counts are 1,123 for weight-for-length z, 246 for weight-for-stature z, and 16,663 for head-circumference z. Head circumference outside 25–65 cm occurs in 15,025 rows; BMI outside 8–60 occurs in 44 rows. These are analysis-quality review rules from the source project, not universal bedside cutoffs.

For 1,955,339 age-2-or-later rows with distributed BMI, weight, and height, the median absolute difference between distributed BMI and recalculated BMI is 0.0000 kg/m²; the 95th percentile is 0.0000, and 0.0% differ by more than 0.1 kg/m². Flag-definition discordance counts are: stunting 0, wasting 0, underweight 0, and obesity 0. A nonzero discordance count should be resolved before treating distributed flags as ground truth.

### BMI categories in the age-2-or-later window

| category | visits | patients | pct_visits |
| --- | --- | --- | --- |
| normal | 1,338,418 | 193,723 | 68.4% |
| overweight | 280,226 | 84,669 | 14.3% |
| obese | 253,091 | 49,998 | 12.9% |
| underweight | 83,602 | 33,608 | 4.3% |

The category distribution is a description of recorded visits with a nonmissing BMI percentile. It is not a prevalence estimate: children with more visits contribute more observations, BMI is missing selectively, and the network’s patient mix and observation window are not a population-sampling frame.

<!-- BEGIN ehr-artifact-profile -->

## 6. Common EHR data artifacts

This section profiles recording, transformation, and linkage artifacts that are characteristic of electronic health record extracts. It was computed from the typed DuckDB bundle rather than the CSV directory; the generator and provenance are documented in the methods section. Every finding below describes the behaviour of a recording and derivation system. None of them is a statement about any child, and none is a clinical judgement.

Two distinct actors produce these artifacts and the report keeps them separate. Some are **capture artifacts** introduced where care is delivered and data are typed, such as digit rounding and repeated same-day measurements. Others are **derivation artifacts** introduced by the augmentation pipeline that computed z-scores, percentiles, velocities, and flags. A derivation artifact can be repaired without touching the clinical record; a capture artifact cannot.

**Bundle agreement check.** Before any new figure was computed, six review counts from the previous section were recomputed from the bundle: head circumference outside the 25–65 cm review range (15,025), |BMI z| > 5 (400), |weight-for-length z| > 5 (1,123), |weight-for-stature z| > 5 (246), |head-circumference z| > 5 (16,663), and BMI outside 8–60 (44). All six reproduce the values reported in section 5, so the bundle is the same snapshot (`2026-08-24`) and the counts in this section are directly comparable with the rest of the report.

### 6.1 Asymmetric truncation of the height z-score (derivation artifact)

The distributed height z-score is bounded above at exactly 3.00 while its lower tail runs to -4.9992. The truncation is not visible as a pile-up at the boundary, so it is easy to miss: only 21 visits sit at or above +3, and the upper tail decays smoothly right up to the bound.

The asymmetry is what exposes it. The two tails should be broadly comparable in a z-score channel, and they are not.

| tail | visits beyond 2.5 in absolute z | visits beyond 3 in absolute z | share of the 2.5 mass continuing past 3 |
| --- | --- | --- | --- |
| lower (negative z) | 21,248 | 9,637 | 45.4% |
| upper (positive z) | 34,732 | 21 | 0.06% |

In the lower tail, 45.4% of the mass beyond |z| = 2.5 continues past |z| = 3. If the upper tail behaved the same way, roughly 15,800 visits would sit above +3; 21 do. The tall-stature tail of the height channel is therefore effectively absent, while the short-stature tail is retained down to −5.

The obvious candidate mechanism does not survive checking. 17,971 visits carry a raw `height_in` but no derived `height_cm`, so the pipeline does discard some measurements — but those discards are short-skewed, not tall-skewed (1,719 imply a stature below 40 cm against 403 above 190 cm), and even counting every tall discard leaves the gap roughly forty times unexplained. Nor is the mass being dropped at the z step: only 46 visits carry a derived height with no z-score. The missing observations were never present in the derived channel rather than removed from it, which is consistent with a reference lookup that terminates at +3 — the height percentile stops at 99.87, the value z = 3 implies — but the snapshot does not expose the derivation, and the mechanism is not identifiable from it. The truncation itself does not depend on the explanation.

The bound is also channel-specific and undocumented in the field names. Weight z runs -4.9991 to 4.9995 and BMI z runs -18.7803 to 6.7026, so the three channels do not share a common support. Any model that consumes several z channels together inherits that inconsistency silently.

**Consequence for this project.** Tall stature is one of the two directions a growth-chart reader is asked to recognise. A height channel whose upper tail stops at +3 cannot support a tall-stature arm, and it will also distort any trajectory that approaches the bound from below. Constructed stimuli should not be calibrated against this channel's upper tail, and the tall-stature codes in the diagnosis table (E34.4 constitutional tall stature, Q87.3 early overgrowth) cannot be paired with a matching measured trajectory here.

The percentile channels show the same bounds from the other side.

| channel | n | at 0 | share at 0 | at 100 | share at 100 | minimum | maximum |
| --- | --- | --- | --- | --- | --- | --- | --- |
| height percentile | 3,491,616 | 2,801 | 0.080% | 0 | 0.000% | 0.00 | 99.87 |
| weight percentile | 6,482,932 | 3,584 | 0.055% | 5,221 | 0.081% | 0.00 | 100.00 |
| BMI percentile | 1,955,337 | 1,599 | 0.082% | 1,590 | 0.081% | 0.00 | 100.00 |
| weight-for-length percentile | 2,027,317 | 6,151 | 0.303% | 1,203 | 0.059% | 0.00 | 100.00 |
| weight-for-stature percentile | 1,371,347 | 1,509 | 0.110% | 856 | 0.062% | 0.00 | 100.00 |

The height percentile never reaches 100 because its z-score never exceeds +3, whereas weight, BMI, weight-for-length, and weight-for-stature percentiles all carry a point mass at both 0 and 100. Those exact-0 and exact-100 values are saturated rather than measured and should not be treated as continuous.

### 6.2 Terminal-digit heaping and measurement granularity (capture artifact)

Height and weight are captured in imperial units (`height_in`, `weight_oz`) and the metric fields are exact conversions of them. The recorded values are strongly heaped on human-readable fractions: of 3,509,633 heights, 31.0% fall on a whole inch, 54.9% on a half inch, and 80.0% on a quarter inch. Of 6,488,028 weights, 54.4% fall on a whole ounce, 30.4% on a half pound, and 24.6% on a whole pound.

Heaping is not uniform across childhood. Infant weights are recorded in ounces, and older children's weights are recorded to the pound, so the effective precision of the weight channel degrades as children age.

| age_band | visits | weights on a whole pound | heights on a whole inch |
| --- | --- | --- | --- |
| 0-<2 years | 2,687,964 | 8.1% | 33.0% |
| 2-<5 years | 1,394,136 | 33.3% | 32.1% |
| 5-<10 years | 1,528,542 | 37.3% | 29.1% |
| 10-<15 years | 741,702 | 39.4% | 27.2% |
| 15-18 years | 135,684 | 37.2% | 25.3% |

**Consequence for this project.** A quarter inch is 0.635 cm, and 80.0% of heights sit on that grid. The derived `height_cm` values carry two decimal places and imply a precision the underlying measurement does not have. This sets a floor on the trajectory deflection that is detectable at all: a deviation smaller than roughly half the rounding interval is not distinguishable from the rounding itself. Serialized stimuli should either preserve the observed grid or state the assumed precision explicitly, because a model shown `height_cm = 104.14` is being given a digit the clinic never measured.

### 6.3 Unit-conversion integrity and a recoverable head-circumference defect

The imperial-to-metric conversions are exact. Across 3,491,662 visits with both a raw and a derived height, 0 disagree with `height_in × 2.54` by more than 0.01 cm; across 6,483,007 weight pairs, 0 disagree with `weight_oz × 0.0283495`. The height and weight channels carry no unit-conversion defect.

Head circumference does. Its out-of-range values form structured clusters.

| head_circ_cm band | visits | median | minimum | maximum |
| --- | --- | --- | --- | --- |
| below 10 cm | 174 | 4.10 | 0.00 | 9.65 |
| 10 to <25 cm | 943 | 18.00 | 10.00 | 24.77 |
| 25 to 65 cm (within review range) | 1,620,665 | 44.00 | 25.00 | 65.00 |
| >65 to 200 cm | 13,472 | 110.49 | 65.50 | 193.04 |
| above 200 cm | 436 | 252.22 | 202.57 | 505.46 |

The cluster between 65 and 200 cm is not noise. It holds 13,472 visits with a median of 110.49 cm, and 13,467 of them — 99.96% — fall back inside the 25–65 cm review range when divided by 2.54, with a median of 43.5 cm. That is a normal infant head circumference. These are centimetre values that were passed through an inch-to-centimetre conversion a second time. A further 436 visits sit above 200 cm, of which 356 become plausible after dividing by 2.54 twice, consistent with the same conversion applied again.

This one defect explains most of the head-circumference damage the previous section reported. Of 16,663 visits with |head-circumference z| > 5, 14,899 (89.4%) sit on a head circumference outside the review range, and the double-converted cluster alone accounts for 13,467 of them. The remaining 1,764 visits have a plausible head circumference but still produce |z| > 5, so the z transform is independently defective as well and repairing the units would not fully fix the channel.

**Consequence for this project.** The previous section's guidance to exclude head-circumference z-score is confirmed, but the diagnosis is now specific rather than general: the raw channel is mostly recoverable by a documented division, and the derived z channel has a second, separate defect. That distinction matters because it means the raw head-circumference measurements are largely usable after repair, which the earlier framing did not establish.

### 6.4 Repeated measurements: zero growth, apparent shrinkage, and copy-forward

Across 1,746,627 successive age-2-or-later height pairs, 88,887 (5.09%) record exactly no change despite a positive age gap, and 59,134 (3.39%) record a decrease. Children in this age range do not shrink, so both categories are recording behaviour rather than physiology. Their dependence on the interval between measurements separates two different mechanisms.

| age gap between successive heights | pairs | exactly zero change | any decrease | decrease over 1 inch |
| --- | --- | --- | --- | --- |
| up to 7 days | 25,987 | 47.84% | 21.34% | 1.95% |
| 8 to 30 days | 82,685 | 32.00% | 19.05% | 1.43% |
| 31 to 90 days | 170,561 | 16.38% | 10.51% | 0.96% |
| 91 to 180 days | 205,195 | 5.15% | 4.22% | 0.52% |
| 181 to 365 days | 368,333 | 1.57% | 1.45% | 0.19% |
| over 365 days | 893,866 | 0.64% | 0.66% | 0.05% |

At short intervals the rates are dominated by measurement noise and rounding: within a week, a child genuinely has not grown a measurable amount, and the quarter-inch grid absorbs the rest, so nearly half of repeat heights are identical and a fifth are lower. At long intervals both mechanisms should vanish, and they do not entirely — over a year apart, exactly-zero change and apparent shrinkage each still occur in well under one percent of pairs, which is the residue consistent with a value carried forward or entered in error.

**Consequence for this project.** The short-interval rates are an empirical measurement-error estimate rather than a defect, and they are directly usable for the matched-noise requirement in the counterfactual stimulus design: any synthetic trajectory whose repeat measurements are noiseless will be unrealistically clean relative to this panel. The long-interval residue is a different matter and should be screened before serialization.

### 6.5 Same-day duplicate encounters and same-day measurement disagreement

Visit identifiers are unique, but a patient can have more than one visit row on the same age in days. This affects 5,478 patient-days (0.08% of 6,488,911) and 11,040 visits (0.17%). The rate is low, but it means `age_in_days` is not a unique key within a patient and any analysis that orders a trajectory by age alone has ties to resolve.

Where the same day carries two or more measurements, they often disagree. 2,958 patient-days carry at least two heights and 942 of those disagree (31.8%); 5,319 carry at least two weights and 2,648 disagree (49.8%).

| channel | patient-days with a disagreement | median spread | 95th percentile | maximum |
| --- | --- | --- | --- | --- |
| height | 942 | 3.18 cm | 12.16 cm | 34.93 cm |
| weight | 2,648 | 0.118 kg | 3.64 kg | 36.57 kg |

The height spread is the notable one. A median disagreement of 3.18 cm between two heights recorded on the same day is far larger than same-day weight disagreement in relative terms, and it is the size of difference expected when recumbent length and standing height are mixed, or when one value is carried from a previous note. It describes discordant same-day pairs rather than the panel as a whole, but it is a direct estimate of how far two heights recorded for the same child on the same day can sit apart.

### 6.6 Distributed delta and velocity fields are not reproducible (derivation artifact)

The augmented visit layer distributes `delta_height_cm`, `delta_age_in_days_height`, and the velocity fields derived from them. On a fixed sample of 43,952 rows carrying a nonmissing `delta_height_cm`, none of the three natural definitions of a successive height change reproduces the distributed value.

| candidate definition of the previous height | rows matching the distributed delta | share |
| --- | --- | --- |
| previous visit of any kind | 4,210 | 9.6% |
| previous height-bearing visit | 8,357 | 19.0% |
| previous raw `height_in`, converted | 3,906 | 8.9% |

Same-day ties are not the explanation: only 0.17% of visits share a patient-day with another visit, which cannot account for agreement as low as 19.0%. The ordering or the measurement series the pipeline used is therefore something this snapshot does not expose.

**Consequence for this project.** The velocity channels are built on these deltas, so `height_velocity`, `height_velocity_z_score`, and their pubertal variants inherit an unverifiable definition. Velocity should be recomputed from the height series with a stated definition rather than consumed as distributed, and the distributed velocity fields should not be serialized into stimuli. This is a stronger conclusion than the previous section's recommendation to inspect velocity distributions before use.

### 6.7 Measurement presence does not mean measurement (capture artifact)

Section 3 reported measurement completeness by age and by source system. Encounter type is the stratifier that shows the completeness figures cannot be read as measurement occurrence.

| encounter_type | visits | weight present | height present | first diagnosis present |
| --- | --- | --- | --- | --- |
| Office Visit | 4,725,643 | 99.9% | 52.2% | 95.8% |
| Well Visit (Conv.) | 778,452 | 99.7% | 98.2% | 94.4% |
| Sick | 580,991 | 99.8% | 16.8% | 95.4% |
| Follow-Up | 92,370 | 99.6% | 24.7% | 93.1% |
| Walk-In | 79,679 | 99.9% | 8.6% | 96.9% |
| Consult | 32,355 | 99.8% | 53.4% | 99.6% |
| Conversion Encounter | 32,007 | 99.8% | 66.5% | 17.3% |
| Newborn | 31,142 | 98.2% | 87.0% | 99.1% |
| Telemedicine | 25,658 | 97.3% | 44.6% | 99.8% |
| Telephone | 22,053 | 98.6% | 49.7% | 34.8% |
| Weight Check | 16,295 | 99.8% | 37.3% | 96.4% |
| Clinical Support | 15,347 | 99.3% | 15.3% | 83.4% |
| Documentation | 13,107 | 97.0% | 82.5% | 8.6% |
| Immunization | 11,774 | 97.3% | 30.5% | 93.4% |
| New Patient | 11,410 | 99.8% | 79.2% | 98.1% |

Telephone and telemedicine encounters carry a weight on the large majority of visits. A weight cannot be measured over the telephone, so those values were produced some other way — reported by a caregiver, populated from a nearby in-person encounter, or attached to an encounter whose type label does not describe how the patient was seen. The mechanism is not simple last-value carry-forward, as the following table shows.

| encounter_type | visits with a weight | weight identical to previous visit | identical with a gap over 7 days |
| --- | --- | --- | --- |
| Office Visit | 4,721,269 | 3.5% | 2.9% |
| Well Visit (Conv.) | 776,132 | 1.7% | 1.4% |
| Sick | 579,649 | 5.8% | 4.8% |
| Telemedicine | 24,977 | 6.5% | 5.4% |
| Telephone | 21,753 | 6.0% | 2.4% |
| Clinical Support | 15,233 | 4.3% | 2.1% |
| Documentation | 12,719 | 25.9% | 31.6% |

Only documentation encounters show a carry-forward signature, where about a quarter of weights exactly repeat the previous value and the rate rises rather than falls as the gap widens. Telephone and telemedicine weights mostly differ from the previous recorded weight, so the mechanism there is not last-value carry-forward; what it is instead is not identifiable from this snapshot.

**Consequence for this project.** A visit-level indicator that a measurement is present is not evidence that a measurement was taken at that encounter. The schedule-density manipulation in the counterfactual design assumes measurement-bearing visits are real measurement occasions; that assumption should be enforced by restricting to encounter types where physical measurement is possible, not by measurement presence alone.

### 6.8 Cross-resource temporal and linkage integrity

Age in days is the only clock in this snapshot, and ordering violations within a resource are visible directly. Counts below 10 are suppressed.

| integrity check | violating rows | rows checked | share |
| --- | --- | --- | --- |
| Lab result age earlier than lab order age | 583,055 | 14,947,495 | 3.901% |
| Medication start age earlier than order age | 329,107 | 3,539,983 | 9.297% |
| Medication end age earlier than start age | 12,709 | 3,179,759 | 0.400% |
| Problem resolved age earlier than noted age | 0 | 754,996 | 0.000% |
| Problem noted before birth (negative age) | 650 | 1,702,300 | 0.038% |
| Lab ordered before birth (negative age) | 47 | 17,230,681 | 0.000% |
| Medication ordered before birth (negative age) | <10 | 3,823,049 | 0.000% |
| Visit recorded before birth (negative age) | 0 | 6,494,473 | 0.000% |

The lab and medication violations are the substantial ones. A result age earlier than its order age and a start age earlier than its order age both indicate that these age fields are derived from different source timestamps with different semantics, so differences between them are not reliable durations. The small number of pre-birth ages are unrecoverable date errors.

Visit linkage is incomplete in every resource that carries a visit identifier, not only in referrals.

| resource | rows | rows with a visit_id | share missing a visit_id | nonnull visit_id not matching a visit | share of nonnull unresolved |
| --- | --- | --- | --- | --- | --- |
| labs | 17,230,681 | 17,229,876 | 0.00% | 5,201,657 | 30.19% |
| medications | 3,823,049 | 3,823,049 | 0.00% | 1,592,437 | 41.65% |
| referrals | 349,827 | 324,997 | 7.10% | 98,623 | 30.35% |

The medication result is the one that changes an assumption elsewhere in the package: `medications.visit_id` is declared required and is populated on every row, yet a large share of those values do not correspond to any visit in this snapshot. A required, populated foreign key that does not resolve is easy to mistake for a complete link. Section 8's referral linkage finding is therefore not specific to referrals; it is a property of the extract.

### 6.9 Laboratory results are semi-structured text

`result_value` is a text field. Of 17,230,681 rows, 2,494,261 (14.5%) carry no value at all, 7,621,449 (44.2%) parse as a number, and 7,114,971 (41.3%) do not. Among the non-numeric values, 484,242 are censored results carrying a comparator prefix such as `<3.3`, and the remainder are qualitative results (`NEGATIVE`, `NOT DETECTED`, `TRACE`), specimen descriptors, and administrative non-results (`NOT REPORTED`, `SEE NOTE`). A naive numeric cast silently discards nearly half the populated values and, more seriously, treats a left-censored result as missing rather than as a bound.

The declared key holds: `(lab_order_id, result_component_name, result_line_num)` has 0 duplicate groups. But 31,628 order-and-component pairs appear on more than one result line, and 23,679 of those (74.9%) carry disagreeing values — repeated or corrected results within a single order. Joining on order and component without the line number will multiply rows and pick an arbitrary value.

### 6.10 Vocabulary and categorical-string hygiene

Diagnosis strings are almost entirely well-formed ICD-10. Of 14,714,503 filled encounter-diagnosis slots across 8,029 distinct codes, 120,393 (0.82%) are not ICD-10-shaped; of 1,709,584 problem-list entries across 4,739 distinct codes, 13,555 (0.79%) are not. In both resources the non-conforming values are entirely `IMO0001` and `IMO0002`, proprietary Intelligent Medical Objects placeholders that Epic emits when a clinical term has no ICD-10 equivalent. `IMO0002` is the entry that appears in the problem-list table of this report as `[not in ICD-10 lookup]`: it is not a lookup failure but a code that carries no diagnostic meaning on its own. It should be excluded from code-based cohort definitions rather than treated as an unmapped diagnosis.

Categorical free-text fields are cleaner than is typical for an EHR extract. Normalising case and internal whitespace collapses lab procedure names from 3,742 to 3,739 distinct values, medication generic names from 1,073 to 1,073, and requested specialties from 119 to 119. Only the lab vocabulary collapses at all, and only by 3. Cosmetic irregularities are common — 1,669,090 lab rows carry an internal double space, and tall-man lettering such as `EPINEPHrine` is preserved from the source system — but they do not fragment the vocabularies. Grouping by these fields is safe after trimming; the risk here is presentational, not analytic.

### 6.11 Artifact summary

| artifact | class | scale in this snapshot | recoverable? |
| --- | --- | --- | --- |
| Height z-score truncated at +3 with the lower tail retained to −5 | derivation | 21 visits at the bound; roughly 15,800 expected above it | No — recompute z from raw height and a stated reference |
| Percentile point mass at exactly 0 and 100 | derivation | up to 6,151 visits in a single channel | No — treat as saturated |
| Terminal-digit heaping on quarter-inch and pound grids | capture | 80.0% of heights on a quarter inch | No — inherent precision limit |
| Head circumference double-converted inch-to-centimetre | derivation | 13,467 visits | Yes — divide by 2.54 |
| Head-circumference z defective on plausible measurements | derivation | 1,764 visits | No — recompute or exclude |
| Zero or negative height change over long intervals | capture | 0.64% and 0.66% of pairs over a year apart | Partly — screen before use |
| Same-day duplicate encounters with disagreeing measurements | capture | 942 patient-days for height | Partly — define a tie rule |
| Distributed deltas and velocities not reproducible | derivation | 19.0% agreement at best | Yes — recompute from the height series |
| Anthropometrics present on non-contact encounters | capture | weight on the large majority of telephone visits | Partly — restrict by encounter type |
| Lab and medication age fields violating their own ordering | capture | 583,055 and 329,107 rows | No — do not treat as durations |
| Populated visit_id not resolving to a visit | linkage | labs, medications, and referrals all affected | No — treat linkage as incomplete |
| Laboratory results as semi-structured text with censored values | capture | 484,242 comparator-prefixed results | Yes — parse comparators explicitly |
| Proprietary IMO placeholder codes | capture | 133,948 slots and entries | Yes — exclude from code-based cohorts |

The derivation artifacts are the ones that matter most for this project, because they affect exactly the fields a growth-chart model would consume and because they are invisible in the field names. Three of them — the height-z ceiling, the head-circumference conversion, and the unreproducible velocities — were not detectable from the distributional summaries in section 5 alone and required an explicit reconstruction of the derivation from the raw channel.

<!-- END ehr-artifact-profile -->

## 7. Diagnosis landscape

### Patient-level flags

These are source-derived flags, not adjudicated diagnoses. `healthy_flag` is especially restrictive because it requires multiple diagnosis and anthropometric conditions to remain absent across the observed record.

| flag | patients | pct |
| --- | --- | --- |
| growth_dx_flag | 35,907 | 14.3% |
| chronic_dx_flag | 203,935 | 81.4% |
| ever_stunting_flag | 17,889 | 7.1% |
| ever_wasting_flag | 66,704 | 26.6% |
| ever_underweight_flag | 33,608 | 13.4% |
| ever_obesity_flag | 49,998 | 20.0% |
| healthy_flag | 24,471 | 9.8% |

| group_label | patients | pct |
| --- | --- | --- |
| neither | 190,210 | 75.9% |
| growth diagnosis flag only | 35,907 | 14.3% |
| healthy flag only | 24,471 | 9.8% |

The growth flag has 35,907 patients; 35,890 have a parseable nonmissing diagnosis age. Negative diagnosis ages occur in 35 flagged patients. The first-month and first-year concentrations are 70.1% and 81.0%, respectively.

### Growth-related code composition

The table below uses patient-level derived code-age columns, which summarize whether a patient had any matching code in the source pipeline. It is sorted by patient count and is intentionally interpreted as coding composition, not trajectory truth. Counts below 10 are suppressed in the displayed table to reduce identifiability risk for rare conditions.

| code | description | patients_display | pct_growth_flag | median_age_display |
| --- | --- | --- | --- | --- |
| P92.6 | Failure to thrive in newborn | 14,428 | 40.2% | 0.03 |
| P07 | Short gestation / low birth weight | 11,014 | 30.7% | 0.03 |
| P05 | Slow fetal growth / fetal malnutrition | 4,069 | 11.3% | 0.01 |
| E30.1 | Precocious puberty | 3,405 | 9.5% | 7.87 |
| P70 | Transitory neonatal carbohydrate disorder | 3,353 | 9.3% | 0.00 |
| K90.0 | Celiac disease | 898 | 2.5% | 7.20 |
| E10 | Type 1 diabetes mellitus | 491 | 1.4% | 7.86 |
| E34.3 | Short stature due to endocrine disorder | 447 | 1.2% | 10.39 |
| E30.0 | Delayed puberty | 419 | 1.2% | 13.64 |
| E03.9 | Hypothyroidism, unspecified | 309 | 0.9% | 6.00 |
| Q90 | Down syndrome | 205 | 0.6% | 0.05 |
| E23.0 | Hypopituitarism | 150 | 0.4% | 9.03 |
| K50 | Crohn disease | 113 | 0.3% | 11.06 |
| E34.4 | Constitutional tall stature | 83 | 0.2% | 4.05 |
| N18 | Chronic kidney disease | 70 | 0.2% | 4.54 |
| K51 | Ulcerative colitis | 62 | 0.2% | 11.95 |
| Q87.1 | Congenital syndrome with short stature | 58 | 0.2% | 3.26 |
| P04.3 | Newborn affected by maternal alcohol use | 53 | 0.1% | 0.50 |
| Q87.3 | Congenital syndrome with early overgrowth | 46 | 0.1% | 1.76 |
| Q98.4 | Klinefelter syndrome, unspecified | 42 | 0.1% | 0.02 |
| Q96 | Turner syndrome | 36 | 0.1% | 0.15 |
| Q87.2 | Congenital syndrome involving limbs | 32 | 0.1% | 1.80 |
| E23.6 | Other pituitary-gland disorders | 31 | 0.1% | 8.29 |
| Q98.0 | Klinefelter syndrome, 47 XXY | 26 | 0.1% | 0.02 |
| Q87.4 | Marfan syndrome | 17 | 0.0% | 5.62 |
| Q98.5 | 47 XYY syndrome | 17 | 0.0% | 0.01 |
| Q77 | Osteochondrodysplasia | 15 | 0.0% | 5.13 |
| Q78.0 | Osteogenesis imperfecta | 10 | 0.0% | 1.63 |
| E22.0 | Acromegaly and pituitary gigantism | <10 | 0.0% | NA |
| Q78.1 | Polyostotic fibrous dysplasia | <10 | 0.0% | NA |
| N25.0 | Renal osteodystrophy | <10 | 0.0% | NA |
| E72.11 | Homocystinuria | <10 | 0.0% | NA |
| E24 | Cushing syndrome | <10 | 0.0% | NA |

### First-listed encounter diagnoses

This table is limited to `enc_diag_1`, the first-listed encounter diagnosis, and therefore does not represent complete diagnosis burden. It is included to show the clinical/coding case mix without expanding all 33 diagnosis slots into a row-level output.

| code | description | visits | patients |
| --- | --- | --- | --- |
| Z00.129 | Encounter for routine child health examination without abnormal findings | 2,116,156 | 247,531 |
| J06.9 | Acute upper respiratory infection, unspecified | 226,259 | 104,916 |
| J02.9 | Acute pharyngitis, unspecified | 188,205 | 85,074 |
| Z23 | Encounter for immunization | 141,979 | 71,416 |
| R50.9 | Fever, unspecified | 137,123 | 77,962 |
| Z00.121 | Encounter for routine child health examination with abnormal findings | 135,447 | 62,872 |
| Z00.110 | Health examination for newborn under 8 days old | 112,989 | 97,303 |
| R05.9 | Cough, unspecified | 100,871 | 60,361 |
| J02.0 | Streptococcal pharyngitis | 99,127 | 59,855 |
| B34.9 | Viral infection, unspecified | 83,251 | 52,255 |
| Z00.111 | Health examination for newborn 8 to 28 days old | 62,329 | 53,179 |
| F90.2 | Attention-deficit hyperactivity disorder, combined type | 57,672 | 11,449 |
| H66.001 | Acute suppurative otitis media without spontaneous rupture of ear drum, right ear | 57,244 | 40,247 |
| J18.9 | Pneumonia, unspecified organism | 49,740 | 34,080 |
| R21 | Rash and other nonspecific skin eruption | 49,060 | 38,536 |
| H66.002 | Acute suppurative otitis media without spontaneous rupture of ear drum, left ear | 48,442 | 35,572 |
| J05.0 | Acute obstructive laryngitis [croup] | 47,267 | 30,255 |
| H66.90 | Otitis media, unspecified, unspecified ear | 43,462 | 21,818 |
| Z20.822 | Contact with and (suspected) exposure to COVID-19 | 41,720 | 27,473 |
| H66.003 | Acute suppurative otitis media without spontaneous rupture of ear drum, bilateral | 38,768 | 28,513 |

### Problem-list diagnoses

| code | description | entries | patients |
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
| IMO0002 | [not in ICD-10 lookup] | 12,915 | 12,915 |
| R62.51 | Failure to thrive (child) | 12,503 | 12,503 |
| J30.9 | Allergic rhinitis, unspecified | 11,383 | 11,383 |
| Z91.018 | Allergy to other foods | 11,308 | 11,308 |
| J06.9 | Acute upper respiratory infection, unspecified | 11,197 | 11,197 |
| B08.1 | Molluscum contagiosum | 10,781 | 10,781 |

Problem-list entries do not carry a complete visit-level link and may include active, historical, or resolved conditions. Their presence is useful for case-mix context, but absence is not evidence that a condition was never present.

## 8. Specialty referrals and recorded care pathways

The referral file contains 349,827 records for 138,071 patients. The median recorded referral age is 5.98 years (IQR 2.02–10.60). Missingness is 7.8% for requested specialty, 7.1% for visit ID, and 7.6% for recorded referral visit count.

### Most frequent requested specialties

| specialty | referrals | pct_referrals | patients | median_age_years |
| --- | --- | --- | --- | --- |
| Otolaryngology | 35,723 | 10.2% | 29,567 | 3.99 |
| [blank] | 27,452 | 7.8% | 15,294 | 7.35 |
| Ophthalmology | 24,298 | 6.9% | 20,605 | 4.58 |
| Orthopedic Surgery | 22,887 | 6.5% | 19,521 | 9.97 |
| Allergy | 21,761 | 6.2% | 18,258 | 5.03 |
| Behavioral Health | 21,748 | 6.2% | 16,442 | 9.29 |
| Dermatology | 20,652 | 5.9% | 17,851 | 7.59 |
| Audiology | 15,972 | 4.6% | 13,616 | 2.24 |
| Gastroenterology | 14,344 | 4.1% | 12,467 | 5.57 |
| Cardiology | 13,610 | 3.9% | 12,134 | 6.83 |
| Neurology | 11,275 | 3.2% | 9,744 | 6.92 |
| Nutrition | 11,035 | 3.2% | 8,910 | 9.39 |
| Urology | 10,697 | 3.1% | 9,140 | 4.02 |
| Speech Pathology | 9,879 | 2.8% | 7,634 | 3.84 |
| Physical Therapy | 9,861 | 2.8% | 8,249 | 11.25 |
| Early Intervention | 9,302 | 2.7% | 8,511 | 1.41 |
| Developmental Medicine | 8,532 | 2.4% | 6,794 | 3.91 |
| Endocrinology | 6,641 | 1.9% | 5,583 | 9.37 |
| Occupational Therapy | 6,573 | 1.9% | 5,002 | 5.14 |
| General Surgery | 4,206 | 1.2% | 3,889 | 3.78 |

### Referral age distribution

| age_band | referrals | patients |
| --- | --- | --- |
| 0-<2 years | 83,982 | 46,347 |
| 2-<5 years | 70,413 | 38,164 |
| 5-<10 years | 96,241 | 50,864 |
| 10-<15 years | 79,461 | 40,381 |
| 15-18 years | 19,730 | 11,515 |

### Growth-relevant specialty families

| specialty_family | referrals | patients | median_age_years |
| --- | --- | --- | --- |
| Other / unspecified | 313,645 | 131,715 | 5.68 |
| Gastroenterology family | 14,715 | 12,764 | 5.58 |
| Nutrition family | 11,038 | 8,912 | 9.39 |
| Endocrinology family | 6,916 | 5,790 | 9.40 |
| Genetics family | 2,426 | 2,116 | 3.20 |
| Nephrology family | 1,087 | 937 | 6.03 |

The family groupings are text-based descriptive groupings created for this report; they are not a validated specialty ontology. They are useful for locating potential growth-related action pathways, not for assigning clinical indication.

### Referral record semantics and linkage

| recorded_visits | referrals |
| --- | --- |
| 1 | 108,736 |
| 3 | 608 |
| 4 | 1 |
| 5 | 476 |
| 6 | 213,345 |
| 10 | 60 |
| [missing] | 26,601 |

Patient IDs resolve for 100.0% of referral rows. Only 64.7% of referral rows have a nonblank visit ID that resolves to an augmented visit in this snapshot. The median number of referral rows per referred patient is 2.0 (75th percentile 3.0; maximum 63). The recorded count values 1 or 6 should not be assumed to mean completed specialty visits without a data dictionary for that field.

Per the GrowthChartLiteracy plan, referrals are inventoried here but no referral-versus-utilization model, AUROC, calibration curve, or endpoint claim is estimated. The action label is subject to positive-unlabeled interpretation: no recorded referral may mean no action, action outside the network, incomplete capture, or insufficient look-forward.

## 9. Labs, medications, and problem-list context

These resources provide case-mix and care-process context but are not substituted for the growth trajectory. The report summarizes counts and completeness without printing laboratory results, medication dates, or patient-linked records.

**Labs:** the projection-only source count is 17,230,681 rows; 17,230,518 rows were parser-readable for field-level aggregates (163 rows excluded after the CSV parser encountered malformed records). The readable rows cover 247,271 patients, 6,578,838 orders, and 12,902 result components. LOINC is present on 7.8% of readable rows, a result value on 85.5%, and a result flag on 9.7%. Patient IDs resolve to the augmented patient file on 100.0% of readable lab rows.

| lab_procedure | n_rows | n_patients |
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

**Medications:** 3,823,049 records for 236,323 patients. The order date is present on 100.0% of records, start date on 92.6%, and end date on 88.2%. Patient IDs resolve on 100.0% of medication rows.

| generic_name | n_rows | n_patients |
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

**Medication record type:**

| record_type | n_rows | n_patients |
| --- | --- | --- |
| Internal | 3,250,374 | 229,099 |
| External | 572,675 | 158,974 |

**Problem list:** 1,709,584 entries for 238,823 patients, with 44.3% having a populated resolved-age field. Patient IDs resolve on 100.0% of rows.

| code | description | entries | patients |
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
| IMO0002 | [not in ICD-10 lookup] | 12,915 | 12,915 |
| R62.51 | Failure to thrive (child) | 12,503 | 12,503 |
| J30.9 | Allergic rhinitis, unspecified | 11,383 | 11,383 |
| Z91.018 | Allergy to other foods | 11,308 | 11,308 |
| J06.9 | Acute upper respiratory infection, unspecified | 11,197 | 11,197 |
| B08.1 | Molluscum contagiosum | 10,781 | 10,781 |

## 10. Research and clinical implications for GrowthChartLiteracy

### What the data support

- A longitudinal, repeated-measures growth representation: age-2-or-later height observations are available for a large majority of patients, with enough repeated points for patient-level trajectories in a substantial analytic frame.
- Counterfactual stimulus construction calibrated to real schedule structure: the observed height gaps, within-child variation, between-child variation, and autocorrelation provide empirical targets for synthetic trajectories.
- Explicit utilization controls: visit count, encounter type, observation span, measurement density, and source-system provenance are visible care-process variables that can be profiled and balanced without treating them as physiology.
- A secondary recorded-action layer: specialty referral records can describe an observed care pathway, provided the index date, look-forward, missing linkage, and positive-unlabeled status are fixed before modeling.

### How the real data changed the experiment design

The real-data profile did not simply supply candidate subjects. It identified which parts of a record can represent physiology, which parts encode observation and care process, and which variables cannot serve as ground truth. The resulting design consequences are:

| Data characteristic observed in the real snapshot | Evidence from this snapshot | Experiment-design consequence |
| --- | --- | --- |
| **Longitudinal, irregular, repeated trajectories** | Median 23 visits per patient; median age-2-or-later height gap 1.00 years; height present on 53.8% of visits; lag-1 height-z autocorrelation 0.924. | E5a changes schedule density while preserving deviation-carrying visits, matched noise, and measurement availability; uncertainty is estimated at the patient or trajectory level rather than treating visits as independent. |
| **Observation and care process are informative** | Visit counts, encounter types, source-system provenance, measurement density, and observation span vary across the panel; only 64.7% of referral rows have a visit ID resolving to an augmented visit. | Utilization is treated as a possible shortcut. E2 describes the available care-process signal, E5 manipulates schedule while holding physiology fixed, and E7 crosses the two factors; the referral layer requires a matched index date and look-forward. |
| **Candidate labels are not trajectory truth** | `growth_dx_flag` covers 35,907 patients, has median age 0.027 years, and reaches 70.1% in the first month; the pre-diagnosis utilization field has AUROC 0.131 versus 0.7447 for lifetime count. | Diagnosis and `healthy_flag` are not used as the primary reference standard. Layer C uses referral as a secondary positive-unlabeled action outcome, while the counterfactual core uses constructed truth or within-subject response changes. |
| **Age and sex define the reference frame** | Calendar dates are absent and age is the only clock; 75.1% retain at least three heights at age 2 years or later, while BMI is structurally available only from age 2 in the augmented pipeline. | The primary trajectory frame is age 2 years and above, sex-specific reference curves are retained, and E9 tests whether the same crossing has different meaning in mid-childhood and the peripubertal window. |
| **Raw and derived representations coexist** | The augmented visit layer contains raw measurements alongside z-scores, percentiles, BMI, velocities, and clinical flags; the underlying clinical object is a plotted trajectory, while the planned model input is serialized text. | E3 compares raw, derived, and combined features across table, sentence, and digit-string formats, selects the format in a held-out split, and treats downstream findings as conditional on text serialization. |
| **Anthropometric quality is heterogeneous** | Head-circumference z-scores reach 306,212.60 and weight-for-length z-scores reach -145.60; 15,025 head-circumference values fall outside 25–65 cm. | Plausibility bounds are applied before serialization, head-circumference z-score is excluded until repaired or validated, and distributed flags are checked rather than assumed to be ground truth. |
| **The derived z and percentile channels are bounded, asymmetrically and inconsistently** | Height z is truncated at exactly +3 with only 21 visits at the bound against roughly 15,800 expected, while its lower tail runs to −5 and weight and BMI z use different supports; height percentile never reaches 100, and the other percentile channels carry a point mass at both 0 and 100. | Tall stature cannot be represented from this channel, so no tall-stature arm is drawn from measured trajectories and E9's peripubertal contrasts avoid the upper bound. Z-scores are recomputed from raw measurements against a stated reference before serialization rather than consumed as distributed. |
| **Recorded precision is coarser than the derived fields imply** | 80.0% of heights fall on a quarter-inch grid (0.635 cm) and whole-pound weight recording rises from 8.1% in infancy to 39.4% at 10–<15 years, yet derived `height_cm` carries two decimals. | The detectable-deflection floor is set from the observed grid rather than from the derived precision, E5a's matched noise is calibrated to it, and serialized stimuli either preserve the grid or state the assumed precision so that a spurious digit is not presented as a measurement. |
| **Measurement presence is not measurement occurrence** | Weight is recorded on 98.6% of telephone and 97.3% of telemedicine encounters, where physical measurement is impossible, and only about 6% of those repeat the previous value exactly. | Trajectory eligibility is defined by encounter types where measurement is possible, not by measurement presence, so E5a's schedule-density manipulation operates on real measurement occasions. |
| **Derived longitudinal fields are not reproducible** | No definition of a successive height change reproduces the distributed `delta_height_cm` (19.0% agreement at best), and same-day duplicate encounters are too rare (0.17% of visits) to explain the gap. | Velocity is recomputed from the height series under a stated definition; distributed velocity and delta fields are excluded from features and stimuli. |

The cohort is large enough that the planned real-patient samples are not supply-constrained. The binding constraints are comparable observation windows, trustworthy labels, and clinician time, which is why the core relies on constructed or counterfactual stimuli and the clinician panel validates roughly 110 curves rather than adjudicating thousands of real records.

Taken together, these characteristics make the study a layered, within-subject counterfactual test of physiology versus utilization shortcuts, with conventional referral-label accuracy analyses kept secondary.

### What the data do not support without additional governance or validation

- A claim that an ICD-10-derived growth flag is a clinician-adjudicated trajectory label. Its timing and composition are strongly affected by neonatal and billing capture.
- A claim that a missing referral is a negative clinical outcome. Referral capture is incomplete at the visit level and absence of a referral is not absence of concern.
- Population prevalence estimates from raw visit-level threshold shares. The observation process is utilization-dependent and repeated visits overweight children with longer or denser records.
- Clinical recommendations for any individual child. The report is aggregate EDA, not a diagnostic or treatment tool.
- Fair subgroup comparisons without missingness-aware denominators. Ethnicity and race non-response are substantial, and measurement and referral capture may vary by source and utilization.

### Recommended analytic guardrails

1. Use age 2 years or later as the primary growth-trajectory frame if the intended reference is CDC-based and the project wants to avoid mixing infant and post-infancy interpretation.
2. Define trajectory eligibility using measurement availability, not only visit count; report the number of height-bearing observations, span, and gaps.
3. Resample and model at the patient or trajectory level, not the visit level, when estimating uncertainty.
4. Treat missingness as potentially informative. Show missingness by age band, sex, race/ethnicity recording, encounter source, and utilization band before interpreting any subgroup contrast.
5. Recompute or validate distributed anthropometric flags after applying an explicit, source-documented plausibility pipeline. Exclude head-circumference z-score from trajectory serialization until its transform is repaired or independently validated. Repair the head-circumference measurement channel by dividing the double-converted cluster by 2.54 rather than discarding it, and note that the z transform remains defective on 1,764 visits with a plausible measurement.
6. Keep diagnosis, referral, and utilization labels separate. A diagnosis code is a recorded code; a referral is a recorded action; neither is an adjudicated physiologic truth.
7. Pre-specify the referral index and look-forward before estimating action-related performance, and report the result as record-based rather than as a diagnosis of the child.
8. Recompute z-scores and percentiles from raw measurements against an explicitly stated reference. Do not consume the distributed height z-score where the tall tail matters, and treat percentile values of exactly 0 and 100 as saturated rather than continuous.
9. State the assumed measurement precision wherever a trajectory is serialized, and do not present derived decimals the recording grid does not support. Set any detectable-deflection threshold at or above the rounding interval.
10. Recompute velocity from the height series under a stated definition. Do not use the distributed `delta_*` or `*_velocity` fields as model inputs until their definition is recovered from the source pipeline.
11. Restrict measurement-bearing visits by encounter type before treating them as measurement occasions, and resolve same-day ties with an explicit rule since `age_in_days` is not unique within a patient.
12. Treat visit-level linkage as incomplete in every resource, not only referrals. A populated `visit_id` in labs or medications does not imply a resolvable link, and lab and medication age fields violate their own ordering often enough that differences between them are not reliable durations.

## 11. Methods and reproducibility

The analysis used DuckDB 1.5.5 through the repository’s `uv` environment. The script materializes only selected columns needed for aggregate queries, uses age in days as the time axis, and does not export identifiers. Quantiles use DuckDB `quantile_cont`; repeated-measure summaries use patient-level grouping and age-ordered window functions. The ICD-10 lookup is normalized to one description per code before joins to prevent lookup duplication from multiplying diagnosis rows. Visit-level tables are explicitly labeled as visit-level; patient-level ever-patterns are grouped by patient.

Section 6 was computed separately from the typed DuckDB bundle rather than the CSV directory, because the artifact probes need repeated windowed passes over the full visit table. The bundle is opened read-only and never copied into the repository; the section emits aggregate tables only, and counts below 10 are suppressed. Before any artifact figure was computed the generator recomputes six review counts from section 5 and the section reports whether they agree, so a bundle drawn from a different snapshot would be visible rather than silently mixed into the report. Successive-measurement statistics in section 6 use an explicit `lag()` over height-bearing visits ordered by age; the distributed `delta_*` fields are not used as inputs because section 6.6 shows they do not reproduce that lag.

The report was generated by:

```sh
PPOC_DATA_ROOT=/Users/joon/w/p3-data/all uv run python reports/eda/build_growth_chart_literacy_eda.py

uv run python reports/eda/build_ehr_artifact_profile.py \
  --bundle /Users/joon/src/tries/ppoc-duckdb-real/ppoc.duckdb
```

The second command regenerates section 6 in place between its `ehr-artifact-profile` markers, so that section stays measured rather than hand-maintained.

The report is descriptive and exploratory. It does not constitute a registered endpoint analysis, a clinical validation study, a diagnostic device evaluation, or evidence of clinical benefit. The source data remain outside the repository; only this aggregate report and its analysis script are written locally.

## Source framing

- `/Users/joon/src/tries/growth-chart-literacy/growth-chart-literacy.md`, §0.3–§0.6, §Cohort and Data, §Preliminary Analysis, and E3–E7/E9
- `/Users/joon/src/tries/growth-chart-literacy/decisions/2026-08-30-restructure.md`, which records the move from an EHR-label gate to a counterfactual core and secondary referral-action layer
- `/Users/joon/src/tries/growth-chart-literacy/docs/data/data_description.md` and the resource-specific descriptions under `docs/data/`
- `/Users/joon/src/tries/growth-chart-literacy/review-2026-08-30-queries.sql` and `scripts/anthropometric_profile.sql`, used as prior analysis context and re-checked against the supplied real-data directory

## Clinical interpretation references

These references anchor the report’s interpretive guardrails; they do not turn aggregate EDA into clinical validation or patient-specific advice.

- [CDC Growth Charts](https://www.cdc.gov/growthcharts/): growth charts are percentile curves used to track growth and are not intended to be the sole diagnostic instrument.
- [CDC: What Growth Charts Are Recommended?](https://www.cdc.gov/growth-chart-training/hcp/overview/recommended.html): WHO Child Growth Standards are recommended from birth to 2 years and CDC Growth Charts from age 2 years onward in the US context.
- [CDC Child and Teen BMI Categories](https://www.cdc.gov/bmi/child-teen-calculator/bmi-categories.html): BMI categories for children and teens use sex-specific BMI-for-age percentiles; this report therefore treats BMI as age-2-or-later and descriptive.
- [WHO Child Growth Standards](https://www.who.int/tools/child-growth-standards/standards): documentation, indicators, and implementation resources for the WHO standards.
