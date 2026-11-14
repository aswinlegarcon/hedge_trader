"""Streamlit page body for the stream chart prototype (Spec 14) with current status in the auto-refreshing fragment (Spec 15)."""
from __future__ import annotations

from datetime import timezone

import streamlit as st

from nifty_lab.brokers.upstox_transport import RequestsTransport

from .constants import (
    INSTRUMENT_KEY,
    INSTRUMENT_LABEL,
    LIGHTWEIGHT_CHARTS_VERSION,
    LWC_ATTRIBUTION,
    RENDER_INTERVAL_SEC,
    REPLAY_BANNER,
)
from .lwc import render_candlestick_chart
from .stream_errors import StreamErrorCode
from .stream_session import (
    ConnectionState,
    Freshness,
    StreamMode,
    StreamSnapshot,
    active_snapshot,
    keepalive,
    start_stream,
    stop_stream,
)

_TERMINAL = (ConnectionState.STOPPED, ConnectionState.ERROR, ConnectionState.OWNER_EXPIRED)


def status_lines(snap: StreamSnapshot) -> list[tuple[str, str]]:
    """Pure view model: (streamlit level, text) for the current snapshot. Transport state and price freshness are
    reported separately; nothing here infers an exchange calendar — exchange status is quoted from the provider."""
    lines: list[tuple[str, str]] = []
    state = snap.state.value.upper()
    if snap.fault is not None:
        lines.append(("error", f"{snap.fault.code.value}: {snap.fault.message}"))
    if snap.state == ConnectionState.STOPPING:
        lines.append(("warning", "STOPPING — waiting for the feed worker to finish its current call (bounded); Start is blocked until then."))
    elif snap.state == ConnectionState.OWNER_EXPIRED:
        lines.append(("warning", "OWNER EXPIRED — this page stopped renewing its lease; the feed was shut down. Press Start to resume."))
    else:
        lines.append(("caption", f"Connection: {state}"))

    if snap.mode == StreamMode.REPLAY:
        lines.append(("caption", "REPLAY · synthetic fixture timeline — no price-freshness claim."))
    elif snap.state in (ConnectionState.STREAMING, ConnectionState.STALE, ConnectionState.WAITING_FOR_DATA):
        if snap.freshness == Freshness.FRESH:
            lines.append(("caption", f"Price FRESH · source age {snap.source_age_sec:.0f}s · no newer source time for {snap.progress_age_sec:.0f}s"))
        elif snap.freshness == Freshness.STALE:
            lines.append(("warning", f"Price STALE — latest source trade is {snap.source_age_sec:.0f}s old and source time has not advanced for {snap.progress_age_sec:.0f}s. Not a current price."))
        else:
            lines.append(("info", f"Connected, waiting for the first trade · provider exchange status: {snap.exchange_status}"))
        if snap.exchange_status not in ("NORMAL_OPEN", "UNKNOWN"):
            lines.append(("warning", f"Provider reports exchange status {snap.exchange_status} — trades may not arrive. No market calendar is inferred."))
    if snap.reconnect_gap:
        lines.append(("warning", f"Reconnect gap recorded (reconnects: {snap.reconnect_attempt}) — do not assume continuous coverage."))
    return lines


@st.fragment(run_every=RENDER_INTERVAL_SEC)
def _stream_chart_fragment(owner: str) -> None:
    live = active_snapshot(owner_token=owner)
    if live is None:
        st.caption("Press **Start stream** to load the REPLAY fixture or LIVE feed.")
        return
    if live.state == ConnectionState.OWNER_CONFLICT:
        st.warning(live.fault.message if live.fault else "Another stream owner is active.")
        return
    if live.state not in _TERMINAL and not live.stop_requested:
        keepalive(owner_token=owner, session_id=live.session_id)  # only the displayed owner renews its lease
    for level, text in status_lines(live):
        getattr(st, level)(text)
    if live.book is None:
        return
    meta = render_candlestick_chart(bars=live.book.chart_series())
    if meta:
        st.session_state["lwc_instance_id"] = meta.get("instanceId")
        st.session_state["lwc_update_count"] = meta.get("updateCount")
    cols = st.columns(5)
    cols[0].metric("Bootstrap bars", live.bootstrap_count)
    cols[1].metric("Stream completed", len(live.book.stream_completed))
    cols[2].metric("Last trade (UTC)", live.last_trade_ts.astimezone(timezone.utc).strftime("%H:%M:%S") if live.last_trade_ts else "—")
    cols[3].metric("Heartbeat (UTC)", live.last_heartbeat_ts.astimezone(timezone.utc).strftime("%H:%M:%S") if live.last_heartbeat_ts else "—")
    cols[4].metric("Reconnect #", live.reconnect_attempt)
    st.caption(
        f"Auto-refresh · {live.state.value} · bars={len(live.book.chart_series())} · "
        f"late_ignored={live.book.late_ticks_ignored} · future_rejected={live.future_ticks_rejected} · "
        f"invalid_rejected={live.invalid_ticks_rejected} · exchange={live.exchange_status}"
    )
    if live.book.coverage_notes:
        st.caption("Coverage: " + "; ".join(f"{n.kind}:{n.detail}" for n in live.book.coverage_notes[-3:]))
    with st.expander("Bar coverage (metadata)"):
        for row in live.book.chart_rows():
            st.write(row)


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
    with c2:
        if st.button("Stop stream"):
            stop_stream(owner_token=owner)  # returns immediately; the fragment shows STOPPING until cleanup completes
    with c3:
        st.metric("Symbol", INSTRUMENT_LABEL)

    _stream_chart_fragment(owner)  # single current view: status, faults, freshness, chart — refreshed without clicks
