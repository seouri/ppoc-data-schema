# Typed Parquet and DuckDB Analytical Exports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add secure, descriptor-driven scripts that independently convert the eight canonical PPOC CSV resources into typed Parquet and materialized DuckDB bundles with strict validation and strong provenance.

**Architecture:** A shared `scripts.typed_export` module parses the Frictionless descriptor, preflights and fingerprints all sources, generates explicit typed DuckDB projections, validates aggregate constraints and relationships, and owns secure bundle publication. The Parquet and DuckDB exporters use that same core but materialize independently from CSV; thin scripts expose a common CLI contract.

**Tech Stack:** Python 3.12+, DuckDB Python API 1.3–1.x, PyArrow 23.x, standard-library `argparse`, `csv`, `dataclasses`, `datetime`, `hashlib`, `json`, `os`, `pathlib`, `secrets`, `shutil`, `stat`, `subprocess`, pytest 8.x, and Ruff.

**Spec:** `docs/superpowers/specs/2026-09-04-typed-analytical-exports-design.md`

## Global Constraints

- Read the complete spec before implementation; it is authoritative when this plan abbreviates a requirement.
- CSV plus `datapackage.json` remains canonical. The scripts never modify, move, or delete source CSVs.
- The selected descriptor must define exactly `patients`, `patients_augmented`, `visits`, `visits_augmented`, `labs`, `medications`, `problem_list`, and `referrals`, in that order.
- Supported Frictionless field types are exactly `string`, `integer`, and `number`; map them to `VARCHAR`, `BIGINT`, and `DOUBLE`.
- Supported field constraints are exactly `required`, `enum`, `minimum`, and `maximum`; unknown schema behavior fails closed.
- Declared empty strings become `NULL`; strings are otherwise unchanged, integers require signed-decimal lexical syntax and `BIGINT` range, and numbers must be finite `DOUBLE` values.
- Decode `labs.csv` strictly as descriptor-declared ISO-8859-1. Do not apply CP1252 substitution, UTF-8 repair, trimming, or value normalization.
- Require exact headers, column order, row counts, constraints, primary keys, strict foreign keys, and logical-link aggregate statistics before promotion.
- Persist DuckDB `NOT NULL` and applicable `CHECK` constraints, but do not declare physical primary/foreign keys or create indexes.
- Parquet uses Zstandard and DuckDB's default row-group sizing, one file per resource, without partitioning, sorting, or row reordering.
- Output is always a bundle directory outside the Git checkout. Directories use mode `0700`; artifact and metadata files use mode `0600`.
- Manifests contain source and output SHA-256 hashes and aggregate metadata, but never absolute source paths, clinical values, patient IDs, or visit IDs.
- Public failures identify at most artifact category, resource, field, and failed rule. Never surface raw DuckDB errors, SQL, source paths, row numbers, or offending values.
- New output publication is atomic by sibling-directory rename. `--replace` uses the spec's validated, recoverable target-to-backup then staging-to-target swap.
- Automated tests use only tiny synthetic exact-schema CSVs under pytest temporary directories; they never read uncontrolled `PPOC_DATA_ROOT` or real data.
- Preserve unrelated worktree changes. Stage and commit only files named by each task.

---

## File and responsibility map

- `scripts/typed_export.py`: all shared models, descriptor parsing, source preflight, fingerprinting, type conversion SQL, validation, manifests, secure lifecycle, format exporters, and common CLI parser/dispatcher.
- `scripts/export_parquet.py`: imports `cli_main` from the sibling module and dispatches `parquet`.
- `scripts/build_duckdb.py`: imports `cli_main` from the sibling module and dispatches `duckdb`.
- `tests/analytical_export_fixtures.py`: builds a tiny descriptor and eight internally consistent synthetic CSVs without importing real-data paths.
- `tests/test_typed_export.py`: unit and integration tests for the shared contract, source handling, validation, redaction, manifests, and lifecycle.
- `tests/test_export_parquet.py`: Parquet bundle behavior and independent PyArrow verification.
- `tests/test_build_duckdb.py`: DuckDB tables, constraints, metadata, read-only reopen, and sidecar integrity.
- `tests/test_analytical_export_cli.py`: subprocess behavior, argument/env precedence, exit codes, safety, and redaction.
- `README.md`: concise repository-level entry points and canonical/derived data boundary.
- `schema/README.md`: complete operator and consumer instructions.

### Task 1: Define the descriptor contract and reusable synthetic fixture

**Files:**
- Create: `tests/analytical_export_fixtures.py`
- Create: `tests/test_typed_export.py`
- Create: `scripts/typed_export.py`

**Interfaces:**
- Consumes: checked-in Frictionless descriptor structure and standard-library JSON/path types.
- Produces: `ExportConfig`, `FieldContract`, `RelationshipContract`, `ResourceContract`, `PackageContract`, `ExportError`, `DescriptorError`, `load_package_contract(path)`, and `EXPECTED_RESOURCE_NAMES`.

- [ ] **Step 1: Create the tiny eight-resource test fixture builder**

Add `tests/analytical_export_fixtures.py` with an immutable return type and one public helper:

```python
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
```

Implement `_valid_rows`, `_valid_value`, and `_write_resource` in the same file. Generate two patients and visits (`SYN-P001`/`SYN-P002`, `SYN-V001`/`SYN-V002`), with visit ages `100` and `200`, one row for each ancillary resource, matching augmented keys, and zero logical orphans. Select the first enum member for constrained fields, each numeric minimum when present or `1`, and synthetic nonempty strings elsewhere. Override identifier/link fields explicitly so every strict relationship is valid. Write `labs.csv` with `encoding="iso-8859-1"`; write all others as UTF-8 with descriptor field order and dialect.

Also expose two mutation helpers used by later tests:

```python
def replace_csv_cell(
    snapshot: TinySnapshot,
    resource_name: str,
    field_name: str,
    value: object,
) -> None:
    """Rewrite one fictional row cell while preserving descriptor CSV settings."""


def replace_labs_cell_bytes(
    snapshot: TinySnapshot,
    field_name: str,
    value: bytes,
) -> None:
    """Rewrite one labs cell from ISO-8859-1 bytes for decoding tests."""
```

Implement both by reading/writing only the tiny test resource with its declared
encoding/dialect and exact field order. `replace_labs_cell_bytes` decodes the
provided bytes with ISO-8859-1 before writing, so every byte maps one-to-one.

- [ ] **Step 2: Write failing descriptor-contract tests**

Create `tests/test_typed_export.py` with these initial tests:

