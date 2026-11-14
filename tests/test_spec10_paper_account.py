"""Spec 10 — read-only Paper Account results."""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from nifty_lab.config import PROJECT_ROOT
from nifty_lab.execution.modes import ExecutionMode
from nifty_lab.execution.paper_close import new_close_intent_id, quote_observation_id, submit_paper_close
from nifty_lab.execution.types import InstrumentKind, OrderSide, ProductType, QuoteSnapshot, TradeCandidate
from nifty_lab.execution.ledger.store import ExecutionLedger
from nifty_lab.paper_account.accounting import build_paper_account_view, load_paper_account_view
from nifty_lab.paper_account.paths import paper_db_path
from nifty_lab.paper_account.fee_basis import allocate_proportional_inr, replay_fee_basis
from nifty_lab.paper_account.reader import (
    load_paper_snapshot,
    open_readonly_connection,
    readonly_db_uri,
    verify_connection_readonly,
)
from decimal import Decimal


def _sell_candidate(qty: int, limit: float, bid: float) -> TradeCandidate:
    return TradeCandidate(
        mode=ExecutionMode.PAPER,
        kind=InstrumentKind.CASH_STOCK,
        instrument_key="ORC",
        trading_symbol="ORC",
        underlying="ORC",
        side=OrderSide.SELL,
        quantity=qty,
        limit_price_inr=limit,
        product=ProductType.DELIVERY,
        quote=QuoteSnapshot(bid, bid + 0.5, 100, 100, "ORC", datetime.now(timezone.utc)),
        lot_size=1,
    )


def _build_oracle_db(path: Path, *, mark: float) -> None:
    ledger = ExecutionLedger(path, mode=ExecutionMode.PAPER)
    buy = TradeCandidate(
        mode=ExecutionMode.PAPER,
        kind=InstrumentKind.CASH_STOCK,
        instrument_key="ORC",
        trading_symbol="ORC",
        underlying="ORC",
        side=OrderSide.BUY,
        quantity=10,
        limit_price_inr=100.0,
        product=ProductType.DELIVERY,
        stop_reference_inr=90.0,
        entry_cost_inr=2.0,
        exit_cost_reserve_inr=0.0,
        user_ack_stop_not_placed=True,
        quote=QuoteSnapshot(99.5, 100.0, 100, 100, "ORC", datetime.now(timezone.utc)),
        lot_size=1,
    )
    ledger.create_reservation(buy, "buy-1", 400.0)
    ledger.apply_paper_fill("buy-1", fill_qty=10, fill_price=100.0, fees=2.0, fill_event_id="buy-1-fill")
    sell = _sell_candidate(4, 110.0, 110.0)
    submit_paper_close(
        ledger,
        sell,
        intent_id=new_close_intent_id(),
        observation_id=quote_observation_id(sell.quote),
        exit_fees_inr=1.0,
        fill_event_id="sell-1-fill",
        slippage_pct=0.0,
    )
    conn = sqlite3.connect(path)
    conn.execute(
        "UPDATE positions SET mark_price=?, mark_time=? WHERE instrument_key=?",
        (mark, datetime.now(timezone.utc).isoformat(), "ORC"),
    )
    conn.commit()
    conn.close()


def test_not_initialized_missing_file(tmp_path: Path):
    view = load_paper_account_view(tmp_path / "missing.db")
    assert view.status == "NOT_INITIALIZED"


def test_readonly_blocks_writes(tmp_path: Path):
    db = tmp_path / "p.db"
    _build_oracle_db(db, mark=100.0)
    conn = open_readonly_connection(db)
    assert conn is not None
    assert verify_connection_readonly(conn)
    with pytest.raises(sqlite3.Error):
        conn.execute("INSERT INTO ledger_meta(key,value) VALUES('x','y')")
    conn.close()


def test_spec_oracle_partial_close_mark_100(tmp_path: Path):
    db = tmp_path / "oracle.db"
    _build_oracle_db(db, mark=100.0)
    view = load_paper_account_view(db)
    assert view.status == "OK"
    assert view.cash_inr == "19437.00"
    assert view.realized_gross_inr == "40.00"
    assert view.realized_net_inr == "38.20"
    assert view.remaining_entry_fees_inr == "1.20"
    assert view.gross_unrealized_total_inr == "0.00"
    assert view.unrealized_after_fees_total_inr == "-1.20"
    assert view.stored_mark_equity_inr == "20037.00"
    assert view.total_pnl_after_paid_fees_inr == "37.00"
    assert view.fees_paid_total_inr == "3.00"


