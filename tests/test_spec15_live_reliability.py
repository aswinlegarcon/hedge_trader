"""Spec 15 — LIVE feed reliability, offline (R01–R05). Sockets blocked; dummy token via env; injected clocks.

Scenario ids (S01–S25) refer to docs/spec_15/capabilities/live-feed-reliability.md.
"""
from __future__ import annotations

import math
import socket
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from nifty_lab.brokers import upstox_transport
from nifty_lab.brokers.upstox_transport import RequestsTransport
from nifty_lab.stream_chart import stream_session as ss
from nifty_lab.stream_chart.candles import CandleBook
from nifty_lab.stream_chart.constants import (
    INSTRUMENT_KEY,
    MAX_FUTURE_SKEW_SECONDS,
    MAX_RECONNECT_ATTEMPTS,
    RECEIPT_PROGRESS_SECONDS,
    SOURCE_FRESH_SECONDS,
)
from nifty_lab.stream_chart.feed_decode import decode_feed_message
from nifty_lab.stream_chart.fixtures import ltpc_frame, market_info_frame
from nifty_lab.stream_chart.proto import MarketDataFeedV3_pb2 as pb
from nifty_lab.stream_chart.replay_fixture import BAR_0445, T_045858, T_045859, acceptance_late_tick_scenario
from nifty_lab.stream_chart.stream_session import (
    ConnectionState,
    Freshness,
    SessionPolicy,
    StreamMode,
    StreamSession,
    active_snapshot,
    keepalive,
    reset_stream_registry_for_tests,
    start_stream,
    stop_stream,
    worker_threads_alive,
)
from nifty_lab.stream_chart.transport import LiveWebSocketTransport, ScriptedLiveTransport

DUMMY_TOKEN = "unittest-access-token-S15"
SECRET_MARKERS = ("Bearer", DUMMY_TOKEN, "wss://", "authorizedRedirect")
T0 = datetime(2026, 11, 14, 9, 30, tzinfo=timezone.utc)


class FakeClock:
    def __init__(self, wall: datetime = T0, mono: float = 1000.0) -> None:
        self._wall, self._mono = wall, mono

    def wall(self) -> datetime:
        return self._wall

    def mono(self) -> float:
        return self._mono

    def advance(self, seconds: float) -> None:  # both clocks move together
        self._wall += timedelta(seconds=seconds)
        self._mono += seconds


def ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


FAST = SessionPolicy(lease_seconds=0.5, monitor_interval_sec=0.02, backoff_sec=(0.01, 0.01, 0.01))


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    reset_stream_registry_for_tests()
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", DUMMY_TOKEN)
    monkeypatch.setattr(upstox_transport, "MIN_INTERVAL_SEC", 0.0)

    class Guarded(socket.socket):
        def connect(self, address):
            raise OSError("network blocked in Spec15 unit tests")

    monkeypatch.setattr(socket, "socket", Guarded)
    yield
    reset_stream_registry_for_tests()


def live_session(clock: FakeClock, mode: StreamMode = StreamMode.LIVE) -> StreamSession:
    s = StreamSession(session_id="gen-1", owner_token="o", mode=mode, http=None, transport=ScriptedLiveTransport([]), book=CandleBook(), clock=clock)
    s.state = ConnectionState.CONNECTING
    return s


def tick(dt: datetime, price: float = 100.0) -> bytes:
    return ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=price, trade_ms=ms(dt))


def wait_until(pred, timeout: float = 5.0, what: str = "condition"):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return
        time.sleep(0.01)
    pytest.fail(f"timeout waiting for {what}")


def wait_state(owner: str, *states: ConnectionState, timeout: float = 5.0):
    out = {}

    def ok():
        out["snap"] = active_snapshot(owner_token=owner)
        return out["snap"] is not None and out["snap"].state in states

    wait_until(ok, timeout, f"state in {states} (last={out.get('snap') and out['snap'].state})")
    return out["snap"]


def assert_sanitized(text: str) -> None:
    for marker in SECRET_MARKERS:
        assert marker not in text, f"{marker!r} leaked into {text!r}"


