# Task 1 implementation report

Status: DONE

## Changed files

- `src/synthetic/derivation_binding.py`: strict frozen binding, oracle, reference-standard, golden-evidence, and review models; exact mapping parsing; duplicate-key-safe JSON parsing; canonical JSON serialization; digest, token, timestamp, status, category, and count validation; fixed redacted unavailable exception.
- `tests/synthetic/test_derivation_binding_models.py`: fictional valid fixture and 28 model, round-trip, immutability, exact-key, hostile-input, category, serialization, and redaction tests.

`src/synthetic/__init__.py` was left unchanged because it does not currently re-export public synthetic contracts.

## Verification

Command:

```text
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_derivation_binding_models.py
```

Output:

```text
............................                                             [100%]
28 passed in 0.03s
```

Command:

```text
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/derivation_binding.py tests/synthetic/test_derivation_binding_models.py
```

Output:

```text
All checks passed!
```

Command:

```text
git diff --check
```

Output: no output (success).

The required red-phase command was also run before implementation and failed at collection as expected with `ModuleNotFoundError: No module named 'synthetic.derivation_binding'`.

## Commit

- `68661cff107e0c475fba1ba8218bc98fa8802751` — `feat: add derivation binding models`

## Concerns

None for the Task 1 scope. The implementation intentionally does not alter parity/export contracts or implement later roadmap tasks.

## Fix round 1

Addressed reviewer findings by retaining `golden_evidence.parity_status` and `review.status` as validated public `str` fields (the exported `DerivationBindingStatus` vocabulary remains available), and by routing count/parity mutations to `golden_evidence` in the tests.

Command:

```text
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/synthetic/test_derivation_binding_models.py
```

Output:

```text
............................                                             [100%]
28 passed in 0.03s
```

Command:

```text
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src/synthetic/derivation_binding.py tests/synthetic/test_derivation_binding_models.py
```

Output:

```text
All checks passed!
```

Command:

```text
git diff --check
```

Output: no output (success).
