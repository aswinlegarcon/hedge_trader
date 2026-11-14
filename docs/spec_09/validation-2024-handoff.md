# Spec 09 — Frozen 2024 validation handoff

Status: **COMPLETE (bounded slice).** One offline validation replay recorded; **STOP** — no 2025/holdout release, no paper/live promotion.

## Scope delivered

| Area | Change |
|---|---|
| Split engine | `splits.py` — `simulate_split()` for development vs `validation-2024` (causal 2021–2023 indicators, independent ₹20k, 2024-only trades/equity, `SPLIT_END` / `NO_NEXT_SESSION`, no 2023 pending carry) |
| Evaluation hash | `evaluation_config.py` — separate from frozen rules hash |
| Preflight | Stricter manifest required, full `dataset_config` identity, typed `row_count`, checkpoint counter checks, validation context/eval/holdout integrity hashes |
| Accounting | Reporting-only candidate/opportunity fixes (trading unchanged); development trade/equity parity preserved |
| CLI | `scripts/run_development_backtest.py --split validation-2024` |
| Tests | `tests/test_spec09_validation_2024.py` (+ updated prefix-invariance in development tests) |

Frozen corrected rules hash (unchanged): `d5781d90f3276de37320059a14529c944580fc671c351cbbc04bed90bb191101`

Evaluation config hash: `a5e169f0f061eb9d08ce9eacca4c3d0220da0b91a2bb39c2f97abcf66f5b7f58`

Engine source digest (post-refactor): `76e338fda38c916453fac169865047425d0f925e7baec0dcffb4e98c8f3964aa`

## Verification commands

```bash
export NSL_FORBID_LIVE_MUTATIONS=1
TMPDIR=.pytest_tmp .venv/bin/pytest -q tests    # 208 passed (this slice)
NSL_FORBID_LIVE_MUTATIONS=1 .venv/bin/python scripts/run_development_backtest.py --split validation-2024
```

Parity (no new development run): `test_development_parity_saved_corrected_run` matches preserved run `22f4e81b-e66a-4ea1-b77d-325323f61db7` — 16 trades, full `equity_daily.json` and `trades.json` byte-identical to simulation output.

Reviewer fixtures (exact): 115-share stop net **-399.85**; gap open **100** net **-2350.60** + risk latch; malformed manifest/meta/counter paths → stable `BLOCKED` classes; tampered 2024/2025 tail leaves development decisions invariant; tampered 2025 integrity-only leaves validation trades invariant.

**Reporting note:** Descriptive opportunity/skip counts on a *new* development rerun would differ from saved `22f4e81b…` summary (`skipped_exit_session` etc.) because accounting was corrected without changing fills. Economics and parity artifacts remain the acceptance gate.

## Registered validation run

| Field | Value |
|---|---|
| run_id | `d1d9016b-3fc0-4dbf-944e-f4dde5353cd2` |
| purpose | `FROZEN_2024_VALIDATION` |
| parent_run_id | `22f4e81b-e66a-4ea1-b77d-325323f61db7` |
| rules_config_hash | `d5781d90f3276de37320059a14529c944580fc671c351cbbc04bed90bb191101` |
| evaluation_config_hash | `a5e169f0f061eb9d08ce9eacca4c3d0220da0b91a2bb39c2f97abcf66f5b7f58` |
| evaluation_bars_hash (2024) | `cabdeb41725090310c7e740742e1bdb3d64d7365be374992a659c808912b343e` |
| evaluation sessions | 249 |
| closed_trades | 14 |
| net_pnl_inr | **24.30** (final cash 20024.30; reconcile 0.00) |
| modeled fees (entry+exit) | ~429.98 |
| max drawdown (net liq peak) | 1092.47 INR (~5.28%) |
| boundary SPLIT_END | 0 |
| readiness | **EXPLORATORY** / **INSUFFICIENT EVIDENCE** |

Artifacts: `research/backtest_runs/d1d9016b-3fc0-4dbf-944e-f4dde5353cd2/` (registration pre-dates outcomes; inventory STARTED → EXPLORATORY_COMPLETE).

Preserved runs **not** modified: `cffbcdd3…`, `22f4e81b…`, history `icicibank-daily-79d0359eb567/`, audit `38e457b0…`.

## Development vs validation (separate panels — do not pool)

| Metric | Development 2021–2023 (`22f4e81b…`) | Validation 2024 (`d1d9016b…`) |
|---|---:|---:|
| Trades | 16 | 14 |
| Net P&L INR | -869.13 | +24.30 |
| Win rate | 37.5% | 42.9% |
| Profit factor | 0.64 | 1.01 |
| Final cash | 19130.87 | 20024.30 |
| Account convention | Continuous dev book | Independent ₹20k; context indicators only |

A slightly positive 2024 ledger **does not** reverse development losses or establish predictive edge (single symbol, small N, illustrative costs, UNVERIFIED calendar).

## Limitations (unchanged)

- Calendar UNVERIFIED; adjustment UNKNOWN.
- Costs illustrative (10 bps/side); not verified broker tariffs.
- 2025 holdout not used for outcomes; hash recorded only.
- No optimization, retuning, or second validation pass in this slice.

## Proposed next smallest task

Analyst review of validation run `d1d9016b…` vs development parent; if authorized later, a **separate** holdout slice (2025) with new registration — not in this chat.

**Stop here.**
