# Growth Reference Kernel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the test-only growth-reference boundary with a validated, provenance-aware LMS table implementation and make the healthy trajectory kernel fail closed on unsupported domains or nonphysical reference output.

**Architecture:** `LmsGrowthReference` owns immutable LMS rows keyed by metric, reference sex, and age in days; it validates an optional source hash, linearly interpolates parameters within each supported domain, and converts z-scores through the LMS equation. `HealthyKernel` remains engine-neutral and continues to generate two independent anthropometric dimensions before deriving weight, but it will use the reference’s declared domain and reject nonfinite or nonpositive values. No clinical reference table is bundled by this plan; callers must provide an approved public artifact.

**Tech Stack:** Python 3.12+, standard-library `csv`, `hashlib`, `math`, `dataclasses`, NumPy PCG64DXSM, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-08-30-synthetic-growth-fixtures-design.md`

## Global Constraints

- `datapackage.json` remains the sole schema authority; this plan does not change CSV paths, headers, field order, types, null conventions, or key semantics.
- Offline generation reads only public schema metadata, pinned public reference tables, versioned configuration, and approved calibration artifacts; no patient-level records or real identifiers may be accepted by the reference layer.
- Every reference artifact is identified by a nonempty versioned `reference_id`; a supplied source hash is lowercase SHA-256 and is checked against the exact file bytes.
- A reference value must be finite and strictly positive for height/length, BMI, and other anthropometric metrics; invalid domains or parameters fail closed with `ValueError`.
- The kernel generates only two independent anthropometric dimensions and derives weight from BMI and height; it must not independently sample weight.
- Existing smoke behavior remains age two years and older and continues to use the injected test reference/oracle; this plan does not relabel it as clinically validated.
- Identical rows, reference metadata, random-stream inputs, and seed must produce identical reference values and trajectory points.
- Hidden truth, event traces, patient-level calibration data, and privacy attack artifacts remain outside visible package APIs.

---

### Task 1: Add the validated tabulated LMS growth reference

**Files:**
- Modify: `src/synthetic/references.py`
- Create: `tests/synthetic/test_references.py`

**Interfaces:**
- Produces `LmsRow(metric: str, age_days: int, reference_sex: str, l: float, m: float, s: float)` as a frozen dataclass.
- Produces `LmsGrowthReference(reference_id: str, rows: Iterable[LmsRow], source_sha256: str | None = None)` with `from_csv(path: Path, reference_id: str, expected_sha256: str | None = None)`, `value(metric: str, age_days: int, reference_sex: str, z: float) -> float`, and read-only `reference_id`, `source_sha256`, `metrics`, `min_age_days`, and `max_age_days` properties.
- Consumes the existing `GrowthReference` protocol without changing the test-only `LinearTestReference`.

- [ ] **Step 1: Write the failing tests for LMS conversion and interpolation**

Add these tests to `tests/synthetic/test_references.py`:

```python
import csv
import hashlib
import math

import pytest

from synthetic.references import LmsGrowthReference, LmsRow


def test_lms_reference_converts_zero_and_nonzero_l_parameters() -> None:
    reference = LmsGrowthReference(
        "public-growth-v1",
        rows=(
            LmsRow("height_cm", 730, "F", 1.0, 100.0, 0.1),
            LmsRow("bmi", 730, "F", 0.0, 16.0, 0.1),
        ),
    )

    assert reference.value("height_cm", 730, "F", 2.0) == pytest.approx(120.0)
    assert reference.value("bmi", 730, "F", 2.0) == pytest.approx(16.0 * math.exp(0.2))


def test_lms_reference_linearly_interpolates_parameters_by_age() -> None:
    reference = LmsGrowthReference(
        "public-growth-v1",
        rows=(
            LmsRow("height_cm", 730, "F", 1.0, 100.0, 0.1),
            LmsRow("height_cm", 1095, "F", 1.0, 110.0, 0.2),
        ),
    )

    # Midpoint parameters are L=1, M=105, S=0.15; z=0 therefore returns M.
    assert reference.value("height_cm", 912, "F", 0.0) == pytest.approx(105.0)


def test_lms_reference_rejects_missing_duplicate_and_invalid_rows() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        LmsGrowthReference(
            "public-growth-v1",
            rows=(
                LmsRow("height_cm", 730, "F", 1.0, 100.0, 0.1),
                LmsRow("height_cm", 730, "F", 1.0, 100.0, 0.1),
            ),
        )

    with pytest.raises(ValueError, match="positive"):
        LmsGrowthReference(
            "public-growth-v1",
            rows=(LmsRow("height_cm", 730, "F", 1.0, 100.0, 0.0),),
        )

    with pytest.raises(ValueError, match="reference_id"):
        LmsGrowthReference("", rows=(LmsRow("height_cm", 730, "F", 1.0, 100.0, 0.1),))


