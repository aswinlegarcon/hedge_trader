"""Learning Center — beginner-friendly explanations and the system's rulebook."""
from __future__ import annotations

import streamlit as st

from nifty_lab.indicators import EXPLANATIONS
from nifty_lab.ui.common import footer, setup_page

setup_page("Learning Center")

t1, t2, t3, t4 = st.tabs(["Indicators", "Option strategies", "Risk rules", "Reading a signal"])
with t1:
    for key, text in EXPLANATIONS.items():
        st.markdown(f"**{key}** — {text}")
with t2:
    st.markdown(
        """
**Credit spread (bull put / bear call)** — you sell one option and buy a further-out option of the same type and expiry.
You receive a net credit. Max profit = credit − costs (if the index stays on the right side of the short strike).
Max loss = (strike width × quantity) − credit + costs. Both are known *before* you enter. That is why the app allows them.

**Iron condor** — a bull put spread plus a bear call spread. Profits if the index stays in a range. Four legs = four
sets of costs and slippage; in v1 it is labelled research-only.

**Protective put** — insurance on a long holding. Costs premium; caps loss below the strike.

**Covered call** — sell a call against a long holding. Earns premium; caps upside; downside remains.

**Why monthly expiry?** More time premium per unit of gap risk, fewer rushed decisions than weeklies, and lower
relative transaction costs. Note NIFTY now expires on **Tuesdays** (verified 2026-11-09); BANKNIFTY has monthly contracts only.

**Executable quotes** — the app values a sale at the **bid** and a purchase at the **ask**. Last-traded price is often stale or
unattainable; using it overstates credits and understates debits.

**Lot sizes change.** NIFTY moved 75 → 65 for contracts expiring from Jan-2026 (NSE circular FAOP70616). Always check the Settings page's
"verified on" date and override when the exchange revises.
"""
    )
with t3:
    st.markdown(
        """
1. **Max contractual loss first.** Every position is evaluated on its worst-case expiry loss including estimated costs, never on a
   stop-loss level. Stops are instructions, not guarantees.
2. **Per-trade budget ₹1,000–₹2,000** (configurable). Above the max → rejected. Below the min → warned (costs will eat the edge).
3. **Portfolio cap 6% of capital** across all open positions; **max 3** open positions; **4% per underlying**.
4. **Drawdown limit ₹10,000** on ₹1,00,000. At 70% of the limit the dashboard warns; at 100% it tells you to stop opening positions.
5. **No naked options.** Unbounded-risk positions are never eligible.
6. **Event risk.** RBI/Fed decisions, CPI prints, budget day, and expiry week widen outcomes. Enter them in the event calendar.
7. **Liquidity.** Bid-ask spread above 10% of mid raises a warning; a zero quote means INSUFFICIENT DATA.
8. **Paper ≠ real.** Paper fills ignore queue position, partial fills and panic. Expect worse live.
"""
    )
with t4:
    st.markdown(
        """
A **signal** here is a *description*, not a *prediction*:

- **Regime** uses the 50/200-day SMAs: BULLISH when price > both and 50 > 200; BEARISH when the reverse; NEUTRAL within 2% of the 200-day; otherwise UNCERTAIN.
- **BULLISH SETUP** requires a bullish regime, nearly all momentum rules agreeing (EMA9>21, MACD>signal & rising, RSI 45–70, close>SMA20) and all filters passing.
- **BEARISH SETUP** is the mirror image.
- **NEUTRAL SETUP** requires a neutral/uncertain regime, narrow Bollinger bands, balanced votes and RSI 40–60.
- **WAIT** is the default whenever a filter fails or votes are mixed. Most days are WAIT days. That is a feature.
- **INSUFFICIENT DATA** appears when fewer than 200 bars exist or any core indicator is NaN.

For every signal you also see: *which rules passed, which failed, what contradicts it, when it becomes invalid, which strategy is being
evaluated, the max possible loss (from the analyzer), and a hypothetical entry/exit plan*. There is no confidence percentage because
no honest one exists.
"""
    )
footer()
