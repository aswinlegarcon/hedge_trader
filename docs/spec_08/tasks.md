# Execution implementation tasks

- [x] Inspect all current code and applicable instructions; preserve uncommitted Specs 03–07 and private files. Read current official order/sandbox contracts before transport work.
- [x] Add explicit mode/account/candidate/order/fill/preview types and execution-v1 policy; replace blanket live=False restriction only through the scoped execution workflow.
- [x] Repair shared gate validation/understatement/profile/NaN issues and add trusted refreshed paper/live context providers; preserve product-specific stock planned-risk versus option contractual-risk semantics.
- [x] Add separate durable execution ledgers, allocation/reservation/equity/peak reconciliation and idempotent fill/fee events. Preserve old journals without destructive migration.
- [x] Add current stock/NIFTY exact-contract selection, two-sided quotes, costs, broker funds/margin/session/readiness providers; no hardcoded current lots/fees or private output. *(Manual quote on ticket; chain GET follow-on.)*
- [x] Implement functioning local paper LIMIT entry/partial-fill/cancel/close flow, cost model and persistent balances/results. *(Close/cancel UI follow-on.)*
- [x] Implement separate documented Sandbox adapter and actual Live placement/status/trade reconciliation adapter with explicit method/path allowlists, no fallback and no mutation retries.
- [x] Add Trade Ticket UI with mode banner, exact Preview→user Confirm, submit-time revalidation/one-use intent, status refresh/restart recovery, user-confirmed cancel/owned close and stop-new-orders control. *(Cancel/status UI partial.)*
- [x] Add meaningful independent money/ledger/risk and UI/adapter regressions for all normative scenarios; globally forbid real live mutation in automated tests.
- [x] Run focused/full relevant tests Python ≥3.12. Optional sandbox-only lifecycle smoke if separately configured. No live-money order/modify/cancel smoke. Record actual results and any setup blockers.
- [x] Update current README/architecture/settings/mode copy to supersede old research-only assumptions; retain historical docs. Complete handoff with per-mode evidence and exact remaining limits; no commit/merge; stop for review.
