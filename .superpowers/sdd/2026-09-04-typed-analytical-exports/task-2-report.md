# Task 2 report: source preflight, fingerprinting, and typed CSV ingestion

## Scope

Implemented Task 2 in `scripts/typed_export.py` and `tests/test_typed_export.py`. The Task 1 descriptor contract models and fail-closed descriptor validation remain unchanged.

## Implemented interfaces

- Added immutable `SourceState` and `SourceFingerprint` models.
- Added `preflight_sources`, which resolves the supplied data root, validates all eight descriptor CSV sources with `lstat`, reads headers using the descriptor encoding and dialect, checks exact field order, collects all resource failures, and emits only resource names in errors.
- Added `fingerprint_sources`, including one 1 MiB-block SHA-256 pass per source, source basenames, row counts, and field counts.
- Added `verify_sources_unchanged`, comparing device, inode, size, and nanosecond mtime and rejecting missing, symlinked, or non-regular sources.
- Added `quote_identifier` and `quote_literal`.
- Added `typed_csv_query`, which declares every CSV column as `VARCHAR`, then applies explicit redacted integer and finite `DOUBLE` conversions. Empty strings become `NULL`; nonempty strings are preserved.
- Added `_redacted_duckdb_error` for allow-listed conversion tokens with a fallback that never exposes raw DuckDB exception text.

Labs are decoded strictly as ISO-8859-1 before DuckDB execution. DuckDB 1.5.5 rejects C1 bytes such as ISO-8859-1 `0x81` under its `latin-1` reader, so the query path uses an ephemeral UTF-8 projection after strict Python decoding; descriptor source files are never modified.

## Tests

Focused tests:

```text
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_typed_export.py
49 passed
```

Lint and whitespace checks:

```text
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check scripts/typed_export.py tests/analytical_export_fixtures.py tests/test_typed_export.py
All checks passed!
git diff --check
```

Repository-wide suite:

```text
3387 passed, 8 skipped, 7 failed
```

The seven failures are pre-existing, unrelated baseline failures in synthetic ancillary README/pathway-link tests and the Synthea overlay digest test. They do not involve the Task 2 implementation or tests.

## Review notes

- Automated fixtures remain tiny synthetic snapshots only.
- Source CSVs are read without rewriting or modifying them.
- Header, encoding, file-type, conversion, quoting, fingerprint, metadata, and mutation boundaries are covered.
- No unrelated files were changed.

## Round 1 review fix

### Findings addressed

1. `preflight_sources` now counts data records while reading each already-required CSV header and rejects a resource when the actual count differs from the descriptor `row_count`. The error remains resource-level and redacted. The existing one-pass 1 MiB-block SHA-256 implementation is unchanged.
2. Added a regression test that truncates and appends a source and a stronger multi-source failure test. The latter corrupts two independent resources, asserts both resource names are reported, records file-open modes to prove no binary hash read occurs on failed preflight, then restores the synthetic files and proves binary reads occur only after successful preflight.

### TDD evidence

The new row-count tests were run before the production change:

```text
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_typed_export.py -k "row_count or preflight_collects_multiple"
2 failed, 1 passed, 49 deselected
```

After the fix:

```text
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_typed_export.py -k "row_count or preflight_collects_multiple"
3 passed, 49 deselected

UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_typed_export.py
52 passed in 0.47s

UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check scripts/typed_export.py tests/analytical_export_fixtures.py tests/test_typed_export.py
All checks passed!

git diff --check
```
