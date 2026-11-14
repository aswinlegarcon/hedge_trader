"""Provenance-aware accounting view from a read-only Paper snapshot."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from .reader import PaperSnapshot
from .reconcile import reconcile_paper_snapshot

Q = Decimal("0.01")
TOL = Decimal("0.01")


def _d(value: Any) -> Decimal | None:
    from decimal import InvalidOperation

    if isinstance(value, bool) or value is None:
        return None
    try:
        x = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not x.is_finite():
        return None
    return x


def _round_inr(x: Decimal) -> Decimal:
    return x.quantize(Q, rounding=ROUND_HALF_UP)


def _s(x: Decimal | None) -> str | None:
    return str(_round_inr(x)) if x is not None else None


@dataclass
class PositionView:
    instrument_key: str
    symbol: str
    quantity: int
    avg_price_inr: str
    mark_price_inr: str | None
    mark_time: str | None
    mark_provenance: str
    mark_age_note: str | None
    entry_fees_inr: str
    cost_basis_inr: str
    position_market_value_inr: str | None
    gross_unrealized_inr: str | None
    unrealized_after_paid_entry_fees_inr: str | None
    reserved_sell_qty: int
    sellable_qty: int


@dataclass
class OrderRowView:
    local_id: str
    side: str
    status: str
    symbol: str
    quantity: int
    filled_qty: int
    reserved_cash_inr: str
    reserved_risk_inr: str


@dataclass
class FillRowView:
    fill_event_id: str
    local_order_id: str
    qty: int
    price_inr: str
    fees_inr: str


@dataclass
class PaperAccountView:
    status: str
    error: str | None
    snapshot_at_utc: str
    read_only_verified: bool
    initial_funding_inr: str | None
    cash_inr: str | None
    reserved_cash_inr: str | None
    reserved_risk_inr: str | None
    cash_available_inr: str | None
    allocation_limit_inr: str
    realized_gross_inr: str | None
    realized_net_inr: str | None
    fees_paid_total_inr: str | None
    remaining_entry_fees_inr: str | None
    stored_mark_equity_inr: str | None
    total_pnl_after_paid_fees_inr: str | None
    gross_unrealized_total_inr: str | None
    unrealized_after_fees_total_inr: str | None
    portfolio_valuation_status: str
    reconciliation_status: str
    positions: list[PositionView] = field(default_factory=list)
    recent_orders: list[OrderRowView] = field(default_factory=list)
    recent_fills: list[FillRowView] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


def _mark_age_note(mark_time: str | None) -> str | None:
    if not mark_time:
        return "mark time unknown"
    try:
        ts = datetime.fromisoformat(mark_time.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - ts
        hours = age.total_seconds() / 3600.0
        return f"stored mark age ~{hours:.1f}h (not a live quote)"
    except (ValueError, TypeError):
        return "mark time unreadable"


def _empty_view(
    snap: PaperSnapshot,
    *,
    status: str,
    error: str | None,
    limitations: list[str],
    recon: str = "UNAVAILABLE",
) -> PaperAccountView:
    return PaperAccountView(
        status=status,
        error=error,
        snapshot_at_utc=snap.snapshot_at_utc,
        read_only_verified=snap.read_only_verified,
        initial_funding_inr=None,
        cash_inr=None,
        reserved_cash_inr=None,
        reserved_risk_inr=None,
        cash_available_inr=None,
        allocation_limit_inr="20000.00",
        realized_gross_inr=None,
        realized_net_inr=None,
        fees_paid_total_inr=None,
        remaining_entry_fees_inr=None,
        stored_mark_equity_inr=None,
        total_pnl_after_paid_fees_inr=None,
        gross_unrealized_total_inr=None,
        unrealized_after_fees_total_inr=None,
        portfolio_valuation_status="UNAVAILABLE",
        reconciliation_status=recon,
        limitations=limitations,
    )


def _fail_closed_view(snap: PaperSnapshot, errors: list[str], limitations: list[str]) -> PaperAccountView:
    return PaperAccountView(
        status="RECONCILIATION_FAILED",
        error=errors[0] if errors else "RECONCILIATION_FAILED",
        snapshot_at_utc=snap.snapshot_at_utc,
        read_only_verified=snap.read_only_verified,
        initial_funding_inr=None,
        cash_inr=None,
        reserved_cash_inr=None,
        reserved_risk_inr=None,
        cash_available_inr=None,
        allocation_limit_inr="20000.00",
        realized_gross_inr=None,
        realized_net_inr=None,
        fees_paid_total_inr=None,
        remaining_entry_fees_inr=None,
        stored_mark_equity_inr=None,
        total_pnl_after_paid_fees_inr=None,
        gross_unrealized_total_inr=None,
        unrealized_after_fees_total_inr=None,
        portfolio_valuation_status="UNAVAILABLE",
        reconciliation_status="RECONCILIATION_FAILED",
        limitations=limitations,
    )


def build_paper_account_view(snap: PaperSnapshot) -> PaperAccountView:
    limitations = [
        "LOCAL PAPER — not a broker account.",
        "STORED LEDGER MARKS — indicative only; not verified live quotes.",
        "Unrealized values exclude future exit fees and slippage — not net liquidation.",
        "Archived strategy evidence remains INSUFFICIENT; 2025 NOT EVALUATED.",
    ]
    if snap.load_status == "NOT_INITIALIZED":
        return _empty_view(snap, status="NOT_INITIALIZED", error=snap.load_error, limitations=limitations, recon="N/A")
    if snap.load_status != "OK":
        return _empty_view(
            snap,
            status=snap.load_status,
            error=snap.load_error,
            limitations=limitations,
        )

    recon = reconcile_paper_snapshot(snap)
    if not recon.ok:
        return _fail_closed_view(snap, recon.errors, limitations)

    cash = recon.cash
    reserved_cash = recon.reserved_cash or Decimal("0")
    reserved_risk = recon.reserved_risk or Decimal("0")
    cash_available = _round_inr(cash - reserved_cash) if cash is not None else None
    realized_gross = recon.realized_gross or Decimal("0")
    realized_net = recon.realized_net or Decimal("0")
    fees_paid = recon.fees_paid or Decimal("0")
    initial = recon.initial_funding

    sell_reserved = recon.sell_reserved_by_instr
    open_positions: list[PositionView] = []
    remaining_entry_fees = Decimal("0")
    all_marks_ok = True
    gross_unreal_total = Decimal("0")
    unreal_after_fees_total = Decimal("0")
    position_market_total = Decimal("0")

    for p in recon.position_rows:
        qty = int(p.get("quantity", 0))
        if qty <= 0:
            continue
        avg = _d(p.get("avg_price"))
        if avg is None or avg <= 0:
            return _fail_closed_view(snap, ["POSITION_AVG"], limitations)
        entry_fees = _d(p.get("entry_fees_inr"))
        if entry_fees is None or entry_fees < 0:
            return _fail_closed_view(snap, ["POSITION_ENTRY_FEES"], limitations)
        remaining_entry_fees += entry_fees
        mark = _d(p.get("mark_price"))
        mark_time = p.get("mark_time")
        if mark is None or mark <= 0:
            all_marks_ok = False
            mark_price_s: str | None = None
            mark_prov = "MARK_MISSING"
            gross_u: str | None = None
            unreal_af: str | None = None
            pmv: str | None = None
        else:
            mark_price_s = str(_round_inr(mark))
            mark_prov = "STORED_LEDGER_MARK"
            gross_u_d = _round_inr(Decimal(qty) * (mark - avg))
            unreal_af_d = _round_inr(gross_u_d - entry_fees)
            gross_u = str(gross_u_d)
            unreal_af = str(unreal_af_d)
            pmv = str(_round_inr(Decimal(qty) * mark))
            gross_unreal_total += gross_u_d
            unreal_after_fees_total += unreal_af_d
            position_market_total += Decimal(qty) * mark

        ik = str(p.get("instrument_key", ""))
        res_sell = sell_reserved.get(ik, 0)
        open_positions.append(
            PositionView(
                instrument_key=ik,
                symbol=str(p.get("symbol", "")),
                quantity=qty,
                avg_price_inr=str(_round_inr(avg)),
                mark_price_inr=mark_price_s,
                mark_time=str(mark_time) if mark_time else None,
                mark_provenance=mark_prov,
                mark_age_note=_mark_age_note(str(mark_time) if mark_time else None),
                entry_fees_inr=str(_round_inr(entry_fees)),
                cost_basis_inr=str(_round_inr(Decimal(qty) * avg)),
                position_market_value_inr=pmv,
                gross_unrealized_inr=gross_u,
                unrealized_after_paid_entry_fees_inr=unreal_af,
                reserved_sell_qty=res_sell,
                sellable_qty=max(0, qty - res_sell),
            )
        )

    if open_positions and not all_marks_ok:
        portfolio_valuation = "UNAVAILABLE_MISSING_MARK"
        stored_equity: str | None = None
        total_pnl: str | None = None
        gross_u_s: str | None = None
        unreal_af_s: str | None = None
    elif open_positions and all_marks_ok:
        portfolio_valuation = "STORED_MARK_EQUITY"
        stored_equity = str(_round_inr(cash + position_market_total))
        total_pnl = str(_round_inr(realized_net + unreal_after_fees_total))
        gross_u_s = str(_round_inr(gross_unreal_total))
        unreal_af_s = str(_round_inr(unreal_after_fees_total))
    else:
        portfolio_valuation = "CASH_ONLY"
        stored_equity = str(_round_inr(cash)) if cash is not None else None
        total_pnl = str(_round_inr(realized_net))
        gross_u_s = "0.00"
        unreal_af_s = "0.00"

    if initial is not None and stored_equity is not None and total_pnl is not None and all_marks_ok:
        implied = _round_inr(Decimal(stored_equity) - initial)
        calc_pnl = _round_inr(Decimal(total_pnl))
        if abs(implied - calc_pnl) > TOL:
            return _fail_closed_view(snap, ["PNL_IDENTITY"], limitations)

    recent_orders: list[OrderRowView] = []
    for o in sorted(snap.orders, key=lambda x: str(x.get("updated_at", "")), reverse=True)[:20]:
        rq = _d(o.get("reserved_cash"))
        rr = _d(o.get("reserved_risk"))
        if rq is None or rr is None:
            continue
        q = o.get("quantity")
        fq = o.get("filled_qty")
        if not isinstance(q, int) or not isinstance(fq, int):
            continue
        recent_orders.append(
            OrderRowView(
                local_id=str(o.get("local_id", "")),
                side=str(o.get("side", "")),
                status=str(o.get("status", "")),
                symbol=str(o.get("symbol", "")),
                quantity=q,
                filled_qty=fq,
                reserved_cash_inr=str(_round_inr(rq)),
                reserved_risk_inr=str(_round_inr(rr)),
            )
        )

    recent_fills: list[FillRowView] = []
    for f in sorted(snap.fills, key=lambda x: str(x.get("filled_at", "")), reverse=True)[:20]:
        fee = _d(f.get("fees"))
        price = _d(f.get("price"))
        qty = f.get("qty")
        if fee is None or price is None or not isinstance(qty, int):
            continue
        recent_fills.append(
            FillRowView(
                fill_event_id=str(f.get("fill_event_id", "")),
                local_order_id=str(f.get("local_order_id", "")),
                qty=qty,
                price_inr=str(_round_inr(price)),
                fees_inr=str(_round_inr(fee)),
            )
        )

    return PaperAccountView(
        status="OK",
        error=None,
        snapshot_at_utc=snap.snapshot_at_utc,
        read_only_verified=snap.read_only_verified,
        initial_funding_inr=_s(initial),
        cash_inr=_s(cash),
        reserved_cash_inr=_s(reserved_cash),
        reserved_risk_inr=_s(reserved_risk),
        cash_available_inr=_s(cash_available),
        allocation_limit_inr="20000.00",
        realized_gross_inr=_s(realized_gross),
        realized_net_inr=_s(realized_net),
        fees_paid_total_inr=_s(fees_paid),
        remaining_entry_fees_inr=_s(remaining_entry_fees),
        stored_mark_equity_inr=stored_equity,
        total_pnl_after_paid_fees_inr=total_pnl,
        gross_unrealized_total_inr=gross_u_s if open_positions and all_marks_ok else (gross_u_s if not open_positions else None),
        unrealized_after_fees_total_inr=unreal_af_s if open_positions and all_marks_ok else (unreal_af_s if not open_positions else None),
        portfolio_valuation_status=portfolio_valuation,
        reconciliation_status="OK",
        positions=open_positions,
        recent_orders=recent_orders,
        recent_fills=recent_fills,
        limitations=limitations,
    )


def load_paper_account_view(db_path) -> PaperAccountView:
    from pathlib import Path

    from .reader import load_paper_snapshot

    return build_paper_account_view(load_paper_snapshot(Path(db_path)))
