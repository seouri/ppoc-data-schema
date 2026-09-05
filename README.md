# PPOC Pediatric EHR Data Package

This repository describes eight de-identified pediatric EHR CSV resources with a machine-readable [Frictionless Data Package](https://specs.frictionlessdata.io/tabular-data-package/) descriptor. The data uses `patient_id` for patient-level linkage, and absolute dates are represented as patient age in days.

[The Pediatric Physicians’ Organization at Children’s (PPOC)](https://www.ppochildrens.org/) is an independent pediatric physician association and primary-care network affiliated with Boston Children’s Hospital, serving practices across Massachusetts. This data is provided by PPOC to the Isaac Kohane Lab in the [Department of Biomedical Informatics](https://dbmi.hms.harvard.edu/) at Harvard Medical School under an IRB protocol and Data Use Agreement.

## Project governance and funding

The project *Artificial Intelligence Analysis of Growth Charts to Identify Abnormal Growth Patterns* is conducted at Harvard Medical School under the following protocols and agreement:

| Instrument | Identifier | Parties or institution |
| --- | --- | --- |
| IRB protocol | `IRB24-0638` | Harvard Medical School |
| Data Safety and Security protocol | `DAT24-0223` | Harvard Medical School |
| Data Use Agreement | `DUA24-0257` | Harvard Medical School and Pediatric Physicians' Organization, LLC (PPOC) |

### Required manuscript acknowledgment

Any manuscript that uses these data must include the following sentence verbatim:

> This project is conducted under Harvard Medical School IRB protocol IRB24-0638 and the Data Use Agreement DUA24-0257 between Harvard Medical School and Pediatric Physicians’ Organization, LLC (PPOC).

Access to project data is restricted to authorized study personnel who have completed all required IRB and information-security training, obtained certificates documenting completion, and been formally listed as study personnel on the approved IRB protocol.

### Required funding acknowledgment

Any manuscript that uses these data must include the following sentence verbatim:

> This work was supported by the Charles H. Hood Foundation and Yosemite.

These project-governance statements apply to the restricted PPOC source snapshot described above. Ordinary synthetic development uses no PPOC rows or patient records and does not require those source-data approvals; see the [synthetic generator guide](docs/synthetic-generator.md) for its separate content and reproducibility requirements. The evaluator-only excess-weight ancillary pathway is a separate roadmap slice documented in that guide. The pediatric-hypothyroidism ancillary pathway is a separate roadmap slice; see its [plan](docs/superpowers/plans/2026-09-02-pediatric-hypothyroidism-ancillary-pathway.md) and [spec](docs/superpowers/specs/2026-09-02-pediatric-hypothyroidism-ancillary-pathway-design.md). The evaluator-only celiac ancillary pathway is a separate roadmap slice; see its [guide](docs/synthetic-generator.md), [plan](docs/superpowers/plans/2026-09-02-celiac-ancillary-pathway.md), and [spec](docs/superpowers/specs/2026-09-02-celiac-ancillary-pathway-design.md). The evaluator-only SGA ancillary pathway is a separate roadmap slice; see its [guide](docs/synthetic-generator.md), [plan](docs/superpowers/plans/2026-09-02-sga-ancillary-pathway.md), and [spec](docs/superpowers/specs/2026-09-02-sga-ancillary-pathway-design.md). The evaluator-only Turner ancillary pathway is a separate roadmap slice; see its [guide](docs/synthetic-generator.md), [plan](docs/superpowers/plans/2026-09-02-turner-ancillary-pathway.md), and [spec](docs/superpowers/specs/2026-09-02-turner-ancillary-pathway-design.md). The evaluator-only undernutrition ancillary pathway is a separate roadmap slice; see its [guide](docs/synthetic-generator.md), [plan](docs/superpowers/plans/2026-09-02-undernutrition-ancillary-pathway.md), and [spec](docs/superpowers/specs/2026-09-02-undernutrition-ancillary-pathway-design.md).

## Contents

- [`datapackage.json`](datapackage.json): field types, nullability, constraints, keys, encodings, and resource metadata.
- [`docs/data_description.md`](docs/data_description.md): dataset overview, relationships, and analysis guidance.
- [`docs/`](docs/): resource-specific field descriptions.
- [`schema/README.md`](schema/README.md): Python loading examples.
- [`schema/build.py`](schema/build.py): regenerate and validate `datapackage.json`.
- [`schema/profile.py`](schema/profile.py): recompute the snapshot statistics from the CSVs.
- [`schema/stats.json`](schema/stats.json): the statistics `build.py` reads, so the descriptor rebuilds without the data.
- [`scripts/export_parquet.py`](scripts/export_parquet.py): export the eight typed CSV resources as a verified Parquet bundle.
- [`scripts/build_duckdb.py`](scripts/build_duckdb.py): build a verified, materialized typed DuckDB bundle.
- [`docs/synthetic-generator.md`](docs/synthetic-generator.md): ordinary synthetic generation and optional governed aggregate-calibration boundaries.
- [`reports/ppoc-eda/`](reports/ppoc-eda/): exploratory data analysis of the snapshot — read this before analysing the data.
- [`reports/build_ppoc_eda.py`](reports/build_ppoc_eda.py): rebuild that report from a DuckDB bundle.
- [`docs/ehr_eda_checklist.md`](docs/ehr_eda_checklist.md): the general EHR exploratory-analysis checklist the report is measured against.

## Resources

| Resource | Rows | Fields | Description |
| --- | ---: | ---: | --- |
| [`patients.csv`](docs/patients.md) | 250,588 | 11 | Patient demographics |
| [`patients_augmented.csv`](docs/patients_augmented.md) | 250,588 | 87 | Patient-level growth and diagnosis summaries |
| [`visits.csv`](docs/visits.md) | 6,494,473 | 43 | Visit-level measurements and diagnoses |
| [`visits_augmented.csv`](docs/visits_augmented.md) | 6,494,473 | 82 | Visit-level derived growth metrics and flags |
| [`labs.csv`](docs/labs.md) | 17,230,681 | 12 | Laboratory result components |
| [`medications.csv`](docs/medications.md) | 3,823,049 | 8 | Medication records |
| [`problem_list.csv`](docs/problem_list.md) | 1,709,584 | 5 | Problem-list entries |
| [`referrals.csv`](docs/referrals.md) | 349,827 | 6 | Specialty referrals |

The package expects these CSVs beside `datapackage.json`. To keep the descriptor in this repository while reading CSVs from another directory, set `PPOC_DATA_ROOT` for the Python example in [`schema/README.md`](schema/README.md).

## Relationships

- `patients.csv` and `patients_augmented.csv` contain one row per `patient_id`.
- `visits.csv` and `visits_augmented.csv` contain `patient_id` and `visit_id`.
- `labs.csv`, `medications.csv`, and `referrals.csv` link to patients through `patient_id`; lab and referral `visit_id` values are nullable, medication `visit_id` is required, and nonnull values in all three resources may not match a visit row.
- `problem_list.csv` links to patients through `patient_id` and has no direct visit key.

Use the `foreignKeys` and `x-logicalForeignKeys` entries in `datapackage.json` for the declared join relationships and their row-level link statistics.

## Validate or regenerate the descriptor

From the repository root:

```sh
python3 schema/build.py
python3 schema/build.py --check
```

Every count, range, and value distribution in the descriptor is measured from the
CSV snapshot rather than maintained by hand. After the data changes, re-measure
with the DuckDB CLI on `PATH` and rebuild:

```sh
python3 schema/profile.py --data-root /path/to/csvs --snapshot 2026-08-24
python3 schema/build.py
```

The Python usage example includes schema-driven pandas loading, declared CSV encodings, nullable types, column selection, and key inspection.

## Analytical exports

CSV plus `datapackage.json` is the canonical package. These commands create verified typed Parquet and materialized DuckDB bundles from an approved source directory; keep the derived restricted-data outputs outside this checkout and under the same controls as the CSVs.

```sh
uv run python scripts/export_parquet.py \
  --data-root /secure/ppoc-csv \
  --output /secure/ppoc-parquet

uv run python scripts/build_duckdb.py \
  --data-root /secure/ppoc-csv \
  --output /secure/ppoc-duckdb
```

Both commands use this repository's `datapackage.json` by default, validate all eight resources, and refuse unsafe or existing destinations. Use `--descriptor` to select another approved descriptor and `--replace` only for a verified prior bundle. See the [operator and consumer guide](schema/README.md) for inventories, validation, provenance, recovery, and read-only consumption examples.

## Exploratory data analysis

[`reports/ppoc-eda/`](reports/ppoc-eda/) is a project-neutral analysis of this snapshot, written so that nobody repeats work already done or misses a check they should have run. It answers four questions without opening the database: what the extract contains, whether a given field can be trusted, whether a surprising number is already known, and whether a standard check was skipped or is simply impossible here.

| Output | Use |
| --- | --- |
| [`ppoc-eda.pdf`](reports/ppoc-eda/ppoc-eda.pdf) | 49 pages; GitHub renders it in the browser |
| [`index.html`](reports/ppoc-eda/index.html) | self-contained — inline figures, sticky contents, find-in-page |
| [`ppoc-eda.md`](reports/ppoc-eda/ppoc-eda.md) | text mirror, for grep and pull-request review |
| [`findings.json`](reports/ppoc-eda/findings.json) | every number the report states, keyed by finding |

36 findings across 9 parts, with 19 figures and 51 tables, all measured from the typed DuckDB bundle for snapshot `2026-08-24`. Three parts are worth reading before designing anything:

- **1.4, how this cohort was built.** The 250,588 patients are what remains after four exclusions applied upstream, including the removal of every patient carrying a diagnosis, medication, or lab that occurred fewer than 11 times — 61% of ICD-10 codes, 56% of medications, and 72% of lab procedures left with their patients. **Rare-condition, rare-exposure, and mortality questions are foreclosed by construction, not merely sparse.**
- **2.1, checklist coverage.** All 44 items of the general checklist mapped to covered, partial, or not applicable, with a reason. Nine checks cannot be run against this extract at all and four more only partly; knowing which ones saves a day looking for fields that do not exist.
- **7.1, the artifact catalogue.** One row per known recording or derivation artifact, with its scale in this snapshot and whether it can be repaired.

Rebuild it from an approved bundle:

```sh
uv run python reports/build_ppoc_eda.py \
  --bundle /secure/ppoc-duckdb/ppoc.duckdb
```

The four outputs are rewritten only when the findings change, so rebuilding an unchanged snapshot leaves the committed files untouched. The PDF step uses headless Chrome and is skipped with a clear message when no browser is found; the other three outputs always build. Use `--list-probes` to see what runs and `--only` to iterate on one.

[`reports/growth-chart-literacy-real-data-eda.md`](reports/growth-chart-literacy-real-data-eda.md) is a thin overlay carrying only what is specific to the growth-chart study, citing the report above for every measurement; [`reports/audit_coverage.py`](reports/audit_coverage.py) checks that the split stays honest.

## Synthetic generator

For realistic development fixtures, run:

```sh
uv run python -m synthetic.generate --profile development-realistic --output /tmp/ppoc-development-realistic --patients 1000 --seed 20260901
```

This produces deterministic, exact-schema healthy/GHD growth trajectories with the configured fictional demographic mix. Use `development-all-disorders` only when you need coverage across every supported disorder subtype. Choose a new output path if the example path already exists.

See the [synthetic generator guide](docs/synthetic-generator.md) for ordinary development-only synthetic fixture generation and validation, including the [all-disorder profile specification](docs/superpowers/specs/2026-09-03-all-disorder-development-profile-design.md) and [implementation plan](docs/superpowers/plans/2026-09-03-all-disorder-coverage-profile.md). Optional governed comparison, privacy, and release workflows are documented there separately and are not required to generate development fixtures.
