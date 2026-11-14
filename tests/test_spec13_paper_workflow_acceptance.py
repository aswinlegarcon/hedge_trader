"""Spec 13 — Paper workflow acceptance (temp DB, mocked broker, readonly reader)."""
from __future__ import annotations

import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nifty_lab.config import PROJECT_ROOT
from nifty_lab.execution.broker_close_quote import fetch_broker_close_quote
from nifty_lab.execution.fill_validation import validate_entry_admission_economics
from nifty_lab.execution.modes import ExecutionMode
from nifty_lab.execution.paper import submit_paper_entry
from nifty_lab.execution.paper_cancel import cancel_paper_remainder, list_paper_order_rows
from nifty_lab.execution.paper_close import new_close_intent_id, quote_observation_id, submit_paper_close
from nifty_lab.execution.preview import (
    build_close_preview,
    build_preview,
    confirm_close_preview,
    confirm_preview,
)
from nifty_lab.execution.types import InstrumentKind, OrderSide, ProductType, QuoteSnapshot, TradeCandidate
from nifty_lab.execution.ledger.store import ExecutionLedger
from nifty_lab.paper_account.accounting import load_paper_account_view
from nifty_lab.paper_account.paths import paper_db_path
from tests.test_spec12_broker_paper_close import _depth_body


KEY = "JRN"
REAL_PAPER_DB = PROJECT_ROOT / "data" / "paper_execution.db"


def _guard_tmp_db(path: Path) -> Path:
    resolved = path.resolve()
    assert resolved != REAL_PAPER_DB.resolve()
    assert str(resolved).find("/tmp") >= 0 or "pytest" in str(resolved)
    return path


def _buy_candidate(**kw) -> TradeCandidate:
    base = dict(
        mode=ExecutionMode.PAPER,
        kind=InstrumentKind.CASH_STOCK,
        instrument_key=KEY,
        trading_symbol=KEY,
        underlying=KEY,
        side=OrderSide.BUY,
        quantity=10,
        limit_price_inr=100.0,
        product=ProductType.DELIVERY,
        stop_reference_inr=90.0,
        entry_cost_inr=2.0,
        exit_cost_reserve_inr=0.0,
        user_ack_stop_not_placed=True,
        quote=QuoteSnapshot(99.9, 100.0, 10, 10, KEY, datetime.now(timezone.utc)),
        lot_size=1,
    )
    base.update(kw)
    return TradeCandidate(**base)


def _submit_buy_after_confirm(ledger: ExecutionLedger, cand: TradeCandidate, *, slippage_pct: float = 0.0):
    ticket = build_preview(cand, ledger.portfolio_context(), slippage_pct=slippage_pct)
    ok, msg = confirm_preview(
        ticket,
        ledger.portfolio_context(),
        slippage_pct=slippage_pct,
        entry_cost_inr=cand.entry_cost_inr,
    )
    assert ok, msg
    return submit_paper_entry(ledger, ticket.candidate, slippage_pct=slippage_pct)


def _sell_candidate(qty: int, limit: float, quote: QuoteSnapshot) -> TradeCandidate:
    return TradeCandidate(
        mode=ExecutionMode.PAPER,
        kind=InstrumentKind.CASH_STOCK,
        instrument_key=KEY,
        trading_symbol=KEY,
        underlying=KEY,
        side=OrderSide.SELL,
        quantity=qty,
        limit_price_inr=limit,
        product=ProductType.DELIVERY,
        quote=quote,
        lot_size=1,
    )


def _view_ok(db: Path):
    v = load_paper_account_view(db)
    assert v.status == "OK"
    assert v.reconciliation_status == "OK"
    return v


@pytest.fixture(autouse=True)
def block_socket(monkeypatch):
    class Guarded(socket.socket):
        def connect(self, *a, **k):
            raise OSError("network blocked")

    monkeypatch.setattr(socket, "socket", Guarded)


@pytest.fixture(autouse=True)
def token_env(monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "unittest-access-token")


