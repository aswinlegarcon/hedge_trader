"""Spec 15 — real WebSocket client compatibility on loopback (R07) and secret-safe diagnostics at DEBUG (R08).

Marked `loopback`: these tests open 127.0.0.1 sockets only. The remote authorize boundary is a fake
requests.Session inside the real RequestsTransport that answers with a ws://127.0.0.1 URI (test seam
`allow_loopback_ws`); connect/send/recv/close are the real `websockets` client. Never touches broker hosts.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus

import pytest

from nifty_lab.brokers import upstox_transport
from nifty_lab.brokers.upstox_transport import RequestsTransport
from nifty_lab.stream_chart.constants import INSTRUMENT_KEY, MAX_RECONNECT_ATTEMPTS, SUBSCRIBE_MODE
from nifty_lab.stream_chart.fixtures import ltpc_frame, market_info_frame
from nifty_lab.stream_chart.stream_session import (
    ConnectionState,
    SessionPolicy,
    StreamMode,
    active_snapshot,
    reset_stream_registry_for_tests,
    start_stream,
    stop_stream,
    worker_threads_alive,
)
from nifty_lab.stream_chart.transport import LiveWebSocketTransport

websockets = pytest.importorskip("websockets")
from websockets.asyncio.server import serve  # noqa: E402

pytestmark = pytest.mark.loopback

DUMMY_TOKEN = "DUMMYTOKEN-S22-7f3a9c"
SECRET_PATH = "SECRETPATH-1b2c3d"
SECRET_QUERY = "SECRETQUERY-4e5f6a"
MARKERS = (DUMMY_TOKEN, SECRET_PATH, SECRET_QUERY, "Bearer ", "authorizedRedirect")
FAST = SessionPolicy(lease_seconds=10.0, monitor_interval_sec=0.05, backoff_sec=(0.05, 0.05, 0.05))
# Test-server logger (the fake Upstox side). Gated by level like the production transport logger, because pytest
# attaches its capture handler to non-propagating loggers too; the server's request line is not app output.
_SILENT = logging.getLogger("tests.loopback.server")
_SILENT.propagate = False
_SILENT.setLevel(logging.WARNING)
_SILENT.addHandler(logging.NullHandler())


def now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def fresh_frames(n: int = 3) -> list[bytes]:
    base = now_ms() - 5_000
    return [market_info_frame(receipt_ms=base)] + [ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=100.0 + i, trade_ms=base + i * 100) for i in range(n)]


class LoopbackFeedServer:
    """Real websockets server on 127.0.0.1: records the subscribe frame, replays schema-encoded frames."""

    def __init__(self, frames: list[bytes], *, close_after: int | None = None, reject_handshake: bool = False) -> None:
        self.frames, self.close_after, self.reject_handshake = frames, close_after, reject_handshake
        self.subscribes: list[object] = []
        self.connections = 0
        self.handshakes = 0
        self.open: set = set()
        self.port: int | None = None
        self._ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop: asyncio.Future | None = None
        self._thread: threading.Thread | None = None

    async def _handler(self, ws) -> None:
        self.connections += 1
        self.open.add(ws)
        try:
            self.subscribes.append(await ws.recv())
            for i, frame in enumerate(self.frames):
                await ws.send(frame)
                if self.close_after is not None and i + 1 >= self.close_after:
                    await ws.close()
                    return
                await asyncio.sleep(0.02)
            await ws.wait_closed()  # hold open until the client closes (Stop)
        finally:
            self.open.discard(ws)

    def _process_request(self, connection, request):
        self.handshakes += 1
        if self.reject_handshake:
            return connection.respond(HTTPStatus.FORBIDDEN, "Forbidden\n")
        return None

    def _run(self) -> None:
        async def main() -> None:
            self._stop = asyncio.get_running_loop().create_future()
            async with serve(self._handler, "127.0.0.1", 0, process_request=self._process_request, logger=_SILENT) as server:
                self.port = server.sockets[0].getsockname()[1]
                self._ready.set()
                await self._stop

        self._loop = asyncio.new_event_loop()
        self._loop.run_until_complete(main())
        self._loop.close()

    def __enter__(self):
        self._thread = threading.Thread(target=self._run, name="loopback-feed", daemon=True)
        self._thread.start()
        assert self._ready.wait(5.0), "loopback server did not start"
        return self

    def __exit__(self, *exc) -> None:
        assert self._loop is not None and self._stop is not None
        self._loop.call_soon_threadsafe(self._stop.set_result, None)
        self._thread.join(5.0)
        assert not self._thread.is_alive()

    def uri(self) -> str:
        return f"ws://127.0.0.1:{self.port}/feed/{SECRET_PATH}?token={SECRET_QUERY}"


class FakeResponse:
    def __init__(self, status: int, content: bytes) -> None:
        self.status_code, self.content, self.headers = status, content, {}


class FakeAuthorize:
    """requests.Session stand-in: the only remote boundary that is stubbed."""

    def __init__(self, status: int, uri: str | None) -> None:
        self.status, self.uri, self.calls = status, uri, 0

    def get(self, url, *, headers, timeout, allow_redirects):
        self.calls += 1
        assert headers["Authorization"] == f"Bearer {DUMMY_TOKEN}"
        body = json.dumps({"data": {"authorizedRedirectUri": self.uri}}).encode() if self.uri else b"{}"
        return FakeResponse(self.status, body)


def live_transport(server: LoopbackFeedServer | None, status: int = 200) -> tuple[LiveWebSocketTransport, FakeAuthorize]:
    fake = FakeAuthorize(status, server.uri() if server else None)
    return LiveWebSocketTransport(RequestsTransport(session=fake), allow_loopback_ws=True), fake  # type: ignore[arg-type]


def socket_fds() -> int:
    if sys.platform != "linux":
        return 0
    count = 0
    for fd in os.listdir("/proc/self/fd"):
        try:
            count += os.readlink(f"/proc/self/fd/{fd}").startswith("socket:")
        except FileNotFoundError:  # the listing fd itself closes while we iterate
            continue
    return count


def wait_until(pred, timeout: float = 5.0, what: str = "condition"):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return
        time.sleep(0.01)
    pytest.fail(f"timeout waiting for {what}")


def wait_state(owner: str, *states: ConnectionState, timeout: float = 5.0):
    out: dict = {}

    def ok():
        out["s"] = active_snapshot(owner_token=owner)
        return out["s"] is not None and out["s"].state in states

    wait_until(ok, timeout, f"{states} (last={out.get('s') and out['s'].state})")
    return out["s"]


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    reset_stream_registry_for_tests()
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", DUMMY_TOKEN)
    monkeypatch.setattr(upstox_transport, "MIN_INTERVAL_SEC", 0.0)
    yield
    reset_stream_registry_for_tests()


def test_s20_production_client_subscribes_decodes_and_closes_on_stop():
    fds0 = socket_fds()
    with LoopbackFeedServer(fresh_frames(3)) as server:
        transport, auth = live_transport(server)
        start_stream(owner_token="lb", mode=StreamMode.LIVE, live_transport=transport, policy=FAST)
        snap = wait_state("lb", ConnectionState.STREAMING)
        assert auth.calls == 1 and server.connections == 1
        assert len(server.subscribes) == 1 and isinstance(server.subscribes[0], bytes)  # binary subscribe frame
        payload = json.loads(server.subscribes[0].decode("utf-8"))
        assert payload["method"] == "sub" and payload["data"] == {"mode": SUBSCRIBE_MODE, "instrumentKeys": [INSTRUMENT_KEY]}
        assert snap.exchange_status == "NORMAL_OPEN" and snap.book is not None and snap.book.forming is not None
        wait_until(lambda: active_snapshot(owner_token="lb").book.forming.close == 102.0, what="all three schema-encoded trades decoded")
        assert active_snapshot(owner_token="lb").last_trade_ts is not None
        t0 = time.perf_counter()
        stop_stream(owner_token="lb")
        wait_until(lambda: worker_threads_alive() == 0, timeout=5.0, what="client worker exit")
        wait_until(lambda: not server.open, timeout=5.0, what="server observes client close")
        assert time.perf_counter() - t0 < 2.0
        assert active_snapshot(owner_token="lb").state == ConnectionState.STOPPED
    wait_until(lambda: socket_fds() <= fds0, timeout=5.0, what="sockets released")


def test_s21_disconnect_then_reconnect_uses_production_lifecycle():
    with LoopbackFeedServer(fresh_frames(4), close_after=2) as server:
        transport, auth = live_transport(server)
        start_stream(owner_token="rc", mode=StreamMode.LIVE, live_transport=transport, policy=FAST)
        wait_until(lambda: server.connections >= 2, timeout=5.0, what="second connection after server close")
        snap = wait_state("rc", ConnectionState.STREAMING, ConnectionState.STALE, ConnectionState.WAITING_FOR_DATA)
        assert snap.reconnect_attempt >= 1 and snap.reconnect_gap is True
        assert auth.calls == server.connections  # one authorize per connection attempt
        assert len(server.subscribes) == server.connections
        snap = wait_state("rc", ConnectionState.ERROR, timeout=5.0)  # server keeps closing → budget exhausted
        assert snap.fault is not None and snap.fault.code.value == "MAX_RECONNECT"
        assert server.connections == 1 + MAX_RECONNECT_ATTEMPTS
        wait_until(lambda: worker_threads_alive() == 0, what="worker exit")
        wait_until(lambda: not server.open, what="server side closed")


def test_s21_authorize_rejection_never_reaches_the_socket():
    with LoopbackFeedServer(fresh_frames(1)) as server:
        transport, auth = live_transport(server, status=401)
        start_stream(owner_token="au", mode=StreamMode.LIVE, live_transport=transport, policy=FAST)
        snap = wait_state("au", ConnectionState.ERROR)
        assert snap.fault is not None and snap.fault.code.value == "FEED_AUTH_FAILED"
        assert auth.calls == 1 and server.handshakes == 0 and server.connections == 0
        wait_until(lambda: worker_threads_alive() == 0, what="worker exit")


def test_s21_handshake_rejection_is_bounded_and_classified():
    with LoopbackFeedServer(fresh_frames(1), reject_handshake=True) as server:
        transport, auth = live_transport(server)
        start_stream(owner_token="hs", mode=StreamMode.LIVE, live_transport=transport, policy=FAST)
        snap = wait_state("hs", ConnectionState.ERROR, timeout=8.0)
        assert snap.fault is not None and snap.fault.code.value == "MAX_RECONNECT"
        assert server.handshakes == 1 + MAX_RECONNECT_ATTEMPTS == auth.calls
        assert server.connections == 0 and snap.reconnect_gap is True
        wait_until(lambda: worker_threads_alive() == 0, what="worker exit")


def _assert_no_markers(records: list[logging.LogRecord], extra: list[str]) -> None:
    texts = [r.getMessage() for r in records] + [str(r.exc_info[1]) for r in records if r.exc_info and r.exc_info[1]] + extra
    for text in texts:
        for marker in MARKERS:
            assert marker not in text, f"{marker!r} leaked: {text[:200]!r}"


@pytest.mark.parametrize("reject_handshake", [False, True])
def test_s22_debug_logging_everywhere_leaks_no_token_or_authorized_uri(caplog, reject_handshake):
    loggers = [logging.getLogger(), logging.getLogger("websockets"), logging.getLogger("urllib3"), logging.getLogger("nifty_lab")]
    levels = [lg.level for lg in loggers]
    for lg in loggers:
        lg.setLevel(logging.DEBUG)
    try:
        with caplog.at_level(logging.DEBUG), LoopbackFeedServer(fresh_frames(2), reject_handshake=reject_handshake) as server:
            transport, _ = live_transport(server)
            start_stream(owner_token="dbg", mode=StreamMode.LIVE, live_transport=transport, policy=FAST)
            if reject_handshake:
                snap = wait_state("dbg", ConnectionState.ERROR, timeout=8.0)
            else:
                snap = wait_state("dbg", ConnectionState.STREAMING)
                assert server.connections == 1
            stop_stream(owner_token="dbg")
            wait_until(lambda: worker_threads_alive() == 0, what="worker exit")
            final = active_snapshot(owner_token="dbg")
        extra = [repr(snap), repr(final), snap.fault.message if snap.fault else "", json.dumps(snap.book.chart_series())]
        assert caplog.records, "DEBUG capture should see at least the app's own records"
        _assert_no_markers(caplog.records, extra)
    finally:
        for lg, lvl in zip(loggers, levels):
            lg.setLevel(lvl)
