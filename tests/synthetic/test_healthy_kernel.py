import pytest

from synthetic.models import PatientState
from synthetic.native.healthy import HealthyKernel
from synthetic.randomness import NamedRandomStreams


class LinearTestReference:
    reference_id = "linear-test-reference-v1"

    def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
        age_years = age_days / 365.25
        if metric == "height_cm":
            return 80.0 + 5.5 * age_years + 4.0 * z
        if metric == "bmi":
            return 16.0 + 0.25 * age_years + 1.2 * z
        raise KeyError(metric)


def test_height_and_bmi_determine_weight() -> None:
    patient = PatientState("syn-patient-a", "F", "F")
    points = HealthyKernel(LinearTestReference()).generate(
        patient,
        ages_days=(730, 1095, 1460),
        streams=NamedRandomStreams(20260830, 0),
    )
    assert len(points) == 3
    for point in points:
        assert point.weight_kg == pytest.approx(
            point.bmi * (point.height_cm / 100.0) ** 2
        )


def test_kernel_is_reproducible_and_age_ordered() -> None:
    patient = PatientState("syn-patient-a", "M", "M")
    kernel = HealthyKernel(LinearTestReference())
    left = kernel.generate(
        patient, (730, 1095, 1460), NamedRandomStreams(5, 0)
    )
    right = kernel.generate(
        patient, (730, 1095, 1460), NamedRandomStreams(5, 0)
    )
    assert left == right
    assert [point.age_days for point in left] == [730, 1095, 1460]


def test_foundation_rejects_infant_ages() -> None:
    patient = PatientState("syn-patient-a", "F", "F")
    with pytest.raises(ValueError, match="age >= 730"):
        HealthyKernel(LinearTestReference()).generate(
            patient, (365,), NamedRandomStreams(5, 0)
        )
