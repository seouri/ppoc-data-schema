import math

import pytest

from synthetic.models import PatientState
from synthetic.native.healthy import HealthyKernel
from synthetic.randomness import NamedRandomStreams


class GuardReference:
    reference_id = "guard-reference-v1"
    min_age_days = 730
    max_age_days = 1095

    def __init__(
        self,
        *,
        height: float = 90.0,
        bmi: float = 16.0,
        min_age_days: int = 730,
    ) -> None:
        self.height = height
        self.bmi = bmi
        self.min_age_days = min_age_days

    def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
        del age_days, reference_sex, z
        if metric == "height_cm":
            return self.height
        if metric == "bmi":
            return self.bmi
        raise KeyError(metric)


def _patient() -> PatientState:
    return PatientState("syn-patient-a", "F", "F")


def test_kernel_rejects_ages_outside_reference_domain() -> None:
    reference = GuardReference()
    with pytest.raises(ValueError, match="domain"):
        HealthyKernel(reference).generate(
            _patient(), (1096,), NamedRandomStreams(5, 0)
        )


def test_kernel_rejects_age_below_reference_domain() -> None:
    with pytest.raises(ValueError, match="domain"):
        HealthyKernel(GuardReference(), minimum_age_days=0).generate(
            _patient(), (0,), NamedRandomStreams(5, 0)
        )


def test_kernel_can_be_configured_for_a_reference_starting_at_birth() -> None:
    reference = GuardReference(min_age_days=0)
    points = HealthyKernel(reference, minimum_age_days=0, maximum_age_days=1095).generate(
        _patient(), (0, 730), NamedRandomStreams(5, 0)
    )

    assert [point.age_days for point in points] == [0, 730]


def test_kernel_does_not_treat_boolean_reference_bounds_as_ages() -> None:
    reference = GuardReference(min_age_days=True)
    reference.max_age_days = False
    points = HealthyKernel(reference, minimum_age_days=0, maximum_age_days=1095).generate(
        _patient(), (0, 730), NamedRandomStreams(5, 0)
    )

    assert [point.age_days for point in points] == [0, 730]


@pytest.mark.parametrize(
    "height,bmi",
    [(0.0, 16.0), (90.0, 0.0), (math.nan, 16.0), (None, 16.0), ("90", 16.0)],
)
def test_kernel_rejects_nonphysical_reference_values(height: float, bmi: float) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        HealthyKernel(GuardReference(height=height, bmi=bmi)).generate(
            _patient(), (730,), NamedRandomStreams(5, 0)
        )


def test_kernel_rejects_invalid_age_configuration() -> None:
    with pytest.raises(ValueError, match="minimum_age_days"):
        HealthyKernel(GuardReference(), minimum_age_days=-1)
    with pytest.raises(ValueError, match="maximum_age_days"):
        HealthyKernel(GuardReference(), minimum_age_days=900, maximum_age_days=800)


@pytest.mark.parametrize("minimum_age_days", [True, 730.5, "730", None])
def test_kernel_rejects_non_integer_minimum_age_configuration(
    minimum_age_days: object,
) -> None:
    with pytest.raises(ValueError, match="minimum_age_days must be a nonnegative integer"):
        HealthyKernel(GuardReference(), minimum_age_days=minimum_age_days)  # type: ignore[arg-type]


@pytest.mark.parametrize("maximum_age_days", [True, 1095.5, "1095"])
def test_kernel_rejects_non_integer_maximum_age_configuration(
    maximum_age_days: object,
) -> None:
    with pytest.raises(ValueError, match="maximum_age_days must be a nonnegative integer"):
        HealthyKernel(GuardReference(), maximum_age_days=maximum_age_days)  # type: ignore[arg-type]


@pytest.mark.parametrize("age_days", [True, 730.5, "730", None])
def test_kernel_rejects_non_integer_requested_ages(age_days: object) -> None:
    with pytest.raises(ValueError, match="ages_days must contain nonnegative integers"):
        HealthyKernel(GuardReference()).generate(
            _patient(), (age_days,), NamedRandomStreams(5, 0)  # type: ignore[assignment]
        )


def test_kernel_accepts_nonnegative_integer_requested_age() -> None:
    points = HealthyKernel(GuardReference()).generate(
        _patient(), (730,), NamedRandomStreams(5, 0)
    )

    assert [point.age_days for point in points] == [730]
