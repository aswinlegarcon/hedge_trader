# Spec 09 — First development-only exploratory daily backtest

Status: MECHANICS CORRECTION applied — stop for review (see development-backtest-handoff.md). Implement this slice, write evidence, then stop for review. This is an experimental mechanics and research task, not strategy acceptance.

## Why / scope

The saved five-year ICICIBANK history is available. Reviewer independently ran 185 passing tests and verified all five raw/normalized chunk hashes. Build one deterministic, offline cash-equity daily experiment using 2021–2023 only. Reserve 2024 validation and 2025 final holdout performance until separate review. No optimizer, alternative strategy search, broker requests, execution-ledger writes or Live promotion.

## Prerequisites: remaining history boundary corrections

Fix these narrowly before running the experiment; both reproduced in isolated fixtures:

1. `nifty_lab/research/full_daily_history/runner.py`, master-resolution exception handler currently changes CONFLICT to NOT_FETCHED. A subsequent healthy-master resume refetches that chunk (one call reproduced). CONFLICT must remain durable across master failures and budget-stop bookkeeping. Test conflict -> master failure -> healthy resume with zero historical calls for the conflicted chunk, preserved affected raw/normalized bytes and counters.
2. Config-conflict handler preserves bytes correctly but its returned result currently says COMPLETE / EXPLORATORY_ONLY without verification. Return an explicit blocked conflict result: backtest eligibility BLOCKED; do not present current-config usable completeness. Preserve existing dataset bytes, record only a separate sanitized invocation sidecar, no HTTP. Test the returned status as well as byte preservation.
3. Strengthen the existing repeated-conflict test: it clears one transport's calls but passes a different uninspected transport to the second invocation. Assert against the actual transport used each time.

No real acquisition/resume invocation is authorized. Saved history/audit artifacts remain byte-for-byte unchanged.

## Requirements

### R1 — Offline verified inputs and split isolation

The engine SHALL accept only this registered dataset: `research/history_runs/icicibank-daily-79d0359eb567/`, ICICIBANK / NSE_EQ|INE090A01021, daily. Source merged canonical hash: `9c1a7e2b6f0d8137597d359ad34a4b58fa4033321040f263b8ea61d769a60b3e` (1240 rows). Reconstruct and verify raw/normalized annual content and canonical merged identity read-only; verify exactly the expected annual windows and instrument/config identity, no missing/duplicate/invalid data silently accepted. Checkpoint/config conflicts, hash mismatch, missing/malformed artifacts, INVALID quality, or missing verified merge SHALL block the experiment with sanitized evidence. Metadata hash alone is not proof of merged content integrity. This preflight MUST NOT invoke the downloader or instrument master service. Existing UNVERIFIED calendar / UNKNOWN adjustment / LIMITED candidate weekday gaps remain explicitly disclosed; no filling missing sessions or invented adjustments.

Strategy calculations and outcomes SHALL use only annual 2021, 2022, 2023 observations. It is permissible to hash 2024/2025 content for integrity, but never calculate indicators, signals, returns, benchmark performance, trade counts or outcomes for those years. Record development subset hash and range separately. A fixture changing 2024/2025 prices (with self-consistent fixture metadata) must leave development outputs unchanged. Do not print future price summaries.

### R2 — Frozen single experimental strategy

ID `icicibank_daily_pullback_v1`; long cash stock only, whole shares. No options/shorts/leverage. Rules below SHALL be registered and hashed before inspecting real development performance; do not change them after seeing results in this task.

- Ascending observed daily sessions in IST; no calendar interpolation. EMA20 and EMA50 use recursive EMA, alpha=2/(span+1), initialized with first development close (`adjust=False` equivalent). No entry signal until 100 observed bars including signal bar have completed.
- At signal session t close: close[t] > EMA20[t] > EMA50[t], low[t] <= EMA20[t], and volume[t] >= median(volume[t-20:t]), excluding t. Only observations through t may influence that signal.
- Entry is next observed session's open plus modeled adverse slippage. Signal low is fixed stop. Skip if raw next open or modeled entry <= stop, any invalid price, insufficient cash, or no next development session. No same-close entry.
- R = modeled entry minus signal low; fixed target = modeled entry + 2R. Stops/targets remain fixed. Evaluate entry-session range too. Stop gap: if raw open <= stop, exit reference raw open. Otherwise stop touched when low <= stop. If both stop and target touch, choose stop first and count ambiguous bars. Target gap at open >= target uses target reference (no favorable gap windfall); target touch uses target reference. Apply adverse SELL slippage to exit reference, including target. Daily bars cannot establish true intrabar order; disclose assumptions.
- If no price exit, time exit at fifth observed session close counting entry session as one. Stop/target checks precede time exit. At final development session close, force exit any remainder with reason SPLIT_END, costs and slippage; never inspect 2024 to complete it. Record boundary truncation. Final-session signals cannot create entries.
- One open position maximum; no pyramiding. Signals while holding are recorded as skipped. For simplicity do not schedule a fresh entry from the session on which a position exits; evaluate fresh signals only on a later flat session. State this convention in artifacts.

### R3 — Explicit illustrative costs and capital simulation

Freeze a transparent illustrative model: 10 basis points adverse slippage per side and a modeled fee of 10 basis points of each executed notional per side. These are experimental assumptions, NOT verified Upstox/NSE/STT/GST/DP charges or a complete real-cost schedule. No external fee research/network required for this slice. Costs UNKNOWN in the real-world sense; all results remain EXPLORATORY. Report these modeled fees and slippage separately; include a warning that actual delivery/exit costs and corporate actions are unresolved. No zero-cost validated result.

