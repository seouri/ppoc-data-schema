# Task 3 report: deterministic age-regime physiology

## Files changed

- `src/synthetic/native/age_regimes.py`: added the evaluator-only `AgeRegimeTrajectoryKernel`, strict age/reference-domain checks, isolated regime-stream sampling, infant/transition and post-transition two-dimension paths, exact smooth-step puberty offsets, optional post-transition head circumference, comparable-size and weight velocities, physical-value guards, and a local transition-continuity check.
- `tests/synthetic/fakes.py`: added the required test-only `RegimeLinearTestReference`; production code does not import it.
- `tests/synthetic/test_age_regime_kernel.py`: added regime, identity, conversion, puberty, determinism, stream-isolation, age/domain, nonphysical-value, velocity, and transition-discontinuity coverage.
- `.superpowers/sdd/2026-08-30-growth-age-regimes/task-3-report.md`: recorded this implementation and verification evidence.

No exporter, resource mapper, manifest, `HealthyKernel`, `DisorderTrajectoryKernel`, or `generate_smoke` file changed.

## Red phase

Command:

```text
uv run pytest -q tests/synthetic/test_age_regime_kernel.py
```

Result: collection failed as expected because the kernel was not implemented:

```text
ImportError: cannot import name 'AgeRegimeTrajectoryKernel' from 'synthetic.native.age_regimes'
1 error in 0.06s
```

The finite/positive fail-closed test was also extended with an oversized integer reference result. Before hardening numeric conversion, that case failed with `OverflowError`; after the minimal guard change it raises the required `ValueError`.

## Green and regression tests

Commands and exact final results:

```text
uv run pytest -q tests/synthetic/test_age_regime_kernel.py
..................                                                       [100%]
18 passed in 0.08s

uv run pytest -q tests/synthetic
........................................................................ [ 42%]
........................................................................ [ 84%]
...........................                                              [100%]
171 passed in 0.27s
```

## Lint

```text
uv run ruff check src/synthetic/native/age_regimes.py tests/synthetic/test_age_regime_kernel.py tests/synthetic/fakes.py
All checks passed!
```

## Commit

Requested message: `feat: add deterministic age-regime kernel`.

The scoped staging set includes `tests/synthetic/fakes.py` in addition to the files shown in the brief's sample `git add` line.

## Concerns

The continuity guard applies to adjacent points leaving the transition regime when the first post-transition point remains within one additional transition-window duration. This catches the specified 730-to-761 discontinuity without misclassifying the brief's deliberately sparse 730-to-4380 stream-isolation trajectory as a measurement jump. The development defaults remain uncalibrated, all returned state remains evaluator-only, and no visible package path changed.

An attempted verification wrapper using `env PYTHONDONTWRITEBYTECODE=1 uv run ...` could not initialize the user-level uv cache under the managed sandbox. The required commands were rerun directly and produced the successful results above. Only generated `__pycache__` directories were removed afterward.
