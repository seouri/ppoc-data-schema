# Plan: a project-neutral EDA reference for the PPOC snapshot

**Status:** implemented. The report is built by `reports/build_ppoc_eda.py` and published to `reports/ppoc-eda/`.
**Outcome.** It did supersede the earlier work in the end: `reports/growth-chart-literacy-real-data-eda.md` has been reduced to a thin project overlay that cites this report, and the two generators under `reports/eda/` were removed once every analysis they produced had a counterpart here. `reports/audit_coverage.py` guards that split.

---

## 1. Purpose and success criteria

One reference document that any researcher touching this PPOC snapshot reads before they start, so that they do not repeat analysis someone has already done and do not miss analysis they should have done.

It succeeds if a researcher can answer all four of these without opening DuckDB:

| Question | Where the report answers it |
| --- | --- |
| "What is in this snapshot and how do the tables join?" | Part 1 |
| "I am about to use field `X` — what do I need to know about it?" | Part 6 field index → linked finding |
| "I got a strange number. Is it known?" | Part 7 artifact catalogue |
| "Have I checked everything I should have?" | Part 2 coverage map, including what this data *cannot* support |

The fourth is the one that is currently unserved and is the main reason to build this.

---

## 2. Scope, non-goals, and neutrality rules

### In scope
All eight resources in the `ppoc-pediatric-ehr` package, both the raw and the augmented layer, at the snapshot pinned in Part 1.

### Non-goals
- Not a clinical validation, a registered analysis, or a statement about any child.
- Not a tutorial on the science of growth assessment.
- Not a replacement for `docs/*.md`, which stay the field-level data dictionary. This report is the *empirical* companion: what the data actually do, as opposed to what the schema says they should.

### Neutrality rules (hard constraints on the writing)

1. No mention of GrowthChartLiteracy, its experiments (E3/E5a/E7/E9), its arms, stimuli, serialization format, or its endpoints.
2. No file paths outside this repository. In-repo references (`docs/`, `datapackage.json`, `schema/`) are fine and encouraged.
3. Every `**Consequence for this project.**` paragraph is replaced by **`Implications for analysis.`**, written for an unknown reader with an unknown question.
4. **No finding may depend on an external document as its authority.** Where the current report cites an upstream project plan for a mechanism — the height z bound, the velocity interval rule — the new report either re-derives it empirically or states it as an inference and shows the evidence. The velocity rule already qualifies: it reproduces on 99.99% of rows, which is proof independent of any document. The z bound qualifies too: the ceiling at exactly 3.00 with 21 visits at the bound is observable directly.
5. Interpretive guidance is phrased as a conditional ("if you intend to use the tall tail, note that…"), never as a directive derived from one project's design.

---

## 3. Output format decision

**Decision: author in HTML, derive a PDF from it, and carry `findings.json` as the source of truth.** Four artifacts, one computation pass, all committed.

### Why not Markdown alone
Roughly ten of the findings are far clearer as pictures than as tables — the asymmetric z-score tail, the terminal-digit grid, the head-circumference conversion bands, the apparent-shrinkage curve by age and sex, the cohort funnel, the missingness matrix over 254 fields. Markdown cannot inline them without shipping a directory of PNGs, which diff badly and drift from the text.

### Why HTML is the authored format, and PDF the published one
GitHub renders a committed PDF in the browser. It does **not** render committed HTML — it shows the source. So the PDF is what makes this readable to someone who never clones the repo, and the HTML is what makes it pleasant for someone who does.

| Option | Role |
| --- | --- |
| Quarto | Rejected: adds a non-Python binary to the toolchain for no capability this needs. |
| Jupyter notebook | Rejected: a reference document is read, not executed; notebooks diff badly and invite stale output. |
| **HTML, authored** | Inline SVG, sticky table of contents, per-finding anchors, find-in-page, opens offline with no server. |
| **PDF, derived from the HTML** | Viewable directly on GitHub, citable with stable page numbers, printable. |
| `findings.json` | Machine-readable source of truth; the only thing that diffs cleanly. |
| Markdown mirror | What a reviewer reads in a pull-request diff. |

### The four outputs

