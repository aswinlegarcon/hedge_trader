# Spec 15 — Implementation handoff

Status: IMPLEMENTED — offline acceptance complete (2026-11-14). **READY_FOR_OPERATOR_SMOKE.** Not LIVE_VERIFIED: no real
Upstox request was made in this task; the operator smoke is a separate, attended step after review.

## Baseline and delivered revision

- Baseline: `main` @ `e54d418b69bf6218a1b9a03b0299ebd591b95993` (Spec 15 specification), on top of `c969b4e` (Spec 14 readiness review) and `b111e52` (Spec 14 chart fixes).
- Delivered: the single commit that adds this file (child of `e54d418`; `git log -1 --format=%H -- docs/spec_15/handoff.md`). Every result below was produced on that commit's working tree (code and tests identical; only this document and `tasks.md` text were finalized after the last run).

## Changes by requirement

| Req | Change | Files |
|-----|--------|-------|
| R01 | Injected `Clock` (`wall()` UTC for source comparisons, `mono()` for every elapsed measurement). `Freshness` {FRESH, STALE, WAITING, SYNTHETIC} computed at snapshot time: FRESH only if source age ∈ [−2s, 30s] **and** monotonic age since source-time progress ≤ 30s. Heartbeats/market_info never touch trade state. REPLAY is `SYNTHETIC` and bypasses wall-clock admission. | `stream_session.py` (`_freshness_locked`, `_on_frame`), `constants.py` (`SOURCE_FRESH_SECONDS`, `RECEIPT_PROGRESS_SECONDS`, `MAX_FUTURE_SKEW_SECONDS`) |
| R02 | Decoder drops non-finite/non-positive prices and non-positive/overflow timestamps (`MAX_TRADE_TS_MS` = 2100-01-01) and reports a bounded `rejected_ticks` count; undecodable bytes count once. Session rejects trades > receipt UTC + 2s before any book/dedupe/high-water/freshness mutation (`future_ticks_rejected`). `last_trade_ts` never regresses; only genuine source-time progress refreshes the progress clock. Older same-bucket trades extend high/low but keep the newer close; equal timestamps keep Spec 14 arrival order. | `feed_decode.py` (`decode_feed_frame`), `stream_session.py`, `candles.py` (`apply_trade`) |
| R03 | `fetch_authorized_ws_uri` normalizes `UpstoxAuthError` from the real `RequestsTransport` (and returned 401/403) into `FeedAuthError`; unusable 200 payload/URI → new `FeedProtocolError`. Both are non-retryable in the worker; other failures use the one bounded loop (3 reconnects, stop-aware 1/2/4s backoff). Clean-close and exception exhaustion both end in `MAX_RECONNECT` with a safe message and `reconnect_gap=True`. Bootstrap is one attempt. | `transport.py`, `stream_errors.py`, `stream_session.py` (`_worker`, `_exhausted`) |
| R04 | `stop_stream` → `request_stop()` only (no join): sets the generation terminal for frames and retries and returns immediately; effective state `STOPPING` until the worker's `finally` marks `STOPPED`. Bootstrap moved into the worker so Start never does I/O under the registry lock. Late frames from a stopped generation are ignored before any mutation. Bounded transport: `open_timeout=10`, `close_timeout=1`, recv poll 0.5s, requests 3s/10s. | `stream_session.py`, `transport.py`, `constants.py` |
| R05 | Unguessable `session_id` (uuid4 hex) as generation; `keepalive(owner, session_id)` renews only for the current owner/generation of a live, non-stopping session; snapshots never renew. Per-session bounded lease monitor (default 20s lease, 2s check) expires an abandoned owner without any registry call, requests stop and exits. Conflict responses carry `book=None` and only the requester's own token. Session lock + registry lock with documented ordering; no lock held across I/O. | `stream_session.py` (`SessionPolicy`, `_lease_monitor`, `keepalive`, `_owns`) |
| R06 | Status, faults, freshness (with ages), exchange status, stopping/expired state, metrics and the chart all render inside the 1 Hz `st.fragment`; the fragment renews the owner lease while displayed. Pure `status_lines(snapshot)` view model. Stale main-body `Connection` metric and duplicate Stop-time chart render removed. | `ui.py` |
| R07 | Loopback `websockets` server tests drive the production `LiveWebSocketTransport` (real connect/send/recv/close, real generated protobuf). Test seam `allow_loopback_ws=True` accepts `ws://127.0.0.1`/`ws://localhost` only; production requires `wss://`. | `transport.py`, `tests/test_spec15_loopback_ws.py` |
| R08 | Dedicated transport logger `nifty_lab.stream_chart.transport.ws` passed to `connect`: `propagate=False`, level WARNING, NullHandler — handshake request lines/headers are never emitted at DEBUG, regardless of root/`websockets` levels. App logs stay enabled. | `transport.py` |
| R09 | `requests>=2.31`, `websockets>=13.0,<18`, `protobuf>=7.36.2,<8` declared in both `pyproject.toml` and `requirements.txt`; `loopback` pytest marker registered. Clean Python 3.12 venv built from `requirements.txt` and verified (below). | `pyproject.toml`, `requirements.txt` |

