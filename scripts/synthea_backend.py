"""Opt-in external Synthea development backend.

The ordinary ``synthetic.generate`` command does not import this module.  The
backend is deliberately kept at the process boundary: it runs a caller-owned,
pinned Synthea checkout, discards FHIR identifiers and names, and returns only
descriptor-shaped fictional rows plus aggregate report values.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import stat
import subprocess
import tempfile
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

from synthetic.base_resources import BASE_RESOURCES
from synthetic.development_runtime import build_development_runtime
from synthetic.package_export import (
    PackageExportMetadata,
    export_exact_schema_package,
)
from synthetic.randomness import synthetic_id
from synthetic.schema_contract import field_names, load_descriptor

BACKEND_ERROR = "synthea backend unavailable"
BACKEND_VERSION = "synthea-backend-v1"
FHIR_PARSER_VERSION = "synthea-fhir-r4-parser-v2"
GROWTH_OVERLAY_ID = "synthea-growth-overlay-v1"
MODULE_ID = "synthea-ppoc-ghd-module-v1"
REPORT_VERSION = "synthea-backend-report-v1"
SYNTHEA_REVISION = "d9d07a6eef91ee5144293b42ab64224d84d124f8"
SYNTHEA_GRADLE_VERSION = "9.2.1"
SYNTHEA_JAVA_MAJOR = 17
SYNTHEA_PROFILE = "synthea-development"
MODULE_PRIOR = 0.143291
_MAX_PEDIATRIC_AGE_YEARS = 18
_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
# Synthea's standalone FHIR exporter uses ``urn:uuid:<id>`` references while
# hand-authored R4 fixtures commonly use the typed ``Patient/<id>`` and
# ``Encounter/<id>`` forms.  Both are local references; absolute URLs and
# references to other resource types remain rejected by ``_reference_id``.
_PATIENT_REFERENCE_RE = re.compile(r"\A(?:Patient/|urn:uuid:)([^/]+)\Z")
_ENCOUNTER_REFERENCE_RE = re.compile(r"\A(?:Encounter/|urn:uuid:)([^/]+)\Z")
_ICD10_SYSTEMS = frozenset(
    {
        "http://hl7.org/fhir/sid/icd-10-cm",
        "http://hl7.org/fhir/sid/icd-10",
        "urn:oid:2.16.840.1.113883.6.90",
    }
)
_ICD10_CODE_RE = re.compile(r"\A[A-Z][0-9][0-9A-Z](?:\.[0-9A-Z]{1,4})?\Z")
_ETHNICITIES = frozenset(
    {
        "Not Hispanic or Latino",
        "Hispanic or Latino",
        "Choose not to Answer",
        "Unknown",
        "Unable to collect",
        "Patient does not know",
    }
)
_RACES = frozenset(
    {
        "American Indian or Alaska Native",
        "Another Race",
        "Asian",
        "Black or African American",
        "Choose not to answer",
        "Middle Eastern or Northern African",
        "Native Hawaiian or Other Pacific Islander",
        "Patient does not know",
        "Unable to collect",
        "Unknown",
        "White",
    }
)
_OBSERVATION_CODES = {
    "8302-2": "height_cm",
    "29463-7": "weight_kg",
    "39156-5": "bmi",
    "9843-4": "head_circ_cm",
}


def _unavailable() -> ValueError:
    return ValueError(BACKEND_ERROR)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _unavailable()
        result[key] = value
    return result


def _reject_nonfinite(_: str) -> None:
    raise _unavailable()


def _parse_document(value: bytes | str | Mapping[str, object]) -> dict[str, object]:
    try:
        if isinstance(value, Mapping):
            value = json.dumps(value, allow_nan=False, separators=(",", ":"))
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        if not isinstance(value, str):
            raise _unavailable()
        parsed = json.loads(
            value,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeError, TypeError, ValueError, json.JSONDecodeError, RecursionError):
        raise _unavailable() from None
    if not isinstance(parsed, dict):
        raise _unavailable()
    return parsed


def _require_text(value: object) -> str:
    if type(value) is not str or not value.strip() or "\n" in value or "\r" in value:
        raise _unavailable()
    return value.strip()


def _resource_entries(document: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    resource_type = document.get("resourceType")
    if resource_type == "Bundle":
        entries = document.get("entry")
        if not isinstance(entries, list):
            raise _unavailable()
        resources: list[dict[str, object]] = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise _unavailable()
            resource = entry.get("resource")
            if resource is None:
                continue
            if not isinstance(resource, dict):
                raise _unavailable()
            resources.append(resource)
        return tuple(resources)
    if type(resource_type) is not str:
        raise _unavailable()
    return (dict(document),)


def _resource_id(resource: Mapping[str, object]) -> str:
    return _require_text(resource.get("id"))


def _reference_id(value: object, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, Mapping):
        raise _unavailable()
    reference = value.get("reference")
    if type(reference) is not str:
        raise _unavailable()
    match = pattern.fullmatch(reference)
    if match is None:
        raise _unavailable()
    return _require_text(match.group(1))


def _fhir_date(value: object) -> date:
    if type(value) is not str:
        raise _unavailable()
    raw = value.strip()
    try:
        parsed = date.fromisoformat(raw[:10])
    except ValueError:
        raise _unavailable() from None
    if raw[:10] != parsed.isoformat():
        raise _unavailable()
    return parsed


def _resource_date(resource: Mapping[str, object], *keys: str) -> date | None:
    for key in keys:
        if key in resource and resource[key] is not None:
            value = resource[key]
            if isinstance(value, Mapping):
                value = value.get("start") or value.get("end")
            return _fhir_date(value)
    return None


def _code_values(resource: Mapping[str, object]) -> tuple[str, ...]:
    code = resource.get("code")
    if not isinstance(code, Mapping):
        return ()
    codings = code.get("coding")
    if not isinstance(codings, list):
        return ()
    values: list[str] = []
    for coding in codings:
        if not isinstance(coding, Mapping) or coding.get("code") is None:
            continue
        try:
            value = _require_text(coding.get("code"))
        except ValueError:
            continue
        if value not in values:
            values.append(value)
    return tuple(values)


def _icd10_code_values(resource: Mapping[str, object]) -> tuple[str, ...]:
    code = resource.get("code")
    if not isinstance(code, Mapping):
        return ()
    codings = code.get("coding")
    if not isinstance(codings, list):
        return ()
    values: list[str] = []
    for coding in codings:
        if not isinstance(coding, Mapping) or coding.get("system") not in _ICD10_SYSTEMS:
            continue
        try:
            value = _require_text(coding.get("code"))
        except ValueError:
            continue
        if _ICD10_CODE_RE.fullmatch(value) is not None and value not in values:
            values.append(value)
    return tuple(values)


def _extension_text(resource: Mapping[str, object], suffix: str) -> tuple[str, ...]:
    extensions = resource.get("extension")
    if not isinstance(extensions, list):
        return ()
    values: list[str] = []
    for extension in extensions:
        if not isinstance(extension, Mapping):
            continue
        url = extension.get("url")
        if not isinstance(url, str) or not url.endswith(suffix):
            continue
        nested = extension.get("extension")
        if isinstance(nested, list):
            for child in nested:
                if isinstance(child, Mapping) and child.get("url") == "text":
                    value = child.get("valueString")
                    if isinstance(value, str) and value.strip():
                        values.append(value.strip())
        coding = extension.get("valueCoding")
        if isinstance(coding, Mapping):
            for key in ("display", "code"):
                value = coding.get(key)
                if isinstance(value, str) and value.strip():
                    values.append(value.strip())
                    break
        value = extension.get("valueString")
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return tuple(values)


def _sex(value: object) -> str:
    return {"female": "F", "male": "M"}.get(value, "U") if type(value) is str else "U"


def _allowed_or_unknown(value: str, allowed: frozenset[str]) -> str:
    return value if value in allowed else "Unknown"


@dataclass(frozen=True, repr=False)
class _FhirObservation:
    source_id: str
    patient_source_id: str
    encounter_source_id: str | None
    effective_date: date
    metric: str
    value: float


@dataclass(frozen=True, repr=False)
class _FhirCondition:
    source_id: str
    patient_source_id: str
    encounter_source_id: str | None
    onset_date: date | None
    codes: tuple[str, ...]


@dataclass(frozen=True, repr=False)
class _FhirEncounter:
    source_id: str
    patient_source_id: str
    start_date: date | None


@dataclass(frozen=True, repr=False)
class ParsedSyntheaPatient:
    """Internal parsed state; source identifiers never enter public projections."""

    source_id: str
    sex: str
    ethnicity: str
    races: tuple[str, ...]
    birth_date: date
    observations: tuple[_FhirObservation, ...]
    encounters: tuple[_FhirEncounter, ...]
    conditions: tuple[_FhirCondition, ...]

    def __repr__(self) -> str:
        return "ParsedSyntheaPatient(<synthetic>)"


@dataclass(frozen=True, repr=False)
class _PpocVisit:
    date: date
    encounter_source_id: str | None
    age_days: int
    height_cm: float | None
    weight_kg: float | None
    bmi: float | None
    head_circ_cm: float | None
    diagnoses: tuple[str, ...]


@dataclass(frozen=True, repr=False)
class FhirProjection:
    """Descriptor-shaped base rows and aggregate counts from one parse."""

    base_rows: dict[str, list[dict[str, object]]]
    patient_count: int
    ghd_count: int
    visit_count: int
    height_observation_count: int
    weight_observation_count: int
    bmi_observation_count: int
    head_observation_count: int
    min_age_days: int
    max_age_days: int
    mean_age_days: float
    growth_overlay_id: str = GROWTH_OVERLAY_ID

    def __repr__(self) -> str:
        return "FhirProjection(<synthetic>)"


@dataclass(frozen=True, repr=False)
class SyntheaBackendReport:
    """Aggregate-only result metadata; no patient-level state is serializable."""

    report_version: str
    engine_revision: str
    module_sha256: str
    overlay_sha256: str
    configuration_sha256: str
    requested_patient_count: int
    generated_patient_count: int
    healthy_count: int
    ghd_count: int
    visit_count: int
    height_observation_count: int
    weight_observation_count: int
    bmi_observation_count: int
    head_observation_count: int
    min_age_days: int
    max_age_days: int
    status: str
    mean_age_days: float = 0.0

    def __post_init__(self) -> None:
        if type(self.report_version) is not str or self.report_version != REPORT_VERSION:
            raise ValueError(BACKEND_ERROR)
        if type(self.engine_revision) is not str or self.engine_revision != SYNTHEA_REVISION:
            raise ValueError(BACKEND_ERROR)
        for name in ("module_sha256", "overlay_sha256", "configuration_sha256"):
            if type(getattr(self, name)) is not str or _DIGEST_RE.fullmatch(getattr(self, name)) is None:
                raise ValueError(BACKEND_ERROR)
        counts = (
            "requested_patient_count",
            "generated_patient_count",
            "healthy_count",
            "ghd_count",
            "visit_count",
            "height_observation_count",
            "weight_observation_count",
            "bmi_observation_count",
            "head_observation_count",
        )
        for name in counts:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(BACKEND_ERROR)
        if self.generated_patient_count != self.healthy_count + self.ghd_count:
            raise ValueError(BACKEND_ERROR)
        if self.generated_patient_count > self.requested_patient_count:
            raise ValueError(BACKEND_ERROR)
        if (
            isinstance(self.min_age_days, bool)
            or not isinstance(self.min_age_days, int)
            or self.min_age_days < 0
            or isinstance(self.max_age_days, bool)
            or not isinstance(self.max_age_days, int)
            or self.max_age_days < self.min_age_days
            or self.status != "GENERATED_TEST_ONLY"
        ):
            raise ValueError(BACKEND_ERROR)
        if (
            isinstance(self.mean_age_days, bool)
            or not isinstance(self.mean_age_days, (int, float))
            or not math.isfinite(float(self.mean_age_days))
            or not self.min_age_days <= float(self.mean_age_days) <= self.max_age_days
        ):
            raise ValueError(BACKEND_ERROR)

    def to_mapping(self) -> dict[str, object]:
        return dict(asdict(self))

    def to_json_bytes(self) -> bytes:
        return (
            json.dumps(
                self.to_mapping(),
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("ascii")


def _parse_observation(resource: Mapping[str, object], patient_id: str) -> _FhirObservation | None:
    codes = _code_values(resource)
    metric = next((_OBSERVATION_CODES[code] for code in codes if code in _OBSERVATION_CODES), None)
    if metric is None:
        return None
    value_quantity = resource.get("valueQuantity")
    if not isinstance(value_quantity, Mapping):
        raise _unavailable()
    value = value_quantity.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _unavailable()
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise _unavailable()
    effective_date = _resource_date(resource, "effectiveDateTime", "effectivePeriod")
    if effective_date is None:
        raise _unavailable()
    encounter = resource.get("encounter")
    encounter_id = None if encounter is None else _reference_id(encounter, _ENCOUNTER_REFERENCE_RE)
    return _FhirObservation(
        source_id=_resource_id(resource),
        patient_source_id=patient_id,
        encounter_source_id=encounter_id,
        effective_date=effective_date,
        metric=metric,
        value=value,
    )


def parse_fhir_documents(
    documents: Iterable[bytes | str | Mapping[str, object]],
) -> tuple[ParsedSyntheaPatient, ...]:
    """Parse supported FHIR resources while retaining source IDs only in memory."""

    records: dict[str, dict[str, object]] = {}

    def record_for(patient_id: str) -> dict[str, object]:
        return records.setdefault(
            patient_id,
            {"patient": None, "observations": [], "encounters": [], "conditions": []},
        )

    for document in documents:
        parsed = _parse_document(document)
        for resource in _resource_entries(parsed):
            resource_type = resource.get("resourceType")
            if resource_type == "Patient":
                patient_id = _resource_id(resource)
                target = record_for(patient_id)
                if target["patient"] is not None:
                    raise _unavailable()
                birth_date = _resource_date(resource, "birthDate")
                if birth_date is None:
                    raise _unavailable()
                race_values = list(
                    dict.fromkeys(
                        _allowed_or_unknown(value, _RACES)
                        for value in _extension_text(resource, "us-core-race")
                    )
                )[:8]
                if not race_values:
                    race_values.append("Unknown")
                race_values.extend("" for _ in range(8 - len(race_values)))
                target["patient"] = (
                    _sex(resource.get("gender")),
                    _allowed_or_unknown(
                        _extension_text(
                            resource,
                            "us-core-ethnicity",
                        )[0]
                        if _extension_text(resource, "us-core-ethnicity")
                        else "Unknown",
                        _ETHNICITIES,
                    ),
                    tuple(race_values),
                    birth_date,
                )
                continue

            if resource_type not in {"Encounter", "Observation", "Condition"}:
                continue
            subject = resource.get("subject")
            if subject is None:
                raise _unavailable()
            patient_id = _reference_id(subject, _PATIENT_REFERENCE_RE)
            target = record_for(patient_id)
            if resource_type == "Encounter":
                target["encounters"].append(
                    _FhirEncounter(
                        source_id=_resource_id(resource),
                        patient_source_id=patient_id,
                        start_date=(
                            _resource_date(resource.get("period", {}), "start")
                            if isinstance(resource.get("period", {}), Mapping)
                            else None
                        ),
                    )
                )
            elif resource_type == "Observation":
                observation = _parse_observation(resource, patient_id)
                if observation is not None:
                    target["observations"].append(observation)
            else:
                codes = _icd10_code_values(resource)
                if not codes:
                    continue
                encounter = resource.get("encounter")
                target["conditions"].append(
                    _FhirCondition(
                        source_id=_resource_id(resource),
                        patient_source_id=patient_id,
                        encounter_source_id=(
                            None
                            if encounter is None
                            else _reference_id(encounter, _ENCOUNTER_REFERENCE_RE)
                        ),
                        onset_date=_resource_date(resource, "onsetDateTime", "recordedDate"),
                        codes=codes,
                    )
                )

    parsed_patients: list[ParsedSyntheaPatient] = []
    for source_id in sorted(records):
        target = records[source_id]
        patient = target["patient"]
        if not isinstance(patient, tuple) or len(patient) != 4:
            raise _unavailable()
        sex, ethnicity, races, birth_date = patient
        if not isinstance(races, tuple) or not isinstance(birth_date, date):
            raise _unavailable()
        observations = tuple(sorted(target["observations"], key=lambda item: item.source_id))
        encounters = tuple(sorted(target["encounters"], key=lambda item: item.source_id))
        conditions = tuple(sorted(target["conditions"], key=lambda item: item.source_id))
        parsed_patients.append(
            ParsedSyntheaPatient(
                source_id=source_id,
                sex=sex,
                ethnicity=ethnicity,
                races=races,
                birth_date=birth_date,
                observations=observations,
                encounters=encounters,
                conditions=conditions,
            )
        )
    if not parsed_patients:
        raise _unavailable()
    return tuple(parsed_patients)


def _build_visits(patient: ParsedSyntheaPatient) -> tuple[_PpocVisit, ...]:
    groups: dict[tuple[str, date], dict[str, float]] = defaultdict(dict)
    for observation in patient.observations:
        if observation.effective_date < patient.birth_date:
            raise _unavailable()
        group_id = observation.encounter_source_id or f"date:{observation.effective_date.isoformat()}"
        group = groups[(group_id, observation.effective_date)]
        group.setdefault(observation.metric, observation.value)
    if not groups:
        raise _unavailable()
    metrics = {metric for values in groups.values() for metric in values}
    if "height_cm" not in metrics:
        raise _unavailable()
    if "weight_kg" not in metrics:
        raise _unavailable()

    ordered = sorted(groups.items(), key=lambda item: (item[0][1], item[0][0]))
    visits: list[_PpocVisit] = []
    for (encounter_id, visit_date), values in ordered:
        age_days = (visit_date - patient.birth_date).days
        bmi = values.get("bmi")
        height = values.get("height_cm")
        weight = values.get("weight_kg")
        if bmi is None and age_days >= 730 and height is not None and weight is not None:
            bmi = weight / (height / 100) ** 2
        visits.append(
            _PpocVisit(
                date=visit_date,
                encounter_source_id=None if encounter_id.startswith("date:") else encounter_id,
                age_days=age_days,
                height_cm=height,
                weight_kg=weight,
                bmi=bmi,
                head_circ_cm=values.get("head_circ_cm"),
                diagnoses=(),
            )
        )

    assigned: list[set[str]] = [set() for _ in visits]
    for condition in patient.conditions:
        matches = [
            index
            for index, visit in enumerate(visits)
            if condition.encounter_source_id is not None
            and visit.encounter_source_id == condition.encounter_source_id
        ]
        if not matches:
            if condition.onset_date is None:
                index = 0
            else:
                index = next(
                    (
                        index
                        for index, visit in enumerate(visits)
                        if visit.date >= condition.onset_date
                    ),
                    len(visits) - 1,
                )
            matches = [index]
        for index in matches:
            assigned[index].update(condition.codes)
    return tuple(
        _PpocVisit(
            date=visit.date,
            encounter_source_id=visit.encounter_source_id,
            age_days=visit.age_days,
            height_cm=visit.height_cm,
            weight_kg=visit.weight_kg,
            bmi=visit.bmi,
            head_circ_cm=visit.head_circ_cm,
            diagnoses=tuple(sorted(assigned[index]))[:33],
        )
        for index, visit in enumerate(visits)
    )


def _validate_pediatric_ages(
    patients: Sequence[ParsedSyntheaPatient], reference_date: date
) -> None:
    """Enforce the fixed 0–18-year Synthea request at the adapter boundary."""

    try:
        eighteenth_birthday = reference_date.replace(
            year=reference_date.year - _MAX_PEDIATRIC_AGE_YEARS
        )
    except ValueError:  # February 29 in a leap year has no non-leap counterpart.
        eighteenth_birthday = reference_date.replace(
            year=reference_date.year - _MAX_PEDIATRIC_AGE_YEARS,
            day=28,
        )
    for patient in patients:
        if patient.birth_date > reference_date or patient.birth_date < eighteenth_birthday:
            raise _unavailable()


def _unit_interval(seed: int, patient_index: int) -> float:
    payload = f"{GROWTH_OVERLAY_ID}\x1f{seed}\x1f{patient_index}\x1fgrowth".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") / 2**64


def _overlay_visit(visit: _PpocVisit, *, ghd: bool, seed: int, patient_index: int) -> _PpocVisit:
    if not ghd:
        return visit
    severity = 0.10 + 0.06 * _unit_interval(seed, patient_index)
    progress = min(1.0, max(0.0, (visit.age_days - 365) / 5114))
    factor = 1.0 - severity * progress
    height = None if visit.height_cm is None else visit.height_cm * factor
    weight = None if visit.weight_kg is None else visit.weight_kg * factor**2
    bmi = visit.bmi
    if height is not None and weight is not None:
        bmi = weight / (height / 100) ** 2
    return _PpocVisit(
        date=visit.date,
        encounter_source_id=visit.encounter_source_id,
        age_days=visit.age_days,
        height_cm=height,
        weight_kg=weight,
        bmi=bmi,
        head_circ_cm=visit.head_circ_cm,
        diagnoses=visit.diagnoses,
    )


def _blank_row(descriptor: Mapping[str, object], resource_name: str) -> dict[str, object]:
    return {field: "" for field in field_names(dict(descriptor), resource_name)}


def project_fhir_patients(
    patients: Sequence[ParsedSyntheaPatient],
    descriptor: Mapping[str, object],
    *,
    seed: int,
) -> FhirProjection:
    """Project parsed FHIR patients into the exact six base-resource row sets."""

    if isinstance(patients, (str, bytes)) or not isinstance(patients, Sequence) or not patients:
        raise _unavailable()
    rows = {name: [] for name in BASE_RESOURCES}
    age_values: list[int] = []
    counts = {metric: 0 for metric in ("height_cm", "weight_kg", "bmi", "head_circ_cm")}
    ghd_count = 0

    for patient_index, patient in enumerate(sorted(patients, key=lambda item: item.source_id)):
        visits = _build_visits(patient)
        ghd = any(code == "E23.0" or code.startswith("E23.0") for visit in visits for code in visit.diagnoses)
        if ghd:
            ghd_count += 1
        public_patient_id = synthetic_id(seed, "synthea-patient", patient_index)
        patient_row = _blank_row(descriptor, "patients")
        patient_row.update(
            {
                "patient_id": public_patient_id,
                "sex": patient.sex,
                "ethnicity": patient.ethnicity,
                **{
                    f"race_{index}": patient.races[index - 1]
                    for index in range(1, 9)
                },
            }
        )
        rows["patients"].append(patient_row)

        for visit_index, raw_visit in enumerate(visits):
            visit = _overlay_visit(raw_visit, ghd=ghd, seed=seed, patient_index=patient_index)
            age_values.append(visit.age_days)
            for metric in counts:
                if getattr(visit, metric) is not None:
                    counts[metric] += 1
            visit_row = _blank_row(descriptor, "visits")
            visit_row.update(
                {
                    "patient_id": public_patient_id,
                    "visit_id": synthetic_id(
                        seed,
                        "synthea-visit",
                        patient_index * 100_000 + visit_index,
                    ),
                    "age_in_days": visit.age_days,
                    "encounter_type": "Office Visit",
                    "orig_enc_source_Epic_yn": "N",
                    "weight_oz": "" if visit.weight_kg is None else visit.weight_kg * 35.274,
                    "height_in": "" if visit.height_cm is None else visit.height_cm / 2.54,
                    "head_circ_cm": "" if visit.head_circ_cm is None else visit.head_circ_cm,
                    "BMI": "" if visit.bmi is None else visit.bmi,
                }
            )
            for diagnosis_index, diagnosis in enumerate(visit.diagnoses, start=1):
                visit_row[f"enc_diag_{diagnosis_index}"] = diagnosis
            rows["visits"].append(visit_row)

    if not age_values:
        raise _unavailable()
    return FhirProjection(
        base_rows=rows,
        patient_count=len(rows["patients"]),
        ghd_count=ghd_count,
        visit_count=len(rows["visits"]),
        height_observation_count=counts["height_cm"],
        weight_observation_count=counts["weight_kg"],
        bmi_observation_count=counts["bmi"],
        head_observation_count=counts["head_circ_cm"],
        min_age_days=min(age_values),
        max_age_days=max(age_values),
        mean_age_days=sum(age_values) / len(age_values),
    )


def _canonical_digest(root: Path) -> str:
    files = sorted(path for path in root.rglob("*") if path.is_file())
    payload = b"".join(
        path.relative_to(root).as_posix().encode("utf-8") + b"\0" + path.read_bytes() + b"\0"
        for path in files
    )
    return hashlib.sha256(payload).hexdigest()


def overlay_digest(root: Path | None = None) -> str:
    """Return the aggregate digest of the checked-in module overlay."""

    overlay = root or Path(__file__).resolve().parent / "synthea" / "overlay"
    if not overlay.is_dir():
        raise _unavailable()
    return _canonical_digest(overlay)


@dataclass(frozen=True)
class SyntheaBackendConfig:
    """Explicit caller-controlled options for one external Synthea run."""

    synthea_root: Path
    output: Path
    patient_count: int
    seed: int
    java_home: Path | None = None
    descriptor_path: Path | None = None
    reference_time: str = "2026-09-01T00:00:00Z"
    software_revision: str = BACKEND_VERSION
    timeout_seconds: float = 900.0
    allow_gradle_network: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.synthea_root, Path) or not isinstance(self.output, Path):
            raise TypeError(BACKEND_ERROR)
        if self.java_home is not None and not isinstance(self.java_home, Path):
            raise ValueError(BACKEND_ERROR)
        if self.descriptor_path is not None and not isinstance(self.descriptor_path, Path):
            raise ValueError(BACKEND_ERROR)
        if (
            isinstance(self.patient_count, bool)
            or not isinstance(self.patient_count, int)
            or not 1 <= self.patient_count <= 10_000
            or isinstance(self.seed, bool)
            or not isinstance(self.seed, int)
        ):
            raise ValueError(BACKEND_ERROR)
        if type(self.reference_time) is not str or not self.reference_time.endswith("Z"):
            raise ValueError(BACKEND_ERROR)
        try:
            datetime.fromisoformat(self.reference_time[:-1]).date()
        except ValueError:
            raise _unavailable() from None
        if (
            type(self.software_revision) is not str
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", self.software_revision)
        ):
            raise ValueError(BACKEND_ERROR)
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(float(self.timeout_seconds))
            or self.timeout_seconds <= 0
            or type(self.allow_gradle_network) is not bool
        ):
            raise ValueError(BACKEND_ERROR)

    @property
    def reference_date(self) -> date:
        return datetime.fromisoformat(self.reference_time[:-1]).date()


def _regular_file(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode)


def _regular_directory(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode)


def _git_output(root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=False,
            shell=False,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        raise _unavailable() from None
    if completed.returncode != 0:
        raise _unavailable()
    return completed.stdout.strip()


def verify_synthea_checkout(root: Path) -> None:
    """Verify the exact external checkout without exposing its path or output."""

    if not isinstance(root, Path) or not _regular_directory(root):
        raise _unavailable()
    required = (
        root / "gradlew",
        root / "build.gradle",
        root / "gradle" / "wrapper" / "gradle-wrapper.properties",
    )
    if not all(_regular_file(path) for path in required):
        raise _unavailable()
    try:
        build_text = (root / "build.gradle").read_text(encoding="utf-8")
        wrapper_text = (root / "gradle" / "wrapper" / "gradle-wrapper.properties").read_text(
            encoding="utf-8"
        )
    except (OSError, UnicodeError):
        raise _unavailable() from None
    if not re.search(r"sourceCompatibility\s*=\s*['\"]17['\"]", build_text):
        raise _unavailable()
    if f"gradle-{SYNTHEA_GRADLE_VERSION}-bin.zip" not in wrapper_text:
        raise _unavailable()
    if _git_output(root, "rev-parse", "HEAD") != SYNTHEA_REVISION:
        raise _unavailable()
    for arguments in (("diff", "--quiet"), ("diff", "--cached", "--quiet")):
        try:
            completed = subprocess.run(
                ["git", "-C", str(root), *arguments],
                check=False,
                shell=False,
                capture_output=True,
            )
        except (OSError, subprocess.SubprocessError):
            raise _unavailable() from None
        if completed.returncode != 0:
            raise _unavailable()


_CHECKOUT_IGNORED = frozenset({".git", ".gradle", "build", "output"})


def copy_checkout_tree(source: Path, destination: Path) -> None:
    """Copy a pinned checkout while rejecting links and special files."""

    if not _regular_directory(source) or destination.exists() or destination.is_symlink():
        raise _unavailable()
    try:
        destination.mkdir(mode=0o700)
        for entry in sorted(source.iterdir(), key=lambda item: item.name):
            if entry.name in _CHECKOUT_IGNORED:
                continue
            if entry.is_symlink():
                raise _unavailable()
            target = destination / entry.name
            if entry.is_dir():
                copy_checkout_tree(entry, target)
            elif entry.is_file():
                shutil.copy2(entry, target, follow_symlinks=False)
            else:
                raise _unavailable()
    except ValueError:
        raise
    except (OSError, shutil.Error):
        raise _unavailable() from None


def copy_overlay_tree(source: Path, destination: Path) -> None:
    """Copy only the versioned module overlay into an isolated work root."""

    if not _regular_directory(source) or destination.exists() or destination.is_symlink():
        raise _unavailable()
    try:
        destination.mkdir(mode=0o700)
        for entry in sorted(source.iterdir(), key=lambda item: item.name):
            if entry.is_symlink():
                raise _unavailable()
            target = destination / entry.name
            if entry.is_dir():
                copy_overlay_tree(entry, target)
            elif entry.is_file():
                shutil.copy2(entry, target, follow_symlinks=False)
            else:
                raise _unavailable()
    except ValueError:
        raise
    except (OSError, shutil.Error):
        raise _unavailable() from None


def verify_java_home(java_home: Path) -> Path:
    """Return the Java executable only when its reported major is exactly 17."""

    if not isinstance(java_home, Path) or not _regular_directory(java_home):
        raise _unavailable()
    executable = java_home / "bin" / "java"
    if not _regular_file(executable):
        raise _unavailable()
    try:
        completed = subprocess.run(
            [str(executable), "-version"],
            check=False,
            shell=False,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        raise _unavailable() from None
    version_text = f"{completed.stdout}\n{completed.stderr}"
    match = re.search(r'version\s+"(\d+)(?:\.|")', version_text)
    if completed.returncode != 0 or match is None or int(match.group(1)) != SYNTHEA_JAVA_MAJOR:
        raise _unavailable()
    return executable


def _reference_arg(reference_time: str) -> str:
    try:
        return datetime.fromisoformat(reference_time[:-1]).date().strftime("%Y%m%d")
    except ValueError:
        raise _unavailable() from None


def build_synthea_command(
    config: SyntheaBackendConfig,
    *,
    work_root: Path,
    fhir_output: Path,
    overlay_dir: Path,
) -> tuple[str, ...]:
    """Build the fixed argument vector passed to Synthea's Gradle task."""

    if not isinstance(config, SyntheaBackendConfig):
        raise _unavailable()
    args = [
        str(work_root / "gradlew"),
        "--no-daemon",
    ]
    if not config.allow_gradle_network:
        args.append("--offline")
    args.extend(
        [
            "-Dorg.gradle.vfs.watch=false",
            "run",
            "--args="
            + " ".join(
                (
                    f"-s {config.seed}",
                    f"-p {config.patient_count}",
                    "-a 0-18",
                    f"-r {_reference_arg(config.reference_time)}",
                    f"-d {overlay_dir}",
                    "--exporter.fhir.export=true",
                    "--exporter.fhir.transaction_bundle=false",
                    f"--exporter.baseDirectory={fhir_output}/",
                )
            ),
        ]
    )
    return tuple(args)


