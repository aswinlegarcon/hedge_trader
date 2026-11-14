"""Shared Decimal helpers for paper account read-side math."""
from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

Q = Decimal("0.01")
TOL = Decimal("0.01")


def d(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        x = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not x.is_finite():
        return None
    return x


def int_qty(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return None


def round_inr(x: Decimal) -> Decimal:
    return x.quantize(Q, rounding=ROUND_HALF_UP)
