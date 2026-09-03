# Synthetic generator

This guide describes the ordinary development route for the exact-schema synthetic smoke generator, the development-only in-memory native cohort, and development-only observed-resource package export in this repository. They are development and integration harnesses for completely generated records; they are not a clinically validated simulator, a prevalence-validated representative cohort, a privacy audit, or a release-approved fixture.

The approved system design is documented in the [synthetic growth fixture specification](superpowers/specs/2026-08-30-synthetic-growth-fixtures-design.md); this guide is its implementation-facing companion.

## Current scope

The exact-schema smoke slice generates healthy patients aged two years and older. It produces three deterministic measurement visits per patient at ages 730, 1095, and 1460 days. Height and BMI are the two generated anthropometric dimensions; weight is derived from them. The smoke profile alternates recorded/reference sex across patients only to exercise the schema. It does not model growth-disorder states, disorder prevalence, calibrated demographics, infancy, puberty, or clinical events. The separate native cohort API below composes completely fictional healthy-plus-disorder trajectories in memory; it does not change this visible smoke contract.

The native generator reads `datapackage.json` as schema metadata only. It does not read the repository's real CSV snapshots or any patient records. The default/no-profile command-line invocation intentionally remains fail-closed with `No production growth reference or authoritative derivation oracle is configured`. The repository separately ships a source-matched growth augmenter as a development derivation candidate for wholly synthetic inputs; its setup, input contract, outputs, and manifest verification are in [the imported augmenter guide](augment-import.md), and its explicit test-only package-export use is in the [candidate augmenter-oracle guide](augmenter-oracle.md). Only explicit development profiles compose the candidate; that reproducible development composition does not establish production authority.

The native generator remains the release-one route and is also the ordinary development route. The [optional Synthea engine-conformance guide](synthea-conformance.md) defines a future, development-only aggregate declaration plus the externally pinned engine, module, growth-extension, adapter, exporter, configuration, license-review, derivation-binding, and evidence prerequisites for an optional comparison. This contract is not imported automatically by generation, export, or evaluator code and supplies no Synthea implementation, Java runtime, conformance result, patient data, network access, or release authorization. It does not change the production command, which remains fail closed with `No production growth reference or authoritative derivation oracle is configured`.

The evaluator-only [golden trajectory guide](golden-trajectories.md) provides a copy-pasteable fictional-reference run over fourteen deterministic forced-coverage cases and all five native pediatric age regimes. The suite keeps hidden trajectory state out of its aggregate-only report, creates no package or output path, and does not establish prevalence, demographic fidelity, clinical validity, task utility, privacy/non-matchability, held-out, scale, Synthea, or release evidence. The native generator remains the release-one route and is also the ordinary development route, the optional Synthea contract remains external and downstream, and the production command remains fail closed with `No production growth reference or authoritative derivation oracle is configured`.

The visible smoke example remains the healthy age-730+ profile: three visits at ages 730, 1095, and 1460 days. It does not export latent age-regime state, puberty state, or any other evaluator-only trajectory state. The broader age-regime behavior below is a development-only injected-reference example, not a change to that visible smoke contract.

## Explicit development CLI profiles

Run these commands from the repository root after `uv sync`. Each command creates a new package only when its output path does not already exist:

```sh
uv run python -m synthetic.generate --profile development-smoke --output /tmp/ppoc-development-smoke --patients 1000 --seed 20260901
uv run python -m synthetic.generate --profile development-cohort --output /tmp/ppoc-development-cohort --patients 1000 --seed 20260901
uv run python -m synthetic.generate --profile development-realistic --output /tmp/ppoc-development-realistic --patients 1000 --seed 20260901
```

`development-smoke` preserves the visible three-visit healthy smoke contract at ages 730, 1095, and 1460 days. `development-cohort` emits a fixed, full-age, healthy-plus-growth-hormone-deficiency (GHD) development profile. Its age schedule is `(0, 365, 730, 1460, 2190, 3650, 4380, 5114, 5475, 6200, 7305)` days; its module prior is healthy/GHD `0.50/0.50`; weight is observed at every scheduled visit; length is disabled; and height and head circumference have `1.0` availability whenever their age-regime channel is structurally applicable, with zero measurement error, no rounding, recognition, or diagnosis. BMI at exactly 730 days uses the CDC 24-month boundary row; day 729 remains outside the BMI source domain.

The cohort's F/M/U weights are `0.50/0.50/0.00`. The zero U sampling weight is deliberate because the CDC tables contain only M/F rows, while the F/M/U recorded-to-reference mapping remains structurally complete for the native contract. Its versioned demographic weights are fixed development configuration, not a calibration result or a real-population claim. Visible packages contain exactly eight descriptor-named CSV resources: the six base resources plus `patients_augmented` and `visits_augmented`. The `development-cohort` ancillary base resources remain descriptor-shaped and empty; the target-shaped profile's explicit GHD ancillary rows are described next. Latent disorder identity, severity, trajectory state, observation truth, source paths, and patient-level diagnostics are never exported.

`development-realistic` is an opt-in target-shaped variant that preserves the same full age schedule, exact schema, and CDC-backed trajectories while using the checked-in `schema/stats.json` snapshot `2026-08-24` for its fictional inputs. Its healthy/GHD module prior is `214681/250588` (`85.6709%`) and `35907/250588` (`14.3291%`), and recognition/diagnosis recording is enabled so GHD members carry the existing fictional visible event descendants. At each sampled GHD diagnosis visit, the exporter adds the fixed synthetic `E23.0` token recognized by the pinned augmenter; this makes the visible `growth_dx_flag` follow the sampled synthetic disorder mix without accepting arbitrary diagnosis input. The same explicit route projects and validates typed fictional GHD ancillary rows: each recognized member receives one referral, each workup receives two labs, each observed diagnosis receives one problem-list row, and a medication appears only when the latent treatment start is not earlier than the observed diagnosis. The in-memory lab marker `Synthetic` is serialized as the exact descriptor missing-value sentinel (`result_flag=""`) because the unchanged real-data enum has no fictional marker. Its demographic weights use the checked-in snapshot counts, folding source-missing ethnicity/race cells into the visible `Unknown` category and retaining a source-shaped race-multiselect probability of `13191/250588`. The U sex cell remains zero because the pinned CDC reference has no U series. These values are a frozen development scenario prior, not a clinical prevalence estimate or diagnosis claim.

All three profiles load the repository `datapackage.json` by default and default `--reference-time` to `2026-09-01T00:00:00Z` and `--software-revision` to `development-generator-v1`; callers may override those metadata values for reproducibility experiments. They use the pinned `cdc-lms-reference-v1` CDC LMS adapter and the `development-augmenter-v1` source-matched binding. Before generation, the runtime verifies the manifest-listed 14-file augmenter closure and the pinned `uv.lock` dependency bytes. The source-matched growth augmenter is not bound as authoritative for clinical, prevalence, privacy, or release decisions. A successful manifest identifies the profile, schema/reference/derivation fingerprints, configuration hash, and `test_only_derivation=true`.

Generation-only CDC calls clamp requested scores to the checked-in source P3/P97 interval so inverse-LMS values remain finite. Direct `CdcGrowthReference.value()` remains strict and rejects scores outside the mathematical LMS domain. The versioned `cdc-p3-p97-generation-domain-v1` token records this numerical safety policy in the development configuration hash; it is not calibration, prevalence, or clinical-validation evidence.

In this guide, `development-authoritative` means that the selected, byte-pinned reference and oracle are authoritative only for reproducibility within these explicit development commands. Every output remains test-only. The command rejects existing, partial, or unsafe output paths and does not overwrite them. To check deterministic behavior, rerun an identical command into two distinct new output roots and compare non-manifest file hashes; do not rerun into the same output root.

These profiles accept no real or governed patient inputs, real-data root, calibration artifact or path, held-out report, privacy input, network address, Synthea checkout, model, or arbitrary diagnosis payload. The default/no-profile invocation, and an unknown profile, still fail closed with `No production growth reference or authoritative derivation oracle is configured` before runtime construction or output-path checks.

Successful local packages do not establish clinical validity, prevalence validation, demographic fidelity, privacy/non-matchability, patient-disjoint held-out validation, task utility, a non-test derivation binding, Synthea conformance, or release authorization. Clinical and reference review, governed prevalence/demographic calibration, held-out evidence, qualified privacy evaluation and non-matchability review, optional Synthea conformance, and release authorization remain separate optional gates for claims outside ordinary development.

## Ordinary development requirements

The three explicit profiles are self-contained synthetic-development workflows. They require only a repository checkout, the pinned public/reference runtime already in the checkout, `uv sync`, a new output path, a positive patient count, and a seed. The descriptor supplies schema shape; the versioned development configuration supplies the fictional demographic weights, healthy/GHD prior, observation policy, and age schedule; and the pinned CDC reference plus source-matched augmenter supplies reproducible growth and derived fields. No real-data root, IRB/DUA authorization, partition key, disclosure or privacy policy, calibration/held-out artifact, release decision, Synthea checkout, model, or patient-level input is needed.

The following controls remain ordinary-development requirements because they affect fixture content or reproducibility: exact descriptor schema and CSV semantics, finite/type/range/key validation, deterministic seeds and named configuration, pinned reference/runtime fingerprints, source-matched augmentation, hidden-truth exclusion from visible files, and atomic no-overwrite output handling. The `test_only_derivation` marker and fail-closed default command are technical authority boundaries; they do not require a governance approval bundle and do not block the explicit development profiles.

Governed calibration, patient-disjoint held-out comparison, privacy/non-matchability evaluation, clinical or task-utility review, Synthea conformance, and release authorization are documented below as optional workflows. They may support a separate real-population or external-release claim, but none is a prerequisite for generating or using ordinary synthetic development fixtures.

## Scheduled development scale profile

The scheduled development scale profile contains three opt-in, test-only checks. The native direct scale profile retains the existing three fixed seeds and exercises the in-memory cohort, cohort/temporal/task evaluators, exact-schema exporter, and source-matched augmenter oracle. The CLI composition checks run one fixed 10,000-patient `development-cohort` package and one fixed 10,000-patient `development-realistic` package through the public command with the pinned CDC reference and source-matched derivation runtime. Run all three with:

```sh
SYNTHETIC_RUN_SCALE=1 uv run pytest -m scale tests/synthetic/test_development_scale.py tests/synthetic/test_generate_cli.py
```

