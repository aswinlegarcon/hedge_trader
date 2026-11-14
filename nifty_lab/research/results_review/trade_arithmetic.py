"""Strict archived trade arithmetic checks (no simulation)."""
from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from .config import INITIAL_CASH_INR, REPORTING_QUANT

TRADE_REQUIRED_KEYS = (
    "qty",
    "entry_fill",
    "exit_fill",
    "entry_raw_open",
    "exit_raw_reference",
    "entry_fee_inr",
    "exit_fee_inr",
    "entry_slippage_inr",
    "exit_slippage_inr",
    "net_pnl_inr",
)


def round_inr(amount: Decimal) -> Decimal:
    return amount.quantize(REPORTING_QUANT, rounding=ROUND_HALF_UP)


def parse_finite_decimal(value: Any, *, allow_zero: bool = False, positive: bool = False) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, float, str)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not d.is_finite():
        return None
    if positive and d <= 0:
        return None
    if not allow_zero and d == 0:
        return None
    if not allow_zero and d < 0:
        if positive:
            return None
    return d


def parse_whole_share_qty(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        if value > 0:
            return value
        return None
    if isinstance(value, str) and value.isdigit():
        q = int(value)
        return q if q > 0 else None
    return None


def recompute_trade_net(qty: int, entry_fill: Decimal, exit_fill: Decimal, entry_fee: Decimal, exit_fee: Decimal) -> Decimal:
    gross = Decimal(qty) * (exit_fill - entry_fill)
    return round_inr(gross - entry_fee - exit_fee)


def recompute_entry_slip(qty: int, entry_fill: Decimal, entry_raw: Decimal) -> Decimal:
    return round_inr(Decimal(qty) * (entry_fill - entry_raw))


def recompute_exit_slip(qty: int, exit_ref: Decimal, exit_fill: Decimal) -> Decimal:
    return round_inr(Decimal(qty) * (exit_ref - exit_fill))


def validate_trade_record(t: Any, idx: int) -> str | None:
    if not isinstance(t, dict):
        return "TRADE_SHAPE"
    for key in TRADE_REQUIRED_KEYS:
        if key not in t:
            return "TRADE_MISSING_FIELD"
    qty = parse_whole_share_qty(t["qty"])
    if qty is None:
        return "TRADE_QTY"
    entry_fill = parse_finite_decimal(t["entry_fill"], positive=True)
    exit_fill = parse_finite_decimal(t["exit_fill"], positive=True)
    entry_raw = parse_finite_decimal(t["entry_raw_open"], positive=True)
    exit_ref = parse_finite_decimal(t["exit_raw_reference"], positive=True)
    entry_fee = parse_finite_decimal(t["entry_fee_inr"], allow_zero=True)
    exit_fee = parse_finite_decimal(t["exit_fee_inr"], allow_zero=True)
    entry_slip = parse_finite_decimal(t["entry_slippage_inr"], allow_zero=True)
    exit_slip = parse_finite_decimal(t["exit_slippage_inr"], allow_zero=True)
    recorded_net = parse_finite_decimal(t["net_pnl_inr"], allow_zero=True)
    if None in (entry_fill, exit_fill, entry_raw, exit_ref, entry_fee, exit_fee, entry_slip, exit_slip, recorded_net):
        return "TRADE_BAD_SCALAR"
    if entry_fee < 0 or exit_fee < 0 or entry_slip < 0 or exit_slip < 0:
        return "TRADE_NEGATIVE_COST"
    calc_net = recompute_trade_net(qty, entry_fill, exit_fill, entry_fee, exit_fee)
    if calc_net != recorded_net:
        return "TRADE_NET_IDENTITY"
    if recompute_entry_slip(qty, entry_fill, entry_raw) != entry_slip:
        return "TRADE_ENTRY_SLIP"
    if recompute_exit_slip(qty, exit_ref, exit_fill) != exit_slip:
        return "TRADE_EXIT_SLIP"
    return None


def executed_turnover_from_trades(trades: list[dict]) -> Decimal:
    total = Decimal("0")
    for t in trades:
        qty = parse_whole_share_qty(t["qty"])
        entry = parse_finite_decimal(t["entry_fill"], positive=True)
        exit_ = parse_finite_decimal(t["exit_fill"], positive=True)
        if qty is None or entry is None or exit_ is None:
            raise ValueError("TRADE_TURNOVER")
        total += Decimal(qty) * entry + Decimal(qty) * exit_
    return round_inr(total)


def validate_summary_trades_equity(
    trades: list[dict],
    summary: dict,
    equity: list[dict],
) -> tuple[dict[str, str], str | None]:
    if not isinstance(summary, dict):
        return {}, "SUMMARY_SHAPE"
    for req in ("closed_trades", "net_pnl_inr", "final_cash_inr", "cash_reconcile_delta_inr"):
        if req not in summary:
            return {}, "SUMMARY_MISSING_FIELD"
    if not equity:
        return {}, "EQUITY_EMPTY"
    if not isinstance(equity, list):
        return {}, "EQUITY_SHAPE"

    closed = summary.get("closed_trades")
    if not isinstance(closed, int) or closed != len(trades):
        return {}, "SUMMARY_TRADE_COUNT"

    trade_nets: list[Decimal] = []
    entry_fees = Decimal("0")
    exit_fees = Decimal("0")
    wins = losses = flats = 0
    for t in trades:
        err = validate_trade_record(t, 0)
        if err:
            return {}, err
        qty = parse_whole_share_qty(t["qty"])
        assert qty is not None
        ef = parse_finite_decimal(t["entry_fee_inr"], allow_zero=True)
        xf = parse_finite_decimal(t["exit_fee_inr"], allow_zero=True)
        net = parse_finite_decimal(t["net_pnl_inr"], allow_zero=True)
        assert ef is not None and xf is not None and net is not None
        entry_fees += ef
        exit_fees += xf
        trade_nets.append(net)
        if net > 0:
            wins += 1
        elif net < 0:
            losses += 1
        else:
            flats += 1

    trade_sum = round_inr(sum(trade_nets, Decimal("0")))
    summary_net = parse_finite_decimal(summary["net_pnl_inr"], allow_zero=True)
    if summary_net is None or summary_net != trade_sum:
        return {}, "SUMMARY_NET_MISMATCH"

    if summary.get("wins") != wins or summary.get("losses") != losses:
        return {}, "SUMMARY_WIN_LOSS"
    if summary.get("breakevens") != flats:
        return {}, "SUMMARY_BREAKEVEN"

    sum_entry = parse_finite_decimal(summary.get("modeled_entry_fees_inr"), allow_zero=True)
    sum_exit = parse_finite_decimal(summary.get("modeled_exit_fees_inr"), allow_zero=True)
    if sum_entry is None or sum_exit is None:
        return {}, "SUMMARY_FEE_FIELD"
    if round_inr(entry_fees) != round_inr(sum_entry) or round_inr(exit_fees) != round_inr(sum_exit):
        return {}, "SUMMARY_FEE_TOTAL"

    turnover = executed_turnover_from_trades(trades)
    reported_turnover = parse_finite_decimal(summary.get("turnover_notional_inr"), positive=True)
    if reported_turnover is None or reported_turnover != turnover:
        return {}, "SUMMARY_TURNOVER"

    last = equity[-1]
    if not isinstance(last, dict):
        return {}, "EQUITY_POINT_SHAPE"
    final_cash = parse_finite_decimal(last.get("cash_inr"), allow_zero=True)
    final_net = parse_finite_decimal(last.get("net_liquidation_inr"), allow_zero=True)
    summary_final_cash = parse_finite_decimal(summary["final_cash_inr"], allow_zero=True)
    summary_final_net = parse_finite_decimal(summary.get("final_net_liquidation_inr"), allow_zero=True)
    if final_cash is None or final_net is None or summary_final_cash is None:
        return {}, "EQUITY_CASH_FIELD"
    if final_cash != summary_final_cash:
        return {}, "SUMMARY_FINAL_CASH"
    if summary_final_net is not None and summary_final_net != final_net:
        return {}, "SUMMARY_FINAL_NET"

    computed_delta = round_inr(final_cash - INITIAL_CASH_INR - trade_sum)
    declared_delta = parse_finite_decimal(summary["cash_reconcile_delta_inr"], allow_zero=True)
    if declared_delta is None:
        return {}, "SUMMARY_RECONCILE_FIELD"
    if computed_delta != Decimal("0.00") or declared_delta != Decimal("0.00"):
        return {}, "CASH_RECONCILE_NONZERO"

    prev_ts: str | None = None
    for pt in equity:
        if not isinstance(pt, dict):
            return {}, "EQUITY_POINT_SHAPE"
        ts = pt.get("ts")
        if not isinstance(ts, str) or not ts:
            return {}, "EQUITY_TS"
        if prev_ts is not None and ts < prev_ts:
            return {}, "EQUITY_ORDER"
        prev_ts = ts
        for field in ("cash_inr", "gross_equity_inr", "net_liquidation_inr"):
            if parse_finite_decimal(pt.get(field), allow_zero=True) is None:
                return {}, "EQUITY_NONFINITE"

    dd = summary.get("drawdown")
    if isinstance(dd, dict):
        mdd = parse_finite_decimal(dd.get("max_drawdown_inr"), allow_zero=True)
        if mdd is None or mdd < 0:
            return {}, "SUMMARY_DRAWDOWN"

    return {
        "trade_net_sum_inr": str(trade_sum),
        "summary_net_pnl_inr": str(summary_net),
        "final_cash_inr": str(final_cash),
        "cash_reconcile_delta_inr": "0.00",
        "executed_turnover_inr": str(turnover),
    }, None