```python
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.typed_export import (
    EXPECTED_RESOURCE_NAMES,
    DescriptorError,
    ExportConfig,
    load_package_contract,
)
from tests.analytical_export_fixtures import write_tiny_snapshot


def test_load_package_contract_preserves_order_and_types(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    contract = load_package_contract(fixture.descriptor)

    assert tuple(resource.name for resource in contract.resources) == EXPECTED_RESOURCE_NAMES
    visits = next(resource for resource in contract.resources if resource.name == "visits")
    assert [field.duckdb_type for field in visits.fields[:4]] == [
        "VARCHAR", "VARCHAR", "BIGINT", "VARCHAR"
    ]
    assert contract.snapshot == "2026-08-24"
    assert contract.descriptor_sha256


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda d: d["resources"].pop(), "exactly eight resources"),
        (lambda d: d["resources"].reverse(), "resource order"),
        (lambda d: d["resources"][0].update(path="../patients.csv"), "unsafe resource path"),
        (lambda d: d["resources"][0]["schema"]["fields"][0].update(type="date"), "unsupported field type"),
        (lambda d: d["resources"][0]["schema"]["fields"][0]["constraints"].update(pattern=".*"), "unsupported constraint"),
    ],
)
def test_load_package_contract_rejects_unsupported_descriptor(
    tmp_path: Path, mutation, message: str
) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    descriptor = json.loads(fixture.descriptor.read_text(encoding="utf-8"))
    mutation(descriptor)
    fixture.descriptor.write_text(json.dumps(descriptor), encoding="utf-8")

    with pytest.raises(DescriptorError, match=message):
        load_package_contract(fixture.descriptor)


def test_export_config_is_immutable(tmp_path: Path) -> None:
    config = ExportConfig(tmp_path / "d.json", tmp_path / "csv", tmp_path / "out")
    with pytest.raises(Exception):
        config.replace = True
```

Also test duplicate resource/field names, multi-component paths, wrong format, unsupported encoding/dialect, missing `x-rowCount`, unsupported `missingValues`, malformed scalar keys, invalid logical counts, missing snapshot, non-object JSON, descriptor symlink/special file, and that error messages do not include descriptor contents.

- [ ] **Step 3: Run the contract tests and confirm the expected failure**

Run:

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_typed_export.py
```

Expected: collection fails because `scripts.typed_export` does not exist.

- [ ] **Step 4: Implement immutable contract models and strict descriptor parsing**

Create `scripts/typed_export.py` beginning with these public definitions:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DESCRIPTOR = ROOT / "datapackage.json"
EXPECTED_RESOURCE_NAMES = (
    "patients",
    "patients_augmented",
    "visits",
    "visits_augmented",
    "labs",
    "medications",
    "problem_list",
    "referrals",
)
TYPE_MAP = {"string": "VARCHAR", "integer": "BIGINT", "number": "DOUBLE"}
SUPPORTED_CONSTRAINTS = frozenset({"required", "enum", "minimum", "maximum"})
ENCODING_MAP = {"utf-8": "utf-8", "iso-8859-1": "latin-1"}


class ExportError(RuntimeError):
    """A redacted analytical-export failure safe for CLI display."""


class DescriptorError(ExportError):
    pass


@dataclass(frozen=True)
class ExportConfig:
    descriptor: Path
    data_root: Path
    output: Path
    replace: bool = False


@dataclass(frozen=True)
class FieldContract:
    name: str
    frictionless_type: str
    duckdb_type: str
    required: bool
    enum: tuple[str | int | float, ...] | None
    minimum: int | float | None
    maximum: int | float | None


@dataclass(frozen=True)
class RelationshipContract:
    field: str
    reference_resource: str
    reference_field: str
    orphan_rows: int | None = None
    null_rows: int | None = None


@dataclass(frozen=True)
class ResourceContract:
    name: str
    csv_path: str
    encoding: str
    delimiter: str
    quote_char: str
    double_quote: bool
    missing_values: tuple[str, ...]
    row_count: int
    fields: tuple[FieldContract, ...]
    primary_key: str | None
    foreign_keys: tuple[RelationshipContract, ...]
    logical_foreign_keys: tuple[RelationshipContract, ...]


@dataclass(frozen=True)
class PackageContract:
    name: str
    version: str
    snapshot: str
    descriptor_path: Path
    descriptor_bytes: bytes
    descriptor_sha256: str
    descriptor: dict[str, Any]
    resources: tuple[ResourceContract, ...]
```

Implement `load_package_contract(path: Path) -> PackageContract` as a fail-closed parser. Require the exact contract listed in the spec, reject descriptor symlinks/non-regular files using `lstat`, parse UTF-8 JSON, validate scalar keys and internal references, and return only immutable nested models. Use generic redacted messages such as `descriptor has unsupported field type`; never echo arbitrary JSON values.

- [ ] **Step 5: Run focused tests and lint**

Run:

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_typed_export.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check scripts/typed_export.py tests/analytical_export_fixtures.py tests/test_typed_export.py
git diff --check
```

Expected: descriptor tests pass; Ruff and whitespace checks pass.

- [ ] **Step 6: Commit the contract layer**

```sh
git add scripts/typed_export.py tests/analytical_export_fixtures.py tests/test_typed_export.py
git commit -m "feat: define analytical export contracts"
```

### Task 2: Add source preflight, fingerprinting, and typed CSV projections

**Files:**
- Modify: `scripts/typed_export.py`
- Modify: `tests/test_typed_export.py`

**Interfaces:**
- Consumes: `PackageContract`, `ResourceContract`, `FieldContract`, and resolved data-root paths from Task 1.
- Produces: `SourceState`, `SourceFingerprint`, `preflight_sources(package, data_root)`, `fingerprint_sources(states)`, `verify_sources_unchanged(states)`, `typed_csv_query(resource, source_path)`, `quote_identifier(value)`, and `quote_literal(value)`.

- [ ] **Step 1: Write failing source and conversion tests**

Append tests that exercise the exact input boundary:

```python
import duckdb

from scripts.typed_export import (
    ExportError,
    fingerprint_sources,
    preflight_sources,
    typed_csv_query,
    verify_sources_unchanged,
)
from tests.analytical_export_fixtures import (
    replace_csv_cell,
    replace_labs_cell_bytes,
)