The native direct parameterized run uses the fixed seeds `20260830`, `20260831`, and `20260901`, generates an exact 10,000-patient fictional cohort per seed, and writes each temporary package beneath pytest's `tmp_path` rather than retaining output in the repository. It checks all eight descriptor resources, exact row counts and schema identity, test-only derivation, longitudinal drift, and visible-only task execution. The `development-cohort` CLI composition check uses seed `20260901`, confirms every generated patient has the fixed full-age schedule, and checks the public package inventory, unique synthetic patient/visit IDs, manifest identity fields, and absence of latent truth in every artifact. The `development-realistic` CLI composition check uses the same scale and seed, verifies the target-shaped GHD ancillary relationships (`labs = 2 * problem_list = 2 * referrals` and `growth_dx_flag` equals the problem-list count), confirms conditional medication bounds, and checks the typed GHD lab marker's serialization sentinel is the exact descriptor missing-value sentinel. The opt-in keeps these multi-minute development checks out of ordinary CI; normal focused runs collect the tests but skip them unless `SYNTHETIC_RUN_SCALE=1` is set.

This gate is composition evidence only. It does not bind the augmenter, prove prevalence or clinical validity, evaluate against real labels, establish privacy/non-matchability, provide held-out or release evidence, run Synthea, or authorize release.

## Aggregate calibration artifacts (development boundary)

This section is optional. An approved calibration artifact is a disclosure-controlled aggregate from the governed `calibration` partition; ordinary development profiles do not load one. When a separately governed comparison needs it, load it only as an aggregate artifact for development review:

```python
from pathlib import Path
from synthetic.calibration import load_calibration_artifact

artifact = load_calibration_artifact(Path("approved-calibration.json"))
print(artifact.artifact_id, len(artifact.strata))
```

Strict keys, types, tokens, support, suppression, and file checks apply; suppressed cells remain null. The loader does not read PPOC CSVs, calibrate prevalence, tune trajectories, validate clinical fidelity, prove non-matchability, or authorize release. The native cohort API may consume the already-loaded artifact through the strict aggregate profile below; file/CLI consumption, held-out validation, privacy auditing, and an optional Synthea adapter are separate deferred gates.

### Development-only native calibrated cohort

`CalibrationSamplingProfile.from_artifact` converts an already-loaded `CalibrationArtifact` into aggregate sampling weights only when every required demographic and recorded-outcome target cell is a released aggregate. Missing or suppressed cells fail closed. `generate_native_cohort` then samples fictional demographics, composes healthy-plus-disorder trajectories from an explicit module prior, applies an explicit `ObservationPolicy`, and optionally projects each passing observation frame with an already-loaded descriptor mapping. It accepts no real-data path, calibration path, key, held-out or privacy report, output path, or patient row, and the fail-closed command-line entry point remains unchanged.

The example uses the fictional `RegimeLinearTestReference`; inject a separately reviewed reference for any use beyond tests. Both the calibration artifact and `descriptor_mapping` have already been loaded by the caller:

```python
from collections.abc import Mapping

from synthetic.calibration import CalibrationArtifact
from synthetic.cohort import (
    CalibrationSamplingProfile,
    CohortConfig,
    CohortModuleWeight,
    NativeCohort,
    generate_native_cohort,
)
from synthetic.models import DisorderKind
from synthetic.native.clinical_modules import (
    GrowthHormoneDeficiencyModule,
    HealthyGrowthModule,
)
from synthetic.native.observations import ObservationPolicy
from tests.synthetic.fakes import RegimeLinearTestReference


def build_development_cohort(
    artifact: CalibrationArtifact,
    descriptor_mapping: Mapping[str, object] | None,
) -> NativeCohort:
    calibration = CalibrationSamplingProfile.from_artifact(artifact)
    config = CohortConfig(
        profile="native-development-v1",
        patient_count=100,
        seed=20260831,
        ages_days=(761, 1_460, 3_650, 5_110, 6_200),
        observation_policy=ObservationPolicy(
            "native-cohort-observation-v1",
            0,
            6_201,
        ),
        module_weights=(
            CohortModuleWeight(DisorderKind.HEALTHY, 0.85),
            CohortModuleWeight(DisorderKind.GROWTH_HORMONE_DEFICIENCY, 0.15),
        ),
        reference_sex_mapping=(("F", "F"), ("M", "M"), ("U", "U")),
    )
    return generate_native_cohort(
        config,
        RegimeLinearTestReference(),
        calibration,
        modules={
            DisorderKind.HEALTHY: HealthyGrowthModule(),
            DisorderKind.GROWTH_HORMONE_DEFICIENCY: GrowthHormoneDeficiencyModule(),
        },
        descriptor=descriptor_mapping,
    )
```

The blank/nonresponse ethnicity or race category remains a distinct aggregate cell and maps explicitly to visible `Unknown`. Race slot one follows the released primary-race weights; when the released multiselect probability draws true, race slot two is drawn from the same weights and slots three through eight remain `Unknown`. This is a documented approximation, not reconstruction of higher-order race combinations; recorded flags do not allocate latent disease. `healthy_flag` and `growth_dx_flag` remain evidence for later prevalence validation, while only the explicit module prior controls latent module sampling.

`NativeCohort.to_mapping()` and `CohortMember.to_mapping()` expose only visible summaries, demographics, frames, and optional bundles. Each returned `member.trajectory` and `member.frame.truth` is evaluator-only and must stay outside ordinary mappings, logs, manifests, and visible packages. When a descriptor was supplied, a caller may separately collect the passing non-null bundles and pass them to `export_observed_resource_package` with the same already-loaded descriptor mapping, explicit export metadata, and an injected derivation oracle. `generate_native_cohort` never calls that package bridge or writes a file.

This API is development orchestration, not evidence of prevalence validation, demographic representativeness, held-out validation, privacy/non-matchability, clinical validity, task utility, other disorder-specific ancillary resources or clinical pathways beyond the GHD projection, authoritative derivation, release approval, or Synthea conformance. Those remain separate deferred gates; the production smoke CLI remains fail closed.

## Evaluator-only native cohort fidelity profile

`validate_native_cohort(cohort, policy)` evaluates one previously generated, completely fictional `NativeCohort` in memory. It returns an immutable `CohortValidationReport` and never generates or mutates members, reads a path, accepts a row, key, held-out report, privacy report, package, or hidden truth object, or changes the fail-closed production smoke CLI. The evaluator is useful for development preflight and counterfactual fixture checks; its aggregate output is not a release artifact.

Construct a `CohortValidationPolicy` before evaluation so the cohort-size minimum, evidence-support minima, demographic tolerance, zero-centered growth bounds, and half-open age windows are explicit. The exact public API is `CohortComparison`, `CohortValidationPolicy`, `CohortValidationStatus`, `CohortValidationReport`, and `validate_native_cohort` from `synthetic.cohort_validation`:

```python
from synthetic.cohort_validation import (
    CohortComparison,
    CohortValidationPolicy,
    CohortValidationStatus,
    validate_native_cohort,
)

cohort = build_development_cohort(artifact, descriptor_mapping)
policy = CohortValidationPolicy(
    policy_id="native-profile-v1",
    policy_version="1",
    minimum_cohort_size=50,
    minimum_cell_support=5,
    minimum_event_support=5,
    proportion_tolerance=0.10,
    growth_tolerances={
        "height_z_score": 3.0,
        "bmi_z_score": 3.0,
        "height_velocity_cm_per_year": 20.0,
        "weight_velocity_kg_per_year": 20.0,
    },
    required_age_windows=(
        ("infancy", 0, 730),
        ("childhood", 730, 3650),
        ("adolescence", 3650, 7305),
    ),
)
report = validate_native_cohort(cohort, policy)
assert report.status in (
    CohortValidationStatus.PASS,
    CohortValidationStatus.FAIL,
    CohortValidationStatus.UNEVALUABLE,
)
print(report.to_mapping())
```

The report keeps visible demographics and the separate aggregate checks named `latent_module.<module>`, `observable_phenotype`, `recorded_recognition`, `recorded_workup`, and `recorded_diagnosis`; these correspond to the latent module, observable phenotype, recorded recognition, recorded workup, and recorded diagnosis layers. The visible demographic checks apply the same blank/nonresponse projection used by native generation: an empty aggregate ethnicity or race category becomes visible `Unknown`, and primary race is the first race slot. A visible category is never presented as recovery of an unrecoverable source value.

The growth summaries use the canonical metrics `height_z_score`, `bmi_z_score`, `height_velocity_cm_per_year`, and `weight_velocity_kg_per_year`. Each required half-open `[lower, upper)` window emits a `growth.<window>.<metric>_mean` comparison; finite values are averaged, and the first point's missing velocity is omitted. The declared bounds are zero-centered development tolerances, not WHO/CDC reference targets or clinical validity criteria. Coverage checks report only aggregate cohort size, members with an observation, and members with a recorded event.

`PASS` means the evaluated structural, demographic, growth, and configured sanity checks met their policy; `FAIL` means at least one check was invalid or outside tolerance; `UNEVALUABLE` means no check failed but required evidence was too small or missing. Overall status precedence is `FAIL` over `UNEVALUABLE` over `PASS`. Layer diagnostics have no real-data target: a healthy latent module is not a real `healthy_flag`, an observable phenotype is not a recorded diagnosis, and recorded flags do not allocate latent disease.

The profile report is evaluator-only aggregate diagnostics, not prevalence validation, demographic representativeness, held-out validation, clinical validity, privacy evidence, non-matchability proof, package or release evidence, task utility, other ancillary clinical pathways beyond the GHD projection, authoritative derivation, or Synthea evidence. It does not prove that a generated patient profile cannot be matched to a real patient; use the separately governed privacy evaluation for qualified, policy-bound evidence, which also cannot prove non-matchability. The production smoke CLI, exact-schema package exporter, held-out validator, privacy auditor, and optional Synthea route remain unchanged and separately gated.

## Optional governed evidence and release review

The commands and evidence sections that follow are optional extensions for real-population comparison, privacy/non-matchability assessment, clinical or task-utility review, Synthea conformance, or external release. They are intentionally separate from the ordinary development profiles above: their governed paths, keys, policies, reports, and human approvals are never required to generate a completely synthetic fixture and are never read by the ordinary generator.

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

Repository CI invokes this path only with the wholly synthetic eight-resource mock package and test key material. No visible generator, CSV exporter, or native trajectory module imports the calibrator or reads its governed input. The native cohort receives only an already-loaded aggregate artifact through `CalibrationSamplingProfile`; the existing file generator examples and output contract remain unchanged.

Calibration output is not prevalence validation, representative-cohort evidence, clinical validation, privacy or non-matchability evidence, or release authorization. Held-out fidelity validation, clinical review, privacy auditing, and any future generator-consumption contract remain separate governed gates.

## Evaluator-only temporal-drift validation

`validate_temporal_drift` evaluates one previously generated, completely fictional `NativeCohort` against an explicit immutable `TemporalDriftPolicy` entirely in memory. Each `TemporalWindowPolicy` declares one ordered half-open `[lower_age_days, upper_age_days)` age window and its visible support floors and drift bounds; the evaluator accepts only the cohort and policy and does not read, write, export, or mutate a package or report.

