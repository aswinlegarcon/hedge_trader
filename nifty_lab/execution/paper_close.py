"""Owned Paper sell-to-close (Spec 08 close slice)."""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, replace

from .fill_validation import validate_close_admission_economics
from .gate import evaluate_entry
from .ledger.store import ExecutionLedger
from .modes import ExecutionMode
from .preview import _hash_identity
from .types import InstrumentKind, OrderSide, ProductType, QuoteSnapshot, TradeCandidate


@dataclass
class PaperCloseResult:
    local_order_id: str
    filled_qty: int
    message: str


def _modeled_fill_qty(
    *,
    quote: QuoteSnapshot,
    limit_price_inr: float,
    kind: InstrumentKind,
    lot_size: int,
    slippage_pct: float = 0.0,
    max_qty: int,
) -> tuple[int, float]:
    marketable = quote.bid * (1 - slippage_pct)
    if marketable < limit_price_inr:
        return 0, 0.0
    fill_qty = min(max_qty, max(int(quote.bid_qty), 0))
    if kind == InstrumentKind.NIFTY_OPTION and lot_size > 1:
        fill_qty = (fill_qty // lot_size) * lot_size
    if fill_qty <= 0:
        return 0, 0.0
    return fill_qty, marketable


def quote_observation_id(quote: QuoteSnapshot) -> str:
    src = quote.evaluated_at.astimezone(__import__("datetime").timezone.utc).isoformat()
    raw = "|".join(
        [
            quote.instrument_key,
            quote.source,
            src,
            f"{quote.bid:.6f}",
            f"{quote.ask:.6f}",
            str(int(quote.bid_qty)),
            str(int(quote.ask_qty)),
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _candidate_from_order(row: dict, *, quote: QuoteSnapshot, quantity: int) -> TradeCandidate:
    return TradeCandidate(
        mode=ExecutionMode.PAPER,
        kind=InstrumentKind(row["instrument_kind"] or InstrumentKind.CASH_STOCK.value),
        instrument_key=str(row["instrument_key"]),
        trading_symbol=str(row["symbol"]),
        underlying=str(row["underlying"]),
        side=OrderSide.SELL,
        quantity=quantity,
        limit_price_inr=float(row["limit_price"]),
        product=ProductType(row["product"] or ProductType.DELIVERY.value),
        quote=quote,
        lot_size=int(row["lot_size"] or 1),
    )


def submit_paper_close(
    ledger: ExecutionLedger,
    candidate: TradeCandidate,
    *,
    intent_id: str,
    observation_id: str,
    exit_fees_inr: float,
    slippage_pct: float = 0.0,
    fill_event_id: str | None = None,
) -> PaperCloseResult:
    if candidate.mode != ExecutionMode.PAPER or candidate.side != OrderSide.SELL:
        raise ValueError("Paper close requires PAPER SELL candidate.")
    if candidate.quote is None:
        raise ValueError("Quote required.")
    validate_close_admission_economics(exit_fees_inr, slippage_pct)
    identity = _hash_identity(candidate)
    local_id = ledger.admit_paper_close(
        candidate,
        intent_id,
        identity,
        exit_fees_inr=exit_fees_inr,
        slippage_pct=slippage_pct,
    )
    row = ledger.get_paper_order(local_id)
    if row is None:
        raise ValueError("Close order missing after admission.")
    order_rem = max(0, int(row["quantity"]) - int(row["filled_qty"]))
    if order_rem <= 0:
        return PaperCloseResult(local_id, 0, "Close order already complete.")
    fill_qty, px = _modeled_fill_qty(
        quote=candidate.quote,
        limit_price_inr=float(row["limit_price"]),
        kind=InstrumentKind(row["instrument_kind"] or candidate.kind.value),
        lot_size=int(row["lot_size"] or candidate.lot_size),
        slippage_pct=slippage_pct,
        max_qty=order_rem,
    )
    if fill_qty <= 0:
        return PaperCloseResult(local_id, 0, "Close limit not marketable; units reserved pending.")
    feid = fill_event_id or f"{local_id}:close:{uuid.uuid4()}"
    filled = ledger.execute_paper_close_fill(
        local_id,
        observation_id=observation_id,
        quote=candidate.quote,
        lot_size=int(row["lot_size"] or 1),
        kind=InstrumentKind(row["instrument_kind"] or candidate.kind.value),
        limit_price_inr=float(row["limit_price"]),
        exit_fees_inr=exit_fees_inr,
        slippage_pct=slippage_pct,
        fill_event_id=feid,
        modeled_fill_qty=fill_qty,
        modeled_fill_price=px,
    )
    if filled <= 0:
        return PaperCloseResult(
            local_id,
            0,
            "Quote observation already consumed or fill ineligible; remainder reserved.",
        )
    suffix = ""
    if filled < order_rem:
        suffix = f" Remainder {order_rem - filled} units reserved."
    return PaperCloseResult(local_id, filled, f"Paper close fill {filled} @ ₹{px:.2f}.{suffix}")


def re_evaluate_paper_close(
    ledger: ExecutionLedger,
    local_order_id: str,
    *,
    quote: QuoteSnapshot,
    observation_id: str,
    exit_fees_inr: float,
    slippage_pct: float = 0.0,
    fill_event_id: str | None = None,
) -> PaperCloseResult:
    row = ledger.get_paper_order(local_order_id)
    if row is None:
        raise ValueError("Unknown close order.")
    if row["side"] != OrderSide.SELL.value:
        raise ValueError("Re-evaluate applies to SELL close orders only.")
    if quote.instrument_key != row["instrument_key"]:
        raise ValueError("Quote instrument does not match the open close order.")
    validate_close_admission_economics(exit_fees_inr, slippage_pct)
    order_rem = max(0, int(row["quantity"]) - int(row["filled_qty"]))
    if order_rem <= 0:
        return PaperCloseResult(local_order_id, 0, "No unfilled close remainder.")
    bound = _candidate_from_order(row, quote=quote, quantity=order_rem)
    ctx = ledger.portfolio_context()
    pending = dict(ctx.pending_sell_qty_by_instrument)
    key = str(row["instrument_key"])
    pending[key] = max(0, pending.get(key, 0) - order_rem)
    ctx = replace(ctx, pending_sell_qty_by_instrument=tuple(sorted(pending.items())))
    gate = evaluate_entry(bound, ctx, for_reduce_only=True)
    if not gate.allowed:
        raise ValueError("; ".join(gate.reasons) or "Re-evaluate blocked.")
    fill_qty, px = _modeled_fill_qty(
        quote=quote,
        limit_price_inr=float(row["limit_price"]),
        kind=InstrumentKind(row["instrument_kind"] or InstrumentKind.CASH_STOCK.value),
        lot_size=int(row["lot_size"] or 1),
        slippage_pct=slippage_pct,
        max_qty=order_rem,
    )
    if fill_qty <= 0:
        return PaperCloseResult(local_order_id, 0, "Remainder still not marketable.")
    feid = fill_event_id or f"{local_order_id}:reeval:{uuid.uuid4()}"
    filled = ledger.execute_paper_close_fill(
        local_order_id,
        observation_id=observation_id,
        quote=quote,
        lot_size=int(row["lot_size"] or 1),
        kind=InstrumentKind(row["instrument_kind"] or InstrumentKind.CASH_STOCK.value),
        limit_price_inr=float(row["limit_price"]),
        exit_fees_inr=exit_fees_inr,
        slippage_pct=slippage_pct,
        fill_event_id=feid,
        modeled_fill_qty=fill_qty,
        modeled_fill_price=px,
    )
    if filled <= 0:
        return PaperCloseResult(local_order_id, 0, "Quote observation already consumed.")
    return PaperCloseResult(local_order_id, filled, f"Paper close fill {filled} @ ₹{px:.2f} (re-eval).")


def new_close_intent_id() -> str:
    return str(uuid.uuid4())
