"""Bounded historical candle GET for audit."""
from __future__ import annotations

import json
from datetime import date

from nifty_lab.brokers.upstox_candles import parse_candle_response
from nifty_lab.brokers.upstox_errors import (
    UpstoxAuthError,
    UpstoxDataError,
    UpstoxEmptyError,
    UpstoxRateLimitError,
    UpstoxUnavailableError,
)
from nifty_lab.brokers.upstox_instruments import encode_instrument_key
from nifty_lab.brokers.upstox_market_data import read_access_token
from nifty_lab.brokers.upstox_transport import API_HOST, HttpTransport, build_auth_header
from nifty_lab.config import FAKE_SECRET_SENTINEL

from .budget import AuditRequestBudget


def historical_candle_path(instrument_key: str, *, to_d: date, from_d: date) -> str:
    enc = encode_instrument_key(instrument_key)
    return f"/v3/historical-candle/{enc}/days/1/{to_d.isoformat()}/{from_d.isoformat()}"


def _map_transport_error(exc: Exception) -> tuple[int | None, str]:
    if isinstance(exc, UpstoxAuthError):
        return 401, "AUTH_BLOCKED"
    if isinstance(exc, UpstoxRateLimitError):
        return 429, "RATE_LIMITED"
    if isinstance(exc, UpstoxUnavailableError):
        return 503, "UNAVAILABLE"
    if isinstance(exc, UpstoxDataError):
        return 400, "TRANSPORT_REJECTED"
    return None, "TRANSPORT_ERROR"


def fetch_historical_candles_raw(
    transport: HttpTransport,
    budget: AuditRequestBudget,
    *,
    instrument_key: str,
    from_d: date,
    to_d: date,
    window_label: str,
) -> tuple[int | None, list[list] | None, str | None]:
    """One historical GET; returns (http_status, candles or None, sanitized error_class)."""
    budget.consume_historical(label=window_label)
    try:
        token = read_access_token()
    except UpstoxAuthError:
        return 401, None, "AUTH_BLOCKED"
    if FAKE_SECRET_SENTINEL in token:
        return 401, None, "AUTH_BLOCKED"
    url = f"https://{API_HOST}{historical_candle_path(instrument_key, from_d=from_d, to_d=to_d)}"
    headers = build_auth_header(token)
    if FAKE_SECRET_SENTINEL in headers.get("Authorization", ""):
        return 401, None, "AUTH_BLOCKED"
    try:
        status, body, _ = transport.get(url, headers=headers, allow_redirects=False)
    except Exception as exc:
        status, err = _map_transport_error(exc)
        return status, None, err
    if status in (401, 403):
        return status, None, "AUTH_BLOCKED"
    if status == 429:
        return status, None, "RATE_LIMITED"
    if status >= 500:
        return status, None, "UNAVAILABLE"
    if status != 200:
        return status, None, "HTTP_ERROR"
    try:
        candles = parse_candle_response(body)
        return status, candles, None
    except UpstoxEmptyError:
        return status, [], "EMPTY"
    except UpstoxDataError:
        return status, None, "PARSE_ERROR"


def sanitized_public_payload(raw_candles: list[list]) -> bytes:
    """Store only public OHLCV payload (no HTTP metadata)."""
    return json.dumps({"candles": raw_candles}, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
