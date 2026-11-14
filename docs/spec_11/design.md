# Design

## Layering

| Layer | Responsibility |
|---|---|
| Spec 10 `load_paper_account_view` | Ledger snapshot + reconciliation (unchanged) |
| `broker_overlay.py` | Fingerprint, batch quote GET, parse by `instrument_token`, freshness, per-position math |
| `ui.py` | Session overlay state, explicit refresh button, separate stored vs broker sections |

## Gating

HTTP only when `view.status == OK` and `len(positions) > 0`. Failed reconciliation or empty book → **zero** outbound calls.

## API

- `GET https://api.upstox.com/v2/market-quote/quotes` with ≤10 URL-encoded `instrument_key` params (deduped from `positions.instrument_key`).
- Reuse `build_auth_header`, `read_access_token`, `HttpTransport` from `nifty_lab.brokers`.
- Match each row by JSON `instrument_token`, not response map keys.

## Timestamps

Keep `retrieved_at_utc` (local), provider `timestamp`, and `last_trade_time` separate. Parse timezone-qualified ISO and documented epoch-ms variants; reject naive/malformed/future trade times.

Freshness: conservative **15s** from `retrieved_at` to effective trade time. HTTP 200 ≠ fresh trade. Stale rows labeled; portfolio overlay totals require **fresh** coverage for **all** open positions.

## Session overlay

Streamlit `session_state` only. Bind overlay to account fingerprint `(instrument_key, qty, avg, entry_fees)`. Clear/invalidate on mismatch or failed refresh (do not relabel old quotes as fresh).

## UX

Never “BROKER LIVE.” Stored-mark equity section remains. Broker section shows source, ages, and “excludes future exit costs — not net liquidation.”

## Errors

Map `UpstoxAuthError`, `UpstoxRateLimitError`, `UpstoxUnavailableError`, `UpstoxDataError` to sanitized UI codes; no tokens, headers, or raw bodies in logs/UI.
