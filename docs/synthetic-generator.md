# Synthetic generator

This guide describes the exact-schema synthetic smoke generator in this repository. It is a development and integration harness for completely generated records; it is not a clinically validated simulator, a prevalence-calibrated cohort, a privacy audit, or a release-approved fixture.

## Current scope

The current vertical slice generates healthy patients aged two years and older. It produces three deterministic measurement visits per patient at ages 730, 1095, and 1460 days. Height and BMI are the two generated anthropometric dimensions; weight is derived from them. The smoke profile alternates recorded/reference sex across patients only to exercise the schema. It does not yet model growth-disorder states, disorder prevalence, calibrated demographics, infancy, puberty, or clinical events.

The generator reads `datapackage.json` as schema metadata only. It does not read the repository's real CSV snapshots or any patient records. The current command-line entry point intentionally fails closed because no production growth reference or authoritative augmentation oracle is shipped.

## Development-only latent growth-disorder modules

The latent trajectory layer is a development and evaluator harness, not a clinical model. It applies a directionally coherent, uncalibrated scenario module to the existing healthy kernel while keeping hidden truth and event traces separate from observable descendants. For example, using the injected test reference already used by the tests:

```python
from synthetic.models import PatientState
from synthetic.native.clinical_modules import FamilialShortStatureModule
from synthetic.native.healthy import HealthyKernel
from synthetic.native.trajectories import DisorderTrajectoryKernel
from synthetic.randomness import NamedRandomStreams
from tests.synthetic.fakes import LinearTestReference

kernel = DisorderTrajectoryKernel(
    HealthyKernel(LinearTestReference()), FamilialShortStatureModule()
)
trajectory = kernel.generate(
    PatientState("synthetic-patient", "F", "F"),
    (730, 1095, 1460),
    NamedRandomStreams(20260830, 0),
)
```

The available modules and their directional signatures are:

- `HealthyGrowthModule`: Δheight-z = 0; ΔBMI-z = 0.
- `FamilialShortStatureModule`: constant negative Δheight-z; ΔBMI-z = 0.
- `ConstitutionalDelayModule`: bounded temporary negative Δheight-z with recovery; ΔBMI-z = 0.
- `GrowthHormoneDeficiencyModule`: progressive negative Δheight-z, nonnegative BMI-z during impairment, and an optional treatment response.

These defaults are uncalibrated development scenarios. `LatentTrajectory.disorder` and `LatentTrajectory.events` are evaluator-only hidden truth and event traces; they are not exported, and visible CSV generation remains unchanged. Prevalence, demographic calibration, disorder-critical labs/medications/referrals, held-out validation, and privacy auditing remain later gates. No real patient data, clinical claim, or privacy claim is introduced by this layer.

## Prerequisites

Run these commands from the repository root:

```sh
uv sync
```

The package requires Python 3.12 or newer. The test-only reference and derivation oracle used in the example below live under `tests/synthetic/fakes.py`; they are safe for smoke tests but must not be presented as clinical or privacy evidence.

## Run the smoke profile from Python

`generate_smoke` requires an injected `GrowthReference`, an injected `DerivationOracle`, and an externally trusted derivation fingerprint/classification. The output path must not already exist.

```python
import tempfile
from pathlib import Path

from synthetic.generate import generate_smoke
from tests.synthetic.fakes import (
    IdentityPreservingTestDerivationOracle,
    LinearTestReference,
)

repository = Path.cwd()
oracle = IdentityPreservingTestDerivationOracle()
output = Path(tempfile.mkdtemp(prefix="ppoc-synthetic-")) / "smoke"

promoted = generate_smoke(
    descriptor_path=repository / "datapackage.json",
    output=output,
    patient_count=10,
    seed=20260830,
    reference_time="2026-08-30T00:00:00Z",
    software_revision="local-smoke",
    reference=LinearTestReference(),
    derivation_oracle=oracle,
    trusted_derivation_fingerprint="0123456789abcdef" * 4,
    trusted_derivation_test_only=True,
)
print(promoted)
```

The trusted fingerprint and `trusted_derivation_test_only` value must come from configuration outside the oracle result. The generator rejects a mismatch, an invalid/non-lowercase SHA-256 fingerprint, a placeholder all-zero fingerprint, or a non-boolean classification. The test oracle's fixed fingerprint is intentionally visible test metadata, not a production identity.

## Oracle and reference contracts

An approved growth reference implements:

```python
value(metric, age_days, reference_sex, z) -> float
```

The foundation requests `height_cm` and `bmi` values. A derivation oracle implements `derive(package_root, descriptor)` and returns `DerivationResult(oracle_id, implementation_fingerprint, test_only)`. The oracle must create the two descriptor-named augmented CSVs: `patients_augmented.csv` and `visits_augmented-20251209150512.csv`.

For a future authoritative oracle, pin the implementation fingerprint through reviewed configuration and set `test_only=False` only after the appropriate parity, clinical, and release gates have passed. Adding a Synthea module is an optional future adapter; this repository currently exposes the engine-neutral protocol, not a Synthea implementation.

