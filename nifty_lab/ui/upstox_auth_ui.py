"""Settings section: Upstox authentication status and the explicit Reconnect workflow (Spec 16). Never shows values.

Access boundary: OAuth initiation and callback processing run only when the Streamlit listener is bound to a loopback
address (`server.address`), read from server configuration, never from client-controlled headers. With a loopback
listener the only remote path is an SSH tunnel, so "operator" means whoever holds a shell account on this host.
Binding: the callback tab only *receives* the approval; the token exchange happens solely in the session that started
the reconnect, when the operator clicks Complete reconnection there.
"""
from __future__ import annotations

from urllib.parse import urlparse

import streamlit as st

from ..brokers.upstox_auth import (
    ENV_REDIRECT_URI,
    AuthStatus,
    LoginError,
    OAuthNotConfigured,
    UpstoxAuthTransport,
    auth_status,
    begin_login,
    complete_login,
    pending_for_session,
    receive_callback,
)

_ICON = {AuthStatus.NOT_CONFIGURED: "⚪", AuthStatus.NOT_VERIFIED: "🟡", AuthStatus.CONNECTED: "🟢", AuthStatus.REAUTH_REQUIRED: "🔴"}
_LOOPBACK = ("127.0.0.1", "localhost", "::1", "[::1]")
_LISTENER_HELP = (
    "OAuth reconnect is refused because the dashboard listener is not bound to a loopback address. "
    "Set `[server] address = \"127.0.0.1\"` in `.streamlit/config.toml` (or pass `--server.address 127.0.0.1`) and reach "
    "the dashboard directly or through an SSH tunnel (`ssh -N -L 8501:127.0.0.1:8501 <host>`)."
)


def _listener_address() -> str | None:
    try:
        from streamlit import config

        return config.get_option("server.address")
    except Exception:  # noqa: BLE001 — no config context
        return None


def oauth_access_allowed() -> bool:
    """True only when the server socket itself is loopback-bound. Fail-closed when unknown."""
    addr = (_listener_address() or "").strip().lower()
    return addr in _LOOPBACK


def _session_key() -> str:
    """Streamlit session id plus a random nonce that exists only in this session's state: stable for the life of the
    browser session, unguessable, and distinct even where session ids collide (AppTest uses one fixed id)."""
    if "_auth_session_key" not in st.session_state:
        import secrets

        ctx = getattr(st.runtime, "scriptrunner", None)
        run = ctx.get_script_run_ctx() if ctx and hasattr(ctx, "get_script_run_ctx") else None
        st.session_state["_auth_session_key"] = f"{getattr(run, 'session_id', None) or id(st.session_state)}:{secrets.token_hex(8)}"
    return st.session_state["_auth_session_key"]


def _set_result(kind: str, message: str) -> None:
    st.session_state["_auth_last_result"] = (kind, message)


def _handle_callback(allowed: bool) -> None:
    qp = st.query_params
    if "code" not in qp and "state" not in qp:
        return
    code, state = qp.get("code"), qp.get("state")
    st.query_params.clear()  # authorization-code parameters never stay in the address bar, allowed or not
    if not allowed:
        _set_result("error", "OAuth callback refused: listener is not loopback-bound. " + _LISTENER_HELP)
        return
    try:
        message = receive_callback(code=code, state=state)
    except LoginError as exc:
        _set_result("error", str(exc))
        return
    mine = pending_for_session(_session_key())
    if mine is not None and mine[0] == state:  # callback arrived in the very session that started it: complete now
        _complete(state)
    else:
        _set_result("info", message)


def _complete(state: str) -> None:
    try:
        result = complete_login(state=state, session_key=_session_key(), transport=UpstoxAuthTransport())
        st.session_state.pop("_auth_login_url", None)
        _set_result("success", result.message)
    except (LoginError, OAuthNotConfigured) as exc:
        _set_result("error", str(exc))


def render_upstox_auth_section() -> None:
    allowed = oauth_access_allowed()
    _handle_callback(allowed)
    st.subheader("Upstox authentication")
    summary = auth_status()
    st.markdown(f"{_ICON[summary.status]} **Status: {summary.status.value}**" + (f" · source: {summary.source}" if summary.source else ""))
    st.caption(summary.detail)
    if summary.status == AuthStatus.REAUTH_REQUIRED:
        st.warning("Automatic retries with this token are stopped. Use **Reconnect Upstox** below; LIVE streams need an explicit Start afterwards.")
    if (last := st.session_state.pop("_auth_last_result", None)) is not None:
        getattr(st, last[0])(last[1])
    if not allowed:
        st.error(_LISTENER_HELP)
        return

    if st.button("Reconnect Upstox", type="primary", help="Opens the official Upstox login; the authorization code is exchanged server-side from this tab only."):
        try:
            url, _state = begin_login(session_key=_session_key())
            st.session_state["_auth_login_url"] = url
        except OAuthNotConfigured as exc:
            st.error(str(exc))
    mine = pending_for_session(_session_key())
    if mine is not None:
        state, received = mine
        if (url := st.session_state.get("_auth_login_url")) is not None:
            st.link_button("Open Upstox login (approve, then come back to this tab)", url)
            import os

            host = urlparse(os.getenv(ENV_REDIRECT_URI, "")).netloc or "<redirect host>"
            st.caption(f"Upstox redirects to the registered URI on **{host}**; if you approve from another computer, reach this dashboard through an SSH tunnel so that host is this server. Valid 10 minutes, single-use.")
        st.caption("Approval received — click Complete reconnection." if received else "Waiting for the Upstox approval to arrive…")
        if st.button("Complete reconnection", key="auth_complete_reconnect", type="primary" if received else "secondary"):
            _complete(state)
            st.rerun()
