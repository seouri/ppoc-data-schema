# Growth augmenter reference data

`scripts/augment.py` preserves the supplied runtime lookup contract: when run from the repository root, it loads these files using its relative `data/` paths. The included CSVs are source-matched reference tables supplied as public growth standards and ICD-10-CM code-table inputs; `augment-runtime-manifest.json` records their exact byte sizes and SHA-256 digests alongside the imported Python files.

This import intentionally excludes patient, visit, problem-list, laboratory, medication, referral, and generated-output data, plus notebooks, caches, virtual environments, credentials, and source-repository metadata. Tests create temporary, wholly fictional exact-schema inputs rather than reading any source data.

These tables support a development derivation candidate only. Their presence and hashes are not clinical validation evidence, do not establish provenance or redistribution authorization beyond the supplied files, and do not imply clinical validity, representativeness, or release approval.