def test_typed_csv_query_maps_values_without_inference(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    package = load_package_contract(fixture.descriptor)
    states = preflight_sources(package, fixture.data_root)
    visits = next(resource for resource in package.resources if resource.name == "visits")
    source = next(state for state in states if state.resource.name == "visits")

    rows = duckdb.connect().execute(typed_csv_query(visits, source.path)).fetchall()

    assert rows[0][0:3] == ("SYN-P001", "SYN-V001", 100)


@pytest.mark.parametrize("bad_value", ["1.0", "1e3", "9223372036854775808"])
def test_integer_conversion_fails_without_echoing_value(tmp_path: Path, bad_value: str) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    replace_csv_cell(fixture, "visits", "age_in_days", bad_value)
    package = load_package_contract(fixture.descriptor)
    source = preflight_sources(package, fixture.data_root)[2]

    with pytest.raises(Exception) as caught:
        duckdb.connect().execute(typed_csv_query(package.resources[2], source.path)).fetchall()

    assert "visits.age_in_days failed integer conversion" in str(caught.value)
    assert bad_value not in str(caught.value)


def test_labs_uses_literal_iso_8859_1_decoding(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    replace_labs_cell_bytes(fixture, "result_value", b"caf\xe9\x81")
    package = load_package_contract(fixture.descriptor)
    source = preflight_sources(package, fixture.data_root)[4]
    query = typed_csv_query(package.resources[4], source.path)

    value = duckdb.connect().execute(
        f'SELECT "result_value" FROM ({query}) AS typed_labs'
    ).fetchone()[0]

    assert value == "caf\u00e9\u0081"
```

Add tests for all-eight-files preflight before hashing, exact header order,
missing/symlinked/non-regular CSV rejection, UTF-8 decoding failure redaction,
empty strings becoming `None`, finite `DOUBLE` requirements (`NaN`, `Inf`, and
overflow fail), unchanged nonempty strings, safe SQL quoting, source basenames,
SHA-256 correctness, mode/size/device/inode/mtime capture, and mutation detected
by `verify_sources_unchanged`.

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_typed_export.py -k "source or typed or integer or labs or fingerprint"
```

Expected: import failures for the new source/conversion interfaces.

- [ ] **Step 3: Implement source models, full preflight, and hashing**

Add:

```python
@dataclass(frozen=True)
class SourceState:
    resource: ResourceContract
    path: Path
    device: int
    inode: int
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class SourceFingerprint:
    resource_name: str
    basename: str
    size: int
    sha256: str
    row_count: int
    field_count: int
```

`preflight_sources` must resolve the data root, build all eight paths from safe
descriptor basenames, reject resource symlinks/special files with `lstat`, read
each header with Python `csv.reader` using the descriptor encoding/dialect, and
compare exact names/order. Collect every failure before creating staging, but
emit only resource-level redacted messages.

`fingerprint_sources` performs one 1 MiB-block SHA-256 pass per source.
`verify_sources_unchanged` repeats `lstat` and compares device, inode, size, and
mtime nanoseconds to the captured state.

- [ ] **Step 4: Implement explicit typed DuckDB query generation**

Generate one relation query per resource. The shape must be equivalent to:

```python
def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def quote_literal(value: str | int | float | bool) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + value.replace("'", "''") + "'"


def _integer_expression(resource: str, field: str) -> str:
    raw = quote_identifier(field)
    error = quote_literal(f"{resource}.{field} failed integer conversion")
    return (
        f"CASE WHEN {raw} IS NULL OR {raw} = '' THEN NULL "
        f"WHEN NOT regexp_full_match({raw}, '^[+-]?[0-9]+$') "
        f"OR try_cast({raw} AS BIGINT) IS NULL THEN error({error}) "
        f"ELSE cast({raw} AS BIGINT) END"
    )


def _number_expression(resource: str, field: str) -> str:
    raw = quote_identifier(field)
    error = quote_literal(f"{resource}.{field} failed number conversion")
    return (
        f"CASE WHEN {raw} IS NULL OR {raw} = '' THEN NULL "
        f"WHEN try_cast({raw} AS DOUBLE) IS NULL "
        f"OR NOT isfinite(try_cast({raw} AS DOUBLE)) THEN error({error}) "
        f"ELSE cast({raw} AS DOUBLE) END"
    )
```

Strings use `NULLIF` around the quoted raw-column expression. Alias every projection back to the
quoted descriptor name. Build `read_csv` with explicit `columns` of `VARCHAR`,
`header=true`, `all_varchar=true`, delimiter, quote character, `escape` equal
to the quote character for the required `doubleQuote: true` dialect, and
`encoding` from `ENCODING_MAP`. Quote all path and descriptor literals with
`quote_literal`; never concatenate raw cell values.

Catch DuckDB exceptions only at the exporter boundary in later tasks. The SQL
itself uses fixed calls to DuckDB's `error` scalar function so direct conversion failures remain
redacted.

Add `_redacted_duckdb_error(error: Exception, package: PackageContract,
fallback: str) -> ExportError`. It may return a conversion message only when
the exception contains one of the exact precomputed
resource-and-field `failed integer conversion` or `failed number conversion`
tokens derived from the parsed contract; otherwise it returns only `fallback`.
It must never copy the raw exception text into the public error.

- [ ] **Step 5: Run conversion tests and lint**

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_typed_export.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check scripts/typed_export.py tests/analytical_export_fixtures.py tests/test_typed_export.py
git diff --check
```

- [ ] **Step 6: Commit source ingestion**

```sh
git add scripts/typed_export.py tests/analytical_export_fixtures.py tests/test_typed_export.py
git commit -m "feat: add typed CSV ingestion"
```

### Task 3: Implement aggregate artifact validation

**Files:**
- Modify: `scripts/typed_export.py`
- Modify: `tests/test_typed_export.py`

**Interfaces:**
- Consumes: `PackageContract` and a callback that returns a trusted SQL relation for each typed output resource.
- Produces: `ValidationRecord` and `validate_artifact(connection, package, relation_for) -> tuple[ValidationRecord, ...]`.

- [ ] **Step 1: Write failing aggregate-validation tests**

Create typed temporary tables from the tiny snapshot, then test each rule by
mutating a copied table. Use only aggregate assertions:

```python
def _load_tiny_tables(fixture: TinySnapshot) -> tuple[PackageContract, duckdb.DuckDBPyConnection]:
    package = load_package_contract(fixture.descriptor)
    sources = preflight_sources(package, fixture.data_root)
    connection = duckdb.connect()
    for source in sources:
        table = quote_identifier(source.resource.name)
        connection.execute(
            f"CREATE TABLE main.{table} AS {typed_csv_query(source.resource, source.path)}"
        )
    return package, connection
```

```python
from scripts.typed_export import ValidationError, validate_artifact


def test_validate_artifact_passes_complete_tiny_snapshot(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    package, connection = _load_tiny_tables(fixture)

    records = validate_artifact(
        connection,
        package,
        lambda resource: f'main."{resource.name}"',
    )

    assert records
    assert {record.status for record in records} == {"PASS"}
    assert all(record.observed is not None for record in records)


def test_validate_artifact_rejects_duplicate_key_without_disclosing_key(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    package, connection = _load_tiny_tables(fixture)
    connection.execute('INSERT INTO main."patients" SELECT * FROM main."patients" LIMIT 1')

    with pytest.raises(ValidationError, match="patients primary key was not unique") as caught:
        validate_artifact(connection, package, lambda resource: f'main."{resource.name}"')

    assert "SYN-P001" not in str(caught.value)
```

Add focused failures for row count, required-null count, enum, minimum, maximum,
missing primary key, unmatched strict foreign key, logical orphan count, logical
null count, and output column name/order/type. Add a test proving logical
orphans are compared with descriptor aggregates but not treated as strict FK
violations when the declared count matches.

- [ ] **Step 2: Run validation tests and confirm failure**

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_typed_export.py -k "validate_artifact"
```

Expected: import failure for `ValidationRecord`, `ValidationError`, and
`validate_artifact`.

- [ ] **Step 3: Implement validation records and rule queries**

Add:

```python
@dataclass(frozen=True)
class ValidationRecord:
    resource: str
    field: str | None
    rule: str
    expected: int | float | str | list[object]
    observed: int | float | str | list[object]
    status: str = "PASS"


class ValidationError(ExportError):
    pass


def validate_artifact(
    connection: duckdb.DuckDBPyConnection,
    package: PackageContract,
    relation_for: Callable[[ResourceContract], str],
) -> tuple[ValidationRecord, ...]:
    records: list[ValidationRecord] = []
    relations = {resource.name: relation_for(resource) for resource in package.resources}
    for resource in package.resources:
        records.extend(validate_relation_schema(connection, resource, relations[resource.name]))
        records.extend(validate_resource_rules(connection, resource, relations[resource.name]))
        records.extend(validate_primary_key(connection, resource, relations[resource.name]))
        records.extend(validate_foreign_keys(connection, resource, relations))
        records.extend(validate_logical_foreign_keys(connection, resource, relations))
    return tuple(records)
```

Implement quoted aggregate SQL for every rule in the spec. Use
`count(*) FILTER (WHERE predicate)` with the generated rule predicate for
row/field/constraint counts, grouped count-of-counts
for scalar primary-key uniqueness, and `NOT EXISTS` anti-joins for foreign keys.
For logical links, count null child keys separately and nonnull values with no
referenced match. Treat omitted `nullRows` as expected zero.

`validate_resource_rules` must place row count and every required/enum/minimum/
maximum violation count for one resource in a single aggregate `SELECT`, so the
17.2-million-row labs and 6.5-million-row visit resources are not rescanned once
per field. Primary-key and each cross-resource relationship check may use a
separate aggregate query.

Define the five private helpers referenced above with these exact signatures:

```python
def validate_relation_schema(
    connection: duckdb.DuckDBPyConnection,
    resource: ResourceContract,
    relation: str,
) -> list[ValidationRecord]:
    """Validate ordered names and mapped types through DESCRIBE."""


def validate_resource_rules(
    connection: duckdb.DuckDBPyConnection,
    resource: ResourceContract,
    relation: str,
) -> list[ValidationRecord]:
    """Validate row count, requiredness, enum, minimum, and maximum rules."""


def validate_primary_key(
    connection: duckdb.DuckDBPyConnection,
    resource: ResourceContract,
    relation: str,
) -> list[ValidationRecord]:
    """Validate a scalar primary key when declared."""


def validate_foreign_keys(
    connection: duckdb.DuckDBPyConnection,
    resource: ResourceContract,
    relations: dict[str, str],
) -> list[ValidationRecord]:
    """Validate every strict scalar foreign key by aggregate anti-join."""


def validate_logical_foreign_keys(
    connection: duckdb.DuckDBPyConnection,
    resource: ResourceContract,
    relations: dict[str, str],
) -> list[ValidationRecord]:
    """Compare null and nonnull-orphan counts with descriptor metadata."""
```

Before data rules, introspect each trusted relation with `DESCRIBE SELECT *`
and require exact mapped names/order/types. Append a `PASS` record
for every completed check. Raise immediately on a mismatch with a fixed message
that names only resource, field, and rule; do not include aggregate SQL or rows.

- [ ] **Step 4: Run the complete shared tests and lint**

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_typed_export.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check scripts/typed_export.py tests/test_typed_export.py
git diff --check
```

- [ ] **Step 5: Commit aggregate validation**

```sh
git add scripts/typed_export.py tests/test_typed_export.py
git commit -m "feat: validate analytical export artifacts"
```

### Task 4: Add canonical manifests and secure bundle lifecycle

**Files:**
- Modify: `scripts/typed_export.py`
- Modify: `tests/test_typed_export.py`

**Interfaces:**
- Consumes: `ExportConfig`, `PackageContract`, source fingerprints, output fingerprints, and validation records.
- Produces: `OutputFingerprint`, `BuildProvenance`, `BundleRun`, `build_manifest`, `write_manifest`, `verify_bundle_manifest`, and `ensure_safe_output` with the signatures defined below.

- [ ] **Step 1: Write failing manifest, permission, and lifecycle tests**

Add tests for canonical JSON and the complete top-level contract:

```python
from scripts.typed_export import (
    BundleRun,
    OutputCollisionError,
    UnsafePathError,
    build_manifest,
    ensure_safe_output,
    sha256_file,
    write_manifest,
)


def test_manifest_is_canonical_and_contains_no_absolute_paths(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path / "input")
    manifest = {
        "manifestVersion": 1,
        "status": "PASS",
        "artifactType": "parquet-bundle",
        "package": {"name": "test", "version": "1", "snapshot": "test"},
        "build": {},
        "descriptor": {},
        "sources": [],
        "outputs": [],
        "validation": {"status": "PASS", "checkCount": 0, "failedChecks": 0},
    }
    destination = tmp_path / "manifest.json"

    write_manifest(destination, manifest)
    payload = destination.read_text(encoding="utf-8")

    assert payload.endswith("\n")
    assert json.loads(payload)["status"] == "PASS"
    assert str(fixture.data_root) not in payload
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
```

Add tests that output equal to/below the repository is rejected; output equal
to/an ancestor of descriptor/data root/source is rejected; output symlinks and
special files are rejected; new staging is `0700`; staged files are `0600`;
initial promotion is one rename; collision without `--replace` preserves the
target; replacement refuses unknown/wrong-kind/unexpected-inventory bundles;
replacement moves a verified target to backup only after new staging validates;
an injected post-backup failure restores the old target; and stale matching
partial/backup siblings cause a basename-only recovery error.

- [ ] **Step 2: Run lifecycle tests and confirm failure**

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_typed_export.py -k "manifest or safe_output or bundle or replace or permission"
```

Expected: missing lifecycle interfaces.

- [ ] **Step 3: Implement canonical fingerprints, provenance, and manifest construction**

Add immutable models:

```python
@dataclass(frozen=True)
class OutputFingerprint:
    basename: str
    size: int
    sha256: str
    row_count: int | None = None
    field_count: int | None = None
    columns: tuple[tuple[str, str], ...] = ()
    tables: tuple[tuple[str, int, int], ...] = ()


@dataclass(frozen=True)
class BuildProvenance:
    created_at_utc: str
    python_version: str
    duckdb_version: str
    pyarrow_version: str
    exporter_git_revision: str | None
    exporter_git_dirty: bool | None
    exporter_module_sha256: str
```

Use these exact manifest/lifecycle helper signatures:

- `build_manifest(artifact_type: str, package: PackageContract, provenance: BuildProvenance, sources: tuple[SourceFingerprint, ...], outputs: tuple[OutputFingerprint, ...], validations: tuple[ValidationRecord, ...]) -> dict[str, object]`
- `write_manifest(path: Path, payload: Mapping[str, object]) -> None`
- `verify_bundle_manifest(bundle: Path, artifact_type: str, expected_names: frozenset[str]) -> dict[str, Any]`
- `ensure_safe_output(repo_root: Path, package: PackageContract, sources: tuple[SourceState, ...], output: Path) -> Path`

Implement `sha256_file` with 1 MiB binary blocks. Build provenance from a
single UTC timestamp, runtime package versions, `git rev-parse HEAD` and
`git status --porcelain` when available, and the bytes of
`scripts/typed_export.py`. Git failures set revision/dirty to `None`; they do
not expose stderr or fail an otherwise attributable run because the module hash
remains authoritative.

Serialize manifests using `json.dumps(payload, indent=2, sort_keys=True,
ensure_ascii=False) + "\n"`. Enforce the exact top-level keys and artifact
types from the spec. Validate every basename and 64-character lowercase digest
before writing. Write through a sibling temporary file opened with mode `0600`,
flush and `fsync`, then `os.replace` within staging.

- [ ] **Step 4: Implement safe staging and recoverable promotion**

Add redacted subclasses `UnsafePathError`, `OutputCollisionError`, and
`LifecycleError`. Implement:

```python
@dataclass
class BundleRun:
    output: Path
    artifact_type: str
    replace: bool
    staging: Path
    backup: Path | None = None
```

Implement `BundleRun.start(output: Path, artifact_type: str, replace: bool) ->
BundleRun`, `promote(self, verify: Callable[[Path], None]) -> Path`, and
`discard_staging(self) -> None` exactly as described below. Also define exact
signatures for `build_manifest`, `write_manifest`, `verify_bundle_manifest`,
and `ensure_safe_output`; use immutable tuples for source, output, and
validation collections.

Use sibling names
`.OUTPUT.parquet-bundle.partial-TOKEN`/`.backup-TOKEN` or
`.OUTPUT.duckdb-bundle.partial-TOKEN`/`.backup-TOKEN`, where `TOKEN` comes from
`secrets.token_hex(8)`. Reject pre-existing matching partial/backup siblings;
do not delete them. Create staging with `mkdir(mode=0o700)` and explicitly
`chmod(0o700)`.

Require the resolved output parent to exist as a directory; do not create an
unapproved parent hierarchy. For new output, verify staging then rename it
once and verify the promoted target. If that final verification fails, rename
the just-promoted directory back to this run's staging path and discard it;
never leave a knowingly failed initial publication at the target. For replacement, validate
the existing manifest/artifact kind/inventory, verify staging, rename target to
backup, rename staging to target, call `verify(target)`, and remove backup only
after success. If a caught error occurs after target-to-backup, restore the
backup. When the newly promoted target exists, first rename it back to this
run's now-vacant staging path, rename backup to target, then discard only that
failed staging bundle. Never recurse outside the exact staging/backup paths
generated by this run.

- [ ] **Step 5: Run lifecycle tests, shared tests, and lint**

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_typed_export.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check scripts/typed_export.py tests/test_typed_export.py
git diff --check
```

- [ ] **Step 6: Commit secure lifecycle support**

```sh
git add scripts/typed_export.py tests/test_typed_export.py
git commit -m "feat: add secure analytical bundle lifecycle"
```

### Task 5: Implement the typed Parquet bundle exporter

**Files:**
- Modify: `scripts/typed_export.py`
- Create: `tests/test_export_parquet.py`

**Interfaces:**
- Consumes: all shared contracts, ingestion, validation, manifest, and lifecycle interfaces from Tasks 1–4.
- Produces: `export_parquet_bundle(config: ExportConfig) -> Path` and `verify_parquet_bundle(path: Path, package: PackageContract) -> None`.

- [ ] **Step 1: Write failing Parquet bundle integration tests**

Create `tests/test_export_parquet.py`:

```python
from __future__ import annotations

import json
import stat
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from scripts.typed_export import ExportConfig, export_parquet_bundle, sha256_file
from tests.analytical_export_fixtures import write_tiny_snapshot


def test_export_parquet_bundle_writes_all_typed_resources(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path / "input")
    output = tmp_path / "parquet"

    result = export_parquet_bundle(
        ExportConfig(fixture.descriptor, fixture.data_root, output)
    )

    assert result == output
    assert {path.name for path in output.iterdir()} == {
        "patients.parquet", "patients_augmented.parquet", "visits.parquet",
        "visits_augmented.parquet", "labs.parquet", "medications.parquet",
        "problem_list.parquet", "referrals.parquet",
        "source-datapackage.json", "manifest.json",
    }
    visits = pq.read_table(output / "visits.parquet")
    assert visits.schema.names[:3] == ["patient_id", "visit_id", "age_in_days"]
    assert visits.schema.field("age_in_days").type == pa.int64()
    assert visits.column("age_in_days").to_pylist() == [100, 200]
    assert stat.S_IMODE((output / "visits.parquet").stat().st_mode) == 0o600
```

Also assert every expected Arrow type/order, null conversion, row count,
Zstandard codec on every populated column chunk, literal ISO-8859-1 lab string,
byte-identical descriptor copy, source/output hash correctness, `PASS` manifest,
same logical rows/schemas across two fresh outputs, source mutation rejection,
conversion/validation failures leaving no promoted bundle, collision behavior,
and successful/rollback-safe replacement.

- [ ] **Step 2: Run Parquet tests and verify they fail**

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_export_parquet.py
```

Expected: import failure for `export_parquet_bundle`.

- [ ] **Step 3: Implement staged Zstandard Parquet export**

Implement `export_parquet_bundle` with this lifecycle:

```python
def export_parquet_bundle(config: ExportConfig) -> Path:
    package = load_package_contract(config.descriptor)
    sources = preflight_sources(package, config.data_root)
    ensure_safe_output(ROOT, package, sources, config.output)
    source_hashes = fingerprint_sources(sources)
    run = BundleRun.start(config.output, "parquet-bundle", config.replace)
    try:
        connection = duckdb.connect()
        connection.execute(f"SET temp_directory={quote_literal(str(run.staging / '.duckdb-tmp'))}")
        for source in sources:
            target = run.staging / f"{source.resource.name}.parquet"
            query = typed_csv_query(source.resource, source.path)
            connection.execute(
                f"COPY ({query}) TO {quote_literal(str(target))} "
                "(FORMAT PARQUET, COMPRESSION ZSTD)"
            )
            target.chmod(0o600)
        records = validate_artifact(
            connection,
            package,
            lambda resource: f"read_parquet({quote_literal(str(run.staging / (resource.name + '.parquet')))})",
        )
        _verify_parquet_with_pyarrow(run.staging, package)
        verify_sources_unchanged(sources)
        _finish_parquet_manifest(run.staging, package, source_hashes, records)
        return run.promote(lambda path: verify_parquet_bundle(path, package))
    except Exception as error:
        run.discard_staging()
        raise _redacted_export_error(error, "parquet export failed") from None
```

Use context/finally handling so the DuckDB connection closes before staging is
discarded or promoted. Remove the internal spill directory before inventory
verification. Copy descriptor bytes directly from `PackageContract` and set
mode `0600`.

- [ ] **Step 4: Implement independent PyArrow and promoted-bundle verification**

For each resource, compare `pyarrow.parquet.ParquetFile.schema_arrow` with the
expected ordered Arrow fields (`string`, `int64`, `float64`), compare metadata
row count, and require `column(index).compression == "ZSTD"` for every column
chunk in every nonempty row group. `verify_parquet_bundle` reparses the
manifest, requires exact inventory, verifies every listed SHA-256/size, verifies
the descriptor hash/copy, and repeats lightweight PyArrow schema/count/codec
checks without reading clinical rows into errors.

- [ ] **Step 5: Run focused and shared verification**

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_export_parquet.py tests/test_typed_export.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check scripts/typed_export.py tests/test_export_parquet.py tests/test_typed_export.py
git diff --check
```

- [ ] **Step 6: Commit the Parquet exporter**

```sh
git add scripts/typed_export.py tests/test_export_parquet.py
git commit -m "feat: export typed Parquet resources"
```

### Task 6: Implement the materialized DuckDB bundle exporter

**Files:**
- Modify: `scripts/typed_export.py`
- Create: `tests/test_build_duckdb.py`

**Interfaces:**
- Consumes: all shared contracts, ingestion, validation, manifest, and lifecycle interfaces from Tasks 1–4.
- Produces: `export_duckdb_bundle(config: ExportConfig) -> Path`, `resource_table_ddl(resource: ResourceContract) -> str`, and `verify_duckdb_bundle(path: Path, package: PackageContract) -> None`.

- [ ] **Step 1: Write failing DuckDB bundle integration tests**

Create `tests/test_build_duckdb.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import duckdb

from scripts.typed_export import ExportConfig, export_duckdb_bundle, sha256_file
from tests.analytical_export_fixtures import write_tiny_snapshot


def test_export_duckdb_bundle_materializes_resources_and_metadata(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path / "input")
    output = tmp_path / "duckdb"

    result = export_duckdb_bundle(
        ExportConfig(fixture.descriptor, fixture.data_root, output)
    )

    assert result == output
    assert {path.name for path in output.iterdir()} == {"ppoc.duckdb", "manifest.json"}
    connection = duckdb.connect(str(output / "ppoc.duckdb"), read_only=True)
    tables = connection.execute(
        "SELECT table_schema, table_name FROM information_schema.tables "
        "ORDER BY table_schema, table_name"
    ).fetchall()
    assert ("main", "patients") in tables
    assert ("main", "labs") in tables
    assert ("ppoc_meta", "build") in tables
    assert ("ppoc_meta", "validations") in tables
    assert connection.execute('SELECT count(*) FROM main."visits"').fetchone() == (2,)
```

Add exact assertions for the eight `main` and four `ppoc_meta` tables; mapped
column order/types; expected `NOT NULL` and `CHECK` constraints; no `PRIMARY
KEY`, `FOREIGN KEY`, indexes, views, macros, or sequences; literal lab text;
resource rows and nulls; complete source/build/descriptor/validation metadata;
read-only reopen; exact two-file inventory/modes; final DB SHA-256 in manifest;
manifest hash verification; logical equality across two fresh runs without
requiring binary DB hash equality; source mutation/conversion/validation
failure; collision; and rollback-safe replacement.

- [ ] **Step 2: Run DuckDB tests and verify they fail**

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_build_duckdb.py
```

Expected: import failure for `export_duckdb_bundle`.

- [ ] **Step 3: Implement explicit resource DDL**

Generate DDL without primary/foreign keys:

```python
def resource_table_ddl(resource: ResourceContract) -> str:
    columns: list[str] = []
    for field in resource.fields:
        clauses = [quote_identifier(field.name), field.duckdb_type]
        if field.required:
            clauses.append("NOT NULL")
        checks: list[str] = []
        column = quote_identifier(field.name)
        if field.enum is not None:
            values = ", ".join(quote_literal(value) for value in field.enum)
            checks.append(f"{column} IN ({values})")
        if field.minimum is not None:
            checks.append(f"{column} >= {quote_literal(field.minimum)}")
        if field.maximum is not None:
            checks.append(f"{column} <= {quote_literal(field.maximum)}")
        if checks:
            clauses.append("CHECK (" + " AND ".join(checks) + ")")
        columns.append(" ".join(clauses))
    return f"CREATE TABLE main.{quote_identifier(resource.name)} (" + ", ".join(columns) + ")"
```

Nullable `CHECK` expressions intentionally pass SQL `NULL`; requiredness is
owned by `NOT NULL`. Insert from `typed_csv_query` so conversion remains one CSV
scan per resource and malformed optional numerics cannot silently become null.

- [ ] **Step 4: Implement exact `ppoc_meta` schema and population**

Create these tables, without keys/indexes:

```sql
CREATE SCHEMA ppoc_meta;
CREATE TABLE ppoc_meta.build (
  manifest_version INTEGER NOT NULL,
  package_name VARCHAR NOT NULL,
  package_version VARCHAR NOT NULL,
  snapshot VARCHAR NOT NULL,
  created_at_utc VARCHAR NOT NULL,
  descriptor_sha256 VARCHAR NOT NULL,
  python_version VARCHAR NOT NULL,
  duckdb_version VARCHAR NOT NULL,
  pyarrow_version VARCHAR NOT NULL,
  exporter_git_revision VARCHAR,
  exporter_git_dirty BOOLEAN,
  exporter_module_sha256 VARCHAR NOT NULL
);
CREATE TABLE ppoc_meta.resources (
  ordinal INTEGER NOT NULL,
  resource_name VARCHAR NOT NULL,
  source_basename VARCHAR NOT NULL,
  source_size BIGINT NOT NULL,
  source_sha256 VARCHAR NOT NULL,
  row_count BIGINT NOT NULL,
  table_name VARCHAR NOT NULL,
  field_count BIGINT NOT NULL
);
CREATE TABLE ppoc_meta.descriptor (
  descriptor_sha256 VARCHAR NOT NULL,
  descriptor_json VARCHAR NOT NULL
);
CREATE TABLE ppoc_meta.validations (
  ordinal INTEGER NOT NULL,
  resource_name VARCHAR NOT NULL,
  field_name VARCHAR,
  rule VARCHAR NOT NULL,
  expected_json VARCHAR NOT NULL,
  observed_json VARCHAR NOT NULL,
  status VARCHAR NOT NULL CHECK (status = 'PASS')
);
```

Insert only aggregate/provenance values. Serialize descriptor and
expected/observed values with canonical JSON. Use the same `BuildProvenance`
instance for DB metadata and sidecar manifest so timestamps agree.

- [ ] **Step 5: Implement staged database build and read-only verification**

Implement `export_duckdb_bundle` in this order: parse/preflight/safety/hash;
start `duckdb-bundle` staging; connect to `run.staging / "ppoc.duckdb"`; create
each table and execute an `INSERT INTO` statement whose target is the quoted
resource table and whose query is returned by `typed_csv_query`, in descriptor
order; run
`validate_artifact` over `main` tables; verify sources unchanged; create and
populate `ppoc_meta`; execute `CHECKPOINT`; close; chmod DB `0600`; reopen
read-only; verify inventory/schema/types/constraints/counts/metadata and query
`duckdb_indexes()` for no indexes; close; hash DB; write manifest; verify exact
bundle; and call `BundleRun.promote` with
`lambda path: verify_duckdb_bundle(path, package)`.

Catch raw DuckDB errors and replace them with the fixed resource/field
conversion message when already produced by DuckDB's `error` function, or the generic
redacted category `duckdb export failed`. Never include the database path or
query in the public exception.

- [ ] **Step 6: Run focused and shared verification**

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_build_duckdb.py tests/test_typed_export.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check scripts/typed_export.py tests/test_build_duckdb.py tests/test_typed_export.py
git diff --check
```

- [ ] **Step 7: Commit the DuckDB exporter**

```sh
git add scripts/typed_export.py tests/test_build_duckdb.py
git commit -m "feat: build typed PPOC DuckDB"
```

### Task 7: Add the common CLI, thin scripts, and operator documentation

**Files:**
- Modify: `scripts/typed_export.py`
- Create: `scripts/export_parquet.py`
- Create: `scripts/build_duckdb.py`
- Create: `tests/test_analytical_export_cli.py`
- Modify: `README.md`
- Modify: `schema/README.md`

**Interfaces:**
- Consumes: `export_parquet_bundle`, `export_duckdb_bundle`, `ExportConfig`, `DEFAULT_DESCRIPTOR`, and `ExportError`.
- Produces: `parse_args(artifact_type, argv) -> ExportConfig`, `cli_main(artifact_type, argv=None) -> int`, and two directly executable commands.

- [ ] **Step 1: Write failing subprocess CLI tests**

Create `tests/test_analytical_export_cli.py` using `subprocess.run` with a
controlled environment:

```python
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tests.analytical_export_fixtures import write_tiny_snapshot

ROOT = Path(__file__).resolve().parents[1]


def _run_cli(script: str, fixture, output: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / script),
            "--descriptor", str(fixture.descriptor),
            "--data-root", str(fixture.data_root),
            "--output", str(output),
            *extra,
        ],
        cwd=ROOT,
        env={**os.environ, "PPOC_DATA_ROOT": ""},
        capture_output=True,
        text=True,
    )


def test_parquet_cli_uses_explicit_paths(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path / "input")
    output = tmp_path / "parquet"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "export_parquet.py"),
            "--descriptor", str(fixture.descriptor),
            "--data-root", str(fixture.data_root),
            "--output", str(output),
        ],
        cwd=ROOT,
        env={**os.environ, "PPOC_DATA_ROOT": ""},
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "parquet-bundle" in result.stdout
    assert "status=PASS" in result.stdout
    assert result.stderr == ""


