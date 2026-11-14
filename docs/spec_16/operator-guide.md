# Operator guide — Upstox authentication and LIVE chart

Never paste tokens, API secrets or authorization codes into chat, tickets, screenshots or this repository.

## 1. One-time setup
1. In the Upstox developer app, set the **redirect URI** to exactly `http://localhost:8501/Settings_and_API_Connections`.
2. In the project `.env` (gitignored, `chmod 600 .env`): `UPSTOX_API_KEY`, `UPSTOX_API_SECRET`, and `UPSTOX_REDIRECT_URI=http://localhost:8501/Settings_and_API_Connections` (byte-identical to step 1). `UPSTOX_ACCESS_TOKEN` is optional: if set, it is used until a managed token is installed or Upstox rejects it.
3. Start the dashboard on the Linux server: `export NSL_FORBID_LIVE_MUTATIONS=1 && .venv/bin/python3.12 -m streamlit run app.py`.

## 2. Reaching the dashboard (Linux callback access)
The dashboard listens on **loopback only** (`.streamlit/config.toml`: `[server] address = "127.0.0.1"`). Reconnect is refused if the listener is bound anywhere else.
- On the server itself: open `http://localhost:8501`.
- From another computer: `ssh -N -L 8501:127.0.0.1:8501 <linux-host>` then open `http://localhost:8501` in that computer's browser. The OAuth redirect to `localhost:8501` reaches the server through the tunnel. Do not put a reverse proxy in front of the dashboard for this flow.
- Whoever can open an SSH session to the server account is the operator; the dashboard itself does not authenticate users.

## 3. Daily reconnection (tokens expire 03:30 IST every day)
1. Settings & API Connections → **Upstox authentication** shows the status (never a value). "rejected / reauthorization required" or an expiry in the past means reconnect.
2. Click **Reconnect Upstox**, then **Open Upstox login**. Log in and approve on Upstox; it opens in a new tab and redirects that tab back to Settings, which shows "Approval received. Return to the original Settings tab…". Nothing is installed yet.
3. Go back to the **original** Settings tab and click **Complete reconnection (approval received)**. Only that tab can complete; the exchange happens server-side there. The page shows "Upstox reconnected…" and the status source becomes `managed` with the expiry time. The approval is single-use and valid for 10 minutes.
4. Any running LIVE stream is stopped by the replacement (`CREDENTIALS_REPLACED`). Open **Stream Chart** and press **Start** again.
5. If completion fails, the message names the cause (app credentials, redirect URI mismatch, expired code, wrong tab) without any values. The previous working credential is never destroyed by a failed attempt; a rejected or expired token is never retried, even if the same value is also present in `.env`.

## 4. LIVE chart use
Stream Chart → mode **LIVE** → **Start**. Read the auto-refreshing status block: `Connection`, `Price FRESH/STALE` with source/progress ages, provider exchange status, reconnect count. Press **Stop** before closing the tab; an abandoned tab is expired automatically after 20 s and the slot is released. Follow the bounded runbook in `docs/spec_15/handoff.md` for any attended verification.

## 5. What is deliberately not automated
No PIN/TOTP storage, no scripted browser login, no unattended daily scheduling, no webhook token delivery (no verifiable authenticity in the current provider docs), no token replication between machines.
