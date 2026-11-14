"""Spec 11 — Upstox broker overlay acceptance (mocked HTTP)."""
from __future__ import annotations

import json
import sqlite3
import socket
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from nifty_lab.config import PROJECT_ROOT
from nifty_lab.paper_account.accounting import load_paper_account_view
from nifty_lab.paper_account.broker_overlay import (
    FRESHNESS_SECONDS,
    BrokerOverlayCache,
    CachedQuoteRow,
    account_fingerprint,
    build_quotes_url,
    materialize_overlay,
    parse_quotes_response,
    refresh_broker_overlay,
)
from tests.test_spec10_paper_account import _build_oracle_db, _tamper


class MockTransport:
    def __init__(self, routes: dict[str, tuple[int, bytes, dict]] | None = None) -> None:
        self.routes = routes or {}
        self.calls: list[str] = []

    def get(self, url: str, *, headers: dict[str, str] | None = None, allow_redirects: bool = False):
        self.calls.append(url)
        assert "Bearer " in (headers or {}).get("Authorization", "")
        for prefix, response in self.routes.items():
            if prefix in url:
                return response
        return 404, b"{}", {}


def _quote_payload(
    rows: dict[str, float],
    *,
    trade_offset_sec: float = 1.0,
    retrieved_at: datetime | None = None,
) -> bytes:
    now = retrieved_at or datetime.now(timezone.utc)
    trade = (now - timedelta(seconds=trade_offset_sec)).isoformat()
    data = {}
    for token, price in rows.items():
        data[f"label-{token}"] = {
            "instrument_token": token,
            "last_price": price,
            "timestamp": now.isoformat(),
            "last_trade_time": trade,
        }
    return json.dumps({"status": "success", "data": data}).encode()


@pytest.fixture(autouse=True)
def block_socket(monkeypatch):
    class Guarded(socket.socket):
        def connect(self, *a, **k):
            raise OSError("network blocked")

    monkeypatch.setattr(socket, "socket", Guarded)


@pytest.fixture(autouse=True)
def token_env(monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "unittest-access-token")


def _oracle_with_nse_key(tmp_path: Path, mark: float = 100.0) -> Path:
    db = tmp_path / "paper.db"
    _build_oracle_db(db, mark=mark)
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE positions SET instrument_key=? WHERE instrument_key=?",
        ("NSE_EQ|ORC", "ORC"),
    )
    conn.execute(
        "UPDATE orders SET instrument_key=?, symbol=?, underlying=? WHERE instrument_key=?",
        ("NSE_EQ|ORC", "ORC", "ORC", "ORC"),
    )
    conn.commit()
    conn.close()
    return db


def test_official_comma_batched_url():
    from nifty_lab.brokers.upstox_errors import UpstoxDataError

    keys = [f"NSE_EQ|K{i}" for i in range(10)]
    url = build_quotes_url(keys)
    assert url.count("instrument_key=") == 1
    assert "NSE_EQ%7CK0,NSE_EQ%7CK1" in url
    with pytest.raises(UpstoxDataError):
        build_quotes_url(keys + ["NSE_EQ|EXTRA"])


def test_parse_rejects_unsuccessful_status():
    body = json.dumps({"status": "error", "data": {}}).encode()
    _, err = parse_quotes_response(body, requested_keys=["T1"], retrieved_at=datetime.now(timezone.utc))
    assert err == "RESPONSE_NOT_SUCCESS"


def test_parse_rejects_close_without_last_price():
    body = json.dumps(
        {
            "status": "success",
            "data": {
                "x": {
                    "instrument_token": "NSE_EQ|X",
                    "close": 99.0,
                    "timestamp": "2026-01-01T10:00:00+00:00",
                    "last_trade_time": "2026-01-01T10:00:00+00:00",
                }
            },
        }
    ).encode()
    _, err = parse_quotes_response(body, requested_keys=["NSE_EQ|X"], retrieved_at=datetime.now(timezone.utc))
    assert err == "INVALID_LAST_PRICE"


