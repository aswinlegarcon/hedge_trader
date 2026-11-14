"""Local paper execution engine — no broker order HTTP (Spec 08)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from .paper_accounting import allocate_proportional
from .fill_validation import validate_entry_admission_economics
from .gate import evaluate_entry, resolved_candidate_risk
from .ledger.store import ExecutionLedger
from .modes import ExecutionMode
from .types import OrderSide, TradeCandidate


@dataclass
class PaperSubmitResult:
    local_id: str
    filled_qty: int
    message: str


def submit_paper_entry(
    ledger: ExecutionLedger,
    candidate: TradeCandidate,
    *,
    slippage_pct: float,
) -> PaperSubmitResult:
    """Paper entry fill — fees are the confirmed modeled entry_cost_inr (simulation, not broker verified)."""
    if candidate.mode != ExecutionMode.PAPER:
        raise ValueError("Paper engine accepts PAPER mode only.")
    if candidate.quote is None:
        raise ValueError("Quote required.")
    validate_entry_admission_economics(candidate.entry_cost_inr, slippage_pct)
    if not candidate.quote.is_valid():
        raise ValueError("Quote must be finite, positive and non-crossed.")
    ctx = ledger.portfolio_context()
    gate = evaluate_entry(candidate, ctx)
    if not gate.allowed:
        raise ValueError("; ".join(gate.reasons) or "Entry blocked.")
    local_id = str(uuid.uuid4())
    risk = resolved_candidate_risk(candidate) or gate.planned_risk_inr
    ledger.create_reservation(candidate, local_id, risk)
    q = candidate.quote
    if candidate.side == OrderSide.BUY:
        marketable_px = q.ask * (1 + slippage_pct)
        if marketable_px > candidate.limit_price_inr:
            return PaperSubmitResult(local_id, 0, "Buy limit below ask — order stays pending.")
        fill_qty = min(candidate.quantity, max(q.ask_qty, 0))
        px = marketable_px
    else:
        marketable_px = q.bid * (1 - slippage_pct)
        if marketable_px < candidate.limit_price_inr:
            return PaperSubmitResult(local_id, 0, "Sell limit above bid — order stays pending.")
        fill_qty = min(candidate.quantity, max(q.bid_qty, 0))
        px = marketable_px
    if fill_qty <= 0 or px <= 0:
        return PaperSubmitResult(local_id, 0, "Limit not marketable against visible depth; order stays pending.")
    fill_fee, _ = allocate_proportional(candidate.entry_cost_inr, fill_qty, candidate.quantity)
    fill_event_id = f"{local_id}:paper:{uuid.uuid4()}"
    ledger.apply_paper_fill(
        local_id, fill_qty=fill_qty, fill_price=px, fees=fill_fee, fill_event_id=fill_event_id
    )
    suffix = ""
    if fill_qty < candidate.quantity:
        suffix = f" Remainder {candidate.quantity - fill_qty} units still reserved."
    return PaperSubmitResult(local_id, fill_qty, f"Paper fill {fill_qty} @ ₹{px:.2f} (modeled).{suffix}")