def test_spec_oracle_mark_105(tmp_path: Path):
    db = tmp_path / "oracle105.db"
    _build_oracle_db(db, mark=105.0)
    view = load_paper_account_view(db)
    assert view.status == "OK"
    assert view.stored_mark_equity_inr == "20067.00"
    assert view.gross_unrealized_total_inr == "30.00"
    assert view.unrealized_after_fees_total_inr == "28.80"
    assert view.total_pnl_after_paid_fees_inr == "67.00"


def test_missing_mark_unavailable_portfolio(tmp_path: Path):
    db = tmp_path / "nomark.db"
    _build_oracle_db(db, mark=100.0)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE positions SET mark_price=NULL, mark_time=NULL WHERE instrument_key='ORC'")
    conn.commit()
    conn.close()
    view = load_paper_account_view(db)
    assert view.portfolio_valuation_status == "UNAVAILABLE_MISSING_MARK"
    assert view.stored_mark_equity_inr is None
    assert view.total_pnl_after_paid_fees_inr is None
    assert view.cash_inr == "19437.00"


def test_non_paper_order_rejected(tmp_path: Path):
    db = tmp_path / "mix.db"
    _build_oracle_db(db, mark=100.0)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO orders(local_id,broker_order_id,mode,status,instrument_key,symbol,underlying,"
        "side,quantity,filled_qty,limit_price,reserved_cash,reserved_risk,created_at,updated_at) "
        "VALUES('x',NULL,'LIVE','OPEN','ORC','ORC','ORC','BUY',1,0,1,0,0,'t','t')"
    )
    conn.commit()
    conn.close()
    view = load_paper_account_view(db)
    assert view.status == "RECONCILIATION_FAILED"
    assert view.error == "NON_PAPER_ORDERS"
    assert view.cash_inr is None


def test_real_paper_db_readonly_if_present():
    path = paper_db_path()
    if not path.is_file():
        pytest.skip("no local paper db")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    snap = load_paper_snapshot(path)
    after = hashlib.sha256(path.read_bytes()).hexdigest()
    assert before == after
    assert snap.read_only_verified
    build_paper_account_view(snap)


def test_streamlit_paper_account_apptest(tmp_path: Path, monkeypatch):
    pytest.importorskip("streamlit.testing.v1", exc_type=ImportError)
    from streamlit.testing.v1 import AppTest

    db = tmp_path / "paper_execution.db"
    _build_oracle_db(db, mark=100.0)
    monkeypatch.setattr("nifty_lab.paper_account.ui.paper_db_path", lambda: db)
    at = AppTest.from_file(str(PROJECT_ROOT / "pages" / "13_Paper_Account.py"))
    at.run(timeout=60)
    assert not at.exception
    assert any("LOCAL PAPER" in (w.value or "") for w in at.warning)


def _tamper(db: Path, sql: str, params: tuple = ()) -> None:
    conn = sqlite3.connect(db)
    conn.execute(sql, params)
    conn.commit()
    conn.close()


def test_reviewer_probe_buy_fill_qty_mismatch(tmp_path: Path):
    db = tmp_path / "p1.db"
    _build_oracle_db(db, mark=100.0)
    _tamper(db, "UPDATE fills SET qty=1 WHERE fill_event_id=?", ("buy-1-fill",))
    view = load_paper_account_view(db)
    assert view.status == "RECONCILIATION_FAILED"
    assert view.error in ("ORDER_FILL_QTY_MISMATCH", "POSITION_UNIT_MISMATCH", "CASH_FILL_MISMATCH")
    assert view.cash_inr is None
    assert view.stored_mark_equity_inr is None


def test_reviewer_probe_orphan_fill(tmp_path: Path):
    db = tmp_path / "p2.db"
    _build_oracle_db(db, mark=100.0)
    _tamper(db, "UPDATE fills SET local_order_id=? WHERE fill_event_id=?", ("missing", "buy-1-fill"))
    view = load_paper_account_view(db)
    assert view.status == "RECONCILIATION_FAILED"
    assert view.error == "FILL_ORPHAN_ORDER"
    assert view.cash_inr is None


def test_reviewer_probe_nan_reserved_cash(tmp_path: Path):
    db = tmp_path / "p3.db"
    _build_oracle_db(db, mark=100.0)
    _tamper(db, "UPDATE orders SET reserved_cash=? WHERE local_id=?", ("NaN", "buy-1"))
    view = load_paper_account_view(db)
    assert view.status == "RECONCILIATION_FAILED"
    assert view.error == "ORDER_RESERVE_INVALID"
    assert view.reserved_cash_inr is None


