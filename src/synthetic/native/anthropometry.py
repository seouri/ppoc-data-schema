"""Shared guarded anthropometric derivations for the native growth kernels."""

from __future__ import annotations

import math
from numbers import Real


def require_finite_real(value: object, message: str) -> float:
    """Return a finite real value, normalizing numeric conversion failures."""

    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(message)  # noqa: TRY004
    try:
        result = float(value)
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise ValueError(message) from exc
    if not math.isfinite(result):
        raise ValueError(message)
    return result


def require_finite_positive(value: object, message: str) -> float:
    """Return a finite strictly positive real value."""

    result = require_finite_real(value, message)
    if result <= 0:
        raise ValueError(message)
    return result


def derive_weight_kg(bmi: object, height_cm: object) -> float:
    """Derive weight from BMI and height, rejecting nonphysical results."""

    try:
        weight_kg = bmi * (height_cm / 100.0) ** 2
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise ValueError("derived weight must be finite and positive") from exc
    return require_finite_positive(weight_kg, "derived weight must be finite and positive")
