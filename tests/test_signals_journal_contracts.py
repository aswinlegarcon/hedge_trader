from datetime import date

import pandas as pd
import pytest

from nifty_lab.contracts import get_contract, monthly_expiry, next_monthly_expiries, round_to_strike, strike_ladder
from nifty_lab.data import generate_synthetic_nifty
from nifty_lab.indicators import compute_indicator_frame
from nifty_lab.journal import Journal, JournalEntry
from nifty_lab.signals import MIN_BARS, Regime, SignalType, evaluate, evaluate_from_ohlcv


def test_contract_specs_and_expiry():
    n = get_contract("nifty")
    assert n.lot_size == 65 and n.strike_interval == 50
    assert get_contract("BANKNIFTY").lot_size == 30
    # Nov 2026: last Tuesday is 24 Nov 2026
    assert monthly_expiry("NIFTY", 2026, 11) == date(2026, 11, 24)
    exps = next_monthly_expiries("NIFTY", date(2026, 11, 9), 3)
    assert exps[0] == date(2026, 11, 24) and all(e.weekday() == 1 for e in exps) and exps == sorted(exps)
    assert next_monthly_expiries("NIFTY", date(2026, 11, 24), 1)[0] > date(2026, 11, 24)
    with pytest.raises(KeyError):
        get_contract("SENSEX")


def test_strike_rounding():
    assert round_to_strike(24_037, "NIFTY") == 24_050
    assert round_to_strike(24_024, "NIFTY") == 24_000
    assert round_to_strike(51_049, "BANKNIFTY") == 51_000
    ladder = strike_ladder(24_010, "NIFTY", 2)
    assert ladder == [23_900, 23_950, 24_000, 24_050, 24_100]


def test_signal_insufficient_data():
    ds = generate_synthetic_nifty(seed=1)
    rep = evaluate_from_ohlcv(ds.df.iloc[: MIN_BARS - 10])
    assert rep.signal == SignalType.INSUFFICIENT_DATA
    assert rep.reasons_to_avoid


def test_signal_report_structure_and_no_lookahead():
    ds = generate_synthetic_nifty(seed=42)
    ind = compute_indicator_frame(ds.df)
    ts = ind.index[400]
    rep_a = evaluate(ind, as_of=ts)
    rep_b = evaluate(compute_indicator_frame(ds.df.loc[:ts]))  # recompute using only past data
    assert rep_a.signal == rep_b.signal
    assert rep_a.indicator_values["close"] == pytest.approx(rep_b.indicator_values["close"])
    assert rep_a.signal in set(SignalType)
    assert rep_a.regime in set(Regime)
    assert rep_a.conditions and rep_a.passed is not None
    assert len(rep_a.passed) + len(rep_a.failed) == len(rep_a.conditions)
    assert rep_a.strategy_candidates and rep_a.invalidation
    assert "VIX" in " ".join(rep_a.reasons_to_avoid)  # missing VIX is flagged


def test_signal_history_contains_variety():
    ds = generate_synthetic_nifty(seed=42)
    ind = compute_indicator_frame(ds.df)
    seen = {evaluate(ind, as_of=t).signal for t in ind.index[220::7]}
    assert SignalType.WAIT in seen
    assert len(seen) >= 2


def test_event_and_vix_warnings():
    ds = generate_synthetic_nifty(seed=42)
    ind = compute_indicator_frame(ds.df)
    rep = evaluate(ind, india_vix=25.0, event_risk_notes=["RBI MPC decision"])
    txt = " ".join(rep.reasons_to_avoid)
    assert "India VIX 25.0" in txt and "Event risk: RBI" in txt


def test_journal_roundtrip(tmp_path):
    j = Journal(tmp_path / "j.db")
    eid = j.add_entry(JournalEntry(trade_date="2026-11-09", instrument="NIFTY 2026-11-24", strategy="Bull Put Spread", max_risk_inr=1500, max_profit_inr=1800, lots=1, quantity=65))
    assert j.open_risk_inr() == 1500
    j.close_entry(eid, 900.0, "hit target", "", "took profit at 50%")
    assert j.open_risk_inr() == 0
    assert j.realised_pnl_inr() == 900
    with pytest.raises(ValueError):
        j.close_entry(eid, 1.0)
    eid2 = j.add_entry(JournalEntry(trade_date="2026-11-10", instrument="NIFTY", strategy="Bear Call", max_risk_inr=1200))
    j.close_entry(eid2, -1200.0)
    perf = j.performance_summary()
    assert perf["trades"] == 2 and perf["win_rate"] == 0.5
    assert perf["profit_factor"] == pytest.approx(900 / 1200)
    assert perf["expectancy_inr"] == pytest.approx(-150)
    with pytest.raises(ValueError):
        j.add_entry(JournalEntry(trade_date="x", instrument="y", strategy="z", is_paper=0))
    j.add_note("idea", "body", "tag")
    assert len(j.notes()) == 1
    j.log_signal("2026-11-09", "NIFTY", "WAIT", "NEUTRAL", {"a": 1}, "SYNTHETIC")
    assert len(j.signal_history()) == 1
