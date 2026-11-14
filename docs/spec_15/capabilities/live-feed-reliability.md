# Capability: reliable read-only feed

Normative language: MUST denotes acceptance requirements. Each scenario needs a named automated test or explicit BLOCKED evidence; xfail/skip does not satisfy it.

## ADDED Requirements

### R01 — Truthful price freshness
LIVE freshness MUST require source and receipt-progress ages within the design thresholds. Transport health MUST be separate.
- S01: Given a one-hour-old trade received now, when the UI materializes, it MUST show stale/not fresh and the source age.
- S02: Given only heartbeats/market_info/pings, no price MUST become fresh; a previously fresh trade MUST expire after 30 seconds.
- S03: Repeated identical/source-time-stationary data and older same-bucket ticks MUST NOT extend source-progress freshness or regress latest trade time.
- S04: UTC clock movement MUST NOT extend monotonic receipt freshness; threshold boundaries MUST be tested with injected clocks.
- S05: REPLAY MUST remain network-free, explicitly synthetic, and usable with its historical fixtures.

### R02 — Timestamp rejection without state poisoning
- S06: A future tick >2s MUST leave book, high-water, latest source and receipt-progress state unchanged; a following valid tick MUST still be admitted.
- S07: Missing, invalid, non-finite, overflow and non-positive timestamp inputs MUST be rejected without crashes or unbounded diagnostics. Test at the decoder/admission boundaries supported by the protobuf field types.
- S08: Older intra-bucket data MUST preserve the newest close while retaining the documented high/low policy; completed bars MUST not reopen.

### R03 — Production authentication behavior
- S09: A fake requests.Session returning 401/403 through real RequestsTransport MUST yield one authorize attempt, a non-retryable safe auth error and no connect call. Preserve the separate bootstrap one-attempt behavior.
- S10: Malformed 200 authorize JSON/payload/URI MUST produce a non-retryable protocol error; a temporary server/transport failure MUST use only the documented bounded reconnect loop.
- S11: Clean-close and exception exhaustion MUST stop at the same configured budget, show a consistent terminal category and retain a reconnect coverage warning.

### R04 — Responsive stop with accounted cleanup
- S12: Stop during bootstrap/authorize, handshake, receive, and backoff MUST immediately invalidate frame/retry admission, return within the design UI budget, and terminate controlled workers within the shutdown budget.
- S13: While worker cleanup is pending, UI MUST say stopping, new Start MUST not create an overlapping worker, and STOPPED MUST require actual worker termination.
- S14: A delayed callback from an old generation after Stop/restart MUST NOT change the new book/state or initiate another authorize call.

### R05 — Owner lease and concurrency
- S15: After an owner stops keepalives, cleanup MUST run without any further registry call; the slot MUST become reusable within the lease+cleanup bound. A second owner MUST start without restarting Streamlit.
- S16: Active keepalives MUST preserve ownership; wrong owner/generation keepalives and Stop requests MUST neither renew nor release it. Conflict responses MUST NOT expose another owner's book or owner token.
- S17: Repeated Start/Stop/expiry cycles MUST leave zero session I/O/monitor workers and no open test sockets. Tests MUST cover snapshot/frame/Stop concurrency without partial snapshots or deadlocks.

### R06 — Current dashboard status
- S18: The real Streamlit page MUST display current freshness, fault, exchange status and stopping state without a button-triggered rerun. Non-normal exchange status and no-trade waiting MUST be explicit, with no invented exchange calendar claim.
- S19: Existing chart data, retention, viewport and restart acceptance MUST remain passing at shipped REPLAY pacing; assertions MUST inspect actual series.data(), not input echoes.

### R07 — Actual WebSocket client compatibility
- S20: A loopback server MUST accept the production client's binary subscribe frame, send schema-encoded feed data, and observe close/cleanup. Test real connect/send/recv, not a fake WebSocket object.
- S21: Loopback disconnect/reconnect and authentication-boundary failures MUST exercise production lifecycle classification; only loopback sockets are allowed in these tests, never public broker hosts.

### R08 — Secret-safe diagnostics
- S22: With root and third-party logging at DEBUG and distinctive dummy token/authorized-URI markers, captured logs, exception displays, snapshots and browser payloads MUST contain none of the markers. Test handshake failures as well as successful connection setup.

### R09 — Installation and delivery integrity
- S23: A clean Python 3.12 environment installed by the documented supported command MUST import the app stream modules, decode the vendored protobuf fixture, and run the loopback compatibility test without relying on undeclared local packages. Record dependency resolution and protobuf compatibility.
- S24: Existing F1/F2/F3 xfails MUST become regular passing tests; the F4 leak characterization MUST become a passing cleanup regression. No new expected failure or skip may hide these requirements.
- S25: Handoff MUST identify exact tested commit(s), scenarios-to-tests, dependency versions, final full-suite counts/reasons for unrelated skips, and all remaining limits. Any missing normative scenario MUST yield BLOCKED, not READY_FOR_OPERATOR_SMOKE.

## MODIFIED Requirements

Spec 14's read-only, single-instrument chart scope and attribution remain. LIVE readiness now requires this capability; the historic GO recommendation in docs/spec_14/live-readiness-review.md is superseded. The operator smoke MUST be separately performed after review, not by the implementation agent in this task.
