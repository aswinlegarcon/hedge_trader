# Change: replace legacy broker assumptions with an Upstox-only research foundation

## Why

The shipped MVP defaults to ₹100,000 capital, ₹10,000 drawdown and Kite/Kotak status stubs. The user now specifies ₹20,000 capital, ₹2,000 portfolio loss limit and Upstox only, with initial interest in stocks/ETFs. The Options Analyzer calls eligibility without drawdown and may label a position eligible despite unknown margin. Connecting real data to this path would convey unsupported readiness.

## What changes

- Establish a versioned research profile with ₹20,000 capital, ₹2,000 fixed total loss/drawdown ceiling, no minimum position-risk requirement, and explicit confirmation state for other risk limits.
- Remove Kite/Kotak adapters, registration, credential checks and active setup instructions. Replace them with one offline Upstox status adapter, without authentication or data requests.
- Route funded-paper eligibility through one explicit portfolio/valuation context. Missing required evidence must produce `INSUFFICIENT DATA`; known breaches produce `REJECTED`. Remove the analyzer's default-zero drawdown bypass.
- Keep calculators, sample/CSV research and existing paper history available. Distinguish legacy/manual journal records from new, qualified funded-paper positions.
- Update current README/architecture/setup guidance; preserve historical specifications and user-owned credentials/databases unchanged.

## Impact and bounded scope

Expected touch points: `nifty_lab/config.py`, `nifty_lab/brokers/{base,__init__,kite,kotak}.py`, new offline `nifty_lab/brokers/upstox.py`, `nifty_lab/risk/{budget,portfolio}.py`, `nifty_lab/ui/common.py`, pages 04/06/08/10 where required for consistent policy and recording, `.env.example`, README, architecture and targeted tests. Inspect all callers before changing interfaces; this list is not permission for unrelated refactoring.

This is a configuration and eligibility-boundary change. It does not implement a full ledger, market-data client, OAuth callback, instrument master, stock strategy, new signal algorithm, or backtester. Until later valuation work supplies trustworthy context, new funded-paper eligibility may correctly remain unavailable.

## Out of scope

Live orders, order SDKs/routing, GTT/baskets, broker login, token exchange/refresh, authenticated API calls, WebSockets, credential collection, private account holdings, news ingestion, backtests and scheduled paper runs. No API readiness or profitable-strategy claims.

## Completion

All requirements in `specs/research-foundation/spec.md` have mapped test evidence; the actual analyzer and paper-recording paths fail closed; existing history is preserved; only Upstox appears in active broker setup. The in-house agent completes `handoff.md` with actual results and unresolved gaps. Passing tests do not authorize live integration or trading.