```python
from synthetic.temporal_drift import (
    TemporalDriftPolicy,
    TemporalWindowPolicy,
    validate_temporal_drift,
)

policy = TemporalDriftPolicy(
    policy_id="temporal-v1",
    policy_version="1",
    minimum_cohort_size=2,
    maximum_unevaluable_checks=1,
    windows=(
        TemporalWindowPolicy(
            window_id="early",
            lower_age_days=0,
            upper_age_days=730,
            minimum_member_support=2,
            minimum_growth_points=1,
            minimum_visible_visits=1,
            minimum_growth_coverage=0.5,
            minimum_visible_visit_coverage=0.5,
            maximum_mean_inter_visit_days=400.0,
            maximum_visit_count_step=2.0,
            maximum_recorded_event_rate_step=0.5,
        ),
        TemporalWindowPolicy(
            window_id="late",
            lower_age_days=730,
            upper_age_days=1_460,
            minimum_member_support=2,
            minimum_growth_points=1,
            minimum_visible_visits=1,
            minimum_growth_coverage=0.5,
            minimum_visible_visit_coverage=0.5,
            maximum_mean_inter_visit_days=365.0,
            maximum_visit_count_step=2.0,
            maximum_recorded_event_rate_step=0.5,
        ),
    ),
)
report = validate_temporal_drift(cohort, policy)
```

The fixed visible metrics are `growth_window_coverage`, `visible_visit_coverage`, `visible_event_rate`, and `mean_inter_visit_days`; `mean_visit_count_step` and `recorded_event_rate_step` compare adjacent configured windows, with no step for the first window. The evaluator also performs the hidden causal checks `causal_event_order` and `causal_event_timing` over evaluator-held source evidence, but emits only aggregate statuses and fixed reason codes rather than hidden ages, events, or identifiers.

`FAIL` means any comparison is outside its bound or any evidence is structurally invalid. Individual comparisons with missing or insufficient evidence remain `UNEVALUABLE` and do not by themselves block an overall `PASS`; when no comparison fails, the overall report is `UNEVALUABLE` only if the cohort is smaller than `minimum_cohort_size`, a required window lacks minimum support, or the number of unevaluable comparisons strictly exceeds `maximum_unevaluable_checks`, and otherwise it is `PASS`. Missing evidence never becomes zero or a comparison-level pass.

This report diagnoses development sequence behavior only. It does not establish real-data temporal fidelity, growth-disorder prevalence, clinical validity, privacy/non-matchability, task utility, release readiness, or Synthea conformance; each remains a separate deferred evidence and governance gate.

## Evaluator-only synthetic task-utility evaluation

`evaluate_task_utility` evaluates task outputs for one previously generated, completely fictional `NativeCohort` entirely in memory. The caller builds an immutable ordered tuple of `TaskPrediction` values from its visible pipeline in the cohort's stable cohort order, declares all support and performance thresholds in a frozen `TaskUtilityPolicy`, and passes no model, callable, path, key, report, or output destination to the evaluator.

```python
from synthetic.task_utility import (
    TaskPrediction,
    TaskUtilityPolicy,
    TaskUtilityStatus,
    evaluate_task_utility,
)


def prediction_from_visible_member(member):
    visible = member.to_mapping()
    pipeline_output = run_visible_growth_pipeline(visible)
    return TaskPrediction(
        predicted_disorder=pipeline_output.predicted_disorder,
        risk_score=pipeline_output.risk_score,
    )


predictions = tuple(
    prediction_from_visible_member(member)
    for member in cohort.members
)
policy = TaskUtilityPolicy(
    policy_id="task-utility-v1",
    policy_version="1",
    minimum_cohort_size=50,
    minimum_evaluable_members=45,
    minimum_class_support=5,
    maximum_unevaluable_members=5,
    require_probability_scores=False,
    minimum_sensitivity=0.80,
    minimum_specificity=0.80,
    minimum_auroc=0.75,
    maximum_brier_score=0.20,
    subgroup_dimensions=("sex",),
)
report = evaluate_task_utility(cohort, predictions, policy)
assert isinstance(report.status, TaskUtilityStatus)
```

The fixed metrics are `sensitivity`, `specificity`, `precision`, `balanced_accuracy`, `auroc`, `brier_score`, `false_positive_count`, and `false_negative_count`. The evaluator always produces the `overall` cell and, when `subgroup_dimensions=("sex",)`, produces the observed fixed scopes `sex:F`, `sex:M`, and `sex:U` in that order after `overall`; absent categories are omitted, and caller-defined subgroup dimensions or demographic labels are rejected.

`PASS` means every evaluable bounded metric meets its declared threshold and all cohort, evaluable-member, class-support, missing-prediction, and requested subgroup gates are satisfied. `FAIL` means an evaluable bounded metric is outside its threshold or the evidence is structurally invalid. `UNEVALUABLE` means a required support or evidence gate is not satisfied; missing evidence never becomes zero or a pass, and any ordinary unevaluable cell suppresses truth-derived metrics and confusion counts. When `require_probability_scores=False`, missing scores do not block otherwise eligible decision-based diagnostics: `auroc` and `brier_score` alone remain `UNEVALUABLE/MISSING_SCORE`; when scores are required, missing score evidence blocks the report according to the frozen policy semantics.

The disorder label is hidden truth used only inside the evaluator to accumulate aggregate confusion and score bins. The aggregate-only report contains fixed metric, status, reason, scope, and count fields; it contains no member identifiers, ordered predictions, individual scores, raw observations, latent trajectories, disorder labels, or private traces, and ordinary cohort, member, frame, and report mappings remain truth-free.

This synthetic development diagnostic does not establish clinical utility, real-data performance or generalization, prevalence evidence, privacy/non-matchability, release readiness, or Synthea conformance; each remains a separate deferred evidence and governance gate.

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

## Governed multi-run prevalence evidence

An authorized operator may run `synthetic.prevalence_evidence` only inside the governed environment after producing complete generated packages through the reviewed package lifecycle. Its Python API accepts an immutable `PrevalenceEvidenceConfig` with at least three predeclared, distinct `PrevalenceRunSpec(package_root, expected_seed)` values and an explicit governed `HeldoutRunConfig` template. `evaluate_prevalence_evidence(config)` verifies the exact manifest/package binding for every run—descriptor inventory, row counts, file digests, schema, generation identity, and expected seed—before it invokes the held-out evaluator. `write_prevalence_evidence(PrevalenceEvidenceResult(report), output)` is the only report writer; neither API changes a package or feeds evidence back into generation.

```sh
uv run python -m synthetic.prevalence_evidence \
  --real-root /governed/ppoc \
  --descriptor /governed/ppoc/datapackage.json \
  --snapshot 2026-08-24 \
  --calibration-artifact /approved/calibration/calibration-artifact.json \
  --calibration-report /approved/calibration/calibration-report.json \
  --partition-policy /governed/partition-policy.json \
  --disclosure-policy /governed/disclosure-policy.json \
  --partition-key-file /governed/partition.key \
  --frozen-policy /governed/fidelity-policy.json \
  --package-root /fixtures/predeclared-seed-101 \
  --expected-seed 101 \
  --package-root /fixtures/predeclared-seed-202 \
  --expected-seed 202 \
  --package-root /fixtures/predeclared-seed-303 \
  --expected-seed 303 \
  --output /governed/prevalence-evidence-report
```

Every governed input is explicit, including each repeated package root and expected seed; there are no default roots, keys, policies, artifacts, snapshots, packages, or seeds. Configuration privately seals each physical package-root directory identity, so replacing a declared root before or during evaluation fails closed. That seal does not snapshot pre-evaluation bytes: operators must keep each declared directory unchanged in place after configuration, while evaluation binds and repeatedly verifies the exact manifest/package bytes it reads. The v1 evidence scope is only observed demographics and recorded outcomes under the frozen held-out policy. Latent disorder prevalence and observable phenotype diagnostics are excluded from the comparison and cannot affect the status. Joint demographic/prevalence strata remain deferred to a reviewed target-registry revision.

`PASS` requires every required cell to be evaluable and pass in every run. `FAIL` means at least one evaluable required cell failed its frozen tolerance. `UNEVALUABLE` means no required cell failed but required evidence was missing, suppressed, or under-supported; it is never treated as zero or `PASS`. Each run is normalized over the exact required v1 key set before its public status and comparison count are derived. The promoted report is aggregate-only: it contains safe identities, package/manifest digests, aggregate comparison values, and statuses, but no paths, partition keys, rows, patient or visit identifiers, supports, denominators, hidden labels, or truth hashes. Its public paired threshold statistic is `maximum_tolerance_exceedance = max(difference - tolerance)` across evaluable runs; a positive value corresponds to `FAIL`, while a standalone aggregate tolerance is deliberately omitted because it would not remain paired with the run supplying the maximum difference. Strict reparse checks the exact v1 keys, run-bounded counts, and report-level feasibility of run/comparison/report statuses without exposing per-run values. Because individual run cells remain withheld, each public per-run status is an in-memory-bound redacted summary rather than independently reconstructable evidence; canonical writer equality binds it to the validated in-memory report before promotion. The gate applies no adaptive prevalence forcing, label allocation, tuning, package mutation, or report feedback.

This is a narrowly scoped patient-disjoint held-out distributional check, not a claim that latent disease prevalence is correct. It does not replace other held-out fidelity checks or establish clinical validity, privacy/non-matchability, task utility, Synthea conformance, or release approval. CI remains synthetic-only with fictional packages and test key material; privacy, clinical review, utility, Synthea, and release gates require their own approved evidence and governance.

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

The native counterfactual layer replays one completely fictional `AgeRegimeDisorderKernel` patient into a baseline world and one intervention world. It is the trajectory component of the counterfactual roadmap: it does not read visible CSV rows, alter the eight-resource descriptor, or turn the fail-closed smoke command into a cohort generator. The in-memory resource-level paired EHR-world composition is documented below; pair-aware package export remains a separate gate.

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

`write_truth_manifest(pair, report, path)` is an explicit evaluator-only boundary. It serializes the hidden patient/state/event trace, causal-layer hashes, and stream identities to canonical JSON outside the visible package. The destination must be a new regular non-symlink file with an existing non-symlink parent; every existing ancestor from the filesystem root through that parent must also be a regular non-symlink directory. The writer opens each ancestor component with `O_NOFOLLOW|O_DIRECTORY` and keeps the final parent descriptor pinned, so an ancestor swap cannot redirect publication or verification. It creates the child directly with descriptor-relative `O_CREAT|O_EXCL|O_NOFOLLOW` mode `0600`, keeps that child descriptor open through size-bounded readback and canonical reparsing, and compares its device/inode identity with the pinned directory entry before closing it. On write or verification failure, cleanup atomically performs a platform no-replace rename to a private random quarantine entry in the already pinned parent, compares that moved inode with the still-open owner descriptor when available, and never unlinks a quarantined inode. If a same-name unlink/recreate replacement wins the race, cleanup restores a regular or symlink replacement with a no-overwrite hard link when possible, deliberately retains the quarantined source, and reports an explicit cleanup error; non-linkable replacements remain private and are reported rather than removed. An owner whose identity cannot be read is likewise quarantined instead of leaving an unaccounted zero-byte destination. Under ordinary failures, the requested destination is absent and available for a retry, while private quarantine entries remain evaluator-controlled for explicit recovery. The quarantine uses only the pinned parent descriptor and a no-replace child rename, so there is no cleanup-directory mkdir/open/rmdir pathname lifecycle to race. Ordinary pair/report mappings and `manifest.json` remain truth-free. Keep the truth manifest in evaluator-controlled storage and do not copy it beside a released fixture package.

