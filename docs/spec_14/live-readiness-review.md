# Spec 14 — LIVE market-data smoke test readiness review

**Date:** 2026-11-14 · **Base:** `main` @ `b111e5257212e8b5c73bb7d2a91a5c444f0426c7` · **Scope:** investigation + verification only; no application code changed.

## Verdict: **GO** for one bounded, read-only LIVE smoke test

GO means the code is ready to *attempt* the smoke test under the procedure below. LIVE streaming itself is **not verified**: the
production WebSocket path (`websockets 17.4`) has never been executed in this repo — every offline check blocks sockets. The
smoke test is the first execution of that path. Four defects were found; none is blocking for a single operator running a
≤15-minute attended test with the abort rules below, and all are documented with strict `xfail` tests so they cannot be forgotten.

## Findings

Numbering: **F** = defect (should be fixed before anything beyond a smoke test), **L** = limitation (document / accept).
Evidence tests live in `tests/test_spec14_live_readiness.py` unless noted.

### Blocking defects

None for the bounded smoke test as specified below.

### Non-blocking defects

| ID | Finding | Where | Evidence |
|----|---------|-------|----------|
| **F1** | **Freshness is keyed on local receipt time only.** An hour-old trade that arrives now flips the session to `STREAMING`; `STALE` is derived from `last_trade_receipt_ts` age, never from the source trade time. The UI does show "Last trade (UTC)", so an operator can detect it by eye, but the `Connection` state implies fresh prices. | `stream_session.py:95-100` (`_effective_state`), `:152-157` (`_on_frame` sets `last_trade_receipt_ts = now` and promotes to STREAMING) | `test_old_trade_received_now_is_not_reported_fresh` (xfail strict); `test_source_trade_time_and_local_receipt_time_are_distinct` (pass: the two fields are distinct) |
| **F2** | **No future-timestamp guard.** One tick with `ltt` in the future raises `_high_water_trade_ms`; every later real tick is then dropped as "late" until restart. Observable only via `late_ignored` climbing while the chart freezes. | `candles.py:116-124` (late policy), `:139` (high-water update); `feed_decode.py:50` rejects `ltt <= 0` only | `test_future_trade_is_rejected_and_does_not_poison_later_ticks` (xfail strict) |
| **F3** | **Authorize 401 through the production transport is retried.** `RequestsTransport.get` raises `UpstoxAuthError` on 401/403 *before* `fetch_authorized_ws_uri` can see the status, so its typed `FeedAuthError` branch (`transport.py:30-31`) is unreachable in production. The worker treats `UpstoxAuthError` as a generic exception and retries 3× with 1/2/4s backoff (4 authorize calls, ~7s) before `ERROR`. The final fault **is** sanitized and useful (`FEED_AUTH_FAILED: Authentication failed. Check local token.`). The design note "auth failure → ERROR (no endless retry)" holds only because retries are bounded. Bootstrap 401 (the common bad-token case) fails fast with no worker. | `upstox_transport.py:66-67`; `stream_session.py:185-196` (`except FeedAuthError` vs `except Exception`); `stream_errors.py:33-36` | `test_authorize_401_through_production_transport_ends_in_sanitized_error_with_bounded_retries` (pass, asserts 1+3 calls), `test_authorize_401_through_production_transport_does_not_retry` (xfail strict), `test_bootstrap_401_through_production_transport_errors_without_worker`, `test_missing_token_live_start_errors_without_any_http` |
| **F4** | **A vanished browser session leaves a LIVE worker running indefinitely and blocks every other session.** The owner token is the Streamlit session id; nothing runs on session end. A closed tab keeps its daemon worker (and WebSocket) alive; `start_stream` from any other session returns `OWNER_CONFLICT`, and `stop_stream` from a non-owner is rejected. Only the original tab, or a Streamlit process restart, can release it. `IDLE_SESSION_SEC` purging applies only to sessions whose worker already exited. | `stream_session.py:275-285` (conflict), `:315-323` (non-owner stop rejected), `:250-259` (purge requires dead worker); no session-end hook anywhere in `nifty_lab/` | `test_vanished_browser_session_leaves_live_worker_running_and_blocks_new_owner` (pass; characterizes current behavior) |

### Non-blocking limitations

