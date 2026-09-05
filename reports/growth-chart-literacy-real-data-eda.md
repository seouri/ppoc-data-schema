<!-- project-overlay -->
# GrowthChartLiteracy: project overlay on the PPOC snapshot

**What this is.** The project-specific layer only: what GrowthChartLiteracy concluded from the PPOC extract, and what those conclusions changed about the experiment design.

**What this is not.** A description of the data. That is [`reports/ppoc-eda/`](ppoc-eda/) — a project-neutral exploratory analysis of the same snapshot, published as [HTML](ppoc-eda/index.html), [PDF](ppoc-eda/ppoc-eda.pdf), a [Markdown mirror](ppoc-eda/ppoc-eda.md), and machine-readable [`findings.json`](ppoc-eda/findings.json). This file used to carry both layers and had grown to 932 lines, most of it measurement that any project using this extract needs. That half now lives in one place.

**Precedence.** Every figure quoted here is measured in the data report at the cited section. Where the two disagree, **the data report is authoritative** — it is regenerated from the bundle and this file is maintained by hand.

---

## Where the measurements moved

| Was here | Is now |
| --- | --- |
| §1 provenance, linkage, grain | data report 1.1, 1.2, 3.1, 3.2 |
| §2 sex, ethnicity, race; visit history | 5.5 |
| §3 completeness by age, encounter types, source system | 3.4, 3.7 |
| §4 trajectory supply, within-child dependence, growth profile, velocity | 4.1, 4.9, 4.10, 4.8 |
| §5 distributions, review thresholds, BMI | 4.3, 4.11 |
| §6 EHR artifacts (all twelve subsections) | 3.1–3.8, 4.2, 4.4–4.8, and the catalogue at 7.1 |
| §7 diagnoses; §8 referrals; §9 labs, medications | 5.1–5.4, 5.6, 5.7 |
| §11 methods and reproducibility | 8.1 |

The data report also carries analyses this file never had: the cohort construction funnel (1.4), the checklist coverage map naming twelve checks this extract cannot support (2.1), the raw-versus-augmented layer comparison (1.3), and a field index over all 254 columns (6.1). `reports/audit_coverage.py` checks that every analysis once here still has a counterpart there.

---

## 1. What the data support

- **A longitudinal, repeated-measures growth representation.** Age-2-or-later height observations are available for a large majority of patients, with enough repeated points for patient-level trajectories (4.1).
- **Counterfactual stimulus construction calibrated to real structure.** Observed gaps, within-child and between-child variation, and autocorrelation give empirical targets for synthetic trajectories (4.10).
- **Explicit utilization controls.** Visit count, encounter type, observation span, measurement density, and source-system provenance are visible care-process variables that can be balanced without being treated as physiology (3.7, 5.5).
- **A secondary recorded-action layer.** Referral records describe an observed care pathway, provided index date, look-forward, missing linkage, and positive-unlabelled status are fixed before modelling (3.2, 5.4).

## 2. How the real data changed the experiment design

The profile did not simply supply candidate subjects. It identified which parts of a record can represent physiology, which encode observation and care process, and which cannot serve as ground truth.

| Data characteristic | Where it is measured | Experiment-design consequence |
| --- | --- | --- |
| **Longitudinal, irregular, repeated trajectories** | 4.1, 4.10 — lag-1 height-z autocorrelation 0.925, intraclass correlation 0.821 | E5a changes schedule density while preserving deviation-carrying visits, matched noise, and measurement availability; uncertainty is estimated at the patient or trajectory level, since a child contributes about 1.2 independent observations however many visits are recorded. |
| **Observation and care process are informative** | 3.2, 3.7, 5.5 | Utilization is treated as a possible shortcut. E2 describes the care-process signal, E5 manipulates schedule while holding physiology fixed, E7 crosses the two; the referral layer requires a matched index date and look-forward. |
| **Candidate labels are not trajectory truth** | 5.6, 5.7 — `growth_dx_flag` covers 35,907 patients at median age 0.027 years, and the tracked-code panel is dominated by perinatal codes | Diagnosis and `healthy_flag` are not the primary reference standard. Layer C uses referral as a secondary positive-unlabelled action outcome; the counterfactual core uses constructed truth or within-subject response changes. |
| **Age and sex define the reference frame** | 1.5, 3.4, 4.9 | The primary trajectory frame is age 2 and above, sex-specific reference curves are retained, and E9 tests whether the same crossing means something different in mid-childhood and the peripubertal window. |
| **Raw and derived representations coexist** | 1.3, 4.6 | E3 compares raw, derived, and combined features across table, sentence, and digit-string formats, selects the format in a held-out split, and treats findings as conditional on text serialization. |
| **Anthropometric quality is heterogeneous** | 4.3, 4.7 — 15,025 head circumferences outside 25–65 cm, of which 13,467 are recoverable by one division | Plausibility bounds are applied before serialization. Head circumference is **repaired before bounding** rather than deleted; its z-score stays excluded, since 1,764 visits carry a plausible measurement and still produce an extreme z. |
| **The derived z and percentile channels are bounded, asymmetrically** | 4.6 — height z truncated at +3, roughly 15,800 visits expected above it | No tall-stature arm is drawn from the distributed channel and E9's peripubertal contrasts avoid the upper bound. The planned ceiling change to +5 is retained, budgeted at roughly 15,800 visits rather than treated as free. Z-scores are recomputed against a stated reference before serialization. |
| **Recorded precision is coarser than the derived fields imply** | 4.2 — 80.0% of heights on a quarter-inch grid | The detectable-deflection floor is set from the observed grid, E5a's matched noise is calibrated to it, and stimuli either preserve the grid or state the assumed precision. |
| **Apparent height loss is mostly not error** | 4.5 — the long-interval decrease rate falls from 0.663% to 0.083% once restricted to ages 2–10 | Shrinkage is not filtered as an outlier: it is the recording grid acting on a flattened trajectory plus a protocol change at 2–3 years. A synthetic trajectory lacking both will not resemble this panel. |
| **Digit transposition is not a hazard here; unit and decimal errors are** | 4.4 | Screening bounds `height_in` and `weight_oz` before conversion and checks the recording grid, rather than spending effort on transposition detection. |
| **Derived longitudinal fields carry a definition the field names do not** | 4.8 — reproduce on 99.99% of rows under a 90–335 day interval rule, 43.7% under a naive lag | Velocity is consumed as distributed and the interval rule travels with it; no velocity here is compared with a visit-to-visit rate. |

