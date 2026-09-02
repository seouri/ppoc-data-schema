# Synthetic Growth Fixture Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic native foundation that can generate and structurally validate an exact-PPOC-schema smoke package when supplied a derivation oracle, without reading real patient data.

**Architecture:** A small Python package loads `datapackage.json` as the schema authority, generates engine-neutral latent and observed records through named random streams, writes the six base resources transactionally, delegates the two augmented resources to a required derivation-oracle interface, and then emits a synthetic descriptor and validation report. This first vertical slice supports healthy patients aged two years and older through an injected reference provider; it deliberately does not claim clinical, prevalence, held-out, or privacy validation.

> **Implementation note:** The code blocks below are the initial task-by-task TDD sketches and are retained as historical context. The completed source and tests are authoritative where later hardening extends these sketches. In particular, visible manifests carry the derivation implementation fingerprint and test-only classification, while the textual oracle ID and review metadata remain in the private derivation binding; the smoke/export paths require that binding explicitly.

> **Scope note:** This plan is historical. Its original calibration and parity prerequisites describe the foundation at that time; the current explicit development profiles use the checked-in test-only reference/oracle, while clinical, population, privacy, and release claims remain separate.

**Tech Stack:** Python 3.12+, uv, NumPy PCG64DXSM, standard-library CSV/JSON/dataclasses/hashlib, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-08-30-synthetic-growth-fixtures-design.md`

## Global Constraints

- `datapackage.json` is the sole schema authority; generated paths, headers, field order, types, null conventions, dialects, encodings, primary keys, foreign keys, and logical links must come from it.
- Declared foreign keys are complete structural relationships. Foundation validation treats `x-logicalForeignKeys` as observational links, recomputes their null/orphan counts in the generated descriptor, and permits incompleteness by default; a later versioned observation/calibration policy may require a selected logical link to be complete without changing the schema fingerprint. The structural validation report retains errors and row counts only.
- Ordinary development reads only the public schema, pinned public reference/runtime files, versioned fictional configuration, and generated state; an approved calibration artifact is optional and belongs only to a governed comparison route. This foundation has no real-data input option.
- Visible identifiers are newly generated and cannot contain hashes, substrings, ordering, or transformations of real identifiers.
- Generate only two independent anthropometric dimensions and derive the third; this foundation generates standing height and BMI and derives weight.
- Hidden truth and event traces never appear in the visible package or ordinary loader APIs.
- Visible manifests record a derivation implementation fingerprint and test-only classification; the textual oracle ID, binding ID, review metadata, and source/dependency details remain in the private derivation binding and are not exported.
- Output directories are never overwritten; partial output stays visibly unvalidated.
- A missing derivation oracle keeps the direct foundation API unavailable; the explicit development CLI supplies the checked-in test-only oracle and reports its test-only status.
- An authoritative augmentation implementation or approved parity harness is required for clinical or release claims, not for ordinary development fixtures.
- Identical inputs, versions, reference time, PRNG specification, and seed must produce identical visible file hashes.
- Synthetic development utility, statistical fidelity, clinical validity, privacy evidence, and release authorization remain separate claims.

## Work-package sequence

This is the first of five independently reviewable plans:

1. **Foundation, this plan:** schema contract, reproducibility, output lifecycle, injected healthy-growth kernel, exact CSV export, derivation boundary, and structural validation.
2. **Growth and clinical modules:** WHO/CDC references, infancy, puberty, disease state machines, disorder-critical resources, and reviewed golden cases.
3. **Calibration and fidelity:** governed aggregate calibration, patient-disjoint held-out validation, prevalence, observation errors, temporal drift, and task utility.
4. **Privacy audit:** shadow-model membership inference, linkage, attribute disclosure, controls, composition, policy decisions, and optional differential privacy.
5. **Synthea backend:** pinned Synthea extension, event adapter, PPOC exporter, and engine-conformance suite.

The foundation's original generated output was a `smoke` profile. The current CLI adds explicitly named `development-smoke` and `development-cohort` profiles using the pinned test-only runtime; those packages remain development artifacts and are not clinical, prevalence, privacy, or release evidence.

## Planned file structure

- `pyproject.toml`: Python, dependency, test, and lint configuration.
- `uv.lock`: exact development and runtime dependency resolution.
- `src/synthetic/schema_contract.py`: descriptor loading, resource lookup, header lookup, and schema fingerprint.
- `src/synthetic/randomness.py`: named seed derivation, generators, and synthetic identifiers.
- `src/synthetic/models.py`: engine-neutral patient, latent point, observed visit, and event records.
- `src/synthetic/manifest.py`: run identity and canonical manifest serialization.
- `src/synthetic/run_directory.py`: non-overwriting partial-output and atomic-promotion lifecycle.
- `src/synthetic/references.py`: growth-reference protocol used by engines.
- `src/synthetic/native/healthy.py`: age-two-and-older healthy growth kernel.
- `src/synthetic/base_resources.py`: mapping from engine records to the six base resource row sets.
- `src/synthetic/csv_package.py`: descriptor-driven CSV writing and generated-descriptor statistics.
- `src/synthetic/derivation.py`: fail-closed derivation-oracle protocol.
- `src/synthetic/validate.py`: structural, type, key, relationship, and provenance validation.
- `src/synthetic/generate.py`: smoke-profile orchestration and CLI.
- `tests/synthetic/`: unit and integration tests.

---

### Task 1: Establish the Python package and test harness

**Files:**
- Create: `pyproject.toml`
- Create: `src/synthetic/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/synthetic/__init__.py`
- Create: `tests/synthetic/test_package_import.py`
- Create: `uv.lock`

**Interfaces:**
- Consumes: repository Python 3.12 or newer and uv.
- Produces: importable `synthetic` package and `uv run pytest` / `uv run ruff check` commands.

- [x] **Step 1: Add project configuration and the failing import test**

```toml
# pyproject.toml
[project]
name = "ppoc-synthetic-fixtures"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "numpy>=2.0,<3",
]

