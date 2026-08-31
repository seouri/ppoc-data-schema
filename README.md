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

## Synthetic fixture implementation

The approved design is in [the synthetic growth fixture specification](docs/superpowers/specs/2026-08-30-synthetic-growth-fixtures-design.md). The first implementation work package establishes an exact-schema synthetic smoke-profile package with injected growth-reference and augmentation interfaces. It does not ship a clinically validated reference model, claim demographic representativeness, calibrate or validate prevalence, read PPOC records, or establish privacy or release approval.

Until the authoritative augmentation implementation or an approved parity harness is supplied, the command-line entry point fails closed. The smoke-profile package must not be labeled a development fixture, golden fixture, or validated output.

See [`docs/synthetic-generator.md`](docs/synthetic-generator.md) for the Python usage example, output contract, safety checks, and verification commands.

## Governed aggregate calibration

The repository also provides `python -m synthetic.calibrate` for authorized offline use inside the governed environment. It requires explicit snapshot, descriptor, policy, creation-time, key-file, and new-output arguments and emits only `calibration-artifact.json` plus an aggregate report whose status is `AGGREGATES_ONLY`. The exact command, key-file controls, target families, and suppression semantics are documented in [the synthetic generator guide](docs/synthetic-generator.md#governed-aggregate-calibration-command).

CI exercises calibration only with wholly synthetic records and test key material. No visible synthetic generator path consumes the calibration artifact. Its aggregates are not prevalence validation, clinical validation, privacy evidence, or release authorization.

## Patient-disjoint held-out validation

The standalone `python -m synthetic.heldout_validate` command compares the complete generated package with disclosure-controlled aggregate targets from a privately derived real-data `held_out` partition under an explicit frozen policy. It requires every governed path, snapshot, policy, partition key, calibration artifact/report, and output path; it has no default data root and CI exercises it only with fictional synthetic packages and test key material. `PASS` requires every evaluable target to meet its frozen tolerance, `FAIL` identifies an evaluable out-of-tolerance target, and suppressed, missing, or underpowered targets are `UNEVALUABLE` rather than zero or `PASS`. The exact command and the aggregate-only output boundary are in [the synthetic generator guide](docs/synthetic-generator.md#patient-disjoint-held-out-validation).

A passing held-out report is not prevalence, clinical, privacy, non-matchability, or release evidence. Privacy, temporal drift, task utility, prevalence, and Synthea evaluation remain separate deferred gates; visible generator, export, manifest, and trajectory code does not consume governed real data or held-out validation output.

## Governed privacy-audit evidence

The standalone `python -m synthetic.privacy_audit` command evaluates a complete generated exact-schema package under an explicit approved privacy policy against explicit governed reference, held-out, shadow, prior-release, and optional control inputs. It emits only a deterministic aggregate report and summary; neither output contains rows, identifiers, paths, keys, features, candidate links, distances, diagnosis values, private profile hashes, or undersized cells. `PASS` is qualified policy-bound evidence that the documented screens found no measured signal above the approved tolerances; it is not non-matchability proof, HIPAA status, zero-risk evidence, or release approval. A privacy expert and data custodian retain release authority. The command, required evidence, status semantics, and output lifecycle are documented in [the synthetic generator guide](docs/synthetic-generator.md#governed-privacy-audit-evidence). Temporal drift, task utility, prevalence, and Synthea remain separate deferred gates, and visible generation, export, manifest, and trajectory code does not import the privacy auditor or governed inputs.
