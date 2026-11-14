# Spec 09 — Frozen 2024 validation replay

Status: AUTHORIZED BOUNDED EXPLORATORY SLICE. Implement prerequisites, prove parity/isolation, perform one offline 2024 replay, write handoff and stop. No 2025 outcomes or trading promotion.

## Review decision / evidence

Independent reviewer: full suite 198 passed. Saved corrected development run `22f4e81b-e66a-4ea1-b77d-325323f61db7` has 16 trades; every trade arithmetic matches fills less fees; sum net P&L -869.13 equals final cash 19130.87 minus 20000. Total modeled fees 539.69. Original provisional and corrected runs remain preserved.

Separate deterministic reviewer fixtures used 100 rising closes (100+0.2*i), signal low117 on bar99 and next open120: 115 shares, ordinary stop net -399.85; next-session opening gap100 net -2350.60 and entry latch true; fifth-session TIME exit; final SPLIT_END exit; opening below stop skips. Core mechanics support proceeding with exploratory validation, NOT strategy acceptance. Costs illustrative, calendar UNVERIFIED, adjustment UNKNOWN. Development losses are evidence and cannot be tuned away.

Frozen corrected rules hash: `d5781d90f3276de37320059a14529c944580fc671c351cbbc04bed90bb191101`. This task shall not alter entry/exit rules, indicator spans/seed, warmup, slippage/fees, sizing/risk limits or rounding. If a newly discovered economic-mechanics defect requires changing those rules or changes development trades/equity, stop before the real validation run and report it.

## Change scope

Extend existing offline research engine to evaluate one explicitly selected split with historical indicator context. Keep default development workflow compatible and preserve Spec08, history acquisition and all saved artifacts. No dependencies/network required. Author a small CLI or explicit `--split validation-2024`; reject holdout/custom evaluation dates for this slice.

### Requirement 1 — finish bounded input/evidence guards first

Current `preflight.py` still assumes several JSON objects have dict shape (`cfg.get`, manifest/readiness/chunks) and converts `meta.row_count` with unguarded int. Malformed checkpoint counters/types can escape the current catch list. Missing manifest currently passes. Make missing/wrong-shaped/invalid scalar/unreadable registered artifacts return stable sanitized BLOCKED evidence, report and terminal inventory state, with zero transport calls and no input writes. Validate complete registered acquisition config payload and consistent dataset/instrument/config identity across checkpoint/config/manifest, not only a few keys plus a copied config_hash. Preserve the known live manifest schema and bytes; no acquisition resume. Do not emit exception messages or data bodies. Keep preflight errors separate from transient report filesystem failures; never mask partial output as success. STARTED attempts interrupted by unexpected computation errors need sanitized terminal error evidence when output is writable.

Fix evidence accounting: opportunity means full-rule signal after warmup irrespective of admission. POSITION_OPEN/HALTED/EXIT_SESSION/NO_NEXT_SESSION/entry-gap skips require correct candidate IDs and actual rule matches; count every candidate once. Current `skipped_exit_session` increments for every exit without a signal, while final-session NO_NEXT_SESSION path is unreachable. No new entries from exit-session signals. This is reporting correction only; do not change trading decisions.

Replace the misleading future-isolation test: it writes changed 2024/2025 data but runs both simulations on the same unchanged dev object. Use the modified input in the second execution and compare exact earlier signals, entries, sizing and completed trade economics, excluding only explicitly boundary-forced outcomes that necessarily differ when the endpoint changes. Add nontrivial hand-calculated fixture tests for reviewer cases above; don't rely solely on real dataset self-reconciliation. Keep malformed input regressions, gap loss, both drawdown latches, stop-first/target-gap, warmup/prior-volume, metric edge cases, baseline cash and split isolation tested.

### Requirement 2 — exact split/context semantics

Evaluation dates: 2024-01-01 through 2024-12-31 inclusive, using observed registered daily sessions only (249 rows expected from acquisition). Read-only verified registered dataset stays `research/history_runs/icicibank-daily-79d0359eb567/`; canonical full hash `9c1a7e2b6f0d8137597d359ad34a4b58fa4033321040f263b8ea61d769a60b3e`.

2021–2023 may supply ONLY causal EMA and trailing-volume warmup. Carry recursive indicator state forward from original 2021 initialization; do not re-seed EMA in 2024 or recompute using any later price. No 2021–2023 trades/account state in the validation portfolio. Start independent validation cash/net peak at 20000, zero position, no pending signal, entry latch false. Only signals whose signal-session date is in 2024 may create validation entries: do not import a 2023 pending signal. First 2024 signal may execute at next observed 2024 open. Existing ₹20k allocation / ₹400 planned risk / ₹2k initial-loss or peak-DD latch remains unchanged. Explicitly label this independent portfolio test, not a continuous 2021–2024 account return.

