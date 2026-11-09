"""Backtesting Lab — Phase 3 placeholder with a transparent statement of what exists."""
from __future__ import annotations

import streamlit as st

from nifty_lab.ui.common import footer, setup_page

setup_page("Backtesting Lab")
st.warning(
    "**Backtesting is Phase 3 and is not implemented yet.** This page intentionally shows no performance numbers. "
    "No strategy in this application has been validated — on real or synthetic data.",
    icon="🧪",
)
st.subheader("What Phase 3 will deliver")
st.markdown(
    """
- Event-driven engine with **no look-ahead** (signals computed from bars ≤ t, fills at t+1 open).
- Realistic costs (the same `CostSchedule` used by the analyzer) and conservative slippage (fill at bid for sells / ask for buys plus a configurable tick penalty).
- Walk-forward and out-of-sample splits; results reported **per volatility regime**.
- Metrics: total return, max drawdown, win rate, profit factor, avg win/loss, expectancy, Sharpe (when meaningful), trade count, exposure time.
- A hard label on every result: **REAL OPTION-CHAIN BACKTEST** vs **UNDERLYING-BASED APPROXIMATION** (Black-Scholes-priced legs from index data).
- Historical option-chain data only from licensed sources (e.g. broker historical API with your subscription). Synthetic chains will never be reported as validation.
"""
)
st.subheader("Why it is not here yet")
st.markdown(
    """
The only data in v1 is synthetic or user-imported index OHLCV. Running an options backtest on that would require
inventing option prices, and presenting those results would be misleading. The engine will ship once
real historical data can be loaded (Phase 2) so that each result can be labelled honestly.
"""
)
footer()
