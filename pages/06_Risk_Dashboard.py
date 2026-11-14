"""Risk Dashboard — budget, exposure, drawdown and concentration from the paper journal."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from nifty_lab.risk import OpenPosition, PortfolioSnapshot, drawdown_series, evaluate_portfolio
from nifty_lab.ui.common import footer, get_journal, inr, setup_page

cfg = setup_page("Risk Dashboard")
journal = get_journal(cfg)
r = cfg.risk

st.caption(
    "Figures below come from the PAPER journal (simulations). They do **not** supply reconciled account valuation for funded-paper "
    "qualification — marks default to zero for dashboard display only."
)
if cfg.legacy_env_conflict:
    st.warning("Legacy NSL_* overrides — funded-paper qualification disabled (Settings).")

open_df = journal.entries(status="OPEN")
closed_df = journal.entries(status="CLOSED")
open_positions = [OpenPosition(str(row["id"]), str(row["instrument"]).split()[0], str(row["strategy"]), float(row["max_risk_inr"] or 0), str(row["instrument"]), str(row["trade_date"])) for _, row in open_df.iterrows()]
realised = journal.realised_pnl_inr()

equity_curve = pd.Series([r.capital], index=pd.to_datetime(["1970-01-01"]))
if not closed_df.empty:
    cl = closed_df.sort_values("closed_at")
    equity_curve = pd.Series(r.capital + cl["realised_pnl_inr"].astype(float).cumsum().values, index=pd.to_datetime(cl["closed_at"]))
    equity_curve = pd.concat([pd.Series([r.capital], index=[equity_curve.index[0] - pd.Timedelta(days=1)]), equity_curve])
peak = float(equity_curve.max())
snap = PortfolioSnapshot(capital=r.capital, open_positions=open_positions, realised_pnl_inr=realised, peak_equity_inr=peak)
issues = evaluate_portfolio(snap, r)

m = st.columns(6)
m[0].metric("Capital", inr(r.capital))
m[1].metric("Paper equity", inr(snap.equity_inr), f"{realised:+,.0f}")
m[2].metric("Open risk (sum of max losses)", inr(snap.open_risk_inr), f"cap {inr(r.max_portfolio_risk_pct * r.capital)}", delta_color="off")
m[3].metric("Drawdown", inr(snap.drawdown_inr), f"limit {inr(r.max_drawdown)}", delta_color="off")
m[4].metric("Worst-case equity", inr(snap.worst_case_equity_inr), help="If every open paper position hits its maximum loss")
m[5].metric("Open positions", f"{len(open_positions)} / {r.max_open_positions}")

if issues:
    for i in issues:
        (st.error if i.startswith("BREACH") else st.warning)(i)
else:
    st.success("No risk-rule breaches in the paper portfolio.")

g1, g2 = st.columns(2)
with g1:
    used = snap.open_risk_inr
    cap = r.max_portfolio_risk_pct * r.capital
    fig = go.Figure(go.Indicator(mode="gauge+number", value=used, number={"prefix": "₹"}, title={"text": "Open risk vs portfolio cap"}, gauge={"axis": {"range": [0, cap]}, "bar": {"color": "#d73027" if used > cap else "#1a9850"}, "steps": [{"range": [0, cap * 0.7], "color": "rgba(26,152,80,0.15)"}, {"range": [cap * 0.7, cap], "color": "rgba(254,196,79,0.3)"}]}))
    fig.update_layout(height=280, margin=dict(l=30, r=30, t=50, b=10))
    st.plotly_chart(fig, width='stretch')
with g2:
    dd = snap.drawdown_inr
    fig = go.Figure(go.Indicator(mode="gauge+number", value=dd, number={"prefix": "₹"}, title={"text": "Drawdown vs limit"}, gauge={"axis": {"range": [0, r.max_drawdown]}, "bar": {"color": "#d73027" if dd >= r.max_drawdown else "#1f77b4"}}))
    fig.update_layout(height=280, margin=dict(l=30, r=30, t=50, b=10))
    st.plotly_chart(fig, width='stretch')

st.subheader("Exposure by underlying")
exp = snap.exposure_by_underlying()
if exp:
    st.bar_chart(pd.Series(exp, name="max loss ₹"))
else:
    st.info("No open paper positions.")

st.subheader("Paper equity & drawdown")
if len(equity_curve) > 1:
    ddf = drawdown_series(equity_curve)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ddf.index, y=ddf["equity"], name="Equity", mode="lines+markers"))
    fig.add_trace(go.Scatter(x=ddf.index, y=ddf["peak"], name="Peak", line=dict(dash="dot")))
    fig.add_hline(y=r.capital - r.max_drawdown, line=dict(color="red", dash="dash"), annotation_text="max drawdown floor")
    fig.update_layout(height=320, margin=dict(l=40, r=40, t=30, b=30))
    st.plotly_chart(fig, width='stretch')
else:
    st.info("Close at least one paper position to see an equity curve.")

st.subheader("Risk rules in force")
st.write(
    f"""
- Profile **{cfg.profile_id}** · per-position max contractual loss: **{"unconfirmed" if r.risk_per_trade_max is None else inr(r.risk_per_trade_max)}** (no minimum size)
- Portfolio open-risk cap: **{r.max_portfolio_risk_pct:.0%} of capital = {inr(r.max_portfolio_risk_pct * r.capital)}**
- Concentration cap per underlying: **{r.max_single_underlying_pct:.0%} = {inr(r.max_single_underlying_pct * r.capital)}**
- Max open positions: **{r.max_open_positions}** · Max drawdown: **{inr(r.max_drawdown)}** ({r.max_drawdown_pct:.0%})
- Unbounded-risk positions (naked options) are never eligible.
- A stop-loss is an *instruction*; it never guarantees the exit price. Eligibility always uses the theoretical maximum spread loss.
- Event-risk warnings come from the manual event calendar (Global News page) until feeds exist.
"""
)
st.caption(
    "Daily / weekly risk reports: Paper Trading Journal. Active profile is ₹20,000 / ₹2,000 loss ceiling (Spec 03); "
    "legacy NSL_* overrides block qualification — see docs/spec_03/."
)
footer()
