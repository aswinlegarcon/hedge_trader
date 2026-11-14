# Spec 09 — Development backtest handoff

Date: 13 November 2026 IST. Status: **MECHANICS CORRECTION — stop for review**. Spec 08 unchanged. Saved history/audit and provisional run `cffbcdd3-e725-4ca6-bd01-97d424dbc6a2/` **byte-for-byte preserved**. **No live/network requests** in this pass.

## Review corrections (F1–F5)

| Finding | Implementation | Test evidence |
|---------|----------------|---------------|
| **F1** Entry sizing > ₹20k allocation; raw open below stop | `ENTRY_ALLOCATION_CEILING`; `_max_shares` uses `min(cash, ceiling)`; skip if `raw_open <= stop` or modeled entry ≤ stop; trade records include raw/fee/slippage fields | `test_max_shares_respects_20k_allocation_ceiling`, `test_raw_open_below_stop_skips_entry` |
| **F2** Baseline negative cash after fees | `_max_buy_hold_shares` sizes with entry fee; `remaining_cash_after_buy >= 0` | `test_buy_hold_baseline_non_negative_cash` (199 shares @ ₹99.9 open) |
| **F3** Weak preflight / malformed meta escape | Config hash + `dataset_config.json`; chunk windows; manifest BLOCKED/CONFLICT; `merged_meta` parse guarded; returns blocked manifests | `test_checkpoint_config_tamper_blocks`, `test_malformed_merged_meta_writes_blocked_manifest` |
| **F4** Vacuous tests | Replaced with arithmetic/isolation cases; cash reconcile; lineage/preregistration | `test_cash_reconciles_with_trades_sum`, `test_prefix_invariance_development_hash`, `test_preregistered_and_lineage`, etc. |
| **F5** Evidence gaps | `TradeRecord` fee/slippage/raw fields; exposure on equity curve; turnover/fees in summary; `registration.json` before sim; STARTED inventory | corrected run artifacts + `test_registered_preflight_readonly` |

### Independent arithmetic examples (fixtures)

- **Allocation ceiling:** `_max_shares(₹30,000 cash, fill ₹100, stop ₹99.5)` → **199** shares, cost **≤ ₹20,000** (not 299 @ ₹29,929).
- **Buy-and-hold:** open ₹99.90 → fill ₹100.00 → **199** shares, remaining cash **≥ 0** (was **-₹20** before fix).
- **Raw open gate:** signal low ₹100, next open ₹99.95 → fill ₹100.05 but **raw ≤ stop** → **admission skip**, **0 trades**.

## Code paths

| Item | Path |
|------|------|
| Package | `nifty_lab/research/development_backtest/` |
| CLI | `scripts/run_development_backtest.py` |
| Tests | `tests/test_spec09_development_backtest.py` (12) + `tests/test_spec09_full_daily_history.py` (13) |

## Verification

```bash
TMPDIR=.pytest_tmp .venv/bin/pytest -q tests/test_spec09_development_backtest.py
TMPDIR=.pytest_tmp .venv/bin/pytest -q tests
NSL_FORBID_LIVE_MUTATIONS=1 .venv/bin/python scripts/run_development_backtest.py
```

| Command | Result |
|---------|--------|
| Development backtest tests | **12 passed** |
| Full `tests/` | **198 passed** |

## Run lineage

| Run | Role | Rules hash | Notes |
|-----|------|------------|-------|
| `cffbcdd3-e725-4ca6-bd01-97d424dbc6a2` | **Original provisional** (preserved) | `de784daaeabb7642c9ce213a832704a46b8ea60e2461fdc95f715cf7ae9df8fb` | Superseded by correction evidence only — not deleted |
| `22f4e81b-e66a-4ea1-b77d-325323f61db7` | **Corrected mechanics replay** | `d5781d90f3276de37320059a14529c944580fc671c351cbbc04bed90bb191101` | `MECHANICS_CORRECTION`, parent = `cffbcdd3…` |

**Pre-registration:** `registration.json` written **before** simulation; inventory `STARTED` then `EXPLORATORY_COMPLETE`.

### Corrected run outcomes (exploratory only)

- Closed trades **16** (6W/10L); net P&L **-₹869.13**; final cash **₹19,130.87**
- Modeled entry/exit fees **₹270.00 / ₹269.69**; slippage totals reported separately
- Turnover notional **₹539,668.04**; `cash_reconcile_delta_inr` **0.00**
- Max drawdown net liq. **₹1,972.86** (~9.62% of peak)
- **2024 validation / 2025 holdout:** not evaluated

## Limitations (unchanged)

- Calendar **UNVERIFIED**; adjustment **UNKNOWN**
- Costs **illustrative** — not verified broker/STT/GST/DP schedule
- Results are **not** predictive, validated, Live-ready, or paper-candidate
- Negative corrected P&L is a valid exploratory finding — **no tuning** applied

## Remaining gaps

- Validation split (2024) replay deferred until mechanics accepted
- Authoritative calendar/adjustment evidence still missing
- Intrabar stop/target ordering remains disclosed assumption on daily bars

## Proposed next task

After review acceptance: **frozen 2024 validation replay** with corrected engine (still **no 2025 holdout outcomes**).

**Stop for review. No commits/merges.**
