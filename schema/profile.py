#!/usr/bin/env python3
"""Profile the CSV snapshot with DuckDB and write the statistics build.py reads.

schema/build.py owns the shape of the package (fields, types, keys); this script
owns every number in it. Run it whenever the snapshot changes:

    python3 schema/profile.py --data-root /path/to/csvs
    python3 schema/build.py

Requires the DuckDB CLI on PATH. build.py never reads the CSVs, so the
descriptor stays reproducible without access to the data.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DESCRIPTOR = ROOT / "datapackage.json"
OUTPUT = ROOT / "schema" / "stats.json"

# Emit a full value distribution only at or below this cardinality; wider
# columns get a truncated top-values list instead.
CATEGORY_LIMIT = 130
TOP_VALUES = 10

# labs.csv mixes cp1252 text with a few UTF-8 sequences. cp1252 decodes all of
# it except five byte values the code page leaves undefined, so those bytes are
# rewritten before DuckDB sees them. Only punctuation and whitespace inside a
# handful of free-text cells is affected; no count or range depends on it.
CP1252_UNDEFINED = r"\201\215\217\220\235"
CP1252_RESOURCES = {"labs"}

DIAGNOSIS_PREFIX = "enc_diag_"

# Columns that are free text or per-row identifiers: a distinct count is either
# meaningless or already covered by a key check.
SKIP_DISTINCT = {"lab_procedure_description", "result_value"}


def quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def column(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def present(name: str) -> str:
    """A cell holding a value, honouring the declared missingValues of [""]."""
    return f"({column(name)} IS NOT NULL AND {column(name)} <> '')"


class Source:
    """One CSV, queried through the DuckDB CLI."""

    def __init__(self, resource: dict[str, Any], data_root: Path) -> None:
        self.name = resource["name"]
        self.path = data_root / resource["path"]
        self.normalize = self.name in CP1252_RESOURCES
        encoding = "cp1252" if self.normalize else resource["encoding"]
        location = "/dev/stdin" if self.normalize else str(self.path)
        self.table = (
            f"read_csv({quote(location)}, header=true, all_varchar=true, "
            f"encoding={quote(encoding)})"
        )

    def query(self, sql: str) -> list[dict[str, Any]]:
        if self.normalize:
            command = (
                f"LC_ALL=C tr {shlex.quote(CP1252_UNDEFINED)} '?????' < {shlex.quote(str(self.path))} "
                f"| duckdb -json -c {shlex.quote(sql)}"
            )
        else:
            command = f"duckdb -json -c {shlex.quote(sql)}"
        result = subprocess.run(
            ["/bin/sh", "-c", command], capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            raise SystemExit(f"duckdb failed on {self.name}:\n{result.stderr.strip()}\n\nquery:\n{sql}")
        return json.loads(result.stdout or "[]")

    def row(self, sql: str) -> dict[str, Any]:
        rows = self.query(sql)
        return rows[0] if rows else {}


def field_pass(
    source: Source, fields: list[dict[str, Any]], countable: list[str]
) -> dict[str, Any]:
    """One scan: row count, missing counts, numeric ranges, cast failures, and
    the distinct counts that decide how each column is summarised."""
    selects = ["count(*) AS row_count"]
    for entry in fields:
        name = entry["name"]
        selects.append(f"count(*) FILTER (NOT {present(name)}) AS {column('missing:' + name)}")
        if entry["type"] in {"number", "integer"}:
            cast = f"TRY_CAST({column(name)} AS DOUBLE)"
            selects.append(f"min({cast}) AS {column('min:' + name)}")
            selects.append(f"max({cast}) AS {column('max:' + name)}")
            selects.append(
                f"count(*) FILTER ({present(name)} AND {cast} IS NULL) AS {column('bad:' + name)}"
            )
    for name in countable:
        selects.append(f"count(DISTINCT {column(name)}) AS {column('distinct:' + name)}")
    row = source.row(f"SELECT {', '.join(selects)} FROM {source.table};")
    fields_out: dict[str, dict[str, Any]] = {}
    for key, value in row.items():
        if ":" not in key:
            continue
        kind, name = key.split(":", 1)
        fields_out.setdefault(name, {})[kind] = value
    return {"rowCount": row["row_count"], "fields": fields_out}


def histogram_pass(source: Source, names: list[str]) -> dict[str, list[list[Any]]]:
    """One scan for every full distribution: DuckDB histograms, ordered here."""
    if not names:
        return {}
    selects = [
        f"histogram({column(name)}) FILTER ({present(name)}) AS {column(name)}" for name in names
    ]
    row = source.row(f"SELECT {', '.join(selects)} FROM {source.table};")
    counts: dict[str, list[list[Any]]] = {}
    for name in names:
        observed = row.get(name) or {}
        counts[name] = sorted(observed.items(), key=lambda item: (-item[1], str(item[0])))
    return counts


def top_values(source: Source, name: str) -> list[list[Any]]:
    rows = source.query(
        f"SELECT {column(name)} AS value, count(*) AS n FROM {source.table} "
        f"WHERE {present(name)} GROUP BY 1 ORDER BY n DESC, 1 LIMIT {TOP_VALUES};"
    )
    return [[row["value"], row["n"]] for row in rows]


def diagnosis_codes(source: Source, fields: list[dict[str, Any]]) -> int | None:
    names = [e["name"] for e in fields if e["name"].startswith(DIAGNOSIS_PREFIX)]
    if not names:
        return None
    listed = ", ".join(column(name) for name in names)
    return source.row(
        "SELECT count(DISTINCT code) AS n FROM "
        f"(SELECT unnest([{listed}]) AS code FROM {source.table}) WHERE code IS NOT NULL AND code <> '';"
    )["n"]


def bmi_categories(source: Source) -> list[dict[str, Any]]:
    rows = source.query(
        "SELECT bmi_category AS value, count(*) AS n, "
        "min(TRY_CAST(bmi_percentile AS DOUBLE)) AS lo, "
        "max(TRY_CAST(bmi_percentile AS DOUBLE)) AS hi "
        f"FROM {source.table} WHERE {present('bmi_category')} GROUP BY 1 ORDER BY lo;"
    )
    return [
        {"value": r["value"], "count": r["n"], "minPercentile": r["lo"], "maxPercentile": r["hi"]}
        for r in rows
    ]


def link_pass(source: Source, visits_csv: Path, key: str) -> dict[str, int]:
    """Rows whose non-null key is absent from visits.csv."""
    visits = (
        f"read_csv({quote(str(visits_csv))}, header=true, all_varchar=true, encoding='utf-8')"
    )
    row = source.row(
        f"SELECT count(*) AS orphan_rows FROM {source.table} AS child "
        f"WHERE child.{column(key)} IS NOT NULL AND child.{column(key)} <> '' "
        f"AND child.{column(key)} NOT IN (SELECT {column(key)} FROM {visits} WHERE {present(key)});"
    )
    return {"orphanRows": row["orphan_rows"]}


def profile_resource(
    resource: dict[str, Any], data_root: Path, visits_csv: Path
) -> dict[str, Any]:
    source = Source(resource, data_root)
    fields = resource["schema"]["fields"]
    named = {entry["name"]: entry for entry in fields}
    # Continuous columns are described by their range; counting distinct floats
    # would cost memory for a number the descriptor never carries.
    countable = [
        name
        for name, entry in named.items()
        if entry["type"] in {"string", "integer"}
        and name not in SKIP_DISTINCT
        and not name.startswith(DIAGNOSIS_PREFIX)
    ]
    stats = field_pass(source, fields, countable)

    # Blinded identifiers have no informative distribution; everything else is
    # summarised in full below the cardinality limit and truncated above it.
    summarised = [
        name
        for name in countable
        if not named[name].get("x-deidentified") and stats["fields"][name]["distinct"]
    ]
    full = [name for name in summarised if stats["fields"][name]["distinct"] <= CATEGORY_LIMIT]
    for name, observed in histogram_pass(source, full).items():
        stats["fields"][name]["categories"] = [list(item) for item in observed]
    for name in summarised:
        if name not in full and named[name]["type"] == "string":
            stats["fields"][name]["topValues"] = top_values(source, name)

    codes = diagnosis_codes(source, fields)
    if codes is not None:
        stats["uniqueDiagnosisCodeCount"] = codes
    if "bmi_category" in named:
        stats["bmiCategories"] = bmi_categories(source)
    for key in ("patient_id", "visit_id", "lab_order_id"):
        if key in named:
            stats.setdefault("uniqueCounts", {})[key] = stats["fields"][key]["distinct"]
    if resource["name"] != "visits" and "visit_id" in named:
        stats["visitLink"] = link_pass(source, visits_csv, "visit_id")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", required=True, type=Path, help="directory holding the CSVs")
    parser.add_argument("--snapshot", required=True, help="label for the profiled snapshot, e.g. 2026-08-24")
    parser.add_argument("--resource", action="append", help="profile only these resources")
    args = parser.parse_args()

    descriptor = json.loads(DESCRIPTOR.read_text())
    visits_csv = args.data_root / "visits.csv"
    selected = args.resource or [item["name"] for item in descriptor["resources"]]

    existing = json.loads(OUTPUT.read_text()) if OUTPUT.exists() else {"resources": {}}
    resources = existing.get("resources", {})
    for item in descriptor["resources"]:
        if item["name"] not in selected:
            continue
        print(f"profiling {item['name']} ...", flush=True)
        resources[item["name"]] = profile_resource(item, args.data_root, visits_csv)

    version = subprocess.run(
        ["duckdb", "-version"], capture_output=True, text=True, check=False
    ).stdout.strip()
    payload = {
        "snapshot": args.snapshot,
        "profiledWith": version,
        "categoryLimit": CATEGORY_LIMIT,
        "topValues": TOP_VALUES,
        "resources": resources,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
