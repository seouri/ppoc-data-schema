import copy
import json
from pathlib import Path

import pytest

from synthetic.derivation_parity import (
    DerivationImplementation,
    DerivationParityPolicy,
    DerivationParityStatus,
    validate_derivation_parity,
)

ROOT = Path(__file__).resolve().parents[2]


def descriptor():
    return json.loads((ROOT / "datapackage.json").read_text(encoding="utf-8"))


def field_specs(package, resource_name):
    return next(item for item in package["resources"] if item["name"] == resource_name)["schema"]["fields"]


def row(package, resource_name, **overrides):
    values = {}
    for spec in field_specs(package, resource_name):
        constraints = spec.get("constraints", {})
        if spec["type"] in {"integer", "number"}:
            value = 0
        elif constraints.get("required") and constraints.get("enum"):
            value = constraints["enum"][0]
        else:
            value = ""
        values[spec["name"]] = value
    values.update(overrides)
    return values


def policy(**overrides):
    values = {
        "policy_id": "parity-policy",
        "policy_version": "v1",
        "minimum_patient_rows": 1,
        "minimum_visit_rows": 1,
        "deterministic_tolerance": 0.001,
        "reference_tolerance": 0.01,
    }
    values.update(overrides)
    return DerivationParityPolicy(**values)


def implementation(name):
    return DerivationImplementation(name, "a" * 64, True)


def fixtures():
    package = descriptor()
    patient = row(
        package,
        "patients",
        patient_id="fictional-person",
        sex="F",
        ethnicity="Choose not to Answer",
        race_1="Unknown",
    )
    visits = [
        row(
            package,
            "visits",
            patient_id="fictional-person",
            visit_id="fictional-visit-one",
            age_in_days=730,
            encounter_type="Office Visit",
            orig_enc_source_Epic_yn="Y",
            weight_oz=70.548,
            height_in=20,
            head_circ_cm=45,
            BMI=17,
            bmi_percentile=50,
            enc_diag_1="E10.9",
        ),
        row(
            package,
            "visits",
            patient_id="fictional-person",
            visit_id="fictional-visit-two",
            age_in_days=800,
            encounter_type="Office Visit",
            orig_enc_source_Epic_yn="Y",
            weight_oz=105.822,
            height_in=24,
            head_circ_cm=46,
            BMI=17,
            bmi_percentile=50,
        ),
    ]
    base = {
        "patients": [patient],
        "visits": visits,
        "labs": [],
        "medications": [],
        "problem_list": [],
        "referrals": [],
    }
    augmented_visits = []
    for visit in visits:
        age = visit["age_in_days"]
        weight = visit["weight_oz"] / 35.274
        height = round(visit["height_in"] * 2.54, 3)
        bmi = "" if age / 30.4375 < 24 else weight / (height / 100) ** 2
        augmented_visits.append(
            row(
                package,
                "visits_augmented",
                patient_id=visit["patient_id"],
                visit_id=visit["visit_id"],
                sex="F",
                ethnicity="",
                race_1="",
                age_in_days=age,
                age_in_months=round(age / 30.4375, 2),
                age_in_years=round(age / 365.25, 3),
                weight_oz=visit["weight_oz"],
                weight_kg=weight,
                height_in=visit["height_in"],
                height_cm=height,
                head_circ_cm=visit["head_circ_cm"],
                bmi=bmi,
                bmi_percentile=50,
                bmi_category="normal",
                weight_z_score=0,
                height_z_score=0,
                bmi_z_score=0,
                head_circ_z_score=0,
                weight_for_length_z_score=0,
                weight_for_stature_z_score=0,
                weight_percentile=50,
                height_percentile=50,
                head_circ_percentile=50,
                weight_for_length_percentile=50,
                weight_for_stature_percentile=50,
                height_velocity_percentile=50,
                height_velocity_percentile_ep=50,
                height_velocity_percentile_ap=50,
                height_velocity_percentile_lp=50,
                stunting_flag=0,
                wasting_flag=0,
                underweight_flag=0,
                obesity_flag=0,
                encounter_type=visit["encounter_type"],
                orig_enc_source_Epic_yn=visit["orig_enc_source_Epic_yn"],
                **{f"enc_diag_{index}": visit[f"enc_diag_{index}"] for index in range(1, 34)},
            )
        )
    summaries = {}
    for metric in (
        "weight_z_score",
        "height_z_score",
        "bmi_z_score",
        "head_circ_z_score",
        "weight_for_length_z_score",
        "weight_for_stature_z_score",
    ):
        summaries |= {
            f"count_{metric}": 2,
            f"mean_{metric}": 0,
            f"std_{metric}": 0,
            f"min_{metric}": 0,
            f"max_{metric}": 0,
        }
    augmented_patient = row(
        package,
        "patients_augmented",
        patient_id="fictional-person",
        sex="F",
        ethnicity="",
        race_1="",
        healthy_flag=0,
        chronic_dx_flag=0,
        growth_dx_flag=1,
        ever_stunting_flag=0,
        ever_wasting_flag=0,
        ever_underweight_flag=0,
        ever_obesity_flag=0,
        visits_count=2,
        visits_count_pre_dx=0,
        min_visit_age_days=730,
        max_visit_age_days=800,
        visits_span_days=70,
        dx_age_years=round(730 / 365.25, 3),
        dx_age_years_e10=round(730 / 365.25, 3),
        **{
            f"dx_age_years_{suffix}": ""
            for suffix in (
                "e03_9", "e22_0", "e23_0", "e23_6", "e24", "e30_0", "e30_1", "e34_3",
                "e34_4", "e72_11", "k50", "k51", "k90_0", "n18", "n25_0", "p04_3", "p05",
                "p07", "p70", "p92_6", "q77", "q78_0", "q78_1", "q87_1", "q87_2", "q87_3",
                "q87_4", "q90", "q96", "q98_0", "q98_4", "q98_5",
            )
        },
        **summaries,
    )
    augmented = {"patients_augmented": [augmented_patient], "visits_augmented": augmented_visits}
    return package, base, copy.deepcopy(augmented), copy.deepcopy(augmented)


