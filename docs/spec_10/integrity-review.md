# Spec 10 review — Paper ledger reconciliation corrections

Status: CORRECTIONS REQUIRED; no new feature or trading promotion. Repository `/Users/sanjain/Documents/hedge_trader/`.

## Independent evidence

Full suite232 passed. Reader uses mode=ro/query_only and data SELECTs in a transaction; partial-close numeric oracle matches. However, existing nine tests do not prove required invalid-ledger cases. Four offline temp-DB probes using the existing `_build_oracle_db` fixture ALL incorrectly returned status OK:

1. `UPDATE fills SET qty=1 WHERE fill_event_id='buy-1-fill'`: position still6 although recorded buys1 minus sells4 imply -3. No fill/cash/unit reconciliation.
2. `UPDATE fills SET local_order_id='missing' WHERE fill_event_id='buy-1-fill'`: orphan fill order remains accepted.
3. `UPDATE orders SET reserved_cash='NaN' WHERE local_id='buy-1'`: invalid reserve becomes0.00.
4. `UPDATE orders SET status='OPEN', quantity=100, filled_qty=4 WHERE side='SELL'`: owned6, pending sell96, still OK.

All probes used disposable databases; real Paper account not modified by reviewer.

## Findings / requirements

### F1 — Fill/order/cash/position/event identities are not reconciled (high)

`nifty_lab/paper_account/accounting.py:build_paper_account_view` currently sums independently stored facts and checks aggregate P&L identity. It does not link fills to orders, verify signed fill quantities/notionals against cash/positions, or ensure realized events belong to valid SELL fills. Aggregate equality is insufficient.

MUST validate every fill's parent order, PAPER mode, known side, matching identity/metadata, finite positive price/whole units and nonnegative fees. Fill_event_id uniqueness and realized event uniqueness/orphan checks must reject missing/wrong-side references. Require per-order sum(fill.qty)==filled_qty, filled_qty<=quantity, statuses/reservations consistent. Check cash movements from recognized initial funding and executed buy/sell notionals plus fees against cash_ledger, without double fee subtraction. Verify recognized initial_allocation event and funded metadata; unknown flows cannot be called trading profit.

Reconcile each current position quantity to signed fills, remaining entry fees/cost basis to average-cost accounting, and realized gross/net to actual SELL fills and proportional entry-fee allocation. Implement read-side derivation or independent arithmetic validation; do not call ExecutionLedger mutators, migrations or portfolio_context. Handle ties/legacy/incomplete provenance honestly as RECONCILIATION UNAVAILABLE rather than guessing sequence, contract metadata or a false OK. Recognized valid stock/ETF/NIFTY bought-option units must follow stored kind/lot semantics; no new instrument support or relabeling.

### F2 — Invalid/missing reserves are coerced to zero; over-reservation accepted (high)

`accounting.py` uses `_d(...) or Decimal('0')` and `_int_qty(...) or 0` in order handling. MUST distinguish a valid numeric zero from parse failure/missing/nonfinite/negative values. Validate required order quantity, filled_qty, status, side, residual reserves and mode before aggregation. Reject unknown statuses and overfills; active SELL reserved remainder per instrument must not exceed owned units. Unit-only SELL reservation must not create cash reserve or count proceeds as cash. Terminal reserves zero. Cash availability belowzero must be flagged, not silently clamped. Do not suppress reconciliation just because both invalid fee totals are negative; reject negative/nonfinite fee fields at their source.

### F3 — Reader schema/read-only claims need narrow hardening (medium)

`nifty_lab/paper_account/reader.py` checks required tables but not columns; missing legacy columns can silently default fees/reserves in accounting. Inspect required columns before materializing view; UNSUPPORTED_SCHEMA for missing required accounting metadata. Preserve optional legacy provenance as unknown only where explicitly safe. Use correctly encoded `Path.as_uri()` or equivalent SQLite URI so paths containing '?'/'#' remain literal paths. A read-only connection failure must never fall back to writeable.

Production `verify_connection_readonly` attempts CREATE TABLE and interprets any sqlite error as read-only proof. Replace production mutation probing with connection configuration verification and read-only construction invariants; retain deliberate blocked-write attempts in fixture tests only. If read_only_verified is false, do not return trusted OK. Keep connection/schema/data observation in one consistent read transaction; no migration/init/funding/peak/mark updates. Handle connection/read/schema errors with sanitized statuses; no raw SQL/database bodies.

### F4 — Suppress unreliable derived values and complete promised visibility

On reconciliation failure/unavailable, view-model MUST set affected equity/P&L/available-cash/realized derived totals unavailable rather than merely attaching a failure status to normal figures. UI must show facts only when independently validated; don't show a partial cash metric after a nonfinite cash row breaks summation. Local Paper banner/provenance/no-live constraints remain.

Original Spec10 also requested gross/net realized, SELL owned/reserved/sellable, recent paper orders/fills and unknown contract metadata visibility. Render those from the SAME validated snapshot with clear monetary/quantity labels. No trade/cancel/close/mark actions and no arbitrary database paths on the page. Per-position mark timestamp/age is not evidence of current broker pricing. Preserve current missing mark behavior and the exact numeric oracle. Flat valid accounts have explicit unrealized0; missing valuation is distinct from zero.

## Required regressions (temporary fixtures, sockets blocked)

- All four reviewer mutations above fail closed with specific stable error classes; no success equity/P&L/cost figures for affected data.
- Positive flat, partial close and full liquidation; repeated valid fill events don't duplicate results; orphan/duplicate/wrong-side realized events and missing parent order rejected.
- Real signed fills/cash/units/fees accounting; changing fill price or quantity while leaving cash/positions unchanged rejected even if aggregate P&L identity is unchanged.
- Pending BUY partial/cancel residual cash+risk; pending SELL reservations, two competing sells, over-reserved units, invalid scalar/negative reserve/fee, unknown status and schema column omission.
- Unrecognized funding/cash event -> unavailable, not fabricated trading return; legacy missing metadata and unknown mark remain explicitly unknown.
- URI paths with reserved characters read exact existing file; missing file not created; fixture blocked-write test; read view never calls init/migrate/peak or network.
- AppTest valid/missing/inconsistent fixtures: status and field suppression, unchanged source DB data/meta, no exception. Snapshot concurrency/WAL consistency verified with fixture connection; no unsafe immutable mode.
- Existing oracle mark100:cash19437,realizedgross40/net38.20,remainingentryfees1.20,equity20037,totalP&L37; mark105 equity20067/P&L67 preserved. Full existing Spec08/09 suites pass.

## Task / boundaries / handoff

Implement ONLY these Spec10 read-side accounting/reader/UI corrections. Do NOT alter execution gate, fills, close/cancel behavior, actual database/schema, marks, funding, archived research, strategies,2025, credentials or network. Real DB source preserved; tests may create/modify temporary fixtures. NSL_FORBID_LIVE_MUTATIONS=1 unchanged. No commits/merges.

Update `docs/spec_10/handoff.md` and tasks/status with each finding->implementation->test evidence, actual test counts/commands, read-only guarantees and remaining limitations. Stop for review. No mark-update/new pricing/execution slice until this acceptance review passes.
