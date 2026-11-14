"""Single-owner stream session: bootstrap once, bounded reconnect, candle book."""
from __future__ import annotations

import logging
import threading
import time
import uuid
import weakref
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from nifty_lab.brokers.upstox_transport import HttpTransport

from .bootstrap import fetch_intraday_bootstrap
from .candles import CandleBook
from .constants import (
    IDLE_SESSION_SEC,
    INSTRUMENT_KEY,
    MAX_RECONNECT_ATTEMPTS,
    RECONNECT_BACKOFF_SEC,
    REPLAY_FRAME_DELAY_SEC,
    STALE_TRADE_SECONDS,
)
from .feed_decode import decode_feed_message
from .replay_fixture import ui_demo_scenario
from .stream_errors import FeedAuthError, StreamErrorCode, StreamFault, sanitize_exception
from .transport import LiveWebSocketTransport, RawFeedTransport, ReplayTransport, ScriptedLiveTransport

_LOG = logging.getLogger(__name__)
_OWNER_LOCK = threading.RLock()
_ACTIVE: StreamSession | None = None
_WORKERS: weakref.WeakSet[threading.Thread] = weakref.WeakSet()


class StreamMode(str, Enum):
    REPLAY = "replay"
    LIVE = "live"


class ConnectionState(str, Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    STREAMING = "streaming"
    STALE = "stale"
    RECONNECTING = "reconnecting"
    ERROR = "error"
    STOPPED = "stopped"
    OWNER_CONFLICT = "owner_conflict"


@dataclass(frozen=True)
class StreamSnapshot:
    session_id: str
    owner_token: str
    mode: StreamMode
    state: ConnectionState
    fault: StreamFault | None = None
    last_trade_ts: datetime | None = None
    last_trade_receipt_ts: datetime | None = None
    last_heartbeat_ts: datetime | None = None
    exchange_status: str = "UNKNOWN"
    bootstrap_count: int = 0
    reconnect_attempt: int = 0
    reconnect_gap: bool = False
    book: CandleBook | None = None


@dataclass
class StreamSession:
    session_id: str
    owner_token: str
    mode: StreamMode
    http: HttpTransport | None
    transport: RawFeedTransport
    book: CandleBook
    state: ConnectionState = ConnectionState.IDLE
    fault: StreamFault | None = None
    last_trade_ts: datetime | None = None
    last_trade_receipt_ts: datetime | None = None
    last_heartbeat_ts: datetime | None = None
    exchange_status: str = "UNKNOWN"
    bootstrap_count: int = 0
    reconnect_attempt: int = 0
    reconnect_gap: bool = False
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None
    _started_bootstrap: bool = False
    _stopped_at: float | None = None

    def is_worker_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _effective_state(self) -> ConnectionState:
        if self.state == ConnectionState.STREAMING and self.last_trade_receipt_ts:
            age = (datetime.now(timezone.utc) - self.last_trade_receipt_ts).total_seconds()
            if age > STALE_TRADE_SECONDS:
                return ConnectionState.STALE
        return self.state

    def snapshot(self) -> StreamSnapshot:
        return StreamSnapshot(
            session_id=self.session_id,
            owner_token=self.owner_token,
            mode=self.mode,
            state=self._effective_state(),
            fault=self.fault,
            last_trade_ts=self.last_trade_ts,
            last_trade_receipt_ts=self.last_trade_receipt_ts,
            last_heartbeat_ts=self.last_heartbeat_ts,
            exchange_status=self.exchange_status,
            bootstrap_count=self.bootstrap_count,
            reconnect_attempt=self.reconnect_attempt,
            reconnect_gap=self.reconnect_gap,
            book=self.book.copy(),
        )

    def _bootstrap_once(self) -> None:
        if self._started_bootstrap:
            return
        if self.mode == StreamMode.REPLAY:
            scenario = ui_demo_scenario()
            self.book.load_replay_bootstrap(scenario.bootstrap)
            self.bootstrap_count = len(scenario.bootstrap)
        else:
            if self.http is None:
                # Test/live-transport injection path — no broker bootstrap.
                self._started_bootstrap = True
                return
            bars = fetch_intraday_bootstrap(self.http)
            self.book.merge_bootstrap(bars)
            self.bootstrap_count = len(bars)
        self._started_bootstrap = True

    def _on_frame(self, raw: bytes) -> None:
        try:
            _type, ticks, market_info = decode_feed_message(raw)
        except Exception as exc:  # noqa: BLE001
            _LOG.debug("decode skip: %s", type(exc).__name__)
            return
        now = datetime.now(timezone.utc)
        if market_info is not None:
            self.last_heartbeat_ts = market_info.receipt_ts_utc
            segs = market_info.segment_status
            self.exchange_status = segs.get("NSE_EQ") or self.exchange_status
            return
        for tick in ticks:
            if tick.instrument_key != INSTRUMENT_KEY:
                continue
            trade_ms = int(tick.trade_ts_utc.timestamp() * 1000)
            if self.book.apply_trade(price=tick.price, trade_ms=trade_ms):
                self.last_trade_ts = tick.trade_ts_utc
                self.last_trade_receipt_ts = now
                if self.state in (ConnectionState.CONNECTING, ConnectionState.RECONNECTING):
                    self.state = ConnectionState.STREAMING
                    self.fault = None

    def _worker(self) -> None:
        attempt = 0
        try:
            while not self._stop.is_set():
                try:
                    if attempt > 0:
                        self.state = ConnectionState.RECONNECTING
                        self.reconnect_attempt = attempt
                        self.reconnect_gap = True
                        backoff = RECONNECT_BACKOFF_SEC[min(attempt - 1, len(RECONNECT_BACKOFF_SEC) - 1)]
                        if self._stop.wait(backoff):
                            break
                    else:
                        self.state = ConnectionState.CONNECTING
                    self.transport.run(on_frame=self._on_frame, stop_event=self._stop)
                    if self._stop.is_set():
                        break
                    if self.mode == StreamMode.REPLAY:
                        if self.state != ConnectionState.ERROR:
                            self.state = ConnectionState.STOPPED
                        break
                    attempt += 1
                    if attempt > MAX_RECONNECT_ATTEMPTS:
                        self.state = ConnectionState.ERROR
                        self.fault = StreamFault(StreamErrorCode.MAX_RECONNECT, "Max reconnect attempts exceeded.")
                        break
                except FeedAuthError as exc:
                    self.state = ConnectionState.ERROR
                    self.fault = sanitize_exception(exc)
                    break
                except Exception as exc:  # noqa: BLE001
                    if self._stop.is_set():
                        break
                    attempt += 1
                    if attempt > MAX_RECONNECT_ATTEMPTS:
                        self.state = ConnectionState.ERROR
                        self.fault = sanitize_exception(exc)
                        break
        finally:
            if self.state not in (ConnectionState.ERROR, ConnectionState.STOPPED):
                if self._stop.is_set():
                    self.state = ConnectionState.STOPPED
                else:
                    self.state = ConnectionState.STOPPED
            self._stopped_at = time.monotonic()

    def start(self) -> None:
        if self.is_worker_alive():
            return
        self._stop.clear()
        try:
            self._bootstrap_once()
        except Exception as exc:  # noqa: BLE001
            self.state = ConnectionState.ERROR
            self.fault = sanitize_exception(exc)
            return
        self._thread = threading.Thread(target=self._worker, name=f"stream-{self.session_id}", daemon=True)
        _WORKERS.add(self._thread)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        if self._thread and self._thread.is_alive():
            return
        if self.state != ConnectionState.ERROR:
            self.state = ConnectionState.STOPPED
        self._stopped_at = time.monotonic()
        self._thread = None


def _build_transport(
    mode: StreamMode,
    http: HttpTransport | None,
    replay_frames: list[bytes] | None,
    *,
    replay_delay_sec: float,
    live_transport: RawFeedTransport | None,
) -> RawFeedTransport:
    if live_transport is not None:
        return live_transport
    if mode == StreamMode.REPLAY:
        scenario = ui_demo_scenario()
        frames = replay_frames if replay_frames is not None else scenario.frames
        return ReplayTransport(frames, frame_delay_sec=replay_delay_sec)
    if http is None:
        raise RuntimeError("LIVE mode requires HTTP transport.")
    return LiveWebSocketTransport(http)


def _purge_idle_locked() -> None:
    global _ACTIVE
    if _ACTIVE is None:
        return
    if _ACTIVE.is_worker_alive():
        return
    if _ACTIVE._stopped_at is None:
        return
    if time.monotonic() - _ACTIVE._stopped_at > IDLE_SESSION_SEC:
        _ACTIVE = None


def start_stream(
    *,
    owner_token: str,
    mode: StreamMode = StreamMode.REPLAY,
    http: HttpTransport | None = None,
    replay_frames: list[bytes] | None = None,
    replay_delay_sec: float | None = None,
    live_transport: RawFeedTransport | None = None,
) -> StreamSnapshot:
    global _ACTIVE
    delay = REPLAY_FRAME_DELAY_SEC if replay_delay_sec is None else replay_delay_sec
    with _OWNER_LOCK:
        _purge_idle_locked()
        if _ACTIVE is not None and _ACTIVE.is_worker_alive():
            if _ACTIVE.owner_token == owner_token:
                return _ACTIVE.snapshot()
            return StreamSnapshot(
                session_id=_ACTIVE.session_id,
                owner_token=owner_token,
                mode=mode,
                state=ConnectionState.OWNER_CONFLICT,
                fault=StreamFault(StreamErrorCode.OWNER_CONFLICT, "Another stream owner is active."),
                book=None,
            )
        if _ACTIVE is not None:
            _ACTIVE.stop()
            if _ACTIVE.is_worker_alive():
                return StreamSnapshot(
                    session_id=_ACTIVE.session_id,
                    owner_token=owner_token,
                    mode=mode,
                    state=ConnectionState.OWNER_CONFLICT,
                    fault=StreamFault(StreamErrorCode.OWNER_CONFLICT, "Previous stream still stopping."),
                    book=None,
                )
        session = StreamSession(
            session_id=str(uuid.uuid4()),
            owner_token=owner_token,
            mode=mode,
            http=http,
            transport=_build_transport(mode, http, replay_frames, replay_delay_sec=delay, live_transport=live_transport),
            book=CandleBook(),
        )
        _ACTIVE = session
        session.start()
        return session.snapshot()


def stop_stream(*, owner_token: str | None = None) -> StreamSnapshot | None:
    global _ACTIVE
    with _OWNER_LOCK:
        if _ACTIVE is None:
            return None
        if owner_token is not None and _ACTIVE.owner_token != owner_token:
            return StreamSnapshot(
                session_id=_ACTIVE.session_id,
                owner_token=owner_token,
                mode=_ACTIVE.mode,
                state=ConnectionState.OWNER_CONFLICT,
                fault=StreamFault(StreamErrorCode.OWNER_CONFLICT, "Stop rejected for non-owner."),
                book=_ACTIVE.book.copy(),
            )
        _ACTIVE.stop()
        snap = _ACTIVE.snapshot()
        if not _ACTIVE.is_worker_alive():
            _ACTIVE = None
        return snap


def active_snapshot(*, owner_token: str | None = None) -> StreamSnapshot | None:
    with _OWNER_LOCK:
        _purge_idle_locked()
        if _ACTIVE is None:
            return None
        if owner_token is not None and _ACTIVE.owner_token != owner_token:
            return StreamSnapshot(
                session_id=_ACTIVE.session_id,
                owner_token=owner_token,
                mode=_ACTIVE.mode,
                state=ConnectionState.OWNER_CONFLICT,
                fault=StreamFault(StreamErrorCode.OWNER_CONFLICT, "Snapshot not available for this owner."),
                book=None,
            )
        return _ACTIVE.snapshot()


def worker_threads_alive() -> int:
    with _OWNER_LOCK:
        return sum(1 for t in list(_WORKERS) if t.is_alive())


def reset_stream_registry_for_tests() -> None:
    global _ACTIVE
    with _OWNER_LOCK:
        if _ACTIVE is not None:
            _ACTIVE.stop()
        _ACTIVE = None