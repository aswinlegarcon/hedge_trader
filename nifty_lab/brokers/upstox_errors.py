"""Sanitized Upstox client errors — no secrets or raw HTTP bodies."""
from __future__ import annotations


class UpstoxError(Exception):
    code: str = "UPSTOX_ERROR"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code:
            self.code = code


class UpstoxAuthError(UpstoxError):
    code = "AUTH_REQUIRED"


class UpstoxRateLimitError(UpstoxError):
    code = "RATE_LIMITED"


class UpstoxUnavailableError(UpstoxError):
    code = "UNAVAILABLE"


class UpstoxInstrumentError(UpstoxError):
    code = "INVALID_INSTRUMENT"


class UpstoxDataError(UpstoxError):
    code = "MALFORMED_DATA"


class UpstoxEmptyError(UpstoxError):
    code = "NO_CANDLES"
