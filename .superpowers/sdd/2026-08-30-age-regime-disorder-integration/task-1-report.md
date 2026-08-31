# Task 1 report: age-regime state sampling and replay

## Files changed

- `src/synthetic/native/age_regimes.py`: added public `sample_state`, keyword-only state replay, and replay-state validation. Ordinary generation retains the existing stream names, distributions, point construction, physical guards, and continuity checks.
- `tests/synthetic/test_age_regime_kernel.py`: added replay and invalid-state tests.

## Verification

- `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_age_regime_kernel.py -k replay` — 2 passed.
- `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_age_regime_kernel.py` — 24 passed.
- `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic` — 180 passed.
- `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/native/age_regimes.py tests/synthetic/test_age_regime_kernel.py` — All checks passed.
- `git diff --check` — passed.

## Concerns

None. Replay is an evaluator-only API on the native kernel and does not alter visible generation paths.

## Fix-round evidence

- Restored the ordinary generator lifecycle by retaining the original head generator from state sampling; replay consumes the corresponding latent head draw before point construction.
- Added `test_ordinary_generation_preserves_head_circumference_stream` with the established seed-5 head values.
- `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_age_regime_kernel.py` — 25 passed.
- `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic` — 181 passed.
- `UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/native/age_regimes.py tests/synthetic/test_age_regime_kernel.py` — All checks passed.
