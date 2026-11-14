# ICICIBANK full daily history (Spec 09 slice)

- dataset_id: `icicibank-daily-79d0359eb567`
- invocation_id: `c4eb5407-0431-4876-bdfe-ac0025bbca65`
- acquisition: **COMPLETE**
- quality: **LIMITED**
- calendar: **UNVERIFIED**
- adjustment: **UNKNOWN**
- backtest eligibility: **EXPLORATORY_ONLY**
- merged hash: `9c1a7e2b6f0d8137597d359ad34a4b58fa4033321040f263b8ea61d769a60b3e`

## Split coverage
- development: data_acquired_for_split
- validation: data_acquired_for_split
- holdout: data_acquired_for_split

## Chunks
- 2021: COMPLETED rows=248 gaps_listed=13
- 2022: COMPLETED rows=248 gaps_listed=12
- 2023: COMPLETED rows=246 gaps_listed=15
- 2024: COMPLETED rows=249 gaps_listed=16
- 2025: COMPLETED rows=249 gaps_listed=13

## Limitations
- NSE session calendar not sourced in-repo; weekday gap lists are candidate missing sessions only.
- Corporate-action and price-adjustment status remains UNKNOWN without authoritative evidence.
- Single-symbol ICICIBANK study; not a survivorship-free universe.
- No strategy signals, outcomes, optimization or broker mutations in this slice.
- Candidate jump flags are investigate-only; not split/corporate-action proof.

## Proposed next step
Optional: authoritative calendar/adjustment review before a separately scoped fixed experimental cash-equity backtest.
