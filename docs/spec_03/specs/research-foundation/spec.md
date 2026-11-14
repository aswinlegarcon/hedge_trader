## ADDED Requirements

### Requirement: Revised research profile
The application SHALL use ₹20,000 initial capital and a fixed ₹2,000 total loss/drawdown ceiling for the active revised profile. It SHALL NOT impose minimum position risk or infer unconfirmed position limits from historical assistant prose.

#### Scenario: New account defaults
- **GIVEN** no explicit revised-profile configuration
- **WHEN** the app loads its research profile
- **THEN** capital is ₹20,000, total ceiling is ₹2,000, minimum risk is absent, and unconfirmed per-position policy is visibly unset.

#### Scenario: Legacy environment conflicts
- **GIVEN** legacy NSL overrides describe a ₹100,000 account
- **WHEN** the revised profile loads
- **THEN** it reports configuration conflict without echoing raw values, does not change the file, and cannot qualify funded-paper entries under the legacy policy.

### Requirement: Upstox is the sole active broker
The application SHALL register only an offline Upstox adapter and SHALL remove active Kite/Kotak modules, exports, credential checks and onboarding. Historical documents and fee-source citations SHALL remain identifiable as historical evidence.

#### Scenario: Offline connection status
- **GIVEN** no token, a placeholder token, or a fake populated token
- **WHEN** Settings is opened
- **THEN** Upstox reports absent or configured-not-connected truthfully, never CONNECTED, and performs zero network calls.

#### Scenario: Legacy credentials remain private
- **GIVEN** a user environment contains old broker credentials
- **WHEN** the new setup flow renders
- **THEN** it neither reads those values for broker status nor displays them, and does not edit or delete the user's environment file.

### Requirement: Explicit fail-closed eligibility
The shared eligibility gate SHALL consume explicit validated portfolio context, with no default-zero drawdown or mark fallback. It SHALL return all blocking reasons and one of ELIGIBLE, REJECTED or INSUFFICIENT DATA using the precedence in design.md.

#### Scenario: Portfolio drawdown boundary
- **GIVEN** C0=₹20,000, H=₹20,000 and E=₹18,000 with otherwise valid explicit fixture inputs
- **WHEN** a candidate is evaluated through the analyzer and save path
- **THEN** new funded-paper entry is REJECTED and cannot be recorded as qualified.

#### Scenario: Peak drawdown after gains
- **GIVEN** H=₹21,000 and E=₹19,000
- **WHEN** a candidate is evaluated
- **THEN** ₹2,000 peak drawdown blocks entry even though initial-capital loss is only ₹1,000.

#### Scenario: Missing or invalid inputs
- **GIVEN** an unconfirmed per-position ceiling, missing mark/peak, unknown required margin/cost, nonfinite amount, stale valuation, unsupported cash flow or unreconciled legacy position
- **WHEN** any funded-paper qualification path evaluates the account
- **THEN** it cannot return ELIGIBLE and explains the missing/invalid evidence; absent an independent known breach it returns INSUFFICIENT DATA.

#### Scenario: Portfolio constraints and downside arithmetic
- **GIVEN** explicit independent fixtures for R=₹1,000 with P=−₹600 or +₹200
- **WHEN** remaining risk is computed
- **THEN** B is ₹400 or ₹1,200 respectively, and a candidate breaching total downside, count, concentration, aggregate risk or funding is REJECTED by the same gate.

#### Scenario: Below historical minimum
- **GIVEN** a fully valid test-only confirmed policy and a small candidate within all upper limits
- **WHEN** eligibility is evaluated
- **THEN** no minimum-risk rejection or encouragement to increase size is emitted.

#### Scenario: Recheck on recording
- **GIVEN** a candidate passed using valid fixture context but the context becomes stale or loses required funding evidence
- **WHEN** funded-paper recording is requested
- **THEN** the shared gate is rerun and no qualified journal entry is inserted.

### Requirement: Preserve research and paper history
The application SHALL preserve existing sample/CSV calculators, educational option payoffs and existing journal records, keeping unqualified/manual education separate from funded-paper eligibility.

#### Scenario: Educational payoff without current funding
- **GIVEN** theoretical quotes and no reconciled portfolio valuation
- **WHEN** the user calculates a payoff
- **THEN** the educational result remains available, current-market qualification is unavailable, and the UI does not present legacy options costs as verified Upstox equity costs.

#### Scenario: Existing journal
- **GIVEN** legacy paper entries in a temporary database fixture
- **WHEN** history is viewed and an open legacy entry is closed
- **THEN** historical amounts remain intact and records are neither silently requalified nor excluded to make new eligibility pass. The user's real database is untouched.

### Requirement: No execution, credential leakage or validation claims
This change SHALL add no network requests or order operations and SHALL NOT claim predictive accuracy, verified account connectivity or backtesting success.

#### Scenario: Secret sentinel and unexpected transport
- **GIVEN** fake secret sentinels and transport configured to fail any network attempt
- **WHEN** status, configuration errors, research pages and eligibility tests run
- **THEN** no sentinel is present in captured logs/UI/errors/artifacts, no order/auth/data endpoint is called, and live execution remains unavailable.

#### Scenario: Honest completion evidence
- **GIVEN** an implementation with failing, skipped or unavailable checks
- **WHEN** the in-house agent writes the handoff
- **THEN** it reports actual outcomes and remaining gaps rather than marking unsupported requirements complete.
