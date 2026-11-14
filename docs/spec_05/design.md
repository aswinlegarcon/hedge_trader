# Design

## 1. One bounded workflow

Add Watchlist Research to navigation. Show the four existing provisional research labels as a selectable list, maximum four per refresh. User clicks Refresh Watchlist. Resolve exact identities once using the public master, then fetch daily and 5m through `UpstoxMarketDataService`; retain its timeframe/date/completeness bounds. Show progress and per-instrument outcomes. A label is not an investment recommendation.

Sequential requests with existing pacing, one batch at a time. Bound the batch to at most 13 outbound calls (one master plus four instruments × daily/history/intraday); do not add retries in this change. A 401/403 aborts remaining requests with AUTH REQUIRED; remaining rows become NOT FETCHED, never silently retained as new results. Other per-instrument failures allow the other rows to finish and remain visible. Cache only per-session non-secret public market results, never token values/headers. No I/O on imports or incidental page reruns.

Snapshot identity includes instrument key, timeframe, request identity and retrieval time. Each timeframe has its own as-of time; do not claim they describe the same instant. New refresh clears prior result authority and updates rows progressively. If keeping previous observations on failure, mark them STALE/reference-only with original dates. Prefer clearing failed rows for simplicity.

The shared Spec 04 sidebar currently retains candidates/dataset when research label, custom symbol or interval changes. Track a public selection identity and clear stale candidate choices/datasets before returning any frame on a changed selection. The new board must not inherit this ambiguity. This small identity correction is part of making the board truthful, not a general transport refactor.

## 2. Deterministic observations

Use an immutable result object carrying exact instrument identity, source, daily/5m as-of and retrieved-at timestamps, evaluation clock, values, observation statements, limitations and data state. Keep financial advice and storage out of this module. Inject clock and datasets for tests.

Daily trend uses latest completed close, SMA50 and SMA200. Label ABOVE BOTH, BELOW BOTH, MIXED or WARM-UP. Report actual numbers. Missing 200-bar history must not be synthesized. Daily data is prior-session context, not today's closing value.

5m momentum uses EMA9/EMA21 and last completed close: ABOVE BOTH WITH EMA9≥EMA21 / BELOW BOTH WITH EMA9≤EMA21 / MIXED / WARM-UP. These are bar-count indicators. Do not reuse daily annualization or NIFTY strategy voting.

VWAP is typical-price candle VWAP, explicitly an approximation to trade-level VWAP: cumulative ((H+L+C)/3 × V) / cumulative V, grouped by Asia/Kolkata session date. Use only the latest session's complete bars, label its date. If there are no current-date bars, do not call it today's VWAP. Zero cumulative volume gives unknown, not zero/infinity. Report close above/below/equal to VWAP numerically.

Relative volume = latest completed 5m volume / mean of the preceding 20 completed 5m volumes, excluding the latest bar; compare within the same session. If fewer than 20 preceding session bars or denominator zero/missing, report unavailable. Label it 'versus preceding 20 session bars', not time-of-day adjusted volume. No numeric threshold implies profitable liquidity.

Support/resistance: reuse confirmed swing/cluster helpers, with their current parameters disclosed. Freeze reference levels using only bars before the latest completed bar and confirmations available at that previous bar. Display nearest support below and resistance above the reference close; absent levels stay unknown. Evaluate whether the last close crossed a frozen prior level against previous close. Do not recompute levels around the new price and then claim a breakout of a moving level. Label 'closed above prior resistance' or 'closed below prior support', with reference level and bar time; not a buy/sell signal. Swing confirmation lag is a visible limitation. Daily and intraday levels remain separate.

Summary is composed from facts, no score: daily/5m direction agreement or disagreement, VWAP relation, frozen-level crossing, volume availability and limitations. Use phrases such as 'daily and intraday conditions align upward', 'mixed observations', 'waiting for data'; never 'high-confidence trade', probability, BUY/SELL or claims of historical success. News/event context is NOT CHECKED in this slice.

## 3. Freshness and partial results

Compare last 5m bar end to an injected aware evaluation clock. For same-date regular-session evaluation, >10 minutes lag is STALE using a stated heuristic (not verified session calendar). Dates before the evaluation date become PRIOR SESSION; do not call them current. Daily bars are last completed daily context; explicitly display their date and do not equate a calendar-day gap with a missing trading session. No full exchange holiday calendar required; flag that limitation, especially after hours/holidays/special sessions.

A complete current 5m bar set does not make the daily dataset current intraday. Show retrieval age and observation age separately. Future timestamps, missing provenance, mismatched identity or mixed intervals must be rejected for summary use. Insufficient daily or intraday input yields PARTIAL DATA with whatever facts are independently available; unavailable observations stay blank/unknown. If no reliable input exists, INSUFFICIENT DATA. STALE/PRIOR SESSION observations remain descriptive reference and cannot be presented as current setup confirmation.

Table columns: symbol/name, daily context date/trend, last 5m completed time/close, EMA relation, session VWAP relation, prior confirmed support/resistance, level-cross observation, relative volume, data state. Table may scroll; detailed card carries explanations and a single chart. Avoid dense dashboards with every indicator simultaneously.

## 4. Preserve boundaries and evidence

Keep current real candle charts and synthetic/CSV flows. Do not unlock Signal Monitor's NIFTY voting for equities, modify production risk gate, qualify journal entries or invoke new endpoints. No price targets, order planning or sizing until a separately specified cost/quote/risk workflow exists. No live trades.

Spec 04 observed limitations (global verified connection state, no bounded retry implementation, some intraday labels/table metrics) and Spec 03 financial-gate review gaps remain documented; do not claim full prior-spec acceptance. Fix only what directly prevents truthful board identity/timeframe display. Small series must not crash the new card/chart controls.

Automated evidence: independent numeric fixtures for VWAP/reset/zero volume, prior-20 volume, EMA/daily warm-up and frozen-level crossing with no future bars; stale/partial/mismatch; per-instrument failure and auth abort; source selection invalidation; fake-token output capture; UI Refresh-to-table/card using mocked service and no private journal. Run relevant regressions under Python ≥3.12 with dotenv disabled for mocked tests.

Optional bounded live check: one selected instrument only, reuse existing official GET operations (master + daily + historical/intraday; max four calls), backend token internally, sanitized summary counts/times only. Report result independently from tests. User's posted Spec 04 success is not a new Spec 05 test. If token absent do not ask for values or fake success. No refresh of all four merely to report a test count.
