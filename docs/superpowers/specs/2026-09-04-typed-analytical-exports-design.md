# Typed Parquet and DuckDB Analytical Exports

**Date:** 2026-09-04
**Status:** Design approved; implementation pending
**Authority:** The checked-in Frictionless `datapackage.json` and the eight CSV resources it describes

## Purpose

Add two repository scripts that convert an authorized PPOC CSV snapshot into
typed analytical artifacts without changing the canonical CSV package:

1. a Parquet bundle containing one Zstandard-compressed Parquet file per
   resource; and
2. a self-contained DuckDB bundle containing materialized copies of all eight
   typed resources.

Both exporters ingest the CSVs directly and share one descriptor-driven
conversion, validation, provenance, and output-lifecycle implementation. The
artifacts remain restricted real-data derivatives governed by the same IRB,
Data Use Agreement, training, and information-security controls as the source
snapshot.

## Goals

- Preserve the checked-in descriptor as the schema, relationship, missingness,
  encoding, and snapshot authority.
- Materialize `string` fields as `VARCHAR`, `integer` fields as `BIGINT`, and
  `number` fields as `DOUBLE`, with declared empty strings represented as
  `NULL`.
- Refuse stale or nonconforming source snapshots rather than infer or repair
  their schema.
- Produce strongly attributable artifacts with content hashes, aggregate
  validation evidence, tool versions, and exporter provenance.
- Keep the Parquet and DuckDB commands independently runnable while ensuring
  that they cannot drift in conversion behavior.
- Keep all generated real-data artifacts outside the Git checkout and use
  restrictive filesystem permissions.
- Test the complete export behavior with tiny synthetic CSV fixtures; never
  require or copy real data in automated tests.

## Non-goals

- Replacing the canonical CSV/Frictionless package.
- Partitioning Parquet datasets or producing more than one Parquet file per
  resource.
- Adding analytical views, indexes, aggregates, denormalized joins, or derived
  clinical variables.
- Inferring a schema, changing the descriptor's type semantics, or deriving
  `DECIMAL` types from descriptive rounding metadata.
- Repairing source encodings, trimming cells, changing values, or performing
  best-effort coercion.
- Declaring physical DuckDB primary-key or foreign-key constraints and their
  supporting indexes.
- Treating `x-logicalForeignKeys` as complete referential constraints.
- Supporting a mutable multi-writer or server database.
- Deleting, rewriting, or moving any source CSV.
- Adding a separate post-hoc manifest-verification command in this slice.

## Repository changes

Create:

- `scripts/typed_export.py`: shared export library and command helpers.
- `scripts/export_parquet.py`: thin Parquet command-line entry point.
- `scripts/build_duckdb.py`: thin DuckDB command-line entry point.
- `tests/test_typed_export.py`: shared contract, validation, safety, and
  lifecycle tests.
- `tests/test_export_parquet.py`: Parquet bundle integration tests.
- `tests/test_build_duckdb.py`: DuckDB bundle integration tests.
- `tests/test_analytical_export_cli.py`: subprocess-level CLI tests.

Modify:

- `README.md`: identify both analytical export commands and their restricted
  derivative status.
- `schema/README.md`: document complete commands, artifact layouts, provenance,
  replacement behavior, and read-only consumption examples.

The existing `duckdb`, `pyarrow`, and test dependencies in `pyproject.toml`
cover this work. No dependency change is expected.

## Command-line interfaces

The commands are:

```sh
uv run python scripts/export_parquet.py \
  --data-root /secure/ppoc-csv \
  --output /secure/ppoc-parquet

uv run python scripts/build_duckdb.py \
  --data-root /secure/ppoc-csv \
  --output /secure/ppoc-duckdb
```

Both commands accept the same arguments:

- `--descriptor PATH`: optional; defaults to the repository's checked-in
  `datapackage.json`.
- `--data-root PATH`: optional only when `PPOC_DATA_ROOT` is set. An explicit
  argument takes precedence over the environment variable.
- `--output PATH`: required. It names the bundle directory, not an individual
  output file.
- `--replace`: optional. Without it, an existing destination is an error.

There is no output default. Both commands reject an output that resolves to the
repository root or any descendant of it. They are noninteractive and return
zero only after the promoted bundle has passed final verification. Argument
errors return status 2; source, conversion, validation, or lifecycle failures
return status 1.

On success, stdout reports the artifact kind, destination, snapshot label,
resource count, total row count, and manifest status. It does not print source
paths or data values.

## Shared component boundaries

