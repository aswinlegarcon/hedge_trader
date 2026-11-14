"""Spec 14 LIVE-readiness checks, now positive regressions after Spec 15 (offline, sockets blocked).

F1–F4 from docs/spec_14/live-readiness-review.md were defects here; Spec 15 fixed them, so every test below
must pass outright (S24). Real StreamSession worker + real RequestsTransport with a fake requests.Session.
"""
from __future__ import annotations

import socket
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from nifty_lab.brokers import upstox_transport
from nifty_lab.brokers.upstox_transport import RequestsTransport
from nifty_lab.stream_chart.candles import CandleBook
from nifty_lab.stream_chart.constants import INSTRUMENT_KEY, MAX_RECONNECT_ATTEMPTS
from nifty_lab.stream_chart.fixtures import ltpc_frame, market_info_frame
from nifty_lab.stream_chart.proto import MarketDataFeedV3_pb2 as pb
from nifty_lab.stream_chart.stream_session import (
    ConnectionState,
    Freshness,
    SessionPolicy,
    StreamMode,
    StreamSession,
    active_snapshot,
    reset_stream_registry_for_tests,
    start_stream,
    stop_stream,
    worker_threads_alive,
)
from nifty_lab.stream_chart.transport import LiveWebSocketTransport, ScriptedLiveTransport

DUMMY_TOKEN = "unittest-access-token"
SECRET_MARKERS = ("Bearer", DUMMY_TOKEN, "wss://", "authorizedRedirect")
FAST = SessionPolicy(lease_seconds=0.3, monitor_interval_sec=0.02, backoff_sec=(0.01, 0.01, 0.01))


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    reset_stream_registry_for_tests()
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", DUMMY_TOKEN)
    monkeypatch.setattr(upstox_transport, "MIN_INTERVAL_SEC", 0.0)

    class Guarded(socket.socket):
        def connect(self, address):
            raise OSError("network blocked in Spec14 readiness tests")

    monkeypatch.setattr(socket, "socket", Guarded)
    yield
    reset_stream_registry_for_tests()


def now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def bare_session(policy: SessionPolicy | None = None) -> StreamSession:
    s = StreamSession(session_id="t", owner_token="t", mode=StreamMode.LIVE, http=None, transport=ScriptedLiveTransport([]), book=CandleBook(), policy=policy or SessionPolicy())
    s.state = ConnectionState.CONNECTING
    return s


def wait_state(owner: str, *states: ConnectionState, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = active_snapshot(owner_token=owner)
        if snap and snap.state in states:
            return snap
        time.sleep(0.01)
    pytest.fail(f"state {states} not reached; last={snap.state if snap else None}")


def wait_workers_gone(timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline and worker_threads_alive():
        time.sleep(0.01)
    assert worker_threads_alive() == 0


def assert_sanitized(text: str) -> None:
    for marker in SECRET_MARKERS:
        assert marker not in text, f"{marker!r} leaked into {text!r}"


# --------------------------------------------------------------------------- freshness (F1, F2)

def test_source_trade_time_and_local_receipt_time_are_distinct():
    s = bare_session()
    old_ms = now_ms() - 3_600_000
    s._on_frame(ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=100.0, trade_ms=old_ms))
    snap = s.snapshot()
    assert snap.last_trade_ts == datetime.fromtimestamp(old_ms / 1000, tz=timezone.utc)
    assert snap.last_trade_receipt_ts is not None
    assert snap.last_trade_receipt_ts - snap.last_trade_ts > timedelta(minutes=59)


def test_old_trade_received_now_is_not_reported_fresh():  # was F1 xfail
    s = bare_session()
    s._on_frame(ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=100.0, trade_ms=now_ms() - 3_600_000))
    snap = s.snapshot()
    assert snap.state == ConnectionState.STALE and snap.freshness == Freshness.STALE
    assert snap.source_age_sec is not None and snap.source_age_sec > 3500


def test_heartbeat_alone_never_implies_fresh_prices():
    s = bare_session()
    s._on_frame(market_info_frame(receipt_ms=now_ms()))
    snap = s.snapshot()
    assert snap.state == ConnectionState.WAITING_FOR_DATA and snap.freshness == Freshness.WAITING
    assert snap.last_trade_ts is None and snap.last_heartbeat_ts is not None
    assert snap.exchange_status == "NORMAL_OPEN"

    s._on_frame(ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=100.0, trade_ms=now_ms()))
    assert s.snapshot().state == ConnectionState.STREAMING
    s.policy = SessionPolicy(source_fresh_seconds=-1.0)  # force the freshness window shut
    assert s.snapshot().state == ConnectionState.STALE
    s._on_frame(market_info_frame(receipt_ms=now_ms()))  # heartbeat cannot un-stale it
    assert s.snapshot().state == ConnectionState.STALE


