## ADDED Requirements

### Requirement: Paper and Live for cash equities and NIFTY long options
The application SHALL implement Paper and user-confirmed Live workflows for cash stock/ETF buys and NIFTY CE/PE buys, with reconciled sell-to-close. Sandbox SHALL be an isolated optional broker-test mode.

#### Scenario: Same ticket, separate modes
- **GIVEN** a valid stock or exact NIFTY long-option ticket
- **WHEN** Paper or Live is selected
- **THEN** the relevant real adapter/engine is used, funds/results remain mode-separated and switching modes invalidates previews without submitting.

#### Scenario: Minimum NIFTY lot does not fit
- **GIVEN** current contract lot metadata and cost-inclusive premium-at-risk above ₹400 for one lot
- **WHEN** the candidate is previewed
- **THEN** no size fits policy is shown, with no fractional lots, increased budget, automatic alternative strike or order.

### Requirement: Validated risk and available funding
New entries SHALL satisfy execution-v1 policy with ₹20k allocation, ₹400 per-position budget and ₹2k stop-new-risk loss/drawdown threshold, using fresh validated context and product-specific risk semantics.

#### Scenario: Invalid or understated candidate
- **GIVEN** NaN/inf, missing marks/funds, wrong profile or a caller-understated candidate loss
- **WHEN** entry evaluation runs
- **THEN** it cannot pass, all blockers are disclosed and calculated risk cannot be reduced by untrusted context.

#### Scenario: Stock planned loss versus full downside
- **GIVEN** stock entry, stop reference, units and sourced costs
- **WHEN** preview shows the ₹400 planned-risk test
- **THEN** full/gap downside and whether a broker stop exists are displayed separately, with no guaranteed maximum-loss claim.

#### Scenario: Concurrent orders and drawdown
- **GIVEN** pending reservations or account drawdown at ₹2k
- **WHEN** another entry is requested
- **THEN** available allocation/risk accounts for pending orders and breaches block new risk, while owned reduce-only exits/cancels remain accessible.

### Requirement: Persistent accounts and realistic paper lifecycle
The execution ledger SHALL reconcile cash/assets/fees/fills/peak across restart and SHALL keep paper/sandbox/live and old journal records distinct.

#### Scenario: Fill, fees and restart
- **GIVEN** a paper buy followed by partial close and fees
- **WHEN** events replay and app restarts
- **THEN** balances/positions/equity reconcile, no fee/fill duplicates occur and legacy paper rows are not real holdings.

#### Scenario: Paper limit and depth
- **GIVEN** a current two-sided quote and limited visible size
- **WHEN** a paper limit is evaluated
- **THEN** only modeled marketable quantity fills within limit, remainder stays reserved, and stale candles do not create fills.

### Requirement: Explicit live confirmation and durable lifecycle
Live order submission SHALL follow a fresh exact preview, single-use user confirmation and server-side duplicate protection, with acknowledgement/fill/unknown outcomes distinguished.

#### Scenario: Changed preview or repeated click
- **GIVEN** a preview whose mode, quote, funding, fees or ticket changes or confirmation repeats
- **WHEN** submit is attempted
- **THEN** changed context requires new review and repeated confirmation cannot generate another order.

#### Scenario: Timeout and partial execution
- **GIVEN** ambiguous submission, broker partial fill or cancelled remainder
- **WHEN** reconciliation runs
- **THEN** no mutation auto-retry occurs, fill IDs book once, reservations remain until resolved and app-owned quantities are not oversold.

### Requirement: Broker readiness and environment isolation
Live readiness SHALL reflect real broker prerequisites; sandbox limitations SHALL never trigger production fallback. Agents SHALL NOT submit live financial orders during implementation verification.

#### Scenario: Missing order readiness
- **GIVEN** a valid data token but missing order permission/static-IP/session/funding evidence
- **WHEN** Live is selected
- **THEN** the implemented workflow explains the concrete blocker and sends no speculative test order; Paper remains available with its own prerequisites.

#### Scenario: Sandbox or research traffic
- **GIVEN** sandbox token or research-page rendering
- **WHEN** the corresponding workflow runs
- **THEN** no production order mutation occurs, no credentials cross hosts/modes and unavailable sandbox APIs never fall back to Live.

#### Scenario: Evidence-based handoff
- **GIVEN** mocked live adapter tests and optional sandbox lifecycle smoke
- **WHEN** implementation completes
- **THEN** handoff separately reports tested Paper, Sandbox and Live capabilities/readiness, with real live placement marked untested by the agent and no performance claims.
