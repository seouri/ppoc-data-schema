from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

import pytest

from synthetic.augmenter_oracle import (
    AUGMENTER_ORACLE_ID,
    AUGMENTER_RUNTIME_MANIFEST_SHA256,
    SourceMatchedAugmenterOracle,
)
from synthetic.cohort import (
    CalibrationSamplingProfile,
    CohortConfig,
    CohortModuleWeight,
    NativeCohort,
    generate_native_cohort,
)
from synthetic.cohort_validation import (
    CohortValidationPolicy,
    CohortValidationStatus,
    validate_native_cohort,
)
from synthetic.derivation_binding import DerivationBinding
from synthetic.models import DisorderKind
from synthetic.native.clinical_modules import (
    GrowthHormoneDeficiencyModule,
    HealthyGrowthModule,
)
from synthetic.native.observations import (
    CensoringMode,
    ObservationPolicy,
    RecordedEventKind,
)
from synthetic.native.resources import BASE_RESOURCE_NAMES
from synthetic.package_export import PackageExportMetadata, export_exact_schema_package
from synthetic.schema_contract import (
    EXPECTED_SCHEMA_FINGERPRINT,
    load_descriptor,
    schema_fingerprint,
)
from synthetic.task_utility import (
    TASK_UTILITY_REPORT_VERSION,
    TaskPrediction,
    TaskUtilityPolicy,
    TaskUtilityReport,
    evaluate_task_utility,
)
from synthetic.temporal_drift import (
    TEMPORAL_DRIFT_REPORT_VERSION,
    TemporalDriftPolicy,
    TemporalDriftReport,
    TemporalDriftStatus,
    TemporalWindowPolicy,
    validate_temporal_drift,
)
from tests.synthetic.cohort_fixtures import aggregate_calibration_artifact
from tests.synthetic.fakes import RegimeLinearTestReference, test_derivation_binding

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "synthetic-generator.md"
README = ROOT / "README.md"
_SCALE_ENABLED = os.environ.get("SYNTHETIC_RUN_SCALE") == "1"
_SCALE_SEEDS = (20260830, 20260831, 20260901)
_SCALE_PATIENT_COUNT = 10_000
_SCALE_VISIT_COUNT = 110_000
_SCALE_AGES = (
    0,
    365,
    730,
    1460,
    2190,
    3650,
    4380,
    5114,
    5475,
    6200,
    7305,
)
_REFERENCE_SEX_MAPPING = (("F", "F"), ("M", "M"), ("U", "U"))
_BASE_ROW_COUNTS = {
    "patients": _SCALE_PATIENT_COUNT,
    "visits": _SCALE_VISIT_COUNT,
    "labs": 0,
    "medications": 0,
    "problem_list": 0,
    "referrals": 0,
}
_PACKAGE_ROW_COUNTS = {
    "patients": _SCALE_PATIENT_COUNT,
    "patients_augmented": _SCALE_PATIENT_COUNT,
    "visits": _SCALE_VISIT_COUNT,
    "visits_augmented": _SCALE_VISIT_COUNT,
    "labs": 0,
    "medications": 0,
    "problem_list": 0,
    "referrals": 0,
}


def _descriptor() -> dict[str, Any]:
    return load_descriptor(ROOT / "datapackage.json")


def _calibration() -> CalibrationSamplingProfile:
    return CalibrationSamplingProfile.from_artifact(aggregate_calibration_artifact())


def _modules() -> dict[DisorderKind, object]:
    return {
        DisorderKind.HEALTHY: HealthyGrowthModule(),
        DisorderKind.GROWTH_HORMONE_DEFICIENCY: GrowthHormoneDeficiencyModule(),
    }


def _observation_policy() -> ObservationPolicy:
    return ObservationPolicy(
        policy_version="development-scale-observation-v1",
        window_start_age_days=0,
        window_end_age_days=7306,
        censoring_mode=CensoringMode.NONE,
        censor_age_days=None,
        visit_probability=1.0,
        length_availability_probability=0.0,
        height_availability_probability=1.0,
        weight_availability_probability=1.0,
        head_circumference_availability_probability=1.0,
        length_error_sd_cm=0.0,
        height_error_sd_cm=0.0,
        weight_error_sd_kg=0.0,
        head_circumference_error_sd_cm=0.0,
        rounding_digits=None,
        recognition_probability=0.0,
        diagnosis_probability=0.0,
        recognition_delay_days=0,
    )


def _cohort_config(seed: int) -> CohortConfig:
    return CohortConfig(
        profile="development-scale-v1",
        patient_count=_SCALE_PATIENT_COUNT,
        seed=seed,
        ages_days=_SCALE_AGES,
        observation_policy=_observation_policy(),
        module_weights=(
            CohortModuleWeight(DisorderKind.HEALTHY, 0.5),
            CohortModuleWeight(DisorderKind.GROWTH_HORMONE_DEFICIENCY, 0.5),
        ),
        reference_sex_mapping=_REFERENCE_SEX_MAPPING,
    )


