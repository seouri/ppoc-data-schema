# Task 2 report: development-only integration boundary

## Files changed

- `README.md`: documents the shipped source-matched augmenter as a wholly synthetic development derivation candidate, preserves the production synthetic-generator fail-closed authority statement, and links the import guide.
- `docs/synthetic-generator.md`: distinguishes the native generator's fail-closed production path from the imported candidate and links the import guide.
- `docs/augment-import.md`: adds setup, exact synthetic input requirements, the CSV/Parquet command shape, timestamped output expectations, runtime-manifest SHA-256 verification, and the development-only authority boundary.
- `tests/test_augment_import.py`: adds focused assertions for the guide's required inputs, command, manifest verification, synthetic-only warning, and non-authoritative boundary.

## Verification

- `PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_augment_import.py` — 5 passed.
- `PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check tests/test_augment_import.py` — all checks passed.

## Concerns

None. The guide deliberately does not bind the imported candidate as authoritative or alter the native generator, package exporter, calibration, privacy, counterfactual, Synthea, or release gates. Copied scripts, reference data, manifest bytes, and dependency metadata were not modified.
