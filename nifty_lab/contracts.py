"""Exchange contract specifications (lot sizes, strike intervals, expiry rules).

These values CHANGE over time. Each entry carries the date it was verified and
the source. The UI must surface ``verified_on`` so the user can judge staleness.

Sources (accessed 2026-11-09):
- NSE circular FAOP70616 (03-Oct-2025) via Zerodha bulletin 429705: lot-size revision
  effective for contracts expiring from Jan-2026 (NIFTY 75->65, BANKNIFTY 35->30).
- NSE contract specifications page: NIFTY strike interval 50; expiry Tuesday.
- Weekly expiries discontinued for BANKNIFTY/FINNIFTY/MIDCPNIFTY from 20-Nov-2024;
  NIFTY retains weekly expiry (SEBI Oct-2024 circular, one weekly index per exchange).
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class ContractSpec:
    symbol: str
    exchange: str
    lot_size: int
    strike_interval: float
    expiry_weekday: int  # Monday=0 ... Sunday=6
    has_weekly_expiry: bool
    verified_on: date
    source: str


CONTRACTS: dict[str, ContractSpec] = {
    "NIFTY": ContractSpec(
        symbol="NIFTY",
        exchange="NFO",
        lot_size=65,
        strike_interval=50.0,
        expiry_weekday=1,  # Tuesday
        has_weekly_expiry=True,
        verified_on=date(2026, 11, 9),
        source="NSE circular FAOP70616 (lot size, effective Jan-2026 expiries); NSE contract specs",
    ),
    "BANKNIFTY": ContractSpec(
        symbol="BANKNIFTY",
        exchange="NFO",
        lot_size=30,
        strike_interval=100.0,
        expiry_weekday=1,  # last Tuesday of the month
        has_weekly_expiry=False,
        verified_on=date(2026, 11, 9),
        source="NSE circular FAOP70616; weekly discontinued 20-Nov-2024",
    ),
    "FINNIFTY": ContractSpec(
        symbol="FINNIFTY",
        exchange="NFO",
        lot_size=60,
        strike_interval=50.0,
        expiry_weekday=1,
        has_weekly_expiry=False,
        verified_on=date(2026, 11, 9),
        source="NSE circular FAOP70616",
    ),
    "MIDCPNIFTY": ContractSpec(
        symbol="MIDCPNIFTY",
        exchange="NFO",
        lot_size=120,
        strike_interval=25.0,
        expiry_weekday=1,
        has_weekly_expiry=False,
        verified_on=date(2026, 11, 9),
        source="NSE circular FAOP70616",
    ),
}


def get_contract(symbol: str) -> ContractSpec:
    try:
        return CONTRACTS[symbol.upper()]
    except KeyError as exc:
        raise KeyError(f"No contract spec for {symbol!r}. Known: {sorted(CONTRACTS)}") from exc


def last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """Return the last occurrence of ``weekday`` in the given month."""
    last_day = calendar.monthrange(year, month)[1]
    d = date(year, month, last_day)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


def monthly_expiry(symbol: str, year: int, month: int) -> date:
    """Nominal monthly expiry (last expiry-weekday of month).

    NOTE: If that day is a trading holiday, NSE moves expiry to the previous
    trading day. Holiday calendars are not bundled; the UI flags this caveat.
    """
    spec = get_contract(symbol)
    return last_weekday_of_month(year, month, spec.expiry_weekday)


def next_monthly_expiries(symbol: str, today: date, count: int = 3) -> list[date]:
    """Upcoming monthly expiries (nominal, holiday-unadjusted), strictly after ``today``."""
    out: list[date] = []
    y, m = today.year, today.month
    while len(out) < count:
        exp = monthly_expiry(symbol, y, m)
        if exp > today:
            out.append(exp)
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def round_to_strike(price: float, symbol: str) -> float:
    """Round an underlying price to the nearest tradable strike."""
    step = get_contract(symbol).strike_interval
    return round(round(price / step) * step, 2)


def strike_ladder(center: float, symbol: str, n_each_side: int = 10) -> list[float]:
    step = get_contract(symbol).strike_interval
    atm = round_to_strike(center, symbol)
    return [round(atm + i * step, 2) for i in range(-n_each_side, n_each_side + 1)]
