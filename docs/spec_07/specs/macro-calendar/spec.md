## ADDED Requirements

### Requirement: Usable captured macro calendar
The app SHALL import the sanitized calendar snapshot and display provider event fields with source/capture provenance, without copying browser credentials or rendering raw HAR HTML.

#### Scenario: Import the user's calendar
- **GIVEN** a valid captured-calendar JSON or local extraction of matching HAR HTML
- **WHEN** the user imports the normalized snapshot
- **THEN** event rows can be filtered by captured date/country/category, capture time and coverage are visible and no browser keys/cookies are persisted.

#### Scenario: Nested HTML and missing fields
- **GIVEN** nested layout tables and missing numeric/forecast fields
- **WHEN** event rows are normalized
- **THEN** outer event identity is preserved, fields map to verified selectors/headers, unknowns stay unknown and no duplicate inner rows appear as events.

### Requirement: No guessed event timing or importance
The app SHALL preserve unconfirmed website timezone and importance semantics until supported by explicit source evidence or labelled user confirmation.

#### Scenario: Unconfirmed capture timezone
- **GIVEN** raw website dates/times without established timezone
- **WHEN** calendar/context renders
- **THEN** original display time and uncertainty are shown without inferred IST/UTC countdowns or imminent-event confirmation.

#### Scenario: Explicit timezone confirmation
- **GIVEN** user-confirmed IANA capture timezone and valid unambiguous time
- **WHEN** conversion is requested
- **THEN** UTC/IST values and confirmation provenance are recorded; invalid/DST-ambiguous/estimated times remain unknown.

### Requirement: Honest bounded public refresh
The client SHALL issue at most one ordinary credential-free GET per explicit public-refresh action and accept only validated calendar data.

#### Scenario: Public endpoint returns no usable data
- **GIVEN** HTTP 202 empty, access denial, challenge or malformed/non-calendar response
- **WHEN** public refresh runs
- **THEN** it reports UNAVAILABLE, preserves old snapshot as captured reference, and performs no browser-key/cookie replay, evasion or retry.

#### Scenario: Public calendar succeeds
- **GIVEN** HTTP 200 with expected table and valid rows
- **WHEN** public refresh completes
- **THEN** a new web snapshot has its own retrieval timestamp, while unknown timezone/importance and incomplete coverage remain explicit.

### Requirement: Shared research context with limitations
Global News & Events and Watchlist Research SHALL share calendar context without altering technical voting, qualification or trading permissions.

#### Scenario: Empty filters or stale snapshot
- **GIVEN** no matching rows or an old imported snapshot
- **WHEN** the calendar or macro panel renders
- **THEN** it describes snapshot scope/age, never all-clear event risk, and blocks stale/unknown-time imminent-event claims while keeping reference browsing available.

#### Scenario: Verification and source isolation
- **GIVEN** fake HAR/HTML fixtures, mock transport and fake Upstox secret sentinel
- **WHEN** tests and optional one-call public smoke run
- **THEN** no token/cookie is sent to Trading Economics, automated tests stay offline, and handoff separates parser/import evidence from actual live status.