| File | Role | Committed |
| --- | --- | --- |
| `reports/ppoc-eda/index.html` | Authored primary. Self-contained: inline SVG and CSS, no external requests. | yes |
| `reports/ppoc-eda/ppoc-eda.pdf` | Derived from the HTML. The GitHub-viewable artifact. | yes |
| `reports/ppoc-eda/findings.json` | Every number the report states, keyed by stable finding id. | yes |
| `reports/ppoc-eda/ppoc-eda.md` | Text mirror; figures become captions linking to HTML anchors. | yes |

**Anti-drift rule:** prose is a template; every number in every output interpolates from `findings.json`. A number cannot appear in one output and not another, and cannot be hand-edited into any of them.

### HTML → PDF pipeline

Headless Chrome, which is present on this machine at `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`, and which renders exactly the CSS and SVG the HTML already uses — so the PDF cannot disagree with the HTML about anything.

```
chrome --headless=new --disable-gpu --no-pdf-header-footer \
       --print-to-pdf=reports/ppoc-eda/ppoc-eda.pdf \
       file://$PWD/reports/ppoc-eda/index.html
```

Resolution order: `$PPOC_CHROME`, then `PATH` (`google-chrome`, `chromium`), then the known macOS app paths. If none is found the HTML, JSON, and Markdown still build and the PDF step reports a clear skip — the PDF is never a build blocker.

**Print stylesheet** (`@media print`), required for the PDF to be worth committing:
- Force the light palette; a dark background is wrong on paper and enormous in ink.
- `@page { size: A4; margin: 18mm 16mm; }` with running heads carrying part and section.
- `break-inside: avoid` on figures, finding blocks, and table rows; `break-before: page` on each Part.
- Expand anything that is interactive-only in HTML — a collapsed field index must be fully expanded in print.
- Render link targets as footnoted anchors, since a PDF reader cannot follow an in-page `#id` the way a browser does.

**Committed-binary discipline.** A PDF that changes on every build would bloat history. Two mitigations, in order:
1. **Rebuild only on change.** The build compares newly computed findings against the committed `findings.json`; if they are identical, the HTML/PDF/Markdown are left untouched. An unchanged snapshot therefore produces no new blob at all. This is the primary defence and it works regardless of renderer stability.
2. **Normalize what is still non-deterministic.** Chrome stamps `/CreationDate`, `/ModDate`, and a trailer `/ID`. Rewrite the dates to a fixed value derived from the snapshot date, then run `qpdf --deterministic-id` (available at `/opt/homebrew/bin/qpdf`).

Whether Chrome's output is byte-stable beyond that — font subsetting and object numbering — is **not assumed**. Phase 1 includes a determinism spike that builds twice and diffs; mitigation 1 makes the answer non-blocking either way.

### Charts: hand-rolled SVG, no new dependency

The project has five lean runtime dependencies and no plotting library. The chart vocabulary needed is small and repetitive — histogram/bar, grouped bar, line with optional series split, heatmap, step, and a funnel. That is roughly 400 lines of a `charts.py` emitting SVG directly from numpy-computed bin counts.

Hand-rolling also buys two things matplotlib does not: the SVG inherits CSS custom properties, so figures follow the light/dark toggle *and* the print stylesheet's forced-light rule; and the output is small and diff-stable.

**Fallback if the vocabulary grows:** add `matplotlib` under a new optional `[dependency-groups] report`. Recorded so the decision is not relitigated silently.

When the charts are built, load the `dataviz` skill first — palette, axis, and legend conventions should not be improvised.

## 4. Report structure

Firm. Numbered parts, stable anchor ids, every finding individually linkable as `#f-<probe>-<slug>`.

### Part 0 — How to use this report
- 0.1 **Three entry points.** New to the data → Part 1. About to use a specific field → Part 6. Explaining a strange number → Part 7.
- 0.2 What this report is and is not; aggregate-only and suppression policy.
- 0.3 Snapshot identity and how to regenerate.

