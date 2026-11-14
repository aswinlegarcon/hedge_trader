# Design

## Integration flow

User explicitly selects Upstox → resolve instrument using official NSE JSON master → select daily or 5m → click Load/Refresh → read backend token from UPSTOX_ACCESS_TOKEN → fetch historical and, for 5m through today, intraday data → validate/merge completed candles → MarketDataset → existing chart/indicator consumers with selected-symbol and interval labels.

No I/O at module import, status render or unrelated page rerun. `ReadOnlyBroker.historical` can retain its DataFrame contract; add a dataset-building service to attach provenance. Add `intraday` additively. `option_chain` stays unavailable. Do not return a mixed object shape from historical.

## Transport and authentication

Prefer a small requests.Session wrapper with explicit requests dependency (already shown in official examples), injected transport for tests, TLS verification enabled and finite timeouts (connect 3s/read 10s). Only permit GET requests to the fixed API candle paths below plus the fixed official instrument asset URL. No generic endpoint entry field; no order-capable SDK dependency.

Allowed authenticated host: api.upstox.com. Paths:
- `/v3/historical-candle/{encoded_instrument_key}/{unit}/{interval}/{to_date}/{from_date}`
- `/v3/historical-candle/intraday/{encoded_instrument_key}/{unit}/{interval}`

Use documented NSE BOD JSON URL linked from the official instruments page (gzip if supplied), never attach Authorization to public assets. Disable automatic authenticated redirects, or validate the same host before any redirect; do not forward bearer headers to another host. URL-encode the instrument key as one path component.

The token is read only by backend runtime to form the Authorization header. No token UI field, log, exception text, command-line argument, cache key, downloadable file or Streamlit session-state value. Never print env contents or raw response/request/header objects. Do not copy the documentation's raw response/exception printing patterns. For tests disable dotenv loading and inject fake tokens. Existing API key/secret/redirect fields may remain presence-only; this slice needs only a valid access token.

Settings explains how to obtain a token via an official supported Upstox flow and set UPSTOX_ACCESS_TOKEN locally, then restart/reload configuration. No login automation or secret file editing by the agent. A missing token returns NOT_CONFIGURED for data access even if key/secret are present; distinguish app configuration from usable data token. Token presence alone never means CONNECTED. Only a successful authorized candle response may establish verified data access, with check time and empty-data state separate. A later 401/403 clears the verified state. Do not invent daily token expiry time or auto-refresh capability; handle authentication failure by asking for a newly generated local token.

## Instruments and fetching

Cache public master in memory for the running app for up to 24h with retrieval time; allow explicit refresh. Match candidate symbols with exchange/segment filtering and show exact security identity. Treat ETF records according to official instrument metadata, not an assumed universal instrument_type. No fuzzy auto-selection; missing/ambiguous resolution yields a user decision or NO DATA.

Offer 5m (minutes/5) and daily (days/1). Default historical window for 5m is 14 calendar days, max one calendar month for this slice; cap rather than build pagination now. Daily default 400 calendar days, cap 2 years. Warn on insufficient warm-up bars. For dates through today combine previous-date historical with today's intraday endpoint; if today is a holiday/no trades, preserve earlier history and show no current-session data, not a fabricated row. Calendar dates use Asia/Kolkata.

Use only completed intraday bars (bar start + interval ≤ evaluation time); flag/drop the forming final bar from indicator inputs. Exclude the current day's daily bar from completed daily indicators unless end-of-session completion is established; simplest first slice uses history through yesterday for daily. Show a forming bar only if clearly separate; not required.

Sort ascending with timezone-aware timestamps preserving instant and displaying Asia/Kolkata. Validate finite positive consistent OHLC, finite nonnegative volume, expected shape and parseable offset timestamps before existing validator can silently repair them. Missing volume is unknown: reject that response for indicator use with a diagnostic, not zero substitution. Identical duplicate rows can deduplicate with a count; conflicting duplicates fail with diagnostic. Preserve OI only as optional metadata if convenient; OHLCV consumers retain their shape. Do not build a full exchange calendar now; disclose gaps and holiday/session validation limitations rather than invent fills.

## Refresh, errors and provenance

Manual load/refresh only. Cache market data briefly (e.g. 30s) within session, keyed by public instrument, interval, dates and non-secret local connection generation, never token. Explicit refresh invalidates the selected request. Token replacement/disconnect clears authenticated caches without using token text or a token hash as a cache key. No cross-user/global cache of authenticated data.

Conservative request budget: one in-flight fetch per session; max 4 outbound calls per click (asset retrieval, historical, intraday and at most one retry combined). Limit active app transport to ≤1 request/s and budget repeated UI refreshes. 401/403 not retried; 400/invalid instrument not retried. One bounded retry for transient transport/5xx/429, honoring Retry-After only up to 3s then return retry-later. Do not wait long or loop indefinitely.

Use typed, sanitized errors: missing token, authentication required/access denied, invalid instrument/range, rate limited, unavailable/timeout, malformed response, no candles. No synthetic fallback on error. Clear active broker dataset on selection change/failure; any last-good chart kept for reference must be explicitly marked stale with old symbol and retrieval time, never shown under new selection. Simplest behavior is clearing it.

Extend provenance additively with instrument_key, interval, exchange timezone, retrieval time, last completed bar and notes/diagnostics. BROKER_LIVE means API origin, not guaranteed streaming/current freshness; label historical vs current-day API candles separately. Show times to minutes/seconds, data age and last completed bar, not 'fresh same day' alone. Escape external metadata before HTML banners.

## Existing workflows and boundaries

Market Overview and Technical Analysis must name the selected equity/ETF, not call it NIFTY. Indicators use bar-count labels on 5m; do not label SMA20 as 20-day on intraday data. Hide daily-annualized realized volatility and daily regime metrics when unsupported on 5m. Do not feed new intraday/equity data into the existing NIFTY strategy-voting engine as a validated signal: Signal Monitor returns research/INSUFFICIENT DATA for unsupported symbol/timeframe, while the chart and basic indicators remain usable. Daily NIFTY synthetic/CSV legacy behavior stays supported with explicit provenance.

No broker data may change production_context_blocked or enable qualified journal save. Retain ₹20k/₹2k policy. Spec 03 review found candidate-risk understatement/NaN/profile validation and stale save-context gaps; record them in handoff as deferred, not fixed or accepted. These do not block read-only charts because funded-paper entry remains unavailable.

## Verification

Mock all HTTP for automated tests and prevent unexpected real network. Test exact paths/encoding, offset normalization, merge/order/duplicate handling, incomplete bar exclusion, data/source switch, expired token and transient failure. Fake-token sentinel must not appear in captured logs/UI/errors/caches. Test a real chart-loading UI path with fake transport and temp journal path; avoid user's private journal.

Provide a bounded smoke command that loads token internally, resolves one initial instrument, fetches at most one historical/intraday pair and prints only symbol, interval, row count, last completed time and sanitized status. No dumping raw JSON or secrets. It may run a single read-only smoke against the user's locally prepared token under this spec's integration authorization. If no token is configured, report BLOCKED and precise local setup steps; do not request values or claim verified access. Do not automate login. To avoid inspecting unrelated secrets, do not open .env for review; runtime may load it privately using existing configuration.
