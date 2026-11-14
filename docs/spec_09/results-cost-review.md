# Spec 09 — Read-only results and cost sensitivity review

Status: AUTHORIZED BOUNDED SLICE. Build archived-result review only, write handoff and stop. No additional backtest, validation rerun, 2025 evaluation, paper or Live promotion.

## Why / analyst decision

Reviewer independently ran 208 passing tests. Saved 2024 validation has 14 trades, 249 equity sessions, net +24.30, modeled fees429.98, executed buy+sell turnover430003.98. Each trade arithmetic and final cash20024.30 reconcile. Frozen rules match d5781d90f3276de37320059a14529c944580fc671c351cbbc04bed90bb191101. Development remains net -869.13 across16 trades. These are independent accounts, not a continuous combined return.

On fixed2024 fills, extra1bp cost on executed turnover =43.00, adjusted diagnostic net -18.70. Extra cost break-even ~0.565bps. This is cost fragility under a stated scenario, NOT a new backtest, actual brokerage prediction, or proof about future returns. Current evidence does not demonstrate an investable edge. Keep2025 sealed; no economic-rule changes or promotion.

## Scope / proposal

Turn existing Backtesting Lab placeholder into a read-only evidence view for the two approved saved runs and an immutable offline cost-diagnostic artifact. No simulation functions, live connectors, strategy search, new research data or execution modifications. This is one research-results review workflow.

## Requirements

### R1 — Registered immutable inputs

Read ONLY archived corrected development run `research/backtest_runs/22f4e81b-e66a-4ea1-b77d-325323f61db7/` and validation run `research/backtest_runs/d1d9016b-3fc0-4dbf-944e-f4dde5353cd2/`. Original provisional cffbcdd3 remains preserved and is not a comparable accepted result. Do not read historical candle files or 2025 prices for this task; saved manifests' holdout-integrity hashes may be displayed as metadata only.

Verify expected run IDs, rules hashes, split/purpose and development-parent lineage against registration and manifest, require completed archived status, and reconcile detailed trades/fees/equity to summaries using Decimal and documented existing precision. Reject missing/malformed/wrong-shaped/inconsistent/nonfinite/nonpositive quantity or price evidence with sanitized `RESULT_UNAVAILABLE` / `RESULT_INCONSISTENT`, never display fabricated/zero success metrics. Preserve sources byte-for-byte, including trial inventory. Hash source files for provenance; pin input fingerprints in diagnostic manifest. UI must detect later changed sources rather than show stale verified results. Do not silently repair old metrics or write into source folders.

Development descriptive counts predating reporting corrections may be imperfect; label unavailable/not comparable counts honestly rather than recomputing signals from prices. Reconciled trade economics and curve are the comparison basis.

### R2 — Fixed-fill diagnostic, not an engine rerun

Freeze these additive cost stresses before execution, separately for each saved book:

1. BASE: archived modeled net P&L unchanged.
2. EXTRA_1BP / EXTRA_5BP / EXTRA_10BP: extra cost = sum(qty*entry_fill + qty*exit_fill)*extra_bps/10000. Use Decimal, aggregate exact turnover then round total extra cost once to INR0.01 using explicit ROUND_HALF_EVEN. Diagnostic net = archived net P&L minus extra cost. Existing fees/slippage are already in archived net; do NOT subtract them twice.
3. EXTRA_INR1_PER_EXECUTION: one hypothetical extra rupee per modeled entry and exit (2*closed trades), a separate scenario, not added to bp stresses. Label assumption one entry execution + one exit execution per archived trade, not a claim about actual broker fills/order counts.

Positive-net extra-cost break-even bps = archived net / executed turnover *10000, with sufficient decimal precision. If original net<=0 report `ALREADY_NONPOSITIVE` with no misleading positive tolerance; if no trades or zero turnover report undefined/no trades, never divide by zero. Report original net return on initial capital only, not annualized from a small sample.

2024 independent checks: turnover430003.98; extra1bp43.00 -> diagnostic net-18.70; extra5bp215.00 -> -190.70; extra10bp430.00 -> -405.70; extra₹1/execution28.00 -> -3.70; break-even~0.565bps. Development stresses remain separate. Do not pool/reset/chain the two books into a combined strategy equity curve.

All results must be labeled `FIXED_FILL_DIAGNOSTIC`: quantities, entries, exits, cash admission, stop sizing, drawdown gates and portfolio path are held fixed. Changing real costs can change sizing/admission/exits/marks; these diagnostic totals do not simulate those effects. Do not generate new stressed equity curves, corrected drawdown, win probabilities or strategy rankings. No choosing best scenario or optimizing rates. Existing10bps fee/side and10bps adverse slippage/side remain illustrative.

