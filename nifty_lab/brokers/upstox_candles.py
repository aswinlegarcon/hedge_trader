"""Parse, validate and merge Upstox V3 candle payloads."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from ..data.base import DataValidationError
from .upstox_errors import UpstoxDataError, UpstoxEmptyError

IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class CandleIntervalSpec:
    unit: str  # minutes | days
    interval: int  # 5 or 1
    label: str

    @property
    def is_intraday(self) -> bool:
        return self.unit == "minutes"


def parse_candle_response(raw: bytes) -> list[list]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise UpstoxDataError("Malformed JSON in candle response.") from exc
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise UpstoxDataError("Missing data object in candle response.")
    candles = data.get("candles")
    if candles is None:
        raise UpstoxEmptyError("No candles in response.")
    if not isinstance(candles, list):
        raise UpstoxDataError("Candles field is not a list.")
    if len(candles) == 0:
        raise UpstoxEmptyError("Empty candle list.")
    return candles


def candles_to_frame(candles: list[list], *, spec: CandleIntervalSpec) -> pd.DataFrame:
    rows = []
    seen: dict[pd.Timestamp, list[float]] = {}
    dup_identical = 0
    for c in candles:
        if not isinstance(c, (list, tuple)) or len(c) < 6:
            raise UpstoxDataError("Unexpected candle row shape.")
        ts_raw = c[0]
        ts = pd.Timestamp(ts_raw)
        if ts.tzinfo is None:
            ts = ts.tz_localize(IST)
        else:
            ts = ts.tz_convert(IST)
        o, h, l, cl, vol = float(c[1]), float(c[2]), float(c[3]), float(c[4]), c[5]
        if vol is None or (isinstance(vol, float) and math.isnan(vol)):
            raise UpstoxDataError("Missing volume on a candle row.")
        vol_f = float(vol)
        if not all(math.isfinite(x) and x > 0 for x in (o, h, l, cl)):
            raise UpstoxDataError("Non-positive or non-finite OHLC.")
        if vol_f < 0 or not math.isfinite(vol_f):
            raise UpstoxDataError("Invalid volume.")
        if h < max(o, cl) or l > min(o, cl):
            raise UpstoxDataError("Inconsistent OHLC on a candle row.")
        if ts in seen:
            if seen[ts] == [o, h, l, cl, vol_f]:
                dup_identical += 1
                continue
            raise UpstoxDataError(f"Conflicting duplicate candle at {ts.isoformat()}.")
        seen[ts] = [o, h, l, cl, vol_f]
        rows.append((ts, o, h, l, cl, vol_f))
    if not rows:
        raise UpstoxEmptyError("No valid candles after deduplication.")
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"]).set_index("ts")
    df = df.sort_index()
    df.index = df.index.tz_convert(IST)
    notes = ""
    if dup_identical:
        notes = f"deduped_identical={dup_identical}"
    df.attrs["broker_notes"] = notes
    df.attrs["interval"] = spec.label
    return df


def drop_incomplete_bars(df: pd.DataFrame, spec: CandleIntervalSpec, *, now: datetime | None = None) -> tuple[pd.DataFrame, int]:
    """Remove the forming bar from indicator input."""
    now = now or datetime.now(IST)
    if df.empty:
        return df, 0
    dropped = 0
    if spec.is_intraday:
        delta = timedelta(minutes=spec.interval)
        keep_idx = []
        for ts in df.index:
            end = ts.to_pydatetime() + delta
            if end <= now.astimezone(IST):
                keep_idx.append(ts)
            else:
                dropped += 1
        return df.loc[keep_idx], dropped
    # Daily: exclude today's bar (session not complete)
    today = now.astimezone(IST).date()
    keep = df.index.date < today
    dropped = int((~keep).sum())
    return df.loc[keep], dropped


INTERVAL_5M = CandleIntervalSpec("minutes", 5, "5m")
INTERVAL_DAILY = CandleIntervalSpec("days", 1, "daily")


def merge_hist_intraday(hist: pd.DataFrame, intra: pd.DataFrame) -> pd.DataFrame:
    if hist.empty:
        out = intra
    elif intra.empty:
        out = hist
    else:
        out = pd.concat([hist, intra]).sort_index()
        out = out[~out.index.duplicated(keep="last")]
    return out
