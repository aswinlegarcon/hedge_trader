# Spec 09 — ICICIBANK historical data audit (sanitized)

- **Run ID:** `38e457b0-5004-4731-bb68-f79118621d2a`
- **Fetched at (UTC):** 2026-11-13T09:21:30.887847+00:00
- **Overall status:** `FEASIBLE_SAMPLE`
- **Instrument:** ICICIBANK (NSE_EQ|INE090A01021)

## Request budget
- Historical attempts: 3 / 3
- Master attempts: 1 / 1

## Predeclared research boundaries
- 2021–2023: development (sample windows only; continuity unverified)
- 2024: validation split — **not fetched** in this audit
- 2025: holdout — December 2025 sample only; no strategy outcomes

## Per-window results
### 2021-01-01_2021-01-31
- Status: `FEASIBLE_SAMPLE`
- HTTP: 200
- Normalized rows: 20
- Data hash: `b693249b5207c2de…`
- Calendar: UNVERIFIED; Adjustment: UNKNOWN

### 2023-01-01_2023-01-31
- Status: `FEASIBLE_SAMPLE`
- HTTP: 200
- Normalized rows: 21
- Data hash: `0f07c85eac05893c…`
- Calendar: UNVERIFIED; Adjustment: UNKNOWN

### 2025-12-01_2025-12-31
- Status: `FEASIBLE_SAMPLE`
- HTTP: 200
- Normalized rows: 22
- Data hash: `61182b0c1580e3b4…`
- Calendar: UNVERIFIED; Adjustment: UNKNOWN

## Limitations

- Three separated monthly samples do not verify continuous 2021–2025 coverage.
- NSE session calendar not sourced in-repo; weekday gaps are candidate missing sessions, not confirmed.
- Corporate-action / adjusted-price status is UNKNOWN; smooth series are not evidence of adjustment.
- Single-symbol ICICIBANK sample is not a survivorship-free universe.
- No strategy signals, outcomes or parameter search were run.
- November 2026 is excluded from historical samples.

## Proposed next step

If acceptable: design resumable bounded full-daily-history acquisition for 2021–2025 with calendar/adjustment review before any backtest engine work.
