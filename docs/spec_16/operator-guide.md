# Operator guide — Upstox authentication and LIVE chart

Never paste tokens, API secrets or authorization codes into chat, tickets, screenshots or this repository.

## 1. One-time setup
1. In the Upstox developer app, set the **redirect URI** to exactly `http://localhost:8501/Settings_and_API_Connections`.
2. In the project `.env` (gitignored, `chmod 600 .env`): `UPSTOX_API_KEY`, `UPSTOX_API_SECRET`, and `UPSTOX_REDIRECT_URI=http://localhost:8501/Settings_and_API_Connections` (byte-identical to step 1). `UPSTOX_ACCESS_TOKEN` is optional: if set, it is used until a managed token is installed or Upstox rejects it.
3. Start the dashboard on the Linux server: `export NSL_FORBID_LIVE_MUTATIONS=1 && .venv/bin/python3.12 -m streamlit run app.py`.

## 2. Reaching the dashboard (Linux callback access)
- On the server itself: open `http://localhost:8501`.
- From another computer: `ssh -N -L 8501:127.0.0.1:8501 <linux-host>` then open `http://localhost:8501` in that computer's browser. The OAuth redirect to `localhost:8501` now reaches the server through the tunnel. Reconnect controls are hidden when the page is opened via any non-loopback host.

## 3. Daily reconnection (tokens expire 03:30 IST every day)
1. Settings & API Connections → **Upstox authentication** shows the status (never a value). "rejected / reauthorization required" or an expiry in the past means reconnect.
2. Click **Reconnect Upstox**, then **Open Upstox login**; log in and approve on Upstox (same browser). You are redirected back to Settings; the page shows "Upstox reconnected…" and the status source becomes `managed` with the expiry time. The link is single-use and valid for 10 minutes.
3. Any running LIVE stream is stopped by the replacement (`CREDENTIALS_REPLACED`). Open **Stream Chart** and press **Start** again.
4. If the status still says rejected after a successful reconnect, the server-side exchange failed: the message names the cause (app credentials, redirect URI mismatch, or expired code) without any values. Fix the configuration and retry; the previous working credential is never destroyed by a failed attempt.

## 4. LIVE chart use
Stream Chart → mode **LIVE** → **Start**. Read the auto-refreshing status block: `Connection`, `Price FRESH/STALE` with source/progress ages, provider exchange status, reconnect count. Press **Stop** before closing the tab; an abandoned tab is expired automatically after 20 s and the slot is released. Follow the bounded runbook in `docs/spec_15/handoff.md` for any attended verification.

## 5. What is deliberately not automated
No PIN/TOTP storage, no scripted browser login, no unattended daily scheduling, no webhook token delivery (no verifiable authenticity in the current provider docs), no token replication between machines.
