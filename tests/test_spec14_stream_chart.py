"""Spec 14 — acceptance corrections (offline REPLAY, candles, session). Browser: test_spec14_browser_acceptance.py."""
from __future__ import annotations

import json
import socket
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from nifty_lab.brokers.upstox_transport import API_HOST
from nifty_lab.config import FAKE_SECRET_SENTINEL
from nifty_lab.stream_chart.candles import CandleBook
from nifty_lab.stream_chart.constants import INSTRUMENT_KEY, SUBSCRIBE_MODE
from nifty_lab.stream_chart.feed_decode import build_subscribe_frame, decode_feed_message
from nifty_lab.stream_chart.fixtures import ltpc_frame, market_info_frame
from nifty_lab.stream_chart.replay_fixture import (
    BAR_0445,
    BAR_0450,
    T_045001,
    T_045858,
    T_045859,
    acceptance_late_tick_scenario,
)
from nifty_lab.stream_chart.stream_errors import FeedAuthError, sanitize_exception
from nifty_lab.stream_chart.stream_session import (
    ConnectionState,
    StreamMode,
    active_snapshot,
    reset_stream_registry_for_tests,
    start_stream,
    stop_stream,
    worker_threads_alive,
)
from nifty_lab.stream_chart.transport import ReplayTransport, ScriptedLiveTransport, fetch_authorized_ws_uri

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class MockTransport:
    def __init__(self, routes: dict[str, tuple[int, bytes, dict]]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def get(self, url: str, *, headers: dict[str, str] | None = None, allow_redirects: bool = False):
        self.calls.append(url)
        if FAKE_SECRET_SENTINEL in (headers or {}).get("Authorization", ""):
            pytest.fail("sentinel leaked into Authorization header")
        for prefix, response in self.routes.items():
            if prefix in url:
                return response
        return 404, b"{}", {}


@pytest.fixture(autouse=True)
def spec14_isolate():
    reset_stream_registry_for_tests()
    yield
    reset_stream_registry_for_tests()


@pytest.fixture(autouse=True)
def block_socket(monkeypatch):
    class Guarded(socket.socket):
        def connect(self, address):
            raise OSError("network blocked in Spec14 tests")

    monkeypatch.setattr(socket, "socket", Guarded)


def test_late_tick_acceptance_timeline():
    scenario = acceptance_late_tick_scenario()
    book = CandleBook()
    book.load_replay_bootstrap(scenario.bootstrap)
    for raw in scenario.frames[:4]:
        _type, ticks, info = decode_feed_message(raw)
        assert info is None
        for tick in ticks:
            book.apply_trade(price=tick.price, trade_ms=int(tick.trade_ts_utc.timestamp() * 1000))
    times = [r["time"] for r in book.chart_series()]
    assert times == sorted(set(times))
    assert BAR_0445 in times and BAR_0450 in times
    assert times.count(BAR_0445) == 1
    assert book.late_ticks_ignored == 1
    book.assert_chart_invariants()


def test_same_millisecond_distinct_prices():
    book = CandleBook()
    ms = T_045859
    assert book.apply_trade(price=100.0, trade_ms=ms)
    assert book.apply_trade(price=100.5, trade_ms=ms)
    assert book.forming.close == 100.5


def test_candle_5m_boundary_ist():
    book = CandleBook()
    ist = ZoneInfo("Asia/Kolkata")
    t1 = datetime(2026, 11, 14, 10, 17, 30, tzinfo=ist)
    t2 = datetime(2026, 11, 14, 10, 19, 0, tzinfo=ist)
    ms1 = int(t1.timestamp() * 1000)
    ms2 = int(t2.timestamp() * 1000)
    assert book.bar_open_epoch(ms1) == book.bar_open_epoch(ms2)


def test_replay_start_stop_offline():
    start_stream(owner_token="o1", mode=StreamMode.REPLAY, replay_delay_sec=0.05)
    time.sleep(0.6)
    snap = stop_stream(owner_token="o1")
    assert snap is not None
    assert snap.book is not None
    snap.book.assert_chart_invariants()


def test_owner_conflict_not_preemptive():
    scenario = acceptance_late_tick_scenario()
    start_stream(
        owner_token="owner-a",
        mode=StreamMode.REPLAY,
        replay_frames=scenario.frames,
        replay_delay_sec=0.3,
    )
    conflict = start_stream(owner_token="owner-b", mode=StreamMode.REPLAY)
    assert conflict.state == ConnectionState.OWNER_CONFLICT
    assert worker_threads_alive() == 1
    stop_stream(owner_token="owner-a")


def test_snapshot_requires_owner():
    start_stream(owner_token="only", mode=StreamMode.REPLAY, replay_delay_sec=0.05)
    foreign = active_snapshot(owner_token="other")
    assert foreign is not None
    assert foreign.state == ConnectionState.OWNER_CONFLICT
    stop_stream(owner_token="only")


def test_auth_failure_typed_no_retry(monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "unittest-access-token")
    transport = ScriptedLiveTransport([], fail_auth=True)
    start_stream(owner_token="auth", mode=StreamMode.LIVE, live_transport=transport)
    for _ in range(20):
        snap = active_snapshot(owner_token="auth")
        if snap and snap.state == ConnectionState.ERROR:
            break
        time.sleep(0.05)
    assert snap is not None
    assert snap.fault is not None
    assert snap.fault.code.value == "FEED_AUTH_FAILED"
    stop_stream(owner_token="auth")


def test_sanitize_hides_wss_uri():
    fault = sanitize_exception(RuntimeError("failed wss://secret-token.example/feed?token=abc"))
    assert "wss://" not in fault.message
    assert "token" not in fault.message.lower()


def test_authorize_401_raises_feed_auth():
    transport = MockTransport(
        {f"https://{API_HOST}/v3/feed/market-data-feed/authorize": (401, b"{}", {})}
    )
    with pytest.raises(FeedAuthError):
        fetch_authorized_ws_uri(transport)


def test_heartbeat_does_not_refresh_trade(monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "unittest-access-token")
    trade = ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=10.0, trade_ms=T_045859)
    hb = market_info_frame(receipt_ms=T_045001)
    start_stream(
        owner_token="hb",
        mode=StreamMode.LIVE,
        live_transport=ScriptedLiveTransport([trade, hb], delay_sec=0.02),
    )
    time.sleep(0.15)
    snap = active_snapshot(owner_token="hb")
    assert snap is not None
    assert snap.last_trade_ts is not None
    assert snap.last_heartbeat_ts is not None
    stop_stream(owner_token="hb")