| ID | Limitation | Where | Evidence |
|----|-----------|-------|----------|
| **L1** | Reconnect budget is per session lifetime, not per outage: `attempt` never resets after a successful reconnection, so the 4th disconnect in a session (even hours apart) ends it in `ERROR`. Fine for ≤15 min. | `stream_session.py:159-196` | `test_reconnect_budget_is_per_session_lifetime_not_per_outage` |
| **L2** | Retry exhaustion after exceptions surfaces as `TRANSPORT_FAILED: Stream transport error.`; `MAX_RECONNECT` is only emitted after clean server closes. `Reconnect #` metric still shows 3. | `stream_session.py:180-184` vs `:192-196` | same test |
| **L3** | Stop during an in-flight HTTP authorize cannot interrupt `requests.get`; `stop()` joins for up to 5s, blocking the Streamlit rerun, then returns with the worker alive until the HTTP timeout (3s connect + 10s read). New starts get `OWNER_CONFLICT: Previous stream still stopping.` for that window. `websockets.connect` open (default 10s) is similarly uninterruptible; active receive and backoff respond to Stop within ~1s. | `stream_session.py:219-228`; `upstox_transport.py:17-18`; `transport.py:74-78` | `test_stop_during_blocking_authorize_waits_for_the_call_then_releases_owner`, `test_stop_during_active_receive_exits_promptly`, existing `test_stop_during_backoff` |
| **L4** | Closed market / no trades: state stays `CONNECTING` indefinitely (STREAMING requires an accepted trade). Exchange status from heartbeats is shown in the fragment caption (`exchange=NORMAL_CLOSE`). Heartbeats correctly never promote state or refresh staleness. | `stream_session.py:143-147`, `:155-157` | `test_closed_market_heartbeats_keep_connecting_state_and_expose_status`, `test_heartbeat_alone_never_implies_fresh_prices` |
| **L5** | The main-body `Connection` metric and fault banner (`ui.py:94-98`) refresh only on reruns (button clicks); the 1 Hz fragment caption (`ui.py:31-34`) is the live status. Operators must read the caption, or click nothing and watch the caption. | `ui.py:22-36`, `:94-98` | inspection |
| **L6** | `websockets` and `protobuf` are runtime dependencies of LIVE/decoding but are declared in neither `requirements.txt` nor `pyproject.toml`; both happen to be installed in this `.venv` (17.4, 7.36.2). A fresh environment would fail LIVE with `TRANSPORT_FAILED` after 3 retries. | `transport.py:72`, `feed_decode.py:8`; `requirements.txt`, `pyproject.toml` | `importlib.metadata` check in this review |
| **L7** | After a session ends (REPLAY complete, ERROR, or Stop not clicked) the registry purges it 120s after the worker exits; the fragment then renders nothing and the chart disappears silently. | `stream_session.py:250-259`, `constants.py:29` | inspection |
| **L8** | Stop unmounts the chart; restart is a fresh iframe/instance (verified by design in the browser tests). | `ui.py:85-90`, `:118-123` | `test_streamlit_shipped_pacing_updates_and_restarts` |

### Secret handling — no defect found

- Token is read server-side from `os.environ` (`upstox_market_data.py:62-65`; `.env` loaded by `config.py:16` with `override=False`) and only ever placed in the `Authorization` header (`upstox_transport.py:77-80`).
- The authorized `wss://` URI is a local variable in `LiveWebSocketTransport.run` (`transport.py:68`); it is never stored on the session or snapshot (`StreamSnapshot` has no URI/token fields; asserted by `test_snapshot_and_faults_carry_no_token_or_wss_uri`).
- Browser traffic: component args are bars only (`ui.py:27`, `index.html:50-53`); the component value is `{instanceId, updateCount, barCount}` (`index.html:57-60`); faults shown in the UI are the sanitized `StreamFault` messages only (`ui.py:98`), and `sanitize_exception` drops any text containing `wss://`, `Bearer `, `authorizedRedirect`, `UPSTOX_ACCESS_TOKEN` (`stream_errors.py:9, 37-39`). Raw exceptions are not logged anywhere on this path (only `_LOG.debug("decode skip: %s", type(exc).__name__)` at `stream_session.py:140`).
- No file/artifact writes exist in `nifty_lab/stream_chart/`.
- **Caveat:** the `websockets` library logs the handshake request line at `DEBUG` level, which would include the authorized URI path/query. The app never configures logging (root stays at WARNING). Do **not** run the smoke test with `DEBUG` logging enabled for `websockets`.

## Checks run

All with `NSL_FORBID_LIVE_MUTATIONS=1`, `.venv/bin/python3.12`, `TMPDIR=/tmp/pytest_hedge`, sockets blocked in the offline modules.

