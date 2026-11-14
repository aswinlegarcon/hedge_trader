# Spec 16 — Real (attended) Upstox reconnect: handoff

**Verdict: BLOCKED** — no real renewal was attempted. Reason: the attended owner login is unavailable in this session, and
the redirect-URI prerequisite is not yet aligned (see owner actions). Nothing was simulated; no exchange was triggered.

- Tested revision: `3f08ff2bc0444222794b09fbb90054b55b986810` (`origin/main`, no application-code changes in this task).
- Timestamps (UTC): preparation checks 09:01–09:03Z on 2026-11-14 (14:31–14:33 IST, Saturday; NSE closed).
- Environment: Linux, Python 3.12.3, `.venv` with declared dependencies, `NSL_FORBID_LIVE_MUTATIONS=1`, Streamlit bound to
  `127.0.0.1` (`.streamlit/config.toml`).

## Prerequisites — required vs observed (non-secret; values never read into this document)

| Prerequisite | Required | Observed | OK |
|---|---|---|---|
| Listener | `server.address = "127.0.0.1"` | set in `.streamlit/config.toml`; live page gate passed (Reconnect controls rendered) | ✅ |
| `UPSTOX_REDIRECT_URI` in `.env` | exactly `http://localhost:8501/Settings_and_API_Connections` | present; scheme http, host loopback (`127.0.0.1`), port 8501, **path is not the Settings page** → not equal | ❌ |
| Upstox app registered redirect URI | exactly the same string | cannot be inspected from here; must equal `.env` byte-for-byte | ❓ owner |
| `UPSTOX_API_KEY`, `UPSTOX_API_SECRET` | present | present (presence only) | ✅ |
| Initial environment token | optional | present; `.env` is `-rw-------` | ✅ |
| Managed store | absent until first reconnect | `data/secrets/upstox_token.json` absent; `data/secrets/` is `drwx------` | ✅ |
| Owner available for the official login | required | not available in this autonomous session | ❌ |

## What was verified on the real dashboard (headless Chromium, loopback, no Upstox page opened)

- Settings → **Upstox authentication** renders `🟢 Status: connected · source: environment`. The `connected` label comes from
  `data/secrets/upstox_auth_state.json` (`verified`: 1 entry, 0600, written 07:56Z): the real dashboard's authenticated
  bootstrap/authorize calls during the Spec 15 later-check smoke were recorded by the Spec 16 transport hook, which was
  already in the working tree at that moment. The label therefore reflects a real successful broker call with the
  environment token, not token presence. No fingerprint or value is reproduced here.
- Clicking **Reconnect Upstox** rendered **Open Upstox login** and **Complete reconnection** with the caption "Waiting for the
  Upstox approval to arrive…". The dialog link targets `api.upstox.com/v2/login/authorization/dialog` with exactly
  `client_id`, `redirect_uri`, `response_type=code`, `state`; its `redirect_uri` is the (misaligned) `.env` value. The link
  was **not** opened; the pending login expired with the process.
- Server log: 43 lines, 0 secret-marker hits (discarded). Captured UI text asserted free of token/URL/state markers.

Not verified (requires the attended flow): callback parameter removal in a real browser round trip, initiating-session-only
completion against a real approval, managed-token installation and permissions on a real token, status after installation,
stream stop on replacement, a bounded read-only request with the managed credential, and stale-environment-token
non-override. All of these have passing offline tests (`tests/test_spec16_auth_lifecycle.py`, 25 passed at this revision)
but **no real-renewal evidence**.

## Streaming verdict (kept separate)

**CONNECTIVITY_ONLY remains the standing verdict** (`docs/spec_15/operator-smoke-handoff.md`). Today is a non-trading day;
the provider reported `CLOSING_END` earlier, so the closed-market smoke was not repeated. Fresh-price and 5m-rollover
verification remain **pending** for a trading-hours session. Not LIVE_DATA_VERIFIED.

## Owner actions (exact, non-secret)

1. Upstox developer portal → the app's **Redirect URI** → set to exactly `http://localhost:8501/Settings_and_API_Connections`.
2. `.env` → `UPSTOX_REDIRECT_URI=http://localhost:8501/Settings_and_API_Connections` (byte-identical to step 1; restart Streamlit once after editing `.env`).
3. If approving from another computer: `ssh -N -L 8501:127.0.0.1:8501 <linux-host>`, then open `http://localhost:8501` there.
4. Attended run (≤ 15 minutes): Settings → **Reconnect Upstox** → **Open Upstox login** (log in and approve on the official page;
   never share the password, OTP, code or token) → the new tab shows "Approval received. Return to the original Settings tab…" →
   back in the **original** tab click **Complete reconnection** → expect "Upstox reconnected…", status source `managed`, expiry
   "03:30 IST" shown, status `not verified` until the first authenticated call → Stream Chart → LIVE → **Start** once (bounded
   read-only request) → **Stop**.
5. Record the sanitized outcome in a follow-up section of this file. If the exchange fails, do not retry more than once; the
   message names the cause (app credentials / redirect URI mismatch / expired code / wrong tab) without values.

## Limitations

- Observations were made with a headless browser on the server itself; the SSH-tunnel path was not exercised.
- The `connected` status predates Spec 16's managed store and refers to the environment token; it will not transfer to a
  managed token, which starts as `not verified` by design.