## Scenario → test → result

All offline results from `TMPDIR=/tmp/pytest_hedge .venv/bin/python3.12 -m pytest -q <module>` with `NSL_FORBID_LIVE_MUTATIONS=1`.
Modules: **A** `tests/test_spec15_live_reliability.py` (34 passed), **B** `tests/test_spec15_loopback_ws.py` (6 passed, `loopback` marker),
**C** `tests/test_spec14_live_readiness.py` (14 passed), **D** `tests/test_spec14_stream_chart.py` (14 passed), **E** `tests/test_spec14_browser_acceptance.py` (3 passed ×3 runs).

| Scenario | Test(s) | Result |
|----------|---------|--------|
| S01 | A `test_s01_hour_old_trade_received_now_is_stale_with_source_age`; C `test_old_trade_received_now_is_not_reported_fresh` | pass |
| S02 | A `test_s02_heartbeats_never_make_price_fresh_and_fresh_expires_after_30s`; C `test_heartbeat_alone_never_implies_fresh_prices` | pass |
| S03 | A `test_s03_stationary_or_older_source_data_does_not_extend_progress_freshness` | pass |
| S04 | A `test_s04_wall_clock_jump_does_not_extend_monotonic_receipt_freshness` (injected clocks, threshold boundaries) | pass |
| S05 | A `test_s05_replay_is_synthetic_offline_and_keeps_its_historic_fixture`; D `test_replay_start_stop_offline`, `test_apptest_page14_load_and_replay` | pass |
| S06 | A `test_s06_future_tick_rejected_without_poisoning_state`; C `test_future_trade_is_rejected_and_does_not_poison_later_ticks` | pass |
| S07 | A `test_s07_invalid_timestamps_and_prices_rejected_at_decoder_without_crash` ×8 (ltt 0/−1/2⁶³−1/overflow, ltp 0/−1/inf/nan), `test_s07_missing_feed_fields_rejected` | pass |
| S08 | A `test_s08_older_intra_bucket_tick_extends_high_low_but_keeps_newest_close`; D `test_late_tick_acceptance_timeline`, `test_same_millisecond_distinct_prices` | pass |
| S09 | A `test_s09_authorize_401_403_through_production_transport_is_single_attempt_non_retryable` ×2, `test_s09_bootstrap_401_is_single_attempt_without_authorize_or_connect`; B `test_s21_authorize_rejection_never_reaches_the_socket` (no connect: 0 handshakes); C auth tests | pass |
| S10 | A `test_s10_malformed_authorize_payload_is_non_retryable_protocol_error` ×4, `test_s10_temporary_server_failure_uses_only_the_bounded_reconnect_loop` | pass |
| S11 | A `test_s11_clean_close_and_exception_exhaustion_share_budget_and_category` ×2; C `test_reconnect_budget_is_per_session_lifetime_with_consistent_category` | pass |
| S12 | A `test_s12_stop_during_blocking_call_returns_fast_and_worker_terminates_within_budget`, `test_s12_stop_during_receive_and_backoff_terminates_within_two_seconds`; C `test_stop_during_blocking_authorize_returns_immediately_then_releases_owner`, `test_stop_during_active_receive_exits_promptly`; D `test_stop_during_backoff` | pass |
| S13 | A `test_s13_stopping_blocks_overlapping_start_and_stopped_requires_termination` | pass |
| S14 | A `test_s14_delayed_callback_from_old_generation_is_ignored` | pass |
| S15 | A `test_s15_abandoned_owner_expires_autonomously_and_slot_becomes_reusable`; C `test_vanished_browser_session_expires_and_releases_owner` | pass |
| S16 | A `test_s16_keepalives_preserve_ownership_and_wrong_owner_cannot_renew_or_release`; D `test_owner_conflict_not_preemptive`, `test_snapshot_requires_owner` | pass |
| S17 | A `test_s17_repeated_cycles_leave_no_workers_and_concurrent_access_is_consistent`; B `test_s20…` (socket fd baseline restored) | pass |
| S18 | A `test_s18_status_lines_report_stale_waiting_stopping_fault_and_exchange_without_calendar_claims`; E `test_streamlit_shipped_pacing_updates_and_restarts` (state changes to `stopped` observed in the fragment with no click); D AppTest | pass |
| S19 | E `test_component_apply_bars_matches_bounded_window`, `test_streamlit_replay_chart_matches_server_candles`, `test_streamlit_shipped_pacing_updates_and_restarts` — assertions read actual `series.data()` | pass ×3 runs |
| S20 | B `test_s20_production_client_subscribes_decodes_and_closes_on_stop` | pass |
| S21 | B `test_s21_disconnect_then_reconnect_uses_production_lifecycle`, `test_s21_authorize_rejection_never_reaches_the_socket`, `test_s21_handshake_rejection_is_bounded_and_classified` | pass |
| S22 | B `test_s22_debug_logging_everywhere_leaks_no_token_or_authorized_uri` ×2 (successful setup and 403 handshake) | pass |
| S23 | clean venv procedure below: import, fixture decode, modules A+B+C+D → 68 passed | pass |
| S24 | C: former F1 `test_old_trade_received_now_is_not_reported_fresh`, F2 `test_future_trade_is_rejected_and_does_not_poison_later_ticks`, F3 `test_authorize_401_through_production_transport_does_not_retry`, F4 `test_vanished_browser_session_expires_and_releases_owner` — all plain passing tests; the repo has no xfail or skip in Spec 14/15 modules | pass |
| S25 | this document | — |