### Part 1 — The snapshot
- 1.1 Package identity and integrity: name, version, snapshot date, bundle sha256, row counts reconciled against `manifest.json` and `datapackage.json`, schema drift against the declared descriptor.
- 1.2 Resource map: eight tables, their grain, primary keys, and join paths. **Figure: entity/link diagram annotated with row counts and measured link-resolution rates.**
- 1.3 **The two layers.** What the augmentation adds on top of the raw extract, and where the two disagree. This subsection is new and is the clearest example of what the current report misses — see §6.
- 1.4 **How this cohort was built.** The full selection pipeline, recovered from the PPOC delivery documents and reconciled against the data. **Figure: cohort funnel.** This is the single most consequential subsection in the report; see §5A.
- 1.5 **The de-identification envelope.** Calendar dates, names, sites, providers, and time-of-day are absent; `age_in_days` is the only clock. Stated once, here, with the list of checks it forecloses, then referenced from Part 2 rather than re-argued.

### Part 2 — Checklist coverage
- 2.1 **Coverage table.** Every item in `docs/ehr_eda_checklist.md`, mapped to: covered / partially covered / not applicable, the report section holding the evidence, and — for anything not fully covered — the reason.
- 2.2 **What this snapshot cannot tell you.** The N/A items consolidated into one list a researcher can read in a minute, so nobody spends a day looking for a provider field.
- 2.3 **Selection effects you cannot analyse around.** Distinct from 2.2: these are questions the data will happily *appear* to answer while returning a biased result. Rare-code exclusion, alive-only ascertainment, the ≥5-measurement requirement, and the recency filter each belong here, with the specific analyses each one invalidates.

### Part 3 — Integrity
- 3.1 Keys, grain, and uniqueness.
- 3.2 Referential integrity and cross-resource linkage.
- 3.3 Age-axis consistency: ordering violations, impossible sequences, out-of-range ages.
- 3.4 Missingness: per field, and conditioned on age band, sex, encounter type, and source system. **Figure: missingness matrix.**
- 3.5 Sentinel and placeholder values masquerading as data.
- 3.6 Terminology: code systems, vintage, granularity, non-conforming and proprietary codes, categorical string hygiene.
- 3.7 Capture and workflow artifacts: measurement presence versus occurrence, copy-forward, order/result reconciliation.

### Part 4 — Anthropometrics
The deep domain section, because it is the richest part of this data and the most artifact-prone.
- 4.1 Availability and trajectory supply (how many children support how long a trajectory).
- 4.2 Recording units, precision, and the measurement grid. **Figure: terminal-digit heaping by age band.**
- 4.3 Distributions and plausibility bounds. **Figure: height/weight/BMI distributions with review ranges overlaid.**
- 4.4 Unit confusion and transcription artifacts, with the permutation-null method stated once. **Figure: mechanism enrichment, observed against null.**
- 4.5 Repeated measurements: zero growth, apparent loss, copy-forward. **Figure: apparent-loss rate by age, split by sex.**
- 4.6 Derived channels: z-scores, percentiles, categories, flags — bounds, saturation, and defects. **Figure: z-score tail asymmetry.**
- 4.7 Derived longitudinal channels: deltas and velocities, and the interval rule that defines them.
- 4.8 **A screening pipeline for anthropometrics** — ordered steps with runnable SQL, from raw plausibility bounds through unit repair to derived-channel selection. The single most reusable page in the report.

### Part 5 — Other clinical domains
Same shape at lower depth: 5.1 diagnoses (encounter and problem list), 5.2 laboratory results, 5.3 medications, 5.4 referrals, 5.5 demographics and recorded identity.

### Part 6 — Field index
Every column across all eight tables. Columns: table, field, type, non-null count, missing %, distinct count, range or top levels, artifact flags, link to the governing finding.

The 33 `enc_diag_*` slots collapse to one row plus an occupancy profile; likewise `race_1`–`race_8`. Expected size after collapsing: roughly 190 rows. Sortable and filterable in HTML.

### Part 7 — Artifact catalogue
The master table, one row per known artifact: artifact, class (capture / derivation / linkage / de-identification), scale in this snapshot, how to detect it, whether it is recoverable, and the recipe. Every row links to its full treatment.

### Part 8 — Methods, determinism, and limitations
Computation environment, suppression policy, the permutation-null design, determinism guarantees, snapshot pinning, and an explicit statement of what a different extract would invalidate.

---

## 5. Coverage map: the checklist against this snapshot