The cohort is large enough that the planned real-patient samples are not supply-constrained. The binding constraints are comparable observation windows, trustworthy labels, and clinician time, which is why the core relies on constructed or counterfactual stimuli and the clinician panel validates roughly 110 curves rather than adjudicating thousands of real records.

Taken together these make the study a layered, within-subject counterfactual test of physiology versus utilization shortcuts, with conventional referral-label accuracy analyses kept secondary.

## 3. What the data do not support without further governance or validation

- **An ICD-10-derived growth flag as a clinician-adjudicated trajectory label.** Its timing and composition are dominated by neonatal and billing capture (5.6, 5.7).
- **A missing referral as a negative clinical outcome.** Referral capture is incomplete at the visit level; absence is not absence of concern (5.4).
- **Population prevalence from visit-level threshold shares.** Observation is utilization-dependent, repeated visits overweight densely recorded children, and the cohort itself excluded every patient carrying a code seen fewer than 11 times (1.4).
- **Clinical recommendations for any individual child.** This is aggregate analysis, not a diagnostic or treatment tool.
- **Fair subgroup comparisons without missingness-aware denominators.** Ethnicity and race non-response are substantial (5.5).

## 4. Project guardrails

General data-handling guidance now lives with the finding that motivates it, as *Implications for analysis* throughout the data report. What remains here is what is specific to this study:

1. **Frame.** Age 2 or later as the primary trajectory frame, so a CDC-based reference is not mixed with infancy.
2. **Eligibility.** Define it by measurement availability and by encounter types where physical measurement is possible — not by measurement presence (3.7).
3. **Uncertainty.** Resample and model at the patient or trajectory level (4.10).
4. **Derived channels.** Recompute z-scores and percentiles from raw measurements against a stated reference rather than consuming the distributed ones (4.6); repair head circumference before bounding (4.7); carry the velocity interval rule alongside any velocity (4.8).
5. **Precision.** State the assumed precision wherever a trajectory is written out, and set any detectable-deflection threshold at or above the recording grid (4.2).
6. **Labels.** Keep diagnosis, referral, and utilization separate; pre-specify the referral index and look-forward; report results as record-based rather than as a diagnosis of the child.
7. **Selection.** Read every frequency against the cohort funnel (1.4). Rare-condition and mortality questions are foreclosed by construction, and trajectory richness is an entry criterion rather than a finding.

## Source framing

- `/Users/joon/src/tries/growth-chart-literacy/growth-chart-literacy.md`, §0.3–§0.6, §Cohort and Data, §Preliminary Analysis, and E3–E7/E9. §Cohort and Data is the authority for the pipeline's declared filters and the planned ceiling change from +3 to +5 whose cost data report 4.6 measures.
- `/Users/joon/src/tries/growth-chart-literacy/decisions/2026-08-30-restructure.md`, recording the move from an EHR-label gate to a counterfactual core and secondary referral-action layer.
- `docs/data_description.md` and the resource descriptions under `docs/`, together with the PPOC delivery documents committed alongside them.

## Clinical interpretation references

These anchor the interpretive guardrails; they do not turn aggregate analysis into clinical validation or patient-specific advice.

- [CDC Growth Charts](https://www.cdc.gov/growthcharts/): percentile curves for tracking growth, not a sole diagnostic instrument.
- [CDC: What Growth Charts Are Recommended?](https://www.cdc.gov/growth-chart-training/hcp/overview/recommended.html): WHO standards from birth to 2 years, CDC charts from age 2 onward in the US context.
- [CDC Child and Teen BMI Categories](https://www.cdc.gov/bmi/child-teen-calculator/bmi-categories.html): sex-specific BMI-for-age percentiles, which is why BMI here is treated as age-2-or-later and descriptive.
- [WHO Child Growth Standards](https://www.who.int/tools/child-growth-standards/standards).
- Daymont C, Ross ME, Localio AR, Fiks AG, Wasserman RC, Grundmeier RW (2017). Automated identification of implausible values in growth data from pediatric electronic health records. *JAMIA* 24(6):1080–1087.
- Agniel D, Kohane IS, Weber GM (2018). Biases in electronic health record data due to processes within the healthcare system: retrospective observational study. *BMJ* 361:k1479.