@pytest.fixture(autouse=True)
def forbid_real_paper_db(monkeypatch):
    def _safe():
        raise AssertionError("Spec 13 must not use default paper_db_path()")

    monkeypatch.setattr("nifty_lab.paper_account.paths.paper_db_path", _safe)


@pytest.fixture
def clock_times(monkeypatch):
    base = datetime(2026, 6, 1, 9, 30, 0, tzinfo=timezone.utc)
    seq = [base + timedelta(seconds=i) for i in range(60)]
    idx = {"n": 0}

    def _next():
        i = idx["n"]
        idx["n"] = min(i + 1, len(seq) - 1)
        return seq[i].isoformat()

    monkeypatch.setattr("nifty_lab.execution.ledger.store._utcnow", _next)


def test_entry_fees_match_confirmed_preview(tmp_path: Path):
    db = _guard_tmp_db(tmp_path / "fee.db")
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    _submit_buy_after_confirm(ledger, _buy_candidate(), slippage_pct=0.0)
    assert ledger.cash_balance() == pytest.approx(18_998.0, abs=0.01)


def test_independent_oracle_journey(tmp_path: Path, clock_times):
    db = _guard_tmp_db(tmp_path / "journey.db")
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)

    class SeqTransport:
        def __init__(self) -> None:
            self.calls: list[str] = []
            self._i = 0
            self.fetch_at: list[datetime] = []

        def get(self, url: str, *, headers=None, allow_redirects=False):
            self.calls.append(url)
            now = datetime.now(timezone.utc)
            self.fetch_at.append(now)
            if self._i == 0:
                body = _depth_body(KEY, token=KEY, bid=110.0, bid_q=3, ask=110.5, ask_q=3, retrieved_at=now)
            else:
                body = _depth_body(KEY, token=KEY, bid=105.0, bid_q=10, ask=105.5, ask_q=10, retrieved_at=now)
            self._i += 1
            return 200, body, {}

    transport = SeqTransport()

    _submit_buy_after_confirm(ledger, _buy_candidate(), slippage_pct=0.0)
    assert ledger.cash_balance() == pytest.approx(18_998.0, abs=0.01)
    v1 = _view_ok(db)
    assert v1.cash_inr == "18998.00"

    cap1 = fetch_broker_close_quote(
        KEY,
        instrument_kind=InstrumentKind.CASH_STOCK,
        transport=transport,
        clock=lambda: transport.fetch_at[-1],
    )
    assert len(transport.calls) == 1
    sell8 = _sell_candidate(8, 110.0, cap1.quote)
    prev = build_close_preview(sell8, ledger.portfolio_context(), exit_fees_inr=0.60, slippage_pct=0.0)
    assert confirm_close_preview(prev, ledger.portfolio_context(), exit_fees_inr=0.60, slippage_pct=0.0)[0]
    r1 = submit_paper_close(
        ledger,
        sell8,
        intent_id=prev.close_intent_id or "",
        observation_id=prev.observation_id or "",
        exit_fees_inr=0.60,
    )
    assert r1.filled_qty == 3
    assert ledger.cash_balance() == pytest.approx(19_327.40, abs=0.01)
    assert ledger.list_closeable_positions()[0]["quantity"] == 7
    assert ledger.list_closeable_positions()[0]["entry_fees_inr"] == pytest.approx(1.40, abs=0.01)
    v2 = _view_ok(db)
    assert v2.realized_net_inr == "28.80"

    row = [x for x in list_paper_order_rows(ledger) if x.side == OrderSide.SELL.value][0]
    cancel_paper_remainder(ledger, row.local_id)

    cap2 = fetch_broker_close_quote(
        KEY,
        instrument_kind=InstrumentKind.CASH_STOCK,
        transport=transport,
        clock=lambda: transport.fetch_at[-1],
    )
    sell7 = _sell_candidate(7, 105.0, cap2.quote)
    prev2 = build_close_preview(sell7, ledger.portfolio_context(), exit_fees_inr=1.40, slippage_pct=0.0)
    assert confirm_close_preview(prev2, ledger.portfolio_context(), exit_fees_inr=1.40, slippage_pct=0.0)[0]
    submit_paper_close(
        ledger,
        sell7,
        intent_id=prev2.close_intent_id or "",
        observation_id=prev2.observation_id or "",
        exit_fees_inr=1.40,
    )
    assert ledger.cash_balance() == pytest.approx(20_061.0, abs=0.01)
    v4 = _view_ok(db)
    assert v4.realized_net_inr == "61.00"
    assert v4.fees_paid_total_inr == "4.00"
    assert len(transport.calls) == 2