def evaluate(package, base, candidate_rows, reference_rows, **policy_overrides):
    return validate_derivation_parity(
        base,
        candidate_rows,
        reference_rows,
        package,
        candidate=implementation("candidate"),
        reference=implementation("reference"),
        policy=policy(**policy_overrides),
    )


def check(report, name):
    return next(item for item in report.checks if item.name == name)


def test_valid_fictional_rows_pass_deterministically_without_mutating_inputs():
    package, base, candidate_rows, reference_rows = fixtures()
    before = copy.deepcopy((base, candidate_rows, reference_rows, package))
    first = evaluate(package, base, candidate_rows, reference_rows)
    second = evaluate(package, base, candidate_rows, reference_rows)
    assert first.status is DerivationParityStatus.PASS
    assert first.to_json_bytes() == second.to_json_bytes()
    assert (base, candidate_rows, reference_rows, package) == before


@pytest.mark.parametrize(
    ("resource", "field", "value"),
    [
        ("visits_augmented", "weight_kg", 3.0),
        ("visits_augmented", "bmi_category", "obese"),
        ("patients_augmented", "healthy_flag", 1),
    ],
)
def test_candidate_field_mismatches_fail_and_are_aggregate_only(resource, field, value):
    package, base, candidate_rows, reference_rows = fixtures()
    candidate_rows[resource][0][field] = value
    report = evaluate(package, base, candidate_rows, reference_rows)
    assert report.status is DerivationParityStatus.FAIL
    parity = check(report, "reference_field_parity")
    assert parity.status is DerivationParityStatus.FAIL
    assert parity.compared_count == 251
    assert parity.mismatch_count >= 1
    assert "fictional" not in repr(report).lower()
    assert "fictional" not in report.to_json_bytes().decode()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda package, base, candidate, reference: candidate["visits_augmented"].pop(),
        lambda package, base, candidate, reference: candidate["visits_augmented"].append(copy.deepcopy(candidate["visits_augmented"][0])),
        lambda package, base, candidate, reference: candidate["patients_augmented"][0].update({"unknown": "x"}),
        lambda package, base, candidate, reference: candidate["visits_augmented"][0].__setitem__("height_percentile", 101),
    ],
)
def test_structural_invalidity_fails_closed(mutate):
    package, base, candidate_rows, reference_rows = fixtures()
    mutate(package, base, candidate_rows, reference_rows)
    report = evaluate(package, base, candidate_rows, reference_rows, minimum_visit_rows=3)
    assert report.status is DerivationParityStatus.FAIL
    assert any(item.reason_code == "STRUCTURAL_INVALID" for item in report.checks)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda package, base, candidate, reference: (
            base["visits"][0].__setitem__("weight_oz", ""),
            candidate["visits_augmented"][0].__setitem__("weight_oz", ""),
            reference["visits_augmented"][0].__setitem__("weight_oz", ""),
            candidate["visits_augmented"][0].__setitem__("weight_kg", ""),
            reference["visits_augmented"][0].__setitem__("weight_kg", ""),
        ),
    ],
)
def test_missing_deterministic_evidence_is_unevaluable(mutate):
    package, base, candidate_rows, reference_rows = fixtures()
    mutate(package, base, candidate_rows, reference_rows)
    report = evaluate(package, base, candidate_rows, reference_rows)
    assert report.status is DerivationParityStatus.UNEVALUABLE
    assert any(item.status is DerivationParityStatus.UNEVALUABLE for item in report.checks)


