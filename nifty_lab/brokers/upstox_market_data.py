"""Fetch Upstox candles into :class:`MarketDataset`."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from ..data.base import DataKind, DataProvenance, MarketDataset
from ..config import FAKE_SECRET_SENTINEL, _PLACEHOLDER_MARKERS
from .upstox_candles import (
    INTERVAL_5M,
    INTERVAL_DAILY,
    CandleIntervalSpec,
    candles_to_frame,
    drop_incomplete_bars,
    merge_hist_intraday,
    parse_candle_response,
)
from .upstox_errors import UpstoxAuthError, UpstoxEmptyError, UpstoxError
from .upstox_instruments import ResolvedInstrument, encode_instrument_key
from .upstox_transport import API_HOST, HttpTransport, RequestsTransport, build_auth_header

IST = ZoneInfo("Asia/Kolkata")


@dataclass
class UpstoxAccessState:
    verified: bool = False
    verified_at: datetime | None = None
    last_error: str | None = None
    outbound_calls_session: int = 0

    def mark_success(self) -> None:
        self.verified = True
        self.verified_at = datetime.now(ZoneInfo("UTC"))
        self.last_error = None

    def mark_auth_failure(self, message: str) -> None:
        self.verified = False
        self.last_error = message

    def clear(self) -> None:
        self.verified = False
        self.verified_at = None
        self.last_error = None


ACCESS_STATE = UpstoxAccessState()


def _token_present() -> bool:
    """A usable (not rejected, not expired) token exists in the managed store or the environment."""
    from .upstox_auth import resolve_access_token

    return resolve_access_token() is not None


def read_access_token() -> str:
    from .upstox_auth import AuthStatus, auth_status, resolve_access_token

    tok = resolve_access_token()
    if tok is None:
        if auth_status().status == AuthStatus.REAUTH_REQUIRED:
            raise UpstoxAuthError("Upstox rejected the configured token. Reconnect Upstox in Settings & API Connections.")
        raise UpstoxAuthError("No Upstox access token. Reconnect Upstox in Settings & API Connections (or set UPSTOX_ACCESS_TOKEN in .env).")
    return tok.value


def connection_generation() -> int:
    """Non-secret cache generation: 0=no usable token, else changes whenever the active token changes."""
    from .upstox_auth import connection_generation as _gen

    return _gen()


@dataclass
class UpstoxMarketDataService:
    transport: HttpTransport = field(default_factory=RequestsTransport)
    state: UpstoxAccessState = field(default_factory=lambda: ACCESS_STATE)
    _calls_this_click: int = 0

    def reset_call_budget(self) -> None:
        self._calls_this_click = 0

    def _authorized_get(self, path: str) -> bytes:
        if self._calls_this_click >= 4:
            raise UpstoxError("Per-refresh request budget exceeded.", code="BUDGET")
        token = read_access_token()
        url = f"https://{API_HOST}{path}"
        headers = build_auth_header(token)
        if FAKE_SECRET_SENTINEL in token:
            raise UpstoxAuthError("Invalid test token configuration.")
        try:
            status, body, _ = self.transport.get(url, headers=headers, allow_redirects=False)
        except UpstoxAuthError as exc:
            self.state.mark_auth_failure(str(exc))
            raise
        self._calls_this_click += 1
        self.state.outbound_calls_session += 1
        if status in (401, 403):
            self.state.mark_auth_failure("Authentication failed. Set a fresh UPSTOX_ACCESS_TOKEN locally and restart.")
            raise UpstoxAuthError("Authentication failed. Set a fresh UPSTOX_ACCESS_TOKEN locally and restart.")
        if status != 200:
            raise UpstoxError(f"Unexpected status {status}")
        return body

    def fetch_candles_historical(
        self, instrument: ResolvedInstrument, spec: CandleIntervalSpec, from_d: date, to_d: date
    ) -> pd.DataFrame:
        enc = encode_instrument_key(instrument.instrument_key)
        path = (
            f"/v3/historical-candle/{enc}/{spec.unit}/{spec.interval}/"
            f"{to_d.isoformat()}/{from_d.isoformat()}"
        )
        raw = self._authorized_get(path)
        return candles_to_frame(parse_candle_response(raw), spec=spec)

    def fetch_candles_intraday(self, instrument: ResolvedInstrument, spec: CandleIntervalSpec) -> pd.DataFrame:
        enc = encode_instrument_key(instrument.instrument_key)
        path = f"/v3/historical-candle/intraday/{enc}/{spec.unit}/{spec.interval}"
        raw = self._authorized_get(path)
        try:
            return candles_to_frame(parse_candle_response(raw), spec=spec)
        except UpstoxEmptyError:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    def load_dataset(self, instrument: ResolvedInstrument, spec: CandleIntervalSpec) -> MarketDataset:
        self.reset_call_budget()
        today = datetime.now(IST).date()
        try:
            if spec.is_intraday:
                from_d = today - timedelta(days=14)
                to_d = today - timedelta(days=1)
                hist = self.fetch_candles_historical(instrument, spec, from_d, to_d)
                intra = self.fetch_candles_intraday(instrument, spec)
                merged = merge_hist_intraday(hist, intra)
            else:
                from_d = today - timedelta(days=400)
                to_d = today - timedelta(days=1)
                merged = self.fetch_candles_historical(instrument, spec, from_d, to_d)
            completed, dropped = drop_incomplete_bars(merged, spec)
            if completed.empty:
                raise UpstoxEmptyError("No completed candles after quality filters.")
            self.state.mark_success()
        except UpstoxAuthError as exc:
            self.state.mark_auth_failure(str(exc))
            raise
        except UpstoxError:
            raise

        notes = str(completed.attrs.get("broker_notes", ""))
        if dropped:
            notes = (notes + f" dropped_incomplete={dropped}").strip()
        last_bar = completed.index[-1].to_pydatetime()
        prov = DataProvenance(
            kind=DataKind.BROKER_LIVE,
            source="Upstox V3 historical/intraday API",
            symbol=instrument.trading_symbol,
            retrieved_at=datetime.now(ZoneInfo("UTC")),
            last_bar_time=last_bar,
            notes=notes,
            instrument_key=instrument.instrument_key,
            bar_interval=spec.label,
            exchange_tz="Asia/Kolkata",
        )
        return MarketDataset(df=completed, provenance=prov)
