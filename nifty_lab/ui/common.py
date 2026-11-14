"""Shared Streamlit helpers: data loading/caching, banners, status widgets."""
from __future__ import annotations

import html
import io
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from ..brokers.upstox_candles import INTERVAL_5M, INTERVAL_DAILY
from ..brokers.upstox_instruments import find_by_label, find_by_trading_symbol, load_master, research_labels
from ..brokers.upstox_market_data import UpstoxMarketDataService, connection_generation
from ..config import AppConfig, load_config
from ..data import DataKind, MarketDataset, generate_synthetic_nifty, load_ohlcv_csv
from ..indicators import compute_indicator_frame
from ..journal import Journal

PAGE_ICON = "📈"
DISCLAIMER = (
    "Research and education only. Nothing here is investment advice. "
    "Live orders require your explicit confirmation on the Trade Ticket — nothing is automated. "
    "Technical signals are not orders; past patterns do not guarantee future results."
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
        .nsl-broker{background:#1b4332;color:#fff;}
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


def supports_nifty_signal_voting(ds: MarketDataset) -> bool:
    """Rule-based NIFTY engine only for synthetic/CSV daily NIFTY paths."""
    if ds.provenance.kind not in (DataKind.SYNTHETIC, DataKind.IMPORTED_CSV):
        return False
    if ds.provenance.bar_interval == "5m":
        return False
    sym = ds.provenance.symbol.upper()
    return sym.startswith("NIFTY") or "NIFTY" in sym


def is_intraday_broker(ds: MarketDataset) -> bool:
    return ds.provenance.kind == DataKind.BROKER_LIVE and ds.provenance.bar_interval == "5m"


def chart_interval_label(ds: MarketDataset) -> str:
    if ds.provenance.bar_interval == "5m":
        return "5-minute"
    return "daily"


@st.cache_data(show_spinner=False)
def _synthetic(seed: int) -> MarketDataset:
    return generate_synthetic_nifty(seed=seed)


def _dataset_from_upload(file) -> MarketDataset:
    return load_ohlcv_csv(io.BytesIO(file.getvalue()), symbol=file.name.rsplit(".", 1)[0].upper())


def _clear_upstox_selection_state() -> None:
    for key in ("upstox_dataset", "upstox_candidates", "active_dataset", "upstox_loaded_selection_id"):
        st.session_state.pop(key, None)


def upstox_selection_identity(label: str, custom_symbol: str, interval_label: str) -> str:
    """Public identity for tests and sidebar invalidation (no secrets)."""
    from ..brokers.upstox_candles import INTERVAL_5M, INTERVAL_DAILY

    spec = INTERVAL_5M if interval_label.startswith("5") else INTERVAL_DAILY
    return f"{label}|{custom_symbol.strip().upper()}|{spec.label}"


def _sidebar_upstox() -> MarketDataset | None:
    st.sidebar.caption("Upstox · read-only candles · token from `.env` only")
    label = st.sidebar.selectbox("Research label", list(research_labels()))
    interval_label = st.sidebar.radio("Interval", ["5 minute", "Daily"], horizontal=True)
    spec = INTERVAL_5M if interval_label.startswith("5") else INTERVAL_DAILY
    custom_sym = st.sidebar.text_input("Or exact NSE trading symbol", "", help="Optional override, e.g. ICICIBANK")
    selection_id = f"{label}|{custom_sym.strip().upper()}|{spec.label}"
    conn_gen = connection_generation()
    if "upstox_conn_gen" not in st.session_state or st.session_state["upstox_conn_gen"] != conn_gen:
        _clear_upstox_selection_state()
        st.session_state["upstox_conn_gen"] = conn_gen
    prev_sel = st.session_state.get("upstox_selection_id")
    if prev_sel is not None and prev_sel != selection_id:
        _clear_upstox_selection_state()
    st.session_state["upstox_selection_id"] = selection_id
    loaded_for = st.session_state.get("upstox_loaded_selection_id")
    if loaded_for is not None and loaded_for != selection_id:
        st.session_state.pop("upstox_dataset", None)
        st.session_state.pop("active_dataset", None)

    candidates = st.session_state.get("upstox_candidates") or []
    if candidates:
        labels = [m.display_label for m in candidates]
        pick = st.sidebar.selectbox("Resolve instrument", labels, key="upstox_resolve_picker")
        instr = candidates[labels.index(pick)]
    else:
        instr = None

    if st.sidebar.button("Load / Refresh Upstox candles", type="primary"):
        st.session_state.pop("upstox_dataset", None)
        svc = UpstoxMarketDataService()
        try:
            master = load_master(svc.transport)
            if custom_sym.strip():
                matches = find_by_trading_symbol(master.records, custom_sym.strip())
                hint = ""
            elif instr is not None:
                matches = [instr]
                hint = ""
            else:
                matches, hint = find_by_label(master.records, label)
            if not matches:
                st.session_state.pop("upstox_candidates", None)
                st.sidebar.error(hint or "NO DATA — could not resolve instrument.")
                return None
            if len(matches) > 1:
                st.session_state["upstox_candidates"] = matches
                st.sidebar.warning(hint or "Multiple matches — pick the exact instrument above, then Load again.")
                return None
            st.session_state.pop("upstox_candidates", None)
            chosen = matches[0]
            if hint:
                st.sidebar.warning(hint)
            ds = svc.load_dataset(chosen, spec)
            st.session_state["upstox_dataset"] = ds
            st.session_state["upstox_loaded_selection_id"] = selection_id
            st.sidebar.success(f"Loaded {chosen.trading_symbol} · {len(ds.df)} completed bars")
        except Exception as exc:
            st.sidebar.error(f"Load failed: {exc}")
            st.session_state.pop("upstox_dataset", None)
            return None
    ds = st.session_state.get("upstox_dataset")
    if ds is not None and st.session_state.get("upstox_loaded_selection_id") != selection_id:
        return None
    return ds


def sidebar_data_source() -> MarketDataset | None:
    """Sidebar control shared by all pages. Returns the active dataset or None."""
    st.sidebar.header("Data source")
    choice = st.sidebar.radio(
        "Select",
        ["Synthetic sample (demo)", "Import CSV (historical)", "Upstox (read-only)"],
        index=0,
        label_visibility="collapsed",
        key="data_source_radio",
    )
    prior = st.session_state.get("_data_source_choice")
    if prior is not None and prior != choice:
        _clear_upstox_selection_state()
    st.session_state["_data_source_choice"] = choice

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
            except Exception as exc:
                st.sidebar.error(f"CSV rejected: {exc}")
        elif "uploaded_dataset" in st.session_state:
            ds = st.session_state["uploaded_dataset"]
        else:
            st.sidebar.info("Upload a CSV to continue. Sample file: data/sample/nifty_synthetic_daily.csv")
    else:
        ds = _sidebar_upstox()

    if ds is not None:
        st.session_state["active_dataset"] = ds
    elif choice.startswith("Upstox"):
        st.session_state.pop("active_dataset", None)
    return ds


def provenance_banner(ds: MarketDataset | None) -> None:
    if ds is None:
        st.markdown('<div class="nsl-banner nsl-off">NO DATA SOURCE ACTIVE — select one in the sidebar.</div>', unsafe_allow_html=True)
        return
    p = ds.provenance
    sym = html.escape(p.symbol)
    if p.kind == DataKind.BROKER_LIVE:
        css = "nsl-broker"
        iv = html.escape(p.bar_interval or "n/a")
        ikey = html.escape(p.instrument_key or "n/a")
        label = f"BROKER LIVE · Upstox API · {sym} · interval {iv}"
        last = p.last_bar_time.strftime("%Y-%m-%d %H:%M %Z") if p.last_bar_time else "n/a"
    elif p.kind == DataKind.SYNTHETIC:
        css = "nsl-syn"
        label = "SYNTHETIC DATA (not real market data)"
        last = p.last_bar_time.strftime("%Y-%m-%d") if p.last_bar_time else "n/a"
        ikey = ""
    else:
        css = "nsl-csv"
        label = f"IMPORTED CSV: {html.escape(p.source)}"
        last = p.last_bar_time.strftime("%Y-%m-%d") if p.last_bar_time else "n/a"
        ikey = ""
    extra = f" · key {ikey}" if p.kind == DataKind.BROKER_LIVE else ""
    st.markdown(
        f'<div class="nsl-banner {css}"><b>{label}</b> · symbol {sym}{extra} · last completed bar {last} · '
        f'{html.escape(p.freshness_label())} · {len(ds.df)} bars · retrieved {p.retrieved_at.strftime("%Y-%m-%d %H:%M UTC")}</div>',
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


def candlestick_figure(
    df: pd.DataFrame,
    overlays: dict[str, pd.Series] | None = None,
    title: str = "",
    show_volume: bool = True,
    bands: tuple[pd.Series, pd.Series] | None = None,
    levels: dict[str, list[float]] | None = None,
    *,
    use_datetime_index: bool = True,
) -> go.Figure:
    rows = 2 if show_volume else 1
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25] if show_volume else [1.0])
    x = df.index if use_datetime_index else list(range(len(df)))
    fig.add_trace(
        go.Candlestick(x=x, open=df["open"], high=df["high"], low=df["low"], close=df["close"], name="OHLC", increasing_line_color="#1a9850", decreasing_line_color="#d73027"),
        row=1,
        col=1,
    )
    if bands is not None:
        up, lo = bands
        fig.add_trace(go.Scatter(x=up.index, y=up, line=dict(width=1, color="rgba(120,120,200,0.6)"), name="BB upper", showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=lo.index, y=lo, line=dict(width=1, color="rgba(120,120,200,0.6)"), fill="tonexty", fillcolor="rgba(120,120,200,0.08)", name="Bollinger", showlegend=True), row=1, col=1)
    for name, series in (overlays or {}).items():
        fig.add_trace(go.Scatter(x=series.index, y=series, mode="lines", name=name, line=dict(width=1.4)), row=1, col=1)
    for lvl in (levels or {}).get("support", []):
        fig.add_hline(y=lvl, line=dict(color="#1a9850", width=1, dash="dot"), annotation_text=f"S {lvl:,.0f}", annotation_position="right", row=1, col=1)
    for lvl in (levels or {}).get("resistance", []):
        fig.add_hline(y=lvl, line=dict(color="#d73027", width=1, dash="dot"), annotation_text=f"R {lvl:,.0f}", annotation_position="right", row=1, col=1)
    if show_volume:
        colors = ["#1a9850" if c >= o else "#d73027" for c, o in zip(df["close"], df["open"])]
        fig.add_trace(go.Bar(x=x, y=df["volume"], marker_color=colors, name="Volume", opacity=0.6), row=2, col=1)
    fig.update_layout(title=title, height=620, xaxis_rangeslider_visible=False, margin=dict(l=40, r=80, t=50, b=30), legend=dict(orientation="h", y=1.02, x=0), hovermode="x unified")
    if not use_datetime_index:
        fig.update_xaxes(rangebreaks=[])
    else:
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
