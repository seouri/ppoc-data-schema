"""Immutable, aggregate-only contracts for derivation parity evaluation."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from statistics import fmean, pstdev
from types import MappingProxyType

from synthetic.schema_contract import EXPECTED_SCHEMA_FINGERPRINT, schema_fingerprint

DERIVATION_PARITY_VERSION = "derivation-parity-v1"
DERIVATION_PARITY_CHECK_NAMES = (
    "schema_contract", "base_shape", "candidate_shape", "reference_shape",
    "patient_key_alignment", "visit_key_alignment", "patient_identity_projection",
    "visit_identity_projection", "deterministic_age_conversion",
    "deterministic_unit_conversion", "deterministic_bmi",
    "deterministic_patient_summaries", "clinical_flag_relationships",
    "reference_field_parity", "support",
)
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_TOLERANCE_CAP = 1_000_000.0
_REASONS = MappingProxyType({
    "PASS": frozenset({"OK", "WITHIN_TOLERANCE"}),
    "FAIL": frozenset({"OUTSIDE_TOLERANCE", "STRUCTURAL_INVALID"}),
    "UNEVALUABLE": frozenset({"INSUFFICIENT_SUPPORT", "MISSING_EVIDENCE"}),
})
DERIVATION_PARITY_REASON_CODES = frozenset(code for codes in _REASONS.values() for code in codes)


class DerivationParityUnavailable(RuntimeError):
    """Raised when parity cannot be evaluated."""

    _MESSAGE = "derivation parity evaluation is unavailable"

    def __init__(self, *_: object) -> None:
        super().__init__(self._MESSAGE)


class DerivationParityStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNEVALUABLE = "UNEVALUABLE"


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or _SAFE_TOKEN.fullmatch(value) is None:
        raise ValueError(f"{field} must be a bounded aggregate-safe token")
    lowered = value.lower()
    if any(word in lowered for word in ("patient", "visit", "row", "path", "source", "truth", "/", "\\")):
        raise ValueError(f"{field} contains unsafe material")
    return value


def _finite(value: object, field: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or (nonnegative and result < 0) or result >= _TOLERANCE_CAP:
        raise ValueError(f"{field} is outside the permitted range")
    return result


def _count(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return value


@dataclass(frozen=True)
class DerivationImplementation:
    implementation_id: str
    fingerprint: str
    test_only: bool

    def __post_init__(self) -> None:
        _token(self.implementation_id, "implementation_id")
        if not isinstance(self.fingerprint, str) or _SHA256.fullmatch(self.fingerprint) is None:
            raise ValueError("fingerprint must be lowercase SHA-256 hex")
        if not isinstance(self.test_only, bool):
            raise TypeError("test_only must be a boolean")

    def to_mapping(self) -> dict[str, object]:
        return {"implementation_id": self.implementation_id, "fingerprint": self.fingerprint, "test_only": self.test_only}

    def __repr__(self) -> str:
        return "DerivationImplementation(<aggregate-safe>)"


@dataclass(frozen=True)
class DerivationParityPolicy:
    policy_id: str
    policy_version: str
    minimum_patient_rows: int
    minimum_visit_rows: int
    deterministic_tolerance: float
    reference_tolerance: float

    def __post_init__(self) -> None:
        _token(self.policy_id, "policy_id")
        _token(self.policy_version, "policy_version")
        if not isinstance(self.minimum_patient_rows, int) or isinstance(self.minimum_patient_rows, bool) or self.minimum_patient_rows < 1:
            raise ValueError("minimum_patient_rows must be at least one")
        if not isinstance(self.minimum_visit_rows, int) or isinstance(self.minimum_visit_rows, bool) or self.minimum_visit_rows < 1:
            raise ValueError("minimum_visit_rows must be at least one")
        object.__setattr__(self, "deterministic_tolerance", _finite(self.deterministic_tolerance, "deterministic_tolerance", nonnegative=True))
        object.__setattr__(self, "reference_tolerance", _finite(self.reference_tolerance, "reference_tolerance", nonnegative=True))

    def to_mapping(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "minimum_patient_rows": self.minimum_patient_rows,
            "minimum_visit_rows": self.minimum_visit_rows,
            "deterministic_tolerance": self.deterministic_tolerance,
            "reference_tolerance": self.reference_tolerance,
        }

    def __repr__(self) -> str:
        return "DerivationParityPolicy(<aggregate-safe>)"


@dataclass(frozen=True, init=False)
class DerivationParityCheck:
    name: str
    status: DerivationParityStatus
    reason_code: str
    compared_count: int | None
    mismatch_count: int | None
    maximum_absolute_difference: float | None

    def __init__(self, name: str, status: DerivationParityStatus, reason_code: str,
                 compared_count: int | None, mismatch_count: int | None,
                 maximum_absolute_difference: float | None, **kwargs: object) -> None:
        if kwargs:
            raise TypeError("unknown check fields")
        if name not in DERIVATION_PARITY_CHECK_NAMES:
            raise ValueError("unknown check name")
        if not isinstance(status, DerivationParityStatus):
            raise TypeError("status must be a DerivationParityStatus")
        if reason_code not in _REASONS[status.value]:
            raise ValueError("reason_code is incompatible with status")
        if status is DerivationParityStatus.UNEVALUABLE:
            compared_count = mismatch_count = None
            maximum_absolute_difference = None
        else:
            if compared_count is None or mismatch_count is None:
                raise ValueError("evaluable checks require counts")
            _count(compared_count, "compared_count")
            _count(mismatch_count, "mismatch_count")
            if mismatch_count > compared_count:
                raise ValueError("mismatch_count exceeds compared_count")
            if maximum_absolute_difference is None:
                raise ValueError("evaluable checks require maximum difference")
            maximum_absolute_difference = _finite(maximum_absolute_difference, "maximum_absolute_difference", nonnegative=True)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "reason_code", reason_code)
        object.__setattr__(self, "compared_count", compared_count)
        object.__setattr__(self, "mismatch_count", mismatch_count)
        object.__setattr__(self, "maximum_absolute_difference", maximum_absolute_difference)

    def to_mapping(self) -> dict[str, object]:
        return {"name": self.name, "status": self.status.value, "reason_code": self.reason_code,
                "compared_count": self.compared_count, "mismatch_count": self.mismatch_count,
                "maximum_absolute_difference": self.maximum_absolute_difference}

    def __repr__(self) -> str:
        return f"DerivationParityCheck(name={self.name!r}, status={self.status.value!r})"


@dataclass(frozen=True, init=False)
class DerivationParityReport:
    contract: str
    schema_fingerprint: str
    policy: DerivationParityPolicy
    candidate: DerivationImplementation
    reference: DerivationImplementation
    patient_row_count: int
    visit_row_count: int
    status: DerivationParityStatus
    status_counts: Mapping[str, int]
    checks: tuple[DerivationParityCheck, ...]

    def __init__(self, contract: object = None, schema_fingerprint: object = None,
                 policy: object = None, candidate: object = None,
                 reference: object = None, patient_row_count: object = None,
                 visit_row_count: object = None, status: object = None,
                 status_counts: object = None, checks: object = None,
                 **extra: object) -> None:
        values = {"contract": contract, "schema_fingerprint": schema_fingerprint,
                  "policy": policy, "candidate": candidate, "reference": reference,
                  "patient_row_count": patient_row_count, "visit_row_count": visit_row_count,
                  "status": status, "status_counts": status_counts, "checks": checks, **extra}
        expected = {"contract", "schema_fingerprint", "policy", "candidate", "reference", "patient_row_count", "visit_row_count", "status", "status_counts", "checks"}
        if set(values) != expected:
            raise ValueError("report keys are fixed")
        if values["contract"] != DERIVATION_PARITY_VERSION:
            raise ValueError("contract is fixed")
        if not isinstance(values["schema_fingerprint"], str) or _SHA256.fullmatch(values["schema_fingerprint"]) is None:
            raise ValueError("schema_fingerprint must be lowercase SHA-256 hex")
        if not isinstance(values["policy"], DerivationParityPolicy) or not isinstance(values["candidate"], DerivationImplementation) or not isinstance(values["reference"], DerivationImplementation):
            raise TypeError("invalid report identities")
        patients, visits = values["patient_row_count"], values["visit_row_count"]
        _count(patients, "patient_row_count")
        _count(visits, "visit_row_count")
        status = values["status"]
        if not isinstance(status, DerivationParityStatus):
            raise TypeError("status must be a DerivationParityStatus")
        checks = tuple(values["checks"]) if isinstance(values["checks"], Iterable) and not isinstance(values["checks"], (str, bytes, Mapping)) else ()
        if not all(isinstance(item, DerivationParityCheck) for item in checks):
            raise TypeError("checks must contain DerivationParityCheck values")
        if len(checks) != len(DERIVATION_PARITY_CHECK_NAMES) or tuple(item.name for item in checks) != DERIVATION_PARITY_CHECK_NAMES:
            raise ValueError("checks must use the fixed ordered check names")
        raw_counts = values["status_counts"]
        if not isinstance(raw_counts, Mapping) or set(raw_counts) != {"PASS", "FAIL", "UNEVALUABLE"}:
            raise ValueError("status_counts keys are fixed")
        counts = {key: _count(raw_counts[key], f"status_counts.{key}") for key in raw_counts}
        expected_counts = {key: sum(item.status.value == key for item in checks) for key in counts}
        if counts != expected_counts or status.value != max((item.status for item in checks), key=lambda item: {DerivationParityStatus.PASS: 0, DerivationParityStatus.UNEVALUABLE: 1, DerivationParityStatus.FAIL: 2}[item]).value:
            raise ValueError("status_counts or status does not match checks")
        for key, value in values.items():
            object.__setattr__(self, key, value)
        object.__setattr__(self, "checks", checks)
        object.__setattr__(self, "status_counts", MappingProxyType(counts))

    def to_mapping(self) -> dict[str, object]:
        return {"contract": self.contract, "schema_fingerprint": self.schema_fingerprint,
                "policy": self.policy.to_mapping(), "candidate": self.candidate.to_mapping(),
                "reference": self.reference.to_mapping(), "patient_row_count": self.patient_row_count,
                "visit_row_count": self.visit_row_count, "status": self.status.value,
                "status_counts": dict(self.status_counts), "checks": [item.to_mapping() for item in self.checks]}

    def to_json_bytes(self) -> bytes:
        return json.dumps(self.to_mapping(), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii") + b"\n"

    def __repr__(self) -> str:
        return f"DerivationParityReport(status={self.status.value!r}, checks={len(self.checks)})"


def validate_derivation_parity(
    base_rows: Mapping[str, Iterable[Mapping[str, object]]],
    candidate_rows: Mapping[str, Iterable[Mapping[str, object]]],
    reference_rows: Mapping[str, Iterable[Mapping[str, object]]],
    descriptor: Mapping[str, object], *, candidate: DerivationImplementation,
    reference: DerivationImplementation, policy: DerivationParityPolicy,
) -> DerivationParityReport:
    try:
        return _evaluate(base_rows, candidate_rows, reference_rows, descriptor, candidate, reference, policy)
    except DerivationParityUnavailable:
        raise
    except (ArithmeticError, KeyError, TypeError, ValueError):
        raise DerivationParityUnavailable() from None


_BASE_RESOURCES = ("patients", "visits", "labs", "medications", "problem_list", "referrals")
_AUGMENTED_RESOURCES = ("patients_augmented", "visits_augmented")
_RESOURCE_ORDER = (
    "patients", "patients_augmented", "visits", "visits_augmented", "labs", "medications",
    "problem_list", "referrals",
)
_NUMERIC_TYPES = frozenset({"integer", "number"})
_Z_METRICS = (
    "weight_z_score", "height_z_score", "bmi_z_score", "head_circ_z_score",
    "weight_for_length_z_score", "weight_for_stature_z_score",
)
_ADVERSE_PATIENT_FLAGS = (
    "chronic_dx_flag", "growth_dx_flag", "ever_stunting_flag", "ever_wasting_flag",
    "ever_underweight_flag", "ever_obesity_flag",
)
_INFORMATIVE_ETHNICITY = frozenset({"Not Hispanic or Latino", "Hispanic or Latino"})
_NONRESPONSE_RACE = frozenset({"Choose not to answer", "Patient does not know", "Unable to collect", "Unknown"})


@dataclass(frozen=True)
class _Resource:
    fields: tuple[str, ...]
    primary_key: str | None
    field_specs: Mapping[str, Mapping[str, object]]


def _status(failed: bool, unevaluable: bool) -> DerivationParityStatus:
    if failed:
        return DerivationParityStatus.FAIL
    if unevaluable:
        return DerivationParityStatus.UNEVALUABLE
    return DerivationParityStatus.PASS


def _check(name: str, failed: bool = False, unevaluable: bool = False, compared: int = 0,
           mismatches: int = 0, difference: float = 0.0) -> DerivationParityCheck:
    status = _status(failed, unevaluable)
    if status is DerivationParityStatus.UNEVALUABLE:
        return DerivationParityCheck(name, status, "MISSING_EVIDENCE", None, None, None)
    return DerivationParityCheck(
        name, status, "STRUCTURAL_INVALID" if failed and mismatches == 0 else
        "OUTSIDE_TOLERANCE" if failed else "OK", compared, mismatches, difference,
    )


def _descriptor_resources(descriptor: Mapping[str, object]) -> tuple[dict[str, _Resource], bool]:
    if not isinstance(descriptor, Mapping) or descriptor.get("profile") != "tabular-data-package":
        return {}, False
    resources = descriptor.get("resources")
    if not isinstance(resources, list) or not all(isinstance(item, Mapping) for item in resources):
        return {}, False
    names = tuple(item.get("name") for item in resources)
    if names != _RESOURCE_ORDER or schema_fingerprint(dict(descriptor)) != EXPECTED_SCHEMA_FINGERPRINT:
        return {}, False
    result: dict[str, _Resource] = {}
    for item in resources:
        schema = item.get("schema")
        fields = schema.get("fields") if isinstance(schema, Mapping) else None
        if not isinstance(fields, list) or not all(isinstance(field, Mapping) for field in fields):
            return {}, False
        names = tuple(field.get("name") for field in fields)
        if any(not isinstance(name, str) or not name for name in names) or len(names) != len(set(names)):
            return {}, False
        primary_key = schema.get("primaryKey")
        if primary_key is not None and (not isinstance(primary_key, str) or primary_key not in names):
            return {}, False
        result[item["name"]] = _Resource(names, primary_key, MappingProxyType({field["name"]: field for field in fields}))
    return result, set(result) == set(_RESOURCE_ORDER)


def _materialize(rows: Mapping[str, Iterable[Mapping[str, object]]], expected: tuple[str, ...]) -> dict[str, tuple[Mapping[str, object], ...]]:
    if not isinstance(rows, Mapping) or set(rows) != set(expected):
        raise TypeError("invalid aggregate input")
    result: dict[str, tuple[Mapping[str, object], ...]] = {}
    for name in expected:
        value = rows[name]
        if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Iterable):
            raise TypeError("invalid aggregate input")
        result[name] = tuple(value)
    return result


def _canonical(value: object, spec: Mapping[str, object]) -> object | None:
    if value is None or value == "":
        return None
    kind = spec.get("type")
    if kind == "string":
        if not isinstance(value, str):
            raise TypeError("invalid scalar")
        return value
    if kind not in _NUMERIC_TYPES or isinstance(value, bool):
        raise TypeError("invalid scalar")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError("invalid scalar") from exc
    if not math.isfinite(number):
        raise ValueError("invalid scalar")
    if kind == "integer":
        if not number.is_integer():
            raise ValueError("invalid scalar")
        return int(number)
    return number


def _validate_rows(rows: tuple[Mapping[str, object], ...], resource: _Resource) -> tuple[tuple[Mapping[str, object], ...], bool]:
    canonical: list[Mapping[str, object]] = []
    valid = True
    seen: set[object] = set()
    for item in rows:
        if not isinstance(item, Mapping) or tuple(item) != resource.fields:
            valid = False
            continue
        values: dict[str, object] = {}
        try:
            for name in resource.fields:
                spec = resource.field_specs[name]
                value = _canonical(item[name], spec)
                constraints = spec.get("constraints", {})
                if not isinstance(constraints, Mapping):
                    raise TypeError("invalid scalar")
                if value is None and constraints.get("required"):
                    raise ValueError("invalid scalar")
                if value is not None:
                    allowed = constraints.get("enum")
                    if allowed is not None and value not in allowed:
                        raise ValueError("invalid scalar")
                    minimum, maximum = constraints.get("minimum"), constraints.get("maximum")
                    if minimum is not None and value < minimum or maximum is not None and value > maximum:
                        raise ValueError("invalid scalar")
                values[name] = value
        except (KeyError, TypeError, ValueError):
            valid = False
            continue
        if resource.primary_key is not None:
            key = values[resource.primary_key]
            if key is None or key in seen:
                valid = False
                continue
            seen.add(key)
        canonical.append(MappingProxyType(values))
    return tuple(canonical), valid


def _by_key(rows: tuple[Mapping[str, object], ...], key: str) -> dict[object, Mapping[str, object]]:
    return {item[key]: item for item in rows}


def _match(actual: object, expected: object, tolerance: float) -> tuple[bool, float]:
    if actual is None or expected is None:
        return actual is expected, 0.0
    if isinstance(actual, (int, float)) and not isinstance(actual, bool) and isinstance(expected, (int, float)) and not isinstance(expected, bool):
        difference = abs(float(actual) - float(expected))
        return difference <= tolerance, difference
    return actual == expected, 0.0


def _informative_ethnicity(value: object) -> object | None:
    return value if value in _INFORMATIVE_ETHNICITY else None


def _informative_race(value: object) -> object | None:
    return None if value in _NONRESPONSE_RACE or value is None else value


def _prefix(field: str) -> str:
    return field.removeprefix("dx_age_years_").replace("_", ".").upper()


def _diagnosis_ages(visits: Iterable[Mapping[str, object]], prefix: str | None = None) -> list[int]:
    ages: list[int] = []
    for visit in visits:
        age = visit["age_in_days"]
        if age is None:
            continue
        diagnoses = (visit[f"enc_diag_{index}"] for index in range(1, 34))
        if any(isinstance(code, str) and code.startswith(prefix or "") for code in diagnoses if code is not None):
            ages.append(age)
    return ages


def _expected_patient_values(patient: object, visits: Iterable[Mapping[str, object]]) -> tuple[dict[str, object], bool]:
    items = tuple(visits)
    ages = [item["age_in_days"] for item in items]
    if any(age is None for age in ages):
        return {}, True
    visit_ages = [int(age) for age in ages]
    diagnosis_ages = _diagnosis_ages(items)
    values: dict[str, object] = {
        "visits_count": len(items),
        "visits_count_pre_dx": sum(age < min(diagnosis_ages) for age in visit_ages) if diagnosis_ages else len(items),
        "min_visit_age_days": min(visit_ages) if visit_ages else None,
        "max_visit_age_days": max(visit_ages) if visit_ages else None,
        "visits_span_days": max(visit_ages) - min(visit_ages) if visit_ages else 0,
        "dx_age_years": round(min(diagnosis_ages) / 365.25, 3) if diagnosis_ages else None,
    }
    for metric in _Z_METRICS:
        values_for_metric = [
            float(item[metric]) for item in items if metric in item and item[metric] is not None
        ]
        prefix = f"{metric}"
        values[f"count_{prefix}"] = len(values_for_metric)
        values[f"mean_{prefix}"] = fmean(values_for_metric) if values_for_metric else None
        values[f"std_{prefix}"] = pstdev(values_for_metric) if values_for_metric else None
        values[f"min_{prefix}"] = min(values_for_metric) if values_for_metric else None
        values[f"max_{prefix}"] = max(values_for_metric) if values_for_metric else None
    for field in (f"dx_age_years_{item}" for item in (
        "e03_9", "e10", "e22_0", "e23_0", "e23_6", "e24", "e30_0", "e30_1", "e34_3",
        "e34_4", "e72_11", "k50", "k51", "k90_0", "n18", "n25_0", "p04_3", "p05", "p07",
        "p70", "p92_6", "q77", "q78_0", "q78_1", "q87_1", "q87_2", "q87_3", "q87_4",
        "q90", "q96", "q98_0", "q98_4", "q98_5",
    )):
        matching = _diagnosis_ages(items, _prefix(field))
        values[field] = round(min(matching) / 365.25, 3) if matching else None
    del patient
    return values, False


def _parity(candidate: tuple[Mapping[str, object], ...], reference: tuple[Mapping[str, object], ...],
            resource: _Resource, tolerance: float) -> tuple[bool, int, int, float]:
    candidate_by_key = _by_key(candidate, resource.primary_key or "")
    reference_by_key = _by_key(reference, resource.primary_key or "")
    failed = set(candidate_by_key) != set(reference_by_key)
    compared = mismatches = 0
    maximum = 0.0
    for identity in set(candidate_by_key) & set(reference_by_key):
        for field in resource.fields:
            compared += 1
            matched, difference = _match(candidate_by_key[identity][field], reference_by_key[identity][field], tolerance)
            maximum = max(maximum, difference)
            if not matched:
                failed = True
                mismatches += 1
    return failed, compared, mismatches, maximum


def _evaluate(base_rows: Mapping[str, Iterable[Mapping[str, object]]],
              candidate_rows: Mapping[str, Iterable[Mapping[str, object]]],
              reference_rows: Mapping[str, Iterable[Mapping[str, object]]],
              descriptor: Mapping[str, object], candidate: DerivationImplementation,
              reference: DerivationImplementation, policy: DerivationParityPolicy) -> DerivationParityReport:
    if not all(isinstance(value, expected) for value, expected in (
        (candidate, DerivationImplementation), (reference, DerivationImplementation), (policy, DerivationParityPolicy),
    )):
        raise DerivationParityUnavailable()
    resources, schema_valid = _descriptor_resources(descriptor)
    base_raw = _materialize(base_rows, _BASE_RESOURCES)
    candidate_raw = _materialize(candidate_rows, _AUGMENTED_RESOURCES)
    reference_raw = _materialize(reference_rows, _AUGMENTED_RESOURCES)
    if not schema_valid:
        checks = tuple(_check(name, failed=name == "schema_contract") for name in DERIVATION_PARITY_CHECK_NAMES)
        return _report(candidate, reference, policy, 0, 0, checks)
    base, base_valid = _validated_group(base_raw, resources)
    output_candidate, candidate_valid = _validated_group(candidate_raw, resources)
    output_reference, reference_valid = _validated_group(reference_raw, resources)
    patients = _by_key(base["patients"], "patient_id")
    visits = _by_key(base["visits"], "visit_id")
    candidate_patients = _by_key(output_candidate["patients_augmented"], "patient_id")
    candidate_visits = _by_key(output_candidate["visits_augmented"], "visit_id")
    reference_patients = _by_key(output_reference["patients_augmented"], "patient_id")
    reference_visits = _by_key(output_reference["visits_augmented"], "visit_id")
    checks: list[DerivationParityCheck] = [_check("schema_contract")]
    checks.append(_check("base_shape", failed=not base_valid))
    checks.append(_check("candidate_shape", failed=not candidate_valid))
    checks.append(_check("reference_shape", failed=not reference_valid))
    patient_alignment = set(patients) != set(candidate_patients) or set(patients) != set(reference_patients)
    visit_alignment = set(visits) != set(candidate_visits) or set(visits) != set(reference_visits)
    visit_alignment |= any(item["patient_id"] not in patients for item in candidate_visits.values())
    visit_alignment |= any(item["patient_id"] not in patients for item in reference_visits.values())
    checks.append(_check("patient_key_alignment", failed=patient_alignment))
    checks.append(_check("visit_key_alignment", failed=visit_alignment))
    patient_projection = _patient_projection(patients, candidate_patients, reference_patients)
    checks.append(_check("patient_identity_projection", *patient_projection))
    visit_projection = _visit_projection(patients, visits, candidate_visits, reference_visits, policy.deterministic_tolerance)
    checks.append(_check("visit_identity_projection", *visit_projection))
    age = _age_check(visits, candidate_visits, reference_visits, policy.deterministic_tolerance)
    checks.append(_check("deterministic_age_conversion", *age))
    units = _unit_check(visits, candidate_visits, reference_visits, policy.deterministic_tolerance)
    checks.append(_check("deterministic_unit_conversion", *units))
    bmi = _bmi_check(candidate_visits, reference_visits, policy.deterministic_tolerance)
    checks.append(_check("deterministic_bmi", *bmi))
    summaries = _summary_check(patients, visits, candidate_patients, reference_patients, candidate_visits, reference_visits, policy.deterministic_tolerance)
    checks.append(_check("deterministic_patient_summaries", *summaries))
    flags = _flag_check(candidate_patients, reference_patients, candidate_visits, reference_visits)
    checks.append(_check("clinical_flag_relationships", *flags))
    parity_patient = _parity(output_candidate["patients_augmented"], output_reference["patients_augmented"], resources["patients_augmented"], policy.reference_tolerance)
    parity_visit = _parity(output_candidate["visits_augmented"], output_reference["visits_augmented"], resources["visits_augmented"], policy.reference_tolerance)
    checks.append(_check("reference_field_parity", parity_patient[0] or parity_visit[0], False,
                         compared=parity_patient[1] + parity_visit[1], mismatches=parity_patient[2] + parity_visit[2],
                         difference=max(parity_patient[3], parity_visit[3])))
    underpowered = len(output_candidate["patients_augmented"]) < policy.minimum_patient_rows or len(output_reference["patients_augmented"]) < policy.minimum_patient_rows or len(output_candidate["visits_augmented"]) < policy.minimum_visit_rows or len(output_reference["visits_augmented"]) < policy.minimum_visit_rows
    checks.append(_check("support", unevaluable=underpowered, compared=2, difference=0.0))
    return _report(candidate, reference, policy, len(output_candidate["patients_augmented"]), len(output_candidate["visits_augmented"]), tuple(checks))


def _validated_group(raw: Mapping[str, tuple[Mapping[str, object], ...]], resources: Mapping[str, _Resource]) -> tuple[dict[str, tuple[Mapping[str, object], ...]], bool]:
    result: dict[str, tuple[Mapping[str, object], ...]] = {}
    valid = True
    for name, items in raw.items():
        result[name], item_valid = _validate_rows(items, resources[name])
        valid &= item_valid
    return result, valid


def _patient_projection(base: Mapping[str, Mapping[str, object]], candidate: Mapping[str, Mapping[str, object]],
                        reference: Mapping[str, Mapping[str, object]]) -> tuple[bool, bool, int, int, float]:
    failed = False
    compared = mismatches = 0
    for outputs in (candidate, reference):
        for identity, item in outputs.items():
            source = base.get(identity)
            if source is None:
                failed = True
                continue
            expected = {"patient_id": source["patient_id"], "sex": source["sex"], "ethnicity": _informative_ethnicity(source["ethnicity"])}
            expected.update({f"race_{index}": _informative_race(source[f"race_{index}"]) for index in range(1, 9)})
            for field, value in expected.items():
                compared += 1
                if item[field] != value:
                    failed = True
                    mismatches += 1
    return failed, False, compared, mismatches, 0.0


def _visit_projection(patients: Mapping[str, Mapping[str, object]], visits: Mapping[str, Mapping[str, object]],
                     candidate: Mapping[str, Mapping[str, object]], reference: Mapping[str, Mapping[str, object]],
                     tolerance: float) -> tuple[bool, bool, int, int, float]:
    failed = False
    compared = mismatches = 0
    maximum = 0.0
    common = ("patient_id", "visit_id", "age_in_days", "weight_oz", "height_in", "head_circ_cm", "encounter_type", "orig_enc_source_Epic_yn") + tuple(f"enc_diag_{index}" for index in range(1, 34))
    for outputs in (candidate, reference):
        for identity, item in outputs.items():
            source = visits.get(identity)
            patient = patients.get(item["patient_id"])
            if source is None or patient is None:
                failed = True
                continue
            expected = {field: source[field] for field in common}
            expected |= {"sex": patient["sex"], "ethnicity": _informative_ethnicity(patient["ethnicity"]), "race_1": _informative_race(patient["race_1"])}
            for field, value in expected.items():
                compared += 1
                matched, difference = _match(item[field], value, tolerance)
                maximum = max(maximum, difference)
                if not matched:
                    failed = True
                    mismatches += 1
    return failed, False, compared, mismatches, maximum


def _age_check(base: Mapping[str, Mapping[str, object]], candidate: Mapping[str, Mapping[str, object]],
               reference: Mapping[str, Mapping[str, object]], tolerance: float) -> tuple[bool, bool, int, int, float]:
    failed = unevaluable = False
    compared = mismatches = 0
    maximum = 0.0
    for outputs in (candidate, reference):
        for identity, item in outputs.items():
            age = base.get(identity, {}).get("age_in_days")
            if age is None:
                unevaluable = True
                continue
            for field, divisor, decimals in (("age_in_months", 30.4375, 2), ("age_in_years", 365.25, 3)):
                compared += 1
                matched, difference = _match(item[field], round(int(age) / divisor, decimals), tolerance)
                maximum = max(maximum, difference)
                if not matched:
                    failed = True
                    mismatches += 1
    return failed, unevaluable, compared, mismatches, maximum


def _unit_check(base: Mapping[str, Mapping[str, object]], candidate: Mapping[str, Mapping[str, object]],
                reference: Mapping[str, Mapping[str, object]], tolerance: float) -> tuple[bool, bool, int, int, float]:
    failed = unevaluable = False
    compared = mismatches = 0
    maximum = 0.0
    for outputs in (candidate, reference):
        for identity, item in outputs.items():
            source = base.get(identity)
            if source is None:
                failed = True
                continue
            for field, raw, conversion in (("weight_kg", source["weight_oz"], lambda x: float(x) / 35.274), ("height_cm", source["height_in"], lambda x: round(float(x) * 2.54, 3))):
                if raw is None:
                    unevaluable = True
                    continue
                if item[field] is None:
                    continue
                compared += 1
                matched, difference = _match(item[field], conversion(raw), tolerance)
                maximum = max(maximum, difference)
                if not matched:
                    failed = True
                    mismatches += 1
    return failed, unevaluable, compared, mismatches, maximum


def _bmi_check(candidate: Mapping[str, Mapping[str, object]], reference: Mapping[str, Mapping[str, object]],
               tolerance: float) -> tuple[bool, bool, int, int, float]:
    failed = unevaluable = False
    compared = mismatches = 0
    maximum = 0.0
    for outputs in (candidate, reference):
        for item in outputs.values():
            age = item["age_in_months"]
            if age is None:
                unevaluable = True
                continue
            weight, height = item["weight_kg"], item["height_cm"]
            expected = None if age < 24 or weight is None or height is None or weight <= 0 or height <= 0 else weight / (height / 100) ** 2
            compared += 1
            matched, difference = _match(item["bmi"], expected, tolerance)
            maximum = max(maximum, difference)
            if not matched:
                failed = True
                mismatches += 1
    return failed, unevaluable, compared, mismatches, maximum


def _summary_check(patients: Mapping[str, Mapping[str, object]], visits: Mapping[str, Mapping[str, object]],
                   candidate_patients: Mapping[str, Mapping[str, object]], reference_patients: Mapping[str, Mapping[str, object]],
                   candidate_visits: Mapping[str, Mapping[str, object]], reference_visits: Mapping[str, Mapping[str, object]],
                   tolerance: float) -> tuple[bool, bool, int, int, float]:
    del patients
    failed = unevaluable = False
    compared = mismatches = 0
    maximum = 0.0
    for outputs, augmented_visits in ((candidate_patients, candidate_visits), (reference_patients, reference_visits)):
        for identity, item in outputs.items():
            related_base = [visit for visit in visits.values() if visit["patient_id"] == identity]
            related_augmented = [visit for visit in augmented_visits.values() if visit["patient_id"] == identity]
            expected, missing = _expected_patient_values(identity, related_base)
            if missing:
                unevaluable = True
                continue
            augmented_expected, missing = _expected_patient_values(identity, related_augmented)
            if missing:
                unevaluable = True
                continue
            for field, value in expected.items():
                if field.startswith(("count_", "mean_", "std_", "min_", "max_")):
                    value = augmented_expected[field]
                compared += 1
                matched, difference = _match(item[field], value, tolerance)
                maximum = max(maximum, difference)
                if not matched:
                    failed = True
                    mismatches += 1
    return failed, unevaluable, compared, mismatches, maximum


def _flag_check(candidate_patients: Mapping[str, Mapping[str, object]], reference_patients: Mapping[str, Mapping[str, object]],
                candidate_visits: Mapping[str, Mapping[str, object]], reference_visits: Mapping[str, Mapping[str, object]]) -> tuple[bool, bool, int, int, float]:
    failed = False
    compared = mismatches = 0
    for outputs, patient_outputs in ((candidate_visits, candidate_patients), (reference_visits, reference_patients)):
        by_patient: dict[object, list[Mapping[str, object]]] = {}
        for item in outputs.values():
            by_patient.setdefault(item["patient_id"], []).append(item)
            relationships = (("stunting_flag", (item["height_z_score"],), -2), ("wasting_flag", (item["weight_for_length_z_score"], item["weight_for_stature_z_score"]), -2), ("underweight_flag", (item["bmi_percentile"],), 5), ("obesity_flag", (item["bmi_percentile"],), 95))
            for field, values, threshold in relationships:
                available = [float(value) for value in values if value is not None]
                if not available:
                    continue
                expected = int(any(value < threshold for value in available)) if field != "obesity_flag" else int(any(value >= threshold for value in available))
                compared += 1
                if item[field] != expected:
                    failed = True
                    mismatches += 1
        for identity, item in patient_outputs.items():
            related = by_patient.get(identity, [])
            expected_flags = {"ever_stunting_flag": "stunting_flag", "ever_wasting_flag": "wasting_flag", "ever_underweight_flag": "underweight_flag", "ever_obesity_flag": "obesity_flag"}
            for field, visit_flag in expected_flags.items():
                compared += 1
                expected = int(any(visit[visit_flag] == 1 for visit in related))
                if item[field] != expected:
                    failed = True
                    mismatches += 1
            compared += 1
            if item["healthy_flag"] == 1 and any(item[field] != 0 for field in _ADVERSE_PATIENT_FLAGS):
                failed = True
                mismatches += 1
    return failed, False, compared, mismatches, 0.0


def _report(candidate: DerivationImplementation, reference: DerivationImplementation, policy: DerivationParityPolicy,
            patient_count: int, visit_count: int, checks: tuple[DerivationParityCheck, ...]) -> DerivationParityReport:
    status = max((item.status for item in checks), key=lambda item: {DerivationParityStatus.PASS: 0, DerivationParityStatus.UNEVALUABLE: 1, DerivationParityStatus.FAIL: 2}[item])
    counts = {item.value: sum(check.status is item for check in checks) for item in DerivationParityStatus}
    return DerivationParityReport(DERIVATION_PARITY_VERSION, EXPECTED_SCHEMA_FINGERPRINT, policy, candidate, reference,
                                 patient_count, visit_count, status, counts, checks)
