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
FIELD_SEMANTIC_KEYS = {
    "x-unit", "x-deidentified", "x-deidentifiedDate", "x-diagnosisPrefix",
    "x-codeSystem", "x-bivRule", "x-conversionFactor", "x-decimalPlaces",
    "x-minAgeMonths", "x-referenceStandard",
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
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f"unsafe output path: {path}")
    with path.open("x", encoding=encoding, newline="") as handle:
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
            enum_types = {str(item): item for item in field["constraints"]["enum"]}
            item["x-categories"] = [
                {"value": enum_types.get(value, value), "count": count}
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
    package_root: Path,
    source_descriptor: dict[str, Any],
    row_counts: dict[str, int],
    *,
    profile: str = "smoke",
) -> Path:
    generated = copy.deepcopy(source_descriptor)
    generated["name"] = f"{source_descriptor['name']}-synthetic"
    generated["title"] = f"{source_descriptor['title']} -- Completely Generated"
    profile_metadata = {
        "smoke": {
            "description": (
                "Synthetic smoke-profile package; contains no real patient records and makes no "
                "claims of demographic representativeness, prevalence calibration, clinical "
                "validity, privacy approval, release approval, or development/golden/validated "
                "fixture status."
            ),
            "version": "synthetic-smoke-v1",
            "keywords": ["synthetic", "smoke-profile"],
        },
        "observed-development": {
            "description": (
                "Synthetic observed-development package; contains no real patient records and "
                "makes no claims of demographic representativeness, prevalence calibration, "
                "clinical validity, privacy approval, release approval, or golden/validated "
                "fixture status."
            ),
            "version": "synthetic-observed-development-v1",
            "keywords": ["synthetic", "observed-development"],
        },
    }.get(
        profile,
        {
            "description": (
                "Synthetic package; contains no real patient records and makes no claims of "
                "demographic representativeness, prevalence calibration, clinical validity, "
                "privacy approval, release approval, or development/golden/validated fixture "
                "status."
            ),
            "version": "synthetic-package-v1",
            "keywords": ["synthetic"],
        },
    )
    generated.update(profile_metadata)
    generated["x-synthetic"] = True
    generated["homepage"] = None
    generated["sources"] = []
    generated["licenses"] = []
    generated["contributors"] = []
    generated.pop("created", None)
    for key in list(generated):
        if key.startswith("x-"):
            generated.pop(key)
    generated["x-synthetic"] = True
    for resource in generated["resources"]:
        for key in list(resource):
            if key.startswith("x-") and key != "x-logicalForeignKeys":
                resource.pop(key)
        resource["x-rowCount"] = row_counts[resource["name"]]
        resource.pop("x-generatedBy", None)
        resource.pop("x-derivedFrom", None)
        for key in SNAPSHOT_STAT_KEYS:
            resource.pop(key, None)
        stats = _generated_field_statistics(package_root, resource)
        for field in resource["schema"]["fields"]:
            for key in list(field):
                if key.startswith("x-") and key not in FIELD_SEMANTIC_KEYS:
                    field.pop(key)
            for key in SNAPSHOT_STAT_KEYS:
                field.pop(key, None)
            field.update(stats[field["name"]])
        if "patient_id" in stats:
            resource["x-uniquePatientCount"] = stats["patient_id"]["x-uniqueValueCount"]
    _replace_logical_link_statistics(package_root, generated)
    output = package_root / "datapackage.json"
    if output.exists() or output.is_symlink():
        raise ValueError(f"unsafe descriptor output path: {output}")
    with output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(generated, indent=2, ensure_ascii=False) + "\n")
    return output
