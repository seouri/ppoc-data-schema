import math

import pytest

from synthetic.models import PatientState
from synthetic.native.clinical_modules import HealthyGrowthModule
from synthetic.native.healthy import HealthyKernel
from synthetic.native.trajectories import DisorderTrajectoryKernel
from synthetic.randomness import NamedRandomStreams

PATIENT = PatientState("syn-patient-a", "F", "F")


class PhysicalOutputReference:
    reference_id = "physical-output-reference-v1"

    def __init__(self, *, height: float = 90.0, bmi: float = 16.0) -> None:
        self.height = height
        self.bmi = bmi

    def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
        del age_days, reference_sex, z
        if metric == "height_cm":
            return self.height
        if metric == "bmi":
            return self.bmi
        raise KeyError(metric)


class HookReference(PhysicalOutputReference):
    def __init__(self, hook_result: object) -> None:
        super().__init__()
        self.hook_result = hook_result

    def generation_z_score(
        self, metric: str, age_days: int, reference_sex: str, z: float
    ) -> object:
        del metric, age_days, reference_sex, z
        return self.hook_result


class TrajectoryPhysicalOutputReference(PhysicalOutputReference):
    def __init__(self, *, height: float, bmi: float) -> None:
        super().__init__(height=height, bmi=bmi)
        self._value_calls = 0

    def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
        self._value_calls += 1
        if self._value_calls <= 2:
            return 90.0 if metric == "height_cm" else 16.0
        return PhysicalOutputReference.value(self, metric, age_days, reference_sex, z)


@pytest.mark.parametrize(
    ("height", "bmi"),
    [
        (1e-200, 16.0),
        (1e308, 16.0),
        (1e308, 1e308),
        (0.1, 5e-324),
    ],
)
def test_healthy_kernel_rejects_nonphysical_derived_weight(
    height: float, bmi: float
) -> None:
    with pytest.raises(ValueError, match="derived weight.*finite and positive"):
        HealthyKernel(PhysicalOutputReference(height=height, bmi=bmi)).generate(
            PATIENT, (730,), NamedRandomStreams(5, 0)
        )


@pytest.mark.parametrize(
    ("height", "bmi", "message"),
    [
        pytest.param(
            10**1000,
            16.0,
            "reference height.*finite and positive",
            id="huge-height-int",
        ),
        pytest.param(
            90.0,
            10**1000,
            "reference BMI.*finite and positive",
            id="huge-bmi-int",
        ),
    ],
)
def test_healthy_kernel_rejects_oversized_integer_reference_values(
    height: object, bmi: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        HealthyKernel(PhysicalOutputReference(height=height, bmi=bmi)).generate(
            PATIENT, (730,), NamedRandomStreams(5, 0)
        )


@pytest.mark.parametrize(
    ("height", "bmi"),
    [
        (1e-200, 16.0),
        (1e308, 16.0),
        (1e308, 1e308),
        (0.1, 5e-324),
    ],
)
def test_disorder_trajectory_kernel_rejects_nonphysical_derived_weight(
    height: float, bmi: float
) -> None:
    reference = TrajectoryPhysicalOutputReference(height=height, bmi=bmi)
    with pytest.raises(ValueError, match="derived weight.*finite and positive"):
        DisorderTrajectoryKernel(
            HealthyKernel(reference), HealthyGrowthModule()
        ).generate(PATIENT, (730,), NamedRandomStreams(5, 0))


@pytest.mark.parametrize(
    ("height", "bmi", "message"),
    [
        pytest.param(
            10**1000,
            16.0,
            "reference height.*finite and positive",
            id="huge-height-int",
        ),
        pytest.param(
            90.0,
            10**1000,
            "reference BMI.*finite and positive",
            id="huge-bmi-int",
        ),
    ],
)
def test_disorder_trajectory_kernel_rejects_oversized_integer_reference_values(
    height: object, bmi: object, message: str
) -> None:
    reference = TrajectoryPhysicalOutputReference(height=height, bmi=bmi)
    with pytest.raises(ValueError, match=message):
        DisorderTrajectoryKernel(
            HealthyKernel(reference), HealthyGrowthModule()
        ).generate(PATIENT, (730,), NamedRandomStreams(5, 0))


@pytest.mark.parametrize(
    "hook_result",
    [True, False, math.nan, math.inf, -math.inf, None, "0", complex(0.0, 0.0)],
)
def test_generation_z_score_rejects_nonfinite_nonreal_hook_results(
    hook_result: object,
) -> None:
    with pytest.raises(ValueError, match="generation_z_score hook.*finite real"):
        HealthyKernel(HookReference(hook_result)).generate(
            PATIENT, (730,), NamedRandomStreams(5, 0)
        )
