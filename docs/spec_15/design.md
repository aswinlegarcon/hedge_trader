# Design — Spec 15

## Evidence and entry points

Read docs/spec_14/live-readiness-review.md and its tests first. Primary paths: nifty_lab/stream_chart/{stream_session,transport,stream_errors,feed_decode,candles,ui,constants}.py; production frontend/index.html; nifty_lab/brokers/upstox_transport.py; tests/test_spec14_{live_readiness,browser_acceptance,stream_chart}.py. Keep changes in the streaming subsystem unless a small, compatible shared-transport extension is necessary and tested for existing callers.

## 1. Time model and price admission

Inject UTC wall time for source comparisons and monotonic time for elapsed waits, lease age, deadlines and retry backoff. Never derive elapsed deadlines from wall time. Use a session-owned dependency object or explicit callables; no production sleeps patched globally.

LIVE policy defaults (named constants): source freshness 30 seconds; receipt inactivity 30 seconds; maximum future skew 2 seconds. These are operational display/admission policies, not exchange guarantees. Keep REPLAY explicitly synthetic and governed by its fixture timeline; do not mark its historic fixture fresh LIVE data or reject it using today's wall clock.

Reject malformed/non-positive/non-finite/out-of-range trade timestamps and timestamps > receipt UTC + 2 seconds before any book, dedupe, high-water, last-trade or freshness mutation. Increment bounded diagnostic counters; never echo raw frames. A valid old trade may populate an initial historical observation, but cannot make the price fresh. Out-of-order accepted trades cannot move last_trade_ts backward or refresh the receipt-of-latest-source-progress clock. Repeated same-source snapshots also cannot refresh that clock. Keep latest valid frame receipt separate if needed for transport diagnostics.

A LIVE price is fresh only if both latest accepted source age and monotonic age since source-time progress are <=30 seconds, with source skew within tolerance. A source age in [-2,0] may be clamped to zero for display. Rejected future data cannot establish freshness. Wall-clock jumps must not extend receipt freshness. Retain Spec 14 same-bucket close semantics: older accepted trades can extend high/low, not overwrite the newer close. Timestamp ties have the existing explicitly documented arrival-order policy.

## 2. State and UI contract

Separate connection lifecycle from price freshness in the snapshot/view model. Retain compatible existing public states where sensible and add explicit STOPPING / WAITING_FOR_DATA / OWNER_EXPIRED equivalents as needed. Document one state table mapping transport, market status and freshness to UI text. Never emit STREAMING/fresh without passing both freshness checks. Heartbeats, market_info, pings and pongs prove different things; none advances source price freshness. With a connected but quiet/closed market, show waiting/stale and the provider exchange status, not perpetual unexplained CONNECTING. Do not infer holidays or exchange closure from local weekdays.

Move current status, errors, source/receipt ages, exchange status and reconnect diagnostics into the actual auto-refreshing fragment, or a single shared current view model rendered there. The initial page must not display a conflicting stale main-body status. Preserve chart retention, zoom, attribution and source-time OHLC. Do not add broker refresh loops outside explicit Start.

## 3. Authentication and bounded retries

Normalize UpstoxAuthError from real RequestsTransport at the authorize boundary (401/403), as well as returned 401/403 tuples, into a non-retryable sanitized auth failure. Bootstrap auth failure must also fail once. Treat invalid successful authorize payloads as non-retryable protocol failures, not authentication failures. Temporary transport/server failures may retry within the existing session-lifetime budget: at most 3 reconnects after the initial attempt, stop-aware backoff 1/2/4 seconds, no hidden second retry engine. Preserve gap warnings; exhausting either clean-close or exception retries has one consistent retry-exhausted category and safe message. No background token refresh or reauthorization after Stop/expiry.

## 4. Ownership and concurrency

Give each run an unguessable internal session/generation identity. Start, snapshot, keepalive and Stop operations validate owner plus generation where applicable so delayed calls cannot keep alive or stop a replacement run. Non-owners must not receive book data or sensitive owner tokens.

