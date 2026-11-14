"""NIFTY Signal Lab — Streamlit entry point.

Run:  streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="NIFTY Signal Lab", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

PAGES = [
    st.Page("pages/01_Market_Overview.py", title="Market Overview", icon="🏠", default=True),
    st.Page("pages/02_Global_News_and_Events.py", title="Global News & Events", icon="📰"),
    st.Page("pages/03_NIFTY_Technical_Analysis.py", title="NIFTY Technical Analysis", icon="📊"),
    st.Page("pages/04_Options_Strategy_Analyzer.py", title="Options Strategy Analyzer", icon="🧮"),
    st.Page("pages/05_Signal_Monitor.py", title="Signal Monitor", icon="🚦"),
    st.Page("pages/06_Risk_Dashboard.py", title="Risk Dashboard", icon="🛡️"),
    st.Page("pages/07_Backtesting_Lab.py", title="Backtesting Lab", icon="🧪"),
    st.Page("pages/08_Paper_Trading_Journal.py", title="Paper Trading Journal", icon="📓"),
    st.Page("pages/09_Learning_Center.py", title="Learning Center", icon="🎓"),
    st.Page("pages/10_Settings_and_API_Connections.py", title="Settings & API Connections", icon="⚙️"),
    st.Page("pages/11_Watchlist_Research.py", title="Watchlist Research", icon="📋"),
    st.Page("pages/12_Trade_Ticket.py", title="Trade Ticket", icon="🎫"),
    st.Page("pages/13_Paper_Account.py", title="Paper Account", icon="📒"),
]

nav = st.navigation(PAGES)
st.sidebar.markdown(
    "**NIFTY Signal Lab** · execution-v1  \n"
    ":orange[Paper default · Live requires explicit confirm on Trade Ticket]"
)
nav.run()
