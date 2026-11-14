"""Settings section: Upstox authentication status and the explicit Reconnect workflow (Spec 16). Never shows values."""
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
)

_ICON = {AuthStatus.NOT_CONFIGURED: "⚪", AuthStatus.NOT_VERIFIED: "🟡", AuthStatus.CONNECTED: "🟢", AuthStatus.REAUTH_REQUIRED: "🔴"}
_LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "[::1]")


def _request_host() -> str | None:
    try:
        return st.context.headers.get("host")
    except Exception:  # noqa: BLE001 — no request context (e.g. AppTest)
        return None


def operator_access_allowed() -> bool:
    """Reconnect controls are shown only when the dashboard is reached over loopback (direct or SSH tunnel)."""
    host = _request_host()
    if host is None:
        return False
    return host.split(":")[0].lower() in _LOOPBACK_HOSTS


def _session_key() -> str:
    if "_auth_session_key" not in st.session_state:
        ctx = getattr(st.runtime, "scriptrunner", None)
        run = ctx.get_script_run_ctx() if ctx and hasattr(ctx, "get_script_run_ctx") else None
        st.session_state["_auth_session_key"] = str(getattr(run, "session_id", None) or id(st.session_state))
    return st.session_state["_auth_session_key"]


def _handle_callback() -> None:
    qp = st.query_params
    if "code" not in qp and "state" not in qp:
        return
    code, state = qp.get("code"), qp.get("state")
    st.query_params.clear()  # authorization-code parameters never stay in the address bar
    try:
        result = complete_login(code=code, state=state, session_key=_session_key(), transport=UpstoxAuthTransport())
        st.session_state["_auth_last_result"] = ("success", result.message)
    except (LoginError, OAuthNotConfigured) as exc:
        st.session_state["_auth_last_result"] = ("error", str(exc))


def render_upstox_auth_section() -> None:
    _handle_callback()
    st.subheader("Upstox authentication")
    summary = auth_status()
    st.markdown(f"{_ICON[summary.status]} **Status: {summary.status.value}**" + (f" · source: {summary.source}" if summary.source else ""))
    st.caption(summary.detail)
    if summary.status == AuthStatus.REAUTH_REQUIRED:
        st.warning("Automatic retries with this token are stopped. Use **Reconnect Upstox** below; LIVE streams need an explicit Start afterwards.")
    if (last := st.session_state.pop("_auth_last_result", None)) is not None:
        (st.success if last[0] == "success" else st.error)(last[1])

    if not operator_access_allowed():
        st.info("Reconnect controls are available only when this page is opened via localhost (directly or through an SSH tunnel to the server).")
        return
    redirect = st.session_state.get("_auth_redirect_hint")
    if redirect is None:
        import os

        redirect = os.getenv(ENV_REDIRECT_URI, "").strip()
        st.session_state["_auth_redirect_hint"] = redirect
    if st.button("Reconnect Upstox", type="primary", help="Opens the official Upstox login; the authorization code is exchanged server-side."):
        try:
            url, _state = begin_login(session_key=_session_key())
            st.session_state["_auth_login_url"] = url
        except OAuthNotConfigured as exc:
            st.error(str(exc))
    if (url := st.session_state.get("_auth_login_url")) is not None:
        st.link_button("Open Upstox login (approve, then you return here)", url)
        host = urlparse(redirect).netloc or "<redirect host>"
        st.caption(f"Upstox will redirect to the registered URI on **{host}**. If you are approving from another computer, open this dashboard through an SSH tunnel so that host resolves to this server. The link is valid for 10 minutes and single-use.")
