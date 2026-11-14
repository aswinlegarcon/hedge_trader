# Spec 09 — Results and cost sensitivity review handoff

Status: **COMPLETE + integrity correction.** Read-only archived review; loader fail-closed. **STOP** — no new backtests, 2025 release, or paper/live promotion.

## Integrity correction (2026-11-13)

| Finding | Fix | Test |
|---|---|---|
| Tampered `exit_fill` with unchanged net → loader OK | Per-trade Decimal identity (net, fees, slippage), turnover vs summary | `test_reviewer_probe_exit_fill_tamper` |
| `final_cash` +100 and declared reconcile 100 → OK | Require **computed** and **declared** reconcile delta **0.00** | `test_reviewer_probe_cash_delta_tamper` |
| Weak qty/float validation | Whole-share positive int only; full trade schema | `test_fractional_qty_rejected`, `test_hand_valid_trade_identity` |
| Registration/manifest drift | Cross-check run ID, rules hash, manifest summary, dev lineage, validation eval hash | loader `development_lineage` / `validation_split` |
| Page double-load snapshot | Single `build_results_review_view` snapshot in `dashboard.py` | `test_fail_closed_view_invalid_book_stress_hidden` |

**Code:** `nifty_lab/research/results_review/trade_arithmetic.py`, hardened `loader.py`, `dashboard.py`, `ui_data.py`.

**No new** `research/review_runs/` artifact in this slice. Existing `ee63ea6a-53e8-4b22-aa8a-edd5d4c68a76/` and backtest sources/inventory **byte-unchanged** (`test_approved_sources_and_inventory_unchanged_on_load`).

## Delivered (original + integrity)

| Component | Path |
|---|---|
| Strict trade arithmetic | `nifty_lab/research/results_review/trade_arithmetic.py` |
| Loader / reconcile | `nifty_lab/research/results_review/loader.py` |
| Fixed-fill diagnostics | `nifty_lab/research/results_review/diagnostics.py` |
| Review runner | `nifty_lab/research/results_review/runner.py` |
| Dashboard view-model | `nifty_lab/research/results_review/ui_data.py` |
| Dashboard render | `nifty_lab/research/results_review/dashboard.py` |
| CLI | `scripts/run_results_cost_review.py` |
| Page | `pages/07_Backtesting_Lab.py` |
| Tests | `tests/test_spec09_results_cost_review.py` (8), `tests/test_spec09_results_review_integrity.py` (7) |

## Commands

```bash
export NSL_FORBID_LIVE_MUTATIONS=1
TMPDIR=.pytest_tmp .venv/bin/pytest -q tests          # 223 passed
```

(AppTest included in suite — no separate visual/pixel check.)

## AppTest evidence

- `test_streamlit_apptest_valid_page`: `pages/07_Backtesting_Lab.py` — **0 exceptions**, holdout **NOT EVALUATED** warning, metrics present (two books on approved sources).
- Invalid tampered validation: fail-closed view — development cost table remains, validation stress **absent** (`test_fail_closed_view_invalid_book_stress_hidden`, `test_reviewer_probe_exit_fill_tamper`).

## Source runs (read-only, unchanged)

| Book | run_id | Net P&L | Trades | Reconcile |
|---|---|---:|---:|---|
| Development 2021–2023 | `22f4e81b-e66a-4ea1-b77d-325323f61db7` | -869.13 | 16 | 0.00 |
| Validation 2024 | `d1d9016b-3fc0-4dbf-944e-f4dde5353cd2` | +24.30 | 14 | 0.00 |

Rules hash: `d5781d90f3276de37320059a14529c944580fc671c351cbbc04bed90bb191101`  
Evaluation hash (validation): `a5e169f0f061eb9d08ce9eacca4c3d0220da0b91a2bb39c2f97abcf66f5b7f58`

Review artifact (unchanged): `research/review_runs/ee63ea6a-53e8-4b22-aa8a-edd5d4c68a76/`

### Validation fixed-fill (still exact after strict loader)

| Scenario | Extra cost | Diagnostic net |
|---|---:|---:|
| EXTRA_1BP | 43.00 | -18.70 |
| EXTRA_INR1_PER_EXECUTION | 28.00 | -3.70 |

## Analyst conclusion (unchanged)

**INSUFFICIENT_EVIDENCE / COST_FRAGILE_VALIDATION** — development negative; validation near break-even under illustrative costs.

## Boundaries

No strategy/rule changes, backtest/validation rerun, new review artifact, 2025 outcomes, network/credentials, Spec08/ledger edits, commits. **NSL_FORBID_LIVE_MUTATIONS=1** preserved.

**Next slice (not authorized here):** paper-account results/mark visibility after analyst sign-off on this loader.

**Stop here.**
