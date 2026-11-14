"""Watchlist Research — manual multi-timeframe comparison (Spec 05)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from nifty_lab.brokers.upstox_market_data import UpstoxMarketDataService
from nifty_lab.config import PROVISIONAL_WATCHLIST
from nifty_lab.research import WatchlistRefreshService
from nifty_lab.ui.common import candlestick_figure, footer, setup_page
from nifty_lab.ui.macro_calendar import render_watchlist_macro_panel
from nifty_lab.ui.watchlist_news import (
    get_snapshot,
    invalidate_news_if_keys_changed,
    render_news_panel,
    run_refresh_news,
)

cfg = setup_page("Watchlist Research")
_news_snap = get_snapshot()
_news_line = (
    f"Upstox company news last checked {_news_snap.retrieved_at.strftime('%Y-%m-%d %H:%M UTC')}; "
    "macro/scheduled events NOT CHECKED."
    if _news_snap and not _news_snap.refresh_failed
    else "Company news NOT CHECKED until you refresh news (shared with Global News page); macro calendar optional import on Global News."
)
st.caption(
    f"Manual comparison of provisional research labels. Descriptive facts only — "
    f"no orders, no funded-paper qualification. {_news_line}"
)
st.info(
    f"Profile **{cfg.profile_id}** · funded-paper qualification remains **blocked** "
    f"(₹{cfg.risk.capital:,.0f} / ₹{cfg.risk.max_drawdown:,.0f} loss ceiling).",
    icon="🛡️",
)

if st.button("Refresh watchlist (sequential)", type="primary"):
    with st.spinner("Fetching daily + 5m for each instrument (bounded requests)…"):
        bundle = WatchlistRefreshService(UpstoxMarketDataService()).refresh()
        st.session_state["watchlist_bundle"] = bundle
        invalidate_news_if_keys_changed([o.instrument_key for o in bundle.observations if o.instrument_key])

bundle = st.session_state.get("watchlist_bundle")
if bundle is None:
    st.warning(f"Click **Refresh watchlist** to load: {', '.join(PROVISIONAL_WATCHLIST)}")
    footer()
    st.stop()

rows = []
for o in bundle.observations:
    rows.append(
        {
            "Label": o.research_label,
            "Symbol": o.trading_symbol or "—",
            "Daily date / trend": f"{o.daily_context_date} · {o.daily_trend}",
            "5m completed / close": f"{o.m5_completed_at or '—'} · {o.m5_close}",
            "EMA (5m)": o.ema_relation,
            "Session VWAP": o.vwap_relation,
            "Support / resistance": f"{o.nearest_support} / {o.nearest_resistance}",
            "Level cross": o.level_observation,
            "Rel. volume": o.rel_volume,
            "State": o.data_state,
        }
    )
st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

pick = st.selectbox("Detail card", [o.research_label for o in bundle.observations])
obs = next(o for o in bundle.observations if o.research_label == pick)
st.subheader(f"{obs.display_name or obs.research_label}")
st.write(f"**Instrument key:** `{obs.instrument_key or 'n/a'}` · **Data state:** {obs.data_state}")
st.write(f"**Summary:** {obs.summary}")
st.write(f"**Diagnostic:** {obs.diagnostic or '—'}")
for lim in obs.limitations:
    st.caption(f"• {lim}")

st.markdown("#### Company news (Upstox)")
nc1, nc2 = st.columns(2)
with nc1:
    if st.button("Refresh news for watchlist"):
        run_refresh_news(bundle, page_number=1)
with nc2:
    snap = get_snapshot()
    if snap and snap.has_more_pages and snap.page_number < 2:
        if st.button("Load next news page"):
            run_refresh_news(bundle, page_number=2)
render_news_panel(get_snapshot(), obs.instrument_key if obs.instrument_key else None)

render_watchlist_macro_panel(obs.research_label)

frames = bundle.frames.get(pick)
if frames is not None:
    st.markdown("#### Daily context (completed bars)")
    st.line_chart(frames.daily["close"].tail(120))
    st.markdown("#### Five-minute (completed bars)")
    tail = frames.m5.tail(min(78, len(frames.m5)))
    st.plotly_chart(
        candlestick_figure(tail, title=f"{obs.trading_symbol} · 5m completed", use_datetime_index=True),
        width="stretch",
    )
else:
    st.info("No chart — fetch failed or resolution incomplete for this row.")

footer()