def test_reviewer_probe_offset_entry_fees_and_realized_net(tmp_path: Path):
    db = tmp_path / "p5.db"
    _build_oracle_db(db, mark=100.0)
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE positions SET entry_fees_inr = entry_fees_inr + 1 WHERE instrument_key='ORC'"
    )
    conn.execute(
        "UPDATE realized_events SET net_inr = net_inr + 1 WHERE fill_event_id='sell-1-fill'"
    )
    conn.commit()
    conn.close()
    view = load_paper_account_view(db)
    assert view.status == "RECONCILIATION_FAILED"
    assert view.error in ("POSITION_ENTRY_FEES_MISMATCH", "REALIZED_EVENT_MISMATCH")
    assert view.realized_net_inr is None
    assert view.remaining_entry_fees_inr is None
    assert view.cash_inr is None


def test_reviewer_probe_offset_avg_price_and_realized(tmp_path: Path):
    db = tmp_path / "p6.db"
    _build_oracle_db(db, mark=100.0)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE positions SET avg_price = avg_price + 1 WHERE instrument_key='ORC'")
    conn.execute(
        "UPDATE realized_events SET gross_inr = gross_inr + 6, net_inr = net_inr + 6 "
        "WHERE fill_event_id='sell-1-fill'"
    )
    conn.commit()
    conn.close()
    view = load_paper_account_view(db)
    assert view.status == "RECONCILIATION_FAILED"
    assert view.error in ("POSITION_BASIS_MISMATCH", "REALIZED_EVENT_MISMATCH")
    assert view.total_pnl_after_paid_fees_inr is None


def _buy_fill(
    ledger: ExecutionLedger,
    *,
    local_id: str,
    fill_event: str,
    qty: int,
    price: float,
    fees: float,
) -> None:
    buy = TradeCandidate(
        mode=ExecutionMode.PAPER,
        kind=InstrumentKind.CASH_STOCK,
        instrument_key="ORC",
        trading_symbol="ORC",
        underlying="ORC",
        side=OrderSide.BUY,
        quantity=qty,
        limit_price_inr=price,
        product=ProductType.DELIVERY,
        stop_reference_inr=90.0,
        entry_cost_inr=fees,
        exit_cost_reserve_inr=0.0,
        user_ack_stop_not_placed=True,
        quote=QuoteSnapshot(price - 0.5, price, 100, 100, "ORC", datetime.now(timezone.utc)),
        lot_size=1,
    )
    ledger.create_reservation(buy, local_id, 400.0)
    ledger.apply_paper_fill(local_id, fill_qty=qty, fill_price=price, fees=fees, fill_event_id=fill_event)


def _build_multi_trade_db(path: Path, *, mark: float) -> None:
    ledger = ExecutionLedger(path, mode=ExecutionMode.PAPER)
    _buy_fill(ledger, local_id="b1", fill_event="b1-fill", qty=6, price=100.0, fees=1.2)
    _buy_fill(ledger, local_id="b2", fill_event="b2-fill", qty=4, price=110.0, fees=0.8)
    sell3 = _sell_candidate(3, 115.0, 115.0)
    submit_paper_close(
        ledger,
        sell3,
        intent_id=new_close_intent_id(),
        observation_id=quote_observation_id(sell3.quote),
        exit_fees_inr=0.5,
        fill_event_id="s1-fill",
        slippage_pct=0.0,
    )
    sell2 = _sell_candidate(2, 108.0, 108.0)
    submit_paper_close(
        ledger,
        sell2,
        intent_id=new_close_intent_id(),
        observation_id=quote_observation_id(sell2.quote),
        exit_fees_inr=0.3,
        fill_event_id="s2-fill",
        slippage_pct=0.0,
    )
    _buy_fill(ledger, local_id="b3", fill_event="b3-fill", qty=5, price=105.0, fees=1.0)
    conn = sqlite3.connect(path)
    conn.execute(
        "UPDATE positions SET mark_price=?, mark_time=? WHERE instrument_key=?",
        (mark, datetime.now(timezone.utc).isoformat(), "ORC"),
    )
    conn.commit()
    conn.close()


def test_multi_buy_partial_closes_reopen_oracle(tmp_path: Path):
    db = tmp_path / "multi.db"
    _build_multi_trade_db(db, mark=102.0)
    view = load_paper_account_view(db)
    assert view.status == "OK"
    assert view.realized_gross_inr == "41.00"
    assert view.realized_net_inr == "39.20"
    assert view.remaining_entry_fees_inr == "2.00"
    assert len(view.positions) == 1
    assert view.positions[0].quantity == 10
    assert view.positions[0].avg_price_inr == "104.50"


