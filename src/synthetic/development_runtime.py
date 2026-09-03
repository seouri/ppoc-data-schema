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
from synthetic.cdc_reference import CDC_GENERATION_DOMAIN_POLICY, CdcGrowthReference
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
from synthetic.native.age_regimes import AgeRegimeConfig
from synthetic.native.ancillary import (
    GHD_LAB_COMPONENT_NAMES,
    GHD_LAB_RESULT_FLAG,
    GhdAncillaryPolicy,
    project_ghd_ancillary_resources,
)
from synthetic.native.ancillary_bundle import merge_ghd_ancillary_resources
from synthetic.native.clinical_modules import (
    CeliacDiseaseModule,
    ConstitutionalDelayModule,
    ExcessWeightModule,
    FamilialShortStatureModule,
    GrowthHormoneDeficiencyModule,
    HealthyGrowthModule,
    PediatricHypothyroidismModule,
    SmallForGestationalAgeModule,
    TurnerSyndromeModule,
    UndernutritionModule,
)
from synthetic.native.multidisorder_ancillary import (
    MultidisorderAncillaryPolicy,
    merge_multidisorder_ancillary_resources,
    project_multidisorder_ancillary_resources,
)
from synthetic.native.observations import CensoringMode, ObservationPolicy, RecordedEventKind
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
_REALISTIC_PROFILE = "development-realistic-v1"
_REALISTIC_PACKAGE_PROFILE = "development-realistic"
_REALISTIC_OBSERVATION_POLICY_VERSION = "development-realistic-observation-v1"
_REALISTIC_TARGET_SNAPSHOT = "schema-stats-2026-08-24"
_REALISTIC_GROWTH_DIAGNOSIS_CODE = "E23.0"
_REALISTIC_ANCILLARY_POLICY_ID = "development-realistic-ghd"
_REALISTIC_ANCILLARY_POLICY_VERSION = "development-realistic-ghd-v1"
_REALISTIC_ANCILLARY_RESULT_DELAY_DAYS = 7
_ALL_DISORDER_PROFILE = "development-all-disorders-v1"
_ALL_DISORDER_PACKAGE_PROFILE = "development-all-disorders"
_ALL_DISORDER_OBSERVATION_POLICY_VERSION = (
    "development-all-disorders-observation-v1"
)
_ALL_DISORDER_TARGET_SNAPSHOT = "schema-stats-2026-08-24"
_ALL_DISORDER_ELIGIBILITY_POLICY_VERSION = "reference-sex-module-eligibility-v1"
_ALL_DISORDER_ANCILLARY_POLICY_ID = "development-all-disorders"
_ALL_DISORDER_ANCILLARY_POLICY_VERSION = "development-all-disorders-ancillary-v1"
_ALL_DISORDER_ANCILLARY_RESULT_DELAY_DAYS = 7
_REALISTIC_DENOMINATOR = 250_588
_REALISTIC_GROWTH_DX_COUNT = 35_907
_REALISTIC_SEX_WEIGHTS = (
    ("F", 122_883 / _REALISTIC_DENOMINATOR),
    ("M", 127_699 / _REALISTIC_DENOMINATOR),
    ("U", 0.0),
)
_REALISTIC_ETHNICITY_WEIGHTS = (
    ("", 0.0),
    ("Not Hispanic or Latino", 170_594 / _REALISTIC_DENOMINATOR),
    ("Hispanic or Latino", 28_549 / _REALISTIC_DENOMINATOR),
    ("Choose not to Answer", 24_566 / _REALISTIC_DENOMINATOR),
    ("Unknown", (20_834 + 5_464) / _REALISTIC_DENOMINATOR),
    ("Unable to collect", 450 / _REALISTIC_DENOMINATOR),
    ("Patient does not know", 131 / _REALISTIC_DENOMINATOR),
)
_REALISTIC_RACE_WEIGHTS = (
    ("", 0.0),
    ("American Indian or Alaska Native", 625 / _REALISTIC_DENOMINATOR),
    ("Another Race", 15_950 / _REALISTIC_DENOMINATOR),
    ("Asian", 15_661 / _REALISTIC_DENOMINATOR),
    ("Black or African American", 12_162 / _REALISTIC_DENOMINATOR),
    ("Choose not to answer", 17_534 / _REALISTIC_DENOMINATOR),
    ("Middle Eastern or Northern African", 512 / _REALISTIC_DENOMINATOR),
    ("Native Hawaiian or Other Pacific Islander", 248 / _REALISTIC_DENOMINATOR),
    ("Patient does not know", 126 / _REALISTIC_DENOMINATOR),
    ("Unable to collect", 492 / _REALISTIC_DENOMINATOR),
    ("Unknown", (23_085 + 8_818) / _REALISTIC_DENOMINATOR),
    ("White", 155_375 / _REALISTIC_DENOMINATOR),
)
_REALISTIC_GHD_PRIOR = _REALISTIC_GROWTH_DX_COUNT / _REALISTIC_DENOMINATOR
_REALISTIC_RACE_MULTISELECT_PROBABILITY = (
    _REALISTIC_DENOMINATOR - 237_397
) / _REALISTIC_DENOMINATOR
_COHORT_AGES_DAYS = (0, 365, 730, 1460, 2190, 3650, 4380, 5114, 5475, 6200, 7305)
_REFERENCE_SEX_MAPPING = (("F", "F"), ("M", "M"), ("U", "U"))
_PACKAGE_EXPORT_FAILURE = "observed package export failed"
_ALL_DISORDER_MODULE_CLASSES = (
    HealthyGrowthModule,
    FamilialShortStatureModule,
    ConstitutionalDelayModule,
    GrowthHormoneDeficiencyModule,
    PediatricHypothyroidismModule,
    CeliacDiseaseModule,
    SmallForGestationalAgeModule,
    TurnerSyndromeModule,
    UndernutritionModule,
    ExcessWeightModule,
)