def test_cli_error_redacts_source_path_and_value(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path / "private-secret-input")
    replace_csv_cell(fixture, "visits", "age_in_days", "SECRET-VALUE")
    result = _run_cli("export_parquet.py", fixture, tmp_path / "out")

    assert result.returncode == 1
    assert "visits.age_in_days failed integer conversion" in result.stderr
    assert "private-secret-input" not in result.stderr
    assert "SECRET-VALUE" not in result.stderr
```

Import `replace_csv_cell` from `tests.analytical_export_fixtures`. Add tests for
both `--help` commands; `parse_args` returning `DEFAULT_DESCRIPTOR` when
`--descriptor` is omitted; explicit
`--data-root` overriding `PPOC_DATA_ROOT`; environment fallback; missing both
returning 2; required `--output`; output-inside-repo rejection; collision and
`--replace`; success summary fields; argument errors returning 2; exporter
errors returning 1; and no traceback/SQL/path/value leakage.
Add `test_two_destination_cli_smoke`, which invokes each command twice and
compares source hashes, resource schemas/counts, typed rows, constraints, and
validation status without requiring binary output hashes to match.

- [ ] **Step 2: Run CLI tests and verify they fail**

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_analytical_export_cli.py
```

Expected: scripts do not exist.

- [ ] **Step 3: Implement the common parser and dispatcher**

