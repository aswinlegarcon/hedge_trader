"""Trade Ticket — Paper, optional Sandbox, user-confirmed Live (Spec 08)."""
from __future__ import annotations

import streamlit as st

from nifty_lab.ui.common import footer, setup_page
from nifty_lab.ui.trade_ticket import render_trade_ticket

setup_page("Trade Ticket")
render_trade_ticket()
footer()
