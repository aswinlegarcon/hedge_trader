# Spec 14 — Handoff (stream chart prototype)

**Status:** IMPLEMENTED + browser-accepted (2026-11-14). Chart retention and real-Streamlit acceptance closed. Ready for operator review.

## Scope delivered

- Page **14_Stream_Chart** — ICICIBANK `NSE_EQ|INE090A01021`, 5m, read-only
- **REPLAY** default: offline `replay_fixture` (bootstrap + paced feed, zero HTTP/token/WSS)
- **LIVE**: `RequestsTransport()` only when user selects LIVE (authorize + WebSocket server-side)
- `nifty_lab/stream_chart/` — candles, decode, session owner, LWC custom component (`frontend/index.html`)
- Apache-2.0 **NOTICE** in UI + `docs/spec_14/NOTICE_LIGHTWEIGHT_CHARTS.md`

## 2026-11-14 retention / acceptance pass — findings and fixes

All three findings were reproduced against the **production component served by a real Streamlit server** in Chromium
(`tests/test_spec14_browser_acceptance.py`), then fixed test-first. Files touched: `frontend/index.html`, `lwc.py`,
two test modules, this handoff. No session, candle, transport, UI, ledger or strategy code changed.

| # | Finding (reproduced) | Root cause | Fix |
|---|----------------------|------------|-----|
| 1 | Rolling window out of sync: `applyBars([1,2,3,4])` then `applyBars([2,3,4,5])` left `series.data()` = `[1,2,3,4,5]` while Python reported `[2,3,4,5]`. | `applyBars` used `series.update()` for same-length and grown arrays. `update()` can only edit/append the last bar; it can never drop the bar that left the bounded window, and for multi-bar appends it skipped intermediate bars. | `applyBars` now calls `series.setData(bars)` on every render. The Python `CandleBook` already owns the bounded window (`MAX_RETAINED_BARS`), so append, multi-append, constant-length rolling, shrink, clear, reset and restart are all exact. Lightweight Charts keeps bar spacing and right offset across `setData`, so the user viewport survives (verified, see below). Dead `reset` kwarg removed from `lwc.render_candlestick_chart`. |
| 2 | Component **never rendered inside real Streamlit**. Two uncaught frontend errors on load: `Unexpected token 'export'` and `Cannot read properties of undefined (reading 'events')`. | `index.html` loaded `streamlit-component-lib@2.0.0/dist/index.js` from unpkg with a plain `<script>` tag; that file is an ES module (`export …`), so the script failed to parse, `window.Streamlit` stayed undefined, `componentReady` was never sent and Streamlit never sent render args. The previous "Playwright harness" was a hand copy of `applyBars` that bypassed the bridge entirely, so this was invisible to it. | Replaced the CDN lib with an inline ~10-line bridge speaking the stable v1 postMessage protocol (`streamlit:componentReady`, `streamlit:render`, `streamlit:setComponentValue`, `streamlit:setFrameHeight`). One fewer CDN dependency. |
| 3 | Chart iframe had `height: 0` in real Streamlit (bounding box `{width: 704, height: 0}`) — invisible even once the bridge worked. | Component never reported its frame height; Streamlit keeps a component iframe at 0px until it does. | `post("streamlit:setFrameHeight", { height: document.body.scrollHeight })` after every render. Iframe now ≥ 400px; `chart.paneSize()` ≈ 1234×412 on a 1280px viewport. |

### Zoom-width assertion failure (reported `from=-104,to=1` → `from=1,to=2`): **test timing, not chart behavior**

Measured in the production component: `timeScale().applyOptions({barSpacing})` and `setVisibleLogicalRange()` are applied
on the chart's **next animation frame**. A synchronous read right after the zoom call returns the stale pre-zoom range
(`options().barSpacing` also still reads the old value), so the "initial" baseline was the un-zoomed width
(≈ paneWidth / 6 ≈ 105 bars) and the "later" read was the applied zoom plus the normal right-anchored one-bar shift when a bar
is appended while the latest bar is visible (`shiftVisibleRangeOnNewBar`, default on). After the zoom is applied, width is
preserved exactly across append and roll (measured 3 → 3 and 50.4167 → 50.4167 logical bars; bar spacing unchanged).

Deterministic readiness used by the tests instead of sleeps: `wait_for_function(() => timeScale().options().barSpacing === 24)`
before taking the baseline; `wait_for_function` on `series.data()` deep-equal to the expected candles before asserting state.
Zoom-preservation coverage was kept and strengthened (both the Streamlit render path and direct `applyBars` path).

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
| Chart data == bounded window (append, multi-append, rolling, shrink, clear, reset, restart) + zoom preserved | `test_component_apply_bars_matches_bounded_window` (production `index.html` served by real Streamlit, direct `applyBars`) |
| Real Streamlit REPLAY: `series.data()` == server candles, same `instanceId` across ≥2 renders, visible iframe, zoom preserved across data-changing renders, stop unmounts, restart exact, zero page/console errors | `test_streamlit_replay_chart_matches_server_candles` |