Add:

```python
def parse_args(artifact_type: str, argv: Sequence[str] | None = None) -> ExportConfig:
    parser = argparse.ArgumentParser(
        description=(
            "Export typed PPOC Parquet resources" if artifact_type == "parquet"
            else "Build a materialized typed PPOC DuckDB"
        )
    )
    parser.add_argument("--descriptor", type=Path, default=DEFAULT_DESCRIPTOR)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args(argv)
    data_root = args.data_root
    if data_root is None:
        value = os.environ.get("PPOC_DATA_ROOT")
        if not value:
            parser.error("--data-root is required when PPOC_DATA_ROOT is unset")
        data_root = Path(value)
    return ExportConfig(args.descriptor, data_root, args.output, args.replace)


def cli_main(artifact_type: str, argv: Sequence[str] | None = None) -> int:
    try:
        config = parse_args(artifact_type, argv)
        output = (
            export_parquet_bundle(config)
            if artifact_type == "parquet"
            else export_duckdb_bundle(config)
        )
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        total_rows = sum(item["rowCount"] for item in manifest["sources"])
        print(
            f"artifact={manifest['artifactType']} output={output} "
            f"snapshot={manifest['package']['snapshot']} resources=8 "
            f"rows={total_rows} status={manifest['status']}"
        )
        return 0
    except ExportError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception:
        print("analytical export failed", file=sys.stderr)
        return 1
```

