# Machine-readable data schema

`datapackage.json` is a Frictionless Tabular Data Package descriptor for eight CSV resources. It describes their fields, data types, null representation, primary keys, foreign keys, derivation links, row counts, and selected controlled vocabularies.

Regenerate and validate the descriptor with:

```sh
python3 schema/build.py
python3 schema/build.py --check
```

The descriptor records the data’s nullable fields, incomplete logical visit links, encodings, and controlled values directly in the resource schemas.

## Python usage

Resolve each resource path relative to `datapackage.json` when the CSVs are packaged together; set `PPOC_DATA_ROOT` when they live in another directory. In the current snapshot, the logical `visits_augmented` resource points to `visits_augmented-20251209150512.csv`. This example inspects the package and loads a small sample without hard-coding the column list:

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