Removed: `test_playwright_persistent_chart_updates` and `tests/fixtures/lwc_harness.html` (a drifted copy of `applyBars`
that never loaded the Streamlit bridge; superseded by the two tests above, which exercise the shipped file).

### How the browser acceptance test works

- Module fixture starts `streamlit run pages/14_Stream_Chart.py` (headless, random port, `NSL_FORBID_LIVE_MUTATIONS=1`,
  file watcher off) through a one-line launcher that sets `stream_session.REPLAY_FRAME_DELAY_SEC = 2.0` **in the test
  server process only**. Production pacing (0.4s) converges ~1s after the first render, too narrow to zoom mid-stream
  deterministically; the test asserts the premise (`series != expected` at first render) so a blown margin fails loudly
  instead of passing silently. Page, component and session code are not modified.
- Expected candles are computed in-test from the same REPLAY fixture via `CandleBook` (bootstrap + every ltpc tick), and
  compared with the browser's actual `series.data()` — not with `lastBars`/component-value echoes.
- `page.on("pageerror")` and `console.error` from every frame are collected; both tests assert the list is empty.

## Commands & results (verified 2026-11-14)

```bash
export NSL_FORBID_LIVE_MUTATIONS=1
mkdir -p /tmp/pytest_hedge

# one-time (venv has no pip; uv is available)
uv pip install --python .venv/bin/python3.12 'playwright>=1.49'
.venv/bin/python3.12 -m playwright install chromium

TMPDIR=/tmp/pytest_hedge .venv/bin/python3.12 -m pytest -q tests/test_spec14_browser_acceptance.py   # 2 passed
TMPDIR=/tmp/pytest_hedge .venv/bin/python3.12 -m pytest -q tests/test_spec14_stream_chart.py         # 14 passed
TMPDIR=/tmp/pytest_hedge .venv/bin/python3.12 -m pytest --tb=short -ra tests                         # 317 passed, 1 skipped
```

- Full suite: `317 passed, 1 skipped in 25.90s` (skip = `test_spec10_paper_account.py:161: no local paper db`, pre-existing).
- Browser repeatability: 3 consecutive runs of `tests/test_spec14_browser_acceptance.py`, all green; end-to-end test
  13.44s / 13.48s / 13.46s, matrix test 1.26s / 1.34s / 1.03s. Then one more run after the final tidy: 16 passed
  (both Spec 14 modules).
- RED steps were observed before each fix: `[1,2,3,4,5] != [2,3,4,5]`; two `pageerror`s; iframe `height: 0`.

## Not verified (operator only)

- **LIVE** Upstox Feed V3 during market hours (`streamlit run app.py` → LIVE + local token). Not touched by this pass.
- Browser tests need network for the pinned Lightweight Charts CDN script (the only remaining CDN dependency).

## Known limitations (pre-existing, not changed — no new features)

- After REPLAY ends the fragment keeps rerunning at 1 Hz until **Stop**; Streamlit sends no render when args are unchanged, so `updateCount` stops advancing (expected).
- **Stop** unmounts the chart (session purged → `active_snapshot()` is `None`), so a restart is a fresh iframe/instance by design; the test asserts the restart has exactly the server candles with unique ascending times.
- The "Chart instance …" caption in the main body never shows: the fragment writes `session_state` but the main script only reruns on button clicks, when the snapshot is gone. Cosmetic.
- Viewport semantics with a sliding window: `setData` keeps the logical range anchored to the right edge, so when the oldest bar drops, a user scrolled far left sees the view drift by one bar. Acceptable for a 500-bar window; revisit if a wider window or left-edge browsing is required.

## Prior specs (same repo)

Specs **03–13** code and handoffs are in the repo; see respective `docs/spec_*/handoff.md`. Paper workflow acceptance: `docs/spec_13/handoff.md`.

## Next agent — suggested reads

1. `docs/spec_14/design.md`, `requirements.md`, `tasks.md`
2. `nifty_lab/stream_chart/frontend/index.html` (bridge + `applyBars`), `tests/test_spec14_browser_acceptance.py`
3. `nifty_lab/stream_chart/stream_session.py` (ownership, REPLAY vs LIVE)
4. `docs/BACKLOG.md` (streaming hardening still backlog)

## Constraints (unchanged)

`NSL_FORBID_LIVE_MUTATIONS=1` for tests/agents. No broker order placement. No commits that add `.env` or credentials.
