import pytest

from nifty_lab.config import RiskConfig
from nifty_lab.options import Quote, bull_put_spread
from nifty_lab.risk import OpenPosition, PortfolioSnapshot, check_position_eligibility, evaluate_portfolio, max_lots_for_budget


def spread(width_credit_bid=90, long_ask=62, lots=1, short=23800, long=23700):
    b = {("PE", float(short)): Quote(width_credit_bid, width_credit_bid + 2), ("PE", float(long)): Quote(long_ask - 2, long_ask)}
    return bull_put_spread("NIFTY", "x", short, long, b, lots, 65)


def test_risk_config_validation():
    with pytest.raises(ValueError):
        RiskConfig(capital=0)
    with pytest.raises(ValueError):
        RiskConfig(max_drawdown=200_000)
    with pytest.raises(ValueError):
        RiskConfig(risk_per_trade_min=3000, risk_per_trade_max=2000)
    with pytest.raises(ValueError):
        RiskConfig(risk_per_trade_max=20_000)
    assert RiskConfig().max_drawdown_pct == pytest.approx(0.10)


def test_eligibility_rejects_over_budget_and_accepts_within():
    risk = RiskConfig()
    # 100-pt wide spread, 28 credit -> 72*65 = 4680 + costs > 2000
    res = check_position_eligibility(spread(), risk)
    assert not res.eligible
    assert any("exceeds per-trade budget" in r for r in res.reasons)
    # 50-pt wide, 28 credit -> 22*65 = 1430 + costs ~ within 1000-2000
    res2 = check_position_eligibility(spread(long=23750), risk)
    assert res2.eligible, res2.reasons
    assert 1000 <= res2.max_loss_incl_costs <= 2000


def test_eligibility_uses_costs():
    risk = RiskConfig(risk_per_trade_min=1000, risk_per_trade_max=1430)
    pos = spread(long=23750)  # max loss before costs exactly 1430
    assert pos.max_loss(include_costs=False) == pytest.approx(1430)
    res = check_position_eligibility(pos, risk)
    assert not res.eligible  # costs push it over


def test_portfolio_cap_and_drawdown_block():
    risk = RiskConfig()
    pos = spread(long=23750)
    res = check_position_eligibility(pos, risk, open_risk_inr=5_500)  # cap is 6000
    assert not res.eligible
    res = check_position_eligibility(pos, risk, open_risk_inr=0, realised_drawdown_inr=9_000)
    assert not res.eligible
    assert any("drawdown" in r for r in res.reasons)


def test_unbounded_never_eligible():
    from nifty_lab.options import OptionLeg, OptionType, Position, Side
    pos = Position("naked", "NIFTY", "x", [OptionLeg(OptionType.CE, 24200, Side.SHORT, Quote(90, 92), 1, 65)])
    res = check_position_eligibility(pos, RiskConfig())
    assert not res.eligible and "UNBOUNDED" in res.reasons[0]


def test_max_lots_for_budget():
    risk = RiskConfig()
    assert max_lots_for_budget(900, risk) == 2
    assert max_lots_for_budget(2001, risk) == 0
    assert max_lots_for_budget(float("inf"), risk) == 0


def test_portfolio_evaluation_rules():
    risk = RiskConfig()
    snap = PortfolioSnapshot(
        capital=100_000,
        open_positions=[
            OpenPosition("1", "NIFTY", "bps", 1900, "x", "d"),
            OpenPosition("2", "NIFTY", "bps", 1900, "x", "d"),
            OpenPosition("3", "BANKNIFTY", "bcs", 1900, "x", "d"),
            OpenPosition("4", "NIFTY", "bps", 1900, "x", "d"),
        ],
        realised_pnl_inr=-7_500,
        peak_equity_inr=100_000,
    )
    issues = evaluate_portfolio(snap, risk)
    text = "\n".join(issues)
    assert "open risk" in text and "BREACH" in text
    assert "open positions > max" in text
    assert "CONCENTRATION" in text
    assert "CORRELATION" in text
    assert "WARNING: drawdown" in text
    assert snap.drawdown_inr == pytest.approx(7_500)
    assert snap.worst_case_equity_inr == pytest.approx(100_000 - 7_500 - 7_600)


def test_portfolio_clean():
    snap = PortfolioSnapshot(100_000, [OpenPosition("1", "NIFTY", "bps", 1500, "x", "d")], 0.0, 100_000)
    assert evaluate_portfolio(snap, RiskConfig()) == []
