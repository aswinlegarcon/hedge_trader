# Spec 13 — Handoff (production-path acceptance)

## Defects resolved

| ID | Fix |
|----|-----|
| **DEFECT-13-01** | `submit_paper_entry` uses confirmed `entry_cost_inr` (proportional on partial); removed `max(20, 0.25×…)` |
| **DEFECT-13-02** | Trade Ticket bid/ask independent of limit; entry slippage % in preview/confirm/submit (no hidden default) |

Simulation convention documented in UI caption and `paper.submit_paper_entry` docstring.

## Commands & counts

```bash
export NSL_FORBID_LIVE_MUTATIONS=1
TMPDIR=.pytest_tmp .venv/bin/pytest -q tests/test_spec13_paper_workflow_acceptance.py  # 8 passed
TMPDIR=.pytest_tmp .venv/bin/pytest -q tests                                     # 313 passed (after Spec 14)
```

## Production-path evidence

| Step | Mechanism | Check |
|------|-----------|--------|
| BUY 10@100 fee ₹2 | `build_preview` → `confirm_preview` → `submit_paper_entry(slippage_pct=0)` | cash **18998**; `test_independent_oracle_journey`, `test_entry_fees_match_confirmed_preview`, `test_apptest_full_paper_journey` |
| Broker SELL partial | Spec 12 fetch + close preview/confirm | oracle through **20061** / net **61** |
| Entry slippage | explicit % frozen at preview | `test_entry_slippage_marketable_and_blocked` |
| Partial entry fees | `allocate_proportional` | `test_partial_entry_fee_allocation` |
| Tamper / replay | preview guards | `test_confirm_rejects_fee_slippage_change`, `test_replay_and_observation_guards` |

## Scenario → test

| Scenario | Test |
|----------|------|
| Primary oracle | `test_independent_oracle_journey` |
| Confirmed entry fees | `test_entry_fees_match_confirmed_preview` |
| Slippage marketable / blocked | `test_entry_slippage_marketable_and_blocked` |
| Partial fee allocation | `test_partial_entry_fee_allocation` |
| Invalid economics | `test_invalid_entry_economics_rejected` |
| Close replay / observation | `test_replay_and_observation_guards` |
| AppTest empty ledger → BUY → broker close | `test_apptest_full_paper_journey` |

## Verified vs unverified

| Verified | Unverified |
|----------|------------|
| Full API oracle + readonly Paper Account checkpoints | Live Upstox connectivity |
| AppTest manual BUY form + broker close (mocked HTTP) | AppTest cancel-remainder button in same run |
| HTTP: 0 on load/preview/confirm entry; 1 per explicit broker fetch | Broker-priced remainder re-eval |
| Temp DB only (`paper_db_path` guarded) | Production `data/paper_execution.db` |

## Limitations

- Modeled fees/slippage are **LOCAL PAPER simulation**, not broker-verified.
- Partial BUY remainder retains unallocated entry fees until a later fill path (no automatic top-up on cancel).
- Mocked quote timestamps; illustrative costs.
- Streaming chart prototype: see **Spec 14** (`docs/spec_14/handoff.md`).

Stop for acceptance review.