"""Upstox authentication lifecycle (Spec 16): managed token store, value-free status, OAuth reconnect.

Facts from the official docs (checked 2026-11-14):
- Authorization-code flow: GET https://api.upstox.com/v2/login/authorization/dialog?client_id&redirect_uri&response_type=code&state,
  then POST https://api.upstox.com/v2/login/authorization/token (form: code, client_id, client_secret, redirect_uri,
  grant_type=authorization_code) → access_token. No refresh grant exists.
- An access_token is valid until 03:30 (IST) the following day regardless of issue time.

Secret handling: token values live only in the managed store file (0600, atomic replace) or the process environment.
No function here logs, prints or returns token values except `resolve_access_token()`/`read_access_token()` callers
that need the header; `ResolvedToken.__repr__` hides the value.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import secrets
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from urllib.parse import urlencode, urlparse
from zoneinfo import ZoneInfo

import requests

from ..config import PROJECT_ROOT, _PLACEHOLDER_MARKERS
from .upstox_errors import UpstoxAuthError

_LOG = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

TOKEN_STORE_ENV = "NSL_TOKEN_STORE"
DEFAULT_TOKEN_STORE = PROJECT_ROOT / "data" / "secrets" / "upstox_token.json"
DIALOG_URL = "https://api.upstox.com/v2/login/authorization/dialog"
TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"
STATE_TTL_SEC = 600.0
MAX_PENDING_LOGINS = 5
AUTH_TIMEOUT = (3.0, 10.0)

ENV_CLIENT_ID = "UPSTOX_API_KEY"
ENV_CLIENT_SECRET = "UPSTOX_API_SECRET"
ENV_REDIRECT_URI = "UPSTOX_REDIRECT_URI"
ENV_ACCESS_TOKEN = "UPSTOX_ACCESS_TOKEN"

_ERROR_MESSAGES = {
    "UDAPI100069": "Upstox rejected the app credentials (API key/secret). Check the app configuration.",
    "UDAPI100070": "Upstox rejected the redirect URI. It must exactly match the URI registered for the app.",
    "UDAPI100057": "Upstox rejected the authorization code (used, expired or invalid). Start Reconnect again.",
}


class AuthStatus(str, Enum):
    NOT_CONFIGURED = "not configured"
    NOT_VERIFIED = "not verified"
    CONNECTED = "connected"
    REAUTH_REQUIRED = "rejected / reauthorization required"


class OAuthNotConfigured(Exception):
    """Reconnect needs UPSTOX_API_KEY, UPSTOX_API_SECRET and UPSTOX_REDIRECT_URI."""


class LoginError(Exception):
    """Callback or exchange failure; message is safe to display (never contains code/token/secret)."""


def fingerprint(token: str) -> str:
    """Non-reversible identifier for a token value (used for rejected/verified marks only)."""
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()[:16]


def expiry_after(issued_at: datetime) -> datetime:
    """Documented rule: valid until 03:30 IST the following day. An issue time before 03:30 expires that same day."""
    local = issued_at.astimezone(IST)
    cutoff = local.replace(hour=3, minute=30, second=0, microsecond=0)
    if local >= cutoff:
        cutoff += timedelta(days=1)
    return cutoff


def _hidden_repr(self) -> str:  # pragma: no cover - trivial
    return f"{type(self).__name__}(source={self.source!r}, fingerprint={self.fingerprint!r}, expires_at={self.expires_at!r})"


@dataclass(frozen=True, repr=False)
class ResolvedToken:
    value: str
    source: str  # "managed" | "environment"
    issued_at: datetime | None
    expires_at: datetime | None
    fingerprint: str

    __repr__ = _hidden_repr


@dataclass(frozen=True)
class AuthSummary:
    status: AuthStatus
    source: str | None
    expires_at: datetime | None
    expiry_known: bool
    detail: str


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _write_private(path: Path, payload: dict) -> None:
    """Atomic replace with 0600 on the file and 0700 on the directory. A failure leaves any existing file intact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.RLock:
    """All TokenStore instances for the same file share one in-process lock (default_store() is called per caller)."""
    key = str(path.resolve()) if path.exists() else str(path.absolute())
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


