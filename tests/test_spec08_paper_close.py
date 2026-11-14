"""Spec 08 — Paper sell-to-close and accounting oracle."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from nifty_lab.execution.gate import evaluate_entry
from nifty_lab.execution.modes import ExecutionMode
from nifty_lab.execution.paper_close import (
    new_close_intent_id,
    quote_observation_id,
    re_evaluate_paper_close,
    submit_paper_close,
)
from nifty_lab.execution.preview import (
    _hash_identity,
    build_close_preview,
    build_preview,
    confirm_close_preview,
    confirm_preview,
)
from nifty_lab.execution.types import InstrumentKind, OrderSide, ProductType, QuoteSnapshot, TradeCandidate
from nifty_lab.execution.ledger.store import ExecutionLedger


def _buy_fill_oracle(ledger: ExecutionLedger, qty: int = 10, price: float = 100.0, entry_fees: float = 20.0) -> None:
    cand = TradeCandidate(
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
        entry_cost_inr=entry_fees,
        exit_cost_reserve_inr=0.0,
        user_ack_stop_not_placed=True,
        quote=QuoteSnapshot(price - 0.5, price, qty, qty, "ORC", datetime.now(timezone.utc)),
        lot_size=1,
    )
    ledger.create_reservation(cand, "buy-orc", 200.0)
    ledger.apply_paper_fill(
        "buy-orc", fill_qty=qty, fill_price=price, fees=entry_fees, fill_event_id="buy-orc-fill"
    )


def _sell_candidate(qty: int, limit: float, bid: float, bid_qty: int) -> TradeCandidate:
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
        quote=QuoteSnapshot(bid, bid + 0.5, bid_qty, bid_qty, "ORC", datetime.now(timezone.utc)),
        lot_size=1,
    )


def test_accounting_oracle_partial_and_full(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "orc.db", mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger)
    assert ledger.cash_balance() == pytest.approx(18_980.0, abs=0.01)
    pos = ledger.list_closeable_positions()[0]
    assert pos["quantity"] == 10
    assert pos["avg_price"] == pytest.approx(100.0)
    assert pos["entry_fees_inr"] == pytest.approx(20.0)

    sell1 = _sell_candidate(4, 110.0, 110.0, 10)
    obs1 = quote_observation_id(sell1.quote)
    submit_paper_close(
        ledger,
        sell1,
        intent_id=new_close_intent_id(),
        observation_id=obs1,
        exit_fees_inr=8.0,
        fill_event_id="s1",
        slippage_pct=0.0,
    )
    assert ledger.cash_balance() == pytest.approx(19_412.0, abs=0.01)
    pos = ledger.list_closeable_positions()[0]
    assert pos["quantity"] == 6
    assert pos["avg_price"] == pytest.approx(100.0)
    assert pos["entry_fees_inr"] == pytest.approx(12.0, abs=0.01)
    assert ledger.cumulative_realized_net() == pytest.approx(24.0, abs=0.01)
    assert ledger.equity() == pytest.approx(20_012.0, abs=0.01)

    sell2 = _sell_candidate(6, 90.0, 90.0, 10)
    obs2 = quote_observation_id(sell2.quote)
    submit_paper_close(
        ledger,
        sell2,
        intent_id=new_close_intent_id(),
        observation_id=obs2,
        exit_fees_inr=12.0,
        fill_event_id="s2",
        slippage_pct=0.0,
    )
    assert ledger.cash_balance() == pytest.approx(19_940.0, abs=0.01)
    assert ledger.list_closeable_positions() == []
    assert ledger.cumulative_realized_net() == pytest.approx(-60.0, abs=0.01)
    assert ledger.equity() == pytest.approx(19_940.0, abs=0.01)


def test_competing_close_rejected(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "c.db", mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger, qty=10)
    sell = _sell_candidate(6, 100.0, 99.5, 10)
    oid = submit_paper_close(
        ledger, sell, intent_id=new_close_intent_id(), observation_id=quote_observation_id(sell.quote),
        exit_fees_inr=1.0, fill_event_id="c1", 
    ).local_order_id
    sell2 = _sell_candidate(5, 100.0, 99.5, 10)
    with pytest.raises(ValueError):
        ledger.admit_paper_close(sell2, new_close_intent_id(), _hash_identity(sell2))


def test_close_allowed_when_entry_blocked(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "r.db", mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger, qty=10)
    ctx = ledger.portfolio_context()
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
        stop_reference_inr=50.0,
        entry_cost_inr=30.0,
        exit_cost_reserve_inr=20.0,
        user_ack_stop_not_placed=True,
        quote=QuoteSnapshot(99.0, 99.5, 10, 10, "ORC", datetime.now(timezone.utc)),
    )
    assert not evaluate_entry(buy, ctx).allowed
    sell = _sell_candidate(2, 90.0, 99.0, 5)
    assert evaluate_entry(sell, ctx, for_reduce_only=True).allowed


def test_replay_observation_no_double_fill(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "obs.db", mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger, qty=10)
    sell = _sell_candidate(4, 110.0, 110.0, 4)
    obs = quote_observation_id(sell.quote)
    r1 = submit_paper_close(
        ledger, sell, intent_id=new_close_intent_id(), observation_id=obs, exit_fees_inr=1.0, fill_event_id="o1"
    )
    assert r1.filled_qty == 4
    r2 = re_evaluate_paper_close(ledger, r1.local_order_id, quote=sell.quote, observation_id=obs, exit_fees_inr=1.0)
    assert r2.filled_qty == 0


def test_partial_close_cancel_preserves_basis(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "pc.db", mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger, qty=10)
    sell = _sell_candidate(10, 108.0, 110.0, 2)
    r = submit_paper_close(
        ledger, sell, intent_id=new_close_intent_id(), observation_id=quote_observation_id(sell.quote),
        exit_fees_inr=2.0, fill_event_id="p1"
    )
    assert r.filled_qty == 2
    pos = ledger.list_closeable_positions()[0]
    assert pos["avg_price"] == pytest.approx(100.0)
    ledger.cancel_paper_remainder(r.local_order_id)
    assert ledger.list_closeable_positions()[0]["quantity"] == 8


def test_close_preview_reduce_only(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "pr.db", mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger, qty=5)
    sell = _sell_candidate(2, 95.0, 99.0, 5)
    t = build_preview(sell, ledger.portfolio_context())
    assert t.gate.allowed
    ok, _ = confirm_preview(t, ledger.portfolio_context())
    assert ok


def _buy_position(
    ledger: ExecutionLedger,
    *,
    kind: InstrumentKind = InstrumentKind.CASH_STOCK,
    key: str = "POS",
    qty: int,
    lot: int = 1,
    price: float = 100.0,
    entry_fees: float = 0.0,
) -> None:
    cand = TradeCandidate(
        mode=ExecutionMode.PAPER,
        kind=kind,
        instrument_key=key,
        trading_symbol=key,
        underlying=key if kind != InstrumentKind.NIFTY_OPTION else "NIFTY",
        side=OrderSide.BUY,
        quantity=qty,
        limit_price_inr=price,
        product=ProductType.DELIVERY,
        stop_reference_inr=90.0,
        entry_cost_inr=entry_fees,
        exit_cost_reserve_inr=0.0,
        user_ack_stop_not_placed=True,
        quote=QuoteSnapshot(price, price + 0.5, qty, qty, key, datetime.now(timezone.utc)),
        lot_size=lot,
    )
    oid = f"buy-{key}-{qty}"
    risk = min(350.0, cand.limit_price_inr * qty)
    ledger.create_reservation(cand, oid, risk)
    ledger.apply_paper_fill(oid, fill_qty=qty, fill_price=price, fees=entry_fees, fill_event_id=f"{oid}-fill")


def test_etf_and_nifty_whole_lot_closes(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "mix.db", mode=ExecutionMode.PAPER)
    _buy_position(ledger, kind=InstrumentKind.CASH_ETF, key="ETF1", qty=10, entry_fees=5.0)
    etf_sell = TradeCandidate(
        mode=ExecutionMode.PAPER,
        kind=InstrumentKind.CASH_ETF,
        instrument_key="ETF1",
        trading_symbol="ETF1",
        underlying="ETF1",
        side=OrderSide.SELL,
        quantity=4,
        limit_price_inr=101.0,
        product=ProductType.DELIVERY,
        quote=QuoteSnapshot(101.0, 101.5, 4, 4, "ETF1", datetime.now(timezone.utc)),
        lot_size=1,
    )
    r = submit_paper_close(
        ledger, etf_sell, intent_id=new_close_intent_id(), observation_id=quote_observation_id(etf_sell.quote),
        exit_fees_inr=1.0, fill_event_id="etf-close",
    )
    assert r.filled_qty == 4
    _buy_position(ledger, kind=InstrumentKind.NIFTY_OPTION, key="OPT1", qty=50, lot=50, price=7.0, entry_fees=2.0)
    opt_sell = TradeCandidate(
        mode=ExecutionMode.PAPER,
        kind=InstrumentKind.NIFTY_OPTION,
        instrument_key="OPT1",
        trading_symbol="OPT1",
        underlying="NIFTY",
        side=OrderSide.SELL,
        quantity=50,
        limit_price_inr=8.0,
        product=ProductType.DELIVERY,
        quote=QuoteSnapshot(8.0, 8.5, 75, 75, "OPT1", datetime.now(timezone.utc)),
        lot_size=50,
    )
    r2 = submit_paper_close(
        ledger, opt_sell, intent_id=new_close_intent_id(), observation_id=quote_observation_id(opt_sell.quote),
        exit_fees_inr=1.0, fill_event_id="opt-close",
    )
    assert r2.filled_qty == 50
    assert not any(p["instrument_key"] == "OPT1" for p in ledger.list_closeable_positions())
    etf = next(p for p in ledger.list_closeable_positions() if p["instrument_key"] == "ETF1")
    assert etf["quantity"] == 6


def test_close_fill_after_cancel_rejected(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "fac.db", mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger, qty=6)
    sell = _sell_candidate(6, 100.0, 99.0, 0)
    oid = submit_paper_close(
        ledger, sell, intent_id=new_close_intent_id(), observation_id=quote_observation_id(sell.quote),
        exit_fees_inr=0.0, fill_event_id="pre",
    ).local_order_id
    ledger.cancel_paper_remainder(oid)
    with pytest.raises(ValueError, match="cancelled"):
        ledger.apply_paper_fill(oid, fill_qty=1, fill_price=99.0, fees=0.0, fill_event_id="late")


def test_close_intent_single_use_across_reopen(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "intent.db", mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger, qty=4)
    sell = _sell_candidate(2, 100.0, 100.0, 2)
    intent = new_close_intent_id()
    obs = quote_observation_id(sell.quote)
    oid1 = submit_paper_close(
        ledger, sell, intent_id=intent, observation_id=obs, exit_fees_inr=0.0, fill_event_id="i1",
    ).local_order_id
    ledger2 = ExecutionLedger(ledger.db_path, mode=ExecutionMode.PAPER)
    sell_other = _sell_candidate(2, 101.0, 101.0, 2)
    with pytest.raises(ValueError, match="intent"):
        ledger2.admit_paper_close(sell_other, intent, _hash_identity(sell_other))
    sell_orders = [o for o in ledger2.list_paper_orders() if o["side"] == OrderSide.SELL.value]
    assert len(sell_orders) == 1
    oid2 = ledger2.admit_paper_close(sell, new_close_intent_id(), _hash_identity(sell), exit_fees_inr=0.0)
    assert oid2 != oid1
    assert len([o for o in ledger2.list_paper_orders() if o["side"] == OrderSide.SELL.value]) == 2


def test_paise_fee_allocation_reconciles_at_full_close(tmp_path: Path):
    from nifty_lab.execution.paper_accounting import allocate_proportional

    a1, r1 = allocate_proportional(10.01, 1, 3)
    a2, r2 = allocate_proportional(r1, 1, 2)
    a3, r3 = allocate_proportional(r2, 1, 1)
    assert pytest.approx(a1 + a2 + a3, abs=0.01) == 10.01
    assert r3 == pytest.approx(0.0, abs=0.01)
    ledger = ExecutionLedger(tmp_path / "paise.db", mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger, qty=3, entry_fees=10.01)
    sell = _sell_candidate(1, 100.0, 100.0, 1)
    submit_paper_close(
        ledger, sell, intent_id=new_close_intent_id(), observation_id=quote_observation_id(sell.quote),
        exit_fees_inr=0.0, fill_event_id="p-close",
    )
    pos = ledger.list_closeable_positions()[0]
    assert pos["entry_fees_inr"] == pytest.approx(r1, abs=0.02)


def test_re_evaluate_uses_fresh_observation(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "reeval.db", mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger, qty=10)
    sell = _sell_candidate(10, 110.0, 110.0, 3)
    obs1 = quote_observation_id(sell.quote)
    r1 = submit_paper_close(
        ledger, sell, intent_id=new_close_intent_id(), observation_id=obs1, exit_fees_inr=0.0, fill_event_id="r1"
    )
    assert r1.filled_qty == 3
    q2 = QuoteSnapshot(110.0, 110.5, 4, 4, "ORC", datetime.now(timezone.utc))
    obs2 = quote_observation_id(q2)
    r2 = re_evaluate_paper_close(ledger, r1.local_order_id, quote=q2, observation_id=obs2, exit_fees_inr=0.0)
    assert r2.filled_qty == 4
    assert ledger.list_closeable_positions()[0]["quantity"] == 3


def test_zero_bid_depth_no_invented_fill(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "zd.db", mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger, qty=5)
    sell = _sell_candidate(5, 90.0, 100.0, 0)
    r = submit_paper_close(
        ledger, sell, intent_id=new_close_intent_id(), observation_id=quote_observation_id(sell.quote),
        exit_fees_inr=0.0, fill_event_id="z1",
    )
    assert r.filled_qty == 0
    assert ledger.list_closeable_positions()[0]["quantity"] == 5


def test_same_order_partial_then_complete_liquidation(tmp_path: Path):
    """Review finding 1: remainder fill must not double-count prior reductions."""
    ledger = ExecutionLedger(tmp_path / "liq.db", mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger, qty=10)
    sell = _sell_candidate(10, 110.0, 110.0, 4)
    r1 = submit_paper_close(
        ledger, sell, intent_id=new_close_intent_id(), observation_id=quote_observation_id(sell.quote),
        exit_fees_inr=0.0, fill_event_id="liq-1",
    )
    assert r1.filled_qty == 4
    q2 = QuoteSnapshot(110.0, 110.5, 10, 10, "ORC", datetime.now(timezone.utc))
    r2 = re_evaluate_paper_close(
        ledger, r1.local_order_id, quote=q2, observation_id=quote_observation_id(q2), exit_fees_inr=0.0, fill_event_id="liq-2"
    )
    assert r2.filled_qty == 6
    assert ledger.list_closeable_positions() == []


def test_identical_later_close_is_new_order_not_historical(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "dup.db", mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger, qty=10)
    sell = _sell_candidate(2, 100.0, 100.0, 2)
    r1 = submit_paper_close(
        ledger, sell, intent_id=new_close_intent_id(), observation_id=quote_observation_id(sell.quote),
        exit_fees_inr=0.0, fill_event_id="d1",
    )
    assert r1.filled_qty == 2
    assert ledger.list_closeable_positions()[0]["quantity"] == 8
    ts = datetime.now(timezone.utc)
    sell2 = TradeCandidate(
        mode=ExecutionMode.PAPER,
        kind=InstrumentKind.CASH_STOCK,
        instrument_key="ORC",
        trading_symbol="ORC",
        underlying="ORC",
        side=OrderSide.SELL,
        quantity=2,
        limit_price_inr=100.0,
        product=ProductType.DELIVERY,
        quote=QuoteSnapshot(100.0, 100.5, 2, 2, "ORC", ts),
        lot_size=1,
    )
    r2 = submit_paper_close(
        ledger, sell2, intent_id=new_close_intent_id(), observation_id=quote_observation_id(sell2.quote),
        exit_fees_inr=0.0, fill_event_id="d2",
    )
    assert r2.local_order_id != r1.local_order_id
    assert r2.filled_qty == 2
    assert ledger.list_closeable_positions()[0]["quantity"] == 6


def test_reevaluate_rejects_foreign_instrument_quote(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "mix.db", mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger, qty=5)
    sell = _sell_candidate(3, 100.0, 100.0, 1)
    r1 = submit_paper_close(
        ledger, sell, intent_id=new_close_intent_id(), observation_id=quote_observation_id(sell.quote),
        exit_fees_inr=0.0, fill_event_id="x1",
    )
    assert r1.filled_qty == 1
    foreign = QuoteSnapshot(120.0, 120.5, 5, 5, "OTHER", datetime.now(timezone.utc))
    with pytest.raises(ValueError, match="instrument"):
        re_evaluate_paper_close(
            ledger, r1.local_order_id, quote=foreign, observation_id=quote_observation_id(foreign), exit_fees_inr=0.0
        )
    assert ledger.list_closeable_positions()[0]["quantity"] == 4


def test_observation_id_includes_source_time(tmp_path: Path):
    base = QuoteSnapshot(100.0, 100.5, 4, 4, "ORC", datetime(2026, 1, 1, tzinfo=timezone.utc))
    later = QuoteSnapshot(100.0, 100.5, 4, 4, "ORC", datetime(2026, 1, 2, tzinfo=timezone.utc))
    assert quote_observation_id(base) != quote_observation_id(later)


def test_nonmarketable_close_does_not_consume_observation(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "nm.db", mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger, qty=5)
    sell = _sell_candidate(2, 120.0, 100.0, 5)
    obs = quote_observation_id(sell.quote)
    r1 = submit_paper_close(
        ledger, sell, intent_id=new_close_intent_id(), observation_id=obs, exit_fees_inr=0.0,
    )
    assert r1.filled_qty == 0
    sell2 = _sell_candidate(2, 100.0, 100.0, 2)
    sell2.quote = sell.quote
    r2 = submit_paper_close(
        ledger, sell2, intent_id=new_close_intent_id(), observation_id=obs, exit_fees_inr=0.0, fill_event_id="nm2",
    )
    assert r2.filled_qty == 2


def test_close_preview_fee_tamper_rejected(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "fee.db", mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger, qty=3)
    sell = _sell_candidate(1, 100.0, 100.0, 1)
    t = build_close_preview(sell, ledger.portfolio_context(), exit_fees_inr=5.0)
    ok, msg = confirm_close_preview(t, ledger.portfolio_context(), exit_fees_inr=7.0, slippage_pct=0.0)
    assert not ok
    assert "fee" in msg.lower()


def test_negative_exit_fees_rejected_with_rollback(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "nf.db", mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger, qty=10)
    cash_before = ledger.cash_balance()
    sell = _sell_candidate(2, 110.0, 110.0, 10)
    with pytest.raises(ValueError, match="[Ff]ee"):
        submit_paper_close(
            ledger, sell, intent_id=new_close_intent_id(), observation_id=quote_observation_id(sell.quote),
            exit_fees_inr=-20.0, fill_event_id="nf1",
        )
    assert ledger.cash_balance() == pytest.approx(cash_before)
    assert ledger.list_closeable_positions()[0]["quantity"] == 10
    sell_orders = [o for o in ledger.list_paper_orders() if o["side"] == OrderSide.SELL.value]
    assert sell_orders == []


def test_relabel_nifty_as_stock_rejected(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "tamper.db", mode=ExecutionMode.PAPER)
    _buy_position(ledger, kind=InstrumentKind.NIFTY_OPTION, key="OPT1", qty=50, lot=50, price=7.0)
    tampered = TradeCandidate(
        mode=ExecutionMode.PAPER,
        kind=InstrumentKind.CASH_STOCK,
        instrument_key="OPT1",
        trading_symbol="OPT1",
        underlying="NIFTY",
        side=OrderSide.SELL,
        quantity=1,
        limit_price_inr=8.0,
        product=ProductType.DELIVERY,
        quote=QuoteSnapshot(8.0, 8.5, 50, 50, "OPT1", datetime.now(timezone.utc)),
        lot_size=1,
    )
    with pytest.raises(ValueError, match="metadata"):
        submit_paper_close(
            ledger, tampered, intent_id=new_close_intent_id(),
            observation_id=quote_observation_id(tampered.quote), exit_fees_inr=1.0,
        )
    assert ledger.list_closeable_positions()[0]["quantity"] == 50


def test_legacy_unknown_metadata_blocked_on_reopen(tmp_path: Path):
    import sqlite3

    ledger = ExecutionLedger(tmp_path / "leg.db", mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger, qty=5)
    with sqlite3.connect(ledger.db_path) as conn:
        conn.execute(
            "UPDATE positions SET instrument_kind=NULL, product=NULL, lot_size=0, closeable=0 WHERE instrument_key='ORC'"
        )
        conn.commit()
    ledger2 = ExecutionLedger(ledger.db_path, mode=ExecutionMode.PAPER)
    assert ledger2.list_closeable_positions() == []
    with pytest.raises(ValueError, match="metadata"):
        sell = _sell_candidate(1, 100.0, 100.0, 1)
        submit_paper_close(
            ledger2, sell, intent_id=new_close_intent_id(), observation_id=quote_observation_id(sell.quote),
            exit_fees_inr=0.0,
        )


def test_same_intent_idempotent_after_restart(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "rst.db", mode=ExecutionMode.PAPER)
    _buy_fill_oracle(ledger, qty=3)
    sell = _sell_candidate(2, 100.0, 100.0, 2)
    intent = new_close_intent_id()
    obs = quote_observation_id(sell.quote)
    oid = submit_paper_close(
        ledger, sell, intent_id=intent, observation_id=obs, exit_fees_inr=1.0, fill_event_id="rst1",
    ).local_order_id
    ledger2 = ExecutionLedger(ledger.db_path, mode=ExecutionMode.PAPER)
    oid2 = ledger2.admit_paper_close(sell, intent, _hash_identity(sell), exit_fees_inr=1.0)
    assert oid2 == oid
