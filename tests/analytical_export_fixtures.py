from __future__ import annotations

import copy
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class TinySnapshot:
    descriptor: Path
    data_root: Path
    rows: dict[str, list[dict[str, object]]]


def write_tiny_snapshot(root: Path) -> TinySnapshot:
    """Write eight fictional PPOC-shaped CSVs and a matching descriptor."""
    descriptor = json.loads((ROOT / "datapackage.json").read_text(encoding="utf-8"))
    descriptor = copy.deepcopy(descriptor)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    data_root = root / "csv"
    data_root.mkdir(mode=0o700)
    rows = _valid_rows(descriptor)
    for resource in descriptor["resources"]:
        name = resource["name"]
        resource["x-rowCount"] = len(rows[name])
        for relationship in resource.get("x-logicalForeignKeys", []):
            relationship["orphanRows"] = 0
            if "nullRows" in relationship:
                relationship["nullRows"] = 0
        _write_resource(data_root / resource["path"], resource, rows[name])
    descriptor_path = root / "datapackage.json"
    descriptor_path.write_text(
        json.dumps(descriptor, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return TinySnapshot(descriptor_path, data_root, rows)


def _valid_rows(descriptor: dict[str, Any]) -> dict[str, list[dict[str, object]]]:
    rows: dict[str, list[dict[str, object]]] = {}
    for resource in descriptor["resources"]:
        count = 2 if resource["name"] in {
            "patients", "patients_augmented", "visits", "visits_augmented"
        } else 1
        rows[resource["name"]] = [
            {
                field["name"]: _valid_value(field, resource["name"], index)
                for field in resource["schema"]["fields"]
            }
            for index in range(count)
        ]

    for index, row in enumerate(rows["patients"]):
        row["patient_id"] = f"SYN-P00{index + 1}"
    for index, row in enumerate(rows["patients_augmented"]):
        row["patient_id"] = f"SYN-P00{index + 1}"
    for index, row in enumerate(rows["visits"]):
        row["patient_id"] = f"SYN-P00{index + 1}"
        row["visit_id"] = f"SYN-V00{index + 1}"
        row["age_in_days"] = (index + 1) * 100
    for index, row in enumerate(rows["visits_augmented"]):
        row["patient_id"] = f"SYN-P00{index + 1}"
        row["visit_id"] = f"SYN-V00{index + 1}"
        row["age_in_days"] = (index + 1) * 100

    for resource_name, row in (
        ("labs", rows["labs"][0]),
        ("medications", rows["medications"][0]),
        ("problem_list", rows["problem_list"][0]),
        ("referrals", rows["referrals"][0]),
    ):
        row["patient_id"] = "SYN-P001"
        if "visit_id" in row:
            row["visit_id"] = "SYN-V001"
        identifier = next(
            field["name"]
            for resource in descriptor["resources"]
            if resource["name"] == resource_name
            for field in resource["schema"]["fields"]
            if field["name"].endswith("_id") and field["name"] not in {"patient_id", "visit_id"}
        )
        row[identifier] = f"SYN-{resource_name.upper()}-001"
    return rows


def _valid_value(field: dict[str, Any], resource_name: str, index: int) -> object:
    constraints = field.get("constraints", {})
    if "enum" in constraints:
        return constraints["enum"][0]
    if "minimum" in constraints:
        return constraints["minimum"]
    if field["type"] == "integer":
        return 1
    if field["type"] == "number":
        return 1
    return f"SYN-{resource_name}-{field['name']}-{index + 1}"


def _write_resource(path: Path, resource: dict[str, Any], rows: list[dict[str, object]]) -> None:
    dialect = resource["dialect"]
    encoding = "latin-1" if resource["encoding"] == "iso-8859-1" else "utf-8"
    with path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[field["name"] for field in resource["schema"]["fields"]],
            delimiter=dialect["delimiter"],
            quotechar=dialect["quoteChar"],
            doublequote=dialect["doubleQuote"],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def replace_csv_cell(
    snapshot: TinySnapshot,
    resource_name: str,
    field_name: str,
    value: object,
) -> None:
    """Rewrite one fictional row cell while preserving descriptor CSV settings."""
    descriptor = json.loads(snapshot.descriptor.read_text(encoding="utf-8"))
    resource = next(item for item in descriptor["resources"] if item["name"] == resource_name)
    rows = list(snapshot.rows[resource_name])
    rows[0] = dict(rows[0])
    rows[0][field_name] = value
    _write_resource(snapshot.data_root / resource["path"], resource, rows)


def replace_labs_cell_bytes(
    snapshot: TinySnapshot,
    field_name: str,
    value: bytes,
) -> None:
    """Rewrite one labs cell from ISO-8859-1 bytes for decoding tests."""
    replace_csv_cell(snapshot, "labs", field_name, value.decode("iso-8859-1"))