Drafted now because it determines what the script must compute. Status is my assessment from the column inventory; the report will state it as measured.

| Checklist item | Status | Note |
| --- | --- | --- |
| 0. Extraction window | **Covered** | Recovered from the delivery documents: cohort as of 31 Dec 2024, extract 03 Feb 2025, registry snapshot 18 Jul 2024. Not in the data; not previously in the repo. |
| 0. Inclusion/exclusion logic | **Covered, and it is the headline** | Full four-step funnel with counts reconciling to 250,588. See §5A.1. `docs/data_description.md` does not contain it. |
| 0. Vendor/version, migration events | Covered | `orig_enc_source_Epic_yn` marks Epic against converted records — the migration signal. |
| 0. Data dictionary present | Covered | `docs/*.md` + `datapackage.json`; drift check is computable. |
| 0. Raw vs CDM vs custom | Covered | Custom extract **plus a derived augmentation layer** — the distinction that matters most here. |
| 1. Row/table counts | Covered | Reconcile against `manifest.json` **and against the vendor's own stated counts**, including lab orders (6,578,838) and patients with a lab (247,271), both of which already reproduce exactly. |
| 1. Primary key uniqueness | Covered | All eight resources. |
| 1. Referential integrity | Covered | Includes the populated-but-unresolvable `visit_id` finding. |
| 1. Duplicate patient detection | **N/A** | No DOB, name, or linkage key survives de-identification. |
| 1. Schema drift | Covered, **and it is non-empty** | Live schema against `datapackage.json` *and* against the vendor dictionary; three documented medication class fields were never delivered. See §5A.3. |
| 1. Grain per table | Covered | Including that `(patient_id, age_in_days)` is *not* unique in visits. |
| 2. Timestamp logic | Covered | Order / result / start / end age fields and their differing semantics. |
| 2. Impossible sequences | Covered | Result before order, end before start, pre-birth ages. |
| 2. Batch-entry clustering | **N/A** | No time-of-day anywhere; ages are integer days. |
| 2. System downtime gaps | **N/A** | Requires calendar dates. |
| 2. Coding/vendor transition | Partial | Epic-vs-converted contrast is computable; ICD-9→10 is not, without dates. |
| 2. Age sanity | Covered | Negative and out-of-range ages. |
| 3. Missingness per field | Covered | All 254 columns → Part 6. |
| 3. Missingness pattern | Covered | By age, sex, encounter type, source system. |
| 3. Sentinel values | Covered | Zero, blank, `UNKNOWN`, `Unable to collect`, and similar. |
| 3. Not-measured vs measured-negative | Covered, **and two fields are currently misread** | `result_flag` null = normal and `resolved_date_age_in_days` null = active problem. See §5A.2. |
| 3. Missingness by site/provider | **N/A** | No site, department, provider, or facility field exists. Encounter type is the nearest available proxy and is used instead. |
| 4. Univariate distributions | Covered | All continuous fields. |
| 4. Unit inconsistencies | Covered | Part 4.4. |
| 4. Digit preference | Covered | Part 4.2. |
| 4. Categorical value counts | Covered | Part 3.6. |
| 4. Outlier detection | Covered | Bounds reported before any exclusion is recommended. |
| 4. Cross-field plausibility | Covered | Includes BMI recomputed from height and weight. |
| 5. Code system vintage | Covered | ICD-10 shape conformance, LOINC coverage on lab results. |
| 5. Granularity consistency | Covered | Part 3.6. |
| 5. Problem list staleness | Covered | Resolved-date population rate. |
| 5. Free-text vs structured | Covered | `result_value` as semi-structured text. |
| 5. Local/custom codes | Covered | The IMO placeholders. |
| 6. Copy-forward detection | Partial | Detectable on measurements; **N/A for note text**, which is not in the extract. |
| 6. Template/boilerplate | **N/A** | No note text. |
| 6. Documentation timing | **N/A** | No timestamps. |
| 6. Order-result reconciliation | Covered | Labs. |
| 7. Cohort representativeness | Partial, **and the cohort is not representative** | No external benchmark ships with this repo, but the selection rules are now known: alive-only, ≥5 growth measurements, recency-filtered, rare-code-excluded. Reported as a selection description rather than an unexplained distribution. |
| 7. Encounter-type mix | Covered | Part 3.7. |
| 7. Follow-up time distribution | Covered | Trajectory span and later-visit availability. |
| 7. Site/provider volume | **N/A** | No such field. |
| 8. Trend breaks over calendar time | **N/A** | No calendar axis. Age-axis profiles are reported instead and are explicitly *not* the same thing. |
| 8. Guideline/policy shift | **N/A** | Requires calendar time. |
| 8. Vendor changeover effects | Partial | Epic-vs-converted contrast only. |

