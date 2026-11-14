"""Deterministic monetary arithmetic."""
from __future__ import annotations

from decimal import Decimal

from .config import FEE_BPS, SLIPPAGE_BPS, money_quantize


def adverse_buy_fill(raw_price: Decimal) -> Decimal:
    return money_quantize(raw_price * (Decimal(1) + SLIPPAGE_BPS / Decimal(10000)))


def adverse_sell_fill(raw_price: Decimal) -> Decimal:
    return money_quantize(raw_price * (Decimal(1) - SLIPPAGE_BPS / Decimal(10000)))


def modeled_fee(notional: Decimal) -> Decimal:
    if notional <= 0:
        return Decimal("0.00")
    return money_quantize(notional * FEE_BPS / Decimal(10000))