This trajectory slice does not establish growth-disorder prevalence, demographic representativeness, observation-error fidelity, temporal drift, task utility, privacy or non-matchability, clinical validity, or release authorization. Those are separate approved gates; a complete exact-schema counterfactual package and an optional Synthea-conforming adapter require their own schema, derivation, longitudinal, causal, utility, and privacy evaluation.

## Evaluator-only observation frame

The native observation layer is the evaluator boundary between a completely fictional latent growth trajectory and a visible longitudinal record. It is deliberately separate from the exact-schema generator: it does not read CSVs, calibration or validation artifacts, write files, modify `datapackage.json`, activate the smoke CLI, or generate any visible package resource. It is not prevalence, demographic, clinical, privacy, non-matchability, or release evidence.

Generate and validate a frame with an explicit fictional trajectory, immutable policy, and the existing named random streams:

```python
from synthetic.native.observations import (
    ObservationPolicy,
    ObservationValidationStatus,
    generate_observation_frame,
    validate_observation_frame,
)
from synthetic.randomness import NamedRandomStreams

frame = generate_observation_frame(
    trajectory,
    ObservationPolicy(
        policy_version="observation-v1",
        window_start_age_days=0,
        window_end_age_days=4000,
        visit_probability=1.0,
        length_availability_probability=1.0,
        height_availability_probability=1.0,
        weight_availability_probability=1.0,
        head_circumference_availability_probability=1.0,
    ),
    NamedRandomStreams(20260831, 0),
)
report = validate_observation_frame(frame)
assert report.status is ObservationValidationStatus.PASS
print(frame.to_mapping())
print(report.to_mapping())
```

The fixed named streams are `observation.window`, `observation.censoring`, `observation.visit.routine`, `observation.measurement-availability`, `observation.measurement-error`, `observation.recognition`, and `observation.recorded-event`. Replaying the same trajectory, policy, seed, and patient index reproduces the same visible frame and hidden truth hashes. The visible frame contains only synthetic patient/visit records, channel statuses and values, recorded fictional recognition/workup/diagnosis descendants, window metadata, and counts; `ObservationTruth` retains the private opportunity, latent/error, and source-event evidence for evaluator checks.

`validate_observation_frame` uses seven fixed aggregate checks: patient identity, effective window, visit references, measurements and derived BMI identity, hidden events, causal event order, and minimum evidence. Reports contain only check names, `PASS`/`FAIL`/`UNEVALUABLE` statuses, fixed reason codes, and status counts. Malformed or missing private evidence is `UNEVALUABLE`, while a typed visible invariant violation is `FAIL`. The report never includes patient IDs, ages tied to a patient, measurement values, source-event payloads, latent values, error deltas, hashes, seeds, paths, or stream identities.

The first observation slice supports routine visit selection, explicit administrative/lost-to-follow-up windows, independent anthropometric availability, additive/rounding error, derived BMI, and recognition/recorded-event projection. Utilization-intensity and measurement-error-removal counterfactuals remain explicitly deferred until observation/resource descendants and their reviewed causal matrices exist. Other disorder-specific ancillary pathways, prevalence/demographic calibration, held-out validation, privacy auditing, and an optional Synthea adapter remain separate roadmap gates; the evaluator-only GHD projection and bundle/package bridges are documented below.

## Evaluator-only observed resource bundles

`project_observed_resources(frame, descriptor)` projects one passing fictional observation frame into an immutable, in-memory bundle containing descriptor-ordered `patients` and `visits` rows, empty `labs`, `medications`, `problem_list`, and `referrals` rows, and fixed fictional clinical descendants. The descriptor is supplied as an already-loaded mapping. No descriptor path, CSV reader, schema mutation, package writer, generator, CLI, calibration input, held-out input, or privacy input is accepted.

In this example, `descriptor_mapping` is an already-loaded mapping supplied by the caller, not a path or a value loaded by the resource module.

```python
from synthetic.native.resources import (
    ResourceValidationStatus,
    project_observed_resources,
    validate_observed_resources,
)


def project_and_validate(frame, descriptor_mapping):
    bundle = project_observed_resources(frame, descriptor_mapping)
    report = validate_observed_resources(bundle)
    assert report.status is ResourceValidationStatus.PASS
    print(bundle.to_mapping())
    print(report.to_mapping())
```

The validator has seven fixed aggregate checks: patient identity, schema shape, visit references, measurements, clinical descendants, ancillary resources, and source-frame evidence. It returns only `PASS`, `FAIL`, or `UNEVALUABLE` statuses, fixed reason codes, and counts; it never returns identifiers, ages, row values, hidden truth, hashes, descriptor shape, paths, or private source references. Missing or malformed private source evidence is `UNEVALUABLE`; typed visible row, key, unit, event, or ancillary-resource violations are `FAIL`.

This evaluator contract does not itself implement augmented resources, exact-schema file export, or package manifests. The development-only bridge below now writes exact-schema files and manifests with an explicit injected oracle; authoritative augmented clinical derivation, prevalence and demographic calibration, other ancillary clinical pathways beyond the evaluator-only GHD projection and bundle integration, held-out validation, privacy/non-matchability evaluation, task utility, clinical validity, release approval, and Synthea conformance remain explicitly deferred gates.

## Evaluator-only GHD ancillary pathway

`project_ghd_ancillary_resources(member, shape, policy)` is a deterministic,
in-memory projection for one previously generated fictional `CohortMember`.
The caller supplies the already extracted `ResourceShape` and a
`GhdAncillaryPolicy(policy_id, policy_version, result_delay_days)`; no path,
CSV, key, report, output, or governed input is accepted. The return value is
an immutable `AncillaryResourceProjection` with exactly four resource tuples:
`labs`, `medications`, `problem_list`, and `referrals`. Validation is a
separate aggregate-only call:

```python
from synthetic.native.ancillary import (
    AncillaryValidationStatus,
    GhdAncillaryPolicy,
    project_ghd_ancillary_resources,
    validate_ghd_ancillary_resources,
)

# member and shape came from a prior in-memory synthetic generation step.
policy = GhdAncillaryPolicy("ghd-ancillary-v1", "1", result_delay_days=7)
projection = project_ghd_ancillary_resources(member, shape, policy)
report = validate_ghd_ancillary_resources(member, projection, policy)
assert report.status is AncillaryValidationStatus.PASS
```

Only a GHD member with the existing valid observation frame can produce
nonempty rows. The first visible `recognition` event emits one referral to
`Synthetic Pediatric Endocrinology`; the first `workup` emits two `labs`
components (`SYN-GHD-IGF1` and `SYN-GHD-STIM`) with exact `result_flag="Synthetic"`; and the first visible
`diagnosis` emits one unresolved `problem_list` row with `SYN-GHD`. A hidden
`treatment_start` event is consulted only after visible diagnosis and then
permits one medication, `Synthetic growth hormone`, with record type
`Internal`; hidden treatment alone never creates a visible row. If an
observation window delays the visible diagnosis beyond the hidden treatment
start, that treatment remains evaluator-held and the medication row is
suppressed rather than implying an earlier observed diagnosis. Event ages
control order, noted, referral, and start timing, while each lab result is
delayed by `policy.result_delay_days`.

Every row follows `shape.field_names(resource)` in exact descriptor order.
Unlisted optional values use the exact empty string (empty-string) convention (`""`): labs
have no LOINC claim, the problem has no visit key and an empty resolved age,
medication end age is empty, and the referral visit-count field is fixed by the
synthetic contract. The fixed fictional content is `SYN-GHD`,
`SYN-GHD-IGF1`, `SYN-GHD-STIM`, `result_flag="Synthetic"`,
`Synthetic Pediatric Endocrinology`, `med_record_type="Internal"`, and
`Synthetic growth hormone`; these are test vocabulary, not ICD,
LOINC, RxNorm, or clinical terminology/reference values. Healthy, non-GHD,
and unrecognized members return four empty tuples. Replaying the same inputs
is deterministic and mutates neither member nor shape.

`AncillaryValidationReport` has fixed checks for pathway scope, row schema,
causal timing, cross-resource links, and source evidence. Its aggregate status
is `PASS`, `FAIL`, or `UNEVALUABLE`: `FAIL` wins over `UNEVALUABLE`, which wins
over `PASS`. Reports expose only check names, statuses, reason codes, and
counts; row identifiers, ages, values, hidden events, and source payloads are
never returned.

This is an evaluator-only exact-row contract. `ObservedResourceBundle` and the
complete package export bridges (which remain development-only) are documented
separately. The explicit `development-realistic` route now uses this projection
and the typed bundle merge before calling `export_exact_schema_package`; it
serializes the fictional lab marker as the descriptor's exact empty-string
sentinel, while the generic empty-ancillary route remains unchanged. Complete
package export for paired counterfactual worlds, non-target profiles, and
authoritative derivation remains deferred, as do other disorders, prevalence
calibration, held-out validation, privacy and non-matchability evidence,
clinical review, task utility, release approval, and Synthea conformance. The
default production CLI remains fail-closed, and existing empty-ancillary
base-resource contracts remain in force.

### In-memory GHD ancillary bundle integration

`merge_ghd_ancillary_resources(bundle, member, projection, policy)` composes the evaluator-only GHD projection with one typed in-memory `ObservedResourceBundle`; it accepts only the same fictional `CohortMember`, exact `AncillaryResourceProjection` shape, and `GhdAncillaryPolicy` used by the prior synthetic generation step. The base bundle must have empty `labs`, `medications`, `problem_list`, and `referrals` tuples, its patient row and source frame must bind to the member, and every ancillary visit link must resolve to a base visit. A passing merge returns a fresh immutable six-resource `ObservedResourceBundle` without mutating the base bundle or projection.

