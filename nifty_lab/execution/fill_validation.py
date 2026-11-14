"""Shared Paper fill / close economics validation (Spec 08)."""
from __future__ import annotations

import math

from .types import QuoteSnapshot


def validate_fill_economics(
    *,
    fill_qty: int,
    fill_price: float,
    fees: float,
    fill_event_id: str,
    slippage_pct: float | None = None,
) -> None:
    if not fill_event_id or not str(fill_event_id).strip():
        raise ValueError("fill_event_id is required for replay-safe fills.")
    if fill_qty <= 0 or fill_qty != int(fill_qty):
        raise ValueError("Fill quantity must be a positive integer.")
    if not math.isfinite(fill_price) or fill_price <= 0:
        raise ValueError("Fill price must be finite and positive.")
    if fees < 0 or not math.isfinite(fees):
        raise ValueError("Fees must be finite and non-negative.")
    if slippage_pct is not None:
        if not math.isfinite(slippage_pct) or slippage_pct < 0:
            raise ValueError("Slippage must be finite and non-negative.")


def validate_entry_admission_economics(
    entry_cost_inr: float,
    slippage_pct: float,
) -> None:
    if not math.isfinite(entry_cost_inr) or entry_cost_inr < 0:
        raise ValueError("Entry fees must be finite and non-negative.")
    if not math.isfinite(slippage_pct) or slippage_pct < 0:
        raise ValueError("Slippage must be finite and non-negative.")


def validate_close_admission_economics(
    exit_fees_inr: float | None,
    slippage_pct: float | None,
) -> None:
    if exit_fees_inr is not None:
        if not math.isfinite(exit_fees_inr) or exit_fees_inr < 0:
            raise ValueError("Exit fees must be finite and non-negative.")
    if slippage_pct is not None:
        if not math.isfinite(slippage_pct) or slippage_pct < 0:
            raise ValueError("Slippage must be finite and non-negative.")


def validate_execution_quote(quote: QuoteSnapshot, *, instrument_key: str) -> None:
    if quote.instrument_key != instrument_key:
        raise ValueError("Quote instrument does not match close order.")
    if not quote.is_valid():
        raise ValueError("Quote prices must be finite and positive.")
    if not quote.is_fresh():
        raise ValueError("Quote is stale — request a new observation.")
