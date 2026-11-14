"""Spec 08 — execution gate, paper ledger, live guard (offline)."""
from __future__ import annotations

import math
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nifty_lab.execution.guard import assert_live_mutation_allowed, live_mutations_forbidden
from nifty_lab.execution.gate import (
    ExecutionPortfolioContext,
    evaluate_entry,
    resolved_candidate_risk,
)
from nifty_lab.execution.modes import ExecutionMode
from nifty_lab.execution.paper import submit_paper_entry
from nifty_lab.execution.policy import EXECUTION_V1
from nifty_lab.execution.preview import build_preview, confirm_preview
from nifty_lab.execution.types import InstrumentKind, OrderSide, ProductType, QuoteSnapshot, TradeCandidate
from nifty_lab.execution.ledger.store import ExecutionLedger
from nifty_lab.execution.adapters.live import LiveOrderAdapter
from nifty_lab.risk.budget import check_position_eligibility
from nifty_lab.risk.context import independent_test_context
from nifty_lab.config import RiskConfig
from nifty_lab.options.payoff import OptionLeg, OptionType, Position, Quote, Side


@pytest.fixture(autouse=True)
def forbid_live(monkeypatch):
    monkeypatch.setenv("NSL_FORBID_LIVE_MUTATIONS", "1")


def _quote() -> QuoteSnapshot:
    return QuoteSnapshot(99.0, 99.5, 500, 500, "K", datetime.now(timezone.utc))


def _ctx(**kw) -> ExecutionPortfolioContext:
    base = dict(
        profile_id=EXECUTION_V1.profile_id,
        policy=EXECUTION_V1,
        equity_inr=20_000.0,
        peak_equity_inr=20_000.0,
        cash_inr=20_000.0,
        reserved_cash_inr=0.0,
        reserved_risk_inr=0.0,
        open_position_count=0,
        open_risk_by_underlying={},
        sum_open_risk_inr=0.0,
        valuation_trusted=True,
        available_strategy_cash_inr=20_000.0,
        exposed_instrument_count=0,
    )
    base.update(kw)
    return ExecutionPortfolioContext(**base)


def _risk300_candidate(**kw) -> TradeCandidate:
    base = dict(
        limit_price_inr=100.0,
        stop_reference_inr=75.0,
        entry_cost_inr=30.0,
        exit_cost_reserve_inr=20.0,
        quantity=10,
    )
    base.update(kw)
    return _stock_candidate(**base)


def _stock_candidate(**kw) -> TradeCandidate:
    base = dict(
        mode=ExecutionMode.PAPER,
        kind=InstrumentKind.CASH_STOCK,
        instrument_key="K",
        trading_symbol="TST",
        underlying="TST",
        side=OrderSide.BUY,
        quantity=10,
        limit_price_inr=100.0,
        product=ProductType.DELIVERY,
        stop_reference_inr=97.0,
        entry_cost_inr=30.0,
        exit_cost_reserve_inr=20.0,
        user_ack_stop_not_placed=True,
        quote=_quote(),
    )
    base.update(kw)
    return TradeCandidate(**base)


def test_gate_rejects_understated_context_field():
    leg = OptionLeg(OptionType.CE, 25000.0, Side.LONG, Quote(60, 62), lots=1, lot_size=65)
    pos = Position("long", "NIFTY", "2026-12-31", [leg])
    true_loss = pos.max_loss(include_costs=True)
    ctx = independent_test_context(candidate_max_loss_inr=0.0, per_position_risk_max=1_500.0)
    res = check_position_eligibility(pos, RiskConfig(risk_per_trade_max=1_500.0), context=ctx)
    assert res.max_loss_incl_costs == pytest.approx(true_loss, rel=0.01)
    if true_loss > 500:
        assert res.status.value == "REJECTED"


def test_gate_reproduces_4797_not_zero_pass():
    """Caller-declared zero must not shrink computed risk."""
    prem = 4797.82 / 65.0
    leg = OptionLeg(OptionType.CE, 25000.0, Side.LONG, Quote(prem - 1, prem + 1), lots=1, lot_size=65)
    pos = Position("long", "NIFTY", "2026-12-31", [leg])
    ctx = independent_test_context(candidate_max_loss_inr=0.0, per_position_risk_max=1_500.0)
    res = check_position_eligibility(pos, RiskConfig(risk_per_trade_max=1_500.0), context=ctx)
    assert res.max_loss_incl_costs > 1000
    assert res.status.value == "REJECTED"


