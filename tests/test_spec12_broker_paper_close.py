"""Spec 12 — broker-priced Paper close (mocked HTTP, temp ledgers)."""
from __future__ import annotations

import json
import math
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nifty_lab.brokers.upstox_errors import UpstoxDataError
from nifty_lab.config import PROJECT_ROOT
from nifty_lab.execution.broker_close_quote import fetch_broker_close_quote, parse_close_quote_payload
from nifty_lab.execution.modes import ExecutionMode
from nifty_lab.execution.paper_close import new_close_intent_id, quote_observation_id, submit_paper_close
from nifty_lab.execution.preview import build_close_preview, confirm_close_preview
from nifty_lab.execution.types import InstrumentKind, OrderSide, ProductType, QuoteSnapshot, TradeCandidate
from nifty_lab.execution.ledger.store import ExecutionLedger
from tests.test_spec08_paper_close import _buy_fill_oracle, _sell_candidate


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


def _row(
    *,
    token: str,
    bid: float = 109.5,
    bid_q: int = 50,
    ask: float = 110.0,
    ask_q: int = 40,
    provider_at: datetime,
    trade_at: datetime,
    omit_provider: bool = False,
    omit_trade: bool = False,
    depth_buy: list | None = None,
    depth_sell: list | None = None,
) -> dict:
    buy = depth_buy if depth_buy is not None else [{"price": bid, "quantity": bid_q, "orders": 1}]
    sell = depth_sell if depth_sell is not None else [{"price": ask, "quantity": ask_q, "orders": 1}]
    row: dict = {
        "instrument_token": token,
        "depth": {"buy": buy, "sell": sell},
        "last_price": 109.9,
    }
    if not omit_provider:
        row["timestamp"] = provider_at.isoformat()
    if not omit_trade:
        row["last_trade_time"] = trade_at.isoformat()
    return row


def _depth_body(
    instrument_key: str,
    *,
    token: str | None = None,
    retrieved_at: datetime | None = None,
    **row_kw,
) -> bytes:
    retrieved_at = retrieved_at or datetime.now(timezone.utc)
    trade_at = row_kw.pop("trade_at", None) or (retrieved_at - timedelta(seconds=1))
    provider_at = row_kw.pop("provider_at", None) or (retrieved_at - timedelta(seconds=1))
    tok = token or instrument_key
    row = _row(token=tok, provider_at=provider_at, trade_at=trade_at, **row_kw)
    return json.dumps({"status": "success", "data": {instrument_key: row}}).encode()


