"""Paper position accounting — paise rounding (Spec 08 close slice)."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def to_paise(amount: float) -> int:
    return int(Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)


def from_paise(paise: int) -> float:
    return float(Decimal(paise) / 100)


def allocate_proportional(total_inr: float, closed_qty: int, total_qty: int) -> tuple[float, float]:
    if total_qty <= 0 or closed_qty <= 0:
        return 0.0, float(total_inr)
    total_p = to_paise(total_inr)
    if closed_qty >= total_qty:
        return from_paise(total_p), 0.0
    closed_p = (total_p * closed_qty) // total_qty
    remain_p = total_p - closed_p
    return from_paise(closed_p), from_paise(remain_p)


def sell_realized(gross_proceeds: float, alloc_cost: float, alloc_entry_fees: float, exit_fees: float) -> tuple[float, float]:
    gross = gross_proceeds - alloc_cost
    net = gross - alloc_entry_fees - exit_fees
    return round(gross, 2), round(net, 2)
