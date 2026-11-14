"""Shared execution entry gate (Spec 08)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal

from ..config import RESEARCH_PROFILE_ID
from ..risk.context import EligibilityStatus
from .policy import EXECUTION_V1, ExecutionPolicy
from .types import InstrumentKind, OrderSide, TradeCandidate


@dataclass
class ExecutionGateResult:
    status: EligibilityStatus
    planned_risk_inr: float
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.status == EligibilityStatus.ELIGIBLE


@dataclass(frozen=True)
class ExecutionPortfolioContext:
    """Trusted reconciled context for execution (paper ledger or live reconcile)."""

    profile_id: str
    policy: ExecutionPolicy
    equity_inr: float
    peak_equity_inr: float
    cash_inr: float
    reserved_cash_inr: float
    reserved_risk_inr: float
    open_position_count: int
    open_risk_by_underlying: dict[str, float]
    sum_open_risk_inr: float
    valuation_trusted: bool = True
    has_unreconciled_external: bool = False
    available_strategy_cash_inr: float | None = None
    owned_quantity_by_instrument: tuple[tuple[str, int], ...] = ()
    pending_sell_qty_by_instrument: tuple[tuple[str, int], ...] = ()
    open_risk_by_instrument: tuple[tuple[str, float], ...] = ()
    pending_buy_risk_by_instrument: tuple[tuple[str, float], ...] = ()
    pending_buy_risk_by_underlying: tuple[tuple[str, float], ...] = ()
    exposed_instrument_count: int = 0


def _finite_money(name: str, value: float | None, *, allow_none: bool = False) -> list[str]:
    if value is None:
        if not allow_none:
            return [f"Missing {name}."]
        return []
    if not math.isfinite(value):
        return [f"Non-finite {name}."]
    return []


def validate_portfolio_context(context: ExecutionPortfolioContext) -> list[str]:
    """Reject NaN/inf/invalid monetary fields before any entry logic."""
    reasons: list[str] = []
    for label, val in (
        ("equity_inr", context.equity_inr),
        ("peak_equity_inr", context.peak_equity_inr),
        ("cash_inr", context.cash_inr),
        ("reserved_cash_inr", context.reserved_cash_inr),
        ("reserved_risk_inr", context.reserved_risk_inr),
        ("sum_open_risk_inr", context.sum_open_risk_inr),
    ):
        reasons.extend(_finite_money(label, val))
    reasons.extend(_finite_money("available_strategy_cash_inr", context.available_strategy_cash_inr, allow_none=True))
    if context.available_strategy_cash_inr is not None and context.available_strategy_cash_inr < 0:
        reasons.append("Negative available strategy cash.")
    if context.reserved_cash_inr < 0 or context.reserved_risk_inr < 0:
        reasons.append("Negative pending reservations in context.")
    for und, risk in context.open_risk_by_underlying.items():
        if not math.isfinite(risk) or risk < 0:
            reasons.append(f"Invalid open risk for {und}.")
    return reasons


def validate_candidate(candidate: TradeCandidate) -> list[str]:
    reasons: list[str] = []
    if candidate.quantity <= 0 or candidate.quantity != int(candidate.quantity):
        reasons.append("Quantity must be a positive integer.")
    if not math.isfinite(candidate.limit_price_inr) or candidate.limit_price_inr <= 0:
        reasons.append("Invalid limit price.")
    if candidate.entry_cost_inr < 0 or not math.isfinite(candidate.entry_cost_inr):
        reasons.append("Entry costs must be finite and non-negative.")
    if candidate.exit_cost_reserve_inr < 0 or not math.isfinite(candidate.exit_cost_reserve_inr):
        reasons.append("Exit cost reserve must be finite and non-negative.")
    if candidate.margin_required_inr is not None and (
        not math.isfinite(candidate.margin_required_inr) or candidate.margin_required_inr < 0
    ):
        reasons.append("Invalid margin requirement.")
    for label, val in (
        ("planned_risk_inr", candidate.planned_risk_inr),
        ("premium_at_risk_inr", candidate.premium_at_risk_inr),
    ):
        if val is not None and not math.isfinite(val):
            reasons.append(f"Non-finite {label}.")
    if candidate.quote is not None and candidate.quote.instrument_key != candidate.instrument_key:
        reasons.append("Quote instrument key does not match ticket instrument key.")
    if not candidate.underlying.strip():
        reasons.append("Underlying is required.")
    if candidate.kind == InstrumentKind.NIFTY_OPTION:
        if candidate.lot_size <= 0:
            reasons.append("NIFTY options require positive lot size metadata.")
        elif candidate.quantity % candidate.lot_size != 0:
            reasons.append("NIFTY quantity must be a whole number of lots.")
    if candidate.kind in (InstrumentKind.CASH_STOCK, InstrumentKind.CASH_ETF) and candidate.side == OrderSide.BUY:
        if candidate.stop_reference_inr is not None and not math.isfinite(candidate.stop_reference_inr):
            reasons.append("Invalid stop reference.")
    return reasons


def _money(x: float) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"))


def compute_stock_planned_risk(
    entry_limit: float,
    stop_ref: float | None,
    quantity: int,
    entry_cost: float,
    exit_reserve: float,
) -> float | None:
    if stop_ref is None or not math.isfinite(stop_ref) or not math.isfinite(entry_limit):
        return None
    if stop_ref >= entry_limit:
        return None
    if quantity <= 0:
        return None
    per_share = entry_limit - stop_ref
    return float(_money(per_share * quantity + entry_cost + exit_reserve))


def compute_option_premium_risk(
    limit_price: float,
    quantity: int,
    entry_cost: float,
    exit_reserve: float,
) -> float | None:
    if not math.isfinite(limit_price) or quantity <= 0:
        return None
    return float(_money(limit_price * quantity + entry_cost + exit_reserve))


def resolved_candidate_risk(candidate: TradeCandidate) -> float | None:
    if candidate.kind in (InstrumentKind.CASH_STOCK, InstrumentKind.CASH_ETF):
        computed = compute_stock_planned_risk(
            candidate.limit_price_inr,
            candidate.stop_reference_inr,
            candidate.quantity,
            candidate.entry_cost_inr,
            candidate.exit_cost_reserve_inr,
        )
    else:
        computed = compute_option_premium_risk(
            candidate.limit_price_inr,
            candidate.quantity,
            candidate.entry_cost_inr,
            candidate.exit_cost_reserve_inr,
        )
    if computed is None or not math.isfinite(computed):
        return None
    # Caller-declared fields may only increase computed risk, never replace it.
    risk = computed
    if candidate.premium_at_risk_inr is not None and math.isfinite(candidate.premium_at_risk_inr):
        risk = max(risk, candidate.premium_at_risk_inr)
    if candidate.planned_risk_inr is not None and math.isfinite(candidate.planned_risk_inr):
        risk = max(risk, candidate.planned_risk_inr)
    return risk


def evaluate_entry(
    candidate: TradeCandidate,
    context: ExecutionPortfolioContext | None,
    *,
    policy: ExecutionPolicy = EXECUTION_V1,
    for_reduce_only: bool = False,
) -> ExecutionGateResult:
    risk = resolved_candidate_risk(candidate)
    res = ExecutionGateResult(status=EligibilityStatus.INSUFFICIENT_DATA, planned_risk_inr=risk or float("nan"))

    cand_errs = validate_candidate(candidate)
    if cand_errs:
        res.status = EligibilityStatus.REJECTED
        res.reasons.extend(cand_errs)
        return res

    if for_reduce_only and candidate.side == OrderSide.BUY:
        res.status = EligibilityStatus.REJECTED
        res.reasons.append("Reduce-only flag applies to validated SELL closes only.")
        return res

    if context is not None:
        ctx_errs = validate_portfolio_context(context)
        if ctx_errs:
            res.status = EligibilityStatus.INSUFFICIENT_DATA
            res.reasons.extend(ctx_errs)
            return res

    if candidate.quote is None or not candidate.quote.is_valid():
        res.reasons.append("Fresh two-sided quote required.")
        return res

    if candidate.side == OrderSide.SELL:
        if not for_reduce_only:
            res.status = EligibilityStatus.REJECTED
            res.reasons.append("Uncovered sells are not supported; use reduce-only close.")
            return res
        if context is None or not context.valuation_trusted:
            res.reasons.append("Reconciled execution portfolio context required for sells.")
            return res
        if not candidate.quote.is_fresh():
            res.reasons.append("Quote is stale or future-dated; refresh within TTL.")
            return res
        owned = dict(context.owned_quantity_by_instrument).get(candidate.instrument_key, 0)
        pending_sell = dict(context.pending_sell_qty_by_instrument).get(candidate.instrument_key, 0)
        available = owned - pending_sell
        if available < candidate.quantity:
            res.status = EligibilityStatus.REJECTED
            res.reasons.append(
                f"Sell quantity {candidate.quantity} exceeds available-to-close {available} "
                f"(owned {owned}, pending sells {pending_sell})."
            )
            return res
        res.status = EligibilityStatus.ELIGIBLE
        res.planned_risk_inr = 0.0
        return res

    if not candidate.quote.is_fresh():
        res.reasons.append("Quote is stale or future-dated; refresh within TTL.")
        return res

    if context is None or not context.valuation_trusted:
        res.reasons.append("Reconciled execution portfolio context required.")
        return res

    if context.profile_id not in (RESEARCH_PROFILE_ID, policy.profile_id):
        res.reasons.append("Profile identity mismatch.")
        return res

    if context.has_unreconciled_external:
        res.reasons.append("Unresolved external broker exposure — reconcile before new risk.")
        return res

    if context.equity_inr < 0 or context.cash_inr < 0:
        res.status = EligibilityStatus.REJECTED
        res.reasons.append("Negative equity or cash — no new risk until reconciled.")
        return res

    if risk is None or not math.isfinite(risk) or risk <= 0:
        res.reasons.append("Could not compute finite entry risk.")
        return res

    res.planned_risk_inr = risk

    if candidate.kind in (InstrumentKind.CASH_STOCK, InstrumentKind.CASH_ETF):
        if candidate.stop_reference_inr is None:
            res.reasons.append("Stock entries require a protective stop reference below entry.")
            return res
        if not candidate.broker_stop_placed and not candidate.user_ack_stop_not_placed:
            res.reasons.append("Acknowledge STOP NOT PLACED at broker before live stock entry.")
            return res

    if candidate.kind == InstrumentKind.NIFTY_OPTION:
        if risk > policy.per_position_budget_inr:
            res.status = EligibilityStatus.REJECTED
            res.reasons.append(
                f"No size fits policy: premium-at-risk ₹{risk:,.2f} exceeds ₹{policy.per_position_budget_inr:,.0f} per position."
            )
            return res

    if risk > policy.per_position_budget_inr:
        res.status = EligibilityStatus.REJECTED
        res.reasons.append(
            f"Planned risk ₹{risk:,.2f} exceeds per-position budget ₹{policy.per_position_budget_inr:,.0f}."
        )
        return res

    if candidate.side == OrderSide.BUY:
        inst = candidate.instrument_key
        open_inst = dict(context.open_risk_by_instrument)
        pending_inst = dict(context.pending_buy_risk_by_instrument)
        resulting_inst_risk = open_inst.get(inst, 0.0) + pending_inst.get(inst, 0.0) + risk
        if resulting_inst_risk > policy.per_position_budget_inr:
            res.status = EligibilityStatus.REJECTED
            res.reasons.append(
                f"Resulting instrument risk ₹{resulting_inst_risk:,.2f} would exceed "
                f"per-position budget ₹{policy.per_position_budget_inr:,.0f} "
                f"(open ₹{open_inst.get(inst, 0):,.2f}, pending ₹{pending_inst.get(inst, 0):,.2f})."
            )
            return res
        if inst not in open_inst and inst not in pending_inst:
            if context.exposed_instrument_count >= policy.max_open_positions:
                res.status = EligibilityStatus.REJECTED
                res.reasons.append(
                    f"Max open instruments ({policy.max_open_positions}) including pending entries."
                )
                return res

    d = max(0.0, context.peak_equity_inr - context.equity_inr)
    init_loss = max(0.0, policy.initial_allocation_inr - context.equity_inr)
    if d >= policy.stop_new_risk_drawdown_inr or init_loss >= policy.stop_new_risk_drawdown_inr:
        res.status = EligibilityStatus.REJECTED
        res.reasons.append(
            f"Stop-new-risk threshold ₹{policy.stop_new_risk_drawdown_inr:,.0f} reached "
            f"(drawdown ₹{d:,.0f}, initial-capital loss ₹{init_loss:,.0f})."
        )
        return res

    pending = context.reserved_risk_inr
    if d + pending + context.sum_open_risk_inr + risk > policy.stop_new_risk_drawdown_inr:
        res.status = EligibilityStatus.REJECTED
        res.reasons.append("Peak drawdown plus open/pending risk would exceed stop-new-risk threshold.")
        return res

    if context.sum_open_risk_inr + pending + risk > policy.aggregate_risk_cap_inr:
        res.status = EligibilityStatus.REJECTED
        res.reasons.append(f"Aggregate risk cap ₹{policy.aggregate_risk_cap_inr:,.0f} exceeded.")
        return res

    und = candidate.underlying.upper()
    open_und = context.open_risk_by_underlying.get(und, 0.0)
    pending_und = dict(context.pending_buy_risk_by_underlying).get(und, 0.0)
    und_risk = open_und + pending_und + risk
    if und_risk > policy.per_underlying_cap_inr:
        res.status = EligibilityStatus.REJECTED
        res.reasons.append(
            f"Underlying concentration cap ₹{policy.per_underlying_cap_inr:,.0f} exceeded for {und} "
            f"(open ₹{open_und:,.2f}, pending ₹{pending_und:,.2f}, new ₹{risk:,.2f})."
        )
        return res

    need_cash = candidate.limit_price_inr * candidate.quantity + candidate.entry_cost_inr
    if candidate.margin_required_inr is not None:
        need_cash = max(need_cash, candidate.margin_required_inr)
    avail = context.available_strategy_cash_inr
    if avail is None:
        avail = context.cash_inr - context.reserved_cash_inr
    if need_cash > avail:
        res.status = EligibilityStatus.REJECTED
        res.reasons.append(f"Insufficient available cash/margin (need ₹{need_cash:,.0f}, avail ₹{avail:,.0f}).")
        return res

    res.status = EligibilityStatus.ELIGIBLE
    if candidate.kind in (InstrumentKind.CASH_STOCK, InstrumentKind.CASH_ETF):
        res.warnings.append(
            "Stock planned risk is not a guaranteed maximum; gap/full-to-zero downside is separate."
        )
    return res
