# Task 2 report: versioned age-regime configuration and classifier

## Files changed

- `src/synthetic/native/age_regimes.py`: added frozen `AgeRegimeConfig` with explicit development-only, uncalibrated defaults and validation for numeric domains, ordering, and cross-field schedule constraints; added `classify_age` with inclusive transition and puberty upper boundaries.
- `tests/synthetic/test_age_regime_config.py`: added the specified boundary, invalid-configuration, and invalid-schedule tests.

## Red phase

Command:

```text
uv run pytest -q tests/synthetic/test_age_regime_config.py
```

Result: collection failed as expected because `synthetic.native.age_regimes` did not yet exist:

```text
ModuleNotFoundError: No module named 'synthetic.native.age_regimes'
```

## Green and regression tests

Commands and results:

```text
uv run pytest -q tests/synthetic/test_age_regime_config.py
11 passed in 0.01s

uv run pytest -q tests/synthetic
153 passed in 0.25s
```

## Lint

```text
uv run ruff check src/synthetic/native/age_regimes.py tests/synthetic/test_age_regime_config.py
All checks passed!
```

## Commit

Recorded below after the final scoped Git checks.

## Concerns

None. Defaults are explicitly documented as development-only and uncalibrated; no prevalence or clinical-evidence claims were added. Existing Task 1 models and other synthetic modules were left unchanged. Generated `__pycache__` directories remain untracked and were not included.