def test_fill_sequence_ambiguous_same_timestamp(tmp_path: Path):
    db = tmp_path / "ambig.db"
    _build_oracle_db(db, mark=100.0)
    conn = sqlite3.connect(db)
    ts = conn.execute("SELECT filled_at FROM fills LIMIT 1").fetchone()[0]
    conn.execute("UPDATE fills SET filled_at=?", (ts,))
    conn.commit()
    conn.close()
    view = load_paper_account_view(db)
    assert view.status == "RECONCILIATION_FAILED"
    assert view.error == "FILL_SEQUENCE_AMBIGUOUS"


def test_proportional_paise_sell_order_matters():
    a1, r1 = allocate_proportional_inr(Decimal("0.05"), 1, 3)
    a2, _r2 = allocate_proportional_inr(r1, 1, 2)
    assert str(a1) == "0.01"
    assert str(a2) == "0.02"


def test_fill_time_naive_rejected(tmp_path: Path):
    db = tmp_path / "naive.db"
    _build_oracle_db(db, mark=100.0)
    _tamper(db, "UPDATE fills SET filled_at=? WHERE fill_event_id=?", ("2026-01-01T10:00:00", "buy-1-fill"))
    view = load_paper_account_view(db)
    assert view.status == "RECONCILIATION_FAILED"
    assert view.error == "FILL_TIME_NAIVE"
    assert view.cash_inr is None


def test_equivalent_utc_ist_instant_buy_sell_ambiguous(tmp_path: Path):
    db = tmp_path / "ist.db"
    _build_oracle_db(db, mark=100.0)
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE fills SET filled_at=? WHERE fill_event_id=?",
        ("2026-01-01T10:00:00+00:00", "buy-1-fill"),
    )
    conn.execute(
        "UPDATE fills SET filled_at=? WHERE fill_event_id=?",
        ("2026-01-01T15:30:00+05:30", "sell-1-fill"),
    )
    conn.commit()
    conn.close()
    view = load_paper_account_view(db)
    assert view.status == "RECONCILIATION_FAILED"
    assert view.error == "FILL_SEQUENCE_AMBIGUOUS"


def test_tied_sell_sell_same_instant_rejected(tmp_path: Path):
    db = tmp_path / "ss.db"
    _build_multi_trade_db(db, mark=100.0)
    conn = sqlite3.connect(db)
    ts = "2026-01-02T12:00:00+00:00"
    conn.execute("UPDATE fills SET filled_at=? WHERE fill_event_id=?", (ts, "s1-fill"))
    conn.execute("UPDATE fills SET filled_at=? WHERE fill_event_id=?", (ts, "s2-fill"))
    conn.commit()
    conn.close()
    view = load_paper_account_view(db)
    assert view.status == "RECONCILIATION_FAILED"
    assert view.error == "FILL_SEQUENCE_AMBIGUOUS"
    assert view.realized_net_inr is None


def test_fill_id_missing_rejected():
    orders = {
        "b1": {
            "instrument_key": "X",
            "side": OrderSide.BUY.value,
        }
    }
    fills = [
        {
            "fill_event_id": "e1",
            "local_order_id": "b1",
            "qty": 1,
            "price": 100.0,
            "fees": 0.0,
            "filled_at": "2026-01-01T10:00:00+00:00",
        }
    ]
    r = replay_fee_basis(fills=fills, positions=[], realized_events=[], orders_by_id=orders)
    assert not r.ok
    assert "FILL_ID_MISSING" in r.errors


def test_tied_buy_buy_same_instant_permutation_invariant():
    orders = {
        "b1": {"instrument_key": "X", "side": OrderSide.BUY.value},
        "b2": {"instrument_key": "X", "side": OrderSide.BUY.value},
    }
    ts = "2026-01-01T12:00:00+00:00"
    f1 = {
        "fill_id": "id-1",
        "fill_event_id": "e1",
        "local_order_id": "b1",
        "qty": 6,
        "price": 100.0,
        "fees": 1.0,
        "filled_at": ts,
    }
    f2 = {
        "fill_id": "id-2",
        "fill_event_id": "e2",
        "local_order_id": "b2",
        "qty": 4,
        "price": 110.0,
        "fees": 2.0,
        "filled_at": ts,
    }
    pos = [{"instrument_key": "X", "quantity": 10, "avg_price": 104.0, "entry_fees_inr": 3.0}]
    r_a = replay_fee_basis(fills=[f1, f2], positions=pos, realized_events=[], orders_by_id=orders)
    r_b = replay_fee_basis(fills=[f2, f1], positions=pos, realized_events=[], orders_by_id=orders)
    assert r_a.ok and r_b.ok
    assert r_a.by_instrument["X"].quantity == r_b.by_instrument["X"].quantity == 10
    assert r_a.by_instrument["X"].entry_fees_inr == r_b.by_instrument["X"].entry_fees_inr