def _duplicate_token_payload(token: str, *, bid_a: float, bid_b: float, retrieved_at: datetime) -> bytes:
    t = retrieved_at - timedelta(seconds=1)
    data = {
        "row_a": _row(token=token, bid=bid_a, provider_at=t, trade_at=t),
        "row_b": _row(token=token, bid=bid_b, provider_at=t, trade_at=t),
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


def test_parse_valid_depth_bbo():
    key = "NSE_EQ|ORC"
    retrieved = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    trade = retrieved - timedelta(seconds=2)
    provider = retrieved - timedelta(seconds=2)
    cap = parse_close_quote_payload(
        _depth_body(key, bid=108.0, bid_q=12, ask=108.5, ask_q=8, retrieved_at=retrieved, provider_at=provider, trade_at=trade),
        instrument_key=key,
        retrieved_at=retrieved,
    )
    assert cap.quote.bid == 108.0
    assert cap.quote.evaluated_at == trade
    assert cap.provider_ts_utc == provider
    assert cap.trade_ts_utc == trade


def test_reject_missing_provider_with_valid_trade():
    retrieved = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    trade = retrieved - timedelta(seconds=1)
    row = _row(token="T", provider_at=trade, trade_at=trade, omit_provider=True)
    body = json.dumps({"status": "success", "data": {"k": row}}).encode()
    with pytest.raises(UpstoxDataError) as exc:
        parse_close_quote_payload(body, instrument_key="k", retrieved_at=retrieved, expected_instrument_token="T")
    assert "PROVIDER" in str(exc.value).upper()


def test_reject_missing_trade_with_valid_provider():
    retrieved = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    provider = retrieved - timedelta(seconds=1)
    row = _row(token="T", provider_at=provider, trade_at=provider, omit_trade=True)
    body = json.dumps({"status": "success", "data": {"k": row}}).encode()
    with pytest.raises(UpstoxDataError) as exc:
        parse_close_quote_payload(body, instrument_key="k", retrieved_at=retrieved, expected_instrument_token="T")
    assert "TRADE" in str(exc.value).upper()


def test_reject_future_provider_time():
    retrieved = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    trade = retrieved - timedelta(seconds=1)
    provider = retrieved + timedelta(seconds=5)
    body = _depth_body("K", token="T", retrieved_at=retrieved, provider_at=provider, trade_at=trade)
    with pytest.raises(UpstoxDataError) as exc:
        parse_close_quote_payload(body, instrument_key="K", retrieved_at=retrieved, expected_instrument_token="T")
    assert "FUTURE" in str(exc.value).upper()


def test_fresh_trade_stale_provider_rejected():
    retrieved = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    trade = retrieved - timedelta(seconds=2)
    provider = retrieved - timedelta(seconds=30)
    body = _depth_body("K", token="T", retrieved_at=retrieved, provider_at=provider, trade_at=trade)
    with pytest.raises(UpstoxDataError) as exc:
        parse_close_quote_payload(body, instrument_key="K", retrieved_at=retrieved, expected_instrument_token="T")
    assert getattr(exc.value, "code", "") == "PROVIDER_TIMESTAMP_STALE" or "OLD" in str(exc.value).upper()


def test_duplicate_token_rows_rejected():
    retrieved = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    body = _duplicate_token_payload("TOK", bid_a=100.0, bid_b=101.0, retrieved_at=retrieved)
    with pytest.raises(UpstoxDataError) as exc:
        parse_close_quote_payload(body, instrument_key="ignored", retrieved_at=retrieved, expected_instrument_token="TOK")
    assert "DUPLICATE" in str(exc.value).upper()
    body_rev = _duplicate_token_payload("TOK", bid_a=99.0, bid_b=100.0, retrieved_at=retrieved)
    with pytest.raises(UpstoxDataError):
        parse_close_quote_payload(body_rev, instrument_key="ignored", retrieved_at=retrieved, expected_instrument_token="TOK")


@pytest.mark.parametrize(
    "depth_buy",
    [
        [{"price": 100.0, "quantity": 10.5, "orders": 1}],
        [{"price": 100.0, "quantity": True, "orders": 1}],
        [{"price": 100.0, "quantity": float("nan"), "orders": 1}],
        [{"price": float("inf"), "quantity": 10, "orders": 1}],
    ],
)
def test_reject_malformed_depth_scalars(depth_buy):
    retrieved = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    t = retrieved - timedelta(seconds=1)
    body = json.dumps(
        {
            "status": "success",
            "data": {"k": _row(token="T", provider_at=t, trade_at=t, depth_buy=depth_buy)},
        }
    ).encode()
    with pytest.raises(UpstoxDataError):
        parse_close_quote_payload(body, instrument_key="k", retrieved_at=retrieved, expected_instrument_token="T")


def test_reject_token_mismatch():
    key = "NSE_EQ|ORC"
    retrieved = datetime.now(timezone.utc)
    with pytest.raises(UpstoxDataError):
        parse_close_quote_payload(
            _depth_body(key, token="OTHER", retrieved_at=retrieved),
            instrument_key=key,
            retrieved_at=retrieved,
        )


def test_fetch_one_get():
    key = "NSE_EQ|ORC"
    transport = MockTransport({"/v2/market-quote/quotes": (200, _depth_body(key), {})})
    cap = fetch_broker_close_quote(key, instrument_kind=InstrumentKind.CASH_STOCK, transport=transport)
    assert cap.quote.is_valid()
    assert len(transport.calls) == 1


def test_option_kind_fails_before_http():
    transport = MockTransport()
    with pytest.raises(ValueError):
        fetch_broker_close_quote("NSE_FO|X", instrument_kind=InstrumentKind.NIFTY_OPTION, transport=transport)
    assert transport.calls == []


def _fresh_cap(key: str = "ORC", *, bid: float = 110.0, bid_q: int = 10, retrieved: datetime | None = None):
    retrieved = retrieved or datetime.now(timezone.utc)
    t = retrieved - timedelta(seconds=1)
    return parse_close_quote_payload(
        _depth_body(key, token=key, bid=bid, bid_q=bid_q, ask=bid + 0.5, ask_q=bid_q, retrieved_at=retrieved, trade_at=t, provider_at=t),
        instrument_key=key,
        retrieved_at=retrieved,
        expected_instrument_token=key,
    )


def test_numeric_oracle_sell4(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "num.db", mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger, qty=10, price=100.0, entry_fees=2.0)
    cap = _fresh_cap(bid=110.0, bid_q=10)
    sell = _sell_candidate(4, 110.0, 110.0, 10)
    sell = TradeCandidate(**{**sell.__dict__, "quote": cap.quote})
    submit_paper_close(
        ledger,
        sell,
        intent_id=new_close_intent_id(),
        observation_id=quote_observation_id(cap.quote),
        exit_fees_inr=1.0,
    )
    with ledger._conn() as conn:
        row = conn.execute("SELECT gross_inr, net_inr FROM realized_events").fetchone()
    assert float(row[0]) == pytest.approx(40.0)
    assert float(row[1]) == pytest.approx(38.2)
    pos = ledger.list_closeable_positions()[0]
    assert pos["quantity"] == 6
    assert pos["entry_fees_inr"] == pytest.approx(1.2)


def test_partial_depth_broker_close(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "partial.db", mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger, qty=10, price=100.0)
    cap = _fresh_cap(bid=110.0, bid_q=3)
    sell = _sell_candidate(5, 110.0, 110.0, 3)
    sell = TradeCandidate(**{**sell.__dict__, "quote": cap.quote})
    r = submit_paper_close(
        ledger,
        sell,
        intent_id=new_close_intent_id(),
        observation_id=quote_observation_id(cap.quote),
        exit_fees_inr=1.0,
    )
    assert r.filled_qty == 3
    assert ledger.list_closeable_positions()[0]["quantity"] == 7


def test_nonmarketable_limit_no_fill(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "nm.db", mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger)
    cap = _fresh_cap(bid=100.0, bid_q=10)
    sell = _sell_candidate(4, 120.0, 100.0, 10)
    sell = TradeCandidate(**{**sell.__dict__, "quote": cap.quote})
    r = submit_paper_close(
        ledger,
        sell,
        intent_id=new_close_intent_id(),
        observation_id=quote_observation_id(cap.quote),
        exit_fees_inr=1.0,
    )
    assert r.filled_qty == 0


def test_stale_broker_snapshot_rejected_at_confirm(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "stale.db", mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger)
    old = datetime.now(timezone.utc) - timedelta(seconds=120)
    quote = QuoteSnapshot(110.0, 110.5, 10, 10, "ORC", old, source="upstox_full_quote_v2")
    sell = _sell_candidate(5, 110.0, 110.0, 10)
    sell = TradeCandidate(**{**sell.__dict__, "quote": quote})
    preview = build_close_preview(sell, ledger.portfolio_context(), exit_fees_inr=1.0)
    ok, msg = confirm_close_preview(preview, ledger.portfolio_context(), exit_fees_inr=1.0, slippage_pct=0.0)
    assert not ok
    assert "TTL" in msg or "expired" in msg.lower()


def test_competing_pending_sell(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "comp.db", mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger, qty=10)
    cap = _fresh_cap()
    sell6 = _sell_candidate(6, 110.0, 110.0, 10)
    sell6 = TradeCandidate(**{**sell6.__dict__, "quote": cap.quote})
    submit_paper_close(
        ledger,
        sell6,
        intent_id=new_close_intent_id(),
        observation_id=quote_observation_id(cap.quote),
        exit_fees_inr=1.0,
    )
    sell5 = _sell_candidate(5, 110.0, 110.0, 10)
    sell5 = TradeCandidate(**{**sell5.__dict__, "quote": cap.quote})
    with pytest.raises(ValueError):
        submit_paper_close(
            ledger,
            sell5,
            intent_id=new_close_intent_id(),
            observation_id=quote_observation_id(cap.quote),
            exit_fees_inr=1.0,
        )


def _seed_paper_ledger(tmp_path: Path) -> Path:
    db = tmp_path / "paper_execution.db"
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger)
    return db


