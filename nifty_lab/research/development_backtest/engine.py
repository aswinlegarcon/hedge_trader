"""Frozen ICICIBANK daily pullback simulator (development bars only)."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

import pandas as pd

from .config import (
    ENTRY_ALLOCATION_CEILING,
    INITIAL_CASH,
    MAX_PLANNED_STOP_INR,
    MEDIAN_VOLUME_LOOKBACK,
    RISK_HALT_INITIAL_LOSS,
    RISK_HALT_PEAK_DRAWDOWN,
    STRATEGY_ID,
    TIME_EXIT_SESSIONS,
    WARMUP_BARS,
    money_quantize,
)
from .indicators import ema_series, rolling_median_excluding_current
from .money import adverse_buy_fill, adverse_sell_fill, modeled_fee
from .validate import validate_development_frame


@dataclass
class SignalRecord:
    signal_ts: str
    action: Literal["OPPORTUNITY", "SKIP"]
    reason: str
    candidate_id: str


@dataclass
class TradeRecord:
    entry_ts: str
    exit_ts: str
    qty: int
    entry_raw_open: str
    entry_fill: str
    exit_raw_reference: str
    exit_fill: str
    stop: str
    target: str
    planned_risk_inr: str
    entry_fee_inr: str
    exit_fee_inr: str
    entry_slippage_inr: str
    exit_slippage_inr: str
    net_pnl_inr: str
    exit_reason: str


@dataclass
class EquityPoint:
    ts: str
    cash_inr: str
    gross_equity_inr: str
    net_liquidation_inr: str
    exposure_pct: str


@dataclass
class SimulationResult:
    strategy_id: str
    signals: list[SignalRecord] = field(default_factory=list)
    trades: list[TradeRecord] = field(default_factory=list)
    equity_curve: list[EquityPoint] = field(default_factory=list)
    opportunity_count: int = 0
    admission_skips: int = 0
    skipped_while_holding: int = 0
    skipped_exit_session: int = 0
    skipped_halted: int = 0
    halted_new_entries: bool = False
    ambiguous_same_bar: int = 0
    boundary_forced_exits: int = 0
    total_fees_inr: str = "0.00"
    turnover_notional_inr: str = "0.00"


def _d(x: float) -> Decimal:
    return Decimal(str(x))


def _net_liquidation(cash: Decimal, qty: int, close: Decimal) -> Decimal:
    if qty <= 0:
        return money_quantize(cash)
    exit_ref = adverse_sell_fill(close)
    notional = Decimal(qty) * exit_ref
    fee = modeled_fee(notional)
    return money_quantize(cash + notional - fee)


def _planned_stop_loss(qty: int, entry_fill: Decimal, stop_raw: Decimal) -> Decimal:
    stop_exit = adverse_sell_fill(stop_raw)
    entry_notional = Decimal(qty) * entry_fill
    stop_notional = Decimal(qty) * stop_exit
    loss = Decimal(qty) * (entry_fill - stop_exit)
    return money_quantize(loss + modeled_fee(entry_notional) + modeled_fee(stop_notional))


def _max_shares(cash: Decimal, entry_fill: Decimal, stop_raw: Decimal) -> int:
    if entry_fill <= stop_raw or entry_fill <= 0:
        return 0
    budget = min(cash, ENTRY_ALLOCATION_CEILING)
    upper = int(budget // entry_fill) + 1
    for q in range(upper, 0, -1):
        cost = Decimal(q) * entry_fill + modeled_fee(Decimal(q) * entry_fill)
        if cost > budget:
            continue
        if cost > cash:
            continue
        if _planned_stop_loss(q, entry_fill, stop_raw) > MAX_PLANNED_STOP_INR:
            continue
        return q
    return 0


def _exit_reference(
    *,
    open_p: Decimal,
    high_p: Decimal,
    low_p: Decimal,
    stop: Decimal,
    target: Decimal,
) -> tuple[Decimal | None, str, bool]:
    ambiguous = False
    stop_hit = low_p <= stop or open_p <= stop
    target_hit = high_p >= target or open_p >= target
    if stop_hit and target_hit:
        ambiguous = True
        if open_p <= stop:
            return open_p, "STOP_GAP", ambiguous
        return stop, "STOP", ambiguous
    if open_p <= stop:
        return open_p, "STOP_GAP", ambiguous
    if low_p <= stop:
        return stop, "STOP", ambiguous
    if open_p >= target:
        return target, "TARGET_GAP", ambiguous
    if high_p >= target:
        return target, "TARGET", ambiguous
    return None, "", ambiguous


def _signal_rule(i: int, *, c, l, ema20, ema50, volumes) -> bool:
    if i < WARMUP_BARS - 1 or i < MEDIAN_VOLUME_LOOKBACK:
        return False
    med = rolling_median_excluding_current(volumes[i - MEDIAN_VOLUME_LOOKBACK : i])
    if med is None:
        return False
    return bool(c > _d(ema20[i]) > _d(ema50[i]) and l <= _d(ema20[i]) and _d(volumes[i]) >= _d(med))


def simulate_development(df: pd.DataFrame) -> SimulationResult:
    from .splits import simulate_development as _split_development

    return _split_development(df)
