"""Black-Scholes pricing, Greeks and implied volatility for European index options.

NIFTY / BANKNIFTY options are European-style (cash settled), so Black-Scholes
is an appropriate first-order model. All rates/vols are annualised decimals
(0.065 = 6.5%); time is in years.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from scipy.optimize import brentq
from scipy.stats import norm

DEFAULT_RISK_FREE = 0.065  # approx. Indian short-term rate; configurable in UI
DEFAULT_DIV_YIELD = 0.012  # approx. NIFTY dividend yield; configurable


@dataclass(frozen=True)
class Greeks:
    price: float
    delta: float
    gamma: float
    theta_per_day: float  # change in price for one calendar day passing
    vega_per_pct: float  # change in price for a 1 percentage-point move in IV
    rho_per_pct: float


def _d1_d2(S: float, K: float, T: float, r: float, q: float, sigma: float) -> tuple[float, float]:
    if S <= 0 or K <= 0:
        raise ValueError("S and K must be positive")
    if T <= 0:
        raise ValueError("T must be positive")
    if sigma <= 0:
        raise ValueError("sigma must be positive")
    vs = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vs
    return d1, d1 - vs


def bs_price(S: float, K: float, T: float, sigma: float, option_type: str, r: float = DEFAULT_RISK_FREE, q: float = DEFAULT_DIV_YIELD) -> float:
    option_type = option_type.upper()
    if T <= 0:  # at expiry: intrinsic value
        return max(S - K, 0.0) if option_type == "CE" else max(K - S, 0.0)
    d1, d2 = _d1_d2(S, K, T, r, q, sigma)
    if option_type == "CE":
        return S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    if option_type == "PE":
        return K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)
    raise ValueError("option_type must be 'CE' or 'PE'")


def bs_greeks(S: float, K: float, T: float, sigma: float, option_type: str, r: float = DEFAULT_RISK_FREE, q: float = DEFAULT_DIV_YIELD) -> Greeks:
    option_type = option_type.upper()
    price = bs_price(S, K, T, sigma, option_type, r, q)
    if T <= 0:
        intrinsic_itm = (S > K) if option_type == "CE" else (S < K)
        delta = (1.0 if intrinsic_itm else 0.0) * (1 if option_type == "CE" else -1)
        return Greeks(price, delta, 0.0, 0.0, 0.0, 0.0)
    d1, d2 = _d1_d2(S, K, T, r, q, sigma)
    sqrtT = math.sqrt(T)
    pdf_d1 = norm.pdf(d1)
    disc_q = math.exp(-q * T)
    disc_r = math.exp(-r * T)
    gamma = disc_q * pdf_d1 / (S * sigma * sqrtT)
    vega = S * disc_q * pdf_d1 * sqrtT  # per 1.0 change in sigma
    common_theta = -(S * disc_q * pdf_d1 * sigma) / (2 * sqrtT)
    if option_type == "CE":
        delta = disc_q * norm.cdf(d1)
        theta = common_theta - r * K * disc_r * norm.cdf(d2) + q * S * disc_q * norm.cdf(d1)
        rho = K * T * disc_r * norm.cdf(d2)
    else:
        delta = -disc_q * norm.cdf(-d1)
        theta = common_theta + r * K * disc_r * norm.cdf(-d2) - q * S * disc_q * norm.cdf(-d1)
        rho = -K * T * disc_r * norm.cdf(-d2)
    return Greeks(
        price=price,
        delta=delta,
        gamma=gamma,
        theta_per_day=theta / 365.0,
        vega_per_pct=vega / 100.0,
        rho_per_pct=rho / 100.0,
    )


def implied_volatility(market_price: float, S: float, K: float, T: float, option_type: str, r: float = DEFAULT_RISK_FREE, q: float = DEFAULT_DIV_YIELD) -> float | None:
    """Solve for IV with Brent's method. Returns None if no solution exists
    (price below intrinsic / above upper bound), which the caller must report
    as INSUFFICIENT DATA rather than guess."""
    if T <= 0 or market_price <= 0:
        return None
    option_type = option_type.upper()
    intrinsic = max(S * math.exp(-q * T) - K * math.exp(-r * T), 0.0) if option_type == "CE" else max(K * math.exp(-r * T) - S * math.exp(-q * T), 0.0)
    upper = S * math.exp(-q * T) if option_type == "CE" else K * math.exp(-r * T)
    if market_price < intrinsic - 1e-9 or market_price > upper + 1e-9:
        return None

    def f(sig: float) -> float:
        return bs_price(S, K, T, sig, option_type, r, q) - market_price

    lo, hi = 1e-4, 5.0
    try:
        if f(lo) > 0 or f(hi) < 0:
            return None
        return float(brentq(f, lo, hi, xtol=1e-8, maxiter=200))
    except (ValueError, RuntimeError):
        return None


def years_to_expiry(days: float) -> float:
    return max(days, 0.0) / 365.0
