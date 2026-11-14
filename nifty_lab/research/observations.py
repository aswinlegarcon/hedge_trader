"""Deterministic watchlist observations from completed OHLCV (Spec 05)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from ..indicators.core import ema, sma, support_resistance_levels

IST = ZoneInfo("Asia/Kolkata")
STALE_LAG_MINUTES = 10


@dataclass(frozen=True)
class WatchlistObservation:
    research_label: str
    trading_symbol: str
    instrument_key: str
    display_name: str
    data_state: str
    daily_context_date: str
    daily_trend: str
    daily_close: float | None
    m5_completed_at: str
    m5_close: float | None
    ema_relation: str
    vwap_relation: str
    session_vwap: float | None
    rel_volume: str
    nearest_support: float | None
    nearest_resistance: float | None
    level_observation: str
    summary: str
    limitations: tuple[str, ...] = field(default_factory=tuple)
    diagnostic: str = ""
    retrieved_at_utc: str = ""


def _session_vwap_last(df: pd.DataFrame) -> tuple[float | None, str]:
    """Typical-price VWAP for the latest session in frame (completed bars only)."""
    if df.empty:
        return None, "unknown"
    if df.index.tz is None:
        idx = df.index.tz_localize(IST)
    else:
        idx = df.index.tz_convert(IST)
    df = df.copy()
    df.index = idx
    session_dates = df.index.date
    last_session = session_dates[-1]
    sess = df[session_dates == last_session]
    typical = (sess["high"] + sess["low"] + sess["close"]) / 3.0
    cum_v = sess["volume"].cumsum()
    if float(cum_v.iloc[-1]) <= 0:
        return None, "unknown"
    cum_pv = (typical * sess["volume"]).cumsum()
    vwap = float(cum_pv.iloc[-1] / cum_v.iloc[-1])
    close = float(sess["close"].iloc[-1])
    if close > vwap:
        rel = "above session VWAP"
    elif close < vwap:
        rel = "below session VWAP"
    else:
        rel = "at session VWAP"
    return vwap, rel


def _rel_volume_prior20(df: pd.DataFrame) -> str:
    if len(df) < 2:
        return "unavailable"
    if df.index.tz is None:
        idx = df.index.tz_localize(IST)
    else:
        idx = df.index.tz_convert(IST)
    df = df.copy()
    df.index = idx
    last_session = df.index.date[-1]
    sess = df[df.index.date == last_session]
    if len(sess) < 2:
        return "unavailable"
    latest_vol = float(sess["volume"].iloc[-1])
    prior = sess["volume"].iloc[:-1]
    if len(prior) < 20:
        return "unavailable (<20 prior session bars)"
    window = prior.tail(20)
    denom = float(window.mean())
    if denom <= 0:
        return "unavailable"
    ratio = latest_vol / denom
    return f"{ratio:.2f} vs preceding 20 session bars"


def _daily_trend(daily: pd.DataFrame) -> tuple[str, float | None, str]:
    if daily.empty:
        return "INSUFFICIENT DATA", None, ""
    close = daily["close"]
    s50 = sma(close, 50)
    s200 = sma(close, 200)
    last = daily.iloc[-1]
    c = float(last["close"])
    if pd.isna(s200.iloc[-1]) or pd.isna(s50.iloc[-1]):
        return "WARM-UP", c, str(daily.index[-1].date())
    if c > s50.iloc[-1] and c > s200.iloc[-1]:
        trend = "ABOVE BOTH (SMA50 & SMA200)"
    elif c < s50.iloc[-1] and c < s200.iloc[-1]:
        trend = "BELOW BOTH (SMA50 & SMA200)"
    else:
        trend = "MIXED"
    return trend, c, str(daily.index[-1].date())


def _ema_relation(m5: pd.DataFrame) -> str:
    if len(m5) < 21:
        return "WARM-UP"
    e9 = ema(m5["close"], 9)
    e21 = ema(m5["close"], 21)
    c = float(m5["close"].iloc[-1])
    if pd.isna(e9.iloc[-1]) or pd.isna(e21.iloc[-1]):
        return "WARM-UP"
    if c > e9.iloc[-1] and c > e21.iloc[-1] and e9.iloc[-1] >= e21.iloc[-1]:
        return "ABOVE BOTH, EMA9≥EMA21"
    if c < e9.iloc[-1] and c < e21.iloc[-1] and e9.iloc[-1] <= e21.iloc[-1]:
        return "BELOW BOTH, EMA9≤EMA21"
    return "MIXED"


def _frozen_levels_and_cross(m5: pd.DataFrame) -> tuple[float | None, float | None, str]:
    if len(m5) < 12:
        return None, None, "levels unknown (warm-up)"
    ref_idx = m5.index[-2]
    hist = m5.iloc[:-1]
    levels = support_resistance_levels(hist, as_of=ref_idx)
    sup = levels["support"][0] if levels["support"] else None
    res = levels["resistance"][0] if levels["resistance"] else None
    prev_c = float(m5["close"].iloc[-2])
    last_c = float(m5["close"].iloc[-1])
    note = "no frozen level cross observed"
    if res is not None and prev_c <= res < last_c:
        note = f"closed above prior resistance {res:,.2f} (confirmed before {ref_idx})"
    elif sup is not None and prev_c >= sup > last_c:
        note = f"closed below prior support {sup:,.2f} (confirmed before {ref_idx})"
    return sup, res, note


def _m5_freshness_state(m5: pd.DataFrame, now: datetime) -> str:
    if m5.empty:
        return "INSUFFICIENT DATA"
    last_ts = m5.index[-1]
    if last_ts.tzinfo is None:
        last_ts = last_ts.tz_localize(IST)
    else:
        last_ts = last_ts.tz_convert(IST)
    now_ist = now.astimezone(IST)
    bar_end = last_ts + timedelta(minutes=5)
    if last_ts.date() < now_ist.date():
        return "PRIOR SESSION"
    if (now_ist - bar_end).total_seconds() > STALE_LAG_MINUTES * 60:
        return "STALE"
    return "OK"


def build_observation(
    *,
    research_label: str,
    trading_symbol: str,
    instrument_key: str,
    display_name: str,
    daily: pd.DataFrame | None,
    m5: pd.DataFrame | None,
    now: datetime | None = None,
    retrieved_at: datetime | None = None,
) -> WatchlistObservation:
    now = now or datetime.now(IST)
    retrieved_at = retrieved_at or datetime.now(ZoneInfo("UTC"))
    limitations = (
        "News/event context NOT CHECKED.",
        "Session VWAP is candle-typical-price approximation, not trade-level.",
        "No exchange holiday calendar — session labels are heuristic.",
        "Observations are descriptive, not trade signals.",
    )
    partial = False
    if daily is None or daily.empty:
        daily_trend, daily_close, daily_date = "INSUFFICIENT DATA", None, ""
        partial = True
    else:
        daily_trend, daily_close, daily_date = _daily_trend(daily)

    if m5 is None or m5.empty:
        partial = True
        state = "INSUFFICIENT DATA"
        return WatchlistObservation(
            research_label=research_label,
            trading_symbol=trading_symbol,
            instrument_key=instrument_key,
            display_name=display_name,
            data_state=state,
            daily_context_date=daily_date,
            daily_trend=daily_trend,
            daily_close=daily_close,
            m5_completed_at="",
            m5_close=None,
            ema_relation="unavailable",
            vwap_relation="unavailable",
            session_vwap=None,
            rel_volume="unavailable",
            nearest_support=None,
            nearest_resistance=None,
            level_observation="unavailable",
            summary="mixed observations; waiting for data" if partial else "INSUFFICIENT DATA",
            limitations=limitations,
            retrieved_at_utc=retrieved_at.strftime("%Y-%m-%d %H:%M UTC"),
        )

    fresh = _m5_freshness_state(m5, now)
    state = "PARTIAL DATA" if partial else fresh
    if partial and fresh == "OK":
        state = "PARTIAL DATA"

    vwap_val, vwap_rel = _session_vwap_last(m5)
    rel_vol = _rel_volume_prior20(m5)
    ema_rel = _ema_relation(m5)
    sup, res, lvl_note = _frozen_levels_and_cross(m5)
    last_ts = m5.index[-1]
    if last_ts.tzinfo is not None:
        last_ts = last_ts.tz_convert(IST)
    m5_close = float(m5["close"].iloc[-1])

    daily_up = "up" in daily_trend or "ABOVE" in daily_trend
    intra_up = "ABOVE" in ema_rel
    if daily_trend == "INSUFFICIENT DATA" or ema_rel == "WARM-UP":
        summary = "mixed observations; incomplete warm-up"
    elif daily_up and intra_up:
        summary = "daily and intraday conditions align upward (descriptive only)"
    elif (not daily_up) and "BELOW" in ema_rel:
        summary = "daily and intraday conditions align downward (descriptive only)"
    else:
        summary = "mixed observations across daily and intraday"

    return WatchlistObservation(
        research_label=research_label,
        trading_symbol=trading_symbol,
        instrument_key=instrument_key,
        display_name=display_name,
        data_state=state,
        daily_context_date=daily_date,
        daily_trend=daily_trend,
        daily_close=daily_close,
        m5_completed_at=last_ts.isoformat(),
        m5_close=m5_close,
        ema_relation=ema_rel,
        vwap_relation=vwap_rel,
        session_vwap=vwap_val,
        rel_volume=rel_vol,
        nearest_support=sup,
        nearest_resistance=res,
        level_observation=lvl_note,
        summary=summary,
        limitations=limitations,
        retrieved_at_utc=retrieved_at.strftime("%Y-%m-%d %H:%M UTC"),
    )
