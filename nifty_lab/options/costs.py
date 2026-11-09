"""Indian F&O transaction-cost model (options, NSE, discount broker).

Rates verified 2026-11-09 from https://zerodha.com/charges/ and the Zerodha
bulletin on STT revision effective 2026-04-01. Kotak Neo brokerage differs by
plan; set ``brokerage_per_order`` accordingly. Rates change — see ``verified_on``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CostSchedule:
    brokerage_per_order: float = 20.0          # flat per executed order (Zerodha F&O)
    stt_sell_pct: float = 0.0015               # 0.15% of premium, sell side (from 1-Apr-2026)
    stt_exercise_pct: float = 0.0015           # 0.15% of intrinsic value if long option exercised at expiry
    exchange_txn_pct: float = 0.0003553        # NSE 0.03553% of premium, both sides
    sebi_fee_pct: float = 0.000001             # ₹10 per crore of premium turnover
    stamp_duty_buy_pct: float = 0.00003        # 0.003% of premium, buy side
    ipft_pct: float = 0.0000000001             # ₹0.01 per crore (negligible, kept for completeness)
    gst_pct: float = 0.18                      # on brokerage + exchange txn + SEBI fee
    verified_on: date = date(2026, 11, 9)
    source: str = "https://zerodha.com/charges/ ; Zerodha bulletin 445377 (STT from 2026-04-01)"


DEFAULT_COSTS = CostSchedule()


@dataclass(frozen=True)
class CostBreakdown:
    brokerage: float
    stt: float
    exchange_txn: float
    sebi_fee: float
    stamp_duty: float
    gst: float
    total: float


def option_order_costs(premium: float, quantity: int, side: str, schedule: CostSchedule = DEFAULT_COSTS) -> CostBreakdown:
    """Costs for ONE executed option order.

    premium: per-unit price; quantity: units (lots * lot_size); side: 'BUY'/'SELL'.
    """
    side = side.upper()
    if side not in ("BUY", "SELL"):
        raise ValueError("side must be BUY or SELL")
    if premium < 0 or quantity <= 0:
        raise ValueError("premium must be >= 0 and quantity > 0")
    turnover = premium * quantity
    brokerage = schedule.brokerage_per_order if turnover > 0 else 0.0
    stt = turnover * schedule.stt_sell_pct if side == "SELL" else 0.0
    exch = turnover * schedule.exchange_txn_pct
    sebi = turnover * schedule.sebi_fee_pct
    stamp = turnover * schedule.stamp_duty_buy_pct if side == "BUY" else 0.0
    ipft = turnover * schedule.ipft_pct
    gst = (brokerage + exch + sebi) * schedule.gst_pct
    total = brokerage + stt + exch + sebi + stamp + ipft + gst
    return CostBreakdown(brokerage, stt, exch + ipft, sebi, stamp, gst, total)


def round_trip_costs(entry_premium: float, exit_premium: float, quantity: int, entry_side: str, schedule: CostSchedule = DEFAULT_COSTS) -> float:
    """Total cost to open a leg and close it before expiry."""
    exit_side = "SELL" if entry_side.upper() == "BUY" else "BUY"
    return option_order_costs(entry_premium, quantity, entry_side, schedule).total + option_order_costs(exit_premium, quantity, exit_side, schedule).total
