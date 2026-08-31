# Synthetic generator

This guide describes the exact-schema synthetic smoke generator in this repository. It is a development and integration harness for completely generated records; it is not a clinically validated simulator, a prevalence-calibrated cohort, a privacy audit, or a release-approved fixture.

## Current scope

The current vertical slice generates healthy patients aged two years and older. It produces three deterministic measurement visits per patient at ages 730, 1095, and 1460 days. Height and BMI are the two generated anthropometric dimensions; weight is derived from them. The smoke profile alternates recorded/reference sex across patients only to exercise the schema. It does not yet model growth-disorder states, disorder prevalence, calibrated demographics, infancy, puberty, or clinical events.

The generator reads `datapackage.json` as schema metadata only. It does not read the repository's real CSV snapshots or any patient records. The current command-line entry point intentionally fails closed because no production growth reference or authoritative augmentation oracle is shipped.

The visible smoke example remains the healthy age-730+ profile: three visits at ages 730, 1095, and 1460 days. It does not export latent age-regime state, puberty state, or any other evaluator-only trajectory state. The broader age-regime behavior below is a development-only injected-reference example, not a change to that visible smoke contract.

## Aggregate calibration artifacts (development boundary)

An approved calibration artifact is a disclosure-controlled aggregate from the governed `calibration` partition. Load it only as an aggregate artifact for development review:

```python
from pathlib import Path
from synthetic.calibration import load_calibration_artifact

artifact = load_calibration_artifact(Path("approved-calibration.json"))
print(artifact.artifact_id, len(artifact.strata))
```

Strict keys, types, tokens, support, suppression, and file checks apply; suppressed cells remain null. The loader does not read PPOC CSVs, calibrate prevalence, tune trajectories, validate clinical fidelity, prove non-matchability, or authorize release. Generator consumption, held-out validation, privacy auditing, and an optional Synthea adapter are separate deferred gates.

### Governed aggregate calibration command

Only an authorized operator inside the governed environment may run the offline calibrator against a real snapshot. Every source and policy input is explicit; there is no default data root, environment-variable fallback, hidden-truth input, patient-partition file, or generator-output input:

```sh
uv run python -m synthetic.calibrate \
  --data-root /governed/ppoc-snapshot \
  --descriptor datapackage.json \
  --snapshot approved-snapshot-v1 \
  --artifact-id approved-aggregate-v1 \
  --created-at 2026-08-31T12:00:00Z \
  --partition-policy /governed/partition-policy.json \
  --disclosure-policy /governed/disclosure-policy.json \
  --partition-key-file /governed/partition.key \
  --output /governed/calibration-output
```

The partition key file must be a regular non-symlink file. Its exact bytes are read in memory, must contain at least 16 bytes, and are never copied, serialized, or included in the report. Policy JSON is strict: duplicate or unexpected keys fail the run. The requested output must be new and is promoted only after both canonical files are flushed and reparsed successfully:

```text
calibration-output/
├── calibration-artifact.json
└── calibration-report.json
```

The artifact contains fixed-registry, calibration-partition aggregates for recorded demographics and outcomes, utilization, observation availability and logical-link completeness, and clean age-windowed physiology summaries. Recorded diagnosis flags are observable outcomes, not latent prevalence. Cells below the disclosure policy's minimum support are `suppressed` with null value, support, and denominator; suppression never becomes numeric zero. The separate report has status `AGGREGATES_ONLY` and exposes only aggregate partition/resource totals, target-family and suppression counts, policy identity, checks, and the shared aggregate hash.

Repository CI invokes this path only with the wholly synthetic eight-resource mock package and test key material. No visible generator, CSV exporter, or native trajectory module imports the calibrator, reads its governed input, or consumes the resulting artifact in this slice. The existing generator examples and output contract therefore remain unchanged.

Calibration output is not prevalence validation, representative-cohort evidence, clinical validation, privacy or non-matchability evidence, or release authorization. Held-out fidelity validation, clinical review, privacy auditing, and any future generator-consumption contract remain separate governed gates.

## Patient-disjoint held-out validation

An authorized operator may run the standalone held-out validator only inside the governed environment. It derives the real-data partition privately from the keyed partition policy, compares disclosed aggregate targets from the real `held_out` partition with the complete generated package, and applies a frozen fidelity policy; it does not expose patient rows, identifiers, sequences, or the partition key.