Reject unknown `artifact_type` values internally before parser creation. Let
`argparse` own status 2. Success may print the explicitly requested output path;
no failure prints source or output absolute paths.

- [ ] **Step 4: Add thin executable scripts**

Create `scripts/export_parquet.py`:

```python
#!/usr/bin/env python3
from typed_export import cli_main

if __name__ == "__main__":
    raise SystemExit(cli_main("parquet"))
```

Create `scripts/build_duckdb.py` with the same shape and
`cli_main("duckdb")`. Set both executable bits. Keep all behavior in the shared
module.

- [ ] **Step 5: Run CLI and format integration tests**

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q \
  tests/test_analytical_export_cli.py \
  tests/test_export_parquet.py \
  tests/test_build_duckdb.py \
  tests/test_typed_export.py
```

Expected: all focused tests pass.

- [ ] **Step 6: Update repository-level documentation**

In `README.md`, add both scripts to `Contents`, add an `Analytical exports`
section after descriptor regeneration, and state explicitly:

> CSV plus `datapackage.json` remains the canonical package. Parquet and DuckDB
> outputs are derived restricted-data artifacts subject to the same IRB, Data
> Use Agreement, training, and information-security controls; the scripts
> refuse to write them inside this repository.

Include copy-ready commands using `/secure/ppoc-csv`, `/secure/ppoc-parquet`,
and `/secure/ppoc-duckdb`, and link to
`schema/README.md`. Do not include real source paths or rows.

- [ ] **Step 7: Add complete operator and consumer documentation**

Append to `schema/README.md`:

- exact common options and `PPOC_DATA_ROOT` precedence;
- Parquet and DuckDB bundle inventories;
- descriptor strictness, source hashes, modes, non-overwrite default,
  recoverable `--replace`, and stale partial/backup handling;
- the canonical/derived and restricted-data boundaries;
- manifest fields and per-artifact hash semantics;
- optional real-data smoke guidance that requires an approved secure output
  root and does not place artifacts in `/tmp` or the checkout.

Include these consumption examples:

```sh
duckdb -readonly /secure/ppoc-duckdb/ppoc.duckdb \
  -c 'SELECT count(*) FROM visits;'

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

