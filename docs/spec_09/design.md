# Design

## Daily research record
Persist a local research store distinct from execution/account ledgers. Each record includes IST session date, UTC creation/availability timestamps, source and coverage state, universe, immutable pre-market plan version, completed-bar observations, candidate/no-trade reasons, and an append-only post-market review. No invented headlines, weights, event times, broker states or performance results. Unknown/old snapshots stay clearly unknown/stale. Pre-market plans created after market open must be labeled late and cannot count as advance forecasts. Do not treat one day of trading as validation.

The UI should answer: What is happening? What evidence supports it? What would invalidate it? Is a registered strategy applicable? Why trade or skip? Is execution available? Research judgments are separate from account eligibility. Provide nontechnical explanations and a default no-trade option. The first slice may use structured manual market notes labeled manual; it must not claim comprehensive automated market coverage.

## One experimental strategy
Use a cash-equity daily trend-pullback example, explicitly not a recommendation: prior close > EMA20 > EMA50; prior low touches/breaches EMA20 but prior close closes above EMA20; prior volume >= trailing 20-session median excluding the signal bar. Using only completed prior bars, model a next-session-open entry plus adverse slippage, with stop at the signal-bar low. Reject nonpositive stop distance. Compute R from modeled entry minus stop, then fix target at entry + 2R; time exit at the fifth session close, counting entry session as one. If entry gaps below/equal stop, skip. If both stop and target touch in one daily bar, assume stop first and disclose intrabar ambiguity. Stop gaps fill at worse available opening price. Freeze exact indicator initialization, warm-up, data adjustment, session alignment, prices and charges before evaluation. Test mechanics independently. No intraday path reconstructed as fact from daily OHLC.

Use the unchanged execution-v1 policy as a maximum eligible allocation in a separate portfolio simulation. Cash cost coverage must include required transaction and exit charges with dated source, or results stay exploratory; zero/unknown fees cannot produce validated status. Distinguish strategy-only opportunity metrics from capital-constrained portfolio returns. Do not fabricate option P&L from an underlying-index move.

## Versioned evaluation
Store strategy ID/version, full rules/config hash, data source/date range/hash, point-in-time universe limitations, cost/slippage assumptions, splits and all runs including rejected variants. Preserve chronological train/validation/final holdout boundaries, fit only on earlier data, and prevent overlapping future trade outcomes across boundaries. Reserve final holdout before tuning; repeated inspection retires it as untouched evidence. Start with fixed rules, no optimizer.

Minimum report: opportunity count, filled trade count, date coverage, win rate with confidence interval and method, average win/loss, net expectancy, profit factor, maximum drawdown, fees/slippage, exposure, turnover, and reproducible baseline over the same period/capital. Include no-trade and data-quality reasons. Bucket descriptively by instrument and predeclared market regime; show counts and uncertainty, not a winner badge from a tiny bucket. Never label a heuristic score as win probability.

Initial status vocabulary: UNTESTED, EXPLORATORY, INSUFFICIENT EVIDENCE, FORWARD PAPER CANDIDATE, PAUSED. First delivery may produce only the first three. A later reviewed promotion protocol must specify sample size/power rationale, untouched results, stability and forward-paper duration; no automatic Live promotion or arbitrary trade count marketed as proof.

Self-evolution is propose -> version -> test -> compare -> analyst review -> user-visible change. Keep active rules frozen while evaluating challengers; never silently overwrite losses or increase risk. The existing ₹20k/₹400/₹2k policy remains provisional operating policy, not an optimized or guaranteed-loss policy.

## Market-context extensions
NIFTY leadership requires current sourced weights and synchronized returns, not just counting green stocks. Approximate weighted contribution must be labeled approximate, with weight date, return baseline and coverage. Missing stocks/weights preclude a full-index attribution claim. Index direction alone does not prove option profitability. Historical news/macro backtests require information-availability timestamps; today's snapshot cannot be injected into historical decisions.

## Primary references checked 13 November 2026
- https://www.niftyindices.com/indices/equity/broad-based-indices/nifty--50 — free-float market-cap weighting.
- https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-47 — limitations of performance claims.
