"""TradingView Lightweight Charts — Streamlit custom component (persistent instance)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit.components.v1 as components

_FRONTEND = Path(__file__).resolve().parent / "frontend"
_lwc_component = components.declare_component("nsl_spec14_lwc", path=str(_FRONTEND))


def render_candlestick_chart(
    *,
    bars: list[dict],
    reset: bool = False,
    component_key: str = "spec14-lwc",
) -> dict[str, Any] | None:
    """Update chart via component bridge; returns instance metadata from the browser."""
    value = _lwc_component(bars=bars, reset=reset, key=component_key, default=None)
    return value if isinstance(value, dict) else None