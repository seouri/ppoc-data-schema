from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def load_descriptor(path: Path) -> dict[str, Any]:
    descriptor = json.loads(path.read_text(encoding="utf-8"))
    if descriptor.get("profile") != "tabular-data-package":
        raise ValueError("descriptor is not a tabular-data-package")
    if not isinstance(descriptor.get("resources"), list):
        raise ValueError("descriptor resources must be a list")
    return descriptor


def resource_spec(descriptor: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [item for item in descriptor["resources"] if item.get("name") == name]
    if len(matches) != 1:
        raise KeyError(f"Unknown resource: {name}")
    return matches[0]


def field_names(descriptor: dict[str, Any], name: str) -> tuple[str, ...]:
    fields = resource_spec(descriptor, name)["schema"]["fields"]
    return tuple(field["name"] for field in fields)


def schema_projection(descriptor: dict[str, Any]) -> dict[str, Any]:
    resources: list[dict[str, Any]] = []
    for resource in descriptor["resources"]:
        schema = resource["schema"]
        resources.append(
            {
                "name": resource["name"],
                "path": resource["path"],
                "encoding": resource.get("encoding", "utf-8"),
                "dialect": resource.get("dialect", {}),
                "fields": [
                    {
                        key: field[key]
                        for key in ("name", "type", "constraints")
                        if key in field
                    }
                    for field in schema["fields"]
                ],
                "missingValues": schema.get("missingValues", []),
                "primaryKey": schema.get("primaryKey"),
                "foreignKeys": schema.get("foreignKeys", []),
                "logicalForeignKeys": [
                    {
                        "fields": link["fields"],
                        "reference": link["reference"],
                    }
                    for link in resource.get("x-logicalForeignKeys", [])
                ],
            }
        )
    return {"resources": resources}


def schema_fingerprint(descriptor: dict[str, Any]) -> str:
    payload = json.dumps(
        schema_projection(descriptor),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
