from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from scripts.synthea_backend import (
    BACKEND_ERROR,
    GROWTH_OVERLAY_ID,
    REPORT_VERSION,
    SyntheaBackendReport,
    _validate_pediatric_ages,
    parse_fhir_documents,
    project_fhir_patients,
)
from synthetic.schema_contract import load_descriptor

ROOT = Path(__file__).resolve().parents[2]
DESCRIPTOR = load_descriptor(ROOT / "datapackage.json")


def _quantity(code: str, value: float, unit: str, *, encounter: str, date: str) -> dict[str, object]:
    return {
        "resourceType": "Observation",
        "id": f"obs-{code}-{date}",
        "subject": {"reference": "Patient/p-source"},
        "encounter": {"reference": f"Encounter/{encounter}"},
        "effectiveDateTime": f"{date}T12:00:00Z",
        "code": {"coding": [{"system": "http://loinc.org", "code": code}]},
        "valueQuantity": {"value": value, "unit": unit},
    }


def _fixture_bundle() -> dict[str, object]:
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "p-source",
                    "gender": "female",
                    "birthDate": "2018-01-01",
                    "extension": [
                        {
                            "url": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-race",
                            "extension": [
                                {"url": "text", "valueString": "White"},
                            ],
                        },
                        {
                            "url": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity",
                            "extension": [
                                {"url": "text", "valueString": "Not Hispanic or Latino"},
                            ],
                        },
                    ],
                }
            },
            {
                "resource": {
                    "resourceType": "Encounter",
                    "id": "e-1",
                    "subject": {"reference": "Patient/p-source"},
                    "period": {"start": "2019-01-01T12:00:00Z"},
                }
            },
            {
                "resource": {
                    "resourceType": "Encounter",
                    "id": "e-2",
                    "subject": {"reference": "Patient/p-source"},
                    "period": {"start": "2020-01-01T12:00:00Z"},
                }
            },
            {"resource": _quantity("8302-2", 80.0, "cm", encounter="e-1", date="2019-01-01")},
            {"resource": _quantity("29463-7", 10.0, "kg", encounter="e-1", date="2019-01-01")},
            {"resource": _quantity("9843-4", 48.0, "cm", encounter="e-1", date="2019-01-01")},
            {"resource": _quantity("8302-2", 88.0, "cm", encounter="e-2", date="2020-01-01")},
            {"resource": _quantity("29463-7", 13.0, "kg", encounter="e-2", date="2020-01-01")},
            {
                "resource": {
                    "resourceType": "Condition",
                    "id": "condition-source",
                    "subject": {"reference": "Patient/p-source"},
                    "encounter": {"reference": "Encounter/e-2"},
                    "onsetDateTime": "2020-01-01T12:00:00Z",
                    "code": {
                        "coding": [
                            {"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "E23.0"}
                        ]
                    },
                }
            },
        ],
    }


def test_parser_projects_exact_schema_rows_and_discards_source_identifiers() -> None:
    patients = parse_fhir_documents([json.dumps(_fixture_bundle()).encode("utf-8")])
    projection = project_fhir_patients(patients, DESCRIPTOR, seed=11)

    assert tuple(projection.base_rows) == (
        "patients",
        "visits",
        "labs",
        "medications",
        "problem_list",
        "referrals",
    )
    patient = projection.base_rows["patients"][0]
    assert patient["patient_id"].startswith("syn-")
    assert patient["patient_id"] != "p-source"
    assert patient["sex"] == "F"
    assert patient["ethnicity"] == "Not Hispanic or Latino"
    assert patient["race_1"] == "White"
    assert all(patient[f"race_{index}"] == "Unknown" for index in range(2, 9))

    visits = projection.base_rows["visits"]
    assert len(visits) == 2
    assert [row["age_in_days"] for row in visits] == [365, 730]
    assert visits[0]["height_in"] == pytest.approx(80 / 2.54)
    assert visits[0]["weight_oz"] == pytest.approx(10 * 35.274)
    assert visits[0]["head_circ_cm"] == 48.0
    assert visits[1]["BMI"] == pytest.approx(13 / (0.88**2))
    assert visits[1]["enc_diag_1"] == "E23.0"
    assert all("source" not in value for row in visits for value in row.values() if isinstance(value, str))


