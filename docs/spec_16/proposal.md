# Spec 16 — Upstox authentication lifecycle and reconnection

Status: IMPLEMENTED (2026-11-14). Baseline: `main` @ `0adda3c` (Spec 15).

## Why

Upstox access tokens expire at 03:30 IST the following day, every day (official docs). Until now the only path was editing
`.env` and restarting the whole app, and a rejected token kept being retried by every consumer until someone noticed. The
operator smoke (docs/spec_15/operator-smoke-handoff.md) confirmed the LIVE chart works but depends on that daily ritual.

## Scope

- Value-free authentication status in Settings: *not configured · not verified · connected · rejected / reauthorization required*, with expiry shown only from trustworthy metadata (our own issue time + the documented 03:30 IST rule; never decoded JWT claims).
- Explicit **Reconnect Upstox** using the official interactive authorization-code flow; server-side code exchange via a narrowly scoped auth transport; cryptographically random, single-use, expiring `state`.
- Managed token store: server-side, gitignored, 0600, atomic replacement, failure-safe; documented precedence over the environment token; rejected tokens are never retried; active streams are stopped before a credential change and need an explicit Start.
- Operator guide for initial setup, daily reconnection, Linux callback access (SSH tunnel), and LIVE chart use.

## Non-goals

No PIN/TOTP-secret storage, automated browser login, unattended scheduling, orders, Paper fills/ledger writes, strategy or backtest changes, 2025 holdout access, token replication between machines, or any real renewal triggered by automation. `NSL_FORBID_LIVE_MUTATIONS=1` stays; the auth POST is not an order mutation and uses its own transport.

## Flow decision (from the official docs, checked 2026-11-14)

- **Authorization code (implemented):** `GET /v2/login/authorization/dialog` → redirect with `code`/`state` → `POST /v2/login/authorization/token` (form: `code, client_id, client_secret, redirect_uri, grant_type=authorization_code`) → `access_token`. No refresh grant exists; key + secret alone cannot renew a token.
- **Access Token Request (approval-based) — deferred:** requires a notifier webhook configured in the Upstox app to *receive* the token; the documentation specifies no signature or authenticity mechanism for that delivery (payload carries `client_id`, `user_id`, `access_token`, `expires_at`, `issued_at`, `message_type`), and this project has no public HTTPS endpoint. An unauthenticated token-install endpoint would be worse than the daily login. Revisit only if Upstox documents verifiable delivery and a secured endpoint exists.
- **TOTP token endpoint — out of scope** (would require storing PIN/TOTP secrets).