class FakeResponse:
    def __init__(self, status: int, content: bytes = b"{}") -> None:
        self.status_code, self.content, self.headers = status, content, {}


class FakeSession:
    def __init__(self, status: int, content: bytes = b"{}", *, fail: Exception | None = None) -> None:
        self.status, self.content, self.fail, self.calls = status, content, fail, []

    def get(self, url, *, headers, timeout, allow_redirects):
        self.calls.append(url)
        assert headers["Authorization"] == f"Bearer {DUMMY_TOKEN}"
        if self.fail:
            raise self.fail
        return FakeResponse(self.status, self.content)


def production_http(status: int, content: bytes = b"{}", **kw) -> tuple[RequestsTransport, FakeSession]:
    fake = FakeSession(status, content, **kw)
    return RequestsTransport(session=fake), fake  # type: ignore[arg-type]


# ============================================================================ R01 freshness

def test_s01_hour_old_trade_received_now_is_stale_with_source_age():
    clock = FakeClock()
    s = live_session(clock)
    s._on_frame(tick(T0 - timedelta(hours=1)))
    snap = s.snapshot()
    assert snap.freshness == Freshness.STALE
    assert snap.state == ConnectionState.STALE
    assert snap.source_age_sec == pytest.approx(3600.0)
    assert snap.last_trade_ts == T0 - timedelta(hours=1)


def test_s02_heartbeats_never_make_price_fresh_and_fresh_expires_after_30s():
    clock = FakeClock()
    s = live_session(clock)
    s._on_frame(market_info_frame(receipt_ms=ms(T0)))
    snap = s.snapshot()
    assert snap.freshness == Freshness.WAITING and snap.state == ConnectionState.WAITING_FOR_DATA
    assert snap.exchange_status == "NORMAL_OPEN" and snap.last_trade_ts is None

    s._on_frame(tick(T0))
    assert s.snapshot().freshness == Freshness.FRESH and s.snapshot().state == ConnectionState.STREAMING
    clock.advance(SOURCE_FRESH_SECONDS)  # boundary: exactly 30s is still fresh
    assert s.snapshot().freshness == Freshness.FRESH
    clock.advance(0.5)
    assert s.snapshot().freshness == Freshness.STALE and s.snapshot().state == ConnectionState.STALE
    for _ in range(3):  # heartbeats keep arriving; price stays stale
        s._on_frame(market_info_frame(receipt_ms=ms(clock.wall())))
    assert s.snapshot().freshness == Freshness.STALE
    assert s.snapshot().last_heartbeat_ts == clock.wall()


def test_s03_stationary_or_older_source_data_does_not_extend_progress_freshness():
    clock = FakeClock()
    s = live_session(clock)
    s._on_frame(tick(T0, 100.0))
    assert s.snapshot().freshness == Freshness.FRESH
    for i in range(1, 8):  # 35s of repeated identical and older same-bucket ticks received "now"
        clock.advance(5)
        s._on_frame(tick(T0, 100.0))  # identical snapshot (dedupe)
        s._on_frame(tick(T0 - timedelta(seconds=1), 99.0 + i * 0.01))  # older same-bucket tick
    snap = s.snapshot()
    assert snap.last_trade_ts == T0  # never regressed
    assert snap.progress_age_sec == pytest.approx(35.0)
    assert snap.freshness == Freshness.STALE


def test_s04_wall_clock_jump_does_not_extend_monotonic_receipt_freshness():
    clock = FakeClock()
    s = live_session(clock)
    s._on_frame(tick(T0))
    clock._mono += RECEIPT_PROGRESS_SECONDS + 1  # 31s elapsed monotonically ...
    clock._wall = T0 + timedelta(seconds=5)  # ... but wall clock says only 5s passed (NTP step)
    snap = s.snapshot()
    assert snap.progress_age_sec == pytest.approx(RECEIPT_PROGRESS_SECONDS + 1)
    assert snap.freshness == Freshness.STALE
    # Boundary: progress age exactly at threshold is fresh.
    clock._mono -= 1
    assert s.snapshot().freshness == Freshness.FRESH


