from __future__ import annotations

import csv
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

LogicalLinkPolicy = Literal["allow_incomplete", "complete"]


@dataclass(frozen=True)
class ValidationReport:
    errors: tuple[str, ...]
    row_counts: dict[str, int]


def _validate_value(resource_name: str, row_number: int, field: dict[str, Any], value: str) -> list[str]:
    prefix = f"{resource_name} row {row_number} {field['name']}:"
    constraints = field.get("constraints", {})
    if value == "":
        return [f"{prefix} required value is missing"] if constraints.get("required") else []
    numeric: int | float | None = None
    if field["type"] == "integer":
        if re.fullmatch(r"[+-]?\d+", value) is None:
            return [f"{prefix} invalid integer"]
        try:
            numeric = int(value)
        except (OverflowError, ValueError):
            return [f"{prefix} invalid integer"]
    elif field["type"] == "number":
        try:
            numeric = float(value)
        except (OverflowError, ValueError):
            return [f"{prefix} invalid number"]
        if not math.isfinite(numeric):
            return [f"{prefix} number must be finite"]
    if "enum" in constraints and value not in {str(item) for item in constraints["enum"]}:
        return [f"{prefix} value is not in enum"]
    if numeric is not None and "minimum" in constraints and numeric < constraints["minimum"]:
        return [f"{prefix} value is below minimum"]
    if numeric is not None and "maximum" in constraints and numeric > constraints["maximum"]:
        return [f"{prefix} value is above maximum"]
    return []


def validate_structure(
    package_root: Path,
    descriptor: dict[str, Any],
    *,
    logical_link_policy: Mapping[tuple[str, str], LogicalLinkPolicy] | None = None,
) -> ValidationReport:
    """Validate descriptor-shaped resources and configured relationship semantics.

    Logical links are observational by default because the source contract permits
    nullable and orphan visit links.  Callers that require a particular logical link
    to be complete can pass ``{("resource", "field"): "complete"}``; all other
    logical links remain explicitly ``allow_incomplete``.
    """
    if logical_link_policy is not None:
        known_links = {
            (resource["name"], link["fields"])
            for resource in descriptor["resources"]
            for link in resource.get("x-logicalForeignKeys", [])
        }
        unknown = set(logical_link_policy) - known_links
        if unknown:
            raise ValueError(f"logical link policy names unknown links: {sorted(unknown)!r}")
        invalid = {
            key: value
            for key, value in logical_link_policy.items()
            if value not in {"allow_incomplete", "complete"}
        }
        if invalid:
            raise ValueError(f"logical link policy has invalid values: {invalid!r}")

    errors: list[str] = []
    row_counts: dict[str, int] = {}
    rows_by_resource: dict[str, list[dict[str, str]]] = {}
    primary_values: dict[str, set[str]] = {}
    for resource in descriptor["resources"]:
        name = resource["name"]
        path = package_root / resource["path"]
        if not path.is_file():
            errors.append(f"{name}: missing file")
            row_counts[name] = 0
            continue
        expected = [field["name"] for field in resource["schema"]["fields"]]
        dialect = resource.get("dialect", {})
        try:
            with path.open(encoding=resource.get("encoding", "utf-8"), newline="") as handle:
                reader = csv.DictReader(
                    handle,
                    delimiter=dialect.get("delimiter", ","),
                    quotechar=dialect.get("quoteChar", '"'),
                    doublequote=dialect.get("doubleQuote", True),
                    strict=True,
                )
                if reader.fieldnames != expected:
                    errors.append(f"{name}: header mismatch")
                    row_counts[name] = 0
                    continue
                rows = list(reader)
        except (UnicodeError, csv.Error) as exc:
            errors.append(f"{name}: unreadable CSV ({exc})")
            row_counts[name] = 0
            continue
        rows_by_resource[name] = rows
        row_counts[name] = len(rows)
        for row_number, row in enumerate(rows, start=2):
            if None in row or any(value is None for value in row.values()):
                errors.append(f"{name} row {row_number}: column count mismatch")
            for field in resource["schema"]["fields"]:
                value = row.get(field["name"], "")
                if value is not None:
                    errors.extend(_validate_value(name, row_number, field, value))
        primary_key = resource["schema"].get("primaryKey")
        if primary_key:
            values = [row.get(primary_key, "") for row in rows]
            if any(value == "" for value in values):
                errors.append(f"{name}: invalid primary key {primary_key} (blank value)")
            if len(values) != len(set(values)):
                errors.append(f"{name}: invalid primary key {primary_key} (duplicate value)")
            primary_values[name] = {value for value in values if value != ""}
    for resource in descriptor["resources"]:
        for foreign_key in resource["schema"].get("foreignKeys", []):
            field = foreign_key["fields"]
            target = foreign_key["reference"]["resource"]
            if any(row.get(field, "") and row[field] not in primary_values.get(target, set())
                   for row in rows_by_resource.get(resource["name"], [])):
                errors.append(f"{resource['name']}: unresolved foreign key {field}")
        for logical_link in resource.get("x-logicalForeignKeys", []):
            field = logical_link["fields"]
            target = logical_link["reference"]["resource"]
            values = [row.get(field, "") for row in rows_by_resource.get(resource["name"], [])]
            target_values = primary_values.get(target, set())
            null_rows = sum(value == "" for value in values)
            orphan_rows = sum(value != "" and value not in target_values for value in values)
            policy = (
                logical_link_policy.get((resource["name"], field), "allow_incomplete")
                if logical_link_policy is not None
                else "allow_incomplete"
            )
            if policy == "complete" and (null_rows or orphan_rows):
                errors.append(f"{resource['name']}: unresolved logical foreign key {field}")
    return ValidationReport(tuple(errors), row_counts)
