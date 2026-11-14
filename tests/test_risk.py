import math
import tempfile
from pathlib import Path

import pytest

from nifty_lab.config import DEFAULT_CAPITAL_INR, DEFAULT_LOSS_CEILING_INR, RiskConfig, load_config
from nifty_lab.options import Quote, bull_put_spread
from nifty_lab.risk import (
    EligibilityStatus,
    OpenRiskLeg,
    PortfolioSnapshot,
    check_position_eligibility,
    evaluate_portfolio,
    independent_test_context,
    max_lots_for_budget,
    remaining_downside,
)
from nifty_lab.risk import OpenPosition


def spread(width_credit_bid=90, long_ask=62, lots=1, short=23800, long=23700):
    b = {("PE", float(short)): Quote(width_credit_bid, width_credit_bid + 2), ("PE", float(long)): Quote(long_ask - 2, long_ask)}
    return bull_put_spread("NIFTY", "x", short, long, b, lots, 65)


def legacy_risk() -> RiskConfig:
    """Explicit legacy-account fixture for options spread math — not the active Spec 03 profile."""
    return RiskConfig(capital=100_000, max_drawdown=10_000, risk_per_trade_max=2_000)


def legacy_context(**overrides):
    defaults = {
        "initial_capital": 100_000.0,
        "loss_ceiling": 10_000.0,
        "equity_inr": 100_000.0,
        "peak_equity_inr": 100_000.0,
        "per_position_risk_max": 2_000.0,
        "available_cash_inr": 100_000.0,
        "candidate_margin_required_inr": 0.0,
    }
    defaults.update(overrides)
    return independent_test_context(**defaults)


def test_risk_config_spec03_defaults():
    r = RiskConfig()
    assert r.capital == DEFAULT_CAPITAL_INR
    assert r.max_drawdown == DEFAULT_LOSS_CEILING_INR
    assert r.risk_per_trade_max is None
    assert r.max_drawdown_pct == pytest.approx(0.10)


def test_risk_config_validation():
    with pytest.raises(ValueError):
        RiskConfig(capital=0)
    with pytest.raises(ValueError):
        RiskConfig(max_drawdown=200_000)
    with pytest.raises(ValueError):
        RiskConfig(risk_per_trade_max=3_000)
    with pytest.raises(ValueError):
        RiskConfig(risk_per_trade_max=20_000)


def test_eligibility_without_context_is_insufficient():
    res = check_position_eligibility(spread(long=23750), legacy_risk())
    assert res.status == EligibilityStatus.INSUFFICIENT_DATA
    assert not res.eligible


def test_eligibility_rejects_over_budget_with_context():
    risk = legacy_risk()
    ctx = legacy_context()
    res = check_position_eligibility(spread(), risk, context=ctx)
    assert res.status == EligibilityStatus.REJECTED
    assert any("per-position ceiling" in r for r in res.reasons)


def test_eligibility_accepts_within_legacy_fixture():
    risk = legacy_risk()
    ctx = legacy_context()
    res = check_position_eligibility(spread(long=23750), risk, context=ctx)
    assert res.status == EligibilityStatus.ELIGIBLE, res.reasons


def test_eligibility_uses_costs():
    risk = RiskConfig(capital=100_000, max_drawdown=10_000, risk_per_trade_max=1_430)
    pos = spread(long=23750)
    assert pos.max_loss(include_costs=False) == pytest.approx(1430)
    ctx = legacy_context(per_position_risk_max=1_430)
    res = check_position_eligibility(pos, risk, context=ctx)
    assert res.status == EligibilityStatus.REJECTED


def test_portfolio_cap_blocks():
    risk = legacy_risk()
    pos = spread(long=23750)
    ctx = legacy_context(open_legs=(OpenRiskLeg("NIFTY", 5_500, 0.0),))
    res = check_position_eligibility(pos, risk, context=ctx)
    assert res.status == EligibilityStatus.REJECTED
    assert any("portfolio cap" in r for r in res.reasons)


def test_drawdown_blocks_via_context():
    risk = legacy_risk()
    pos = spread(long=23750)
    ctx = legacy_context(equity_inr=90_000, peak_equity_inr=100_000)
    res = check_position_eligibility(pos, risk, context=ctx)
    assert res.status == EligibilityStatus.REJECTED
    assert any("drawdown" in r.lower() for r in res.reasons)


def test_unbounded_never_eligible():
    from nifty_lab.options import OptionLeg, OptionType, Position, Side

    pos = Position("naked", "NIFTY", "x", [OptionLeg(OptionType.CE, 24200, Side.SHORT, Quote(90, 92), 1, 65)])
    ctx = legacy_context()
    res = check_position_eligibility(pos, RiskConfig(), context=ctx)
    assert res.status == EligibilityStatus.REJECTED and "UNBOUNDED" in res.reasons[0]


def test_max_lots_for_budget():
    risk = legacy_risk()
    assert max_lots_for_budget(900, risk) == 2
    assert max_lots_for_budget(2001, risk) == 0
    assert max_lots_for_budget(float("inf"), risk) == 0
    assert max_lots_for_budget(100, RiskConfig()) == 0


def test_remaining_downside_arithmetic():
    assert remaining_downside(1_000, -600) == pytest.approx(400)
    assert remaining_downside(1_000, 200) == pytest.approx(1_200)


def test_portfolio_evaluation_rules():
    risk = legacy_risk()
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


def test_portfolio_clean():
    snap = PortfolioSnapshot(100_000, [OpenPosition("1", "NIFTY", "bps", 1500, "x", "d")], 0.0, 100_000)
    assert evaluate_portfolio(snap, legacy_risk()) == []


def test_load_config_legacy_conflict_flag(monkeypatch):
    monkeypatch.setenv("NSL_CAPITAL_INR", "100000")
    cfg = load_config()
    assert cfg.legacy_env_conflict
    assert cfg.risk.capital == DEFAULT_CAPITAL_INR