def test_s05_replay_is_synthetic_offline_and_keeps_its_historic_fixture():
    start_stream(owner_token="r", mode=StreamMode.REPLAY, replay_delay_sec=0.01, clock=FakeClock(wall=datetime(2030, 1, 1, tzinfo=timezone.utc)))
    snap = wait_state("r", ConnectionState.STOPPED)
    assert snap.freshness == Freshness.SYNTHETIC
    assert snap.book is not None and snap.future_ticks_rejected == 0
    assert BAR_0445 in [r["time"] for r in snap.book.chart_series()]  # historic 2026-11-14 bars accepted under a 2030 clock
    assert snap.book.late_ticks_ignored == 1
    stop_stream(owner_token="r")


# ============================================================================ R02 timestamp admission

def test_s06_future_tick_rejected_without_poisoning_state():
    clock = FakeClock()
    s = live_session(clock)
    s._on_frame(tick(T0 - timedelta(seconds=10), 100.0))
    before = (s.book.forming, s.book._high_water_trade_ms, s.snapshot().last_trade_ts, s.snapshot().progress_age_sec)
    s._on_frame(tick(T0 + timedelta(seconds=MAX_FUTURE_SKEW_SECONDS + 0.5), 999.0))
    after = s.snapshot()
    assert (s.book.forming, s.book._high_water_trade_ms, after.last_trade_ts, after.progress_age_sec) == before
    assert after.future_ticks_rejected == 1 and after.freshness == Freshness.FRESH
    s._on_frame(tick(T0, 101.0))  # a following valid tick is admitted
    assert s.book.forming is not None and s.book.forming.close == 101.0
    assert s.snapshot().last_trade_ts == T0
    # skew within tolerance is admitted and clamps to zero for display
    s._on_frame(tick(T0 + timedelta(seconds=1), 102.0))
    assert s.snapshot().last_trade_ts == T0 + timedelta(seconds=1)
    assert s.snapshot().source_age_sec == 0.0


def _raw_frame(ltp: float, ltt: int) -> bytes:
    m = pb.FeedResponse()
    m.type = pb.Type.live_feed
    m.currentTs = ms(T0)
    f = m.feeds[INSTRUMENT_KEY]
    f.ltpc.ltp = ltp
    f.ltpc.ltt = ltt
    return m.SerializeToString()


@pytest.mark.parametrize(
    "ltp,ltt",
    [(100.0, 0), (100.0, -1), (100.0, 2**63 - 1), (100.0, 4_102_444_800_001), (0.0, ms(T0)), (-1.0, ms(T0)), (math.inf, ms(T0)), (math.nan, ms(T0))],
)
def test_s07_invalid_timestamps_and_prices_rejected_at_decoder_without_crash(ltp, ltt):
    kind, ticks, info = decode_feed_message(_raw_frame(ltp, ltt))
    assert kind == "live_feed" and ticks == [] and info is None
    s = live_session(FakeClock())
    s._on_frame(_raw_frame(ltp, ltt))  # bounded diagnostics, no mutation
    snap = s.snapshot()
    assert snap.invalid_ticks_rejected == 1 and snap.last_trade_ts is None and s.book.forming is None


def test_s07_missing_feed_fields_rejected():
    m = pb.FeedResponse()
    m.type = pb.Type.live_feed
    m.feeds[INSTRUMENT_KEY].ltpc.ltp = 100.0  # ltt missing (0)
    kind, ticks, _ = decode_feed_message(m.SerializeToString())
    assert ticks == []
    s = live_session(FakeClock())
    s._on_frame(b"\xff\xfe\x00garbage")  # undecodable frame: counted, no crash
    assert s.snapshot().invalid_ticks_rejected == 1