def test_lms_reference_rejects_unknown_keys_and_out_of_domain_values() -> None:
    reference = LmsGrowthReference(
        "public-growth-v1",
        rows=(LmsRow("height_cm", 730, "F", 1.0, 100.0, 0.1),),
    )

    with pytest.raises(KeyError, match="weight"):
        reference.value("weight", 730, "F", 0.0)
    with pytest.raises(ValueError, match="domain"):
        reference.value("height_cm", 729, "F", 0.0)
    with pytest.raises(ValueError, match="finite"):
        reference.value("height_cm", 730, "F", float("nan"))


def test_lms_reference_loads_csv_and_checks_exact_source_hash(tmp_path) -> None:
    path = tmp_path / "growth.csv"
    path.write_text(
        "metric,age_days,reference_sex,l,m,s\n"
        "height_cm,730,F,1,100,0.1\n",
        encoding="utf-8",
        newline="",
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    reference = LmsGrowthReference.from_csv(
        path, reference_id="public-growth-v1", expected_sha256=digest
    )

    assert reference.source_sha256 == digest
    assert reference.value("height_cm", 730, "F", 0.0) == pytest.approx(100.0)
    with pytest.raises(ValueError, match="SHA-256"):
        LmsGrowthReference.from_csv(
            path, reference_id="public-growth-v1", expected_sha256="0" * 64
        )


def test_lms_reference_rejects_bad_csv_columns(tmp_path) -> None:
    path = tmp_path / "growth.csv"
    path.write_text("metric,age_days,reference_sex,l,m\nheight_cm,730,F,1,100\n", encoding="utf-8")

    with pytest.raises(ValueError, match="columns"):
        LmsGrowthReference.from_csv(path, reference_id="public-growth-v1")
```

- [ ] **Step 2: Run the reference tests to verify the feature is missing**

Run: `uv run pytest -q tests/synthetic/test_references.py`

Expected: collection fails because `LmsGrowthReference` and `LmsRow` are not defined.

- [ ] **Step 3: Implement the minimal validated LMS reference**

In `src/synthetic/references.py`:

1. Keep the existing `GrowthReference` protocol unchanged for compatibility.
2. Add the frozen `LmsRow` dataclass and validate every row’s metric and sex are nonempty strings, `age_days` is a nonnegative integer (not `bool`), and `l`, `m`, and `s` are finite floats with `m > 0` and `s > 0`.
3. Require a nonempty `reference_id`, reject duplicate `(metric, age_days, reference_sex)` keys, and store rows in deterministic sorted order.
4. Build per-`(metric, reference_sex)` age series. `value` must reject unknown metrics/sexes, nonfinite z-scores, and ages outside that series’ min/max domain. Interpolate `l`, `m`, and `s` linearly between surrounding rows; exact endpoints are valid.
5. Convert z to a value with `M * (1 + L * S * z) ** (1 / L)` when `L != 0`, and `M * exp(S * z)` when `L == 0`. Reject a nonpositive LMS base before exponentiation and reject any nonfinite or nonpositive result.
6. Implement `from_csv` with the exact column set `metric,age_days,reference_sex,l,m,s`, UTF-8 `csv.DictReader`, strict missing/extra-column rejection, typed parsing, and exact-byte SHA-256 verification when `expected_sha256` is supplied. Record the computed file hash as `source_sha256`.

- [ ] **Step 4: Run the reference tests to verify they pass**

Run: `uv run pytest -q tests/synthetic/test_references.py`

Expected: all reference tests pass with no warnings.

- [ ] **Step 5: Run focused lint and the existing synthetic suite**

Run: `uv run ruff check src/synthetic/references.py tests/synthetic/test_references.py && uv run pytest -q tests/synthetic`

Expected: Ruff reports no findings and all synthetic tests pass.

- [ ] **Step 6: Commit the validated reference implementation**

```bash
git add src/synthetic/references.py tests/synthetic/test_references.py
git commit -m "feat: add validated LMS growth reference"
```

---

### Task 2: Harden the healthy trajectory kernel around reference domains

**Files:**
- Modify: `src/synthetic/native/healthy.py`
- Create: `tests/synthetic/test_healthy_reference_guards.py`

**Interfaces:**
- Consumes: `GrowthReference.value(...)` and optional `min_age_days`/`max_age_days` attributes exposed by `LmsGrowthReference`.
- Produces: `HealthyKernel(reference, minimum_age_days: int = 730, maximum_age_days: int | None = None)` and the existing `generate(...) -> tuple[LatentPoint, ...]` signature.
- Preserves: `LatentPoint` fields, named `growth` stream, existing age-two smoke behavior, and the height/BMI-to-weight identity.

- [ ] **Step 1: Write failing tests for domain and physical-output guards**

Add these tests to `tests/synthetic/test_healthy_reference_guards.py`:

```python
import math

import pytest

from synthetic.models import PatientState
from synthetic.native.healthy import HealthyKernel
from synthetic.randomness import NamedRandomStreams


class GuardReference:
    reference_id = "guard-reference-v1"
    min_age_days = 730
    max_age_days = 1095

    def __init__(self, *, height: float = 90.0, bmi: float = 16.0) -> None:
        self.height = height
        self.bmi = bmi

    def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
        del age_days, reference_sex, z
        if metric == "height_cm":
            return self.height
        if metric == "bmi":
            return self.bmi
        raise KeyError(metric)


def _patient() -> PatientState:
    return PatientState("syn-patient-a", "F", "F")


def test_kernel_rejects_ages_outside_reference_domain() -> None:
    reference = GuardReference()
    with pytest.raises(ValueError, match="domain"):
        HealthyKernel(reference).generate(
            _patient(), (1096,), NamedRandomStreams(5, 0)
        )


def test_kernel_can_be_configured_for_a_reference_starting_at_birth() -> None:
    reference = GuardReference()
    points = HealthyKernel(reference, minimum_age_days=0, maximum_age_days=1095).generate(
        _patient(), (0, 730), NamedRandomStreams(5, 0)
    )

    assert [point.age_days for point in points] == [0, 730]


@pytest.mark.parametrize("height,bmi", [(0.0, 16.0), (90.0, 0.0), (math.nan, 16.0)])
def test_kernel_rejects_nonphysical_reference_values(height: float, bmi: float) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        HealthyKernel(GuardReference(height=height, bmi=bmi)).generate(
            _patient(), (730,), NamedRandomStreams(5, 0)
        )


def test_kernel_rejects_invalid_age_configuration() -> None:
    with pytest.raises(ValueError, match="minimum_age_days"):
        HealthyKernel(GuardReference(), minimum_age_days=-1)
    with pytest.raises(ValueError, match="maximum_age_days"):
        HealthyKernel(GuardReference(), minimum_age_days=900, maximum_age_days=800)
```

- [ ] **Step 2: Run the guard tests to verify they fail**

Run: `uv run pytest -q tests/synthetic/test_healthy_reference_guards.py`

Expected: collection or assertions fail because the kernel has no configurable domain or physical-output guards.

- [ ] **Step 3: Implement minimal kernel guards**

In `src/synthetic/native/healthy.py`:

1. Add keyword-only `minimum_age_days` and `maximum_age_days` constructor arguments, defaulting to `730` and `None`. Reject a negative minimum and a maximum smaller than the minimum.
2. During `generate`, keep the existing unique/increasing check, reject ages below `minimum_age_days`, and reject ages above `maximum_age_days` when configured.
3. If the reference exposes integer `min_age_days` or `max_age_days`, reject requested ages outside those bounds with a `ValueError` containing `domain`. Do not require those optional attributes from the `GrowthReference` protocol.
4. After requesting each height and BMI value, reject any nonfinite or nonpositive value with a `ValueError` containing `finite and positive`; then derive weight exactly as before.
5. Keep the existing reference calls, named stream, z-score AR updates, `LatentPoint` construction, and default age-two behavior unchanged.

- [ ] **Step 4: Run focused tests and the full suite**

Run: `uv run pytest -q tests/synthetic/test_healthy_kernel.py tests/synthetic/test_healthy_reference_guards.py && uv run pytest -q`

Expected: all focused and repository tests pass.

- [ ] **Step 5: Run lint and schema checks**

Run: `uv run ruff check src tests && python3 schema/build.py --check && git diff --check`

Expected: Ruff has no findings, the eight descriptor resources validate, and Git reports no whitespace errors.

- [ ] **Step 6: Commit the kernel hardening**

```bash
git add src/synthetic/native/healthy.py tests/synthetic/test_healthy_reference_guards.py
git commit -m "feat: guard healthy trajectories by reference domain"
```

---

### Task 3: Document the approved-reference handoff

**Files:**
- Modify: `docs/synthetic-generator.md`
- Test: `tests/synthetic/test_package_import.py` (only if a documentation example is made executable)

**Interfaces:**
- Consumes: `LmsGrowthReference.from_csv` and the existing injected `GrowthReference` boundary.
- Produces: documentation that explains how to supply a pinned public LMS artifact without implying that this repository bundles a clinically validated reference.

- [ ] **Step 1: Add the reference-provider section**

Document the exact CSV columns, SHA-256 pinning, age/sex/metric domain behavior, and a short `LmsGrowthReference.from_csv(...)` example. State that the artifact must be approved and public, that no patient rows may be used, and that a table-backed reference alone is not prevalence, clinical, or privacy validation.

- [ ] **Step 2: Verify documentation and repository checks**

Run: `uv run pytest -q && uv run ruff check src tests && python3 schema/build.py --check && git diff --check`

Expected: all tests pass, Ruff has no findings, the schema check validates eight resources, and Git reports no whitespace errors.

- [ ] **Step 3: Commit the documentation**

```bash
git add docs/synthetic-generator.md
git commit -m "docs: describe pinned LMS reference inputs"
```

---

## Completion gate

Before calling this plan complete, verify that:

- LMS conversion, interpolation, CSV parsing, and exact-byte hash pinning have passing tests.
- The healthy kernel rejects unsupported reference domains and nonfinite/nonpositive anthropometric outputs while preserving the existing smoke profile.
- No clinical reference data, real patient rows, hidden truth, or privacy evidence entered the repository.
- The full pytest, Ruff, schema, and whitespace checks pass from the feature branch.
- The usage guide explicitly labels the reference layer as an input contract, not clinical or prevalence validation.

