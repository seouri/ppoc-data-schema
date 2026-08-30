from dataclasses import dataclass


@dataclass(frozen=True)
class PatientState:
    patient_id: str
    recorded_sex: str
    reference_sex: str


@dataclass(frozen=True)
class LatentPoint:
    patient_id: str
    age_days: int
    height_cm: float
    bmi: float
    weight_kg: float
    height_z: float
    bmi_z: float


@dataclass(frozen=True)
class ObservedVisit:
    patient_id: str
    visit_id: str
    age_days: int
    encounter_type: str
    height_in: float | None
    weight_oz: float | None
    epic_bmi: float | None


@dataclass(frozen=True)
class ClinicalEvent:
    patient_id: str
    age_days: int
    event_type: str
    code: str | None
    hidden: bool