## Freshness / state table and clock policy

Internal transport state (`StreamSession.state`) × freshness → displayed `ConnectionState`:

| Transport | Freshness (LIVE) | Displayed | UI text |
|-----------|------------------|-----------|---------|
| CONNECTING / RECONNECTING | — | same | "Connection: CONNECTING/RECONNECTING" (+ gap warning after a reconnect) |
| link up (frames observed) | WAITING (no accepted trade) | WAITING_FOR_DATA | info: "Connected, waiting for the first trade · provider exchange status: X"; warning if X ∉ {NORMAL_OPEN, UNKNOWN} — no calendar inference |
| link up | FRESH | STREAMING | caption: "Price FRESH · source age Ns · no newer source time for Ms" |
| link up | STALE | STALE | warning: "Price STALE — … Not a current price." |
| any non-terminal, stop requested | — | STOPPING | warning: Start blocked until the worker finishes |
| worker exited after Stop | — | STOPPED | caption |
| worker exited after lease expiry | — | OWNER_EXPIRED | warning + fault OWNER_EXPIRED, "Press Start to resume" |
| terminal failure | — | ERROR | error: `CODE: safe message` (FEED_AUTH_FAILED, FEED_AUTHORIZE_INVALID, BOOTSTRAP_FAILED, MAX_RECONNECT, TRANSPORT_FAILED) |
| REPLAY link up | SYNTHETIC | STREAMING | caption: "REPLAY · synthetic fixture timeline — no price-freshness claim." |

Clock policy: `clock.wall()` only for source-time comparisons (future skew, source age); `clock.mono()` for progress age, lease age, idle purge and backoff waits. Source age in [−2, 0] is clamped to 0 for display. Heartbeats set `last_heartbeat_ts`/`exchange_status` only.

## Lifecycle, lease and lock strategy; measured bounds

- Locks: registry `_OWNER_LOCK` guards the `_ACTIVE` pointer only; `StreamSession._lock` guards session fields and the book. Registry → session lock order only; no lock is held across HTTP, WebSocket I/O, joins, sleeps or bootstrap. Frame callback, snapshot, Stop and monitor were raced in A `test_s17…` (2 feeders, 3 readers, concurrent stop): no errors, no partial snapshots.
- Threads per session: one I/O worker (bootstrap → connect loop) and one lease monitor (exits on stop or worker death). Both are counted by `worker_threads_alive()`; every lifecycle test asserts 0 at the end.
- Measured on a real loopback WebSocket (default policy, this machine):

