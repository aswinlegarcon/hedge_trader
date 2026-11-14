"""Upstox GET /v2/news — instrument_keys only (Spec 06)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import urlencode

from ..brokers.upstox_errors import UpstoxAuthError, UpstoxDataError
from ..brokers.upstox_market_data import ACCESS_STATE, read_access_token
from ..brokers.upstox_transport import API_HOST, HttpTransport, build_auth_header
from .snapshot import (
    NEWS_CATEGORY_INSTRUMENT_KEYS,
    NewsSnapshot,
    merge_snapshots,
    news_selection_id,
    normalize_news_response,
)

FORBIDDEN_NEWS_CATEGORIES = frozenset({"holdings", "positions", "portfolio"})
MAX_INSTRUMENT_KEYS = 4
DEFAULT_PAGE_SIZE = 25
MAX_PAGES = 2


class NewsTransport(Protocol):
    def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        allow_redirects: bool = False,
    ) -> tuple[int, bytes, dict[str, str]]: ...


@dataclass
class UpstoxNewsClient:
    transport: HttpTransport
    _calls: int = 0

    def reset_call_budget(self) -> None:
        self._calls = 0

    def _news_url(self, keys: list[str], page_number: int, page_size: int) -> str:
        if not keys:
            raise UpstoxDataError("No instrument keys for news request.")
        if len(keys) > MAX_INSTRUMENT_KEYS:
            raise UpstoxDataError("At most four instrument keys per news request.")
        params: list[tuple[str, str]] = [("category", NEWS_CATEGORY_INSTRUMENT_KEYS)]
        for k in keys:
            params.append(("instrument_keys", k))
        params.append(("page_number", str(page_number)))
        params.append(("page_size", str(page_size)))
        return f"https://{API_HOST}/v2/news?{urlencode(params)}"

    def fetch_page(self, keys: list[str], *, page_number: int = 1, page_size: int = DEFAULT_PAGE_SIZE) -> bytes:
        if self._calls >= 1:
            raise UpstoxDataError("One news HTTP request per explicit refresh action.")
        token = read_access_token()
        url = self._news_url(keys, page_number, page_size)
        headers = build_auth_header(token)
        try:
            status, body, _ = self.transport.get(url, headers=headers, allow_redirects=False)
        except UpstoxAuthError as exc:
            ACCESS_STATE.mark_auth_failure(str(exc))
            raise
        self._calls += 1
        if status in (401, 403):
            ACCESS_STATE.mark_auth_failure("Authentication failed for news API.")
            raise UpstoxAuthError("Authentication failed for news API.")
        if status != 200:
            raise UpstoxDataError(f"News request failed with status {status}")
        return body


def refresh_watchlist_news(
    client: UpstoxNewsClient,
    instrument_keys: list[str],
    *,
    page_number: int = 1,
    existing: NewsSnapshot | None = None,
) -> NewsSnapshot:
    keys = list(dict.fromkeys(k for k in instrument_keys if k))[:MAX_INSTRUMENT_KEYS]
    if not keys:
        return NewsSnapshot(
            requested_keys=tuple(),
            retrieved_at=datetime.now(timezone.utc),
            selection_id="",
            page_number=1,
            page_size=DEFAULT_PAGE_SIZE,
            has_more_pages=False,
            per_key_state={},
            diagnostic="No resolved instrument keys — refresh watchlist or resolve symbols first.",
            refresh_failed=True,
            failure_message="No keys",
        )
    sel = news_selection_id(keys)
    if existing is not None and page_number > 1:
        if existing.selection_id != sel:
            raise UpstoxDataError("Selection changed — refresh page 1 first.")
        if page_number > MAX_PAGES:
            raise UpstoxDataError("Maximum two pages retained.")
        client.reset_call_budget()
        raw = client.fetch_page(keys, page_number=page_number)
        articles, states, q, old, diag, has_more = normalize_news_response(
            raw, keys, page_number=page_number, page_size=DEFAULT_PAGE_SIZE
        )
        snap = merge_snapshots(existing, articles, page_number)
        snap.per_key_state.update(states)
        snap.quarantined_count += q
        snap.excluded_old_count += old
        snap.has_more_pages = has_more
        snap.retrieved_at = datetime.now(timezone.utc)
        return snap

    client.reset_call_budget()
    try:
        raw = client.fetch_page(keys, page_number=page_number)
        articles, states, q, old, diag, has_more = normalize_news_response(
            raw, keys, page_number=page_number, page_size=DEFAULT_PAGE_SIZE
        )
        return NewsSnapshot(
            requested_keys=tuple(keys),
            retrieved_at=datetime.now(timezone.utc),
            selection_id=sel,
            page_number=page_number,
            page_size=DEFAULT_PAGE_SIZE,
            has_more_pages=has_more,
            per_key_state=states,
            articles=articles,
            quarantined_count=q,
            excluded_old_count=old,
            diagnostic=diag,
        )
    except Exception as exc:
        return NewsSnapshot(
            requested_keys=tuple(keys),
            retrieved_at=datetime.now(timezone.utc),
            selection_id=sel,
            page_number=page_number,
            page_size=DEFAULT_PAGE_SIZE,
            has_more_pages=False,
            per_key_state={k: "UNAVAILABLE" for k in keys},
            refresh_failed=True,
            failure_message=str(exc),
        )
