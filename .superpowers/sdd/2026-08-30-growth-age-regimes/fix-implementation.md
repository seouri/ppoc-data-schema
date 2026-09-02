# Age-regime adversarial fix implementation

## Scope

Implemented the adversarial fixes requested against main commit `434cfda` on the isolated branch `codex/age-regimes-adversarial-fixes`.

The changes cover oversized numeric inputs, optional head-circumference availability, late transition discontinuities, malformed reference-domain metadata, standalone classifier bounds, reference arithmetic/type failures, and the infancy two-dimension contract.

## Implementation

- `src/synthetic/models.py` now normalizes `math.isfinite` conversion failures for state and point numeric fields to the existing `ValueError` model contract. `AgeRegimePoint` rejects any standing `height_cm` or `bmi` on `INFANCY`.
- `src/synthetic/native/age_regimes.py` validates standalone ages against `maximum_age_days`, guards smooth-step arithmetic, treats declared reference min/max metadata as strict nonnegative integer bounds, and converts `ArithmeticError`/`TypeError` raised by `reference.value` to a redacted `ValueError` while preserving `KeyError` and reference-domain `ValueError` behavior.
- Head circumference is evaluated only through the configured decay boundary. Missing head data at the boundary is optional; earlier missing data remains an error, and transition points can therefore carry `None` after decay.
- Transition continuity checks every actual crossing pair and compares the stable length-to-height representation at both the first post-transition age and the pair's current age, catching jumps that begin after day 761 without turning sparse normal trajectories into growth-jump failures.
- `src/synthetic/golden_trajectories.py` keeps its evaluator-only identity contract aligned with the optional post-decay head channel; post-transition head data remains prohibited.
- The observation-generation hostile-input regression now bypasses the model invariant explicitly so it continues to exercise the downstream boundary with malformed latent data.

## Follow-up: oversized-age hardening

Two additional important gaps were fixed on top of the original change. The pre-transition catch-up fraction now converts oversized integer-division failures to the age-regime arithmetic `ValueError` contract. Puberty state sampling now wraps arithmetic, type, and range failures from the random uniform draws, so huge but structurally valid integer puberty bounds cannot leak a NumPy `OverflowError`.

Focused red regressions first reproduced the raw `OverflowError` from both the catch-up division and `Generator.uniform`. The corresponding green regressions cover a valid huge-age pre-transition configuration with an explicit state and huge puberty bounds with ordinary generation; both now fail closed with `ValueError` while default configurations remain unchanged.

## Final velocity-gap hardening

The velocity annualization now guards the age-gap scale calculation. A focused `(H, 2H)` regression with `H = 10**1000` first reproduced the raw integer-to-float `OverflowError`; it now fails closed with the documented finite-velocity `ValueError` while ordinary velocity arithmetic remains unchanged.

The shared `generation_z_score` helper now likewise normalizes custom-hook `ArithmeticError` and `TypeError` failures to a fixed `ValueError`. A pair of downstream regressions first reproduced the leaked exceptions and now pass without changing the existing `KeyError` or domain-`ValueError` paths.

## TDD evidence

New regressions were added before the corresponding production changes. The initial red run reproduced ten missing guards across model/config/kernel tests. The infancy regression initially failed to raise; it passed after adding the model invariant. The golden trajectory suite initially reported six identity failures because its evaluator still required head circumference in a post-decay transition point; the evaluator-only check was updated and those cases pass.

## Verification

```text
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_age_regime_models.py tests/synthetic/test_age_regime_config.py tests/synthetic/test_age_regime_kernel.py tests/synthetic/test_age_regime_disorder.py tests/synthetic/test_golden_trajectories.py tests/synthetic/test_golden_trajectory_docs.py tests/synthetic/test_golden_trajectory_boundaries.py tests/synthetic/test_counterfactual_world_assembly.py tests/synthetic/test_observation_generation.py
208 passed in 2.51s

PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/models.py src/synthetic/native/age_regimes.py src/synthetic/golden_trajectories.py tests/synthetic/test_age_regime_models.py tests/synthetic/test_age_regime_config.py tests/synthetic/test_age_regime_kernel.py tests/synthetic/test_observation_generation.py
All checks passed!

python3 schema/build.py --check
validated 8 resources in datapackage.json

git diff --check
clean
```

The follow-up verification reran the same focused/downstream matrix with the two additional regressions:

```text
210 passed in 2.50s
All checks passed!
validated 8 resources in datapackage.json
git diff --check: clean
```

The final focused/downstream verification, including the velocity-gap regression, reported `211 passed in 2.44s`; Ruff, schema validation, and `git diff --check` remained clean.

The final verification including the hook regressions reported `254 passed in 2.50s`; Ruff, schema validation, and `git diff --check` remained clean.

No visible export/resource path, schema contract, roadmap, or documentation claim was changed.
