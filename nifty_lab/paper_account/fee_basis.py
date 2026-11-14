"""Derive average cost and proportional entry fees from validated fills (read-only)."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from nifty_lab.execution.types import OrderSide

from .decimal_inr import TOL, d as _d, int_qty as _int_qty, round_inr as _round_inr

Q = Decimal("0.01")


def _to_paise(amount: Decimal) -> int:
    return int(amount.quantize(Q, rounding=ROUND_HALF_UP) * 100)


def _from_paise(paise: int) -> Decimal:
    return Decimal(paise) / 100


def allocate_proportional_inr(total: Decimal, closed_qty: int, total_qty: int) -> tuple[Decimal, Decimal]:
    if total_qty <= 0 or closed_qty <= 0:
        return Decimal("0"), _round_inr(total)
    total_p = _to_paise(total)
    if closed_qty >= total_qty:
        return _from_paise(total_p), Decimal("0")
    closed_p = (total_p * closed_qty) // total_qty
    remain_p = total_p - closed_p
    return _from_paise(closed_p), _from_paise(remain_p)


def sell_realized_inr(
    proceeds: Decimal,
    alloc_cost: Decimal,
    alloc_entry_fees: Decimal,
    exit_fees: Decimal,
) -> tuple[Decimal, Decimal]:
    gross = proceeds - alloc_cost
    net = gross - alloc_entry_fees - exit_fees
    return _round_inr(gross), _round_inr(net)


@dataclass
class InstrumentState:
    quantity: int = 0
    cost_basis_inr: Decimal = Decimal("0")
    entry_fees_inr: Decimal = Decimal("0")

    @property
    def avg_price_inr(self) -> Decimal | None:
        if self.quantity <= 0:
            return None
        return self.cost_basis_inr / Decimal(self.quantity)


@dataclass
class FeeBasisReplay:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    by_instrument: dict[str, InstrumentState] = field(default_factory=dict)
    expected_realized: dict[str, tuple[Decimal, Decimal]] = field(default_factory=dict)
    realized_gross: Decimal = Decimal("0")
    realized_net: Decimal = Decimal("0")


def _parse_fill_time(raw: Any) -> tuple[datetime | None, str | None]:
    if not raw or not isinstance(raw, str):
        return None, "FILL_TIME_MISSING"
    text = raw.strip()
    if not text:
        return None, "FILL_TIME_MISSING"
    try:
        ts = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None, "FILL_TIME_MISSING"
    if ts.tzinfo is None:
        return None, "FILL_TIME_NAIVE"
    try:
        offset = ts.tzinfo.utcoffset(ts)
    except (TypeError, ValueError):
        return None, "FILL_TIME_MISSING"
    if offset is None:
        return None, "FILL_TIME_NAIVE"
    return ts.astimezone(timezone.utc), None


def _fill_id_value(raw: Any) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    fid = raw.strip()
    if not fid:
        return None
    return fid


def _ordered_fills(
    fills: list[dict],
    orders_by_id: dict[str, dict],
) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    rows: list[tuple[float, dict, str, str]] = []

    for f in fills:
        feid = str(f.get("fill_event_id") or "").strip()
        lid = f.get("local_order_id")
        if not feid or not isinstance(lid, str) or lid not in orders_by_id:
            continue
        fid = _fill_id_value(f.get("fill_id"))
        if fid is None:
            if "FILL_ID_MISSING" not in errors:
                errors.append("FILL_ID_MISSING")
            continue
        ts, t_err = _parse_fill_time(f.get("filled_at"))
        if t_err:
            if t_err not in errors:
                errors.append(t_err)
            continue
        if ts is None:
            if "FILL_TIME_MISSING" not in errors:
                errors.append("FILL_TIME_MISSING")
            continue
        order = orders_by_id[lid]
        ik = str(order.get("instrument_key", ""))
        side = str(order.get("side", ""))
        instant = ts.timestamp()
        rows.append((instant, f, ik, side))

    if errors:
        return [], errors
    if not rows and fills:
        return [], ["FILL_TIME_MISSING"]

    groups: dict[tuple[float, str], list[str]] = defaultdict(list)
    for instant, _f, ik, side in rows:
        groups[(instant, ik)].append(side)

    for sides in groups.values():
        if len(sides) <= 1:
            continue
        if OrderSide.SELL.value in sides:
            errors.append("FILL_SEQUENCE_AMBIGUOUS")
            break
        if OrderSide.BUY.value in sides and OrderSide.SELL.value in sides:
            errors.append("FILL_SEQUENCE_AMBIGUOUS")
            break

    if errors:
        return [], errors

    rows.sort(key=lambda r: r[0])
    return [r[1] for r in rows], []


def replay_fee_basis(
    *,
    fills: list[dict],
    positions: list[dict],
    realized_events: list[dict],
    orders_by_id: dict[str, dict],
) -> FeeBasisReplay:
    out = FeeBasisReplay()
    ordered, order_err = _ordered_fills(fills, orders_by_id)
    if order_err:
        out.errors.extend(order_err)
        out.ok = False
        return out
    if not ordered and fills:
        out.errors.append("FILL_TIME_MISSING")
        out.ok = False
        return out

    states: dict[str, InstrumentState] = {}
    for f in ordered:
        lid = str(f.get("local_order_id"))
        order = orders_by_id[lid]
        ik = str(order.get("instrument_key", ""))
        side = str(order.get("side", ""))
        fq = _int_qty(f.get("qty"))
        price = _d(f.get("price"))
        fee = _d(f.get("fees"))
        feid = str(f.get("fill_event_id"))
        if fq is None or price is None or fee is None or fq <= 0:
            continue
        st = states.setdefault(ik, InstrumentState())
        if side == OrderSide.BUY.value:
            st.quantity += fq
            st.cost_basis_inr += Decimal(fq) * price
            st.entry_fees_inr = _round_inr(st.entry_fees_inr + fee)
            continue
        if side != OrderSide.SELL.value:
            out.errors.append("FILL_SIDE")
            continue
        old_q = st.quantity
        if fq > old_q:
            out.errors.append("SELL_EXCEEDS_OWNED")
            out.ok = False
            return out
        avg = st.avg_price_inr
        if avg is None or old_q <= 0:
            out.errors.append("SELL_WITHOUT_BASIS")
            out.ok = False
            return out
        alloc_fees, remain_fees = allocate_proportional_inr(st.entry_fees_inr, fq, old_q)
        alloc_cost = Decimal(fq) * avg
        proceeds = Decimal(fq) * price
        gross, net = sell_realized_inr(proceeds, alloc_cost, alloc_fees, fee)
        out.expected_realized[feid] = (gross, net)
        out.realized_gross += gross
        out.realized_net += net
        new_q = old_q - fq
        if new_q == 0:
            st.quantity = 0
            st.cost_basis_inr = Decimal("0")
            st.entry_fees_inr = Decimal("0")
        else:
            st.quantity = new_q
            st.cost_basis_inr = Decimal(new_q) * avg
            st.entry_fees_inr = _round_inr(remain_fees)

    ev_by_fill: dict[str, dict] = {str(e.get("fill_event_id")): e for e in realized_events if e.get("fill_event_id")}
    for feid, (eg, en) in out.expected_realized.items():
        ev = ev_by_fill.get(feid)
        if ev is None:
            out.errors.append("SELL_FILL_NO_REALIZED")
            continue
        sg = _d(ev.get("gross_inr"))
        sn = _d(ev.get("net_inr"))
        if sg is None or sn is None:
            out.errors.append("REALIZED_NONFINITE")
            continue
        if abs(_round_inr(sg) - eg) > TOL or abs(_round_inr(sn) - en) > TOL:
            out.errors.append("REALIZED_EVENT_MISMATCH")
            break

    for ev in realized_events:
        feid = str(ev.get("fill_event_id", ""))
        if feid not in out.expected_realized:
            out.errors.append("REALIZED_ORPHAN")
            break

    for p in positions:
        ik = str(p.get("instrument_key", ""))
        pq = _int_qty(p.get("quantity"))
        if pq is None:
            continue
        derived = states.get(ik, InstrumentState())
        if pq != derived.quantity:
            out.errors.append("POSITION_UNIT_MISMATCH")
            break
        if pq == 0:
            continue
        stored_avg = _d(p.get("avg_price"))
        stored_fees = _d(p.get("entry_fees_inr"))
        if stored_avg is None or stored_avg <= 0 or stored_fees is None:
            out.errors.append("POSITION_BASIS_INVALID")
            break
        stored_cost = Decimal(pq) * stored_avg
        if abs(_round_inr(stored_cost) - _round_inr(derived.cost_basis_inr)) > TOL:
            out.errors.append("POSITION_BASIS_MISMATCH")
            break
        if abs(_round_inr(stored_fees) - _round_inr(derived.entry_fees_inr)) > TOL:
            out.errors.append("POSITION_ENTRY_FEES_MISMATCH")
            break

    if out.errors:
        out.ok = False
    else:
        out.by_instrument = states
        out.realized_gross = _round_inr(out.realized_gross)
        out.realized_net = _round_inr(out.realized_net)
    return out
