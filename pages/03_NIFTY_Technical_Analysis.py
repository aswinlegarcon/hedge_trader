"""NIFTY Technical Analysis — indicators with beginner explanations."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from nifty_lab.indicators import explain, support_resistance_levels
from nifty_lab.ui.common import (
    candlestick_figure,
    chart_interval_label,
    footer,
    indicator_frame,
    is_intraday_broker,
    line_panel,
    provenance_banner,
    setup_page,
    sidebar_data_source,
)

cfg = setup_page("Technical Analysis")
ds = sidebar_data_source()
provenance_banner(ds)
if ds is None:
    st.stop()

ind = indicator_frame(ds.df)
st.sidebar.header("Chart options")
lookback = st.sidebar.slider("Bars to display", 60, min(1000, len(ind)), min(250, len(ind)), step=10)
show = st.sidebar.multiselect("Overlays", ["SMA 20", "SMA 50", "SMA 200", "EMA 9", "EMA 21", "Bollinger Bands", "Support/Resistance"], default=["SMA 20", "SMA 50", "SMA 200", "Support/Resistance"])
tail = ind.tail(lookback)

overlays = {}
col_map = {"SMA 20": "sma20", "SMA 50": "sma50", "SMA 200": "sma200", "EMA 9": "ema9", "EMA 21": "ema21"}
for label, col in col_map.items():
    if label in show:
        overlays[label] = tail[col]
bands = (tail["bb_upper"], tail["bb_lower"]) if "Bollinger Bands" in show else None
levels = support_resistance_levels(ind, as_of=ind.index[-1]) if "Support/Resistance" in show else None

last = ind.iloc[-1]
m = st.columns(6)
m[0].metric("Close", f"{last['close']:,.2f}")
m[1].metric("RSI 14", f"{last['rsi14']:.1f}" if pd.notna(last["rsi14"]) else "n/a")
m[2].metric("ATR 14", f"{last['atr14']:,.0f} ({last['atr_pct']:.2%})" if pd.notna(last["atr14"]) else "n/a")
m[3].metric("MACD hist", f"{last['hist']:,.1f}" if pd.notna(last["hist"]) else "n/a")
if is_intraday_broker(ds):
    m[4].metric("Realised vol 20d", "n/a (5m data)")
    m[5].metric("Vol regime", "n/a (5m data)")
else:
    m[4].metric("Realised vol 20d", f"{last['rv20']:.1%}" if pd.notna(last["rv20"]) else "n/a")
    m[5].metric("Vol regime", str(last["vol_regime"]))
st.caption(
    f"Symbol **{ds.provenance.symbol}** · {chart_interval_label(ds)} bars · "
    f"last bar {ind.index[-1]} · SMA labels refer to bars on this timeframe, not calendar days unless daily."
)

st.plotly_chart(
    candlestick_figure(
        tail,
        overlays=overlays,
        title=f"{ds.provenance.symbol} · {chart_interval_label(ds)}",
        bands=bands,
        levels=levels,
        use_datetime_index=not is_intraday_broker(ds),
    ),
    width="stretch",
)

t1, t2, t3, t4 = st.tabs(["Momentum", "Volatility", "Volume & levels", "Indicator table"])
with t1:
    st.plotly_chart(line_panel({"RSI 14": tail["rsi14"]}, "RSI 14", hlines=[(70, "overbought"), (30, "oversold")]), width='stretch')
    st.plotly_chart(line_panel({"MACD": tail["macd"], "Signal": tail["signal"], "Histogram": tail["hist"]}, "MACD (12, 26, 9)", hlines=[(0, "")]), width='stretch')
    with st.expander("What do these mean?"):
        st.write("**RSI** — " + explain("rsi14"))
        st.write("**MACD** — " + explain("macd"))
        st.write("**EMA 9 / 21** — " + explain("ema9") + " " + explain("ema21"))
with t2:
    st.plotly_chart(line_panel({"ATR 14": tail["atr14"]}, "ATR 14 (points)"), width='stretch')
    st.plotly_chart(line_panel({"BB width": tail["bb_width"]}, "Bollinger band width (relative)"), width='stretch')
    if not is_intraday_broker(ds):
        st.plotly_chart(line_panel({"Realised vol 20d": tail["rv20"]}, "Annualised realised volatility"), width="stretch")
    else:
        st.info("Realised volatility annualisation is unavailable on 5-minute broker data in this slice.")
    with st.expander("What do these mean?"):
        for k in ("atr14", "bollinger", "vol_regime", "rv20"):
            st.write(f"**{k}** — {explain(k)}")
with t3:
    st.plotly_chart(line_panel({"Volume / 20d avg": tail["vol_ratio"]}, "Relative volume", hlines=[(1.0, "average"), (1.5, "high")]), width='stretch')
    lv = support_resistance_levels(ind, as_of=ind.index[-1])
    c1, c2 = st.columns(2)
    c1.write("**Support zones (nearest first)**")
    c1.write(", ".join(f"{x:,.0f}" for x in lv["support"]) or "none detected")
    c2.write("**Resistance zones (nearest first)**")
    c2.write(", ".join(f"{x:,.0f}" for x in lv["resistance"]) or "none detected")
    with st.expander("What do these mean?"):
        st.write("**Volume** — " + explain("volume"))
        st.write("**Support/Resistance** — " + explain("support_resistance"))
        st.write("**VWAP** — " + explain("vwap") + " (not shown: this is daily data)")
with t4:
    cols = ["open", "high", "low", "close", "volume", "sma20", "sma50", "sma200", "ema9", "ema21", "rsi14", "macd", "signal", "hist", "atr14", "bb_upper", "bb_lower", "rv20", "vol_regime", "vol_ratio"]
    st.dataframe(tail[cols].iloc[::-1].round(2), width='stretch', height=400)
    st.download_button("Download indicator CSV", ind[cols].to_csv().encode(), file_name="indicators.csv", mime="text/csv")

footer()
