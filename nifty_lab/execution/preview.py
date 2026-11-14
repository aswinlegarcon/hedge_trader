"""Single-use preview / confirmation (Spec 08)."""
from __future__ import annotations

import copy
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .fill_validation import validate_close_admission_economics, validate_entry_admission_economics
from .gate import ExecutionGateResult, evaluate_entry
from .gate import ExecutionPortfolioContext
from .policy import EXECUTION_V1
from .types import TradeCandidate


@dataclass
class PreviewTicket:
    preview_id: str
    candidate: TradeCandidate
    identity_hash: str
    created_at: datetime
    reviewed_at: datetime
    expires_at: datetime
    gate: ExecutionGateResult
    confirm_label: str
    consumed: bool = False
    warnings: list[str] = field(default_factory=list)
    close_intent_id: str | None = None
    exit_fees_inr: float | None = None
    slippage_pct: float | None = None
    observation_id: str | None = None


def _hash_identity(candidate: TradeCandidate) -> str:
    return hashlib.sha256(candidate.ticket_identity().encode()).hexdigest()[:24]


def build_preview(
    candidate: TradeCandidate,
    context: ExecutionPortfolioContext | None,
    *,
    for_reduce_only: bool | None = None,
    slippage_pct: float = 0.0,
) -> PreviewTicket:
    """Preserve original quote source time/provenance; reviewed_at is separate metadata."""
    now = datetime.now(timezone.utc)
    snapshot = copy.deepcopy(candidate)
    reduce = for_reduce_only if for_reduce_only is not None else snapshot.side.value == "SELL"
    if not reduce:
        validate_entry_admission_economics(snapshot.entry_cost_inr, slippage_pct)
        if snapshot.quote is not None and not snapshot.quote.is_valid():
            raise ValueError("Quote must be finite, positive and non-crossed.")
    gate = evaluate_entry(snapshot, context, for_reduce_only=reduce)
    label = (
        f"Submit {snapshot.mode.value} {snapshot.side.value} "
        f"{snapshot.quantity} {snapshot.trading_symbol} limit ₹{snapshot.limit_price_inr:.2f}"
    )
    return PreviewTicket(
        preview_id=str(uuid.uuid4()),
        candidate=snapshot,
        identity_hash=_hash_identity(snapshot),
        created_at=now,
        reviewed_at=now,
        expires_at=now + timedelta(seconds=EXECUTION_V1.confirmation_ttl_seconds),
        gate=gate,
        confirm_label=label,
        warnings=list(gate.warnings),
        slippage_pct=float(slippage_pct) if not reduce else None,
    )


def confirm_preview(
    ticket: PreviewTicket,
    context: ExecutionPortfolioContext | None,
    *,
    slippage_pct: float | None = None,
    entry_cost_inr: float | None = None,
) -> tuple[bool, str]:
    if ticket.consumed:
        return False, "Confirmation already used."
    now = datetime.now(timezone.utc)
    if now > ticket.expires_at:
        return False, "Preview expired — request a new preview."
    if _hash_identity(ticket.candidate) != ticket.identity_hash:
        return False, "Ticket identity changed."
    if context is None:
        return False, "Fresh portfolio context required at confirm."
    if ticket.candidate.quote is not None and not ticket.candidate.quote.is_fresh(now=now):
        return False, "Quote TTL expired — request a new preview."
    reduce = ticket.candidate.side.value == "SELL"
    if not reduce:
        if slippage_pct is None or ticket.slippage_pct is None:
            return False, "Invalid entry preview — request a new preview."
        if abs(ticket.slippage_pct - slippage_pct) > 1e-12:
            return False, "Entry slippage changed — request a new preview."
        if entry_cost_inr is not None and abs(ticket.candidate.entry_cost_inr - entry_cost_inr) > 1e-9:
            return False, "Entry fees changed — request a new preview."
    fresh = evaluate_entry(ticket.candidate, context, for_reduce_only=reduce)
    if not fresh.allowed:
        return False, "Funding/risk context changed — request a new preview."
    if not ticket.gate.allowed:
        return False, "Preview is not eligible."
    ticket.consumed = True
    return True, "Confirmed"


def build_close_preview(
    candidate: TradeCandidate,
    context: ExecutionPortfolioContext | None,
    *,
    exit_fees_inr: float,
    slippage_pct: float = 0.0,
) -> PreviewTicket:
    """Paper close preview with durable intent, fees, slippage and source observation id."""
    from .paper_close import new_close_intent_id, quote_observation_id

    validate_close_admission_economics(exit_fees_inr, slippage_pct)
    ticket = build_preview(candidate, context, for_reduce_only=True)
    if candidate.quote is None:
        raise ValueError("Close preview requires a quote.")
    ticket.close_intent_id = new_close_intent_id()
    ticket.exit_fees_inr = float(exit_fees_inr)
    ticket.slippage_pct = float(slippage_pct)
    ticket.observation_id = quote_observation_id(candidate.quote)
    ticket.confirm_label = (
        f"Confirm Paper close {candidate.quantity} {candidate.trading_symbol} "
        f"limit ₹{candidate.limit_price_inr:.2f} · exit fees ₹{exit_fees_inr:.2f}"
    )
    return ticket


def confirm_close_preview(
    ticket: PreviewTicket,
    context: ExecutionPortfolioContext | None,
    *,
    exit_fees_inr: float,
    slippage_pct: float,
) -> tuple[bool, str]:
    if ticket.close_intent_id is None or ticket.observation_id is None:
        return False, "Invalid close preview — request a new preview."
    if ticket.exit_fees_inr is not None and abs(ticket.exit_fees_inr - exit_fees_inr) > 1e-9:
        return False, "Exit fees changed — request a new preview."
    if ticket.slippage_pct is not None and abs(ticket.slippage_pct - slippage_pct) > 1e-12:
        return False, "Slippage assumption changed — request a new preview."
    return confirm_preview(ticket, context)
