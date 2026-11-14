# Spec 05 — Watchlist research board

Date: 2026-11-13 (Asia/Kolkata). Status: IMPLEMENTED — see [handoff.md](handoff.md).

OpenSpec-style package using the user's `docs/spec_05/` convention. Read [proposal](proposal.md), [design](design.md), [requirements](specs/watchlist-research/spec.md), [tasks](tasks.md), [agent prompt](agent-prompt.md), and [handoff template](handoff.md).

## Baseline evidence

- Spec 04 supplies official instrument lookup, daily history and five-minute historical/intraday candles. Reviewer reran the current pytest suite with dotenv loading disabled: 74 tests pass. No live call was repeated for this review.
- `docs/spec_04/handoff.md` records the earlier token-absent smoke. User subsequently pasted a successful read-only smoke: ICICIBANK, daily, 271 bars, last completed 2026-11-12 IST. Treat that later result as user-supplied evidence, not the reviewer's independent live verification.
- Current UI loads one instrument/timeframe at a time. Existing signal voting is deliberately NIFTY daily synthetic/CSV only. The new board is a separate equity/ETF research summary, not activation of that strategy engine.
- Capital remains ₹20,000; total portfolio loss ceiling ₹2,000; per-position ceiling unconfirmed; funded-paper production remains blocked. Earlier financial-gate findings remain deferred.

## Intent

Turn connected candles into a useful daily review of ICICI Bank, Gold BeEs, Bharti Airtel and L&T. Reuse existing GET endpoints; no new broker capabilities, login helper, quote feed or offline prerequisite milestone.

Official source contracts carried forward: [Upstox historical candles](https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/), [intraday candles](https://upstox.com/developer/api-documentation/v3/get-intra-day-candle-data/), [instruments](https://upstox.com/developer/api-documentation/instruments/), consulted in Spec 04 on 2026-11-13. The research rules below are explicit engineering hypotheses, not an API capability or validated trading edge.
