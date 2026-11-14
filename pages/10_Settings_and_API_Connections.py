"""Settings & API Connections — status only; secrets are never displayed or requested here."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from nifty_lab.brokers import ALL_BROKERS, ConnectionState
from nifty_lab.config import PROVISIONAL_WATCHLIST, credential_status, legacy_conflict_message
from nifty_lab.contracts import CONTRACTS
from nifty_lab.options import DEFAULT_COSTS
from nifty_lab.ui.common import footer, inr, setup_page
from nifty_lab.ui.upstox_auth_ui import render_upstox_auth_section

cfg = setup_page("Settings & API Connections")

st.error("**Live trading: DISABLED (hard-coded).** No order-placement code exists. Spec 03 adds Upstox offline status only.", icon="🔒")

if cfg.legacy_env_conflict:
    st.warning(legacy_conflict_message())

st.subheader("Revised research profile (Spec 03)")
r = cfg.risk
st.dataframe(
    pd.DataFrame(
        {
            "Setting": [
                "Profile",
                "Initial capital",
                "Total loss / drawdown ceiling",
                "Per-position risk ceiling",
                "Portfolio risk cap (interim)",
                "Concentration cap / underlying",
                "Max open positions",
                "Provisional watchlist (labels only)",
            ],
            "Value": [
                cfg.profile_id,
                inr(r.capital),
                f"{inr(r.max_drawdown)} ({r.max_drawdown_pct:.0%})",
                "Unconfirmed — user must set a ceiling ≤ portfolio limit",
                inr(r.max_portfolio_risk_pct * r.capital),
                inr(r.max_single_underlying_pct * r.capital),
                r.max_open_positions,
                ", ".join(PROVISIONAL_WATCHLIST),
            ],
        }
    ),
    hide_index=True,
    width="stretch",
)

render_upstox_auth_section()

st.subheader("Broker (read-only status — Upstox only)")
for b in ALL_BROKERS:
    s = b.status()
    icon = {"CONNECTED": "🟢", "CONFIGURED (not connected)": "🟡", "NOT CONFIGURED": "⚪", "ERROR": "🔴"}[s.state.value]
    with st.container(border=True):
        st.markdown(f"{icon} **{s.name}** — {s.state.value}")
        st.write(s.detail)
        st.caption(f"Docs: {s.docs_url} · {s.pricing_note}")

st.subheader("Credential presence (values are never shown)")
rows = [{"Broker": broker, "Variable": var, "Set": "✅" if ok else "❌"} for broker, vars_ in credential_status().items() for var, ok in vars_.items()]
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
st.markdown(
    """
**How to configure (do NOT paste secrets into any chat or into this page):**
1. Copy `.env.example` to `.env` in the project folder.
2. Add `UPSTOX_*` placeholders when you are ready for a future read-only integration spec. `.env` is git-ignored.
3. **Market data:** use **Reconnect Upstox** above (official login; token installed server-side, no restart). The legacy `UPSTOX_ACCESS_TOKEN` in `.env` still works as the initial path; a managed token takes precedence over it. Never paste a token into Streamlit or chat. See `docs/spec_16/operator-guide.md`.
4. Legacy Kite/Kotak variables are not used for data access in this build.
5. Current specs: [spec_03](../spec_03/README.md), [spec_04](../spec_04/README.md). Historical broker notes: [RESEARCH.md](../RESEARCH.md).
"""
)

st.subheader("Contract specifications in use (index options — educational)")
st.dataframe(
    pd.DataFrame(
        [
            {
                "Symbol": c.symbol,
                "Lot size": c.lot_size,
                "Strike step": c.strike_interval,
                "Weekly expiry": c.has_weekly_expiry,
                "Verified on": c.verified_on.isoformat(),
                "Source": c.source,
            }
            for c in CONTRACTS.values()
        ]
    ),
    hide_index=True,
    width="stretch",
)

st.subheader("Transaction-cost schedule (legacy options estimate)")
cs = DEFAULT_COSTS
st.dataframe(
    pd.DataFrame(
        {
            "Charge": [
                "Brokerage / order",
                "STT (sell premium)",
                "STT (exercise, intrinsic)",
                "NSE txn charge (premium)",
                "SEBI fee",
                "Stamp duty (buy)",
                "GST",
            ],
            "Rate": [
                f"₹{cs.brokerage_per_order:.0f}",
                f"{cs.stt_sell_pct:.3%}",
                f"{cs.stt_exercise_pct:.3%}",
                f"{cs.exchange_txn_pct:.5%}",
                "₹10 / crore",
                f"{cs.stamp_duty_buy_pct:.3%}",
                f"{cs.gst_pct:.0%} on brokerage+txn+SEBI",
            ],
        }
    ),
    hide_index=True,
    width="stretch",
)
st.caption(
    f"Verified {cs.verified_on} — {cs.source}. **Not** verified Upstox equity/ETF costs; educational options math only."
)

st.subheader("Regulatory notes")
st.markdown(
    """
- SEBI retail API / algorithmic-trading circulars apply to any future execution feature. **This app sends no orders.**
- Option contract specs (lot sizes, expiry days) change frequently — re-verify before trading.
- Upstox OAuth and historical candles: official docs only; entitlements for this account are unverified.
"""
)
footer()
