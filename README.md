# PPOC Pediatric EHR Data Package

This repository describes eight de-identified pediatric EHR CSV resources with a machine-readable [Frictionless Data Package](https://specs.frictionlessdata.io/tabular-data-package/) descriptor. The data uses `patient_id` for patient-level linkage, and absolute dates are represented as patient age in days.

[The Pediatric Physicians’ Organization at Children’s (PPOC)](https://www.ppochildrens.org/) is an independent pediatric physician association and primary-care network affiliated with Boston Children’s Hospital, serving practices across Massachusetts. This data is provided by PPOC to the Isaac Kohane Lab in the [Department of Biomedical Informatics](https://dbmi.hms.harvard.edu/) at Harvard Medical School under an IRB protocol and Data Use Agreement.

## Contents

- [`datapackage.json`](datapackage.json): field types, nullability, constraints, keys, encodings, and resource metadata.
- [`docs/data_description.md`](docs/data_description.md): dataset overview, relationships, and analysis guidance.
- [`docs/`](docs/): resource-specific field descriptions.
- [`schema/README.md`](schema/README.md): Python loading examples.
- [`schema/build.py`](schema/build.py): regenerate and validate `datapackage.json`.
- [`schema/profile.py`](schema/profile.py): recompute the snapshot statistics from the CSVs.
- [`schema/stats.json`](schema/stats.json): the statistics `build.py` reads, so the descriptor rebuilds without the data.
- [`docs/synthetic-generator.md`](docs/synthetic-generator.md): synthetic generator and governed aggregate-calibration boundaries.

## Resources

| Resource | Rows | Fields | Description |
| --- | ---: | ---: | --- |
| [`patients.csv`](docs/patients.md) | 250,588 | 11 | Patient demographics |
| [`patients_augmented.csv`](docs/patients_augmented.md) | 250,588 | 87 | Patient-level growth and diagnosis summaries |
| [`visits.csv`](docs/visits.md) | 6,494,473 | 43 | Visit-level measurements and diagnoses |
| [`visits_augmented-20251209150512.csv`](docs/visits_augmented.md) | 6,494,473 | 82 | Visit-level derived growth metrics and flags |
| [`labs.csv`](docs/labs.md) | 17,230,681 | 12 | Laboratory result components |
| [`medications.csv`](docs/medications.md) | 3,823,049 | 8 | Medication records |
| [`problem_list.csv`](docs/problem_list.md) | 1,709,584 | 5 | Problem-list entries |
| [`referrals.csv`](docs/referrals.md) | 349,827 | 6 | Specialty referrals |

The package expects these CSVs beside `datapackage.json`. To keep the descriptor in this repository while reading CSVs from another directory, set `PPOC_DATA_ROOT` for the Python example in [`schema/README.md`](schema/README.md).

## Relationships

- `patients.csv` and `patients_augmented.csv` contain one row per `patient_id`.
- `visits.csv` and `visits_augmented-20251209150512.csv` contain `patient_id` and `visit_id`.
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

## Synthetic generator

See the [synthetic generator guide](docs/synthetic-generator.md) for development-only synthetic fixture generation, validation, and governance boundaries.
