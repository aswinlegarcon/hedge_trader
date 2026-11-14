"""Read-side ledger reconciliation (no ExecutionLedger)."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from nifty_lab.execution.modes import ExecutionMode
from nifty_lab.execution.types import OrderSide, OrderStatus

from .decimal_inr import TOL, d as _d, int_qty as _int_qty, round_inr as _round_inr
from .fee_basis import replay_fee_basis
from .reader import PaperSnapshot, _ACTIVE_ORDER_STATUSES, _TERMINAL_ORDER_STATUSES, paper_orders_only

_ALL_ORDER_STATUSES = {s.value for s in OrderStatus}


@dataclass
class ReconcileResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    cash: Decimal | None = None
    reserved_cash: Decimal | None = None
    reserved_risk: Decimal | None = None
    fees_paid: Decimal | None = None
    realized_gross: Decimal | None = None
    realized_net: Decimal | None = None
    initial_funding: Decimal | None = None
    fill_by_event: dict[str, dict] = field(default_factory=dict)
    orders_by_id: dict[str, dict] = field(default_factory=dict)
    sell_reserved_by_instr: dict[str, int] = field(default_factory=dict)
    position_rows: list[dict] = field(default_factory=list)


def reconcile_paper_snapshot(snap: PaperSnapshot) -> ReconcileResult:
    out = ReconcileResult(ok=True)
    if snap.load_status != "OK" or not snap.read_only_verified:
        out.ok = False
        if not snap.read_only_verified:
            out.errors.append("READ_ONLY_UNVERIFIED")
        return out

    orders, mode_err = paper_orders_only(snap.orders)
    if mode_err:
        out.errors.append(mode_err)

    orders_by_id: dict[str, dict] = {}
    for o in orders:
        lid = o.get("local_id")
        if not isinstance(lid, str) or not lid:
            out.errors.append("ORDER_ID")
            continue
        if lid in orders_by_id:
            out.errors.append("ORDER_DUP")
        mode = str(o.get("mode", ""))
        if mode != ExecutionMode.PAPER.value:
            out.errors.append("ORDER_MODE")
        status = o.get("status")
        if not isinstance(status, str) or status not in _ALL_ORDER_STATUSES:
            out.errors.append("ORDER_STATUS_UNKNOWN")
        qty = _int_qty(o.get("quantity"))
        filled = _int_qty(o.get("filled_qty"))
        if qty is None or filled is None:
            out.errors.append("ORDER_QTY")
        elif filled > qty:
            out.errors.append("ORDER_OVERFILL")
        side = o.get("side")
        if side not in (OrderSide.BUY.value, OrderSide.SELL.value):
            out.errors.append("ORDER_SIDE")
        rc = _d(o.get("reserved_cash"))
        rr = _d(o.get("reserved_risk"))
        if rc is None or rr is None:
            out.errors.append("ORDER_RESERVE_INVALID")
        elif rc < 0 or rr < 0:
            out.errors.append("ORDER_RESERVE_NEGATIVE")
        elif isinstance(status, str) and status in _TERMINAL_ORDER_STATUSES and (rc != 0 or rr != 0):
            out.errors.append("TERMINAL_RESERVE_NONZERO")
        elif side == OrderSide.SELL.value and isinstance(status, str) and status in _ACTIVE_ORDER_STATUSES and rc != 0:
            out.errors.append("SELL_CASH_RESERVE")
        orders_by_id[lid] = o

    cash_sum = Decimal("0")
    fee_ledger = Decimal("0")
    recognized_initial = False
    for row in snap.cash_ledger:
        dc = _d(row.get("delta_cash"))
        df = _d(row.get("delta_fees"))
        if dc is None or df is None:
            out.errors.append("CASH_LEDGER_NONFINITE")
            break
        note = str(row.get("note") or "")
        if note == "initial_allocation":
            recognized_initial = True
        cash_sum += dc
        fee_ledger += df
    else:
        out.cash = _round_inr(cash_sum - fee_ledger)
        if not recognized_initial:
            out.errors.append("INITIAL_ALLOCATION_UNRECOGNIZED")

    funded = _d(snap.meta.get("funded"))
    if funded is None:
        out.errors.append("INITIAL_FUNDING_UNKNOWN")
    else:
        out.initial_funding = _round_inr(funded)

    fill_ids: set[str] = set()
    fees_paid = Decimal("0")
    fill_qty_by_order: dict[str, int] = {}
    fill_by_event: dict[str, dict] = {}
    cash_from_fills = Decimal("0")

    for f in snap.fills:
        feid = f.get("fill_event_id")
        lid = f.get("local_order_id")
        if not feid or feid in fill_ids:
            out.errors.append("FILL_EVENT_DUP")
        if feid:
            fill_ids.add(str(feid))
            fill_by_event[str(feid)] = f
        if not isinstance(lid, str) or lid not in orders_by_id:
            out.errors.append("FILL_ORPHAN_ORDER")
            continue
        order = orders_by_id[lid]
        fee = _d(f.get("fees"))
        fq = _int_qty(f.get("qty"))
        price = _d(f.get("price"))
        if fee is None or fq is None or price is None or fq <= 0 or price <= 0 or fee < 0:
            out.errors.append("FILL_INVALID")
            continue
        fees_paid += fee
        fill_qty_by_order[lid] = fill_qty_by_order.get(lid, 0) + fq
        side = str(order.get("side"))
        notional = Decimal(fq) * price
        if side == OrderSide.BUY.value:
            cash_from_fills -= notional + fee
        elif side == OrderSide.SELL.value:
            cash_from_fills += notional - fee
        else:
            out.errors.append("FILL_SIDE")

    for lid, order in orders_by_id.items():
        filled = _int_qty(order.get("filled_qty"))
        if filled is None:
            continue
        summed = fill_qty_by_order.get(lid, 0)
        if summed != filled:
            out.errors.append("ORDER_FILL_QTY_MISMATCH")

    net_by_instr: dict[str, int] = {}
    for f in snap.fills:
        lid = f.get("local_order_id")
        if not isinstance(lid, str) or lid not in orders_by_id:
            continue
        order = orders_by_id[lid]
        fq = _int_qty(f.get("qty"))
        if fq is None:
            continue
        ik = str(order.get("instrument_key", ""))
        if str(order.get("side")) == OrderSide.BUY.value:
            net_by_instr[ik] = net_by_instr.get(ik, 0) + fq
        else:
            net_by_instr[ik] = net_by_instr.get(ik, 0) - fq

    for p in snap.positions:
        ik = str(p.get("instrument_key", ""))
        pq = _int_qty(p.get("quantity"))
        if pq is None:
            out.errors.append("POSITION_QTY")
            continue
        implied = net_by_instr.get(ik, 0)
        if pq != implied:
            out.errors.append("POSITION_UNIT_MISMATCH")
        if pq > 0:
            out.position_rows.append(p)
        elif ik in net_by_instr and net_by_instr[ik] != 0:
            out.errors.append("POSITION_UNIT_MISMATCH")

    for ik, implied in net_by_instr.items():
        stored = next((p for p in snap.positions if str(p.get("instrument_key")) == ik), None)
        pq = _int_qty(stored.get("quantity")) if stored else 0
        if (pq or 0) != implied:
            if "POSITION_UNIT_MISMATCH" not in out.errors:
                out.errors.append("POSITION_UNIT_MISMATCH")

    realized_ids: set[str] = set()
    for ev in snap.realized_events:
        feid = str(ev.get("fill_event_id", ""))
        if not feid or feid in realized_ids:
            out.errors.append("REALIZED_DUP")
        realized_ids.add(feid)

    realized_gross = Decimal("0")
    realized_net = Decimal("0")
    if not out.errors:
        basis = replay_fee_basis(
            fills=snap.fills,
            positions=snap.positions,
            realized_events=snap.realized_events,
            orders_by_id=orders_by_id,
        )
        if not basis.ok:
            out.errors.extend(basis.errors)
        else:
            realized_gross = basis.realized_gross
            realized_net = basis.realized_net

    reserved_cash = Decimal("0")
    reserved_risk = Decimal("0")
    sell_reserved: dict[str, int] = {}
    owned: dict[str, int] = {str(p.get("instrument_key")): _int_qty(p.get("quantity")) or 0 for p in snap.positions}

    for o in orders_by_id.values():
        st = str(o.get("status", ""))
        rc = _d(o.get("reserved_cash"))
        rr = _d(o.get("reserved_risk"))
        if rc is None or rr is None:
            continue
        if st in _ACTIVE_ORDER_STATUSES:
            reserved_cash += rc
            reserved_risk += rr
            if str(o.get("side")) == OrderSide.SELL.value:
                qty = _int_qty(o.get("quantity"))
                filled = _int_qty(o.get("filled_qty"))
                if qty is not None and filled is not None:
                    rem = qty - filled
                    if rem > 0:
                        ik = str(o.get("instrument_key", ""))
                        sell_reserved[ik] = sell_reserved.get(ik, 0) + rem

    for ik, pending in sell_reserved.items():
        if pending > owned.get(ik, 0):
            out.errors.append("SELL_OVER_RESERVED")

    if out.cash is not None and reserved_cash > out.cash:
        if _round_inr(out.cash - reserved_cash) < 0:
            out.errors.append("CASH_AVAILABLE_NEGATIVE")

    if fees_paid < 0 or fee_ledger < 0:
        out.errors.append("FEE_NEGATIVE")

    if out.cash is not None and out.initial_funding is not None and not out.errors:
        implied_cash = _round_inr(out.initial_funding + cash_from_fills)
        if abs(implied_cash - out.cash) > TOL:
            out.errors.append("CASH_FILL_MISMATCH")

    if not out.errors and abs(_round_inr(fees_paid) - _round_inr(fee_ledger)) > TOL:
        out.errors.append("FEE_LEDGER_MISMATCH")

    out.orders_by_id = orders_by_id
    out.fill_by_event = fill_by_event
    out.sell_reserved_by_instr = sell_reserved
    if out.errors:
        out.ok = False
        out.cash = None
        out.initial_funding = None
    else:
        out.fees_paid = _round_inr(fees_paid)
        out.reserved_cash = _round_inr(reserved_cash)
        out.reserved_risk = _round_inr(reserved_risk)
        out.realized_gross = _round_inr(realized_gross)
        out.realized_net = _round_inr(realized_net)
    return out
