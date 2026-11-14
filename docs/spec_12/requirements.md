# Spec 12 — Requirements & scenarios (acceptance)

## R1 Dual timestamps

Provider `timestamp` and `last_trade_time` required independently. No fallback. Future vs `retrieved_at` rejected. Both must be ≤15s old at receipt. `QuoteSnapshot.evaluated_at` = conservative `min(provider, trade)` for confirm TTL.

## R2 Token identity scan

Match rows by `instrument_token` only; reject 0 or >1 matches (order-independent).

## R3 Strict depth scalars

Whole positive quantities; strict prices; no `int()` truncation; bool/fractional/NaN/inf rejected.

## R4 UI source safety

Explicit **Broker snapshot** vs **Manual simulation**. Failed fetch clears capture + preview. Manual inputs only when manual source selected.

## R5 Spec 08 close path unchanged

Preview economics frozen; confirm via existing APIs.

### Findings → tests

| Finding | Test |
|---------|------|
| Trade-only freshness fallback | removed; `test_reject_missing_*`, `test_fresh_trade_stale_provider_rejected` |
| Dict-key row pick | `_row_by_instrument_token`; `test_duplicate_token_rows_rejected` |
| Loose depth parse | `_strict_*`; `test_reject_malformed_depth_scalars` (×4) |
| Silent manual fallback after broker fail | UI clear; `test_apptest_failed_refresh_clears_confirm` |
| Hidden manual under broker capture | source radio; `test_apptest_source_switch_invalidates_preview` |
| Accounting EV | `test_numeric_oracle_sell4` (gross 40, net 38.2, qty 6, entry fees 1.2) |

### Scenarios

| ID | Scenario | Evidence |
|----|----------|----------|
| S1 | Valid depth | `test_parse_valid_depth_bbo` |
| S2 | Timestamp rejects | `test_reject_missing_*`, `test_reject_future_provider_time` |
| S3 | Stale provider | `test_fresh_trade_stale_provider_rejected` |
| S4 | Duplicate token | `test_duplicate_token_rows_rejected` |
| S5 | HTTP discipline | `test_fetch_one_get`, AppTests |
| S6 | Ledger safety | partial/nonmarketable/pending/competing tests |
| S7 | Confirm stale | `test_stale_broker_snapshot_rejected_at_confirm` |