| Measurement | Result | Budget |
|---|---|---|
| `stop_stream` return during active receive | 0.2 ms | 250 ms |
| worker + monitor terminated after Stop (receive) | 5 ms; server observed close in 20 ms | 2 s |
| `stop_stream` return during an uninterruptible 3 s call | 0.2 ms, state `stopping`; worker ended 2.80 s later | 20 s (requests 3 s connect + 10 s read ≤ 13 s; ws open 10 s) |
| lease expiry → all workers gone (1 s lease, production 2 s monitor, no registry call) | 1.98 s, final `owner_expired` | lease + 2 s + 20 s |

Budgets are acceptance bounds under controlled tests, not real-time guarantees under OS/network failure.

## Real loopback WebSocket protocol evidence (B)

Production client → loopback `websockets.asyncio.server`: authorize via real `RequestsTransport` (fake `requests.Session`, dummy token, `ws://127.0.0.1:<port>/feed/<marker>?token=<marker>`), then real `connect` with `open_timeout=10`, `close_timeout=1`, pings 20/20, logger injected. Server observed exactly one **binary** subscribe frame `{"guid":"nsl-spec14","method":"sub","data":{"mode":"ltpc","instrumentKeys":["NSE_EQ|INE090A01021"]}}`, served schema-encoded `market_info` + `ltpc` frames that the session decoded into a forming bar (close 102.0), saw the client close on Stop, and the process socket fd count returned to baseline. Server-initiated close after 2 frames produced one authorize + one subscribe per connection, `reconnect_attempt ≥ 1`, `reconnect_gap=True`, and `MAX_RECONNECT` after exactly 1 + 3 connections. Authorize 401 → 0 handshakes; handshake 403 → 4 handshakes, `MAX_RECONNECT`.

## Clean install (S23)

```bash
/usr/bin/python3.12 -m venv /tmp/pytest_hedge/clean-venv
/tmp/pytest_hedge/clean-venv/bin/pip install -r requirements.txt
export NSL_FORBID_LIVE_MUTATIONS=1
TMPDIR=/tmp/pytest_hedge /tmp/pytest_hedge/clean-venv/bin/python -m pytest -q \
  tests/test_spec15_loopback_ws.py tests/test_spec15_live_reliability.py \
  tests/test_spec14_stream_chart.py tests/test_spec14_live_readiness.py      # 68 passed
```

Python 3.12.3. Resolved: `streamlit==1.67.0`, `websockets==17.4`, `protobuf==7.36.2`, `requests==2.34.2`, `pandas==3.1.1`, `numpy==2.5.4`, `pytest==9.2.0`, `python-dotenv==1.2.4`.
Protobuf: the vendored `MarketDataFeedV3_pb2.py` validates runtime ≥ 7.36.2 (same major); declared `protobuf>=7.36.2,<8` resolves to 7.36.2 and the fixture decodes (`live_feed`×4, `market_info`×1, 4 ticks). Streamlit ≥ 1.38 keeps `st.fragment(run_every=…)` (present since 1.37); verified on 1.67.0 only. Playwright is a dev extra (`pip install -e .[dev]` or `pip install playwright && playwright install chromium`) and is not needed for the clean-install checks.

## Browser repeatability and final full suite

- `tests/test_spec14_browser_acceptance.py` run 3 consecutive times against the committed UI at **shipped** REPLAY pacing (the third test uses the unpatched server; the first two also run under the slowed server for the mid-stream zoom case): 3 passed / 3 passed / 3 passed.
- Final full suite on the delivered tree: `372 passed, 1 skipped in 38.48s` (`TMPDIR=/tmp/pytest_hedge .venv/bin/python3.12 -m pytest --tb=short -ra tests`). The single skip is pre-existing and unrelated: `tests/test_spec10_paper_account.py:161: no local paper db`. Previous baseline was 317 passed; +55 tests from Spec 15 modules and converted Spec 14 regressions.

## Secret handling and scope confirmation