After folding in the delivery documents, eleven items are not applicable and three more are partial; two that were partial are now fully covered. **Publishing that list is a deliverable in itself** — it is the difference between a researcher spending an hour confirming a field does not exist and reading one line.

---

## 5A. What the PPOC delivery documents add

Three documents shipped with the data: a cohort/exclusion workbook, a field dictionary workbook, and a Visio extract diagram. I inspected all three. **Almost none of their content is in this repository**, and several items contradict or explain findings in the existing report.

### 5A.1 The cohort was heavily selected, and the repo does not say so

Recovered from the extract diagram and the workbook Summary sheet, reconciled against the data:

| Step | Remaining |
| --- | --- |
| PPOC active-patient registry, age < 18 as of 31 Dec 2024 | 361,326 |
| less patients of 2 practices that declined participation | 352,017 |
| ≥ 5 growth measurements on distinct dates of one type, spanning > 1095 days, last measurement < 400 days ago (under-3s exempted from the span rule) | 290,175 |
| less patients carrying any **rare** diagnosis, medication, or lab | **250,588** |

The final count matches the snapshot exactly. So do the per-resource row counts in the diagram, and two counts nothing in this repo records: **6,578,838 lab orders** and **247,271 patients with ≥ 1 lab**, both of which reproduce from the data exactly. That is strong independent confirmation the bundle is the delivered extract.

**"Active" means alive.** The registry requires living status = alive, not a test or inactive record, an active PPOC PCP association, and either a visit in the last 3 years or one scheduled in the next 15 months.

**"Rare" means fewer than 11 occurrences in the data set**, and the exclusion removed the *patient*, not the code: 18,604 of 30,493 ICD-10 codes, 1,391 of 2,503 medications, and 9,621 of 13,402 lab procedures were classed rare.

**Consequences that must be stated prominently and are currently stated nowhere:**

- **Rare-disease, rare-exposure, and rare-lab research is invalid on this data.** Roughly 61% of diagnosis codes, 56% of medications, and 72% of lab procedures were removed along with every patient who had one. `docs/data_description.md` currently advertises "disease prevalence" and "pharmacoepidemiology" as use cases. That guidance is unsafe as written and the new report must say so plainly.
- **No deceased patients exist**, so mortality is not an available outcome and any survival framing is censored by construction.
- **Trajectory richness is an entry criterion, not a finding.** Every patient has ≥ 5 growth measurements of some type. Statistics like "97.9% have at least three height observations" describe the selection rule, not pediatric primary care, and the report must frame them that way.
- **The recency filter right-censors by design** — last measurement within 400 days of 31 Dec 2024.
- **A calendar anchor exists after all.** Ages are relative to birth, but the cohort is pinned to 31 Dec 2024 and the extract to 03 Feb 2025. Section 1.5's "no calendar axis" claim needs this qualification.

One discrepancy between the two source documents to record rather than resolve silently: the workbook says under-3s with ≥ 5 measurements are exempt from the *span* requirement (N = 55,833); the diagram says the exemption is for age < 3 with *at least 1* measurement. The workbook also says "less than 11 occurrences" where the exclusion sheets say "< 10 patients". The report states both readings and flags the ambiguity.

### 5A.2 Field semantics the dictionary settles, and the current report gets wrong

