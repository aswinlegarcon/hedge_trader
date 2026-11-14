# Spec 10 — Finish per-fill fee and cost-basis reconciliation

Status: BOUNDED CORRECTION REQUIRED. Earlier F1 fill/order/quantity and F2 reserve fixes verified; full suite239 passed independently. Do not add marks/pricing/execution features yet.

## Evidence and scope

The updated handoff explicitly defers deep per-fill fee allocation. That was required by original Spec10 design and integrity-review F1. Aggregate cash/unit/P&L identities cannot prove realized versus unrealized allocation.

Reviewer reproduced these temporary-fixture mutations, both incorrectly status OK:

1. Oracle after BUY10@100 fee2, SELL4@110 fee1: increase positions.entry_fees_inr by1 and realized_events.net_inr by1. UI reports realized net39.20 and remaining fees2.20 (correct values38.20 and1.20), but totalP&L37 still reconciles. Even total fee conservation passes; the proportional allocation is wrong.
2. Increase remaining avg_price by1 and realized_events.gross_inr/net_inr by6. UI reports realized net44.20 and unrealized-after-fees-7.20 (correct38.20/-1.20); totalP&L37 still reconciles.

Root: `/Users/sanjain/Documents/hedge_trader/nifty_lab/paper_account/reconcile.py` validates references then sums realized_events and uses stored positions basis/fees without independently deriving their amounts from chronological fills. No production data modified by reviewer.

## Requirements

### Per-instrument read-side average-cost derivation

Derive independently from validated Paper fills joined to orders in a reliable chronological execution order. Track owned units, average fill-price cost basis, remaining paid entry fees and expected realized gross/net per SELL fill. BUY adds units/notional/fees; SELL uses pre-sale average basis and allocates entry fees proportionally q_sold/q_owned, with full-close remainder handling matching the documented ledger convention. Verify each persisted realized event against its own SELL fill, not only aggregate sums. Verify open position avg_price/cost basis and remaining entry_fees against derived amounts; validate final owned units as before. Interleaved instruments independent; partial buys, partial closes, full liquidation and reopening correctly reset state. No FIFO substitution, inferred contract relabeling or self-validation using stored average/realized values as the derivation oracle.

Use finite Decimal read-side arithmetic with explicit rounding/tolerance compatible with persisted float ledger, max documented INR0.01 reconciliation tolerance. Compare monetary cost basis rather than rounding average price prematurely; preserve actual delta evidence. Do not increase tolerance until probes pass. No writes or execution-accounting refactor in this slice.

Reliable sequencing requires actual execution timestamp/identity columns: inspect schema and validate them. Do not order tied conflicting BUY/SELL events by random UUID or database SELECT order. If exact economic history cannot be established (missing legacy fields, inconsistent identities, ambiguous dependent fills at same timestamp), return RECONCILIATION UNAVAILABLE with derived metrics suppressed, not guessed OK. Clearly distinguish unavailable evidence from detected arithmetic mismatch. Unique fill_event_id remains replay identity, not chronological order.

### Tests and error behavior

- Both offsetting reviewer mutations fail closed, no cash/equity/realized/unrealized success figures.
- Pure independent hand-calculated oracle still38.20 realized net/1.20 fees remaining; mark100 equity20037/P&L37; mark105 equity20067/P&L67.
- Two buys at different prices and fees -> weighted average, then two partial closes, final close and reopen -> exact independent expected per-fill realized amounts/remaining fees. Test unequal buy quantities/fees, not just equal lots.
- Alter only one persisted realized gross/net or basis/remaining fee -> rejected even with compensating changes keeping totals consistent.
- Event identity wrong/missing/duplicate, conflicting temporal order and insufficient legacy provenance -> unavailable/failed, stable sanitized codes and suppressed metrics.
- Previous four reviewer probes, pending/cancel/reserve behavior, missing marks and mode isolation stay tested. No derive-by-instantiating ExecutionLedger or calling portfolio_context.

### Read snapshot consistency

Small carry-over: reader.py still inspects table/column schema before BEGIN although handoff claims schema+data share a transaction. Put schema inspection and data SELECTs inside the same read transaction, retaining mode=ro/query_only and no mutation probe. Prove coherent fixture reads across concurrent/WAL write and incompatible schemas; no immutable-mode workaround, migrations or writable fallback.

## Task / boundaries

Implement ONLY this existing Spec10 reconciliation completion and transaction placement, meaningful temp-fixture tests and handoff evidence. Preserve all real Paper DB, archived backtest/review/history/audit artifacts and inventory. No network/credentials, marks, funding, orders, gate/fill changes, strategy/backtests,2025, commits/merges. NSL_FORBID_LIVE_MUTATIONS=1 unchanged. Tests may seed temporary databases only.

Update docs/spec_10/handoff.md and tasks with derivation algorithm/precision, finding->test map, actual commands/counts and remaining unavailable legacy cases. Run full suite and valid/inconsistent AppTest; stop for acceptance review. Do not repeat the earlier completion claim while deferring proportional fee/basis checks. Mark-update workflow is a separate future specification, not this task.