def test_parse_rejects_unexpected_token():
    body = json.dumps(
        {
            "status": "success",
            "data": {
                "x": {
                    "instrument_token": "NSE_EQ|OTHER",
                    "last_price": 1,
                    "timestamp": "2026-01-01T10:00:00+00:00",
                    "last_trade_time": "2026-01-01T09:59:59+00:00",
                }
            },
        }
    ).encode()
    _, err = parse_quotes_response(body, requested_keys=["NSE_EQ|WANT"], retrieved_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc))
    assert err == "UNEXPECTED_INSTRUMENT_TOKEN"


def test_parse_canonical_v2_official_field_shapes():
    retrieved = datetime(2020, 12, 28, 10, 5, 59, tzinfo=timezone.utc)
    trade_ms = str(int(datetime(2020, 12, 28, 10, 0, 59, tzinfo=timezone.utc).timestamp() * 1000))
    body = json.dumps(
        {
            "status": "success",
            "data": {
                "NSE_EQ|INE": {
                    "instrument_token": "NSE_EQ|INE",
                    "last_price": 1073.25,
                    "timestamp": "2020-12-28 15:35:49+05:30",
                    "last_trade_time": trade_ms,
                }
            },
        }
    ).encode()
    rows, err = parse_quotes_response(body, requested_keys=["NSE_EQ|INE"], retrieved_at=retrieved)
    assert err is None
    assert rows["NSE_EQ|INE"].last_price == Decimal("1073.25")


def test_parse_timestamp_epoch_ms_on_timestamp_field():
    now = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    ms = int((now - timedelta(seconds=2)).timestamp() * 1000)
    trade_ms = int((now - timedelta(seconds=3)).timestamp() * 1000)
    body = json.dumps(
        {
            "status": "success",
            "data": {
                "x": {
                    "instrument_token": "NSE_EQ|X",
                    "last_price": 100.5,
                    "timestamp": ms,
                    "last_trade_time": str(trade_ms),
                }
            },
        }
    ).encode()
    rows, err = parse_quotes_response(body, requested_keys=["NSE_EQ|X"], retrieved_at=now)
    assert err is None
    assert "NSE_EQ|X" in rows


def test_parse_rejects_seconds_epoch_and_naive_iso():
    now = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    body_s = json.dumps(
        {
            "status": "success",
            "data": {
                "x": {
                    "instrument_token": "NSE_EQ|X",
                    "last_price": 1,
                    "timestamp": 1_609_000_000,
                    "last_trade_time": "2026-01-01T09:59:00+00:00",
                }
            },
        }
    ).encode()
    _, err = parse_quotes_response(body_s, requested_keys=["NSE_EQ|X"], retrieved_at=now)
    assert err == "PROVIDER_TIMESTAMP_INVALID"
    body_n = json.dumps(
        {
            "status": "success",
            "data": {
                "x": {
                    "instrument_token": "NSE_EQ|X",
                    "last_price": 1,
                    "timestamp": "2026-01-01T10:00:00",
                    "last_trade_time": "2026-01-01T09:59:00+00:00",
                }
            },
        }
    ).encode()
    _, err = parse_quotes_response(body_n, requested_keys=["NSE_EQ|X"], retrieved_at=now)
    assert err == "PROVIDER_TIMESTAMP_INVALID"


def test_parse_future_provider_with_valid_trade_rejected():
    now = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    body = json.dumps(
        {
            "status": "success",
            "data": {
                "x": {
                    "instrument_token": "NSE_EQ|X",
                    "last_price": 10,
                    "timestamp": "2026-01-01T12:00:00+00:00",
                    "last_trade_time": "2026-01-01T09:59:50+00:00",
                }
            },
        }
    ).encode()
    _, err = parse_quotes_response(body, requested_keys=["NSE_EQ|X"], retrieved_at=now)
    assert err == "FUTURE_PROVIDER_TIMESTAMP"


