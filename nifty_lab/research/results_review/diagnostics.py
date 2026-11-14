"""Fixed-fill additive cost diagnostics (no engine rerun)."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any

from .config import EXTRA_INR_PER_EXECUTION, INITIAL_CASH_INR, REPORTING_QUANT, STRESS_SCENARIOS_BPS


def _d(value: str | int | float) -> Decimal:
    return Decimal(str(value))


def round_inr(amount: Decimal) -> Decimal:
    return amount.quantize(REPORTING_QUANT, rounding=ROUND_HALF_EVEN)


def executed_turnover_inr(trades: list[dict[str, Any]]) -> Decimal:
    total = Decimal("0")
    for t in trades:
        qty = _d(t["qty"])
        if qty <= 0:
            raise ValueError("NONPOSITIVE_QTY")
        entry = _d(t["entry_fill"])
        exit_ = _d(t["exit_fill"])
        if entry <= 0 or exit_ <= 0:
            raise ValueError("NONPOSITIVE_FILL")
        total += qty * entry + qty * exit_
    return round_inr(total)


def archived_net_pnl_inr(trades: list[dict[str, Any]]) -> Decimal:
    return round_inr(sum(_d(t["net_pnl_inr"]) for t in trades))


def extra_cost_bps(turnover: Decimal, bps: int) -> Decimal:
    if turnover <= 0:
        return Decimal("0.00")
    raw = turnover * Decimal(bps) / Decimal("10000")
    return round_inr(raw)


def break_even_bps(net_pnl: Decimal, turnover: Decimal) -> str | float:
    if net_pnl <= 0:
        return "ALREADY_NONPOSITIVE"
    if turnover <= 0:
        return "NO_TURNOVER"
    precise = net_pnl / turnover * Decimal("10000")
    return float(precise)


def fixed_fill_stress_table(
    trades: list[dict[str, Any]],
    *,
    book_label: str,
) -> dict[str, Any]:
    if not trades:
        return {
            "book": book_label,
            "status": "NO_TRADES",
            "closed_trades": 0,
            "scenarios": [],
        }
    turnover = executed_turnover_inr(trades)
    base_net = archived_net_pnl_inr(trades)
    closed = len(trades)
    scenarios: list[dict[str, Any]] = []

    scenarios.append(
        {
            "scenario_id": "BASE",
            "label": "Archived modeled net (unchanged)",
            "extra_cost_inr": "0.00",
            "diagnostic_net_pnl_inr": str(base_net),
            "note": "FIXED_FILL_DIAGNOSTIC",
        }
    )

    for bps in STRESS_SCENARIOS_BPS:
        if bps == 0:
            continue
        extra = extra_cost_bps(turnover, bps)
        diag = round_inr(base_net - extra)
        scenarios.append(
            {
                "scenario_id": f"EXTRA_{bps}BP",
                "label": f"Extra {bps} bps on executed turnover",
                "extra_bps": bps,
                "extra_cost_inr": str(extra),
                "diagnostic_net_pnl_inr": str(diag),
                "note": "FIXED_FILL_DIAGNOSTIC; does not re-simulate sizing/admission/exits",
            }
        )

    inr_exec_cost = round_inr(Decimal("2") * Decimal(closed) * EXTRA_INR_PER_EXECUTION)
    scenarios.append(
        {
            "scenario_id": "EXTRA_INR1_PER_EXECUTION",
            "label": "₹1 hypothetical per modeled entry and exit (2×closed trades)",
            "extra_cost_inr": str(inr_exec_cost),
            "diagnostic_net_pnl_inr": str(round_inr(base_net - inr_exec_cost)),
            "executions_counted": closed * 2,
            "note": "Separate from bps stresses; not a broker fill count claim",
        }
    )

    be = break_even_bps(base_net, turnover)
    return {
        "book": book_label,
        "status": "OK",
        "closed_trades": closed,
        "executed_turnover_inr": str(turnover),
        "archived_net_pnl_inr": str(base_net),
        "net_return_on_initial_capital": str(round_inr(base_net / INITIAL_CASH_INR * Decimal("100"))) + "%",
        "break_even_extra_bps": be,
        "scenarios": scenarios,
        "disclaimer": (
            "FIXED_FILL_DIAGNOSTIC: trades, qty, fills and portfolio path held fixed. "
            "Archived fees/slippage already inside net P&L — stresses are additive only."
        ),
    }
