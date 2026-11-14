"""Sanitized stream error codes (no secrets in UI/logs)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from nifty_lab.brokers.upstox_errors import UpstoxAuthError

_SECRET_MARKERS = ("wss://", "Bearer ", "authorizedRedirect", "UPSTOX_ACCESS_TOKEN")


class FeedAuthError(Exception):
    """Typed authorize failure (HTTP 401/403 or missing token). Non-retryable. No URL in message."""


class FeedProtocolError(Exception):
    """Authorize answered 200 but the payload/URI is unusable. Non-retryable. No URL in message."""


class StreamErrorCode(str, Enum):
    FEED_AUTH_FAILED = "FEED_AUTH_FAILED"
    FEED_AUTHORIZE_INVALID = "FEED_AUTHORIZE_INVALID"
    BOOTSTRAP_FAILED = "BOOTSTRAP_FAILED"
    MAX_RECONNECT = "MAX_RECONNECT"
    OWNER_CONFLICT = "OWNER_CONFLICT"
    TRANSPORT_FAILED = "TRANSPORT_FAILED"
    OWNER_EXPIRED = "OWNER_EXPIRED"
    STOPPED = "STOPPED"


@dataclass(frozen=True)
class StreamFault:
    code: StreamErrorCode
    message: str


def sanitize_exception(exc: BaseException) -> StreamFault:
    if isinstance(exc, FeedAuthError):
        return StreamFault(StreamErrorCode.FEED_AUTH_FAILED, "Feed authorization failed. Check local token.")
    if isinstance(exc, UpstoxAuthError):
        return StreamFault(StreamErrorCode.FEED_AUTH_FAILED, "Authentication failed. Check local token.")
    if isinstance(exc, FeedProtocolError):
        return StreamFault(StreamErrorCode.FEED_AUTHORIZE_INVALID, "Feed authorize response invalid.")
    text = str(exc)
    if any(marker in text for marker in _SECRET_MARKERS):
        return StreamFault(StreamErrorCode.TRANSPORT_FAILED, "Transport error. See logs locally.")
    lowered = text.lower()
    if "bootstrap" in lowered:
        return StreamFault(StreamErrorCode.BOOTSTRAP_FAILED, "Intraday bootstrap failed.")
    if "authorize" in lowered:
        return StreamFault(StreamErrorCode.FEED_AUTHORIZE_INVALID, "Feed authorize response invalid.")
    return StreamFault(StreamErrorCode.TRANSPORT_FAILED, "Stream transport error.")