"""Shared Streamlit helpers: data loading/caching, banners, status widgets."""
from __future__ import annotations

import io
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from ..config import AppConfig, load_config
from ..data import DataKind, MarketDataset, generate_synthetic_nifty, load_ohlcv_csv
from ..indicators import compute_indicator_frame
from ..journal import Journal

PAGE_ICON = "📈"
DISCLAIMER = (
    "Research and education only. Nothing here is investment advice. Version 1 places NO live trades. "
    "Technical signals are not profitable trades; past patterns do not guarantee future results."
)


def setup_page(title: str) -> AppConfig:
    st.markdown(
        """<style>
        .block-container{padding-top:1.2rem;}
        div[data-testid="stMetric"]{background:rgba(128,128,128,0.08);border-radius:8px;padding:8px 12px;}
        .nsl-banner{padding:8px 12px;border-radius:6px;font-size:0.9rem;margin-bottom:8px;}
        .nsl-syn{background:#7a4b00;color:#fff;}
        .nsl-csv{background:#0b5394;color:#fff;}
        .nsl-off{background:#555;color:#fff;}
        </style>""",
        unsafe_allow_html=True,
    )
    cfg = load_config()
    st.title(title)
    return cfg


def get_journal(cfg: AppConfig) -> Journal:
    if "journal" not in st.session_state:
        st.session_state["journal"] = Journal(cfg.db_path)
    return st.session_state["journal"]


@st.cache_data(show_spinner=False)
def _synthetic(seed: int) -> MarketDataset:
    return generate_synthetic_nifty(seed=seed)


def _dataset_from_upload(file) -> MarketDataset:
    return load_ohlcv_csv(io.BytesIO(file.getvalue()), symbol=file.name.rsplit(".", 1)[0].upper())


def sidebar_data_source() -> MarketDataset | None:
    """Sidebar control shared by all pages. Returns the active dataset or None."""
    st.sidebar.header("Data source")
    choice = st.sidebar.radio("Select", ["Synthetic sample (demo)", "Import CSV (historical)", "Broker API (Phase 2)"], index=0, label_visibility="collapsed")
    ds: MarketDataset | None = None
    if choice.startswith("Synthetic"):
        seed = st.sidebar.number_input("Synthetic seed", 1, 9999, 42, help="Different seeds produce different fake price paths.")
        ds = _synthetic(int(seed))
    elif choice.startswith("Import"):
        up = st.sidebar.file_uploader("OHLCV CSV", type=["csv"], help="Columns: date, open, high, low, close, volume")
        if up is not None:
            try:
                ds = _dataset_from_upload(up)
                st.session_state["uploaded_dataset"] = ds
            except Exception as exc:  # show the validation error plainly
                st.sidebar.error(f"CSV rejected: {exc}")
        elif "uploaded_dataset" in st.session_state:
            ds = st.session_state["uploaded_dataset"]
        else:
            st.sidebar.info("Upload a CSV to continue. Sample file: data/sample/nifty_synthetic_daily.csv")
    else:
        st.sidebar.warning("Live read-only broker data arrives in Phase 2. Configure keys on the Settings page.")
    if ds is not None:
        st.session_state["active_dataset"] = ds
    return ds


def provenance_banner(ds: MarketDataset | None) -> None:
    if ds is None:
        st.markdown('<div class="nsl-banner nsl-off">NO DATA SOURCE ACTIVE — select one in the sidebar.</div>', unsafe_allow_html=True)
        return
    p = ds.provenance
    css = "nsl-syn" if p.kind == DataKind.SYNTHETIC else "nsl-csv"
    label = "SYNTHETIC DATA (not real market data)" if p.kind == DataKind.SYNTHETIC else f"IMPORTED CSV: {p.source}"
    last = p.last_bar_time.strftime("%Y-%m-%d") if p.last_bar_time else "n/a"
    st.markdown(
        f'<div class="nsl-banner {css}"><b>{label}</b> · symbol {p.symbol} · last bar {last} · {p.freshness_label()} · '
        f'{len(ds.df)} bars · retrieved {p.retrieved_at.strftime("%Y-%m-%d %H:%M UTC")}</div>',
        unsafe_allow_html=True,
    )
    if p.notes:
        st.caption(p.notes)


def footer() -> None:
    st.divider()
    st.caption(DISCLAIMER)


@st.cache_data(show_spinner=False)
def indicator_frame(df: pd.DataFrame) -> pd.DataFrame:
    return compute_indicator_frame(df)


def candlestick_figure(df: pd.DataFrame, overlays: dict[str, pd.Series] | None = None, title: str = "", show_volume: bool = True, bands: tuple[pd.Series, pd.Series] | None = None, levels: dict[str, list[float]] | None = None) -> go.Figure:
    rows = 2 if show_volume else 1
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25] if show_volume else [1.0])
    fig.add_trace(go.Candlestick(x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"], name="OHLC", increasing_line_color="#1a9850", decreasing_line_color="#d73027"), row=1, col=1)
    if bands is not None:
        up, lo = bands
        fig.add_trace(go.Scatter(x=df.index, y=up, line=dict(width=1, color="rgba(120,120,200,0.6)"), name="BB upper", showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=lo, line=dict(width=1, color="rgba(120,120,200,0.6)"), fill="tonexty", fillcolor="rgba(120,120,200,0.08)", name="Bollinger", showlegend=True), row=1, col=1)
    for name, series in (overlays or {}).items():
        fig.add_trace(go.Scatter(x=series.index, y=series, mode="lines", name=name, line=dict(width=1.4)), row=1, col=1)
    for lvl in (levels or {}).get("support", []):
        fig.add_hline(y=lvl, line=dict(color="#1a9850", width=1, dash="dot"), annotation_text=f"S {lvl:,.0f}", annotation_position="right", row=1, col=1)
    for lvl in (levels or {}).get("resistance", []):
        fig.add_hline(y=lvl, line=dict(color="#d73027", width=1, dash="dot"), annotation_text=f"R {lvl:,.0f}", annotation_position="right", row=1, col=1)
    if show_volume:
        colors = ["#1a9850" if c >= o else "#d73027" for c, o in zip(df["close"], df["open"])]
        fig.add_trace(go.Bar(x=df.index, y=df["volume"], marker_color=colors, name="Volume", opacity=0.6), row=2, col=1)
    fig.update_layout(title=title, height=620, xaxis_rangeslider_visible=False, margin=dict(l=40, r=80, t=50, b=30), legend=dict(orientation="h", y=1.02, x=0), hovermode="x unified")
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    return fig


def line_panel(series_map: dict[str, pd.Series], title: str, hlines: list[tuple[float, str]] | None = None, height: int = 260) -> go.Figure:
    fig = go.Figure()
    for name, s in series_map.items():
        fig.add_trace(go.Scatter(x=s.index, y=s, mode="lines", name=name, line=dict(width=1.3)))
    for y, label in hlines or []:
        fig.add_hline(y=y, line=dict(dash="dash", width=1, color="gray"), annotation_text=label, annotation_position="right")
    fig.update_layout(title=title, height=height, margin=dict(l=40, r=80, t=40, b=20), legend=dict(orientation="h", y=1.1, x=0), hovermode="x unified")
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    return fig


def inr(x: float | None) -> str:
    if x is None:
        return "INSUFFICIENT DATA"
    if x == float("inf"):
        return "UNBOUNDED"
    return f"₹{x:,.0f}"


def now_utc_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