def test_parse_missing_trade_time_rejected():
    body = json.dumps(
        {
            "status": "success",
            "data": {
                "x": {
                    "instrument_token": "NSE_EQ|X",
                    "last_price": 10,
                    "timestamp": "2026-01-01T10:00:00+00:00",
                }
            },
        }
    ).encode()
    _, err = parse_quotes_response(
        body, requested_keys=["NSE_EQ|X"], retrieved_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    )
    assert err == "TRADE_TIMESTAMP_MISSING"


def test_materialize_stale_after_clock_advances_without_http(tmp_path):
    db = _oracle_with_nse_key(tmp_path)
    view = load_paper_account_view(db)
    fetched = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    trade = fetched - timedelta(seconds=2)
    cache = BrokerOverlayCache(
        fingerprint=account_fingerprint(view),
        retrieved_at_utc=fetched,
        quotes={
            "NSE_EQ|ORC": CachedQuoteRow(
                instrument_key="NSE_EQ|ORC",
                instrument_token="NSE_EQ|ORC",
                last_price=Decimal("105"),
                provider_ts_utc=fetched,
                trade_ts_utc=trade,
                raw_provider=fetched.isoformat(),
                raw_trade=trade.isoformat(),
            )
        },
    )
    fresh = materialize_overlay(view, cache, now=fetched + timedelta(seconds=1))
    assert fresh.positions[0].freshness == "FRESH"
    assert fresh.portfolio_value_inr == "20067.00"
    stale = materialize_overlay(view, cache, now=fetched + timedelta(seconds=FRESHNESS_SECONDS + 1))
    assert stale.positions[0].freshness == "STALE"
    assert stale.portfolio_value_inr is None


def test_numeric_oracle_uses_cost_basis_not_rounded_avg():
    from nifty_lab.paper_account.accounting import PaperAccountView, PositionView

    pos = PositionView(
        instrument_key="NSE_EQ|X",
        symbol="X",
        quantity=3,
        avg_price_inr="100.33",
        mark_price_inr=None,
        mark_time=None,
        mark_provenance="",
        mark_age_note=None,
        entry_fees_inr="0.50",
        cost_basis_inr="301.00",
        position_market_value_inr=None,
        gross_unrealized_inr=None,
        unrealized_after_paid_entry_fees_inr=None,
        reserved_sell_qty=0,
        sellable_qty=3,
    )
    view = PaperAccountView(
        status="OK",
        error=None,
        snapshot_at_utc="t",
        read_only_verified=True,
        initial_funding_inr=None,
        cash_inr="1000.00",
        reserved_cash_inr="0",
        reserved_risk_inr="0",
        cash_available_inr="1000.00",
        allocation_limit_inr="20000",
        realized_gross_inr=None,
        realized_net_inr=None,
        fees_paid_total_inr=None,
        remaining_entry_fees_inr=None,
        stored_mark_equity_inr=None,
        total_pnl_after_paid_fees_inr=None,
        gross_unrealized_total_inr=None,
        unrealized_after_fees_total_inr=None,
        portfolio_valuation_status="",
        reconciliation_status="OK",
        positions=[pos],
    )
    fetched = datetime.now(timezone.utc)
    trade = fetched - timedelta(seconds=1)
    cache = BrokerOverlayCache(
        fingerprint=account_fingerprint(view),
        retrieved_at_utc=fetched,
        quotes={
            "NSE_EQ|X": CachedQuoteRow(
                instrument_key="NSE_EQ|X",
                instrument_token="NSE_EQ|X",
                last_price=Decimal("101"),
                provider_ts_utc=fetched,
                trade_ts_utc=trade,
                raw_provider=fetched.isoformat(),
                raw_trade=trade.isoformat(),
            )
        },
    )
    bundle = materialize_overlay(view, cache, now=fetched)
    assert bundle.positions[0].gross_unrealized_inr == "2.00"


def test_fingerprint_changes_when_cash_changes(tmp_path):
    view = load_paper_account_view(_oracle_with_nse_key(tmp_path))
    assert view.status == "OK"
    fp1 = account_fingerprint(view)
    view.cash_inr = "19436.00"
    assert account_fingerprint(view) != fp1


