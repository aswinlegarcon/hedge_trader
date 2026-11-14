"""Explicit portfolio context for funded-paper eligibility (Spec 03).

Production UI must not fabricate equity, peak equity or marks from the journal alone.
Use :func:`production_context_blocked` until a trustworthy valuation provider exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..config import RESEARCH_PROFILE_ID


class EligibilityStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    REJECTED = "REJECTED"
    INSUFFICIENT_DATA = "INSUFFICIENT DATA"


@dataclass(frozen=True)
class OpenRiskLeg:
    """One open position's worst-case and mark on the same cost basis."""

    underlying: str
    max_loss_inr: float  # R_i — total entry-to-worst including costs
    net_pnl_inr: float = 0.0  # P_i — current net P&L on the same basis


@dataclass(frozen=True)
class FundedPaperContext:
    profile_id: str
    initial_capital: float
    loss_ceiling: float
    equity_inr: float | None
    peak_equity_inr: float | None
    open_legs: tuple[OpenRiskLeg, ...] = ()
    candidate_max_loss_inr: float | None = None
    candidate_underlying: str = ""
    available_cash_inr: float | None = None
    candidate_margin_required_inr: float | None = None
    per_position_risk_max: float | None = None  # None = user policy unconfirmed
    has_unreconciled_legacy: bool = False
    valuation_trusted: bool = False
    profile_authorized: bool = True
    max_open_positions: int = 3
    max_portfolio_risk_pct: float = 0.06
    max_single_underlying_pct: float = 0.04
    require_margin_for_options: bool = True

    def remaining_risk_leg(self, leg: OpenRiskLeg) -> float:
        return max(0.0, leg.max_loss_inr + leg.net_pnl_inr)

    def sum_remaining_risk(self) -> float:
        return sum(self.remaining_risk_leg(leg) for leg in self.open_legs)

    def drawdown_inr(self) -> float | None:
        if self.equity_inr is None or self.peak_equity_inr is None:
            return None
        return max(0.0, self.peak_equity_inr - self.equity_inr)

    def initial_capital_loss_inr(self) -> float | None:
        if self.equity_inr is None:
            return None
        return max(0.0, self.initial_capital - self.equity_inr)


def production_context_blocked(
    *,
    initial_capital: float,
    loss_ceiling: float,
    profile_authorized: bool,
    has_unreconciled_legacy: bool = False,
) -> FundedPaperContext:
    """Fail-closed context for UI paths without reconciled marks."""
    return FundedPaperContext(
        profile_id=RESEARCH_PROFILE_ID,
        initial_capital=initial_capital,
        loss_ceiling=loss_ceiling,
        equity_inr=None,
        peak_equity_inr=None,
        has_unreconciled_legacy=has_unreconciled_legacy,
        valuation_trusted=False,
        profile_authorized=profile_authorized,
    )


def independent_test_context(**overrides: object) -> FundedPaperContext:
    """Explicit fixtures for unit tests — never loaded from environment."""
    base = {
        "profile_id": RESEARCH_PROFILE_ID,
        "initial_capital": 20_000.0,
        "loss_ceiling": 2_000.0,
        "equity_inr": 20_000.0,
        "peak_equity_inr": 20_000.0,
        "valuation_trusted": True,
        "profile_authorized": True,
        "per_position_risk_max": 1_500.0,
        "available_cash_inr": 20_000.0,
        "candidate_margin_required_inr": 0.0,
        "has_unreconciled_legacy": False,
    }
    base.update(overrides)
    return FundedPaperContext(**base)  # type: ignore[arg-type]
