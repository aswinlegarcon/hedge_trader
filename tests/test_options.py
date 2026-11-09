import math

import numpy as np
import pytest

from nifty_lab.options import (
    DEFAULT_COSTS,
    CostSchedule,
    OptionLeg,
    OptionType,
    Position,
    Quote,
    Side,
    bear_call_spread,
    bs_greeks,
    bs_price,
    bull_put_spread,
    covered_call,
    implied_volatility,
    iron_condor,
    option_order_costs,
    protective_put,
    theoretical_quote_book,
)

ZERO = CostSchedule(brokerage_per_order=0, stt_sell_pct=0, stt_exercise_pct=0, exchange_txn_pct=0, sebi_fee_pct=0, stamp_duty_buy_pct=0, ipft_pct=0, gst_pct=0)


# --- Black-Scholes ---------------------------------------------------------
def test_put_call_parity():
    S, K, T, r, q, sig = 24000, 24000, 30 / 365, 0.065, 0.012, 0.14
    c = bs_price(S, K, T, sig, "CE", r, q)
    p = bs_price(S, K, T, sig, "PE", r, q)
    assert c - p == pytest.approx(S * math.exp(-q * T) - K * math.exp(-r * T), abs=1e-6)


def test_bs_known_value():
    # Hull textbook: S=42, K=40, r=10%, sigma=20%, T=0.5 -> call 4.76, put 0.81
    assert bs_price(42, 40, 0.5, 0.2, "CE", 0.10, 0.0) == pytest.approx(4.76, abs=0.01)
    assert bs_price(42, 40, 0.5, 0.2, "PE", 0.10, 0.0) == pytest.approx(0.81, abs=0.01)


def test_greeks_ranges():
    g = bs_greeks(24000, 24000, 30 / 365, 0.14, "CE")
    assert 0.4 < g.delta < 0.6
    assert g.gamma > 0
    assert g.theta_per_day < 0
    assert g.vega_per_pct > 0
    gp = bs_greeks(24000, 24000, 30 / 365, 0.14, "PE")
    assert -0.6 < gp.delta < -0.4
    assert gp.gamma == pytest.approx(g.gamma)


def test_implied_vol_roundtrip_and_failure():
    price = bs_price(24000, 23500, 25 / 365, 0.16, "PE")
    iv = implied_volatility(price, 24000, 23500, 25 / 365, "PE")
    assert iv == pytest.approx(0.16, abs=1e-5)
    assert implied_volatility(0.0, 24000, 23500, 25 / 365, "PE") is None  # zero price
    assert implied_volatility(50.0, 24000, 23500, 0.0, "PE") is None  # expired
    assert implied_volatility(30_000.0, 24000, 23500, 25 / 365, "CE") is None  # above upper bound S


def test_iv_rejects_price_below_intrinsic():
    assert implied_volatility(100.0, 24000, 23000, 25 / 365, "CE") is None  # intrinsic ≈ 1000


# --- Costs -----------------------------------------------------------------
def test_option_costs_sell_includes_stt_buy_includes_stamp():
    sell = option_order_costs(100.0, 65, "SELL")
    buy = option_order_costs(100.0, 65, "BUY")
    turnover = 6500.0
    assert sell.stt == pytest.approx(turnover * 0.0015)
    assert buy.stt == 0
    assert buy.stamp_duty == pytest.approx(turnover * 0.00003)
    assert sell.stamp_duty == 0
    assert sell.brokerage == 20
    assert sell.gst == pytest.approx((20 + sell.exchange_txn + sell.sebi_fee) * 0.18, rel=1e-6)
    assert sell.total > buy.total
    with pytest.raises(ValueError):
        option_order_costs(100.0, 65, "HOLD")


# --- Payoff ----------------------------------------------------------------
def book(spot=24000.0):
    strikes = [spot + i * 50 for i in range(-10, 11)]
    b, ivs = theoretical_quote_book(spot, strikes, 30 / 365, 0.14, 0.065, 0.012)
    return b, ivs