def _pick_broker_source(at) -> None:
    for r in at.radio:
        if r.label and "close quote source" in r.label.lower():
            r.set_value("Broker snapshot").run(timeout=90)
            return


def test_trade_ticket_load_zero_http(tmp_path: Path, monkeypatch):
    pytest.importorskip("streamlit.testing.v1", exc_type=ImportError)
    from streamlit.testing.v1 import AppTest

    db = _seed_paper_ledger(tmp_path)
    monkeypatch.setattr("nifty_lab.ui.trade_ticket._ledger_path", lambda _mode: db)
    calls: list[str] = []

    class FailTransport:
        def get(self, url, *, headers=None, allow_redirects=False):
            calls.append(url)
            return 500, b"", {}

    monkeypatch.setattr("nifty_lab.ui.trade_ticket.RequestsTransport", lambda: FailTransport())
    at = AppTest.from_file(str(PROJECT_ROOT / "pages" / "12_Trade_Ticket.py"))
    at.run(timeout=90)
    assert not at.exception
    assert calls == []


def test_trade_ticket_fetch_preview_confirm_flow(tmp_path: Path, monkeypatch):
    pytest.importorskip("streamlit.testing.v1", exc_type=ImportError)
    from streamlit.testing.v1 import AppTest

    db = _seed_paper_ledger(tmp_path)
    monkeypatch.setattr("nifty_lab.ui.trade_ticket._ledger_path", lambda _mode: db)
    body = _depth_body("ORC", token="ORC", bid=110.0, bid_q=10, ask=110.5, ask_q=10)
    transport = MockTransport({"/v2/market-quote/quotes": (200, body, {})})
    monkeypatch.setattr("nifty_lab.ui.trade_ticket.RequestsTransport", lambda: transport)

    at = AppTest.from_file(str(PROJECT_ROOT / "pages" / "12_Trade_Ticket.py"))
    at.run(timeout=90)
    _pick_broker_source(at)
    for btn in at.button:
        if "fetch broker close quote" in (btn.label or "").lower():
            btn.click().run(timeout=90)
            break
    assert len(transport.calls) == 1
    before = len(transport.calls)
    for btn in at.button:
        if (btn.label or "") == "Preview Paper close":
            btn.click().run(timeout=90)
            break
    assert len(transport.calls) == before
    confirm_clicked = False
    for btn in at.button:
        if (btn.label or "").startswith("Confirm Paper close"):
            btn.click().run(timeout=90)
            confirm_clicked = True
            break
    assert confirm_clicked
    assert len(transport.calls) == 1
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    assert ledger.list_closeable_positions()[0]["quantity"] == 9