def test_distinct_timestamps_valid_oracle_unchanged(tmp_path: Path):
    db = tmp_path / "distinct.db"
    _build_oracle_db(db, mark=100.0)
    view = load_paper_account_view(db)
    assert view.status == "OK"
    assert view.realized_net_inr == "38.20"


def test_reviewer_probe_sell_over_reserved(tmp_path: Path):
    db = tmp_path / "p4.db"
    _build_oracle_db(db, mark=100.0)
    conn = sqlite3.connect(db)
    sell_id = conn.execute("SELECT local_id FROM orders WHERE side='SELL' LIMIT 1").fetchone()[0]
    conn.execute(
        "UPDATE orders SET status='OPEN', quantity=100, filled_qty=4 WHERE local_id=?",
        (sell_id,),
    )
    conn.commit()
    conn.close()
    view = load_paper_account_view(db)
    assert view.status == "RECONCILIATION_FAILED"
    assert view.error == "SELL_OVER_RESERVED"
    assert view.cash_inr is None


def test_uri_reserved_path_chars(tmp_path: Path):
    db = tmp_path / "paper#vault.db"
    _build_oracle_db(db, mark=100.0)
    assert "paper%23vault.db" in readonly_db_uri(db)
    view = load_paper_account_view(db)
    assert view.status == "OK"
    assert view.cash_inr == "19437.00"


def test_unsupported_schema_missing_column(tmp_path: Path):
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE ledger_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO ledger_meta VALUES ('funded', '20000');
        CREATE TABLE orders (
            local_id TEXT PRIMARY KEY, broker_order_id TEXT, mode TEXT, status TEXT,
            instrument_key TEXT, symbol TEXT, underlying TEXT, side TEXT,
            quantity INTEGER, filled_qty INTEGER, limit_price REAL,
            reserved_cash REAL, reserved_risk REAL, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE fills (
            fill_id TEXT PRIMARY KEY, fill_event_id TEXT, local_order_id TEXT,
            qty INTEGER, price REAL, fees REAL, filled_at TEXT
        );
        CREATE TABLE positions (
            instrument_key TEXT PRIMARY KEY, symbol TEXT, underlying TEXT,
            quantity INTEGER, avg_price REAL, mark_price REAL, mark_time TEXT
        );
        CREATE TABLE cash_ledger (
            event_id TEXT PRIMARY KEY, delta_cash REAL, delta_fees REAL, note TEXT, created_at TEXT
        );
        CREATE TABLE realized_events (
            event_id TEXT PRIMARY KEY, fill_event_id TEXT, gross_inr REAL, net_inr REAL, created_at TEXT
        );
        """
    )
    conn.close()
    snap = load_paper_snapshot(db)
    assert snap.load_status == "UNSUPPORTED_SCHEMA"
    assert snap.load_error == "MISSING_COLUMN"
    view = build_paper_account_view(snap)
    assert view.status == "UNSUPPORTED_SCHEMA"
    assert view.cash_inr is None


def test_streamlit_reconciliation_failed_apptest(tmp_path: Path, monkeypatch):
    pytest.importorskip("streamlit.testing.v1", exc_type=ImportError)
    from streamlit.testing.v1 import AppTest

    db = tmp_path / "bad.db"
    _build_oracle_db(db, mark=100.0)
    _tamper(db, "UPDATE fills SET local_order_id=? WHERE fill_event_id=?", ("missing", "buy-1-fill"))
    monkeypatch.setattr("nifty_lab.paper_account.ui.paper_db_path", lambda: db)
    before = db.read_bytes()
    at = AppTest.from_file(str(PROJECT_ROOT / "pages" / "13_Paper_Account.py"))
    at.run(timeout=60)
    assert not at.exception
    assert db.read_bytes() == before
    assert any("RECONCILIATION_FAILED" in (e.value or "") for e in at.error)


def test_streamlit_not_initialized_apptest(tmp_path: Path, monkeypatch):
    pytest.importorskip("streamlit.testing.v1", exc_type=ImportError)
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr("nifty_lab.paper_account.ui.paper_db_path", lambda: tmp_path / "nope.db")
    at = AppTest.from_file(str(PROJECT_ROOT / "pages" / "13_Paper_Account.py"))
    at.run(timeout=60)
    assert not at.exception
    assert any("NOT INITIALIZED" in (w.value or "") for w in at.warning)
