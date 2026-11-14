# Spec 08 follow-on — Paper cancel of unfilled remainder

Date: 13 November 2026 IST. Status: IMPLEMENTED IN TREE — see `handoff.md`; not accepted for Live. This is an unfinished Spec 08 slice, not acceptance of Live readiness. Spec 09 remains separate research scope.

## Proposal
The three primary pass-2 review reproductions now block: stale preview, negative fill price and the second same-instrument ₹300-risk entry. The existing full suite passes. Proceed with one bounded user-visible capability: cancel an unfilled Paper order or the remainder of a partially filled Paper order. Preserve actual fills and release only the cancelled remainder's reservations.

Two independently reproduced carry-over invariants belong in this slice:
- Three distinct instrument keys with the same underlying each reserved ₹350, producing ₹1,050 pending risk despite the ₹800 underlying cap. The gate includes pending risk globally but not in underlying concentration. Exact source: /Users/sanjain/Documents/hedge_trader/nifty_lab/execution/gate.py, underlying-cap calculation; /Users/sanjain/Documents/hedge_trader/nifty_lab/execution/ledger/store.py, _portfolio_context_conn.
- Applying the same fill ID/order/quantity/price with fee changed from ₹20 to ₹200 silently returns. Exact source: /Users/sanjain/Documents/hedge_trader/nifty_lab/execution/ledger/store.py, existing-event payload comparison in apply_paper_fill. Fee belongs in immutable event identity comparison, or a separately versioned fee-adjustment event, never a silently ignored conflict.

## Design
Paper-only local cancel API plus a small Paper orders/status panel on the Trade Ticket. Never call broker transports. Cancellation uses a durable order ID, fresh displayed state and explicit user confirmation naming mode, instrument and remaining units. Keep Live and Sandbox controls inactive with honest status. Do not implement owned-position sell/close in this slice.

Use BEGIN IMMEDIATE for cancellation and serialize it with reservation/fill transactions. Re-read current state inside the transaction. Cancel the whole current remainder only; retain original quantity, filled quantity, fills, booked fees/cash and position cost basis. Transition only local PENDING/OPEN/PARTIALLY_FILLED orders to CANCELLED, and release remaining reserved cash/risk. No new fee, cash proceeds, realized P&L or position reduction comes from cancellation itself. Repeated confirmed cancel is idempotent, including after restart. Reject attempts on another mode, unknown order, filled order or unresolved broker/unknown-submission order rather than pretending cancellation occurred.

A fill that wins the transaction race is retained; cancellation then affects only remaining units. A fill attempted after local cancellation must not create exposure, restore status or consume cancelled reservations. Preserve replay of already recorded fills as a harmless no-op even after cancellation. A duplicate ID with differing immutable payload, including fees, must fail. Distinguish accepted historical replay from a new fill against a terminal order. No terminal order may be reopened.

Fix underlying concentration using a consistent transaction snapshot containing open risk plus pending BUY risk for that underlying plus candidate risk. Cancelling unfilled BUY remainder removes exactly its pending contribution. Do not release other orders' allocations. Preserve per-instrument ₹400, total ₹1,200, count 3, ₹20k funds and ₹2k stop-new-risk rules. Cancellation remains available when new-risk limits are breached, but still checks mode/order ownership; missing fresh market quotes must not block local cancellation.

Keep money rounding explicit. Migration must preserve existing execution DBs and legacy paper journal; never reset balances or delete user data. Use temporary databases for tests.

## ADDED Requirements

### Requirement: Truthful local Paper cancellation
The application SHALL cancel only the unfilled remainder of an owned Paper order and persist the terminal result.

#### Scenario: Unfilled cancel and restart
GIVEN a reserved, unfilled Paper BUY
WHEN the user confirms cancel and restarts
THEN status remains CANCELLED, its reservations are zero, balances/positions are unchanged and repeated cancellation does not book another event.

#### Scenario: Partial fill then cancel
GIVEN an order for 10 units with 2 units filled
WHEN cancellation is confirmed
THEN the 2-unit position/fills/fees remain, the 8-unit remainder is cancelled and only its reservations are released.

#### Scenario: Serialized fill/cancel race
GIVEN fill and cancellation attempting the same order
WHEN either transaction wins
THEN no overfill or reopening occurs, real prior local fills are retained and the cancelled remainder cannot fill later; replay of an already recorded fill stays harmless.

### Requirement: Pending concentration and immutable fill events
The existing gate/ledger SHALL preserve complete pending underlying exposure and reject changed immutable replay payloads.

#### Scenario: Three pending same-underlying instruments
GIVEN distinct instruments in one underlying with ₹350 risk each
WHEN the third reservation is attempted
THEN it fails the ₹800 underlying cap with no partial insert; after cancelling one earlier order, a permitted new reservation may pass within all caps.

#### Scenario: Fee-conflicting replay
GIVEN a persisted fill ID with ₹20 fees
WHEN the same ID arrives with ₹200 fees
THEN an explicit conflict is raised and all ledger state remains unchanged; an identical replay after restart stays a no-op.

#### Scenario: Risk breach or unavailable quotes
GIVEN a pending local Paper order and a stop-new-risk breach or stale/missing quote
WHEN cancellation is confirmed
THEN the owned local remainder may be cancelled without requiring a new-entry gate or market fill.

#### Scenario: Mode isolation
GIVEN a Live/Sandbox/UNKNOWN_SUBMISSION or unknown order
WHEN Paper cancellation is requested
THEN no broker request occurs and no unrelated local order/position is changed.

## Tasks
- [ ] Inspect applicable instructions, Spec 08 docs, current code/tests and preserve uncommitted work. Keep live mutations disabled.
- [ ] Fix pending underlying concentration and immutable fee replay comparison with regressions for both exact reproductions.
- [ ] Add transactional Paper remainder cancellation and terminal-fill rules, preserving historical replay.
- [ ] Add Paper order/status/cancel UI with explicit confirmation, fresh status and restart persistence; no broker controls activated.
- [ ] Test unfilled/partial/repeated/restart cancel, filled/unknown/wrong-mode rejection, fill/cancel serialization, no quote dependency and isolated reservation release. Test money/position identities and existing gate/replay regressions.
- [ ] Run focused/full required tests. Report actual collected counts and commands; do not copy old handoff totals.
- [ ] Update docs/spec_08/handoff.md with per-scenario evidence and remaining close/reconcile/broker-context/sandbox/live gaps. Retain CORRECTIONS IN PROGRESS, not accepted for Live. Stop for review, no commits or merges.

## Implementer prompt
Implement only this follow-on slice in /Users/sanjain/Documents/hedge_trader after reading existing docs/spec_08 and applicable instructions. No broker place/modify/cancel/close calls, credential inspection/output, live guard changes, account setting changes, commits or merges. First retain all pass-3 fixes, then address the two carry-over invariants and local Paper cancel flow with the normative tests above. Do not start sell-to-close, Spec 09, Sandbox HTTP or Live wiring. Preserve user data. Complete the handoff with actual evidence and stop.
