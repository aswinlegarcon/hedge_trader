# Spec 08 implementation handoff

Status: **CORRECTIONS IN PROGRESS** — **not accepted for Live**. `NSL_FORBID_LIVE_MUTATIONS=1`. No broker place/modify/cancel/close. No git commits.

## Paper close slice — review corrections (13 Nov 2026)

Follow-on per `docs/spec_08/paper-close-slice.md`; first review (`spec_08_paper_close_review.md`) + second review (`spec_08_paper_close_review_2.md`).

### Fixes delivered

| Finding | Fix |
|---------|-----|
| 1. Remainder fill oversell check | SELL ownership gate uses current owned minus other pending only (`fill_qty`, not `prior_filled + fill_qty`) |
| 2. Economic hash ≠ intent | `admit_paper_close` dedupes **intent_id only** (idempotent restart); identical economics with new intent creates a **new** order |
| 3. Re-eval instrument binding | `re_evaluate_paper_close` takes **quote + fees** only; limit/kind/lot/qty from persisted order; foreign quote rejected |
| 4. Observation identity | `quote_observation_id(quote)` uses source time + BBO/depth; consume is **atomic with successful fill** only (`execute_paper_close_fill`) |
| 5. Preview-bound economics | `build_close_preview` / `confirm_close_preview` — stable `close_intent_id`, `exit_fees_inr`, `slippage_pct`, `observation_id`; UI uses frozen ticket on submit |

### Second-review blockers (transaction / identity / migration)

| Finding | Fix |
|---------|-----|
| Invalid exit fees on close path | `fill_validation.py` — shared checks on `apply_paper_fill`, `_apply_paper_fill_conn`, `execute_paper_close_fill`, `admit_paper_close`, `submit`/`re_evaluate`, `build_close_preview` |
| Caller relabels owned contract | `admit_paper_close` / reduce-only `create_reservation` match **persisted** kind/lot/product/symbol/underlying; orders store contract from position row |
| Legacy metadata guessing | Removed `CASH_STOCK`/lot-1/DELIVERY inference; reopen sets `closeable=0` when kind/product/lot incomplete; `list_closeable_positions` filters `closeable=1` only |

Prior cancel, gate, replay, first-review close fixes and **numeric accounting oracle** retained.

### Scenario evidence

| Scenario | Test |
|----------|------|
| Accounting oracle | `test_accounting_oracle_partial_and_full` |
| Same-order 4+6 liquidation | `test_same_order_partial_then_complete_liquidation` |
| Distinct identical later close | `test_identical_later_close_is_new_order_not_historical` |
| Intent idempotent restart | `test_same_intent_idempotent_after_restart` |
| Re-eval foreign quote | `test_reevaluate_rejects_foreign_instrument_quote` |
| Observation vs ticket | `test_observation_id_includes_source_time` |
| Nonmarketable no consume | `test_nonmarketable_close_does_not_consume_observation` |
| Fee tamper at confirm | `test_close_preview_fee_tamper_rejected` |
| Negative exit fees rollback | `test_negative_exit_fees_rejected_with_rollback` |
| NIFTY relabeled as stock | `test_relabel_nifty_as_stock_rejected` |
| Unknown legacy on reopen | `test_legacy_unknown_metadata_blocked_on_reopen` |
| Cancel / competition / ETF / NIFTY / depth | Existing close + `test_spec08_execution.py` |

### Verification (actual run)

```bash
TMPDIR=.pytest_tmp .venv/bin/pytest -q tests/test_spec08_execution.py tests/test_spec08_paper_close.py
TMPDIR=.pytest_tmp .venv/bin/pytest -q tests
```

| Command | Result |
|---------|--------|
| Spec 08 focused | **59 passed** (37 execution + 22 close) |
| Full `tests/` | **160 passed** |

### UI (honest)

Trade Ticket close section: owned / reserved / sellable caption, cumulative realized, manual-quote disclaimer, preview-bound fees/slippage/intent, observation id caption, re-eval uses **saved order limit** (bid/depth only for refresh).

**Still not delivered:** dedicated realized/unrealized results panel with gross/net breakdown per position; manual mark update workflow; full estimated net at preview from bound fees (caption shows fees only).

### Remaining scope

- `UNKNOWN_SUBMISSION` reconciliation UI
- Sandbox place HTTP; Live confirm → adapter
- Spec 09 (separate)

**Overall Spec 08:** **CORRECTIONS IN PROGRESS** — stop for review.
