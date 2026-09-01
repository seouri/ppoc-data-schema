# Growth augmenter import design

## Goal

Vendor the supplied pediatric growth augmenter and every runtime file it reads so developers can run the source-matched augmentation pipeline against wholly synthetic exact-schema inputs, while preserving the existing fail-closed authority and release boundaries.

## Import boundary

The import includes `scripts/augment.py`, its local `scripts/harrall_outliers.py` helper, and the ten CDC LMS/height-velocity reference CSVs plus `icd10cm-tabular-2026.csv` that the module loads at import time. The Python dependency closure is pandas, NumPy, SciPy, and PyArrow (PyArrow is needed for the declared Parquet output path). The copied Python and reference files remain byte-identical to the supplied source files; a checked-in manifest records relative paths, sizes, and SHA-256 digests.

The import excludes all patient, visit, problem-list, laboratory, medication, referral, generated-output, notebook, cache, virtual-environment, credential, and source-repository metadata files. Those files are not runtime dependencies of the augmenter and must never enter this repository. The bundled reference tables are standards/code lookups only; their provenance and hashes are documented separately, and no claim of clinical validation or redistribution authorization is made by this import.

## Runtime and authority boundary

`python scripts/augment.py input_dir` remains the source-compatible command and expects `visits.csv`, `patients.csv`, and `problem_list.csv` in the caller-provided input directory. It reads the bundled `data/` reference files and writes timestamped CSV or Parquet outputs to the requested output directory. Tests invoke it only with a temporary wholly synthetic input package derived from the checked-in schema headers. The script is not called by the native generator, visible package exporter, calibration path, privacy evaluator, or counterfactual route.

The imported implementation is a development derivation candidate. It is not automatically bound as authoritative, does not prove clinical validity, prevalence fidelity, demographic representativeness, privacy/non-matchability, Synthea conformance, or release approval, and does not change the production CLI's fail-closed behavior. Any future binding still requires the existing derivation-parity, derivation-binding, review, and governance gates.

## Verification

The import test verifies the manifest, exact copied-file hashes, reference-table headers, importability, and a small synthetic augmentation run whose output headers match the descriptor's `visits_augmented` and `patients_augmented` schemas. Dependency metadata and `uv.lock` are updated together. The full repository test suite, Ruff, schema check, and staged whitespace check remain required before merge; no test reads a real-data path.
