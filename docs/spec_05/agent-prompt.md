# In-house agent prompt

Implement only `docs/spec_05/` in `/Users/sanjain/Documents/hedge_trader`. Read README/proposal/design/specs/tasks first. Deliver a manual Watchlist Research board for the existing four research labels using the working Upstox candle service: daily trend beside five-minute EMA/VWAP/volume and confirmed support/resistance observations, exact timestamps and a selected-instrument card/chart.

This is a usable research workflow, not another connector milestone. Reuse existing GET endpoints and indicator helpers; keep the layer small. No new login helper, news, backtesting, orders, sizing, targets, stop suggestions or strategy qualification. Preserve ₹20k/₹2k profile, unconfirmed per-position policy and blocked funded-paper entry. Do not expand NIFTY strategy voting to broker equities.

Be precise about no-look-ahead level references, session VWAP and previous-20 volume mean. Handle partial/stale data and one-symbol failures. Fix the shared source-selection identity bug: changing label/custom symbol/interval must invalidate old candidates and cached broker dataset before rendering. Do not refactor unrelated transport/accounting defects; document remaining ones honestly.

Preserve all uncommitted work. Do not open or print `.env` or credentials; token may be consumed privately by the existing backend. Automated tests use fake inputs/mocked service and no real network/private database. An optional one-instrument, max-four-call read-only smoke is authorized if locally configured; never claim the user's prior smoke as your new verification. No commits or merges.

Complete `docs/spec_05/handoff.md` with actual file references, scenario-test evidence, test commands/results, separate live status and remaining limitations; stop for review.
