# Spec 09 first slice — bounded historical-data feasibility audit

Date: 13 November 2026 IST. Status: **IMPLEMENTED (bounded audit slice) — stop for review**. Full Spec 09 engine/backtest remains NOT IMPLEMENTED. This slice takes precedence over the broader first-delivery tasks in docs/spec_09/tasks.md: implement the audit ONLY, stop for review, then separately scope the backtest. Read README.md, design.md and backtesting-research.md. Preserve all Spec 08 work and its CORRECTIONS IN PROGRESS/not Live-ready status.

## Proposal
Determine whether existing Upstox daily candles can support a later 2021–2025 cash-equity study. One fixed stock: ICICIBANK. Deliver reproducible fixture-tested audit code, a bounded read-only runner and a sanitized report/manifest. Do not implement a strategy, optimizer, historical performance report or full-history downloader in this slice.

The sample answers whether three separated historical windows are accessible and structurally usable. It cannot establish continuous five-year coverage, survivorship-free market coverage, trustworthy option prices or a profitable strategy. No new subscription or platform registration.

## Design

### Existing boundaries
Inspect and reuse nifty_lab/brokers/upstox_transport.py, upstox_instruments.py, upstox_candles.py and upstox_market_data.py. Do not route this through execution/order adapters. Use official Upstox V3 daily historical candles and verify current request contracts before changing URL construction: https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/ . Existing scripts/upstox_market_data_smoke.py provides a bounded-run pattern, not permission to print arbitrary exceptions or use its entire dataset workflow if that makes extra calls.

### Fixed universe and request budget
Use one exact NSE equity ICICIBANK instrument, resolved from an existing public master cache if possible. If unavailable, permit at most one public master GET to the existing documented master host, then fail closed if ambiguous/unavailable. Never guess an instrument from a label or fetch private profile/holdings/orders.

At most three authenticated historical GET attempts total, exactly these daily windows (inclusive):
- 2021-01-01 through 2021-01-31.
- 2023-01-01 through 2023-01-31.
- 2025-12-01 through 2025-12-31.

No automatic retries, pagination probes, intraday-today fallback, extra authentication/private account requests, premium expired instruments, redirects to unapproved hosts or requests for other stocks. Token expires or permission fails: report a sanitized BLOCKED status; do not ask for/paste secrets or launch OAuth. Keep any redirect handling within existing verified transport boundaries. Count attempted requests even when they fail. No scheduling/background polling. Existing token may only be consumed privately server-side; do not inspect .env contents manually or log headers/token/response bodies.

Fixture tests precede optional bounded live GET smoke. Run it at most once as part of this handoff; persist public sanitized reports so review need not repeat network calls. If token/setup is unavailable, mocked implementation may finish but live feasibility remains UNVERIFIED. No external paid API, permission/static-IP change, subscription upgrade or order mutation.

### Dataset and manifest
For each window record requested dates, returned minimum/maximum source date, instrument key/symbol/exchange/type, interval, timezone interpretation, source endpoint/API version, fetched-at UTC, success/HTTP classification without raw bodies, row count and data hash. Preserve original public OHLCV response data and normalized candles locally with provenance; exclude any HTTP metadata that could contain secrets. Save public data in a dedicated research/audit cache, never execution ledger or existing candle selection. Use an explicit output directory, predictable filenames and overwrite protection/versioned run IDs; do not silently replace an earlier audit.

Quality checks must use raw rows before sorting/deduplication so malformed, out-of-range and duplicate bars cannot be hidden by the normalizer. Record raw and accepted/rejected counts, conflicting duplicate timestamps, ordering, finite positive OHLC, low <= min(open,close) <= max(open,close) <= high, finite nonnegative volume and interval/date/timezone consistency. Flag unexplained zero-volume/suspicious jumps for investigation, not automatic correction. Do not forward-fill executable bars.

Weekdays with no bar are possible missing sessions, not confirmed data gaps: NSE holidays/special sessions require a sourced session calendar. If calendar is not available in the audited code, mark calendar coverage UNVERIFIED, report candidate gaps and do not add network requests to scrape one. Document listing-date, corporate-action/adjustment and delisting limitations. Adjustment status remains UNKNOWN unless authoritative evidence establishes it; never infer adjusted prices from smoothness. Current watchlist selection is not a survivorship-free historical universe.

Compute deterministic hashes of canonical normalized OHLCV plus a separate manifest/schema/config version; no secret-dependent hashes or private data. Datasets with zero rows, corruption, truncation or uncertain coverage remain limited/blocked as appropriate. Explain whether one symbol's windows give a credible basis for the next bulk-data design; never label the full 2021–2025 dataset VERIFIED from these samples.