def test_closed_market_heartbeats_show_waiting_and_expose_status():
    s = bare_session()
    s._on_frame(market_info_frame(receipt_ms=now_ms(), status=pb.MarketStatus.NORMAL_CLOSE))
    snap = s.snapshot()
    assert snap.state == ConnectionState.WAITING_FOR_DATA  # explicit, not perpetual CONNECTING
    assert snap.exchange_status == "NORMAL_CLOSE"
    assert snap.last_trade_ts is None


def test_future_trade_is_rejected_and_does_not_poison_later_ticks():  # was F2 xfail
    s = bare_session()
    s._on_frame(ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=100.0, trade_ms=now_ms() + 86_400_000))
    s._on_frame(ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=101.0, trade_ms=now_ms()))
    assert s.book.late_ticks_ignored == 0
    assert s.book.forming is not None and s.book.forming.close == 101.0
    assert s.snapshot().future_ticks_rejected == 1


# --------------------------------------------------------------------------- authentication (F3)

class FakeResponse:
    def __init__(self, status: int, content: bytes = b"{}") -> None:
        self.status_code, self.content, self.headers = status, content, {}


class FakeSession:
    """Stands in for requests.Session inside the production RequestsTransport."""

    def __init__(self, status: int, content: bytes = b"{}") -> None:
        self.status, self.content, self.calls = status, content, []

    def get(self, url, *, headers, timeout, allow_redirects):
        self.calls.append(url)
        assert headers["Authorization"] == f"Bearer {DUMMY_TOKEN}"  # dummy token only, never .env
        return FakeResponse(self.status, self.content)


def production_http(status: int, content: bytes = b"{}") -> tuple[RequestsTransport, FakeSession]:
    fake = FakeSession(status, content)
    return RequestsTransport(session=fake), fake  # type: ignore[arg-type]


def test_bootstrap_401_through_production_transport_is_single_attempt():
    http, fake = production_http(401)
    start_stream(owner_token="auth", mode=StreamMode.LIVE, http=http, policy=FAST)
    snap = wait_state("auth", ConnectionState.ERROR)
    assert snap.fault is not None and snap.fault.code.value == "FEED_AUTH_FAILED"
    assert_sanitized(snap.fault.message)
    assert len(fake.calls) == 1 and "/v3/historical-candle/intraday/" in fake.calls[0]
    wait_workers_gone()


def test_missing_token_live_start_errors_without_any_http(monkeypatch):
    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN")
    http, fake = production_http(200)
    start_stream(owner_token="auth", mode=StreamMode.LIVE, http=http, policy=FAST)
    snap = wait_state("auth", ConnectionState.ERROR)
    assert snap.fault is not None and snap.fault.code.value == "FEED_AUTH_FAILED"
    assert_sanitized(snap.fault.message)
    assert fake.calls == []
    wait_workers_gone()


def test_authorize_401_through_production_transport_does_not_retry():  # was F3 xfail
    http, fake = production_http(401)
    start_stream(owner_token="auth", mode=StreamMode.LIVE, live_transport=LiveWebSocketTransport(http), policy=FAST)
    snap = wait_state("auth", ConnectionState.ERROR)
    assert snap.fault is not None and snap.fault.code.value == "FEED_AUTH_FAILED"
    assert_sanitized(snap.fault.message)
    assert len(fake.calls) == 1 and "/v3/feed/market-data-feed/authorize" in fake.calls[0]
    assert snap.reconnect_attempt == 0
    wait_workers_gone()


def test_authorize_200_invalid_body_is_protocol_error_and_not_retried():
    http, fake = production_http(200, b'{"data": {"authorizedRedirectUri": "https://not-wss"}}')
    start_stream(owner_token="auth", mode=StreamMode.LIVE, live_transport=LiveWebSocketTransport(http), policy=FAST)
    snap = wait_state("auth", ConnectionState.ERROR)
    assert snap.fault is not None and snap.fault.code.value == "FEED_AUTHORIZE_INVALID"
    assert_sanitized(snap.fault.message)
    assert len(fake.calls) == 1


# --------------------------------------------------------------------------- connection lifecycle (F4)

class BlockingAuthorizeTransport:
    """Models the HTTP authorize call: blocks and ignores stop_event (bounded only by the HTTP timeout)."""

    def __init__(self, block_sec: float) -> None:
        self.block_sec = block_sec
        self.entered = threading.Event()

    def run(self, *, on_frame, stop_event):
        self.entered.set()
        time.sleep(self.block_sec)
        if stop_event.is_set():
            return
        on_frame(ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=1.0, trade_ms=now_ms()))