class _StoreLock:
    """In-process RLock + advisory OS file lock (fcntl.flock) so competing threads *and* processes serialize
    every read-modify-write of the shared state. Supported deployment: Linux/macOS single host."""

    def __init__(self, path: Path) -> None:
        self._rlock = _lock_for(path)
        self._lockfile = path.with_name(path.name + ".lock")
        self._fd: int | None = None

    def __enter__(self):
        self._rlock.acquire()
        self._lockfile.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(self._lockfile, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(self._fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc) -> None:
        try:
            if self._fd is not None:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
        finally:
            self._fd = None
            self._rlock.release()


class TokenStore:
    """Server-side managed token (one file) plus value-free marks keyed by fingerprint (sibling state file).

    Marks are durable and one-directional: `rejected` and `expired` are never cleared by a later success, so a delayed
    2xx from an in-flight request cannot resurrect a credential that the broker has rejected or that has expired."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.state_path = self.path.with_name("upstox_auth_state.json")
        self._lock = _StoreLock(self.path)

    # -- token ------------------------------------------------------------
    def read(self) -> ResolvedToken | None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError):
            return None
        value = raw.get("access_token")
        if not isinstance(value, str) or not value.strip():
            return None
        issued = datetime.fromisoformat(raw["issued_at"]) if raw.get("issued_at") else None
        expires = datetime.fromisoformat(raw["expires_at"]) if raw.get("expires_at") else None
        return ResolvedToken(value=value.strip(), source="managed", issued_at=issued, expires_at=expires, fingerprint=fingerprint(value))

    def install(self, token: str, *, issued_at: datetime, source: str) -> None:
        payload = {"access_token": token.strip(), "issued_at": issued_at.isoformat(), "expires_at": expiry_after(issued_at).isoformat(), "source": source}
        with self._lock:
            _write_private(self.path, payload)

    def clear(self) -> None:
        with self._lock:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass

    # -- marks ------------------------------------------------------------
    def _state(self) -> dict:
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _update_state(self, key: str, fp: str) -> None:
        with self._lock:  # read-modify-write under the shared lock: no competing write can drop a mark
            state = self._state()
            state.setdefault(key, {}).setdefault(fp, _utcnow().isoformat())
            _write_private(self.state_path, state)

    def mark_rejected(self, fp: str) -> None:
        self._update_state("rejected", fp)

    def mark_expired(self, fp: str) -> None:
        self._update_state("expired", fp)

    def mark_verified(self, fp: str) -> None:
        self._update_state("verified", fp)  # never clears rejected/expired

    def is_rejected(self, fp: str) -> bool:
        return fp in self._state().get("rejected", {})

    def is_unusable(self, fp: str) -> bool:
        """Rejected by the broker or known-expired — regardless of which source presents the token now."""
        state = self._state()
        return fp in state.get("rejected", {}) or fp in state.get("expired", {})

    def verified_at(self, fp: str) -> datetime | None:
        raw = self._state().get("verified", {}).get(fp)
        return datetime.fromisoformat(raw) if raw else None


def default_store() -> TokenStore:
    return TokenStore(Path(os.getenv(TOKEN_STORE_ENV) or DEFAULT_TOKEN_STORE))


def _env_token() -> ResolvedToken | None:
    val = os.getenv(ENV_ACCESS_TOKEN, "").strip()
    if not val or any(m in val.lower() for m in _PLACEHOLDER_MARKERS):
        return None
    return ResolvedToken(value=val, source="environment", issued_at=None, expires_at=None, fingerprint=fingerprint(val))


def resolve_access_token(store: TokenStore | None = None, *, now: datetime | None = None) -> ResolvedToken | None:
    """Precedence: managed store (unexpired, not rejected) > environment token (not rejected) > none.
    A rejected or expired credential is never returned, so no caller can retry with it."""
    store = store or default_store()
    now = now or _utcnow()
    managed = store.read()
    if managed is not None:
        if managed.expires_at is not None and now >= managed.expires_at:
            store.mark_expired(managed.fingerprint)  # durable: an identical environment token can never revive it
        elif not store.is_unusable(managed.fingerprint):
            return managed
    env = _env_token()
    # A *different* environment credential is a documented fallback: it has no issuance metadata (expiry unknown)
    # and stays "not verified" until a 2xx; a rejected or known-expired value is never returned from any source.
    if env is not None and not store.is_unusable(env.fingerprint):
        return env
    return None


def auth_status(store: TokenStore | None = None, *, now: datetime | None = None) -> AuthSummary:
    store = store or default_store()
    now = now or _utcnow()
    managed, env = store.read(), _env_token()
    if managed is None and env is None:
        return AuthSummary(AuthStatus.NOT_CONFIGURED, None, None, False, "No Upstox access token configured. Use Reconnect Upstox (or set UPSTOX_ACCESS_TOKEN in .env for the initial path).")
    if managed is not None and managed.expires_at is not None and now >= managed.expires_at:
        if env is None or store.is_unusable(env.fingerprint):
            return AuthSummary(AuthStatus.REAUTH_REQUIRED, "managed", managed.expires_at, True, f"Managed token expired at {managed.expires_at.astimezone(IST):%Y-%m-%d %H:%M} IST (documented 03:30 IST daily expiry). Reconnect Upstox.")
    active = resolve_access_token(store, now=now)
    if active is None:
        return AuthSummary(AuthStatus.REAUTH_REQUIRED, None, None, False, "The configured token was rejected by Upstox. Reconnect Upstox; the rejected token will not be retried.")
    if active.source == "managed":
        exp = active.expires_at.astimezone(IST) if active.expires_at else None
        expiry_text = f"expires {exp:%Y-%m-%d %H:%M} IST (03:30 IST daily rule)" if exp else "expiry unknown"
    else:
        expiry_text = "expiry unknown (environment token has no issuance metadata)"
    verified = store.verified_at(active.fingerprint)
    if verified is not None:
        return AuthSummary(AuthStatus.CONNECTED, active.source, active.expires_at, active.expires_at is not None, f"Last authenticated broker call succeeded at {verified.astimezone(IST):%H:%M:%S} IST; {expiry_text}.")
    return AuthSummary(AuthStatus.NOT_VERIFIED, active.source, active.expires_at, active.expires_at is not None, f"Token present ({active.source}) but no authenticated call has succeeded yet; {expiry_text}.")


def note_response(authorization_header: str | None, status_code: int, store: TokenStore | None = None) -> None:
    """Transport hook: 401/403 marks the presented token rejected; a 2xx marks it verified. Value-free."""
    if not authorization_header or not authorization_header.startswith("Bearer "):
        return
    fp = fingerprint(authorization_header[len("Bearer ") :])
    store = store or default_store()
    if status_code in (401, 403):
        store.mark_rejected(fp)
    elif 200 <= status_code < 300:
        store.mark_verified(fp)


def connection_generation(store: TokenStore | None = None) -> int:
    """Non-secret cache generation: 0 when no usable token, else derived from the active token's fingerprint."""
    tok = resolve_access_token(store)
    return 0 if tok is None else 1 + int(tok.fingerprint, 16) % 1_000_000_007


# --------------------------------------------------------------------------- OAuth reconnect

@dataclass(frozen=True)
class OAuthConfig:
    client_id: str
    client_secret: str
    redirect_uri: str

    @classmethod
    def from_env(cls) -> OAuthConfig:
        missing = [n for n in (ENV_CLIENT_ID, ENV_CLIENT_SECRET, ENV_REDIRECT_URI) if not os.getenv(n, "").strip()]
        if missing:
            raise OAuthNotConfigured(f"Reconnect Upstox needs {', '.join(missing)} in the local .env (values are never shown).")
        return cls(os.environ[ENV_CLIENT_ID].strip(), os.environ[ENV_CLIENT_SECRET].strip(), os.environ[ENV_REDIRECT_URI].strip())


@dataclass
class PendingLogin:
    session_key: str  # the Streamlit session that clicked Reconnect; only it may complete
    created_mono: float
    used: bool = False
    code: str | None = None  # held in process memory only between callback receipt and completion


_PENDING: dict[str, PendingLogin] = {}
_PENDING_LOCK = threading.Lock()


def begin_login(*, session_key: str, mono: float | None = None) -> tuple[str, str]:
    """Return (dialog_url, state). State is 32 random bytes (url-safe), single-use, expires after STATE_TTL_SEC."""
    cfg = OAuthConfig.from_env()
    state = secrets.token_urlsafe(32)
    now = time.monotonic() if mono is None else mono
    with _PENDING_LOCK:
        for st_key in [k for k, p in _PENDING.items() if now - p.created_mono > STATE_TTL_SEC or p.used]:
            _PENDING.pop(st_key, None)
        while len(_PENDING) >= MAX_PENDING_LOGINS:
            _PENDING.pop(next(iter(_PENDING)))
        _PENDING[state] = PendingLogin(session_key=session_key, created_mono=now)
    url = f"{DIALOG_URL}?{urlencode({'client_id': cfg.client_id, 'redirect_uri': cfg.redirect_uri, 'response_type': 'code', 'state': state})}"
    return url, state


def _pending_locked(state: str | None, now: float) -> PendingLogin:
    if not state:
        raise LoginError("Reconnect callback is missing its state. Start Reconnect Upstox again.")
    pending = _PENDING.get(state)
    if pending is None or pending.used:
        raise LoginError("Reconnect state is unknown or was already used. Start Reconnect Upstox again.")
    if now - pending.created_mono > STATE_TTL_SEC:
        _PENDING.pop(state, None)
        raise LoginError("Reconnect expired (10 minute limit). Start Reconnect Upstox again.")
    return pending


def receive_callback(*, code: str | None, state: str | None, mono: float | None = None) -> str:
    """Step 1 (any session, typically the new tab Upstox redirected to): validate and hold the code for the initiating
    session. Exchanges nothing, installs nothing, stops nothing. Returns a safe instruction for the operator."""
    now = time.monotonic() if mono is None else mono
    if not code:
        raise LoginError("Reconnect callback is missing its authorization code. Start Reconnect Upstox again.")
    with _PENDING_LOCK:
        pending = _pending_locked(state, now)
        if pending.code is not None:
            raise LoginError("This approval was already received. Complete it from the original Settings tab, or start again.")
        pending.code = code
    return "Approval received. Return to the original Settings tab that started this reconnect and click Complete reconnection. You can close this tab."


def pending_for_session(session_key: str, *, mono: float | None = None) -> tuple[str, bool] | None:
    """(state, approval_received) for the unused, unexpired login this session initiated, else None."""
    now = time.monotonic() if mono is None else mono
    with _PENDING_LOCK:
        for state, p in _PENDING.items():
            if p.session_key == session_key and not p.used and now - p.created_mono <= STATE_TTL_SEC:
                return state, p.code is not None
    return None


@dataclass(frozen=True)
class LoginResult:
    ok: bool
    message: str


class UpstoxAuthTransport:
    """Narrowly scoped POST client for the token endpoint only. Not an order channel; unaffected by the order guard."""

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()

    def post_token(self, url: str, form: dict[str, str]) -> dict:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "api.upstox.com" or parsed.path != urlparse(TOKEN_URL).path:
            raise UpstoxAuthError("Auth transport only posts to the Upstox token endpoint.")
        try:
            resp = self.session.post(url, data=form, headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}, timeout=AUTH_TIMEOUT, allow_redirects=False)
        except requests.RequestException as exc:
            raise UpstoxAuthError("Network error while contacting Upstox token endpoint.") from exc
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        if resp.status_code != 200:
            code = None
            errors = payload.get("errors") if isinstance(payload, dict) else None
            if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                code = errors[0].get("errorCode")
            raise UpstoxAuthError(_ERROR_MESSAGES.get(code or "", f"Upstox token endpoint returned HTTP {resp.status_code}."))
        return payload if isinstance(payload, dict) else {}


