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

## Fix round 1

Review found two fail-closed gaps in commit `9d211a9`: the continuity check silently skipped sparse adjacent samples that spanned the full transition window or ended later than an undocumented local cutoff, and extreme finite heights could raise `OverflowError` during derived BMI/weight exponentiation before validation.

Regression tests were added before production changes. The sparse continuity cases reproduced as two missing `ValueError`s:

```text
uv run pytest -q tests/synthetic/test_age_regime_kernel.py -k transition_discontinuity
.FF                                                                      [100%]
2 failed, 1 passed, 17 deselected in 0.08s
```

The transition and post-transition arithmetic cases reproduced as uncontrolled overflow errors:

```text
uv run pytest -q tests/synthetic/test_age_regime_kernel.py -k 'overflow'
FF                                                                       [100%]
2 failed, 20 deselected in 0.07s
```

The continuity guard now detects every adjacent pair satisfying `previous.age_days <= transition_end < current.age_days`, independent of the observation gap. It compares the converted-length and standing-height representations at the common first-post-transition age using the stable childhood height channel, so sparse samples such as `(699, 761)` and `(699, 3000)` cannot bypass validation. Derived BMI and weight now use guarded multiplication/division without exponentiation and pass all results through finite/positive validation, converting arithmetic failures to documented `ValueError`s.

Fresh fix-round verification:

```text
uv run pytest -q tests/synthetic/test_age_regime_kernel.py
......................                                                   [100%]
22 passed in 0.05s

uv run pytest -q tests/synthetic
........................................................................ [ 41%]
........................................................................ [ 82%]
...............................                                          [100%]
175 passed in 0.33s

uv run ruff check src/synthetic/native/age_regimes.py tests/synthetic/test_age_regime_kernel.py tests/synthetic/fakes.py
All checks passed!
```

No API, stream naming, exporter/resource path, plan, or ledger changed in this fix round. The earlier local-gap continuity concern is superseded by the common-age representation check above.