def test_bull_put_spread_metrics_no_costs():
    b = {("PE", 23800.0): Quote(90, 92), ("PE", 23700.0): Quote(60, 62)}
    pos = bull_put_spread("NIFTY", "2026-11-24", 23800, 23700, b, lots=1, lot_size=65)
    credit_per_unit = 90 - 62  # sell at bid, buy at ask
    assert pos.net_premium == pytest.approx(credit_per_unit * 65)
    assert pos.is_credit
    assert pos.max_profit(include_costs=False) == pytest.approx(credit_per_unit * 65)
    assert pos.max_loss(include_costs=False) == pytest.approx((100 - credit_per_unit) * 65)
    assert pos.breakevens(include_costs=False) == [pytest.approx(23800 - credit_per_unit)]
    assert pos.max_loss(include_costs=True) > pos.max_loss(include_costs=False)
    assert pos.max_profit(include_costs=True) < pos.max_profit(include_costs=False)


def test_bear_call_spread_mirror():
    b = {("CE", 24200.0): Quote(90, 92), ("CE", 24300.0): Quote(60, 62)}
    pos = bear_call_spread("NIFTY", "2026-11-24", 24200, 24300, b, 1, 65)
    assert pos.max_profit(include_costs=False) == pytest.approx(28 * 65)
    assert pos.max_loss(include_costs=False) == pytest.approx(72 * 65)
    assert pos.breakevens(include_costs=False) == [pytest.approx(24228)]
    with pytest.raises(ValueError):
        bear_call_spread("NIFTY", "x", 24300, 24200, b, 1, 65)


def test_iron_condor_only_one_side_loses():
    b, _ = book()
    pos = iron_condor("NIFTY", "x", 23700, 23600, 24300, 24400, b, 1, 65)
    credit = pos.net_premium
    assert credit > 0
    assert pos.max_loss(include_costs=False) == pytest.approx(100 * 65 - credit)
    bes = pos.breakevens(include_costs=False)
    assert len(bes) == 2 and bes[0] < 23700 and bes[1] > 24300


def test_missing_quote_is_insufficient_data():
    with pytest.raises(KeyError, match="INSUFFICIENT DATA"):
        bull_put_spread("NIFTY", "x", 23800, 23700, {}, 1, 65)


def test_covered_call_unbounded_downside_bounded_at_zero_and_protective_put():
    b, _ = book()
    cc = covered_call("NIFTY", "x", 24000, 65, 24200, b, 1, 65)
    assert math.isfinite(cc.max_loss(include_costs=False))
    assert cc.max_loss(include_costs=False) > 24000 * 65 * 0.9  # nearly the whole notional
    assert math.isfinite(cc.max_profit(include_costs=False))
    pp = protective_put("NIFTY", "x", 24000, 65, 23800, b, 1, 65)
    assert pp.max_loss(include_costs=False) == pytest.approx((24000 - 23800 + b[("PE", 23800.0)].ask) * 65)
    assert math.isinf(pp.max_profit(include_costs=False))


def test_naked_short_call_is_unbounded():
    leg = OptionLeg(OptionType.CE, 24200, Side.SHORT, Quote(90, 92), 1, 65)
    pos = Position("naked", "NIFTY", "x", [leg])
    assert math.isinf(pos.max_loss())
    assert pos.reward_to_risk() is None


def test_payoff_curve_consistent_with_kinks():
    b, ivs = book()
    pos = bull_put_spread("NIFTY", "x", 23800, 23700, b, 1, 65, ivs)
    xs, ys = pos.payoff_curve(24000, width_pct=0.1, include_costs=False)
    assert ys.max() == pytest.approx(pos.max_profit(include_costs=False), abs=1e-6)
    assert -ys.min() == pytest.approx(pos.max_loss(include_costs=False), abs=1e-6)
    g = pos.net_greeks(24000, 30 / 365, 0.065, 0.012)
    assert g is not None and g["delta"] > 0 and g["theta_per_day"] > 0  # short put spread: positive delta, positive theta


def test_quote_validation():
    with pytest.raises(ValueError):
        Quote(10, 5)
    assert Quote(10, 12).mid == 11
    assert Quote(0, 0).spread_pct == float("inf")
