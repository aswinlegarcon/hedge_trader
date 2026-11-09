"""Market Overview — home page."""
from __future__ import annotations

import streamlit as st

from nifty_lab.brokers import ALL_BROKERS, ConnectionState
from nifty_lab.signals import evaluate
from nifty_lab.ui.common import candlestick_figure, footer, indicator_frame, inr, provenance_banner, setup_page, sidebar_data_source

cfg = setup_page("Market Overview")
ds = sidebar_data_source()
provenance_banner(ds)

st.info(
    "**Version 1 — read-only research build.** No order placement exists anywhere in this code base. "
    "Live market data for the instruments below arrives in Phase 2 once a read-only broker API is configured; "
    "until then every tile that lacks a data source says so explicitly.",
    icon="🛡️",
)

# --- Indian markets -----------------------------------------------------------
st.subheader("Indian markets")
cols = st.columns(6)
tiles = ["NIFTY 50", "BANK NIFTY", "NIFTY Next 50", "India VIX", "Sector indices", "Market breadth"]
for col, name in zip(cols, tiles):
    with col:
        if name == "NIFTY 50" and ds is not None:
            df = ds.df
            chg = df["close"].iloc[-1] / df["close"].iloc[-2] - 1 if len(df) > 1 else 0.0
            label = "NIFTY 50 (SYNTHETIC)" if ds.provenance.is_synthetic else f"NIFTY 50 ({ds.provenance.symbol})"
            st.metric(label, f"{df['close'].iloc[-1]:,.2f}", f"{chg:+.2%}")
            st.caption(f"Last bar {df.index[-1].date()} · {ds.provenance.kind.value}")
        else:
            st.metric(name, "NO DATA")
            st.caption("Source not configured")

# --- Global markets -----------------------------------------------------------
st.subheader("Global markets")
gcols = st.columns(6)
for col, name in zip(gcols, ["S&P 500", "Nasdaq", "US 10Y yield", "USD/INR", "Brent crude", "Gold"]):
    with col:
        st.metric(name, "NO DATA")
        st.caption("Phase 2 source")

st.caption("Tiles show **NO DATA** rather than a guessed value. The app never invents live market information.")

# --- Chart + headline signal ----------------------------------------------------
if ds is not None:
    ind = indicator_frame(ds.df)
    report = evaluate(ind)
    left, right = st.columns([3, 1])
    with left:
        tail = ind.tail(250)
        fig = candlestick_figure(tail, overlays={"SMA 20": tail["sma20"], "SMA 50": tail["sma50"], "SMA 200": tail["sma200"]}, title=f"{ds.provenance.symbol} — daily (last 250 bars)")
        st.plotly_chart(fig, width='stretch')
    with right:
        st.markdown("#### Headline signal")
        st.metric("Signal", report.signal.value)
        st.metric("Regime", report.regime.value)
        st.metric("RSI 14", f"{report.indicator_values.get('rsi14', float('nan')):.1f}" if report.signal.value != "INSUFFICIENT DATA" else "n/a")
        st.metric("ATR 14", f"{report.indicator_values.get('atr14', float('nan')):,.0f}" if report.signal.value != "INSUFFICIENT DATA" else "n/a")
        st.metric("Vol regime", str(report.indicator_values.get("vol_regime", "n/a")))
        st.caption(f"As of {report.as_of.date() if report.as_of is not None else 'n/a'} · see Signal Monitor for every rule.")
        if report.reasons_to_avoid:
            st.warning("Reasons to avoid: " + " ".join(report.reasons_to_avoid[:2]))

# --- Connection status -------------------------------------------------------------
st.subheader("Connections & risk budget")
c1, c2 = st.columns(2)
with c1:
    for b in ALL_BROKERS:
        s = b.status()
        icon = "🟢" if s.state == ConnectionState.CONNECTED else ("🟡" if s.state == ConnectionState.CONFIGURED_NOT_CONNECTED else "⚪")
        st.write(f"{icon} **{s.name}** — {s.state.value}. {s.detail}")
with c2:
    r = cfg.risk
    st.write(f"Capital **{inr(r.capital)}** · max drawdown **{inr(r.max_drawdown)}** ({r.max_drawdown_pct:.0%}) · per-trade risk **{inr(r.risk_per_trade_min)}–{inr(r.risk_per_trade_max)}**")
    st.write(f"Portfolio risk cap **{inr(r.max_portfolio_risk_pct * r.capital)}** · max open positions **{r.max_open_positions}**")

footer()