Default owner lease: 20 seconds since last explicit owner/viewer keepalive, measured monotonically; monitor checks at most every 2 seconds. The Streamlit fragment renews only the current owner's lease while that session is displayed. Snapshot reads, incoming feed frames and global registry access do not implicitly renew it. An independent bounded monitor must expire an abandoned LIVE owner even if nobody calls the registry again. Background tabs that cease rendering may expire; show a clear restart action when they return. No automatic ownership takeover while the old network worker is alive.

On expiry request shutdown, expose a sanitized owner-expired reason, and reclaim the slot only once all old I/O workers are dead. Another session may start without a process restart after cleanup. A normal user Stop cancels the lease monitor too. Terminal-session metadata may be retained briefly for display but must not block a new Start once cleanup completes. Monitor design must be bounded; no accumulating per-tick timers or immortal sweeper threads.

Protect mutable session/book fields and snapshot copies with a clear lock strategy. Do not hold the registry lock or session data lock across HTTP, WebSocket I/O, joins, sleeps or bootstrap. No deadlock between frame callback, snapshot, Stop and monitor. Bootstrap belongs to the same stop-aware session lifecycle; synchronous Start must not block unrelated owners behind global-lock I/O.

## 5. Shutdown contract

Stop request returns to the UI within 250ms under deterministic controlled tests, immediately makes the generation terminal for new frames/retries, and reports STOPPING while cleanup remains. Do not claim STOPPED or free ownership while the old worker is alive. Frames arriving after Stop/expiry cannot mutate the book or restore STREAMING.

Use explicit bounded authorization, handshake, receive and close behavior. Controlled injected production-path tests must show all session I/O and monitor workers terminate within 20 seconds of Stop/expiry; active receive/backoff should terminate within 2 seconds. Lease cleanup therefore finishes within 42 seconds of the last keepalive (20 lease + <=2 monitor + <=20 shutdown). These are acceptance budgets, not claims of hard real-time guarantees under OS/network failure. If an underlying operation cannot be bounded safely, retain ownership, show a specific shutdown failure and BLOCK smoke readiness; do not abandon a helper network thread and call cleanup complete. Explain actual library/OS limitations in the handoff. Avoid blocking requests calls on the event-loop thread; if using a helper, bound and account for its entire lifetime.

## 6. Real transport compatibility and secret handling

Exercise LiveWebSocketTransport using the installed declared websockets API and real generated protobuf on loopback. Stub only remote authorization/destination at an injected boundary; do not replace connect/send/recv with fake methods in this compatibility test. Production must continue to require wss; allow a loopback-only test seam without allowing arbitrary ws URLs in production. Confirm binary subscribe payload, fixed instrument/mode, binary feed decode, disconnect/reconnect and Stop.

Use a dedicated transport logger that drops third-party handshake details even when root and websockets logging are DEBUG. Do not globally disable application logging. Allowlisted application diagnostics may include category, attempt and timing but never token, Authorization header, authorized URI/query, raw request/response or raw exception message. Verify with distinctive dummy secrets and captured logs at DEBUG. Sanitization after the library has already emitted a secret is insufficient.

## 7. Reproducible dependencies

Declare every direct runtime dependency used by the stream path in the installation sources the project actually supports. Include requests, websockets and protobuf; keep pyproject.toml and requirements.txt coherent. Verify generated protobuf runtime compatibility; the current generated module checks 7.36.2, so do not merely add an unconstrained protobuf dependency. Choose tested ranges or regenerate deliberately from the existing official schema with documented provenance. Also verify the minimum supported Streamlit version supports the fragment API in use. Document a canonical Python 3.12 install and test command plus compatible resolved versions; do not use a pre-populated .venv as dependency proof. Do not introduce a new package manager or wholesale dependency upgrade solely for this task.

## References (checked 2026-11-14)

- Upstox Feed V3: https://upstox.com/developer/api-documentation/v3/get-market-data-feed/ — protobuf protocol, source fields and control-frame heartbeat distinction.
- Authorize V3: https://upstox.com/developer/api-documentation/get-market-data-feed-authorize-v3/ — server-side authorized WebSocket URI.
- websockets asyncio client: https://websockets.readthedocs.io/en/stable/reference/asyncio/client.html — explicit connection/close timeouts and logger injection. Verify behavior against the version selected for implementation.

The policy constants, owner lease and acceptance deadlines above are project design decisions, not provider service-level guarantees.
