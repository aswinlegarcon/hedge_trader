"""Spec 14 — LIVE readiness checks (offline). Drives the real StreamSession worker and the real RequestsTransport
with a fake requests.Session; no sockets, no credentials (token is a monkeypatched dummy).

Strict ``xfail`` tests document defects found by the readiness review; they must start passing (and be unmarked)
when the defect is fixed. See docs/spec_14/live-readiness-review.md.
"""
from __future__ import annotations

import socket
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from nifty_lab.brokers.upstox_transport import RequestsTransport
from nifty_lab.brokers import upstox_transport
from nifty_lab.stream_chart import stream_session as ss
from nifty_lab.stream_chart.candles import CandleBook
from nifty_lab.stream_chart.constants import INSTRUMENT_KEY, MAX_RECONNECT_ATTEMPTS
from nifty_lab.stream_chart.fixtures import ltpc_frame, market_info_frame
from nifty_lab.stream_chart.proto import MarketDataFeedV3_pb2 as pb
from nifty_lab.stream_chart.stream_session import (
    ConnectionState,
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


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    reset_stream_registry_for_tests()
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", DUMMY_TOKEN)
    monkeypatch.setattr(upstox_transport, "MIN_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(ss, "RECONNECT_BACKOFF_SEC", (0.01, 0.01, 0.01))

    class Guarded(socket.socket):
        def connect(self, address):
            raise OSError("network blocked in Spec14 readiness tests")

    monkeypatch.setattr(socket, "socket", Guarded)
    yield
    reset_stream_registry_for_tests()


def now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def bare_session() -> StreamSession:
    """A LIVE session object with no worker, to feed frames synchronously into the production _on_frame."""
    s = StreamSession(session_id="t", owner_token="t", mode=StreamMode.LIVE, http=None, transport=ScriptedLiveTransport([]), book=CandleBook())
    s.state = ConnectionState.CONNECTING
    return s


def wait_state(owner: str, *states: ConnectionState, timeout: float = 3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = active_snapshot(owner_token=owner)
        if snap and snap.state in states:
            return snap
        time.sleep(0.01)
    pytest.fail(f"state {states} not reached; last={snap.state if snap else None}")


def assert_sanitized(text: str) -> None:
    for marker in SECRET_MARKERS:
        assert marker not in text, f"{marker!r} leaked into {text!r}"


# --------------------------------------------------------------------------- freshness

def test_source_trade_time_and_local_receipt_time_are_distinct():
    s = bare_session()
    old_ms = now_ms() - 3_600_000
    s._on_frame(ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=100.0, trade_ms=old_ms))
    snap = s.snapshot()
    assert snap.last_trade_ts == datetime.fromtimestamp(old_ms / 1000, tz=timezone.utc)
    assert snap.last_trade_receipt_ts is not None
    assert snap.last_trade_receipt_ts - snap.last_trade_ts > timedelta(minutes=59)


@pytest.mark.xfail(strict=True, reason="F1: staleness keyed on local receipt time only; an hour-old trade received now shows STREAMING")
def test_old_trade_received_now_is_not_reported_fresh():
    s = bare_session()
    s._on_frame(ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=100.0, trade_ms=now_ms() - 3_600_000))
    assert s.snapshot().state != ConnectionState.STREAMING


def test_heartbeat_alone_never_implies_fresh_prices(monkeypatch):
    s = bare_session()
    s._on_frame(market_info_frame(receipt_ms=now_ms()))
    snap = s.snapshot()
    assert snap.state == ConnectionState.CONNECTING  # heartbeat does not promote to STREAMING
    assert snap.last_trade_ts is None and snap.last_heartbeat_ts is not None
    assert snap.exchange_status == "NORMAL_OPEN"

    # A real trade, then it goes stale; a later heartbeat must not un-stale it.
    s._on_frame(ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=100.0, trade_ms=now_ms()))
    assert s.snapshot().state == ConnectionState.STREAMING
    monkeypatch.setattr(ss, "STALE_TRADE_SECONDS", -1)
    assert s.snapshot().state == ConnectionState.STALE
    s._on_frame(market_info_frame(receipt_ms=now_ms()))
    assert s.snapshot().state == ConnectionState.STALE