| Field | Dictionary says | Consequence |
| --- | --- | --- |
| `result_flag` | "(NONE) indicates a normal result. Any other value indicates abnormal." | The delivered data has **15,550,985 nulls and no literal "(NONE)"**. Null therefore means **normal**, not missing. Treating it as missing discards the largest normal-result signal in the file. |
| `resolved_date_age_in_days` | "null = problem currently active" | **951,677 nulls are active problems, not missing data.** The existing report frames this as 44.3% populated, implying missingness. |
| `visit_id` (labs, meds, referrals) | "may not match to all if ordered outside a visit" | The 30–42% unresolved rate is **expected and documented**, not a defect. The current report presents it as a surprise. |
| `lab_procedure_name` / `lab_procedure_description` | description "may provide more information for the Care Everywhere labs" | Care Everywhere rows carry the useful text in `description`, not `name`. |
| labs, granularity note | "lab results may not properly link to the original order, creating duplicate records" | The vendor documents the duplicate-result-line behaviour the report measures at 31,628 pairs. |
| labs, coverage note | "Includes care everywhere labs (without results)" | Explains the 14.5% of lab rows with no `result_value`. |
| `med_order_date_age_in_days` | for historically documented meds this is the *documentation* date, and start dates "may be inaccurate" | Explains the 9.3% start-before-order violations as a documented property, not corruption. |
| `med_end_date_age_in_days` | "may be future dates if medication is currently active" | Explains end-date anomalies. |
| `orig_enc_source_Epic_yn` | converted encounters "may be missing diagnosis information" | Explains 17.3% diagnosis presence on conversion encounters. |
| `sex` | "values: M, F, U" | `U` is a documented category, not a data error. |

Every row above turns an unexplained observation into a documented one. That is the difference between a researcher filing a bug and a researcher writing one line of handling code.

### 5A.3 Schema drift: three documented fields were never delivered

Comparing the dictionary against the live bundle, column by column:

| Resource | Result |
| --- | --- |
| patients, visits, problem_list, referrals, labs | dictionary and delivery agree |
| **medications** | **`med_therapeutic_class`, `med_pharmaceutical_class`, `med_pharmaceutical_subclass` are documented but absent** |

Anyone planning a drug-class analysis will find those three fields promised by the dictionary and missing from the data. This belongs in Part 1.1 and in the field index.

### 5A.4 Handling rule for the source documents — public repository

`ppoc-patient-list-notes-*.xlsx` is **not safe to publish**. Its `exclusion - labs` sheet lists 9,622 lab procedure names, of which 523 exceed 45 characters and 11 contain explicit calendar dates, because free-text clinical narrative was typed into the procedure-name field at the source. Examples carry a facility name, a date, an age, and family circumstances, each at a unique-patient count of 1.

This repository is public. All three delivery documents are now gitignored; the dictionary and the diagram scan clean and can be un-ignored deliberately if redistribution is intended, but the notes workbook should not be.

**Rule for the report:** facts, counts, and field semantics may be carried over. **No verbatim lab procedure name, and no free-text string from any source document, may appear in any output.** A neutrality-audit style test enforces it: no output may contain a calendar-date pattern outside the two known cohort anchors.

---

## 6. New analyses this report adds


Beyond reorganising and de-projecting what already exists, the following are not in the current report. I verified the first one while drafting this plan, because a plan that promises findings should demonstrate at least one.

### 6.1 Raw-versus-augmented layer agreement — **verified, and it found something**

Joining `visits` to `visits_augmented` on `visit_id` across all 6,494,473 rows:

| Field | Rows where the layers disagree |
| --- | --- |
| `height_in`, `weight_oz`, `head_circ_cm`, `encounter_type`, `age_in_days` | 0 |
| `BMI` vs `bmi` | 1,703,046 |

The augmentation preserves every shared measurement exactly except BMI. The gap decomposes as:

- **1,703,005 rows carry a raw `BMI` but a null augmented `bmi`**, at a median age of **0.51 years**. The augmented layer withholds BMI below age 2, consistent with CDC BMI-for-age starting at 2 years; the raw layer does not. **A researcher reading `visits.BMI` therefore silently gets infant BMI values that the augmented layer deliberately suppresses.**
- 41 rows the other way.
- **536 rows where both are present and differ by more than 0.01** — a genuine inconsistency worth its own finding.

This is exactly the class of trap the report should catch, and nothing in the current report looks for it.

### 6.2 Corrections the delivery documents force

