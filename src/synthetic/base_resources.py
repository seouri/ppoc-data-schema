from __future__ import annotations

from typing import Any

from synthetic.models import LatentPoint, PatientState
from synthetic.randomness import synthetic_id
from synthetic.schema_contract import field_names

BASE_RESOURCES = (
    "patients",
    "visits",
    "labs",
    "medications",
    "problem_list",
    "referrals",
)


def _blank_row(descriptor: dict[str, Any], resource_name: str) -> dict[str, object]:
    return {name: "" for name in field_names(descriptor, resource_name)}


def build_base_rows(
    descriptor: dict[str, Any],
    patient: PatientState,
    points: tuple[LatentPoint, ...],
    *,
    seed: int,
) -> dict[str, list[dict[str, object]]]:
    """Map engine-neutral patient and latent points to descriptor-shaped base rows.

    Ancillary resources are intentionally represented by empty row lists until a
    generator supplies those domains.  Every emitted row is initialized from the
    descriptor field order, so adding fields to the source contract cannot silently
    produce malformed CSV records.
    """
    rows = {name: [] for name in BASE_RESOURCES}
    patient_row = _blank_row(descriptor, "patients")
    patient_row.update(
        {
            "patient_id": patient.patient_id,
            "sex": patient.recorded_sex,
            "ethnicity": "Unknown",
        }
    )
    rows["patients"].append(patient_row)

    for index, point in enumerate(points):
        visit = _blank_row(descriptor, "visits")
        visit.update(
            {
                "patient_id": patient.patient_id,
                "visit_id": synthetic_id(seed, "visit", index),
                "age_in_days": point.age_days,
                "encounter_type": "Office Visit",
                "orig_enc_source_Epic_yn": "Y",
                "weight_oz": point.weight_kg * 35.274,
                "height_in": point.height_cm / 2.54,
                "BMI": point.bmi,
            }
        )
        rows["visits"].append(visit)
    return rows