def test_underpowered_support_is_unevaluable():
    package, base, candidate_rows, reference_rows = fixtures()
    report = evaluate(package, base, candidate_rows, reference_rows, minimum_patient_rows=2)
    assert report.status is DerivationParityStatus.UNEVALUABLE
    assert check(report, "support").status is DerivationParityStatus.UNEVALUABLE


def test_blank_diagnosis_slots_do_not_create_diagnosis_age_summaries():
    package, base, candidate_rows, reference_rows = fixtures()
    for rows in (base["visits"], candidate_rows["visits_augmented"], reference_rows["visits_augmented"]):
        rows[0]["enc_diag_1"] = ""
    for rows in (candidate_rows["patients_augmented"], reference_rows["patients_augmented"]):
        rows[0].update(
            {
                "healthy_flag": 1,
                "growth_dx_flag": 0,
                "visits_count_pre_dx": 2,
                "dx_age_years": "",
                "dx_age_years_e10": "",
            }
        )
    assert evaluate(package, base, candidate_rows, reference_rows).status is DerivationParityStatus.PASS


def test_bmi_gating_uses_base_age_not_candidate_age_conversion():
    package, base, candidate_rows, reference_rows = fixtures()
    candidate_rows["visits_augmented"][1].update({"age_in_months": 0, "bmi": ""})
    report = evaluate(package, base, candidate_rows, reference_rows)
    assert check(report, "deterministic_bmi").status is DerivationParityStatus.FAIL


@pytest.mark.parametrize(
    "mutate",
    [
        lambda package, base, candidate, reference: package["resources"].reverse(),
        lambda package, base, candidate, reference: package["resources"][0]["schema"]["fields"].reverse(),
        lambda package, base, candidate, reference: candidate["visits_augmented"][0].__setitem__("age_in_months", 0),
        lambda package, base, candidate, reference: candidate["visits_augmented"][1].__setitem__("height_cm", 0),
        lambda package, base, candidate, reference: candidate["visits_augmented"][1].__setitem__("bmi", ""),
        lambda package, base, candidate, reference: candidate["patients_augmented"][0].__setitem__("visits_span_days", 0),
        lambda package, base, candidate, reference: candidate["patients_augmented"][0].__setitem__("dx_age_years_e10", 0),
        lambda package, base, candidate, reference: candidate["patients_augmented"][0].__setitem__("mean_weight_z_score", 1),
        lambda package, base, candidate, reference: candidate["visits_augmented"][0].__setitem__("stunting_flag", 1),
    ],
)
def test_declared_deterministic_relationships_fail_when_contradicted(mutate):
    package, base, candidate_rows, reference_rows = fixtures()
    mutate(package, base, candidate_rows, reference_rows)
    assert evaluate(package, base, candidate_rows, reference_rows).status is DerivationParityStatus.FAIL


def test_projection_and_every_augmented_field_are_checked():
    package, base, candidate_rows, reference_rows = fixtures()
    for resource in ("patients_augmented", "visits_augmented"):
        for field in candidate_rows[resource][0]:
            original = candidate_rows[resource][0][field]
            if field in {"patient_id", "visit_id", "sex", "ethnicity", "race_1", "encounter_type", "orig_enc_source_Epic_yn"}:
                continue
            spec = next(item for item in field_specs(package, resource) if item["name"] == field)
            if spec["type"] in {"integer", "number"}:
                if spec.get("constraints", {}).get("enum") == [0, 1]:
                    candidate_rows[resource][0][field] = 1 - original
                else:
                    candidate_rows[resource][0][field] = 1 if original in {0, ""} else original + 1
            elif field.startswith("race_"):
                candidate_rows[resource][0][field] = "White"
            elif spec.get("constraints", {}).get("enum"):
                candidate_rows[resource][0][field] = next(
                    value for value in spec["constraints"]["enum"] if value != original
                )
            else:
                candidate_rows[resource][0][field] = "changed"
            report = evaluate(package, base, candidate_rows, reference_rows)
            assert check(report, "reference_field_parity").mismatch_count >= 1, (resource, field)
            candidate_rows[resource][0][field] = original
    candidate_rows["visits_augmented"][0]["ethnicity"] = "Not Hispanic or Latino"
    assert evaluate(package, base, candidate_rows, reference_rows).status is DerivationParityStatus.FAIL