```python
from synthetic.native.ancillary_bundle import (
    AncillaryBundleValidationStatus,
    merge_ghd_ancillary_resources,
    validate_ghd_ancillary_bundle,
)
from synthetic.native.resources import ResourceValidationStatus, validate_observed_resources

# base_bundle, member, projection, and policy are prior typed in-memory synthetic values.
enriched_bundle = merge_ghd_ancillary_resources(base_bundle, member, projection, policy)
report = validate_ghd_ancillary_bundle(enriched_bundle, member, policy)
assert report.status is AncillaryBundleValidationStatus.PASS

# The legacy generic validator intentionally rejects nonempty ancillary rows.
assert validate_observed_resources(enriched_bundle).status is ResourceValidationStatus.FAIL
```

`validate_ghd_ancillary_bundle` returns a separate aggregate-only `AncillaryBundleValidationReport` with fixed `bundle_identity`, `base_resources`, `ancillary_resources`, and `truth_boundary` checks. It re-runs the current validators against a zeroed base view and an extracted ancillary projection; `FAIL` wins over `UNEVALUABLE`, which wins over `PASS`. A typed visible row, identity, shape, link, causal-timing, or nested truth-boundary violation is `FAIL`; absent or malformed private source evidence is `UNEVALUABLE` only when no independently visible violation is demonstrable. The report contains fixed statuses, reason codes, and counts only: no rows, IDs, source frame, latent trajectory, hidden event, or truth payload is serialized or rendered.

This synthetic-only, evaluator-only seam is itself in-memory only: it has no file input, package/file export, manifest, descriptor mutation, or CLI. The explicit `development-realistic` runtime is the narrow caller that projects and merges these typed rows, converts the fictional lab marker to the exact descriptor sentinel, flattens all six resources, and sends them through the existing exact-schema exporter and source-matched augmenter. The merge remains the reviewed seam used by the paired counterfactual worlds composer below; it does not make paired counterfactual worlds, non-target profiles, or authoritative augmented derivation exportable. Those package/export paths, other disorders, prevalence or demographic calibration, held-out validation, clinical review, task utility, privacy or non-matchability, release approval, and Synthea conformance remain separately deferred.

## Evaluator-only excess-weight ancillary pathway

`project_excess_weight_ancillary_resources(member, shape, policy)` and `validate_excess_weight_ancillary_resources(member, projection, policy)` are deterministic, evaluator-only, in-memory APIs for one previously generated fictional member. The public types are `CohortMember`, `ResourceShape`, `ExcessWeightAncillaryPolicy`, `ExcessWeightAncillaryProjection`, `ExcessWeightAncillaryCheck`, `ExcessWeightAncillaryValidationStatus`, and `ExcessWeightAncillaryValidationReport`; malformed typed inputs cross the fixed `ExcessWeightAncillaryProjectionUnavailable` boundary.

The boundary accepts only a typed `CohortMember`, an already extracted `ResourceShape`, and an `ExcessWeightAncillaryPolicy`. It returns an immutable exact-schema projection with four fixed resource tuples: `labs`, `medications`, `problem_list`, and `referrals`. Every row follows the supplied descriptor field order and uses the exact empty-string sentinel for omitted fields. No descriptor path, CSV reader, package writer, output destination, CLI, or governed input is accepted, and this slice does not integrate with the runtime or package exporter.

The fixed fictional constants are `EXCESS_WEIGHT_DIAGNOSIS_CODE`: `SYN-EXCESS-WEIGHT`, `EXCESS_WEIGHT_LIPID_COMPONENT`: `SYN-EXCESS-WEIGHT-LIPID`, `EXCESS_WEIGHT_A1C_COMPONENT`: `SYN-EXCESS-WEIGHT-A1C`, `EXCESS_WEIGHT_REFERRAL_SPECIALTY`: `Synthetic Pediatric Nutrition`, and `EXCESS_WEIGHT_LAB_RESULT_FLAG`: `Synthetic`, serialized as `result_flag="Synthetic"`. A visible `recognition` produces one `referrals` row, `workup` produces one two-component `labs` order, and `diagnosis` produces one unresolved `problem_list` row. The `medications` tuple is always empty, including when a latent `treatment_start` event is present: this slice treats treatment as behavioral/weight-management evidence and creates no visible medication row. Hidden or unrecorded events never create visible descendants.

`EXCESS_WEIGHT` is evaluator-only as a latent trajectory kind; it neither implies nor writes `obesity_flag`, which remains separately derived from observed BMI percentile. Healthy, GHD, and other non-target members return four empty tuples. This evaluator-only pathway is not prevalence evidence, privacy/non-matchability proof, clinical validity or treatment guidance, release authorization, or Synthea conformance. Package/export integration, prevalence calibration, held-out comparison, privacy review, clinical review, release authorization, and optional Synthea conformance remain deferred.

## Evaluator-only pediatric-hypothyroidism ancillary pathway

`project_pediatric_hypothyroidism_ancillary_resources(member, shape, policy)` and `validate_pediatric_hypothyroidism_ancillary_resources(member, projection, policy)` are deterministic, evaluator-only, in-memory APIs for one previously generated fictional member. The public types are `PediatricHypothyroidismAncillaryPolicy`, `PediatricHypothyroidismAncillaryProjection`, `PediatricHypothyroidismAncillaryValidationStatus`, `PediatricHypothyroidismAncillaryCheck`, and `PediatricHypothyroidismAncillaryValidationReport`; the fixed projection failure boundary is `PediatricHypothyroidismAncillaryProjectionUnavailable`. The validator reports only `PASS`, `FAIL`, and `UNEVALUABLE` checks in fixed order.

The projection returns immutable `labs`, `medications`, `problem_list`, and `referrals` tuples. Rows retain the exact descriptor schema as exact-schema rows and the exact descriptor field order, use the descriptor's empty-string sentinel for omitted values, and are created only in memory for evaluator-only use. A visible `recognition` event produces one `referrals` row, visible `workup` produces two `labs` components, and visible `diagnosis` produces one `problem_list` row that is unresolved. A visible diagnosis plus a hidden `treatment_start` at or after the observed diagnosis permits one medication; hidden treatment alone never creates a medication, and treatment before a censored observed diagnosis is suppressed.

The fictional constants are `SYN-PEDIATRIC-HYPOTHYROIDISM`, `SYN-HYPOTHYROIDISM-TSH`, `SYN-HYPOTHYROIDISM-FREE-T4`, `result_flag="Synthetic"`, `Synthetic Pediatric Endocrinology`, `Synthetic levothyroxine`, and `med_record_type="Internal"`. These labels are fictional and are not ICD, LOINC, or RxNorm terminology or a clinical claim; latent hypothyroidism remains hidden evaluator state. This pathway has no visible runtime or package export route. Runtime/package integration, prevalence and demographic calibration, privacy/non-matchability review, clinical review, release authorization, real or held-out data, and optional Synthea conformance remain deferred.

## Evaluator-only celiac ancillary pathway

`project_celiac_ancillary_resources(member, shape, policy)` and `validate_celiac_ancillary_resources(member, projection, policy)` are deterministic, evaluator-only APIs that accept only typed in-memory values from one fictional member. The public types are `CeliacAncillaryPolicy`, `CeliacAncillaryProjection`, `CeliacAncillaryProjectionUnavailable`, `CeliacAncillaryValidationStatus`, `CeliacAncillaryCheck`, and `CeliacAncillaryValidationReport`; validation uses the fixed `PASS`, `FAIL`, and `UNEVALUABLE` statuses. The projection returns immutable exact-schema `labs`, `medications`, `problem_list`, and `referrals` tuples in the supplied descriptor field order.

The fixed fictional constants are `CELIAC_DIAGNOSIS_CODE="SYN-CELIAC-DISEASE"`, `CELIAC_TTG_IGA_COMPONENT="SYN-CELIAC-TTG-IGA"`, `CELIAC_TOTAL_IGA_COMPONENT="SYN-CELIAC-TOTAL-IGA"`, `CELIAC_LAB_RESULT_FLAG="Synthetic"`, `CELIAC_REFERRAL_SPECIALTY="Synthetic Pediatric Gastroenterology"`, `CELIAC_MEDICATION_NAME="Synthetic gluten-free intervention"`, and `CELIAC_MEDICATION_RECORD_TYPE="Internal"`; their exact values are `SYN-CELIAC-DISEASE`, `SYN-CELIAC-TTG-IGA`, `SYN-CELIAC-TOTAL-IGA`, `Synthetic Pediatric Gastroenterology`, and `Synthetic gluten-free intervention`. These serialize as `result_flag="Synthetic"` and `med_record_type="Internal"`. Deterministic opaque IDs use the `celiac-ancillary-id-v1` namespace. A visible `recognition` event creates one `referrals` row, visible `workup` creates two serology `labs` rows in one order with a delayed result, and visible `diagnosis` creates one unresolved `problem_list` row. A visible diagnosis plus a typed hidden `treatment_start` at or after that diagnosis permits one medication; hidden treatment alone and treatment before a censored diagnosis do not create medication rows.

These labels are fictional/nonclinical and make no ICD, LOINC, or RxNorm claim. Latent state remains hidden, and output is deterministic, immutable, exact-schema, and evaluator-only; healthy and all other disorder kinds return empty tuples. This pathway does not write or infer `obesity_flag`. Runtime/package integration, prevalence/demographic calibration, privacy/non-matchability, clinical review, release authorization, real or held-out data, and optional Synthea conformance remain deferred and are not ordinary-development prerequisites.

## Evaluator-only SGA ancillary pathway

`project_sga_ancillary_resources(member, shape, policy)` and `validate_sga_ancillary_resources(member, projection, policy)` are deterministic, evaluator-only APIs that accept only typed in-memory `CohortMember`, `ResourceShape`, and `SgaAncillaryPolicy` values for one fictional member. The public types are `SgaAncillaryPolicy`, `SgaAncillaryProjection`, `SgaAncillaryProjectionUnavailable`, `SgaAncillaryValidationStatus`, `SgaAncillaryCheck`, and `SgaAncillaryValidationReport`; the validator has only the fixed `PASS`, `FAIL`, and `UNEVALUABLE` statuses. The projection returns immutable exact-schema `labs`, `medications`, `problem_list`, and `referrals` tuples in the supplied descriptor field order, using empty strings for omitted fields. It accepts no descriptor path, CSV reader, package writer, output destination, CLI, or governed input.

The fixed fictional constants are `SGA_DIAGNOSIS_CODE="SYN-SGA"`, `SGA_GESTATIONAL_AGE_COMPONENT="SYN-SGA-GESTATIONAL-AGE"`, `SGA_BIRTH_SIZE_COMPONENT="SYN-SGA-BIRTH-SIZE"`, `SGA_LAB_RESULT_FLAG="Synthetic"`, and `SGA_REFERRAL_SPECIALTY="Synthetic Neonatology Follow-up"`; their exact values are `SYN-SGA`, `SYN-SGA-GESTATIONAL-AGE`, `SYN-SGA-BIRTH-SIZE`, and `Synthetic Neonatology Follow-up`. Lab rows serialize as `result_flag="Synthetic"`, with deterministic opaque IDs in the `sga-ancillary-id-v1` namespace. A visible `recognition` event creates one `referrals` row, visible `workup` creates two `labs` components in one order with a delayed result, and visible `diagnosis` creates one unresolved `problem_list` row. The descriptor has no dedicated gestational-age resource, so the fictional lab components carry empty values for `result_loinc_code` and `result_value` rather than invented measurements. The `medications` tuple is always empty, including for hidden or injected treatment state: there is no visible medication row. Hidden or unrecorded events never create visible descendants.

