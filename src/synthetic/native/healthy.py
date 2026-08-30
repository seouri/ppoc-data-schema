from __future__ import annotations

from synthetic.models import LatentPoint, PatientState
from synthetic.randomness import NamedRandomStreams
from synthetic.references import GrowthReference


class HealthyKernel:
    def __init__(self, reference: GrowthReference) -> None:
        self.reference = reference

    def generate(
        self,
        patient: PatientState,
        ages_days: tuple[int, ...],
        streams: NamedRandomStreams,
    ) -> tuple[LatentPoint, ...]:
        if tuple(sorted(set(ages_days))) != ages_days:
            raise ValueError("ages_days must be unique and increasing")
        if any(age < 730 for age in ages_days):
            raise ValueError("foundation kernel requires age >= 730 days")

        growth = streams.generator("growth")
        height_z = float(growth.normal(0.0, 0.8))
        bmi_z = float(growth.normal(0.0, 0.8))
        points: list[LatentPoint] = []
        for age_days in ages_days:
            height_z = 0.96 * height_z + float(growth.normal(0.0, 0.08))
            bmi_z = 0.85 * bmi_z + float(growth.normal(0.0, 0.20))
            height_cm = self.reference.value(
                "height_cm", age_days, patient.reference_sex, height_z
            )
            bmi = self.reference.value("bmi", age_days, patient.reference_sex, bmi_z)
            weight_kg = bmi * (height_cm / 100.0) ** 2
            points.append(
                LatentPoint(
                    patient_id=patient.patient_id,
                    age_days=age_days,
                    height_cm=height_cm,
                    bmi=bmi,
                    weight_kg=weight_kg,
                    height_z=height_z,
                    bmi_z=bmi_z,
                )
            )
        return tuple(points)
