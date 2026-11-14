# Spec 14 — Design

## Data path

1. **Authorize (LIVE only):** server-side `GET /v3/feed/market-data-feed/authorize` → `authorizedRedirectUri` (never exposed to browser).
2. **Bootstrap (once per Start):** `GET /v3/historical-candle/intraday/{key}/minutes/5` → completed bars merged into `CandleBook`.
3. **Subscribe:** UTF-8 JSON `method=sub`, `mode=ltpc`, single instrument key on WebSocket (LIVE) or deterministic protobuf frames (REPLAY).
4. **Decode:** `FeedResponse` protobuf → ltpc ticks with `ltt` trade time; ignore non-ltpc unions in prototype.
5. **Aggregate:** IST 5m bucket open; dedupe by `trade_ms`; roll forming bar forward on boundary cross.

## Session owner

- Module-level single `StreamSession` with lock; same Streamlit owner token → no second thread.
- Stop sets event, joins thread, clears owner.
- LIVE: bounded reconnect with backoff; auth failure → ERROR (no endless retry).
- REPLAY: play frames once → STOPPED (no reconnect).

## UI

- `pages/14_Stream_Chart.py` → `nifty_lab.stream_chart.ui`.
- `st.fragment(run_every=1s)` refreshes chart while running.
- `lwc.render_candlestick_chart` pins Lightweight Charts CDN and reuses `window.__nslLwc_*` between reruns.

## Security

- Tokens and WSS URLs stay in Python process only.
- `NSL_FORBID_LIVE_MUTATIONS` guards orders only; streaming remains read-only (tests default REPLAY).