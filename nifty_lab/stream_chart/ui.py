"""Streamlit page body for Spec 14 stream chart prototype."""
from __future__ import annotations

from datetime import timezone

import streamlit as st

from nifty_lab.brokers.upstox_transport import RequestsTransport

from .constants import (
    INSTRUMENT_KEY,
    INSTRUMENT_LABEL,
    LIGHTWEIGHT_CHARTS_VERSION,
    LWC_ATTRIBUTION,
    REPLAY_BANNER,
)
from .lwc import render_candlestick_chart
from .stream_errors import StreamErrorCode
from .stream_session import ConnectionState, StreamMode, active_snapshot, start_stream, stop_stream


@st.fragment(run_every=1.0)
def _stream_chart_fragment(owner: str) -> None:
    live = active_snapshot(owner_token=owner)
    if live is None or live.book is None:
        return
    meta = render_candlestick_chart(bars=live.book.chart_series())
    if meta:
        st.session_state["lwc_instance_id"] = meta.get("instanceId")
        st.session_state["lwc_update_count"] = meta.get("updateCount")
    st.caption(
        f"Auto-refresh · {live.state.value} · bars={len(live.book.chart_series())} · "
        f"late_ignored={live.book.late_ticks_ignored} · exchange={live.exchange_status}"
    )
    if live.book.coverage_notes:
        st.caption("Coverage: " + "; ".join(f"{n.kind}:{n.detail}" for n in live.book.coverage_notes[-3:]))


def _owner_token() -> str:
    if "_stream_owner" not in st.session_state:
        ctx = getattr(st.runtime, "scriptrunner", None)
        run = ctx.get_script_run_ctx() if ctx and hasattr(ctx, "get_script_run_ctx") else None
        sid = getattr(run, "session_id", None)
        st.session_state["_stream_owner"] = sid or f"local-{id(st.session_state)}"
    return str(st.session_state["_stream_owner"])


def render_stream_chart_page() -> None:
    st.title("ICICIBANK — 5m stream chart (prototype)")
    st.caption(
        f"Instrument `{INSTRUMENT_KEY}` · read-only market data · Lightweight Charts v{LIGHTWEIGHT_CHARTS_VERSION}"
    )
    st.caption(LWC_ATTRIBUTION)
    st.warning(
        "**Research prototype.** No orders, no ledger writes. Authorized WebSocket URLs stay server-side only.",
        icon="🛡️",
    )

    mode_key = "stream_mode"
    if mode_key not in st.session_state:
        st.session_state[mode_key] = StreamMode.REPLAY.value
    mode = st.radio(
        "Feed mode",
        options=[StreamMode.REPLAY.value, StreamMode.LIVE.value],
        format_func=lambda x: "REPLAY (offline fixture)" if x == StreamMode.REPLAY.value else "LIVE (Upstox Feed V3)",
        horizontal=True,
        key=mode_key,
    )
    if mode == StreamMode.REPLAY.value:
        st.info(REPLAY_BANNER, icon="🔁")

    owner = _owner_token()
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Start stream", type="primary"):
            if mode == StreamMode.REPLAY.value:
                snap = start_stream(owner_token=owner, mode=StreamMode.REPLAY)
            else:
                snap = start_stream(owner_token=owner, mode=StreamMode.LIVE, http=RequestsTransport())
            if snap.fault and snap.fault.code == StreamErrorCode.OWNER_CONFLICT:
                st.warning(snap.fault.message)
            else:
                st.session_state["_stream_running"] = True
    with c2:
        if st.button("Stop stream"):
            stop_stream(owner_token=owner)
            st.session_state["_stream_running"] = False
            if snap := active_snapshot(owner_token=owner):
                if snap.book:
                    render_candlestick_chart(bars=snap.book.chart_series())
    with c3:
        st.metric("Symbol", INSTRUMENT_LABEL)

    snap = active_snapshot(owner_token=owner)
    state = snap.state.value if snap else ConnectionState.IDLE.value
    st.metric("Connection", state.upper())
    if snap and snap.fault:
        st.error(f"{snap.fault.code.value}: {snap.fault.message}")
    if snap and snap.book:
        cols = st.columns(5)
        cols[0].metric("Bootstrap bars", snap.bootstrap_count)
        cols[1].metric("Stream completed", len(snap.book.stream_completed))
        cols[2].metric(
            "Last trade (UTC)",
            snap.last_trade_ts.astimezone(timezone.utc).strftime("%H:%M:%S") if snap.last_trade_ts else "—",
        )
        cols[3].metric(
            "Heartbeat (UTC)",
            snap.last_heartbeat_ts.astimezone(timezone.utc).strftime("%H:%M:%S") if snap.last_heartbeat_ts else "—",
        )
        cols[4].metric("Reconnect #", snap.reconnect_attempt)
        if snap.reconnect_gap:
            st.warning("Reconnect gap recorded — do not assume continuous coverage.")
        inst = st.session_state.get("lwc_instance_id")
        if inst:
            st.caption(f"Chart instance `{inst[:8]}…` updates={st.session_state.get('lwc_update_count', 0)}")

    if st.session_state.get("_stream_running"):
        _stream_chart_fragment(owner)
    elif snap and snap.book and snap.book.chart_series():
        render_candlestick_chart(bars=snap.book.chart_series())
    else:
        st.caption("Press **Start stream** to load the REPLAY fixture or LIVE feed.")

    if snap and snap.book:
        with st.expander("Bar coverage (metadata)"):
            for row in snap.book.chart_rows():
                st.write(row)