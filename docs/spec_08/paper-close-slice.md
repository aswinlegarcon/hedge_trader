# Spec 08 follow-on — owned Paper sell-to-close

Date: 13 November 2026 IST. Status: **CORRECTIONS IN PROGRESS — stop for review** (not Live-ready). Focused Spec 08: **59**; full suite: **160** (see `handoff.md`).

## Proposal
Complete one usable local Paper round trip: select an existing long holding, preview an exact partial/full SELL, confirm, reserve owned units, simulate valid LIMIT fills, cancel an unfilled close remainder, and inspect realized/unrealized results across restart. No broker HTTP, new feeds, automatic exits, shorts, sandbox/live wiring or Spec 09 work.

## Current gaps to fix within this slice
- preview.py and create_reservation currently evaluate every order as a new entry; SELL needs explicit validated reduce-only semantics carried through preview, confirm and atomic admission.
- store.py currently reserves BUY-style notional cash for every side and changes remaining average price to the SELL price after a partial close. A SELL close must reserve units, not its sale notional, and preserve cost basis of the remaining holding.
- orders/positions do not retain enough immutable kind/product/lot metadata and fee-basis information to support safe selection and accounting. Add non-destructive migration and recover basis from recorded fills where unambiguous; never assume an unknown old holding is a particular option contract/lot size.
- Existing paper engine fee formula (max ₹20 or 25% of estimated entry costs) is a heuristic, not verified brokerage. Replace or explicitly version a reproducible simulated fee model with all assumptions visible. Persist actual modeled fees once per event; do not claim broker-accurate net performance.

## Design

### Scope and identity
PAPER ledger and PAPER orders only. Select holdings from the ledger; derive instrument key, symbol, underlying, instrument kind, product and lot size from trusted persisted Paper metadata rather than editable sell labels. Exact NIFTY long-option closes respect saved lot metadata; no contract selection/expiry/settlement research added here. Legacy holdings with irrecoverable metadata or basis show a concrete reconciliation blocker, with no deletion, zero-cost invention or guessed metadata. Fresh positions created in this release must be fully closeable. A naked SELL is never allowed.

Extend the existing shared gate explicitly for owned close. Basic valid quantity, quote identity/TTL, mode/account/profile and supported contract metadata are mandatory. Effective sellable units = owned quantity minus outstanding SELL remainder. Only an exact long-position reduction may bypass new-entry cash/risk/drawdown limits. Negative account cash, stale unrelated portfolio marks or a ₹2k new-risk breach must not prevent a safe owned close when its own execution quote/ownership are sound. Do not make missing stop reference a blocker for a SELL. Unknown ownership or wrong profile/mode must block.

### Preview, confirm and durable submission
UI shows mode, position, owned/reserved/sellable units, selected quantity, LIMIT, bid/ask/depth, original source timestamp, slippage/fee assumptions and estimated net result. Manual quotes remain clearly manual and unverified; keep reviewed-at separate from source time. Require a fresh selected-instrument quote <=15 seconds, and an exact single-use confirmation <=30 seconds. Changed economic inputs or mode invalidate preview. Preserve one accepted reviewed snapshot across ordinary UI reruns.

Use a stable persisted close intent ID and consume/reserve it in one immediate transaction, linked to the preview and immutable payload. Repeated clicks, two sessions and restart cannot create duplicate close orders from the same intent. Re-read owned/pending quantities in the transaction. Every fill re-checks remaining order quantity and owned units; transaction races must never create a short position. Keep event IDs mandatory and conflicts explicit. Do not rely only on an in-memory consumed flag.

### Local LIMIT lifecycle
SELL fills use bid minus a nonnegative finite slippage assumption, only when modeled price >= limit. Visible bid depth caps fill size; option fills must be whole saved lots, rounding depth down to a lot multiple. Nonmarketable/zero-depth orders stay pending with their units reserved. No simulated price improvement invented by clamping price to limit.

Provide an explicit local 'Re-evaluate Paper remainder' action using a new reviewed fresh quote and durable event ID; it must not create another order or auto-poll/replay quotes into unlimited fills. Persist quote-event consumption so repeating the same observation cannot reuse the same visible depth. If evidence is only daily/5m bars, do not infer executable BBO/depth from candles. Mark simulation assumptions clearly. A new observation can support an additional partial fill; repeated confirmation of the same observation cannot.

An outstanding close reserves its remaining owned units; no entry-style notional cash or extra strategy risk reservation. Keep existing position risk until an actual close fill; reduce stored position risk proportionally after a partial close. Cancelling an outstanding close releases only its remaining unit reservation; it changes no position, fee, cost basis or realized P&L. Existing Paper cancel API must support this without enabling broker cancel. No fills after local cancellation; prior-event replay remains harmless.

### Accounting and marks
Use weighted-average cost basis for this Paper simulation (not tax reporting). For BUY fills, add acquisition notional and entry fee basis to the holding. For SELL fills, allocate proportional remaining acquisition notional and entry fees to closed units; retain the same per-unit acquisition basis on remaining units. Realized gross P&L = sale proceeds minus allocated acquisition notional. Realized net P&L additionally subtracts allocated entry fees and that exit's modeled fees. Do not debit entry fees again from cash at close. Record event-level accounting so full liquidation does not erase historical realized results.