def test_partial_coverage_at_materialize(tmp_path):
    db = _oracle_with_nse_key(tmp_path)
    view = load_paper_account_view(db)
    cache = BrokerOverlayCache(
        fingerprint=account_fingerprint(view),
        retrieved_at_utc=datetime.now(timezone.utc),
        quotes={},
    )
    bundle = materialize_overlay(view, cache, now=datetime.now(timezone.utc))
    assert bundle.positions[0].freshness == "MISSING"
    assert bundle.portfolio_value_inr is None


def test_slow_response_retrieval_after_transport_get(tmp_path, token_env):
    db = _oracle_with_nse_key(tmp_path)
    view = load_paper_account_view(db)
    clock = {"t": datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)}

    def tick():
        return clock["t"]

    class SlowTransport:
        def get(self, url, *, headers=None, allow_redirects=False):
            trade_ms = str(int((clock["t"] - timedelta(seconds=1)).timestamp() * 1000))
            provider = (clock["t"] - timedelta(seconds=1)).isoformat()
            body = json.dumps(
                {
                    "status": "success",
                    "data": {
                        "NSE_EQ|ORC": {
                            "instrument_token": "NSE_EQ|ORC",
                            "last_price": 105.0,
                            "timestamp": provider,
                            "last_trade_time": trade_ms,
                        }
                    },
                }
            ).encode()
            clock["t"] = clock["t"] + timedelta(seconds=3)
            return 200, body, {}

    result = refresh_broker_overlay(view, SlowTransport(), clock=tick)
    assert result.ok
    assert result.cache is not None
    assert result.cache.retrieved_at_utc == clock["t"]


def test_over_ten_unique_keys_no_http(tmp_path, token_env):
    from nifty_lab.paper_account.accounting import PaperAccountView, PositionView

    positions = [
        PositionView(
            instrument_key=f"NSE_EQ|K{i}",
            symbol=f"K{i}",
            quantity=1,
            avg_price_inr="1",
            mark_price_inr=None,
            mark_time=None,
            mark_provenance="",
            mark_age_note=None,
            entry_fees_inr="0",
            cost_basis_inr="1",
            position_market_value_inr=None,
            gross_unrealized_inr=None,
            unrealized_after_paid_entry_fees_inr=None,
            reserved_sell_qty=0,
            sellable_qty=1,
        )
        for i in range(11)
    ]
    view = PaperAccountView(
        status="OK",
        error=None,
        snapshot_at_utc="t",
        read_only_verified=True,
        initial_funding_inr="1",
        cash_inr="1",
        reserved_cash_inr="0",
        reserved_risk_inr="0",
        cash_available_inr="1",
        allocation_limit_inr="20000",
        realized_gross_inr=None,
        realized_net_inr=None,
        fees_paid_total_inr=None,
        remaining_entry_fees_inr=None,
        stored_mark_equity_inr=None,
        total_pnl_after_paid_fees_inr=None,
        gross_unrealized_total_inr=None,
        unrealized_after_fees_total_inr=None,
        portfolio_valuation_status="",
        reconciliation_status="OK",
        positions=positions,
    )
    transport = MockTransport({"/v2/market-quote/quotes": (200, b"{}", {})})
    result = refresh_broker_overlay(view, transport)
    assert not result.ok
    assert result.error == "BATCH_LIMIT"
    assert transport.calls == []


def test_refresh_one_get_no_retry(tmp_path):
    db = _oracle_with_nse_key(tmp_path)
    view = load_paper_account_view(db)
    transport = MockTransport({"/v2/market-quote/quotes": (200, _quote_payload({"NSE_EQ|ORC": 105.0}), {})})
    result = refresh_broker_overlay(view, transport)
    assert result.ok
    assert len(transport.calls) == 1
    assert "instrument_key=" in transport.calls[0]


def test_refresh_failure_does_not_return_cache(tmp_path):
    db = _oracle_with_nse_key(tmp_path)
    view = load_paper_account_view(db)
    transport = MockTransport({"/v2/market-quote/quotes": (401, b"{}", {})})
    result = refresh_broker_overlay(view, transport)
    assert not result.ok
    assert result.cache is None
    assert result.error == "AUTH_REQUIRED"


