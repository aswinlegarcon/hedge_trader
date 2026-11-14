# Change: fetch real Upstox candles into existing charts

## Why

Upstox account access is available and the user wants working market-data research. The current adapter and sidebar remain offline placeholders. We can deliver a real chart without waiting for complete portfolio accounting, automated login, WebSockets or a broad offline ingestion framework.

## What changes

One end-to-end slice: choose Upstox, choose a resolved NSE equity/ETF, load daily history or five-minute history plus today's candles, and show the chart with its actual instrument, interval, source and times. Use a locally configured access token and the existing read-only adapter. Use manual load/refresh, not background polling.

Initial research labels: ICICI Bank, Gold BeES, Bharti Airtel, L&T. Search current instrument data and display the exact selected trading symbol/name/segment/key. No guessed instrument keys or new recommendations. Let the user resolve ambiguity rather than silently selecting a different security.

## Scope

Implement market-data transport, small instrument resolver/cache, candle conversion, provenance and chart wiring together. Add a minimal read-only smoke-check command and meaningful mocked/UI tests. Keep synthetic and CSV access.

Expected locations: `nifty_lab/brokers/upstox.py`, small transport/instrument helpers as needed, `nifty_lab/data/base.py` and adapter normalization, `nifty_lab/ui/common.py`, Market Overview, Technical Analysis, Signal Monitor and Settings only where needed for selected-symbol/freshness/interval behavior, dependencies, setup docs and tests. Avoid architecture rewrites.

## Non-goals

Orders, GTT, baskets, portfolio/funds/margin retrieval, OAuth callback server, automated token renewal, WebSockets, quote/orderbook endpoints, option chains, news, backtests, valuation-ledger repairs and funded-paper activation. Do not repair every Spec 03 issue in this task. Preserve blocked production recording.

## Success

With a locally configured valid token, a user can load a watchlist instrument and inspect real completed five-minute candles and daily history in the existing dashboard. Missing/invalid/expired access fails clearly without exposing secrets or displaying a previous instrument's data. Automated checks pass independently of credentials; a bounded read-only smoke result is reported honestly as successful, blocked or not run.
