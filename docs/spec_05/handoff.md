# Spec 05 implementation handoff

Status: **IMPLEMENTED — ready for review.** No commits, merges, orders, or funded-paper activation.

## Summary

- **Watchlist Research** page (`pages/11_Watchlist_Research.py`) — manual sequential refresh for four provisional labels; table + detail card with daily close line and 5m candlestick chart.
- **`nifty_lab/research/`** — deterministic observations (daily trend SMA50/200, 5m EMA9/21, session VWAP, prior-20 relative volume, frozen S/R level notes, data states).
- **Selection identity fix** — changing label, custom symbol, or interval invalidates stale `upstox_dataset`, candidates, and `active_dataset` unless the load matches the current `upstox_selection_id`.

## Files touched

| File | Role |
|---|---|
| `nifty_lab/research/observations.py` | Core fact engine |
| `nifty_lab/research/watchlist_board.py` | Sequential refresh + auth abort |
| `nifty_lab/ui/common.py` | `_clear_upstox_selection_state`, `upstox_selection_identity`, loaded-for guard |
| `pages/11_Watchlist_Research.py` | UI board |
| `app.py` | Navigation entry |
| `scripts/watchlist_one_smoke.py` | Optional one-instrument live smoke |
| `tests/test_spec05_watchlist.py` | Mocked scenarios |

Spec 03/04 behavior preserved (funded-paper blocked, Signal Monitor NIFTY-only voting).

## Scenario → test

| Scenario | Evidence |
|---|---|
| VWAP / rel volume / session | `test_rel_volume_excludes_latest_from_mean`, `test_vwap_zero_volume_unknown` |
| Daily trend | `test_daily_trend_above_both` |
| Frozen level | `test_frozen_level_cross_detection` |
| Changed selection identity | `test_selection_identity_changes` (+ UI logic in `common.py`) |
| Auth abort | `test_auth_abort_remaining_not_fetched` |
| No sentinel leak | `test_no_sentinel_in_diagnostic` |
| Refresh bundle | `WatchlistRefreshService` with `WatchlistRefreshBundle` |

## Verification commands

```bash
cd /Users/sanjain/Documents/hedge_trader
.venv/bin/python -m pytest -q
.venv/bin/python scripts/watchlist_one_smoke.py   # optional live
```

**Pytest:** **81 passed** (74 prior + 7 Spec 05).

**Live (this agent run, separate from Spec 04):**

```
OK symbol=ICICIBANK state=STALE daily=MIXED 5m_close=... summary=...
```

(Token consumed via existing backend only; no credential values captured in handoff.)

## Known limitations (honest)

- No exchange holiday/session calendar — STALE uses a 10-minute heuristic on 5m bar end.
- Global `ACCESS_STATE` from Spec 04 unchanged (connection verified is process-wide).
- Watchlist refresh performs up to **9 calls per instrument** (daily + 5m each with historical/intraday) — may approach transport budget; sequential only.
- Spec 03 financial-gate review items remain **deferred**.

## Next smallest task

Session calendar + explicit market-hours banner for STALE/PRIOR SESSION labels (still read-only, no orders).

---

*Stop for review.*