`scripts/typed_export.py` owns all behavior that must remain identical between
the two formats:

- immutable configuration and parsed descriptor models;
- path resolution and restricted-output checks;
- descriptor, source-file, dialect, encoding, and header preflight;
- SHA-256 hashing and stable-source checks;
- quoted SQL identifier and literal construction;
- descriptor-to-DuckDB type and constraint generation;
- typed CSV projection generation;
- aggregate constraint, row-count, key, and relationship validation;
- redacted exporter errors and validation records;
- manifest construction and canonical JSON serialization;
- private staging, collision handling, recoverable replacement, and promotion;
- `export_parquet_bundle(...)`; and
- `export_duckdb_bundle(...)`.

The two executable scripts parse their format-specific program name and call
the corresponding shared function. They contain no type mapping, validation,
hashing, or filesystem lifecycle logic.

The implementation may use private dataclasses such as `ExportConfig`,
`PackageContract`, `ResourceContract`, `FieldContract`, `SourceFingerprint`,
and `ValidationRecord`. The stable library-level entry points are:

```python
def export_parquet_bundle(config: ExportConfig) -> Path: ...

def export_duckdb_bundle(config: ExportConfig) -> Path: ...
```

Both return the promoted bundle directory. No API accepts row mappings or
in-memory clinical data.

## Descriptor contract

The selected descriptor must be a JSON object that defines exactly these eight
resources, in this order:

1. `patients`
2. `patients_augmented`
3. `visits`
4. `visits_augmented`
5. `labs`
6. `medications`
7. `problem_list`
8. `referrals`

For every resource, the exporter requires:

- a unique safe resource name;
- a unique, relative, single-component `.csv` path with no traversal;
- `format: csv`, a supported declared encoding, and the checked-in CSV dialect
  shape (`header`, `delimiter`, `quoteChar`, and `doubleQuote`);
- `schema.missingValues` equal to `[""]`;
- a nonempty ordered field list with unique names;
- field types limited to `string`, `integer`, and `number`;
- field constraints limited to `required`, `enum`, `minimum`, and `maximum`;
- a nonnegative integer `x-rowCount`;
- scalar primary keys when present;
- scalar, internally resolvable `foreignKeys`; and
- well-formed scalar `x-logicalForeignKeys` with nonnegative declared
  `orphanRows` and, when present, `nullRows`.

Unknown field types, constraint keywords, unsafe paths, duplicate names,
malformed keys, missing row counts, and unsupported dialect or encoding values
fail before staging begins. The descriptor's
`x-statisticsSource.snapshot` is the artifact snapshot label; the CLI does not
accept a second snapshot label.

An alternate `--descriptor` remains subject to the same exact eight-resource
PPOC contract. Its own fields, constraints, relationships, and row counts are
authoritative for that invocation.

## Source preflight and provenance

The data root must resolve to an existing directory. Each descriptor-named CSV
must exist as a regular file and must not itself be a symbolic link. Before any
output is created, the exporter checks all eight files, not one resource at a
time, so a late missing or unsafe source cannot leave a partial artifact.

For each source, preflight records device, inode, size, and nanosecond
modification time; reads only the header with the declared encoding and CSV
dialect; and requires exact field names and order. The exporter then computes
one streaming SHA-256 pass over every original CSV. After conversion and
validation, it repeats the file-stat check. Any changed identity, size, or
modification time fails the run. This design assumes the governed source
snapshot is immutable during a run; it does not add a second full hash pass.

Manifest provenance uses only resource names and source basenames. Absolute
source paths are neither persisted nor printed in validation failures.

## CSV decoding and typed projection

DuckDB's Python API reads every source field initially as text with explicit
descriptor field names, order, dialect, and encoding. Automatic schema
inference is disabled.

The conversion mapping is fixed:

| Frictionless type | DuckDB type | Parquet logical/physical result |
| --- | --- | --- |
| `string` | `VARCHAR` | Arrow string |
| `integer` | `BIGINT` | signed 64-bit integer |
| `number` | `DOUBLE` | IEEE 754 double |

For all types, a source `NULL` or declared empty string maps to SQL `NULL`.
Nonempty strings are preserved exactly after descriptor-directed decoding;
there is no trimming, normalization, category rewriting, or Unicode repair.

Nonempty integers must match an optional sign followed by one or more decimal
digits and must fit in `BIGINT`. Values such as `1.0`, `1e3`, or an overflowing
integer fail rather than round or coerce. Nonempty numbers must cast to
`DOUBLE` and be finite; `NaN`, positive or negative infinity, and overflow
fail. Conversion failures identify only the resource, field, and rule.