Cash increases by sell notional minus exit fees. Equity = cash + remaining marked asset value; unfilled orders do not create assets, proceeds or realized profit. Display gross unrealized movement and unallocated entry fees separately (or clearly labeled net unrealized). Reconcile equity change to realized net plus unrealized gross minus remaining entry fees, absent deposits/withdrawals. Do not double-count premium, principal, commissions or mark changes as realized income. Persist initial and high-water equity correctly, across restart; stale/missing marks prohibit a trustworthy current-equity claim or new-risk authorization, but not an otherwise valid close. Provide explicit manual-mark updates with timestamps/provenance rather than presenting old fill prices as live marks.

Money calculations need explicit paise rounding with residual allocation to final close so partial allocations sum exactly to total original fee/basis. Keep original fill fees and legacy journal intact. Cancel/status panels should refresh after successful actions instead of leaving apparently active rows on screen.

## ADDED Requirements and scenarios

### Requirement: Owned-only, duplicate-safe Paper exits
The system SHALL admit only confirmed owned/unreserved Paper SELL quantities and persist the submission and unit reservations atomically.

#### Scenario: Competing close requests
GIVEN 10 owned units with 6 already reserved for a close
WHEN a second request tries to sell 5, or two full closes race
THEN overselling is rejected without ledger changes; one intent cannot create two orders, including after restart.

#### Scenario: Breached new-risk limit
GIVEN a valid Paper holding and a reached ₹2k stop-new-risk threshold or unrelated stale marks
WHEN a fresh owned SELL close is confirmed
THEN reduction remains possible while new BUY risk stays blocked; wrong-profile or unknown ownership still blocks.

### Requirement: Realistic partial execution and cancellation
The system SHALL preserve limit/depth/lot bounds and retain all prior cancel/replay invariants.

#### Scenario: Limit, depth and observation replay
GIVEN a SELL limit above modeled bid, or depth below a whole option lot
WHEN Paper close is evaluated
THEN no fill is invented; eligible depth may fill only whole supported units/lots; repeating a consumed quote observation cannot reuse its depth.

#### Scenario: Partial close, re-evaluate, cancel and restart
GIVEN a partial close with an unfilled remainder
WHEN a distinct quote supports another fill or the user cancels and restarts
THEN only actual fills reduce holdings/basis/risk, the remainder retains or releases its unit reservation appropriately, and historical event replay cannot duplicate any result or reopen a cancelled order.

### Requirement: Reconciled net Paper results
The system SHALL retain correct cash, acquisition basis, fee allocation, marks and realized results after partial/full exits.

#### Scenario: Numeric accounting oracle
GIVEN ₹20,000 starting cash, buy 10 units at ₹100 with ₹20 entry fees, and mark remaining units at ₹100
WHEN 4 sell at ₹110 with ₹8 exit fees
THEN cash is ₹19,412, remaining acquisition average ₹100, units 6, remaining entry fees ₹12, realized gross ₹40, realized net ₹24, and equity ₹20,012. Gross unrealized is zero, and equity change ₹12 equals realized net ₹24 minus remaining entry fees ₹12.
WHEN the final 6 sell at ₹90 with ₹12 exit fees
THEN cash/equity is ₹19,940, no holding remains, cumulative realized net is -₹60 and all fees total ₹40. Restart and event replay preserve these exact results. This is a deterministic test fixture, not a forecast or actual fee schedule.

#### Scenario: Averaging, penny rounding and invalid writes
GIVEN multiple acquisition fills and partial closes with fractional-paise allocation
WHEN accounting runs
THEN weighted basis and residual fees reconcile to the paise at full close; invalid prices/fees/quantities, overfills and conflicting event IDs roll back entirely.

### Requirement: Mode and UI honesty
The UI SHALL expose only simulated Paper closing and disclose quotes/costs/valuation limitations.

#### Scenario: End-to-end Paper ticket
GIVEN a fresh fully described Paper position
WHEN the user selects close, previews, confirms, partially fills and cancels the remainder
THEN statuses, sellable quantities, holdings and results visibly refresh, including across reruns; no broker transport runs. Live/Sandbox selection cannot act on Paper holdings.

## Tasks
- [x] Read applicable instructions/current Spec 08 work and preserve all uncommitted/user data; keep live mutation guard enabled.
- [x] Add safe additive metadata/accounting migration and frozen owned-position identity; reject unresolved legacy basis rather than invent values.
- [x] Carry reduce-only intent through shared preview/confirm/transactional admission; persist single-use intent, unit reservations and event/quote consumption.
- [x] Implement local Paper close/re-evaluate/partial-fill behavior and connect existing remainder cancellation.
- [x] Correct weighted cost basis, entry-fee allocations, realized P&L, risk reductions, marks and equity reconciliation without rewriting legacy journal into execution holdings.
- [x] Add positions/close/results UI with exact confirmation and fresh statuses; manual input/simulation assumptions explicit.
- [x] Test each scenario above with temp stores/fake quotes, including stock, ETF and NIFTY whole-lot positions, competition/restart/replay, accounting oracle, zero depth, source TTL and UI reruns. No real HTTP needed.
- [x] Run focused/full required tests and report actual collected totals. Update docs/spec_08/handoff.md with evidence and honest gaps. Stop for review, no commits or merges.

## Implementer prompt
Implement only docs/spec_08/paper-close-slice.md in /Users/sanjain/Documents/hedge_trader. No broker place/modify/cancel/close calls, credential inspection/output, account setup changes, live guard changes, Sandbox/Live wiring, Spec 09 implementation, new market feeds, shorts or automated exits. Preserve accepted Paper cancel behavior and all prior gate/replay fixes. Deliver a functional owned Paper close lifecycle and exact accounting, not stubs. Use fake data/temp databases and UI tests that do not access user secrets or live ledger files. Update handoff and stop; overall Spec 08 remains incomplete/not Live-ready.
