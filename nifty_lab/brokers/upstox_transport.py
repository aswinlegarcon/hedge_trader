"""GET-only Upstox HTTP transport with host allowlist (Spec 04)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlparse

import requests

from .upstox_errors import UpstoxAuthError, UpstoxDataError, UpstoxRateLimitError, UpstoxUnavailableError

API_HOST = "api.upstox.com"
ASSETS_HOST = "assets.upstox.com"
ALLOWED_HOSTS = frozenset({API_HOST, ASSETS_HOST})

CONNECT_TIMEOUT = 3.0
READ_TIMEOUT = 10.0
MIN_INTERVAL_SEC = 1.0
MAX_RETRY_WAIT_SEC = 3.0


class HttpTransport(Protocol):
    def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        allow_redirects: bool = False,
    ) -> tuple[int, bytes, dict[str, str]]: ...


@dataclass
class RequestsTransport:
    """Production transport using requests with TLS verification."""

    session: requests.Session = field(default_factory=requests.Session)
    _last_request_at: float = 0.0

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        allow_redirects: bool = False,
    ) -> tuple[int, bytes, dict[str, str]]:
        host = urlparse(url).hostname
        if host not in ALLOWED_HOSTS:
            raise UpstoxDataError(f"Blocked request host: {host or 'unknown'}", code="INVALID_HOST")
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < MIN_INTERVAL_SEC:
            time.sleep(MIN_INTERVAL_SEC - elapsed)
        hdrs = dict(headers or {})
        try:
            resp = self.session.get(
                url,
                headers=hdrs,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                allow_redirects=allow_redirects,
            )
        except requests.Timeout as exc:
            raise UpstoxUnavailableError("Request timed out. Try again shortly.") from exc
        except requests.RequestException as exc:
            raise UpstoxUnavailableError("Network error. Check connectivity and retry.") from exc
        self._last_request_at = time.monotonic()
        _note_auth_outcome(hdrs.get("Authorization"), resp.status_code)
        if resp.status_code in (401, 403):
            raise UpstoxAuthError("Authentication failed (token rejected). Reconnect Upstox in Settings & API Connections.")
        if resp.status_code == 429:
            raise UpstoxRateLimitError("Rate limited. Wait and use manual refresh.")
        if resp.status_code >= 500:
            raise UpstoxUnavailableError(f"Upstox server error ({resp.status_code}). Retry later.")
        if resp.status_code >= 400:
            raise UpstoxDataError(f"Request rejected ({resp.status_code}). Check instrument and date range.")
        return resp.status_code, resp.content, {k.lower(): v for k, v in resp.headers.items()}


def _note_auth_outcome(authorization: str | None, status_code: int) -> None:
    """Spec 16: mark the presented token rejected (401/403) or verified (2xx) by fingerprint; never stores values."""
    try:
        from .upstox_auth import note_response

        note_response(authorization, status_code)
    except Exception:  # noqa: BLE001 — marks are best-effort; never break a data call
        pass


def build_auth_header(token: str) -> dict[str, str]:
    if not token or not token.strip():
        raise UpstoxAuthError("Missing access token. Set UPSTOX_ACCESS_TOKEN in .env locally.")
    return {"Authorization": f"Bearer {token.strip()}", "Accept": "application/json"}