Birth-state at age zero and catch-up versus persistent branch state remains hidden evaluator state and never changes the fictional labels or rows. These labels are fictional/nonclinical and make no ICD, LOINC, or RxNorm claim. Healthy and all other disorder kinds return empty tuples, and this pathway does not write or derive `obesity_flag`.

This SGA slice has no runtime/package integration and is not prevalence/demographic calibration, privacy/non-matchability evidence, clinical review or guidance, release authorization, real or held-out data work, or Synthea conformance. Runtime/package integration, prevalence/demographic calibration, privacy/non-matchability, clinical review, release authorization, real or held-out data, gestational-age resource expansion, and optional Synthea conformance remain deferred and are not ordinary-development prerequisites.

## Evaluator-only Turner ancillary pathway

`project_turner_ancillary_resources(member, shape, policy)` and `validate_turner_ancillary_resources(member, projection, policy)` are deterministic, typed in-memory, exact-schema, evaluator-only APIs for one fictional member. The public values are `TurnerAncillaryPolicy`, `TurnerAncillaryProjection`, `TurnerAncillaryProjectionUnavailable`, `TurnerAncillaryValidationStatus`, `TurnerAncillaryCheck`, and `TurnerAncillaryValidationReport`; validation uses fixed `PASS`, `FAIL`, and `UNEVALUABLE` statuses. The current descriptor has four named resource shapes, in fixed order: `labs`, `medications`, `problem_list`, and `referrals`. Projection rows are immutable tuples in the supplied descriptor field order, with empty-string missing-value conventions; this boundary accepts typed `CohortMember` and `ResourceShape` values only and has no descriptor path, CSV, package writer, or CLI route.

The closed fictional vocabulary is `TURNER_DIAGNOSIS_CODE` = `SYN-TURNER-SYNDROME`, `TURNER_KARYOTYPE_COMPONENT` = `SYN-TURNER-KARYOTYPE`, `TURNER_ENDOCRINE_EVIDENCE_COMPONENT` = `SYN-TURNER-ENDOCRINE-EVIDENCE`, `TURNER_LAB_RESULT_FLAG` = `Synthetic`, `TURNER_REFERRAL_SPECIALTY` = `Synthetic Pediatric Endocrinology`, `TURNER_MEDICATION_NAME` = `Synthetic estrogen intervention`, and `TURNER_MEDICATION_RECORD_TYPE` = `Internal`; the deterministic identifier namespace is `turner-ancillary-id-v1`. These labels are fictional rather than clinical terminology: they are not ICD, LOINC, or RxNorm terminology or clinical value claims. The `Synthetic` marker is typed in memory and appears as `result_flag="Synthetic"`; medication rows use `med_record_type="Internal"`; lab `result_loinc_code` and `result_value` and other unrepresented fields remain empty.

The native `TurnerSyndromeModule` owns female-reference `reference_sex="F"` eligibility and the no birth-state deficit trajectory; recorded sex is not used to infer reference eligibility at this ancillary boundary. Hidden onset, phenotype, and treatment state remain upstream evaluator state. A visible `recognition` creates one `referrals` row, a visible `workup` creates two `labs` per workup with the two fixed components and delayed results, and a visible `diagnosis` creates one unresolved `problem_list` row. Referral, lab, and medication rows use the event's source-point visit link; the problem-list schema has no visit key. A visible diagnosis plus a private `treatment_start` at or after diagnosis creates one medication linked to the diagnosis visit, but treatment suppression leaves no medication when diagnosis is absent or censored (or treatment is earlier); hidden treatment alone never creates one. A treatment response or nonresponse creates no extra row, and no response event is emitted; no `obesity_flag` is emitted.

Healthy and every non-Turner member return four empty tuples for these resources, including GHD, hypothyroidism, celiac, SGA, undernutrition, excess weight, familial short stature, and constitutional delay. Runtime/package integration, prevalence/demographic calibration, privacy/non-matchability, clinical review, clinical/release claims, release authorization, real or held-out data, and optional Synthea conformance remain deferred in this ordinary-development fixture contract; these are not ordinary-development prerequisites.

## In-memory paired counterfactual EHR worlds

`assemble_counterfactual_ehr_worlds` composes one existing validated `CounterfactualPair` into an immutable `CounterfactualEhrWorldPair` of baseline and intervention `CohortMember` values. It accepts only shared `SyntheticDemographics`, one `ObservationPolicy`, an already-loaded descriptor mapping, and a `GhdAncillaryPolicy`; all inputs and results stay evaluator-only and in-memory. The composer replays the observation process with `NamedRandomStreams` using the same seed and patient index in both worlds, rather than independently resampling it, so assembly is deterministic for the same typed inputs.

The current base visits resource cannot project an observed `LENGTH` measurement. Use a base-compatible policy with `length_availability_probability=0.0` (or otherwise ensure no observed `LENGTH`) when composing resource rows. This is a fail-closed schema boundary, not a dropped value or an inferred height substitute.

```python
from synthetic.native.ancillary import GhdAncillaryPolicy
from synthetic.native.counterfactual_worlds import (
    CounterfactualWorldValidationStatus,
    assemble_counterfactual_ehr_worlds,
    validate_counterfactual_ehr_worlds,
)
from synthetic.native.observations import ObservationPolicy
from synthetic.native.resources import SyntheticDemographics

# `pair` is an existing validated CounterfactualPair from fictional native replay.
# This caller already knows the fictional identifier used when it created `pair`.
# `descriptor_mapping` is an already-loaded descriptor mapping supplied by this caller.
demographics = SyntheticDemographics("syn-counterfactual", sex="F")
observation_policy = ObservationPolicy(
    policy_version="counterfactual-world-v1",
    window_start_age_days=0,
    window_end_age_days=4000,
    length_availability_probability=0.0,
)
ancillary_policy = GhdAncillaryPolicy("ghd-ancillary-v1", "1", result_delay_days=7)
worlds = assemble_counterfactual_ehr_worlds(
    pair,
    demographics,
    observation_policy,
    descriptor_mapping,
    ancillary_policy,
)
report = validate_counterfactual_ehr_worlds(worlds)
assert report.status is CounterfactualWorldValidationStatus.PASS
print(worlds.to_mapping())
print(report.to_mapping())
```

The assembler independently validates that the supplied demographics identify the paired fictional patient; the example does not retrieve that identity through evaluator-only pair context.

The aggregate validator has exactly seven checks, in fixed order: `pair_binding`, `shared_demographics`, `shared_observation`, `observation_invariants`, `resource_invariants`, `permitted_changes`, and `truth_boundary`. Its only statuses are `PASS`, `FAIL`, and `UNEVALUABLE`, with precedence `FAIL > UNEVALUABLE > PASS`. Reports and assembly failures are fixed and redacted: they contain no patient or visit identifiers, row values, ages, latent trajectory states, hidden event payloads, seed/index, stream identities, descriptor contents, or private exception text. Hidden truth remains an evaluator boundary even though the validator rechecks it internally.

The visible resource-level intervention matrix is deliberately narrow. `PHYSIOLOGY_SEVERITY` may change only recorded growth measurement values; visit structure, availability, visible event trace, clinical descendants, and ancillary rows stay invariant. `EARLIER_RECOGNITION` preserves growth measurement values, availability, patient rows, and visits, while the visible event trace plus event-derived clinical descendants and ancillary rows may differ through the reviewed recognition pathway. `TREATMENT_ADHERENCE` preserves event trace, clinical descendants, ancillary rows, and measurement availability; growth values may differ only at or after the private `treatment_start`, and remain invariant when no treatment start exists. `UTILIZATION_INTENSITY` and `MEASUREMENT_ERROR_REMOVAL` remain rejected until their own reviewed resource descendants and matrices exist.

This has no file input or output: it is not a file writer, package exporter, manifest workflow, CLI, real-data or governed-data interface, calibration or held-out evaluator, privacy or non-matchability proof, clinical model, prevalence or demographic calibration, task utility experiment, or release approval. Pair-aware exact-schema export is documented below as a separate development-only bridge. A Synthea implementation is an optional later adapter only after conformance to this native contract; it does not replace the resource-level validator or hidden-truth boundary.

## Evaluator-only augmented-derivation parity gate

`DERIVATION_PARITY_VERSION = "derivation-parity-v1"` identifies the in-memory `validate_derivation_parity` evaluator. It compares an already-loaded fictional or privately controlled candidate output with an independently supplied reference output; it never opens a path, reads or writes a file, invokes generation or export, or consumes calibration, held-out, privacy, model, network, or Synthea inputs. `base_rows` contains exactly `patients`, `visits`, `labs`, `medications`, `problem_list`, and `referrals`; `candidate_rows` and `reference_rows` each contain exactly `patients_augmented` and `visits_augmented`.

The evaluator separately checks `deterministic_age_conversion`, `deterministic_unit_conversion`, `deterministic_bmi`, `deterministic_patient_summaries`, and `clinical_flag_relationships`, then applies `reference_field_parity` to every augmented field. Identifiers, strings, flags/enums, copied identity fields, and null state are exact. Only eligible finite numeric reference-dependent fields use `reference_tolerance`. Deterministic formulas use `deterministic_tolerance`. Formula semantics are bound by `DERIVATION_PARITY_VERSION` and the checked-in evaluator implementation, not caller-mutated derivation annotations. Structural or comparison failures are `FAIL`; missing required evidence or support is `UNEVALUABLE`; otherwise a check is `PASS`, with overall precedence `FAIL > UNEVALUABLE > PASS`.

```python
from collections.abc import Iterable, Mapping

from synthetic.derivation_parity import (
    DerivationImplementation,
    DerivationParityPolicy,
    DerivationParityStatus,
    validate_derivation_parity,
)


def evaluate_loaded_rows(
    base_rows: Mapping[str, Iterable[Mapping[str, object]]],
    candidate_rows: Mapping[str, Iterable[Mapping[str, object]]],
    reference_rows: Mapping[str, Iterable[Mapping[str, object]]],
    descriptor_mapping: Mapping[str, object],
    candidate: DerivationImplementation,
    reference: DerivationImplementation,
    policy: DerivationParityPolicy,
) -> dict[str, object]:
    report = validate_derivation_parity(
        base_rows,
        candidate_rows,
        reference_rows,
        descriptor_mapping,
        candidate=candidate,
        reference=reference,
        policy=policy,
    )
    assert report.status in (
        DerivationParityStatus.PASS,
        DerivationParityStatus.FAIL,
        DerivationParityStatus.UNEVALUABLE,
    )
    return report.to_mapping()
```

