"""Single-owner stream session: bootstrap once, bounded reconnect, candle book, owner lease (Spec 14 + Spec 15).

Lock strategy
- `_OWNER_LOCK` (registry) guards only the `_ACTIVE` pointer and is never held across I/O, joins or sleeps.
- `StreamSession._lock` guards the session's mutable fields and the book; `_on_frame`, `snapshot()`, the lease
  monitor and state transitions take it briefly. Transport I/O, bootstrap HTTP and backoff waits run outside it.
- Nothing takes the registry lock while holding a session lock, so there is no lock-order inversion.

Clocks: `clock.wall()` (UTC datetime) is used only for source-time comparisons; `clock.mono()` for every elapsed
measurement (progress freshness, lease age, idle purge). Tests inject both.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
import weakref
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol

from nifty_lab.brokers.upstox_errors import UpstoxAuthError
from nifty_lab.brokers.upstox_transport import HttpTransport

from .bootstrap import fetch_intraday_bootstrap
from .candles import CandleBook, CoverageNote
from .constants import (
    IDLE_SESSION_SEC,
    INSTRUMENT_KEY,
    LEASE_MONITOR_INTERVAL_SEC,
    MAX_FUTURE_SKEW_SECONDS,
    MAX_RECONNECT_ATTEMPTS,
    OWNER_LEASE_SECONDS,
    RECEIPT_PROGRESS_SECONDS,
    RECONNECT_BACKOFF_SEC,
    REPLAY_FRAME_DELAY_SEC,
    SOURCE_FRESH_SECONDS,
    STOP_JOIN_BUDGET_SEC,
)
from .feed_decode import decode_feed_frame
from .replay_fixture import ui_demo_scenario
from .stream_errors import FeedAuthError, FeedProtocolError, StreamErrorCode, StreamFault, sanitize_exception
from .transport import LiveWebSocketTransport, RawFeedTransport, ReplayTransport

_LOG = logging.getLogger(__name__)
_OWNER_LOCK = threading.RLock()
_ACTIVE: StreamSession | None = None
_WORKERS: weakref.WeakSet[threading.Thread] = weakref.WeakSet()  # I/O workers and lease monitors


class Clock(Protocol):
    def wall(self) -> datetime: ...

    def mono(self) -> float: ...


class SystemClock:
    def wall(self) -> datetime:
        return datetime.now(timezone.utc)

    def mono(self) -> float:
        return time.monotonic()


@dataclass(frozen=True)
class SessionPolicy:
    source_fresh_seconds: float = SOURCE_FRESH_SECONDS
    receipt_progress_seconds: float = RECEIPT_PROGRESS_SECONDS
    max_future_skew_seconds: float = MAX_FUTURE_SKEW_SECONDS
    lease_seconds: float = OWNER_LEASE_SECONDS
    monitor_interval_sec: float = LEASE_MONITOR_INTERVAL_SEC
    backoff_sec: tuple[float, ...] = RECONNECT_BACKOFF_SEC
    max_reconnect_attempts: int = MAX_RECONNECT_ATTEMPTS
    idle_session_sec: float = IDLE_SESSION_SEC


class StreamMode(str, Enum):
    REPLAY = "replay"
    LIVE = "live"


class ConnectionState(str, Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    WAITING_FOR_DATA = "waiting_for_data"  # link up, no accepted trade yet
    STREAMING = "streaming"  # link up and price FRESH (LIVE) / frames flowing (REPLAY)
    STALE = "stale"  # link up, latest price not fresh
    RECONNECTING = "reconnecting"
    STOPPING = "stopping"  # stop/expiry requested, worker cleanup pending
    STOPPED = "stopped"
    ERROR = "error"
    OWNER_EXPIRED = "owner_expired"
    OWNER_CONFLICT = "owner_conflict"


class Freshness(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    WAITING = "waiting"  # no accepted trade yet
    SYNTHETIC = "synthetic"  # REPLAY fixture timeline; never a freshness claim


_TERMINAL = (ConnectionState.STOPPED, ConnectionState.ERROR, ConnectionState.OWNER_EXPIRED)
_LINK_UP = ConnectionState.STREAMING  # internal transport state: connected, frames observed


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
    freshness: Freshness = Freshness.WAITING
    source_age_sec: float | None = None  # receipt UTC − latest accepted source trade time (clamped ≥ 0)
    progress_age_sec: float | None = None  # monotonic seconds since source time last progressed
    future_ticks_rejected: int = 0
    invalid_ticks_rejected: int = 0
    stop_requested: bool = False


def _conflict(session_id: str, owner_token: str, mode: StreamMode, message: str) -> StreamSnapshot:
    return StreamSnapshot(
        session_id=session_id,
        owner_token=owner_token,
        mode=mode,
        state=ConnectionState.OWNER_CONFLICT,
        fault=StreamFault(StreamErrorCode.OWNER_CONFLICT, message),
        book=None,
    )


@dataclass
class StreamSession:
    session_id: str
    owner_token: str
    mode: StreamMode
    http: HttpTransport | None
    transport: RawFeedTransport
    book: CandleBook
    clock: Clock = field(default_factory=SystemClock)
    policy: SessionPolicy = field(default_factory=SessionPolicy)
    state: ConnectionState = ConnectionState.IDLE
    fault: StreamFault | None = None
    last_trade_ts: datetime | None = None
    last_trade_receipt_ts: datetime | None = None
    last_heartbeat_ts: datetime | None = None
    exchange_status: str = "UNKNOWN"
    bootstrap_count: int = 0
    reconnect_attempt: int = 0
    reconnect_gap: bool = False
    future_ticks_rejected: int = 0
    invalid_ticks_rejected: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None
    _monitor: threading.Thread | None = None
    _progress_mono: float | None = None
    _lease_mono: float = 0.0
    _expired: bool = False
    _stopped_at: float | None = None

    # ------------------------------------------------------------------ liveness / lease
    def is_worker_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop_requested(self) -> bool:
        return self._stop.is_set()

    def renew_lease(self) -> None:
        with self._lock:
            self._lease_mono = self.clock.mono()

    def request_stop(self) -> None:
        """Make this generation terminal for frames and retries; returns immediately (no join)."""
        self._stop.set()

    # ------------------------------------------------------------------ freshness
    def _freshness_locked(self, now_wall: datetime, now_mono: float) -> tuple[Freshness, float | None, float | None]:
        if self.mode == StreamMode.REPLAY:
            return Freshness.SYNTHETIC, None, None
        if self.last_trade_ts is None or self._progress_mono is None:
            return Freshness.WAITING, None, None
        source_age = (now_wall - self.last_trade_ts).total_seconds()
        progress_age = now_mono - self._progress_mono
        fresh = (
            -self.policy.max_future_skew_seconds <= source_age <= self.policy.source_fresh_seconds
            and progress_age <= self.policy.receipt_progress_seconds
        )
        return (Freshness.FRESH if fresh else Freshness.STALE), max(0.0, source_age), progress_age

    def _effective_state_locked(self, freshness: Freshness) -> ConnectionState:
        if self.state in _TERMINAL:
            return self.state
        if self._stop.is_set():
            return ConnectionState.STOPPING
        if self.state != _LINK_UP:
            return self.state
        if self.mode == StreamMode.REPLAY:
            return ConnectionState.STREAMING
        return {
            Freshness.FRESH: ConnectionState.STREAMING,
            Freshness.STALE: ConnectionState.STALE,
            Freshness.WAITING: ConnectionState.WAITING_FOR_DATA,
        }[freshness]

    def snapshot(self) -> StreamSnapshot:
        now_wall, now_mono = self.clock.wall(), self.clock.mono()
        with self._lock:
            freshness, source_age, progress_age = self._freshness_locked(now_wall, now_mono)
            return StreamSnapshot(
                session_id=self.session_id,
                owner_token=self.owner_token,
                mode=self.mode,
                state=self._effective_state_locked(freshness),
                fault=self.fault,
                last_trade_ts=self.last_trade_ts,
                last_trade_receipt_ts=self.last_trade_receipt_ts,
                last_heartbeat_ts=self.last_heartbeat_ts,
                exchange_status=self.exchange_status,
                bootstrap_count=self.bootstrap_count,
                reconnect_attempt=self.reconnect_attempt,
                reconnect_gap=self.reconnect_gap,
                book=self.book.copy(),
                freshness=freshness,
                source_age_sec=source_age,
                progress_age_sec=progress_age,
                future_ticks_rejected=self.future_ticks_rejected,
                invalid_ticks_rejected=self.invalid_ticks_rejected,
                stop_requested=self._stop.is_set(),
            )

    # ------------------------------------------------------------------ frames
    def _on_frame(self, raw: bytes) -> None:
        if self._stop.is_set():  # terminal generation: late frames never mutate state
            return
        try:
            frame = decode_feed_frame(raw)
        except Exception as exc:  # noqa: BLE001 — undecodable bytes: bounded counter, no echo
            _LOG.debug("decode skip: %s", type(exc).__name__)
            with self._lock:
                self.invalid_ticks_rejected += 1
            return
        now_wall, now_mono = self.clock.wall(), self.clock.mono()
        with self._lock:
            if self._stop.is_set():
                return
            self.invalid_ticks_rejected += frame.rejected_ticks
            if self.state in (ConnectionState.CONNECTING, ConnectionState.RECONNECTING):
                self.state = _LINK_UP  # any decoded frame proves the link; freshness is judged separately
                self.fault = None
            if frame.market_info is not None:
                self.last_heartbeat_ts = frame.market_info.receipt_ts_utc
                self.exchange_status = frame.market_info.segment_status.get("NSE_EQ") or self.exchange_status
                return
            for tick in frame.ticks:
                if tick.instrument_key != INSTRUMENT_KEY:
                    continue
                if self.mode == StreamMode.LIVE and (tick.trade_ts_utc - now_wall).total_seconds() > self.policy.max_future_skew_seconds:
                    self.future_ticks_rejected += 1  # rejected before any book/high-water/freshness mutation
                    continue
                trade_ms = int(tick.trade_ts_utc.timestamp() * 1000)
                if self.book.apply_trade(price=tick.price, trade_ms=trade_ms):
                    self.last_trade_receipt_ts = now_wall
                    if self.last_trade_ts is None or tick.trade_ts_utc > self.last_trade_ts:
                        self.last_trade_ts = tick.trade_ts_utc  # never regresses
                        self._progress_mono = now_mono  # only genuine source-time progress refreshes this

    # ------------------------------------------------------------------ worker
    def _bootstrap(self) -> None:
        if self.mode == StreamMode.REPLAY:
            scenario = ui_demo_scenario()
            with self._lock:
                self.book.load_replay_bootstrap(scenario.bootstrap)
                self.bootstrap_count = len(scenario.bootstrap)
            return
        if self.http is None:  # injected live transport: no broker bootstrap
            return
        bars = fetch_intraday_bootstrap(self.http)  # one attempt per Start; HTTP outside any lock
        with self._lock:
            self.book.merge_bootstrap(bars)
            self.bootstrap_count = len(bars)
            if not bars:
                self.book.coverage_notes.append(CoverageNote("bootstrap", "No intraday candles returned (market closed or pre-open); streaming without bootstrap bars."))

    def _set_terminal(self, state: ConnectionState, fault: StreamFault | None) -> None:
        with self._lock:
            self.state = state
            self.fault = fault

    def _exhausted(self, category: str) -> None:
        self._set_terminal(
            ConnectionState.ERROR,
            StreamFault(StreamErrorCode.MAX_RECONNECT, f"Reconnect budget exhausted after {self.policy.max_reconnect_attempts} attempts ({category})."),
        )

    def _worker(self) -> None:
        attempt = 0
        try:
            try:
                self._bootstrap()
            except (FeedAuthError, UpstoxAuthError) as exc:  # bootstrap is one attempt per Start
                self._set_terminal(ConnectionState.ERROR, sanitize_exception(exc))
                return
            except Exception as exc:  # noqa: BLE001
                category = sanitize_exception(exc).code.value
                self._set_terminal(ConnectionState.ERROR, StreamFault(StreamErrorCode.BOOTSTRAP_FAILED, f"Intraday bootstrap failed ({category}). Nothing was streamed."))
                return
            while not self._stop.is_set():
                try:
                    if attempt > 0:
                        with self._lock:
                            self.state = ConnectionState.RECONNECTING
                            self.reconnect_attempt = attempt
                            self.reconnect_gap = True
                        backoff = self.policy.backoff_sec[min(attempt - 1, len(self.policy.backoff_sec) - 1)]
                        if self._stop.wait(backoff):
                            break
                    else:
                        with self._lock:
                            self.state = ConnectionState.CONNECTING
                    self.transport.run(on_frame=self._on_frame, stop_event=self._stop)
                    if self._stop.is_set():
                        break
                    if self.mode == StreamMode.REPLAY:
                        self._set_terminal(ConnectionState.STOPPED, None)
                        break
                    attempt += 1
                    if attempt > self.policy.max_reconnect_attempts:
                        self._exhausted("clean close")
                        break
                except (FeedAuthError, FeedProtocolError, UpstoxAuthError) as exc:  # non-retryable by design
                    self._set_terminal(ConnectionState.ERROR, sanitize_exception(exc))
                    break
                except Exception as exc:  # noqa: BLE001 — transport/server failure: bounded reconnect loop
                    if self._stop.is_set():
                        break
                    attempt += 1
                    if attempt > self.policy.max_reconnect_attempts:
                        self._exhausted(sanitize_exception(exc).code.value)
                        break
        finally:
            with self._lock:
                if self.state not in _TERMINAL:
                    self.state = ConnectionState.OWNER_EXPIRED if self._expired else ConnectionState.STOPPED
                self._stopped_at = self.clock.mono()

    def _lease_monitor(self) -> None:
        """Bounded per-session monitor: expires an abandoned owner without any registry call, then exits."""
        while not self._stop.wait(self.policy.monitor_interval_sec):
            if not self.is_worker_alive():
                return
            with self._lock:
                expired = self.clock.mono() - self._lease_mono > self.policy.lease_seconds
                if expired:
                    self._expired = True
                    self.fault = StreamFault(StreamErrorCode.OWNER_EXPIRED, "Owner lease expired (no keepalive from the owning page). Press Start to resume.")
            if expired:
                self._stop.set()
                return

    def start(self) -> None:
        if self.is_worker_alive():
            return
        self._stop.clear()
        with self._lock:
            self.state = ConnectionState.CONNECTING
            self._lease_mono = self.clock.mono()
        self._thread = threading.Thread(target=self._worker, name=f"stream-{self.session_id[:8]}", daemon=True)
        self._monitor = threading.Thread(target=self._lease_monitor, name=f"lease-{self.session_id[:8]}", daemon=True)
        _WORKERS.add(self._thread)
        _WORKERS.add(self._monitor)
        self._thread.start()
        self._monitor.start()

    def join_monitor(self, timeout: float = 1.0) -> None:
        """The monitor only ever waits on the stop event, so after request_stop() this returns promptly."""
        if self._monitor is not None and self._monitor.is_alive():
            self._monitor.join(timeout)

    def stop(self, timeout: float = STOP_JOIN_BUDGET_SEC) -> None:
        """Blocking stop for tests/registry reset: request, then wait up to the shutdown budget."""
        self.request_stop()
        self.join_monitor()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout)


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
    if _ACTIVE is None or _ACTIVE.is_worker_alive() or _ACTIVE._stopped_at is None:
        return
    if _ACTIVE.clock.mono() - _ACTIVE._stopped_at > _ACTIVE.policy.idle_session_sec:
        _ACTIVE = None


def start_stream(
    *,
    owner_token: str,
    mode: StreamMode = StreamMode.REPLAY,
    http: HttpTransport | None = None,
    replay_frames: list[bytes] | None = None,
    replay_delay_sec: float | None = None,
    live_transport: RawFeedTransport | None = None,
    clock: Clock | None = None,
    policy: SessionPolicy | None = None,
) -> StreamSnapshot:
    """Create and start a session. Returns immediately; bootstrap and I/O happen on the session worker."""
    global _ACTIVE
    delay = REPLAY_FRAME_DELAY_SEC if replay_delay_sec is None else replay_delay_sec
    with _OWNER_LOCK:
        _purge_idle_locked()
        if _ACTIVE is not None and _ACTIVE.is_worker_alive():
            if _ACTIVE.stop_requested():
                return _conflict(_ACTIVE.session_id, owner_token, mode, "Previous stream still stopping.")
            if _ACTIVE.owner_token == owner_token:
                return _ACTIVE.snapshot()
            return _conflict(_ACTIVE.session_id, owner_token, mode, "Another stream owner is active.")
        if _ACTIVE is not None:  # dead worker: release its monitor, then replace
            _ACTIVE.request_stop()
            _ACTIVE.join_monitor()
        session = StreamSession(
            session_id=uuid.uuid4().hex,
            owner_token=owner_token,
            mode=mode,
            http=http,
            transport=_build_transport(mode, http, replay_frames, replay_delay_sec=delay, live_transport=live_transport),
            book=CandleBook(),
            clock=clock or SystemClock(),
            policy=policy or SessionPolicy(),
        )
        _ACTIVE = session
        session.start()
        return session.snapshot()


def _owns(owner_token: str | None, session_id: str | None) -> bool:
    assert _ACTIVE is not None
    if owner_token is not None and _ACTIVE.owner_token != owner_token:
        return False
    return session_id is None or _ACTIVE.session_id == session_id


def stop_stream(*, owner_token: str | None = None, session_id: str | None = None) -> StreamSnapshot | None:
    """Owner/generation-validated stop. Returns within the UI budget: no join of the I/O worker."""
    global _ACTIVE
    with _OWNER_LOCK:
        if _ACTIVE is None:
            return None
        if not _owns(owner_token, session_id):
            return _conflict(_ACTIVE.session_id, owner_token or "", _ACTIVE.mode, "Stop rejected for non-owner.")
        _ACTIVE.request_stop()
        _ACTIVE.join_monitor()
        snap = _ACTIVE.snapshot()
        if not _ACTIVE.is_worker_alive():
            _ACTIVE = None
        return snap


def stop_for_credential_change() -> bool:
    """Spec 16: credentials are being replaced — stop whatever is active regardless of owner. Returns True if a
    running session was asked to stop. The next session requires an explicit Start with the new credential."""
    with _OWNER_LOCK:
        if _ACTIVE is None or not _ACTIVE.is_worker_alive():
            return False
        with _ACTIVE._lock:
            _ACTIVE.fault = StreamFault(StreamErrorCode.CREDENTIALS_REPLACED, "Upstox credentials were replaced; this stream was stopped. Press Start to resume with the new token.")
        _ACTIVE.request_stop()
        _ACTIVE.join_monitor()
        return True


def keepalive(*, owner_token: str, session_id: str | None = None) -> bool:
    """Renew the owner lease. Only the current owner (and generation, if given) of a live session may renew."""
    with _OWNER_LOCK:
        if _ACTIVE is None or not _ACTIVE.is_worker_alive() or _ACTIVE.stop_requested():
            return False
        if not _owns(owner_token, session_id):
            return False
        _ACTIVE.renew_lease()
        return True


def active_snapshot(*, owner_token: str | None = None, session_id: str | None = None) -> StreamSnapshot | None:
    """Read-only; never renews the lease."""
    with _OWNER_LOCK:
        _purge_idle_locked()
        if _ACTIVE is None:
            return None
        if not _owns(owner_token, session_id):
            return _conflict(_ACTIVE.session_id, owner_token or "", _ACTIVE.mode, "Snapshot not available for this owner.")
        return _ACTIVE.snapshot()


def worker_threads_alive() -> int:
    """Alive session threads (I/O workers and lease monitors)."""
    with _OWNER_LOCK:
        return sum(1 for t in list(_WORKERS) if t.is_alive())


def reset_stream_registry_for_tests() -> None:
    global _ACTIVE
    with _OWNER_LOCK:
        active = _ACTIVE
        _ACTIVE = None
    if active is not None:
        active.stop(timeout=5.0)
    for t in list(_WORKERS):
        if t.is_alive():
            t.join(timeout=5.0)
