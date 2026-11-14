# Spec 12 — Handoff (acceptance corrections)

## Changes

- **`broker_close_quote.py`**: independent provider + trade timestamps; 15s receipt freshness on **both**; `evaluated_at=min(provider,trade)`; token-only row scan with duplicate reject; strict depth scalars.
- **`trade_ticket.py`**: **Broker snapshot** / **Manual simulation** radio; failed fetch clears capture + preview; manual bid inputs only in manual mode; holding fingerprint clears stale state.

## Findings → tests

| Review finding | Test |
|----------------|------|
| Missing trade fell back to provider time | `test_reject_missing_trade_with_valid_provider` |
| Missing provider accepted with trade | `test_reject_missing_provider_with_valid_trade` |
| Recent trade hid stale depth | `test_fresh_trade_stale_provider_rejected` |
| First matching JSON row wins | `test_duplicate_token_rows_rejected` (both orderings) |
| `int(10.9)` depth | `test_reject_malformed_depth_scalars` |
| Failed fetch kept stale preview | `test_apptest_failed_refresh_clears_confirm` |
| Broker capture overrode hidden manual fields | `test_apptest_source_switch_invalidates_preview` |
| Realized EV | `test_numeric_oracle_sell4` |

## Commands & counts

```bash
export NSL_FORBID_LIVE_MUTATIONS=1
TMPDIR=.pytest_tmp .venv/bin/pytest -q tests/test_spec12_broker_paper_close.py  # 22 passed
TMPDIR=.pytest_tmp .venv/bin/pytest -q tests                                     # 294 passed
```

## Scenario coverage (abbrev.)

| Area | Tests |
|------|-------|
| Parse/timestamp/depth | 10 + 4 param |
| Ledger oracle/safety | `test_numeric_oracle_sell4`, partial, nonmarketable, competing, stale confirm |
| AppTest HTTP | load 0 GET, fetch→preview→confirm, failed refresh, source switch |
| Pre-HTTP guard | `test_option_kind_fails_before_http` |

## Limitations (unchanged)

- Remainder re-eval on Trade Ticket still manual (out of scope).
- `expected_instrument_token` defaults to `instrument_key`.
- No live smoke, commits, mark/overlay writes.

Stop for review.