Not new computation so much as new *reading* of existing computation, and each one changes a conclusion:
- `result_flag` null means normal, not missing (15,550,985 rows).
- `resolved_date_age_in_days` null means an active problem, not missing (951,677 rows).
- Unresolved `visit_id` in labs, medications, and referrals is documented expected behaviour for orders placed outside a visit, not a linkage defect.
- Medication start-before-order violations are a documented property of historically documented medications.
- Trajectory-richness statistics describe the cohort entry rule, not pediatric care.

### 6.3 Other additions
- **Schema drift** of the live bundle against `datapackage.json`.
- **Sentinel-value sweep** across all categorical and numeric fields.
- **BMI recomputation** from `height_cm` and `weight_kg` against the distributed `bmi`, at both layers.
- **Full field-level missingness** for all 254 columns; the current report profiles a chosen subset.
- **Lab order/result reconciliation** — orders with no result and results with no order.
- **`patients` versus `patients_augmented`** agreement, the same check as 6.1 on the patient grain.
- **Race multi-select structure**: `race_1`–`race_8` occupancy, which the current report touches only via `race_1`.
- **Trajectory-span profile** as a survival-style curve rather than a few summary counts.

---

## 7. Figure inventory

Eleven figures, each tied to a claim that is genuinely harder to make in a table.

| # | Figure | Part | Type |
| --- | --- | --- | --- |
| 1 | Cohort construction funnel, 361,326 → 250,588, with each exclusion labelled | 1.4 | funnel |
| 2 | Resource map with row counts and link-resolution rates | 1.2 | diagram |
| 3 | Missingness matrix, field × age band | 3.4 | heatmap |
| 4 | Visit volume and measurement availability by age | 3.4 | line |
| 5 | Terminal-digit heaping by age band | 4.2 | grouped bar |
| 6 | Height / weight / BMI distributions with review bounds | 4.3 | histogram |
| 7 | Head-circumference value clusters, log scale, ×2.54 bands marked | 4.4 | histogram |
| 8 | Transcription mechanism enrichment, observed vs null | 4.4 | grouped bar |
| 9 | Apparent height-loss rate by age, split by sex | 4.5 | line |
| 10 | Height z-score tail asymmetry against the +3 bound | 4.6 | histogram |
| 11 | Trajectory span: share of children retaining N height observations | 4.1 | step |

---

## 8. Script architecture

New package, with no modification of and no import from the generators that existed at the time. Probe *logic* was adapted from the earlier, already-verified artifact profiler rather than re-derived — the permutation-null machinery in particular. Those generators have since been deleted; the ported figures were checked against their output before they went.

```
reports/ppoc_eda/
  __main__.py        CLI: --bundle, --out-dir, --formats, --only, --list-probes
  context.py         read-only connection, snapshot identity, suppression, formatting
  findings.py        Finding dataclass, registry, stable ids, JSON serialization
  charts.py          SVG primitives (bar, grouped bar, line, heatmap, histogram, step)
  probes/
    snapshot.py      Part 1
    integrity.py     Part 3.1-3.3
    missingness.py   Part 3.4-3.5
    terminology.py   Part 3.6
    capture.py       Part 3.7
    anthropometry.py Part 4
    domains.py       Part 5
    fieldindex.py    Part 6
  render/
    html.py          primary
    markdown.py      mirror
```

Outputs to `reports/ppoc-eda/`.

**Contract every probe honours:** takes a context, returns a list of `Finding` objects. A `Finding` carries a stable id, a title, the computed values, optional table and figure payloads, prose templates, and its artifact-catalogue classification. Probes never emit prose containing a literal number and never touch the filesystem. Rendering is a pure function of the finding set, which is what makes the three outputs consistent by construction.

`--only` runs one probe for fast iteration; `--list-probes` supports a coverage test asserting every checklist row maps to a probe.

---

## 9. Determinism, privacy, and verification

**Determinism.** Seeded RNG; `ORDER BY` on every query feeding a permutation; no wall-clock value in the report body — generation time goes only into `findings.json` metadata, so regenerating an unchanged snapshot produces a byte-identical HTML and Markdown. Verified by running twice and diffing, the same gate already used on the artifact profiler.