No trade may read a 2025 bar to complete its outcome. Force open position liquidation at last observed 2024 close when no normal price/time exit occurs; report SPLIT_END. Record final-session qualifying signals as NO_NEXT_SESSION. Historical context is never included in 2024 trade counts, equity metrics or evaluation baseline return. Integrity hashing of 2025 data remains permitted; indicators/signals/returns/outcomes for 2025 do not.

Baseline: standalone 20000 whole-share buy-and-hold at first observed 2024 session open, liquidate last 2024 session close with unchanged illustrative fee/slippage model and nonnegative remainder cash; cash baseline20000. This differs from development's warmup-delayed baseline start because earlier context already supplies warmup. Disclose evaluation and benchmark dates/convention; do not alter original development baseline.

Separate immutable strategy rules hash from split/evaluation config hash. Preserve corrected economic rules hash above; store evaluation hash covering context range/hash, evaluation dates, independent-account initialization, baseline and split-boundary conventions. Engine refactoring may change source digest; report this and verify exact development trade/curve parity in temporary outputs before unlocking validation. Candidate-count-only fixes may change descriptive counts; document that difference separately.

### Requirement 3 — no-peeking registration and artifacts

After all fixture/full-suite/parity checks pass, authorize exactly ONE saved-data real 2024 experiment. Before computing its outcomes, write registration and append STARTED inventory: strategy/rules hash, evaluation config/hash, source digest, full data/context/evaluation hashes, development parent `22f4e81b-e66a-4ea1-b77d-325323f61db7`, purpose FROZEN_2024_VALIDATION, no optimization, future split locked. Do not default its lineage to MECHANICS_CORRECTION or original provisional parent.

Write new immutable `research/backtest_runs/<run_id>/` artifacts: registration, manifest, per-candidate signals/skips, detailed trades/raw references/costs, daily cash/equity/net-liq/exposure and human-readable report. Record terminal success/blocked/error inventory state. No overwrite/delete/relabel of original runs; no writes to history/audit/paper execution DBs.

Report net trade/P&L/fee/slippage reconciliation; opportunities/fills/skips and reasons; wins/losses/breakevens and Wilson95% interval; expectancy/profit factor with honest undefined metrics; drawdown INR/% with denominator; exposure and turnover definitions; risk latch and ambiguity/boundary counts; cash/buyhold baselines with dates/costs. Compare development and validation in separate panels/rows; never silently pool independent-account curves or market a combined probability. Label not statistically established with small samples and single-symbol retrospective selection.

The only resulting readiness labels are EXPLORATORY or INSUFFICIENT EVIDENCE. A positive 2024 outcome alone cannot promote; a negative outcome must remain recorded. No parameter/cost changes, rerun seeking improvement, or 2025 performance after seeing 2024. Stop for analyst review regardless of outcome.

## Scenarios / acceptance

- Config/manifest/checkpoint/meta wrong shape/scalar/missing/counter corruption -> sanitized durable blocked/error evidence; sockets blocked.
- Independent reviewer arithmetic cases reproduced with exact expected quantities/fees/P&L; fixture initial-loss/peak-DD gates and cash conservation.
- Nontrivial changed-future input actually used in prefix test; previous decisions invariant.
- Split fixture: prior context changes warmup causally but never creates trades outside evaluation; no pending2023 entry; final2024 exit uses no2025 price. Changed2025 values with self-consistent fixture hashes leave validation results identical. Fixture hashes may be injected into test registration; production must not bypass registered identity.
- Strategy hash unchanged, evaluation hash deterministic; development trades and full daily curve equal saved corrected reference after refactor, no persistent real development rerun. Metrics/count fixes separately explained.
- One registered2024 run only after checks; artifacts/cost totals reconcile, baseline independently calculated, future holdout locked and run lineage accurate.
- Full suite passes; no live requests, credential access, Spec08 changes, execution DB writes or commits/merges. NSL_FORBID_LIVE_MUTATIONS=1 preserved.

## Tasks / handoff

- [ ] Implement prerequisite guard/accounting/test corrections without changing frozen economics.
- [ ] Add explicit split evaluation with causal history and restricted CLI.
- [ ] Pass fixture tests/full suite and independent development parity.
- [ ] Register then execute one bounded offline2024 validation experiment.
- [ ] Write `docs/spec_09/validation-2024-handoff.md`: scenario-to-test evidence, commands/counts, actual run hashes/lineage/outcomes, development comparison, limitations and proposed next smallest task.
- [ ] Stop for review. No 2025 release, forward-paper promotion or Live acceptance.