def test_s08_older_intra_bucket_tick_extends_high_low_but_keeps_newest_close():
    book = CandleBook()
    assert book.apply_trade(price=100.0, trade_ms=T_045859)
    assert book.apply_trade(price=105.0, trade_ms=T_045858)  # older, same bucket, higher
    assert book.apply_trade(price=95.0, trade_ms=T_045858 - 10)  # older, lower
    f = book.forming
    assert f is not None and (f.high, f.low, f.close) == (105.0, 95.0, 100.0)
    # equal-timestamp arrival-order policy unchanged (Spec 14): later arrival sets close
    assert book.apply_trade(price=100.5, trade_ms=T_045859)
    assert book.forming.close == 100.5
    # completed bars never reopen
    scenario = acceptance_late_tick_scenario()
    book2 = CandleBook()
    book2.load_replay_bootstrap(scenario.bootstrap)
    for raw in scenario.frames[:4]:
        for t in decode_feed_message(raw)[1]:
            book2.apply_trade(price=t.price, trade_ms=ms(t.trade_ts_utc))
    completed = {b.time_epoch: b for b in book2.stream_completed}
    assert BAR_0445 in completed
    assert not book2.apply_trade(price=1.0, trade_ms=T_045858)  # late into completed bucket
    assert completed[BAR_0445] == {b.time_epoch: b for b in book2.stream_completed}[BAR_0445]
    book2.assert_chart_invariants()


# ============================================================================ R03 authentication

@pytest.mark.parametrize("status", [401, 403])
def test_s09_authorize_401_403_through_production_transport_is_single_attempt_non_retryable(status):
    http, fake = production_http(status)
    start_stream(owner_token="a", mode=StreamMode.LIVE, live_transport=LiveWebSocketTransport(http), policy=FAST)
    snap = wait_state("a", ConnectionState.ERROR)
    assert snap.fault is not None and snap.fault.code.value == "FEED_AUTH_FAILED"
    assert_sanitized(snap.fault.message)
    assert len(fake.calls) == 1 and "/authorize" in fake.calls[0]
    assert snap.reconnect_attempt == 0
    wait_until(lambda: worker_threads_alive() == 0, what="worker exit")


def test_s09_bootstrap_401_is_single_attempt_without_authorize_or_connect():
    http, fake = production_http(401)
    start_stream(owner_token="b", mode=StreamMode.LIVE, http=http, policy=FAST)
    snap = wait_state("b", ConnectionState.ERROR)
    assert snap.fault is not None and snap.fault.code.value == "FEED_AUTH_FAILED"
    assert_sanitized(snap.fault.message)
    assert len(fake.calls) == 1 and "/v3/historical-candle/intraday/" in fake.calls[0]
    wait_until(lambda: worker_threads_alive() == 0, what="worker exit")


@pytest.mark.parametrize(
    "body",
    [b"not json", b'{"data": "nope"}', b'{"data": {"authorizedRedirectUri": "https://not-wss"}}', b'{"data": {"authorizedRedirectUri": "ws://127.0.0.1:1/x"}}'],
)
def test_s10_malformed_authorize_payload_is_non_retryable_protocol_error(body):
    http, fake = production_http(200, body)
    start_stream(owner_token="p", mode=StreamMode.LIVE, live_transport=LiveWebSocketTransport(http), policy=FAST)
    snap = wait_state("p", ConnectionState.ERROR)
    assert snap.fault is not None and snap.fault.code.value == "FEED_AUTHORIZE_INVALID"
    assert_sanitized(snap.fault.message)
    assert len(fake.calls) == 1


def test_s10_temporary_server_failure_uses_only_the_bounded_reconnect_loop():
    http, fake = production_http(503)
    start_stream(owner_token="t", mode=StreamMode.LIVE, live_transport=LiveWebSocketTransport(http), policy=FAST)
    snap = wait_state("t", ConnectionState.ERROR)
    assert len(fake.calls) == 1 + MAX_RECONNECT_ATTEMPTS
    assert snap.fault is not None and snap.fault.code.value == "MAX_RECONNECT"
    assert snap.reconnect_attempt == MAX_RECONNECT_ATTEMPTS and snap.reconnect_gap is True


class CleanCloseTransport:
    def __init__(self) -> None:
        self.runs = 0

    def run(self, *, on_frame, stop_event):
        self.runs += 1
        on_frame(ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=10.0 + self.runs, trade_ms=ms(T0) + self.runs))
        return  # server closed cleanly


