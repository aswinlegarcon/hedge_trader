## ADDED Requirements

### Requirement: Actual read-only Upstox candle access
The application SHALL use a locally configured token for bounded authenticated GET requests to official V3 candle endpoints and official instrument assets only.

#### Scenario: Load a watchlist instrument
- **GIVEN** an unambiguously resolved NSE equity/ETF and valid local access token
- **WHEN** the user selects Upstox, 5m and Load
- **THEN** prior candles and today's completed intraday candles appear in timestamp order on the existing chart, with exact instrument identity and API source.

#### Scenario: Daily research
- **GIVEN** a resolved instrument and valid token
- **WHEN** daily history is requested
- **THEN** days/1 history through yesterday loads with daily labels and honest warm-up warnings.

### Requirement: Honest identity and candle quality
The application SHALL resolve instrument_key from official JSON metadata, keep timezone-aware bar timestamps and exclude incomplete/invalid candles from indicators.

#### Scenario: Ambiguous security
- **GIVEN** multiple or no instrument matches
- **WHEN** a user selects a research label
- **THEN** no guessed instrument request is sent and the user sees resolution choices or NO DATA.

#### Scenario: Partial or malformed data
- **GIVEN** a forming bar, out-of-order records, duplicates or invalid OHLC/volume
- **WHEN** a response is normalized
- **THEN** completed valid bars are sorted, forming bars excluded, identical duplicates diagnosed and conflicting/malformed data rejected without silent repair or invented volume.

### Requirement: Safe refresh and errors
The application SHALL use explicit refresh, bounded timeouts/retries, sanitized diagnostics and truthful connection/freshness status.

#### Scenario: Missing or expired token
- **GIVEN** absent token or 401/403 response
- **WHEN** Load is requested
- **THEN** the UI explains local token setup/renewal, clears verified connection state and never displays secrets or unrelated cached charts.

#### Scenario: Throttle or timeout
- **GIVEN** 429, 5xx or network failure
- **WHEN** the load completes
- **THEN** retries remain within the design budget and a clear retry-later/unavailable result appears without synthetic fallback.

#### Scenario: Switch instrument or source
- **GIVEN** a previously loaded broker dataset
- **WHEN** symbol, source, interval, connection or request changes and the new load fails
- **THEN** the old dataset cannot masquerade as the new selection; all chart labels and provenance reflect displayed data.

### Requirement: Charts do not authorize trades
The integration SHALL preserve blocked funded-paper recording, distinguish API history from streaming quotes and avoid unsupported NIFTY/intraday trading conclusions.

#### Scenario: Equity or 5m chart loaded
- **GIVEN** real broker equity/ETF or intraday candles
- **WHEN** chart/Signal Monitor/Options pages render
- **THEN** selected-symbol and bar-based labels are correct, unsupported daily annualization/voting is unavailable, and no funded-paper save or order operation is enabled.

### Requirement: Evidence and secret privacy
Automated tests SHALL use mocked HTTP and fake tokens. Live read-only verification SHALL report sanitized observable results separately from implementation/test status.

#### Scenario: Automated verification
- **GIVEN** fake transport, token sentinel and temporary storage
- **WHEN** request, normalization, UI and failure tests run
- **THEN** no unexpected network call occurs, no sentinel leaks, and synthetic/CSV regression results are reported.

#### Scenario: Bounded real connection check
- **GIVEN** locally prepared credentials or no usable token
- **WHEN** the bounded smoke command runs
- **THEN** it reports instrument, interval, row count and last completed time on success, or a sanitized BLOCKED/failed reason, never raw credentials/headers or a claim of predictive accuracy.