def test_per_position_400_blocks_option():
    cand = TradeCandidate(
        mode=ExecutionMode.PAPER,
        kind=InstrumentKind.NIFTY_OPTION,
        instrument_key="OPT",
        trading_symbol="NIFTY24C",
        underlying="NIFTY",
        side=OrderSide.BUY,
        quantity=65,
        limit_price_inr=10.0,
        product=ProductType.DELIVERY,
        entry_cost_inr=50.0,
        exit_cost_reserve_inr=20.0,
        quote=QuoteSnapshot(99.0, 99.5, 500, 500, "OPT", datetime.now(timezone.utc)),
        lot_size=65,
    )
    res = evaluate_entry(cand, _ctx())
    assert not res.allowed
    assert "No size fits" in " ".join(res.reasons) or "exceeds" in " ".join(res.reasons)


def test_paper_fill_and_restart_equity(tmp_path: Path):
    db = tmp_path / "paper.db"
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    cand = _stock_candidate()
    out = submit_paper_entry(ledger, cand, slippage_pct=0.0)
    assert out.filled_qty == 10
    eq = ledger.equity()
    assert eq < 20_000.0
    ledger2 = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    assert ledger2.cash_balance() == ledger.cash_balance()


def test_preview_single_use():
    cand = _stock_candidate()
    t = build_preview(cand, _ctx(), slippage_pct=0.0)
    ok, _ = confirm_preview(t, _ctx(), slippage_pct=0.0)
    assert ok
    ok2, msg = confirm_preview(t, _ctx(), slippage_pct=0.0)
    assert not ok2
    assert "already used" in msg


def test_confirm_requires_context():
    t = build_preview(_stock_candidate(), _ctx(), slippage_pct=0.0)
    ok, msg = confirm_preview(t, None, slippage_pct=0.0)
    assert not ok
    assert "context" in msg.lower()


def test_reduce_only_buy_rejected():
    cand = _stock_candidate()
    res = evaluate_entry(cand, None, for_reduce_only=True)
    assert not res.allowed


def test_negative_reserves_rejected():
    cand = _stock_candidate()
    res = evaluate_entry(cand, _ctx(reserved_cash_inr=-1.0))
    assert not res.allowed


def test_negative_costs_rejected():
    cand = _stock_candidate(entry_cost_inr=-10.0)
    res = evaluate_entry(cand, _ctx())
    assert not res.allowed


def test_quote_key_mismatch_rejected():
    quote = QuoteSnapshot(99.0, 99.5, 10, 10, "OTHER", datetime.now(timezone.utc))
    cand = _stock_candidate(quote=quote)
    res = evaluate_entry(cand, _ctx())
    assert not res.allowed


def test_ticket_identity_ignores_quote_timestamp():
    ts1 = datetime.now(timezone.utc)
    ts2 = ts1.replace(microsecond=ts1.microsecond)  # same second ok
    from datetime import timedelta

    q1 = QuoteSnapshot(99.0, 99.5, 10, 10, "K", ts1)
    q2 = QuoteSnapshot(99.0, 99.5, 10, 10, "K", ts1 + timedelta(seconds=5))
    c1 = _stock_candidate(quote=q1)
    c2 = _stock_candidate(quote=q2)
    assert c1.ticket_identity() == c2.ticket_identity()


def test_partial_fill_replay_idempotent(tmp_path: Path):
    db = tmp_path / "paper.db"
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    cand = _stock_candidate(quantity=10)
    ledger.create_reservation(cand, "ord-1", 120.0)
    eid = "evt-partial-2"
    ledger.apply_paper_fill("ord-1", fill_qty=2, fill_price=99.5, fees=20.0, fill_event_id=eid)
    ledger.apply_paper_fill("ord-1", fill_qty=2, fill_price=99.5, fees=20.0, fill_event_id=eid)
    assert ledger.position_quantity("K") == 2


def test_two_distinct_partials_accumulate(tmp_path: Path):
    db = tmp_path / "paper.db"
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    cand = _stock_candidate(quantity=10)
    ledger.create_reservation(cand, "ord-2", 120.0)
    ledger.apply_paper_fill("ord-2", fill_qty=2, fill_price=99.5, fees=20.0, fill_event_id="e2a")
    ledger.apply_paper_fill("ord-2", fill_qty=3, fill_price=99.6, fees=20.0, fill_event_id="e2b")
    assert ledger.position_quantity("K") == 5


