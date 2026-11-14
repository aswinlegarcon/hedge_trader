"""Session-scoped Upstox quote overlay for reconciled Paper positions (no DB writes)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable

from nifty_lab.brokers.upstox_errors import (
    UpstoxAuthError,
    UpstoxDataError,
    UpstoxError,
    UpstoxRateLimitError,
    UpstoxUnavailableError,
)
from nifty_lab.brokers.upstox_instruments import encode_instrument_key
from nifty_lab.brokers.upstox_market_data import read_access_token
from nifty_lab.brokers.upstox_transport import API_HOST, HttpTransport, build_auth_header

from .accounting import PaperAccountView, PositionView
from .decimal_inr import round_inr as _round_inr

FRESHNESS_SECONDS = 15
MAX_INSTRUMENT_KEYS = 10
QUOTES_PATH = "/v2/market-quote/quotes"

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class CachedQuoteRow:
    instrument_key: str
    instrument_token: str
    last_price: Decimal
    provider_ts_utc: datetime
    trade_ts_utc: datetime
    raw_provider: str
    raw_trade: str


@dataclass
class BrokerOverlayCache:
    fingerprint: str
    retrieved_at_utc: datetime
    quotes: dict[str, CachedQuoteRow] = field(default_factory=dict)


@dataclass(frozen=True)
class BrokerPositionOverlay:
    instrument_key: str
    instrument_token: str
    last_price_inr: str
    position_value_inr: str
    gross_unrealized_inr: str
    unrealized_after_entry_fees_inr: str
    freshness: str
    trade_age_seconds: float
    retrieval_age_seconds: float
    retrieved_at_utc: str
    provider_timestamp: str
    last_trade_time: str
    age_note: str


@dataclass
class BrokerOverlayBundle:
    status: str
    error: str | None
    fingerprint: str | None
    fetched_at_utc: str | None
    positions: list[BrokerPositionOverlay] = field(default_factory=list)
    portfolio_value_inr: str | None = None
    gross_unrealized_total_inr: str | None = None
    unrealized_after_fees_total_inr: str | None = None
    coverage_note: str | None = None


@dataclass(frozen=True)
class BrokerFetchResult:
    ok: bool
    cache: BrokerOverlayCache | None = None
    error: str | None = None


def account_fingerprint(view: PaperAccountView) -> str | None:
    if view.status != "OK" or not view.positions:
        return None
    parts: list[str] = [f"cash={view.cash_inr or ''}"]
    for p in sorted(view.positions, key=lambda x: x.instrument_key):
        parts.append(
            f"{p.instrument_key}|{p.quantity}|{p.cost_basis_inr}|{p.entry_fees_inr}"
        )
    digest = hashlib.sha256("\n".join(parts).encode()).hexdigest()
    return digest[:32]


def select_instrument_keys(positions: list[PositionView]) -> tuple[list[str], str | None]:
    seen: set[str] = set()
    out: list[str] = []
    for p in sorted(positions, key=lambda x: x.instrument_key):
        key = p.instrument_key.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    if not out:
        return [], "NO_KEYS"
    if len(out) > MAX_INSTRUMENT_KEYS:
        return [], "BATCH_LIMIT"
    return out, None


def _parse_iso_utc(raw: str) -> datetime | None:
    try:
        ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if ts.tzinfo is None:
        return None
    return ts.astimezone(timezone.utc)


def _parse_epoch_ms_value(raw: int) -> datetime | None:
    if raw < 100_000_000_000:
        return None
    try:
        return datetime.fromtimestamp(raw / 1000.0, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None


def _parse_documented_timestamp(raw: Any) -> datetime | None:
    """ISO-with-timezone or epoch milliseconds on the same documented field."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return _parse_epoch_ms_value(raw)
    if isinstance(raw, float) and raw.is_integer():
        return _parse_epoch_ms_value(int(raw))
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    iso = _parse_iso_utc(text)
    if iso is not None:
        return iso
    if text.isdigit():
        return _parse_epoch_ms_value(int(text))
    return None


