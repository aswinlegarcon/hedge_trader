"""Zerodha Kite Connect adapter (Phase 2 — read-only skeleton).

Facts verified 2026-11-09 (https://kite.trade/docs/connect/v3/):
- Login: https://kite.zerodha.com/connect/login?v=3&api_key=... -> request_token
  -> POST /session/token with checksum SHA256(api_key + request_token + api_secret)
  -> access_token, expires 06:00 next day (regulatory).
- Rate limits: quote 1 req/s, historical 3 req/s, others 10 req/s.
- Historical intervals: minute, 3/5/10/15/30/60minute, day.
- WebSocket: up to 3000 instruments per connection, 3 connections per API key.
- Pricing: ₹500/month per app; historical data included since 2025-02-08.
This module only *reports* configuration state in v1. No network calls yet.
"""
from __future__ import annotations

import os

import pandas as pd

from .base import BrokerStatus, ConnectionState, ReadOnlyBroker


class KiteReadOnly(ReadOnlyBroker):
    name = "Zerodha Kite Connect"

    def status(self) -> BrokerStatus:
        key = os.getenv("KITE_API_KEY", "")
        tok = os.getenv("KITE_ACCESS_TOKEN", "")
        configured = bool(key.strip()) and "your_" not in key
        if not configured:
            state, detail = ConnectionState.NOT_CONFIGURED, "Set KITE_API_KEY / KITE_API_SECRET in .env (never in chat)."
        elif not tok.strip():
            state, detail = ConnectionState.CONFIGURED_NOT_CONNECTED, "API key present. Daily login flow needed to obtain access_token (expires 06:00 IST)."
        else:
            state, detail = ConnectionState.CONFIGURED_NOT_CONNECTED, "Token present but live connectivity is Phase 2 — not wired in v1."
        return BrokerStatus(self.name, state, detail, "https://kite.trade/docs/connect/v3/", "₹500/month per app (historical data included). Verified 2026-11-09.", "2026-11-09")

    def historical(self, symbol: str, interval: str, start: str, end: str) -> pd.DataFrame:
        raise NotImplementedError("Kite historical data integration is scheduled for Phase 2.")

    def option_chain(self, underlying: str, expiry: str) -> pd.DataFrame:
        raise NotImplementedError("Kite option-chain integration is scheduled for Phase 2.")
