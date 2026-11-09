"""Settings & API Connections — status only; secrets are never displayed or requested here."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from nifty_lab.brokers import ALL_BROKERS, ConnectionState
from nifty_lab.config import credential_status
from nifty_lab.contracts import CONTRACTS
from nifty_lab.options import DEFAULT_COSTS
from nifty_lab.ui.common import footer, inr, setup_page

cfg = setup_page("Settings & API Connections")

st.error("**Live trading: DISABLED (hard-coded in v1).** There is no order-placement code in this application. Enabling it requires a separate design review.", icon="🔒")

st.subheader("Broker connections (read-only)")
for b in ALL_BROKERS:
    s = b.status()
    icon = {"CONNECTED": "🟢", "CONFIGURED (not connected)": "🟡", "NOT CONFIGURED": "⚪", "ERROR": "🔴"}[s.state.value]
    with st.container(border=True):
        st.markdown(f"{icon} **{s.name}** — {s.state.value}")
        st.write(s.detail)
        st.caption(f"Docs: {s.docs_url} · {s.pricing_note}")

st.subheader("Credential presence (values are never shown)")
rows = [{"Broker": broker, "Variable": var, "Set": "✅" if ok else "❌"} for broker, vars_ in credential_status().items() for var, ok in vars_.items()]
st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
st.markdown(
    """
**How to configure (do NOT paste secrets into any chat or into this page):**
1. Copy `.env.example` to `.env` in the project folder.
2. Fill `KITE_API_KEY` / `KITE_API_SECRET` from https://developers.kite.trade (₹500/month per app, verified 2026-11-09). `.env` is git-ignored.
3. Kite's `access_token` must be generated daily through the official login flow (expires 06:00 IST). Phase 2 will add a guided, in-browser flow using the official `kiteconnect` SDK — never an unofficial bypass.
4. Kotak Neo uses the official `kotak-neo-python` SDK with TOTP + MPIN at login time; those are entered interactively and never stored.
5. Restart the app. This page only reports whether each variable is set.
"""
)

st.subheader("Risk budget (from .env, NSL_* variables)")
r = cfg.risk
st.dataframe(pd.DataFrame({"Setting": ["Capital", "Max drawdown", "Per-trade risk min", "Per-trade risk max", "Portfolio risk cap", "Concentration cap / underlying", "Max open positions"], "Value": [inr(r.capital), inr(r.max_drawdown), inr(r.risk_per_trade_min), inr(r.risk_per_trade_max), inr(r.max_portfolio_risk_pct * r.capital), inr(r.max_single_underlying_pct * r.capital), r.max_open_positions]}), hide_index=True, width='stretch')

st.subheader("Contract specifications in use")
st.dataframe(pd.DataFrame([{"Symbol": c.symbol, "Lot size": c.lot_size, "Strike step": c.strike_interval, "Weekly expiry": c.has_weekly_expiry, "Verified on": c.verified_on.isoformat(), "Source": c.source} for c in CONTRACTS.values()]), hide_index=True, width='stretch')

st.subheader("Transaction-cost schedule")
cs = DEFAULT_COSTS
st.dataframe(pd.DataFrame({"Charge": ["Brokerage / order", "STT (sell premium)", "STT (exercise, intrinsic)", "NSE txn charge (premium)", "SEBI fee", "Stamp duty (buy)", "GST"], "Rate": [f"₹{cs.brokerage_per_order:.0f}", f"{cs.stt_sell_pct:.3%}", f"{cs.stt_exercise_pct:.3%}", f"{cs.exchange_txn_pct:.5%}", "₹10 / crore", f"{cs.stamp_duty_buy_pct:.3%}", f"{cs.gst_pct:.0%} on brokerage+txn+SEBI"]}), hide_index=True, width='stretch')
st.caption(f"Verified {cs.verified_on} — {cs.source}. Kotak Neo brokerage differs by plan.")

st.subheader("Regulatory notes (verified 2026-11-09)")
st.markdown(
    """
- SEBI circular SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013 (4-Feb-2025) governs retail algorithmic trading via broker APIs: brokers must
  provide API access through unique API keys with **static-IP whitelisting**, and order flows above exchange-specified per-second thresholds
  must be registered as algos. Exchange implementation standards came into force during 2025–2026. **This app sends no orders**, so it is a
  read-only data consumer, but any future execution feature must be designed against this framework.
- Kite Connect access tokens expire daily at 06:00 (regulatory requirement) — automated token harvesting is not permitted; use the official flow.
- Option contract specs (lot sizes, expiry days) have changed several times since 2024; re-verify before each month.
"""
)
footer()