`labs.csv` is decoded exactly as its descriptor declares: ISO-8859-1 bytes are
mapped deterministically to Unicode code points and then stored as ordinary
UTF-8-compatible strings in DuckDB/Parquet. The exporter does not reuse the
profiler's CP1252 substitution, detect embedded UTF-8 sequences, or repair
mojibake. The source SHA-256 retains byte-level provenance.

The generated SQL must quote every descriptor-derived identifier and bind or
safely quote every path/literal. Raw cell values never become SQL fragments,
error messages, logs, metadata, or manifest fields.

## Validation contract

Both exporters perform the same validations against the typed generated
artifact rather than repeatedly rescanning CSV text:

1. each resource row count equals `x-rowCount`;
2. every required field is nonnull;
3. every nonnull constrained field satisfies its `enum`, `minimum`, and
   `maximum` constraints;
4. every declared primary key is nonnull and unique;
5. every declared `foreignKeys` value matches its referenced resource;
6. every logical relationship reproduces its declared nonnull orphan count and
   its declared null count, with an omitted `nullRows` interpreted as zero; and
7. all eight output schemas preserve descriptor names, order, and mapped types.

Validation queries return aggregate counts only. A failure record contains the
resource, optional field, rule name, expected aggregate, and observed aggregate.
It never contains an offending row, source cell, patient ID, visit ID, or SQL
query. All failures prevent promotion.

DuckDB tables physically retain mapped types, `NOT NULL` for required fields,
and applicable `CHECK` constraints for enums and numeric bounds. Primary and
foreign keys are exhaustively validated but are not declared in table DDL, so
the artifact does not create their supporting indexes. Logical foreign keys
remain metadata only.

## Parquet export pipeline

The Parquet exporter creates a private sibling staging directory and a private
DuckDB working connection whose spill directory is inside staging. For each
resource, it performs one typed CSV scan and writes
`<resource-name>.parquet` with Zstandard compression and DuckDB's default row
group sizing. It does not partition, sort, or reorder rows.

After all eight files exist, DuckDB validates rows, constraints, keys, and
relationships by querying the staged Parquet files. PyArrow then independently
opens every file and verifies:

- exact column names and order;
- expected Arrow types;
- readable metadata and row count; and
- Zstandard compression for every populated column chunk.

The exporter copies the selected descriptor bytes unchanged to
`source-datapackage.json`, hashes all staged deliverables, writes the manifest,
and verifies the exact allowed bundle inventory before promotion.

The final Parquet bundle contains exactly:

```text
<output>/
├── patients.parquet
├── patients_augmented.parquet
├── visits.parquet
├── visits_augmented.parquet
├── labs.parquet
├── medications.parquet
├── problem_list.parquet
├── referrals.parquet
├── source-datapackage.json
└── manifest.json
```

## DuckDB export pipeline

The DuckDB exporter creates `<staging>/ppoc.duckdb`, connects through the
DuckDB Python API, and creates the `main` resource tables from explicit DDL.
Each table is populated by one typed projection directly from its source CSV.
The exporter creates resources in descriptor order, performs all same-resource
and cross-resource validations, and only then creates metadata tables.

`main` contains exactly the eight materialized resource tables. No views,
indexes, sequences, macros, or extra user tables are created.

The `ppoc_meta` schema contains exactly:

- `build`: one row with manifest version, package name/version, snapshot,
  creation time, descriptor hash, Python/DuckDB/PyArrow versions, exporter Git
  revision when available, dirty-worktree state when available, and the
  running shared-module SHA-256;
- `resources`: one row per resource with source basename, source byte size,
  source SHA-256, row count, table name, and field count;
- `descriptor`: one row with the descriptor SHA-256 and complete descriptor
  JSON stored as `VARCHAR`; and
- `validations`: one row per aggregate validation with resource, nullable field,
  rule, expected JSON, observed JSON, and `PASS` status.

No metadata table includes the database's own final hash because adding that
value would change the file being hashed.

The exporter checkpoints and closes the database, sets the required file mode,
reopens it read-only, and verifies the exact schemas, types, constraints,
counts, metadata inventory, and validation status. It then closes the database,
computes its SHA-256, writes the sidecar manifest, and verifies the exact bundle
inventory.

The final DuckDB bundle contains exactly:

```text
<output>/
├── ppoc.duckdb
└── manifest.json
```

## Manifest contract

