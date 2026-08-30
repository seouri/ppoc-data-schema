from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


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