class DropTransport(CleanCloseTransport):
    def run(self, *, on_frame, stop_event):
        super().run(on_frame=on_frame, stop_event=stop_event)
        raise ConnectionError("drop")


@pytest.mark.parametrize("transport_cls", [CleanCloseTransport, DropTransport])
def test_s11_clean_close_and_exception_exhaustion_share_budget_and_category(transport_cls):
    transport = transport_cls()
    start_stream(owner_token="x", mode=StreamMode.LIVE, live_transport=transport, policy=FAST)
    snap = wait_state("x", ConnectionState.ERROR)
    assert transport.runs == 1 + MAX_RECONNECT_ATTEMPTS
    assert snap.fault is not None and snap.fault.code.value == "MAX_RECONNECT"
    assert_sanitized(snap.fault.message)
    assert snap.reconnect_gap is True and snap.reconnect_attempt == MAX_RECONNECT_ATTEMPTS


# ============================================================================ R04 responsive stop

class BlockingTransport:
    """Models an uninterruptible HTTP/handshake call followed by a frame; records what happened after Stop."""

    def __init__(self, block_sec: float) -> None:
        self.block_sec, self.frames_after_stop, self.entered = block_sec, 0, threading.Event()

    def run(self, *, on_frame, stop_event):
        self.entered.set()
        time.sleep(self.block_sec)
        if stop_event.is_set():
            self.frames_after_stop += 1
        on_frame(ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=1.0, trade_ms=ms(T0)))


def test_s12_stop_during_blocking_call_returns_fast_and_worker_terminates_within_budget():
    clock = FakeClock()
    transport = BlockingTransport(0.4)
    start_stream(owner_token="s", mode=StreamMode.LIVE, live_transport=transport, policy=FAST, clock=clock)
    assert transport.entered.wait(2.0)
    t0 = time.perf_counter()
    snap = stop_stream(owner_token="s")
    assert time.perf_counter() - t0 < 0.25
    assert snap is not None and snap.state == ConnectionState.STOPPING and snap.stop_requested
    wait_until(lambda: worker_threads_alive() == 0, timeout=2.0, what="worker termination")
    final = active_snapshot(owner_token="s")
    assert final is not None and final.state == ConnectionState.STOPPED
    assert transport.frames_after_stop == 1 and final.last_trade_ts is None  # late frame was not admitted


def test_s12_stop_during_receive_and_backoff_terminates_within_two_seconds():
    now = ms(datetime.now(timezone.utc)) - 60_000
    frames = [ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=1.0 + i, trade_ms=now + i) for i in range(500)]
    start_stream(owner_token="rx", mode=StreamMode.LIVE, live_transport=ScriptedLiveTransport(frames, delay_sec=0.05), policy=FAST)
    wait_state("rx", ConnectionState.STREAMING, ConnectionState.STALE)
    t0 = time.perf_counter()
    stop_stream(owner_token="rx")
    wait_until(lambda: worker_threads_alive() == 0, timeout=2.0, what="receive worker exit")
    assert time.perf_counter() - t0 < 2.0
    reset_stream_registry_for_tests()
    slow = SessionPolicy(lease_seconds=5, monitor_interval_sec=0.02, backoff_sec=(5.0, 5.0, 5.0))
    start_stream(owner_token="bo", mode=StreamMode.LIVE, live_transport=DropTransport(), policy=slow)
    wait_state("bo", ConnectionState.RECONNECTING)
    t0 = time.perf_counter()
    stop_stream(owner_token="bo")
    wait_until(lambda: worker_threads_alive() == 0, timeout=2.0, what="backoff worker exit")
    assert time.perf_counter() - t0 < 2.0


