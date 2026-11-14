# Spec 10 — Paper account results (read-only)

Status: AUTHORIZED BOUNDED IMPLEMENTATION; stop for review after evidence. Spec09 integrity review: independent full suite223 passed; known altered-fill and nonzero-cash regressions now reject. Archived strategy still INSUFFICIENT EVIDENCE;2025 holdout remains sealed. No strategy promotion is implied by this product work.

## Why
The user needs to see what the existing local paper account holds, what money is reserved, what has been gained/lost and how trustworthy the prices are. Spec08 already has entry/cancel/close mechanics but no dedicated realized/unrealized results panel. Build that visibility before adding more execution functionality.

## Change
Add one Paper Account results page backed by a consistent SQLite read-only snapshot. Show cash/reservations, open positions and marks, gross/net realized results, remaining entry costs and unrealized results, total paid fees, recent paper orders/fills and accounting reconciliation. Do not add a mark writer, quotes/API refresh, trades, journal saves or execution settings.

## Boundaries
Paper only; not the broker account. No Live/Sandbox ledger access, order mutations, new strategies/backtests,2025 outcomes, account authorization or Live promotion. Keep NSL_FORBID_LIVE_MUTATIONS=1. No credentials/.env inspection, HTTP, dependencies, commits/merges. Preserve all real databases/research artifacts. Tests use temporary fixture databases. Implement only this folder, write handoff and stop.