def _stop_active_stream() -> None:
    from ..stream_chart.stream_session import stop_for_credential_change  # local import: avoid import cycle

    stop_for_credential_change()


def complete_login(*, state: str | None, session_key: str, transport: UpstoxAuthTransport, store: TokenStore | None = None, mono: float | None = None) -> LoginResult:
    """Step 2, only in the session that started the login: consume the held code (single-use), exchange it server-side,
    stop any active stream, install atomically. Any failure leaves the existing credential untouched."""
    now = time.monotonic() if mono is None else mono
    with _PENDING_LOCK:
        pending = _pending_locked(state, now)
        if pending.session_key != session_key:
            raise LoginError("This reconnect was started from a different session. Complete it from the Settings tab that started it.")
        if pending.code is None:
            raise LoginError("Upstox approval has not been received yet. Finish the login in the Upstox tab, then click Complete reconnection.")
        pending.used = True  # single-use: consumed before the exchange
        code = pending.code
        _PENDING.pop(state, None)  # the code is no longer held anywhere after this point
    cfg = OAuthConfig.from_env()
    form = {"code": code, "client_id": cfg.client_id, "client_secret": cfg.client_secret, "redirect_uri": cfg.redirect_uri, "grant_type": "authorization_code"}
    try:
        payload = transport.post_token(TOKEN_URL, form)
    except UpstoxAuthError as exc:
        raise LoginError(str(exc)) from None
    token = payload.get("access_token")
    if not isinstance(token, str) or not token.strip():
        raise LoginError("Upstox token response did not contain an access token. Nothing was changed.")
    store = store or default_store()
    _stop_active_stream()  # active streams must not continue across a credential change
    store.install(token, issued_at=_utcnow(), source="oauth")
    _LOG.info("upstox: replacement access token installed (managed store); streams stopped; explicit Start required")
    return LoginResult(True, "Upstox reconnected: a new access token is installed. Any running stream was stopped; press Start to resume.")


def reset_login_registry_for_tests() -> None:
    with _PENDING_LOCK:
        _PENDING.clear()