def test_entry_slippage_marketable_and_blocked(tmp_path: Path):
    ledger = ExecutionLedger(_guard_tmp_db(tmp_path / "slip.db"), mode=ExecutionMode.PAPER)
    cand = _buy_candidate(
        limit_price_inr=100.1,
        quote=QuoteSnapshot(99.5, 100.0, 10, 10, KEY, datetime.now(timezone.utc)),
    )
    r_ok = _submit_buy_after_confirm(ledger, cand, slippage_pct=0.001)
    assert r_ok.filled_qty == 10
    ledger2 = ExecutionLedger(_guard_tmp_db(tmp_path / "slip2.db"), mode=ExecutionMode.PAPER)
    cand2 = _buy_candidate(limit_price_inr=100.0, entry_cost_inr=2.0)
    t = build_preview(cand2, ledger2.portfolio_context(), slippage_pct=0.001)
    confirm_preview(t, ledger2.portfolio_context(), slippage_pct=0.001, entry_cost_inr=2.0)
    r_no = submit_paper_entry(ledger2, t.candidate, slippage_pct=0.001)
    assert r_no.filled_qty == 0
    assert ledger2.cash_balance() == pytest.approx(20_000.0, abs=0.01)


def test_partial_entry_fee_allocation(tmp_path: Path):
    ledger = ExecutionLedger(_guard_tmp_db(tmp_path / "part.db"), mode=ExecutionMode.PAPER)
    cand = _buy_candidate(
        quantity=10,
        entry_cost_inr=10.0,
        quote=QuoteSnapshot(99.5, 100.0, 10, 3, KEY, datetime.now(timezone.utc)),
    )
    r = _submit_buy_after_confirm(ledger, cand, slippage_pct=0.0)
    assert r.filled_qty == 3
    pos = ledger.list_closeable_positions()[0]
    assert pos["entry_fees_inr"] == pytest.approx(3.0, abs=0.01)
    assert ledger.reserved_cash() > 0


def test_invalid_entry_economics_rejected(tmp_path: Path):
    with pytest.raises(ValueError):
        validate_entry_admission_economics(-1.0, 0.0)
    with pytest.raises(ValueError):
        build_preview(_buy_candidate(entry_cost_inr=-1.0), ExecutionLedger(_guard_tmp_db(tmp_path / "x.db"), mode=ExecutionMode.PAPER).portfolio_context())


def test_confirm_rejects_fee_slippage_change(tmp_path: Path):
    ledger = ExecutionLedger(_guard_tmp_db(tmp_path / "tamper.db"), mode=ExecutionMode.PAPER)
    ticket = build_preview(_buy_candidate(), ledger.portfolio_context(), slippage_pct=0.0)
    ok, msg = confirm_preview(ticket, ledger.portfolio_context(), slippage_pct=0.01, entry_cost_inr=2.0)
    assert not ok
    assert "slippage" in msg.lower()


