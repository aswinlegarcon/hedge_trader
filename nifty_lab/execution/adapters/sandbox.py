"""Sandbox order adapter — separate token/host, never falls back to live (Spec 08)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from ..modes import ExecutionMode
from ..types import OrderStatus, TradeCandidate
from .live import LiveOrderResult, OrderTransport

SANDBOX_ORDER_HOST = "api-sandbox.upstox.com"


@dataclass
class SandboxOrderAdapter:
    transport: OrderTransport

    def place_limit(self, candidate: TradeCandidate, *, local_id: str) -> LiveOrderResult:
        if candidate.mode != ExecutionMode.SANDBOX:
            raise ValueError("Sandbox adapter requires SANDBOX mode.")
        token = os.getenv("UPSTOX_SANDBOX_ACCESS_TOKEN", "").strip()
        if not token:
            return LiveOrderResult(local_id, OrderStatus.REJECTED, None, "Sandbox token not configured.")
        # Sandbox path documented separately — fail closed if host unavailable in this build.
        if os.getenv("UPSTOX_SANDBOX_ENABLED", "").strip() not in ("1", "true", "True"):
            return LiveOrderResult(
                local_id,
                OrderStatus.REJECTED,
                None,
                "Sandbox adapter disabled (set UPSTOX_SANDBOX_ENABLED=1 after verifying official sandbox host).",
            )
        return LiveOrderResult(local_id, OrderStatus.REJECTED, None, "Sandbox place not wired for this account in agent build.")
