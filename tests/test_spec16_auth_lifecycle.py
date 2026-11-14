"""Spec 16 — Upstox authentication lifecycle (offline; mocked exchanges; sockets blocked).

Scenario ids refer to docs/spec_16/capabilities/auth-lifecycle.md.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import stat
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from nifty_lab.brokers import upstox_auth as ua
from nifty_lab.brokers import upstox_transport
from nifty_lab.brokers.upstox_auth import (
    AuthStatus,
    LoginError,
    OAuthNotConfigured,
    TokenStore,
    UpstoxAuthTransport,
    auth_status,
    begin_login,
    complete_login,
    default_store,
    receive_callback,
    expiry_after,
    fingerprint,
    reset_login_registry_for_tests,
    resolve_access_token,
)
from nifty_lab.brokers.upstox_errors import UpstoxAuthError
from nifty_lab.brokers.upstox_market_data import connection_generation, read_access_token
from nifty_lab.brokers.upstox_transport import RequestsTransport
from nifty_lab.stream_chart import stream_session as ss
from nifty_lab.stream_chart.fixtures import market_info_frame
from nifty_lab.stream_chart.stream_session import ConnectionState, SessionPolicy, StreamMode, active_snapshot, start_stream, stop_stream, worker_threads_alive
from nifty_lab.stream_chart.transport import LiveWebSocketTransport, ScriptedLiveTransport

IST = ZoneInfo("Asia/Kolkata")
ENV_TOKEN = "ENVTOKEN-aaaa1111-S16"
NEW_TOKEN = "NEWTOKEN-bbbb2222-S16"
CLIENT_ID = "client-id-S16"
CLIENT_SECRET = "CLIENTSECRET-cccc3333-S16"
AUTH_CODE = "AUTHCODE-dddd4444-S16"
REDIRECT = "http://localhost:8501/Settings_and_API_Connections"
MARKERS = (ENV_TOKEN, NEW_TOKEN, CLIENT_SECRET, AUTH_CODE, "Bearer ")
FAST = SessionPolicy(lease_seconds=5.0, monitor_interval_sec=0.02, backoff_sec=(0.01, 0.01, 0.01))


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    ss.reset_stream_registry_for_tests()
    reset_login_registry_for_tests()
    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("UPSTOX_API_KEY", CLIENT_ID)
    monkeypatch.setenv("UPSTOX_API_SECRET", CLIENT_SECRET)
    monkeypatch.setenv("UPSTOX_REDIRECT_URI", REDIRECT)
    monkeypatch.setattr(upstox_transport, "MIN_INTERVAL_SEC", 0.0)

    class Guarded(socket.socket):
        def connect(self, address):
            raise OSError("network blocked in Spec16 tests")

    monkeypatch.setattr(socket, "socket", Guarded)
    yield
    ss.reset_stream_registry_for_tests()
    reset_login_registry_for_tests()


def assert_clean(text: str) -> None:
    for m in MARKERS:
        assert m not in text, f"{m!r} leaked into {text[:200]!r}"


class FakeResponse:
    def __init__(self, status: int, payload) -> None:
        self.status_code = status
        self.content = json.dumps(payload).encode() if not isinstance(payload, bytes) else payload
        self.headers = {}

    def json(self):
        return json.loads(self.content.decode())


class FakeTokenSession:
    """requests.Session stand-in for the token endpoint (POST) — the only remote boundary stubbed."""

    def __init__(self, status: int = 200, payload=None, *, raise_exc: Exception | None = None) -> None:
        self.status = status
        self.payload = payload if payload is not None else {"access_token": NEW_TOKEN, "extended_token": None, "user_id": "u"}
        self.raise_exc = raise_exc
        self.calls: list[dict] = []

    def post(self, url, *, data, headers, timeout, allow_redirects=False):
        self.calls.append({"url": url, "data": dict(data), "headers": dict(headers)})
        if self.raise_exc:
            raise self.raise_exc
        return FakeResponse(self.status, self.payload)


class FakeGetSession:
    def __init__(self, status: int) -> None:
        self.status, self.auth_headers = status, []

    def get(self, url, *, headers, timeout, allow_redirects):
        self.auth_headers.append(headers.get("Authorization"))
        return FakeResponse(self.status, {"data": {"candles": []}} if self.status == 200 else {})


def auth_transport(fake: FakeTokenSession) -> UpstoxAuthTransport:
    return UpstoxAuthTransport(session=fake)  # type: ignore[arg-type]


# ============================================================================ R1 token store

def test_s01_store_writes_atomically_with_restrictive_permissions(tmp_path):
    path = tmp_path / "secrets" / "upstox_token.json"
    store = TokenStore(path)
    issued = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)
    store.install(NEW_TOKEN, issued_at=issued, source="oauth")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    rec = store.read()
    assert rec is not None and rec.value == NEW_TOKEN and rec.source == "managed" and rec.issued_at == issued
    assert rec.expires_at == expiry_after(issued)
    assert not list(path.parent.glob("*.tmp*"))  # no temp leftovers
    assert NEW_TOKEN not in repr(rec)  # value never shown in reprs


def test_s02_failed_replacement_keeps_working_credential(tmp_path, monkeypatch):
    store = TokenStore(tmp_path / "s" / "t.json")
    store.install(ENV_TOKEN, issued_at=datetime.now(timezone.utc), source="oauth")

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(ua.os, "replace", boom)
    with pytest.raises(OSError):
        store.install(NEW_TOKEN, issued_at=datetime.now(timezone.utc), source="oauth")
    monkeypatch.undo()
    assert store.read().value == ENV_TOKEN
    assert not list((tmp_path / "s").glob("*.tmp*"))


def test_s03_expiry_follows_documented_0330_ist_rule():
    before = datetime(2026, 11, 14, 2, 0, tzinfo=IST)  # issued before 03:30 → same day 03:30
    assert expiry_after(before) == datetime(2026, 11, 14, 3, 30, tzinfo=IST)
    after = datetime(2026, 11, 14, 10, 0, tzinfo=IST)  # issued after → next day 03:30
    assert expiry_after(after) == datetime(2026, 11, 15, 3, 30, tzinfo=IST)
    exact = datetime(2026, 11, 14, 3, 30, tzinfo=IST)
    assert expiry_after(exact) == datetime(2026, 11, 15, 3, 30, tzinfo=IST)


# ============================================================================ R2 precedence + status

def test_s04_precedence_managed_over_env_and_rejected_env_never_overrides(monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", ENV_TOKEN)
    store = default_store()
    assert resolve_access_token().source == "environment"
    store.install(NEW_TOKEN, issued_at=datetime.now(timezone.utc), source="oauth")
    tok = resolve_access_token()
    assert tok.value == NEW_TOKEN and tok.source == "managed"
    # the env token is later rejected by the broker: it must never be chosen again, with or without a managed token
    store.mark_rejected(fingerprint(ENV_TOKEN))
    store.clear()
    assert resolve_access_token() is None
    assert auth_status().status == AuthStatus.REAUTH_REQUIRED
    with pytest.raises(UpstoxAuthError) as exc:
        read_access_token()
    assert "Reconnect Upstox" in str(exc.value)
    assert_clean(str(exc.value))


def test_s05_expired_managed_token_requires_reauth_and_is_not_used(monkeypatch):
    store = default_store()
    store.install(NEW_TOKEN, issued_at=datetime.now(timezone.utc) - timedelta(days=2), source="oauth")
    assert resolve_access_token() is None
    summary = auth_status()
    assert summary.status == AuthStatus.REAUTH_REQUIRED and summary.expiry_known and "expired" in summary.detail.lower()
    assert_clean(summary.detail)
    # identical token supplied through the environment must not resurrect the known-expired credential
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", NEW_TOKEN)
    assert resolve_access_token() is None
    assert auth_status().status == AuthStatus.REAUTH_REQUIRED
    store.clear()  # even after the managed file is gone, the expiry mark is durable
    assert resolve_access_token() is None
    # a genuinely different environment credential is a documented fallback with unknown expiry, unverified
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", ENV_TOKEN)
    tok = resolve_access_token()
    assert tok is not None and tok.source == "environment" and tok.expires_at is None
    assert auth_status().status == AuthStatus.NOT_VERIFIED


def test_s17_late_success_cannot_resurrect_a_rejected_credential():
    store = default_store()
    fp = fingerprint(ENV_TOKEN)
    store.mark_rejected(fp)
    store.mark_verified(fp)  # delayed 2xx from an in-flight request lands after the 401
    assert store.is_rejected(fp)
    import os as _os

    _os.environ["UPSTOX_ACCESS_TOKEN"] = ENV_TOKEN
    try:
        assert resolve_access_token() is None and auth_status().status == AuthStatus.REAUTH_REQUIRED
    finally:
        del _os.environ["UPSTOX_ACCESS_TOKEN"]
    # even the transport hook ordering 401 → 200 keeps the rejection
    from nifty_lab.brokers.upstox_auth import note_response

    note_response(f"Bearer {NEW_TOKEN}", 401)
    note_response(f"Bearer {NEW_TOKEN}", 200)
    assert store.is_rejected(fingerprint(NEW_TOKEN))


def test_s18_shared_state_updates_are_not_lost_under_concurrent_writers():
    import threading

    fps = [fingerprint(f"tok-{i}") for i in range(40)]
    errors: list[BaseException] = []

    def worker(i: int) -> None:
        try:
            st = default_store()  # a fresh instance per caller, as production code does
            (st.mark_rejected if i % 2 else st.mark_verified)(fps[i])
            if i % 4 == 0:
                st.mark_rejected(fps[0])
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert errors == []
    st = default_store()
    for i, fp in enumerate(fps):
        assert st.is_rejected(fp) if i % 2 else st.verified_at(fp) is not None, i
    assert st.is_rejected(fps[0])  # the rejection written concurrently with a verification survived


def test_s06_status_labels_are_value_free_and_truthful(monkeypatch):
    s = auth_status()
    assert s.status == AuthStatus.NOT_CONFIGURED and s.expires_at is None
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", ENV_TOKEN)
    s = auth_status()
    assert s.status == AuthStatus.NOT_VERIFIED and s.source == "environment" and not s.expiry_known  # no issuance metadata → unknown
    assert_clean(s.detail + s.status.value)
    store = default_store()
    store.mark_verified(fingerprint(ENV_TOKEN))
    assert auth_status().status == AuthStatus.CONNECTED
    store.install(NEW_TOKEN, issued_at=datetime.now(timezone.utc), source="oauth")
    s = auth_status()
    assert s.status == AuthStatus.NOT_VERIFIED and s.source == "managed" and s.expiry_known and s.expires_at is not None
    assert "03:30" in s.detail
    for label in AuthStatus:
        assert_clean(label.value)


def test_s07_transport_marks_rejection_and_success_by_fingerprint(monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", ENV_TOKEN)
    fake = FakeGetSession(401)
    with pytest.raises(UpstoxAuthError):
        RequestsTransport(session=fake).get("https://api.upstox.com/v3/x", headers={"Authorization": f"Bearer {ENV_TOKEN}"})  # type: ignore[arg-type]
    assert auth_status().status == AuthStatus.REAUTH_REQUIRED
    assert resolve_access_token() is None  # no retry storm: nobody can obtain the rejected token again
    default_store().install(NEW_TOKEN, issued_at=datetime.now(timezone.utc), source="oauth")
    ok = FakeGetSession(200)
    RequestsTransport(session=ok).get("https://api.upstox.com/v3/x", headers={"Authorization": f"Bearer {NEW_TOKEN}"})  # type: ignore[arg-type]
    assert auth_status().status == AuthStatus.CONNECTED and auth_status().source == "managed"
    assert connection_generation() != 0


def test_s08_rejected_credential_stops_stream_retries_and_next_start_makes_no_http(monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", ENV_TOKEN)
    fake = FakeGetSession(401)
    http = RequestsTransport(session=fake)  # type: ignore[arg-type]
    start_stream(owner_token="a", mode=StreamMode.LIVE, live_transport=LiveWebSocketTransport(http), policy=FAST)
    deadline = time.time() + 5
    while time.time() < deadline and (active_snapshot(owner_token="a") or ss._ACTIVE.snapshot()).state != ConnectionState.ERROR:
        time.sleep(0.01)
    snap = active_snapshot(owner_token="a")
    assert snap.fault.code.value == "FEED_AUTH_FAILED" and len(fake.auth_headers) == 1
    stop_stream(owner_token="a")
    while worker_threads_alive():
        time.sleep(0.01)
    start_stream(owner_token="a", mode=StreamMode.LIVE, live_transport=LiveWebSocketTransport(http), policy=FAST)
    deadline = time.time() + 5
    while time.time() < deadline and active_snapshot(owner_token="a").state != ConnectionState.ERROR:
        time.sleep(0.01)
    snap = active_snapshot(owner_token="a")
    assert snap.fault.code.value == "FEED_AUTH_FAILED" and "Reconnect Upstox" in snap.fault.message
    assert len(fake.auth_headers) == 1  # the rejected token was not sent again


# ============================================================================ R3 OAuth reconnect

def test_s09_begin_login_builds_exact_dialog_url_with_random_single_use_state():
    url1, state1 = begin_login(session_key="sess-1")
    url2, state2 = begin_login(session_key="sess-1")
    assert state1 != state2 and len(state1) >= 32
    from urllib.parse import parse_qs, urlparse

    u = urlparse(url1)
    assert (u.scheme, u.netloc, u.path) == ("https", "api.upstox.com", "/v2/login/authorization/dialog")
    q = parse_qs(u.query)
    assert q == {"client_id": [CLIENT_ID], "redirect_uri": [REDIRECT], "response_type": ["code"], "state": [state1]}
    assert CLIENT_SECRET not in url1


def test_s09_begin_login_requires_configuration(monkeypatch):
    monkeypatch.delenv("UPSTOX_API_SECRET")
    with pytest.raises(OAuthNotConfigured) as exc:
        begin_login(session_key="s")
    assert "UPSTOX_API_SECRET" in str(exc.value) and CLIENT_ID not in str(exc.value)


@pytest.mark.parametrize("case", ["missing_state", "unknown_state", "missing_code", "expired", "replayed_callback", "replayed_completion"])
def test_s10_callback_validation_rejects_bad_states_without_exchange(case):
    fake = FakeTokenSession()
    _, state = begin_login(session_key="sess")
    code, st_val = AUTH_CODE, state
    if case == "missing_state":
        st_val = None
    elif case == "unknown_state":
        st_val = "x" * 43
    elif case == "missing_code":
        code = None
    elif case == "expired":
        ua._PENDING[state].created_mono -= ua.STATE_TTL_SEC + 1
    elif case == "replayed_callback":
        receive_callback(code=code, state=state)
    elif case == "replayed_completion":
        receive_callback(code=code, state=state)
        assert complete_login(state=state, session_key="sess", transport=auth_transport(fake)).ok
        fake.calls.clear()
    with pytest.raises(LoginError) as exc:
        if case == "replayed_completion":
            complete_login(state=state, session_key="sess", transport=auth_transport(fake))
        else:
            receive_callback(code=code, state=st_val)
    assert fake.calls == []  # no token exchange for an invalid callback or a replay
    assert_clean(str(exc.value))
    assert resolve_access_token() is None or case == "replayed_completion"


def test_s19_completion_requires_the_initiating_session_and_a_received_callback(monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", ENV_TOKEN)
    fake = FakeTokenSession()
    _, state = begin_login(session_key="sess-A")
    with pytest.raises(LoginError) as exc:  # no approval received yet
        complete_login(state=state, session_key="sess-A", transport=auth_transport(fake))
    assert "not been received" in str(exc.value).lower() or "approval" in str(exc.value).lower()
    msg = receive_callback(code=AUTH_CODE, state=state)
    assert "original" in msg.lower() and AUTH_CODE not in msg
    with pytest.raises(LoginError) as exc:  # the callback tab (another session) cannot complete
        complete_login(state=state, session_key="sess-B", transport=auth_transport(fake))
    assert "session" in str(exc.value).lower()
    assert fake.calls == [] and resolve_access_token().value == ENV_TOKEN and default_store().read() is None
    assert ua._PENDING[state].used is False  # a wrong-session attempt does not burn the pending login
    result = complete_login(state=state, session_key="sess-A", transport=auth_transport(fake))  # legitimate completion
    assert result.ok and len(fake.calls) == 1 and resolve_access_token().value == NEW_TOKEN


def test_s11_valid_completion_exchanges_server_side_installs_token_and_stops_active_stream(monkeypatch, caplog):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", ENV_TOKEN)
    frames = [market_info_frame(receipt_ms=int(time.time() * 1000) + i) for i in range(5000)]
    start_stream(owner_token="tab", mode=StreamMode.LIVE, live_transport=ScriptedLiveTransport(frames, delay_sec=0.01), policy=FAST)
    deadline = time.time() + 5
    while time.time() < deadline and active_snapshot(owner_token="tab").state != ConnectionState.WAITING_FOR_DATA:
        time.sleep(0.01)
    fake = FakeTokenSession()
    _, state = begin_login(session_key="sess-A")
    for lg in ("", "urllib3", "nifty_lab"):
        logging.getLogger(lg).setLevel(logging.DEBUG)
    with caplog.at_level(logging.DEBUG):
        receive_callback(code=AUTH_CODE, state=state)  # lands in the new tab's session
        assert worker_threads_alive() >= 1  # receiving a callback changes nothing yet
        result = complete_login(state=state, session_key="sess-A", transport=auth_transport(fake))  # original tab completes
    assert result.ok
    call = fake.calls[0]
    assert call["url"] == "https://api.upstox.com/v2/login/authorization/token"
    assert call["data"] == {"code": AUTH_CODE, "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "redirect_uri": REDIRECT, "grant_type": "authorization_code"}
    assert call["headers"].get("Content-Type") == "application/x-www-form-urlencoded"
    tok = resolve_access_token()
    assert tok.value == NEW_TOKEN and tok.source == "managed" and tok.expires_at == expiry_after(tok.issued_at)
    assert read_access_token() == NEW_TOKEN  # existing clients pick up the replacement on their next request
    while worker_threads_alive():
        time.sleep(0.01)
    snap = active_snapshot(owner_token="tab")
    assert snap.state == ConnectionState.STOPPED and snap.fault.code.value == "CREDENTIALS_REPLACED"
    assert_clean(result.message + snap.fault.message)
    for rec in caplog.records:
        assert_clean(rec.getMessage())
    assert state not in ua._PENDING  # consumed; the code is no longer held anywhere


def test_s12_exchange_failure_keeps_existing_credential_and_is_sanitized(monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", ENV_TOKEN)
    body = {"errors": [{"errorCode": "UDAPI100057", "message": f"bad code {AUTH_CODE}", "propertyPath": None}]}
    fake = FakeTokenSession(400, body)
    _, state = begin_login(session_key="s")
    receive_callback(code=AUTH_CODE, state=state)
    with pytest.raises(LoginError) as exc:
        complete_login(state=state, session_key="s", transport=auth_transport(fake))
    assert "authorization code" in str(exc.value).lower()
    assert_clean(str(exc.value))
    assert resolve_access_token().value == ENV_TOKEN  # untouched
    assert default_store().read() is None
    fake2 = FakeTokenSession(200, {"status": "success"})  # malformed success payload changes nothing either
    _, state2 = begin_login(session_key="s")
    receive_callback(code=AUTH_CODE, state=state2)
    with pytest.raises(LoginError):
        complete_login(state=state2, session_key="s", transport=auth_transport(fake2))
    assert resolve_access_token().value == ENV_TOKEN


def test_s13_auth_transport_only_talks_to_the_token_endpoint():
    t = auth_transport(FakeTokenSession())
    with pytest.raises(UpstoxAuthError):
        t.post_token("https://evil.example/v2/login/authorization/token", {"grant_type": "authorization_code"})
    with pytest.raises(UpstoxAuthError):
        t.post_token("https://api.upstox.com/v2/order/place", {"grant_type": "authorization_code"})


def test_s14_pending_logins_are_bounded_and_expire():
    states = [begin_login(session_key="s")[1] for _ in range(ua.MAX_PENDING_LOGINS + 3)]
    assert len(ua._PENDING) == ua.MAX_PENDING_LOGINS
    assert states[0] not in ua._PENDING and states[-1] in ua._PENDING


# ============================================================================ R4 Settings page (AppTest)

PAGE = str(Path(__file__).resolve().parents[1] / "pages" / "10_Settings_and_API_Connections.py")


def _texts(at) -> str:
    return "\n".join([m.value for m in at.markdown] + [c.value for c in at.caption] + [s.value for s in at.success] + [i.value for i in at.info] + [w.value for w in at.warning] + [e.value for e in at.error])


def test_s15_settings_flow_completes_only_in_the_initiating_session(monkeypatch):
    pytest.importorskip("streamlit.testing.v1", exc_type=ImportError)
    from streamlit.testing.v1 import AppTest

    from nifty_lab.ui import upstox_auth_ui as aui

    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", ENV_TOKEN)
    monkeypatch.setattr(aui, "_listener_address", lambda: "127.0.0.1")
    fake = FakeTokenSession()
    monkeypatch.setattr(aui, "UpstoxAuthTransport", lambda: auth_transport(fake))

    at1 = AppTest.from_file(PAGE)
    at1.run(timeout=60)
    assert not at1.exception
    t = _texts(at1)
    assert "Status: not verified" in t and "source: environment" in t
    assert_clean(t)
    next(b for b in at1.button if b.label == "Reconnect Upstox").click().run(timeout=60)
    assert not at1.exception and len(ua._PENDING) == 1
    state = next(iter(ua._PENDING))
    assert any(b.label.startswith("Complete reconnection") for b in at1.button)

    # callback lands in a different tab/session: nothing is exchanged or installed there
    at2 = AppTest.from_file(PAGE)
    at2.query_params["code"] = AUTH_CODE
    at2.query_params["state"] = state
    at2.run(timeout=60)
    assert not at2.exception
    assert "code" not in at2.query_params and "state" not in at2.query_params
    assert fake.calls == [] and default_store().read() is None
    assert "original" in _texts(at2).lower()
    assert_clean(_texts(at2))

    # replaying the callback is rejected
    at3 = AppTest.from_file(PAGE)
    at3.query_params["code"] = AUTH_CODE
    at3.query_params["state"] = state
    at3.run(timeout=60)
    assert not at3.exception and any("already" in e.value for e in at3.error) and fake.calls == []

    # the initiating tab completes explicitly
    next(b for b in at1.button if b.label.startswith("Complete reconnection")).click().run(timeout=60)
    assert not at1.exception
    assert len(fake.calls) == 1 and fake.calls[0]["data"]["code"] == AUTH_CODE
    t = _texts(at1)
    assert "Upstox reconnected" in t and "source: managed" in t and "03:30" in t
    assert_clean(t)
    assert resolve_access_token().value == NEW_TOKEN


def test_s16_oauth_processing_refused_unless_listener_is_loopback(monkeypatch):
    pytest.importorskip("streamlit.testing.v1", exc_type=ImportError)
    from streamlit.testing.v1 import AppTest

    from nifty_lab.ui import upstox_auth_ui as aui

    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", ENV_TOKEN)
    fake = FakeTokenSession()
    monkeypatch.setattr(aui, "UpstoxAuthTransport", lambda: auth_transport(fake))
    _, state = begin_login(session_key="x")
    frames = [market_info_frame(receipt_ms=int(time.time() * 1000) + i) for i in range(5000)]
    start_stream(owner_token="tab", mode=StreamMode.LIVE, live_transport=ScriptedLiveTransport(frames, delay_sec=0.01), policy=FAST)
    for address in (None, "", "0.0.0.0", "192.168.1.20"):
        monkeypatch.setattr(aui, "_listener_address", lambda a=address: a)
        at = AppTest.from_file(PAGE)
        at.query_params["code"] = AUTH_CODE
        at.query_params["state"] = state
        at.run(timeout=60)
        assert not at.exception
        assert not any(b.label == "Reconnect Upstox" for b in at.button)
        assert "code" not in at.query_params
        assert fake.calls == [] and default_store().read() is None and ua._PENDING[state].code is None
        assert worker_threads_alive() >= 1  # stream untouched
        assert any("loopback" in e.value.lower() for e in at.error)
    # a client-controlled Host header plays no part in the decision
    monkeypatch.setattr(aui, "_listener_address", lambda: "0.0.0.0")
    assert aui.oauth_access_allowed() is False
    monkeypatch.setattr(aui, "_listener_address", lambda: "::1")
    assert aui.oauth_access_allowed() is True
