# Plan: a project-neutral EDA reference for the PPOC snapshot

**Status:** proposed, not yet implemented
**Supersedes nothing.** `reports/growth-chart-literacy-real-data-eda.md` and its two generators stay as they are; this is a new, parallel deliverable built from scratch.

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

**Decision: a self-contained HTML report as the primary artifact, `findings.json` as the machine-readable source of truth, and a Markdown mirror for grep and diff.** All three from a single computation pass.

### Why not Markdown alone
Roughly ten of the findings are far clearer as pictures than as tables — the asymmetric z-score tail, the terminal-digit grid, the head-circumference conversion bands, the apparent-shrinkage curve by age and sex, the missingness matrix over 254 fields. Markdown cannot inline them without shipping a directory of PNGs, which diff badly and drift from the text.

### Why HTML rather than Quarto, notebook, or PDF
| Option | Verdict |
| --- | --- |
| Quarto → HTML/PDF | Rejected: adds a non-Python binary to the toolchain for no capability this needs. |
| Jupyter notebook | Rejected: a reference document is read, not executed; notebooks diff badly and invite stale output. |
| PDF | Rejected: no search-in-page across a long field index, no anchor links, worse to regenerate. |
| Self-contained HTML | **Chosen**: inline SVG, sticky table of contents, anchor links per finding, browser find-in-page over the whole document, opens offline from the repo with no server and no assets. |

### The three outputs

| File | Role |
| --- | --- |
| `reports/ppoc-eda/index.html` | Primary. Self-contained: inline SVG, inline CSS, no external requests. |
| `reports/ppoc-eda/findings.json` | Every number the report states, keyed by stable finding id. This is what git diffs cleanly across regenerations, and what another script or an assistant can consume without parsing prose. |
| `reports/ppoc-eda/ppoc-eda.md` | Text mirror: all prose and tables, figures replaced by captions linking to the HTML anchor. For grep, for review in a PR, and for loading into an LLM context. |

**Anti-drift rule:** prose is a template; every number in the HTML and the Markdown is interpolated from `findings.json`. A number cannot appear in one output and not the other, and cannot be hand-edited into either.

### Charts: hand-rolled SVG, no new dependency

The project has five lean runtime dependencies and no plotting library. The chart vocabulary this report needs is small and repetitive — histogram/bar, grouped bar, line with optional series split, heatmap, and a percentile ribbon. That is roughly 350 lines of a `charts.py` emitting SVG directly from numpy-computed bin counts.

Doing it by hand also buys two things matplotlib does not: the SVG inherits CSS custom properties, so the figures follow a light/dark toggle, and the output is small and diff-stable.

**Fallback if the vocabulary grows:** add `matplotlib` under a new optional `[dependency-groups] report` so the core install stays lean. Recorded here so the decision is not relitigated silently.

When the charts are built, load the `dataviz` skill first — palette, axis, and legend conventions should not be improvised.

---

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
- 1.4 **The de-identification envelope.** Calendar dates, names, sites, providers, and time-of-day are absent; `age_in_days` is the only clock. Stated once, here, with the list of checks it forecloses, then referenced from Part 2 rather than re-argued.

### Part 2 — Checklist coverage
- 2.1 **Coverage table.** Every item in `docs/ehr_eda_checklist.md`, mapped to: covered / partially covered / not applicable, the report section holding the evidence, and — for anything not fully covered — the reason.
- 2.2 **What this snapshot cannot tell you.** The N/A items consolidated into one list a researcher can read in a minute, so nobody spends a day looking for a provider field.

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
| 0. Extraction window | Partial | Snapshot date known; no calendar dates in the data, so no start/end window. |
| 0. Inclusion/exclusion logic | Covered | From `docs/data_description.md`. |
| 0. Vendor/version, migration events | Covered | `orig_enc_source_Epic_yn` marks Epic against converted records — the migration signal. |
| 0. Data dictionary present | Covered | `docs/*.md` + `datapackage.json`; drift check is computable. |
| 0. Raw vs CDM vs custom | Covered | Custom extract **plus a derived augmentation layer** — the distinction that matters most here. |
| 1. Row/table counts | Covered | Reconcile against `manifest.json`. |
| 1. Primary key uniqueness | Covered | All eight resources. |
| 1. Referential integrity | Covered | Includes the populated-but-unresolvable `visit_id` finding. |
| 1. Duplicate patient detection | **N/A** | No DOB, name, or linkage key survives de-identification. |
| 1. Schema drift | Covered | Live schema against `datapackage.json`. |
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
| 3. Not-measured vs measured-negative | Covered | Labs especially. |
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
| 7. Cohort representativeness | Partial | Distributions reported; **no external benchmark ships with this repo**, so the comparison is left to the reader and that limit is stated. |
| 7. Encounter-type mix | Covered | Part 3.7. |
| 7. Follow-up time distribution | Covered | Trajectory span and later-visit availability. |
| 7. Site/provider volume | **N/A** | No such field. |
| 8. Trend breaks over calendar time | **N/A** | No calendar axis. Age-axis profiles are reported instead and are explicitly *not* the same thing. |
| 8. Guideline/policy shift | **N/A** | Requires calendar time. |
| 8. Vendor changeover effects | Partial | Epic-vs-converted contrast only. |