def test_s13_stopping_blocks_overlapping_start_and_stopped_requires_termination():
    transport = BlockingTransport(0.5)
    start_stream(owner_token="s", mode=StreamMode.LIVE, live_transport=transport, policy=FAST)
    assert transport.entered.wait(2.0)
    stop_stream(owner_token="s")
    assert active_snapshot(owner_token="s").state == ConnectionState.STOPPING
    again = start_stream(owner_token="s", mode=StreamMode.REPLAY, replay_delay_sec=0.01)
    assert again.state == ConnectionState.OWNER_CONFLICT and "stopping" in again.fault.message.lower()
    assert worker_threads_alive() == 1  # no overlapping worker
    wait_until(lambda: active_snapshot(owner_token="s").state == ConnectionState.STOPPED, what="STOPPED after termination")
    assert worker_threads_alive() == 0
    assert start_stream(owner_token="s", mode=StreamMode.REPLAY, replay_delay_sec=0.01).state != ConnectionState.OWNER_CONFLICT


def test_s14_delayed_callback_from_old_generation_is_ignored():
    http_old, fake_old = production_http(200, b'{"data": {"authorizedRedirectUri": "wss://127.0.0.1:9/feed"}}')
    start_stream(owner_token="g", mode=StreamMode.LIVE, live_transport=LiveWebSocketTransport(http_old), policy=FAST)
    old = ss._ACTIVE
    assert old is not None
    wait_state("g", ConnectionState.ERROR)  # connect blocked by socket guard → bounded retries → ERROR
    calls_before = len(fake_old.calls)
    stop_stream(owner_token="g")
    wait_until(lambda: worker_threads_alive() == 0, what="old worker exit")
    start_stream(owner_token="g", mode=StreamMode.LIVE, live_transport=ScriptedLiveTransport([], delay_sec=0.0), policy=FAST)
    new = ss._ACTIVE
    assert new is not None and new is not old and new.session_id != old.session_id
    old._on_frame(ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=42.0, trade_ms=ms(T0)))  # delayed old-generation frame
    assert new.book.forming is None and old.book.forming is None
    assert active_snapshot(owner_token="g").last_trade_ts is None
    assert len(fake_old.calls) == calls_before  # no new authorize from the dead generation
    assert keepalive(owner_token="g", session_id=old.session_id) is False  # stale generation cannot renew
    assert stop_stream(owner_token="g", session_id=old.session_id).state == ConnectionState.OWNER_CONFLICT


# ============================================================================ R05 owner lease

def test_s15_abandoned_owner_expires_autonomously_and_slot_becomes_reusable():
    clock = FakeClock()
    frames = [market_info_frame(receipt_ms=ms(T0) + i) for i in range(2000)]
    start_stream(owner_token="tab-a", mode=StreamMode.LIVE, live_transport=ScriptedLiveTransport(frames, delay_sec=0.01), policy=FAST, clock=clock)
    wait_state("tab-a", ConnectionState.WAITING_FOR_DATA)
    clock.advance(FAST.lease_seconds + 0.1)  # no keepalives, no registry calls from the owner
    # No further registry calls: the monitor alone must shut it down.
    deadline = time.time() + 3.0
    while time.time() < deadline and worker_threads_alive():
        time.sleep(0.01)
    assert worker_threads_alive() == 0
    snap = ss._ACTIVE.snapshot()  # direct read, still no registry call
    assert snap.state == ConnectionState.OWNER_EXPIRED and snap.fault.code.value == "OWNER_EXPIRED"
    assert_sanitized(snap.fault.message)
    second = start_stream(owner_token="tab-b", mode=StreamMode.REPLAY, replay_delay_sec=0.01)
    assert second.state != ConnectionState.OWNER_CONFLICT and second.owner_token == "tab-b"
    stop_stream(owner_token="tab-b")


