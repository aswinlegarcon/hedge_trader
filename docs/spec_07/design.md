# Design

## 1. Source handling

Primary usable source for this slice is the sanitized JSON produced from the supplied HAR. Import through a Streamlit JSON upload (bounded e.g. 5 MB) and keep normalized objects in local session state. Do not upload raw HAR to any third-party service. Optional local extraction command may read the explicitly supplied HAR path, decode only the matching HTML response and emit allowlisted event fields. Never log/serialize the whole HAR or request/response headers.

The author snapshot is located at `/Users/sanjain/Documents/Codex/2026-11-13/referenced-chatgpt-conversation-this-is-an/outputs/tradingeconomics_calendar_snapshot.json`. Use as a local manual-check input, not a repository fixture or hardcoded runtime dependency. Automated fixtures must be tiny synthetic HTML/JSON, with no captured keys or private metadata.

Har matching: exact HTTPS host tradingeconomics.com, path /calendar, partial=calendar, method GET, status 200 and HTML containing table id calendar. Decode base64 when declared. Select the newest valid matching capture, retain its capture time as capture_started_at. Missing payload/table fails with diagnostic. No execution of scripts from captured HTML.

## 2. HTML and snapshot parsing

Website HTML is an undocumented source adapter, not the official TE API. Identify event rows with data-id, data-country, data-category, data-event and data-url. Parse only outer calendar event rows; nested layout tables must not truncate events or create duplicate records. Map cells using header/element identifiers, not fragile whole-row text splitting. Event title comes from .calendar-event. Values use #actual, #previous, #consensus; reference uses .calendar-reference. Preserve revision text/tooltip separately. Establish the provider-forecast column from captured headers before labelling it; otherwise keep raw/unmapped rather than silently equating it with consensus.

Use provider event ID as identity. Deduplicate same ID/capture consistently and report conflicting duplicate fields. Preserve all monetary/percentage/K/M/B strings; missing text is unknown, never zero. Source links must resolve to safe HTTPS tradingeconomics.com URLs; no external fetches. Render escaped text/link widgets; no raw captured HTML in unsafe rendering.

Snapshot includes origin HAR_SNAPSHOT or PUBLIC_HTML, capture/retrieval time, displayed date range, event count, parser diagnostics, timezone status, importance status and coverage description. Every event includes ID, country/category/name/reference, display date/time strings, actual/previous/consensus/provider forecast when established, source URL and optional known scheduled_at_utc/importance.

Do not assume website display timezone from the official API documentation, local computer timezone, country or user locale. Default UNCONFIRMED. UI may allow the user to explicitly confirm the capture's display timezone; store this as USER_CONFIRMED with selected IANA zone and convert using zoneinfo, preserving raw values. Ambiguous/nonexistent DST times, non-time labels and invalid dates stay unknown and exclude countdowns. Show IST only after valid timezone conversion, with the confirmation provenance. If no confirmation is provided, display the captured time exactly with 'timezone unconfirmed'.

Do not map undocumented event-/calendar-date- CSS classes to importance by guessing. Preserve unknown until source legend/CSS mapping is established with fixture evidence, or allow an explicit manual tag labelled user-entered. Unknown importance stays visible in All and a distinct Unknown group; a 'High only' filter must disclose unknown events excluded. Estimated/date-only timings do not become exact schedules. No artificial event time or economic forecast.

## 3. Bounded public refresh

One explicit manual action makes one GET to fixed `https://tradingeconomics.com/calendar?partial=calendar`, TLS verified, connect/read timeouts 3s/15s, no redirects, no automatic retries/polling. No Authorization/Cookie/session/Socket.IO key/custom browser fingerprint headers. Use a small source-specific transport so Upstox bearer token can never reach Trading Economics. Do not weaken Upstox allowlists.

Accept only HTTP 200 with expected calendar table and valid rows. HTTP 202/204 empty, 3xx, 401/403/429, challenge/login HTML, non-calendar or malformed payload yields UNAVAILABLE with sanitized status; do not replay HAR keys, solve challenges or retry through alternative fingerprints/proxies. A 200 with zero valid rows is coverage unknown/parse-empty, not 'no events'. The author obtained 202 empty; reproduce honestly rather than claiming live readiness.

Success yields a new PUBLIC_HTML snapshot with retrieval time; its source remains a web snapshot, not a guaranteed realtime feed. Timezone/importance still require independent evidence. Failure leaves imported snapshot available only as imported/reference with original capture time and an explicit refresh-failed notice. Never timestamp old data as newly fetched.

## 4. Calendar UI and context

Global News & Events gets Macro Calendar section above the manual calendar. Keep company news and manual events separate. Import JSON and Try Public Refresh are explicit actions, no startup fetch. Initial filters: All dates within captured range or Today/Tomorrow/This Week/Custom; countries India and United States by default with All available; importance All/High/Medium/Low/Unknown as supported. Filters yielding zero rows mean 'no matching rows in this snapshot', never all-clear event risk.

Table: captured/converted date-time + timezone status, country, event/reference, importance status, actual, consensus, previous, provider forecast if established, source link. Caption shows capture/retrieval time, coverage dates, data origin and limitations. Snapshot can contain released and future events; presence of actual is 'value reported in capture', not independently confirmed release truth. No actual before publication is invented.

Watchlist detail macro panel reuses same session snapshot without HTTP. Show selected-country scope and next relevant scheduled events only if timing is known and not past as of injected clock. For unconfirmed time show 'calendar imported; timing unconfirmed' with link to calendar section, not exact countdown. A conservative source-age threshold (30 minutes for an imminent-event view, clearly a design heuristic) marks older snapshot context STALE/reference and disables imminent-event confirmations. Preserve wider historical browsing. Event coverage is country-filtered macro context, not asserted causality for a particular stock/ETF.

Manual events retain original user-entered provenance and do not get silently merged/deduped into provider events. Signal voting and financial qualification remain unchanged. Upcoming earnings, corporate actions, global unscheduled news and exchange session calendar are not covered by this source automatically.

## 5. Verification

Independent tiny fixtures test nested table extraction, field mapping, missing values, safe links, duplicate IDs, newest capture selection and base64 decoding. Cover timezone unknown vs explicit confirmation, DST/time-only ambiguity, unknown importance and zero-filter results. Client tests prove one fixed public GET, no credentials/cookies/redirect retry, and 202 empty -> unavailable while old snapshot capture time stays intact. UI integration exercises import-to-filtered table and shared macro-panel display. Mock tests never consume the real HAR/.env or perform real network.

Run existing relevant regressions Python ≥3.12 with dotenv disabled. Optional live verification is a single ordinary public GET, separate from mocked test count; do not repeatedly hit an unavailable endpoint. Local manual import may use author's sanitized JSON. Handoff records imported count/date range/timezone gaps and actual live result independently. No claim of complete/current 'all events'.
