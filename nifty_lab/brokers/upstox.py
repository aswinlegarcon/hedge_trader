"""Upstox read-only adapter — status plus market-data service (Spec 04)."""
from __future__ import annotations

import os

import pandas as pd

from .base import BrokerStatus, ConnectionState, ReadOnlyBroker
from .upstox_market_data import ACCESS_STATE, _token_present


class UpstoxReadOnly(ReadOnlyBroker):
    name = "Upstox API"

    def status(self) -> BrokerStatus:
        has_token = _token_present()
        if not has_token:
            state = ConnectionState.NOT_CONFIGURED
            detail = (
                "Market data needs UPSTOX_ACCESS_TOKEN in .env (never in chat). "
                "Obtain via the official Upstox developer OAuth flow, then restart."
            )
        elif ACCESS_STATE.verified:
            state = ConnectionState.CONNECTED
            detail = (
                "Last authorized candle fetch succeeded. Data is API history, not a live quote stream. "
                "Use Load/Refresh in the sidebar for updates."
            )
        else:
            state = ConnectionState.CONFIGURED_NOT_CONNECTED
            detail = (
                "Access token appears set. Use Upstox → Load/Refresh to verify connectivity. "
                "Token presence alone does not mean connected."
            )
            if ACCESS_STATE.last_error:
                detail += f" Last error: {ACCESS_STATE.last_error}"
        return BrokerStatus(
            self.name,
            state,
            detail,
            "https://upstox.com/developer/api-documentation/",
            "API terms depend on your Upstox account.",
            "2026-11-13",
        )

    def historical(self, symbol: str, interval: str, start: str, end: str) -> pd.DataFrame:
        raise NotImplementedError("Use UpstoxMarketDataService.load_dataset for candle access.")

    def option_chain(self, underlying: str, expiry: str) -> pd.DataFrame:
        raise NotImplementedError("Option chains are out of scope for Spec 04.")
