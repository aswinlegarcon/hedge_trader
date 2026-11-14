"""Spec 06 — Upstox watchlist news (mocked HTTP)."""
from __future__ import annotations

import json
import socket
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from nifty_lab.brokers.upstox_errors import UpstoxAuthError, UpstoxDataError
from nifty_lab.config import FAKE_SECRET_SENTINEL
from nifty_lab.news.snapshot import (
    NEWS_CATEGORY_INSTRUMENT_KEYS,
    STALE_SNAPSHOT_MINUTES,
    NewsSnapshot,
    normalize_news_response,
)
from nifty_lab.news.upstox_news import (
    FORBIDDEN_NEWS_CATEGORIES,
    UpstoxNewsClient,
    refresh_watchlist_news,
)


@pytest.fixture(autouse=True)
def block_net(monkeypatch):
    class G(socket.socket):
        def connect(self, *a, **k):
            raise OSError("blocked")

    monkeypatch.setattr(socket, "socket", G)


class MockTransport:
    def __init__(self, status: int = 200, body: bytes = b"{}", *, fail_auth: bool = False):
        self.status = status
        self.body = body
        self.urls: list[str] = []
        self.fail_auth = fail_auth

    def get(self, url, *, headers=None, allow_redirects=False):
        self.urls.append(url)
        if self.fail_auth:
            return 401, b"{}", {}
        return self.status, self.body, {}


def _article(key: str, ms: int, url: str = "https://example.com/a") -> dict:
    return {
        "heading": "Headline",
        "description": "Provider summary text",
        "link": url,
        "date": str(ms),
        "instrument_keys": [key],
    }


def test_category_fixed_instrument_keys_only(monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "fake-token-for-tests")
    body = json.dumps({"status": "success", "data": {"news_list": []}}).encode()
    tr = MockTransport(body=body)
    client = UpstoxNewsClient(tr)
    client.fetch_page(["K1"])
    qs = parse_qs(urlparse(tr.urls[0]).query)
    assert qs["category"] == [NEWS_CATEGORY_INSTRUMENT_KEYS]
    assert qs["instrument_keys"] == ["K1"]
    assert "holdings" not in tr.urls[0]


def test_forbidden_categories_not_used_in_client():
    assert "holdings" in FORBIDDEN_NEWS_CATEGORIES
    assert NEWS_CATEGORY_INSTRUMENT_KEYS not in FORBIDDEN_NEWS_CATEGORIES


def test_one_request_per_refresh(monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "fake-token-for-tests")
    body = json.dumps({"status": "success", "data": {"news_list": []}}).encode()
    client = UpstoxNewsClient(MockTransport(body=body))
    client.fetch_page(["K1"])
    with pytest.raises(UpstoxDataError):
        client.fetch_page(["K1"])


def test_empty_news_list_per_key_no_recent():
    raw = json.dumps({"status": "success", "data": {"news_list": []}}).encode()
    arts, states, *_ = normalize_news_response(raw, ["A", "B"])
    assert arts == []
    assert states == {"A": "NO RECENT ARTICLES", "B": "NO RECENT ARTICLES"}


def test_empty_data_coverage_unknown():
    raw = json.dumps({"status": "success", "data": {}}).encode()
    arts, states, *_ = normalize_news_response(raw, ["A"])
    assert arts == []
    assert states["A"] == "COVERAGE UNKNOWN"


def test_ms_timestamp_and_sort():
    now = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
    ms_old = int((now - timedelta(days=1)).timestamp() * 1000)
    ms_new = int((now - timedelta(hours=1)).timestamp() * 1000)
    raw = json.dumps(
        {
            "status": "success",
            "data": {
                "news_list": [
                    _article("K", ms_old, "https://example.com/old"),
                    _article("K", ms_new, "https://example.com/new"),
                ]
            },
        }
    ).encode()
    arts, states, *_ = normalize_news_response(raw, ["K"], now=now)
    assert len(arts) == 2
    assert arts[0].url.endswith("/new")
    assert states["K"] == "OK"


def test_unsafe_url_quarantined():
    now = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
    ms = int(now.timestamp() * 1000)
    raw = json.dumps(
        {"status": "success", "data": {"news_list": [_article("K", ms, "javascript:alert(1)")]}}
    ).encode()
    arts, _, q, *_ = normalize_news_response(raw, ["K"], now=now)
    assert arts == []
    assert q >= 1


def test_old_article_excluded_count():
    now = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
    ms = int((now - timedelta(days=10)).timestamp() * 1000)
    raw = json.dumps({"status": "success", "data": {"news_list": [_article("K", ms)]}}).encode()
    arts, _, _, old, *_ = normalize_news_response(raw, ["K"], now=now)
    assert not arts
    assert old == 1


def test_dedupe_same_url_time():
    now = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
    ms = int(now.timestamp() * 1000)
    item = _article("K", ms, "https://example.com/x")
    raw = json.dumps({"status": "success", "data": {"news_list": [item, item]}}).encode()
    arts, *_ = normalize_news_response(raw, ["K"], now=now)
    assert len(arts) == 1


def test_fake_secret_in_payload():
    raw = json.dumps({"status": "success", "data": {"news_list": []}, "x": FAKE_SECRET_SENTINEL}).encode()
    arts, states, *_ = normalize_news_response(raw, ["K"])
    assert states["K"] == "ERROR"


def test_auth_failure_marks_no_success_snapshot(monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "fake-token-for-tests")
    client = UpstoxNewsClient(MockTransport(fail_auth=True))
    snap = refresh_watchlist_news(client, ["KEY1"])
    assert snap.refresh_failed
    assert snap.articles == []


def test_stale_snapshot_flag():
    snap = NewsSnapshot(
        requested_keys=("K",),
        retrieved_at=datetime.now(timezone.utc) - timedelta(minutes=STALE_SNAPSHOT_MINUTES + 1),
        selection_id="K",
        page_number=1,
        page_size=25,
        has_more_pages=False,
        per_key_state={"K": "OK"},
    )
    assert snap.is_stale()


def test_refresh_failure_message_sanitized(monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "fake-token-for-tests")
    client = UpstoxNewsClient(MockTransport(status=500, body=b"err"))
    snap = refresh_watchlist_news(client, ["KEY1"])
    assert snap.refresh_failed
    assert FAKE_SECRET_SENTINEL not in snap.failure_message
