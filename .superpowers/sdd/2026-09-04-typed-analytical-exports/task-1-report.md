# Task 1 report: descriptor contract and synthetic fixture

## Implemented

- Added `scripts/typed_export.py` with the approved immutable public contract models:
  `ExportConfig`, `FieldContract`, `RelationshipContract`, `ResourceContract`,
  `PackageContract`, `ExportError`, `DescriptorError`, and `EXPECTED_RESOURCE_NAMES`.
- Implemented `load_package_contract()` as a fail-closed parser for the checked-in
  eight-resource descriptor. It validates resource order and uniqueness, safe single-file
  CSV paths, supported field types and constraints, scalar primary/relationship keys,
  internal relationship targets, encodings, CSV dialect, missing values, row counts,
  logical relationship counts, and the required statistics snapshot.
- Descriptor loading rejects symlinks and non-regular files, parses UTF-8 JSON, records
  descriptor bytes and SHA-256, and uses redacted generic errors without echoing
  descriptor values.
- Added `tests/analytical_export_fixtures.py` with the immutable `TinySnapshot` return
  type, deterministic two-patient/two-visit synthetic rows, one-row ancillary resources,
  matching augmented identifiers, zero logical orphans, declared CSV field order/dialects,
  ISO-8859-1 labs output, and both cell mutation helpers.
- Added `tests/test_typed_export.py` covering the positive contract, immutability, the
  requested malformed-descriptor matrix, relationship target validation, redacted errors,
  and exact fixture shape/encoding.

## TDD and verification

1. Wrote the fixture and contract tests first.
2. Confirmed the initial focused run failed during collection because
   `scripts.typed_export` did not exist.
3. Implemented the minimal contract layer and iterated against focused failures.
4. Final focused verification:

   ```text
   UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_typed_export.py
   23 passed in 0.18s

   UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check scripts/typed_export.py tests/analytical_export_fixtures.py tests/test_typed_export.py
   All checks passed!

   git diff --check
   passed
   ```

5. Full repository verification:

   ```text
   UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q
   3361 passed, 8 skipped, 7 failed in 227.07s
   ```

   The seven failures are pre-existing unrelated synthetic documentation/overlay tests:
   six README roadmap-link assertions and one Synthea overlay digest assertion. None
   reference the three Task 1 files. The eight skips are the repository's existing
   opt-in scale/Synthea tests.

## Scope review

Only the three requested source/test files are intended for the Task 1 commit. Test
execution regenerated unrelated tracked Python bytecode cache files; these are excluded
from staging and are not part of the implementation.

## Round 1 review fixes

Review findings were reproduced with focused tests before implementation:

- `PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_typed_export.py -k 'non_finite or extra_dialect or deeply_immutable'`
  initially reported `8 failed, 23 deselected`; the parser accepted all six non-finite
  values, the extra dialect key, and mutable descriptor content.

Implemented fixes:

- `_number()` rejects float NaN and positive/negative infinity before constructing a field
  contract.
- Resource dialect validation requires the exact approved key set
  (`header`, `delimiter`, `quoteChar`, `doubleQuote`) and the existing exact semantics.
- `PackageContract.descriptor` is recursively frozen at load time: mappings become
  read-only mapping proxies and arrays become tuples, preventing top-level or nested
  mutation while retaining the captured descriptor bytes and digest.
- Added focused regression coverage for all three review findings.

Final round-1 verification:

```text
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_typed_export.py -k 'non_finite or extra_dialect or deeply_immutable'
8 passed, 23 deselected in 0.07s

PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_typed_export.py
31 passed in 0.22s

PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check scripts/typed_export.py tests/analytical_export_fixtures.py tests/test_typed_export.py
All checks passed!

git diff --check
passed
```