```sh
uv run python -m synthetic.heldout_validate \
  --real-root /governed/ppoc \
  --descriptor /governed/ppoc/datapackage.json \
  --snapshot 2026-08-24 \
  --synthetic-root /fixtures/development-20260830 \
  --calibration-artifact /approved/calibration/calibration-artifact.json \
  --calibration-report /approved/calibration/calibration-report.json \
  --partition-policy /governed/partition-policy.json \
  --disclosure-policy /governed/disclosure-policy.json \
  --partition-key-file /governed/partition.key \
  --frozen-policy /governed/fidelity-policy.json \
  --output /governed/heldout-report
```

Every path is required: there is no default governed data root, descriptor, policy, key, snapshot, or output. Repository CI is synthetic-only: it uses fictional exact-schema packages and test key material, with no real data in CI. Visible generation, export, manifest, and trajectory paths do not import this validator or consume a governed path, key, calibration artifact, or held-out report.

`PASS` means every evaluable disclosed aggregate target met the frozen tolerance. `FAIL` means an evaluable target fell outside that tolerance. `UNEVALUABLE` means a target was suppressed, missing, underpowered, or a required target family had no evaluable cell; it is never treated as zero or `PASS`. `FAIL` and `UNEVALUABLE` both promote their aggregate-only report but return a nonzero gate status, while input or compatibility failures promote no report.

A passing held-out report is limited aggregate fidelity evidence. It is not evidence of growth-disorder prevalence, demographic representativeness, clinical validity, privacy or non-matchability, or release approval. Privacy evaluation, temporal drift, task utility, prevalence evaluation, and a Synthea adapter remain separate deferred gates and require their own approved evidence and governance.

## Governed privacy-audit evidence

An authorized operator may run the standalone privacy auditor only inside the governed environment against a completely generated exact-schema package and an approved frozen privacy policy. Every governed input is explicit; there is no default real-data root, policy, output, held-out package, shadow manifest, control package, or prior-release discovery.

```sh
uv run python -m synthetic.privacy_audit \
  --real-root /governed/calibration \
  --heldout-root /governed/heldout \
  --synthetic-root /fixtures/development-20260830 \
  --policy /governed/approved-risk-policy.json \
  --shadow-manifest /governed/shadow-manifest.json \
  --prior-release-root /governed/prior-release-1 \
  --negative-control-root /governed/independent-control \
  --positive-control-root /governed/copied-control \
  --output /governed/privacy-audit-report
```

The required flags are `--real-root`, `--synthetic-root`, `--policy`, and `--output`; `--prior-release-root` may be repeated. The auditor stages each package in a separate private connection and runs only the fixed policy controls. It writes a new directory containing only `privacy-audit-report.json` and `privacy-audit-summary.txt`, after exclusive writes, fsync, reparse, byte comparison, and non-replacing promotion. Output failures leave only a fixed redacted failure artifact.

The report contains aggregate control metrics, policy identity, counts, statuses, and decision reasons. It never contains patient or visit rows, identifiers, paths, source keys, feature tuples, candidate pairs, distances, private profile hashes, diagnosis values, or undersized cells. `PASS` means all required controls were evaluable and passed; `FAIL` means at least one evaluated control failed; `UNEVALUABLE` means a required control lacked sufficient or valid evidence. Missing optional shadow, prior-release, or control-package evidence is recorded as unevaluable without blocking a policy that does not require it; optional nearest-neighbor and linkage screens still use their fixed reference/permutation fallback when no held-out package is supplied. The CLI returns 0 only for a promoted `PASS` report, 1 for a promoted `FAIL`/`UNEVALUABLE` report or redacted hard failure, and 2 for invalid arguments.

A passing report is qualified, policy-bound privacy evidence only: under the approved recipient, release context, attacker knowledge, controls, and tolerances, it found no measured linkage, membership, or attribute-inference signal above tolerance. It is not a proof of non-matchability or zero risk, a HIPAA de-identification determination, or release authorization. A privacy expert and data custodian remain responsible for release approval. Temporal drift, task utility, prevalence, and Synthea remain separate deferred evidence gates.

## Evaluator-only trajectory counterfactual validation

