from __future__ import annotations

import copy
import csv
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

SNAPSHOT_STAT_KEYS = {
    "x-categories", "x-missingCount", "x-observedPercentileRange", "x-observedRange",
    "x-topValues", "x-topValuesTruncated", "x-uniqueDiagnosisCodeCount",
    "x-uniqueLabOrderCount", "x-uniqueVisitIdCount", "x-uniqueValueCount",
    "x-uniquePatientCount", "x-unobservedEnumValues",
}


def write_resource(
    path: Path,
    resource: dict[str, Any],
    rows: Iterable[Mapping[str, object]],
) -> int:
    """Write rows using the source resource's exact header, dialect, and encoding."""
    fields = [field["name"] for field in resource["schema"]["fields"]]
    dialect = resource.get("dialect", {})
    encoding = resource.get("encoding", "utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter=dialect.get("delimiter", ","),
            quotechar=dialect.get("quoteChar", '"'),
            doublequote=dialect.get("doubleQuote", True),
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            if tuple(row) != tuple(fields):
                raise ValueError(f"row keys do not match {resource['name']} field order")
            writer.writerow(row)
            count += 1
    return count


def _read_rows(package_root: Path, resource: dict[str, Any]) -> list[dict[str, str]]:
    dialect = resource.get("dialect", {})
    with (package_root / resource["path"]).open(
        encoding=resource.get("encoding", "utf-8"), newline=""
    ) as handle:
        return list(csv.DictReader(
            handle,
            delimiter=dialect.get("delimiter", ","),
            quotechar=dialect.get("quoteChar", '"'),
            doublequote=dialect.get("doubleQuote", True),
            strict=True,
        ))


def _generated_field_statistics(package_root: Path, resource: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = _read_rows(package_root, resource)
    statistics: dict[str, dict[str, Any]] = {}
    for field in resource["schema"]["fields"]:
        name = field["name"]
        present = [row[name] for row in rows if row.get(name, "") != ""]
        item: dict[str, Any] = {
            "x-missingCount": len(rows) - len(present),
            "x-uniqueValueCount": len(set(present)),
        }
        if field["type"] in {"integer", "number"} and present:
            numeric = [float(value) for value in present]
            item["x-observedRange"] = {"minimum": min(numeric), "maximum": max(numeric)}
        if "enum" in field.get("constraints", {}) and present:
            counts = Counter(present)
            item["x-categories"] = [
                {"value": value, "count": count}
                for value, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
            ]
        statistics[name] = item
    return statistics


def _replace_logical_link_statistics(package_root: Path, descriptor: dict[str, Any]) -> None:
    rows_by_resource = {resource["name"]: _read_rows(package_root, resource) for resource in descriptor["resources"]}
    primary_values: dict[str, set[str]] = {}
    for resource in descriptor["resources"]:
        key = resource["schema"].get("primaryKey")
        if key:
            primary_values[resource["name"]] = {
                row[key] for row in rows_by_resource[resource["name"]] if row.get(key, "")
            }
    for resource in descriptor["resources"]:
        for link in resource.get("x-logicalForeignKeys", []):
            field = link["fields"]
            values = [row.get(field, "") for row in rows_by_resource[resource["name"]]]
            target_values = primary_values.get(link["reference"]["resource"], set())
            link["nullRows"] = sum(value == "" for value in values)
            link["orphanRows"] = sum(value != "" and value not in target_values for value in values)


def write_synthetic_descriptor(
    package_root: Path, source_descriptor: dict[str, Any], row_counts: dict[str, int]
) -> Path:
    generated = copy.deepcopy(source_descriptor)
    generated["name"] = f"{source_descriptor['name']}-synthetic"
    generated["title"] = f"{source_descriptor['title']} -- Completely Generated"
    generated["description"] = "Completely generated development fixtures; contains no real patient records."
    generated["x-synthetic"] = True
    generated["homepage"] = None
    generated["sources"] = []
    generated["licenses"] = []
    generated["contributors"] = []
    generated.pop("x-statisticsSource", None)
    for resource in generated["resources"]:
        resource["x-rowCount"] = row_counts[resource["name"]]
        resource.pop("x-generatedBy", None)
        resource.pop("x-derivedFrom", None)
        for key in SNAPSHOT_STAT_KEYS:
            resource.pop(key, None)
        stats = _generated_field_statistics(package_root, resource)
        for field in resource["schema"]["fields"]:
            for key in SNAPSHOT_STAT_KEYS:
                field.pop(key, None)
            field.update(stats[field["name"]])
        if "patient_id" in stats:
            resource["x-uniquePatientCount"] = stats["patient_id"]["x-uniqueValueCount"]
    _replace_logical_link_statistics(package_root, generated)
    output = package_root / "datapackage.json"
    output.write_text(json.dumps(generated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output
