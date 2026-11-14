"""ICICIBANK 5m streaming chart prototype (Spec 14)."""
from __future__ import annotations

from nifty_lab.stream_chart.ui import render_stream_chart_page
from nifty_lab.ui.common import footer, setup_page

setup_page("Stream Chart")
render_stream_chart_page()
footer()