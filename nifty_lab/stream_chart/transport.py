"""Feed transports — REPLAY (deterministic) and LIVE (authorized WebSocket)."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections.abc import Callable
from typing import Protocol

from nifty_lab.brokers.upstox_transport import API_HOST, HttpTransport, build_auth_header
from nifty_lab.brokers.upstox_market_data import read_access_token

from .constants import FEED_AUTHORIZE_PATH, INSTRUMENT_KEY, SUBSCRIBE_MODE
from .feed_decode import build_subscribe_frame
from .stream_errors import FeedAuthError

_LOG = logging.getLogger(__name__)


class RawFeedTransport(Protocol):
    def run(self, *, on_frame: Callable[[bytes], None], stop_event: threading.Event) -> None: ...


def fetch_authorized_ws_uri(http: HttpTransport) -> str:
    token = read_access_token()
    url = f"https://{API_HOST}{FEED_AUTHORIZE_PATH}"
    status, body, _ = http.get(url, headers=build_auth_header(token), allow_redirects=False)
    if status in (401, 403):
        raise FeedAuthError("Feed authorization rejected.")
    if status != 200:
        raise FeedAuthError(f"Feed authorization failed with status {status}.")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise FeedAuthError("Feed authorize returned non-JSON.") from exc
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise FeedAuthError("Feed authorize missing data.")
    uri = data.get("authorizedRedirectUri") or data.get("authorized_redirect_uri")
    if not isinstance(uri, str) or not uri.startswith("wss://"):
        raise FeedAuthError("Feed authorize missing wss redirect URI.")
    return uri


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
    def __init__(self, http: HttpTransport) -> None:
        self._http = http

    def run(self, *, on_frame: Callable[[bytes], None], stop_event: threading.Event) -> None:
        if stop_event.is_set():
            return
        uri = fetch_authorized_ws_uri(self._http)
        sub = build_subscribe_frame(instrument_keys=[INSTRUMENT_KEY], mode=SUBSCRIBE_MODE)

        async def _loop() -> None:
            import websockets

            async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as ws:
                await ws.send(sub)
                while not stop_event.is_set():
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
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