Simulate initial cash ₹20,000, no deposits/leverage; size once at entry using maximum whole-share quantity satisfying both available cash including entry modeled fee and ₹400 estimated stop loss including adverse stop execution and both modeled fees. For q shares, planned stop loss = q*(entry_fill - stop*(1-slip)) + fee(q*entry_fill) + fee(q*stop*(1-slip)). Require finite positive stop exit reference. Cash must never become negative from an admitted entry. Keep ₹800 underlying / ₹1200 aggregate / max3 limits visible; single-position ₹400 is tighter here. Sizing must not use future daily low/exit price or later equity.

Mark open positions at observed close for daily equity (cash + shares*close), report gross marked equity and separately net-liquidation equity after estimated exit fee/slippage. Use net-liquidation equity to maintain running peak and drawdown; latch stop-new-entry if loss from initial capital OR peak drawdown reaches ₹2000. Existing positions still exit normally. Risk budget is planned risk, not guaranteed maximum: stop gaps can exceed ₹400/₹2000; do not clamp losses. No auto-compounding beyond ₹20k entry allocation or risk increase from profits. Freeze price/fee precision and rounding in config and tests before real run; cash arithmetic should use decimal or a documented deterministic monetary convention.

### R4 — Report, baseline and reproducibility

Write new, distinct artifacts under `research/backtest_runs/<run_id>/`: frozen config/rules and hashes, preflight manifest, development dataset hash, chronological signals/skips/trades with entry/exit timestamps/reasons/qty/stop/target/planned risk/actual net result, daily equity, report. Preserve existing runs; reject overwrite. Write blocked-run manifest/report too, using sanitized error classes, never exception bodies or credentials. No paper DB writes.

Report signal/opportunity count, filled trades and skips by reason (do not call raw signals simulated returns), wins/losses/breakevens after modeled costs, win rate with Wilson 95% interval, average net win/loss, net expectancy per closed trade, profit factor (explicit undefined/infinite where appropriate), net P&L, initial/final equity, daily-marked maximum drawdown in INR/% with denominator, exposure, turnover definition, modeled fees/slippage and boundary/ambiguity counts. Zero/one-trade reports must be honest and well-defined. Show yearly development breakdown descriptively, no best-strategy/ranking badge.

Baseline: same ₹20k and development evaluation interval beginning at the first session after 100-bar warmup; whole-share buy-and-hold at that open and liquidation at final development close, same cost/slippage model, remaining cash included. Also show cash baseline. Baselines are descriptive and do not use strategy risk sizing or claim investability. Label comparison differences explicitly. Report UNTESTED before execution and EXPLORATORY or INSUFFICIENT EVIDENCE afterward, never validated/profitable-future/predictive accuracy, FORWARD PAPER CANDIDATE or Live-ready. No threshold declared proof.

Persist source dataset identity, code revision + dirty state or equivalent engine source digest, rules/config/cost hashes, split policy and all attempted real experiments in an append-only trial inventory. One real development run only after fixtures pass; replay may verify determinism without searching variants. If rules need changes after outcomes, preserve original and stop for review rather than rerun adjusted variants.

### R5 — Scope boundaries

A bounded CLI (`scripts/run_development_backtest.py` or equivalent) and research package/tests are sufficient. No dashboard overhaul; at most update Backtesting Lab copy with accurate status/artifact reference. Do not touch Spec08 accounting/gates/execution UI, tokens, environment, API integrations, journal or broker endpoints. NSL_FORBID_LIVE_MUTATIONS=1 stays enforced. No commits/merges. No reading .env, no credentials in output. No downloading libraries/data/books. Existing dependencies first.

## Scenarios / verification

- Prefix-invariance: a signal at t and entry sizing at t+1 are unchanged by later bars; no future volume/EMA/cash leakage.
- Exact indicator initialization, 100-bar warmup, prior20 median, next-open execution and no last-session entry.
- Entry/exit hand-calculated fixture including share sizing, fees, adverse slippage, cash conservation, marks and final liquidation.
- Same-bar dual touch stop-first; gap-through-stop realizes excess risk rather than clamping; target gap rule; entry-day and fifth-session exits; final split liquidation.
- Whole shares, insufficient cash, invalid prices, no pyramiding, skipped held/exit-session signals; stop-new-entry latch at initial-loss or peak-DD threshold while exits continue.
- Zero trades, all losses, no losses, breakevens, confidence interval and undefined metric handling; benchmark independently hand-calculated.
- Input tampering including merged content versus metadata; missing/conflicted/malformed inputs produce blocked durable report with zero HTTP.
- Validation/holdout isolation and identical fixture outputs/hashes on repeat; append-only artifacts and one trial record per real run.
- Above prerequisite regressions pass; run full existing suite with sockets blocked in new tests.

## Tasks / handoff

- [x] Fix and prove prerequisite history boundary cases using temporary fixtures only.
- [x] Freeze versioned rules/cost/precision and implement offline preflight + engine.
- [x] Prove mechanics with hand-calculated fixtures and run full suite.
- [x] Perform exactly one development-only experiment using saved data; preserve artifacts and all limitations. No validation/holdout outcomes.
- [x] Update `docs/spec_09/development-backtest-handoff.md` with finding-to-test mapping, commands/counts, artifact paths/hashes, outcomes and limitations, untouched future splits, no-live confirmation, and proposed next smallest task.
- [ ] Stop for review; Spec09 overall and Spec08 Live readiness are not automatically accepted.