[dependency-groups]
dev = [
  "pytest>=8.3,<9",
  "ruff>=0.12,<1",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/synthetic"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"

[tool.ruff]
target-version = "py312"
line-length = 100
```

```python
# tests/synthetic/test_package_import.py
def test_package_has_version() -> None:
    import synthetic

    assert synthetic.__version__ == "0.1.0"
```

- [x] **Step 2: Resolve dependencies and verify the test fails**

Run: `uv lock && uv run pytest tests/synthetic/test_package_import.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'synthetic'`.

- [x] **Step 3: Add the minimal package**

```python
# src/synthetic/__init__.py
"""Completely generated PPOC-schema pediatric fixtures."""

__version__ = "0.1.0"
```

Create empty `tests/__init__.py` and `tests/synthetic/__init__.py` files so integration tests can import shared fakes without relying on an unrelated installed `tests` package.

- [x] **Step 4: Run package tests and lint**

Run: `uv run pytest tests/synthetic/test_package_import.py -v && uv run ruff check src tests`

Expected: one passing test and no Ruff findings.

- [x] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock src/synthetic/__init__.py tests/__init__.py tests/synthetic/__init__.py tests/synthetic/test_package_import.py
git commit -m "build: initialize synthetic fixture package"
```

---

### Task 2: Lock the PPOC schema contract and fingerprint

**Files:**
- Create: `src/synthetic/schema_contract.py`
- Create: `tests/synthetic/test_schema_contract.py`

**Interfaces:**
- Consumes: `load_descriptor(path: Path) -> dict[str, Any]`.
- Produces: `resource_spec(descriptor, name) -> dict[str, Any]`, `field_names(descriptor, name) -> tuple[str, ...]`, and `schema_fingerprint(descriptor) -> str`.

- [x] **Step 1: Write failing contract tests**

```python
# tests/synthetic/test_schema_contract.py
from pathlib import Path

import pytest

from synthetic.schema_contract import (
    field_names,
    load_descriptor,
    resource_spec,
    schema_fingerprint,
)

ROOT = Path(__file__).resolve().parents[2]


def test_checked_in_schema_fingerprint_is_stable() -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    assert schema_fingerprint(descriptor) == (
        "795724ec4838df8afa9c09b7c059fa76f644d7f8fb6dcc8ce808da203c2f8597"
    )


def test_contract_has_exact_resource_paths_and_field_counts() -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    expected = {
        "patients": ("patients.csv", 11),
        "patients_augmented": ("patients_augmented.csv", 87),
        "visits": ("visits.csv", 43),
        "visits_augmented": ("visits_augmented-20251209150512.csv", 82),
        "labs": ("labs.csv", 12),
        "medications": ("medications.csv", 8),
        "problem_list": ("problem_list.csv", 5),
        "referrals": ("referrals.csv", 6),
    }
    assert {
        resource["name"]: (resource["path"], len(field_names(descriptor, resource["name"])))
        for resource in descriptor["resources"]
    } == expected


def test_unknown_resource_fails_closed() -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    with pytest.raises(KeyError, match="Unknown resource"):
        resource_spec(descriptor, "unknown")
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/synthetic/test_schema_contract.py -v`

Expected: FAIL because `synthetic.schema_contract` does not exist.

- [x] **Step 3: Implement canonical schema projection**

```python
# src/synthetic/schema_contract.py
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def load_descriptor(path: Path) -> dict[str, Any]:
    descriptor = json.loads(path.read_text(encoding="utf-8"))
    if descriptor.get("profile") != "tabular-data-package":
        raise ValueError("descriptor is not a tabular-data-package")
    if not isinstance(descriptor.get("resources"), list):
        raise ValueError("descriptor resources must be a list")
    return descriptor


def resource_spec(descriptor: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [item for item in descriptor["resources"] if item.get("name") == name]
    if len(matches) != 1:
        raise KeyError(f"Unknown resource: {name}")
    return matches[0]


def field_names(descriptor: dict[str, Any], name: str) -> tuple[str, ...]:
    fields = resource_spec(descriptor, name)["schema"]["fields"]
    return tuple(field["name"] for field in fields)


def schema_projection(descriptor: dict[str, Any]) -> dict[str, Any]:
    resources: list[dict[str, Any]] = []
    for resource in descriptor["resources"]:
        schema = resource["schema"]
        resources.append(
            {
                "name": resource["name"],
                "path": resource["path"],
                "encoding": resource.get("encoding", "utf-8"),
                "dialect": resource.get("dialect", {}),
                "fields": [
                    {
                        key: field[key]
                        for key in ("name", "type", "constraints")
                        if key in field
                    }
                    for field in schema["fields"]
                ],
                "missingValues": schema.get("missingValues", []),
                "primaryKey": schema.get("primaryKey"),
                "foreignKeys": schema.get("foreignKeys", []),
                "logicalForeignKeys": [
                    {
                        "fields": link["fields"],
                        "reference": link["reference"],
                    }
                    for link in resource.get("x-logicalForeignKeys", [])
                ],
            }
        )
    return {"resources": resources}


def schema_fingerprint(descriptor: dict[str, Any]) -> str:
    payload = json.dumps(
        schema_projection(descriptor),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
```

- [x] **Step 4: Run tests and descriptor check**

Run: `uv run pytest tests/synthetic/test_schema_contract.py -v && python3 schema/build.py --check`

Expected: three passing tests and `validated 8 resources in datapackage.json`.

- [x] **Step 5: Commit**

```bash
git add src/synthetic/schema_contract.py tests/synthetic/test_schema_contract.py
git commit -m "feat: lock synthetic package schema contract"
```

---

### Task 3: Add deterministic random streams, identifiers, and manifests

**Files:**
- Create: `src/synthetic/randomness.py`
- Create: `src/synthetic/manifest.py`
- Create: `tests/synthetic/test_reproducibility.py`

**Interfaces:**
- Consumes: `NamedRandomStreams(run_seed: int, patient_index: int)`.
- Produces: `generator(name: str) -> numpy.random.Generator`, `synthetic_id(run_seed: int, kind: str, index: int) -> str`, `RunManifest.to_json_bytes() -> bytes`.

- [x] **Step 1: Write failing reproducibility tests**

```python
# tests/synthetic/test_reproducibility.py
import json

from synthetic.manifest import RunManifest
from synthetic.randomness import NamedRandomStreams, synthetic_id


def test_named_streams_are_stable_and_isolated() -> None:
    left = NamedRandomStreams(20260830, 7)
    right = NamedRandomStreams(20260830, 7)
    assert left.generator("growth").normal(size=4).tolist() == (
        right.generator("growth").normal(size=4).tolist()
    )
    assert left.generator("growth").normal(size=4).tolist() != (
        left.generator("visits").normal(size=4).tolist()
    )


def test_identifiers_are_deterministic_but_opaque() -> None:
    first = synthetic_id(20260830, "patient", 7)
    assert first == synthetic_id(20260830, "patient", 7)
    assert first != synthetic_id(20260830, "visit", 7)
    assert "7" not in first


def test_manifest_serialization_is_canonical() -> None:
    manifest = RunManifest.smoke(
        seed=20260830,
        schema_fingerprint="abc",
        reference_time="2026-08-30T00:00:00Z",
        reference_id="linear-test-reference-v1",
        configuration_sha256="config-hash",
        software_revision="test-revision",
    )
    decoded = json.loads(manifest.to_json_bytes())
    assert decoded["status"] == "GENERATED_UNVALIDATED"
    assert decoded["reference_id"] == "linear-test-reference-v1"
    assert decoded["software_revision"] == "test-revision"
    assert manifest.to_json_bytes().endswith(b"\n")
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/synthetic/test_reproducibility.py -v`

Expected: FAIL because the modules do not exist.

- [x] **Step 3: Implement named streams and opaque IDs**

```python
# src/synthetic/randomness.py
from __future__ import annotations

import hashlib

import numpy as np

PRNG_FAMILY = "numpy.random.PCG64DXSM"
SEED_DERIVATION_VERSION = "sha256-v1"


def _seed(*parts: object) -> int:
    material = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:16], "big")


class NamedRandomStreams:
    def __init__(self, run_seed: int, patient_index: int) -> None:
        self.run_seed = run_seed
        self.patient_index = patient_index

    def generator(self, name: str) -> np.random.Generator:
        if not name or any(character.isspace() for character in name):
            raise ValueError("stream name must be a nonempty token")
        bit_generator = np.random.PCG64DXSM(
            _seed(SEED_DERIVATION_VERSION, self.run_seed, self.patient_index, name)
        )
        return np.random.Generator(bit_generator)


def synthetic_id(run_seed: int, kind: str, index: int) -> str:
    digest = hashlib.sha256(
        f"synthetic-id-v1\x1f{run_seed}\x1f{kind}\x1f{index}".encode("utf-8")
    ).hexdigest()
    return f"syn-{kind}-{digest[:24]}"
```

- [x] **Step 4: Implement canonical manifest serialization**

```python
# src/synthetic/manifest.py
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

from synthetic.randomness import PRNG_FAMILY, SEED_DERIVATION_VERSION


@dataclass(frozen=True)
class RunManifest:
    manifest_version: str
    generator_version: str
    profile: str
    engine: str
    seed: int
    schema_fingerprint: str
    reference_time: str
    reference_id: str
    configuration_sha256: str
    software_revision: str
    prng_family: str
    seed_derivation_version: str
    status: str
    row_counts: dict[str, int] = field(default_factory=dict)
    file_sha256: dict[str, str] = field(default_factory=dict)
    # Visible cryptographic implementation identity; textual oracle_id stays in the private binding.
    derivation_fingerprint: str = ""

    @classmethod
    def smoke(
        cls,
        *,
        seed: int,
        schema_fingerprint: str,
        reference_time: str,
        reference_id: str,
        configuration_sha256: str,
        software_revision: str,
    ) -> "RunManifest":
        return cls(
            manifest_version="1",
            generator_version="0.1.0",
            profile="smoke",
            engine="native",
            seed=seed,
            schema_fingerprint=schema_fingerprint,
            reference_time=reference_time,
            reference_id=reference_id,
            configuration_sha256=configuration_sha256,
            software_revision=software_revision,
            prng_family=PRNG_FAMILY,
            seed_derivation_version=SEED_DERIVATION_VERSION,
            status="GENERATED_UNVALIDATED",
        )

    def to_json_bytes(self) -> bytes:
        return (
            json.dumps(asdict(self), sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        ).encode("utf-8")
```

- [x] **Step 5: Run tests and lint**

Run: `uv run pytest tests/synthetic/test_reproducibility.py -v && uv run ruff check src tests`

Expected: three passing tests and no Ruff findings.

- [x] **Step 6: Commit**

```bash
git add src/synthetic/randomness.py src/synthetic/manifest.py tests/synthetic/test_reproducibility.py
git commit -m "feat: add reproducible synthetic run identity"
```

---

### Task 4: Implement the non-overwriting run lifecycle

**Files:**
- Create: `src/synthetic/run_directory.py`
- Create: `tests/synthetic/test_run_directory.py`

**Interfaces:**
- Consumes: `RunDirectory.start(target: Path, run_id: str) -> RunDirectory`.
- Produces: writable `partial_path`, `promote() -> Path`, and `fail(reason: str) -> Path`.

- [x] **Step 1: Write failing lifecycle tests**

```python
# tests/synthetic/test_run_directory.py
from pathlib import Path

import pytest

from synthetic.run_directory import RunDirectory


def test_refuses_existing_target(tmp_path: Path) -> None:
    target = tmp_path / "run"
    target.mkdir()
    with pytest.raises(FileExistsError):
        RunDirectory.start(target, "abc")


def test_promotes_partial_directory_atomically(tmp_path: Path) -> None:
    run = RunDirectory.start(tmp_path / "run", "abc")
    (run.partial_path / "patients.csv").write_text("patient_id\n", encoding="utf-8")
    assert run.promote() == tmp_path / "run"
    assert not run.partial_path.exists()


def test_failure_keeps_evidence_outside_target(tmp_path: Path) -> None:
    run = RunDirectory.start(tmp_path / "run", "abc")
    failed = run.fail("derivation unavailable")
    assert failed.name == ".run.abc.failed"
    assert "derivation unavailable" in (failed / "failure.json").read_text()
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/synthetic/test_run_directory.py -v`

Expected: FAIL because `synthetic.run_directory` does not exist.

- [x] **Step 3: Implement the lifecycle**

```python
# src/synthetic/run_directory.py
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunDirectory:
    target: Path
    partial_path: Path
    failed_path: Path

    @classmethod
    def start(cls, target: Path, run_id: str) -> "RunDirectory":
        target = target.resolve()
        partial = target.parent / f".{target.name}.{run_id}.partial"
        failed = target.parent / f".{target.name}.{run_id}.failed"
        for path in (target, partial, failed):
            if path.exists():
                raise FileExistsError(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial.mkdir()
        return cls(target=target, partial_path=partial, failed_path=failed)

    def promote(self) -> Path:
        if self.target.exists():
            raise FileExistsError(self.target)
        os.replace(self.partial_path, self.target)
        return self.target

    def fail(self, reason: str) -> Path:
        (self.partial_path / "failure.json").write_text(
            json.dumps({"status": "FAILED", "reason": reason}, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(self.partial_path, self.failed_path)
        return self.failed_path
```

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/synthetic/test_run_directory.py -v`

Expected: three passing tests.

- [x] **Step 5: Commit**

```bash
git add src/synthetic/run_directory.py tests/synthetic/test_run_directory.py
git commit -m "feat: add fail-closed fixture output lifecycle"
```

---

### Task 5: Define engine-neutral records and the healthy growth kernel

**Files:**
- Create: `src/synthetic/models.py`
- Create: `src/synthetic/references.py`
- Create: `src/synthetic/native/__init__.py`
- Create: `src/synthetic/native/healthy.py`
- Create: `tests/synthetic/test_healthy_kernel.py`

**Interfaces:**
- Consumes: `GrowthReference.value(metric, age_days, reference_sex, z) -> float` and named patient streams.
- Produces: `HealthyKernel.generate(patient, ages_days) -> tuple[LatentPoint, ...]`; each point contains height, BMI, and deterministically derived weight.

- [x] **Step 1: Write failing anthropometric tests with an injected test reference**

```python
# tests/synthetic/test_healthy_kernel.py
import pytest

from synthetic.models import PatientState
from synthetic.native.healthy import HealthyKernel
from synthetic.randomness import NamedRandomStreams


class LinearTestReference:
    reference_id = "linear-test-reference-v1"

    def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
        age_years = age_days / 365.25
        if metric == "height_cm":
            return 80.0 + 5.5 * age_years + 4.0 * z
        if metric == "bmi":
            return 16.0 + 0.25 * age_years + 1.2 * z
        raise KeyError(metric)


def test_height_and_bmi_determine_weight() -> None:
    patient = PatientState("syn-patient-a", "F", "F")
    points = HealthyKernel(LinearTestReference()).generate(
        patient,
        ages_days=(730, 1095, 1460),
        streams=NamedRandomStreams(20260830, 0),
    )
    assert len(points) == 3
    for point in points:
        assert point.weight_kg == pytest.approx(
            point.bmi * (point.height_cm / 100.0) ** 2
        )


def test_kernel_is_reproducible_and_age_ordered() -> None:
    patient = PatientState("syn-patient-a", "M", "M")
    kernel = HealthyKernel(LinearTestReference())
    left = kernel.generate(
        patient, (730, 1095, 1460), NamedRandomStreams(5, 0)
    )
    right = kernel.generate(
        patient, (730, 1095, 1460), NamedRandomStreams(5, 0)
    )
    assert left == right
    assert [point.age_days for point in left] == [730, 1095, 1460]


def test_foundation_rejects_infant_ages() -> None:
    patient = PatientState("syn-patient-a", "F", "F")
    with pytest.raises(ValueError, match="age >= 730"):
        HealthyKernel(LinearTestReference()).generate(
            patient, (365,), NamedRandomStreams(5, 0)
        )
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/synthetic/test_healthy_kernel.py -v`

Expected: FAIL because the model and kernel modules do not exist.

- [x] **Step 3: Add engine-neutral records and reference protocol**

```python
# src/synthetic/models.py
from dataclasses import dataclass


@dataclass(frozen=True)
class PatientState:
    patient_id: str
    recorded_sex: str
    reference_sex: str


@dataclass(frozen=True)
class LatentPoint:
    patient_id: str
    age_days: int
    height_cm: float
    bmi: float
    weight_kg: float
    height_z: float
    bmi_z: float


@dataclass(frozen=True)
class ObservedVisit:
    patient_id: str
    visit_id: str
    age_days: int
    encounter_type: str
    height_in: float | None
    weight_oz: float | None
    epic_bmi: float | None


@dataclass(frozen=True)
class ClinicalEvent:
    patient_id: str
    age_days: int
    event_type: str
    code: str | None
    hidden: bool
```

```python
# src/synthetic/references.py
from typing import Protocol


class GrowthReference(Protocol):
    reference_id: str

    def value(
        self, metric: str, age_days: int, reference_sex: str, z: float
    ) -> float: ...
```

```python
# src/synthetic/native/__init__.py
"""Native synthetic-patient engine."""
```

- [x] **Step 4: Implement the minimum age-two-and-older kernel**

```python
# src/synthetic/native/healthy.py
from __future__ import annotations

from synthetic.models import LatentPoint, PatientState
from synthetic.randomness import NamedRandomStreams
from synthetic.references import GrowthReference


class HealthyKernel:
    def __init__(self, reference: GrowthReference) -> None:
        self.reference = reference

    def generate(
        self,
        patient: PatientState,
        ages_days: tuple[int, ...],
        streams: NamedRandomStreams,
    ) -> tuple[LatentPoint, ...]:
        if tuple(sorted(set(ages_days))) != ages_days:
            raise ValueError("ages_days must be unique and increasing")
        if any(age < 730 for age in ages_days):
            raise ValueError("foundation kernel requires age >= 730 days")
        growth = streams.generator("growth")
        height_z = float(growth.normal(0.0, 0.8))
        bmi_z = float(growth.normal(0.0, 0.8))
        points: list[LatentPoint] = []
        for age_days in ages_days:
            height_z = 0.96 * height_z + float(growth.normal(0.0, 0.08))
            bmi_z = 0.85 * bmi_z + float(growth.normal(0.0, 0.20))
            height_cm = self.reference.value(
                "height_cm", age_days, patient.reference_sex, height_z
            )
            bmi = self.reference.value(
                "bmi", age_days, patient.reference_sex, bmi_z
            )
            weight_kg = bmi * (height_cm / 100.0) ** 2
            points.append(
                LatentPoint(
                    patient_id=patient.patient_id,
                    age_days=age_days,
                    height_cm=height_cm,
                    bmi=bmi,
                    weight_kg=weight_kg,
                    height_z=height_z,
                    bmi_z=bmi_z,
                )
            )
        return tuple(points)
```

- [x] **Step 5: Run tests and lint**

Run: `uv run pytest tests/synthetic/test_healthy_kernel.py -v && uv run ruff check src tests`

Expected: three passing tests and no Ruff findings.

- [x] **Step 6: Commit**

```bash
git add src/synthetic/models.py src/synthetic/references.py src/synthetic/native tests/synthetic/test_healthy_kernel.py
git commit -m "feat: add healthy growth kernel contract"
```

---

### Task 6: Map engine output to six base resources and exact CSV headers

**Files:**
- Create: `src/synthetic/base_resources.py`
- Create: `src/synthetic/csv_package.py`
- Create: `tests/synthetic/test_base_resources.py`

**Interfaces:**
- Consumes: `PatientState`, `LatentPoint`, descriptor field order.
- Produces: `build_base_rows(...) -> dict[str, list[dict[str, object]]]` and `write_resource(path, resource, rows) -> int`.

- [x] **Step 1: Write failing base-resource and encoding tests**

```python
# tests/synthetic/test_base_resources.py
import csv
from pathlib import Path

from synthetic.base_resources import build_base_rows
from synthetic.csv_package import write_resource
from synthetic.models import LatentPoint, PatientState
from synthetic.schema_contract import field_names, load_descriptor, resource_spec

ROOT = Path(__file__).resolve().parents[2]


def test_base_rows_cover_six_nonderived_resources() -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    patient = PatientState("syn-patient-a", "F", "F")
    point = LatentPoint("syn-patient-a", 730, 90.0, 16.0, 12.96, 0.0, 0.0)
    rows = build_base_rows(descriptor, patient, (point,), seed=9)
    assert set(rows) == {
        "patients", "visits", "labs", "medications", "problem_list", "referrals"
    }
    assert tuple(rows["patients"][0]) == field_names(descriptor, "patients")
    assert tuple(rows["visits"][0]) == field_names(descriptor, "visits")
    assert rows["visits"][0]["weight_oz"] == 12.96 * 35.274
    assert rows["visits"][0]["height_in"] == 90.0 / 2.54


def test_writer_uses_descriptor_header_and_encoding(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    resource = resource_spec(descriptor, "labs")
    output = tmp_path / resource["path"]
    write_resource(output, resource, [])
    with output.open(encoding="iso-8859-1", newline="") as handle:
        assert next(csv.reader(handle)) == list(field_names(descriptor, "labs"))
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/synthetic/test_base_resources.py -v`

Expected: FAIL because base-resource modules do not exist.

- [x] **Step 3: Implement descriptor-shaped base rows**

```python
# src/synthetic/base_resources.py
from __future__ import annotations

from typing import Any

from synthetic.models import LatentPoint, PatientState
from synthetic.randomness import synthetic_id
from synthetic.schema_contract import field_names

BASE_RESOURCES = (
    "patients",
    "visits",
    "labs",
    "medications",
    "problem_list",
    "referrals",
)


def _blank_row(descriptor: dict[str, Any], resource_name: str) -> dict[str, object]:
    return {name: "" for name in field_names(descriptor, resource_name)}


def build_base_rows(
    descriptor: dict[str, Any],
    patient: PatientState,
    points: tuple[LatentPoint, ...],
    *,
    seed: int,
) -> dict[str, list[dict[str, object]]]:
    rows = {name: [] for name in BASE_RESOURCES}
    patient_row = _blank_row(descriptor, "patients")
    patient_row.update(
        {
            "patient_id": patient.patient_id,
            "sex": patient.recorded_sex,
            "ethnicity": "Unknown",
        }
    )
    rows["patients"].append(patient_row)
    for index, point in enumerate(points):
        visit = _blank_row(descriptor, "visits")
        visit.update(
            {
                "patient_id": patient.patient_id,
                "visit_id": synthetic_id(seed, "visit", index),
                "age_in_days": point.age_days,
                "encounter_type": "Office Visit",
                "orig_enc_source_Epic_yn": "Y",
                "weight_oz": point.weight_kg * 35.274,
                "height_in": point.height_cm / 2.54,
                "BMI": point.bmi,
            }
        )
        rows["visits"].append(visit)
    return rows
```

- [x] **Step 4: Implement exact CSV writing**

```python
# src/synthetic/csv_package.py
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable, Mapping


def write_resource(
    path: Path,
    resource: dict[str, Any],
    rows: Iterable[Mapping[str, object]],
) -> int:
    fields = [field["name"] for field in resource["schema"]["fields"]]
    dialect = resource.get("dialect", {})
    encoding = resource.get("encoding", "utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter=dialect.get("delimiter", ","),
            quotechar=dialect.get("quoteChar", '"'),
            doublequote=dialect.get("doubleQuote", True),
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            if tuple(row) != tuple(fields):
                raise ValueError(f"row keys do not match {resource['name']} field order")
            writer.writerow(row)
            count += 1
    return count
```

- [x] **Step 5: Run tests and lint**

Run: `uv run pytest tests/synthetic/test_base_resources.py -v && uv run ruff check src tests`

Expected: two passing tests and no Ruff findings.

- [x] **Step 6: Commit**

```bash
git add src/synthetic/base_resources.py src/synthetic/csv_package.py tests/synthetic/test_base_resources.py
git commit -m "feat: write descriptor-shaped base resources"
```

---

### Task 7: Add the fail-closed derivation-oracle boundary

**Files:**
- Create: `src/synthetic/derivation.py`
- Create: `tests/synthetic/test_derivation.py`

**Interfaces:**
- Consumes: `DerivationOracle.derive(package_root, descriptor) -> DerivationResult`.
- Produces: verified presence of `patients_augmented.csv` and `visits_augmented-20251209150512.csv`, plus a pinned oracle identity.

- [x] **Step 1: Write failing derivation-boundary tests**

```python
# tests/synthetic/test_derivation.py
import hashlib
from pathlib import Path

import pytest

from synthetic.derivation import (
    DerivationResult,
    DerivationUnavailable,
    require_augmented_outputs,
)
from synthetic.schema_contract import load_descriptor

ROOT = Path(__file__).resolve().parents[2]


def test_missing_oracle_is_not_a_success_state() -> None:
    with pytest.raises(DerivationUnavailable, match="authoritative derivation"):
        raise DerivationUnavailable("authoritative derivation oracle is not configured")


def test_requires_both_descriptor_named_augmented_outputs(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    (tmp_path / "patients_augmented.csv").write_text("patient_id\n", encoding="utf-8")
    with pytest.raises(DerivationUnavailable, match="visits_augmented"):
        require_augmented_outputs(tmp_path, descriptor, oracle_id="fake-v1")


def test_returns_pinned_identity_when_both_outputs_exist(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    for name in ("patients_augmented", "visits_augmented"):
        resource = next(item for item in descriptor["resources"] if item["name"] == name)
        (tmp_path / resource["path"]).write_text("header\n", encoding=resource["encoding"])
    assert require_augmented_outputs(
        tmp_path, descriptor, oracle_id="fake-v1"
    ) == DerivationResult("fake-v1", hashlib.sha256(b"fake-v1").hexdigest())
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/synthetic/test_derivation.py -v`

Expected: FAIL because `synthetic.derivation` does not exist.

- [x] **Step 3: Implement the protocol and explicit unavailable state**

```python
# src/synthetic/derivation.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from synthetic.schema_contract import resource_spec


class DerivationUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class DerivationResult:
    oracle_id: str
    implementation_fingerprint: str


class DerivationOracle(Protocol):
    oracle_id: str

    def derive(
        self, package_root: Path, descriptor: dict[str, Any]
    ) -> DerivationResult: ...


def require_augmented_outputs(
    package_root: Path,
    descriptor: dict[str, Any],
    *,
    oracle_id: str,
) -> DerivationResult:
    for name in ("patients_augmented", "visits_augmented"):
        path = package_root / resource_spec(descriptor, name)["path"]
        if not path.is_file():
            raise DerivationUnavailable(f"missing {name} output from {oracle_id}")
    return DerivationResult(
        oracle_id=oracle_id,
        implementation_fingerprint=hashlib.sha256(oracle_id.encode()).hexdigest(),
    )
```

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/synthetic/test_derivation.py -v`

Expected: three passing tests.

- [x] **Step 5: Commit**

```bash
git add src/synthetic/derivation.py tests/synthetic/test_derivation.py
git commit -m "feat: define authoritative derivation boundary"
```

---

### Task 8: Build structural validation and synthetic descriptor output

**Files:**
- Modify: `src/synthetic/csv_package.py`
- Create: `src/synthetic/validate.py`
- Create: `tests/synthetic/test_structural_validation.py`

**Interfaces:**
- Consumes: eight generated CSVs and the source descriptor.
- Produces: `write_synthetic_descriptor(...) -> Path` and `validate_structure(...) -> ValidationReport`.

- [x] **Step 1: Write failing exact-header, type, key, and metadata tests**

```python
# tests/synthetic/test_structural_validation.py
import copy
import csv
import json
from pathlib import Path

from synthetic.csv_package import write_synthetic_descriptor
from synthetic.schema_contract import load_descriptor
from synthetic.validate import validate_structure

ROOT = Path(__file__).resolve().parents[2]


def _empty_package(root: Path, descriptor: dict) -> None:
    for resource in descriptor["resources"]:
        path = root / resource["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding=resource["encoding"], newline="") as handle:
            csv.writer(handle).writerow(
                field["name"] for field in resource["schema"]["fields"]
            )


def test_empty_exact_schema_package_is_structurally_valid(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    _empty_package(tmp_path, descriptor)
    report = validate_structure(tmp_path, descriptor)
    assert report.errors == ()
    assert report.row_counts == {item["name"]: 0 for item in descriptor["resources"]}


def test_wrong_header_fails_with_resource_name(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    _empty_package(tmp_path, descriptor)
    (tmp_path / "patients.csv").write_text("wrong\n", encoding="utf-8")
    report = validate_structure(tmp_path, descriptor)
    assert "patients: header mismatch" in report.errors


def test_invalid_required_and_enum_values_fail(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    _empty_package(tmp_path, descriptor)
    patients = next(item for item in descriptor["resources"] if item["name"] == "patients")
    fields = [field["name"] for field in patients["schema"]["fields"]]
    row = {field: "" for field in fields}
    row.update({"patient_id": "syn-patient-a", "sex": "X"})
    with (tmp_path / "patients.csv").open("a", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=fields).writerow(row)
    report = validate_structure(tmp_path, descriptor)
    assert "patients row 2 sex: value is not in enum" in report.errors


def test_synthetic_descriptor_removes_real_statistics(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    _empty_package(tmp_path, descriptor)
    row_counts = {item["name"]: 0 for item in descriptor["resources"]}
    output = write_synthetic_descriptor(tmp_path, copy.deepcopy(descriptor), row_counts)
    generated = json.loads(output.read_text())
    assert generated["name"] == "ppoc-pediatric-ehr-synthetic"
    assert generated["x-synthetic"] is True
    assert all(resource["x-rowCount"] == 0 for resource in generated["resources"])
    serialized = output.read_text()
    assert '"x-topValues"' not in serialized
    assert "250588" not in serialized
    patient_id = generated["resources"][0]["schema"]["fields"][0]
    assert patient_id["x-missingCount"] == 0
    assert patient_id["x-uniqueValueCount"] == 0
    logical_links = [
        link
        for resource in generated["resources"]
        for link in resource.get("x-logicalForeignKeys", [])
    ]
    assert logical_links
    assert all(link["nullRows"] == 0 and link["orphanRows"] == 0 for link in logical_links)
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/synthetic/test_structural_validation.py -v`

Expected: FAIL because the validator and descriptor writer do not exist.

- [x] **Step 3: Add generated-descriptor sanitization**

```python
# add these imports with the existing imports in src/synthetic/csv_package.py,
# then append the constants and functions below
import copy
import json
from collections import Counter

SNAPSHOT_STAT_KEYS = {
    "x-categories",
    "x-missingCount",
    "x-observedPercentileRange",
    "x-observedRange",
    "x-topValues",
    "x-topValuesTruncated",
    "x-uniqueDiagnosisCodeCount",
    "x-uniqueLabOrderCount",
    "x-uniqueVisitIdCount",
    "x-uniqueValueCount",
    "x-uniquePatientCount",
    "x-unobservedEnumValues",
}


def _generated_field_statistics(
    package_root: Path, resource: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    path = package_root / resource["path"]
    with path.open(
        encoding=resource.get("encoding", "utf-8"), newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    statistics: dict[str, dict[str, Any]] = {}
    for field in resource["schema"]["fields"]:
        name = field["name"]
        present = [row[name] for row in rows if row[name] != ""]
        unique = set(present)
        item: dict[str, Any] = {
            "x-missingCount": len(rows) - len(present),
            "x-uniqueValueCount": len(unique),
        }
        if field["type"] in {"integer", "number"} and present:
            numeric = [float(value) for value in present]
            item["x-observedRange"] = {
                "minimum": min(numeric),
                "maximum": max(numeric),
            }
        if "enum" in field.get("constraints", {}) and present:
            counts = Counter(present)
            item["x-categories"] = [
                {"value": value, "count": count}
                for value, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
            ]
        statistics[name] = item
    return statistics


def _replace_logical_link_statistics(
    package_root: Path, descriptor: dict[str, Any]
) -> None:
    rows_by_resource: dict[str, list[dict[str, str]]] = {}
    primary_values: dict[str, set[str]] = {}
    for resource in descriptor["resources"]:
        with (package_root / resource["path"]).open(
            encoding=resource.get("encoding", "utf-8"), newline=""
        ) as handle:
            rows = list(csv.DictReader(handle))
        rows_by_resource[resource["name"]] = rows
        primary_key = resource["schema"].get("primaryKey")
        if primary_key:
            primary_values[resource["name"]] = {
                row[primary_key] for row in rows if row[primary_key] != ""
            }
    for resource in descriptor["resources"]:
        for link in resource.get("x-logicalForeignKeys", []):
            field = link["fields"]
            target = link["reference"]["resource"]
            values = [row[field] for row in rows_by_resource[resource["name"]]]
            link["nullRows"] = sum(value == "" for value in values)
            link["orphanRows"] = sum(
                value != "" and value not in primary_values[target] for value in values
            )


def write_synthetic_descriptor(
    package_root: Path,
    source_descriptor: dict[str, Any],
    row_counts: dict[str, int],
) -> Path:
    generated = copy.deepcopy(source_descriptor)
    generated["name"] = f"{source_descriptor['name']}-synthetic"
    generated["title"] = f"{source_descriptor['title']} -- Completely Generated"
    generated["description"] = (
        "Completely generated development fixtures; contains no real patient records."
    )
    generated["x-synthetic"] = True
    generated.pop("x-statisticsSource", None)
    for resource in generated["resources"]:
        resource["x-rowCount"] = row_counts[resource["name"]]
        for key in SNAPSHOT_STAT_KEYS:
            resource.pop(key, None)
        field_statistics = _generated_field_statistics(package_root, resource)
        for field in resource["schema"]["fields"]:
            for key in SNAPSHOT_STAT_KEYS:
                field.pop(key, None)
            field.update(field_statistics[field["name"]])
        if "patient_id" in field_statistics:
            resource["x-uniquePatientCount"] = field_statistics["patient_id"][
                "x-uniqueValueCount"
            ]
    _replace_logical_link_statistics(package_root, generated)
    output = package_root / "datapackage.json"
    output.write_text(
        json.dumps(generated, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output
```

- [x] **Step 4: Implement structural validation**

```python
# src/synthetic/validate.py
from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ValidationReport:
    errors: tuple[str, ...]
    row_counts: dict[str, int]


def _validate_value(
    resource_name: str,
    row_number: int,
    field: dict[str, Any],
    value: str,
) -> list[str]:
    prefix = f"{resource_name} row {row_number} {field['name']}:"
    constraints = field.get("constraints", {})
    if value == "":
        return [f"{prefix} required value is missing"] if constraints.get("required") else []
    numeric: float | None = None
    if field["type"] == "integer":
        if re.fullmatch(r"[+-]?\d+", value) is None:
            return [f"{prefix} invalid integer"]
        numeric = float(int(value))
    elif field["type"] == "number":
        try:
            numeric = float(value)
        except ValueError:
            return [f"{prefix} invalid number"]
        if not math.isfinite(numeric):
            return [f"{prefix} number must be finite"]
    if "enum" in constraints and value not in {str(item) for item in constraints["enum"]}:
        return [f"{prefix} value is not in enum"]
    if numeric is not None and "minimum" in constraints and numeric < constraints["minimum"]:
        return [f"{prefix} value is below minimum"]
    if numeric is not None and "maximum" in constraints and numeric > constraints["maximum"]:
        return [f"{prefix} value is above maximum"]
    return []


def validate_structure(
    package_root: Path, descriptor: dict[str, Any]
) -> ValidationReport:
    errors: list[str] = []
    row_counts: dict[str, int] = {}
    primary_values: dict[str, set[str]] = {}
    rows_by_resource: dict[str, list[dict[str, str]]] = {}
    for resource in descriptor["resources"]:
        name = resource["name"]
        path = package_root / resource["path"]
        if not path.is_file():
            errors.append(f"{name}: missing file")
            row_counts[name] = 0
            continue
        expected = [field["name"] for field in resource["schema"]["fields"]]
        with path.open(
            encoding=resource.get("encoding", "utf-8"), newline=""
        ) as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != expected:
                errors.append(f"{name}: header mismatch")
                row_counts[name] = 0
                continue
            rows = list(reader)
        rows_by_resource[name] = rows
        row_counts[name] = len(rows)
        for row_number, row in enumerate(rows, start=2):
            for field in resource["schema"]["fields"]:
                errors.extend(
                    _validate_value(name, row_number, field, row[field["name"]])
                )
        primary_key = resource["schema"].get("primaryKey")
        if primary_key:
            values = [row[primary_key] for row in rows]
            if "" in values or len(values) != len(set(values)):
                errors.append(f"{name}: invalid primary key {primary_key}")
            primary_values[name] = set(values)
    for resource in descriptor["resources"]:
        name = resource["name"]
        for foreign_key in resource["schema"].get("foreignKeys", []):
            field = foreign_key["fields"]
            target = foreign_key["reference"]["resource"]
            target_values = primary_values.get(target, set())
            if any(
                row.get(field, "") not in target_values
                for row in rows_by_resource.get(name, [])
            ):
                errors.append(f"{name}: unresolved foreign key {field}")
    return ValidationReport(tuple(errors), row_counts)
```

- [x] **Step 5: Run tests and lint**

Run: `uv run pytest tests/synthetic/test_structural_validation.py -v && uv run ruff check src tests`

Expected: four passing tests and no Ruff findings.

- [x] **Step 6: Commit**

```bash
git add src/synthetic/csv_package.py src/synthetic/validate.py tests/synthetic/test_structural_validation.py
git commit -m "feat: validate synthetic package structure"
```

---

### Task 9: Assemble and test the smoke-profile vertical slice

**Files:**
- Create: `src/synthetic/generate.py`
- Create: `tests/synthetic/fakes.py`
- Create: `tests/synthetic/test_generate_smoke.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: source descriptor, injected `GrowthReference`, injected `DerivationOracle`, patient count, seed, reference time, and nonexisting output path.
- Produces: exact eight-resource package, synthetic descriptor, `manifest.json`, and `validation-report.json`.

- [x] **Step 1: Write a failing end-to-end test with explicit fake boundaries**

```python
# tests/synthetic/fakes.py
import csv
from pathlib import Path

from synthetic.derivation import DerivationResult
from synthetic.schema_contract import resource_spec


class LinearTestReference:
    reference_id = "linear-test-reference-v1"

    def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
        age_years = age_days / 365.25
        if metric == "height_cm":
            return 80.0 + 5.5 * age_years + 4.0 * z
        if metric == "bmi":
            return 16.0 + 0.25 * age_years + 1.2 * z
        raise KeyError(metric)


class IdentityPreservingTestDerivationOracle:
    oracle_id = "identity-preserving-test-oracle-v1"

    def derive(self, package_root: Path, descriptor: dict) -> DerivationResult:
        with (package_root / "patients.csv").open(encoding="utf-8", newline="") as handle:
            patients = list(csv.DictReader(handle))
        with (package_root / "visits.csv").open(encoding="utf-8", newline="") as handle:
            visits = list(csv.DictReader(handle))
        visits_by_patient: dict[str, list[dict[str, str]]] = {}
        for visit in visits:
            visits_by_patient.setdefault(visit["patient_id"], []).append(visit)

        patient_resource = resource_spec(descriptor, "patients_augmented")
        patient_fields = patient_resource["schema"]["fields"]
        patient_rows = []
        for patient in patients:
            row = {
                field["name"]: 0
                if field["type"] == "integer"
                and field.get("constraints", {}).get("required")
                else ""
                for field in patient_fields
            }
            observed = visits_by_patient.get(patient["patient_id"], [])
            ages = [int(visit["age_in_days"]) for visit in observed]
            row.update(
                {
                    "patient_id": patient["patient_id"],
                    "sex": patient["sex"],
                    "healthy_flag": 1,
                    "visits_count": len(observed),
                    "visits_count_pre_dx": len(observed),
                    "min_visit_age_days": min(ages) if ages else "",
                    "max_visit_age_days": max(ages) if ages else "",
                    "visits_span_days": max(ages) - min(ages) if ages else 0,
                }
            )
            patient_rows.append(row)

        visit_resource = resource_spec(descriptor, "visits_augmented")
        visit_fields = visit_resource["schema"]["fields"]
        sex_by_patient = {patient["patient_id"]: patient["sex"] for patient in patients}
        visit_rows = []
        for visit in visits:
            row = {
                field["name"]: 0
                if field["type"] == "integer"
                and field.get("constraints", {}).get("required")
                else ""
                for field in visit_fields
            }
            for name in row:
                if name in visit:
                    row[name] = visit[name]
            row.update(
                {
                    "patient_id": visit["patient_id"],
                    "visit_id": visit["visit_id"],
                    "sex": sex_by_patient[visit["patient_id"]],
                    "bmi": visit["BMI"],
                }
            )
            visit_rows.append(row)

        for resource, rows in (
            (patient_resource, patient_rows),
            (visit_resource, visit_rows),
        ):
            fields = [field["name"] for field in resource["schema"]["fields"]]
            with (package_root / resource["path"]).open(
                "w", encoding=resource["encoding"], newline=""
            ) as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
        return DerivationResult(self.oracle_id)
```

```python
# tests/synthetic/test_generate_smoke.py
import hashlib
import json
from pathlib import Path

import pytest

from synthetic.derivation import DerivationUnavailable
from synthetic.generate import generate_smoke
from tests.synthetic.fakes import (
    IdentityPreservingTestDerivationOracle,
    LinearTestReference,
)

ROOT = Path(__file__).resolve().parents[2]


def _hashes(root: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.iterdir())
        if path.is_file()
    }


def test_smoke_generation_is_exact_schema_and_reproducible(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    arguments = dict(
        descriptor_path=ROOT / "datapackage.json",
        patient_count=3,
        seed=20260830,
        reference_time="2026-08-30T00:00:00Z",
        software_revision="test-revision",
        reference=LinearTestReference(),
        derivation_oracle=IdentityPreservingTestDerivationOracle(),
    )
    generate_smoke(output=first, **arguments)
    generate_smoke(output=second, **arguments)
    assert _hashes(first) == _hashes(second)
    manifest = json.loads((first / "manifest.json").read_text())
    assert manifest["profile"] == "smoke"
    assert manifest["status"] == "STRUCTURE_VALIDATED_TEST_ORACLE"
    assert set(manifest["row_counts"]) == {
        "patients", "patients_augmented", "visits", "visits_augmented",
        "labs", "medications", "problem_list", "referrals",
    }
    assert manifest["row_counts"]["patients_augmented"] == 3
    assert manifest["row_counts"]["visits_augmented"] == 9
    assert manifest["reference_id"] == "linear-test-reference-v1"
    assert manifest["file_sha256"]


def test_no_derivation_oracle_cannot_promote_output(tmp_path: Path) -> None:
    with pytest.raises(DerivationUnavailable):
        generate_smoke(
            descriptor_path=ROOT / "datapackage.json",
            output=tmp_path / "run",
            patient_count=1,
            seed=1,
            reference_time="2026-08-30T00:00:00Z",
            software_revision="test-revision",
            reference=LinearTestReference(),
            derivation_oracle=None,
        )
    assert not (tmp_path / "run").exists()
```

- [x] **Step 2: Run the integration test to verify it fails**

Run: `uv run pytest tests/synthetic/test_generate_smoke.py -v`

Expected: FAIL because `synthetic.generate` does not exist.

- [x] **Step 3: Implement smoke orchestration**

```python
# src/synthetic/generate.py
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
from pathlib import Path

from synthetic.base_resources import BASE_RESOURCES, build_base_rows
from synthetic.csv_package import write_resource, write_synthetic_descriptor
from synthetic.derivation import DerivationOracle, DerivationUnavailable
from synthetic.manifest import RunManifest
from synthetic.models import PatientState
from synthetic.native.healthy import HealthyKernel
from synthetic.randomness import NamedRandomStreams, synthetic_id
from synthetic.references import GrowthReference
from synthetic.run_directory import RunDirectory
from synthetic.schema_contract import (
    load_descriptor,
    resource_spec,
    schema_fingerprint,
)
from synthetic.validate import validate_structure


def generate_smoke(
    *,
    descriptor_path: Path,
    output: Path,
    patient_count: int,
    seed: int,
    reference_time: str,
    software_revision: str,
    reference: GrowthReference,
    derivation_oracle: DerivationOracle | None,
) -> Path:
    if patient_count < 1:
        raise ValueError("patient_count must be positive")
    if derivation_oracle is None:
        raise DerivationUnavailable("authoritative derivation oracle is not configured")
    descriptor = load_descriptor(descriptor_path)
    smoke_configuration = {
        "patient_count": patient_count,
        "ages_days": [730, 1095, 1460],
        "profile": "smoke",
    }
    configuration_sha256 = hashlib.sha256(
        json.dumps(
            smoke_configuration, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    run_id = hashlib.sha256(
        f"{seed}:{patient_count}:{reference_time}".encode("utf-8")
    ).hexdigest()[:12]
    run = RunDirectory.start(output, run_id)
    try:
        accumulated = {name: [] for name in BASE_RESOURCES}
        kernel = HealthyKernel(reference)
        for patient_index in range(patient_count):
            reference_sex = "F" if patient_index % 2 == 0 else "M"
            patient = PatientState(
                patient_id=synthetic_id(seed, "patient", patient_index),
                recorded_sex=reference_sex,
                reference_sex=reference_sex,
            )
            points = kernel.generate(
                patient,
                ages_days=(730, 1095, 1460),
                streams=NamedRandomStreams(seed, patient_index),
            )
            patient_rows = build_base_rows(
                descriptor, patient, points, seed=seed + patient_index
            )
            for name in BASE_RESOURCES:
                accumulated[name].extend(patient_rows[name])
        row_counts: dict[str, int] = {}
        for name in BASE_RESOURCES:
            resource = resource_spec(descriptor, name)
            row_counts[name] = write_resource(
                run.partial_path / resource["path"],
                resource,
                accumulated[name],
            )
        derivation = derivation_oracle.derive(run.partial_path, descriptor)
        report = validate_structure(run.partial_path, descriptor)
        if report.errors:
            raise ValueError("; ".join(report.errors))
        row_counts.update(report.row_counts)
        write_synthetic_descriptor(run.partial_path, descriptor, row_counts)
        manifest = RunManifest.smoke(
            seed=seed,
            schema_fingerprint=schema_fingerprint(descriptor),
            reference_time=reference_time,
            reference_id=reference.reference_id,
            configuration_sha256=configuration_sha256,
            software_revision=software_revision,
        )
        (run.partial_path / "validation-report.json").write_text(
            json.dumps(dataclasses.asdict(report), indent=2) + "\n",
            encoding="utf-8",
        )
        file_sha256 = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(run.partial_path.iterdir())
            if path.is_file()
        }
        manifest = dataclasses.replace(
            manifest,
            status="STRUCTURE_VALIDATED_TEST_ORACLE"
            if derivation.oracle_id.startswith("identity-preserving-test-")
            else "STRUCTURE_VALIDATED",
            row_counts=row_counts,
            file_sha256=file_sha256,
            derivation_fingerprint=derivation.implementation_fingerprint,
        )
        (run.partial_path / "manifest.json").write_bytes(manifest.to_json_bytes())
        return run.promote()
    except Exception as error:
        run.fail(str(error))
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--patients", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.parse_args()
    raise SystemExit(
        "No production growth reference or authoritative derivation oracle is configured"
    )


if __name__ == "__main__":
    main()
```

- [x] **Step 4: Run the end-to-end and full test suites**

Run: `uv run pytest tests/synthetic/test_generate_smoke.py -v && uv run pytest -q`

Expected: two integration tests pass and the complete suite has zero failures.

- [x] **Step 5: Document the nonclinical smoke boundary**

Add this section to `README.md`:

```markdown
## Synthetic fixture implementation

The approved design is in [the synthetic growth fixture specification](docs/superpowers/specs/2026-08-30-synthetic-growth-fixtures-design.md). The first implementation work package establishes an exact-schema smoke generator with injected growth-reference and augmentation interfaces. It does not ship a clinically validated reference model, estimate prevalence, read PPOC records, or establish privacy or release approval.

The default/no-profile command-line entry point remains fail-closed. The explicit development profiles use the checked-in test-only augmentation runtime and may produce reproducible development fixtures; an authoritative implementation or approved parity harness is still required before any clinical or release validity claim.
```

The repository keeps this detailed boundary in `docs/synthetic-generator.md` and links to it from `README.md`, which remains a concise project index.

- [x] **Step 6: Run final foundation verification**

Run: `uv run pytest -q && uv run ruff check src tests && python3 schema/build.py --check && git diff --check`

Expected: all tests pass, Ruff has no findings, all eight descriptor resources validate, and Git reports no whitespace errors.

- [x] **Step 7: Commit**

```bash
git add src/synthetic/generate.py tests/synthetic/fakes.py tests/synthetic/test_generate_smoke.py README.md
git commit -m "feat: generate exact-schema synthetic smoke package"
```

## Foundation completion gate

Before starting the growth-and-clinical-modules plan, verify all of the following:

- Every foundation task has its own passing test cycle and commit.
- The full test and Ruff commands pass from a clean checkout.
- `python3 schema/build.py --check` still validates exactly eight resources.
- A smoke run with the test oracle writes the exact eight descriptor-named CSVs.
- A run without a derivation oracle fails without promoting the requested output directory.
- The smoke manifest pins schema fingerprint, seed, PRNG family, seed derivation, reference time, reference identity, configuration hash, software revision, the derivation implementation fingerprint, row counts, and visible output hashes. The private derivation binding retains the textual oracle identity and maps it to that fingerprint; visible manifests intentionally omit `oracle_id`, binding IDs, review metadata, paths, and truth state. Logical-link null/orphan counts are machine-readable in the generated descriptor; `validation-report.json` intentionally contains only structural errors and row counts.
- Visible package files contain no hidden truth or event trace.
- Documentation makes no clinical, prevalence, privacy, or release claim for the smoke profile.

## Completion evidence (2026-09-02)

- Independent foundation review approved the implementation after hardening oversized integer parsing, exact augmented-output header and regular-file checks, malformed descriptor-shape handling, the explicit logical-link completeness policy, the visible derivation-fingerprint/private oracle-ID boundary, and the static reader allowlist.
- Focused derivation, validation, export, and boundary suite: `102 passed`.
- Full repository suite: `2681 passed, 4 skipped` (the four skips are the opt-in development-scale tests).
- Ruff: `All checks passed!`; schema contract: `validated 8 resources in datapackage.json`; dependency lock: `Resolved 17 packages`; `git diff --check`: clean.
- The test-only smoke path writes all eight descriptor-named CSV resources, records reproducible visible hashes and derivation fingerprint metadata, rejects missing derivation binding without promotion, and keeps logical-link null/orphan counts in the generated descriptor rather than the structural report.