def invoke_synthea(
    config: SyntheaBackendConfig,
    *,
    work_root: Path,
    overlay_dir: Path,
) -> Path:
    """Run Synthea in an isolated root and return its private FHIR directory."""

    if not isinstance(config, SyntheaBackendConfig) or not _regular_directory(work_root):
        raise _unavailable()
    fhir_output = work_root / "synthea-output"
    try:
        fhir_output.mkdir(mode=0o700)
    except OSError:
        raise _unavailable() from None
    java_home = config.java_home or (
        Path(os.environ["JAVA_HOME"]) if os.environ.get("JAVA_HOME") else None
    )
    if java_home is None:
        raise _unavailable()
    executable = verify_java_home(java_home)
    command = build_synthea_command(
        config,
        work_root=work_root,
        fhir_output=fhir_output,
        overlay_dir=overlay_dir,
    )
    environment = dict(os.environ)
    environment["JAVA_HOME"] = str(java_home)
    environment["PATH"] = f"{java_home / 'bin'}{os.pathsep}{environment.get('PATH', '')}"
    del executable
    try:
        completed = subprocess.run(
            list(command),
            cwd=work_root,
            env=environment,
            check=False,
            shell=False,
            capture_output=True,
            timeout=float(config.timeout_seconds),
        )
    except (OSError, subprocess.SubprocessError):
        raise _unavailable() from None
    if completed.returncode != 0:
        raise _unavailable()
    result_root = fhir_output / "fhir" if (fhir_output / "fhir").is_dir() else fhir_output
    try:
        files = [
            path
            for path in result_root.iterdir()
            if path.is_file() and not path.is_symlink() and path.suffix == ".json"
        ]
    except OSError:
        raise _unavailable() from None
    if not files:
        raise _unavailable()
    return result_root