- [ ] **Step 8: Run docs, CLI, lint, schema, and whitespace checks**

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q \
  tests/test_analytical_export_cli.py \
  tests/test_export_parquet.py \
  tests/test_build_duckdb.py \
  tests/test_typed_export.py \
  tests/test_datapackage_metadata.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check \
  scripts/typed_export.py \
  scripts/export_parquet.py \
  scripts/build_duckdb.py \
  tests/analytical_export_fixtures.py \
  tests/test_typed_export.py \
  tests/test_export_parquet.py \
  tests/test_build_duckdb.py \
  tests/test_analytical_export_cli.py
python3 schema/build.py --check
git diff --check
```

- [ ] **Step 9: Commit CLI and documentation**

```sh
git add \
  scripts/typed_export.py \
  scripts/export_parquet.py \
  scripts/build_duckdb.py \
  tests/test_analytical_export_cli.py \
  README.md \
  schema/README.md
git commit -m "docs: add typed analytical export workflows"
```

### Task 8: Run complete verification and final review

**Files:**
- Review: all files changed since the design commit.
- Modify: only files requiring fixes discovered by verification/review.

**Interfaces:**
- Consumes: the complete implementation and approved spec.
- Produces: verified implementation evidence and a clean, scoped branch ready for integration.

- [ ] **Step 1: Run all focused exporter tests from a clean process**

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q \
  tests/test_typed_export.py \
  tests/test_export_parquet.py \
  tests/test_build_duckdb.py \
  tests/test_analytical_export_cli.py
```

