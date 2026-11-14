## ADDED Requirements

### Requirement: Manual watchlist comparison
The application SHALL compare up to four resolved NSE equity/ETF research instruments using existing read-only daily and five-minute candle services.

#### Scenario: Refresh and inspect
- **GIVEN** four initial research labels and mocked or authorized real candle access
- **WHEN** Refresh Watchlist is selected
- **THEN** each instrument receives an independently identified result row and selectable detail card, with no import/rerun/background fetch.

#### Scenario: Partial failure
- **GIVEN** one instrument fails to resolve or fetch
- **WHEN** other instruments complete
- **THEN** their observations remain available and the failed row has its own diagnostic; on authentication failure remaining fetches abort as NOT FETCHED.

### Requirement: Descriptive multi-timeframe facts
The research module SHALL compute the documented daily/5m/VWAP/volume/level observations from completed bars, without predictions, position sizing or trade instructions.

#### Scenario: Numeric indicator evidence
- **GIVEN** independently calculated fixture candles
- **WHEN** daily trend, EMA relation, session VWAP and relative volume are evaluated
- **THEN** values match fixtures, latest volume is excluded from the previous-20 mean, session resets work, and zero/short inputs remain unknown or WARM-UP.

#### Scenario: Frozen-level crossing
- **GIVEN** a reference support/resistance set confirmed before the latest completed bar
- **WHEN** that bar closes across a reference level
- **THEN** the observation cites that original level and time, uses no later confirmation and is not labelled BUY/SELL.

### Requirement: Truthful data identity and time
The application SHALL distinguish source, instrument, interval, retrieval time, completed-bar time and stale/partial states.

#### Scenario: Changed selection
- **GIVEN** a previous symbol/interval and stored ambiguity choices
- **WHEN** the user changes the research label, exact symbol or timeframe
- **THEN** the old candidate/dataset is invalidated and cannot appear as the newly selected instrument.

#### Scenario: Missing current context
- **GIVEN** prior-session 5m bars, missing daily data, stale bars or insufficient warm-up
- **WHEN** the board renders
- **THEN** independently available observations are labelled PRIOR SESSION, STALE, PARTIAL DATA or WARM-UP as appropriate, and never presented as a current confirmed opportunity.

### Requirement: Research-only boundary and verifiable handoff
The board SHALL preserve blocked paper qualification and no-order behavior, with mocked automated tests and separately reported live evidence.

#### Scenario: Board result is descriptive
- **GIVEN** upward-aligned observations and a frozen-level crossing
- **WHEN** the detail card renders
- **THEN** it includes values, dates and limitations, notes news NOT CHECKED, and offers no execution, funded qualification, forecast accuracy or confidence percentage.

#### Scenario: Test and smoke evidence
- **GIVEN** fake-token automated tests and optional locally authenticated one-instrument smoke
- **WHEN** verification completes
- **THEN** no unexpected network or credential output occurs, request budgets hold, and handoff separates actual test counts from live SUCCESS/BLOCKED/FAILED status.
