# Design — Spec 16

## Components

- `nifty_lab/brokers/upstox_auth.py` — `TokenStore` (managed token file + sibling state file of fingerprint marks), `resolve_access_token()` (precedence), `auth_status()` (value-free summary), `note_response()` (transport hook), `begin_login()/complete_login()` (OAuth), `UpstoxAuthTransport` (token-endpoint-only POST), `expiry_after()`.
- `nifty_lab/brokers/upstox_market_data.py` — `read_access_token()`, `_token_present()`, `connection_generation()` now delegate to the store; every existing consumer (candles, news, overlay, research runners, stream bootstrap/authorize) therefore picks up a replacement token on its next request.
- `nifty_lab/brokers/upstox_transport.py` — after each response calls `note_response(Authorization, status)`; 401/403 text now says "Reconnect Upstox in Settings & API Connections".
- `nifty_lab/stream_chart/stream_session.py` — `stop_for_credential_change()` (owner-independent request-stop with fault `CREDENTIALS_REPLACED`); `sanitize_exception` passes through our own static `UpstoxAuthError` guidance.
- `nifty_lab/ui/upstox_auth_ui.py` — Settings section; `pages/10_Settings_and_API_Connections.py` renders it.

## Token store

Path `data/secrets/upstox_token.json` (override `NSL_TOKEN_STORE`), JSON `{access_token, issued_at, expires_at, source}`. Write: `mkstemp` in the same directory, `fchmod 0600`, fsync, `os.replace`; directory `chmod 0700`. Any failure before `replace` unlinks the temp file and leaves the previous file untouched. State file `upstox_auth_state.json` holds `{rejected: {fp: ts}, verified: {fp: ts}}` where `fp = sha256(token)[:16]` — never a value. The store is local to the machine; nothing replicates it.

Precedence: managed (unexpired, not rejected) → environment (`UPSTOX_ACCESS_TOKEN`, not placeholder, not rejected) → none. Because the managed token wins, a stale environment token cannot override a newly installed one; because rejections are recorded by fingerprint, a rejected environment token is never retried even after the managed token is cleared.

Status: *not configured* (no candidate) · *rejected / reauthorization required* (expired managed without usable env, or every candidate rejected) · *connected* (the active token's fingerprint has a 2xx mark) · *not verified* (otherwise). Expiry text only for managed tokens (`issued_at` + 03:30 IST rule); environment tokens say "expiry unknown".

## OAuth

`begin_login(session_key)` → `secrets.token_urlsafe(32)` state stored process-locally with the initiating Streamlit session id and a monotonic timestamp; TTL 600 s; at most 5 pending (oldest evicted). `complete_login(code, state, session_key, transport)` validates presence, existence, non-use and TTL, then marks the state used **before** exchanging; exchanges via `UpstoxAuthTransport.post_token` (https + host + path allowlisted, form-encoded, 3 s/10 s timeouts, error codes `UDAPI100069/100070/100057` mapped to fixed messages, bodies never echoed); on success stops any active stream, installs the token, returns `LoginResult(ok, message, cross_session)`.

Session binding, honestly: the Upstox dialog opens in a new tab, so the callback necessarily arrives in a *new* Streamlit session; the initiating session id is recorded and surfaced as `cross_session`, but acceptance cannot be tied to a browser identity because Streamlit offers no server-settable cookie. Compensating controls: state randomness, single use, 10-minute TTL, exact registered redirect URI, loopback-only controls (S16), and the exchange happening only inside this process.

The Settings page reads `st.query_params`, immediately clears them, and renders the result; Reconnect controls render only when the request `Host` is `localhost`/`127.0.0.1`/`[::1]` (missing host → hidden, fail-closed).

## Linux callback access

The owner approves on Upstox from any computer, but the redirect lands in *that* browser. Registered redirect URI and `UPSTOX_REDIRECT_URI` must both be `http://localhost:8501/Settings_and_API_Connections` (or the `127.0.0.1` equivalent — identical strings). When the owner is not on the Linux server, open the dashboard through `ssh -N -L 8501:127.0.0.1:8501 <linux-host>` so `localhost:8501` in the owner's browser *is* the server. No new hosting, no public exposure.

## Guard interaction

`NSL_FORBID_LIVE_MUTATIONS` guards order mutation only. The token POST uses its own transport; order permissions were not broadened.