def _cohort_policy() -> CohortValidationPolicy:
    return CohortValidationPolicy(
        policy_id="development-scale-cohort-v1",
        policy_version="1",
        minimum_cohort_size=_SCALE_PATIENT_COUNT,
        minimum_cell_support=1,
        minimum_event_support=1,
        proportion_tolerance=0.05,
        growth_tolerances={
            "height_z_score": 2.0,
            "bmi_z_score": 2.0,
            "height_velocity_cm_per_year": 20.0,
            "weight_velocity_kg_per_year": 20.0,
        },
        required_age_windows=(
            ("infancy", 0, 730),
            ("transition", 730, 1460),
            ("childhood", 1460, 3650),
            ("puberty", 3650, 5475),
            ("adolescence", 5475, 7306),
        ),
    )


def _temporal_window(
    window_id: str, lower_age_days: int, upper_age_days: int
) -> TemporalWindowPolicy:
    return TemporalWindowPolicy(
        window_id=window_id,
        lower_age_days=lower_age_days,
        upper_age_days=upper_age_days,
        minimum_member_support=_SCALE_PATIENT_COUNT,
        minimum_growth_points=1,
        minimum_visible_visits=1,
        minimum_growth_coverage=1.0,
        minimum_visible_visit_coverage=1.0,
        maximum_mean_inter_visit_days=2_000.0,
        maximum_visit_count_step=11.0,
        maximum_recorded_event_rate_step=1.0,
    )


def _temporal_policy() -> TemporalDriftPolicy:
    return TemporalDriftPolicy(
        policy_id="development-scale-temporal-v1",
        policy_version="1",
        minimum_cohort_size=_SCALE_PATIENT_COUNT,
        maximum_unevaluable_checks=10,
        windows=(
            _temporal_window("infancy", 0, 730),
            _temporal_window("transition", 730, 1460),
            _temporal_window("childhood", 1460, 3650),
            _temporal_window("puberty", 3650, 5475),
            _temporal_window("adolescence", 5475, 7306),
        ),
    )


def _task_policy() -> TaskUtilityPolicy:
    return TaskUtilityPolicy(
        policy_id="development-scale-task-v1",
        policy_version="1",
        minimum_cohort_size=4,
        minimum_evaluable_members=1,
        minimum_class_support=1,
        maximum_unevaluable_members=0,
        require_probability_scores=True,
        minimum_sensitivity=0.0,
        minimum_specificity=0.0,
        minimum_auroc=0.0,
        maximum_brier_score=1.0,
        subgroup_dimensions=(),
    )


def _candidate_binding() -> DerivationBinding:
    mapping = test_derivation_binding().to_mapping()
    oracle = mapping["oracle"]
    assert isinstance(oracle, dict)
    oracle["oracle_id"] = AUGMENTER_ORACLE_ID
    oracle["implementation_fingerprint"] = AUGMENTER_RUNTIME_MANIFEST_SHA256
    return DerivationBinding.from_mapping(mapping)


def _base_rows(cohort: NativeCohort) -> dict[str, list[dict[str, object]]]:
    rows = {name: [] for name in BASE_RESOURCE_NAMES}
    for member in cohort.members:
        bundle = member.bundle
        assert bundle is not None
        for resource_name in BASE_RESOURCE_NAMES:
            rows[resource_name].extend(
                row.to_mapping() for row in bundle.rows[resource_name]
            )
    return rows


def _visible_task_predictions(cohort: NativeCohort) -> tuple[TaskPrediction, ...]:
    predictions: list[TaskPrediction] = []
    for member in cohort.members:
        diagnosed = any(
            event.event_kind is RecordedEventKind.DIAGNOSIS
            for event in member.frame.events
        )
        predictions.append(TaskPrediction(diagnosed, float(diagnosed)))
    return tuple(predictions)


def _csv_row_count(path: Path, encoding: str) -> int:
    with path.open(encoding=encoding, newline="") as stream:
        return sum(1 for _ in csv.DictReader(stream))


def _package_row_counts(
    package: Path, descriptor: dict[str, Any]
) -> dict[str, int]:
    return {
        resource["name"]: _csv_row_count(
            package / resource["path"], resource.get("encoding", "utf-8")
        )
        for resource in descriptor["resources"]
    }


def _package_inventory(package: Path) -> tuple[str, ...]:
    return tuple(
        sorted(
            path.relative_to(package).as_posix()
            for path in package.rglob("*")
            if path.is_file()
        )
    )


def _scale_documentation_section(document: str) -> str:
    heading = "## Scheduled development scale profile\n"
    assert heading in document
    return document.split(heading, maxsplit=1)[1].split("\n## ", maxsplit=1)[0]


def test_development_scale_documentation_declares_scheduled_gate_and_boundaries() -> None:
    guide = _scale_documentation_section(GUIDE.read_text(encoding="utf-8"))
    readme = README.read_text(encoding="utf-8")

    assert "SYNTHETIC_RUN_SCALE=1 uv run pytest -m scale tests/synthetic/test_development_scale.py" in guide
    for detail in (
        "20260830",
        "20260831",
        "20260901",
        "10,000-patient",
        "temporary package",
        "all eight descriptor resources",
        "derivation",
        "longitudinal",
        "task",
        "opt-in",
    ):
        assert detail in guide

    for non_claim in (
        "prevalence",
        "clinical validity",
        "real labels",
        "privacy/non-matchability",
        "held-out",
        "Synthea",
        "release evidence",
    ):
        assert non_claim in guide

    assert "[synthetic generator guide](docs/synthetic-generator.md)" in readme


