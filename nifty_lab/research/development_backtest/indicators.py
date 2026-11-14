"""Development-only indicators (no future-year data)."""
from __future__ import annotations

import statistics
from typing import Sequence


def ema_series(values: Sequence[float], span: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (span + 1.0)
    out: list[float] = []
    for i, v in enumerate(values):
        if i == 0:
            out.append(float(v))
        else:
            out.append(alpha * float(v) + (1.0 - alpha) * out[-1])
    return out


def rolling_median_excluding_current(prior: Sequence[float]) -> float | None:
    if len(prior) < 1:
        return None
    return float(statistics.median(prior))
