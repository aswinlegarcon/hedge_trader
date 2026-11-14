"""Broker full-quote BBO/depth for Paper sell-to-close (Spec 12)."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from nifty_lab.brokers.upstox_errors import UpstoxDataError
from nifty_lab.brokers.upstox_transport import HttpTransport
from nifty_lab.paper_account.broker_overlay import (
    FRESHNESS_SECONDS,
    _provider_timestamp,
    _trade_timestamp,
    fetch_market_quotes,
    utc_now,
)
from nifty_lab.paper_account.broker_overlay import Clock

from .types import InstrumentKind, QuoteSnapshot

DepthError = UpstoxDataError


@dataclass(frozen=True)
class BrokerCloseQuoteCapture:
    quote: QuoteSnapshot
    retrieved_at: datetime
    instrument_token: str
    provider_ts_utc: datetime
    trade_ts_utc: datetime
    provider_timestamp_raw: str
    last_trade_time_raw: str


def _strict_price(val: Any, *, field: str) -> float:
    if isinstance(val, bool) or val is None:
        raise DepthError(f"{field} missing or invalid.", code="DEPTH_PRICE_INVALID")
    try:
        price = float(val)
    except (TypeError, ValueError) as exc:
        raise DepthError(f"{field} malformed.", code="DEPTH_PRICE_INVALID") from exc
    if not math.isfinite(price) or price <= 0:
        raise DepthError(f"{field} nonpositive or nonfinite.", code="DEPTH_PRICE_INVALID")
    return price


def _strict_whole_qty(val: Any, *, field: str) -> int:
    if isinstance(val, bool):
        raise DepthError(f"{field} invalid.", code="DEPTH_QTY_INVALID")
    if isinstance(val, int):
        if val <= 0:
            raise DepthError(f"{field} nonpositive.", code="DEPTH_QTY_INVALID")
        return val
    if isinstance(val, float):
        if not math.isfinite(val) or val != math.floor(val) or val <= 0:
            raise DepthError(f"{field} fractional or invalid.", code="DEPTH_QTY_INVALID")
        return int(val)
    raise DepthError(f"{field} missing or invalid.", code="DEPTH_QTY_INVALID")


def _top_of_book(levels: Any, *, side: str) -> tuple[float, int]:
    if not isinstance(levels, list) or not levels:
        raise DepthError(f"{side} depth missing.", code="DEPTH_INCOMPLETE")
    row = levels[0]
    if not isinstance(row, dict):
        raise DepthError(f"{side} depth malformed.", code="DEPTH_INCOMPLETE")
    price = _strict_price(row.get("price"), field=f"{side} price")
    qty = _strict_whole_qty(row.get("quantity"), field=f"{side} quantity")
    return price, qty


def _require_both_timestamps(
    row: dict[str, Any],
    *,
    retrieved_at: datetime,
) -> tuple[datetime, datetime, str, str]:
    retrieved = retrieved_at.astimezone(timezone.utc)
    prov_ts, perr = _provider_timestamp(row)
    if prov_ts is None:
        raise DepthError(
            f"Provider timestamp invalid ({perr}).",
            code=perr or "PROVIDER_TIMESTAMP_MISSING",
        )
    trade_ts, terr = _trade_timestamp(row)
    if trade_ts is None:
        raise DepthError(
            f"Trade timestamp invalid ({terr}).",
            code=terr or "TRADE_TIMESTAMP_MISSING",
        )
    if prov_ts > retrieved:
        raise DepthError("Provider timestamp in the future.", code="PROVIDER_TIMESTAMP_FUTURE")
    if trade_ts > retrieved:
        raise DepthError("Trade timestamp in the future.", code="TRADE_TIMESTAMP_FUTURE")
    for ts, code in ((prov_ts, "PROVIDER_TIMESTAMP_STALE"), (trade_ts, "TRADE_TIMESTAMP_STALE")):
        age = (retrieved - ts).total_seconds()
        if age > FRESHNESS_SECONDS:
            raise DepthError("Quote snapshot too old at receipt.", code=code)
    prov_raw = str(row.get("timestamp", ""))
    trade_raw = str(row.get("last_trade_time") or row.get("last_trade_timestamp") or "")
    return prov_ts, trade_ts, prov_raw, trade_raw


def _row_by_instrument_token(data: dict[str, Any], expected: str) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for candidate in data.values():
        if not isinstance(candidate, dict):
            continue
        token = str(candidate.get("instrument_token", "")).strip()
        if token == expected:
            matches.append(candidate)
    if not matches:
        raise DepthError("Instrument quote missing.", code="INSTRUMENT_MISSING")
    if len(matches) > 1:
        raise DepthError("Duplicate instrument_token rows.", code="DUPLICATE_TOKEN")
    return matches[0]


def parse_close_quote_payload(
    body: bytes,
    *,
    instrument_key: str,
    retrieved_at: datetime,
    expected_instrument_token: str | None = None,
) -> BrokerCloseQuoteCapture:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DepthError("Malformed quote payload.", code="MALFORMED_PAYLOAD") from exc
    if not isinstance(payload, dict) or str(payload.get("status", "")).lower() != "success":
        raise DepthError("Quote response not success.", code="RESPONSE_NOT_SUCCESS")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise DepthError("Malformed quote data.", code="MALFORMED_PAYLOAD")

    expected = (expected_instrument_token or instrument_key).strip()
    row = _row_by_instrument_token(data, expected)

    token = str(row.get("instrument_token", "")).strip()
    if token != expected:
        raise DepthError("instrument_token mismatch.", code="TOKEN_MISMATCH")

    depth = row.get("depth")
    if not isinstance(depth, dict):
        raise DepthError("depth missing.", code="DEPTH_MISSING")
    bid, bid_qty = _top_of_book(depth.get("buy"), side="bid")
    ask, ask_qty = _top_of_book(depth.get("sell"), side="ask")

    prov_ts, trade_ts, prov_raw, trade_raw = _require_both_timestamps(row, retrieved_at=retrieved_at)
    conservative_at = prov_ts if prov_ts <= trade_ts else trade_ts

    quote = QuoteSnapshot(
        bid=bid,
        ask=ask,
        bid_qty=bid_qty,
        ask_qty=ask_qty,
        instrument_key=instrument_key,
        evaluated_at=conservative_at,
        source="upstox_full_quote_v2",
    )
    if not quote.is_valid():
        raise DepthError("Crossed or invalid BBO.", code="BBO_INVALID")

    return BrokerCloseQuoteCapture(
        quote=quote,
        retrieved_at=retrieved_at.astimezone(timezone.utc),
        instrument_token=token,
        provider_ts_utc=prov_ts,
        trade_ts_utc=trade_ts,
        provider_timestamp_raw=prov_raw,
        last_trade_time_raw=trade_raw,
    )


def fetch_broker_close_quote(
    instrument_key: str,
    *,
    instrument_kind: InstrumentKind,
    transport: HttpTransport,
    expected_instrument_token: str | None = None,
    clock: Clock | None = None,
) -> BrokerCloseQuoteCapture:
    if instrument_kind not in (InstrumentKind.CASH_STOCK, InstrumentKind.CASH_ETF):
        raise ValueError("Broker close quote is for cash stocks/ETFs in PAPER mode only.")
    body, retrieved_at = fetch_market_quotes([instrument_key], transport, clock=clock or utc_now)
    return parse_close_quote_payload(
        body,
        instrument_key=instrument_key,
        retrieved_at=retrieved_at,
        expected_instrument_token=expected_instrument_token,
    )