def test_s16_keepalives_preserve_ownership_and_wrong_owner_cannot_renew_or_release():
    clock = FakeClock()
    frames = [market_info_frame(receipt_ms=ms(T0) + i) for i in range(5000)]
    start_stream(owner_token="own", mode=StreamMode.LIVE, live_transport=ScriptedLiveTransport(frames, delay_sec=0.01), policy=FAST, clock=clock)
    sid = active_snapshot(owner_token="own").session_id
    for _ in range(6):  # 6 × 0.3s = 1.8s > lease, kept alive by owner keepalives
        clock.advance(0.3)
        assert keepalive(owner_token="own", session_id=sid) is True
        time.sleep(0.05)
    assert worker_threads_alive() == 2 and active_snapshot(owner_token="own").state == ConnectionState.WAITING_FOR_DATA  # worker + monitor
    # snapshot reads by anyone do not renew; wrong owner / wrong generation cannot renew or stop
    assert keepalive(owner_token="intruder") is False
    assert keepalive(owner_token="own", session_id="wrong-gen") is False
    conflict = start_stream(owner_token="intruder", mode=StreamMode.REPLAY)
    assert conflict.state == ConnectionState.OWNER_CONFLICT and conflict.book is None and conflict.owner_token == "intruder"
    rejected = stop_stream(owner_token="intruder")
    assert rejected.state == ConnectionState.OWNER_CONFLICT and rejected.book is None and rejected.owner_token == "intruder"
    assert worker_threads_alive() == 2  # still running, still owned
    for _ in range(5):  # snapshots alone do not renew → expiry
        clock.advance(0.3)
        active_snapshot(owner_token="own")
        time.sleep(0.03)
    wait_until(lambda: worker_threads_alive() == 0, what="expiry without keepalive")
    assert ss._ACTIVE.snapshot().state == ConnectionState.OWNER_EXPIRED


def test_s17_repeated_cycles_leave_no_workers_and_concurrent_access_is_consistent():
    base = threading.active_count()
    for i in range(6):
        clock = FakeClock()
        frames = [ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=1.0 + k, trade_ms=ms(T0) + k) for k in range(50)]
        start_stream(owner_token=f"o{i}", mode=StreamMode.LIVE, live_transport=ScriptedLiveTransport(frames, delay_sec=0.005), policy=FAST, clock=clock)
        if i % 3 == 0:
            stop_stream(owner_token=f"o{i}")
        elif i % 3 == 1:
            clock.advance(FAST.lease_seconds + 1)  # expiry path
        else:
            wait_state(f"o{i}", ConnectionState.ERROR)  # frames ran out: clean close → bounded reconnects → ERROR
        wait_until(lambda: worker_threads_alive() == 0, what=f"cycle {i} cleanup")
    assert threading.active_count() <= base + 1

    # concurrency: frames, snapshots and stop racing on one session
    clock = FakeClock()
    s = live_session(clock)
    errors: list[BaseException] = []
    stop = threading.Event()

    def feeder():
        k = 0
        while not stop.is_set():
            k += 1
            try:
                s._on_frame(ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=100.0 + (k % 7), trade_ms=ms(T0) + k))
            except BaseException as e:  # noqa: BLE001
                errors.append(e)

    def reader():
        while not stop.is_set():
            try:
                snap = s.snapshot()
                if snap.last_trade_ts is not None:
                    assert snap.book is not None and snap.book.forming is not None
                    assert snap.book.forming.close == snap.book.chart_series()[-1]["close"]
            except BaseException as e:  # noqa: BLE001
                errors.append(e)

    threads = [threading.Thread(target=feeder) for _ in range(2)] + [threading.Thread(target=reader) for _ in range(3)]
    for t in threads:
        t.start()
    time.sleep(0.4)
    s.request_stop()
    stop.set()
    for t in threads:
        t.join(timeout=2.0)
        assert not t.is_alive()
    assert errors == []
    assert s.snapshot().state == ConnectionState.STOPPING


# ============================================================================ R06 status view model (S18)

def _snap(**kw):
    from nifty_lab.stream_chart.stream_session import StreamSnapshot

    base = dict(session_id="s", owner_token="o", mode=StreamMode.LIVE, state=ConnectionState.STREAMING)
    base.update(kw)
    return StreamSnapshot(**base)


def _texts(snap) -> str:
    from nifty_lab.stream_chart.ui import status_lines

    return "\n".join(f"{lvl}|{txt}" for lvl, txt in status_lines(snap))