### R3 — Saved diagnostic artifact and analyst conclusion

One bounded offline generation under new `research/review_runs/<review_id>/` (or equivalent separate namespace) writes immutable manifest/config/source fingerprints/scenario table/report. Reject overwrite. Do not append a new backtest trial: this is a review of existing experiments. Include existing run IDs/rules/evaluation hashes, generation timestamp, source file checksums, frozen stress definitions, aggregation/rounding, reconcile status, per-book results, limitations and analyst conclusion `INSUFFICIENT_EVIDENCE / COST_FRAGILE_VALIDATION`. Preserve original artifacts and all losses.

Conclusion: development is negative; validation is near break-even under illustrative costs and becomes negative under specified small additive-cost stresses. No demonstrated robust edge under this evidence; do not promote to forward-paper candidate or Live. This does not prove the strategy can never work. No2025 release, no new strategy variant or parameter changes in this slice.

Reference provenance note (reviewer checked13Nov2026): official https://upstox.com/brokerage-charges/ lists separate brokerage, statutory charges, exchange charges and DP charges. Do not insert current public rates into2021–2024 historical fills or claim account-specific/historical tariffs confirmed. Current page contains multiple effective-date sections; actual account plan, historical fee dates, delivery vs same-day treatment and rounding remain unresolved. Store the URL and checked date as reference only; no scraping/network in implementation/runtime, no account or credential access.

### R4 — Dashboard: make research status understandable

On existing `pages/07_Backtesting_Lab.py`, show a read-only Results review section:

- Clear EXPLORATORY / INSUFFICIENT EVIDENCE status; no Live or paper qualification.
- Separate Development2021–2023 and Validation2024 cards/table with run identity, initial/final cash, trade count, net P&L, win rate + interval if present, profit factor, drawdown/denominator, modeled fees/slippage, evaluation/baseline dates and existing cash/buyhold results. Never label37.5%/42.9% observed win rate as next-trade probability.
- Existing saved daily equity curve per book, visibly independent account; no stitched return or invented intraday marks. Dates/values come from reconciled archived evidence.
- Fixed-fill cost table and plain-language explanation: "A small extra cost can erase this validation gain; these scenarios keep the old trades fixed." Display INR and units consistently; 1bp=0.01% of executed turnover.
- Data limitations always visible: calendar UNVERIFIED, adjustment UNKNOWN, fees illustrative, single symbol/small sample, daily-bar ordering assumption. "2025 holdout: NOT EVALUATED".
- No buttons that launch simulations, refresh APIs, trade/save into journal, change rules or unlock holdout. No auto-generating review artifacts on every Streamlit rerun; read/validate existing review files, or calculate pure in-memory diagnostics if artifact absent and label accordingly. Optional explicit local CLI generates the single persistent report. No arbitrary paths entered by user.

Existing unrelated synthetic learning controls may remain if clearly labeled, but must not be confused with these archived broker-candle experiments. Review actual page before changing copy; do not overhaul other pages.

## Scenarios / verification

- Hand-calculated Decimal fixture: known qty/fills/net -> exact turnover/stress net, no double fees/slippage.
- Saved2024 expected values above; development book separate.
- Zero trades, negative net, break-even net, malformed source, NaN/inf, bad lineage/rules/hash, mismatched summary/trade/curve -> honest unavailable/blocked diagnostics.
- Snapshot all source file bytes/hashes before/after offline review; unchanged sources and inventory. Distinct immutable review output; reject overwrite; fingerprints reproducible apart from review ID/timestamp.
- Socket-blocked tests proving loader/diagnostic/UI helper does not call simulation/downloader/broker. UI imports must have no HTTP/simulation/write side effects. Existing full suite passes.
- Smoke dashboard Results review using approved archived inputs (no broker refresh), verify labels/cards/table/charts, no credential values/screens. If UI cannot be checked, say so honestly in handoff.

## Tasks / boundaries / handoff

- [ ] Inspect current Backtesting Lab and archived artifact schema.
- [ ] Implement read-only validated archived loader and deterministic cost diagnostics.
- [ ] Add meaningful fixture/accounting/source-preservation tests; run full suite.
- [ ] Generate one immutable offline diagnostic report; render read-only dashboard evidence.
- [ ] Update `docs/spec_09/results-cost-review-handoff.md` with requirements-to-test evidence, commands/counts, source fingerprints, report path, UI verification and remaining limitations.
- [ ] STOP for analyst review. No2025 outcomes, new backtests/strategy tuning, external data requests, .env/credentials, Spec08/execution DB changes, commits/merges. NSL_FORBID_LIVE_MUTATIONS=1 preserved.
