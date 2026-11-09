"""Portfolio exposure, drawdown and concentration tracking (paper positions)."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ..config import RiskConfig


@dataclass
class OpenPosition:
    position_id: str
    underlying: str
    strategy: str
    max_loss_inr: float
    expiry: str
    opened_at: str
    mark_pnl_inr: float = 0.0


@dataclass
class PortfolioSnapshot:
    capital: float
    open_positions: list[OpenPosition]
    realised_pnl_inr: float
    peak_equity_inr: float
    checks: list[str] = field(default_factory=list)

    @property
    def open_risk_inr(self) -> float:
        return float(sum(p.max_loss_inr for p in self.open_positions))

    @property
    def unrealised_pnl_inr(self) -> float:
        return float(sum(p.mark_pnl_inr for p in self.open_positions))

    @property
    def equity_inr(self) -> float:
        return self.capital + self.realised_pnl_inr + self.unrealised_pnl_inr

    @property
    def drawdown_inr(self) -> float:
        return max(0.0, self.peak_equity_inr - self.equity_inr)

    @property
    def worst_case_equity_inr(self) -> float:
        """Equity if every open position hits its maximum loss."""
        return self.capital + self.realised_pnl_inr - self.open_risk_inr

    def exposure_by_underlying(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for p in self.open_positions:
            out[p.underlying] = out.get(p.underlying, 0.0) + p.max_loss_inr
        return out


def evaluate_portfolio(snapshot: PortfolioSnapshot, risk: RiskConfig) -> list[str]:
    """Return a list of human-readable breaches/warnings. Empty = all clear."""
    issues: list[str] = []
    if snapshot.drawdown_inr >= risk.max_drawdown:
        issues.append(f"BREACH: drawdown ₹{snapshot.drawdown_inr:,.0f} >= limit ₹{risk.max_drawdown:,.0f}. Stop opening new positions.")
    elif snapshot.drawdown_inr >= 0.7 * risk.max_drawdown:
        issues.append(f"WARNING: drawdown ₹{snapshot.drawdown_inr:,.0f} is at {snapshot.drawdown_inr / risk.max_drawdown:.0%} of the limit.")
    cap = risk.max_portfolio_risk_pct * risk.capital
    if snapshot.open_risk_inr > cap:
        issues.append(f"BREACH: open risk ₹{snapshot.open_risk_inr:,.0f} > portfolio cap ₹{cap:,.0f}.")
    if len(snapshot.open_positions) > risk.max_open_positions:
        issues.append(f"BREACH: {len(snapshot.open_positions)} open positions > max {risk.max_open_positions}.")
    conc_cap = risk.max_single_underlying_pct * risk.capital
    for und, amt in snapshot.exposure_by_underlying().items():
        if amt > conc_cap:
            issues.append(f"CONCENTRATION: ₹{amt:,.0f} at risk in {und} > cap ₹{conc_cap:,.0f}.")
    worst = snapshot.worst_case_equity_inr
    if snapshot.peak_equity_inr - worst > risk.max_drawdown:
        issues.append(f"WARNING: if all open positions hit max loss, drawdown would be ₹{snapshot.peak_equity_inr - worst:,.0f} (> limit).")
    # Correlation note: index strategies on NIFTY and BANKNIFTY are highly correlated.
    unds = {p.underlying for p in snapshot.open_positions}
    if {"NIFTY", "BANKNIFTY"} <= unds:
        issues.append("CORRELATION: NIFTY and BANKNIFTY positions are strongly correlated; treat combined risk as one bet.")
    return issues


def drawdown_series(equity: pd.Series) -> pd.DataFrame:
    peak = equity.cummax()
    dd = equity - peak
    return pd.DataFrame({"equity": equity, "peak": peak, "drawdown": dd, "drawdown_pct": dd / peak})