def test_ghd_overlay_is_monotone_bmi_consistent_and_healthy_is_unchanged() -> None:
    patients = parse_fhir_documents([json.dumps(_fixture_bundle()).encode("utf-8")])
    projection = project_fhir_patients(patients, DESCRIPTOR, seed=11)

    assert projection.growth_overlay_id == GROWTH_OVERLAY_ID
    assert projection.ghd_count == 1
    first, second = projection.base_rows["visits"]
    assert second["height_in"] / first["height_in"] > 1
    height_cm = second["height_in"] * 2.54
    weight_kg = second["weight_oz"] / 35.274
    assert second["BMI"] == pytest.approx(weight_kg / (height_cm / 100) ** 2)
    assert projection.height_observation_count == 2
    assert projection.weight_observation_count == 2


def test_parser_accepts_transaction_entries_and_rejects_duplicate_or_invalid_values() -> None:
    bundle = _fixture_bundle()
    transaction = dict(bundle)
    transaction["type"] = "transaction"
    assert len(parse_fhir_documents([json.dumps(transaction).encode("utf-8")])) == 1

    duplicate = b'{"resourceType":"Patient","id":"x","id":"y"}'
    with pytest.raises(ValueError, match=BACKEND_ERROR):
        parse_fhir_documents([duplicate])

    invalid = _quantity("8302-2", -1, "cm", encounter="e-1", date="2019-01-01")
    with pytest.raises(ValueError, match=BACKEND_ERROR):
        parse_fhir_documents([json.dumps(invalid).encode("utf-8")])


def test_parser_accepts_synthea_urn_uuid_references() -> None:
    bundle = _fixture_bundle()
    for entry in bundle["entry"]:
        resource = entry["resource"]
        if not isinstance(resource, dict):
            continue
        subject = resource.get("subject")
        if isinstance(subject, dict):
            subject["reference"] = "urn:uuid:p-source"
        encounter = resource.get("encounter")
        if isinstance(encounter, dict):
            encounter_id = encounter["reference"].split("/", 1)[-1]
            encounter["reference"] = f"urn:uuid:{encounter_id}"
    assert len(parse_fhir_documents([json.dumps(bundle).encode("utf-8")])) == 1


def test_projection_requires_anthropometry_and_rejects_pre_birth_observations() -> None:
    patient = {
        "resourceType": "Patient",
        "id": "p-only",
        "gender": "unknown",
        "birthDate": "2020-01-01",
    }
    parsed = parse_fhir_documents([json.dumps(patient).encode("utf-8")])
    with pytest.raises(ValueError, match=BACKEND_ERROR):
        project_fhir_patients(parsed, DESCRIPTOR, seed=1)

    bad = _fixture_bundle()
    for item in bad["entry"]:
        resource = item.get("resource")
        if isinstance(resource, dict) and resource.get("id") == "obs-8302-2-2019-01-01":
            resource["effectiveDateTime"] = "2017-01-01T12:00:00Z"
            break
    with pytest.raises(ValueError, match=BACKEND_ERROR):
        project_fhir_patients(
            parse_fhir_documents([json.dumps(bad).encode("utf-8")]), DESCRIPTOR, seed=1
        )


def test_backend_enforces_the_requested_zero_to_eighteen_year_age_range() -> None:
    patient = parse_fhir_documents([json.dumps(_fixture_bundle()).encode("utf-8")])[0]
    with pytest.raises(ValueError, match=BACKEND_ERROR):
        _validate_pediatric_ages(
            [replace(patient, birth_date=date(1990, 1, 1))], date(2026, 9, 1)
        )
    with pytest.raises(ValueError, match=BACKEND_ERROR):
        _validate_pediatric_ages(
            [replace(patient, birth_date=date(2026, 9, 2))], date(2026, 9, 1)
        )


def test_aggregate_report_is_canonical_and_contains_no_paths_or_records() -> None:
    report = SyntheaBackendReport(
        report_version=REPORT_VERSION,
        engine_revision="d9d07a6eef91ee5144293b42ab64224d84d124f8",
        module_sha256="a" * 64,
        overlay_sha256="b" * 64,
        configuration_sha256="c" * 64,
        requested_patient_count=2,
        generated_patient_count=2,
        healthy_count=1,
        ghd_count=1,
        visit_count=4,
        height_observation_count=4,
        weight_observation_count=4,
        bmi_observation_count=4,
        head_observation_count=2,
        min_age_days=365,
        max_age_days=730,
        status="GENERATED_TEST_ONLY",
        mean_age_days=547.5,
    )
    encoded = report.to_json_bytes()
    assert json.loads(encoded) == report.to_mapping()
    assert encoded.endswith(b"\n")
    text = encoded.decode("ascii")
    assert "/" not in text
    assert "p-source" not in text
    assert "patient_id" not in text
