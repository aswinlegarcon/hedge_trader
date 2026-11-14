# Paper Account Results capability

## ADDED Requirements

### Requirement: Consistent, non-mutating Paper snapshot
The application SHALL read only the existing registered local Paper database through one read transaction, without invoking ledger initialization/migrations/peak updates, execution adapters or network calls. It SHALL report missing/incompatible/unreadable data honestly and never create an account.

#### Scenario: First-time viewer
GIVEN no paper_execution.db exists WHEN the page opens THEN display NOT INITIALIZED and create no file/table/funding.

#### Scenario: Existing account with WAL/concurrent writer
GIVEN an active Paper ledger WHEN results load THEN all displayed fields derive from one consistent SQLite snapshot; no mixed transaction facts or unsafe immutable connection. Prove reader cannot write. Repeated views do not change source DB data or ledger_meta. SQLite WAL/read locks may change ephemeral lock state; do not claim bytes unchanged based solely on lock-file metadata.

### Requirement: Transparent cash and reservations
The page SHALL display cash net of paid fees, pending reserved cash/risk, unreserved cash and pending SELL reserved units independently. Pending and cancelled order accounting SHALL match actual ledger statuses. It SHALL not subtract cash reserves from equity or count reserved SELL proceeds as cash.

#### Scenario: Partial fill then cancel
GIVEN a partially filled BUY with remaining reserves WHEN results are viewed THEN only residual reservation reduces available cash; position/fill fees remain. AFTER a fixture cancel THEN remaining reservation is zero and existing position/fees remain. This page itself cannot cancel.

### Requirement: Realized and unrealized accounting with provenance
The page SHALL derive realized gross/net from recorded events and display each open position's stored mark, time, missing/provenance state, cost, remaining entry fees and unrealized gross/after-paid-entry-fee values. It SHALL never describe stored or missing marks as fresh market quotes, or omit unknown exit costs while calling the result net liquidation.

#### Scenario: Hand-calculated partial close
GIVEN initial funding20000, BUY10@100 with entry fee2, then SELL4@110 with exit fee1, mark100 on remaining6 THEN cash19437, realized gross40, realized net38.20, remaining entry fees1.20, gross unrealized0, unrealized after paid entry fee-1.20, indicative equity20037, total net-after-paid-fees P&L37, total paid fees3. No double fee subtraction. WITH stored mark105 THEN position value630, indicative equity20067, unrealized gross30/net-after-paid-fee28.80, total P&L67. Mark remains indicative, future exit costs excluded.

#### Scenario: Flat account
GIVEN all positions closed THEN remaining entry fees/unrealized0, cash-initial funding equals cumulative realized net (with recognized flows), and realized fees allocate exactly once. Replayed events do not duplicate results.

#### Scenario: Missing/stale marks
GIVEN missing mark on one position THEN portfolio market equity/unrealized/total P&L unavailable, never a zero/average-cost live valuation; cash/realized facts still visible. GIVEN stored marks with old/unknown timestamp THEN show age/provenance and indicative status, never live trust. No writes to repair metadata.

### Requirement: Fail-closed reconciliation and mode isolation
The reader SHALL check finite scalar types, quantities, identities, recognized cash flows, fill/cash/position/event consistency and fee allocations. Inconsistent data SHALL produce visible RECONCILIATION FAILED / UNAVAILABLE, suppressing misleading derived totals; directly valid partial facts may remain identified as such. It SHALL never feed execution authorization.

#### Scenario: Tampered ledger
GIVEN orphan/duplicate realized fill reference, wrong mode, nonfinite value, negative fee/reserve, inconsistent units/cash/fee allocation THEN reject affected derived metrics with stable sanitized error. Do not migrate or mutate the database. Rejected LIVE/SANDBOX records never appear as Paper results.

### Requirement: No promotion or execution
The UI SHALL present Paper status only with no trade/mark/account mutation controls. Existing strategy remains INSUFFICIENT EVIDENCE,2025 NOT EVALUATED, and Live disabled. Viewing this account is operational visibility, not validated strategy performance.