def _all_disorder_module_weights(
    *, nonhealthy_probability: float, turner_probability: float
) -> tuple[CohortModuleWeight, ...]:
    return tuple(
        CohortModuleWeight(
            kind,
            (
                0.5
                if kind is DisorderKind.HEALTHY
                else turner_probability
                if kind is DisorderKind.TURNER_SYNDROME
                else nonhealthy_probability
            ),
        )
        for kind in DisorderKind
    )


_ALL_DISORDER_F_PRIOR = _all_disorder_module_weights(
    nonhealthy_probability=1 / 18,
    turner_probability=1 / 18,
)
_ALL_DISORDER_M_PRIOR = _all_disorder_module_weights(
    nonhealthy_probability=1 / 16,
    turner_probability=0.0,
)


def _all_disorder_modules() -> dict[DisorderKind, object]:
    modules = tuple(module_class() for module_class in _ALL_DISORDER_MODULE_CLASSES)
    return {module.kind: module for module in modules}


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


def development_realistic_calibration_profile() -> CalibrationSamplingProfile:
    """Return the frozen aggregate target shape for realistic development data.

    Missing source demographic cells are folded into the visible ``Unknown``
    category because the synthetic patient contract does not expose null
    demographic values.  The U sex cell is deliberately zero: the pinned CDC
    reference has only F/M series and cannot generate a U reference trajectory.
    """
    return CalibrationSamplingProfile(
        artifact_id=_REALISTIC_PROFILE,
        target_registry_version=TARGET_REGISTRY_VERSION,
        sex_weights=_REALISTIC_SEX_WEIGHTS,
        ethnicity_weights=_REALISTIC_ETHNICITY_WEIGHTS,
        race_weights=_REALISTIC_RACE_WEIGHTS,
        race_multiselect_probability=_REALISTIC_RACE_MULTISELECT_PROBABILITY,
        # The observed source flag is a target-shaped latent module prior for
        # this profile, not a recorded-outcome allocation or clinical claim.
        recorded_healthy_probability=0.0,
        recorded_growth_dx_probability=0.0,
    )