def test_no_fetch_when_reconciliation_failed(tmp_path):
    db = _oracle_with_nse_key(tmp_path)
    _tamper(db, "UPDATE fills SET qty=1 WHERE fill_event_id=?", ("buy-1-fill",))
    view = load_paper_account_view(db)
    transport = MockTransport()
    result = refresh_broker_overlay(view, transport)
    assert not result.ok
    assert transport.calls == []


def test_page_load_zero_http_apptest(tmp_path, monkeypatch):
    pytest.importorskip("streamlit.testing.v1", exc_type=ImportError)
    from streamlit.testing.v1 import AppTest

    db = _oracle_with_nse_key(tmp_path)
    monkeypatch.setattr("nifty_lab.paper_account.ui.paper_db_path", lambda: db)
    calls: list[str] = []

    class FailTransport:
        def get(self, url, *, headers=None, allow_redirects=False):
            calls.append(url)
            return 500, b"", {}

    monkeypatch.setattr("nifty_lab.paper_account.ui.RequestsTransport", lambda: FailTransport())
    at = AppTest.from_file(str(PROJECT_ROOT / "pages" / "13_Paper_Account.py"))
    at.run(timeout=60)
    assert not at.exception
    assert calls == []


def test_apptest_one_click_one_get_then_rerun(tmp_path, monkeypatch):
    pytest.importorskip("streamlit.testing.v1", exc_type=ImportError)
    from streamlit.testing.v1 import AppTest

    db = _oracle_with_nse_key(tmp_path)
    monkeypatch.setattr("nifty_lab.paper_account.ui.paper_db_path", lambda: db)
    transport = MockTransport({"/v2/market-quote/quotes": (200, _quote_payload({"NSE_EQ|ORC": 105.0}), {})})
    monkeypatch.setattr("nifty_lab.paper_account.ui.RequestsTransport", lambda: transport)
    at = AppTest.from_file(str(PROJECT_ROOT / "pages" / "13_Paper_Account.py"))
    at.run(timeout=60)
    for btn in at.button:
        if "broker" in (btn.label or "").lower():
            btn.click().run(timeout=60)
            break
    assert len(transport.calls) == 1
    at.run(timeout=60)
    assert len(transport.calls) == 1


def test_apptest_failed_refresh_clears_overlay(tmp_path, monkeypatch):
    pytest.importorskip("streamlit.testing.v1", exc_type=ImportError)
    from streamlit.testing.v1 import AppTest

    db = _oracle_with_nse_key(tmp_path)
    monkeypatch.setattr("nifty_lab.paper_account.ui.paper_db_path", lambda: db)
    ok = MockTransport({"/v2/market-quote/quotes": (200, _quote_payload({"NSE_EQ|ORC": 105.0}), {})})
    bad = MockTransport({"/v2/market-quote/quotes": (503, b"{}", {})})
    state = {"t": ok}

    monkeypatch.setattr("nifty_lab.paper_account.ui.RequestsTransport", lambda: state["t"])
    at = AppTest.from_file(str(PROJECT_ROOT / "pages" / "13_Paper_Account.py"))
    at.run(timeout=60)
    for i, btn in enumerate(at.button):
        if "broker" in (btn.label or "").lower():
            btn.click().run(timeout=60)
            break
    state["t"] = bad
    for btn in at.button:
        if "broker" in (btn.label or "").lower():
            btn.click().run(timeout=60)
            break
    assert any("refresh failed" in (e.value or "").lower() for e in at.error) or any(
        "UNAVAILABLE" in (e.value or "") for e in at.error
    )


def test_real_db_bytes_unchanged(tmp_path):
    db = _oracle_with_nse_key(tmp_path)
    before = db.read_bytes()
    transport = MockTransport({"/v2/market-quote/quotes": (200, _quote_payload({"NSE_EQ|ORC": 101.0}), {})})
    refresh_broker_overlay(load_paper_account_view(db), transport)
    assert db.read_bytes() == before
