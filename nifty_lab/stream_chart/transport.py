"""Feed transports — REPLAY (deterministic) and LIVE (authorized WebSocket)."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import Callable
from typing import Protocol

from nifty_lab.brokers.upstox_errors import UpstoxAuthError
from nifty_lab.brokers.upstox_market_data import read_access_token
from nifty_lab.brokers.upstox_transport import API_HOST, HttpTransport, build_auth_header

from .constants import FEED_AUTHORIZE_PATH, INSTRUMENT_KEY, SUBSCRIBE_MODE, WS_CLOSE_TIMEOUT_SEC, WS_OPEN_TIMEOUT_SEC, WS_RECV_POLL_SEC
from .feed_decode import build_subscribe_frame
from .stream_errors import FeedAuthError, FeedProtocolError

# Dedicated transport logger (Spec 15 design §6). The websockets library logs handshake request lines/headers at
# DEBUG — those can carry the authorized URI — so this logger never propagates and emits nothing below WARNING,
# regardless of root/"websockets" logger levels. Application diagnostics stay on the module logger below.
_WS_LOG = logging.getLogger("nifty_lab.stream_chart.transport.ws")
_WS_LOG.propagate = False
_WS_LOG.setLevel(logging.WARNING)
_WS_LOG.addHandler(logging.NullHandler())
_LOG = logging.getLogger(__name__)

_LOOPBACK_WS_PREFIXES = ("ws://127.0.0.1:", "ws://localhost:")


class RawFeedTransport(Protocol):
    def run(self, *, on_frame: Callable[[bytes], None], stop_event: threading.Event) -> None: ...


def fetch_authorized_ws_uri(http: HttpTransport, *, allow_loopback_ws: bool = False) -> str:
    """One authorize attempt. 401/403 (raised or returned) and a missing token → FeedAuthError (non-retryable);
    unusable 200 payload → FeedProtocolError (non-retryable); other failures propagate as retryable."""
    token = read_access_token()  # UpstoxAuthError when missing → sanitized auth failure
    url = f"https://{API_HOST}{FEED_AUTHORIZE_PATH}"
    try:
        status, body, _ = http.get(url, headers=build_auth_header(token), allow_redirects=False)
    except UpstoxAuthError as exc:
        raise FeedAuthError("Feed authorization rejected.") from exc
    if status in (401, 403):
        raise FeedAuthError("Feed authorization rejected.")
    if status != 200:
        raise RuntimeError(f"Feed authorize failed with status {status}.")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise FeedProtocolError("Feed authorize returned non-JSON.") from exc
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise FeedProtocolError("Feed authorize missing data.")
    uri = data.get("authorizedRedirectUri") or data.get("authorized_redirect_uri")
    if not isinstance(uri, str):
        raise FeedProtocolError("Feed authorize missing redirect URI.")
    if uri.startswith("wss://") or (allow_loopback_ws and uri.startswith(_LOOPBACK_WS_PREFIXES)):
        return uri
    raise FeedProtocolError("Feed authorize redirect URI is not wss.")


class ReplayTransport:
    def __init__(self, frames: list[bytes], *, frame_delay_sec: float = 0.0) -> None:
        self._frames = frames
        self._delay = frame_delay_sec

    def run(self, *, on_frame: Callable[[bytes], None], stop_event: threading.Event) -> None:
        for frame in self._frames:
            if stop_event.is_set():
                return
            on_frame(frame)
            if self._delay > 0 and stop_event.wait(self._delay):
                return


class LiveWebSocketTransport:
    """Authorize over HTTPS (worker thread, outside any event loop), then stream binary frames over WebSocket.

    `allow_loopback_ws` is a test seam for loopback servers only; production builds never set it.
    """

    def __init__(self, http: HttpTransport, *, allow_loopback_ws: bool = False) -> None:
        self._http = http
        self._allow_loopback_ws = allow_loopback_ws

    def run(self, *, on_frame: Callable[[bytes], None], stop_event: threading.Event) -> None:
        if stop_event.is_set():
            return
        uri = fetch_authorized_ws_uri(self._http, allow_loopback_ws=self._allow_loopback_ws)
        if stop_event.is_set():
            return
        sub = build_subscribe_frame(instrument_keys=[INSTRUMENT_KEY], mode=SUBSCRIBE_MODE)

        async def _loop() -> None:
            from websockets.asyncio.client import connect

            async with connect(
                uri,
                open_timeout=WS_OPEN_TIMEOUT_SEC,
                close_timeout=WS_CLOSE_TIMEOUT_SEC,
                ping_interval=20,
                ping_timeout=20,
                logger=_WS_LOG,
            ) as ws:
                await ws.send(sub)  # bytes → binary frame, as Feed V3 requires
                while not stop_event.is_set():
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=WS_RECV_POLL_SEC)
                    except asyncio.TimeoutError:
                        continue
                    if isinstance(msg, bytes):
                        on_frame(msg)

        asyncio.run(_loop())


class ScriptedLiveTransport:
    """Test double: scripted frames with optional disconnect before completion."""

    def __init__(
        self,
        frames: list[bytes],
        *,
        fail_auth: bool = False,
        disconnect_after: int | None = None,
        delay_sec: float = 0.0,
    ) -> None:
        self._frames = frames
        self._fail_auth = fail_auth
        self._disconnect_after = disconnect_after
        self._delay = delay_sec

    def run(self, *, on_frame: Callable[[bytes], None], stop_event: threading.Event) -> None:
        if self._fail_auth:
            raise FeedAuthError("Injected auth failure.")
        for idx, frame in enumerate(self._frames):
            if stop_event.is_set():
                return
            on_frame(frame)
            if self._disconnect_after is not None and idx + 1 >= self._disconnect_after:
                raise ConnectionError("Injected disconnect.")
            if self._delay > 0 and stop_event.wait(self._delay):
                return