def development_realistic_config(patient_count: int, seed: int) -> CohortConfig:
    """Return the frozen target-shaped healthy/GHD development configuration."""
    return CohortConfig(
        profile=_REALISTIC_PROFILE,
        patient_count=patient_count,
        seed=seed,
        ages_days=_COHORT_AGES_DAYS,
        observation_policy=ObservationPolicy(
            policy_version=_REALISTIC_OBSERVATION_POLICY_VERSION,
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
            recognition_probability=1.0,
            diagnosis_probability=1.0,
            recognition_delay_days=0,
        ),
        module_weights=(
            CohortModuleWeight(DisorderKind.HEALTHY, 1.0 - _REALISTIC_GHD_PRIOR),
            CohortModuleWeight(
                DisorderKind.GROWTH_HORMONE_DEFICIENCY,
                _REALISTIC_GHD_PRIOR,
            ),
        ),
        reference_sex_mapping=_REFERENCE_SEX_MAPPING,
    )


def development_all_disorders_calibration_profile() -> CalibrationSamplingProfile:
    """Return the snapshot-shaped demographics for fictional module coverage."""
    return CalibrationSamplingProfile(
        artifact_id=_ALL_DISORDER_PROFILE,
        target_registry_version=TARGET_REGISTRY_VERSION,
        sex_weights=_REALISTIC_SEX_WEIGHTS,
        ethnicity_weights=_REALISTIC_ETHNICITY_WEIGHTS,
        race_weights=_REALISTIC_RACE_WEIGHTS,
        race_multiselect_probability=_REALISTIC_RACE_MULTISELECT_PROBABILITY,
        recorded_healthy_probability=0.0,
        recorded_growth_dx_probability=0.0,
    )


def development_all_disorders_config(patient_count: int, seed: int) -> CohortConfig:
    """Return the fixed conditional-prior all-disorder coverage configuration."""
    return CohortConfig(
        profile=_ALL_DISORDER_PROFILE,
        patient_count=patient_count,
        seed=seed,
        ages_days=_COHORT_AGES_DAYS,
        observation_policy=ObservationPolicy(
            policy_version=_ALL_DISORDER_OBSERVATION_POLICY_VERSION,
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
            recognition_probability=1.0,
            diagnosis_probability=1.0,
            recognition_delay_days=0,
        ),
        module_weights=_ALL_DISORDER_F_PRIOR,
        reference_sex_mapping=_REFERENCE_SEX_MAPPING,
        module_weights_by_reference_sex=(
            ("F", _ALL_DISORDER_F_PRIOR),
            ("M", _ALL_DISORDER_M_PRIOR),
        ),
        age_regime_config=AgeRegimeConfig(
            puberty_max_age_days=5834,
            puberty_sampling_max_age_days=5114,
        ),
    )


def development_realistic_ancillary_policy() -> GhdAncillaryPolicy:
    """Return the fixed synthetic GHD ancillary-row policy for package export."""
    return GhdAncillaryPolicy(
        policy_id=_REALISTIC_ANCILLARY_POLICY_ID,
        policy_version=_REALISTIC_ANCILLARY_POLICY_VERSION,
        result_delay_days=_REALISTIC_ANCILLARY_RESULT_DELAY_DAYS,
    )


def development_all_disorders_ancillary_policy() -> MultidisorderAncillaryPolicy:
    """Return the fixed all-disorder fictional ancillary sidecar policy."""
    return MultidisorderAncillaryPolicy(
        policy_id=_ALL_DISORDER_ANCILLARY_POLICY_ID,
        policy_version=_ALL_DISORDER_ANCILLARY_POLICY_VERSION,
        result_delay_days=_ALL_DISORDER_ANCILLARY_RESULT_DELAY_DAYS,
    )


