"""Backtesting Lab — archived Spec 09 results review (read-only)."""
from __future__ import annotations

import streamlit as st

from nifty_lab.research.results_review.dashboard import render_archived_results_review
from nifty_lab.ui.common import footer, setup_page

setup_page("Backtesting Lab")

st.warning(
    "**EXPLORATORY / INSUFFICIENT EVIDENCE** — Archived ICICIBANK daily pullback research only. "
    "Not validated for Live or forward paper. **2025 holdout: NOT EVALUATED.**",
    icon="🧪",
)

render_archived_results_review()

st.divider()
st.subheader("Phase 3 engine (not delivered)")
st.markdown(
    """
The event-driven options/index backtest engine described in earlier Phase 3 notes is **still not implemented**.
Synthetic learning controls elsewhere in the app are unrelated to these archived broker-candle experiments.
"""
)
footer()
