# Task 2 fix round 1: dynamic-import boundary regressions

The static Synthea boundary scanner now records literal module targets from
`importlib.import_module` and `__import__` calls alongside direct and relative
imports. This closes dynamic manifest-consumer and forbidden-runtime-import
evasions without classifying computed targets or changing production code.

## Red phase

Regression fixtures were added first for a dynamic manifest consumer and a
forbidden runtime import. Against the pre-fix scanner:

```text
uv run pytest -q tests/synthetic/test_synthea_conformance_boundaries.py
.........FFF.                                                            [100%]
3 failed, 10 passed in 0.22s
```

The two dynamic manifest fixtures and the `__import__("subprocess")` fixture
failed because `_imports` did not inspect call nodes.

## Green verification

```text
uv run pytest -q tests/synthetic/test_synthea_conformance_boundaries.py
.............                                                            [100%]
13 passed in 0.27s

uv run pytest -q tests/synthetic/test_synthea_conformance.py tests/synthetic/test_synthea_conformance_docs.py tests/synthetic/test_synthea_conformance_boundaries.py
........................................................................ [ 67%]
..................................                                       [100%]
106 passed in 0.32s

uv run ruff check tests/synthetic/test_synthea_conformance_boundaries.py
All checks passed!
```

No production source, Synthea contract, docs, data, lockfile, or runtime
dependency changed. Only `tests/synthetic/test_synthea_conformance_boundaries.py`
and this evidence report are in scope.

## Concerns

Only literal string targets are classified, as required; unrelated computed
dynamic behavior remains outside this conservative AST scanner.