**Privacy.** Read-only connection. Aggregate output only. Suppression below 10 records, applied centrally in `context.py` rather than per probe. A render-time assertion rejects any cell that matches an identifier column's value pattern, so a probe cannot leak an id by accident.

**Verification, four gates:**
1. **Snapshot agreement** — row counts and sha256 against `manifest.json`, plus the vendor's independently stated counts from the delivery documents (250,588 patients, 6,494,473 visits, 6,578,838 lab orders, 247,271 patients with a lab). Abort on mismatch rather than silently profiling a different extract.
2. **Internal consistency** — every number in the HTML and Markdown traces to a `findings.json` key; a test asserts no orphan literals in the templates.
3. **Determinism** — two runs produce identical `findings.json`; HTML and Markdown byte-identical; the PDF is rebuilt only when `findings.json` changes, so an unchanged snapshot yields no new blob.
3a. **Disclosure guard** — no output may contain a verbatim source-document free-text string or a calendar-date pattern outside the two known cohort anchors. Enforced as a test, because the source documents carry clinical narrative and this repository is public.
4. **Detector validation** — this repo already generates synthetic PPOC-shaped data under `src/synthetic`. Build a fixture with *known injected artifacts* (whole-foot heights, decimal-shifted weights, double-converted head circumferences) and assert the probes recover them at the injected rate. This tests that the detectors work, not merely that the plumbing runs — and no existing test does that.

---

## 10. Build order

| Phase | Deliverable | Gate |
| --- | --- | --- |
| 1 | `context.py`, `findings.py`, both renderers, one trivial probe end to end | Three outputs produced, determinism gate green |
| 2 | `charts.py` with all seven primitives, one real figure | Renders in light, dark, and print; no external requests |
| 2a | PDF step: Chrome discovery, print stylesheet, metadata normalization, rebuild-on-change gate | PDF opens, matches the HTML, and a no-op rebuild leaves the file untouched |
| 3 | Parts 1–3 probes, including the cohort funnel and the vendor-count reconciliation | Coverage table complete, every N/A justified, vendor counts agree |
| 4 | Part 4 anthropometrics, including the ported transcription and shrinkage probes | Figures 4–10 |
| 5 | Parts 5–7, field index, artifact catalogue | Detector-validation tests green |
| 6 | Part 0 and Part 8 prose, cross-links, final read-through | Neutrality audit and disclosure guard both green |

The neutrality audit in phase 6 is mechanical — grep the outputs for `GrowthChartLiteracy`, `E3|E5a|E7|E9`, `stimul`, `counterfactual`, `serializ`, `this project`, and any absolute path outside the repo. The disclosure guard is the same shape: no verbatim source-document free text, no calendar date outside the two cohort anchors. Both belong in the test suite, not in a human's eyes.

---

## 11. Decisions needed before phase 1

1. **Charts:** hand-rolled SVG with no new dependency, as recommended — or add `matplotlib` under an optional `report` dependency group?
2. **Outputs:** all three (HTML + JSON + Markdown), or drop the Markdown mirror? Note that GitHub will not render a committed HTML file in the browser, so the Markdown mirror is what a reviewer sees in a pull request. That is the main argument for keeping it.
3. ~~Commit the built outputs?~~ **Decided: yes**, HTML and PDF both, so the report is viewable on GitHub. Blob churn is bounded by the rebuild-on-change gate in §3.
4. **Field index scope:** collapse `enc_diag_1`–`33` and `race_1`–`8` to one row each as proposed, or list every column?
5. **Follow-on:** once this exists, reduce `growth-chart-literacy-real-data-eda.md` to a thin project overlay that cites this report instead of restating it? Worth doing, but a separate task.
6. **New — source documents:** all three are now gitignored (§5A.4). Keep it that way, or un-ignore the dictionary workbook and the extract diagram, which scan clean? The notes workbook should stay out regardless.
7. **New — correct `docs/data_description.md`?** It advertises "disease prevalence" and "pharmacoepidemiology" use cases that the rare-code exclusion undermines. That file is read by people and by LLMs as the authority on this dataset. I would fix it now rather than wait for the new report, as a small separate commit.

I would proceed with the recommendation on every item above unless you say otherwise. Items 6 and 7 are the ones I would act on soonest.
