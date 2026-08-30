from typing import Protocol


class GrowthReference(Protocol):
    reference_id: str

    def value(
        self, metric: str, age_days: int, reference_sex: str, z: float
    ) -> float: ...