def test_s18_status_lines_report_stale_waiting_stopping_fault_and_exchange_without_calendar_claims():
    stale = _texts(_snap(state=ConnectionState.STALE, freshness=Freshness.STALE, source_age_sec=3600.0, progress_age_sec=40.0))
    assert "warning|Price STALE" in stale and "3600s" in stale and "Not a current price" in stale
    fresh = _texts(_snap(freshness=Freshness.FRESH, source_age_sec=2.0, progress_age_sec=1.0))
    assert "caption|Price FRESH" in fresh and "warning" not in fresh
    waiting = _texts(_snap(state=ConnectionState.WAITING_FOR_DATA, freshness=Freshness.WAITING, exchange_status="NORMAL_CLOSE"))
    assert "info|Connected, waiting for the first trade" in waiting and "NORMAL_CLOSE" in waiting
    assert "No market calendar is inferred" in waiting and "holiday" not in waiting.lower() and "weekend" not in waiting.lower()
    from nifty_lab.stream_chart.stream_errors import StreamErrorCode, StreamFault

    stopping = _texts(_snap(state=ConnectionState.STOPPING, stop_requested=True))
    assert "warning|STOPPING" in stopping
    fault = _texts(_snap(state=ConnectionState.ERROR, fault=StreamFault(StreamErrorCode.FEED_AUTH_FAILED, "Feed authorization failed. Check local token.")))
    assert "error|FEED_AUTH_FAILED: Feed authorization failed. Check local token." in fault
    expired = _texts(_snap(state=ConnectionState.OWNER_EXPIRED, fault=StreamFault(StreamErrorCode.OWNER_EXPIRED, "Owner lease expired.")))
    assert "warning|OWNER EXPIRED" in expired and "Press Start" in expired
    replay = _texts(_snap(mode=StreamMode.REPLAY, freshness=Freshness.SYNTHETIC))
    assert "synthetic" in replay and "FRESH" not in replay
    gap = _texts(_snap(freshness=Freshness.FRESH, source_age_sec=1.0, progress_age_sec=1.0, reconnect_gap=True, reconnect_attempt=1))
    assert "Reconnect gap recorded" in gap


# ============================================================================ bootstrap on a non-trading day (operator smoke finding)

class RoutedSession:
    """requests.Session stand-in that answers by URL substring."""

    def __init__(self, routes: dict[str, tuple[int, bytes]]) -> None:
        self.routes, self.calls = routes, []

    def get(self, url, *, headers, timeout, allow_redirects):
        self.calls.append(url)
        for needle, (status, body) in self.routes.items():
            if needle in url:
                return FakeResponse(status, body)
        return FakeResponse(404, b"{}")


def test_empty_intraday_bootstrap_on_closed_market_is_zero_bars_not_an_error():
    fake = RoutedSession({"/historical-candle/intraday/": (200, b'{"status":"success","data":{"candles":[]}}'), "/authorize": (200, b'{"data":{"authorizedRedirectUri":"https://not-wss"}}')})
    start_stream(owner_token="wk", mode=StreamMode.LIVE, http=RequestsTransport(session=fake), policy=FAST)  # type: ignore[arg-type]
    snap = wait_state("wk", ConnectionState.ERROR)  # the stubbed authorize is deliberately invalid → proves we got past bootstrap
    assert snap.fault is not None and snap.fault.code.value == "FEED_AUTHORIZE_INVALID"
    assert snap.bootstrap_count == 0 and snap.book is not None
    assert any(n.kind == "bootstrap" for n in snap.book.coverage_notes)
    assert [u for u in fake.calls if "/authorize" in u]  # feed connection was attempted after the empty bootstrap


def test_non_auth_bootstrap_failure_is_reported_as_bootstrap_failed():
    fake = RoutedSession({"/historical-candle/intraday/": (200, b'{"data":{"candles":"not-a-list"}}')})
    start_stream(owner_token="bf", mode=StreamMode.LIVE, http=RequestsTransport(session=fake), policy=FAST)  # type: ignore[arg-type]
    snap = wait_state("bf", ConnectionState.ERROR)
    assert snap.fault is not None and snap.fault.code.value == "BOOTSTRAP_FAILED"
    assert_sanitized(snap.fault.message)
    assert len(fake.calls) == 1  # one attempt, no feed connection
