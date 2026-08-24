#!/usr/bin/env python3
"""Build and self-check the tabular data package."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "datapackage.json"


def field(
    name: str,
    field_type: str,
    description: str,
    *,
    required: bool = False,
    constraints: dict[str, Any] | None = None,
    **metadata: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": name,
        "type": field_type,
        "description": description,
    }
    field_constraints = dict(constraints or {})
    if required:
        field_constraints["required"] = True
    if field_constraints:
        result["constraints"] = field_constraints
    result.update(metadata)
    return result


def identifier(name: str, entity: str) -> dict[str, Any]:
    return field(
        name,
        "string",
        f"Blinded unique identifier for the {entity}.",
        required=True,
        **{"x-deidentified": True},
    )


SEX_VALUES = ["F", "M", "U"]
ETHNICITY_VALUES = [
    "Not Hispanic or Latino",
    "Hispanic or Latino",
    "Choose not to Answer",
    "Unknown",
    "Unable to collect",
    "Patient does not know",
]
RACE_VALUES = [
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
]
INFORMATIVE_ETHNICITY_VALUES = ETHNICITY_VALUES[:2]
INFORMATIVE_RACE_VALUES = [
    value
    for value in RACE_VALUES
    if value
    not in {
        "Choose not to answer",
        "Patient does not know",
        "Unable to collect",
        "Unknown",
    }
]


def categories(counts: dict[Any, int] | list[tuple[Any, int]]) -> list[dict[str, Any]]:
    """Observed value frequencies, dropping values absent from the column."""
    items = counts.items() if isinstance(counts, dict) else counts
    return [{"value": value, "count": count} for value, count in items if count]


# Value frequencies below are transcribed from the docs/ snapshot summaries; see
# the package-level x-statisticsSource note. validate_package cross-checks every
# distribution against its row and missing-value counts.
SEX_COUNTS = {"F": 122883, "M": 127699, "U": 6}
ETHNICITY_COUNTS = {
    "Not Hispanic or Latino": 170594,
    "Hispanic or Latino": 28549,
    "Choose not to Answer": 24566,
    "Unknown": 20834,
    "Unable to collect": 450,
    "Patient does not know": 131,
}
ETHNICITY_MISSING = 5464
# Counts per race_1 ... race_8 column.
RACE_COUNTS = {
    "American Indian or Alaska Native": (625, 71, 15, 0, 0, 0, 0, 0),
    "Another Race": (15950, 1137, 63, 2, 2, 1, 0, 0),
    "Asian": (15661, 566, 15, 2, 0, 0, 0, 0),
    "Black or African American": (12162, 835, 31, 0, 0, 0, 0, 0),
    "Choose not to answer": (17534, 516, 19, 1, 0, 0, 0, 0),
    "Middle Eastern or Northern African": (512, 87, 7, 0, 0, 0, 0, 0),
    "Native Hawaiian or Other Pacific Islander": (248, 86, 10, 6, 1, 0, 0, 0),
    "Patient does not know": (126, 1, 0, 0, 0, 0, 0, 0),
    "Unable to collect": (492, 11, 0, 0, 0, 0, 0, 0),
    "Unknown": (23085, 1554, 59, 0, 0, 1, 1, 0),
    "White": (155375, 8327, 402, 27, 3, 1, 1, 1),
}
RACE_MISSING = (8818, 237397, 249967, 250550, 250582, 250585, 250586, 250587)


PATIENT_FIELDS = [
    identifier("patient_id", "patient"),
    field(
        "sex",
        "string",
        "Recorded patient sex; U means unknown.",
        required=True,
        constraints={"enum": SEX_VALUES},
        **{"x-categories": categories(SEX_COUNTS)},
    ),
    field(
        "ethnicity",
        "string",
        "Recorded patient ethnicity; non-response is retained as a category in the base file.",
        constraints={"enum": ETHNICITY_VALUES},
        **{"x-categories": categories(ETHNICITY_COUNTS), "x-missingCount": ETHNICITY_MISSING},
    ),
]
PATIENT_FIELDS.extend(
    field(
        f"race_{index}",
        "string",
        f"Recorded race category at position {index}; blank when no category is present.",
        constraints={"enum": RACE_VALUES},
        **{
            "x-categories": categories(
                [(value, counts[index - 1]) for value, counts in RACE_COUNTS.items()]
            ),
            "x-missingCount": RACE_MISSING[index - 1],
        },
    )
    for index in range(1, 9)
)


def age_field(
    name: str,
    event: str,
    *,
    required: bool = False,
    constraints: dict[str, Any] | None = None,
    **metadata: Any,
) -> dict[str, Any]:
    return field(
        name,
        "integer",
        f"Patient age in days at {event}, replacing the absolute date for de-identification.",
        required=required,
        constraints=constraints,
        **{"x-unit": "day", "x-deidentifiedDate": True, **metadata},
    )


ENCOUNTER_TYPE_COUNTS = {
    "Abstract": 3672,
    "Clinical Support": 15347,
    "Consult": 32355,
    "Conversion Encounter": 32007,
    "Documentation": 13107,
    "ED": 1,
    "Episode Changes": 2,
    "Erroneous Encounter": 555,
    "Erroneous Telephone Encounter": 2,
    "Evaluation": 143,
    "External Contact": 211,
    "Flu": 2104,
    "Follow-Up": 92370,
    "History": 11,
    "Hospital": 5,
    "Immunization": 11774,
    "Lab": 1351,
    "Lab Requisition": 63,
    "Lactation Consult": 1384,
    "Lactation Encounter": 1337,
    "Letter (Out)": 18,
    "Medication Management": 4345,
    "New Patient": 11410,
    "Newborn": 31142,
    "Nurse Only": 3786,
    "Nutrition": 5406,
    "Office Visit": 4725643,
    "Ophth Exam": 11,
    "Orders Only": 273,
    "OurPractice Advisory": 1,
    "Patient Care Review": 3,
    "Patient Message": 209,
    "Pre-op/Pre-procedure Orders": 575,
    "Procedure visit": 678,
    "Refill": 12,
    "Routine Prenatal": 4,
    "Scanned Document": 23,
    "Sick": 580991,
    "Telemedicine": 25658,
    "Telephone": 22053,
    "Transcribe Orders": 4,
    "Treatment": 1,
    "Walk-In": 79679,
    "Weight Check": 16295,
    "Well Visit (Conv.)": 778452,
}


VISIT_FIELDS = [
    identifier("patient_id", "patient"),
    identifier("visit_id", "visit"),
    age_field("age_in_days", "the visit", required=True, constraints={"minimum": 1, "maximum": 6571}),
    field(
        "encounter_type",
        "string",
        f"Encounter classification; {len(ENCOUNTER_TYPE_COUNTS)} values occur in the data.",
        required=True,
        constraints={"enum": list(ENCOUNTER_TYPE_COUNTS)},
        **{
            "x-uniqueValueCount": len(ENCOUNTER_TYPE_COUNTS),
            "x-categories": categories(ENCOUNTER_TYPE_COUNTS),
        },
    ),
    field(
        "orig_enc_source_Epic_yn",
        "string",
        "Y when the encounter originated in Epic; N when converted from a legacy EMR.",
        constraints={"enum": ["Y", "N"]},
    ),
    field("weight_oz", "number", "Recorded weight in ounces; may contain outliers.", constraints={"minimum": 0.2, "maximum": 22648}, **{"x-unit": "ounce"}),
    field("height_in", "number", "Recorded height or length in inches; may contain outliers.", constraints={"minimum": 1.18, "maximum": 115}, **{"x-unit": "inch"}),
    field("head_circ_cm", "number", "Recorded head circumference in centimeters; may contain outliers.", constraints={"minimum": 0, "maximum": 505.46}, **{"x-unit": "centimeter"}),
    field(
        "BMI",
        "number",
        "Body mass index recorded by Epic in the base visits file.",
        constraints={"minimum": 0.01, "maximum": 21164.05},
        **{"x-unit": "kg/m2"},
    ),
    field(
        "bmi_percentile",
        "number",
        "BMI-for-age percentile recorded by Epic.",
        constraints={"minimum": 0, "maximum": 100},
        **{"x-unit": "percentile"},
    ),
]
VISIT_FIELDS.extend(
    field(
        f"enc_diag_{index}",
        "string",
        ("Primary or first-listed" if index == 1 else f"Diagnosis position {index}")
        + " encounter diagnosis code.",
        **{"x-codeSystem": "ICD-10-CM"},
    )
    for index in range(1, 34)
)


GROWTH_DIAGNOSES = [
    ("E03.9", "Hypothyroidism, unspecified"),
    ("E10", "Type 1 diabetes mellitus"),
    ("E22.0", "Acromegaly and pituitary gigantism"),
    ("E23.0", "Hypopituitarism"),
    ("E23.6", "Other disorders of pituitary gland"),
    ("E24", "Cushing's syndrome"),
    ("E30.0", "Delayed puberty"),
    ("E30.1", "Precocious puberty"),
    ("E34.3", "Short stature due to endocrine disorder"),
    ("E34.4", "Constitutional tall stature"),
    ("E72.11", "Homocystinuria"),
    ("K50", "Crohn's disease [regional enteritis]"),
    ("K51", "Ulcerative colitis"),
    ("K90.0", "Celiac disease"),
    ("N18", "Chronic kidney disease"),
    ("N25.0", "Renal osteodystrophy"),
    ("P04.3", "Newborn affected by maternal use of alcohol"),
    ("P05", "Slow fetal growth and fetal malnutrition"),
    ("P07", "Short gestation and low birth weight"),
    ("P70", "Transitory newborn carbohydrate-metabolism disorder"),
    ("P92.6", "Failure to thrive in newborn"),
    ("Q77", "Osteochondrodysplasia with defects of growth"),
    ("Q78.0", "Osteogenesis imperfecta"),
    ("Q78.1", "Polyostotic fibrous dysplasia"),
    ("Q87.1", "Congenital syndrome associated with short stature"),
    ("Q87.2", "Congenital syndrome predominantly involving limbs"),
    ("Q87.3", "Congenital syndrome involving early overgrowth"),
    ("Q87.4", "Marfan syndrome"),
    ("Q90", "Down syndrome"),
    ("Q96", "Turner syndrome"),
    ("Q98.0", "Klinefelter syndrome, 47 XXY"),
    ("Q98.4", "Klinefelter syndrome, unspecified"),
    ("Q98.5", "Karyotype 47 XYY"),
]


def binary_flag(name: str, description: str, *, required: bool = True) -> dict[str, Any]:
    return field(
        name,
        "integer",
        description,
        required=required,
        constraints={"enum": [0, 1]},
    )


PATIENT_ROW_COUNT = 250588

PATIENT_AUGMENTED_FIELDS = copy.deepcopy(PATIENT_FIELDS)
PATIENT_AUGMENTED_FIELDS[2]["constraints"]["enum"] = INFORMATIVE_ETHNICITY_VALUES
for race_field in PATIENT_AUGMENTED_FIELDS[3:]:
    race_field["constraints"]["enum"] = INFORMATIVE_RACE_VALUES


def informative_only(entry: dict[str, Any], row_count: int) -> None:
    """Non-informative responses are cleaned to null in the augmented file, so
    the retained categories are the enum members and everything else is missing."""
    kept = [row for row in entry["x-categories"] if row["value"] in entry["constraints"]["enum"]]
    entry["x-categories"] = kept
    entry["x-missingCount"] = row_count - sum(row["count"] for row in kept)


for demographic in PATIENT_AUGMENTED_FIELDS[2:]:
    informative_only(demographic, PATIENT_ROW_COUNT)
PATIENT_AUGMENTED_FIELDS.extend(
    [
        binary_flag("healthy_flag", "1 only when all diagnosis and adverse-growth history flags are 0."),
        binary_flag("chronic_dx_flag", "1 when any visit or problem-list diagnosis is in the chronic diagnosis set."),
        binary_flag("growth_dx_flag", "1 when any visit or problem-list diagnosis starts with a growth-disorder prefix."),
        binary_flag("ever_stunting_flag", "1 when any visit has height_z_score below -2."),
        binary_flag("ever_wasting_flag", "1 when any visit meets the wasting threshold."),
        binary_flag("ever_underweight_flag", "1 when any visit has bmi_percentile below 5."),
        binary_flag("ever_obesity_flag", "1 when any visit has bmi_percentile at least 95."),
        field("visits_count", "integer", "Total recorded visits; 0 for a patient with no visits.", required=True, constraints={"minimum": 0}),
        field("visits_count_pre_dx", "integer", "Visits before the first growth-related diagnosis, or all visits when none exists.", required=True, constraints={"minimum": 0}),
        age_field("min_visit_age_days", "the first recorded visit"),
        age_field("max_visit_age_days", "the last recorded visit"),
        field("visits_span_days", "integer", "Days between first and last visit; null with no visits.", constraints={"minimum": 0}, **{"x-unit": "day"}),
        field("dx_age_years", "number", "Minimum age in years at any growth-related diagnosis.", **{"x-unit": "year"}),
    ]
)
for code, diagnosis_description in GROWTH_DIAGNOSES:
    suffix = code.lower().replace(".", "_")
    PATIENT_AUGMENTED_FIELDS.append(
        field(
            f"dx_age_years_{suffix}",
            "number",
            f"Minimum age in years at a diagnosis starting with {code}: {diagnosis_description}.",
            **{"x-unit": "year", "x-diagnosisPrefix": code, "x-codeSystem": "ICD-10-CM"},
    )
)
for metric in [
    "weight_z_score",
    "height_z_score",
    "bmi_z_score",
    "head_circ_z_score",
    "weight_for_length_z_score",
    "weight_for_stature_z_score",
]:
    PATIENT_AUGMENTED_FIELDS.extend(
        [
            field(f"count_{metric}", "integer", f"Count of non-null visit-level {metric} values.", constraints={"minimum": 0}),
            field(f"mean_{metric}", "number", f"Mean visit-level {metric}."),
            field(f"std_{metric}", "number", f"Standard deviation of visit-level {metric} values.", constraints={"minimum": 0}),
            field(f"min_{metric}", "number", f"Minimum visit-level {metric}."),
            field(f"max_{metric}", "number", f"Maximum visit-level {metric}."),
        ]
    )


VISIT_BY_NAME = {item["name"]: item for item in VISIT_FIELDS}


def copy_visit(name: str) -> dict[str, Any]:
    return copy.deepcopy(VISIT_BY_NAME[name])


VISIT_AUGMENTED_FIELDS = [
    copy_visit("patient_id"),
    copy_visit("visit_id"),
    field("sex", "string", "Recorded patient sex joined from patients.csv.", required=True, constraints={"enum": SEX_VALUES}),
    field("ethnicity", "string", "Informative ethnicity joined from patients.csv; non-response values are null.", constraints={"enum": INFORMATIVE_ETHNICITY_VALUES}),
    field("race_1", "string", "Informative primary race joined from patients.csv; non-response values are null.", constraints={"enum": INFORMATIVE_RACE_VALUES}),
    copy_visit("age_in_days"),
    field("age_in_months", "number", "age_in_days divided by 30.4375 and rounded to 2 decimals.", **{"x-unit": "month", "x-derivedFrom": ["age_in_days"], "x-decimalPlaces": 2}),
    field("age_in_years", "number", "age_in_days divided by 365.25 and rounded to 3 decimals.", **{"x-unit": "year", "x-derivedFrom": ["age_in_days"], "x-decimalPlaces": 3}),
    copy_visit("weight_oz"),
    field("weight_kg", "number", "Weight converted from ounces and set to null when biologically implausible.", **{"x-unit": "kilogram", "x-derivedFrom": ["weight_oz"], "x-conversionFactor": "1 kg = 35.274 oz", "x-bivRule": "null when abs(weight_z_score) > 5"}),
    binary_flag("weight_outlier_flag", "1 when the Harrall algorithm flags weight as a statistical outlier.", required=False),
    copy_visit("height_in"),
    field("height_cm", "number", "Height converted from inches and set to null when biologically implausible.", **{"x-unit": "centimeter", "x-derivedFrom": ["height_in"], "x-conversionFactor": "1 in = 2.54 cm", "x-decimalPlaces": 3, "x-bivRule": "null when height_z_score < -5 or height_z_score > 3"}),
    binary_flag("height_outlier_flag", "1 when the Harrall algorithm flags height as a statistical outlier.", required=False),
    copy_visit("head_circ_cm"),
]

augmented_bmi = copy_visit("BMI")
augmented_bmi["name"] = "bmi"
augmented_bmi["description"] = "BMI recalculated from filtered weight_kg and height_cm for ages of at least 24 months."
# The recalculated value is not the Epic-recorded BMI, so the observed range of
# the base column does not carry over.
augmented_bmi.pop("constraints", None)
augmented_bmi["x-derivedFrom"] = ["weight_kg", "height_cm", "age_in_months"]
augmented_bmi["x-minAgeMonths"] = 24
VISIT_AUGMENTED_FIELDS.append(augmented_bmi)

for name, description, extra in [
    ("weight_z_score", "CDC LMS weight-for-age Z-score", {"x-bivRule": "null when abs(weight_z_score) > 5"}),
    ("height_z_score", "CDC LMS height-for-age Z-score", {"x-bivRule": "null when height_z_score < -5 or height_z_score > 3"}),
    ("bmi_z_score", "CDC LMS BMI-for-age Z-score", {}),
    ("head_circ_z_score", "CDC LMS head-circumference Z-score", {}),
    ("weight_for_length_z_score", "CDC LMS weight-for-length Z-score for heights 45-103.5 cm", {}),
    ("weight_for_stature_z_score", "CDC LMS weight-for-stature Z-score for heights 77-121.5 cm", {}),
]:
    VISIT_AUGMENTED_FIELDS.append(field(name, "number", f"{description}.", **{"x-referenceStandard": "CDC LMS growth reference", **extra}))

for name, description in [
    ("weight_percentile", "Weight-for-age percentile"),
    ("height_percentile", "Height-for-age percentile"),
    ("bmi_percentile", "BMI-for-age percentile recalculated from the CDC LMS Z-score"),
    ("head_circ_percentile", "Head-circumference percentile"),
    ("weight_for_length_percentile", "Weight-for-length percentile"),
    ("weight_for_stature_percentile", "Weight-for-stature percentile"),
]:
    percentile_field = field(name, "number", f"{description}.", constraints={"minimum": 0, "maximum": 100}, **{"x-unit": "percentile"})
    VISIT_AUGMENTED_FIELDS.append(percentile_field)

VISIT_AUGMENTED_FIELDS.extend(
    [
        field(
            "bmi_category",
            "string",
            "CDC BMI classification derived from bmi_percentile.",
            constraints={"enum": ["underweight", "normal", "overweight", "obese", "severe_obesity"]},
            **{"x-derivedFrom": ["bmi_percentile"]},
        ),
        field("weight_velocity", "number", "Longitudinal weight growth rate.", **{"x-unit": "kg/year"}),
        field("height_velocity", "number", "Longitudinal height growth rate.", **{"x-unit": "cm/year"}),
        field("delta_weight_kg", "number", "Weight difference from the reference measurement.", **{"x-unit": "kilogram"}),
        field("delta_age_in_days_weight", "integer", "Age interval used for weight velocity.", constraints={"minimum": 0}, **{"x-unit": "day"}),
        field("delta_height_cm", "number", "Height difference from the reference measurement.", **{"x-unit": "centimeter"}),
        field("delta_age_in_days_height", "integer", "Age interval used for height velocity.", constraints={"minimum": 0}, **{"x-unit": "day"}),
    ]
)
for suffix, onset in [("", "no pubertal-onset adjustment"), ("_ep", "earlier pubertal onset"), ("_ap", "average pubertal onset"), ("_lp", "later pubertal onset")]:
    VISIT_AUGMENTED_FIELDS.append(field(f"height_velocity_z_score{suffix}", "number", f"Height-velocity Z-score with {onset}.", **{"x-decimalPlaces": 4}))
for suffix, onset in [("", "no pubertal-onset adjustment"), ("_ep", "earlier pubertal onset"), ("_ap", "average pubertal onset"), ("_lp", "later pubertal onset")]:
    VISIT_AUGMENTED_FIELDS.append(
        field(
            f"height_velocity_percentile{suffix}",
            "number",
            f"Height-velocity percentile with {onset}.",
            constraints={"minimum": 0, "maximum": 100},
            **{"x-unit": "percentile", "x-decimalPlaces": 2},
        )
    )
VISIT_AUGMENTED_FIELDS.extend(
    [
        binary_flag("stunting_flag", "1 when height_z_score is below -2."),
        binary_flag("wasting_flag", "1 when weight-for-length or weight-for-stature Z-score is below -2."),
        binary_flag("obesity_flag", "1 when bmi_percentile is at least 95."),
        binary_flag("underweight_flag", "1 when bmi_percentile is below 5."),
        copy_visit("encounter_type"),
        copy_visit("orig_enc_source_Epic_yn"),
    ]
)
VISIT_AUGMENTED_FIELDS.extend(copy_visit(f"enc_diag_{index}") for index in range(1, 34))

# Keep the descriptor in the output order after constructing the reusable field
# definitions above.
VISIT_AUGMENTED_ORDER = [
    "patient_id", "visit_id", "sex", "ethnicity", "race_1", "age_in_days",
    "age_in_months", "age_in_years", "weight_oz", "weight_kg",
    "weight_outlier_flag", "delta_weight_kg", "delta_age_in_days_weight",
    "weight_velocity", "weight_z_score", "weight_percentile",
    "weight_for_length_z_score", "weight_for_length_percentile",
    "weight_for_stature_z_score", "weight_for_stature_percentile", "wasting_flag",
    "height_in", "height_cm", "height_outlier_flag", "delta_height_cm",
    "delta_age_in_days_height", "height_velocity", "height_velocity_z_score",
    "height_velocity_z_score_ep", "height_velocity_z_score_ap",
    "height_velocity_z_score_lp", "height_velocity_percentile",
    "height_velocity_percentile_ep", "height_velocity_percentile_ap",
    "height_velocity_percentile_lp", "height_z_score", "height_percentile",
    "stunting_flag", "head_circ_cm", "head_circ_z_score", "head_circ_percentile",
    "bmi", "bmi_z_score", "bmi_percentile", "bmi_category", "underweight_flag",
    "obesity_flag", "encounter_type", "orig_enc_source_Epic_yn",
]
VISIT_AUGMENTED_ORDER.extend(f"enc_diag_{index}" for index in range(1, 34))
VISIT_AUGMENTED_BY_NAME = {item["name"]: item for item in VISIT_AUGMENTED_FIELDS}
if set(VISIT_AUGMENTED_BY_NAME) != set(VISIT_AUGMENTED_ORDER):
    raise ValueError("visits_augmented field definitions do not match output field names")
VISIT_AUGMENTED_FIELDS = [VISIT_AUGMENTED_BY_NAME[name] for name in VISIT_AUGMENTED_ORDER]


RESULT_FLAG_COUNTS = {
    "Abnormal": 704327,
    "High": 513650,
    "Low": 361300,
    "Sensitive": 62794,
    "Resistant": 10278,
    "High Panic": 9744,
    "(NONE)": 5881,
    "Normal": 4273,
    "Panic": 3056,
    "Intermediate": 1704,
    "Low Panic": 1406,
    "Critical": 373,
    "Negative": 188,
    "High Off-Scale": 134,
    "Susceptible-Dose Dependent": 123,
    "Abnormal High": 99,
    "Abnormal Low": 92,
    "Invalid High": 84,
    "Sig Change Up": 68,
    "Positive": 35,
    "Critical High": 23,
    "Low Off-Scale": 17,
    "Critical Low": 13,
    "Class 0: Absent Allergen Specific IgE": 7,
    "Invalid Low": 4,
    "Delta Abnormal High": 4,
    "Class 2: Moderate Level Allergen Specific IgE": 3,
    "In Process": 3,
    "Better": 3,
    "Delta Critical High": 3,
    "Sig Change Down": 2,
    "Class 3: High Level Allergen Specific IgE": 2,
    "Moderately Sensitive": 1,
    "Delta Abnormal Low": 1,
    "Worse": 1,
}


LAB_FIELDS = [
    identifier("patient_id", "patient"),
    field("visit_id", "string", "Associated visit identifier; blank for 805 rows and absent from visits.csv for some otherwise non-null values.", **{"x-deidentified": True, "x-missingCount": 805}),
    identifier("lab_order_id", "lab order"),
    field("result_line_num", "integer", "Sequential result-component line within a lab order.", constraints={"minimum": 1, "maximum": 149}, **{"x-missingCount": 2283186}),
    age_field("lab_order_date_age_in_days", "lab order", required=True, constraints={"minimum": -687, "maximum": 6570}),
    field("lab_procedure_name", "string", "Epic lab procedure name.", **{"x-uniqueValueCount": 3742}),
    field("lab_procedure_description", "string", "Additional procedure description, especially for external labs."),
    age_field("lab_result_date_age_in_days", "lab result", constraints={"minimum": -44378, "maximum": 6570}, **{"x-missingCount": 2283186}),
    field("result_component_name", "string", "Name of the result component; null when no result is available.", **{"x-uniqueValueCount": 12902, "x-missingCount": 2283186}),
    field("result_loinc_code", "string", "LOINC code for the result component when available.", **{"x-codeSystem": "LOINC", "x-uniqueValueCount": 2194, "x-missingCount": 15880579}),
    field("result_value", "string", "Result represented as text; it may be numeric, categorical, or narrative.", **{"x-missingCount": 2494261}),
    field(
        "result_flag",
        "string",
        "HL7 result interpretation flag; blank when unassigned. Both (NONE) and Normal occur, so a flag is not abnormal merely because it differs from (NONE).",
        constraints={"enum": list(RESULT_FLAG_COUNTS)},
        **{
            "x-uniqueValueCount": len(RESULT_FLAG_COUNTS),
            "x-categories": categories(RESULT_FLAG_COUNTS),
            "x-missingCount": 15550985,
        },
    ),
]


MEDICATION_FIELDS = [
    identifier("patient_id", "patient"),
    identifier("visit_id", "visit"),
    identifier("med_record_id", "medication record"),
    age_field("med_order_date_age_in_days", "medication order", required=True, constraints={"minimum": -45, "maximum": 6605}),
    age_field("med_start_date_age_in_days", "medication start", constraints={"minimum": -40149, "maximum": 36581}, **{"x-missingCount": 283066}),
    age_field("med_end_date_age_in_days", "medication end", constraints={"minimum": 0, "maximum": 31105}, **{"x-missingCount": 450340}),
    field(
        "med_record_type",
        "string",
        "Internal for a PPOC-provider order; External for a historical or outside record.",
        required=True,
        constraints={"enum": ["Internal", "External"]},
        **{"x-categories": categories({"Internal": 3250374, "External": 572675})},
    ),
        field("med_simple_generic_name", "string", "Simplified generic medication name.", required=True, **{"x-uniqueValueCount": 1073}),
]


PROBLEM_FIELDS = [
    identifier("patient_id", "patient"),
    identifier("problem_list_id", "problem-list entry"),
    age_field("noted_date_age_in_days", "first problem notation", constraints={"minimum": -44891, "maximum": 6601}, **{"x-missingCount": 7284}),
    age_field("resolved_date_age_in_days", "problem resolution", constraints={"minimum": -84, "maximum": 6605}),
    field("pl_diag", "string", "Problem-list diagnosis code.", required=True, **{"x-codeSystem": "ICD-10-CM", "x-uniqueValueCount": 4739}),
]


REFERRAL_FIELDS = [
    identifier("patient_id", "patient"),
    field("visit_id", "string", "Associated visit identifier; nullable when the referral is not linked to a visit.", **{"x-deidentified": True, "x-missingCount": 24830}),
    identifier("referral_id", "referral"),
    age_field("referral_date_age_in_days", "referral", required=True, constraints={"minimum": 1, "maximum": 6567}),
    field("requested_specialty", "string", "Requested referral specialty; nullable.", **{"x-uniqueValueCount": 119, "x-missingCount": 27452}),
    field(
        "referral_number_of_visits",
        "integer",
        "Authorized or associated visit count; nullable.",
        constraints={"minimum": 1, "maximum": 10},
        **{
            "x-categories": categories({1: 108736, 6: 213345, 3: 608, 5: 476, 10: 60, 4: 1}),
            "x-missingCount": 26601,
        },
    ),
]


def foreign_key(field_name: str, resource: str, reference_field: str) -> dict[str, Any]:
    return {
        "fields": field_name,
        "reference": {"resource": resource, "fields": reference_field},
    }


def resource(
    name: str,
    description: str,
    fields: list[dict[str, Any]],
    row_count: int,
    *,
    path: str | None = None,
    primary_key: str | None = None,
    foreign_keys: list[dict[str, Any]] | None = None,
    encoding: str = "utf-8",
    derived_from: list[str] | None = None,
    **metadata: Any,
) -> dict[str, Any]:
    schema: dict[str, Any] = {"fields": fields, "missingValues": [""]}
    if primary_key:
        schema["primaryKey"] = primary_key
    if foreign_keys:
        schema["foreignKeys"] = foreign_keys
    result: dict[str, Any] = {
        "profile": "tabular-data-resource",
        "name": name,
        "path": path or f"{name}.csv",
        "title": name.replace("_", " ").title(),
        "description": description,
        "x-documentation": f"docs/{name}.md",
        "format": "csv",
        "mediatype": "text/csv",
        "encoding": encoding,
        "dialect": {"header": True, "delimiter": ",", "quoteChar": '"', "doubleQuote": True},
        "schema": schema,
        "x-rowCount": row_count,
        "x-fieldCount": len(fields),
    }
    if derived_from:
        result["x-derivedFrom"] = derived_from
    result.update(metadata)
    return result


VISITS_AUGMENTED_PATH = "visits_augmented-20251209150512.csv"

AUGMENT_COMMAND = "python scripts/augment.py input_dir [--output_dir output] [--output_format {csv,parquet}]"
VISITS_AUGMENTED_GENERATOR = {
    "script": "scripts/augment.py",
    "function": "augment_visits",
    "command": f"{AUGMENT_COMMAND} [--filter_errors|--no_filter_errors]",
    "referenceStandard": "CDC LMS growth reference",
    "outlierAlgorithm": "Harrall",
    "bivFiltering": "enabled by default via --filter_errors; disable with --no_filter_errors",
}
PATIENTS_AUGMENTED_GENERATOR = {
    "script": "scripts/augment.py",
    "function": "augment_patients",
    "command": AUGMENT_COMMAND,
}


RESOURCES = [
    resource(
        "patients",
        "One demographic record per de-identified pediatric patient.",
        PATIENT_FIELDS,
        250588,
        primary_key="patient_id",
        **{"x-uniquePatientCount": 250588},
    ),
    resource(
        "patients_augmented",
        "Patient demographics plus longitudinal diagnosis and growth summaries.",
        PATIENT_AUGMENTED_FIELDS,
        250588,
        primary_key="patient_id",
        foreign_keys=[foreign_key("patient_id", "patients", "patient_id")],
        derived_from=["patients", "visits_augmented", "problem_list"],
        **{
            "x-uniquePatientCount": 250588,
            "x-generatedBy": PATIENTS_AUGMENTED_GENERATOR,
        },
    ),
    resource(
        "visits",
        "One de-identified pediatric encounter with anthropometrics and up to 33 diagnoses per row.",
        VISIT_FIELDS,
        6494473,
        primary_key="visit_id",
        foreign_keys=[foreign_key("patient_id", "patients", "patient_id")],
        **{
            "x-uniquePatientCount": 250588,
            "x-uniqueDiagnosisCodeCount": 8031,
        },
    ),
    resource(
        "visits_augmented",
        "Visit records augmented with demographics, standardized growth metrics, velocities, and clinical flags.",
        VISIT_AUGMENTED_FIELDS,
        6494473,
        path=VISITS_AUGMENTED_PATH,
        primary_key="visit_id",
        foreign_keys=[
            foreign_key("patient_id", "patients", "patient_id"),
            foreign_key("visit_id", "visits", "visit_id"),
        ],
        derived_from=["visits", "patients"],
        **{
            "x-uniquePatientCount": 250588,
            "x-uniqueDiagnosisCodeCount": 8031,
            "x-generatedBy": VISITS_AUGMENTED_GENERATOR,
        },
    ),
    resource(
        "labs",
        "One lab result component per row; orders without results remain represented.",
        LAB_FIELDS,
        17230681,
        foreign_keys=[foreign_key("patient_id", "patients", "patient_id")],
        encoding="iso-8859-1",
        **{
            "x-uniquePatientCount": 247271,
            "x-uniqueVisitIdCount": 2859084,
            "x-uniqueLabOrderCount": 6578838,
            "x-logicalForeignKeys": [{"fields": "visit_id", "reference": {"resource": "visits", "fields": "visit_id"}, "orphanRows": 5201657, "nullRows": 805}],
            "x-keyDescription": "No row-level primary key: lab_order_id repeats and result_line_num is missing in 2,283,186 rows.",
        },
    ),
    resource(
        "medications",
        "One pediatric prescription, administration, or historical medication record per row.",
        MEDICATION_FIELDS,
        3823049,
        primary_key="med_record_id",
        foreign_keys=[
            foreign_key("patient_id", "patients", "patient_id"),
        ],
        **{
            "x-uniquePatientCount": 236323,
            "x-uniqueVisitIdCount": 2757560,
            "x-logicalForeignKeys": [{"fields": "visit_id", "reference": {"resource": "visits", "fields": "visit_id"}, "orphanRows": 1592437}],
        },
    ),
    resource(
        "problem_list",
        "One patient problem-list diagnosis entry per row.",
        PROBLEM_FIELDS,
        1709584,
        primary_key="problem_list_id",
        foreign_keys=[foreign_key("patient_id", "patients", "patient_id")],
        **{
            "x-uniquePatientCount": 238823,
        },
    ),
    resource(
        "referrals",
        "One specialty referral associated with a pediatric visit per row.",
        REFERRAL_FIELDS,
        349827,
        primary_key="referral_id",
        foreign_keys=[
            foreign_key("patient_id", "patients", "patient_id"),
        ],
        **{
            "x-uniquePatientCount": 138071,
            "x-uniqueVisitIdCount": 298615,
            "x-logicalForeignKeys": [{"fields": "visit_id", "reference": {"resource": "visits", "fields": "visit_id"}, "orphanRows": 98623, "nullRows": 24830}],
        },
    ),
]


PACKAGE = {
    "profile": "tabular-data-package",
    "name": "ppoc-pediatric-ehr",
    "title": "PPOC Pediatric EHR Data Package",
    "description": "Machine-readable schema for de-identified pediatric EHR data. Absolute dates are replaced by patient age in days.",
    "homepage": "https://www.ppochildrens.org/",
    "version": "1.0.0",
    "created": "2026-08-18T00:00:00Z",
    "keywords": ["pediatrics", "electronic-health-records", "growth", "de-identified"],
    "x-statisticsSource": "Row, missing-value, unique-value, and category counts are transcribed from the docs/ snapshot summaries; they are not recomputed from the CSVs by schema/build.py.",
    "licenses": [
        {
            "name": "other-closed",
            "title": "Restricted use under Harvard Medical School and PPOC IRB protocol and Data Use Agreement",
            "path": "https://www.ppochildrens.org/",
        }
    ],
    "sources": [
        {
            "title": "Pediatric Physicians' Organization at Children's (PPOC)",
            "path": "https://www.ppochildrens.org/",
        }
    ],
    "contributors": [
        {
            "title": "Pediatric Physicians' Organization at Children's (PPOC)",
            "path": "https://www.ppochildrens.org/",
            "role": "publisher",
        },
        {
            "title": "Isaac Kohane Lab, Department of Biomedical Informatics, Harvard Medical School",
            "path": "https://dbmi.hms.harvard.edu/",
            "role": "maintainer",
        },
    ],
    "resources": RESOURCES,
}


def validate_statistics(item: dict[str, Any]) -> None:
    """Cross-check transcribed counts, which no CSV read can confirm here."""
    row_count = item["x-rowCount"]
    for entry in item["schema"]["fields"]:
        label = f"{item['name']}.{entry['name']}"
        constraints = entry.get("constraints", {})
        minimum, maximum = constraints.get("minimum"), constraints.get("maximum")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError(f"inverted range on {label}")
        missing = entry.get("x-missingCount", 0)
        if missing > row_count:
            raise ValueError(f"missing count exceeds row count on {label}")
        if constraints.get("required") and missing:
            raise ValueError(f"{label} is required but declares missing values")
        observed = entry.get("x-categories")
        if not observed:
            continue
        enum_values = constraints.get("enum")
        if enum_values is not None:
            unknown = [row["value"] for row in observed if row["value"] not in enum_values]
            if unknown:
                raise ValueError(f"categories outside the enum on {label}: {unknown}")
        else:
            for row in observed:
                if minimum is not None and row["value"] < minimum:
                    raise ValueError(f"category below the declared minimum on {label}")
                if maximum is not None and row["value"] > maximum:
                    raise ValueError(f"category above the declared maximum on {label}")
        unique_count = entry.get("x-uniqueValueCount")
        if unique_count is not None and unique_count != len(observed):
            raise ValueError(f"unique value count disagrees with categories on {label}")
        total = sum(row["count"] for row in observed) + missing
        if total != row_count:
            raise ValueError(f"categories plus missing values do not total the row count on {label}: {total} vs {row_count}")


def validate_package(package: dict[str, Any]) -> None:
    resources = package["resources"]
    resource_names = [item["name"] for item in resources]
    if len(resource_names) != len(set(resource_names)):
        raise ValueError("resource names must be unique")
    by_resource = {item["name"]: item for item in resources}
    for item in resources:
        names = [entry["name"] for entry in item["schema"]["fields"]]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate field in {item['name']}")
        if item["x-fieldCount"] != len(names):
            raise ValueError(f"incorrect field count in {item['name']}")
        primary_key = item["schema"].get("primaryKey")
        if primary_key and primary_key not in names:
            raise ValueError(f"missing primary key field in {item['name']}")
        for key in item["schema"].get("foreignKeys", []):
            if key["fields"] not in names:
                raise ValueError(f"missing foreign key field in {item['name']}")
            target = by_resource[key["reference"]["resource"]]
            target_names = {entry["name"] for entry in target["schema"]["fields"]}
            if key["reference"]["fields"] not in target_names:
                raise ValueError(f"missing referenced field for {item['name']}")
        validate_statistics(item)
    expected_counts = {"patients": 11, "patients_augmented": 87, "visits": 43, "visits_augmented": 82, "labs": 12, "medications": 8, "problem_list": 5, "referrals": 6}
    actual_counts = {item["name"]: len(item["schema"]["fields"]) for item in resources}
    if actual_counts != expected_counts:
        raise ValueError(f"unexpected field counts: {actual_counts}")


def serialized_package() -> str:
    validate_package(PACKAGE)
    return json.dumps(PACKAGE, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if datapackage.json is absent or stale")
    args = parser.parse_args()
    expected = serialized_package()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text() != expected:
            raise SystemExit("datapackage.json is stale; run: python3 schema/build.py")
        print(f"validated {len(RESOURCES)} resources in {OUTPUT.name}")
        return
    OUTPUT.write_text(expected)
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