| Command | Result |
|---------|--------|
| `pytest -q tests/test_spec14_live_readiness.py` (new; real `StreamSession` worker + real `RequestsTransport` with a fake `requests.Session`; dummy token via env) | 12 passed, 3 xfailed (F1, F2, F3) |
| `pytest -q tests/test_spec14_stream_chart.py` | 14 passed |
| `pytest -q tests/test_spec14_browser_acceptance.py` (adds `test_streamlit_shipped_pacing_updates_and_restarts`: unpatched page at shipped 0.4s pacing, Start → convergence to server candles → "Auto-refresh · stopped" → Stop unmounts → Start → fresh instance converges; readiness observed, no sleeps) | 3 passed |
| Static trace: `RequestsTransport.get` → `fetch_authorized_ws_uri` / `fetch_intraday_bootstrap` → `StreamSession.start` / `_worker` → `sanitize_exception` → `ui.py:98` | documented above |
| Dependency presence: `websockets 17.4`, `requests 2.34.2`, `protobuf 7.36.2` in `.venv` | present (L6: undeclared) |

Full suite not rerun: only tests were added and no application code changed (last full run on this exact base: 317 passed, 1 skipped).

## Not verified

- Any real Upstox request or WebSocket frame. The `websockets 17.4` API path (`connect`, `send`, `recv`, binary subscribe frame) is unexecuted; the smoke test is its first run.
- Decode of a real Feed V3 `FeedResponse` (fixtures use the vendored schema with ltpc only; non-ltpc unions are ignored by design).
- Behaviour under a real token rotation / 401 mid-stream (only modelled offline).
- The macOS checkout was not touched or inspected.

## Operator smoke procedure (bounded, read-only)

**Preconditions:** market hours (NSE, Mon–Fri 09:15–15:30 IST); a single operator; one browser tab; a fresh `UPSTOX_ACCESS_TOKEN`
in local `.env` (never pasted anywhere else); this `.venv`; no `DEBUG` logging. **Maximum duration: 10 minutes streaming,
15 minutes wall clock.**

```bash
export NSL_FORBID_LIVE_MUTATIONS=1   # orders stay blocked; streaming is read-only GET + ws subscribe
.venv/bin/python3.12 -m streamlit run app.py
```

1. Open page **14 Stream Chart**. Select **LIVE (Upstox Feed V3)**. Note wall-clock time (T0).
2. Click **Start stream** once. Expected within ~15s: `Bootstrap bars` > 0, fragment caption cycles `connecting` → `streaming`,
   `Last trade (UTC)` within ~1 minute of now, `late_ignored` small and not climbing continuously, chart shows bootstrap bars plus a forming bar.
3. Watch for 5–10 minutes without clicking Start again. Expected: `Last trade (UTC)` keeps advancing; a 5m rollover appends a bar
   without duplicating or dropping bars; `Reconnect #` stays 0 (or ≤1 with a "Reconnect gap" warning); state alternates only
   between `streaming` and (briefly, in thin trading) `stale`.
4. Click **Stop stream** once. Expected within ~2s (≤5s): chart unmounts, `Connection` = `STOPPED`, no error banner.
5. Optional once: **Start stream** again → expected a fresh bootstrap and `streaming` within ~15s; then **Stop stream**. Done.

**Abort immediately (click Stop; if the UI is unresponsive for >15s, stop the Streamlit process with Ctrl-C) if any of:**
- `FEED_AUTH_FAILED` or `TRANSPORT_FAILED` banner (do not retry more than once; verify the token locally first).
- `Last trade (UTC)` more than 2 minutes behind the wall clock while the state still says `streaming` (F1), or `late_ignored` climbing with a frozen chart (F2).
- Any text in the UI, browser console, or terminal containing `wss://`, `Bearer`, or the token.
- `Reconnect #` reaches 2.
- 15 minutes elapsed.
After the session, close the tab **only after** clicking Stop (F4); if the tab was closed first, restart the Streamlit process.

**Sanitized evidence to collect:** T0 and stop time; screenshots of the chart and the fragment caption at start, after one 5m rollover, and after Stop;
the metrics row values (bootstrap count, stream completed, last trade/heartbeat UTC, reconnect #); the `Connection` state after Stop;
the browser devtools console filtered to errors (expected: none). **Do not collect** terminal output, `.env`, network panel entries for
`api.upstox.com`, or any WebSocket URL.
