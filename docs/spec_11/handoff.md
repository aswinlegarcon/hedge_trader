# Spec 11 — broker overlay handoff (parse + retrieval corrections)

Status: **ACCEPTANCE FIXES (2nd pass)**. **STOP** for review.

## This pass

| Fix | Evidence |
|---|---|
| Documented `timestamp` / `last_trade_time` ISO **or** epoch-ms on same field | `test_parse_canonical_v2_official_field_shapes`, `test_parse_timestamp_epoch_ms_on_timestamp_field` |
| Reject seconds-epoch + naive ISO | `test_parse_rejects_seconds_epoch_and_naive_iso` |
| `retrieved_at` after `transport.get()`; injectable `clock` on fetch/refresh | `test_slow_response_retrieval_after_transport_get` |
| >10 unique keys → `BATCH_LIMIT`, no HTTP, no Streamlit exception | `test_over_ten_unique_keys_no_http` |
| `select_instrument_keys` → `(keys, err)` inside refresh (no raise) | refresh path |

## Commands

```bash
export NSL_FORBID_LIVE_MUTATIONS=1
TMPDIR=.pytest_tmp .venv/bin/pytest -q tests   # 272 passed (22 Spec11)
```

## Portfolio rule (unchanged)

Broker portfolio totals only when every position is **FRESH** at display-time trade age ≤15s (no new HTTP).

## Boundaries

Mocked HTTP only; no DB writes; **NSL_FORBID_LIVE_MUTATIONS=1**.

**Stop here.**