Both formats write `manifest.json` as UTF-8, two-space-indented, sorted-key JSON
with LF line endings and a final newline. Resource/output arrays retain
descriptor order. The manifest itself is excluded from its own output-hash
list.

The top-level shape is:

```json
{
  "manifestVersion": 1,
  "status": "PASS",
  "artifactType": "parquet-bundle",
  "package": {},
  "build": {},
  "descriptor": {},
  "sources": [],
  "outputs": [],
  "validation": {}
}
```

`artifactType` is `parquet-bundle` or `duckdb-bundle`. Required content is:

- `package`: descriptor package name, version, and authoritative snapshot;
- `build`: UTC creation time, Python/DuckDB/PyArrow versions, Zstandard for
  Parquet, exporter Git revision and dirty state when available, and the
  running shared-module SHA-256;
- `descriptor`: basename, byte size, and SHA-256;
- `sources`: resource name, source basename, source byte size, source SHA-256,
  validated row count, and field count;
- `outputs`: basename, byte size, SHA-256, row count, field count, and ordered
  column name/type pairs for each Parquet file; the DuckDB entry records the
  database file and its eight resource-table counts;
- `validation`: `PASS`, total check count, and zero failed checks.

The Parquet manifest hashes all eight Parquet files and the byte-identical
`source-datapackage.json`. The DuckDB manifest hashes `ppoc.duckdb`. Generated
timestamps and physical database layout may differ across runs. Every manifest
hash must match its own artifact bytes; given unchanged sources and descriptor,
the typed rows, schemas, counts, constraints, relationships, and source
fingerprints must agree across two fresh destinations. Cross-run equality of
the binary DuckDB or Parquet file hashes is not a contract.

## Restricted-data and path safeguards

The exporter resolves the repository root and output parent before creating
anything. It rejects an output equal to or below the repository root, including
paths that enter the checkout through symbolic links. Existing destination
symlinks and special files are always errors. It also rejects an output that is
equal to or an ancestor of the selected descriptor, data root, or any source
CSV, so replacement can never move or remove an input.

New staging and bundle directories use mode `0700`; generated database,
Parquet, descriptor-copy, and manifest files use mode `0600`. The exporter
applies these modes explicitly rather than relying only on the caller's umask.

The exporter persists no absolute paths. Public errors and validation records
may name a resource and field but never include cell values or identifiers.
DuckDB exceptions and SQL text are caught internally and replaced with fixed,
redacted exporter errors. Temporary names contain only artifact kind and a
random token.

The source directory and CSVs are never opened for writing. No source content
is copied except into the requested analytical artifacts and the descriptor
copy in the Parquet bundle.

## Staging, promotion, and replacement

All work occurs in a uniquely named private sibling directory on the
destination filesystem. The exporter preflights every source and destination
condition before creating staging. A failed run closes DuckDB connections and
removes only the staging directory it created; it never removes a source or an
existing destination.

For a destination that does not exist, the validated staging directory is
renamed once to the requested output path. The rename provides atomic initial
publication on a local filesystem.

Portable filesystems cannot atomically replace an existing nonempty directory.
With `--replace`, the exporter therefore performs a recoverable swap:

1. require the existing directory to contain a valid exporter manifest whose
   artifact type matches the requested command and whose inventory contains no
   unexpected entries;
2. finish and validate the new staging bundle;
3. rename the existing target to a unique sibling backup;
4. rename staging to the requested target;
5. re-open and revalidate the promoted manifest and artifact; and
6. remove the backup only after successful final verification.

If a caught failure occurs after step 3, the exporter restores the backup when
safe. A process or machine crash may leave a staging or backup directory. The
next invocation does not delete or infer intent from either one; it fails with
a basename-only recovery instruction. Recovery and cleanup of ambiguous crash
artifacts remain explicit operator actions.

## Error model

The shared library raises one public exporter exception hierarchy with
format-specific subclasses where useful. Errors fall into descriptor,
preflight, conversion, validation, output-collision, unsafe-path, and lifecycle
categories. Messages are deterministic and redacted.

Examples of permitted messages are:

- `labs.result_line_num failed integer conversion`
- `visits row count did not match the descriptor`
- `referrals.visit_id logical orphan count did not match the descriptor`
- `output already exists; rerun with --replace`

Messages must not include an offending value, row number tied to clinical data,
patient/visit identifier, generated SQL, or absolute source path. The CLI may
print the explicitly requested output destination after success.

## Testing strategy

