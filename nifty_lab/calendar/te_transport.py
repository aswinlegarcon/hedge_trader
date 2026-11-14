"""Credential-free GET transport for Trading Economics only (Spec 07)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlparse

import requests

TE_HOST = "tradingeconomics.com"
PUBLIC_CALENDAR_URL = f"https://{TE_HOST}/calendar?partial=calendar"
CONNECT_TIMEOUT = 3.0
READ_TIMEOUT = 15.0
MIN_INTERVAL_SEC = 1.0


class TETransport(Protocol):
    def get(self, url: str) -> tuple[int, bytes, dict[str, str]]: ...


@dataclass
class TEHttpTransport:
    """Isolated from Upstox — no bearer token path."""

    session: requests.Session = field(default_factory=requests.Session)
    _last_request_at: float = 0.0
    _calls: int = 0

    def reset_call_budget(self) -> None:
        self._calls = 0

    def get(self, url: str) -> tuple[int, bytes, dict[str, str]]:
        host = urlparse(url).hostname
        if host != TE_HOST:
            raise ValueError(f"Blocked host for TE transport: {host}")
        if self._calls >= 1:
            raise RuntimeError("One GET per explicit public refresh.")
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < MIN_INTERVAL_SEC:
            time.sleep(MIN_INTERVAL_SEC - elapsed)
        headers = {"Accept": "text/html"}
        resp = self.session.get(
            url,
            headers=headers,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            allow_redirects=False,
        )
        self._calls += 1
        self._last_request_at = time.monotonic()
        return resp.status_code, resp.content or b"", {k.lower(): v for k, v in resp.headers.items()}