### Supplying an approved LMS reference

The reference layer is an input contract. Supply an approved, public LMS artifact from outside this repository; do not add patient rows or other real clinical data. The CSV header must contain exactly these six columns, in any order: `metric`, `age_days`, `reference_sex`, `l`, `m`, `s`. Each row supplies one metric/sex/age point, with nonnegative integer `age_days` and numeric `l`, `m`, and `s`; `m` and `s` must be finite and positive. The loader records the SHA-256 of the exact file bytes. Pin it at load time with `expected_sha256`, which must be a lowercase 64-character hexadecimal SHA-256 digest; the loader enforces that exact format and rejects a changed artifact.

```python
from pathlib import Path

from synthetic.references import LmsGrowthReference

reference = LmsGrowthReference.from_csv(
    Path("approved-growth-lms.csv"),
    reference_id="approved-public-growth-v1",
    expected_sha256="0123456789abcdef" * 4,
)
```

The domain is determined by the rows supplied for each `(metric, reference_sex)` pair. Requests must use a supported metric and reference sex and an integer age within that pair's minimum and maximum ages; ages between rows are linearly interpolated in the LMS parameters, while ages outside the domain are rejected. The resulting LMS value must be finite and positive. A table-backed reference is not, by itself, clinical validation, prevalence validation, or privacy validation; those require separate approved evidence and governance.

## Output layout

A successful run promotes the partial directory to the requested output path and contains exactly these eight descriptor-named CSV resources plus metadata:

```text
smoke/
├── patients.csv
├── patients_augmented.csv
├── visits.csv
├── visits_augmented-20251209150512.csv
├── labs.csv
├── medications.csv
├── problem_list.csv
├── referrals.csv
├── datapackage.json
├── validation-report.json
└── manifest.json
```

All CSV headers, field order, dialects, encodings, constraints, keys, and logical links come from the source descriptor. Ancillary base resources are represented with schema-correct headers and may be empty in this smoke profile. The generated descriptor removes source snapshot statistics and provenance while retaining schema semantics and generated-only statistics.

`validation-report.json` records structural errors and row counts. A successful report has no errors. `manifest.json` records the schema fingerprint, seed, PRNG and seed-derivation versions, reference identity/time, configuration hash, software revision, trusted derivation fingerprint, status, row counts, and SHA-256 hashes for every generated file except the manifest itself. Hash keys are package-relative POSIX paths.

## Safety and failure behavior

The generator is deliberately fail closed:

- It refuses an existing target, partial path, or failed path; it never overwrites an output.
- It validates descriptor resource paths as unique, safe relative paths and reserves control filenames.
- It writes base resources exclusively and uses descriptor-declared encoding/dialect settings.
- It runs the oracle against staged copies of base CSVs and a copied descriptor, checks base hashes, rejects symlinks/special files/unexpected artifacts, and copies only the two expected augmented outputs back into the run.
- It checks the actual partial tree again before validation, so an oracle cannot add hidden files or mutate base resources through a captured path.
- It validates required values, types, enums, ranges, primary keys, declared foreign keys, exact headers, and CSV shape. Intentional logical-link orphans remain allowed.

If a run fails after the partial directory is created, the generator writes `failure.json` and archives the evidence as a sibling path such as `.smoke.<run-id>.failed`. That directory is visibly unvalidated and must not be consumed as a successful fixture. A failed run is not silently retried or overwritten.

## Verify a run and the repository

From the repository root, run:

```sh
uv run pytest -q
uv run ruff check src tests
python3 schema/build.py --check
git diff --check
```

For a generated package, inspect `manifest.json` and `validation-report.json`, then verify that the manifest's relative file hashes match the files on disk. To test reproducibility, generate into two fresh output paths with identical descriptor, seed, reference time, software revision, reference implementation, and trusted oracle configuration, then compare the non-manifest file hashes.

## The command-line entry point

This command currently exits with an explicit unavailable-oracle message after parsing its basic arguments:

```sh
uv run python -m synthetic.generate --output /tmp/ppoc-smoke --patients 10 --seed 20260830
```

That behavior is intentional. Do not treat a command-line failure as a missing flag or bypass the injected-reference/oracle boundary. Wire a reviewed production reference and authoritative oracle through an explicit API/CLI design before enabling it.

## Claims and non-claims

The smoke profile is suitable for exercising schema loaders, joins, deterministic pipelines, counterfactual plumbing, and failure handling. It does not establish that generated trajectories match real growth distributions, that growth-disorder prevalence or demographics are representative, or that downstream clinical decisions are valid.

It also does not demonstrate that a generated patient profile cannot be matched to a real patient. Structural safeguards and synthetic-only inputs reduce accidental leakage, but non-matchability requires a separate privacy evaluation (for example, linkage, attribute-disclosure, and membership-inference testing) under the applicable data-governance process. Do not publish the smoke package as a golden, validated, development, clinical, representative, privacy-safe, or release-approved fixture.
