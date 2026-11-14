"""Spec 14 — browser acceptance: the production LWC component inside real Streamlit (REPLAY, zero broker I/O).

Requires the optional dev deps: ``playwright`` + ``playwright install chromium`` and network access for the
pinned unpkg CDN script(s) that ``nifty_lab/stream_chart/frontend/index.html`` loads.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from nifty_lab.stream_chart.candles import CandleBook
from nifty_lab.stream_chart.feed_decode import decode_feed_message
from nifty_lab.stream_chart.replay_fixture import ui_demo_scenario

pytest.importorskip("playwright.sync_api", exc_type=ImportError)
from playwright.sync_api import expect, sync_playwright  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / "pages" / "14_Stream_Chart.py"
COMPONENT = "nifty_lab.stream_chart.lwc.nsl_spec14_lwc"
IFRAME = f'iframe[title="{COMPONENT}"]'
SLOT = "window.__nslLwc_spec14"
SERIES = f"{SLOT}.series.data().map(b => [b.time, b.open, b.high, b.low, b.close])"
TIMES = f"{SLOT}.series.data().map(b => b.time)"
LOGICAL_WIDTH = f"() => {{ const r = {SLOT}.chart.timeScale().getVisibleLogicalRange(); return r.to - r.from; }}"
# Production pacing (0.4s/frame) converges ~1s after the first render, too tight to zoom deterministically
# mid-stream, so the test server slows the fixture clock only. The page, component and session code are untouched.
REPLAY_FRAME_DELAY_SEC = 2.0
LAUNCHER = (
    "import sys; import nifty_lab.stream_chart.stream_session as ss;"
    f" ss.REPLAY_FRAME_DELAY_SEC = {REPLAY_FRAME_DELAY_SEC};"
    " sys.argv = ['streamlit', 'run', *sys.argv[1:]]; from streamlit.web.cli import main; main()"
)
MATCHES = "(exp, act) => act.length === exp.length && act.every((b, i) => b.every((v, j) => Math.abs(v - exp[i][j]) < 1e-9))"


def expected_replay_series() -> list[list[float]]:
    """Same candles the server derives from the REPLAY fixture (bootstrap + every ltpc tick)."""
    scenario = ui_demo_scenario()
    book = CandleBook()
    book.load_replay_bootstrap(scenario.bootstrap)
    for raw in scenario.frames:
        _type, ticks, _info = decode_feed_message(raw)
        for tick in ticks:
            book.apply_trade(price=tick.price, trade_ms=int(tick.trade_ts_utc.timestamp() * 1000))
    return [[r["time"], r["open"], r["high"], r["low"], r["close"]] for r in book.chart_series()]


def _start_streamlit(tmp_path_factory, prefix: list[str]):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    log = (tmp_path_factory.mktemp("streamlit") / "server.log").open("w")
    proc = subprocess.Popen(
        [*prefix, str(PAGE), "--server.headless", "true",
         "--server.address", "127.0.0.1", "--server.port", str(port),
         "--server.fileWatcherType", "none", "--browser.gatherUsageStats", "false"],
        cwd=PROJECT_ROOT, env={**os.environ, "NSL_FORBID_LIVE_MUTATIONS": "1"}, stdout=log, stderr=log,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            if urllib.request.urlopen(f"{url}/_stcore/health", timeout=1).read() == b"ok":
                break
        except OSError:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail(f"streamlit did not become healthy; see {log.name}")
    yield url
    proc.terminate()
    proc.wait(timeout=15)
    log.close()


@pytest.fixture(scope="module")
def streamlit_url(tmp_path_factory):
    """Real Streamlit, REPLAY pacing slowed to 2.0s/frame (test server only) for the mid-stream zoom test."""
    yield from _start_streamlit(tmp_path_factory, [sys.executable, "-c", LAUNCHER])


@pytest.fixture(scope="module")
def streamlit_url_shipped(tmp_path_factory):
    """Real Streamlit exactly as shipped: production REPLAY pacing, no patches."""
    yield from _start_streamlit(tmp_path_factory, [sys.executable, "-m", "streamlit", "run"])


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    pg = browser.new_page()
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    pg.on("console", lambda m: errors.append(f"console.error: {m.text} @ {m.location.get('url')}") if m.type == "error" else None)
    yield pg, errors
    pg.close()


def wait_component_frame(pg):
    return pg.wait_for_selector(IFRAME, state="attached", timeout=30_000).content_frame()


def test_component_apply_bars_matches_bounded_window(streamlit_url, page):
    """Drive the production applyBars (served by the real Streamlit server) through every window shape."""
    pg, errors = page
    pg.goto(streamlit_url)  # a script run registers the component with the server
    expect(pg.get_by_role("button", name="Start stream")).to_be_visible(timeout=30_000)
    pg.goto(f"{streamlit_url}/component/{COMPONENT}/index.html")
    pg.wait_for_function("typeof ensureChart === 'function' && typeof applyBars === 'function'")
    pg.evaluate("() => ensureChart()")

    def apply(times: list[int]) -> list[int]:
        bars = [{"time": t, "open": 1, "high": 2, "low": 0.5, "close": 1.5} for t in times]
        return pg.evaluate(f"(bars) => {{ applyBars({SLOT}, bars); return {TIMES}; }}", bars)

    assert apply([1, 2, 3, 4]) == [1, 2, 3, 4]  # initial load
    assert apply([2, 3, 4, 5]) == [2, 3, 4, 5]  # reported probe: constant-length rolling window
    assert apply([2, 3, 4, 5, 6]) == [2, 3, 4, 5, 6]  # append one
    assert apply([2, 3, 4, 5, 6, 7, 8]) == [2, 3, 4, 5, 6, 7, 8]  # append several at once
    assert apply([3, 4, 5, 6, 7, 8, 9]) == [3, 4, 5, 6, 7, 8, 9]  # roll again
    assert apply([5, 6, 7, 8, 9]) == [5, 6, 7, 8, 9]  # shrink from the left
    assert apply([5, 6, 7]) == [5, 6, 7]  # shrink from the right
    assert apply([]) == []  # clear
    assert apply([10, 11]) == [10, 11]  # reset after clear
    assert apply([20, 21, 22]) == [20, 21, 22]  # restart: wholesale replacement, no leftovers

    # User zoom (bar spacing + logical width) must survive append and roll. Lightweight Charts applies
    # time-scale options on its next animation frame, so wait for that instead of reading synchronously.
    pg.evaluate(f"() => {SLOT}.chart.timeScale().applyOptions({{barSpacing: 24}})")
    pg.wait_for_function(f"() => {SLOT}.chart.timeScale().options().barSpacing === 24")
    width0 = pg.evaluate(LOGICAL_WIDTH)
    assert width0 > 1
    assert apply([20, 21, 22, 23]) == [20, 21, 22, 23]
    assert apply([21, 22, 23, 24]) == [21, 22, 23, 24]
    assert pg.evaluate(f"() => {SLOT}.chart.timeScale().options().barSpacing") == 24
    assert abs(pg.evaluate(LOGICAL_WIDTH) - width0) < 1e-6
    assert errors == []


def test_streamlit_replay_chart_matches_server_candles(streamlit_url, page):
    """Click-driven REPLAY inside real Streamlit: actual series.data() == server candles, same chart instance
    across renders, visible iframe, user zoom preserved across data-changing renders, clean stop/restart,
    zero frontend errors."""
    pg, errors = page
    expected = expected_replay_series()
    pg.goto(streamlit_url)
    pg.get_by_role("button", name="Start stream").click()
    frame = wait_component_frame(pg)
    frame.wait_for_function(f"() => {SLOT} && {SLOT}.updateCount >= 1", timeout=30_000)
    inst0, early = frame.evaluate(f"() => [{SLOT}.instanceId, {SERIES}]")
    assert early != expected, "REPLAY converged before the first render; slow the fixture pacing"

    # The user zooms while bars are still arriving.
    frame.evaluate(f"() => {SLOT}.chart.timeScale().applyOptions({{barSpacing: 24}})")
    frame.wait_for_function(f"() => {SLOT}.chart.timeScale().options().barSpacing === 24")
    width0 = frame.evaluate(LOGICAL_WIDTH)

    frame.wait_for_function(f"(exp) => ({MATCHES})(exp, {SERIES})", arg=expected, timeout=30_000)
    inst1, updates, spacing, actual = frame.evaluate(
        f"() => [{SLOT}.instanceId, {SLOT}.updateCount, {SLOT}.chart.timeScale().options().barSpacing, {SERIES}]"
    )
    assert actual == expected
    assert updates >= 2 and inst1 == inst0  # later renders updated the same chart instance in place
    assert spacing == 24
    assert abs(frame.evaluate(LOGICAL_WIDTH) - width0) < 1e-6

    box = pg.locator(IFRAME).bounding_box()
    assert box and box["width"] > 300 and box["height"] >= 400, box  # the chart is actually visible
    pane = frame.evaluate(f"() => {SLOT}.chart.paneSize()")
    assert pane["width"] > 200 and pane["height"] > 200, pane

    pg.get_by_role("button", name="Stop stream").click()
    expect(pg.locator(IFRAME)).to_have_count(0, timeout=30_000)  # stop unmounts the chart
    pg.get_by_role("button", name="Start stream").click()
    frame = wait_component_frame(pg)
    frame.wait_for_function(f"(exp) => {SLOT} && ({MATCHES})(exp, {SERIES})", arg=expected, timeout=30_000)
    times = frame.evaluate(f"() => {TIMES}")
    assert times == sorted(set(times)) and len(times) == len(expected)  # fresh instance, no leftovers
    assert errors == []


def test_streamlit_shipped_pacing_updates_and_restarts(streamlit_url_shipped, page):
    """Unpatched page at shipped pacing: Start → chart converges to the server candles and the session reports
    stopped → Stop unmounts → Start again converges on a fresh instance. Readiness is observed, never slept."""
    pg, errors = page
    expected = expected_replay_series()
    pg.goto(streamlit_url_shipped)
    pg.get_by_role("button", name="Start stream").click()
    frame = wait_component_frame(pg)
    frame.wait_for_function(f"(exp) => {SLOT} && ({MATCHES})(exp, {SERIES})", arg=expected, timeout=30_000)
    inst0 = frame.evaluate(f"() => {SLOT}.instanceId")
    expect(pg.get_by_text("Auto-refresh · stopped")).to_be_visible(timeout=15_000)  # REPLAY ran to completion
    assert frame.evaluate(f"() => [{SLOT}.instanceId, {SERIES}]") == [inst0, expected]

    pg.get_by_role("button", name="Stop stream").click()
    expect(pg.locator(IFRAME)).to_have_count(0, timeout=30_000)
    pg.get_by_role("button", name="Start stream").click()
    frame = wait_component_frame(pg)
    frame.wait_for_function(f"(exp) => {SLOT} && ({MATCHES})(exp, {SERIES})", arg=expected, timeout=30_000)
    expect(pg.get_by_text("Auto-refresh · stopped")).to_be_visible(timeout=15_000)
    inst1, times = frame.evaluate(f"() => [{SLOT}.instanceId, {TIMES}]")
    assert inst1 != inst0 and times == sorted(set(times)) and len(times) == len(expected)
    assert errors == []
