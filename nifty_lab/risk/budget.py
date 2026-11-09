"""Position sizing and eligibility checks against the configured risk budget.

Rules (deterministic, no AI involvement):
1. A position is eligible only if its *maximum contractual loss including
   estimated costs* is within [risk_per_trade_min, risk_per_trade_max]
   (below min is allowed but flagged as under-utilised).
2. Unbounded-risk positions are never eligible.
3. Portfolio-level: open risk + new risk <= max_portfolio_risk_pct x capital,
   and open risk + new risk must not push the account past max drawdown.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..config import RiskConfig
from ..options.payoff import Position


@dataclass
class EligibilityResult:
    eligible: bool
    max_loss_incl_costs: float
    budget_min: float
    budget_max: float
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def budget_utilisation(self) -> float | None:
        if math.isinf(self.max_loss_incl_costs) or self.budget_max == 0:
            return None
        return self.max_loss_incl_costs / self.budget_max


def check_position_eligibility(position: Position, risk: RiskConfig, open_risk_inr: float = 0.0, realised_drawdown_inr: float = 0.0) -> EligibilityResult:
    max_loss = position.max_loss(include_costs=True)
    res = EligibilityResult(eligible=True, max_loss_incl_costs=max_loss, budget_min=risk.risk_per_trade_min, budget_max=risk.risk_per_trade_max)

    if math.isinf(max_loss):
        res.eligible = False
        res.reasons.append("Maximum loss is UNBOUNDED (naked short exposure). Not permitted.")
        return res

    if max_loss > risk.risk_per_trade_max:
        res.eligible = False
        res.reasons.append(f"Max loss incl. costs ₹{max_loss:,.0f} exceeds per-trade budget ₹{risk.risk_per_trade_max:,.0f}.")
    elif max_loss < risk.risk_per_trade_min:
        res.warnings.append(f"Max loss ₹{max_loss:,.0f} is below the minimum research size ₹{risk.risk_per_trade_min:,.0f}; position may be too small to matter after costs.")

    portfolio_cap = risk.max_portfolio_risk_pct * risk.capital
    if open_risk_inr + max_loss > portfolio_cap:
        res.eligible = False
        res.reasons.append(f"Open risk ₹{open_risk_inr:,.0f} + new ₹{max_loss:,.0f} exceeds portfolio risk cap ₹{portfolio_cap:,.0f}.")

    remaining_dd = risk.max_drawdown - realised_drawdown_inr
    if open_risk_inr + max_loss > remaining_dd:
        res.eligible = False
        res.reasons.append(f"Worst case would breach remaining drawdown allowance ₹{remaining_dd:,.0f}.")

    mp = position.max_profit(include_costs=True)
    if not math.isinf(mp) and mp <= 0:
        res.eligible = False
        res.reasons.append("Max profit after costs is <= 0; the trade cannot make money.")
    rr = position.reward_to_risk(include_costs=True)
    if rr is not None and rr < 0.20:
        res.warnings.append(f"Reward:risk {rr:.2f} is low (<0.20). Credit spreads this far OTM need a very high win rate to break even.")

    for w in position.liquidity_warnings():
        res.warnings.append("Liquidity: " + w)
    return res


def max_lots_for_budget(per_lot_max_loss: float, risk: RiskConfig) -> int:
    """How many lots keep total max loss within the per-trade budget (floor, min 0)."""
    if per_lot_max_loss <= 0 or math.isinf(per_lot_max_loss):
        return 0
    return int(risk.risk_per_trade_max // per_lot_max_loss)