@dataclass(frozen=True, repr=False)
class SyntheaBackendResult:
    """Promoted package path plus aggregate-only backend metadata."""

    package: Path
    report: SyntheaBackendReport

    def __repr__(self) -> str:
        return "SyntheaBackendResult(<synthetic>)"


def _module_path() -> Path:
    return Path(__file__).resolve().parent / "synthea" / "overlay" / "modules" / "ppoc_growth_disorder.json"


def _configuration_digest(
    config: SyntheaBackendConfig,
    *,
    module_sha256: str,
    overlay_sha256: str,
) -> str:
    payload = {
        "backend_version": BACKEND_VERSION,
        "parser_version": FHIR_PARSER_VERSION,
        "engine_revision": SYNTHEA_REVISION,
        "gradle_version": SYNTHEA_GRADLE_VERSION,
        "java_major": SYNTHEA_JAVA_MAJOR,
        "module_id": MODULE_ID,
        "module_sha256": module_sha256,
        "growth_overlay_id": GROWTH_OVERLAY_ID,
        "overlay_sha256": overlay_sha256,
        "profile": SYNTHEA_PROFILE,
        "patient_count": config.patient_count,
        "seed": config.seed,
        "reference_time": config.reference_time,
        "software_revision": config.software_revision,
        "allow_gradle_network": config.allow_gradle_network,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _read_fhir_documents(root: Path) -> tuple[bytes, ...]:
    if not _regular_directory(root):
        raise _unavailable()
    try:
        paths = sorted(root.iterdir(), key=lambda path: path.name)
    except OSError:
        raise _unavailable() from None
    documents: list[bytes] = []
    for path in paths:
        if path.suffix != ".json":
            continue
        if not _regular_file(path):
            raise _unavailable()
        try:
            documents.append(path.read_bytes())
        except OSError:
            raise _unavailable() from None
    if not documents:
        raise _unavailable()
    return tuple(documents)


def generate_synthea_package(config: SyntheaBackendConfig) -> SyntheaBackendResult:
    """Run the external bridge and promote one exact-schema synthetic package."""

    if not isinstance(config, SyntheaBackendConfig):
        raise _unavailable()
    if config.output.exists() or config.output.is_symlink():
        raise FileExistsError("output path already exists")
    repository_root = Path(__file__).resolve().parents[1]
    descriptor_path = config.descriptor_path or repository_root / "datapackage.json"
    overlay_source = Path(__file__).resolve().parent / "synthea" / "overlay"
    module_path = _module_path()
    try:
        verify_synthea_checkout(config.synthea_root)
        if not _regular_file(module_path):
            raise _unavailable()
        module_sha256 = hashlib.sha256(module_path.read_bytes()).hexdigest()
        overlay_sha256 = overlay_digest(overlay_source)
        descriptor = load_descriptor(descriptor_path)
        with tempfile.TemporaryDirectory(prefix="ppoc-synthea-backend-") as temporary:
            staging = Path(temporary)
            checkout = staging / "checkout"
            overlay = staging / "overlay"
            copy_checkout_tree(config.synthea_root, checkout)
            copy_overlay_tree(overlay_source, overlay)
            fhir_root = invoke_synthea(config, work_root=checkout, overlay_dir=overlay / "modules")
            patients = parse_fhir_documents(_read_fhir_documents(fhir_root))
            _validate_pediatric_ages(patients, config.reference_date)
            projection = project_fhir_patients(patients, descriptor, seed=config.seed)
            if projection.patient_count != config.patient_count:
                raise _unavailable()
            runtime = build_development_runtime(repository_root)
            configuration_sha256 = _configuration_digest(
                config,
                module_sha256=module_sha256,
                overlay_sha256=overlay_sha256,
            )
            package = export_exact_schema_package(
                descriptor,
                projection.base_rows,
                config.output,
                metadata=PackageExportMetadata(
                    profile=SYNTHEA_PROFILE,
                    seed=config.seed,
                    reference_time=config.reference_time,
                    reference_id=runtime.reference.reference_id,
                    reference_sha256=runtime.reference.source_sha256,
                    configuration_sha256=configuration_sha256,
                    software_revision=config.software_revision,
                    engine="synthea",
                ),
                derivation_oracle=runtime.derivation_oracle,
                derivation_binding=runtime.derivation_binding,
            )
            report = SyntheaBackendReport(
                report_version=REPORT_VERSION,
                engine_revision=SYNTHEA_REVISION,
                module_sha256=module_sha256,
                overlay_sha256=overlay_sha256,
                configuration_sha256=configuration_sha256,
                requested_patient_count=config.patient_count,
                generated_patient_count=projection.patient_count,
                healthy_count=projection.patient_count - projection.ghd_count,
                ghd_count=projection.ghd_count,
                visit_count=projection.visit_count,
                height_observation_count=projection.height_observation_count,
                weight_observation_count=projection.weight_observation_count,
                bmi_observation_count=projection.bmi_observation_count,
                head_observation_count=projection.head_observation_count,
                min_age_days=projection.min_age_days,
                max_age_days=projection.max_age_days,
                status="GENERATED_TEST_ONLY",
                mean_age_days=projection.mean_age_days,
            )
            return SyntheaBackendResult(package=package, report=report)
    except FileExistsError:
        raise
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:  # noqa: BLE001 - public backend failures are fixed and redacted.
        raise _unavailable() from None


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the opt-in Synthea development backend")
    parser.add_argument("--synthea-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--patients", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--java-home", type=Path, default=None)
    parser.add_argument("--descriptor", type=Path, default=None)
    parser.add_argument("--reference-time", default="2026-09-01T00:00:00Z")
    parser.add_argument("--software-revision", default=BACKEND_VERSION)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("--allow-gradle-network", action="store_true")
    try:
        args = parser.parse_args(argv)
        result = generate_synthea_package(
            SyntheaBackendConfig(
                synthea_root=args.synthea_root,
                output=args.output,
                patient_count=args.patients,
                seed=args.seed,
                java_home=args.java_home,
                descriptor_path=args.descriptor,
                reference_time=args.reference_time,
                software_revision=args.software_revision,
                timeout_seconds=args.timeout_seconds,
                allow_gradle_network=args.allow_gradle_network,
            )
        )
        print(result.package)
        print(result.report.to_json_bytes().decode("ascii"), end="")
    except FileExistsError:
        raise SystemExit(BACKEND_ERROR) from None
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:  # noqa: BLE001 - public CLI failures are fixed and redacted.
        raise SystemExit(BACKEND_ERROR) from None


if __name__ == "__main__":
    main()
