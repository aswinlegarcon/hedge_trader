# Design — Spec 16

## Components

- `nifty_lab/brokers/upstox_auth.py` — `TokenStore` (managed token file + sibling state file of fingerprint marks), `resolve_access_token()` (precedence), `auth_status()` (value-free summary), `note_response()` (transport hook), `begin_login()/complete_login()` (OAuth), `UpstoxAuthTransport` (token-endpoint-only POST), `expiry_after()`.
- `nifty_lab/brokers/upstox_market_data.py` — `read_access_token()`, `_token_present()`, `connection_generation()` now delegate to the store; every existing consumer (candles, news, overlay, research runners, stream bootstrap/authorize) therefore picks up a replacement token on its next request.
- `nifty_lab/brokers/upstox_transport.py` — after each response calls `note_response(Authorization, status)`; 401/403 text now says "Reconnect Upstox in Settings & API Connections".
- `nifty_lab/stream_chart/stream_session.py` — `stop_for_credential_change()` (owner-independent request-stop with fault `CREDENTIALS_REPLACED`); `sanitize_exception` passes through our own static `UpstoxAuthError` guidance.
- `nifty_lab/ui/upstox_auth_ui.py` — Settings section (listener gate, receive/complete); `pages/10_Settings_and_API_Connections.py` renders it. `.streamlit/config.toml` binds the listener to `127.0.0.1`.

## Token store

Path `data/secrets/upstox_token.json` (override `NSL_TOKEN_STORE`), JSON `{access_token, issued_at, expires_at, source}`. Write: `mkstemp` in the same directory, `fchmod 0600`, fsync, `os.replace`; directory `chmod 0700`. Any failure before `replace` unlinks the temp file and leaves the previous file untouched. State file `upstox_auth_state.json` holds `{rejected: {fp: ts}, verified: {fp: ts}}` where `fp = sha256(token)[:16]` — never a value. The store is local to the machine; nothing replicates it.

Precedence: managed (unexpired, not rejected) → environment (`UPSTOX_ACCESS_TOKEN`, not placeholder, not rejected) → none. Because the managed token wins, a stale environment token cannot override a newly installed one; because rejections are recorded by fingerprint, a rejected environment token is never retried even after the managed token is cleared.

Status: *not configured* (no candidate) · *rejected / reauthorization required* (expired managed without usable env, or every candidate rejected) · *connected* (the active token's fingerprint has a 2xx mark) · *not verified* (otherwise). Expiry text only for managed tokens (`issued_at` + 03:30 IST rule); environment tokens say "expiry unknown".

## OAuth

`begin_login(session_key)` → `secrets.token_urlsafe(32)` state stored process-locally with the initiating session key and a monotonic timestamp; TTL 600 s; at most 5 pending (oldest evicted). Exchange via `UpstoxAuthTransport.post_token` (https + host + path allowlisted, form-encoded, 3 s/10 s timeouts, error codes `UDAPI100069/100070/100057` mapped to fixed messages, bodies never echoed). See the two-step binding below.

### Access boundary (not authentication by header)

OAuth initiation **and** callback processing run only when the Streamlit listener itself is bound to a loopback address:
`oauth_access_allowed()` reads `server.address` from server configuration (`.streamlit/config.toml` now sets
`address = "127.0.0.1"`), never from client-controlled headers. If the listener is not loopback (unset, `0.0.0.0`, a LAN
address), the Settings page clears any `code`/`state` from the URL, refuses the callback, hides the controls and shows the
configuration instruction. Assumptions this relies on: the dashboard is not fronted by a reverse proxy; remote operators
reach it through an SSH tunnel (`ssh -N -L 8501:127.0.0.1:8501 <host>`), so the operator identity is the host's SSH/OS
account. This is a network boundary plus OS authentication; the UI performs no authentication of its own and does not
claim to.

### Binding the callback to its initiator

Streamlit cannot set browser cookies, and the Upstox dialog opens in a new tab, so the redirect always lands in a *new*
Streamlit session. The flow is therefore two-step:

1. `receive_callback(code, state)` — any session (the new tab): validates state (known, unused, unexpired) and holds the
   code **in process memory** on the pending record. It exchanges nothing, installs nothing, stops nothing, and rejects a
   second delivery of the same state.
2. `complete_login(state, session_key)` — only the session whose key created the pending record: consumes the code
   (single-use, removed from memory before the exchange), exchanges server-side, stops active streams, installs atomically.
   A wrong session is refused without burning the pending login; a missing approval is refused with guidance.

The session key is the Streamlit session id plus a random nonce that lives only in that session's `session_state`,
so it is stable for the tab, unguessable, and unique even where ids collide. If the callback happens to land in the
initiating session, the UI completes immediately; otherwise it tells the operator to return to the original tab and
click **Complete reconnection**. Credentials are never installed from a session that did not start the reconnect.

### Durable marks and concurrency

`rejected` and `expired` marks are one-directional: `mark_verified` never clears them, so a delayed 2xx from an in-flight
request cannot resurrect a credential the broker rejected. `resolve_access_token` records `expired` for a managed token
once its documented expiry passes, and `is_unusable(fp)` is consulted for **every** source — an identical token supplied
through the environment is not used; a *different* environment credential remains a documented fallback (expiry unknown,
status "not verified" until a 2xx). All instances for the same store path share one in-process `RLock`, and every
read-modify-write of the state file additionally takes an advisory `fcntl.flock` on a sibling `.lock` file, so competing
threads and processes on the same host cannot drop a mark. Supported deployment: single host, Linux/macOS.

## Linux callback access

The owner approves on Upstox from any computer, but the redirect lands in *that* browser. Registered redirect URI and `UPSTOX_REDIRECT_URI` must both be `http://localhost:8501/Settings_and_API_Connections` (or the `127.0.0.1` equivalent — identical strings). When the owner is not on the Linux server, open the dashboard through `ssh -N -L 8501:127.0.0.1:8501 <linux-host>` so `localhost:8501` in the owner's browser *is* the server. No new hosting, no public exposure.

## Guard interaction

`NSL_FORBID_LIVE_MUTATIONS` guards order mutation only. The token POST uses its own transport; order permissions were not broadened.