The native counterfactual layer replays one completely fictional `AgeRegimeDisorderKernel` patient into a baseline world and one intervention world. It is the trajectory component of the counterfactual roadmap: it does not read visible CSV rows, alter the eight-resource descriptor, or turn the fail-closed smoke command into a cohort generator. Package-level counterfactual EHR worlds remain deferred until observation, diagnosis, treatment, and ancillary-resource generation are available.

Use the paired API with a test or separately approved fictional kernel and a new external truth-manifest destination whose parent already exists:

```python
from pathlib import Path

from synthetic.models import PatientState
from synthetic.native.age_regime_disorder import AgeRegimeDisorderKernel
from synthetic.native.age_regimes import AgeRegimeTrajectoryKernel
from synthetic.native.clinical_modules import FamilialShortStatureModule
from synthetic.native.counterfactual import (
    CounterfactualValidationStatus,
    InterventionKind,
    generate_counterfactual_pair,
    validate_counterfactual_pair,
    write_truth_manifest,
)
from tests.synthetic.fakes import RegimeLinearTestReference

patient = PatientState("syn-counterfactual", "F", "F")
kernel = AgeRegimeDisorderKernel(
    AgeRegimeTrajectoryKernel(RegimeLinearTestReference()),
    FamilialShortStatureModule(),
)
pair = generate_counterfactual_pair(
    kernel,
    patient,
    (0, 365, 730, 1460, 1825, 2190, 4000),
    run_seed=20260831,
    patient_index=0,
    intervention=InterventionKind.EARLIER_RECOGNITION,
)
report = validate_counterfactual_pair(pair)
if report.status is not CounterfactualValidationStatus.PASS:
    raise RuntimeError(report.to_mapping())
write_truth_manifest(pair, report, Path("counterfactual-truth.json"))
```

The fixed trajectory matrices support `physiology_severity`, `earlier_recognition`, and `treatment_adherence`. Physiology severity changes only the growth-physiology layer; earlier recognition changes recognition timing and permits the event-trace descendant; treatment adherence changes treatment response and permits post-treatment growth. Utilization-intensity and measurement-error-removal are rejected until the visible observation/resource layer exists. Every matrix names manipulated nodes, permitted descendants, required invariants, reused streams, rejected resampling, and trajectory assertions; callers cannot weaken those fixed semantics.

`validate_counterfactual_pair` returns an aggregate-only report. Each fixed check has status `PASS`, `FAIL`, or `UNEVALUABLE`; the report is `FAIL` if any check fails, otherwise `UNEVALUABLE` when required evidence is missing, otherwise `PASS`. Reports contain only check names, statuses, reason codes, and counts. They do not contain patient IDs, seeds, event payloads, hidden state, layer hashes, stream identities, paths, or candidate links. A `PASS` is evidence that this causal replay contract held for the supplied fictional pair, not clinical efficacy or release evidence.

The minimum growth evidence for a `PASS` is one finite stature z-score (`height_z` or `length_z`) and one finite mass z-score (`bmi_z` or `weight_z`) at every requested point in both worlds. The native kernel supplies those dimensions for each age regime; a missing or partial point is reported as `UNEVALUABLE` with `GROWTH_EVIDENCE_MISSING`, never as a pass. Point-level `GrowthRegime` labels are also compared as part of the invariant age-regime layer, so a sampled state alone cannot hide a label change.

`write_truth_manifest(pair, report, path)` is an explicit evaluator-only boundary. It serializes the hidden patient/state/event trace, causal-layer hashes, and stream identities to canonical JSON outside the visible package. The destination must be a new regular non-symlink file with an existing non-symlink parent; every existing ancestor from the filesystem root through that parent must also be a regular non-symlink directory. The writer opens each ancestor component with `O_NOFOLLOW|O_DIRECTORY` and keeps the final parent descriptor pinned, so an ancestor swap cannot redirect publication or verification. It creates the child directly with descriptor-relative `O_CREAT|O_EXCL|O_NOFOLLOW` mode `0600`, keeps that child descriptor open through size-bounded readback and canonical reparsing, and compares its device/inode identity with the pinned directory entry before closing it. A failed write or verification removes the child only when that identity still belongs to this invocation, so an unlink/recreate race cannot read or remove a replacement and the destination remains available for a retry. Ordinary pair/report mappings and `manifest.json` remain truth-free. Keep the truth manifest in evaluator-controlled storage and do not copy it beside a released fixture package.

