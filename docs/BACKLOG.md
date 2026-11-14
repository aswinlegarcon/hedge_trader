# Backlog — Streaming market-data and chart dashboard

Recorded: 14 November 2026 IST.
Status: **Spec 14 prototype implemented** (page 14, ICICIBANK 5m, REPLAY + bounded LIVE). Further items below remain backlog for multi-symbol, volume, gap recovery, and production hardening.
Priority: review Spec 14 handoff before expanding scope.

## User intent

The dashboard should update automatically with a continuous stream of real market data and interactive candles, rather than require manual refresh. Aim for a TradingView-style chart experience, without claiming full TradingView feature parity. User explicitly deferred this until first priorities are complete.

Current behavior: existing broker candles/quote overlays are manually refreshed snapshots. Continuous streaming has not been implemented. Live market data is independent of real-money order execution: streaming must work with Live mutations still disabled.

## Candidate architecture (evaluate when scheduled)

- Server-side Upstox Market Data Feed V3 WebSocket connection, authorized using the existing local account; verify actual account entitlements, official limits and supported instrument/mode coverage at implementation time.
- TradingView Lightweight Charts as the candidate chart renderer. It is open source under Apache2.0, subject to required notices/attribution. The full TradingView platform and Advanced Charts are separate products; do not assume their source/features/licenses are available.
- The charting library does not provide market data: feed comes from Upstox, charts render it.
- Historical candle bootstrap plus streamed updates; distinguish forming candles from completed candles. Correct exchange timestamps/IST sessions, cumulative-volume handling, ordering/deduplication and late ticks. Reconnect with bounded backoff and gap recovery; never silently draw uninterrupted data over a disconnect.
- Explicit user start/stop stream; no manual refresh needed once subscribed. Bound subscriptions/watchlist, shared connection lifecycle, session isolation and UI update cadence; stop background work when appropriate.
- Clear connecting/streaming/reconnecting/stale/closed-or-unknown states, last source tick and receive times. HTTP success or a heartbeat is not evidence of fresh prices. No fabricated prices, current bars during gaps or guaranteed delivery claims.
- Watchlist/symbol/timeframe selection, candlesticks/volume, zoom/pan/crosshair and selected indicators as separately bounded UI increments. Full TradingView/Pine-script/drawing-tool parity is not promised.
- Evaluate whether current Streamlit component architecture supports smooth incremental updates; avoid full-app rerender per tick. Do not commit to a frontend rewrite until a small performance prototype is measured.

## Boundaries / acceptance planning

Read-only market-data project. Keep broker secrets and authorized WebSocket URLs server-side and out of logs/browser storage. No order endpoints, risk-policy changes, strategy promotion, automatic trades or release of2025 holdout. Keep NSL_FORBID_LIVE_MUTATIONS=1.

Future acceptance should include deterministic recorded-feed replay (not strategy backtesting), disconnect/reconnect/gap/staleness tests, candle correctness versus recorded source, subscription cleanup, user symbol-switch isolation and responsive chart update evidence. Live feed smoke must be separately bounded and honestly identify closed-market conditions. This backlog entry authorizes none of those live operations now.

## Official references checked 14 November 2026

- https://upstox.com/developer/api-documentation/v3/get-market-data-feed/
- https://www.tradingview.com/lightweight-charts/
- https://www.tradingview.com/charting-library-docs/latest/product-comparison/
- https://github.com/tradingview/lightweight-charts/blob/master/README.md

No implementation or installation in this backlog task.
