# Spec 11 — Upstox broker price overlay (Paper Account)

Status: AUTHORIZED BOUNDED IMPLEMENTATION; stop after evidence.

## Why

Spec 10 values paper positions from **stored ledger marks** only. Users need an optional, explicit broker snapshot for indicative unrealized P&L without mutating the paper ledger or execution paths.

## Change

Add a **Refresh broker prices** control on the Paper Account page. On success, show session-scoped overlay columns (broker price, age, indicative value, unrealized) beside existing stored-mark valuation. One batched GET to Upstox full market quote per click; no fetch on load.

## Boundaries

Paper read path unchanged. No DB/mark/cash/peak writes. No orders, gate/fill changes, master download on this page, polling, or Live promotion. Mocked HTTP in tests; no live smoke in CI. **NSL_FORBID_LIVE_MUTATIONS=1**. No commits in agent slice.