This trajectory slice does not establish growth-disorder prevalence, demographic representativeness, observation-error fidelity, temporal drift, task utility, privacy or non-matchability, clinical validity, or release authorization. Those are separate approved gates; a complete exact-schema counterfactual package and an optional Synthea-conforming adapter require their own schema, derivation, longitudinal, causal, utility, and privacy evaluation.

### Development-only age-regime smoke example

When exercising the latent trajectory layer with an injected reference, cover the five `GrowthRegime` classifier regimes: infancy, transition, childhood, puberty, and adolescence. Infancy runs before the configured transition window; transition spans the configured 24-month window (700–760 days by default, so day 730 is transition); childhood follows that window until the injected puberty schedule; puberty follows onset for its configured tempo; and adolescence continues through the maximum age (including 7305). At every age, generate only two independent anthropometric dimensions: length plus weight before transition, and height plus BMI after transition, with the applicable third value derived explicitly. Do not generate height/length, weight, and BMI as three independent states.

The following compact example is development-only. Its injected reference is a test double, and its expected metrics are evaluator requirements rather than clinical targets. The named `puberty_age_days` value is an injected schedule/configuration value for this smoke example, not a clinical timing claim. The reference contract supplies finite values for `length_cm`, `weight_kg`, `head_circumference_cm`, `height_cm`, and `bmi` at each requested age, sex, and z-score.

```python
from synthetic.models import PatientState
from synthetic.native.age_regimes import AgeRegimeConfig, AgeRegimeTrajectoryKernel
from synthetic.randomness import NamedRandomStreams
from tests.synthetic.test_age_regime_kernel import RegimeReference

puberty_age_days = 4_745  # injected schedule/config value for this example
config = AgeRegimeConfig(
    puberty_min_age_days=puberty_age_days,
    puberty_max_age_days=puberty_age_days,
)
reference = RegimeReference()  # test double supporting all five metric names; never production
kernel = AgeRegimeTrajectoryKernel(reference, config)
ages = (0, 730, puberty_age_days, 7_305)  # infancy, transition, puberty, adolescence
trajectory = kernel.generate(
    PatientState("synthetic-age-regime", "F", "F"),
    ages,
    NamedRandomStreams(20260830, 1),
)
# Evaluator-only checks: continuity at regime boundaries; two-dimension identity;
# explicit conversion; valid reference domains; length_cm, weight_kg, height_cm,
# and bmi values; age-windowed velocity; and head_circumference_cm behavior.
```

Velocity and head-circumference fields used by those checks are evaluator-only derived views. The trajectory `.state` and `.points` are likewise evaluator-only and are not exported as latent truth or as a new visible smoke resource; the existing observable CSV contract and its non-matchability limitation remain unchanged. This example uses no WHO/CDC clinical table and creates no disorder-critical descendants. These defaults are uncalibrated development scenarios. Clinical validity, prevalence, demographic calibration, held-out validation, privacy evaluation, Synthea conformance, and any release gate remain deferred until separately approved evidence and governance are available; a Synthea adapter would require its own conformance evaluation.

### Evaluator-only age-regime disorder composition

`AgeRegimeDisorderKernel` composes one injected age-regime physiology kernel with one injected disorder scenario. The following example uses the test-only `RegimeLinearTestReference` and spans infancy, transition, puberty, and adolescence (with childhood represented between transition and puberty):

```python
from synthetic.models import PatientState
from synthetic.native.age_regime_disorder import AgeRegimeDisorderKernel
from synthetic.native.age_regimes import AgeRegimeConfig, AgeRegimeTrajectoryKernel
from synthetic.native.clinical_modules import FamilialShortStatureModule
from synthetic.randomness import NamedRandomStreams
from tests.synthetic.fakes import RegimeLinearTestReference

reference = RegimeLinearTestReference()  # test double; never a clinical reference
config = AgeRegimeConfig(puberty_min_age_days=4_500, puberty_max_age_days=4_500)
result = AgeRegimeDisorderKernel(
    AgeRegimeTrajectoryKernel(reference, config), FamilialShortStatureModule()
).generate(
    PatientState("synthetic-disorder", "F", "F"),
    (0, 730, 761, 4_500, 7_305),
    NamedRandomStreams(20260830, 0),
)
```