`DerivationParityReport` is aggregate-only: its fixed fields are `contract`, `schema_fingerprint`, `policy`, `candidate`, `reference`, `patient_row_count`, `visit_row_count`, `status`, `status_counts`, and `checks`; every check has only `name`, `status`, `reason_code`, `compared_count`, `mismatch_count`, and `maximum_absolute_difference`. Unevaluable checks suppress their counts and difference to `null`. The report's policy controls are public policy identity, not secret inputs. `DerivationParityUnavailable` is a fixed redacted failure, and neither reports nor exceptions include rows, identifiers, source values, diagnosis codes, paths, or hidden truth.

A passing comparison binds the supplied candidate and reference implementations; it does not make either clinically authoritative. An independently reviewed reference implementation, reference standard, code-set decision, fixed reference fixture, and data-custodian approval are prerequisites for using a passing report in a release decision. CI fixtures are wholly fictional. In governed use, a separately controlled process privately loads both candidate and reference inputs under required review controls before passing the already-loaded rows to this evaluator. Task utility is a separate non-authority evidence boundary governed by its own approved policy. This evaluator-only parity gate does not establish clinical validity, real-population prevalence, privacy/non-matchability, release approval, or Synthea conformance; those require separate approved evidence and governance.

## Authoritative derivation binding

`DERIVATION_BINDING_VERSION = "derivation-binding-v1"` identifies the immutable `DerivationBinding` supplied alongside every injected derivation oracle. It is a binding record, not an oracle result: the caller loads it before export, passes it explicitly as `derivation_binding`, and the exporter verifies that its oracle identity, implementation fingerprint, schema fingerprint, and `test_only` classification match. The binding records aggregate-safe identities and digests only. Its required golden categories are exactly `filter_order`, `age_boundaries`, `missingness`, `harrall_outlier`, `biv_filtering`, `velocity_variants`, and `rounding`.

The fictional example below is explicitly test-only. It contains no real paths, rows, review prose, or production secrets; a pending review is represented only by empty fields. It is suitable for wholly fictional tests because incomplete golden, fuzz, parity, and review evidence stays `UNEVALUABLE`, not passing evidence.

```python
from synthetic.derivation_binding import DerivationBinding
from synthetic.package_export import export_observed_resource_package
from synthetic.schema_contract import EXPECTED_SCHEMA_FINGERPRINT
from tests.synthetic.fakes import IdentityPreservingTestDerivationOracle

test_binding = DerivationBinding.from_mapping(
    {
        "binding_version": "derivation-binding-v1",
        "binding_id": "fictional-test-binding-v1",
        "schema_fingerprint": EXPECTED_SCHEMA_FINGERPRINT,
        "oracle": {
            "oracle_id": "identity-preserving-test-oracle-v1",
            "implementation_fingerprint": "0123456789abcdef" * 4,
            "source_revision": "fictional-revision-v1",
            "dependency_fingerprint": "a" * 64,
            "source_kind": "approved_parity_harness",
        },
        "reference_standard": {
            "standard_id": "fictional-standard-v1",
            "standard_fingerprint": "b" * 64,
            "version": "fictional-standard-v1",
        },
        "golden_evidence": {
            "manifest_id": None,
            "manifest_fingerprint": None,
            "parity_contract": None,
            "parity_report_id": None,
            "parity_report_fingerprint": None,
            "parity_status": "UNEVALUABLE",
            "candidate_implementation_fingerprint": None,
            "reference_implementation_fingerprint": None,
            "parity_schema_fingerprint": None,
            "covered_categories": [
                "filter_order",
                "age_boundaries",
                "missingness",
                "harrall_outlier",
                "biv_filtering",
                "velocity_variants",
                "rounding",
            ],
            "bidirectional_case_count": 0,
            "synthetic_fuzz_case_count": 0,
            "fuzz_corpus_fingerprint": None,
        },
        "review": {
            "review_id": None,
            "review_fingerprint": None,
            "reviewed_at": None,
            "reviewer_role": None,
            "status": "PENDING",
        },
        "test_only": True,
    }
)

exported = export_observed_resource_package(
    fictional_bundles,
    fictional_descriptor_mapping,
    fictional_destination,
    metadata=fictional_metadata,
    derivation_oracle=IdentityPreservingTestDerivationOracle(),
    derivation_binding=test_binding,
)
```

`IdentityPreservingTestDerivationOracle` is explicitly test-only: it copies fictional visible identity fields and is not an authoritative clinical derivation implementation. A test-only binding can support fictional testing only; it cannot become an approved non-test binding by changing the caller or oracle result. An approved non-test binding has `test_only=False`, complete matching golden, parity, fuzz, schema, oracle, reference-standard, and approved-review evidence, and a `PASS` report. Status precedence is `FAIL > UNEVALUABLE > PASS`; missing evidence is never converted to zero or `PASS`.

The binding evaluator is aggregate-only and serializes no rows, paths, or secrets. It does not execute an external harness, calibration, held-out, privacy, native-trajectory, temporal, prevalence, or Synthea route. A data custodian retains golden inputs/outputs, fuzz rows, and parity report bytes; only safe IDs/digests are recorded in the repository. The default/no-profile production command-line interface still fails closed with `No production growth reference or authoritative derivation oracle is configured`; the explicit development profiles use a separate test-only binding and do not claim production authority.

Software validation of a binding is not clinical validity, privacy validation, prevalence validation, Synthea conformance, or release authorization. An approved binding is necessary but not sufficient for clinical or release claims; those need their own approved evidence and governance. Synthea remains an optional later engine-conformance route.

## Exact-schema observed-resource package export

`export_observed_resource_package` is the development-only bridge from one or more passing in-memory observed-resource bundles to an exact-schema, synthetic-only package. The caller supplies an already-loaded descriptor mapping; the exporter does not accept a descriptor path, a real-data root, a calibration input, a held-out report, a privacy policy, or a Synthea input. Every bundle must already validate as `PASS`. The exporter checks each bundle against the supplied descriptor shape, rejects duplicate synthetic patient and visit identifiers, then sorts bundles deterministically by synthetic patient ID before it writes the shared exact-schema lifecycle.

The complete export call below receives `bundles` from the evaluator-only projection step above. Its `IdentityPreservingTestDerivationOracle` is an explicit injected test-only oracle: it owns the two augmented rows and is not an authoritative clinical derivation implementation. The descriptor mapping is loaded by this caller for illustration; no package-path reader is passed into the exporter.

```python
from pathlib import Path

from synthetic.native.resources import ResourceValidationStatus, validate_observed_resources
from synthetic.package_export import (
    PackageExportMetadata,
    export_observed_resource_package,
)
from synthetic.schema_contract import load_descriptor
from tests.synthetic.fakes import (
    IdentityPreservingTestDerivationOracle,
    test_derivation_binding,
)


def export_passing_observed_bundles(repository: Path, bundles: list[object], output: Path) -> Path:
    descriptor_mapping = load_descriptor(repository / "datapackage.json")
    for bundle in bundles:
        assert validate_observed_resources(bundle).status is ResourceValidationStatus.PASS

    return export_observed_resource_package(
        bundles,
        descriptor_mapping,
        output,
        metadata=PackageExportMetadata(
            profile="observed-development",
            seed=20260831,
            reference_time="2026-08-31T00:00:00Z",
            reference_id="fictional-observed-reference-v1",
            reference_sha256="b" * 64,
            configuration_sha256="a" * 64,
            software_revision="development-example",
        ),
        derivation_oracle=IdentityPreservingTestDerivationOracle(),
        derivation_binding=test_derivation_binding(),
    )
```

The promoted package contains exactly these eleven output files:

```text
patients.csv
patients_augmented.csv
visits.csv
visits_augmented-20251209150512.csv
labs.csv
medications.csv
problem_list.csv
referrals.csv
datapackage.json
validation-report.json
manifest.json
```

The two augmented resources are oracle-owned. This legacy observed-bundle helper
continues to export empty ancillary base resources, preserving its generic
validator contract. The explicit `development-realistic` route is the exception
documented above: it serializes the validated fictional GHD ancillary rows via
`export_exact_schema_package` and the same oracle-owned augmented resources. The
exact descriptor fields, order, dialects, encodings, constraints, keys, logical
links, generated-only descriptor, structural validation report, manifest hashes,
and atomic lifecycle are shared with the smoke export contract below.

The exporter refuses an existing target and redacts bundle or lifecycle failures as `observed package export failed`; a failed lifecycle is retained only as an unvalidated sibling failure archive. A successful package is a synthetic-only development artifact. Its structural success is not privacy/non-matchability or prevalence evidence, and it is not evidence of demographic calibration, other ancillary clinical pathways, held-out validation, task utility, clinical validity, release readiness, or Synthea conformance. Those remain separate deferred gates with their own approved evidence and governance.

## Pair-aware exact-schema counterfactual package export

`export_counterfactual_ehr_world_pair` is the development-only bridge from one previously assembled, validated fictional `CounterfactualEhrWorldPair` to two exact-schema child packages. The caller supplies the typed in-memory pair, a caller-loaded descriptor mapping, explicit metadata (`PackageExportMetadata`), and an explicit test-only derivation oracle; the exporter accepts no descriptor path, real-data or governed-data input, calibration or held-out artifact, privacy policy, model, network, or Synthea dependency. `CounterfactualPackageExportUnavailable` is the fixed redacted failure type.

The pair API has one stable call shape. `worlds` and `descriptor_mapping` are already assembled in memory, while `output` is the new destination chosen by the caller; `metadata` and the trusted test-only oracle contract are explicit rather than inferred from pair context:

```python
from pathlib import Path

from synthetic.package_export import (
    PackageExportMetadata,
    export_counterfactual_ehr_world_pair,
)
from synthetic.schema_contract import load_descriptor
from synthetic.validate import validate_structure
from tests.synthetic.fakes import (
    IdentityPreservingTestDerivationOracle,
    test_derivation_binding,
)

# `worlds` is a previously assembled and PASS-validated fictional pair.
descriptor_mapping = load_descriptor(Path("datapackage.json"))
metadata = PackageExportMetadata(
    profile="counterfactual-development",
    seed=20260831,
    reference_time="2026-08-31T00:00:00Z",
    reference_id="fictional-counterfactual-reference-v1",
    software_revision="development-example",
    configuration_sha256="a" * 64,
    reference_sha256="b" * 64,
)
output = export_counterfactual_ehr_world_pair(
    worlds,
    descriptor_mapping,
    Path("counterfactual-pair"),
    metadata=metadata,
    derivation_oracle=IdentityPreservingTestDerivationOracle(),
    derivation_binding=test_derivation_binding(),
)

# Existing package tooling receives an ordinary child, never the envelope.
validate_structure(output / "baseline", descriptor_mapping)
validate_structure(output / "intervention", descriptor_mapping)
```