def test_overfill_rejected_unchanged(tmp_path: Path):
    db = tmp_path / "paper.db"
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    cand = _stock_candidate(quantity=10)
    ledger.create_reservation(cand, "ord-3", 120.0)
    ledger.apply_paper_fill("ord-3", fill_qty=2, fill_price=99.5, fees=20.0, fill_event_id="e3a")
    cash = ledger.cash_balance()
    with pytest.raises(ValueError, match="Overfill"):
        ledger.apply_paper_fill("ord-3", fill_qty=20, fill_price=99.5, fees=20.0, fill_event_id="e3b")
    assert ledger.position_quantity("K") == 2
    assert ledger.cash_balance() == cash


def test_partial_fill_survives_restart(tmp_path: Path):
    db = tmp_path / "paper.db"
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    cand = _stock_candidate(quantity=10)
    ledger.create_reservation(cand, "ord-4", 120.0)
    eid = "evt-restart-2"
    ledger.apply_paper_fill("ord-4", fill_qty=2, fill_price=99.5, fees=20.0, fill_event_id=eid)
    ledger2 = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    ledger2.apply_paper_fill("ord-4", fill_qty=2, fill_price=99.5, fees=20.0, fill_event_id=eid)
    assert ledger2.position_quantity("K") == 2


def test_live_adapter_guard_blocks():
    class T:
        def post(self, url, *, body, headers):
            raise AssertionError("no network")

    with pytest.raises(RuntimeError):
        LiveOrderAdapter(T()).place_limit(_stock_candidate(mode=ExecutionMode.LIVE))


def test_live_guard_env():
    assert live_mutations_forbidden()
    with pytest.raises(RuntimeError):
        assert_live_mutation_allowed()


def test_execution_gate_rejects_understated_planned_risk():
    cand = _stock_candidate(planned_risk_inr=1.0, quantity=10, limit_price_inr=100.0, stop_reference_inr=60.0)
    res = evaluate_entry(cand, _ctx())
    assert res.planned_risk_inr > 400
    assert not res.allowed


def test_execution_gate_rejects_nan_available_cash():
    cand = _stock_candidate()
    ctx = _ctx(available_strategy_cash_inr=float("nan"))
    res = evaluate_entry(cand, ctx)
    assert not res.allowed
    assert any("Non-finite" in r for r in res.reasons)


def test_execution_gate_rejects_uncovered_option_sell():
    cand = _stock_candidate(
        kind=InstrumentKind.NIFTY_OPTION,
        side=OrderSide.SELL,
        stop_reference_inr=None,
        lot_size=65,
        quantity=65,
    )
    res = evaluate_entry(cand, _ctx())
    assert not res.allowed


def test_paper_buy_does_not_fill_above_limit(tmp_path: Path):
    db = tmp_path / "paper.db"
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    quote = QuoteSnapshot(98.0, 100.0, 100, 100, "K", datetime.now(timezone.utc))
    cand = _stock_candidate(limit_price_inr=99.0, quote=quote)
    out = submit_paper_entry(ledger, cand, slippage_pct=0.0)
    assert out.filled_qty == 0
    assert ledger.reserved_cash() > 0


def test_partial_fill_keeps_remainder_reservation(tmp_path: Path):
    db = tmp_path / "paper.db"
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    quote = QuoteSnapshot(99.0, 99.5, 100, 2, "K", datetime.now(timezone.utc))
    cand = _stock_candidate(limit_price_inr=100.0, quantity=10, quote=quote)
    out = submit_paper_entry(ledger, cand, slippage_pct=0.0)
    assert out.filled_qty == 2
    assert ledger.reserved_cash() > 0
    assert ledger.reserved_risk() > 0


def test_fill_replay_idempotent(tmp_path: Path):
    db = tmp_path / "paper.db"
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    cand = _stock_candidate(quantity=10)
    ctx = ledger.portfolio_context()
    gate = evaluate_entry(cand, ctx)
    local_id = "test-local"
    ledger.create_reservation(cand, local_id, gate.planned_risk_inr)
    eid = "evt-full"
    ledger.apply_paper_fill(local_id, fill_qty=10, fill_price=99.5, fees=20.0, fill_event_id=eid)
    ledger.apply_paper_fill(local_id, fill_qty=10, fill_price=99.5, fees=20.0, fill_event_id=eid)
    with ledger._conn() as conn:
        n = conn.execute("SELECT COUNT(*) FROM fills WHERE local_order_id=?", (local_id,)).fetchone()[0]
    assert n == 1