def _provider_timestamp(row: dict[str, Any]) -> tuple[datetime | None, str | None]:
    if "timestamp" not in row or row["timestamp"] is None:
        return None, "PROVIDER_TIMESTAMP_MISSING"
    ts = _parse_documented_timestamp(row["timestamp"])
    if ts is None:
        return None, "PROVIDER_TIMESTAMP_INVALID"
    return ts, None


def _trade_timestamp(row: dict[str, Any]) -> tuple[datetime | None, str | None]:
    raw = row.get("last_trade_time")
    if raw is None:
        raw = row.get("last_trade_timestamp")
    if raw is None:
        return None, "TRADE_TIMESTAMP_MISSING"
    ts = _parse_documented_timestamp(raw)
    if ts is None:
        return None, "TRADE_TIMESTAMP_INVALID"
    return ts, None


def _last_price_only(row: dict[str, Any]) -> Decimal | None:
    if "last_price" not in row:
        return None
    try:
        x = Decimal(str(row["last_price"]))
    except Exception:
        return None
    if not x.is_finite() or x <= 0:
        return None
    return x


def parse_quotes_response(
    body: bytes,
    *,
    requested_keys: list[str],
    retrieved_at: datetime,
) -> tuple[dict[str, CachedQuoteRow], str | None]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}, "MALFORMED_PAYLOAD"
    if not isinstance(payload, dict):
        return {}, "MALFORMED_PAYLOAD"
    if str(payload.get("status", "")).lower() != "success":
        return {}, "RESPONSE_NOT_SUCCESS"
    data = payload.get("data")
    if not isinstance(data, dict):
        return {}, "MALFORMED_PAYLOAD"

    requested = set(requested_keys)
    by_key: dict[str, CachedQuoteRow] = {}
    seen_tokens: set[str] = set()

    for row in data.values():
        if not isinstance(row, dict):
            return {}, "MALFORMED_ROW"
        token = row.get("instrument_token")
        if not isinstance(token, str) or not token.strip():
            return {}, "MISSING_INSTRUMENT_TOKEN"
        token = token.strip()
        if token not in requested:
            return {}, "UNEXPECTED_INSTRUMENT_TOKEN"
        if token in seen_tokens:
            return {}, "DUPLICATE_INSTRUMENT_TOKEN"
        seen_tokens.add(token)

        price = _last_price_only(row)
        if price is None:
            return {}, "INVALID_LAST_PRICE"

        provider_ts, p_err = _provider_timestamp(row)
        if p_err:
            return {}, p_err
        trade_ts, t_err = _trade_timestamp(row)
        if t_err:
            return {}, t_err
        assert provider_ts is not None and trade_ts is not None
        if provider_ts > retrieved_at.astimezone(timezone.utc) + timedelta(seconds=2):
            return {}, "FUTURE_PROVIDER_TIMESTAMP"
        if trade_ts > retrieved_at.astimezone(timezone.utc) + timedelta(seconds=2):
            return {}, "FUTURE_TRADE_TIMESTAMP"

        raw_p = row.get("timestamp")
        raw_t = row.get("last_trade_time", row.get("last_trade_timestamp"))
        by_key[token] = CachedQuoteRow(
            instrument_key=token,
            instrument_token=token,
            last_price=price,
            provider_ts_utc=provider_ts,
            trade_ts_utc=trade_ts,
            raw_provider=str(raw_p),
            raw_trade=str(raw_t),
        )

    return by_key, None


def build_quotes_url(instrument_keys: list[str]) -> str:
    if not instrument_keys:
        raise UpstoxDataError("No instrument keys to quote.", code="NO_KEYS")
    if len(instrument_keys) > MAX_INSTRUMENT_KEYS:
        raise UpstoxDataError("Instrument key batch exceeds limit.", code="BATCH_LIMIT")
    joined = ",".join(encode_instrument_key(k) for k in instrument_keys)
    return f"https://{API_HOST}{QUOTES_PATH}?instrument_key={joined}"