def test_closed_market_heartbeats_keep_connecting_state_and_expose_status():
    s = bare_session()
    s._on_frame(market_info_frame(receipt_ms=now_ms(), status=pb.MarketStatus.NORMAL_CLOSE))
    snap = s.snapshot()
    assert snap.state == ConnectionState.CONNECTING  # never STREAMING without a trade (shown as CONNECTING all day)
    assert snap.exchange_status == "NORMAL_CLOSE"
    assert snap.last_trade_ts is None


@pytest.mark.xfail(strict=True, reason="F2: no future-timestamp guard; one future tick raises the high-water mark and every later real tick is dropped as late")
def test_future_trade_is_rejected_and_does_not_poison_later_ticks():
    s = bare_session()
    future_ms = now_ms() + 86_400_000
    s._on_frame(ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=100.0, trade_ms=future_ms))
    s._on_frame(ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=101.0, trade_ms=now_ms()))
    assert s.book.late_ticks_ignored == 0
    assert s.book.forming is not None and s.book.forming.close == 101.0


# --------------------------------------------------------------------------- authentication (production transport)

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


def test_bootstrap_401_through_production_transport_errors_without_worker():
    http, fake = production_http(401)
    snap = start_stream(owner_token="auth", mode=StreamMode.LIVE, http=http)
    assert snap.state == ConnectionState.ERROR
    assert snap.fault is not None and snap.fault.code.value == "FEED_AUTH_FAILED"
    assert_sanitized(snap.fault.message)
    assert len(fake.calls) == 1 and "/v3/historical-candle/intraday/" in fake.calls[0]
    assert worker_threads_alive() == 0


def test_missing_token_live_start_errors_without_any_http(monkeypatch):
    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN")
    http, fake = production_http(200)
    snap = start_stream(owner_token="auth", mode=StreamMode.LIVE, http=http)
    assert snap.state == ConnectionState.ERROR
    assert snap.fault is not None and snap.fault.code.value == "FEED_AUTH_FAILED"
    assert_sanitized(snap.fault.message)
    assert fake.calls == [] and worker_threads_alive() == 0


def test_authorize_401_through_production_transport_ends_in_sanitized_error_with_bounded_retries():
    http, fake = production_http(401)
    start_stream(owner_token="auth", mode=StreamMode.LIVE, live_transport=LiveWebSocketTransport(http))
    snap = wait_state("auth", ConnectionState.ERROR)
    assert snap.fault is not None and snap.fault.code.value == "FEED_AUTH_FAILED"
    assert_sanitized(snap.fault.message)
    assert all("/v3/feed/market-data-feed/authorize" in u for u in fake.calls)
    assert len(fake.calls) == 1 + MAX_RECONNECT_ATTEMPTS  # retried with backoff before giving up (see F3)
    stop_stream(owner_token="auth")
    assert worker_threads_alive() == 0


@pytest.mark.xfail(strict=True, reason="F3: RequestsTransport raises UpstoxAuthError (not FeedAuthError) on 401, so the typed no-retry path is bypassed in production")
def test_authorize_401_through_production_transport_does_not_retry():
    http, fake = production_http(401)
    start_stream(owner_token="auth", mode=StreamMode.LIVE, live_transport=LiveWebSocketTransport(http))
    wait_state("auth", ConnectionState.ERROR)
    assert len(fake.calls) == 1


def test_authorize_200_invalid_body_is_typed_and_not_retried():
    http, fake = production_http(200, b'{"data": {"authorizedRedirectUri": "https://not-wss"}}')
    start_stream(owner_token="auth", mode=StreamMode.LIVE, live_transport=LiveWebSocketTransport(http))
    snap = wait_state("auth", ConnectionState.ERROR)
    assert snap.fault is not None and snap.fault.code.value == "FEED_AUTH_FAILED"
    assert_sanitized(snap.fault.message)
    assert len(fake.calls) == 1


# --------------------------------------------------------------------------- connection lifecycle

class BlockingAuthorizeTransport:
    """Models the HTTP authorize call: blocks and ignores stop_event (bounded only by the HTTP timeout)."""

    def __init__(self, block_sec: float) -> None:
        self.block_sec = block_sec
        self.frames_sent = 0

    def run(self, *, on_frame, stop_event):
        time.sleep(self.block_sec)  # requests.get cannot see stop_event
        if stop_event.is_set():
            return
        on_frame(ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=1.0, trade_ms=now_ms()))


