"""Shared guarded anthropometric derivations for the native growth kernels."""

from __future__ import annotations

import math
from numbers import Real


def derive_weight_kg(bmi: object, height_cm: object) -> float:
    """Derive weight from BMI and height, rejecting nonphysical results."""

    try:
        weight_kg = bmi * (height_cm / 100.0) ** 2
        if isinstance(weight_kg, bool) or not isinstance(weight_kg, Real):
            raise TypeError("derived weight must be real")
        result = float(weight_kg)
        if not math.isfinite(result) or result <= 0:
            raise ValueError("derived weight must be finite and positive")
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise ValueError("derived weight must be finite and positive") from exc
    return result