- Token read from `os.environ` only (`.env` via `python-dotenv`, `override=False`); tests inject dummy markers through the environment and never read `.env`. No test printed or asserted on a real value.
- S22: with root, `websockets`, `urllib3` and `nifty_lab` loggers at DEBUG, captured records, snapshot reprs, fault messages and chart payloads contained none of the dummy token / authorized-path / query markers, for both successful setup and a 403 handshake. (pytest attaches its capture handler to non-propagating loggers too, so the production logger's WARNING level gate — not just `propagate=False` — is what keeps handshake lines out.)
- No broker request, order, ledger write, strategy/backtest change or 2025 holdout access occurred. `NSL_FORBID_LIVE_MUTATIONS=1` for every run.

## Remaining limitations

- **LIVE is unverified.** Only loopback compatibility is proven; Upstox-specific behaviour (control frames, close codes, token lifetime) is untested until the operator smoke.
- `websockets` declared `>=13.0,<18`; verified on 17.4 only (the `websockets.asyncio` client API used exists from 13.0 per upstream docs).
- Stop cannot interrupt an in-flight `requests` call or WebSocket open handshake; it is bounded by their timeouts (≤ 13 s and 10 s). The UI reports STOPPING meanwhile.
- Reconnect budget (3) is per session lifetime, by design; a long-running LIVE session with 4 drops ends in `MAX_RECONNECT` and needs a manual Start.
- After a LIVE Stop the terminal session (and its chart) stays visible until a new Start or the 120 s idle purge; a REPLAY Stop clears immediately because its worker is already finished.
- Source age is inherently wall-clock based; only progress/lease/backoff are monotonic.
- Browser tests require network access to the pinned Lightweight Charts CDN and an installed Chromium.
- The `Chart instance` caption from Spec 14 (never visible) was dropped; the component value round-trip still populates `session_state`.

## Verdict

**READY_FOR_OPERATOR_SMOKE** — every normative scenario S01–S25 has a passing automated test or recorded evidence; no xfail/skip hides any of them. Not LIVE_VERIFIED.

## Operator runbook (to be executed only after reviewer acceptance; not performed in this task)

Preconditions: one attended operator, one browser tab, this `requirements.txt` environment, fresh `UPSTOX_ACCESS_TOKEN` in local `.env` (never pasted elsewhere), `NSL_FORBID_LIVE_MUTATIONS=1`, default logging (no DEBUG). Validate market availability from the page's provider exchange status, not from the weekday. **Max 10 minutes streaming / 15 minutes wall clock.**

```bash
export NSL_FORBID_LIVE_MUTATIONS=1
.venv/bin/python3.12 -m streamlit run app.py
```

1. Open page **14 Stream Chart**, select **LIVE**, note T0, click **Start stream** once.
2. Expect within ~15 s: `Connection: CONNECTING` → `WAITING_FOR_DATA` or `STREAMING`; `Bootstrap bars` > 0; if the provider status is not `NORMAL_OPEN`, the page says so and waiting is expected — do not extend the test to wait for the market.
3. While trading: `Price FRESH · source age ≤ 30s`; `Last trade (UTC)` advancing; `Reconnect #` 0 (≤ 1 with the gap warning); a 5m rollover appends one bar if it happens naturally — do not lengthen the run to force one.
4. Click **Stop stream** once. Expect `STOPPING` for at most a few seconds, then `STOPPED`, no error banner, Start available again.
5. Optional once: Start → `STREAMING`/`WAITING_FOR_DATA` within ~15 s → Stop.

Abort (click Stop; if the page is unresponsive > 15 s, Ctrl-C the Streamlit process) on: any `FEED_AUTH_FAILED` / `FEED_AUTHORIZE_INVALID` / `MAX_RECONNECT` banner (verify the token locally; retry at most once); `Price STALE` persisting > 2 minutes while the provider says `NORMAL_OPEN`; `future_rejected` or `invalid_rejected` climbing; `OWNER EXPIRED` while the tab was open; any `wss://`, `Bearer` or token text anywhere; 15 minutes elapsed.

Sanitized evidence: T0 and stop time; screenshots of the fragment status block and chart at start, mid-run and after Stop; the metrics row; the final `Connection` state; browser console filtered to errors (expected none). Never collect terminal output, `.env`, network panel entries for `api.upstox.com`, or any WebSocket URL.
