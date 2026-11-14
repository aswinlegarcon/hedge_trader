## ADDED Requirements

### Requirement: Instrument-specific news access
The application SHALL request only Upstox GET /v2/news with category=instrument_keys for at most four exact watchlist keys, using existing private backend token handling.

#### Scenario: Refresh selected watchlist news
- **GIVEN** resolved watchlist keys and configured token or fake transport
- **WHEN** Refresh News is selected
- **THEN** exactly one news request is sent with encoded keys and fixed category, without candle, holdings, positions or order calls.

#### Scenario: Access unavailable
- **GIVEN** missing token, 401/403, throttling or transport failure
- **WHEN** news is refreshed
- **THEN** a sanitized status appears, old content is not labelled newly checked, technical charts remain usable and no fallback scraping or scope escalation occurs.

### Requirement: Source-attributed news integrity
Each displayed article SHALL carry a headline, safe source link, provider publication time and snapshot retrieval time, with source-reported association to exact instrument keys.

#### Scenario: Normalize and deduplicate
- **GIVEN** millisecond timestamps and the same article mapped to multiple requested instruments/pages
- **WHEN** normalization completes
- **THEN** times convert correctly, newest-first ordering holds, duplicate counts don't inflate and all associated instrument keys persist.

#### Scenario: Malformed or unsafe news item
- **GIVEN** invalid dates, missing required fields, future timestamps or unsafe article links
- **WHEN** data is parsed and rendered
- **THEN** invalid items are quarantined with diagnostics, no script/HTML/article fetch runs and no invented headline/date/source is substituted.

### Requirement: Explicit coverage and cache state
The application SHALL distinguish unrequested news, valid-empty results, unknown coverage, partial pagination, cached snapshots and failed fetches.

#### Scenario: Empty is not a risk clearance
- **GIVEN** an empty article list or a missing requested key
- **WHEN** the news panel renders
- **THEN** it shows NO RECENT ARTICLES or COVERAGE UNKNOWN respectively, with no inference of no event risk; macro/events remain NOT CHECKED.

#### Scenario: Page or selection change
- **GIVEN** a cached page-1 response
- **WHEN** next page is explicitly requested or instrument selection changes
- **THEN** at most one additional news call occurs for that click, pagination/truncation is visible and old-symbol news cannot masquerade as new-symbol context.

### Requirement: Research-only cross-page workflow
Global News & Events and Watchlist Research SHALL reuse the normalized session news snapshot without modifying technical calculations, qualified-paper state or trade authorization.

#### Scenario: Review company context
- **GIVEN** a successful news snapshot
- **WHEN** the user opens the corresponding watchlist detail card
- **THEN** associated headlines and source times appear without a new network fetch, company-news check time is explicit, manual events remain separate and no trade/sentiment/confidence output is added.

#### Scenario: Verification evidence
- **GIVEN** mocked tests and optional bounded one-instrument live check
- **WHEN** handoff is written
- **THEN** actual results, request counts, privacy checks and live status are recorded separately, alongside remaining macro/calendar/financial limitations.