def fetch_market_quotes(
    instrument_keys: list[str],
    transport: HttpTransport,
    *,
    clock: Clock | None = None,
) -> tuple[bytes, datetime]:
    clk = clock or utc_now
    token = read_access_token()
    url = build_quotes_url(instrument_keys)
    headers = build_auth_header(token)
    status, body, _hdrs = transport.get(url, headers=headers, allow_redirects=False)
    retrieved_at = clk().astimezone(timezone.utc)
    if status in (401, 403):
        raise UpstoxAuthError("Authentication failed. Set a fresh UPSTOX_ACCESS_TOKEN locally and restart.")
    if status == 429:
        raise UpstoxRateLimitError("Rate limited. Wait and use manual refresh.")
    if status >= 500:
        raise UpstoxUnavailableError("Broker quote service unavailable.")
    if status != 200:
        raise UpstoxDataError(f"Quote request rejected ({status}).", code="HTTP_ERROR")
    return body, retrieved_at


def _trade_fresh(trade_ts: datetime, *, now: datetime, retrieved_at: datetime) -> tuple[str, float, float]:
    trade_age = (now - trade_ts).total_seconds()
    retrieval_age = (now - retrieved_at).total_seconds()
    if trade_age < 0:
        return "INVALID", trade_age, retrieval_age
    label = "FRESH" if trade_age <= FRESHNESS_SECONDS else "STALE"
    return label, trade_age, retrieval_age


def materialize_overlay(
    view: PaperAccountView,
    cache: BrokerOverlayCache,
    *,
    now: datetime | None = None,
) -> BrokerOverlayBundle:
    fp = account_fingerprint(view)
    now_utc = (now or utc_now()).astimezone(timezone.utc)
    if view.status != "OK" or fp is None or fp != cache.fingerprint:
        return BrokerOverlayBundle(
            status="UNAVAILABLE",
            error="ACCOUNT_CHANGED",
            fingerprint=fp,
            fetched_at_utc=cache.retrieved_at_utc.isoformat(),
        )

    overlays: list[BrokerPositionOverlay] = []
    all_fresh = True
    any_quote = False
    gross_total = Decimal("0")
    after_fees_total = Decimal("0")
    mv_total = Decimal("0")
    retrieved = cache.retrieved_at_utc.astimezone(timezone.utc)

    for pos in view.positions:
        row = cache.quotes.get(pos.instrument_key)
        if row is None:
            all_fresh = False
            overlays.append(
                BrokerPositionOverlay(
                    instrument_key=pos.instrument_key,
                    instrument_token="—",
                    last_price_inr="—",
                    position_value_inr="—",
                    gross_unrealized_inr="—",
                    unrealized_after_entry_fees_inr="—",
                    freshness="MISSING",
                    trade_age_seconds=-1.0,
                    retrieval_age_seconds=(now_utc - retrieved).total_seconds(),
                    retrieved_at_utc=retrieved.isoformat(),
                    provider_timestamp="—",
                    last_trade_time="—",
                    age_note="No broker quote for requested instrument token.",
                )
            )
            continue

        fresh, trade_age, retrieval_age = _trade_fresh(
            row.trade_ts_utc, now=now_utc, retrieved_at=retrieved
        )
        if fresh != "FRESH":
            all_fresh = False

        cost_basis = Decimal(pos.cost_basis_inr)
        entry_fees = Decimal(pos.entry_fees_inr)
        qty = Decimal(pos.quantity)
        mv = qty * row.last_price
        gross_u = _round_inr(mv - cost_basis)
        unreal_af = _round_inr(gross_u - entry_fees)
        any_quote = True

        if fresh == "FRESH":
            gross_total += gross_u
            after_fees_total += unreal_af
            mv_total += mv

        age_note = (
            f"Trade age ~{trade_age:.1f}s · retrieval age ~{retrieval_age:.1f}s "
            f"(retrieved {retrieved.isoformat()}) — "
            f"{'within' if fresh == 'FRESH' else 'outside'} {FRESHNESS_SECONDS}s indicative window."
        )
        overlays.append(
            BrokerPositionOverlay(
                instrument_key=pos.instrument_key,
                instrument_token=row.instrument_token,
                last_price_inr=str(_round_inr(row.last_price)),
                position_value_inr=str(_round_inr(mv)),
                gross_unrealized_inr=str(gross_u),
                unrealized_after_entry_fees_inr=str(unreal_af),
                freshness=fresh,
                trade_age_seconds=trade_age,
                retrieval_age_seconds=retrieval_age,
                retrieved_at_utc=retrieved.isoformat(),
                provider_timestamp=row.raw_provider,
                last_trade_time=row.raw_trade,
                age_note=age_note,
            )
        )

    cash = Decimal(view.cash_inr or "0")
    coverage = None
    pf_val: str | None = None
    g_tot: str | None = None
    u_tot: str | None = None
    status = "OK" if any_quote else "EMPTY"
    if not all_fresh:
        coverage = (
            "Broker portfolio totals unavailable — missing quotes and/or trade age beyond "
            f"{FRESHNESS_SECONDS}s at display time (evaluated without new HTTP)."
        )
    elif view.positions:
        pf_val = str(_round_inr(cash + mv_total))
        g_tot = str(_round_inr(gross_total))
        u_tot = str(_round_inr(after_fees_total))

    return BrokerOverlayBundle(
        status=status,
        error=None,
        fingerprint=fp,
        fetched_at_utc=retrieved.isoformat(),
        positions=overlays,
        portfolio_value_inr=pf_val,
        gross_unrealized_total_inr=g_tot,
        unrealized_after_fees_total_inr=u_tot,
        coverage_note=coverage,
    )


