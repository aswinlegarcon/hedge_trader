"""Validated development bar invariants (post-preflight)."""
from __future__ import annotations

import math

import pandas as pd


def validate_development_frame(df: pd.DataFrame) -> str | None:
    if df.empty:
        return "EMPTY_FRAME"
    if not df.index.is_monotonic_increasing:
        return "UNORDERED_INDEX"
    if df.index.duplicated().any():
        return "DUPLICATE_SESSION"
    required = ("open", "high", "low", "close", "volume")
    for col in required:
        if col not in df.columns:
            return "MISSING_COLUMN"
    for col in required:
        series = df[col]
        if series.isna().any():
            return "NONFINITE_VALUES"
        for val in series:
            if not isinstance(val, (int, float)) or not math.isfinite(float(val)):
                return "NONFINITE_VALUES"
    for _, row in df.iterrows():
        o, h, l, c, v = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]), float(row["volume"])
        if o <= 0 or h <= 0 or l <= 0 or c <= 0 or v < 0:
            return "INVALID_OHLCV"
        if h < max(o, c) or l > min(o, c):
            return "OHLC_INCONSISTENT"
    return None