@pytest.mark.parametrize(
    "seed", _SCALE_SEEDS, ids=lambda seed: str(seed)
)
@pytest.mark.scale
@pytest.mark.skipif(
    not _SCALE_ENABLED,
    reason="set SYNTHETIC_RUN_SCALE=1 to run the development scale profile",
)
def test_development_scale_profile(seed: int, tmp_path: Path) -> None:
    descriptor = _descriptor()
    cohort = generate_native_cohort(
        _cohort_config(seed),
        RegimeLinearTestReference(),
        _calibration(),
        modules=_modules(),
        descriptor=descriptor,
    )

    assert type(cohort) is NativeCohort
    assert len(cohort.members) == _SCALE_PATIENT_COUNT
    patient_ids = tuple(member.demographics.patient_id for member in cohort.members)
    visit_ids = tuple(
        visit.visit_id
        for member in cohort.members
        for visit in member.frame.visits
    )
    assert len(patient_ids) == len(set(patient_ids)) == _SCALE_PATIENT_COUNT
    assert len(visit_ids) == len(set(visit_ids)) == _SCALE_VISIT_COUNT
    assert all(patient_id.startswith("syn-") for patient_id in patient_ids)
    assert all(visit_id.startswith("syn-") for visit_id in visit_ids)
    assert cohort.to_mapping()["visible_visit_count"] == _SCALE_VISIT_COUNT

    cohort_report = validate_native_cohort(cohort, _cohort_policy())
    assert not any(
        comparison.status is CohortValidationStatus.FAIL
        for comparison in cohort_report.comparisons
    )

    temporal_report = validate_temporal_drift(cohort, _temporal_policy())
    assert type(temporal_report) is TemporalDriftReport
    assert temporal_report.report_version == TEMPORAL_DRIFT_REPORT_VERSION
    assert temporal_report.cohort_size == _SCALE_PATIENT_COUNT
    assert all(
        comparison.reason_code != "STRUCTURAL_INVALID"
        for comparison in temporal_report.comparisons
    )
    assert temporal_report.status in {
        TemporalDriftStatus.PASS,
        TemporalDriftStatus.UNEVALUABLE,
    }

    task_report = evaluate_task_utility(
        cohort,
        _visible_task_predictions(cohort),
        _task_policy(),
    )
    assert type(task_report) is TaskUtilityReport
    assert task_report.report_version == TASK_UTILITY_REPORT_VERSION
    assert task_report.cohort_size == _SCALE_PATIENT_COUNT

    base_rows = _base_rows(cohort)
    assert {name: len(rows) for name, rows in base_rows.items()} == _BASE_ROW_COUNTS
    binding = _candidate_binding()
    assert binding.test_only is True
    assert binding.oracle.oracle_id == AUGMENTER_ORACLE_ID
    assert (
        binding.oracle.implementation_fingerprint
        == AUGMENTER_RUNTIME_MANIFEST_SHA256
    )
    package = export_exact_schema_package(
        descriptor,
        base_rows,
        tmp_path / f"development-scale-{seed}",
        metadata=PackageExportMetadata(
            profile="development-scale",
            seed=seed,
            reference_time="2026-09-01T00:00:00Z",
            reference_id="fictional-development-scale-v1",
            software_revision="development-scale-test-v1",
            configuration_sha256="a" * 64,
            reference_sha256="b" * 64,
        ),
        derivation_oracle=SourceMatchedAugmenterOracle(),
        derivation_binding=binding,
    )

    generated_descriptor = load_descriptor(package / "datapackage.json")
    generated_names = tuple(
        resource["name"] for resource in generated_descriptor["resources"]
    )
    descriptor_names = tuple(resource["name"] for resource in descriptor["resources"])
    assert len(generated_names) == 8
    assert generated_names == descriptor_names
    assert set(generated_names) == {
        "patients",
        "patients_augmented",
        "visits",
        "visits_augmented",
        "labs",
        "medications",
        "problem_list",
        "referrals",
    }
    assert _package_row_counts(package, generated_descriptor) == _PACKAGE_ROW_COUNTS
    assert schema_fingerprint(generated_descriptor) == EXPECTED_SCHEMA_FINGERPRINT

    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["seed"] == seed
    assert manifest["schema_fingerprint"] == EXPECTED_SCHEMA_FINGERPRINT
    assert manifest["row_counts"] == _PACKAGE_ROW_COUNTS
    assert manifest["derivation_fingerprint"] == AUGMENTER_RUNTIME_MANIFEST_SHA256
    assert manifest["status"] == "STRUCTURE_VALIDATED_TEST_ORACLE"

    expected_inventory = tuple(
        sorted(
            [resource["path"] for resource in descriptor["resources"]]
            + ["datapackage.json", "validation-report.json", "manifest.json"]
        )
    )
    assert _package_inventory(package) == expected_inventory