def test_apptest_failed_refresh_clears_confirm(tmp_path: Path, monkeypatch):
    pytest.importorskip("streamlit.testing.v1", exc_type=ImportError)
    from streamlit.testing.v1 import AppTest

    db = _seed_paper_ledger(tmp_path)
    monkeypatch.setattr("nifty_lab.ui.trade_ticket._ledger_path", lambda _mode: db)
    good = _depth_body("ORC", token="ORC", bid=110.0, bid_q=10)
    phase = {"n": 0}

    class ToggleTransport:
        def get(self, url, *, headers=None, allow_redirects=False):
            phase["n"] += 1
            if phase["n"] == 1:
                return 200, good, {}
            return 503, b"{}", {}

    monkeypatch.setattr("nifty_lab.ui.trade_ticket.RequestsTransport", lambda: ToggleTransport())
    at = AppTest.from_file(str(PROJECT_ROOT / "pages" / "12_Trade_Ticket.py"))
    at.run(timeout=90)
    _pick_broker_source(at)
    for btn in at.button:
        if "fetch broker close quote" in (btn.label or "").lower():
            btn.click().run(timeout=90)
            break
    for btn in at.button:
        if (btn.label or "") == "Preview Paper close":
            btn.click().run(timeout=90)
            break
    had_confirm = any((b.label or "").startswith("Confirm Paper close") for b in at.button)
    for btn in at.button:
        if "fetch broker close quote" in (btn.label or "").lower():
            btn.click().run(timeout=90)
            break
    assert had_confirm
    assert not any((b.label or "").startswith("Confirm Paper close") for b in at.button)
    assert phase["n"] == 2


def test_apptest_source_switch_invalidates_preview(tmp_path: Path, monkeypatch):
    pytest.importorskip("streamlit.testing.v1", exc_type=ImportError)
    from streamlit.testing.v1 import AppTest

    db = _seed_paper_ledger(tmp_path)
    monkeypatch.setattr("nifty_lab.ui.trade_ticket._ledger_path", lambda _mode: db)
    body = _depth_body("ORC", token="ORC", bid=110.0, bid_q=10)
    transport = MockTransport({"/v2/market-quote/quotes": (200, body, {})})
    monkeypatch.setattr("nifty_lab.ui.trade_ticket.RequestsTransport", lambda: transport)
    at = AppTest.from_file(str(PROJECT_ROOT / "pages" / "12_Trade_Ticket.py"))
    at.run(timeout=90)
    _pick_broker_source(at)
    for btn in at.button:
        if "fetch broker close quote" in (btn.label or "").lower():
            btn.click().run(timeout=90)
            break
    for btn in at.button:
        if (btn.label or "") == "Preview Paper close":
            btn.click().run(timeout=90)
            break
    assert any((b.label or "").startswith("Confirm Paper close") for b in at.button)
    for r in at.radio:
        if r.label and "close quote source" in r.label.lower():
            r.set_value("Manual simulation").run(timeout=90)
            break
    assert not any((b.label or "").startswith("Confirm Paper close") for b in at.button)
