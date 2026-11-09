"""Builders for the defined-risk strategies supported in v1.

All builders accept *executable* quotes (bid/ask) per strike and return a
:class:`Position`. They never fabricate prices: if a quote is missing the
caller gets a ``KeyError`` and the UI shows INSUFFICIENT DATA.
"""
from __future__ import annotations

from collections.abc import Mapping

from .payoff import OptionLeg, OptionType, Position, Quote, Side, UnderlyingLeg

QuoteBook = Mapping[tuple[str, float], Quote]  # key: (option_type, strike)


def _q(book: QuoteBook, opt: str, strike: float) -> Quote:
    try:
        return book[(opt, float(strike))]
    except KeyError as exc:
        raise KeyError(f"No executable quote for {opt} {strike:g} — INSUFFICIENT DATA") from exc


def _iv(ivs: Mapping[tuple[str, float], float] | None, opt: str, strike: float) -> float | None:
    if ivs is None:
        return None
    return ivs.get((opt, float(strike)))


def bull_put_spread(underlying: str, expiry: str, short_strike: float, long_strike: float, book: QuoteBook, lots: int, lot_size: int, ivs=None) -> Position:
    """Sell a put, buy a lower put. Bullish/neutral, defined risk, credit."""
    if not long_strike < short_strike:
        raise ValueError("Bull put spread requires long_strike < short_strike")
    legs = [
        OptionLeg(OptionType.PE, short_strike, Side.SHORT, _q(book, "PE", short_strike), lots, lot_size, _iv(ivs, "PE", short_strike)),
        OptionLeg(OptionType.PE, long_strike, Side.LONG, _q(book, "PE", long_strike), lots, lot_size, _iv(ivs, "PE", long_strike)),
    ]
    return Position(f"Bull Put Spread {short_strike:g}/{long_strike:g}", underlying, expiry, legs,
                    notes=["Profits if the index stays above the short put strike at expiry.",
                           "Max loss = (strike width - net credit) x quantity + costs."])


def bear_call_spread(underlying: str, expiry: str, short_strike: float, long_strike: float, book: QuoteBook, lots: int, lot_size: int, ivs=None) -> Position:
    """Sell a call, buy a higher call. Bearish/neutral, defined risk, credit."""
    if not long_strike > short_strike:
        raise ValueError("Bear call spread requires long_strike > short_strike")
    legs = [
        OptionLeg(OptionType.CE, short_strike, Side.SHORT, _q(book, "CE", short_strike), lots, lot_size, _iv(ivs, "CE", short_strike)),
        OptionLeg(OptionType.CE, long_strike, Side.LONG, _q(book, "CE", long_strike), lots, lot_size, _iv(ivs, "CE", long_strike)),
    ]
    return Position(f"Bear Call Spread {short_strike:g}/{long_strike:g}", underlying, expiry, legs,
                    notes=["Profits if the index stays below the short call strike at expiry.",
                           "Max loss = (strike width - net credit) x quantity + costs."])


def iron_condor(underlying: str, expiry: str, put_short: float, put_long: float, call_short: float, call_long: float, book: QuoteBook, lots: int, lot_size: int, ivs=None) -> Position:
    """Bull put spread + bear call spread. Neutral, defined risk, credit."""
    if not (put_long < put_short < call_short < call_long):
        raise ValueError("Iron condor requires put_long < put_short < call_short < call_long")
    bp = bull_put_spread(underlying, expiry, put_short, put_long, book, lots, lot_size, ivs)
    bc = bear_call_spread(underlying, expiry, call_short, call_long, book, lots, lot_size, ivs)
    return Position(f"Iron Condor {put_long:g}/{put_short:g}/{call_short:g}/{call_long:g}", underlying, expiry, bp.legs + bc.legs,
                    notes=["Profits if the index expires between the two short strikes.",
                           "Only one side can lose at expiry; max loss = wider wing width - total credit + costs.",
                           "RESEARCH ONLY in v1: four legs mean four sets of transaction costs and slippage."])


def protective_put(underlying: str, expiry: str, underlying_price: float, underlying_qty: int, put_strike: float, book: QuoteBook, lots: int, lot_size: int, ivs=None) -> Position:
    """Long underlying + long put. Caps downside below the strike (insurance)."""
    if underlying_qty <= 0:
        raise ValueError("protective put requires a long underlying position")
    legs = [OptionLeg(OptionType.PE, put_strike, Side.LONG, _q(book, "PE", put_strike), lots, lot_size, _iv(ivs, "PE", put_strike))]
    pos = Position(f"Protective Put {put_strike:g}", underlying, expiry, legs, UnderlyingLeg(underlying_price, underlying_qty),
                   notes=["Requires an existing long position in the underlying (stock or futures).",
                          "For NIFTY you cannot hold the index directly; this models a futures/ETF-equivalent exposure."])
    if underlying_qty != lots * lot_size:
        pos.notes.append(f"WARNING: underlying quantity {underlying_qty} != option quantity {lots * lot_size}; hedge is partial.")
    return pos


def covered_call(underlying: str, expiry: str, underlying_price: float, underlying_qty: int, call_strike: float, book: QuoteBook, lots: int, lot_size: int, ivs=None) -> Position:
    """Long underlying + short call. Income strategy; downside is NOT protected."""
    if underlying_qty <= 0:
        raise ValueError("covered call requires a long underlying position")
    legs = [OptionLeg(OptionType.CE, call_strike, Side.SHORT, _q(book, "CE", call_strike), lots, lot_size, _iv(ivs, "CE", call_strike))]
    pos = Position(f"Covered Call {call_strike:g}", underlying, expiry, legs, UnderlyingLeg(underlying_price, underlying_qty),
                   notes=["Downside risk is the full underlying exposure minus the premium received.",
                          "Max loss reported assumes the underlying can fall to zero."])
    if underlying_qty < lots * lot_size:
        pos.notes.append("WARNING: short calls exceed underlying holding — this is a partially NAKED call (unbounded risk).")
    return pos


def theoretical_quote_book(spot: float, strikes: list[float], T: float, iv: float, r: float, q: float, half_spread_pct: float = 0.02, min_half_spread: float = 0.25) -> tuple[dict, dict]:
    """Build a SYNTHETIC quote book from Black-Scholes with a flat IV.

    Returns (book, ivs). Clearly labelled THEORETICAL in the UI; use only when
    no live option chain is available. Bid/ask are mid ± max(2%, ₹0.25).
    """
    from .pricing import bs_price

    book: dict[tuple[str, float], Quote] = {}
    ivs: dict[tuple[str, float], float] = {}
    for k in strikes:
        for opt in ("CE", "PE"):
            mid = bs_price(spot, k, T, iv, opt, r, q)
            half = max(mid * half_spread_pct, min_half_spread)
            bid = max(mid - half, 0.05) if mid > 0.05 else 0.0
            ask = mid + half
            book[(opt, float(k))] = Quote(round(bid, 2), round(ask, 2))
            ivs[(opt, float(k))] = iv
    return book, ivs