def test_stop_during_backoff():
    frames = [ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=1.0, trade_ms=T_045859)]
    start_stream(
        owner_token="stop",
        mode=StreamMode.LIVE,
        live_transport=ScriptedLiveTransport(frames, disconnect_after=1, delay_sec=0.0),
        replay_delay_sec=0.0,
    )
    time.sleep(0.05)
    stop_stream(owner_token="stop")
    deadline = time.time() + 3.0
    while time.time() < deadline and worker_threads_alive() > 0:
        time.sleep(0.05)
    assert worker_threads_alive() == 0


def test_bounded_dedupe_memory():
    book = CandleBook()
    for i in range(12_000):
        book.apply_trade(price=1.0 + i * 1e-6, trade_ms=1_700_000_000_000 + i)
    assert len(book._seen_keys) <= 10_000


def test_apptest_page14_load_and_replay(monkeypatch):
    pytest.importorskip("streamlit.testing.v1", exc_type=ImportError)
    from streamlit.testing.v1 import AppTest

    http_calls: list[str] = []

    class GuardTransport:
        def get(self, url: str, *, headers=None, allow_redirects: bool = False):
            http_calls.append(url)
            raise AssertionError("HTTP must not run in REPLAY AppTest")

    from nifty_lab.stream_chart import ui as sc_ui

    monkeypatch.setattr(sc_ui, "RequestsTransport", GuardTransport)
    monkeypatch.setattr(sc_ui, "render_candlestick_chart", lambda **_: {"instanceId": "apptest", "updateCount": 1})
    at = AppTest.from_file(str(PROJECT_ROOT / "pages" / "14_Stream_Chart.py"))
    at.run(timeout=30)
    assert not at.exception
    start = next(b for b in at.button if "Start stream" in (b.label or ""))
    start.click().run(timeout=30)
    assert not at.exception
    time.sleep(0.9)
    stop = next(b for b in at.button if "Stop stream" in (b.label or ""))
    stop.click().run(timeout=30)
    assert not at.exception
    assert http_calls == []


def test_subscribe_frame_utf8():
    frame = build_subscribe_frame(instrument_keys=[INSTRUMENT_KEY], mode=SUBSCRIBE_MODE)
    payload = json.loads(frame.decode("utf-8"))
    assert payload["method"] == "sub"