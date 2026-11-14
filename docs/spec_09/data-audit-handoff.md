# Spec 09 — Historical data audit handoff

Date: 13 November 2026 IST. Status: **AUDIT SLICE — review corrections applied; stop for review**. Full Spec 09 engine/backtest **NOT IMPLEMENTED**. Spec 08 unchanged: **CORRECTIONS IN PROGRESS / not Live-ready**.

## Scope

Bounded ICICIBANK daily audit per `docs/spec_09/historical-data-audit.md` — **no new live requests** in this correction pass. Original saved live run preserved at `research/audit_runs/38e457b0-5004-4731-bb68-f79118621d2a/`.

## Review corrections (spec_09_data_audit_review.md)

| Issue | Fix |
|--------|-----|
| Production transport raises escape runner | `fetch_historical_candles_raw` maps `UpstoxAuthError` / rate-limit / unavailable / data errors to sanitized `error_class`; runner always finalizes manifest/report on master failure, abort, or auth stop |
| Intraday rows accepted as daily | Daily policy: **00:00:00 IST** anchor only; one bar per session date; intraday timestamps and same-date conflicts → **LIMITED** |
| Missing NOT_FETCHED inventory | Auth block stops further historical calls; remaining windows `NOT_FETCHED` with `AUTH_STOP` |
| Weekday gaps | `candidate_weekday_gap_count` + `CANDIDATE_WEEKDAY_GAPS` finding; calendar remains **UNVERIFIED** |

Manifest schema: **`spec09_historical_audit_v1.1`** (extra raw audit fields).

## Verification (actual runs — fixture only this pass)

```bash
TMPDIR=.pytest_tmp .venv/bin/pytest -q tests/test_spec09_historical_audit.py
TMPDIR=.pytest_tmp .venv/bin/pytest -q tests
```

| Command | Result |
|---------|--------|
| Spec 09 audit tests | **13 passed** |
| Full `tests/` | **173 passed** |

## Original live run (unchanged)

Run ID: `38e457b0-5004-4731-bb68-f79118621d2a` — `overall_status=FEASIBLE_SAMPLE`, **3/3** historical + **1/1** master.

**Accepted normalized bar counts (re-verified against saved raw): 20 / 21 / 22** — December window **22** (handoff previously understated at 21).

| Window | Rows | Data hash prefix |
|--------|------|------------------|
| 2021-01 | 20 | `b693249b…` |
| 2023-01 | 21 | `0f07c85e…` |
| 2025-12 | 22 | (see saved manifest) |

Calendar **UNVERIFIED**; adjustment **UNKNOWN**. Samples do **not** prove continuous 2021–2025 coverage or strategy viability.

## Scenario evidence (tests)

| Scenario | Test |
|----------|------|
| Raw OHLC / range / same-date | `test_raw_audit_flags_broken_and_out_of_range` |
| Intraday contamination | `test_intraday_same_date_limited_not_feasible` |
| Descending daily input OK | `test_daily_midnight_descending_input_order_feasible` |
| NaT / malformed timestamp | `test_nat_timestamp_rejected` |
| Candidate weekday gaps | `test_weekday_gaps_recorded_without_verification` |
| Hash stability / change | `test_canonical_hash_stable_for_same_data`, `test_canonical_hash_changes_when_values_change` |
| **Raising** UpstoxAuthError → manifest | `test_raising_transport_auth_writes_manifest` |
| Tuple 401 mock auth | `test_auth_blocked_sanitized` |
| Budget / three-window mock | existing tests |

## Research boundaries (declared)

| Period | Role |
|--------|------|
| 2021–2023 | Development samples only |
| 2024 | Validation — not fetched |
| 2025 | Holdout — Dec sample only |

## Limitations (unchanged)

No NSE calendar source in-repo; no adjustment evidence; single symbol; no strategy/backtest; no broker mutations.

## Proposed next step

After review acceptance: design **resumable bounded full daily history** acquisition with calendar/adjustment review — **not** started in this correction.

**Stop for review.**
