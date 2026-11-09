"""Transparent rule-based signal engine.

The engine evaluates a fixed, documented rule set against the indicator frame
*as of a given bar* (only that bar and earlier are used) and returns a
:class:`SignalReport` listing every condition that passed or failed. There are
no probabilities or confidence scores — only rules and their outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import pandas as pd

from ..indicators.core import compute_indicator_frame, support_resistance_levels


class SignalType(str, Enum):
    BULLISH_SETUP = "BULLISH SETUP"
    BEARISH_SETUP = "BEARISH SETUP"
    NEUTRAL_SETUP = "NEUTRAL SETUP"
    WAIT = "WAIT"
    INSUFFICIENT_DATA = "INSUFFICIENT DATA"


class Regime(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    UNCERTAIN = "UNCERTAIN"


@dataclass
class Condition:
    name: str
    passed: bool
    detail: str
    direction: str  # 'bull', 'bear', 'neutral', 'filter'


@dataclass
class SignalReport:
    signal: SignalType
    regime: Regime
    as_of: pd.Timestamp | None
    indicator_values: dict[str, float | str]
    conditions: list[Condition] = field(default_factory=list)
    reasons_to_avoid: list[str] = field(default_factory=list)
    invalidation: list[str] = field(default_factory=list)
    strategy_candidates: list[str] = field(default_factory=list)
    hypothetical_plan: dict[str, str] = field(default_factory=dict)
    levels: dict[str, list[float]] = field(default_factory=dict)

    @property
    def passed(self) -> list[Condition]:
        return [c for c in self.conditions if c.passed]

    @property
    def failed(self) -> list[Condition]:
        return [c for c in self.conditions if not c.passed]

    def supporting(self, direction: str) -> list[Condition]:
        return [c for c in self.conditions if c.passed and c.direction == direction]

    def contradicting(self, direction: str) -> list[Condition]:
        opposite = {"bull": "bear", "bear": "bull"}.get(direction)
        return [c for c in self.conditions if c.passed and c.direction == opposite]


MIN_BARS = 200  # need SMA200 for regime


def _f(x) -> float:
    return float(x) if x is not None and not pd.isna(x) else float("nan")


def determine_regime(row: pd.Series) -> tuple[Regime, list[Condition]]:
    close, s50, s200 = _f(row["close"]), _f(row["sma50"]), _f(row["sma200"])
    conds: list[Condition] = []
    if np.isnan(s200) or np.isnan(s50):
        return Regime.UNCERTAIN, conds
    above200 = close > s200
    above50 = close > s50
    stacked_bull = s50 > s200
    conds.append(Condition("Close above 200-day SMA", above200, f"close {close:,.0f} vs SMA200 {s200:,.0f}", "bull"))
    conds.append(Condition("Close below 200-day SMA", not above200, f"close {close:,.0f} vs SMA200 {s200:,.0f}", "bear"))
    conds.append(Condition("50-day SMA above 200-day SMA (bullish structure)", stacked_bull, f"SMA50 {s50:,.0f} vs SMA200 {s200:,.0f}", "bull"))
    conds.append(Condition("50-day SMA below 200-day SMA (bearish structure)", not stacked_bull, f"SMA50 {s50:,.0f} vs SMA200 {s200:,.0f}", "bear"))
    if above200 and above50 and stacked_bull:
        return Regime.BULLISH, conds
    if not above200 and not above50 and not stacked_bull:
        return Regime.BEARISH, conds
    dist = abs(close - s200) / s200
    if dist < 0.02:
        return Regime.NEUTRAL, conds
    return Regime.UNCERTAIN, conds


def evaluate(df_ind: pd.DataFrame, as_of: pd.Timestamp | None = None, india_vix: float | None = None, event_risk_notes: list[str] | None = None) -> SignalReport:
    """Evaluate the rule set at ``as_of`` (default last bar). ``df_ind`` must come
    from :func:`compute_indicator_frame` (or contain the same columns)."""
    if as_of is not None:
        hist = df_ind.loc[:as_of]
    else:
        hist = df_ind
    if len(hist) < MIN_BARS or hist.iloc[-1][["sma200", "rsi14", "atr14", "macd", "signal"]].isna().any():
        return SignalReport(
            signal=SignalType.INSUFFICIENT_DATA,
            regime=Regime.UNCERTAIN,
            as_of=hist.index[-1] if len(hist) else None,
            indicator_values={"bars_available": len(hist), "bars_required": MIN_BARS},
            reasons_to_avoid=[f"Only {len(hist)} bars available; {MIN_BARS} needed for the 200-day SMA regime filter."],
        )

    row = hist.iloc[-1]
    prev = hist.iloc[-2]
    ts = hist.index[-1]
    regime, conds = determine_regime(row)

    close, rsi_v = _f(row["close"]), _f(row["rsi14"])
    macd_v, sig_v, hist_v, hist_prev = _f(row["macd"]), _f(row["signal"]), _f(row["hist"]), _f(prev["hist"])
    ema9, ema21 = _f(row["ema9"]), _f(row["ema21"])
    sma20 = _f(row["sma20"])
    atr_v, atr_pct = _f(row["atr14"]), _f(row["atr_pct"])
    bb_pct = _f(row["bb_pct_b"])
    bb_width = _f(row["bb_width"])
    vol_regime = str(row.get("vol_regime", "INSUFFICIENT DATA"))
    vol_ratio = _f(row.get("vol_ratio", np.nan))
    rv20 = _f(row.get("rv20", np.nan))

    # Momentum conditions ------------------------------------------------------
    conds.append(Condition("EMA9 above EMA21 (short-term momentum up)", ema9 > ema21, f"EMA9 {ema9:,.0f} vs EMA21 {ema21:,.0f}", "bull"))
    conds.append(Condition("EMA9 below EMA21 (short-term momentum down)", ema9 < ema21, f"EMA9 {ema9:,.0f} vs EMA21 {ema21:,.0f}", "bear"))
    conds.append(Condition("MACD above signal line", macd_v > sig_v, f"MACD {macd_v:,.1f} vs signal {sig_v:,.1f}", "bull"))
    conds.append(Condition("MACD below signal line", macd_v < sig_v, f"MACD {macd_v:,.1f} vs signal {sig_v:,.1f}", "bear"))
    conds.append(Condition("MACD histogram rising", hist_v > hist_prev, f"hist {hist_v:,.1f} vs prev {hist_prev:,.1f}", "bull"))
    conds.append(Condition("MACD histogram falling", hist_v < hist_prev, f"hist {hist_v:,.1f} vs prev {hist_prev:,.1f}", "bear"))
    conds.append(Condition("RSI14 in healthy bullish zone (45-70)", 45 <= rsi_v <= 70, f"RSI {rsi_v:.1f}", "bull"))
    conds.append(Condition("RSI14 in bearish zone (30-55)", 30 <= rsi_v <= 55, f"RSI {rsi_v:.1f}", "bear"))
    conds.append(Condition("RSI14 not overbought (<70)", rsi_v < 70, f"RSI {rsi_v:.1f}", "filter"))
    conds.append(Condition("RSI14 not oversold (>30)", rsi_v > 30, f"RSI {rsi_v:.1f}", "filter"))
    conds.append(Condition("Close above 20-day SMA", close > sma20, f"close {close:,.0f} vs SMA20 {sma20:,.0f}", "bull"))
    conds.append(Condition("Close below 20-day SMA", close < sma20, f"close {close:,.0f} vs SMA20 {sma20:,.0f}", "bear"))
    conds.append(Condition("Price inside Bollinger Bands (not stretched)", 0.05 <= bb_pct <= 0.95, f"%B {bb_pct:.2f}", "filter"))
    conds.append(Condition("Range-bound: Bollinger width in lower half of recent history", bb_width < _f(hist["bb_width"].tail(120).median()), f"BB width {bb_width:.3f}", "neutral"))
    conds.append(Condition("Volatility regime not EXTREME", vol_regime != "EXTREME", f"regime {vol_regime}", "filter"))

    # Reasons to avoid ------------------------------------------------------------
    avoid: list[str] = []
    if vol_regime == "EXTREME":
        avoid.append("Volatility regime is EXTREME: option spreads can gap through both strikes; stops are unreliable.")
    if vol_regime == "INSUFFICIENT DATA":
        avoid.append("Volatility regime could not be classified (needs ~60+ bars of ATR history).")
    if rsi_v >= 70:
        avoid.append("RSI >= 70: market is stretched; chasing bullish setups here has poor historical risk/reward.")
    if rsi_v <= 30:
        avoid.append("RSI <= 30: market is washed out; shorting here risks a sharp relief rally.")
    if not np.isnan(vol_ratio) and vol_ratio < 0.6:
        avoid.append(f"Volume is only {vol_ratio:.0%} of its 20-day average: low participation, moves are less trustworthy.")
    if india_vix is not None:
        if india_vix >= 20:
            avoid.append(f"India VIX {india_vix:.1f} is elevated (>=20): premiums are rich but gap risk is high.")
        elif india_vix <= 11:
            avoid.append(f"India VIX {india_vix:.1f} is very low (<=11): credit spreads collect little premium for the risk taken.")
    else:
        avoid.append("India VIX not available: implied-volatility context is missing (INSUFFICIENT DATA).")
    for note in event_risk_notes or []:
        avoid.append("Event risk: " + note)
    hours_old = (pd.Timestamp.now(tz="UTC") - (ts.tz_localize("UTC") if ts.tzinfo is None else ts)).total_seconds() / 3600
    if hours_old > 72:
        avoid.append(f"Data is {hours_old / 24:.0f} days old; do not act on stale signals.")

    # Decide signal -------------------------------------------------------------------
    bull_votes = len([c for c in conds if c.passed and c.direction == "bull"])
    bear_votes = len([c for c in conds if c.passed and c.direction == "bear"])
    filters_ok = all(c.passed for c in conds if c.direction == "filter")
    bull_total = len([c for c in conds if c.direction == "bull"])
    bear_total = len([c for c in conds if c.direction == "bear"])

    if not filters_ok:
        signal = SignalType.WAIT
    elif regime == Regime.BULLISH and bull_votes >= bull_total - 1:
        signal = SignalType.BULLISH_SETUP
    elif regime == Regime.BEARISH and bear_votes >= bear_total - 1:
        signal = SignalType.BEARISH_SETUP
    elif regime in (Regime.NEUTRAL, Regime.UNCERTAIN) and any(c.passed for c in conds if c.direction == "neutral") and abs(bull_votes - bear_votes) <= 2 and 40 <= rsi_v <= 60:
        signal = SignalType.NEUTRAL_SETUP
    else:
        signal = SignalType.WAIT

    # Levels / plan ------------------------------------------------------------
    levels = support_resistance_levels(hist, as_of=ts)
    strategies: list[str] = []
    plan: dict[str, str] = {}
    invalidation: list[str] = []
    one_atr = f"{atr_v:,.0f} pts ({atr_pct:.2%})"
    if signal == SignalType.BULLISH_SETUP:
        strategies = ["Bull put credit spread (short put ~1.5-2 ATR below spot, long put one strike interval lower)"]
        plan = {
            "entry": "Hypothetical: open spread on next session if close still above SMA20 and EMA9 > EMA21.",
            "exit_profit": "Buy back the spread at 50-60% of the credit received, or 5 trading days before expiry.",
            "exit_loss": "Close if the index closes below the short put strike OR the spread's loss reaches 1.5x credit. Note: a stop is an instruction, not a guarantee of fill price.",
            "atr": one_atr,
        }
        invalidation = ["Daily close below the 20-day SMA", "EMA9 crosses below EMA21", "Close below nearest support level", "Volatility regime flips to EXTREME"]
    elif signal == SignalType.BEARISH_SETUP:
        strategies = ["Bear call credit spread (short call ~1.5-2 ATR above spot, long call one strike interval higher)"]
        plan = {
            "entry": "Hypothetical: open spread on next session if close still below SMA20 and EMA9 < EMA21.",
            "exit_profit": "Buy back the spread at 50-60% of the credit received, or 5 trading days before expiry.",
            "exit_loss": "Close if the index closes above the short call strike OR the spread's loss reaches 1.5x credit. A stop does not guarantee the fill price.",
            "atr": one_atr,
        }
        invalidation = ["Daily close above the 20-day SMA", "EMA9 crosses above EMA21", "Close above nearest resistance level", "Volatility regime flips to EXTREME"]
    elif signal == SignalType.NEUTRAL_SETUP:
        strategies = ["Iron condor (RESEARCH ONLY): short strikes ~2 ATR either side, wings one interval wider"]
        plan = {
            "entry": "Hypothetical: open when realised vol is falling and no major event is inside the holding window.",
            "exit_profit": "Buy back at 50% of credit received.",
            "exit_loss": "Close the threatened side if the index closes beyond a short strike; never add to a losing condor.",
            "atr": one_atr,
        }
        invalidation = ["Daily close outside the Bollinger Bands", "Bollinger width expanding above its recent median", "Scheduled high-impact event inside the holding window"]
    else:
        strategies = ["No strategy — conditions are mixed. Keep researching; cash is a position."]
        invalidation = ["N/A"]

    values: dict[str, float | str] = {
        "close": close, "sma20": sma20, "sma50": _f(row["sma50"]), "sma200": _f(row["sma200"]), "ema9": ema9, "ema21": ema21,
        "rsi14": rsi_v, "macd": macd_v, "macd_signal": sig_v, "macd_hist": hist_v, "atr14": atr_v, "atr_pct": atr_pct,
        "bb_pct_b": bb_pct, "bb_width": bb_width, "rv20": rv20, "vol_regime": vol_regime, "vol_ratio": vol_ratio,
    }
    if india_vix is not None:
        values["india_vix"] = india_vix

    return SignalReport(signal=signal, regime=regime, as_of=ts, indicator_values=values, conditions=conds, reasons_to_avoid=avoid, invalidation=invalidation, strategy_candidates=strategies, hypothetical_plan=plan, levels=levels)


def evaluate_from_ohlcv(df: pd.DataFrame, **kwargs) -> SignalReport:
    return evaluate(compute_indicator_frame(df), **kwargs)
