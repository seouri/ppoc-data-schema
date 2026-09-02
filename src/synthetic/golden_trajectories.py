"""Deterministic, evaluator-only golden growth-trajectory coverage."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from itertools import pairwise

from synthetic.models import (
    AgeRegimeDisorderTrajectory,
    AgeRegimePoint,
    AgeRegimeState,
    AgeRegimeTrajectory,
    ClinicalEvent,
    DisorderKind,
    GrowthRegime,
    LatentDisorderState,
    PatientState,
)
from synthetic.native.age_regime_disorder import AgeRegimeDisorderKernel
from synthetic.native.age_regimes import AgeRegimeTrajectoryKernel
from synthetic.native.clinical_modules import (
    CeliacDiseaseModule,
    ConstitutionalDelayModule,
    FamilialShortStatureModule,
    GrowthDisorderModule,
    GrowthHormoneDeficiencyModule,
    HealthyGrowthModule,
    PediatricHypothyroidismModule,
)
from synthetic.randomness import NamedRandomStreams
from synthetic.references import GrowthReference

GOLDEN_TRAJECTORY_VERSION = "growth-golden-v1"
GOLDEN_CASE_IDS = (
    "golden-healthy-v1",
    "golden-familial-short-stature-v1",
    "golden-constitutional-delay-v1",
    "golden-growth-hormone-deficiency-v1",
    "golden-pediatric-hypothyroidism-v1",
    "golden-celiac-disease-v1",
)
GOLDEN_REASON_CODES = (
    "NONDETERMINISTIC",
    "MISSING_REGIME",
    "MISSING_EVENT",
    "IDENTITY_VIOLATION",
    "HEIGHT_PATTERN",
    "BMI_PATTERN",
    "INVALID_TRAJECTORY",
)

_UNAVAILABLE_MESSAGE = "golden trajectory suite unavailable"
_CASE_ID = re.compile(r"golden-[a-z0-9]+(?:-[a-z0-9]+)*-v[1-9][0-9]*\Z")
_PATIENT_ID = re.compile(r"syn-golden-[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_TOKEN = re.compile(r"[a-z][a-z0-9_]*\Z")
_MAX_AGE_DAYS = 7305
_PUBERTY_ONSET_BOUNDS = (3287, 5114)
_PUBERTY_TEMPO_BOUNDS = (730, 1460)
_PUBERTY_HEIGHT_SPURT_BOUNDS = (0.2, 0.8)
_PUBERTY_BMI_SHIFT_BOUNDS = (-0.2, 0.3)
_AGE_TUPLE = (0, 700, 730, 760, 3000, 4379, 4380, 4740, 5470, 5475, 6575, 7305)
_HEAD_CIRCUMFERENCE_DECAY_DAYS = 730
_ALL_REGIMES = tuple(GrowthRegime)
_DISEASE_EVENTS = (
    "latent_onset",
    "observable_phenotype",
    "recognition_opportunity",
    "workup",
    "recorded_diagnosis",
)
_EVENT_PHASES = {
    "latent_onset": 0,
    "observable_phenotype": 1,
    "recognition_opportunity": 2,
    "workup": 3,
    "recorded_diagnosis": 4,
    "treatment_start": 5,
    "treatment_response": 6,
    "treatment_nonresponse": 6,
}
_PHYSIOLOGY_Z_FIELDS = (
    "birth_length_z",
    "birth_weight_z",
    "head_circumference_z",
    "childhood_height_z",
    "childhood_bmi_z",
    "puberty_height_spurt_z",
    "puberty_bmi_shift_z",
)
_FIXED_PHYSIOLOGY_VALUES = (
    "age-regimes-v1",
    0.1,
    -0.1,
    0.2,
    0.0,
    0.0,
    4380,
    1095,
    0.5,
    0.0,
)
_FIXED_DISORDER_VALUES = {
    GOLDEN_CASE_IDS[0]: (DisorderKind.HEALTHY, None, 0.0, 0, None, 0.0),
    GOLDEN_CASE_IDS[1]: (
        DisorderKind.FAMILIAL_SHORT_STATURE,
        0,
        1.0,
        0,
        None,
        0.0,
    ),
    GOLDEN_CASE_IDS[2]: (
        DisorderKind.CONSTITUTIONAL_DELAY,
        4380,
        1.0,
        360,
        None,
        0.0,
    ),
    GOLDEN_CASE_IDS[3]: (
        DisorderKind.GROWTH_HORMONE_DEFICIENCY,
        3000,
        1.0,
        0,
        3510,
        0.6,
    ),
    GOLDEN_CASE_IDS[4]: (
        DisorderKind.PEDIATRIC_HYPOTHYROIDISM,
        1460,
        1.0,
        0,
        1850,
        0.6,
    ),
    GOLDEN_CASE_IDS[5]: (
        DisorderKind.CELIAC_DISEASE,
        2190,
        1.0,
        0,
        2640,
        0.6,
    ),
}


class GoldenTrajectoryUnavailable(ValueError):
    """Raised with a fixed message when the suite cannot safely be evaluated."""


class GoldenPattern(str, Enum):
    ZERO = "zero"
    CONSTANT_NEGATIVE = "constant_negative"
    DELAYED_RECOVERY = "delayed_recovery"
    PROGRESSION_RESPONSE = "progression_response"
    POSITIVE_AFTER_ONSET = "positive_after_onset"


class GoldenStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


def _copied_tuple(value: tuple[object, ...]) -> tuple[object, ...]:
    return tuple(item for item in value)


def _valid_case_id(value: object) -> bool:
    return type(value) is str and _CASE_ID.fullmatch(value) is not None


def _validate_integer_ages(value: object, *, nonempty: bool = True) -> tuple[int, ...]:
    if type(value) is not tuple or (nonempty and not value):
        raise ValueError("ages must be a tuple")
    if any(type(age) is not int or not 0 <= age <= _MAX_AGE_DAYS for age in value):
        raise ValueError("ages must be in the evaluator domain")
    if any(left >= right for left, right in pairwise(value)):
        raise ValueError("ages must be strictly increasing")
    return tuple(age for age in value)


def _exact_finite_float(value: object) -> bool:
    return type(value) is float and math.isfinite(value)


def _exact_optional_age(value: object) -> bool:
    return value is None or (type(value) is int and 0 <= value <= _MAX_AGE_DAYS)


def _validate_physiology_state(state: object, *, fixed: bool) -> None:
    if type(state) is not AgeRegimeState:
        raise TypeError("physiology_state must be an exact AgeRegimeState")
    if type(state.module_version) is not str or state.module_version != "age-regimes-v1":
        raise ValueError("physiology_state version is unavailable")
    if any(not _exact_finite_float(getattr(state, field)) for field in _PHYSIOLOGY_Z_FIELDS):
        raise ValueError("physiology_state z values must be exact and finite")
    if not (
        _PUBERTY_HEIGHT_SPURT_BOUNDS[0]
        <= state.puberty_height_spurt_z
        <= _PUBERTY_HEIGHT_SPURT_BOUNDS[1]
        and _PUBERTY_BMI_SHIFT_BOUNDS[0]
        <= state.puberty_bmi_shift_z
        <= _PUBERTY_BMI_SHIFT_BOUNDS[1]
    ):
        raise ValueError("physiology_state puberty offsets are unavailable")
    if (
        type(state.puberty_onset_age_days) is not int
        or not _PUBERTY_ONSET_BOUNDS[0] <= state.puberty_onset_age_days <= _PUBERTY_ONSET_BOUNDS[1]
    ):
        raise ValueError("physiology_state puberty onset is unavailable")
    if (
        type(state.puberty_tempo_days) is not int
        or not _PUBERTY_TEMPO_BOUNDS[0] <= state.puberty_tempo_days <= _PUBERTY_TEMPO_BOUNDS[1]
        or state.puberty_onset_age_days + state.puberty_tempo_days > _MAX_AGE_DAYS
    ):
        raise ValueError("physiology_state puberty tempo is unavailable")
    values = (
        state.module_version,
        state.birth_length_z,
        state.birth_weight_z,
        state.head_circumference_z,
        state.childhood_height_z,
        state.childhood_bmi_z,
        state.puberty_onset_age_days,
        state.puberty_tempo_days,
        state.puberty_height_spurt_z,
        state.puberty_bmi_shift_z,
    )
    if fixed and values != _FIXED_PHYSIOLOGY_VALUES:
        raise ValueError("fixed physiology_state does not match the golden contract")


def _validate_disorder_state(state: object, *, case_id: str) -> None:
    if type(state) is not LatentDisorderState:
        raise TypeError("disorder_state must be an exact LatentDisorderState")
    if type(state.kind) is not DisorderKind:
        raise TypeError("disorder_state kind must be an exact DisorderKind")
    if not _exact_optional_age(state.onset_age_days):
        raise ValueError("disorder_state onset is unavailable")
    if not _exact_finite_float(state.severity) or state.severity < 0:
        raise ValueError("disorder_state severity is unavailable")
    if (
        type(state.puberty_delay_days) is not int
        or not 0 <= state.puberty_delay_days <= _MAX_AGE_DAYS
    ):
        raise ValueError("disorder_state puberty delay is unavailable")
    if not _exact_optional_age(state.treatment_start_age_days):
        raise ValueError("disorder_state treatment start is unavailable")
    if not _exact_finite_float(state.treatment_response) or not 0 <= state.treatment_response <= 1:
        raise ValueError("disorder_state treatment response is unavailable")
    expected = _FIXED_DISORDER_VALUES.get(case_id)
    values = (
        state.kind,
        state.onset_age_days,
        state.severity,
        state.puberty_delay_days,
        state.treatment_start_age_days,
        state.treatment_response,
    )
    if expected is not None and values != expected:
        raise ValueError("fixed disorder_state does not match the golden contract")
    if state.kind is DisorderKind.HEALTHY:
        coherent = (
            state.onset_age_days is None
            and state.severity == 0
            and state.puberty_delay_days == 0
            and state.treatment_start_age_days is None
            and state.treatment_response == 0
        )
    elif state.kind is DisorderKind.FAMILIAL_SHORT_STATURE:
        coherent = (
            state.onset_age_days is not None
            and state.severity > 0
            and state.puberty_delay_days == 0
            and state.treatment_start_age_days is None
            and state.treatment_response == 0
        )
    elif state.kind is DisorderKind.CONSTITUTIONAL_DELAY:
        coherent = (
            state.onset_age_days is not None
            and state.severity > 0
            and state.puberty_delay_days > 0
            and state.treatment_start_age_days is None
            and state.treatment_response == 0
        )
    else:
        treatment_start = state.treatment_start_age_days
        coherent = (
            state.onset_age_days is not None
            and state.severity > 0
            and state.puberty_delay_days == 0
            and (
                (treatment_start is None and state.treatment_response == 0)
                or (
                    treatment_start is not None
                    and treatment_start >= state.onset_age_days
                    and 0 <= state.treatment_response <= 1
                )
            )
        )
    if not coherent:
        raise ValueError("disorder_state is incoherent")


@dataclass(frozen=True, repr=False)
class GoldenTrajectoryCase:
    case_id: str
    patient: PatientState
    seed: int
    ages_days: tuple[int, ...]
    physiology_state: AgeRegimeState
    disorder_state: LatentDisorderState
    required_regimes: tuple[GrowthRegime, ...]
    required_event_types: tuple[str, ...]
    height_pattern: GoldenPattern
    bmi_pattern: GoldenPattern
    pattern_probe_ages_days: tuple[int, ...]

    def __init_subclass__(cls, **kwargs: object) -> None:
        del cls, kwargs
        raise TypeError("GoldenTrajectoryCase cannot be subclassed")

    def __post_init__(self) -> None:
        if not _valid_case_id(self.case_id):
            raise ValueError("case_id must be a safe golden token")
        if type(self.patient) is not PatientState:
            raise TypeError("patient must be an exact PatientState")
        if (
            type(self.patient.patient_id) is not str
            or _PATIENT_ID.fullmatch(self.patient.patient_id) is None
            or type(self.patient.recorded_sex) is not str
            or not self.patient.recorded_sex
            or type(self.patient.reference_sex) is not str
            or not self.patient.reference_sex
        ):
            raise ValueError("patient must contain fixed fictional values")
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("seed must be a nonnegative integer")
        _validate_physiology_state(self.physiology_state, fixed=self.case_id in GOLDEN_CASE_IDS)
        _validate_disorder_state(self.disorder_state, case_id=self.case_id)
        ages = _validate_integer_ages(self.ages_days)
        probes = _validate_integer_ages(self.pattern_probe_ages_days)
        if type(self.required_regimes) is not tuple or not self.required_regimes:
            raise ValueError("required_regimes must be a nonempty tuple")
        if any(type(regime) is not GrowthRegime for regime in self.required_regimes):
            raise TypeError("required_regimes must contain exact GrowthRegime values")
        if len(set(self.required_regimes)) != len(self.required_regimes):
            raise ValueError("required_regimes must be unique")
        if type(self.required_event_types) is not tuple:
            raise ValueError("required_event_types must be a tuple")
        if any(
            type(event_type) is not str
            or _TOKEN.fullmatch(event_type) is None
            or event_type not in _EVENT_PHASES
            for event_type in self.required_event_types
        ):
            raise ValueError("required_event_types must contain fixed event tokens")
        if len(set(self.required_event_types)) != len(self.required_event_types):
            raise ValueError("required_event_types must be unique")
        phases = tuple(_EVENT_PHASES[event_type] for event_type in self.required_event_types)
        if any(left >= right for left, right in pairwise(phases)):
            raise ValueError("required_event_types must be causally ordered")
        if type(self.height_pattern) is not GoldenPattern:
            raise TypeError("height_pattern must be an exact GoldenPattern")
        if type(self.bmi_pattern) is not GoldenPattern:
            raise TypeError("bmi_pattern must be an exact GoldenPattern")
        _validate_pattern_size(self.height_pattern, probes)
        _validate_pattern_size(self.bmi_pattern, probes)
        object.__setattr__(self, "ages_days", ages)
        object.__setattr__(self, "required_regimes", _copied_tuple(self.required_regimes))
        object.__setattr__(self, "required_event_types", _copied_tuple(self.required_event_types))
        object.__setattr__(self, "pattern_probe_ages_days", probes)

    def __repr__(self) -> str:
        return "<GoldenTrajectoryCase redacted>"


def _validate_pattern_size(pattern: GoldenPattern, probes: tuple[int, ...]) -> None:
    exact_sizes = {
        GoldenPattern.DELAYED_RECOVERY: 3,
        GoldenPattern.PROGRESSION_RESPONSE: 4,
    }
    expected = exact_sizes.get(pattern)
    if expected is not None and len(probes) != expected:
        raise ValueError("pattern probe count is invalid")
    if pattern is GoldenPattern.CONSTANT_NEGATIVE and len(probes) < 2:
        raise ValueError("pattern probe count is invalid")
    if pattern is GoldenPattern.POSITIVE_AFTER_ONSET and len(probes) < 2:
        raise ValueError("pattern probe count is invalid")


@dataclass(frozen=True, repr=False)
class GoldenCaseResult:
    case_id: str
    status: GoldenStatus
    reason_codes: tuple[str, ...]

    def __init_subclass__(cls, **kwargs: object) -> None:
        del cls, kwargs
        raise TypeError("GoldenCaseResult cannot be subclassed")

    def __post_init__(self) -> None:
        if not _valid_case_id(self.case_id):
            raise ValueError("case_id must be a safe golden token")
        if type(self.status) is not GoldenStatus:
            raise TypeError("status must be an exact GoldenStatus")
        if type(self.reason_codes) is not tuple or not self.reason_codes:
            raise ValueError("reason_codes must be a nonempty tuple")
        if any(type(reason) is not str for reason in self.reason_codes):
            raise TypeError("reason_codes must contain strings")
        if self.status is GoldenStatus.PASS:
            if self.reason_codes != ("OK",):
                raise ValueError("passing results require OK")
        else:
            if any(reason not in GOLDEN_REASON_CODES for reason in self.reason_codes):
                raise ValueError("failure reason is not registered")
            expected = tuple(
                reason for reason in GOLDEN_REASON_CODES if reason in self.reason_codes
            )
            if self.reason_codes != expected:
                raise ValueError("failure reasons must use fixed order")
        object.__setattr__(self, "reason_codes", _copied_tuple(self.reason_codes))

    def to_mapping(self) -> dict[str, object]:
        return _result_mapping(self)

    def __repr__(self) -> str:
        return "<GoldenCaseResult redacted>"


@dataclass(frozen=True, repr=False)
class GoldenTrajectoryReport:
    report_version: str
    status: GoldenStatus
    case_results: tuple[GoldenCaseResult, ...]

    def __init_subclass__(cls, **kwargs: object) -> None:
        del cls, kwargs
        raise TypeError("GoldenTrajectoryReport cannot be subclassed")

    def __post_init__(self) -> None:
        if type(self.report_version) is not str or self.report_version != GOLDEN_TRAJECTORY_VERSION:
            raise ValueError("report_version is unavailable")
        if type(self.status) is not GoldenStatus:
            raise TypeError("status must be an exact GoldenStatus")
        if type(self.case_results) is not tuple or not self.case_results:
            raise ValueError("case_results must be a nonempty tuple")
        if any(type(result) is not GoldenCaseResult for result in self.case_results):
            raise TypeError("case_results must contain exact GoldenCaseResult values")
        identifiers = tuple(result.case_id for result in self.case_results)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("case_results must have unique case IDs")
        expected_status = (
            GoldenStatus.PASS
            if all(result.status is GoldenStatus.PASS for result in self.case_results)
            else GoldenStatus.FAIL
        )
        if self.status is not expected_status:
            raise ValueError("report status does not match case results")
        object.__setattr__(self, "case_results", _copied_tuple(self.case_results))

    def to_mapping(self) -> dict[str, object]:
        return _report_mapping(self)

    def to_json_bytes(self) -> bytes:
        return (
            json.dumps(
                _report_mapping(self),
                sort_keys=True,
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("ascii")
            + b"\n"
        )

    def __repr__(self) -> str:
        return "<GoldenTrajectoryReport aggregate>"


def _result_mapping(result: GoldenCaseResult) -> dict[str, object]:
    return {
        "case_id": result.case_id,
        "status": result.status.value,
        "reason_codes": list(result.reason_codes),
    }


def _report_mapping(report: GoldenTrajectoryReport) -> dict[str, object]:
    return {
        "report_version": report.report_version,
        "status": report.status.value,
        "case_results": [_result_mapping(result) for result in report.case_results],
    }


def _physiology_state() -> AgeRegimeState:
    return AgeRegimeState(
        module_version="age-regimes-v1",
        birth_length_z=0.1,
        birth_weight_z=-0.1,
        head_circumference_z=0.2,
        childhood_height_z=0.0,
        childhood_bmi_z=0.0,
        puberty_onset_age_days=4380,
        puberty_tempo_days=1095,
        puberty_height_spurt_z=0.5,
        puberty_bmi_shift_z=0.0,
    )


def _case(
    case_id: str,
    kind: DisorderKind,
    disorder_state: LatentDisorderState,
    events: tuple[str, ...],
    height_pattern: GoldenPattern,
    bmi_pattern: GoldenPattern,
    probes: tuple[int, ...],
    seed: int,
) -> GoldenTrajectoryCase:
    if disorder_state.kind is not kind:
        raise ValueError("golden case kind mismatch")
    return GoldenTrajectoryCase(
        case_id=case_id,
        patient=PatientState(f"syn-{case_id}", "F", "F"),
        seed=seed,
        ages_days=_AGE_TUPLE,
        physiology_state=_physiology_state(),
        disorder_state=disorder_state,
        required_regimes=_ALL_REGIMES,
        required_event_types=events,
        height_pattern=height_pattern,
        bmi_pattern=bmi_pattern,
        pattern_probe_ages_days=probes,
    )


DEFAULT_GOLDEN_CASES = (
    _case(
        GOLDEN_CASE_IDS[0],
        DisorderKind.HEALTHY,
        LatentDisorderState(DisorderKind.HEALTHY, None, 0.0),
        (),
        GoldenPattern.ZERO,
        GoldenPattern.ZERO,
        (0, 730, 4380, 7305),
        1001,
    ),
    _case(
        GOLDEN_CASE_IDS[1],
        DisorderKind.FAMILIAL_SHORT_STATURE,
        LatentDisorderState(DisorderKind.FAMILIAL_SHORT_STATURE, 0, 1.0),
        _DISEASE_EVENTS,
        GoldenPattern.CONSTANT_NEGATIVE,
        GoldenPattern.ZERO,
        (0, 730, 4380, 7305),
        1002,
    ),
    _case(
        GOLDEN_CASE_IDS[2],
        DisorderKind.CONSTITUTIONAL_DELAY,
        LatentDisorderState(
            DisorderKind.CONSTITUTIONAL_DELAY,
            4380,
            1.0,
            puberty_delay_days=360,
        ),
        _DISEASE_EVENTS,
        GoldenPattern.DELAYED_RECOVERY,
        GoldenPattern.ZERO,
        (4380, 4740, 5470),
        1003,
    ),
    _case(
        GOLDEN_CASE_IDS[3],
        DisorderKind.GROWTH_HORMONE_DEFICIENCY,
        LatentDisorderState(
            DisorderKind.GROWTH_HORMONE_DEFICIENCY,
            3000,
            1.0,
            treatment_start_age_days=3510,
            treatment_response=0.6,
        ),
        _DISEASE_EVENTS + ("treatment_start", "treatment_response"),
        GoldenPattern.PROGRESSION_RESPONSE,
        GoldenPattern.POSITIVE_AFTER_ONSET,
        (3000, 3510, 3875, 5000),
        1004,
    ),
    _case(
        GOLDEN_CASE_IDS[4],
        DisorderKind.PEDIATRIC_HYPOTHYROIDISM,
        LatentDisorderState(
            DisorderKind.PEDIATRIC_HYPOTHYROIDISM,
            1460,
            1.0,
            treatment_start_age_days=1850,
            treatment_response=0.6,
        ),
        _DISEASE_EVENTS + ("treatment_start", "treatment_response"),
        GoldenPattern.PROGRESSION_RESPONSE,
        GoldenPattern.POSITIVE_AFTER_ONSET,
        (1460, 1850, 2215, 3000),
        1005,
    ),
    _case(
        GOLDEN_CASE_IDS[5],
        DisorderKind.CELIAC_DISEASE,
        LatentDisorderState(
            DisorderKind.CELIAC_DISEASE,
            2190,
            1.0,
            treatment_start_age_days=2640,
            treatment_response=0.6,
        ),
        _DISEASE_EVENTS + ("treatment_start", "treatment_response"),
        GoldenPattern.PROGRESSION_RESPONSE,
        GoldenPattern.PROGRESSION_RESPONSE,
        (2190, 2640, 3005, 3500),
        1006,
    ),
)


def _default_modules() -> dict[DisorderKind, GrowthDisorderModule]:
    return {
        DisorderKind.HEALTHY: HealthyGrowthModule(),
        DisorderKind.FAMILIAL_SHORT_STATURE: FamilialShortStatureModule(),
        DisorderKind.CONSTITUTIONAL_DELAY: ConstitutionalDelayModule(),
        DisorderKind.GROWTH_HORMONE_DEFICIENCY: GrowthHormoneDeficiencyModule(),
        DisorderKind.PEDIATRIC_HYPOTHYROIDISM: PediatricHypothyroidismModule(),
        DisorderKind.CELIAC_DISEASE: CeliacDiseaseModule(),
    }


def _validated_modules(
    modules: Mapping[DisorderKind, GrowthDisorderModule] | None,
) -> dict[DisorderKind, GrowthDisorderModule]:
    if modules is None:
        copied = _default_modules()
    else:
        if not isinstance(modules, Mapping):
            raise TypeError("modules must be a mapping")
        copied = dict(modules)
    if set(copied) != set(DisorderKind) or any(type(kind) is not DisorderKind for kind in copied):
        raise ValueError("modules must contain exactly the disorder kinds")
    for kind, module in copied.items():
        if type(getattr(module, "kind", None)) is not DisorderKind or module.kind is not kind:
            raise ValueError("module kind does not match its key")
        if type(getattr(module, "module_version", None)) is not str:
            raise TypeError("module version is unavailable")
        for method in ("sample_state", "height_z_delta", "bmi_z_delta", "events"):
            if not callable(getattr(module, method, None)):
                raise TypeError("module interface is unavailable")
    return copied


def _validated_cases(cases: tuple[GoldenTrajectoryCase, ...]) -> tuple[GoldenTrajectoryCase, ...]:
    if type(cases) is not tuple or not cases:
        raise ValueError("cases must be a nonempty tuple")
    if any(type(case) is not GoldenTrajectoryCase for case in cases):
        raise TypeError("cases must contain exact GoldenTrajectoryCase values")
    copied = tuple(
        GoldenTrajectoryCase(
            case.case_id,
            case.patient,
            case.seed,
            case.ages_days,
            case.physiology_state,
            case.disorder_state,
            case.required_regimes,
            case.required_event_types,
            case.height_pattern,
            case.bmi_pattern,
            case.pattern_probe_ages_days,
        )
        for case in cases
    )
    identifiers = tuple(case.case_id for case in copied)
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("case IDs must be unique")
    return copied


def run_golden_trajectory_suite(
    reference: GrowthReference,
    *,
    modules: Mapping[DisorderKind, GrowthDisorderModule] | None = None,
    cases: tuple[GoldenTrajectoryCase, ...] = DEFAULT_GOLDEN_CASES,
) -> GoldenTrajectoryReport:
    """Evaluate fixed fictional scenarios and return an aggregate-only report."""

    failed = False
    report: GoldenTrajectoryReport | None = None
    try:
        report = _run_suite(reference, modules=modules, cases=cases)
    except Exception:  # noqa: BLE001 - public boundary redacts evaluator failures
        failed = True
    if failed or report is None:
        raise GoldenTrajectoryUnavailable(_UNAVAILABLE_MESSAGE)
    return report


def _run_suite(
    reference: GrowthReference,
    *,
    modules: Mapping[DisorderKind, GrowthDisorderModule] | None,
    cases: tuple[GoldenTrajectoryCase, ...],
) -> GoldenTrajectoryReport:
    if not callable(getattr(reference, "value", None)):
        raise TypeError("reference interface is unavailable")
    copied_modules = _validated_modules(modules)
    copied_cases = _validated_cases(cases)
    results = tuple(
        _run_case(reference, copied_modules[case.disorder_state.kind], case)
        for case in copied_cases
    )
    status = (
        GoldenStatus.PASS
        if all(result.status is GoldenStatus.PASS for result in results)
        else GoldenStatus.FAIL
    )
    return GoldenTrajectoryReport(GOLDEN_TRAJECTORY_VERSION, status, results)


def _run_case(
    reference: GrowthReference,
    module: GrowthDisorderModule,
    case: GoldenTrajectoryCase,
) -> GoldenCaseResult:
    kernel = AgeRegimeDisorderKernel(AgeRegimeTrajectoryKernel(reference), module)
    left = kernel.generate(
        case.patient,
        case.ages_days,
        NamedRandomStreams(case.seed, 0),
        physiology_state=case.physiology_state,
        disorder_state=case.disorder_state,
    )
    right = kernel.generate(
        case.patient,
        case.ages_days,
        NamedRandomStreams(case.seed, 0),
        physiology_state=case.physiology_state,
        disorder_state=case.disorder_state,
    )
    failures: set[str] = set()
    if left != right:
        failures.add("NONDETERMINISTIC")
    if not _valid_trajectory(left, case):
        failures.add("INVALID_TRAJECTORY")
    else:
        regimes = {point.regime for point in left.physiology.points}
        if any(regime not in regimes for regime in case.required_regimes):
            failures.add("MISSING_REGIME")
        event_types = tuple(event.event_type for event in left.events)
        if not _ordered_subset(case.required_event_types, event_types):
            failures.add("MISSING_EVENT")
        if not _valid_identities(left):
            failures.add("IDENTITY_VIOLATION")
    if not _matches_pattern(module, case, metric="height"):
        failures.add("HEIGHT_PATTERN")
    if not _matches_pattern(module, case, metric="bmi"):
        failures.add("BMI_PATTERN")
    if not failures:
        return GoldenCaseResult(case.case_id, GoldenStatus.PASS, ("OK",))
    ordered = tuple(reason for reason in GOLDEN_REASON_CODES if reason in failures)
    return GoldenCaseResult(case.case_id, GoldenStatus.FAIL, ordered)


def _valid_trajectory(
    trajectory: object,
    case: GoldenTrajectoryCase,
) -> bool:
    try:
        if (
            type(trajectory) is not AgeRegimeDisorderTrajectory
            or type(trajectory.physiology) is not AgeRegimeTrajectory
            or type(trajectory.physiology.state) is not AgeRegimeState
            or type(trajectory.physiology.points) is not tuple
            or not trajectory.physiology.points
            or type(trajectory.disorder) is not LatentDisorderState
            or trajectory.disorder != case.disorder_state
            or type(trajectory.events) is not tuple
        ):
            return False
        points = trajectory.physiology.points
        if any(not _valid_point_shape(point, case.patient.patient_id) for point in points):
            return False
        if tuple(point.age_days for point in points) != case.ages_days:
            return False
        if any(left.age_days >= right.age_days for left, right in pairwise(points)):
            return False
        if any(
            not _valid_event_shape(event, case.patient.patient_id) for event in trajectory.events
        ):
            return False
        phases = tuple(_EVENT_PHASES.get(event.event_type, -1) for event in trajectory.events)
        if any(phase < 0 for phase in phases):
            return False
        return not any(
            (left.age_days, phases[index]) > (right.age_days, phases[index + 1])
            for index, (left, right) in enumerate(zip(trajectory.events, trajectory.events[1:]))
        )
    except (AttributeError, ArithmeticError, TypeError, ValueError):
        return False


def _valid_point_shape(point: object, patient_id: str) -> bool:
    if type(point) is not AgeRegimePoint:
        return False
    if (
        type(point.patient_id) is not str
        or point.patient_id != patient_id
        or type(point.age_days) is not int
        or not 0 <= point.age_days <= _MAX_AGE_DAYS
        or type(point.regime) is not GrowthRegime
        or not _exact_finite_float(point.weight_kg)
    ):
        return False
    optional_floats = (
        point.length_cm,
        point.height_cm,
        point.bmi,
        point.head_circumference_cm,
        point.length_z,
        point.height_z,
        point.weight_z,
        point.bmi_z,
        point.height_velocity_cm_per_year,
        point.weight_velocity_kg_per_year,
    )
    return all(value is None or _exact_finite_float(value) for value in optional_floats)


def _valid_event_shape(event: object, patient_id: str) -> bool:
    return (
        type(event) is ClinicalEvent
        and type(event.patient_id) is str
        and event.patient_id == patient_id
        and type(event.age_days) is int
        and event.age_days >= 0
        and type(event.event_type) is str
        and _TOKEN.fullmatch(event.event_type) is not None
        and (event.code is None or type(event.code) is str)
        and type(event.hidden) is bool
    )


def _ordered_subset(required: tuple[str, ...], observed: tuple[str, ...]) -> bool:
    position = 0
    for event_type in observed:
        if position < len(required) and event_type == required[position]:
            position += 1
    return position == len(required)


def _finite_positive(value: object) -> bool:
    return _exact_finite_float(value) and value > 0


def _finite(value: object) -> bool:
    return _exact_finite_float(value)


def _equal(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-12)


def _valid_identities(trajectory: AgeRegimeDisorderTrajectory) -> bool:
    try:
        points = trajectory.physiology.points
        previous_age: int | None = None
        previous_size: float | None = None
        previous_weight: float | None = None
        for point in points:
            if not _finite_positive(point.weight_kg):
                return False
            head_is_valid = (
                _finite_positive(point.head_circumference_cm)
                if point.age_days < _HEAD_CIRCUMFERENCE_DECAY_DAYS
                else point.head_circumference_cm is None
                or _finite_positive(point.head_circumference_cm)
            )
            if point.regime is GrowthRegime.INFANCY:
                if not (
                    _finite_positive(point.length_cm)
                    and point.height_cm is None
                    and point.bmi is None
                    and head_is_valid
                    and _finite(point.length_z)
                    and point.height_z is None
                    and _finite(point.weight_z)
                    and point.bmi_z is None
                ):
                    return False
                size = point.length_cm - 0.7
            elif point.regime is GrowthRegime.TRANSITION:
                if not (
                    _finite_positive(point.length_cm)
                    and _finite_positive(point.height_cm)
                    and _finite_positive(point.bmi)
                    and head_is_valid
                    and _finite(point.length_z)
                    and _finite(point.height_z)
                    and _finite(point.weight_z)
                    and point.bmi_z is None
                ):
                    return False
                if not _equal(point.height_cm, point.length_cm - 0.7):
                    return False
                size = point.height_cm
            else:
                if not (
                    point.length_cm is None
                    and _finite_positive(point.height_cm)
                    and _finite_positive(point.bmi)
                    and point.head_circumference_cm is None
                    and point.length_z is None
                    and _finite(point.height_z)
                    and point.weight_z is None
                    and _finite(point.bmi_z)
                ):
                    return False
                size = point.height_cm
            if not _finite_positive(size):
                return False
            if point.height_cm is not None:
                expected_weight = point.bmi * (point.height_cm / 100.0) ** 2
                if not _finite_positive(expected_weight) or not _equal(
                    point.weight_kg, expected_weight
                ):
                    return False
            if previous_age is None:
                if (
                    point.height_velocity_cm_per_year is not None
                    or point.weight_velocity_kg_per_year is not None
                ):
                    return False
            else:
                expected_height_velocity = (
                    (size - previous_size) * 365.25 / (point.age_days - previous_age)
                )
                expected_weight_velocity = (
                    (point.weight_kg - previous_weight) * 365.25 / (point.age_days - previous_age)
                )
                if (
                    not _finite(expected_height_velocity)
                    or not _finite(expected_weight_velocity)
                    or not _finite(point.height_velocity_cm_per_year)
                    or not _finite(point.weight_velocity_kg_per_year)
                    or not _equal(point.height_velocity_cm_per_year, expected_height_velocity)
                    or not _equal(point.weight_velocity_kg_per_year, expected_weight_velocity)
                ):
                    return False
            previous_age = point.age_days
            previous_size = size
            previous_weight = point.weight_kg
        return True
    except (AttributeError, ArithmeticError, TypeError, ValueError):
        return False


def _zero(value: float) -> bool:
    return math.isclose(value, 0.0, rel_tol=0.0, abs_tol=1e-12)


def _matches_pattern(
    module: GrowthDisorderModule,
    case: GoldenTrajectoryCase,
    *,
    metric: str,
) -> bool:
    method = module.height_z_delta if metric == "height" else module.bmi_z_delta
    pattern = case.height_pattern if metric == "height" else case.bmi_pattern
    values = tuple(method(case.disorder_state, age) for age in case.pattern_probe_ages_days)
    if any(not _finite(value) for value in values):
        return False
    if pattern is GoldenPattern.ZERO:
        return all(_zero(value) for value in values)
    if pattern is GoldenPattern.CONSTANT_NEGATIVE:
        return all(value < 0 for value in values) and all(
            _equal(values[0], value) for value in values[1:]
        )
    if pattern is GoldenPattern.DELAYED_RECOVERY:
        return _zero(values[0]) and values[1] < 0 and _zero(values[2])
    if pattern is GoldenPattern.PROGRESSION_RESPONSE:
        return _zero(values[0]) and values[1] < 0 and values[1] < values[2] <= values[3]
    return _zero(values[0]) and all(value > 0 for value in values[1:])
