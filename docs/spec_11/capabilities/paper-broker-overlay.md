# Capability: Paper broker price overlay

## Requirements

1. **R1** Preserve Spec 10 read-only load; broker fetch only after successful reconciliation with open positions.
2. **R2** One comma-separated `instrument_key` query param (official v2 contract); ≤10 deduped keys (else `BATCH_LIMIT`, **zero HTTP**); one GET per explicit refresh; no load/poll/master fetch.
3. **R3** `status=success`; match `instrument_token` to requested keys only; finite positive `last_price` only (no `close` fallback); reject duplicates/unexpected tokens.
4. **R4** Provider `timestamp` and `last_trade_time` each accept timezone-qualified ISO **or** epoch milliseconds (same field; digit strings count as ms); optional `last_trade_timestamp` only when `last_trade_time` absent. No seconds-epoch guess. Both required and validated independently; `retrieved_at` recorded **after** HTTP response via injectable clock; freshness from **trade** age at display time (15s).
5. **R5** Session cache stores normalized prices/timestamps + retrieval instant only; `materialize_overlay(view, cache, now)` recomputes freshness/totals without HTTP; fingerprint includes **cash** and **cost_basis_inr** + entry fees per position.
6. **R6** Dual display: stored marks vs broker snapshot; portfolio broker totals only if every open position has a **fresh** quote at display time.
7. **R7** Sanitized auth/rate-limit/unavailable/data errors; failed refresh clears session cache (no relabeled stale quotes).

## Portfolio total rule

`cash + Σ(position value)` and unrealized rollups appear only when **every** open position is `FRESH` at the injected display clock (trade age ≤15s from `now`, trade timestamp present). Any `MISSING`, `STALE`, or account fingerprint mismatch suppresses portfolio overlay totals.

## Scenarios

| ID | Given | When | Then |
|---|---|---|---|
| S1 | Reconciled positions | One broker refresh click | 1 comma-batched GET |
| S2 | Session cache | Rerun after 15s+ | Rows STALE; totals gone; 0 HTTP |
| S3 | Cash changes | Render | Overlay invalidated |
| S4 | Failed refresh | Click | Cache cleared; error only |
| S5 | Partial quote response | Refresh | MISSING rows; totals suppressed |
