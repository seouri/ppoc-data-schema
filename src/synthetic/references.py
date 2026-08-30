import csv
import hashlib
import math
from bisect import bisect_left
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class GrowthReference(Protocol):
    reference_id: str

    def value(
        self, metric: str, age_days: int, reference_sex: str, z: float
    ) -> float: ...


@dataclass(frozen=True)
class LmsRow:
    metric: str
    age_days: int
    reference_sex: str
    l: float
    m: float
    s: float

    def __post_init__(self) -> None:
        if not isinstance(self.metric, str) or not self.metric:
            raise ValueError("metric must be a nonempty string")
        if not isinstance(self.reference_sex, str) or not self.reference_sex:
            raise ValueError("reference_sex must be a nonempty string")
        if not isinstance(self.age_days, int) or isinstance(self.age_days, bool) or self.age_days < 0:
            raise ValueError("age_days must be a nonnegative integer")
        for name in ("l", "m", "s"):
            try:
                number = float(getattr(self, name))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be a finite float") from exc
            if not math.isfinite(number):
                raise ValueError(f"{name} must be a finite float")
            if name in ("m", "s") and number <= 0:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, number)


class LmsGrowthReference:
    def __init__(
        self, reference_id: str, rows: Iterable[LmsRow], source_sha256: str | None = None
    ) -> None:
        if not isinstance(reference_id, str) or not reference_id:
            raise ValueError("reference_id must be a nonempty string")
        normalized = tuple(rows)
        if not normalized:
            raise ValueError("rows must not be empty")
        keys = [(row.metric, row.age_days, row.reference_sex) for row in normalized]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate LMS row")
        self._reference_id = reference_id
        self._source_sha256 = source_sha256
        self._rows = tuple(sorted(normalized, key=lambda row: (row.metric, row.reference_sex, row.age_days)))
        self._series: dict[tuple[str, str], tuple[LmsRow, ...]] = {}
        for row in self._rows:
            self._series.setdefault((row.metric, row.reference_sex), ())
            self._series[(row.metric, row.reference_sex)] += (row,)
        self._metrics = tuple(sorted({row.metric for row in self._rows}))

    @property
    def reference_id(self) -> str:
        return self._reference_id

    @property
    def source_sha256(self) -> str | None:
        return self._source_sha256

    @property
    def metrics(self) -> tuple[str, ...]:
        return self._metrics

    @property
    def min_age_days(self) -> int:
        return min(row.age_days for row in self._rows)

    @property
    def max_age_days(self) -> int:
        return max(row.age_days for row in self._rows)

    def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
        try:
            score = float(z)
        except (TypeError, ValueError) as exc:
            raise ValueError("z must be finite") from exc
        if not math.isfinite(score):
            raise ValueError("z must be finite")
        try:
            series = self._series[(metric, reference_sex)]
        except KeyError as exc:
            raise KeyError(metric if metric not in self._metrics else reference_sex) from exc
        if not isinstance(age_days, int) or isinstance(age_days, bool):
            raise TypeError("age_days must be an integer")
        if age_days < series[0].age_days or age_days > series[-1].age_days:
            raise ValueError("age_days is outside the domain")
        ages = [row.age_days for row in series]
        right = bisect_left(ages, age_days)
        if right == len(series) or ages[right] == age_days:
            lms = series[right]
        else:
            lower, upper = series[right - 1], series[right]
            midpoint = (lower.age_days + upper.age_days) // 2
            fraction = (
                0.5
                if age_days == midpoint
                else (age_days - lower.age_days) / (upper.age_days - lower.age_days)
            )
            lms = LmsRow(
                metric, age_days, reference_sex,
                lower.l + fraction * (upper.l - lower.l),
                lower.m + fraction * (upper.m - lower.m),
                lower.s + fraction * (upper.s - lower.s),
            )
        if lms.l == 0:
            try:
                result = lms.m * math.exp(lms.s * score)
            except OverflowError as exc:
                raise ValueError("LMS result is not finite and positive") from exc
        else:
            base = 1 + lms.l * lms.s * score
            if base <= 0:
                raise ValueError("LMS base must be positive")
            try:
                result = lms.m * math.pow(base, 1 / lms.l)
            except (OverflowError, ValueError) as exc:
                raise ValueError("LMS result is not finite and positive") from exc
        if not math.isfinite(result) or result <= 0:
            raise ValueError("LMS result is not finite and positive")
        return result

    @classmethod
    def from_csv(
        cls, path: Path, reference_id: str, expected_sha256: str | None = None
    ) -> "LmsGrowthReference":
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected_sha256 is not None and digest != expected_sha256:
            raise ValueError("SHA-256 hash does not match expected value")
        columns = ("metric", "age_days", "reference_sex", "l", "m", "s")
        rows: list[LmsRow] = []
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or set(reader.fieldnames) != set(columns) or len(reader.fieldnames) != len(columns):
                raise ValueError("CSV columns must be exactly metric, age_days, reference_sex, l, m, s")
            for raw in reader:
                if None in raw:
                    raise ValueError("CSV columns must be exactly metric, age_days, reference_sex, l, m, s")
                try:
                    rows.append(LmsRow(raw["metric"], int(raw["age_days"]), raw["reference_sex"], float(raw["l"]), float(raw["m"]), float(raw["s"])) )
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError("invalid typed LMS row") from exc
        return cls(reference_id, rows, source_sha256=digest)
