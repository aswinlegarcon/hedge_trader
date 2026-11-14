"""Descriptive development metrics (exploratory only)."""
from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

import pandas as pd

from .config import INITIAL_CASH, WARMUP_BARS, money_quantize
from .engine import SimulationResult, TradeRecord
from .money import adverse_buy_fill, adverse_sell_fill, modeled_fee


def _wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if n <= 0:
        return None, None
    p = wins / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    margin = z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n) / denom
    return centre - margin, centre + margin


def _max_buy_hold_shares(entry_fill: Decimal) -> int:
    for q in range(int(INITIAL_CASH // entry_fill), 0, -1):
        cost = Decimal(q) * entry_fill + modeled_fee(Decimal(q) * entry_fill)
        if cost <= INITIAL_CASH:
            return q
    return 0


def summarize_trades(trades: list[TradeRecord], sim: SimulationResult | None = None) -> dict[str, Any]:
    closed = len(trades)
    pnls = [Decimal(t.net_pnl_inr) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    flats = [p for p in pnls if p == 0]
    gross_win = sum(wins, Decimal("0"))
    gross_loss = sum(losses, Decimal("0"))
    if gross_loss == 0:
        profit_factor: str | float = "undefined" if gross_win > 0 else "n/a"
    else:
        profit_factor = float(money_quantize(gross_win / abs(gross_loss)))
    expectancy = money_quantize(sum(pnls, Decimal("0")) / closed) if closed else Decimal("0")
    lo, hi = _wilson_interval(len(wins), closed)
    entry_fees = sum((Decimal(t.entry_fee_inr) for t in trades), Decimal("0"))
    exit_fees = sum((Decimal(t.exit_fee_inr) for t in trades), Decimal("0"))
    entry_slip = sum((Decimal(t.entry_slippage_inr) for t in trades), Decimal("0"))
    exit_slip = sum((Decimal(t.exit_slippage_inr) for t in trades), Decimal("0"))
    out: dict[str, Any] = {
        "closed_trades": closed,
        "wins": len(wins),
        "losses": len(losses),
        "breakevens": len(flats),
        "win_rate": (len(wins) / closed) if closed else None,
        "win_rate_wilson_95_lo": lo,
        "win_rate_wilson_95_hi": hi,
        "avg_net_win": str(money_quantize(sum(wins, Decimal("0")) / len(wins))) if wins else None,
        "avg_net_loss": str(money_quantize(sum(losses, Decimal("0")) / len(losses))) if losses else None,
        "net_expectancy_per_trade": str(expectancy),
        "profit_factor": profit_factor,
        "net_pnl_inr": str(money_quantize(sum(pnls, Decimal("0")))),
        "modeled_entry_fees_inr": str(money_quantize(entry_fees)),
        "modeled_exit_fees_inr": str(money_quantize(exit_fees)),
        "modeled_entry_slippage_inr": str(money_quantize(entry_slip)),
        "modeled_exit_slippage_inr": str(money_quantize(exit_slip)),
        "fees_note": "Fees reported separately; slippage already in fill prices.",
        "modeled_fees_note": "Illustrative 10bps/side; not verified real tariffs.",
    }
    if sim is not None and sim.equity_curve:
        final_cash = Decimal(sim.equity_curve[-1].cash_inr)
        reconcile = money_quantize(final_cash - INITIAL_CASH)
        trade_sum = money_quantize(sum(pnls, Decimal("0")))
        out["cash_reconcile_delta_inr"] = str(money_quantize(reconcile - trade_sum))
        out["turnover_notional_inr"] = sim.turnover_notional_inr
        out["exposure_note"] = "Daily exposure_pct uses mark close; denominator gross_equity."
    return out


def equity_drawdown(equity: list[dict[str, str]]) -> dict[str, Any]:
    if not equity:
        return {"max_drawdown_inr": "0.00", "max_drawdown_pct": 0.0, "denominator": "net_liquidation_peak"}
    peak = Decimal(equity[0]["net_liquidation_inr"])
    max_dd = Decimal("0")
    max_dd_pct = 0.0
    for row in equity:
        net = Decimal(row["net_liquidation_inr"])
        peak = max(peak, net)
        dd = peak - net
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = float(dd / peak) if peak > 0 else 0.0
    return {
        "max_drawdown_inr": str(money_quantize(max_dd)),
        "max_drawdown_pct": max_dd_pct,
        "denominator": "net_liquidation_peak",
    }


def cash_baseline_final(df: pd.DataFrame) -> str:
    return str(INITIAL_CASH)


def buy_hold_baseline_independent(df: pd.DataFrame) -> dict[str, Any]:
    """First through last session in frame (e.g. 2024 only); fees in sizing."""
    if df.empty:
        return {"status": "EMPTY"}
    entry_bar = df.iloc[0]
    exit_bar = df.iloc[-1]
    entry_raw = Decimal(str(entry_bar["open"]))
    exit_raw = Decimal(str(exit_bar["close"]))
    entry_fill = adverse_buy_fill(entry_raw)
    shares = _max_buy_hold_shares(entry_fill)
    if shares <= 0:
        return {"status": "NO_SHARES"}
    cost = Decimal(shares) * entry_fill + modeled_fee(Decimal(shares) * entry_fill)
    cash_left = money_quantize(INITIAL_CASH - cost)
    if cash_left < 0:
        return {"status": "NEGATIVE_CASH", "cash_left": str(cash_left)}
    exit_fill = adverse_sell_fill(exit_raw)
    proceeds = Decimal(shares) * exit_fill - modeled_fee(Decimal(shares) * exit_fill)
    final = money_quantize(cash_left + proceeds)
    return {
        "status": "OK",
        "shares": shares,
        "entry_session": str(entry_bar.name),
        "exit_session": str(exit_bar.name),
        "entry_raw_open": str(entry_raw),
        "entry_fill": str(entry_fill),
        "remaining_cash_after_buy": str(cash_left),
        "final_equity_inr": str(final),
        "net_pnl_inr": str(money_quantize(final - INITIAL_CASH)),
        "convention": "First observed evaluation open to last evaluation close; fees in sizing.",
    }


def buy_hold_baseline(df: pd.DataFrame) -> dict[str, Any]:
    if len(df) <= WARMUP_BARS:
        return {"status": "INSUFFICIENT_BARS"}
    entry_bar = df.iloc[WARMUP_BARS]
    exit_bar = df.iloc[-1]
    entry_raw = Decimal(str(entry_bar["open"]))
    exit_raw = Decimal(str(exit_bar["close"]))
    entry_fill = adverse_buy_fill(entry_raw)
    shares = _max_buy_hold_shares(entry_fill)
    if shares <= 0:
        return {"status": "NO_SHARES"}
    cost = Decimal(shares) * entry_fill + modeled_fee(Decimal(shares) * entry_fill)
    cash_left = money_quantize(INITIAL_CASH - cost)
    if cash_left < 0:
        return {"status": "NEGATIVE_CASH", "cash_left": str(cash_left)}
    exit_fill = adverse_sell_fill(exit_raw)
    proceeds = Decimal(shares) * exit_fill - modeled_fee(Decimal(shares) * exit_fill)
    final = money_quantize(cash_left + proceeds)
    return {
        "status": "OK",
        "shares": shares,
        "entry_session": str(entry_bar.name),
        "exit_session": str(exit_bar.name),
        "entry_raw_open": str(entry_raw),
        "entry_fill": str(entry_fill),
        "remaining_cash_after_buy": str(cash_left),
        "final_equity_inr": str(final),
        "net_pnl_inr": str(money_quantize(final - INITIAL_CASH)),
        "convention": "Whole shares at bar[WARMUP] open; fees on entry/exit notional; adverse slippage in fills.",
    }


def yearly_trade_breakdown(trades: list[TradeRecord]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for t in trades:
        year = pd.Timestamp(t.exit_ts).year
        key = str(year)
        out.setdefault(key, {"trades": 0, "wins": 0, "losses": 0})
        out[key]["trades"] += 1
        pnl = Decimal(t.net_pnl_inr)
        if pnl > 0:
            out[key]["wins"] += 1
        elif pnl < 0:
            out[key]["losses"] += 1
    return out