Expected: all focused tests pass with no skips related to core behavior.

- [ ] **Step 2: Run the complete repository suite and static checks**

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src scripts tests
python3 schema/build.py --check
git diff --check
```

Record exact pass counts and any unrelated baseline failure separately; do not
describe an interrupted or failing full suite as passing.

- [ ] **Step 3: Run two-destination synthetic CLI smokes**

Run the dedicated subprocess smoke created in Task 7. It generates one tiny
snapshot under pytest's external temporary directory, invokes each CLI to two
fresh destinations, verifies both manifests against their own artifact bytes,
compares source hashes, schemas, row counts, typed rows, constraints, and
relationship results, and confirms that binary DuckDB hash equality is not
required.

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q \
  tests/test_analytical_export_cli.py::test_two_destination_cli_smoke
```

- [ ] **Step 4: Perform a spec-to-diff review**

Review `git diff f982487...HEAD` against every acceptance criterion.
Confirm exact file inventories, source immutability, output path guards,
permissions, type mapping, lab decoding, all aggregate validations, no physical
PK/FK/indexes, metadata tables, manifest redaction, replacement restoration,
documentation, and no real-data fixture/path. Search changed files for
`patient_id` values other than fictional `SYN-*`, absolute user paths, raw
DuckDB exception interpolation, SQL logging, `PPOC_DATA_ROOT` access in tests,
and generated `.parquet`/`.duckdb` files.

- [ ] **Step 5: Fix review findings test-first and commit only if needed**

For each substantive finding, add or strengthen a focused failing regression
test, run it to observe failure, make the smallest implementation correction,
rerun focused/full checks, and commit only the affected files:

```sh
git add \
  scripts/typed_export.py \
  scripts/export_parquet.py \
  scripts/build_duckdb.py \
  tests/analytical_export_fixtures.py \
  tests/test_typed_export.py \
  tests/test_export_parquet.py \
  tests/test_build_duckdb.py \
  tests/test_analytical_export_cli.py \
  README.md \
  schema/README.md
git commit -m "fix: harden analytical export boundary"
```

Do not create an empty commit when no fixes are needed.

- [ ] **Step 6: Optionally verify the governed real snapshot**

Only when `PPOC_DATA_ROOT` and an explicitly approved secure output root are
available, run each exporter once to fresh external bundle directories. Do not
use `/tmp`, the repository, or an inferred destination for real data. Verify
all eight counts, `PASS` manifests, output hashes, PyArrow readability, and a
read-only DuckDB reopen. Do not delete or publish those artifacts without a
separate explicit instruction.

If real data or an approved secure output root is unavailable, report this
step as not run; synthetic acceptance remains the automated implementation
gate.

- [ ] **Step 7: Inspect final Git scope**

```sh
git status --short --branch
git diff f982487...HEAD --name-status
git log --oneline f982487..HEAD
```

Expected: only the planned scripts, tests, and documentation are changed; no
generated analytical artifacts or unrelated user files are staged/untracked.