def build_development_cohort(
    runtime: DevelopmentRuntime,
    *,
    descriptor: Mapping[str, object],
    patient_count: int,
    seed: int,
) -> NativeCohort:
    """Build the evaluator-held native cohort before its visible rows are exported."""
    return _build_development_native_cohort(
        runtime,
        config=development_cohort_config(patient_count, seed),
        calibration=development_calibration_profile(),
        descriptor=descriptor,
    )


def _build_development_native_cohort(
    runtime: DevelopmentRuntime,
    *,
    config: CohortConfig,
    calibration: CalibrationSamplingProfile,
    descriptor: Mapping[str, object],
    modules: Mapping[DisorderKind, object] | None = None,
) -> NativeCohort:
    """Build and validate a native cohort for an explicit development profile."""
    if not isinstance(runtime, DevelopmentRuntime):
        raise TypeError("runtime must be a DevelopmentRuntime")
    cohort = generate_native_cohort(
        config,
        runtime.reference,
        calibration,
        modules=(
            {
                DisorderKind.HEALTHY: HealthyGrowthModule(),
                DisorderKind.GROWTH_HORMONE_DEFICIENCY: GrowthHormoneDeficiencyModule(),
            }
            if modules is None
            else modules
        ),
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


def build_development_realistic_cohort(
    runtime: DevelopmentRuntime,
    *,
    descriptor: Mapping[str, object],
    patient_count: int,
    seed: int,
) -> NativeCohort:
    """Build the target-shaped healthy-plus-GHD development cohort."""
    return _build_development_native_cohort(
        runtime,
        config=development_realistic_config(patient_count, seed),
        calibration=development_realistic_calibration_profile(),
        descriptor=descriptor,
    )


def build_development_all_disorders_cohort(
    runtime: DevelopmentRuntime,
    *,
    descriptor: Mapping[str, object],
    patient_count: int,
    seed: int,
) -> NativeCohort:
    """Build the deterministic cohort containing every native disorder module."""
    return _build_development_native_cohort(
        runtime,
        config=development_all_disorders_config(patient_count, seed),
        calibration=development_all_disorders_calibration_profile(),
        descriptor=descriptor,
        modules=_all_disorder_modules(),
    )


def _configuration_sha256(
    runtime: DevelopmentRuntime,
    config: CohortConfig,
    calibration: CalibrationSamplingProfile,
) -> str:
    age_regime_parameters = asdict(config.age_regime_config)
    if age_regime_parameters.get("puberty_sampling_max_age_days") is None:
        del age_regime_parameters["puberty_sampling_max_age_days"]
    clinical_module_versions = {
        DisorderKind.HEALTHY.value: HealthyGrowthModule.module_version,
        DisorderKind.GROWTH_HORMONE_DEFICIENCY.value: GrowthHormoneDeficiencyModule.module_version,
    }
    if config.profile == _ALL_DISORDER_PROFILE:
        clinical_module_versions = {
            module_class.kind.value: module_class.module_version
            for module_class in _ALL_DISORDER_MODULE_CLASSES
        }
    configuration = {
        "profile": config.profile,
        "generation_domain_policy": CDC_GENERATION_DOMAIN_POLICY,
        "patient_count": config.patient_count,
        "ages_days": config.ages_days,
        "observation_policy": config.observation_policy.to_mapping(),
        "module_weights": tuple(
            (weight.kind.value, weight.probability) for weight in config.module_weights
        ),
        "reference_sex_mapping": config.reference_sex_mapping,
        "age_regime": {
            "module_version": config.age_regime_config.module_version,
            "parameters": age_regime_parameters,
        },
        "clinical_module_versions": clinical_module_versions,
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
    if config.profile == _REALISTIC_PROFILE:
        configuration["realistic_target_snapshot"] = _REALISTIC_TARGET_SNAPSHOT
        configuration["realistic_growth_diagnosis_code"] = _REALISTIC_GROWTH_DIAGNOSIS_CODE
        policy = development_realistic_ancillary_policy()
        configuration["realistic_ancillary_policy"] = {
            "policy_id": policy.policy_id,
            "policy_version": policy.policy_version,
            "result_delay_days": policy.result_delay_days,
        }
    if config.profile == _ALL_DISORDER_PROFILE:
        policy = development_all_disorders_ancillary_policy()
        configuration["module_weights_by_reference_sex"] = tuple(
            (
                reference_sex,
                tuple((weight.kind.value, weight.probability) for weight in weights),
            )
            for reference_sex, weights in config.module_weights_by_reference_sex
        )
        configuration["all_disorder_target_snapshot"] = _ALL_DISORDER_TARGET_SNAPSHOT
        configuration["all_disorder_eligibility_policy"] = (
            _ALL_DISORDER_ELIGIBILITY_POLICY_VERSION
        )
        configuration["all_disorder_growth_diagnosis_code"] = (
            _REALISTIC_GROWTH_DIAGNOSIS_CODE
        )
        configuration["all_disorder_ancillary_policy"] = {
            "policy_id": policy.policy_id,
            "policy_version": policy.policy_version,
            "result_delay_days": policy.result_delay_days,
        }
    payload = json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _visible_base_rows(
    cohort: NativeCohort,
    *,
    include_realistic_pathway: bool = False,
    include_all_disorder_pathways: bool = False,
) -> dict[str, list[dict[str, object]]]:
    rows = {resource_name: [] for resource_name in BASE_RESOURCE_NAMES}
    ancillary_policy = (
        development_realistic_ancillary_policy()
        if include_realistic_pathway
        else None
    )
    all_disorder_policy = (
        development_all_disorders_ancillary_policy()
        if include_all_disorder_pathways
        else None
    )
    for member in cohort.members:
        bundle = member.bundle
        if bundle is None:
            raise ValueError("observed resource bundle did not pass validation")
        if ancillary_policy is not None:
            projection = project_ghd_ancillary_resources(
                member,
                bundle.shape,
                ancillary_policy,
            )
            bundle = merge_ghd_ancillary_resources(
                bundle, member, projection, ancillary_policy
            )
        if all_disorder_policy is not None:
            projection = project_multidisorder_ancillary_resources(
                member,
                bundle.shape,
                all_disorder_policy,
            )
            bundle = merge_multidisorder_ancillary_resources(
                bundle,
                member,
                projection,
                all_disorder_policy,
            )
        member_rows = {
            resource_name: [row.to_mapping() for row in bundle.rows[resource_name]]
            for resource_name in BASE_RESOURCE_NAMES
        }
        if include_realistic_pathway:
            # The typed in-memory pathway uses ``Synthetic`` as its explicit
            # fictional marker.  The unchanged exact descriptor does not
            # enumerate that marker, so serialize it as the descriptor's
            # missing-value sentinel after the merged bundle has validated.
            for row in member_rows["labs"]:
                if (
                    row.get("result_component_name") in GHD_LAB_COMPONENT_NAMES
                    and row.get("result_flag") == GHD_LAB_RESULT_FLAG
                ):
                    row["result_flag"] = ""
        if include_all_disorder_pathways:
            for row in member_rows["labs"]:
                if row.get("result_flag") == "Synthetic":
                    row["result_flag"] = ""
        if (
            include_realistic_pathway
            and member.trajectory.disorder.kind
            is DisorderKind.GROWTH_HORMONE_DEFICIENCY
        ):
            diagnosis_event = next(
                (
                    event
                    for event in member.frame.events
                    if event.event_kind is RecordedEventKind.DIAGNOSIS
                ),
                None,
            )
            if diagnosis_event is None:
                raise ValueError("realistic growth diagnosis event is missing")
            diagnosis_visit = next(
                (
                    row
                    for row in member_rows["visits"]
                    if row.get("age_in_days") == diagnosis_event.age_days
                ),
                None,
            )
            if diagnosis_visit is None:
                raise ValueError("realistic growth diagnosis visit is missing")
            diagnosis_slot = next(
                (
                    field_name
                    for field_name in diagnosis_visit
                    if field_name.startswith("enc_diag_")
                    and diagnosis_visit[field_name] == ""
                ),
                None,
            )
            if diagnosis_slot is None:
                raise ValueError("realistic growth diagnosis slot is missing")
            diagnosis_visit[diagnosis_slot] = _REALISTIC_GROWTH_DIAGNOSIS_CODE
        if (
            include_all_disorder_pathways
            and member.trajectory.disorder.kind
            is DisorderKind.GROWTH_HORMONE_DEFICIENCY
        ):
            diagnosis_event = next(
                (
                    event
                    for event in member.frame.events
                    if event.event_kind is RecordedEventKind.DIAGNOSIS
                ),
                None,
            )
            if diagnosis_event is None:
                raise ValueError("all-disorder GHD diagnosis event is missing")
            diagnosis_visit = next(
                (
                    row
                    for row in member_rows["visits"]
                    if row.get("age_in_days") == diagnosis_event.age_days
                ),
                None,
            )
            if diagnosis_visit is None:
                raise ValueError("all-disorder GHD diagnosis visit is missing")
            diagnosis_slot = next(
                (
                    field_name
                    for field_name in diagnosis_visit
                    if field_name.startswith("enc_diag_")
                    and diagnosis_visit[field_name] == ""
                ),
                None,
            )
            if diagnosis_slot is None:
                raise ValueError("all-disorder GHD diagnosis slot is missing")
            diagnosis_visit[diagnosis_slot] = _REALISTIC_GROWTH_DIAGNOSIS_CODE
        for resource_name in BASE_RESOURCE_NAMES:
            rows[resource_name].extend(member_rows[resource_name])
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


def generate_development_realistic_cohort(
    runtime: DevelopmentRuntime,
    *,
    descriptor_path: Path,
    output: Path,
    patient_count: int,
    seed: int,
    reference_time: str,
    software_revision: str,
) -> Path:
    """Generate and promote an exact-schema target-shaped cohort package."""
    try:
        _require_output_available(output)
        descriptor = load_descriptor(descriptor_path)
        cohort = build_development_realistic_cohort(
            runtime,
            descriptor=descriptor,
            patient_count=patient_count,
            seed=seed,
        )
        config = development_realistic_config(patient_count, seed)
        calibration = development_realistic_calibration_profile()
        return export_exact_schema_package(
            descriptor,
            _visible_base_rows(cohort, include_realistic_pathway=True),
            output,
            metadata=PackageExportMetadata(
                profile=_REALISTIC_PACKAGE_PROFILE,
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


def generate_development_all_disorders_cohort(
    runtime: DevelopmentRuntime,
    *,
    descriptor_path: Path,
    output: Path,
    patient_count: int,
    seed: int,
    reference_time: str,
    software_revision: str,
) -> Path:
    """Generate the exact-schema package for every native disorder pathway."""
    try:
        _require_output_available(output)
        descriptor = load_descriptor(descriptor_path)
        cohort = build_development_all_disorders_cohort(
            runtime,
            descriptor=descriptor,
            patient_count=patient_count,
            seed=seed,
        )
        config = development_all_disorders_config(patient_count, seed)
        calibration = development_all_disorders_calibration_profile()
        return export_exact_schema_package(
            descriptor,
            _visible_base_rows(cohort, include_all_disorder_pathways=True),
            output,
            metadata=PackageExportMetadata(
                profile=_ALL_DISORDER_PACKAGE_PROFILE,
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