Twelve items are not applicable and four more are partial. **Publishing that list is a deliverable in itself** — it is the difference between a researcher spending an hour confirming a field does not exist and reading one line.

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

### 6.2 Other additions
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

Ten figures, each tied to a claim that is genuinely harder to make in a table.

| # | Figure | Part | Type |
| --- | --- | --- | --- |
| 1 | Resource map with row counts and link-resolution rates | 1.2 | diagram |
| 2 | Missingness matrix, field × age band | 3.4 | heatmap |
| 3 | Visit volume and measurement availability by age | 3.4 | line |
| 4 | Terminal-digit heaping by age band | 4.2 | grouped bar |
| 5 | Height / weight / BMI distributions with review bounds | 4.3 | histogram |
| 6 | Head-circumference value clusters, log scale, ×2.54 bands marked | 4.4 | histogram |
| 7 | Transcription mechanism enrichment, observed vs null | 4.4 | grouped bar |
| 8 | Apparent height-loss rate by age, split by sex | 4.5 | line |
| 9 | Height z-score tail asymmetry against the +3 bound | 4.6 | histogram |
| 10 | Trajectory span: share of children retaining N height observations | 4.1 | step |

---

## 8. Script architecture

New package, no modification of and no import from the existing generators. Probe *logic* may be adapted from `reports/eda/build_ehr_artifact_profile.py`, which is already verified and deterministic — re-deriving the permutation-null machinery would be waste.

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
1. **Snapshot agreement** — row counts and sha256 against `manifest.json`; abort on mismatch rather than silently profiling a different extract.
2. **Internal consistency** — every number in the HTML and Markdown traces to a `findings.json` key; a test asserts no orphan literals in the templates.
3. **Determinism** — two runs, byte-identical.
4. **Detector validation** — this repo already generates synthetic PPOC-shaped data under `src/synthetic`. Build a fixture with *known injected artifacts* (whole-foot heights, decimal-shifted weights, double-converted head circumferences) and assert the probes recover them at the injected rate. This tests that the detectors work, not merely that the plumbing runs — and no existing test does that.

---

## 10. Build order

| Phase | Deliverable | Gate |
| --- | --- | --- |
| 1 | `context.py`, `findings.py`, both renderers, one trivial probe end to end | Three outputs produced, determinism gate green |
| 2 | `charts.py` with all six primitives, one real figure | Renders in light and dark, no external requests |
| 3 | Parts 1–3 probes | Coverage table complete, every N/A justified |
| 4 | Part 4 anthropometrics, including the ported transcription and shrinkage probes | Figures 4–10 |
| 5 | Parts 5–7, field index, artifact catalogue | Detector-validation tests green |
| 6 | Part 0 and Part 8 prose, cross-links, final read-through | Neutrality audit: zero hits for the forbidden terms |

The neutrality audit in phase 6 is mechanical — grep the outputs for `GrowthChartLiteracy`, `E3|E5a|E7|E9`, `stimul`, `counterfactual`, `serializ`, `this project`, and any absolute path outside the repo. It belongs in the test suite, not in a human's eyes.

---

## 11. Decisions needed before phase 1

1. **Charts:** hand-rolled SVG with no new dependency, as recommended — or add `matplotlib` under an optional `report` dependency group?
2. **Outputs:** all three (HTML + JSON + Markdown), or drop the Markdown mirror? Note that GitHub will not render a committed HTML file in the browser, so the Markdown mirror is what a reviewer sees in a pull request. That is the main argument for keeping it.
3. **Commit the built outputs**, or treat them as build products and gitignore them? Committing makes the report readable straight from a clone; it also puts a large generated HTML file in history.
4. **Field index scope:** collapse `enc_diag_1`–`33` and `race_1`–`8` to one row each as proposed, or list every column?
5. **Follow-on:** once this exists, reduce `growth-chart-literacy-real-data-eda.md` to a thin project overlay that cites this report instead of restating it? Worth doing, but a separate task.

I would proceed with the recommendation on every item above unless you say otherwise; item 3 is the only one where I have no strong preference.
