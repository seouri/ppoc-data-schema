from __future__ import annotations

import math
from numbers import Real

from synthetic.models import LatentPoint, PatientState
from synthetic.randomness import NamedRandomStreams
from synthetic.references import GrowthReference, generation_z_score


def _nonnegative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


class HealthyKernel:
    def __init__(
        self,
        reference: GrowthReference,
        *,
        minimum_age_days: int = 730,
        maximum_age_days: int | None = None,
    ) -> None:
        minimum_age_days = _nonnegative_int("minimum_age_days", minimum_age_days)
        if maximum_age_days is not None:
            maximum_age_days = _nonnegative_int("maximum_age_days", maximum_age_days)
        if maximum_age_days is not None and maximum_age_days < minimum_age_days:
            raise ValueError("maximum_age_days must not be smaller than minimum_age_days")
        self.reference = reference
        self.minimum_age_days = minimum_age_days
        self.maximum_age_days = maximum_age_days

    def generate(
        self,
        patient: PatientState,
        ages_days: tuple[int, ...],
        streams: NamedRandomStreams,
    ) -> tuple[LatentPoint, ...]:
        if not isinstance(ages_days, tuple) or not ages_days:
            raise ValueError("ages_days must be a nonempty tuple")
        if any(
            isinstance(age, bool) or not isinstance(age, int) or age < 0
            for age in ages_days
        ):
            raise ValueError("ages_days must contain nonnegative integers")
        if tuple(sorted(set(ages_days))) != ages_days:
            raise ValueError("ages_days must be unique and increasing")
        if any(age < self.minimum_age_days for age in ages_days):
            raise ValueError(
                f"foundation kernel requires age >= {self.minimum_age_days} days"
            )
        if self.maximum_age_days is not None and any(
            age > self.maximum_age_days for age in ages_days
        ):
            raise ValueError(
                f"foundation kernel requires age <= {self.maximum_age_days} days"
            )

        reference_min_age = getattr(self.reference, "min_age_days", None)
        reference_max_age = getattr(self.reference, "max_age_days", None)
        if isinstance(reference_min_age, int) and not isinstance(reference_min_age, bool) and any(
            age < reference_min_age for age in ages_days
        ):
            raise ValueError("requested ages are outside the reference domain")
        if isinstance(reference_max_age, int) and not isinstance(reference_max_age, bool) and any(
            age > reference_max_age for age in ages_days
        ):
            raise ValueError("requested ages are outside the reference domain")

        growth = streams.generator("growth")
        height_z = float(growth.normal(0.0, 0.8))
        bmi_z = float(growth.normal(0.0, 0.8))
        points: list[LatentPoint] = []
        for age_days in ages_days:
            height_z = 0.96 * height_z + float(growth.normal(0.0, 0.08))
            bmi_z = 0.85 * bmi_z + float(growth.normal(0.0, 0.20))
            height_z = generation_z_score(
                self.reference,
                "height_cm",
                age_days,
                patient.reference_sex,
                height_z,
            )
            bmi_z = generation_z_score(
                self.reference,
                "bmi",
                age_days,
                patient.reference_sex,
                bmi_z,
            )
            height_cm = self.reference.value(
                "height_cm", age_days, patient.reference_sex, height_z
            )
            bmi = self.reference.value("bmi", age_days, patient.reference_sex, bmi_z)
            if (
                isinstance(height_cm, bool)
                or not isinstance(height_cm, Real)
                or not math.isfinite(height_cm)
                or height_cm <= 0
            ):
                raise ValueError("reference height must be finite and positive")
            if (
                isinstance(bmi, bool)
                or not isinstance(bmi, Real)
                or not math.isfinite(bmi)
                or bmi <= 0
            ):
                raise ValueError("reference BMI must be finite and positive")
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
