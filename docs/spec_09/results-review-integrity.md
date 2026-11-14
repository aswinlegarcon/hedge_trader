# Spec 09 — Archived results integrity correction

Status: AUTHORIZED BOUNDED CORRECTION. Fix the saved-results validator only, demonstrate rejection of inconsistent records, update handoff and stop. No new strategy, backtest, review generation, 2025 outcomes or trading promotion.

## Reviewer evidence

- Full suite: 216 passed independently.
- Streamlit AppTest on `pages/07_Backtesting_Lab.py`: zero exceptions, two books with expected metrics, two cost tables, 2025 NOT EVALUATED notice present. This is runtime page verification, not a pixel/visual inspection.
- Current saved costs remain as previously reconciled; no changes to their economics are requested.
- Two isolated temp-copy probes reproduced incorrect `load_status=OK`:
  1. Change validation `trades.json` first exit_fill to9999.00 while leaving net_pnl and summary unchanged. Loader still OK. It never recomputes P&L from fills/fees, so altered turnover produces a misleading cost table.
  2. Add100 to final equity cash and set summary.cash_reconcile_delta_inr=100.00. Loader still OK and returns reconcile delta100.00. Matching an erroneous declared delta is not zero reconciliation.

## Findings / exact references

All relative references rooted at `/Users/sanjain/Documents/hedge_trader/`.

`nifty_lab/research/results_review/loader.py:_validate_trade` checks a subset via float and `int(qty)` but never verifies fees, raw/slippage fields or per-trade economic identity. Fractional quantities can be truncated for validation yet used untruncated by diagnostic Decimal calculations. Infinity/bad types can escape as exceptions.

`loader.py:_reconcile_book` compares a declared delta to computed delta but never requires computed delta==0. Summary defaults can hide missing fields; malformed equity/Decimal values can escape. Registration shape and cross-document rules/run identities are incompletely validated. Hash fingerprints detect bytes changing; they do not establish economic consistency.

## Requirements (MUST)

### R1 — Strict finite trade arithmetic

Use strict required schema for the actual approved run format. Quantity must be a genuine positive whole-share integer (reject bool, fractional values and coercion/truncation). Monetary values parsed as finite Decimal; entry/exit fill and raw price references positive; fees and adverse slippage nonnegative, with stable sanitized errors for missing/wrong-shaped/NaN/inf/scalar values. Do not default missing fees/P&L to zero.

For EACH trade, independently recompute net = qty*(exit_fill-entry_fill)-entry_fee-exit_fee under documented archived0.01 rounding; require equality to recorded trade net. Reconcile entry and exit slippage amounts to qty*(entry_fill-entry_raw_open) and qty*(exit_raw_reference-exit_fill), using frozen rounding. Validate fee/slippage summary totals against trade detail, turnover against executed fills, trade count and win/loss/breakeven accounting. No double subtraction of fees/slippage in diagnostic net. Do not call simulator or candle loader; these are archived arithmetic checks only.

### R2 — Require actual zero cash reconciliation

Require `final_cash - 20000 - sum(recomputed_trade_net) == 0.00` independent of the source's declared delta. Nonzero computed OR declared delta is RESULT_INCONSISTENT. Verify required summary net, final cash/net liquidation and detailed last equity point agree for the fully closed archived books; reject absent/nonfinite values and inconsistent curve shape/date ordering or out-of-book dates. Validate every displayed monetary/percentage field for finite type/appropriate bounds; unavailable optional metric is explicitly unavailable, not zero. No exception bodies/data bodies/credential values in errors.

Require registration and manifest object types; consistent approved run ID, frozen rules hash and validation split/evaluation hash/purpose/parent across BOTH documents rather than accepting whichever has a matching value. Development registration uses MECHANICS_CORRECTION lineage: preserve schema compatibility but verify its known parent original provisional ID as recorded. Reject contradictory registration fields or source summary vs manifest summary. Stable RESULT_UNAVAILABLE / RESULT_INCONSISTENT only; no raw AttributeError/InvalidOperation/OverflowError propagating to page.

### R3 — Fail closed through the full read-only view

A failed book supplies no cost scenario table, equity curve or success metrics. The other valid book may remain independently visible. Source revalidation on every read remains; stale saved review fingerprints remain visibly stale, but a fresh fingerprint never overrides economic inconsistencies. Reuse the same validated book snapshot for cards/charts/tables within one page render rather than independently reloading divergent snapshots.

If saved review manifest is missing/malformed/wrong-shaped, fall back only to verified in-memory diagnostics with an honest artifact warning; never crash or present the artifact as verified. Do not rewrite original saved review artifact.

## Verification scenarios

- Reproduce altered exit_fill with unchanged net -> RESULT_INCONSISTENT; no stress table for that book.
- Reproduce final_cash+100 plus declared delta100 -> RESULT_INCONSISTENT; same when declared delta absent/zero.
- Hand-calculated valid trade with fees/raw/slip -> OK; malformed/missing/negative/nonfinite fees; fractional/bool qty; inconsistent recorded fee/slippage/turnover/count -> fail closed.
- Registration list/null or conflicting run/rules/purpose/parent/evaluation hash -> fail closed.
- Malformed equity point/summary/review manifest -> sanitized failure or honest artifact fallback, no page exception.
- Zero trades/metric undefined handled explicitly, without a fabricated profitability result.
- Approved original books still pass and retain original diagnostics:2024 extra1bp43.00 -> -18.70; extra₹1/execution28.00 -> -3.70. Development remains negative.
- Snapshot BOTH source folders, existing `research/review_runs/ee63ea6a-53e8-4b22-aa8a-edd5d4c68a76/`, and backtest trial inventory bytes before/after tests on temporary copies: unchanged. No new persistent research/review run.
- Socket-blocked new fixtures; full suite passes. Streamlit AppTest verifies page with valid and invalid book fixtures: expected errors/cards/tables/holdout notice, no HTTP/simulation/writes. Actual visual verification only claim if performed.

## Boundaries / handoff

Implement ONLY loader/view integrity fixes and meaningful regressions. No strategy/economic rule changes, backtest/validation replay, diagnostic artifact regeneration, fresh market/history/news requests,2025 calculations, Spec08/execution ledger edits, .env/credential access, commits/merges. NSL_FORBID_LIVE_MUTATIONS=1 stays unchanged.

Update `docs/spec_09/results-cost-review-handoff.md`: findings->code->tests, actual commands/counts, AppTest evidence, preserved sources, remaining gaps. Stop for review. The next planned product slice is separate paper-account results/mark visibility, after this evidence loader passes; that task is not authorized by this correction spec.
