# Design

## 1. Bounded client

Use only fixed HTTPS GET `/v2/news` on api.upstox.com, with category fixed in code to instrument_keys. Expose an instrument-key list parameter, not arbitrary category/URL/headers. A batch accepts at most four nonempty unique resolved keys from the active board. Never fall back to category holdings or positions, and never discover a portfolio.

Use existing bearer token internally, TLS verification, finite timeouts and pacing. URL-encode query parameters with a standard encoder; token is only in Authorization. Instrument keys are public identifiers. No automatic redirects with bearer forwarding. Avoid new order-capable SDKs.

Default page_number=1, page_size=25. One HTTP news request per explicit click; no automatic retries/pagination. 'Load next page' is another explicit single bounded call, max two pages retained (50 response records before dedup). Show page count and truncation/remaining-results notice using metadata; do not claim complete seven-day coverage. Support providers returning fewer items legitimately. Existing master resolution may cost one separate public-asset call if needed; total at most two outbound calls for a news-refresh action, no candle requests.

Reject empty/unresolved keys before network. 401/403 yields authentication/access unavailable with no scope escalation or login automation. Distinguish missing token, access denied, rate limited, timeout/server unavailable, malformed response and valid-empty response using sanitized errors. No raw request/response dumps or exception chaining rendered to users. News success records news_checked_at only; it does not certify candle freshness or mark candle connectivity newly verified. Auth failure may clear existing shared authorization state consistently.

## 2. Typed snapshot and normalization

Snapshot: requested exact keys, UTC retrieved_at, seven-day provider window label, page metadata, per-instrument state, articles and diagnostics. Use injected aware evaluation clock. Article: heading, optional provider summary excerpt, validated URL, published_at UTC, source label 'Upstox News API', article host if available, associated instrument keys. No imaginary publisher field: article host is not independently verified publisher identity.

Require success payload/object mapping with lists for returned requested keys; ignore unexpected keys with diagnostics. An explicitly empty list for a requested instrument is NO RECENT ARTICLES. A missing key is COVERAGE UNKNOWN, unless upstream contract/verified live response establishes missing keys mean empty; record that evidence before adopting it. Top-level empty data maps all keys to COVERAGE UNKNOWN rather than assuming no news. Invalid shape is ERROR/PARTIAL, not empty.

Heading, safe URL and valid publication timestamp required for a displayable item. Convert milliseconds to aware datetime; flag/quarantine invalid, nonfinite or more-than-five-minutes-future times. No guessed dates. Sort valid articles newest first. Don't relabel old provider items as published today. An item older than seven days is excluded with a count diagnostic, not silently represented as recent.

Validate article URLs as HTTPS, no embedded user/password, controls or javascript/data/file scheme. Render links and text with normal escaped Streamlit text/link widgets, never unsafe external HTML. Do not fetch URLs/thumbnails or send bearer headers to article hosts. No full article content scraping. Show heading and optional short provider excerpt up to 240 characters, attributed as 'provider summary'; truncation is explicit, not a generated summary. Full article is a user-opened external link.

Deduplicate by normalized safe URL and publication timestamp, preserving all associations across instruments. Duplicate items on page 2 don't inflate the count; don't merge different-date updates solely because their heading matches. Keep returned associations as provider-reported relevance, not proof the company is the article's sole subject. General-market articles may appear for multiple symbols.

## 3. User workflow

Global News & Events displays a Watchlist News section, resolved selection (max four), Refresh News, response status, provider's recent-history window and snapshot time. Replace only the placeholder that falsely says no feed exists; keep the manually entered upcoming-event calendar distinctly user-entered. Scheduled macro events remain NOT CHECKED.

Watchlist Research selected card shows latest up to five associated articles or explicit NOT CHECKED / NO RECENT ARTICLES / COVERAGE UNKNOWN / UNAVAILABLE. A compact 'Refresh news for watchlist' invokes the same client/snapshot as page 02. Selecting another card is local, not an HTTP call. Switching exact keys invalidates the active news snapshot or marks it as belonging to the old selection. Never associate data through display-label similarity alone.

News refresh never reruns candle fetch, changes technical summary values or promotes a descriptive row into a trade signal. Refreshing candles for the same key does not erase valid news, but different retrieval times stay visible. If no candles are currently resolved, show how to resolve them; no bulk candle I/O behind a news button.

After successful fetch replace the blanket 'news NOT CHECKED' caption with precise 'Upstox company news checked at [time]; recent-history coverage limited; macro/events NOT CHECKED'. An empty result is not 'no risk'. If the snapshot becomes older than 15 minutes, label it 'cached news snapshot — refresh to check for updates', not invalid market news. Old articles remain valid history with publication time. No background poll or scheduling.

Store normalized news in session state only, with public selection identity and page metadata; no token/client/headers in cache arguments, session state or serialization. A failed explicit refresh must not leave previous headlines labelled freshly checked. Either clear results or show previous content as cached/reference with original timestamp plus failure. No private DB migration or journal access.

## 4. Preserve scope and honest evidence

Keep no orders and blocked funded-paper qualification; leave NIFTY voting restriction intact. Do not treat headlines as confirmed factual truth, infer sentiment or invent catalysts/earnings dates. API content is source-reported. The future macro calendar will need separately verified official schedules.

Spec 05 handoff states 'up to 9 calls per instrument'; inspected path appears to request one daily plus two 5m calls (three per instrument) without new retries. Do not repeat the nine-call claim as verified. Correct this documentary inconsistency with actual mocked transport counts if touching the handoff; no transport rewrite needed for news.

Other prior unresolved items remain deferred: market-session/holiday labels, process-wide connection state, partial-frame recovery, missing broad UI scenario coverage and Spec 03 financial-gate issues. These do not block a bounded read-only news panel. Do not mark them fixed by passing this slice's tests.

## 5. Verification

Mock transport and fake tokens, disable dotenv loading for automated checks, prohibit unexpected network/private journal access. Cover batch/query budget, forbidden categories, publication conversion/sorting/age, duplicate associations, explicit empty vs missing key, malformed/unsafe article data, expired access, partial pagination, selection changes and stale/failure state. Capture fake-token sentinel in logs/UI/error paths and ensure no output leakage. Exercise Refresh-to-panel and page-to-page snapshot reuse with UI tests or a clearly evidenced integration harness; test count alone is not a scenario map.

Optional live smoke: one instrument from existing resolved/public metadata; at most one news call plus one master call if necessary. Token consumed internally only. Output symbol, article count, newest valid publication time, retrieved time, pagination/coverage state and sanitized result. No article full text, headers or token values. Report SUCCESS / VALID EMPTY / COVERAGE UNKNOWN / BLOCKED / FAILED honestly. If endpoint denied do not request higher permissions or scrape a fallback. Finish mocked implementation and report limitation.