def test_replay_and_observation_guards(tmp_path: Path):
    db = _guard_tmp_db(tmp_path / "guards.db")
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    _submit_buy_after_confirm(ledger, _buy_candidate(), slippage_pct=0.0)
    body = _depth_body(KEY, token=KEY, bid=110.0, bid_q=10, retrieved_at=datetime.now(timezone.utc))
    from nifty_lab.execution.broker_close_quote import parse_close_quote_payload

    cap = parse_close_quote_payload(body, instrument_key=KEY, retrieved_at=datetime.now(timezone.utc), expected_instrument_token=KEY)
    sell = _sell_candidate(4, 200.0, cap.quote)
    prev = build_close_preview(sell, ledger.portfolio_context(), exit_fees_inr=1.0)
    confirm_close_preview(prev, ledger.portfolio_context(), exit_fees_inr=1.0, slippage_pct=0.0)
    cash_before = ledger.cash_balance()
    assert submit_paper_close(ledger, sell, intent_id=prev.close_intent_id or "", observation_id=prev.observation_id or "", exit_fees_inr=1.0).filled_qty == 0
    assert ledger.cash_balance() == cash_before
    ok2, msg = confirm_close_preview(prev, ledger.portfolio_context(), exit_fees_inr=1.0, slippage_pct=0.0)
    assert not ok2 and "already used" in msg.lower()


def _apptest_set_number(at, needle: str, value) -> None:
    for w in at.number_input:
        if w.label and needle.lower() in w.label.lower():
            w.set_value(value)
            return


def _apptest_buy_jrn_from_empty(at) -> None:
    for w in at.text_input:
        lab = (w.label or "").lower()
        if "trading symbol" in lab or "instrument key" in lab or "underlying" in lab:
            w.set_value(KEY)
    _apptest_set_number(at, "quantity", 10)
    _apptest_set_number(at, "limit price", 100.0)
    _apptest_set_number(at, "quote bid", 99.9)
    _apptest_set_number(at, "quote ask", 100.0)
    _apptest_set_number(at, "modeled entry fees", 2.0)
    _apptest_set_number(at, "modeled entry slippage", 0.0)
    for w in at.checkbox:
        if "stop" in (w.label or "").lower():
            w.check()
            break
    at.run(timeout=120)


def test_apptest_full_paper_journey(tmp_path: Path, monkeypatch):
    pytest.importorskip("streamlit.testing.v1", exc_type=ImportError)
    from streamlit.testing.v1 import AppTest

    db = _guard_tmp_db(tmp_path / "ui_journey.db")
    monkeypatch.setattr("nifty_lab.ui.trade_ticket._ledger_path", lambda _mode: db)
    calls: list[str] = []

    class TTransport:
        def get(self, url, *, headers=None, allow_redirects=False):
            calls.append(url)
            now = datetime.now(timezone.utc)
            body = _depth_body(KEY, token=KEY, bid=110.0, bid_q=3, ask=110.5, ask_q=3, retrieved_at=now)
            return 200, body, {}

    monkeypatch.setattr("nifty_lab.ui.trade_ticket.RequestsTransport", lambda: TTransport())

    at = AppTest.from_file(str(PROJECT_ROOT / "pages" / "12_Trade_Ticket.py"))
    at.run(timeout=120)
    assert calls == []
    _apptest_buy_jrn_from_empty(at)
    for btn in at.button:
        if (btn.label or "") == "Preview order":
            btn.click().run(timeout=120)
            break
    for btn in at.button:
        if (btn.label or "").startswith("Submit PAPER BUY"):
            btn.click().run(timeout=120)
            break
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    assert ledger.cash_balance() == pytest.approx(18_998.0, abs=0.01)
    assert len(ledger.list_closeable_positions()) == 1
    assert calls == []
    at.run(timeout=120)

    for r in at.radio:
        if r.label and "close quote source" in r.label.lower():
            r.set_value("Broker snapshot").run(timeout=120)
            break
    for btn in at.button:
        if "fetch broker close quote" in (btn.label or "").lower():
            btn.click().run(timeout=120)
            break
    assert len(calls) == 1
    for btn in at.button:
        if (btn.label or "") == "Preview Paper close":
            btn.click().run(timeout=120)
            break
    assert len(calls) == 1
    for btn in at.button:
        if (btn.label or "").startswith("Confirm Paper close"):
            btn.click().run(timeout=120)
            break
    v = load_paper_account_view(db)
    assert v.status == "OK"
    assert ledger.list_closeable_positions()[0]["quantity"] == 9