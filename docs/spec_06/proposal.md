# Change: source-backed company news for the existing watchlist

## Why

The board now compares real daily/5m observations but labels news NOT CHECKED. A bounded Upstox news integration adds the next missing research input without changing financial qualification or requiring another provider.

## Scope

- A GET-only news client using existing backend authentication/transport and exact resolved instrument keys.
- Explicit manual Refresh News for up to four selected watchlist instruments, independent of candle refresh.
- Recent headlines on Global News & Events and a compact news panel for the selected Watchlist Research card, sharing the same session snapshot.
- Source, safe article link, provider publication time and retrieval time; separate missing/empty/error/partial/stale states.
- Preserve the manual event calendar and mark macro/upcoming events NOT CHECKED. No inference that no headlines means no event risk.

Expected files: small `nifty_lab/news/` module or equivalent broker news adapter, narrow transport helper additions, pages 02/11, tests, optional `scripts/upstox_news_smoke.py`, setup docs and this handoff. Reuse resolved board keys; don't refetch all candles to load news. If no resolved watchlist exists, explain how to refresh the board or resolve labels using the existing public master only.

## Non-goals

Sentiment scores, forecasts, generated article summaries, BUY/SELL recommendations, trade eligibility, earnings/FOMC/RBI schedule ingestion, web scraping, full-article downloads, notifications, schedules, token/login helpers, private holdings/positions/funds, orders, fixes to unrelated financial or session-calendar issues, commits and merges.

## Success

One explicit news refresh displays properly associated recent articles and citations on both pages. Errors leave technical observations usable. Automated tests use fake transports; a bounded one-news-call live check reports actual access, valid-empty response or a sanitized failure without exposing secrets.