def test_stop_during_blocking_authorize_waits_for_the_call_then_releases_owner():
    """stop() joins the worker for up to 5s (stream_session.py:222); an in-flight HTTP authorize cannot be
    interrupted, so Stop blocks the UI thread until the call returns (bounded by the HTTP timeouts)."""
    start_stream(owner_token="a", mode=StreamMode.LIVE, live_transport=BlockingAuthorizeTransport(0.8))
    time.sleep(0.05)
    t0 = time.time()
    stop_stream(owner_token="a")
    assert time.time() - t0 >= 0.6  # Stop waited for the blocking call
    assert worker_threads_alive() == 0
    assert start_stream(owner_token="b", mode=StreamMode.REPLAY, replay_delay_sec=0.01).state != ConnectionState.OWNER_CONFLICT
    stop_stream(owner_token="b")


def test_stop_during_active_receive_exits_promptly():
    frames = [ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=1.0 + i, trade_ms=now_ms() + i) for i in range(200)]
    start_stream(owner_token="rx", mode=StreamMode.LIVE, live_transport=ScriptedLiveTransport(frames, delay_sec=0.05))
    wait_state("rx", ConnectionState.STREAMING)
    t0 = time.time()
    stop_stream(owner_token="rx")
    assert worker_threads_alive() == 0
    assert time.time() - t0 < 1.0


class ShortLivedConnection:
    """Each connection streams one fresh trade successfully, then drops."""

    def __init__(self) -> None:
        self.runs = 0

    def run(self, *, on_frame, stop_event):
        self.runs += 1
        on_frame(ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=10.0 + self.runs, trade_ms=now_ms() + self.runs))
        raise ConnectionError("drop")


def test_reconnect_budget_is_per_session_lifetime_not_per_outage():
    transport = ShortLivedConnection()
    start_stream(owner_token="rc", mode=StreamMode.LIVE, live_transport=transport)
    snap = wait_state("rc", ConnectionState.ERROR)
    assert transport.runs == 1 + MAX_RECONNECT_ATTEMPTS  # successful streaming never refunds the budget (L1)
    # Exception-driven exhaustion surfaces as TRANSPORT_FAILED; MAX_RECONNECT is only for clean closes (L2).
    assert snap.fault is not None and snap.fault.code.value in ("MAX_RECONNECT", "TRANSPORT_FAILED")
    assert snap.reconnect_attempt == MAX_RECONNECT_ATTEMPTS
    assert snap.reconnect_gap is True
    stop_stream(owner_token="rc")


def test_vanished_browser_session_leaves_live_worker_running_and_blocks_new_owner():
    frames = [market_info_frame(receipt_ms=now_ms() + i) for i in range(400)]
    start_stream(owner_token="closed-tab", mode=StreamMode.LIVE, live_transport=ScriptedLiveTransport(frames, delay_sec=0.02))
    time.sleep(0.05)
    # The browser owning "closed-tab" is gone; nothing in the app stops its worker.
    assert worker_threads_alive() == 1
    assert start_stream(owner_token="new-tab", mode=StreamMode.LIVE, live_transport=ScriptedLiveTransport([])).state == ConnectionState.OWNER_CONFLICT
    rejected = stop_stream(owner_token="new-tab")
    assert rejected is not None and rejected.state == ConnectionState.OWNER_CONFLICT
    assert worker_threads_alive() == 1  # F4: only the original owner token or a process restart can release it
    stop_stream(owner_token="closed-tab")
    assert worker_threads_alive() == 0


# --------------------------------------------------------------------------- secrets

def test_snapshot_and_faults_carry_no_token_or_wss_uri():
    http, _ = production_http(200, b'{"data": {"authorizedRedirectUri": "wss://feed.example/x?token=secret"}}')
    start_stream(owner_token="sec", mode=StreamMode.LIVE, live_transport=LiveWebSocketTransport(http))
    snap = wait_state("sec", ConnectionState.ERROR)  # websockets.connect is blocked by the socket guard
    assert snap.fault is not None
    assert_sanitized(snap.fault.message)
    assert "secret" not in snap.fault.message
    for field_name in ("session_id", "owner_token", "exchange_status"):
        assert_sanitized(str(getattr(snap, field_name)))
    assert not hasattr(snap, "uri") and not hasattr(snap, "token")
    stop_stream(owner_token="sec")
