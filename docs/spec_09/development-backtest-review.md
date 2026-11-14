# Spec 09 development backtest review — corrections before validation

Status: CORRECTIONS REQUIRED. No 2024 validation or 2025 holdout performance authorized. Reviewer independently ran 194 tests successfully, then reproduced the failures below using temporary fixtures only. No live requests, no real-data rerun by reviewer.

Repository root for all references: `/Users/sanjain/Documents/hedge_trader/`.

## Findings

### F1 — Entry and allocation violate frozen mechanics (high)

`nifty_lab/research/development_backtest/engine.py:89` sizes from all cash, without the frozen ₹20k entry allocation ceiling. Probe `_max_shares(30000,100,99.5)` permits 299 shares costing ₹29,929.90. Limit entry notional plus modeled entry fee to min(available cash, ₹20,000), retaining ₹400 total modeled planned stop risk. Profits may remain cash but must not raise authorized allocation/risk.

`engine.py:161–163` checks only slipped entry against stop. Raw open ₹99.95, stop ₹100 becomes modeled entry ₹100.05 and passes; original rule requires skipping if raw open OR modeled entry <= stop. Add a real signal -> next-open fixture asserting no buy/fees/trade in this case. Test valid positive raw-open distance separately. Include raw prices/fees/slippage in trade evidence so this is auditable.

### F2 — Baseline can borrow cash implicitly (high)

`nifty_lab/research/development_backtest/metrics.py:76–91`: quantity uses cash // slipped entry without including entry fees. Raw open ₹99.90 -> fill ₹100 -> 200 shares -> remaining cash -₹20. Size whole shares including fee; require non-negative remaining cash. Keep baseline convention otherwise frozen; independently hand-calculate final equity, fees, slippage, entry/exit sessions.

### F3 — Preflight ignores config identity and malformed metadata escapes (high)

`nifty_lab/research/development_backtest/preflight.py:91` calls load_checkpoint_raw and never checks registered checkpoint config hash, dataset_config contents/hash, expected exact year windows, checkpoint dataset identity, or relevant manifest quality/conflict state. In a copied registered dataset, replacing checkpoint config_hash and dataset_config symbol with OTHER still returns ok=True. Data hashes do not substitute for provenance/config validation.

`preflight.py:183` parses merged_meta outside error handling; malformed JSON raises JSONDecodeError, so the runner does not write the required blocked evidence.

Verify registered identity/config hash and annual windows against canonical registered acquisition config, consistent checkpoint/config/manifest identity, quality/eligibility and merged metadata row count/content. Reject conflicts/INVALID. Keep original UNVERIFIED calendar/UNKNOWN adjustment/LIMITED warnings. Handle missing, malformed, wrong-shaped and unreadable artifacts throughout as sanitized blocked results, including runner report/inventory paths. Do not rewrite input files or invoke acquisition/master/network. Add fixture mutations for config, wrong years, metadata and merged-content tampering. Engine input should reject invalid/nonfinite OHLCV and duplicate sessions rather than silently sort/drop; clarify the trusted verified-input boundary.

### F4 — Test names do not provide claimed mechanics evidence (high)

`tests/test_spec09_development_backtest.py:83–97` calls a test “hand calculated single stop trade” but asserts only opportunity_count >= 0. This passes with a broken/no-op simulator. The prefix test at lines73–80 uses flat bars with no trades and compares only counts. The hash test only checks calling the hash function twice returns the same value.

Replace these with independent expected numeric outcomes and nontrivial signals. Cover every original spec scenario: 100-bar warmup and prior20 median excluding current; next open; full cash/fee/risk/P&L reconciliation; entry day and fifth-session exit; stop gap excess loss without clamp; stop-first ambiguity; target gap convention; boundary forced exit and final-session signal handling; held/exit-session skips; capital ceiling; initial-loss and peak-DD latch with exits still working; zero/all-win/all-loss/breakeven metric cases; actual changed-future prefix and changed-2024/25 isolation with self-consistent fixtures; failed preflight durable blocked manifest/report and zero sockets; immutable runs and deterministic content. No tests may claim coverage from nonnegative counters alone. Tests should use temporary fixture data; an optional read-only registered dataset integrity test is fine.

### F5 — Required evidence and registration are incomplete (medium)

`TradeRecord` / metrics / report omit executed entry/exit fee amounts, raw references and realized slippage amounts, exposure and turnover. POSITION_OPEN counting omits volume condition; halted/final/exit-session candidate accounting is incomplete. Define opportunity as a full-rule signal after warmup regardless of portfolio admission; record skip reasons separately with exact candidate identity. Preserve original convention that exit-session signals cannot schedule new entries. Report fees/slippage separately (slippage already embedded in fill P&L, do not subtract twice); reconcile sum of trade net P&L to final cash minus initial cash and daily curve. Define exposure/turnover denominators and percent drawdown denominator; disclose calendar/adjustment limitations and baseline convention in the human report, not only JSON.

`config.py:frozen_rules_payload` omits precision/rounding and ₹20k allocation cap; include all economically relevant rules/cost/risk parameters and explicit rounding mode. `runner.py` computes the rules hash after simulation; materialize the frozen payload/hash/source digest and append STARTED trial record before evaluating real bars, then append outcome/error. Preserve blocked/aborted attempt evidence. A self-consistency hash does not prove unchanged rule registration. Do not tune thresholds/periods/costs after results.

## Bounded implementation task

Implement ONLY F1–F5 mechanics, preflight and evidence corrections; no strategy redesign, optimizer, additional instruments, UI overhaul, network, credentials, Spec08, execution ledger or live mutations. Keep NSL_FORBID_LIVE_MUTATIONS=1. No commits/merges. Original audit/history and run `cffbcdd3-e725-4ca6-bd01-97d424dbc6a2` MUST remain byte-for-byte unchanged.

After fixture/full-suite verification, exactly ONE corrected development-only replay of saved 2021–2023 data is authorized. Record parent original run, original rules hash `de784daaeabb7642c9ce213a832704a46b8ea60e2461fdc95f715cf7ae9df8fb`, new corrected implementation/rules/source hashes, reason MECHANICS_CORRECTION, and changed versus unchanged economic rules. Original run remains provisional/superseded-by-correction in new append-only evidence, never deleted or rewritten. Pre-register corrected configuration before execution. Do not iterate based on whether P&L improves. A negative result is a valid research finding. Do not evaluate 2024 or 2025 outcomes, even as a smoke test.

Update `docs/spec_09/development-backtest-handoff.md` with finding -> implementation -> test mapping, actual commands/counts, independent arithmetic examples, one corrected run and lineage, fees/slippage/exposure/turnover, limitations and remaining gaps. Stop for review before validation. Proposed validation replay is deferred until mechanics acceptance; this task does not authorize paper or Live promotion.
