"""Typed Upstox news snapshot normalization (Spec 06)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from ..config import FAKE_SECRET_SENTINEL

NEWS_CATEGORY_INSTRUMENT_KEYS = "instrument_keys"
SUMMARY_EXCERPT_LEN = 240
SEVEN_DAY_WINDOW = timedelta(days=7)
FUTURE_TOLERANCE = timedelta(minutes=5)
STALE_SNAPSHOT_MINUTES = 15

_UNSAFE_SCHEMES = ("javascript:", "data:", "file:")


@dataclass(frozen=True)
class NewsArticle:
    heading: str
    url: str
    published_at: datetime
    summary_excerpt: str
    instrument_keys: tuple[str, ...]
    source_label: str = "Upstox News API"
    host: str = ""


@dataclass
class NewsSnapshot:
    requested_keys: tuple[str, ...]
    retrieved_at: datetime
    selection_id: str
    page_number: int
    page_size: int
    has_more_pages: bool
    per_key_state: dict[str, str]
    articles: list[NewsArticle] = field(default_factory=list)
    quarantined_count: int = 0
    excluded_old_count: int = 0
    diagnostic: str = ""
    refresh_failed: bool = False
    failure_message: str = ""

    def is_stale(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        age = now - self.retrieved_at.astimezone(timezone.utc)
        return age.total_seconds() > STALE_SNAPSHOT_MINUTES * 60


def news_selection_id(keys: list[str]) -> str:
    return "|".join(sorted(k for k in keys if k))


def _safe_url(url: str) -> str | None:
    if not url or not isinstance(url, str):
        return None
    u = url.strip()
    low = u.lower()
    if any(low.startswith(s) for s in _UNSAFE_SCHEMES):
        return None
    parsed = urlparse(u)
    if parsed.scheme != "https":
        return None
    if parsed.username or parsed.password:
        return None
    return u


def _parse_ms(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, str) and re.match(r"^[\d.]+$", value):
            ms = float(value)
        else:
            ms = float(value)
    except (TypeError, ValueError):
        return None
    if not (ms == ms):  # nan
        return None
    if ms > 1e15:
        seconds = ms / 1_000_000.0
    elif ms > 1e11:
        seconds = ms / 1000.0
    else:
        seconds = ms
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


def _excerpt(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= SUMMARY_EXCERPT_LEN:
        return text
    return text[: SUMMARY_EXCERPT_LEN - 1] + "…"


def normalize_news_response(
    raw: bytes,
    requested_keys: list[str],
    *,
    now: datetime | None = None,
    page_number: int = 1,
    page_size: int = 25,
) -> tuple[list[NewsArticle], dict[str, str], int, int, str, bool]:
    """Returns articles, per_key_state, quarantined, excluded_old, diagnostic, has_more."""
    now = now or datetime.now(timezone.utc)
    keys = [k for k in requested_keys if k]
    states = {k: "COVERAGE UNKNOWN" for k in keys}
    if not keys:
        return [], states, 0, 0, "no keys requested", False
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return [], {k: "ERROR" for k in keys}, 0, 0, "malformed JSON", False
    if FAKE_SECRET_SENTINEL in raw.decode("utf-8", errors="ignore"):
        return [], {k: "ERROR" for k in keys}, 0, 0, "invalid sentinel in payload", False
    if not isinstance(payload, dict) or payload.get("status") != "success":
        return [], {k: "ERROR" for k in keys}, 0, 0, "unsuccessful status", False
    data = payload.get("data")
    if data is None or data == {}:
        return [], states, 0, 0, "empty data object", False

    raw_items: list[dict] = []
    per_key_lists: dict[str, list] = {}
    has_more = False
    if isinstance(data, dict):
        meta = data.get("metadata") or data.get("meta") or {}
        if isinstance(meta, dict):
            has_more = bool(meta.get("has_next_page") or meta.get("has_more"))
        if "news_list" in data and isinstance(data["news_list"], list):
            if data["news_list"] == []:
                states = {k: "NO RECENT ARTICLES" for k in keys}
                return [], states, 0, 0, "", has_more
            raw_items = [x for x in data["news_list"] if isinstance(x, dict)]
        for k in keys:
            if k in data and isinstance(data[k], list):
                per_key_lists[k] = data[k]

    if per_key_lists:
        for k, lst in per_key_lists.items():
            states[k] = "NO RECENT ARTICLES" if len(lst) == 0 else "OK"

    quarantined = 0
    excluded_old = 0
    articles: list[NewsArticle] = []

    def ingest(item: dict, assoc: list[str]) -> None:
        nonlocal quarantined, excluded_old
        heading = str(item.get("heading") or item.get("title") or "").strip()
        url = _safe_url(str(item.get("link") or item.get("url") or ""))
        pub = _parse_ms(item.get("date") or item.get("created_at") or item.get("published_at"))
        if not heading or not url or pub is None:
            quarantined += 1
            return
        if pub > now + FUTURE_TOLERANCE:
            quarantined += 1
            return
        if now - pub > SEVEN_DAY_WINDOW:
            excluded_old += 1
            return
        summary = _excerpt(str(item.get("description") or item.get("summary") or ""))
        host = urlparse(url).hostname or ""
        articles.append(
            NewsArticle(
                heading=heading,
                url=url,
                published_at=pub,
                summary_excerpt=summary,
                instrument_keys=tuple(sorted(set(assoc))),
                host=host,
            )
        )

    for item in raw_items:
        assoc = item.get("instrument_keys") or item.get("instrument_key") or []
        if isinstance(assoc, str):
            assoc = [assoc]
        if not assoc:
            assoc = [k for k in keys if k in str(item)]
        ingest(item, [str(a) for a in assoc if a])

    for k, lst in per_key_lists.items():
        for item in lst:
            if isinstance(item, dict):
                ingest(item, [k])

    if not raw_items and not per_key_lists:
        return [], states, 0, 0, "unrecognized data shape", has_more

    for k in keys:
        if states[k] == "COVERAGE UNKNOWN" and any(k in a.instrument_keys for a in articles):
            states[k] = "OK" if any(k in a.instrument_keys for a in articles) else "NO RECENT ARTICLES"
        if states[k] == "COVERAGE UNKNOWN" and not articles:
            pass
        elif states[k] == "COVERAGE UNKNOWN" and not any(k in a.instrument_keys for a in articles):
            states[k] = "NO RECENT ARTICLES"

    # dedupe by url + published_at
    seen: set[tuple[str, int]] = set()
    deduped: list[NewsArticle] = []
    for a in sorted(articles, key=lambda x: x.published_at, reverse=True):
        key = (a.url, int(a.published_at.timestamp()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(a)

    return deduped, states, quarantined, excluded_old, "", has_more


def merge_snapshots(base: NewsSnapshot, page2_articles: list[NewsArticle], page_number: int) -> NewsSnapshot:
    seen = {(a.url, int(a.published_at.timestamp())) for a in base.articles}
    merged = list(base.articles)
    for a in page2_articles:
        key = (a.url, int(a.published_at.timestamp()))
        if key not in seen:
            seen.add(key)
            merged.append(a)
    merged.sort(key=lambda x: x.published_at, reverse=True)
    base.articles = merged
    base.page_number = page_number
    return base
