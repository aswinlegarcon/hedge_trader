# Change: compare the initial watchlist using daily and five-minute research facts

## Why

Real candles now load, but assessing four instruments still requires repeated manual chart navigation. The next product outcome is one review board showing source-backed technical facts, why conditions agree or disagree, and which data is missing.

## Scope

Add a Watchlist Research page and a deterministic summary module. A manual Refresh loads daily and five-minute datasets for up to the four existing provisional research labels through the current Upstox service. Show a compact comparison table and a detailed card/chart for the selected instrument. No automatic scheduling.

Show exact security identity, snapshot/bar times, daily trend, five-minute EMA alignment, current-session VWAP, volume relative to previous bars, prior confirmed support/resistance and a factual summary. Use complete candles only. Include a visible explanation that candles are historical observations, not executable quotes or a proven entry recommendation.

Reuse existing modules. Candidate files: a small `nifty_lab/research/` module, new `pages/11_Watchlist_Research.py`, `app.py` navigation, narrow helper additions to existing Upstox service/UI code, tests and setup docs. Fix shared source-selection identity where needed so existing and new pages cannot show an old instrument under a new selection.

## Out of scope

Buy/sell instructions, targets/stop suggestions, sizing, per-position policy changes, paper qualification, journal changes, forecasts/confidence percentages, ranking by expected returns, backtesting, news ingestion, new broker endpoints, quote/WebSocket feeds, OAuth helpers, commits and merges.

## Success

One explicit refresh yields independently labelled rows for each resolved instrument, with daily and 5m facts and clear stale/partial/error states. A selected row opens an explanatory card with indicator values and a chart. Failures never silently reuse another security's data. Tests prove the rule arithmetic and refresh/UI behavior, without live calls in the suite.