### Predeclared research boundaries
Reserve 2021–2023 for development, 2024 validation and 2025 final holdout for the later daily-strategy study, subject to actual coverage review. No strategy signals/outcomes or parameter searches in this audit. Warm-up/outcome boundary leakage and purging will be specified before the engine; a data-quality inspection is not permission to tune on holdout returns. November 2026 data is not included in these historical samples. Five-year intraday coverage is not assumed from daily availability.

### Report and readiness
Provide per-window result and overall FEASIBLE_SAMPLE / LIMITED / BLOCKED / LIVE_CHECK_UNVERIFIED as explicit scope-limited statuses. Explain calendar, adjustment, universe and historical options limitations. Provide the smallest proposed next implementation task: resumable bounded full-daily-history acquisition with quality/adjustment review if sampling is feasible, otherwise the exact blocker. No broad downloader or backtest automatically starts after the report.

Optional Backtesting Lab copy correction may state that Upstox research candles now exist while the backtest engine/strategy validation remain absent; don't add false performance numbers or call Spec 09 implemented as a whole. Do not build daily report UI, signal generation, Paper strategy automation or new financial recommendations.

## ADDED Requirements

### Requirement: Bounded read-only historical audit
The system SHALL enforce one-symbol and three-history-attempt limits before network calls, using distinct public audit artifacts and no broker mutations.

#### Scenario: Successful three-window sample
GIVEN supported daily windows and mocked or valid authenticated read-only access
WHEN the runner executes
THEN it makes no more than three historical requests and one optional public master request, saves provenance/hashes and reports sampled feasibility only.

#### Scenario: Token failure or extra request
GIVEN an auth error, ambiguous instrument or an attempt to exceed the budget
WHEN execution reaches the guard
THEN it produces a sanitized blocker and no retry, order call or private account query; secrets never appear in stdout/stderr/logs/manifests.

### Requirement: Honest data-quality evidence
The audit SHALL retain raw anomalies and distinguish observed rows from verified historical session coverage.

#### Scenario: Duplicate, invalid OHLC or out-of-range rows
GIVEN a fixture with duplicates, broken OHLC, nonfinite prices or bars outside requested dates
WHEN auditing and normalizing
THEN findings/raw rejected counts remain visible, no clean-coverage label is awarded and no tradable bars are invented.

#### Scenario: Calendar and adjustment unknown
GIVEN absent weekday bars and unknown corporate-action adjustments
WHEN the manifest is generated
THEN candidate gaps and unresolved adjustment status are explicit; neither missing trading sessions nor corrected prices are fabricated.

#### Scenario: Reproducible artifacts
GIVEN the same public candle fixture/config and a changed fetched-at time
WHEN normalized data is hashed
THEN the data hash stays stable; changed candle values change it; manifest captures run provenance without secrets.

### Requirement: No strategy or trading promotion
#### Scenario: Favorable-looking sample
GIVEN all three windows return structurally valid rows
WHEN the report is delivered
THEN five-year continuity, option-backtest readiness, predictive accuracy and profitability remain unverified; the runner stops with a proposed next step.

## Tasks
- [x] Read applicable instructions, Spec 09 docs and current data transport/normalization; preserve all uncommitted Spec 03–08 work and private files.
- [x] Implement independently testable raw/normalized quality audit and deterministic manifest/hash output.
- [x] Add explicit request budgets and allowlisted read-only runner, cached master resolution and immutable/versioned artifact output.
- [x] Test raw anomalies, date/timezone boundaries, output safety with fake secret sentinels, request budgets/no retries, blocked auth, canonical hashes and no order/private endpoint use using fixtures/temp dirs.
- [x] Run focused/full required checks. Optional one bounded live GET audit only after fixture tests, sanitized output and no repeated smoke calls. Report actual attempted requests and results.
- [x] Write docs/spec_09/data-audit-handoff.md with exact changed paths, scenario evidence, commands/counts, sanitized artifact locations, real vs mocked statuses and limitations. Do not overwrite broader handoff as complete.
- [x] Stop for review. No commits/merges, broker mutations, new subscriptions, Spec 08 changes or automatic full-history/backtest launch.

## Implementer prompt
Implement ONLY docs/spec_09/historical-data-audit.md in /Users/sanjain/Documents/hedge_trader. Read the complete spec and applicable instructions. Keep NSL_FORBID_LIVE_MUTATIONS=1; no .env inspection or secret output. One ICICIBANK daily audit with the exact three windows and hard network budget; fixture tests first, optional one bounded live GET smoke, honest public-data provenance/quality report. Preserve unfinished Paper/results work. No order endpoints, private account data, premium APIs, new feeds/subscriptions, strategy runs, commits or merges. Work in the current hedge_trader IDE chat, not Agents Window. Record actual evidence in data-audit-handoff.md and stop.
