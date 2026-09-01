# Imported growth augmenter

The repository includes `scripts/augment.py` and its checked-in runtime references as a source-matched development derivation candidate. It accepts only wholly synthetic exact-schema base resources. It is not bound as authoritative and does not change the native generator, package exporter, calibration, privacy, counterfactual, Synthea, or release gates.

> **Warning:** Do not point this script at governed data, real patient data, or any directory containing either. This development-only import is for wholly synthetic inputs only.

## Setup and synthetic input

From the repository root, install the declared runtime dependencies:

```sh
uv sync
```

Create or select an explicit wholly synthetic input directory containing these three files directly at its root:

```text
fixtures/augment-input/
├── visits.csv
├── patients.csv
└── problem_list.csv
```

Each file must satisfy the matching base-resource schema and header order in `datapackage.json`: `visits.csv`, `patients.csv`, and `problem_list.csv`, respectively. The importer reads these base resources from the supplied directory and its bundled reference tables from this repository; it does not make the input authoritative.

## Run

Run the command from the repository root, with explicit synthetic input and output directories:

```sh
uv run python scripts/augment.py fixtures/augment-input --output_dir artifacts/augment-output --output_format csv
```

For Parquet output, replace `csv` with `parquet`. The importer creates the output directory when needed and writes timestamped files such as:

```text
artifacts/augment-output/
├── visits_augmented-YYYYMMDDHHMMSS.csv
└── patients_augmented-YYYYMMDDHHMMSS.csv
```

With `--output_format parquet`, the same timestamped names use the `.parquet` extension. These outputs are development artifacts, not a package export or an authority, calibration, privacy, counterfactual, Synthea, or release result.

## Verify the imported runtime

`data/augment-runtime-manifest.json` records every imported runtime file with its relative path, byte count, and SHA-256 digest. From the repository root, verify the manifest and hashes before use:

```sh
uv run python -c 'import hashlib, json, pathlib; root = pathlib.Path("."); manifest = json.loads((root / "data/augment-runtime-manifest.json").read_text()); [entry["bytes"] == (root / entry["path"]).stat().st_size and entry["sha256"] == hashlib.sha256((root / entry["path"]).read_bytes()).hexdigest() or (_ for _ in ()).throw(SystemExit(entry["path"])) for entry in manifest["files"]]; print("augment runtime manifest hashes verified")'
```

This check confirms that the local imported runtime matches the checked-in manifest. It does not make the candidate authoritative or establish clinical, prevalence, privacy, non-matchability, calibration, Synthea, or release evidence.
