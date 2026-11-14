# Spec 10 — Paper Account handoff (fee & basis completion)

Status: **FEE/BASIS + FILL SEQUENCING COMPLETE**. Read-only Paper results with UTC-normalized fill ordering, average-cost replay, and fail-closed reconciliation. **STOP** for acceptance review.

## Fee-basis review → code → tests

| Finding | Implementation | Regression test(s) |
|---|---|---|
| Stored `realized_events` / `positions` not independently derived | `fee_basis.py` — UTC-ordered replay on `filled_at`, weighted avg cost, paise allocation, per-SELL realized check | `test_reviewer_probe_offset_entry_fees_and_realized_net`, `test_reviewer_probe_offset_avg_price_and_realized` |
| Aggregate P&L identity insufficient | `reconcile.py` uses replay totals only after per-fill validation; offsets that preserve total P&L still fail | offset probe tests above |
| Multi-leg independent oracle | Two buys (unequal qty/fees), two partial sells, reopen buy — hand-checked realized **41.00 / 39.20**, remaining fees **2.00**, avg **104.50** | `test_multi_buy_partial_closes_reopen_oracle` |
| Ambiguous same-timestamp BUY+SELL | `FILL_SEQUENCE_AMBIGUOUS` | `test_fill_sequence_ambiguous_same_timestamp`, `test_equivalent_utc_ist_instant_buy_sell_ambiguous` |
| Schema+data in one transaction | `reader.py` — `BEGIN` before `PRAGMA table_info`/column checks and all `SELECT`s | existing read tests; legacy `MISSING_COLUMN` unchanged |

## Fill-sequencing corrections → code → tests

| Requirement | Implementation | Test(s) |
|---|---|---|
| Timezone-qualified `filled_at` only; normalize to UTC | `_parse_fill_time()` → `FILL_TIME_NAIVE` / `FILL_TIME_MISSING`; group/sort on `timestamp()` UTC | `test_fill_time_naive_rejected` |
| Equivalent instants across offsets | UTC `+00:00` vs IST `+05:30` same epoch → one instant bucket | `test_equivalent_utc_ist_instant_buy_sell_ambiguous` |
| No `fill_id` chronology; SELL ties fail closed | Sort UTC instant only; ≥2 fills same (instant, instrument) with any SELL → `FILL_SEQUENCE_AMBIGUOUS` | `test_tied_sell_sell_same_instant_rejected` |
| Persisted `fill_id` required | No `fill_event_id` fallback | `test_fill_id_missing_rejected` |
| BUY-only ties commutative | Replay order-independent for tied BUYs; instruments isolated per `(instant, ik)` | `test_tied_buy_buy_same_instant_permutation_invariant` |
| Paise order sensitivity | 3 units / ₹0.05 fees → ₹0.01 then ₹0.02 on 1+1 closes | `test_proportional_paise_sell_order_matters` |
| Distinct valid timestamps | Prior oracle unchanged | `test_distinct_timestamps_valid_oracle_unchanged`, all prior probes |

### Algorithm / precision (read-side)

- Parse `filled_at` with mandatory timezone; convert to UTC; sort by UTC epoch only (never `fill_id`).
- Per instrument, bucket fills by UTC instant; >1 fill at same instant with any **SELL** (including SELL+SELL or BUY+SELL) → unavailable; tied **BUY-only** buckets allowed (commutative cost/fees).
- BUY: add `qty × price` to monetary cost basis; add entry fees to pool (rounded paise).
- SELL: proportional entry-fee allocation (`//` paise split, ledger-compatible); realized gross/net from proceeds, `qty × avg`, allocated entry fees, exit fees; **0.01 INR** tolerance vs persisted rows.
- Open position: compare **monetary** `qty × avg_price` and `entry_fees_inr` to replay state.
- Sanitized codes only; derived metrics suppressed on any sequencing/basis failure (no uncaught exceptions).

### Reviewer offset probes (both fail closed)

| Mutation | Error (first) | Suppressed metrics |
|---|---|---|
| `entry_fees_inr+1`, `realized net_inr+1` | `POSITION_ENTRY_FEES_MISMATCH` / `REALIZED_EVENT_MISMATCH` | cash, realized, remaining fees, equity |
| `avg_price+1`, `realized gross/net+6` | `POSITION_BASIS_MISMATCH` / `REALIZED_EVENT_MISMATCH` | total P&L, unrealized, equity |

Prior four integrity probes remain covered (`test_reviewer_probe_*`).

## Delivered components

| Component | Path |
|---|---|
| INR Decimal helpers | `nifty_lab/paper_account/decimal_inr.py` |
| Fee/basis replay | `nifty_lab/paper_account/fee_basis.py` |
| Reconciliation | `nifty_lab/paper_account/reconcile.py` |
| Read-only snapshot | `nifty_lab/paper_account/reader.py` (`filled_at`, `fill_id` required) |
| Accounting / UI | `nifty_lab/paper_account/accounting.py`, `ui.py`, `pages/13_Paper_Account.py` |
| Tests | `tests/test_spec10_paper_account.py` (**27**) |

**NOT on production path:** `ExecutionLedger`, `get_ledger()`, `portfolio_context()`.

## Commands

```bash
export NSL_FORBID_LIVE_MUTATIONS=1
TMPDIR=.pytest_tmp .venv/bin/pytest -q tests   # 250 passed (27 Spec10)
streamlit run app.py
```

## Partial-close oracle (unchanged)

Mark **100**: cash **19437.00**, realized gross/net **40.00 / 38.20**, remaining entry fees **1.20**, stored-mark equity **20037.00**, total P&L **37.00**, fees paid **3.00**.

Mark **105**: equity **20067.00**, total P&L **67.00**.

## Unavailable legacy cases

- DBs without `fills.filled_at` or `fill_id` → `UNSUPPORTED_SCHEMA` / `FILL_ID_MISSING`.
- Naive `filled_at` (no offset) → `FILL_TIME_NAIVE`.
- Same UTC instant with multiple fills and any SELL on one symbol → `FILL_SEQUENCE_AMBIGUOUS` (includes SELL+SELL; paise path order-dependent).
- Deep audit of `planned_risk_inr`, contract metadata, and cross-instrument ties beyond stored fill timestamps — still explicit unknown where replay cannot establish order.

## Boundaries

No real DB writes from page, marks/funding/gate/fill changes, network/credentials, strategies/backtests/2025, commits/merges. **NSL_FORBID_LIVE_MUTATIONS=1** unchanged. Temp fixture DBs only in tests.

**Stop here — await fill-sequencing + fee/basis acceptance before mark-update or execution slices.**
