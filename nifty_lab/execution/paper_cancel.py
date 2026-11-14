"""Paper-only local cancellation (Spec 08 cancel slice)."""
from __future__ import annotations

from dataclasses import dataclass

from .ledger.store import ExecutionLedger
from .modes import ExecutionMode
from .types import OrderStatus


@dataclass
class PaperOrderRow:
    local_id: str
    symbol: str
    instrument_key: str
    side: str
    limit_price: float
    status: str
    quantity: int
    filled_qty: int
    remainder: int
    reserved_cash: float
    reserved_risk: float
    cancellable: bool


def list_paper_order_rows(ledger: ExecutionLedger) -> list[PaperOrderRow]:
    out: list[PaperOrderRow] = []
    for r in ledger.list_paper_orders():
        if r["mode"] != ExecutionMode.PAPER.value:
            continue
        qty = int(r["quantity"])
        filled = int(r["filled_qty"])
        rem = max(0, qty - filled)
        st = str(r["status"])
        cancellable = rem > 0 and st in (
            OrderStatus.PENDING.value,
            OrderStatus.OPEN.value,
            OrderStatus.PARTIALLY_FILLED.value,
        )
        out.append(
            PaperOrderRow(
                local_id=str(r["local_id"]),
                symbol=str(r["symbol"]),
                instrument_key=str(r["instrument_key"]),
                side=str(r.get("side") or ""),
                limit_price=float(r.get("limit_price") or 0),
                status=st,
                quantity=qty,
                filled_qty=filled,
                remainder=rem,
                reserved_cash=float(r["reserved_cash"] or 0),
                reserved_risk=float(r["reserved_risk"] or 0),
                cancellable=cancellable,
            )
        )
    return out


def confirm_cancel_label(row: PaperOrderRow) -> str:
    return (
        f"Confirm PAPER cancel remainder {row.remainder} units of {row.symbol} "
        f"(local {row.local_id[:8]}…)"
    )


def cancel_paper_remainder(ledger: ExecutionLedger, local_id: str) -> str:
    return ledger.cancel_paper_remainder(local_id)
