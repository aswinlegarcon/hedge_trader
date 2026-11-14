"""Trade ticket and order types (Spec 08)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .modes import ExecutionMode


class InstrumentKind(str, Enum):
    CASH_STOCK = "CASH_STOCK"
    CASH_ETF = "CASH_ETF"
    NIFTY_OPTION = "NIFTY_OPTION"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class ProductType(str, Enum):
    DELIVERY = "DELIVERY"
    INTRADAY = "INTRADAY"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    UNKNOWN_SUBMISSION = "UNKNOWN_SUBMISSION"


@dataclass(frozen=True)
class QuoteSnapshot:
    bid: float
    ask: float
    bid_qty: int
    ask_qty: int
    instrument_key: str
    evaluated_at: datetime
    source: str = "upstox_quote"

    def is_valid(self) -> bool:
        import math

        if not all(math.isfinite(x) for x in (self.bid, self.ask)):
            return False
        if self.bid <= 0 or self.ask <= 0:
            return False
        if self.ask < self.bid:
            return False
        return True

    def is_fresh(self, *, ttl_seconds: float = 15.0, now: datetime | None = None) -> bool:
        from datetime import timezone

        import math

        now = now or datetime.now(timezone.utc)
        ts = self.evaluated_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        else:
            ts = ts.astimezone(timezone.utc)
        age = (now - ts).total_seconds()
        if not math.isfinite(age) or age < 0:
            return False
        return age <= ttl_seconds


@dataclass
class TradeCandidate:
    mode: ExecutionMode
    kind: InstrumentKind
    instrument_key: str
    trading_symbol: str
    underlying: str
    side: OrderSide
    quantity: int
    limit_price_inr: float
    product: ProductType
    # Stock planned-risk inputs
    stop_reference_inr: float | None = None
    # Option / stock cost breakdown (paise totals computed in gate)
    entry_cost_inr: float = 0.0
    exit_cost_reserve_inr: float = 0.0
    planned_risk_inr: float | None = None
    premium_at_risk_inr: float | None = None
    margin_required_inr: float | None = None
    broker_stop_placed: bool = False
    user_ack_stop_not_placed: bool = False
    quote: QuoteSnapshot | None = None
    lot_size: int = 1

    def ticket_identity(self) -> str:
        q = self.quote
        qpart = "no-quote"
        if q is not None:
            qpart = f"{q.instrument_key}:{q.bid:.4f}:{q.ask:.4f}:{q.bid_qty}:{q.ask_qty}"
        stop = "" if self.stop_reference_inr is None else f"{self.stop_reference_inr:.4f}"
        return "|".join(
            [
                self.mode.value,
                self.kind.value,
                self.instrument_key,
                self.underlying.upper(),
                self.side.value,
                str(self.quantity),
                f"{self.limit_price_inr:.2f}",
                self.product.value,
                stop,
                f"{self.entry_cost_inr:.2f}",
                f"{self.exit_cost_reserve_inr:.2f}",
                str(self.lot_size),
                f"{self.margin_required_inr:.2f}" if self.margin_required_inr is not None else "",
                f"{self.planned_risk_inr:.2f}" if self.planned_risk_inr is not None else "",
                f"{self.premium_at_risk_inr:.2f}" if self.premium_at_risk_inr is not None else "",
                qpart,
            ]
        )