The promoted output is one atomic envelope containing exactly `baseline/`, `intervention/`, and `pair-manifest.json`. The top-level envelope is not a PPOC package; pass `output / "baseline"` or `output / "intervention"` to ordinary structural/package tooling. Each child remains an exact eleven-file package: the eight descriptor-named CSVs (`patients.csv`, `patients_augmented.csv`, `visits.csv`, `visits_augmented-20251209150512.csv`, `labs.csv`, `medications.csv`, `problem_list.csv`, and `referrals.csv`), `datapackage.json`, `validation-report.json`, and `manifest.json`. The child packages use the unchanged exact descriptor and augmented-resource lifecycle, and the explicit test-only oracle owns the two augmented resources.

The pair manifest is aggregate-only and is not a truth manifest. Its fixed fields are `contract`, `schema_fingerprint`, `matrix_version`, `intervention`, `serialization_projection`, `validation_status`, `validation_check_counts`, visible `metadata`, and `children` entries containing only relative `path` values and child `manifest_sha256` digests. `serialization_projection` is always `ghd-result-flag-empty-v1`: source-world GHD rows whose evaluator-only `labs.result_flag="Synthetic"` marker is copied for serialization as the exact descriptor missing-value sentinel `""`; the in-memory worlds are never mutated, and no other value is normalized. The manifest contains no patient or visit identifiers, row values, ages, latent states, event payloads, hidden truth, trajectories, source objects, evaluator representations, descriptor contents, seeds or indexes from pair context, or temporary paths.

The exporter revalidates the pair and requires aggregate `PASS` before creating any public lifecycle path, calls the existing exact-schema child exporter exactly twice in fixed baseline/intervention order, and promotes only after an exact recursive inventory check. Invalid worlds, malformed descriptors or oracle contracts, output collisions, and post-creation failures are redacted as `counterfactual package export failed`; failed archives contain only fixed failure content. Successful structure is development evidence only: it is not prevalence or demographic calibration, held-out validation, temporal drift, task utility, clinical validity, privacy or non-matchability evidence, release approval, or Synthea conformance. Authoritative augmentation, cohort-scale generation, clinical review, privacy evaluation, non-matchability proof, release approval, and an optional later Synthea adapter remain separate deferred gates.

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

If a module exposes the optional `validate_patient(patient)` eligibility hook, both native composition kernels run it before any reference-backed baseline generation. Turner syndrome uses this hook to reject non-female reference series without making avoidable reference calls; modules without patient-specific eligibility retain the existing behavior.

For `infancy` and `transition`, the module's height effect adjusts the length z-score and its BMI effect adjusts the weight z-score; adjusted `length_cm` and `weight_kg` are then re-requested from the reference. At transition, standing height is the explicit length-to-height conversion and BMI is derived from weight and height. For `childhood`, `puberty`, and `adolescence`, the adjusted height and BMI z-scores are re-requested directly and weight is derived from BMI and height. Thus the anthropometric identities remain explicit: `BMI = weight_kg / (height_cm / 100) ** 2` whenever standing height and BMI exist, and pre-transition weight is the independent mass dimension. Transition continuity is rechecked after effects are applied, including sparse age pairs; invalid or nonfinite adjusted references, derived values, or velocities fail closed.

Constitutional delay has one schedule rule: sample the module's onset and delay, add `puberty_delay_days` to the sampled age-regime puberty onset, and replay physiology with that adjusted state. The module API includes a temporary-recovery height effect, but this composition uses its delay state to shift puberty and intentionally skips that overlapping height delta, so delay is applied exactly once. If the shifted onset falls outside the configured domain, composition fails closed rather than extrapolating. Other modules retain their own effects and event schedules: `HealthyGrowthModule` has zero anthropometric effect; `FamilialShortStatureModule` applies a constant negative height effect; `ConstitutionalDelayModule` supplies the temporary-recovery effect and delay state described above; `GrowthHormoneDeficiencyModule` applies progressive impairment with an optional causally ordered treatment response; `PediatricHypothyroidismModule` applies progressive impairment with a relative BMI increase and optional causally ordered treatment response; `CeliacDiseaseModule` applies weight/BMI-first decline, delayed height decline, and optional causally ordered partial recovery; `SmallForGestationalAgeModule` starts below reference size at birth, recovers BMI by one year, and either catches up in height by five years or retains a persistent height offset; `TurnerSyndromeModule` requires a female growth-reference sex, has no birth-state deficit, and applies progressive height impairment with optional treatment response and a relative BMI increase; `UndernutritionModule` applies weight/BMI-first decline, delayed progressive height impairment, and optional partial treatment recovery; and `ExcessWeightModule` applies sustained positive BMI growth without requiring a linear-growth effect, with optional partial treatment recovery. All ten are uncalibrated development scenarios; choosing a module is not prevalence estimation.

The composition requests only named `regime.birth`, `regime.childhood`, `regime.puberty`, `regime.residual`, `regime.head`, and the selected `disorder.<module-kind>` stream (for example, `disorder.familial_short_stature`, `disorder.pediatric_hypothyroidism`, `disorder.celiac_disease`, `disorder.small_for_gestational_age`, `disorder.turner_syndrome`, `disorder.undernutrition`, or `disorder.excess_weight`). It never requests a `growth` stream. The physiology, hidden disorder state, and hidden clinical-event trace remain an evaluator boundary and do not enter visible smoke output.

Non-GHD diagnosis, laboratory, medication, and referral descendants; prevalence and demographic calibration; held-out validation; privacy auditing; package-level counterfactual worlds; clinical approval of a reference; and Synthea conformance are deferred gates. These scenarios are not clinically validated and do not claim a match to real EHR or growth data. The healthy age-730+ smoke/export boundary remains three visits at ages 730, 1095, and 1460 days, and the existing non-matchability limitation still applies: synthetic generation alone cannot establish that a profile cannot be matched to a real patient.

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
- `PediatricHypothyroidismModule`: progressive negative Δheight-z, relative BMI-z increase during impairment, and an optional heterogeneous treatment response.
- `CeliacDiseaseModule`: weight/BMI-first decline, delayed height impairment, and an optional partial treatment recovery or nonresponse.
- `SmallForGestationalAgeModule`: negative birth length/weight effects, faster BMI catch-up, and either height catch-up or persistent short stature.
- `TurnerSyndromeModule`: female-reference-compatible progressive height impairment, no birth-state deficit, relative BMI increase, and an optional treatment response.
- `UndernutritionModule`: weight/BMI-first decline, delayed progressive height impairment, and an optional partial treatment recovery or nonresponse.
- `ExcessWeightModule`: sustained positive BMI growth without a linear-growth effect, with an optional partial treatment recovery or nonresponse.

The hypothyroidism, celiac-disease, SGA, Turner-syndrome, undernutrition, and excess-weight modules are trajectory-only in this slice: their generic workup, diagnosis, treatment, birth-state, or sex-reference events remain hidden evaluator state, with no TSH/free-T4, levothyroxine, celiac serology, gestational-age, karyotype, estrogen, nutrition-supplement, obesity-treatment, or other visible ancillary rows. Those disorder-specific descendants require a separate reviewed resource contract.

`EXCESS_WEIGHT` is evaluator-only and neither implies nor writes `obesity_flag`; that field remains separately derived from observed BMI percentile.

Each module and its frozen configuration exposes a stable, unique `module_version` identifier (currently the module name plus `-v1`). The identifier changes when the mechanism or its state/event semantics change; changing only scenario parameter values does not silently change the identifier, so callers should record both the identifier and configuration. Zero-effect states emit only their hidden latent-onset event; a treated zero-response state emits `treatment_nonresponse` rather than a treatment-response event, and a nonzero response always requires a treatment start.

These defaults are uncalibrated development scenarios. `LatentTrajectory.disorder` and `LatentTrajectory.events` are evaluator-only hidden truth and event traces; they are not exported, and visible CSV generation remains unchanged. Prevalence, demographic calibration, disorder-critical labs/medications/referrals, held-out validation, privacy auditing, and package-level counterfactual worlds remain later gates. No real patient data, clinical claim, or privacy claim is introduced by this layer.

## Prerequisites

Run these commands from the repository root:

```sh
uv sync
```

The package requires Python 3.12 or newer. The test-only reference and derivation oracle used in the smoke example below live under `tests/synthetic/fakes.py`; they are safe for smoke tests but must not be presented as clinical or privacy evidence.

## Run the smoke profile from Python

`generate_smoke` requires an injected `GrowthReference`, an injected `DerivationOracle`, and an explicit derivation binding. The output path must not already exist.

```python
import tempfile
from pathlib import Path

from synthetic.generate import generate_smoke
from tests.synthetic.fakes import (
    IdentityPreservingTestDerivationOracle,
    LinearTestReference,
    test_derivation_binding,
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
    derivation_binding=test_derivation_binding(),
)
print(promoted)
```

The binding must come from configuration outside the oracle result. The generator rejects an oracle identity, implementation fingerprint, or test-only classification mismatch. The test oracle's fixed fingerprint is intentionally visible test metadata, not a production identity.

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

All CSV headers, field order, dialects, encodings, constraints, keys, and logical links come from the source descriptor. Ancillary base resources are represented with schema-correct headers and may be empty in this smoke profile. The generated descriptor removes source snapshot statistics, provenance, and project-governance metadata while retaining schema semantics and generated-only statistics; those source-only fields do not become ordinary fixture requirements.

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

The default/no-profile invocation intentionally exits with the fixed unavailable-oracle message after parsing its basic arguments:

```sh
uv run python -m synthetic.generate --output /tmp/ppoc-smoke --patients 10 --seed 20260830
```

That behavior is intentional. Do not treat a command-line failure as a missing flag or bypass the injected-reference/oracle boundary. The three explicit development profiles are documented above; they use the pinned source-matched runtime for test-only reproducibility and do not enable a production route. Wire a reviewed production reference and authoritative oracle through an explicit API/CLI design before enabling a production route.

## Claims and non-claims

The smoke and explicit development profiles are suitable for exercising schema loaders, joins, deterministic pipelines, counterfactual plumbing, and failure handling. They do not establish that generated trajectories match real growth distributions, that growth-disorder prevalence or demographics are representative, or that downstream clinical decisions are valid.

It also does not demonstrate that a generated patient profile cannot be matched to a real patient. Structural safeguards and synthetic-only inputs reduce accidental leakage, while a separate privacy evaluation provides only qualified, policy-bound evidence under its approved data-governance process (for example, linkage, attribute-disclosure, and membership-inference testing); it does not prove non-matchability. Do not publish any generated package as a golden, validated, clinical, representative, privacy-safe, or release-approved fixture.
