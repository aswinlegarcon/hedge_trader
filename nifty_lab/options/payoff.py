"""Option position payoff engine (deterministic, no pricing model required).

A :class:`Position` is a set of option legs (plus an optional linear underlying
holding). Expiry payoff is piecewise-linear, so maximum profit / loss are found
exactly by evaluating at every kink (strike), at zero and at a far-right point.

Conventions
-----------
* ``Quote`` carries bid and ask. Conservative fills: BUY at ask, SELL at bid.
* Quantities are in *units* (lots x lot_size). Premiums are per unit.
* Costs are *estimated* exchange/statutory charges plus brokerage for opening
  every leg and closing it before expiry (conservative: we assume we pay to exit).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from .costs import DEFAULT_COSTS, CostSchedule, option_order_costs


class OptionType(str, Enum):
    CE = "CE"
    PE = "PE"


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True)
class Quote:
    bid: float
    ask: float

    def __post_init__(self) -> None:
        if self.bid < 0 or self.ask < 0:
            raise ValueError("bid/ask must be non-negative")
        if self.ask < self.bid:
            raise ValueError(f"ask ({self.ask}) < bid ({self.bid})")

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread_pct(self) -> float:
        return (self.ask - self.bid) / self.mid if self.mid > 0 else float("inf")


@dataclass(frozen=True)
class OptionLeg:
    option_type: OptionType
    strike: float
    side: Side
    quote: Quote
    lots: int = 1
    lot_size: int = 65
    iv: float | None = None  # implied vol if known (for display only)

    def __post_init__(self) -> None:
        if self.lots <= 0 or self.lot_size <= 0:
            raise ValueError("lots and lot_size must be positive")
        if self.strike <= 0:
            raise ValueError("strike must be positive")

    @property
    def quantity(self) -> int:
        return self.lots * self.lot_size

    @property
    def fill_price(self) -> float:
        """Conservative executable price: pay the ask to buy, hit the bid to sell."""
        return self.quote.ask if self.side == Side.LONG else self.quote.bid

    @property
    def sign(self) -> int:
        return 1 if self.side == Side.LONG else -1

    def intrinsic(self, spot: np.ndarray | float) -> np.ndarray | float:
        if self.option_type == OptionType.CE:
            return np.maximum(np.asarray(spot, dtype=float) - self.strike, 0.0)
        return np.maximum(self.strike - np.asarray(spot, dtype=float), 0.0)

    def payoff(self, spot: np.ndarray | float) -> np.ndarray | float:
        """Expiry P&L for this leg (before costs), total across quantity."""
        return self.sign * (self.intrinsic(spot) - self.fill_price) * self.quantity

    def entry_costs(self, schedule: CostSchedule = DEFAULT_COSTS) -> float:
        side = "BUY" if self.side == Side.LONG else "SELL"
        return option_order_costs(self.fill_price, self.quantity, side, schedule).total

    def estimated_exit_costs(self, schedule: CostSchedule = DEFAULT_COSTS) -> float:
        """Assume we close the leg near its entry price (conservative placeholder).

        STT on the closing sell of a long leg is charged on premium, so a long
        leg's exit cost is estimated at the entry premium; a short leg's buy-back
        is estimated at the entry premium as well.
        """
        side = "SELL" if self.side == Side.LONG else "BUY"
        return option_order_costs(self.fill_price, self.quantity, side, schedule).total


@dataclass(frozen=True)
class UnderlyingLeg:
    """Linear exposure (stock / futures). quantity > 0 long, < 0 short."""

    entry_price: float
    quantity: int

    def payoff(self, spot: np.ndarray | float) -> np.ndarray | float:
        return (np.asarray(spot, dtype=float) - self.entry_price) * self.quantity


@dataclass
class Position:
    name: str
    underlying: str
    expiry: str  # ISO date string
    legs: list[OptionLeg]
    underlying_leg: UnderlyingLeg | None = None
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.legs and self.underlying_leg is None:
            raise ValueError("Position needs at least one leg")

    # --- basic figures ----------------------------------------------------
    @property
    def net_premium(self) -> float:
        """Net cash flow at entry across option legs: +credit, -debit (total INR)."""
        return float(sum(-leg.sign * leg.fill_price * leg.quantity for leg in self.legs))

    @property
    def is_credit(self) -> bool:
        return self.net_premium > 0

    def entry_costs(self, schedule: CostSchedule = DEFAULT_COSTS) -> float:
        return float(sum(leg.entry_costs(schedule) for leg in self.legs))

    def estimated_total_costs(self, schedule: CostSchedule = DEFAULT_COSTS) -> float:
        return float(sum(leg.entry_costs(schedule) + leg.estimated_exit_costs(schedule) for leg in self.legs))

    # --- payoff -------------------------------------------------------------
    def payoff(self, spot: np.ndarray | float, include_costs: bool = True, schedule: CostSchedule = DEFAULT_COSTS) -> np.ndarray | float:
        total = np.zeros_like(np.asarray(spot, dtype=float))
        for leg in self.legs:
            total = total + leg.payoff(spot)
        if self.underlying_leg is not None:
            total = total + self.underlying_leg.payoff(spot)
        if include_costs:
            total = total - self.estimated_total_costs(schedule)
        return total

    def _kinks(self) -> list[float]:
        strikes = sorted({leg.strike for leg in self.legs})
        if not strikes:
            ref = self.underlying_leg.entry_price if self.underlying_leg else 1.0
            strikes = [ref]
        far_right = strikes[-1] * 3.0
        return [0.0] + strikes + [far_right]

    def _slope_right(self) -> float:
        """Payoff slope for spot -> +inf (units)."""
        slope = 0.0
        for leg in self.legs:
            if leg.option_type == OptionType.CE:
                slope += leg.sign * leg.quantity
        if self.underlying_leg is not None:
            slope += self.underlying_leg.quantity
        return slope

    def _slope_left(self) -> float:
        """Payoff slope for spot -> 0 (negative direction). Puts and underlying matter."""
        slope = 0.0
        for leg in self.legs:
            if leg.option_type == OptionType.PE:
                slope -= leg.sign * leg.quantity
        if self.underlying_leg is not None:
            slope += self.underlying_leg.quantity
        return slope

    def max_profit(self, include_costs: bool = True, schedule: CostSchedule = DEFAULT_COSTS) -> float:
        """Maximum expiry profit. ``inf`` if unbounded to the upside."""
        if self._slope_right() > 0:
            return float("inf")
        vals = self.payoff(np.array(self._kinks()), include_costs, schedule)
        return float(np.max(vals))

    def max_loss(self, include_costs: bool = True, schedule: CostSchedule = DEFAULT_COSTS) -> float:
        """Maximum expiry loss as a POSITIVE number. ``inf`` if unbounded upside risk.

        Downside is bounded by spot = 0, so a naked put / long underlying returns
        its (large but finite) loss at zero.
        """
        if self._slope_right() < 0:
            return float("inf")
        vals = self.payoff(np.array(self._kinks()), include_costs, schedule)
        return float(max(0.0, -np.min(vals)))

    def breakevens(self, include_costs: bool = True, schedule: CostSchedule = DEFAULT_COSTS) -> list[float]:
        """Spot levels where expiry P&L crosses zero (linear interpolation between kinks)."""
        xs = np.array(self._kinks())
        ys = np.asarray(self.payoff(xs, include_costs, schedule))
        out: list[float] = []
        for i in range(len(xs) - 1):
            y0, y1 = ys[i], ys[i + 1]
            if y0 == 0.0:
                out.append(float(xs[i]))
            elif (y0 < 0 < y1) or (y0 > 0 > y1):
                out.append(float(xs[i] + (xs[i + 1] - xs[i]) * (-y0) / (y1 - y0)))
        return sorted(set(round(b, 2) for b in out if b > 0))

    def reward_to_risk(self, include_costs: bool = True, schedule: CostSchedule = DEFAULT_COSTS) -> float | None:
        mp, ml = self.max_profit(include_costs, schedule), self.max_loss(include_costs, schedule)
        if ml == 0 or np.isinf(ml) or np.isinf(mp):
            return None
        return mp / ml

    def payoff_curve(self, center: float, width_pct: float = 0.12, points: int = 400, include_costs: bool = True) -> tuple[np.ndarray, np.ndarray]:
        xs = np.linspace(center * (1 - width_pct), center * (1 + width_pct), points)
        return xs, np.asarray(self.payoff(xs, include_costs))

    def net_greeks(self, spot: float, T: float, r: float, q: float) -> dict[str, float] | None:
        """Aggregate Greeks using each leg's IV; None if any leg lacks IV."""
        from .pricing import bs_greeks  # local import to keep payoff model-free

        if any(leg.iv is None for leg in self.legs):
            return None
        agg = {"delta": 0.0, "gamma": 0.0, "theta_per_day": 0.0, "vega_per_pct": 0.0}
        for leg in self.legs:
            g = bs_greeks(spot, leg.strike, T, leg.iv, leg.option_type.value, r, q)  # type: ignore[arg-type]
            agg["delta"] += leg.sign * g.delta * leg.quantity
            agg["gamma"] += leg.sign * g.gamma * leg.quantity
            agg["theta_per_day"] += leg.sign * g.theta_per_day * leg.quantity
            agg["vega_per_pct"] += leg.sign * g.vega_per_pct * leg.quantity
        if self.underlying_leg is not None:
            agg["delta"] += self.underlying_leg.quantity
        return agg

    def liquidity_warnings(self, max_spread_pct: float = 0.10) -> list[str]:
        warns = []
        for leg in self.legs:
            if leg.quote.mid <= 0:
                warns.append(f"{leg.option_type.value} {leg.strike:g}: no quote (bid/ask zero)")
            elif leg.quote.spread_pct > max_spread_pct:
                warns.append(f"{leg.option_type.value} {leg.strike:g}: wide bid-ask spread {leg.quote.spread_pct:.1%}")
        return warns