def test_stale_quote_blocks_preview_and_confirm():
    stale_at = datetime.now(timezone.utc) - timedelta(hours=1)
    quote = QuoteSnapshot(99.0, 99.5, 10, 10, "K", stale_at, source="manual_ticket_input")
    cand = _stock_candidate(quote=quote)
    direct = evaluate_entry(cand, _ctx())
    assert not direct.allowed
    ticket = build_preview(cand, _ctx(), slippage_pct=0.0)
    assert not ticket.gate.allowed
    assert ticket.candidate.quote.evaluated_at == stale_at


def test_resulting_position_risk_blocks_second_entry(tmp_path: Path):
    db = tmp_path / "paper.db"
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    cand = _risk300_candidate()
    assert resolved_candidate_risk(cand) == pytest.approx(300.0, rel=0.01)
    out = submit_paper_entry(ledger, cand, slippage_pct=0.0)
    assert out.filled_qty == 10
    ctx = ledger.portfolio_context()
    assert dict(ctx.open_risk_by_instrument).get("K", 0) == pytest.approx(300.0, rel=0.01)
    res = evaluate_entry(cand, ctx)
    assert not res.allowed
    assert any("Resulting instrument risk" in r for r in res.reasons)


def test_negative_fill_price_leaves_ledger_unchanged(tmp_path: Path):
    db = tmp_path / "paper.db"
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    cand = _stock_candidate(quantity=2)
    ledger.create_reservation(cand, "ord-neg", resolved_candidate_risk(cand) or 100.0)
    cash0 = ledger.cash_balance()
    pos0 = ledger.position_quantity("K")
    with pytest.raises(ValueError):
        ledger.apply_paper_fill(
            "ord-neg", fill_qty=2, fill_price=-10.0, fees=0.0, fill_event_id="neg-evt"
        )
    assert ledger.cash_balance() == cash0
    assert ledger.position_quantity("K") == pos0


def test_fill_event_id_required(tmp_path: Path):
    db = tmp_path / "paper.db"
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    cand = _stock_candidate(quantity=2)
    ledger.create_reservation(cand, "ord-req", 100.0)
    with pytest.raises(ValueError, match="fill_event_id"):
        ledger.apply_paper_fill("ord-req", fill_qty=1, fill_price=99.5, fees=0.0, fill_event_id="")


def test_conflicting_fill_event_id_raises(tmp_path: Path):
    db = tmp_path / "paper.db"
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    cand = _stock_candidate(quantity=10)
    ledger.create_reservation(cand, "ord-c", 100.0)
    ledger.apply_paper_fill("ord-c", fill_qty=2, fill_price=99.5, fees=0.0, fill_event_id="same-id")
    with pytest.raises(ValueError, match="Conflicting"):
        ledger.apply_paper_fill("ord-c", fill_qty=3, fill_price=99.5, fees=0.0, fill_event_id="same-id")


def test_conflicting_fill_event_fees_raises_unchanged(tmp_path: Path):
    db = tmp_path / "paper.db"
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    cand = _stock_candidate(quantity=4)
    ledger.create_reservation(cand, "ord-fee", 100.0)
    ledger.apply_paper_fill("ord-fee", fill_qty=2, fill_price=99.5, fees=20.0, fill_event_id="fee-id")
    cash = ledger.cash_balance()
    pos = ledger.position_quantity("K")
    with pytest.raises(ValueError, match="Conflicting"):
        ledger.apply_paper_fill("ord-fee", fill_qty=2, fill_price=99.5, fees=200.0, fill_event_id="fee-id")
    assert ledger.cash_balance() == cash
    assert ledger.position_quantity("K") == pos


def _risk350_candidate(instrument_key: str, underlying: str = "BANK") -> TradeCandidate:
    return _stock_candidate(
        instrument_key=instrument_key,
        underlying=underlying,
        limit_price_inr=100.0,
        stop_reference_inr=70.0,
        entry_cost_inr=30.0,
        exit_cost_reserve_inr=20.0,
        quantity=10,
        quote=QuoteSnapshot(99.0, 99.5, 500, 500, instrument_key, datetime.now(timezone.utc)),
    )


def test_underlying_cap_blocks_third_pending_350(tmp_path: Path):
    db = tmp_path / "paper.db"
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    for idx, key in enumerate(("K1", "K2", "K3")):
        cand = _risk350_candidate(key)
        assert resolved_candidate_risk(cand) == pytest.approx(350.0, rel=0.01)
        if idx < 2:
            ledger.create_reservation(cand, f"ord-{idx}", 350.0)
        else:
            with pytest.raises(ValueError):
                ledger.create_reservation(cand, f"ord-{idx}", 350.0)
    ctx = ledger.portfolio_context()
    assert dict(ctx.pending_buy_risk_by_underlying).get("BANK", 0) == pytest.approx(700.0, rel=0.01)


