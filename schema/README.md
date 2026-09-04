# Machine-readable data schema

`datapackage.json` is a Frictionless Tabular Data Package descriptor for eight CSV resources. It describes their fields, data types, null representation, primary keys, foreign keys, derivation links, row counts, and selected controlled vocabularies.

Regenerate and validate the descriptor with:

```sh
python3 schema/build.py
python3 schema/build.py --check
```

The descriptor records the data’s nullable fields, incomplete logical visit links, encodings, and controlled values directly in the resource schemas.

## Python usage

Resolve each resource path relative to `datapackage.json` when the CSVs are packaged together; set `PPOC_DATA_ROOT` when they live in another directory. The logical `visits_augmented` resource points to the stable package path `visits_augmented.csv`; direct `scripts/augment.py` runs may emit timestamped intermediate files before package export. This example inspects the package and loads a small sample without hard-coding the column list:

```python
import json
import os
from pathlib import Path

import pandas as pd


PACKAGE_PATH = Path("datapackage.json")
PACKAGE_DIR = PACKAGE_PATH.parent
DATA_ROOT = Path(os.environ.get("PPOC_DATA_ROOT", PACKAGE_DIR))
PACKAGE = json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))

PANDAS_TYPES = {
    "string": "string",
    "integer": "Int64",  # nullable integer, including fields with blanks
    "number": "Float64",
}


def resource_spec(name: str) -> dict:
    """Return the package resource named *name*."""
    for resource in PACKAGE["resources"]:
        if resource["name"] == name:
            return resource
    raise KeyError(f"Unknown resource: {name}")


def read_resource(
    name: str,
    *,
    nrows: int | None = None,
    usecols: list[str] | None = None,
) -> pd.DataFrame:
    """Read a package resource using the types and encoding in the descriptor."""
    resource = resource_spec(name)
    fields = resource["schema"]["fields"]
    selected = set(usecols) if usecols is not None else None
    dtype = {
        field["name"]: PANDAS_TYPES[field["type"]]
        for field in fields
        if selected is None or field["name"] in selected
    }
    return pd.read_csv(
        DATA_ROOT / resource["path"],
        dtype=dtype,
        encoding=resource.get("encoding", "utf-8"),
        nrows=nrows,
        usecols=usecols,
    )


for resource in PACKAGE["resources"]:
    schema = resource["schema"]
    print(
        resource["name"],
        "fields=", len(schema["fields"]),
        "primary_key=", schema.get("primaryKey"),
    )

patients = read_resource("patients", nrows=1_000)
print(patients[["patient_id", "sex", "ethnicity"]].head())

# The lab resource declares ISO-8859-1 and nullable integer/string fields.
labs = read_resource(
    "labs",
    nrows=1_000,
    usecols=["patient_id", "visit_id", "result_line_num", "result_value"],
)
print(labs.dtypes)

referrals = resource_spec("referrals")
nullable_fields = [
    field["name"]
    for field in referrals["schema"]["fields"]
    if not field.get("constraints", {}).get("required", False)
]
print("nullable referral fields:", nullable_fields)
print("patient foreign keys:", referrals["schema"].get("foreignKeys", []))
print("logical visit links:", referrals.get("x-logicalForeignKeys", []))
```

For a full resource, omit `nrows`; for a memory-conscious analysis, pass only the fields needed through `usecols`. The package’s `foreignKeys` and `x-logicalForeignKeys` entries identify complete patient joins and incomplete visit-ID relationships, respectively.

## Typed analytical exports

CSV files plus `datapackage.json` are the canonical PPOC package. The Parquet and DuckDB outputs are derived restricted-data bundles, not replacement source packages. They remain subject to the same IRB, Data Use Agreement, required training, and information-security controls as the CSV snapshot. The commands refuse destinations inside this checkout. Treat manifests, schemas, counts, and validation metadata as provenance and integrity information; they do not make clinical interpretation, diagnostic use, or disclosure of clinical values permissible.

Both commands accept the same options:

```text
--descriptor PATH   descriptor to validate and use (default: repository datapackage.json)
--data-root PATH    directory containing the eight canonical CSV resources
--output PATH       required destination bundle directory
--replace           explicitly replace a verified existing bundle
```

`--data-root` takes precedence over `PPOC_DATA_ROOT`. If neither is supplied, argument parsing stops with status 2 before any export. `--output` is always required. Argument errors return status 2; redacted exporter failures return status 1. The default is non-overwrite. `--replace` is recoverable only when the existing destination is a verified bundle of the matching type; replacement promotes a fully verified staging bundle and retains/restores the prior bundle if promotion verification fails. A stale partial or backup sibling requires operator recovery rather than automatic deletion.

Use an approved secure output root for real-data work. The following are copy-ready examples, but they must not be run until the source access and destination are approved; do not place restricted artifacts in `/tmp` or in the repository checkout:

```sh
uv run python scripts/export_parquet.py \
  --data-root /secure/ppoc-csv \
  --output /secure/ppoc-parquet

uv run python scripts/build_duckdb.py \
  --data-root /secure/ppoc-csv \
  --output /secure/ppoc-duckdb
```

The Parquet bundle contains `manifest.json`, `source-datapackage.json`, and one typed Zstandard Parquet file for each of the eight resources: `patients`, `patients_augmented`, `visits`, `visits_augmented`, `labs`, `medications`, `problem_list`, and `referrals`. `source-datapackage.json` is the copied canonical descriptor used for the export.

The DuckDB bundle contains `manifest.json` and a materialized `ppoc.duckdb`. The database has the eight typed resource tables in `main` plus `ppoc_meta.build`, `ppoc_meta.resources`, `ppoc_meta.descriptor`, and `ppoc_meta.validations`. It contains materialized rows and constraints rather than live links to the CSV files; it is not a direct-CSV reader or an automatically refreshed database.

Each manifest records the package name, version, snapshot, descriptor basename/size/SHA-256, source basenames/sizes/SHA-256 values/row and field counts, exporter build provenance, and aggregate validation status. It intentionally excludes absolute paths and cell values. Parquet output fingerprints bind each `.parquet` file and the descriptor copy, including resource row count, field count, and typed columns. The DuckDB fingerprint binds `ppoc.duckdb` and its resource table names, counts, and field counts. Both exporters preflight the exact eight-resource descriptor contract, decode declared encodings strictly (including labs), validate typed schemas, row counts, constraints, and declared relationships, and confirm source files did not change during export.

Consume derived artifacts read-only and keep query results within the approved environment. For example:

```sh
duckdb -readonly /secure/ppoc-duckdb/ppoc.duckdb \
  -c 'SELECT count(*) FROM visits;'
```

```sh
duckdb -c "SELECT patient_id, age_in_days, height_z_score
FROM read_parquet('/secure/ppoc-parquet/visits_augmented.parquet')
WHERE height_z_score < -2
LIMIT 10;"
```

```python
from pathlib import Path
import duckdb

database = Path("/secure/ppoc-duckdb/ppoc.duckdb")
with duckdb.connect(str(database), read_only=True) as connection:
    counts = connection.sql(
        "SELECT 'patients' AS resource, count(*) AS rows FROM patients "
        "UNION ALL SELECT 'visits', count(*) FROM visits"
    ).fetchall()
print(counts)
```
