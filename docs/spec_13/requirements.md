# Spec 13 — Requirements

## R0 Production fixes (Spec 13 completion)

- Entry fill fees = confirmed `entry_cost_inr` (proportional partial fills).
- Entry slippage explicit in preview/confirm/submit; bid/ask not bound to limit.

## R1 Independent oracle

Temporary ₹20k account; checkpoint cash, position, fees, realized, reservations per primary oracle table in handoff.

## R2 APIs only (no gate bypass)

Preview/confirm on entry and close; cancel via `cancel_paper_remainder`; no direct orphan fills except post-confirm buy execution documented in handoff.

## R3 Reader

`load_paper_account_view` reconciles at each checkpoint; readonly verified; never touches real Paper DB.

## R4 HTTP discipline

Explicit fetch only; zero on load/preview/confirm/cancel/reader.

## R5 Safeguards

Replay intent, consumed observation, nonmarketable limit, stale confirm, source invalidation (Spec 12 tests referenced + journey guards).

## R6 Cross-mode

No Live/Sandbox adapter invocations in acceptance module.
