"""Live Upstox order adapter — guarded, no automatic retries (Spec 08)."""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

from ..guard import assert_live_mutation_allowed
from ..modes import ExecutionMode
from ..types import OrderStatus, TradeCandidate

LIVE_ORDER_HOST = "api-hft.upstox.com"


class OrderTransport(Protocol):
    def post(self, url: str, *, body: bytes, headers: dict[str, str]) -> tuple[int, bytes]: ...


@dataclass
class LiveOrderResult:
    local_id: str
    status: OrderStatus
    broker_order_id: str | None
    message: str


@dataclass
class LiveOrderAdapter:
    transport: OrderTransport
    mode: ExecutionMode = ExecutionMode.LIVE

    def place_limit(self, candidate: TradeCandidate, *, local_id: str | None = None) -> LiveOrderResult:
        assert_live_mutation_allowed()
        if candidate.mode != ExecutionMode.LIVE:
            raise ValueError("Live adapter requires LIVE mode.")
        host = urlparse(f"https://{LIVE_ORDER_HOST}").hostname
        if host != LIVE_ORDER_HOST:
            raise ValueError("Live order host pinned.")
        token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
        if not token:
            return LiveOrderResult(
                local_id or str(uuid.uuid4()),
                OrderStatus.REJECTED,
                None,
                "Missing access token.",
            )
        lid = local_id or str(uuid.uuid4())
        payload = {
            "quantity": candidate.quantity,
            "product": candidate.product.value,
            "validity": "DAY",
            "price": candidate.limit_price_inr,
            "tag": f"nsl-{lid[:8]}",
            "instrument_token": candidate.instrument_key,
            "order_type": "LIMIT",
            "transaction_type": candidate.side.value,
            "disclosed_quantity": 0,
            "trigger_price": 0,
            "is_amo": False,
        }
        url = f"https://{LIVE_ORDER_HOST}/v2/order/place"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json"}
        status, body = self.transport.post(url, body=json.dumps(payload).encode(), headers=headers)
        if status >= 500:
            return LiveOrderResult(lid, OrderStatus.UNKNOWN_SUBMISSION, None, f"Ambiguous HTTP {status}.")
        if status == 401 or status == 403:
            return LiveOrderResult(lid, OrderStatus.REJECTED, None, f"HTTP {status} auth/permission.")
        try:
            data = json.loads(body.decode())
        except json.JSONDecodeError:
            return LiveOrderResult(lid, OrderStatus.UNKNOWN_SUBMISSION, None, "Malformed response.")
        if data.get("status") == "success":
            oid = str(data.get("data", {}).get("order_id", ""))
            return LiveOrderResult(lid, OrderStatus.OPEN, oid or None, "Broker accepted order.")
        return LiveOrderResult(lid, OrderStatus.REJECTED, None, "Broker rejected order.")
