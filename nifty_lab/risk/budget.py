"""Position sizing and fail-closed funded-paper eligibility (Spec 03).

Theoretical payoff math may run without portfolio context. **Funded-paper qualification**
requires an explicit :class:`FundedPaperContext` — never default-zero drawdown or marks.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..config import RiskConfig
from ..options.payoff import Position
from .context import EligibilityStatus, FundedPaperContext


@dataclass
class EligibilityResult:
    status: EligibilityStatus
    max_loss_incl_costs: float
    budget_max: float | None
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def eligible(self) -> bool:
        return self.status == EligibilityStatus.ELIGIBLE

    @property
    def budget_utilisation(self) -> float | None:
        if self.budget_max is None or self.budget_max == 0 or math.isinf(self.max_loss_incl_costs):
            return None
        return self.max_loss_incl_costs / self.budget_max


def _reject(res: EligibilityResult, reason: str) -> EligibilityResult:
    res.status = EligibilityStatus.REJECTED
    res.reasons.append(reason)
    return res


def _insufficient(res: EligibilityResult, reason: str) -> EligibilityResult:
    if res.status != EligibilityStatus.REJECTED:
        res.status = EligibilityStatus.INSUFFICIENT_DATA
    res.reasons.append(reason)
    return res


def remaining_downside(max_loss: float, net_pnl: float) -> float:
    """B = max(0, R + P) on the same cost basis."""
    return max(0.0, max_loss + net_pnl)


def check_position_eligibility(
    position: Position,
    risk: RiskConfig,
    *,
    context: FundedPaperContext | None = None,
    open_risk_inr: float = 0.0,
    realised_drawdown_inr: float = 0.0,
) -> EligibilityResult:
    """Tri-state gate. Without ``context``, funded-paper qualification is INSUFFICIENT DATA.

    ``open_risk_inr`` and ``realised_drawdown_inr`` are ignored (legacy call sites).
    """
    del open_risk_inr, realised_drawdown_inr

    max_loss = position.max_loss(include_costs=True)
    res = EligibilityResult(
        status=EligibilityStatus.INSUFFICIENT_DATA,
        max_loss_incl_costs=max_loss,
        budget_max=risk.risk_per_trade_max,
    )

    if math.isinf(max_loss):
        return _reject(res, "Maximum loss is UNBOUNDED (naked short exposure). Not permitted.")

    if context is None:
        return _insufficient(
            res,
            "Funded-paper qualification requires explicit portfolio valuation context; "
            "reconciled equity/peak marks are not available in this build.",
        )

    if not context.profile_authorized:
        return _insufficient(res, "Revised research profile is not authorized due to legacy NSL_* conflict.")

    if not context.valuation_trusted:
        return _insufficient(res, "Valuation context is not marked trustworthy.")

    if context.has_unreconciled_legacy:
        return _insufficient(res, "Unreconciled legacy or manual open exposure blocks funded-paper qualification.")

    if context.equity_inr is None or context.peak_equity_inr is None:
        return _insufficient(res, "Equity and peak equity are required.")

    if not math.isfinite(context.equity_inr) or not math.isfinite(context.peak_equity_inr):
        return _insufficient(res, "Equity inputs must be finite.")

    declared = context.candidate_max_loss_inr
    if declared is not None:
        if not math.isfinite(declared) or declared < 0:
            return _insufficient(res, "Declared candidate max loss is invalid (must be finite and non-negative).")
        b_new = max(max_loss, declared)
    else:
        b_new = max_loss
    if not math.isfinite(b_new) or b_new < 0:
        return _insufficient(res, "Candidate max loss is not finite.")

    if context.per_position_risk_max is None and risk.risk_per_trade_max is None:
        return _insufficient(res, "Per-position risk ceiling is unconfirmed; cannot qualify funded-paper entries.")
    per_pos_cap = context.per_position_risk_max if context.per_position_risk_max is not None else risk.risk_per_trade_max
    if per_pos_cap is not None and b_new > per_pos_cap:
        return _reject(res, f"Candidate max loss incl. costs ₹{b_new:,.0f} exceeds confirmed per-position ceiling ₹{per_pos_cap:,.0f}.")

    d = context.drawdown_inr()
    init_loss = context.initial_capital_loss_inr()
    if d is None or init_loss is None:
        return _insufficient(res, "Could not compute drawdown metrics.")

    if d >= context.loss_ceiling:
        return _reject(
            res,
            f"Portfolio drawdown ₹{d:,.0f} is at or above the ₹{context.loss_ceiling:,.0f} loss ceiling; "
            "no new funded-paper entries.",
        )

    sum_b = context.sum_remaining_risk()
    if d + sum_b + b_new > context.loss_ceiling:
        return _reject(
            res,
            f"Peak drawdown ₹{d:,.0f} plus remaining open downside ₹{sum_b:,.0f} plus candidate ₹{b_new:,.0f} "
            f"would exceed the ₹{context.loss_ceiling:,.0f} ceiling.",
        )
    if init_loss + sum_b + b_new > context.loss_ceiling:
        return _reject(
            res,
            f"Initial-capital loss ₹{init_loss:,.0f} plus remaining open downside ₹{sum_b:,.0f} plus candidate ₹{b_new:,.0f} "
            f"would exceed the ₹{context.loss_ceiling:,.0f} ceiling.",
        )

    portfolio_cap = context.max_portfolio_risk_pct * context.initial_capital
    open_risk = sum(leg.max_loss_inr for leg in context.open_legs)
    if open_risk + b_new > portfolio_cap:
        return _reject(
            res,
            f"Open risk ₹{open_risk:,.0f} + candidate ₹{b_new:,.0f} exceeds interim portfolio cap ₹{portfolio_cap:,.0f}.",
        )

    if len(context.open_legs) + 1 > context.max_open_positions:
        return _reject(res, f"Would exceed max open positions ({context.max_open_positions}).")

    und = context.candidate_underlying or position.underlying
    conc_cap = context.max_single_underlying_pct * context.initial_capital
    und_risk = sum(leg.max_loss_inr for leg in context.open_legs if leg.underlying == und) + b_new
    if und_risk > conc_cap:
        return _reject(res, f"Concentration in {und}: ₹{und_risk:,.0f} > cap ₹{conc_cap:,.0f}.")

    if context.require_margin_for_options and position.legs and context.candidate_margin_required_inr is None:
        return _insufficient(res, "Options funded-paper qualification requires explicit margin/cash requirement.")

    if context.available_cash_inr is not None and context.candidate_margin_required_inr is not None:
        if context.candidate_margin_required_inr > context.available_cash_inr:
            return _reject(
                res,
                f"Required margin/cash ₹{context.candidate_margin_required_inr:,.0f} exceeds available cash "
                f"₹{context.available_cash_inr:,.0f}.",
            )
    elif context.available_cash_inr is None:
        return _insufficient(res, "Available cash is unknown.")

    mp = position.max_profit(include_costs=True)
    if not math.isinf(mp) and mp <= 0:
        return _reject(res, "Max profit after costs is <= 0; the trade cannot make money.")

    rr = position.reward_to_risk(include_costs=True)
    if rr is not None and rr < 0.20:
        res.warnings.append(f"Reward:risk {rr:.2f} is low (<0.20).")

    for w in position.liquidity_warnings():
        res.warnings.append("Liquidity: " + w)

    res.status = EligibilityStatus.ELIGIBLE
    return res


def max_lots_for_budget(per_lot_max_loss: float, risk: RiskConfig) -> int:
    if risk.risk_per_trade_max is None:
        return 0
    if per_lot_max_loss <= 0 or math.isinf(per_lot_max_loss):
        return 0
    return int(risk.risk_per_trade_max // per_lot_max_loss)
