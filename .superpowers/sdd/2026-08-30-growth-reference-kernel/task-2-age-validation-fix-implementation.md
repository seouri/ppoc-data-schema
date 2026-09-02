# Task 2 age-validation fix implementation

## Scope

Implemented the current-main review fix for `HealthyKernel`: constructor age
bounds and every requested age are now validated as nonnegative Python integers
before ordering, domain, or reference comparisons. Boolean values are rejected
explicitly because `bool` is an `int` subclass. `maximum_age_days=None` remains
the supported unbounded default.

Changed only:

- `src/synthetic/native/healthy.py`
- `tests/synthetic/test_healthy_reference_guards.py`

No reference implementation, documentation, schema, script/data, or lock file
was changed.

## TDD evidence

Regression cases were added before the production validation change. Running
the cases against the base `main` source (`386a231`) produced the expected red
result:

```text
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/Users/joon/src/tries/ppoc-data-schema/src \
/Users/joon/src/tries/ppoc-data-schema/.venv/bin/python -m pytest -q \
tests/synthetic/test_healthy_reference_guards.py
11 failed, 11 passed
```

The minimal implementation adds one field-aware nonnegative-integer helper,
uses it for both constructor bounds, and validates the nonempty `ages_days`
tuple before the existing uniqueness and domain checks. The same focused run
against this worktree is green:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
/Users/joon/src/tries/ppoc-data-schema/.venv/bin/python -m pytest -q \
tests/synthetic/test_healthy_reference_guards.py
22 passed
```

The regression matrix covers `True`, `730.5`, strings, and `None` for the
required minimum bound and requested ages; it covers boolean and non-integer
maximum bounds; and it confirms a valid nonnegative integer age still produces
a point.

## Verification

```text
focused healthy/reference/development tests: 109 passed, 3 skipped
ruff check (healthy implementation and guard tests): All checks passed!
python3 schema/build.py --check: validated 8 resources in datapackage.json
git diff --check: clean
```

The three skipped tests are the opt-in 10,000-member development scale profile
(`SYNTHETIC_RUN_SCALE=1`); no scale profile was run as part of this focused
fix.
