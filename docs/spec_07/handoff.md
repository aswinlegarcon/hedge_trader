# Spec 07 implementation handoff

Status: **IMPLEMENTED** (captured Trading Economics macro calendar + honest public refresh). No git commits. Funded-paper qualification remains **blocked**.

## Implementation

| Area | Path |
|------|------|
| Snapshot types / stale heuristic | `nifty_lab/calendar/types.py` |
| Sanitized JSON import (≤5 MB) | `nifty_lab/calendar/import_json.py` |
| HTML adapter (`table#calendar`, nested `<tr>` depth) | `nifty_lab/calendar/html_parse.py` |
| TE-only GET transport (isolated from Upstox) | `nifty_lab/calendar/te_transport.py` |
| Public refresh (202/403/empty → UNAVAILABLE) | `nifty_lab/calendar/public_refresh.py` |
| In-memory filters | `nifty_lab/calendar/filters.py` |
| Streamlit macro section + watchlist panel | `nifty_lab/ui/macro_calendar.py` |
| Page 02 / 11 wiring | `pages/02_Global_News_and_Events.py`, `pages/11_Watchlist_Research.py` |
| Tests (synthetic, offline) | `tests/test_spec07_calendar.py` (7 cases) |
| Import verification script | `scripts/macro_calendar_import_check.py` |
| One-shot public smoke | `scripts/te_calendar_public_smoke.py` |

**Preserved:** Spec 03–06 behavior, company news, manual user-entered events (separate provenance), no orders, no HAR/cookie/Socket.IO replay, no challenge bypass.

## Import evidence (author snapshot)

Command:

```bash
.venv/bin/python scripts/macro_calendar_import_check.py \
  "/Users/sanjain/Documents/Codex/2026-11-13/referenced-chatgpt-conversation-this-is-an/outputs/tradingeconomics_calendar_snapshot.json"
```

Result:

```
OK events=432 origin=HAR_SNAPSHOT captured=2026-11-13T04:53:50.319000+00:00 coverage=2026-11-12..2026-11-23
timezone=UNCONFIRMED — displayed calendar timezon importance=NOT DECODED — CSS event classe
```

Snapshot metadata in JSON also records `live_replay_result: HTTP 202 with empty body` — **not** claimed as working live feed in UI.

## Verification

- **Command:** `.venv/bin/pytest -q tests`
- **Result:** **101 passed** (94 prior + 7 Spec 07), socket blocked in suite
- Scenarios: synthetic HTML field mapping + forecast column, JSON import, HTTP 202 unavailable, HTTP 200 parse success, one GET budget, Upstox host blocks TE URL, stale imminent threshold

## Live public refresh (separate from tests)

Command: `.venv/bin/python scripts/te_calendar_public_smoke.py`

Result (this environment, ordinary GET, no cookies):

```
LIVE: UNAVAILABLE: HTTP 403 access denied or rate limited.
```

Spec/README author observation: **HTTP 202 empty**. Current run saw **403** — both mean **no usable public calendar HTML** without claiming realtime access. UI keeps imported snapshot as captured reference only.

## User workflow

1. **Global News & Events** → **Macro calendar** → upload sanitized JSON → filter by date/country/importance.
2. Optional **Try public calendar refresh** — one credential-free GET; on failure, prior import unchanged with explicit status line.
3. **Watchlist Research** detail card → **Macro context** reuses session snapshot; unconfirmed timezone → “timing unconfirmed”, no countdown.

## Remaining limitations

- Display timezone and CSS importance remain **explicitly unknown** until user confirms IANA zone (optional) or future evidenced mapping.
- Not a complete/corporate calendar; not NSE session hours; not earnings/FOMC schedule ingestion.
- Public endpoint may return 202/403/empty — **do not** treat as production feed.
- Filter “no rows” ≠ “no macro risk”; stale snapshot (>30m) disables imminent-event claims on watchlist panel.
- Spec 03 financial-gate and prior deferred items unchanged.

**Smallest next task (optional):** Re-run public smoke from a residential network once; if 200+rows, document sanitized row count only — still not “realtime certified.”
