"""Frozen development-only binding for the pinned CDC augmenter runtime."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

from synthetic.augmenter_oracle import (
    AUGMENTER_ORACLE_ID,
    AUGMENTER_RUNTIME_MANIFEST_SHA256,
    UV_LOCK_SHA256,
    SourceMatchedAugmenterOracle,
    verify_source_matched_runtime,
)
from synthetic.calibration_targets import TARGET_REGISTRY_VERSION
from synthetic.cdc_reference import CdcGrowthReference
from synthetic.cohort import (
    CalibrationSamplingProfile,
    CohortConfig,
    CohortModuleWeight,
    NativeCohort,
    generate_native_cohort,
)
from synthetic.derivation_binding import (
    DERIVATION_BINDING_VERSION,
    REQUIRED_GOLDEN_CATEGORIES,
    DerivationBinding,
)
from synthetic.models import DisorderKind
from synthetic.native.clinical_modules import (
    GrowthHormoneDeficiencyModule,
    HealthyGrowthModule,
)
from synthetic.native.observations import CensoringMode, ObservationPolicy
from synthetic.native.resources import (
    BASE_RESOURCE_NAMES,
    ResourceValidationStatus,
    validate_observed_resources,
)
from synthetic.package_export import (
    PackageExportMetadata,
    PackageExportUnavailable,
    _require_output_available,
    export_exact_schema_package,
)
from synthetic.schema_contract import EXPECTED_SCHEMA_FINGERPRINT, load_descriptor

_REFERENCE_ID = "cdc-lms-reference-v1"
_REFERENCE_VERSION = "cdc-lms-mapping-v1"
_BINDING_ID = "development-augmenter-v1"
_SOURCE_REVISION = "augment-runtime-v1"
_SOURCE_KIND = "authoritative_implementation"
_RUNTIME_MISMATCH = "development runtime identities are inconsistent"
_COHORT_PROFILE = "development-cohort-v1"
_COHORT_PACKAGE_PROFILE = "development-cohort"
_OBSERVATION_POLICY_VERSION = "development-cohort-observation-v1"
_COHORT_AGES_DAYS = (0, 365, 730, 1460, 2190, 3650, 4380, 5114, 5475, 6200, 7305)
_REFERENCE_SEX_MAPPING = (("F", "F"), ("M", "M"), ("U", "U"))
_PACKAGE_EXPORT_FAILURE = "observed package export failed"


@dataclass(frozen=True)
class DevelopmentRuntime:
    """Reference, oracle, and aggregate-only test binding for development."""

    reference: CdcGrowthReference
    derivation_oracle: SourceMatchedAugmenterOracle
    derivation_binding: DerivationBinding
    dependency_fingerprint: str

    def __post_init__(self) -> None:
        try:
            standard = self.derivation_binding.reference_standard
            oracle = self.derivation_binding.oracle
            golden = self.derivation_binding.golden_evidence
            review = self.derivation_binding.review
            matches = (
                isinstance(self.reference, CdcGrowthReference)
                and isinstance(self.derivation_oracle, SourceMatchedAugmenterOracle)
                and isinstance(self.derivation_binding, DerivationBinding)
                and self.dependency_fingerprint == UV_LOCK_SHA256
                and self.derivation_binding.binding_version == DERIVATION_BINDING_VERSION
                and self.derivation_binding.binding_id == _BINDING_ID
                and self.derivation_binding.schema_fingerprint
                == EXPECTED_SCHEMA_FINGERPRINT
                and self.derivation_binding.test_only is True
                and self.reference.reference_id == _REFERENCE_ID
                and standard.standard_id == self.reference.reference_id
                and standard.standard_fingerprint == self.reference.source_sha256
                and standard.version == _REFERENCE_VERSION
                and self.derivation_oracle.oracle_id == AUGMENTER_ORACLE_ID
                and oracle.oracle_id == self.derivation_oracle.oracle_id
                and oracle.implementation_fingerprint
                == self.derivation_oracle.implementation_fingerprint
                and oracle.implementation_fingerprint
                == AUGMENTER_RUNTIME_MANIFEST_SHA256
                and oracle.source_revision == _SOURCE_REVISION
                and oracle.source_kind == _SOURCE_KIND
                and oracle.dependency_fingerprint == self.dependency_fingerprint
                and golden.manifest_id is None
                and golden.manifest_fingerprint is None
                and golden.parity_contract is None
                and golden.parity_report_id is None
                and golden.parity_report_fingerprint is None
                and golden.parity_status == "UNEVALUABLE"
                and golden.candidate_implementation_fingerprint is None
                and golden.reference_implementation_fingerprint is None
                and golden.parity_schema_fingerprint is None
                and golden.covered_categories == REQUIRED_GOLDEN_CATEGORIES
                and golden.bidirectional_case_count == 0
                and golden.synthetic_fuzz_case_count == 0
                and golden.fuzz_corpus_fingerprint is None
                and review.review_id is None
                and review.review_fingerprint is None
                and review.reviewed_at is None
                and review.reviewer_role is None
                and review.status == "PENDING"
            )
        except Exception:  # noqa: BLE001 - expose no implementation details at this boundary.
            matches = False
        if not matches:
            raise ValueError(_RUNTIME_MISMATCH)


def build_development_runtime(repository_root: Path) -> DevelopmentRuntime:
    """Build the test-only runtime from the verified checked-in closure."""
    verify_source_matched_runtime(repository_root)
    reference = CdcGrowthReference.from_repository(repository_root)
    oracle = SourceMatchedAugmenterOracle(repository_root)
    binding = DerivationBinding.from_mapping(
        {
            "binding_version": "derivation-binding-v1",
            "binding_id": _BINDING_ID,
            "schema_fingerprint": EXPECTED_SCHEMA_FINGERPRINT,
            "oracle": {
                "oracle_id": AUGMENTER_ORACLE_ID,
                "implementation_fingerprint": AUGMENTER_RUNTIME_MANIFEST_SHA256,
                "source_revision": _SOURCE_REVISION,
                "dependency_fingerprint": UV_LOCK_SHA256,
                "source_kind": _SOURCE_KIND,
            },
            "reference_standard": {
                "standard_id": _REFERENCE_ID,
                "standard_fingerprint": reference.source_sha256,
                "version": _REFERENCE_VERSION,
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
                "covered_categories": list(REQUIRED_GOLDEN_CATEGORIES),
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
    return DevelopmentRuntime(reference, oracle, binding, UV_LOCK_SHA256)


def development_calibration_profile() -> CalibrationSamplingProfile:
    """Return the immutable, wholly generated development demographic profile."""
    return CalibrationSamplingProfile(
        artifact_id=_COHORT_PROFILE,
        target_registry_version=TARGET_REGISTRY_VERSION,
        # The CDC reference has F/M tables only; retain U structurally but never sample it.
        sex_weights=(("F", 0.50), ("M", 0.50), ("U", 0.00)),
        ethnicity_weights=(
            ("", 0.02),
            ("Not Hispanic or Latino", 0.65),
            ("Hispanic or Latino", 0.18),
            ("Choose not to Answer", 0.03),
            ("Unknown", 0.04),
            ("Unable to collect", 0.03),
            ("Patient does not know", 0.05),
        ),
        race_weights=(
            ("", 0.01),
            ("American Indian or Alaska Native", 0.01),
            ("Another Race", 0.03),
            ("Asian", 0.08),
            ("Black or African American", 0.12),
            ("Choose not to answer", 0.02),
            ("Middle Eastern or Northern African", 0.02),
            ("Native Hawaiian or Other Pacific Islander", 0.01),
            ("Patient does not know", 0.02),
            ("Unable to collect", 0.02),
            ("Unknown", 0.04),
            ("White", 0.62),
        ),
        race_multiselect_probability=0.06,
        recorded_healthy_probability=0.0,
        recorded_growth_dx_probability=0.0,
    )


def development_cohort_config(patient_count: int, seed: int) -> CohortConfig:
    """Return the immutable healthy-plus-GHD development cohort configuration."""
    return CohortConfig(
        profile=_COHORT_PROFILE,
        patient_count=patient_count,
        seed=seed,
        ages_days=_COHORT_AGES_DAYS,
        observation_policy=ObservationPolicy(
            policy_version=_OBSERVATION_POLICY_VERSION,
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
        ),
        module_weights=(
            CohortModuleWeight(DisorderKind.HEALTHY, 0.5),
            CohortModuleWeight(DisorderKind.GROWTH_HORMONE_DEFICIENCY, 0.5),
        ),
        reference_sex_mapping=_REFERENCE_SEX_MAPPING,
    )


def build_development_cohort(
    runtime: DevelopmentRuntime,
    *,
    descriptor: Mapping[str, object],
    patient_count: int,
    seed: int,
) -> NativeCohort:
    """Build the evaluator-held native cohort before its visible rows are exported."""
    if not isinstance(runtime, DevelopmentRuntime):
        raise TypeError("runtime must be a DevelopmentRuntime")
    config = development_cohort_config(patient_count, seed)
    cohort = generate_native_cohort(
        config,
        runtime.reference,
        development_calibration_profile(),
        modules={
            DisorderKind.HEALTHY: HealthyGrowthModule(),
            DisorderKind.GROWTH_HORMONE_DEFICIENCY: GrowthHormoneDeficiencyModule(),
        },
        descriptor=descriptor,
    )
    if type(cohort) is not NativeCohort:
        raise ValueError("native cohort generation did not return a native cohort")
    for member in cohort.members:
        bundle = member.bundle
        if (
            bundle is None
            or validate_observed_resources(bundle).status is not ResourceValidationStatus.PASS
        ):
            raise ValueError("observed resource bundle did not pass validation")
    return cohort


def _configuration_sha256(
    runtime: DevelopmentRuntime,
    config: CohortConfig,
    calibration: CalibrationSamplingProfile,
) -> str:
    configuration = {
        "profile": config.profile,
        "patient_count": config.patient_count,
        "ages_days": config.ages_days,
        "observation_policy": config.observation_policy.to_mapping(),
        "module_weights": tuple(
            (weight.kind.value, weight.probability) for weight in config.module_weights
        ),
        "reference_sex_mapping": config.reference_sex_mapping,
        "age_regime": {
            "module_version": config.age_regime_config.module_version,
            "parameters": asdict(config.age_regime_config),
        },
        "clinical_module_versions": {
            DisorderKind.HEALTHY.value: HealthyGrowthModule.module_version,
            DisorderKind.GROWTH_HORMONE_DEFICIENCY.value: GrowthHormoneDeficiencyModule.module_version,
        },
        "calibration": {
            "artifact_id": calibration.artifact_id,
            "target_registry_version": calibration.target_registry_version,
            "sex_weights": calibration.sex_weights,
            "ethnicity_weights": calibration.ethnicity_weights,
            "race_weights": calibration.race_weights,
            "race_multiselect_probability": calibration.race_multiselect_probability,
            "recorded_healthy_probability": calibration.recorded_healthy_probability,
            "recorded_growth_dx_probability": calibration.recorded_growth_dx_probability,
        },
        "reference": {
            "reference_id": runtime.reference.reference_id,
            "source_sha256": runtime.reference.source_sha256,
        },
    }
    payload = json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _visible_base_rows(cohort: NativeCohort) -> dict[str, list[dict[str, object]]]:
    rows = {resource_name: [] for resource_name in BASE_RESOURCE_NAMES}
    for member in cohort.members:
        bundle = member.bundle
        if bundle is None:
            raise ValueError("observed resource bundle did not pass validation")
        for resource_name in BASE_RESOURCE_NAMES:
            rows[resource_name].extend(
                row.to_mapping() for row in bundle.rows[resource_name]
            )
    return rows


def generate_development_cohort(
    runtime: DevelopmentRuntime,
    *,
    descriptor_path: Path,
    output: Path,
    patient_count: int,
    seed: int,
    reference_time: str,
    software_revision: str,
) -> Path:
    """Generate and promote an exact-schema development cohort package."""
    try:
        _require_output_available(output)
        descriptor = load_descriptor(descriptor_path)
        cohort = build_development_cohort(
            runtime,
            descriptor=descriptor,
            patient_count=patient_count,
            seed=seed,
        )
        config = development_cohort_config(patient_count, seed)
        calibration = development_calibration_profile()
        return export_exact_schema_package(
            descriptor,
            _visible_base_rows(cohort),
            output,
            metadata=PackageExportMetadata(
                profile=_COHORT_PACKAGE_PROFILE,
                seed=seed,
                reference_time=reference_time,
                reference_id=runtime.reference.reference_id,
                reference_sha256=runtime.reference.source_sha256,
                configuration_sha256=_configuration_sha256(runtime, config, calibration),
                software_revision=software_revision,
            ),
            derivation_oracle=runtime.derivation_oracle,
            derivation_binding=runtime.derivation_binding,
        )
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:  # noqa: BLE001 - package failures must expose only the fixed contract.
        raise PackageExportUnavailable(_PACKAGE_EXPORT_FAILURE) from None