def refresh_broker_overlay(
    view: PaperAccountView,
    transport: HttpTransport,
    *,
    clock: Clock | None = None,
) -> BrokerFetchResult:
    fp = account_fingerprint(view)
    if view.status != "OK" or fp is None:
        reason = "RECONCILIATION_FAILED" if view.status != "OK" else "NO_POSITIONS"
        return BrokerFetchResult(ok=False, error=reason)
    keys, key_err = select_instrument_keys(view.positions)
    if key_err:
        return BrokerFetchResult(ok=False, error=key_err)
    try:
        body, fetched_at = fetch_market_quotes(keys, transport, clock=clock)
        by_key, parse_err = parse_quotes_response(body, requested_keys=keys, retrieved_at=fetched_at)
        if parse_err:
            return BrokerFetchResult(ok=False, error=parse_err)
        return BrokerFetchResult(
            ok=True,
            cache=BrokerOverlayCache(
                fingerprint=fp,
                retrieved_at_utc=fetched_at.astimezone(timezone.utc),
                quotes=by_key,
            ),
        )
    except UpstoxError as exc:
        code = exc.code if hasattr(exc, "code") else "UPSTOX_ERROR"
        return BrokerFetchResult(ok=False, error=code)


def build_overlay_bundle(
    view: PaperAccountView,
    quotes_by_token: dict[str, Any],
    *,
    fetched_at: datetime,
    fetch_error: str | None = None,
    now: datetime | None = None,
) -> BrokerOverlayBundle:
    """Test helper: adapt legacy quote dicts into cache + materialize."""
    if fetch_error:
        return BrokerOverlayBundle(
            status="FETCH_FAILED",
            error=fetch_error,
            fingerprint=account_fingerprint(view),
            fetched_at_utc=fetched_at.isoformat(),
        )
    cache_rows: dict[str, CachedQuoteRow] = {}
    for key, row in quotes_by_token.items():
        cache_rows[key] = CachedQuoteRow(
            instrument_key=key,
            instrument_token=str(row["instrument_token"]),
            last_price=row["last_price"],
            provider_ts_utc=row["provider_ts"],
            trade_ts_utc=row["trade_ts"],
            raw_provider=str(row.get("raw_provider", "")),
            raw_trade=str(row.get("raw_trade", "")),
        )
    fp = account_fingerprint(view)
    cache = BrokerOverlayCache(
        fingerprint=fp or "",
        retrieved_at_utc=fetched_at.astimezone(timezone.utc),
        quotes=cache_rows,
    )
    return materialize_overlay(view, cache, now=now or fetched_at)