Automated tests construct a temporary descriptor with the same eight resource
names and a tiny internally consistent snapshot. Test helpers generate all
field headers and valid cells from the descriptor contract, then override
specific values to exercise failures. No fixture contains real PPOC data, and
no automated test reads `PPOC_DATA_ROOT` unless a test explicitly controls that
environment variable with a temporary directory.

Shared tests cover:

- exact eight-resource descriptor parsing and rejection of unknown shapes;
- safe paths, output-outside-repository enforcement, regular-file checks, and
  all-resources-first preflight;
- exact headers and field order;
- all type mappings, empty-to-null semantics, integer lexical rules, finite
  doubles, required values, enums, and numeric bounds;
- strict ISO-8859-1 lab decoding without substitution;
- source hashing and source-change detection;
- primary-key uniqueness, strict foreign keys, and logical relationship counts;
- error redaction and absence of source paths or row values;
- secure modes and exact output inventories;
- collision refusal, recognized replacement, restoration on injected failure,
  and stale staging/backup refusal; and
- canonical manifest serialization and hash verification.

Parquet integration tests cover:

- all eight files, descriptor copy, and manifest;
- exact Arrow schemas, values, nulls, row counts, and field order;
- Zstandard compression for populated column chunks;
- independent PyArrow reads;
- semantic equality across fresh runs and verification that each manifest hash
  matches its own staged artifact; and
- corruption or schema mismatch preventing promotion.

DuckDB integration tests cover:

- exactly eight `main` tables and four `ppoc_meta` tables;
- mapped column types and order;
- physical `NOT NULL` and `CHECK` constraints;
- no physical primary/foreign-key declarations or indexes;
- complete metadata and validation rows;
- successful read-only reopen;
- final database hash in the sidecar manifest; and
- semantic determinism of resource rows and source fingerprints across fresh
  runs.

CLI tests run both scripts in subprocesses and cover `--help`, descriptor
override, explicit data root, `PPOC_DATA_ROOT` fallback and precedence, required
output, `--replace`, exit statuses, stdout summary, and stderr redaction.

Implementation verification is:

```sh
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q \
  tests/test_typed_export.py \
  tests/test_export_parquet.py \
  tests/test_build_duckdb.py \
  tests/test_analytical_export_cli.py
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check scripts tests
python3 schema/build.py --check
git diff --check
```

Documentation also gives opt-in commands for a real-data end-to-end run against
`PPOC_DATA_ROOT`. Real-data execution is additional local evidence, not a CI
requirement. Its success criteria are eight matching resource counts, all
validation records passing, verified output hashes, successful PyArrow reads,
and successful read-only DuckDB reopen.

## Documentation requirements

`README.md` adds both scripts to the repository contents and explains that CSV
plus `datapackage.json` remains canonical. It states that Parquet and DuckDB are
derived restricted analytical products, not de-identification or release
artifacts.

`schema/README.md` documents:

- both complete commands and all options;
- source descriptor and `PPOC_DATA_ROOT` resolution;
- output-outside-checkout and restrictive-permission behavior;
- both exact bundle inventories;
- `--replace` and crash-recovery semantics;
- manifest fields and hash expectations;
- a DuckDB CLI query and a Python read-only connection example;
- a DuckDB query over one generated Parquet file; and
- the optional real-data smoke and aggregate checks.

Documentation never includes or suggests committing generated paths, source
paths, identifiers, or sample real rows.

## Acceptance criteria

The feature is complete when:

1. both commands independently ingest the same descriptor-governed CSV snapshot
   and produce the exact approved bundle inventories outside the repository;
2. all fields have the approved `VARCHAR`/`BIGINT`/`DOUBLE` mapping, exact order,
   and empty-to-null semantics without inference or repair;
3. every descriptor row count, field constraint, primary key, strict foreign
   key, and logical relationship statistic is validated before promotion;
4. all Parquet resources use Zstandard and independently pass PyArrow schema,
   count, and readability checks;
5. `ppoc.duckdb` contains all eight materialized typed resources plus only the
   approved `ppoc_meta` tables, reopens read-only, and has no physical PK/FK
   declarations or indexes;
6. manifests provide the approved strong source/output provenance without
   absolute paths or data values;
7. new artifacts and staging use modes `0700`/`0600`, outputs inside the Git
   checkout are rejected, and failures disclose no clinical values;
8. initial promotion is atomic and replacement is recoverable without deleting
   a prior valid artifact before the new artifact is validated;
9. focused tests, the complete suite, Ruff, descriptor freshness, and diff
   checks pass; and
10. documentation presents copy-ready commands and preserves the canonical
    CSV/Frictionless and restricted-data governance boundaries.
