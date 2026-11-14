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


@pytest.mark.parametrize("case", ["missing_state", "unknown_state", "missing_code", "expired", "replayed"])
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
    elif case == "replayed":
        assert complete_login(code=code, state=state, session_key="sess", transport=auth_transport(fake)).ok
        fake.calls.clear()
    with pytest.raises(LoginError) as exc:
        complete_login(code=code, state=st_val, session_key="sess", transport=auth_transport(fake))
    assert fake.calls == []  # no token exchange for an invalid callback
    assert_clean(str(exc.value))
    assert resolve_access_token() is None or case == "replayed"


def test_s11_valid_callback_exchanges_server_side_installs_token_and_stops_active_stream(monkeypatch, caplog):
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
        result = complete_login(code=AUTH_CODE, state=state, session_key="sess-B", transport=auth_transport(fake))  # callback lands in a new tab/session
    assert result.ok and result.cross_session is True
    call = fake.calls[0]
    assert call["url"] == "https://api.upstox.com/v2/login/authorization/token"
    assert call["data"] == {"code": AUTH_CODE, "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "redirect_uri": REDIRECT, "grant_type": "authorization_code"}
    assert call["headers"].get("Content-Type") == "application/x-www-form-urlencoded"
    tok = resolve_access_token()
    assert tok.value == NEW_TOKEN and tok.source == "managed" and tok.expires_at == expiry_after(tok.issued_at)
    assert read_access_token() == NEW_TOKEN  # existing clients pick up the replacement on their next request
    # the active stream was stopped and must be started explicitly
    while worker_threads_alive():
        time.sleep(0.01)
    snap = active_snapshot(owner_token="tab")
    assert snap.state == ConnectionState.STOPPED and snap.fault.code.value == "CREDENTIALS_REPLACED"
    assert_clean(result.message + snap.fault.message)
    for rec in caplog.records:
        assert_clean(rec.getMessage())


def test_s12_exchange_failure_keeps_existing_credential_and_is_sanitized(monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", ENV_TOKEN)
    body = {"errors": [{"errorCode": "UDAPI100057", "message": f"bad code {AUTH_CODE}", "propertyPath": None}]}
    fake = FakeTokenSession(400, body)
    _, state = begin_login(session_key="s")
    with pytest.raises(LoginError) as exc:
        complete_login(code=AUTH_CODE, state=state, session_key="s", transport=auth_transport(fake))
    assert "authorization code" in str(exc.value).lower()
    assert_clean(str(exc.value))
    assert resolve_access_token().value == ENV_TOKEN  # untouched
    assert default_store().read() is None
    # malformed success payload (no access_token) is also a failure that changes nothing
    fake2 = FakeTokenSession(200, {"status": "success"})
    _, state2 = begin_login(session_key="s")
    with pytest.raises(LoginError):
        complete_login(code=AUTH_CODE, state=state2, session_key="s", transport=auth_transport(fake2))
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

def test_s15_settings_page_shows_status_and_processes_callback_without_exposing_values(monkeypatch):
    pytest.importorskip("streamlit.testing.v1", exc_type=ImportError)
    from streamlit.testing.v1 import AppTest

    from nifty_lab.ui import upstox_auth_ui as aui

    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", ENV_TOKEN)
    monkeypatch.setattr(aui, "_request_host", lambda: "localhost:8501")
    fake = FakeTokenSession()
    monkeypatch.setattr(aui, "UpstoxAuthTransport", lambda: auth_transport(fake))
    page = str(Path(__file__).resolve().parents[1] / "pages" / "10_Settings_and_API_Connections.py")

    at = AppTest.from_file(page)
    at.run(timeout=60)
    assert not at.exception
    page_text = "\n".join(m.value for m in at.markdown) + "\n".join(c.value for c in at.caption)
    assert "Status: not verified" in page_text and "source: environment" in page_text
    assert_clean(page_text)

    # Reconnect → link rendered, state registered
    next(b for b in at.button if b.label == "Reconnect Upstox").click().run(timeout=60)
    assert not at.exception
    assert len(ua._PENDING) == 1
    state = next(iter(ua._PENDING))

    # Callback arrives (new session in practice): code/state in query params → exchanged, cleared, token installed
    at2 = AppTest.from_file(page)
    at2.query_params["code"] = AUTH_CODE
    at2.query_params["state"] = state
    at2.run(timeout=60)
    assert not at2.exception
    assert "code" not in at2.query_params and "state" not in at2.query_params
    assert fake.calls and fake.calls[0]["data"]["code"] == AUTH_CODE
    assert any("Upstox reconnected" in s.value for s in at2.success)
    text2 = "\n".join(m.value for m in at2.markdown) + "\n".join(c.value for c in at2.caption) + "\n".join(s.value for s in at2.success)
    assert "source: managed" in text2 and "03:30" in text2
    assert_clean(text2)
    assert resolve_access_token().value == NEW_TOKEN

    # replaying the same callback is rejected and changes nothing
    at3 = AppTest.from_file(page)
    at3.query_params["code"] = AUTH_CODE
    at3.query_params["state"] = state
    at3.run(timeout=60)
    assert not at3.exception and any("already used" in e.value for e in at3.error)
    assert len(fake.calls) == 1


def test_s16_reconnect_controls_hidden_off_loopback(monkeypatch):
    pytest.importorskip("streamlit.testing.v1", exc_type=ImportError)
    from streamlit.testing.v1 import AppTest

    from nifty_lab.ui import upstox_auth_ui as aui

    monkeypatch.setattr(aui, "_request_host", lambda: "192.168.1.20:8501")
    page = str(Path(__file__).resolve().parents[1] / "pages" / "10_Settings_and_API_Connections.py")
    at = AppTest.from_file(page)
    at.run(timeout=60)
    assert not at.exception
    assert not any(b.label == "Reconnect Upstox" for b in at.button)
    assert any("localhost" in i.value for i in at.info)