def test_cancel_then_fourth_reservation_allowed(tmp_path: Path):
    db = tmp_path / "paper.db"
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    ledger.create_reservation(_risk350_candidate("K1"), "o1", 350.0)
    ledger.create_reservation(_risk350_candidate("K2"), "o2", 350.0)
    with pytest.raises(ValueError):
        ledger.create_reservation(_risk350_candidate("K3"), "o3", 350.0)
    ledger.cancel_paper_remainder("o1")
    ledger.create_reservation(_risk350_candidate("K3"), "o3", 350.0)


def test_cancel_unfilled_releases_reservation(tmp_path: Path):
    db = tmp_path / "paper.db"
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    quote = QuoteSnapshot(98.0, 100.0, 100, 100, "K", datetime.now(timezone.utc))
    cand = _stock_candidate(limit_price_inr=99.0, quote=quote)
    out = submit_paper_entry(ledger, cand, slippage_pct=0.0)
    assert out.filled_qty == 0
    assert ledger.reserved_cash() > 0
    cash = ledger.cash_balance()
    ledger.cancel_paper_remainder(out.local_id)
    assert ledger.reserved_cash() == 0.0
    assert ledger.cash_balance() == cash
    ledger.cancel_paper_remainder(out.local_id)
    assert ledger.reserved_cash() == 0.0


def test_partial_cancel_preserves_fill(tmp_path: Path):
    db = tmp_path / "paper.db"
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    cand = _stock_candidate(quantity=10)
    ledger.create_reservation(cand, "pc", 120.0)
    ledger.apply_paper_fill("pc", fill_qty=2, fill_price=99.5, fees=20.0, fill_event_id="pf")
    cash = ledger.cash_balance()
    pos = ledger.position_quantity("K")
    ledger.cancel_paper_remainder("pc")
    assert ledger.position_quantity("K") == pos
    assert ledger.cash_balance() == cash
    assert ledger.reserved_cash() == 0.0


def test_fill_after_cancel_rejected(tmp_path: Path):
    db = tmp_path / "paper.db"
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    cand = _stock_candidate(quantity=10)
    ledger.create_reservation(cand, "ca", 120.0)
    ledger.cancel_paper_remainder("ca")
    with pytest.raises(ValueError, match="cancelled"):
        ledger.apply_paper_fill("ca", fill_qty=2, fill_price=99.5, fees=0.0, fill_event_id="late")


def test_replay_after_intervening_fill_is_harmless(tmp_path: Path):
    db = tmp_path / "paper.db"
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    cand = _stock_candidate(quantity=10)
    ledger.create_reservation(cand, "ord-int", 120.0)
    ledger.apply_paper_fill("ord-int", fill_qty=2, fill_price=99.5, fees=0.0, fill_event_id="first")
    ledger.apply_paper_fill("ord-int", fill_qty=2, fill_price=99.5, fees=0.0, fill_event_id="second")
    assert ledger.position_quantity("K") == 4
    ledger.apply_paper_fill("ord-int", fill_qty=2, fill_price=99.5, fees=0.0, fill_event_id="first")
    assert ledger.position_quantity("K") == 4


def test_distinct_events_same_price_qty_both_book(tmp_path: Path):
    db = tmp_path / "paper.db"
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    cand = _stock_candidate(quantity=10)
    ledger.create_reservation(cand, "ord-duppx", 100.0)
    ledger.apply_paper_fill("ord-duppx", fill_qty=2, fill_price=99.5, fees=0.0, fill_event_id="evt-a")
    ledger.apply_paper_fill("ord-duppx", fill_qty=2, fill_price=99.5, fees=0.0, fill_event_id="evt-b")
    assert ledger.position_quantity("K") == 4


def test_pending_reservation_blocks_second_risk300(tmp_path: Path):
    db = tmp_path / "paper.db"
    ledger = ExecutionLedger(db, mode=ExecutionMode.PAPER)
    cand = _risk300_candidate()
    ledger.create_reservation(cand, "pending-a", resolved_candidate_risk(cand) or 300.0)
    res = evaluate_entry(cand, ledger.portfolio_context())
    assert not res.allowed
