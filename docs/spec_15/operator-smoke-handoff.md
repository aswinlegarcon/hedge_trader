# Spec 15 — Operator LIVE smoke handoff (ICICIBANK, read-only)

Date: 2026-11-14 (Saturday, NSE closed). Linux, Python 3.12.3, declared dependencies (`.venv`), `NSL_FORBID_LIVE_MUTATIONS=1`.
Driver: the shipped dashboard (`streamlit run app.py`, loopback port) operated through headless Chromium exactly as an
operator would (mode LIVE, Start, Stop, one restart), capturing only the on-screen status text. Token values, raw broker
responses, authorized WebSocket URLs and server logs were never printed, stored in this repo, or included here; the
driver asserted that every recorded line was free of `wss://`, `Bearer`, authorized-URI and JWT-shaped markers (0 hits),
and the Streamlit server log was scanned for the same markers (0 hits) and discarded.

Runbook followed: `docs/spec_15/handoff.md` → "Operator runbook". Budget: ≤ 10 min streaming / ≤ 15 min wall clock per run.

## Baseline check — shipped revision `0adda3c34242523324d487eef44a73bdb3f2bd94`

| Step | Observation |
|------|-------------|
| Start (LIVE) | `Connection: CONNECTING` at +2 s |
| +4 s | `TRANSPORT_FAILED: Stream transport error.` · `Connection: ERROR` · bars=0 · exchange=UNKNOWN |
| Stop | terminal within 2 s (chart/status cleared) |
| Restart | not attempted (runbook: no retry after a terminal fault) |

**Verdict: AUTH_OR_TRANSPORT_FAILURE (bootstrap).** Root cause established offline and fixed test-first: on a non-trading day
the intraday candle endpoint returns an empty `candles` list, which `parse_candle_response` raises as `UpstoxEmptyError`;
the worker treated any bootstrap exception as terminal and `sanitize_exception` labelled it `TRANSPORT_FAILED`. The feed
was never attempted. Authentication was *not* the cause (an auth failure would have read `FEED_AUTH_FAILED`).

Fix (commit that adds this file): `fetch_intraday_bootstrap` treats an empty candle list as zero bootstrap bars with a
coverage note (`bootstrap: No intraday candles returned (market closed or pre-open)…`), and non-auth bootstrap failures are
reported as `BOOTSTRAP_FAILED` at the call site. Regression tests:
`test_empty_intraday_bootstrap_on_closed_market_is_zero_bars_not_an_error`, `test_non_auth_bootstrap_failure_is_reported_as_bootstrap_failed`.

## Later check — fixed tree (working tree of the same commit; stream code identical to what was committed)

Disclosure: the working tree at that moment also already contained the Spec 16 transport hook (`upstox_transport.py` → `note_response`), so this run recorded a value-free `verified` mark for the environment token in `data/secrets/upstox_auth_state.json`; that is why Settings later shows `connected · source: environment`.

Elapsed 107 s total; streaming held ~90 s deliberately short because the market was closed.

| Step | Observation |
|------|-------------|
| Start (LIVE) | `Connection: CONNECTING` (+2 s) → `Connection: STALE` (+4 s): authorize + WebSocket succeeded, frames arriving |
| Bootstrap | `Bootstrap bars = 0` with coverage note (closed market) — expected |
| Provider status | `exchange=CLOSING_END` (quoted from `market_info`); UI: "Provider reports exchange status CLOSING_END — trades may not arrive. No market calendar is inferred." |
| Price freshness | one last-trade snapshot (Friday's final print) decoded into a single bar; UI: "Price STALE — latest source trade is 77388s old and source time has not advanced for 50s. Not a current price." Source age advanced 2 s per 2 s poll; progress age advanced monotonically. **No fresh price was claimed.** |
| Heartbeat | `Heartbeat (UTC)` populated at connect; `Last trade (UTC)` static (Friday) — correctly separate |
| Reconnects | 0; no gap warning |
| Stop (1) | `Connection: STOPPED` within the 2 s polling step; `Auto-refresh · stopped · bars=1 · … · exchange=CLOSING_END` |
| Restart (the single allowed one) | connected again in 4 s (CONNECTING → STALE) |
| Stop (2) | `STOPPED` within 2 s |
| Browser console | only Streamlit's own relative-path probes on the multipage URL (`/Stream_Chart/_stcore/host-config`, `/Stream_Chart/_stcore/health` → 404); no component errors |
| Secrets | 0 marker hits in captured UI text; 0 in the server log |

**Verdict: CONNECTIVITY_ONLY.** Verified: authorization, WebSocket connection, provider exchange status, source/progress
freshness labelling (stale, truthfully), explicit Stop with worker cleanup, one restart. **Not verified:** fresh-price
display, live candle updates, 5m rollover — the market was closed; none is claimed.

## Not done / limitations

- A trading-hours run is still required to observe `Price FRESH`, chart updates and a natural rollover.
- Headless Chromium drove the real page; screenshots were taken into the session scratch area only (not committed) because they would show the live dashboard only, but the policy here is "no artifacts" until a reviewer asks.
- Both runs used the owner's pre-configured `.env` token; no token value was read, printed or copied by the operator tooling.

## Later checks (Spec 16)

See `docs/spec_16/handoff.md`. Spec 16 did not perform any further LIVE run; the managed-token path was verified with mocked exchanges only.
