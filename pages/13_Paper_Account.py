"""Paper Account — read-only results from local execution ledger."""
from __future__ import annotations

import streamlit as st

from nifty_lab.paper_account.ui import render_paper_account_results
from nifty_lab.ui.common import footer, setup_page

setup_page("Paper Account")

st.warning(
    "**LOCAL PAPER** — Operational visibility only. Not a broker account, not validated strategy performance. "
    "**Live disabled here.** Stored marks are not live quotes.",
    icon="📒",
)

render_paper_account_results()

footer()
