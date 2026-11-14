# Change: one trade ticket with separate paper and live execution

## Why

The user now wants actual and simulated trades for stocks and NIFTY opportunities. Current code is research-only, with no order adapter, current execution quotes, reconciled portfolio ledger or reliable reusable entry gate. Implement both modes through one preview/risk/order lifecycle instead of continuing unrelated research-only milestones.

## Deliverables

- Trade Ticket page: instrument class, exact stock or NIFTY contract, Paper/Live selector and separate Sandbox test workflow; current quotes, size, LIMIT price, stock planned stop reference, costs/funding/risk preview.
- Local paper engine with durable cash/positions/order/fill/fee ledger; fake fills are explicitly simulated. Use Upstox sandbox additionally for supported broker API testing.
- Actual Upstox live adapter behind explicit user confirmation and validated fresh risk/funding/context. Implement real submission and status reconciliation, not stubs or global permanent disable.
- Mode-separated journals/results and account reconciliations, partial fills, cancels, unknown submissions, restart recovery, close-position ticket and a stop-new-orders control.
- Replace old blanket 'no order code anywhere' copy with truthful mode/readiness labels; preserve historical briefs as historical.

## Bounded first execution scope

Buy cash stocks/ETFs or buy one selected NIFTY call/put contract (integer lots, current contract metadata). Sell only to close owned/unreserved quantity. Initial LIMIT/DAY workflow, no MTF/leverage/market orders/AMO/slicing/GTT, no automatic signals submitting orders. Broker may infer AMO, so enforce current-session readiness before submission rather than trusting is_amo=False alone.

Optional sandbox tests use distinct host/token and supported API contracts only. No live-money smoke test in implementation. Both production Paper and Live features can be delivered while a particular account's Live readiness is BLOCKED by missing broker setup; report the exact distinction.

## Excluded from this spec

Automated strategy selection/execution, copy trading, transfers/payments, static-IP registration, order-all/exit-all operations, naked selling, futures, multi-leg spread execution, predictive accuracy claims and unrelated calendar/news refactors. No commits/merges.
