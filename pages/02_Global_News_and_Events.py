"""Global News & Events — Phase 2 placeholder with an honest status and a manual event calendar."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from nifty_lab.ui.common import footer, setup_page

cfg = setup_page("Global News & Events")

st.warning(
    "**News intelligence is a Phase 2 feature.** No live feed is connected, so this page shows no headlines. "
    "The app will never display invented news. When connected, every item will carry its source, publication time and link, "
    "and confirmed facts will be separated from interpretation.",
    icon="📰",
)

st.subheader("Planned sources (official / reputable)")
sources = pd.DataFrame(
    [
        ["RBI press releases", "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx", "Policy decisions, inflation commentary", "RSS/HTML, official"],
        ["SEBI circulars", "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=7&smid=0", "Regulatory changes affecting F&O", "HTML, official"],
        ["NSE circulars", "https://www.nseindia.com/resources/exchange-communication-circulars", "Lot sizes, expiry changes, holidays", "HTML, official; respect ToS"],
        ["US Federal Reserve", "https://www.federalreserve.gov/newsevents/pressreleases.htm", "FOMC decisions", "RSS, official"],
        ["US BLS", "https://www.bls.gov/schedule/news_release/cpi.htm", "US CPI schedule", "HTML, official"],
        ["MOSPI (India)", "https://www.mospi.gov.in/", "India CPI/IIP releases", "HTML, official"],
        ["Reuters / Moneycontrol", "—", "Market headlines (licensing/ToS to be verified before use)", "Only via permitted feeds/APIs"],
    ],
    columns=["Source", "URL", "What it provides", "Access"],
)
st.dataframe(sources, width='stretch', hide_index=True)

st.subheader("Manual event calendar (user-entered)")
st.caption("Until automated feeds exist, note upcoming high-impact events here. They feed the Signal Monitor's event-risk warnings for this session.")
if "manual_events" not in st.session_state:
    st.session_state["manual_events"] = []
with st.form("add_event"):
    c1, c2, c3 = st.columns([1, 2, 1])
    d = c1.date_input("Date", value=date.today())
    desc = c2.text_input("Event (e.g. RBI MPC decision, US CPI, NIFTY monthly expiry)")
    impact = c3.selectbox("Impact", ["High", "Medium", "Low"])
    if st.form_submit_button("Add event") and desc.strip():
        st.session_state["manual_events"].append({"date": d.isoformat(), "event": desc.strip(), "impact": impact, "source": "user-entered"})
if st.session_state["manual_events"]:
    st.dataframe(pd.DataFrame(st.session_state["manual_events"]).sort_values("date"), width='stretch', hide_index=True)
else:
    st.info("No events entered.")

footer()