def test_stop_during_blocking_authorize_returns_immediately_then_releases_owner():
    transport = BlockingAuthorizeTransport(0.5)
    start_stream(owner_token="a", mode=StreamMode.LIVE, live_transport=transport, policy=FAST)
    assert transport.entered.wait(2.0)
    t0 = time.perf_counter()
    snap = stop_stream(owner_token="a")
    assert time.perf_counter() - t0 < 0.25 and snap.state == ConnectionState.STOPPING
    assert start_stream(owner_token="b", mode=StreamMode.REPLAY, replay_delay_sec=0.01).state == ConnectionState.OWNER_CONFLICT
    wait_workers_gone()
    assert active_snapshot(owner_token="a").state == ConnectionState.STOPPED
    assert start_stream(owner_token="b", mode=StreamMode.REPLAY, replay_delay_sec=0.01).state != ConnectionState.OWNER_CONFLICT
    stop_stream(owner_token="b")


def test_stop_during_active_receive_exits_promptly():
    base = now_ms() - 5_000  # recent source times: FRESH → STREAMING
    frames = [ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=1.0 + i, trade_ms=base + i) for i in range(200)]
    start_stream(owner_token="rx", mode=StreamMode.LIVE, live_transport=ScriptedLiveTransport(frames, delay_sec=0.05), policy=FAST)
    wait_state("rx", ConnectionState.STREAMING)
    t0 = time.perf_counter()
    stop_stream(owner_token="rx")
    wait_workers_gone(timeout=2.0)
    assert time.perf_counter() - t0 < 1.0


class ShortLivedConnection:
    """Each connection streams one fresh trade successfully, then drops."""

    def __init__(self) -> None:
        self.runs = 0

    def run(self, *, on_frame, stop_event):
        self.runs += 1
        on_frame(ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=10.0 + self.runs, trade_ms=now_ms() + self.runs))
        raise ConnectionError("drop")


def test_reconnect_budget_is_per_session_lifetime_with_consistent_category():
    transport = ShortLivedConnection()
    start_stream(owner_token="rc", mode=StreamMode.LIVE, live_transport=transport, policy=FAST)
    snap = wait_state("rc", ConnectionState.ERROR)
    assert transport.runs == 1 + MAX_RECONNECT_ATTEMPTS  # successful streaming never refunds the budget (documented)
    assert snap.fault is not None and snap.fault.code.value == "MAX_RECONNECT"
    assert_sanitized(snap.fault.message)
    assert snap.reconnect_gap is True and snap.reconnect_attempt == MAX_RECONNECT_ATTEMPTS


def test_vanished_browser_session_expires_and_releases_owner():  # was F4 leak characterization
    frames = [market_info_frame(receipt_ms=now_ms() + i) for i in range(5000)]
    start_stream(owner_token="closed-tab", mode=StreamMode.LIVE, live_transport=ScriptedLiveTransport(frames, delay_sec=0.01), policy=FAST)
    wait_state("closed-tab", ConnectionState.WAITING_FOR_DATA)
    # The browser owning "closed-tab" is gone: no keepalive, no Stop, no registry call at all.
    wait_workers_gone(timeout=3.0)
    snap = active_snapshot(owner_token="new-tab")  # non-owner sees a conflict without book data ...
    assert snap.state == ConnectionState.OWNER_CONFLICT and snap.book is None
    second = start_stream(owner_token="new-tab", mode=StreamMode.REPLAY, replay_delay_sec=0.01)  # ... but can start
    assert second.state != ConnectionState.OWNER_CONFLICT
    stop_stream(owner_token="new-tab")
    wait_workers_gone()


# --------------------------------------------------------------------------- secrets

def test_snapshot_and_faults_carry_no_token_or_wss_uri():
    http, _ = production_http(200, b'{"data": {"authorizedRedirectUri": "wss://127.0.0.1:9/x?token=secret"}}')
    start_stream(owner_token="sec", mode=StreamMode.LIVE, live_transport=LiveWebSocketTransport(http), policy=FAST)
    snap = wait_state("sec", ConnectionState.ERROR)  # connect is blocked by the socket guard → bounded retries
    assert snap.fault is not None
    assert_sanitized(snap.fault.message)
    assert "secret" not in snap.fault.message and "secret" not in repr(snap)
    assert not hasattr(snap, "uri") and not hasattr(snap, "token")
    stop_stream(owner_token="sec")
