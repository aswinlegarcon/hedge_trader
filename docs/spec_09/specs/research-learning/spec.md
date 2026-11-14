# ADDED Requirements

## Requirement: Honest daily plan and review
The system SHALL persist an immutable dated plan and append-only observations/review, with source freshness and no-trade reasons.

### Scenario: Late or incomplete context
GIVEN a plan created after the session starts or stale/unknown macro information
WHEN daily research is rendered
THEN late creation and missing coverage are explicit and no advance-prediction or all-events-checked claim appears.

## Requirement: Reproducible strategy evidence
The system SHALL evaluate a frozen experimental strategy using available-at-the-time inputs, explicit execution assumptions, costs and chronological boundaries.

### Scenario: Future data mutation
GIVEN a signal at session T
WHEN later bars or future metadata change
THEN its inputs and original signal cannot change through look-ahead; revised datasets create a new version/run.

### Scenario: Ambiguous fills and costs
GIVEN a bar touches both stop and target or charges are unknown
WHEN a report is produced
THEN conservative stop-first handling is disclosed and unknown costs prohibit validated/promotable performance claims.

### Scenario: Ranking with little evidence
GIVEN a high historical win rate from a small or tuned sample
WHEN comparing strategies or buckets
THEN counts, uncertainty, net expectancy, drawdown and holdout contamination are visible; no guaranteed return or calibrated win probability is inferred.

## Requirement: Controlled improvement and execution separation
The system SHALL preserve strategy versions, losing runs and unchanged account-risk rules; research SHALL NOT submit orders or auto-promote strategies.

### Scenario: Best experimental result
GIVEN a favorable backtest
WHEN review completes
THEN the system may propose a challenger or further paper evaluation but cannot change active live rules, submit orders or raise capital/risk limits.

### Scenario: Spec 08 remains incomplete
GIVEN unaccepted execution ledger/confirmation behavior
WHEN a research candidate appears
THEN research remains available, execution stays honestly blocked and simulated research results are not represented as verified paper ledger performance.

### Scenario: Index leadership or option result lacks data
GIVEN absent constituent weights or historical option quotes
WHEN interpreting NIFTY/option opportunities
THEN the system shows missing coverage and cannot fabricate weighted attribution or option returns from index candles.
