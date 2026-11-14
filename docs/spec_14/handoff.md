# Spec 14 — Handoff (stream chart prototype)

**Status:** IMPLEMENTED (initial + acceptance corrections). Ready for next agent / operator review.

## Scope delivered

- Page **14_Stream_Chart** — ICICIBANK `NSE_EQ|INE090A01021`, 5m, read-only
- **REPLAY** default: offline `replay_fixture` (bootstrap + paced feed, zero HTTP/token/WSS)
- **LIVE**: `RequestsTransport()` only when user selects LIVE (authorize + WebSocket server-side)
- `nifty_lab/stream_chart/` — candles, decode, session owner, LWC custom component (`frontend/index.html`)
- Apache-2.0 **NOTICE** in UI + `docs/spec_14/NOTICE_LIGHTWEIGHT_CHARTS.md`

## Findings → tests

| Finding | Test |
|---------|------|
| `HttpTransport()` Protocol breaks AppTest | `test_apptest_page14_load_and_replay` |
| REPLAY must not HTTP bootstrap | `test_replay_start_stop_offline`, AppTest `http_calls == []` |
| Late tick / duplicate bar times | `test_late_tick_acceptance_timeline` |
| Same-ms distinct prices | `test_same_millisecond_distinct_prices` |
| Owner must not be preempted | `test_owner_conflict_not_preemptive`, `test_snapshot_requires_owner` |
| Sanitized errors (no WSS in UI) | `test_sanitize_hides_wss_uri`, `test_auth_failure_typed_no_retry` |
| Heartbeat ≠ trade freshness | `test_heartbeat_does_not_refresh_trade` |
| Stop interrupts backoff | `test_stop_during_backoff` |
| Bounded dedupe | `test_bounded_dedupe_memory` |
| Persistent chart updates | `test_playwright_persistent_chart_updates` + `tests/fixtures/lwc_harness.html` |

## Commands & results (last verified)

```bash
export NSL_FORBID_LIVE_MUTATIONS=1
mkdir -p /tmp/pytest_hedge

# Prefer python3.12 if macOS blocks .venv/bin/python (Documents TCC)
TMPDIR=/tmp/pytest_hedge .venv/bin/python3.12 -m pytest -q tests/test_spec14_stream_chart.py    # 15 passed
TMPDIR=/tmp/pytest_hedge .venv/bin/python3.12 -m pytest --tb=no -ra tests                  # 317 passed
```

Playwright (optional dev dep — needs network for unpkg CDN in harness):

```bash
.venv/bin/python3.12 -m pip install 'playwright>=1.49'
.venv/bin/python3.12 -m playwright install chromium
TMPDIR=/tmp/pytest_hedge .venv/bin/python3.12 -m pytest -q \
  tests/test_spec14_stream_chart.py::test_playwright_persistent_chart_updates
```

## Verified (automated)

- Full suite green with `NSL_FORBID_LIVE_MUTATIONS=1`
- Offline REPLAY AppTest journey on page 14
- Playwright harness: stable chart `instanceId`, rollover, zoom range, reset (after harness/test fixes)

## Not verified (operator only)

- **LIVE** Upstox Feed V3 during market hours (`streamlit run app.py` → LIVE + local token)
- **Real Streamlit component iframe** persistence (AppTest mocks `render_candlestick_chart`; harness covers JS update contract)

## Prior specs (same repo)

Specs **03–13** code and handoffs are included in this commit slice; see respective `docs/spec_* /handoff.md`. Paper workflow acceptance: `docs/spec_13/handoff.md`.

## Next agent — suggested reads

1. `docs/spec_14/design.md`, `requirements.md`, `tasks.md`
2. `nifty_lab/stream_chart/stream_session.py` (ownership, REPLAY vs LIVE)
3. `docs/BACKLOG.md` (streaming hardening still backlog)

## Constraints (unchanged)

`NSL_FORBID_LIVE_MUTATIONS=1` for tests/agents. No broker order placement. No commits that add `.env` or credentials.