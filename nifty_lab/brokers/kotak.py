"""Kotak Neo adapter (Phase 2 — read-only skeleton).

Facts verified 2026-11-09 (https://github.com/Kotak-Neo/kotak-neo-python):
- Official Python SDK 'kotak-neo-python' (v3.0.x); legacy 'kotak-neo-api-v2' retired.
- Auth: consumer key/secret + mobile, then TOTP + MPIN (interactive; never stored).
- Market data: quotes, scrip master search, option chains, WebSocket streaming,
  historical candles (per README).
This module only *reports* configuration state in v1.
"""
from __future__ import annotations

import os

import pandas as pd

from .base import BrokerStatus, ConnectionState, ReadOnlyBroker


class KotakNeoReadOnly(ReadOnlyBroker):
    name = "Kotak Neo"

    def status(self) -> BrokerStatus:
        key = os.getenv("KOTAK_CONSUMER_KEY", "")
        configured = bool(key.strip()) and "your_" not in key
        state = ConnectionState.CONFIGURED_NOT_CONNECTED if configured else ConnectionState.NOT_CONFIGURED
        detail = "Consumer key present. Interactive TOTP/MPIN login is Phase 2." if configured else "Set KOTAK_CONSUMER_KEY / KOTAK_CONSUMER_SECRET / KOTAK_MOBILE in .env."
        return BrokerStatus(self.name, state, detail, "https://github.com/Kotak-Neo/kotak-neo-python", "API access via Kotak Neo account; check current plan terms. Verified 2026-11-09.", "2026-11-09")

    def historical(self, symbol: str, interval: str, start: str, end: str) -> pd.DataFrame:
        raise NotImplementedError("Kotak Neo historical data integration is scheduled for Phase 2.")

    def option_chain(self, underlying: str, expiry: str) -> pd.DataFrame:
        raise NotImplementedError("Kotak Neo option-chain integration is scheduled for Phase 2.")
