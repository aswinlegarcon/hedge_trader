# Spec 09 research addendum — backtest before strategy promotion

Researched 13 November 2026 IST. Specification/research only: no backtest implemented or performance validated, no credential inspection and no broker calls. Preserve the active Spec 08 Paper-close implementation task; this is queued research work, not a second task dispatched to that agent.

## Findings in plain language

Backtesting means replaying historical market observations chronologically through fixed decision and execution rules. A decision at time T may use only information available by T. Record simulated entries/exits, rejected opportunities, positions, fees and account equity. Downloading five years of data is necessary input for that chosen window, not a backtest by itself.

Win rate is wins divided by closed trades; define wins after costs, breakevens and partial-trade grouping before measuring. It is not a strategy survival probability. No universal evidence was established for the podcast's claim that 30–35% winners last and >50% winners expire. Without the episode and its exact definitions, its intended claim cannot be verified. A low win rate may suit a system with large occasional gains; a high win rate may conceal rare large losses. Neither implies durability.

For gross payoff examples, expectancy per trade = win fraction × average gross win − loss fraction × average gross loss − average total trading costs. Do not subtract costs again if using already-net outcomes. Hypothetical 35% winners, ₹300 average win and ₹100 average loss gives ₹40/trade before costs; 60%, ₹50 and ₹100 gives -₹10/trade before costs. These examples are arithmetic, not forecasts or proposed position sizes. A 35% system can also fail through costs, long losing streaks, limited sample size and changing conditions.

Bailey, Borwein, López de Prado and Zhu's research describes how selecting a winner among many tested variants can overfit historical noise and degrade out of sample. Retain all trials, frozen rules and realistic costs; a single untouched period alone does not eliminate repeated-search risk. The paper also notes that methods cannot rescue incorrect execution assumptions or guarantee robustness to future structural breaks. [Author-hosted paper](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

## Upstox data assessment

Official Historical Candle V3 documentation lists minute/hour history from January 2022 and daily/weekly/monthly history from January 2000. For 1–15-minute bars the per-request retrieval window is one month; longer intervals have other windows. These are documented API ranges, not proof that every symbol has complete history. [Historical V3](https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/).

Expired derivative history is a separate endpoint and its documentation identifies Upstox Plus entitlement. Verify actual account access, contract coverage and response quality before proposing an upgrade. No historical BBO/depth guarantee follows from OHLC candles; option expiry/strike/lot metadata and data available at contract-selection time matter. [Expired candles](https://upstox.com/developer/api-documentation/get-expired-historical-candle-data/).

For a five-year 2021–2025 study, daily data may be the first feasible path; documented intraday history starting 2022 cannot provide that complete window. Dataset selection must reflect listing dates, corporate actions, session calendars and gaps. Do not use today's surviving NIFTY/watchlist membership as an unbiased historical market universe. A fixed current-watchlist study may be exploratory with selection bias disclosed. Do not simulate options profits from NIFTY direction alone.

No new platform or paid account is required by this research decision. First audit what current Upstox entitlement actually returns, then name the specific missing data, granularity, legal usage and cost if another supplier becomes necessary. Do not upgrade subscriptions or accept terms automatically.

## Existing application versus target workflow

`/Users/sanjain/Documents/hedge_trader/pages/07_Backtesting_Lab.py` is a placeholder and explicitly states no validated strategy. Its claim that all v1 data is synthetic/imported is now outdated relative to implemented Upstox candles. Update that copy during backtesting implementation without implying that an engine already exists.

Target sequence for EACH strategy version: frozen rules and data-quality audit -> historical backtest and chronological validation -> forward Paper evaluation -> independent readiness review -> optional user-confirmed limited Live use. Paper order/ledger software tests may continue now; they are different from a strategy passing forward-paper validation. No profitability, guaranteed success or automatic live promotion.

## First queued task: historical-data feasibility audit

This addendum prioritizes data feasibility and a reproducible backtest before broader automated daily-report features in Spec 09. It preserves existing design's versioned experimental strategy and prohibitions. Do not dispatch while the same agent is implementing the active Paper-close slice.

### Requirements
- Read applicable instructions, current Upstox transport/instrument/candle architecture and official V3 limits. Reuse read-only transport boundaries; keep order mutations forbidden. No new order endpoints, secrets output or raw HTTP error/header logs.
- Produce an explicit dataset manifest: instrument identity, interval, requested and returned dates, source/version, timezone, row count, duplicate/missing/session checks, OHLC integrity, volume, price-adjustment status and content hash. Unknown adjustment status must remain unknown and constrain validation.
- Start with a bounded read-only sample after implementation, using the existing server-side token without displaying it: one selected existing stock, daily candles, at most three date-window requests total. Cover old/middle/recent portions of the intended five-year period; record limitations rather than claiming continuous coverage. Respect current rate limits. Test with fixtures before optional live GET smoke. No five-year bulk download until chunking/cache/resume design is reviewed.
- Treat 2021–2025 as a provisional closed five-calendar-year daily research window, with actual availability reported. Predeclare chronological development/validation/final holdout boundaries before examining strategy outcomes. Inspecting price quality is not permission to optimize on final holdout outcomes. Do not manufacture five years where listings/data do not support it.
- Do not access premium expired instruments, other brokers or new subscriptions in this first audit. Report options entitlement/coverage as unverified until a separately bounded check is authorized.
- Output a feasible/limited/blocked assessment and smallest engine implementation task, not strategy scores or fake backtest P&L. Then implement the frozen Spec 09 backtest/report only after audit review.

### Scenarios
GIVEN missing dates, duplicate bars or unknown adjustments, WHEN the audit runs, THEN it reports quality limitations and never forward-fills tradable prices or claims clean history.

GIVEN a 2021 intraday request unsupported by documented coverage, WHEN planning a five-year backtest, THEN it proposes a different explicit interval/window instead of fabricating bars.

GIVEN no historical option contract prices, WHEN options testing is discussed, THEN it stays unvalidated and cannot reuse index returns as option P&L.

GIVEN any successful audit, WHEN readiness is displayed, THEN it means data feasibility only, not a proven profitable strategy or permission to trade.

## Learning material

Ernest P. Chan, *Quantitative Trading: How to Build Your Own Algorithmic Trading Business*. Wiley's listed contents include strategy selection, transaction costs, survivorship/data-snooping bias and backtesting. Use the legitimate publisher excerpt/library/book for study; this review inspected the publisher listing, not the full book. [Publisher listing](https://www.wiley.com/en-us/quantitative-trading-how-to-build-your-own-algorithmic-trading-business-2nd-edition-p-9781119800071).

For the user, add future learning cards beside results: what win rate means; why a 35% strategy may gain or lose; drawdown and losing streaks; how future-data leakage misleads; why Paper and Live fills differ. These are queued UI ideas, not delivered features.