The returned `result.physiology`, `result.disorder`, and `result.events` are hidden evaluator objects. They are not CSV columns, descriptor resources, manifest fields, or ordinary-loader fields. This composition API does not alter the visible smoke generator, schema, resource mapping, or export contract.

For `infancy` and `transition`, the module's height effect adjusts the length z-score and its BMI effect adjusts the weight z-score; adjusted `length_cm` and `weight_kg` are then re-requested from the reference. At transition, standing height is the explicit length-to-height conversion and BMI is derived from weight and height. For `childhood`, `puberty`, and `adolescence`, the adjusted height and BMI z-scores are re-requested directly and weight is derived from BMI and height. Thus the anthropometric identities remain explicit: `BMI = weight_kg / (height_cm / 100) ** 2` whenever standing height and BMI exist, and pre-transition weight is the independent mass dimension. Transition continuity is rechecked after effects are applied, including sparse age pairs; invalid or nonfinite adjusted references, derived values, or velocities fail closed.

Constitutional delay has one schedule rule: sample the module's onset and delay, add `puberty_delay_days` to the sampled age-regime puberty onset, and replay physiology with that adjusted state. The module API includes a temporary-recovery height effect, but this composition uses its delay state to shift puberty and intentionally skips that overlapping height delta, so delay is applied exactly once. If the shifted onset falls outside the configured domain, composition fails closed rather than extrapolating. Other modules retain their own effects and event schedules: `HealthyGrowthModule` has zero anthropometric effect; `FamilialShortStatureModule` applies a constant negative height effect; `ConstitutionalDelayModule` supplies the temporary-recovery effect and delay state described above; and `GrowthHormoneDeficiencyModule` applies progressive impairment with an optional causally ordered treatment response. All four are uncalibrated development scenarios; choosing a module is not prevalence estimation.

The composition requests only named `regime.birth`, `regime.childhood`, `regime.puberty`, `regime.residual`, `regime.head`, and the selected `disorder.<module-kind>` stream (for example, `disorder.familial_short_stature`). It never requests a `growth` stream. The physiology, hidden disorder state, and hidden clinical-event trace remain an evaluator boundary and do not enter visible smoke output.

Diagnosis, laboratory, medication, and referral descendants; prevalence and demographic calibration; held-out validation; privacy auditing; package-level counterfactual worlds; clinical approval of a reference; and Synthea conformance are deferred gates. These scenarios are not clinically validated and do not claim a match to real EHR or growth data. The healthy age-730+ smoke/export boundary remains three visits at ages 730, 1095, and 1460 days, and the existing non-matchability limitation still applies: synthetic generation alone cannot establish that a profile cannot be matched to a real patient.

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

Each module and its frozen configuration exposes a stable, unique `module_version` identifier (currently the module name plus `-v1`). The identifier changes when the mechanism or its state/event semantics change; changing only scenario parameter values does not silently change the identifier, so callers should record both the identifier and configuration. Zero-effect states emit only their hidden latent-onset event; a treated zero-response state emits `treatment_nonresponse` rather than a treatment-response event, and a nonzero response always requires a treatment start.

These defaults are uncalibrated development scenarios. `LatentTrajectory.disorder` and `LatentTrajectory.events` are evaluator-only hidden truth and event traces; they are not exported, and visible CSV generation remains unchanged. Prevalence, demographic calibration, disorder-critical labs/medications/referrals, held-out validation, privacy auditing, and package-level counterfactual worlds remain later gates. No real patient data, clinical claim, or privacy claim is introduced by this layer.

## Prerequisites

Run these commands from the repository root:

```sh
uv sync
```

The package requires Python 3.12 or newer. The test-only reference and derivation oracle used in the smoke example below live under `tests/synthetic/fakes.py`; they are safe for smoke tests but must not be presented as clinical or privacy evidence.

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

It also does not demonstrate that a generated patient profile cannot be matched to a real patient. Structural safeguards and synthetic-only inputs reduce accidental leakage, while a separate privacy evaluation provides only qualified, policy-bound evidence under its approved data-governance process (for example, linkage, attribute-disclosure, and membership-inference testing); it does not prove non-matchability. Do not publish the smoke package as a golden, validated, development, clinical, representative, privacy-safe, or release-approved fixture.
